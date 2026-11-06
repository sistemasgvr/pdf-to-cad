using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;
using Civil3DBasico.Mcp.Aplicacion;
using Civil3DBasico.Mcp.Dominio;
using CivilDB = Autodesk.Civil.DatabaseServices;

// ============================================================================
//  ADAPTADOR de escritura: mover (vertical y en planta), buzones, válvulas y
//  quitar accesorios. Todo dentro de la transacción de `Aplicar` (un paso de U).
// ============================================================================

namespace Civil3DBasico.Mcp.Infraestructura
{
    internal sealed partial class Civil3DEditor
    {
        /// <summary>Mueve una utilidad ENTERA el mismo vector (dx, dy, dz):
        ///  1) las estructuras propias (Position);
        ///  2) las piezas de presión de Civil 3D (Position): al estar conectadas arrastran las puntas de sus tuberías;
        ///  3) cada tubería a su punto FINAL (original + v, medido antes de mover nada), así ninguna se mueve dos veces;
        ///  4) los accesorios SÓLIDOS del plugin (no están conectados): TransformBy + su COORD/COTA en el XDATA.
        /// Al final se comprueba y se avisa en la consola si algo no quedó donde debía.</summary>
        private static void Mover(Database db, Transaction tr, CambioMover c, Editor ed)
        {
            var v = new Vector3d(c.Dx, c.Dy, c.Dz);
            var tubos = new List<(Entity e, Point3d a, Point3d b)>();
            foreach (string h in c.Handles)
            {
                var e = (Entity)tr.GetObject(Existe(db, h), OpenMode.ForWrite);
                if (e is CivilDB.Pipe p) tubos.Add((e, p.StartPoint, p.EndPoint));
                else if (e is CivilDB.PressurePipe pp) tubos.Add((e, pp.StartPoint, pp.EndPoint));
                else throw new ErrorUsuario($"{h} no es una tubería.");
            }
            var estructuras = new List<(CivilDB.Structure s, Point3d pos)>();
            foreach (string h in c.Estructuras)
            {
                ObjectId id = Ids.De(db, h);
                if (!id.IsNull && tr.GetObject(id, OpenMode.ForWrite) is CivilDB.Structure s) estructuras.Add((s, s.Position));
            }
            var piezas = new List<(CivilDB.PressurePart p, Point3d pos)>();
            var solidos = new List<Entity>();
            foreach (string h in c.Accesorios)
            {
                ObjectId id = Ids.De(db, h);
                if (id.IsNull) continue;
                var e = (Entity)tr.GetObject(id, OpenMode.ForWrite);
                if (e is CivilDB.PressurePart pa) piezas.Add((pa, pa.Position));
                else solidos.Add(e);
            }
            foreach (var (s, pos) in estructuras) s.Position = pos + v;
            foreach (var (pa, pos) in piezas) pa.Position = pos + v;
            foreach (var (e, a, b) in tubos)
            {
                if (e is CivilDB.Pipe p) { p.StartPoint = a + v; p.EndPoint = b + v; }
                else if (e is CivilDB.PressurePipe pp) { pp.StartPoint = a + v; pp.EndPoint = b + v; }
            }
            foreach (Entity e in solidos)
            {
                e.TransformBy(Matrix3d.Displacement(v));
                SumarXData(e, c.Dx, c.Dy, c.Dz);
            }
            double peor = 0.0;
            foreach (var (e, a, b) in tubos)
            {
                Point3d s = ((Curve)e).StartPoint, f = ((Curve)e).EndPoint;
                peor = Math.Max(peor, Math.Max(s.DistanceTo(a + v), f.DistanceTo(b + v)));
            }
            foreach (var (pa, pos) in piezas) peor = Math.Max(peor, pa.Position.DistanceTo(pos + v));
            if (peor > 0.01)
                ed.WriteMessage($"\n[IA] ⚠ Al mover la utilidad algo quedó corrido hasta {peor:F2} ft: revisa la unión (U para deshacer).");
        }

        /// <summary>El sólido guarda su punto y cota en el XDATA (los usa el perfil): se corren con él.</summary>
        private static void SumarXData(Entity e, double dx, double dy, double dz)
        {
            using (ResultBuffer rb = e.GetXDataForApplication(Civil3DLector.APP_ACCESORIO))
            {
                if (rb == null) return;
                var nuevos = new List<TypedValue>();
                bool cambio = false;
                foreach (TypedValue tv in rb)
                {
                    string kv = tv.TypeCode == (int)DxfCode.ExtendedDataAsciiString ? tv.Value as string : null;
                    int eq = kv?.IndexOf('=') ?? -1;
                    string clave = eq > 0 ? kv.Substring(0, eq).ToUpperInvariant() : "";
                    double suma = clave == "COORD_X" ? dx : clave == "COORD_Y" ? dy : clave == "COTA_EJE_FT" ? dz : double.NaN;
                    if (!double.IsNaN(suma) && double.TryParse(kv.Substring(eq + 1).Replace(',', '.'), System.Globalization.NumberStyles.Float,
                                                               System.Globalization.CultureInfo.InvariantCulture, out double z))
                    {
                        nuevos.Add(new TypedValue(tv.TypeCode, clave + "=" + (z + suma).ToString("F3", System.Globalization.CultureInfo.InvariantCulture)));
                        cambio = true;
                    }
                    else nuevos.Add(tv);
                }
                if (cambio) using (var nb = new ResultBuffer(nuevos.ToArray())) e.XData = nb;
            }
        }

        private static void Buzon(Database db, Transaction tr, CambioBuzon c)
        {
            if (!(tr.GetObject(Existe(db, c.Handle), OpenMode.ForWrite) is CivilDB.Structure s))
                throw new ErrorUsuario($"{c.Elemento} no es un buzón ni una caja.");
            if (c.Rim.HasValue) s.RimElevation = c.Rim.Value;
            if (c.Sump.HasValue) s.SumpElevation = c.Sump.Value;
        }

        private static void Valvula(Database db, Transaction tr, CambioValvula c, Editor ed)
        {
            string motivo = c.Poner
                ? ComandosRedes.McpPonerValvula(ed, db, tr, c.X, c.Y, c.DirX, c.DirY, c.DiametroIn, c.Union, c.Material)
                : ComandosRedes.McpQuitarValvula(ed, db, tr, new Point2d(c.X, c.Y), c.Solidos, c.Handles);
            if (motivo != null)
            {
                if (c.Poner) throw new ErrorUsuario("No se pudo poner la válvula: " + motivo + ".");
                ed.WriteMessage($"\n[IA] ⚠ Válvula quitada, pero {motivo}.");
            }
        }

        /// <summary>«Aquí no va accesorio»: se borra (pieza o sólidos) y cada tubería que llegaba se alarga por su
        /// recta hasta el centro (sin conectarse: como «No hay accesorio» de la app).</summary>
        private static void QuitarAccesorio(Database db, Transaction tr, CambioQuitarAccesorio c)
        {
            foreach (string h in c.Accesorios)
            {
                ObjectId id = Ids.De(db, h);
                if (!id.IsNull) tr.GetObject(id, OpenMode.ForWrite).Erase();
            }
            var centro = new Point2d(c.X, c.Y);
            foreach (string h in c.Handles)
            {
                ObjectId id = Ids.De(db, h);
                if (id.IsNull) continue;
                var e = (Entity)tr.GetObject(id, OpenMode.ForWrite);
                if (!(e is Curve cv)) continue;
                Point3d a = cv.StartPoint, b = cv.EndPoint;
                bool ini = new Point2d(a.X, a.Y).GetDistanceTo(centro) <= new Point2d(b.X, b.Y).GetDistanceTo(centro);
                Point3d cerca = ini ? a : b, lejos = ini ? b : a;
                Vector3d dir = cerca - lejos;
                double l2 = dir.X * dir.X + dir.Y * dir.Y;
                if (l2 < 1e-12) continue;
                // el punto de su recta (en planta) más cercano al centro, con la cota que sigue su pendiente
                double t = ((c.X - lejos.X) * dir.X + (c.Y - lejos.Y) * dir.Y) / l2;
                Point3d nuevo = lejos + dir * t;
                if (e is CivilDB.Pipe p) { if (ini) p.StartPoint = nuevo; else p.EndPoint = nuevo; }
                else if (e is CivilDB.PressurePipe pp) { if (ini) pp.StartPoint = nuevo; else pp.EndPoint = nuevo; }
            }
        }
    }
}

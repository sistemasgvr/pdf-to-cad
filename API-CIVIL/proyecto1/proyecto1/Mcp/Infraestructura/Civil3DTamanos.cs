using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text.RegularExpressions;
using Autodesk.AutoCAD.DatabaseServices;
using Civil3DBasico.Mcp.Dominio;
using CivilDB = Autodesk.Civil.DatabaseServices;
using Styles = Autodesk.Civil.DatabaseServices.Styles;

// ============================================================================
//  ADAPTADOR: los tubos de la LISTA DE PIEZAS de la red de una tubería (para
//  proponer_tamano) y el cambio de tamaño en sí. Gravedad/conduit: familias y
//  tamaños de la PartsList (SwapPartFamilyAndSize). Presión: tubos de la
//  PressurePartList (SwapPartSize). La «Clave» de cada tamaño solo la entiende
//  este archivo.
// ============================================================================

namespace Civil3DBasico.Mcp.Infraestructura
{
    internal static class Civil3DTamanos
    {
        private static readonly Regex NUM = new Regex(@"(\d+(?:\.\d+)?)", RegexOptions.Compiled);
        private static readonly Regex DIAM = new Regex(@"\d+(?:\.\d+)?\s*(?:in\b|inch\b|pulg\b|"")", RegexOptions.Compiled | RegexOptions.IgnoreCase);

        public static List<TamanoDisponible> De(Transaction tr, Entity tubo)
        {
            var r = new List<TamanoDisponible>();
            if (tubo is CivilDB.Pipe p)
            {
                var net = tr.GetObject(p.NetworkId, OpenMode.ForRead) as CivilDB.Network;
                var pl = net == null || net.PartsListId.IsNull ? null : tr.GetObject(net.PartsListId, OpenMode.ForRead) as Styles.PartsList;
                if (pl == null) return r;
                foreach (ObjectId fid in pl.GetPartFamilyIdsByDomain(CivilDB.DomainType.Pipe))
                {
                    if (!(tr.GetObject(fid, OpenMode.ForRead) is Styles.PartFamily fam)) continue;
                    for (int i = 0; i < fam.PartSizeCount; i++)
                    {
                        if (!(tr.GetObject(fam[i], OpenMode.ForRead) is Styles.PartSize sz)) continue;
                        double d = DiamGravedad(sz);
                        if (d <= 0) continue;
                        r.Add(new TamanoDisponible
                        {
                            Clave = $"G|{fid.Handle}|{fam[i].Handle}", Familia = fam.Name, Nombre = sz.Name, DiametroIn = d,
                            Material = MaterialGravedad(sz, fam),
                        });
                    }
                }
            }
            else if (tubo is CivilDB.PressurePipe pp)
            {
                foreach (Styles.PressurePartSize sz in TubosPresion(tr, pp))
                {
                    string desc = sz.Description ?? "";
                    double d = ComandosPresion.ExtraerDiametroDeDescripcion(desc);
                    if (d <= 0) continue;
                    r.Add(new TamanoDisponible { Clave = "P|" + desc, Familia = SinDiametro(desc), Nombre = desc, DiametroIn = d, Material = SinDiametro(desc) });
                }
            }
            return r;
        }

        /// <summary>Cambia el tamaño. Gravedad: la rasante (solera) queda donde estaba. Presión: el eje no se mueve.</summary>
        public static void Cambiar(Transaction tr, Entity tubo, string clave)
        {
            string[] k = (clave ?? "").Split(new[] { '|' }, 3);
            if (tubo is CivilDB.Pipe p && k.Length == 3 && k[0] == "G")
            {
                Database db = p.Database;
                ObjectId fam = Ids.De(db, k[1]), size = Ids.De(db, k[2]);
                if (fam.IsNull || size.IsNull) throw new Aplicacion.ErrorUsuario("Ese tamaño ya no está en la lista de piezas: volver a proponerlo.");
                double r0 = Civil3DLector.RadioInterior(p);
                double zi = p.StartPoint.Z - r0, zf = p.EndPoint.Z - r0;
                p.SwapPartFamilyAndSize(fam, size);
                double r1 = Civil3DLector.RadioInterior(p);
                var a = p.StartPoint; p.StartPoint = new Autodesk.AutoCAD.Geometry.Point3d(a.X, a.Y, zi + r1);
                var b = p.EndPoint; p.EndPoint = new Autodesk.AutoCAD.Geometry.Point3d(b.X, b.Y, zf + r1);
                return;
            }
            if (tubo is CivilDB.PressurePipe pp && k.Length >= 2 && k[0] == "P")
            {
                string desc = clave.Substring(2);
                foreach (Styles.PressurePartSize sz in TubosPresion(tr, pp))
                    if (string.Equals(sz.Description, desc, StringComparison.Ordinal)) { pp.SwapPartSize(sz); return; }
                throw new Aplicacion.ErrorUsuario("Ese tubo ya no está en la lista de piezas de presión: volver a proponerlo.");
            }
            throw new Aplicacion.ErrorUsuario("No se pudo cambiar el tamaño de esa tubería.");
        }

        private static List<Styles.PressurePartSize> TubosPresion(Transaction tr, CivilDB.PressurePipe pp)
        {
            var net = tr.GetObject(pp.NetworkId, OpenMode.ForRead) as CivilDB.PressurePipeNetwork;
            var pl = net == null || net.PartsListId.IsNull ? null : tr.GetObject(net.PartsListId, OpenMode.ForRead) as Styles.PressurePartList;
            return pl?.GetParts(CivilDB.PressurePartDomainType.Pipe) ?? new List<Styles.PressurePartSize>();
        }

        /// <summary>Diámetro interior en pulgadas. El dato del tamaño puede venir en pies o en pulgadas según el
        /// catálogo: se toma el que se parece al número del nombre («12 inch …»).</summary>
        private static double DiamGravedad(Styles.PartSize sz)
        {
            double? v = Campo(sz, CivilDB.PartContextType.PipeInnerDiameter) ?? Campo(sz, CivilDB.PartContextType.PipeInnerWidth);
            Match mm = NUM.Match(sz.Name ?? "");
            double nombre = mm.Success ? double.Parse(mm.Groups[1].Value, CultureInfo.InvariantCulture) : 0.0;
            if (!v.HasValue || v.Value <= 0) return nombre;
            if (nombre > 0) return Math.Abs(v.Value * 12.0 - nombre) < Math.Abs(v.Value - nombre) ? v.Value * 12.0 : v.Value;
            return v.Value < 6.0 ? v.Value * 12.0 : v.Value;
        }

        private static string MaterialGravedad(Styles.PartSize sz, Styles.PartFamily fam)
        {
            try
            {
                var f = sz.SizeDataRecord?.GetDataFieldBy(CivilDB.PartContextType.Material);
                string m = f?.Value?.ToString();
                if (!string.IsNullOrWhiteSpace(m)) return m;
            }
            catch { }
            return fam.Name;
        }

        private static double? Campo(Styles.PartSize sz, CivilDB.PartContextType ctx)
        {
            try
            {
                var f = sz.SizeDataRecord?.GetDataFieldBy(ctx);
                if (f?.Value != null) return Convert.ToDouble(f.Value, CultureInfo.InvariantCulture);
            }
            catch { }
            return null;
        }

        /// <summary>La descripción del tubo de presión sin su diámetro («pipe-8 in-ductile iron» → «pipe-ductile iron»).</summary>
        public static string SinDiametro(string desc) =>
            Regex.Replace(DIAM.Replace(desc ?? "", ""), @"[-\s]{2,}", "-").Trim(' ', '-');
    }
}

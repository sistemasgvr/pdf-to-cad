using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.Civil;
using CivilDB = Autodesk.Civil.DatabaseServices;
using Exception = System.Exception;

// ============================================================================
//  ETIQUETAS QUE DEPENDEN DEL RANGO FINAL (DISENO.md G.10, G.11-4)
//   · Colocación de callouts y tramos en su destino maquetado moviendo
//     LabelLocation (nunca DraggedOffset), visibilidad de leaders y recreación
//     de los tramos de fila 2 en su ancla definitiva.
//   · «STATION (FT)», estaciones de extremo, título, cotas de recubrimiento,
//     separaciones con cruces y verticales de límite (ProfileViewDepthLabel),
//     y orden de dibujo (MoveToBottom) para que las máscaras los tapen.
// ============================================================================

namespace Civil3DBasico
{
    internal static class PerfilEtiquetasVista
    {
        private static double VE(ContextoPerfil ctx) { return ctx.S / ctx.V; }

        private static CivilDB.ProfileView Pv(Transaction tr, HojaPerfil h)
        {
            if (h.PvId.IsNull) return null;
            try { return (CivilDB.ProfileView)tr.GetObject(h.PvId, OpenMode.ForRead); } catch { return null; }
        }

        /// <summary>Lleva la esquina inferior izquierda de la etiqueta al destino (x, y) del dibujo; true si se movió.</summary>
        private static bool LlevarA(Transaction tr, ObjectId lbl, double x, double y)
        {
            if (!PerfilMaquetacion.MedirEtiqueta(tr, lbl, out Extents3d ext)) return false;
            PerfilMaquetacion.Mover(tr, lbl, new Vector3d(x - ext.MinPoint.X, y - ext.MinPoint.Y, 0));
            return true;
        }

        /// <summary>
        /// G.10-1…3 (T4): mueve cada callout/tramo de la hoja a destino = O + (X0, Y0)·S desde su caja medida (hoja.Medidas),
        /// restaura leaders (callouts/cruces/rasante FromLabelStyle; fila 1 AlwaysHide) y recrea los tramos de fila 2 en (cx, z(YFila1Base)).
        /// </summary>
        internal static void Colocar(Transaction tr, ContextoPerfil ctx, HojaPerfil hoja)
        {
            var pv = Pv(tr, hoja); var r = hoja.Final;
            if (pv == null || r == null) return;
            double s = ctx.S;
            PerfilVista.FindXY(pv, VE(ctx), r.StationStart, r.ElevationMin, out double ox, out double oy);
            foreach (var c in hoja.Callouts.Where(c => !c.EtiquetaId.IsNull && c.Bloque != null && !c.Bloque.Descartado))
            {
                try
                {
                    LlevarA(tr, c.EtiquetaId, ox + c.Bloque.X0 * s, oy + c.Bloque.Y0 * s);
                    var l = (CivilDB.Label)tr.GetObject(c.EtiquetaId, OpenMode.ForWrite);
                    PerfilEtiquetas.Leaders(l, true, true);
                    ctx.Resumen.Callouts++;
                }
                catch (Exception ex) { PerfilLog.Error("COLOCAR", c.Id, ex); }
            }
            foreach (var t in hoja.Rotulos.Where(t => !t.EtiquetaId.IsNull && t.Fila != null && !t.Fila.Omitido && !t.Fila.AVertical))
            {
                try
                {
                    var f = t.Fila;
                    if (f.Fila == 2)
                    {
                        PerfilEtiquetas.Borrar(tr, t.EtiquetaId);
                        t.EtiquetaId = PerfilEtiquetas.CrearStationElevation(tr, hoja.PvId, ctx.Estilos.Tramo, ctx.Estilos.SinMarcador,
                            PerfilDiseno.EstDeX(f.Cx, r, s), PerfilDiseno.ZDeY(r.YFila1Base, r),
                            PerfilDiseno.LineasVariante(f, f.NumLineas).Select(PerfilTextos.Sanear));
                        if (t.EtiquetaId.IsNull) continue;
                    }
                    LlevarA(tr, t.EtiquetaId, ox + f.X0 * s, oy + f.Y0 * s);
                    var l = (CivilDB.Label)tr.GetObject(t.EtiquetaId, OpenMode.ForWrite);
                    PerfilEtiquetas.Leaders(l, f.Fila == 2, false);
                    ctx.Resumen.Rotulos++;
                }
                catch (Exception ex) { PerfilLog.Error("COLOCAR", t.Id, ex); }
            }
        }

        private static ObjectId Texto(Transaction tr, ContextoPerfil ctx, HojaPerfil h, ObjectId estilo, double est, double z, IEnumerable<string> lineas)
        {
            ObjectId id = PerfilEtiquetas.CrearStationElevation(tr, h.PvId, estilo, ctx.Estilos.SinMarcador, est, z, lineas.Select(PerfilTextos.Sanear));
            if (!id.IsNull) h.EtiquetasVista.Add(id);
            return id;
        }

        /// <summary>G.10-4 (T4): crea «STATION (FT)», las estaciones de extremo (si no son múltiplo de EstMayor) y el título, con leaders ocultos. Ids en hoja.</summary>
        internal static void CrearEtiquetasDeVista(Transaction tr, ContextoPerfil ctx, HojaPerfil hoja)
        {
            var r = hoja.Final;
            if (hoja.PvId.IsNull || r == null) return;
            double mayor = ctx.Int.EstMayor;
            hoja.EjeTituloId = Texto(tr, ctx, hoja, ctx.Estilos.EjeTitulo, (r.StationStart + r.StationEnd) / 2.0, r.ElevationMin, new[] { PerfilTextos.TITULO_ESTACION });
            bool NoMultiplo(double e) { double m = Math.Abs(e - Math.Round(e / mayor) * mayor); return m > 0.01; }
            if (NoMultiplo(r.StationStart)) hoja.EstStartId = Texto(tr, ctx, hoja, ctx.Estilos.EstExtremo, r.StationStart, r.ElevationMin, new[] { PerfilTextos.FormatoEstacion(r.StationStart, 0) });
            if (NoMultiplo(r.StationEnd)) hoja.EstEndId = Texto(tr, ctx, hoja, ctx.Estilos.EstExtremo, r.StationEnd, r.ElevationMin, new[] { PerfilTextos.FormatoEstacion(r.StationEnd, 0) });
            var porD = ctx.Rec.Pasos.GroupBy(p => Math.Round(p.Tramo.DiamIn)).Select(g => (d: g.Key, l: g.Sum(p => p.EstHasta - p.EstDesde)));
            double dPred = porD.OrderByDescending(x => x.l).Select(x => x.d).FirstOrDefault();
            var titulo = PerfilTextos.LineasTitulo(ctx.Numero, hoja.Indice + 1, ctx.Hojas.Count, dPred, (ClaseRed)(int)ctx.Red.Tipo, ctx.Red.NombreRed, ctx.S, ctx.V);
            hoja.TituloId = Texto(tr, ctx, hoja, ctx.Estilos.Titulo, r.StationStart, r.ElevationMin, titulo);
        }

        private static ObjectId Cota(Transaction tr, HojaPerfil h, ObjectId estilo, Point2d a, Point2d b)
        {
            if (estilo.IsNull) return ObjectId.Null;
            try
            {
                ObjectId id = CivilDB.ProfileViewDepthLabel.Create(h.PvId, estilo, a, b);
                h.AlFondo.Add(id); h.EtiquetasVista.Add(id);
                return id;
            }
            catch (Exception ex) { PerfilLog.Error("COTA", "ProfileViewDepthLabel", ex); return ObjectId.Null; }
        }

        /// <summary>G.10-5 (T4): cotas de recubrimiento (ProfileViewDepthLabel corona→terreno) en las estaciones de ElegirEstacionesRecubrimiento. Devuelve cuántas.</summary>
        internal static int CrearRecubrimientos(Transaction tr, ContextoPerfil ctx, HojaPerfil hoja)
        {
            var pv = Pv(tr, hoja); var r = hoja.Final; var rec = ctx.Rec;
            if (pv == null || r == null || ctx.SinSuperficie || ctx.Estilos.Profundidad.IsNull) return 0;
            double s = ctx.S;
            var leaders = hoja.Callouts.Where(c => c.Bloque != null && !c.Bloque.Descartado)
                .Select(c => { double e2 = PerfilDiseno.EstDeX(c.Bloque.X0 + c.Bloque.DxEnganche, r, s); return new[] { Math.Min(c.EstAncla, e2), Math.Max(c.EstAncla, e2) }; }).ToList();
            var cruces = hoja.Cruces.Select(i => ctx.Cruces[i]).Select(c => new[] { c.Estacion - c.AltoExtFt, c.Estacion + c.AltoExtFt }).ToList();
            double s3 = double.NaN, minCub = double.MaxValue;
            for (int i = 0; i < rec.TerrenoEst.Length; i++)
            {
                double e = rec.TerrenoEst[i], t = rec.TerrenoZ[i];
                if (double.IsNaN(t) || e < hoja.EstA || e > hoja.EstB) continue;
                double cub = t - PerfilEje.Corona(rec, e);
                if (cub < minCub) { minCub = cub; s3 = e; }
            }
            int n = 0;
            foreach (double e in PerfilDiseno.ElegirEstacionesRecubrimiento(hoja.EstA, hoja.EstB, s, leaders, cruces, s3))
            {
                double t = PerfilEje.TerrenoEn(rec, e), c = PerfilEje.Corona(rec, e);
                if (double.IsNaN(t) || t - c <= 0.10) continue;
                if (!Cota(tr, hoja, ctx.Estilos.Profundidad, P(pv, VE(ctx), e, c), P(pv, VE(ctx), e, t)).IsNull) n++;
            }
            ctx.Resumen.Profundidades += n;
            return n;
        }

        /// <summary>G.10-6 (T4): cotas de separación entre paredes con cruces (|ClaroFt| ≤ 10 y CotaSeparacionCabe). Devuelve cuántas.</summary>
        internal static int CrearSeparaciones(Transaction tr, ContextoPerfil ctx, HojaPerfil hoja)
        {
            var pv = Pv(tr, hoja);
            if (pv == null || ctx.Estilos.Profundidad.IsNull) return 0;
            int n = 0;
            foreach (var c in hoja.Cruces.Select(i => ctx.Cruces[i]).Where(c => c.EtiquetaDelGrupo))
            {
                if (Math.Abs(c.ClaroFt) > 10 || !PerfilDiseno.CotaSeparacionCabe(Math.Abs(c.ClaroFt), ctx.V)) continue;
                double zr = PerfilEje.ZEjeRecorrido(ctx.Rec, c.Estacion), ar = PerfilEje.AltoExtEn(ctx.Rec, c.Estacion);
                double a = c.Encima ? zr + ar / 2 : c.ZEje + c.AltoExtFt / 2, b = c.Encima ? c.ZEje - c.AltoExtFt / 2 : zr - ar / 2;
                if (!Cota(tr, hoja, ctx.Estilos.Profundidad, P(pv, VE(ctx), c.Estacion, a), P(pv, VE(ctx), c.Estacion, b)).IsNull) n++;
            }
            return n;
        }

        /// <summary>G.10-7 (T4): vertical de límite (estilo Limite) en cada pared de hoja.Final.Paredes, de cota(YFila1Base) a corona + 0.05"·S.</summary>
        internal static void CrearLimites(Transaction tr, ContextoPerfil ctx, HojaPerfil hoja)
        {
            var pv = Pv(tr, hoja); var r = hoja.Final;
            if (pv == null || r == null || ctx.Estilos.Limite.IsNull) return;
            double zTope = PerfilDiseno.ZDeY(r.YFila1Base, r);
            foreach (double e in r.Paredes)
            {
                var a = P(pv, VE(ctx), e, zTope);
                var b = P(pv, VE(ctx), e, PerfilEje.Corona(ctx.Rec, e));
                Cota(tr, hoja, ctx.Estilos.Limite, a, new Point2d(b.X, b.Y + 0.05 * ctx.S));
            }
        }

        /// <summary>G.10-8 (T4): MoveToBottom de hoja.AlFondo en el DrawOrderTable del BTR dueño de la vista (ForWrite).</summary>
        internal static void EnviarAlFondo(Transaction tr, HojaPerfil hoja)
        {
            if (hoja.AlFondo.Count == 0 || hoja.PvId.IsNull) return;
            try
            {
                var pv = (CivilDB.ProfileView)tr.GetObject(hoja.PvId, OpenMode.ForRead);
                var btr = (BlockTableRecord)tr.GetObject(pv.OwnerId, OpenMode.ForRead);
                var dot = (DrawOrderTable)tr.GetObject(btr.DrawOrderTableId, OpenMode.ForWrite);
                var ids = new ObjectIdCollection();
                foreach (var id in hoja.AlFondo.Where(i => !i.IsNull && !i.IsErased)) ids.Add(id);
                if (ids.Count > 0) dot.MoveToBottom(ids);
            }
            catch (Exception ex) { PerfilLog.Error("COTA", "orden de dibujo", ex); }
        }

        /// <summary>
        /// G.11-4 (T5): coloca estaciones de extremo, «STATION (FT)» y título respecto a pv.GeometricExtents y al origen del marco
        /// (con el caso sin números mayores). Devuelve cuántas movió.
        /// </summary>
        internal static int ColocarEtiquetasDeVista(Transaction tr, ContextoPerfil ctx, HojaPerfil hoja)
        {
            var pv = Pv(tr, hoja); var r = hoja.Final;
            if (pv == null || r == null || !PerfilVista.ExtentsVista(tr, hoja.PvId, out Extents3d ev)) return 0;
            double s = ctx.S;
            PerfilVista.FindXY(pv, VE(ctx), r.StationStart, r.ElevationMin, out double ox, out double oy);
            int n = 0;
            bool sinNumeros = oy - ev.MinPoint.Y < 0.10 * s;
            if (sinNumeros) PerfilLog.Aviso("VISTA", "Sin números de estación en el rango: extremos alineados al marco");
            void Extremo(ObjectId id, double est)
            {
                if (id.IsNull || !PerfilMaquetacion.MedirEtiqueta(tr, id, out Extents3d e)) return;
                double cx = ox + PerfilDiseno.XMarco(est, r, s) * s;
                double y0 = sinNumeros ? oy - 0.08 * s - (e.MaxPoint.Y - e.MinPoint.Y) : ev.MinPoint.Y;
                if (LlevarA(tr, id, cx - (e.MaxPoint.X - e.MinPoint.X) / 2.0, y0)) n++;
            }
            Extremo(hoja.EstStartId, r.StationStart);
            Extremo(hoja.EstEndId, r.StationEnd);
            double yTituloEje = ev.MinPoint.Y;
            if (!hoja.EjeTituloId.IsNull && PerfilMaquetacion.MedirEtiqueta(tr, hoja.EjeTituloId, out Extents3d et))
            {
                double h = et.MaxPoint.Y - et.MinPoint.Y, w = et.MaxPoint.X - et.MinPoint.X;
                double top = ev.MinPoint.Y - 0.10 * s;
                if (LlevarA(tr, hoja.EjeTituloId, ox + r.AnchoMarco * s / 2.0 - w / 2.0, top - h)) n++;
                yTituloEje = top - h;
            }
            if (!hoja.TituloId.IsNull && PerfilMaquetacion.MedirEtiqueta(tr, hoja.TituloId, out Extents3d tt))
            {
                double h = tt.MaxPoint.Y - tt.MinPoint.Y;
                if (LlevarA(tr, hoja.TituloId, ev.MinPoint.X, yTituloEje - 0.25 * s - h)) n++;
            }
            return n;
        }

        /// <summary>Point2d de (est, z) en la vista vía PerfilVista.FindXY (para ProfileViewDepthLabel).</summary>
        internal static Point2d P(CivilDB.ProfileView pv, double ve, double est, double z)
        {
            PerfilVista.FindXY(pv, ve, est, z, out double x, out double y);
            return new Point2d(x, y);
        }
    }
}

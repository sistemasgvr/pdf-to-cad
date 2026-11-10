using System;
using System.Linq;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using CivilDB = Autodesk.Civil.DatabaseServices;
using Exception = System.Exception;

// ============================================================================
//  VÁLVULAS EN LA VISTA DE PERFIL (2026-11-06, pedido del usuario: «que se vea en el perfil del mismo modo que en
//  la app»). El sólido de la válvula no aparece en una ProfileView (solo las piezas de red), así que se dibuja como
//  en un plano de perfil y como lo dibuja la app (`perfil_vista._valvulas`): el «moño» a lo largo de la tubería con
//  su largo real, el vástago y la CAJA de la válvula (valve box) de la corona hasta la cota CAJA_TOPE_Z (0: aún no
//  hay terreno). Polilíneas en la capa del perfil, colocadas con FindXY (respeta la VE); siguen a su vista
//  (PerfilValvulasSeguir).
//  Fase T5v: después de la maquetación (T2–T5 cambian el rango de las vistas).
// ============================================================================

namespace Civil3DBasico
{
    internal static class PerfilValvulasVista
    {
        private const double MOÑO_MIN_IN = 0.12;   // medio moño mínimo en el ploteo (in), como VALVULA_MIN_PX de la app
        private const double CAJA_MIN_IN = 0.03;   // media caja mínima en el ploteo (in)

        internal static void Dibujar(ContextoPerfil ctx)
        {
            var rec = ctx.Rec;
            if (rec == null || ctx.Hojas.Count == 0) return;
            double ve = ctx.V > 0 ? ctx.S / ctx.V : 1.0;
            int n = 0;
            using (Transaction tr = ctx.Db.TransactionManager.StartTransaction())
            {
                var ms = (BlockTableRecord)tr.GetObject(SymbolUtilityServices.GetBlockModelSpaceId(ctx.Db), OpenMode.ForWrite);
                foreach (var h in ctx.Hojas.Where(h => !h.PvId.IsNull && h.Final != null))
                {
                    CivilDB.ProfileView pv;
                    try { pv = (CivilDB.ProfileView)tr.GetObject(h.PvId, OpenMode.ForRead); } catch { continue; }
                    foreach (int nd in rec.Nodos)
                    {
                        var nodo = rec.Red.Nodos[nd];
                        if (nodo.Tipo != TipoNodo.Accesorio || nodo.Accesorio != TipoAccesorio.Valvula) continue;
                        if (!rec.EstNodo.TryGetValue(nd, out double est)) continue;
                        if (est < h.Final.StationStart - 1e-6 || est > h.Final.StationEnd + 1e-6) continue;
                        try { n += Valvula(tr, ms, ctx, pv, ve, nodo, est); }
                        catch (Exception ex) { PerfilLog.Error("VALVULA", "válvula en " + est.ToString("0.##"), ex); }
                    }
                }
                tr.Commit();
            }
            PerfilLog.Log("VALVULA", n + " válvula(s) dibujadas en el perfil");
            PerfilValvulasSeguir.Activar(ctx.Doc);
            ComandosPerfil.Flush(ctx.Doc);
        }

        private static int Valvula(Transaction tr, BlockTableRecord ms, ContextoPerfil ctx, CivilDB.ProfileView pv, double ve,
                                   NodoPerfil nodo, double est)
        {
            var rec = ctx.Rec;
            double eje = double.IsNaN(nodo.ZEje) ? PerfilEje.ZEjeRecorrido(rec, est) : nodo.ZEje;
            double alto = PerfilEje.AltoExtEn(rec, est);
            if (alto <= 1e-6) alto = (double.IsNaN(nodo.DiamPrincipalIn) ? 8.0 : nodo.DiamPrincipalIn) / 12.0;
            double medio = Math.Max(double.IsNaN(nodo.LargoTotalFt) ? alto / 2 : nodo.LargoTotalFt / 2, MOÑO_MIN_IN * ctx.S);
            double fondo = eje - alto / 2, corona = eje + alto / 2;
            void Poner(bool cerrada, params (double e, double z)[] ez)
            {
                var pl = new Polyline();
                for (int i = 0; i < ez.Length; i++) pl.AddVertexAt(i, PerfilEtiquetasVista.P(pv, ve, ez[i].e, ez[i].z), 0, 0, 0);
                pl.Closed = cerrada;
                if (ctx.Estilos != null && !ctx.Estilos.CapaId.IsNull) pl.LayerId = ctx.Estilos.CapaId;
                pl.ColorIndex = 256;
                ms.AppendEntity(pl);
                tr.AddNewlyCreatedDBObject(pl, true);
                // sigue a su vista si el usuario cambia el rango o la mueve (PerfilValvulasSeguir)
                try { PerfilValvulasSeguir.Etiquetar(tr, ctx.Db, pl, pv.ObjectId, ve, ez.Select(x => new Point2d(x.e, x.z)).ToArray()); }
                catch (Exception ex) { PerfilLog.Error("VALVULA", "XDATA del trazo", ex); }
            }

            // moño: dos triángulos que se tocan en el centro
            Poner(true, (est - medio, fondo), (est, eje), (est - medio, corona));
            Poner(true, (est + medio, fondo), (est, eje), (est + medio, corona));
            // vástago con su tuerca
            double zv = corona + 0.8 * alto;
            Poner(false, (est, eje), (est, zv));
            Poner(false, (est - 0.6 * medio, zv), (est + 0.6 * medio, zv));
            // caja de la válvula: de la corona a la superficie, con su tapa
            if (!double.IsNaN(nodo.CajaTopeZ) && nodo.CajaTopeZ - corona > 1e-6)
            {
                double dIn = double.IsNaN(nodo.CajaDiamIn) || nodo.CajaDiamIn <= 0 ? 5.25 : nodo.CajaDiamIn;
                double r = Math.Max(dIn / 24.0, CAJA_MIN_IN * ctx.S);
                double tope = nodo.CajaTopeZ;
                Poner(true, (est - r, corona), (est + r, corona), (est + r, tope), (est - r, tope));
                Poner(false, (est - 1.8 * r, tope), (est + 1.8 * r, tope));
            }
            return 1;
        }
    }
}

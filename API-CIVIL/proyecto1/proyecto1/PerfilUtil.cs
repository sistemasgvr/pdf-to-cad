using System;
using System.Collections.Generic;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.Civil.ApplicationServices;
using CivilDB = Autodesk.Civil.DatabaseServices;

namespace Civil3DBasico
{
    /// <summary>
    /// Utilidad compartida para las vistas de perfil: ajusta el rango vertical a
    /// [cotaMin - margen, cotaMax + margen] (por defecto margen = 5 m) tomando las
    /// cotas de TODOS los perfiles del eje (rasante y/o terreno), y limita las
    /// estaciones al largo del eje. Así el perfil se ve bien (no aplastado).
    /// </summary>
    internal static class PerfilUtil
    {
        public const double Margen = 5.0;

        public static bool AjustarRango(CivilDB.ProfileView pv, ObjectId alignId, Transaction tr, double margen = Margen)
        {
            if (pv == null) return false;
            CivilDB.Alignment al = tr.GetObject(alignId, OpenMode.ForRead) as CivilDB.Alignment;
            if (al == null) return false;

            double min = double.MaxValue, max = double.MinValue;
            foreach (ObjectId id in al.GetProfileIds())
            {
                try
                {
                    CivilDB.Profile p = tr.GetObject(id, OpenMode.ForRead) as CivilDB.Profile;
                    if (p == null) continue;
                    if (p.ElevationMin < min) min = p.ElevationMin;
                    if (p.ElevationMax > max) max = p.ElevationMax;
                }
                catch { }   // un perfil en estado inválido (p.ej. PVIs degenerados) no debe tumbar el ajuste
            }
            if (min == double.MaxValue) return false;   // no hay perfiles con datos aún

            // Rango vertical: +margen sobre la cota máxima, -margen bajo la mínima
            pv.ElevationRangeMode = CivilDB.ElevationRangeType.UserSpecified;
            pv.ElevationMin = min - margen;
            pv.ElevationMax = max + margen;

            LimpiarBandasYEstaciones(pv, al);
            return true;
        }

        // Crea el perfil de RASANTE de diseño de la red (objeto Profile nativo de
        // Civil3D, no una polilínea manual) con un PVI en cada buzón, en la
        // estación y cota (SumpElevation = fondo de tubería) correspondientes.
        // Devuelve ObjectId.Null si no se pudo crear (no bloquea el resto del flujo).
        public static ObjectId CrearPerfilRasante(CivilDocument civilDoc, Database db, ObjectId alignId,
            List<PerfilLongitudinalDatos.NodoBuzon> nodos, string nombreRed, Transaction tr)
        {
            try
            {
                if (nodos == null || nodos.Count < 2) return ObjectId.Null;
                // Estilo de perfil "Standard" (por nombre, no el primero de la lista al
                // azar) — así el Profile creado se ve con un estilo reconocible y
                // predecible al abrirlo/seleccionarlo en Civil3D.
                ObjectId pStyle = BuscarEstiloPerfilPorNombre(civilDoc, tr, "Standard");
                ObjectId pLabel = civilDoc.Styles.LabelSetStyles.ProfileLabelSetStyles[0];
                ObjectId profId = CivilDB.Profile.CreateByLayout(
                    $"{nombreRed}-rasante", alignId, db.Clayer, pStyle, pLabel);
                if (!profId.IsValid || profId.IsNull) return ObjectId.Null;

                CivilDB.Profile prof = tr.GetObject(profId, OpenMode.ForWrite) as CivilDB.Profile;
                if (prof == null) return ObjectId.Null;

                // Dos buzones muy juntos (quiebre) pueden proyectar casi la misma estación
                // sobre el eje. Un PVI con estación igual o menor al anterior deja el Profile
                // en un estado inválido — luego CUALQUIER lectura (ElevationMin/Max, etc.)
                // truena con "Retrieve attribute failed". Se salta el PVI cuando no avanza
                // lo suficiente, y cada AddPVI va en su propio try/catch por si igual falla.
                const double minSeparacion = 0.05;   // pies
                double ultimaSta = double.NegativeInfinity;
                int agregados = 0;
                foreach (var n in nodos)
                {
                    if (n.Station - ultimaSta < minSeparacion) continue;
                    try { prof.PVIs.AddPVI(n.Station, n.Invert); ultimaSta = n.Station; agregados++; }
                    catch { }
                }
                if (agregados < 2) return ObjectId.Null;

                return profId;
            }
            catch { return ObjectId.Null; }
        }

        // Busca un estilo de perfil por NOMBRE (p.ej. "Standard", el que trae Civil3D
        // por defecto) en vez de tomar ciegamente el primero de la lista — así el
        // Profile creado usa un estilo predecible y reconocible. Si no existe ese
        // nombre en el dibujo (plantilla distinta), cae al primero de la lista.
        private static ObjectId BuscarEstiloPerfilPorNombre(CivilDocument civilDoc, Transaction tr, string nombre)
        {
            ObjectId primero = ObjectId.Null;
            foreach (ObjectId id in civilDoc.Styles.ProfileStyles)
            {
                if (primero.IsNull) primero = id;
                try
                {
                    var st = tr.GetObject(id, OpenMode.ForRead) as CivilDB.Styles.ProfileStyle;
                    if (st != null && string.Equals(st.Name, nombre, StringComparison.OrdinalIgnoreCase))
                        return id;
                }
                catch { }
            }
            return primero;
        }

        private static void LimpiarBandasYEstaciones(CivilDB.ProfileView pv, CivilDB.Alignment al)
        {
            // Quitar TODAS las bandas (Superelevation, Vertical/Horizontal Geometry...) → solo la elevación.
            // Es cosmético: si algo falla, no debe tumbar la creación del perfil.
            try
            {
                CivilDB.ProfileViewBandItemCollection top = pv.Bands.GetTopBandItems();
                for (int i = top.Count - 1; i >= 0; i--) top.RemoveAt(i);
                pv.Bands.SetTopBandItems(top);

                CivilDB.ProfileViewBandItemCollection bot = pv.Bands.GetBottomBandItems();
                for (int i = bot.Count - 1; i >= 0; i--) bot.RemoveAt(i);
                pv.Bands.SetBottomBandItems(bot);
            }
            catch { }

            // Estaciones limitadas al eje
            try
            {
                pv.StationRangeMode = CivilDB.StationRangeType.UserSpecified;
                pv.StationStart = al.StartingStation;
                pv.StationEnd = al.EndingStation;
            }
            catch { }
        }
    }
}

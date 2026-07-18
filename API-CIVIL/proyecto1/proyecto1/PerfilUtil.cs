using Autodesk.AutoCAD.DatabaseServices;
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
                CivilDB.Profile p = tr.GetObject(id, OpenMode.ForRead) as CivilDB.Profile;
                if (p == null) continue;
                if (p.ElevationMin < min) min = p.ElevationMin;
                if (p.ElevationMax > max) max = p.ElevationMax;
            }
            if (min == double.MaxValue) return false;   // no hay perfiles con datos aún

            // Rango vertical: +margen sobre la cota máxima, -margen bajo la mínima
            pv.ElevationRangeMode = CivilDB.ElevationRangeType.UserSpecified;
            pv.ElevationMin = min - margen;
            pv.ElevationMax = max + margen;

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
            return true;
        }
    }
}

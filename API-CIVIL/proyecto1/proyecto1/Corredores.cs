using System;
using System.Collections.Generic;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Runtime;
using Autodesk.Civil.ApplicationServices;
using CivilDB = Autodesk.Civil.DatabaseServices; // alias: objetos de Civil 3D (Corridor, Alignment, Profile...)
using Exception = System.Exception;

// ============================================================================
//  GUÍA RÁPIDA (detalle en README.md, sección 4)
//  - [CommandMethod("X")] = comando que escribes en Civil 3D.
//  - Patrón: doc/ed/db → Transaction → pedir datos (ed.Get...) → crear/leer → Commit.
//  - tr.GetObject(id, ForRead/ForWrite) = "abrir" un objeto por su ObjectId.
//  Jerarquía de un corredor:
//     Corridor  →  Baseline (un eje + su rasante)  →  BaselineRegion (un assembly)
//  Un perfil (Profile) es invisible hasta dibujar una vista de perfil (ProfileView).
// ============================================================================

namespace Civil3DBasico
{
    /// <summary>
    /// Comandos de corredores (Corridor), perfiles/rasantes, vistas de perfil,
    /// superficies del corredor y extracción de sólidos 3D.
    /// Un corredor = Alignment (eje) + Profile (rasante) + Assembly (sección tipo).
    /// El Assembly se arma a mano en Civil 3D; aquí solo se selecciona.
    /// </summary>
    public class ComandosCorredores
    {
        // Margen fijo (m) que se aplica arriba y abajo del rango de datos
        // al crear automáticamente una vista de perfil.
        private const double MargenVista = 5.0;

        // Helper compartido: fija el rango vertical de una vista de perfil a
        // [cotaMin - margen, cotaMax + margen] a partir de los perfiles del eje.
        // Devuelve true si encontró datos y aplicó el rango.
        private bool AjustarRangoVertical(CivilDB.ProfileView pv, ObjectId alignId, double margen, Transaction tr)
        {
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
            if (min == double.MaxValue) return false;   // vista sin perfiles con datos

            pv.ElevationRangeMode = CivilDB.ElevationRangeType.UserSpecified;
            pv.ElevationMin = min - margen;
            pv.ElevationMax = max + margen;
            return true;
        }

        // Deja la vista de perfil "limpia": rango vertical con margen fijo,
        // SIN bandas de datos (solo la elevación) y limitada al largo del eje.
        private void PrepararVistaPerfil(CivilDB.ProfileView pv, ObjectId alignId, Transaction tr)
        {
            // 1) Rango vertical con margen fijo
            AjustarRangoVertical(pv, alignId, MargenVista, tr);

            // 2) Quitar TODAS las bandas (dejar solo la grilla de elevación).
            //    Cosmético -> si algo falla no debe tumbar la creación del perfil.
            try
            {
                CivilDB.ProfileViewBandItemCollection top = pv.Bands.GetTopBandItems();
                for (int i = top.Count - 1; i >= 0; i--) top.RemoveAt(i);
                pv.Bands.SetTopBandItems(top);

                CivilDB.ProfileViewBandItemCollection bot = pv.Bands.GetBottomBandItems();
                for (int i = bot.Count - 1; i >= 0; i--) bot.RemoveAt(i);
                pv.Bands.SetBottomBandItems(bot);
            }
            catch { /* bandas son cosméticas */ }

            // 3) Limitar el rango horizontal al alineamiento (inicio..fin del eje)
            CivilDB.Alignment al = tr.GetObject(alignId, OpenMode.ForRead) as CivilDB.Alignment;
            if (al != null)
            {
                pv.StationRangeMode = CivilDB.StationRangeType.UserSpecified;
                pv.StationStart = al.StartingStation;
                pv.StationEnd = al.EndingStation;
            }
        }

        // Configura la frecuencia de una región para que el corredor siga el eje:
        // secciones cada 'freq' m + secciones en los puntos de geometría del eje y perfil.
        private void ConfigurarFrecuencia(CivilDB.BaselineRegion region, double freq)
        {
            CivilDB.AppliedAssemblySetting fs = region.AppliedAssemblySetting;
            fs.FrequencyAlongTangents = freq;
            fs.FrequencyAlongCurves = freq;
            fs.FrequencyAlongSpirals = freq;
            fs.FrequencyAlongProfileCurves = freq;
            fs.AppliedAtHorizontalGeometryPoints = true;
            fs.AppliedAtProfileGeometryPoints = true;
            fs.AppliedAtProfileHighLowPoints = true;
        }

        // =====================================================================
        // CORREDOR  (Corridor)
        //   Requiere que YA existan en el dibujo: Alignment (eje), Profile
        //   (rasante/terreno de ese eje) y Assembly (sección tipo).
        //   La API de 2026 crea corredor + baseline + región en UNA llamada.
        // =====================================================================
        [CommandMethod("CREAR_CORREDOR")]
        public void CrearCorredor()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            // Alignment (eje horizontal)
            PromptEntityOptions peoA = new PromptEntityOptions("\nSeleccione el Alignment (eje):");
            peoA.SetRejectMessage("\nDebe ser un Alignment.");
            peoA.AddAllowedClass(typeof(CivilDB.Alignment), true);
            PromptEntityResult perA = ed.GetEntity(peoA);
            if (perA.Status != PromptStatus.OK) return;

            // Profile (rasante o terreno de ESE eje)
            PromptEntityOptions peoP = new PromptEntityOptions("\nSeleccione el Profile de ese eje:");
            peoP.SetRejectMessage("\nDebe ser un Profile.");
            peoP.AddAllowedClass(typeof(CivilDB.Profile), true);
            PromptEntityResult perP = ed.GetEntity(peoP);
            if (perP.Status != PromptStatus.OK) return;

            // Assembly (sección tipo)
            PromptEntityOptions peoS = new PromptEntityOptions("\nSeleccione el Assembly (sección tipo):");
            peoS.SetRejectMessage("\nDebe ser un Assembly.");
            peoS.AddAllowedClass(typeof(CivilDB.Assembly), true);
            PromptEntityResult perS = ed.GetEntity(peoS);
            if (perS.Status != PromptStatus.OK) return;

            // Nombre del corredor
            PromptStringOptions pso = new PromptStringOptions("\nNombre del corredor:");
            pso.AllowSpaces = true;
            PromptResult pnr = ed.GetString(pso);
            if (pnr.Status != PromptStatus.OK || string.IsNullOrWhiteSpace(pnr.StringResult)) return;
            string nombre = pnr.StringResult.Trim();

            // Frecuencia: cada cuántos metros se inserta el assembly. Menor = sigue mejor las curvas.
            PromptDoubleOptions pfo = new PromptDoubleOptions("\nFrecuencia (intervalo entre secciones, m):");
            pfo.AllowNegative = false; pfo.AllowZero = false; pfo.DefaultValue = 5.0; pfo.UseDefaultValue = true;
            PromptDoubleResult pfr = ed.GetDouble(pfo);
            if (pfr.Status != PromptStatus.OK) return;
            double freq = pfr.Value;

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    // API 2026: crea corredor + baseline (eje+perfil) + región (assembly) de una vez.
                    // Add(nombreCorredor, nombreBaseline, alignmentId, profileId, nombreRegion, assemblyId)
                    ObjectId corridorId = civilDoc.CorridorCollection.Add(
                        nombre, "BL-1", perA.ObjectId, perP.ObjectId, "R-1", perS.ObjectId);

                    CivilDB.Corridor corridor = (CivilDB.Corridor)tr.GetObject(corridorId, OpenMode.ForWrite);

                    // Configurar la frecuencia para que el corredor siga el trayecto del eje.
                    ConfigurarFrecuencia(corridor.Baselines[0].BaselineRegions[0], freq);

                    corridor.Rebuild();

                    tr.Commit();
                    ed.WriteMessage($"\n✓ Corredor '{nombre}' creado (baseline BL-1, región R-1, frecuencia {freq:F1} m).");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    ed.WriteMessage("\n(Comprueba que el Profile pertenezca al Alignment seleccionado.)");
                    tr.Abort();
                }
            }
        }

        // =====================================================================
        // CORREDOR POR TRAMOS — un baseline por cada tramo recto (ideal para un
        //   canal con esquinas de 90°: así ningún baseline cruza el vértice y cada
        //   tramo sale recto/limpio). Cada tramo es un Alignment + su Profile.
        //   Todos comparten el mismo Assembly (la sección del canal).
        // =====================================================================
        [CommandMethod("CREAR_CORREDOR_TRAMOS")]
        public void CrearCorredorTramos()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            // Nombre del corredor
            PromptStringOptions pso = new PromptStringOptions("\nNombre del corredor (canal):");
            pso.AllowSpaces = true;
            PromptResult pnr = ed.GetString(pso);
            if (pnr.Status != PromptStatus.OK || string.IsNullOrWhiteSpace(pnr.StringResult)) return;
            string nombre = pnr.StringResult.Trim();

            // Assembly (uno solo, compartido por todos los tramos)
            PromptEntityOptions peoS = new PromptEntityOptions("\nSeleccione el Assembly (sección del canal):");
            peoS.SetRejectMessage("\nDebe ser un Assembly.");
            peoS.AddAllowedClass(typeof(CivilDB.Assembly), true);
            PromptEntityResult perS = ed.GetEntity(peoS);
            if (perS.Status != PromptStatus.OK) return;
            ObjectId assemblyId = perS.ObjectId;

            // Frecuencia
            PromptDoubleOptions pfo = new PromptDoubleOptions("\nFrecuencia (intervalo entre secciones, m):");
            pfo.AllowNegative = false; pfo.AllowZero = false; pfo.DefaultValue = 5.0; pfo.UseDefaultValue = true;
            PromptDoubleResult pfr = ed.GetDouble(pfo);
            if (pfr.Status != PromptStatus.OK) return;
            double freq = pfr.Value;

            // Recolectar los tramos: (Alignment, Profile) de cada tramo recto
            var tramos = new List<(ObjectId align, ObjectId profile)>();
            while (true)
            {
                PromptEntityOptions peoA = new PromptEntityOptions($"\nTramo {tramos.Count + 1}: seleccione el Alignment (ESC/Enter para terminar):");
                peoA.SetRejectMessage("\nDebe ser un Alignment.");
                peoA.AddAllowedClass(typeof(CivilDB.Alignment), true);
                peoA.AllowNone = true;
                PromptEntityResult perA = ed.GetEntity(peoA);
                if (perA.Status != PromptStatus.OK) break;   // ESC/Enter -> terminar

                PromptEntityOptions peoP = new PromptEntityOptions("\n   Seleccione el Profile de ESE tramo:");
                peoP.SetRejectMessage("\nDebe ser un Profile.");
                peoP.AddAllowedClass(typeof(CivilDB.Profile), true);
                PromptEntityResult perP = ed.GetEntity(peoP);
                if (perP.Status != PromptStatus.OK) break;

                tramos.Add((perA.ObjectId, perP.ObjectId));
            }

            if (tramos.Count == 0)
            {
                ed.WriteMessage("\nNo se agregó ningún tramo. Operación cancelada.");
                return;
            }

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    // Corredor vacío (solo nombre) y luego un baseline+región por tramo
                    ObjectId corridorId = civilDoc.CorridorCollection.Add(nombre);
                    CivilDB.Corridor corridor = (CivilDB.Corridor)tr.GetObject(corridorId, OpenMode.ForWrite);

                    int i = 1;
                    foreach (var t in tramos)
                    {
                        CivilDB.Baseline bl = corridor.Baselines.Add($"BL-{i}", t.align, t.profile);
                        CivilDB.BaselineRegion region = bl.BaselineRegions.Add($"R-{i}", assemblyId);
                        ConfigurarFrecuencia(region, freq);
                        i++;
                    }

                    corridor.Rebuild();

                    tr.Commit();
                    ed.WriteMessage($"\n✓ Corredor '{nombre}' creado con {tramos.Count} tramo(s) (un baseline por tramo, frecuencia {freq:F1} m).");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    ed.WriteMessage("\n(Cada Profile debe pertenecer al Alignment de su tramo.)");
                    tr.Abort();
                }
            }
        }

        // =====================================================================
        // CORREDOR POR REGIONES — UN solo eje y UNA sola rasante (un baseline),
        //   con varias REGIONES por estación, cada una con su assembly.
        //   Ideal para: mismo trazado que cambia de sección por tramos de estación
        //   (ej. 0–150 sección A, 150–300 sección B). NO divide el alineamiento.
        // =====================================================================
        [CommandMethod("CREAR_CORREDOR_REGIONES")]
        public void CrearCorredorRegiones()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            // Eje (uno) y su rasante (una) — los mismos para todas las regiones
            PromptEntityOptions peoA = new PromptEntityOptions("\nSeleccione el Alignment (eje):");
            peoA.SetRejectMessage("\nDebe ser un Alignment.");
            peoA.AddAllowedClass(typeof(CivilDB.Alignment), true);
            PromptEntityResult perA = ed.GetEntity(peoA);
            if (perA.Status != PromptStatus.OK) return;

            PromptEntityOptions peoP = new PromptEntityOptions("\nSeleccione el Profile (rasante) de ese eje:");
            peoP.SetRejectMessage("\nDebe ser un Profile.");
            peoP.AddAllowedClass(typeof(CivilDB.Profile), true);
            PromptEntityResult perP = ed.GetEntity(peoP);
            if (perP.Status != PromptStatus.OK) return;

            PromptStringOptions pso = new PromptStringOptions("\nNombre del corredor:");
            pso.AllowSpaces = true;
            PromptResult pnr = ed.GetString(pso);
            if (pnr.Status != PromptStatus.OK || string.IsNullOrWhiteSpace(pnr.StringResult)) return;
            string nombre = pnr.StringResult.Trim();

            PromptDoubleOptions pfo = new PromptDoubleOptions("\nFrecuencia (intervalo entre secciones, m):");
            pfo.AllowNegative = false; pfo.AllowZero = false; pfo.DefaultValue = 5.0; pfo.UseDefaultValue = true;
            PromptDoubleResult pfr = ed.GetDouble(pfo);
            if (pfr.Status != PromptStatus.OK) return;
            double freq = pfr.Value;

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    // Rango de estaciones del eje (ayuda)
                    CivilDB.Alignment al = (CivilDB.Alignment)tr.GetObject(perA.ObjectId, OpenMode.ForRead);
                    double s0 = al.StartingStation, s1 = al.EndingStation;
                    ed.WriteMessage($"\nEl eje va de la estación {s0:F3} a {s1:F3}.");

                    // Corredor vacío + UN baseline (eje + rasante)
                    ObjectId corridorId = civilDoc.CorridorCollection.Add(nombre);
                    CivilDB.Corridor corridor = (CivilDB.Corridor)tr.GetObject(corridorId, OpenMode.ForWrite);
                    CivilDB.Baseline bl = corridor.Baselines.Add("BL-1", perA.ObjectId, perP.ObjectId);

                    // Ir agregando regiones: assembly + estación inicio/fin
                    double lastEnd = s0;
                    int i = 1, nReg = 0;
                    while (true)
                    {
                        PromptEntityOptions peoS = new PromptEntityOptions($"\nRegión {i}: seleccione el Assembly (ESC/Enter para terminar):");
                        peoS.SetRejectMessage("\nDebe ser un Assembly.");
                        peoS.AddAllowedClass(typeof(CivilDB.Assembly), true);
                        peoS.AllowNone = true;
                        PromptEntityResult perS = ed.GetEntity(peoS);
                        if (perS.Status != PromptStatus.OK) break;

                        PromptDoubleOptions pIni = new PromptDoubleOptions("\n  Estación inicio:") { AllowNegative = true, DefaultValue = lastEnd, UseDefaultValue = true };
                        PromptDoubleResult rIni = ed.GetDouble(pIni);
                        if (rIni.Status != PromptStatus.OK) break;
                        PromptDoubleOptions pFin = new PromptDoubleOptions("\n  Estación fin:") { AllowNegative = true, DefaultValue = s1, UseDefaultValue = true };
                        PromptDoubleResult rFin = ed.GetDouble(pFin);
                        if (rFin.Status != PromptStatus.OK) break;
                        if (rFin.Value <= rIni.Value) { ed.WriteMessage("\n  La estación fin debe ser mayor que la inicio."); continue; }

                        CivilDB.BaselineRegion region = bl.BaselineRegions.Add($"R-{i}", perS.ObjectId, rIni.Value, rFin.Value);
                        ConfigurarFrecuencia(region, freq);
                        ed.WriteMessage($"\n  + Región R-{i}: {rIni.Value:F2} → {rFin.Value:F2}");
                        lastEnd = rFin.Value; i++; nReg++;
                    }

                    if (nReg == 0) { ed.WriteMessage("\nNo se agregó ninguna región. Cancelado."); tr.Abort(); return; }

                    corridor.Rebuild();
                    tr.Commit();
                    ed.WriteMessage($"\n✓ Corredor '{nombre}' creado con 1 eje/rasante y {nReg} región(es).");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    ed.WriteMessage("\n(El Profile debe pertenecer al Alignment; las estaciones dentro del rango del eje.)");
                    tr.Abort();
                }
            }
        }

        // =====================================================================
        // RUTA A — PERFIL DE TERRENO (EG): proyecta una superficie sobre el eje.
        //   Requiere: Alignment + Superficie (TIN) existentes.
        //   Profile.CreateFromSurface(nombre, alignId, surfaceId, layerId, styleId, labelSetId)
        // =====================================================================
        [CommandMethod("CREAR_PROFILE_TERRENO")]
        public void CrearProfileTerreno()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            // Alignment
            PromptEntityOptions peoA = new PromptEntityOptions("\nSeleccione el Alignment (eje):");
            peoA.SetRejectMessage("\nDebe ser un Alignment.");
            peoA.AddAllowedClass(typeof(CivilDB.Alignment), true);
            PromptEntityResult perA = ed.GetEntity(peoA);
            if (perA.Status != PromptStatus.OK) return;

            // Superficie
            PromptEntityOptions peoS = new PromptEntityOptions("\nSeleccione la Superficie (TIN):");
            peoS.SetRejectMessage("\nDebe ser una superficie TIN.");
            peoS.AddAllowedClass(typeof(CivilDB.TinSurface), true);
            PromptEntityResult perS = ed.GetEntity(peoS);
            if (perS.Status != PromptStatus.OK) return;

            // Nombre
            PromptStringOptions pso = new PromptStringOptions("\nNombre del perfil de terreno:");
            pso.AllowSpaces = true;
            PromptResult pnr = ed.GetString(pso);
            if (pnr.Status != PromptStatus.OK || string.IsNullOrWhiteSpace(pnr.StringResult)) return;
            string nombre = pnr.StringResult.Trim();

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    ObjectId styleId = civilDoc.Styles.ProfileStyles[0];
                    ObjectId labelSetId = civilDoc.Styles.LabelSetStyles.ProfileLabelSetStyles[0];

                    ObjectId profId = CivilDB.Profile.CreateFromSurface(
                        nombre, perA.ObjectId, perS.ObjectId, db.Clayer, styleId, labelSetId);

                    // Verificar que el perfil salió con datos (longitud > 0)
                    CivilDB.Profile p = tr.GetObject(profId, OpenMode.ForRead) as CivilDB.Profile;
                    double len = (p != null) ? p.Length : 0.0;

                    // IMPORTANTE: un perfil es INVISIBLE hasta que se dibuja una vista de perfil.
                    PromptPointResult ppr = ed.GetPoint("\nPunto de inserción para la vista de perfil (ESC para omitir):");
                    if (ppr.Status == PromptStatus.OK)
                    {
                        ObjectId pvId = CivilDB.ProfileView.Create(perA.ObjectId, ppr.Value);
                        CivilDB.ProfileView pvW = (CivilDB.ProfileView)tr.GetObject(pvId, OpenMode.ForWrite);
                        PrepararVistaPerfil(pvW, perA.ObjectId, tr);   // rango + sin bandas + limitado al eje
                    }

                    tr.Commit();
                    ed.WriteMessage($"\n✓ Perfil de terreno '{nombre}' creado (longitud {len:F2} m).");
                    ed.WriteMessage(ppr.Status == PromptStatus.OK
                        ? "\n  Vista de perfil dibujada. (También en Prospector > Alignments > eje > Profiles.)"
                        : "\n  Sin vista. El perfil es DATO del eje (Prospector > Alignments > eje > Profiles), no una entidad suelta.");
                    ed.WriteMessage("\n  Nota: para el CORREDOR necesitas una RASANTE -> usa CREAR_PROFILE_DISENO.");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        // =====================================================================
        // RUTA B — PERFIL DE DISEÑO (rasante FG): línea de diseño por PVIs.
        //   Requiere: solo un Alignment (NO necesita superficie).
        //   Profile.CreateByLayout(...) + profile.PVIs.AddPVI(estacion, cota)
        // =====================================================================
        [CommandMethod("CREAR_PROFILE_DISENO")]
        public void CrearProfileDiseno()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            // Alignment
            PromptEntityOptions peoA = new PromptEntityOptions("\nSeleccione el Alignment (eje):");
            peoA.SetRejectMessage("\nDebe ser un Alignment.");
            peoA.AddAllowedClass(typeof(CivilDB.Alignment), true);
            PromptEntityResult perA = ed.GetEntity(peoA);
            if (perA.Status != PromptStatus.OK) return;

            // Nombre
            PromptStringOptions pso = new PromptStringOptions("\nNombre del perfil de diseño (rasante):");
            pso.AllowSpaces = true;
            PromptResult pnr = ed.GetString(pso);
            if (pnr.Status != PromptStatus.OK || string.IsNullOrWhiteSpace(pnr.StringResult)) return;
            string nombre = pnr.StringResult.Trim();

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    // Rango de estaciones del eje (como ayuda al usuario)
                    CivilDB.Alignment al = (CivilDB.Alignment)tr.GetObject(perA.ObjectId, OpenMode.ForRead);
                    double s0 = al.StartingStation, s1 = al.EndingStation;
                    ed.WriteMessage($"\nEl eje va de la estación {s0:F3} a {s1:F3}. Introduce los PVIs (estación, cota).");

                    ObjectId styleId = civilDoc.Styles.ProfileStyles[0];
                    ObjectId labelSetId = civilDoc.Styles.LabelSetStyles.ProfileLabelSetStyles[0];

                    // Crear perfil de diseño vacío
                    ObjectId profId = CivilDB.Profile.CreateByLayout(nombre, perA.ObjectId, db.Clayer, styleId, labelSetId);
                    CivilDB.Profile profile = (CivilDB.Profile)tr.GetObject(profId, OpenMode.ForWrite);

                    // Ir agregando PVIs hasta que el usuario pulse ESC/Enter en la estación
                    int nPvi = 0;
                    while (true)
                    {
                        PromptDoubleOptions pEst = new PromptDoubleOptions($"\nPVI {nPvi + 1} - Estación (ESC/Enter para terminar):");
                        pEst.AllowNone = true;
                        PromptDoubleResult rEst = ed.GetDouble(pEst);
                        if (rEst.Status != PromptStatus.OK) break;

                        PromptDoubleResult rCota = ed.GetDouble(new PromptDoubleOptions("\n   Cota (elevación):") { AllowNegative = true });
                        if (rCota.Status != PromptStatus.OK) break;

                        profile.PVIs.AddPVI(rEst.Value, rCota.Value);
                        nPvi++;
                    }

                    if (nPvi < 2)
                    {
                        ed.WriteMessage("\nUn perfil necesita al menos 2 PVIs. Operación cancelada.");
                        tr.Abort();
                        return;
                    }

                    // Vista de perfil para ver la rasante (un perfil es invisible sin ella)
                    PromptPointResult ppr = ed.GetPoint("\nPunto de inserción para la vista de perfil (ESC para omitir):");
                    if (ppr.Status == PromptStatus.OK)
                    {
                        ObjectId pvId = CivilDB.ProfileView.Create(perA.ObjectId, ppr.Value);
                        CivilDB.ProfileView pvW = (CivilDB.ProfileView)tr.GetObject(pvId, OpenMode.ForWrite);
                        PrepararVistaPerfil(pvW, perA.ObjectId, tr);   // rango + sin bandas + limitado al eje
                    }

                    tr.Commit();
                    ed.WriteMessage($"\n✓ Rasante '{nombre}' creada con {nPvi} PVIs. Esta SÍ sirve como perfil del CORREDOR.");
                    if (ppr.Status == PromptStatus.OK) ed.WriteMessage("\n  Vista de perfil dibujada.");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        // =====================================================================
        // CREAR_RASANTE_EN_VISTA (Opción B) — diseñas la rasante PINCHANDO puntos
        //   dentro de una Vista de Perfil. Cada clic se convierte a (estación, cota)
        //   con ProfileView.FindStationAndElevationAtXY y se agrega como PVI.
        //   No necesita superficie. El eje sale de la propia vista de perfil.
        // =====================================================================
        [CommandMethod("CREAR_RASANTE_EN_VISTA")]
        public void CrearRasanteEnVista()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            // Seleccionar una Vista de Perfil
            PromptEntityOptions peo = new PromptEntityOptions("\nSeleccione la Vista de Perfil donde dibujar la rasante:");
            peo.SetRejectMessage("\nDebe ser una Vista de Perfil (ProfileView).");
            peo.AddAllowedClass(typeof(CivilDB.ProfileView), true);
            PromptEntityResult per = ed.GetEntity(peo);
            if (per.Status != PromptStatus.OK) return;

            // Nombre de la rasante
            PromptStringOptions pso = new PromptStringOptions("\nNombre de la rasante:");
            pso.AllowSpaces = true;
            PromptResult pnr = ed.GetString(pso);
            if (pnr.Status != PromptStatus.OK || string.IsNullOrWhiteSpace(pnr.StringResult)) return;
            string nombre = pnr.StringResult.Trim();

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    // La vista de perfil sabe a qué eje pertenece
                    CivilDB.ProfileView pv = (CivilDB.ProfileView)tr.GetObject(per.ObjectId, OpenMode.ForRead);
                    ObjectId alignId = pv.AlignmentId;

                    ObjectId styleId = civilDoc.Styles.ProfileStyles[0];
                    ObjectId labelSetId = civilDoc.Styles.LabelSetStyles.ProfileLabelSetStyles[0];

                    // Rasante vacía, ligada a ese eje
                    ObjectId profId = CivilDB.Profile.CreateByLayout(nombre, alignId, db.Clayer, styleId, labelSetId);
                    CivilDB.Profile profile = (CivilDB.Profile)tr.GetObject(profId, OpenMode.ForWrite);

                    ed.WriteMessage("\nPincha los PVIs dentro de la vista (de izquierda a derecha). ESC/Enter para terminar.");
                    int nPvi = 0;
                    while (true)
                    {
                        PromptPointOptions ppo = new PromptPointOptions($"\nPVI {nPvi + 1} (clic en la vista): ");
                        ppo.AllowNone = true;
                        PromptPointResult ppr = ed.GetPoint(ppo);
                        if (ppr.Status != PromptStatus.OK) break;

                        double est = 0, cota = 0;
                        bool dentro = pv.FindStationAndElevationAtXY(ppr.Value.X, ppr.Value.Y, ref est, ref cota);
                        if (!dentro)
                        {
                            ed.WriteMessage("\n  (Ese punto cae fuera de la vista de perfil; ignorado.)");
                            continue;
                        }

                        profile.PVIs.AddPVI(est, cota);
                        nPvi++;
                        ed.WriteMessage($"\n  PVI {nPvi}: estación {est:F3}, cota {cota:F3}");
                    }

                    if (nPvi < 2)
                    {
                        ed.WriteMessage("\nUna rasante necesita al menos 2 PVIs. Operación cancelada.");
                        tr.Abort();
                        return;
                    }

                    // Dejar la vista limpia (rango + sin bandas + limitada al eje), ya con la rasante nueva
                    CivilDB.ProfileView pvW = (CivilDB.ProfileView)tr.GetObject(per.ObjectId, OpenMode.ForWrite);
                    PrepararVistaPerfil(pvW, alignId, tr);

                    tr.Commit();
                    ed.WriteMessage($"\n✓ Rasante '{nombre}' creada con {nPvi} PVIs pinchados. Sirve como perfil del CORREDOR.");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        // =====================================================================
        // CREAR_VISTA_PERFIL — dibuja una vista de perfil VACÍA para un eje.
        //   Útil cuando NO hay superficie: crea el "lienzo" (grilla) para luego
        //   pinchar la rasante con CREAR_RASANTE_EN_VISTA.
        // =====================================================================
        [CommandMethod("CREAR_VISTA_PERFIL")]
        public void CrearVistaPerfil()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;

            PromptEntityOptions peo = new PromptEntityOptions("\nSeleccione el Alignment (eje):");
            peo.SetRejectMessage("\nDebe ser un Alignment.");
            peo.AddAllowedClass(typeof(CivilDB.Alignment), true);
            PromptEntityResult per = ed.GetEntity(peo);
            if (per.Status != PromptStatus.OK) return;

            PromptPointResult ppr = ed.GetPoint("\nPunto de inserción de la vista de perfil:");
            if (ppr.Status != PromptStatus.OK) return;

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    ObjectId pvId = CivilDB.ProfileView.Create(per.ObjectId, ppr.Value);
                    CivilDB.ProfileView pvW = (CivilDB.ProfileView)tr.GetObject(pvId, OpenMode.ForWrite);
                    PrepararVistaPerfil(pvW, per.ObjectId, tr);   // sin bandas + limitada al eje
                    tr.Commit();
                    ed.WriteMessage($"\n✓ Vista de perfil creada (Id: {pvId}). Ahora usa CREAR_RASANTE_EN_VISTA para dibujar la rasante.");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        // =====================================================================
        // AJUSTAR_RANGO_VISTA — fija el rango vertical de una vista de perfil a
        //   [cota mínima - margen, cota máxima + margen] a partir de los perfiles
        //   del eje. Margen configurable (por defecto 5 m).
        // =====================================================================
        [CommandMethod("AJUSTAR_RANGO_VISTA")]
        public void AjustarRangoVista()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;

            // Vista de perfil
            PromptEntityOptions peo = new PromptEntityOptions("\nSeleccione la Vista de Perfil a ajustar:");
            peo.SetRejectMessage("\nDebe ser una Vista de Perfil (ProfileView).");
            peo.AddAllowedClass(typeof(CivilDB.ProfileView), true);
            PromptEntityResult per = ed.GetEntity(peo);
            if (per.Status != PromptStatus.OK) return;

            // Margen (m)
            PromptDoubleOptions pmo = new PromptDoubleOptions("\nMargen por arriba/abajo (m):");
            pmo.AllowNegative = false; pmo.DefaultValue = 5.0; pmo.UseDefaultValue = true;
            PromptDoubleResult pmr = ed.GetDouble(pmo);
            if (pmr.Status != PromptStatus.OK) return;
            double margen = pmr.Value;

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    CivilDB.ProfileView pv = (CivilDB.ProfileView)tr.GetObject(per.ObjectId, OpenMode.ForWrite);

                    if (!AjustarRangoVertical(pv, pv.AlignmentId, margen, tr))
                    {
                        ed.WriteMessage("\nEsa vista no tiene perfiles con datos. Crea primero un perfil o rasante.");
                        tr.Abort();
                        return;
                    }

                    tr.Commit();
                    ed.WriteMessage($"\n✓ Rango vertical fijado: {pv.ElevationMin:F2} a {pv.ElevationMax:F2} (margen {margen:F2} m).");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        // =====================================================================
        // SUPERFICIE DEL CORREDOR — genera una superficie a partir de un código
        //   de enlace del corredor (típico: "Top" = terminado, "Datum" = fondo).
        //   corridor.CorridorSurfaces.Add(nombre) + AddLinkCode(codigo, true) + Rebuild.
        // =====================================================================
        [CommandMethod("CREAR_SUPERFICIE_CORREDOR")]
        public void CrearSuperficieCorredor()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;

            // Corredor
            PromptEntityOptions peo = new PromptEntityOptions("\nSeleccione el Corredor:");
            peo.SetRejectMessage("\nDebe ser un Corredor.");
            peo.AddAllowedClass(typeof(CivilDB.Corridor), true);
            PromptEntityResult per = ed.GetEntity(peo);
            if (per.Status != PromptStatus.OK) return;

            // Nombre de la superficie
            PromptStringOptions pso = new PromptStringOptions("\nNombre de la superficie del corredor:");
            pso.AllowSpaces = true;
            PromptResult pnr = ed.GetString(pso);
            if (pnr.Status != PromptStatus.OK || string.IsNullOrWhiteSpace(pnr.StringResult)) return;
            string nombre = pnr.StringResult.Trim();

            // Código de enlace
            PromptKeywordOptions pko = new PromptKeywordOptions("\nCódigo de enlace: [Top/Datum] <Top>:", "Top Datum");
            pko.AllowNone = true;
            PromptResult rko = ed.GetKeywords(pko);
            if (rko.Status != PromptStatus.OK && rko.Status != PromptStatus.None) return;
            string codigo = (rko.Status == PromptStatus.OK) ? rko.StringResult : "Top";

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    CivilDB.Corridor corridor = (CivilDB.Corridor)tr.GetObject(per.ObjectId, OpenMode.ForWrite);

                    CivilDB.CorridorSurface cs = corridor.CorridorSurfaces.Add(nombre);
                    cs.AddLinkCode(codigo, true);   // true = añadir como breakline
                    corridor.Rebuild();

                    tr.Commit();
                    ed.WriteMessage($"\n✓ Superficie de corredor '{nombre}' creada con el código '{codigo}'.");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    ed.WriteMessage("\n(Verifica que el assembly tenga ese código de enlace, p. ej. 'Top'.)");
                    tr.Abort();
                }
            }
        }

        // =====================================================================
        // SÓLIDOS 3D DEL CORREDOR — extrae sólidos 3D de las FORMAS (shapes) del
        //   assembly a lo largo del corredor. Requiere que el assembly tenga shapes
        //   (áreas cerradas: cuerpo del canal, revestimiento...). corridor.ExportSolids.
        // =====================================================================
        [CommandMethod("EXTRAER_SOLIDOS_CORREDOR")]
        public void ExtraerSolidosCorredor()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;

            PromptEntityOptions peo = new PromptEntityOptions("\nSeleccione el Corredor a convertir en sólidos 3D:");
            peo.SetRejectMessage("\nDebe ser un Corredor.");
            peo.AddAllowedClass(typeof(CivilDB.Corridor), true);
            PromptEntityResult per = ed.GetEntity(peo);
            if (per.Status != PromptStatus.OK) return;

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    CivilDB.Corridor corridor = (CivilDB.Corridor)tr.GetObject(per.ObjectId, OpenMode.ForRead);

                    CivilDB.ExportCorridorSolidsParams p = new CivilDB.ExportCorridorSolidsParams();
                    p.ExportShapes = true;          // exportar las formas (áreas cerradas) como sólidos
                    p.CreateSolidForShape = true;   // crear sólido 3D por cada forma
                    // IMPORTANTE: false = construye el sólido conectando la sección REAL estación a
                    // estación, respetando huecos (canal hueco). Con true (barrido) se rellenaría el hueco.
                    p.SweepSolidForShape = false;
                    p.ExportLinks = false;          // los enlaces son superficies, no sólidos

                    // Exporta al dibujo actual; devuelve los ObjectId de los sólidos creados
                    ObjectIdCollection ids = corridor.ExportSolids(p, db);

                    tr.Commit();
                    ed.WriteMessage($"\n✓ Sólidos 3D extraídos del corredor: {ids.Count}.");
                    if (ids.Count == 0)
                        ed.WriteMessage("\n(0 sólidos: revisa que el assembly del canal tenga FORMAS/shapes cerradas, no solo enlaces.)");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
        }
    }
}

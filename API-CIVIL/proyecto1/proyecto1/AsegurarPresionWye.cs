using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using Microsoft.Data.Sqlite;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using CivilDB = Autodesk.Civil.DatabaseServices;
using PresStyles = Autodesk.Civil.DatabaseServices.Styles;

// ============================================================================
//  Wye reales del catálogo Imperial_AWWA_Steel
//
//  Cuando la detección de junturas encuentra una unión Y (3 tuberías con
//  ángulos ~120°) el orquestador busca en la PressurePartList activa una
//  pieza `PressurePartType.Wye`. Si el usuario no cargó manualmente la
//  familia "Wye ..." del catálogo Imperial_AWWA_Steel en su PartsList,
//  esa búsqueda devuelve null y caemos a Tee. Aquí resolvemos eso: leemos
//  el .sqlite del catálogo, filtramos las familias con ID_TYPE=4 (wye) y
//  las agregamos a la PartsList vía PressurePartList.AddPart(GUID) —
//  el mismo API que usa la UI cuando el usuario tilda una familia.
//
//  Notas de implementación:
//    · La ruta del catálogo se resuelve por versión detectada (2027/26/25/24).
//    · El API AddPart de PressurePartList no está uniformemente expuesto en
//      todas las versiones; se llama por reflexión con manejo defensivo. Si
//      no está disponible, el fallback (Tee) se conserva y se avisa por
//      consola una única vez.
// ============================================================================

namespace Civil3DBasico
{
    internal static class AsegurarPresionWye
    {
        // Nombre del catálogo dentro de <ProgramData>\Autodesk\C3D <year>\enu\Pressure Pipes Catalog\Imperial\
        internal const string CATALOGO = "Imperial_AWWA_Steel";

        // Nombre de la lista de piezas PERSISTENTE que mantiene registrado el
        // catálogo Steel en el dibujo (equivale a "Load new catalog"). No se borra.
        internal const string STEEL_LIST_NAME = "GVR_AWWA_Steel";

        // Lista de piezas COMPLETA del catálogo Steel (tubos + fittings + wye),
        // cuyo catálogo PROPIO es Steel. Las redes de presión la usan para que
        // AddFitting(Wye) funcione sin registro manual (la Y es del catálogo
        // propio de la lista). Decisión del usuario: "red de agua toda en Steel".
        internal const string STEEL_FULL_NAME = "AWWA_Steel";

        // Cache por sesión para no re-leer el SQLite cada juntura.
        private static List<(Guid pid, string famName, string desc, List<double> diams, int angle)> _wyeCache;
        private static bool _addPartTried, _addPartWorks;
        private static bool _nativeSqliteLoaded;

        // Fuerza la carga de la DLL nativa e_sqlite3.dll ANTES de tocar
        // Microsoft.Data.Sqlite. Bajo NETLOAD la carpeta `runtimes/win-x64/
        // native/` no se resuelve automáticamente y el type-initializer de
        // SqliteConnection lanza TypeInitializationException. Con esta carga
        // manual el runtime la encuentra en el AppDomain como si fuera del
        // directorio del ensamblado.
        private static void EnsureSqliteNativeLoaded(Editor ed = null)
        {
            if (_nativeSqliteLoaded) return;
            try
            {
                string asmPath = typeof(AsegurarPresionWye).Assembly.Location;
                string dir = Path.GetDirectoryName(asmPath);
                foreach (string sub in new[] {
                    Path.Combine(dir, "e_sqlite3.dll"),
                    Path.Combine(dir, "runtimes", "win-x64", "native", "e_sqlite3.dll"),
                })
                {
                    if (File.Exists(sub))
                    {
                        System.Runtime.InteropServices.NativeLibrary.Load(sub);
                        ed?.WriteMessage($"\n  · [WYE-LOAD] e_sqlite3.dll cargado manualmente desde: {sub}");
                        _nativeSqliteLoaded = true;
                        return;
                    }
                }
                ed?.WriteMessage($"\n  ⚠ [WYE-LOAD] e_sqlite3.dll no encontrado junto a {asmPath} (ni en runtimes/win-x64/native/).");
            }
            catch (Exception ex)
            {
                ed?.WriteMessage($"\n  ⚠ [WYE-LOAD] Error cargando e_sqlite3.dll: {ex.Message}");
            }
        }

        // Localiza el .sqlite del catálogo Imperial_AWWA_Steel probando TODAS
        // las combinaciones (versión × idioma) instaladas en la máquina.
        // El catálogo binario y sus GUIDs de PART_FAMILY_ID son idénticos entre
        // idiomas (verificado con C3D 2025 esp y C3D 2027 enu), así que
        // cualquier locale que exista sirve. Las carpetas de idioma son
        // subdirectorios directos de "C3D <year>" (ej. enu, esp, deu, fra,
        // ita, jpn, chs, cht, kor, plk, ptb, rus, csy...). Iterando por FS
        // no dependemos de una lista fija de códigos.
        //
        // Prioridad: primero se prefiere el LOCALE con el que la sesión de
        // Civil 3D está corriendo (LCID → carpeta) — así la ruta es la del
        // instalado del usuario, no una carpeta hermana que quizás tenga el
        // catálogo desactualizado —, y de fallback probamos todos los otros.
        internal static string LocalizarSqlite()
        {
            var pd = Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData);
            string autodeskRoot = Path.Combine(pd, "Autodesk");
            if (!Directory.Exists(autodeskRoot)) return null;
            // Orden de versión: la MÁS NUEVA instalada primero, para
            // aprovechar cualquier corrección de catálogo posterior.
            int[] years = new[] { 2027, 2026, 2025, 2024 };
            string prefLocale = LocaleActual();
            foreach (int year in years)
            {
                string yearDir = Path.Combine(autodeskRoot, $"C3D {year}");
                if (!Directory.Exists(yearDir)) continue;
                // 1) Preferir el idioma actual de C3D si esa subcarpeta existe.
                if (!string.IsNullOrEmpty(prefLocale))
                {
                    string cand = Path.Combine(yearDir, prefLocale,
                        $"Pressure Pipes Catalog\\Imperial\\{CATALOGO}.sqlite");
                    if (File.Exists(cand)) return cand;
                }
                // 2) Cualquier otra carpeta de idioma que exista bajo el año.
                foreach (string localeDir in Directory.GetDirectories(yearDir))
                {
                    string cand = Path.Combine(localeDir,
                        $"Pressure Pipes Catalog\\Imperial\\{CATALOGO}.sqlite");
                    if (File.Exists(cand)) return cand;
                }
            }
            return null;
        }

        // Locale-tag de la sesión actual de Civil 3D. Windows expone el LCID
        // del proceso vía CultureInfo — Autodesk usa 3 letras (enu/esp/deu/…)
        // que mapean así. Los planos del cliente pueden estar mezclados, pero
        // la sesión que ejecuta el plugin tiene UN SOLO idioma, y ese es el
        // que tiene el catálogo instalado. Devolvemos "" cuando no hay match
        // (el llamador cae a enumerar carpetas de idioma).
        private static string LocaleActual()
        {
            try
            {
                var lcid = System.Globalization.CultureInfo.InstalledUICulture.LCID;
                // Solo listamos los idiomas de Civil 3D que se distribuyen —
                // basta cubrir esp/enu para el usuario actual; el resto queda
                // como fallback por enumeración de carpetas.
                switch (lcid)
                {
                    case 0x0409: case 0x0009: return "enu"; // English
                    case 0x040A: case 0x0C0A: case 0x080A: case 0x000A: return "esp"; // Español
                    case 0x0407: case 0x0007: return "deu"; // Deutsch
                    case 0x040C: case 0x0007 + 5: return "fra"; // Français (0x040C)
                    case 0x0410: return "ita";  // Italiano
                    case 0x0411: return "jpn";  // 日本語
                    case 0x0804: return "chs";  // 简体中文
                    case 0x0404: return "cht";  // 繁體中文
                    case 0x0412: return "kor";  // 한국어
                    case 0x0415: return "plk";  // Polski
                    case 0x0416: return "ptb";  // Português (BR)
                    case 0x0419: return "rus";  // Русский
                    case 0x0405: return "csy";  // Čeština
                }
            }
            catch { }
            return "";
        }

        // Lee todos los TAMAÑOS Wye del catálogo — una entrada por PID (size)
        // porque PressurePartList.GetPart(guidString) consume el GUID de
        // tamaño, no el de familia. Cada tamaño trae su GUID (PID), el nombre
        // de familia, la descripción legible, el diámetro nominal y el ángulo
        // (parseado del nombre "Wye 30_ BV_ ..."). Devuelve TODOS los sizes
        // (típicamente ~116 en Imperial_AWWA_Steel: 5 familias × ~23 diámetros).
        internal static List<(Guid pid, string famName, string desc, List<double> diams, int angle)> LeerWyes(Editor edLog = null)
        {
            if (_wyeCache != null) return _wyeCache;
            var lista = new List<(Guid, string, string, List<double>, int)>();
            string sqlite = LocalizarSqlite();
            if (sqlite == null)
            {
                edLog?.WriteMessage("\n  ⚠ [WYE-LOAD] LocalizarSqlite() devolvió null (¿no está instalado el catálogo Imperial?).");
                _wyeCache = lista; return lista;
            }
            try
            {
                if (!File.Exists(sqlite))
                {
                    edLog?.WriteMessage($"\n  ⚠ [WYE-LOAD] File.Exists = false para: {sqlite}");
                    _wyeCache = lista; return lista;
                }
                EnsureSqliteNativeLoaded(edLog);
                var cs = new SqliteConnectionStringBuilder
                { DataSource = sqlite, Mode = SqliteOpenMode.ReadOnly }.ToString();
                using var conn = new SqliteConnection(cs);
                conn.Open();
                // ID_TYPE = 4 = "wye" en WA_BRANCH_FITTING_TYPE_TBD.
                // Leemos el PID (GUID de TAMAÑO, no de familia) — PressurePartList
                // .GetPart(guidString) consume el PID del tamaño individual.
                using var cmd = conn.CreateCommand();
                cmd.CommandText = @"SELECT PID, PART_FAMILY_NAME, DESCRIPTION, DIAMETER_NOMINAL
                                    FROM WA_BRANCH_FITTING_MODEL WHERE ID_TYPE = 4";
                int nRows = 0, nGuidFail = 0;
                using (var rd = cmd.ExecuteReader())
                {
                    while (rd.Read())
                    {
                        nRows++;
                        string gs = rd.IsDBNull(0) ? "" : rd.GetString(0);
                        if (!Guid.TryParse(gs, out Guid g)) { nGuidFail++; continue; }
                        string fn = rd.IsDBNull(1) ? "" : rd.GetString(1);
                        string dsc = rd.IsDBNull(2) ? "" : rd.GetString(2);
                        string dn = rd.IsDBNull(3) ? "" : rd.GetString(3);
                        var diams = ExtraerDiams(dn);
                        int ang = ExtraerAngulo(fn);
                        lista.Add((g, fn, dsc, diams, ang));
                    }
                }
                edLog?.WriteMessage($"\n  · [WYE-LOAD] SQL retornó {nRows} tamaño(s) con ID_TYPE=4; {lista.Count} agregados a la lista; {nGuidFail} PID inválido(s).");
            }
            catch (Exception exSq)
            {
                edLog?.WriteMessage($"\n  ⚠ [WYE-LOAD] Excepción leyendo SQLite: {exSq.GetType().Name}: {exSq.Message}");
            }
            _wyeCache = lista;
            return lista;
        }

        // Asegura que la PartsList activa tenga cargadas TODAS las familias Wye
        // del catálogo Imperial_AWWA_Steel. Idempotente: si la familia ya
        // aparece entre los fittings actuales, no la vuelve a agregar. Devuelve
        // el número de familias nuevas realmente agregadas.
        // Alias público del método de carga — mismo comportamiento que
        // AsegurarEnPartsList pero con nombre explícito para invocarlo desde
        // PREPARAR_FAMILIAS_STEP2 (el botón "Preparar familias" del panel).
        // Construye (o reusa) la Parts List COMPLETA de Steel: catálogo propio
        // Steel + todos los tubos y fittings del catálogo. Devuelve su ObjectId
        // (ObjectId.Null si falla). Idempotente: si ya existe y tiene tubos, la
        // reusa. Es lo que usan las redes de presión de agua.
        internal static ObjectId ConstruirListaSteelCompleta(
            PresStyles.PressurePartListCollection plc, Transaction tr, Editor ed)
        {
            if (plc == null || tr == null) return ObjectId.Null;
            string sqlite = LocalizarSqlite();
            if (string.IsNullOrEmpty(sqlite))
            {
                ed?.WriteMessage("\n  ⚠ [STEEL-FULL] No encontré Imperial_AWWA_Steel.sqlite.");
                return ObjectId.Null;
            }

            // ¿Ya existe?
            ObjectId existente = ObjectId.Null;
            for (int i = 0; i < plc.Count; i++)
            {
                var p = tr.GetObject(plc[i], OpenMode.ForRead) as PresStyles.PressurePartList;
                if (p != null && string.Equals(p.Name, STEEL_FULL_NAME, StringComparison.OrdinalIgnoreCase))
                { existente = plc[i]; break; }
            }
            if (existente != ObjectId.Null)
            {
                var p = tr.GetObject(existente, OpenMode.ForRead) as PresStyles.PressurePartList;
                int nT = p?.GetParts(CivilDB.PressurePartDomainType.Pipe)?.Count ?? 0;
                int nF = p?.GetParts(CivilDB.PressurePartDomainType.Fitting)?.Count ?? 0;
                if (nT > 0 && nF > 0)
                {
                    ed?.WriteMessage($"\n  · [STEEL-FULL] Reusando '{STEEL_FULL_NAME}' ({nT} tubos, {nF} fittings).");
                    return existente;
                }
            }

            // Activar catálogo Steel y crear/abrir la lista (su .Catalog será Steel).
            ActivarCatalogo(ed);
            PresStyles.PressurePartList lista;
            ObjectId listaId;
            if (existente != ObjectId.Null)
            { listaId = existente; lista = tr.GetObject(listaId, OpenMode.ForWrite) as PresStyles.PressurePartList; }
            else
            {
                listaId = plc.Add(STEEL_FULL_NAME);
                lista = tr.GetObject(listaId, OpenMode.ForWrite) as PresStyles.PressurePartList;
                ed?.WriteMessage($"\n  · [STEEL-FULL] Creada lista '{STEEL_FULL_NAME}' (catálogo Steel).");
            }
            if (lista == null) return ObjectId.Null;

            object cat = lista.GetType().GetProperty("Catalog")?.GetValue(lista);
            if (cat == null)
            {
                ed?.WriteMessage("\n  ⚠ [STEEL-FULL] La lista no expuso catálogo Steel.");
                return listaId;
            }
            var tCatT = cat.GetType();
            var mGetParts = tCatT.GetMethod("GetParts",
                BindingFlags.Public | BindingFlags.Instance, null,
                new[] { typeof(CivilDB.PressurePartDomainType) }, null);
            if (mGetParts == null) return listaId;

            try { lista.UpgradeOpen(); } catch { }
            int totalAdd = 0;
            foreach (var dom in new[] { CivilDB.PressurePartDomainType.Pipe,
                                        CivilDB.PressurePartDomainType.Fitting })
            {
                List<PresStyles.PressurePartSize> catParts;
                try
                {
                    object lo = mGetParts.Invoke(cat, new object[] { dom });
                    catParts = ((System.Collections.IEnumerable)lo).Cast<PresStyles.PressurePartSize>().ToList();
                }
                catch (Exception ex)
                { ed?.WriteMessage($"\n  ⚠ [STEEL-FULL] GetParts({dom}) falló: {ex.InnerException?.Message ?? ex.Message}"); continue; }

                var yaHay = new HashSet<string>(
                    (lista.GetParts(dom) ?? new List<PresStyles.PressurePartSize>())
                        .Select(f => (f.Description ?? "").Trim().ToLowerInvariant()),
                    StringComparer.OrdinalIgnoreCase);
                int add = 0, err = 0;
                foreach (var ps in catParts)
                {
                    if (ps == null) continue;
                    string d = (ps.Description ?? "").Trim().ToLowerInvariant();
                    if (yaHay.Contains(d)) continue;
                    try { lista.AddPart(ps); yaHay.Add(d); add++; }
                    catch { err++; }
                }
                totalAdd += add;
                ed?.WriteMessage($"\n  · [STEEL-FULL] {dom}: {add} agregadas ({err} error(es)).");
            }
            ed?.WriteMessage($"\n  · [STEEL-FULL] Total agregado a '{STEEL_FULL_NAME}': {totalAdd}.");
            return listaId;
        }

        // Elige la PressurePartList de trabajo para redes de PRESIÓN: SIEMPRE
        // "Standard" (creada por la plantilla → sí construye piezas). Nunca las
        // listas auxiliares creadas por código (AWWA_Steel / GVR_*), que Civil 3D
        // no puede instanciar (AddLinePipe/AddFitting → "Fail to add ...").
        internal static ObjectId ElegirPartsListStandard(
            PresStyles.PressurePartListCollection plc, Transaction tr)
        {
            if (plc == null || plc.Count == 0 || tr == null) return ObjectId.Null;
            ObjectId first = ObjectId.Null, nonHelper = ObjectId.Null;
            for (int i = 0; i < plc.Count; i++)
            {
                var p = tr.GetObject(plc[i], OpenMode.ForRead) as PresStyles.PressurePartList;
                if (p == null) continue;
                if (first == ObjectId.Null) first = plc[i];
                if (string.Equals(p.Name, "Standard", StringComparison.OrdinalIgnoreCase))
                    return plc[i];
                bool esAux = string.Equals(p.Name, STEEL_LIST_NAME, StringComparison.OrdinalIgnoreCase)
                          || string.Equals(p.Name, STEEL_FULL_NAME, StringComparison.OrdinalIgnoreCase)
                          || (p.Name ?? "").StartsWith("GVR_", StringComparison.OrdinalIgnoreCase);
                if (nonHelper == ObjectId.Null && !esAux) nonHelper = plc[i];
            }
            return nonHelper != ObjectId.Null ? nonHelper : first;
        }

        // Activa (globalmente) el catálogo Imperial_AWWA_Steel como catálogo de
        // presión "actual" — equivale al botón "Load new catalog". Necesario ANTES
        // de net.AddFitting() de una pieza Wye: la geometría de la Wye vive en el
        // .sqlite de Steel, y si el catálogo activo es otro (p.ej. PushOn, que es
        // el propio de la lista Standard), AddFitting lanza "Fail to add a new
        // fitting.". Las piezas PushOn siguen resolviéndose por ser el catálogo
        // propio de la lista, así que dejar Steel activo no rompe Tees/Elbows.
        internal static bool ActivarCatalogo(Editor ed = null)
        {
            string sqlite = LocalizarSqlite();
            if (string.IsNullOrEmpty(sqlite)) return false;
            try
            {
                var asm = typeof(PresStyles.PressurePartList).Assembly;
                var tCat = asm.GetType("Autodesk.Civil.DatabaseServices.Styles.PressurePartCatalog");
                var mSet = tCat?.GetMethod("SetCatalog",
                    BindingFlags.Public | BindingFlags.Static, null, new[] { typeof(string) }, null);
                if (mSet == null) return false;
                mSet.Invoke(null, new object[] { sqlite });
                return true;
            }
            catch (Exception ex)
            {
                ed?.WriteMessage($"\n  ⚠ [WYE] ActivarCatalogo falló: {ex.InnerException?.Message ?? ex.Message}");
                return false;
            }
        }

        internal static int CargarWyesEnPartsList(PresStyles.PressurePartList pl,
            List<PresStyles.PressurePartSize> fittingsExistentes,
            Transaction tr, PresStyles.PressurePartListCollection plc, Editor ed)
            => AsegurarEnPartsList(pl, fittingsExistentes, tr, plc, ed);

        internal static int AsegurarEnPartsList(PresStyles.PressurePartList pl,
            List<PresStyles.PressurePartSize> fittingsExistentes,
            Transaction tr, PresStyles.PressurePartListCollection plc, Editor ed)
        {
            _wyeCache = null;
            if (pl == null) return 0;
            string sqlite = LocalizarSqlite();
            ed?.WriteMessage($"\n  · [WYE-LOAD] Catálogo SQLite: {(sqlite ?? "(no encontrado)")}");
            if (string.IsNullOrEmpty(sqlite))
            {
                ed?.WriteMessage("\n  ⚠ [WYE-LOAD] No encontré Imperial_AWWA_Steel.sqlite — no se cargan Wye.");
                return 0;
            }

            // ── API REAL (confirmada por dump de AeccPressurePipesMgd 13.9.1.1308):
            //   PressurePartCatalog.SetCatalog(fullPath)   ← estático = botón "Load new catalog"
            //   <partsList>.Catalog                         → PressurePartCatalog de ESA lista
            //   catalog.GetParts(PressurePartDomainType)    → List<PressurePartSize> del CATÁLOGO
            //   pl.AddPart(PressurePartSize)                = "Add Type" + "Add all sizes"
            //
            // DESCUBRIMIENTO (run del usuario): pl.Catalog NO refleja SetCatalog —
            // devuelve el catálogo PROPIO de la lista (PushOn → Cross/Elbow/Tee,
            // sin Wye). Para leer el catálogo Steel que activó SetCatalog creamos
            // una lista TEMPORAL después de SetCatalog: su .Catalog sí queda ligado
            // al catálogo activo (Steel, con Wye). Copiamos las Wye a la lista real
            // con AddPart y borramos la temporal. Es lo mismo que en el diálogo:
            // "Load new catalog" + elegir "Imperial_AWWA_Steel" en el desplegable.
            var asm = typeof(PresStyles.PressurePartList).Assembly;
            var tCat = asm.GetType("Autodesk.Civil.DatabaseServices.Styles.PressurePartCatalog");
            if (tCat == null)
            {
                ed?.WriteMessage("\n  ⚠ [WYE-LOAD] No encontré el tipo PressurePartCatalog en el assembly.");
                return 0;
            }
            try
            {
                ed?.WriteMessage($"\n  · [WYE-LOAD] SetCatalog → {sqlite}");
                var mSet = tCat.GetMethod("SetCatalog",
                    BindingFlags.Public | BindingFlags.Static, null, new[] { typeof(string) }, null);
                if (mSet == null) { ed?.WriteMessage("\n  ⚠ [WYE-LOAD] SetCatalog(string) no encontrado."); return 0; }
                mSet.Invoke(null, new object[] { sqlite });
            }
            catch (Exception exSet)
            {
                ed?.WriteMessage($"\n  ⚠ [WYE-LOAD] SetCatalog falló: {exSet.InnerException?.Message ?? exSet.Message}");
                return 0;
            }

            // Si el llamador no pasó la colección, la resolvemos (necesaria para
            // crear la lista temporal ligada al catálogo activo).
            if (plc == null)
            {
                try
                {
                    var cdoc = Autodesk.Civil.ApplicationServices.CivilApplication.ActiveDocument;
                    if (cdoc != null)
                        plc = PresStyles.StylesRootPressurePipesExtension.GetPressurePartLists(cdoc.Styles);
                }
                catch (Exception exPlc)
                {
                    ed?.WriteMessage($"\n  ⚠ [WYE-LOAD] No pude resolver PressurePartListCollection: {exPlc.Message}");
                }
            }

            // Lista TEMPORAL ligada al catálogo Steel, solo para poder LEER sus
            // piezas Wye (su .Catalog apunta al catálogo activo = Steel). Se borra
            // al final: no aporta nada dejarla y solo ensucia el árbol.
            object cat = null;
            PresStyles.PressurePartList steelList = null;
            ObjectId steelListId = ObjectId.Null;
            if (plc != null && tr != null)
            {
                try
                {
                    steelListId = plc.Add("GVR_TMP_STEEL_" + Guid.NewGuid().ToString("N").Substring(0, 8));
                    steelList = tr.GetObject(steelListId, OpenMode.ForRead) as PresStyles.PressurePartList;
                    if (steelList != null)
                        cat = steelList.GetType().GetProperty("Catalog")?.GetValue(steelList);
                }
                catch (Exception exTmp)
                {
                    ed?.WriteMessage($"\n  ⚠ [WYE-LOAD] No pude crear lista temporal Steel: {exTmp.InnerException?.Message ?? exTmp.Message}");
                }
            }
            if (cat == null)
            {
                try { cat = pl.GetType().GetProperty("Catalog")?.GetValue(pl); } catch { }
            }
            if (cat == null)
            {
                ed?.WriteMessage("\n  ⚠ [WYE-LOAD] No obtuve ningún PressurePartCatalog.");
                BorrarLista(steelListId, tr);
                return 0;
            }

            List<PresStyles.PressurePartSize> catFittings;
            try
            {
                var mGetParts = tCat.GetMethod("GetParts",
                    BindingFlags.Public | BindingFlags.Instance, null,
                    new[] { typeof(CivilDB.PressurePartDomainType) }, null);
                if (mGetParts == null) { ed?.WriteMessage("\n  ⚠ [WYE-LOAD] catalog.GetParts(domain) no encontrado."); BorrarLista(steelListId, tr); return 0; }
                object listObj = mGetParts.Invoke(cat, new object[] { CivilDB.PressurePartDomainType.Fitting });
                catFittings = ((System.Collections.IEnumerable)listObj)
                    .Cast<PresStyles.PressurePartSize>().ToList();
            }
            catch (Exception exGP)
            {
                ed?.WriteMessage($"\n  ⚠ [WYE-LOAD] catalog.GetParts(Fitting) falló: {exGP.InnerException?.Message ?? exGP.Message}");
                BorrarLista(steelListId, tr);
                return 0;
            }
            int nCat = catFittings?.Count ?? 0;
            int nWyeCat = catFittings?.Count(p => p != null && p.PartType == CivilDB.PressurePartType.Wye) ?? 0;
            ed?.WriteMessage($"\n  · [WYE-LOAD] Catálogo Fitting: {nCat} pieza(s); {nWyeCat} son Wye.");
            if (nWyeCat == 0)
            {
                try
                {
                    var tipos = catFittings.Where(p => p != null)
                        .Select(p => p.PartType.ToString()).Distinct().OrderBy(s => s);
                    ed?.WriteMessage($"\n     PartTypes en el catálogo: {string.Join(", ", tipos)}");
                }
                catch { }
                ed?.WriteMessage("\n  ⚠ [WYE-LOAD] El catálogo no expone Wye.");
                BorrarLista(steelListId, tr);
                return 0;
            }

            // Descripciones Wye ya presentes en la lista — idempotente.
            var existentes = new HashSet<string>(
                (fittingsExistentes ?? new List<PresStyles.PressurePartSize>())
                    .Where(f => f.PartType == CivilDB.PressurePartType.Wye)
                    .Select(f => (f.Description ?? "").Trim().ToLowerInvariant()),
                StringComparer.OrdinalIgnoreCase);

            try { pl.UpgradeOpen(); } catch { }
            int agregadas = 0, saltadas = 0, errores = 0;
            foreach (var ps in catFittings)
            {
                if (ps == null || ps.PartType != CivilDB.PressurePartType.Wye) continue;
                string d = (ps.Description ?? "").Trim().ToLowerInvariant();
                if (existentes.Contains(d)) { saltadas++; continue; }
                try
                {
                    pl.AddPart(ps);
                    agregadas++;
                    existentes.Add(d);
                }
                catch (Exception ex)
                {
                    errores++;
                    string msg = ex.InnerException?.Message ?? ex.Message;
                    if (errores <= 5)
                        ed?.WriteMessage($"\n  ⚠ AddPart falló para '{ps.Description}': {msg}");
                    else if (errores == 6)
                        ed?.WriteMessage("\n  ⚠ (más errores similares — silenciados)");
                }
            }
            ed?.WriteMessage($"\n  · [WYE-LOAD] Resumen: {agregadas} agregadas, {saltadas} ya existían, {errores} error(es).");
            BorrarLista(steelListId, tr);
            return agregadas;
        }

        // Borra una PressurePartList por ObjectId (la lista temporal Steel).
        private static void BorrarLista(ObjectId id, Transaction tr)
        {
            if (id == ObjectId.Null || tr == null) return;
            try
            {
                var o = tr.GetObject(id, OpenMode.ForWrite, false, true) as PresStyles.PressurePartList;
                o?.Erase();
            }
            catch { }
        }

        // Carga el archivo .sqlite del catálogo en la PressurePartList activa.
        // Equivale al botón "Load new catalog" del diálogo Pressure Network
        // Parts List. Sin esto, GetPart(guid) devuelve null: las piezas del
        // catálogo no están indexadas en la lista hasta que se hace este paso.
        // La API cambió de nombre entre versiones (LoadCatalog / AddCatalog /
        // LoadFromCatalog / AttachCatalog…) → probamos varios nombres por
        // reflexión con signatura (string) y logueamos los métodos que existen
        // con "catalog"/"load" para diagnóstico.
        private static readonly HashSet<string> _catalogosCargados = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        private static void CargarCatalogoEnPartsList(PresStyles.PressurePartList pl, string sqlitePath, Editor ed)
        {
            if (pl == null || string.IsNullOrEmpty(sqlitePath)) return;
            // Ya cargado en esta sesión — no re-cargar.
            string clave = pl.ObjectId.Handle.Value.ToString("X") + "|" + sqlitePath;
            if (_catalogosCargados.Contains(clave))
            {
                ed?.WriteMessage($"\n  · [WYE-LOAD] Catálogo ya estaba cargado en esta sesión — skip.");
                return;
            }
            var t = pl.GetType();
            var flags = BindingFlags.Public | BindingFlags.Instance;
            var candidatos = new[] { "LoadCatalog", "AddCatalog", "LoadFromCatalog",
                                     "AttachCatalog", "SetCatalog", "AddCatalogFile",
                                     "LoadCatalogFile", "ImportCatalog" };
            MethodInfo mLoad = null;
            foreach (string nm in candidatos)
            {
                mLoad = t.GetMethod(nm, flags, null, new[] { typeof(string) }, null);
                if (mLoad != null) break;
            }
            if (mLoad == null)
            {
                ed?.WriteMessage($"\n  ⚠ [WYE-LOAD] PressurePartList no expone LoadCatalog/AddCatalog(string).");
                ed?.WriteMessage($"\n     Métodos con 'catalog'/'load' en {t.FullName}:");
                try
                {
                    var flags2 = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static;
                    var listables = t.GetMethods(flags2)
                        .Where(m => m.Name.IndexOf("catalog", StringComparison.OrdinalIgnoreCase) >= 0 ||
                                    m.Name.IndexOf("load", StringComparison.OrdinalIgnoreCase) >= 0 ||
                                    m.Name.IndexOf("attach", StringComparison.OrdinalIgnoreCase) >= 0 ||
                                    m.Name.IndexOf("import", StringComparison.OrdinalIgnoreCase) >= 0)
                        .Distinct().ToList();
                    foreach (var m in listables)
                    {
                        string sig = string.Join(", ", m.GetParameters().Select(p => p.ParameterType.Name + " " + p.Name));
                        ed?.WriteMessage($"\n       · {(m.IsStatic ? "static " : "")}{m.Name}({sig}) → {m.ReturnType.Name}");
                    }
                    // También propiedades tipo 'Catalogs'
                    var propsCat = t.GetProperties(flags2)
                        .Where(p => p.Name.IndexOf("catalog", StringComparison.OrdinalIgnoreCase) >= 0)
                        .ToList();
                    ed?.WriteMessage($"\n     Propiedades con 'catalog':");
                    foreach (var p in propsCat)
                        ed?.WriteMessage($"\n       · {p.PropertyType.Name} {p.Name}");
                }
                catch { }
                return;
            }
            try
            {
                ed?.WriteMessage($"\n  · [WYE-LOAD] Cargando catálogo con {mLoad.Name}(string) …");
                try { pl.UpgradeOpen(); } catch { }
                mLoad.Invoke(pl, new object[] { sqlitePath });
                _catalogosCargados.Add(clave);
                ed?.WriteMessage($"\n  · [WYE-LOAD] Catálogo cargado exitosamente.");
            }
            catch (Exception ex)
            {
                ed?.WriteMessage($"\n  ⚠ [WYE-LOAD] Falló {mLoad.Name}({sqlitePath}): {ex.InnerException?.Message ?? ex.Message}");
            }
        }

        // Descriptor del método resuelto + cómo invocarlo. Diferentes versiones
        // de AeccPressurePipesMgd.dll exponen firmas distintas:
        //   · AddPart(Guid)                                              — 2019+
        //   · AddPart(Guid, PressurePartDomainType)                      — algunas 2020+
        //   · AddPart(Guid, PressurePartDomainType, PressurePartType)    — otras
        //   · AddParts(IEnumerable<Guid>, PressurePartDomainType)        — 2024+
        // El resolver arma la lista de argumentos correcta.
        internal class AddPartDescriptor
        {
            public MethodInfo Method;
            public Func<Guid, object[]> ArgsFor;   // recibe el famId → args
            public string FirmaLegible;
        }

        private static AddPartDescriptor ResolverAddPart(PresStyles.PressurePartList pl)
        {
            if (pl == null) return null;
            var t = pl.GetType();
            var flags = BindingFlags.Public | BindingFlags.Instance;
            var candidatos = t.GetMethods(flags)
                .Where(m => m.Name.Equals("AddPart", StringComparison.OrdinalIgnoreCase)
                         || m.Name.Equals("AddParts", StringComparison.OrdinalIgnoreCase)
                         || m.Name.Equals("AddPartByGuid", StringComparison.OrdinalIgnoreCase))
                .ToList();
            foreach (var m in candidatos)
            {
                var ps = m.GetParameters();
                string sig = string.Join(",", ps.Select(p => p.ParameterType.Name));
                // (Guid)
                if (ps.Length == 1 && ps[0].ParameterType == typeof(Guid))
                    return new AddPartDescriptor {
                        Method = m,
                        ArgsFor = g => new object[] { g },
                        FirmaLegible = $"{m.Name}(Guid)"
                    };
                // (Guid, PressurePartDomainType) — orden habitual
                if (ps.Length == 2 && ps[0].ParameterType == typeof(Guid) &&
                    ps[1].ParameterType.Name.Contains("DomainType"))
                    return new AddPartDescriptor {
                        Method = m,
                        ArgsFor = g => new object[] { g, CivilDB.PressurePartDomainType.Fitting },
                        FirmaLegible = $"{m.Name}(Guid, PressurePartDomainType.Fitting)"
                    };
                // (PressurePartDomainType, Guid) — orden inverso
                if (ps.Length == 2 && ps[1].ParameterType == typeof(Guid) &&
                    ps[0].ParameterType.Name.Contains("DomainType"))
                    return new AddPartDescriptor {
                        Method = m,
                        ArgsFor = g => new object[] { CivilDB.PressurePartDomainType.Fitting, g },
                        FirmaLegible = $"{m.Name}(PressurePartDomainType.Fitting, Guid)"
                    };
                // (Guid, PressurePartDomainType, PressurePartType)
                if (ps.Length == 3 && ps[0].ParameterType == typeof(Guid) &&
                    ps[1].ParameterType.Name.Contains("DomainType") &&
                    ps[2].ParameterType.Name.Contains("PartType"))
                    return new AddPartDescriptor {
                        Method = m,
                        ArgsFor = g => new object[] { g, CivilDB.PressurePartDomainType.Fitting, CivilDB.PressurePartType.Wye },
                        FirmaLegible = $"{m.Name}(Guid, PressurePartDomainType.Fitting, PressurePartType.Wye)"
                    };
            }
            return null;
        }

        internal static List<double> ExtraerDiams(string dnStr)
        {
            var r = new List<double>();
            if (string.IsNullOrEmpty(dnStr)) return r;
            foreach (var p in System.Text.RegularExpressions.Regex.Split(dnStr, @"\s*x\s*"))
            {
                var mm = System.Text.RegularExpressions.Regex.Match(p.Trim(), @"([\d.]+)");
                if (mm.Success && double.TryParse(mm.Groups[1].Value, NumberStyles.Float,
                        CultureInfo.InvariantCulture, out double d))
                    r.Add(d);
            }
            return r;
        }

        internal static int ExtraerAngulo(string nombre)
        {
            if (string.IsNullOrEmpty(nombre)) return 0;
            var m = System.Text.RegularExpressions.Regex.Match(nombre, @"Wye\s*(\d{1,3})",
                System.Text.RegularExpressions.RegexOptions.IgnoreCase);
            if (m.Success && int.TryParse(m.Groups[1].Value, out int a)) return a;
            return 0;
        }
    }
}

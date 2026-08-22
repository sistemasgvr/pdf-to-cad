using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;
using Autodesk.Civil.ApplicationServices;
using CivilDB = Autodesk.Civil.DatabaseServices;                 // alias: objetos de Civil 3D (Network, Structure, Pipe...)
using PartsStyles = Autodesk.Civil.DatabaseServices.Styles;      // alias: catálogo (PartsList, PartFamily, PartSize...)
using Exception = System.Exception;

// ============================================================================
//  GUÍA RÁPIDA (detalle en README.md, secciones 4 y 6)
//  - [CommandMethod("X")] = comando que escribes en Civil 3D.
//  - Patrón: doc/ed/db → Transaction → pedir datos (ed.Get...) → crear/leer → Commit.
//  Anatomía de una red de tubería:
//     Network  →  Structures (buzones)  +  Pipes (tuberías)
//     La Parts List es el CATÁLOGO: qué familias (tipos) y tamaños se pueden usar.
//  Ideas clave del catálogo:
//    - civilDoc.Styles.PartsListSet                       → colección de Parts Lists
//    - partsList.GetPartFamilyIdsByDomain(Structure/Pipe) → familias de la lista
//    - family[i]                                          → un tamaño (PartSize) de la familia
//    - una Parts List solo puede tener tamaños que el catálogo defina.
// ============================================================================

namespace Civil3DBasico
{
    /// <summary>
    /// Redes de tuberías (Pipe Network). Archivo separado de los corredores.
    /// Anatomía:  Network  →  Parts List (catálogo)  +  Structures (buzones)  +  Pipes (tuberías).
    /// Comandos: crear red, listar/añadir piezas del catálogo, y crear la red desde CSV.
    /// </summary>
    public partial class ComandosRedes
    {
        // =====================================================================
        // CREAR_RED — crea una Pipe Network vacía, le asigna una Parts List y,
        //   opcionalmente, una superficie de referencia (para las cotas de tapa).
        // =====================================================================
        [CommandMethod("CREAR_RED")]
        public void CrearRed()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            // Nombre de la red
            PromptStringOptions pso = new PromptStringOptions("\nNombre de la Pipe Network:");
            pso.AllowSpaces = true;
            PromptResult pnr = ed.GetString(pso);
            if (pnr.Status != PromptStatus.OK || string.IsNullOrWhiteSpace(pnr.StringResult)) return;
            string nombre = pnr.StringResult.Trim();

            // ¿Superficie de referencia para las cotas de tapa (rim)?
            ObjectId surfId = ObjectId.Null;
            PromptKeywordOptions pk = new PromptKeywordOptions("\n¿Superficie de referencia para las cotas de tapa? [Si/No] <No>:", "Si No");
            pk.AllowNone = true;
            PromptResult rk = ed.GetKeywords(pk);
            if (rk.Status == PromptStatus.OK && rk.StringResult == "Si")
            {
                PromptEntityOptions peo = new PromptEntityOptions("\nSeleccione la superficie (TIN):");
                peo.SetRejectMessage("\nDebe ser una superficie TIN.");
                peo.AddAllowedClass(typeof(CivilDB.TinSurface), true);
                PromptEntityResult per = ed.GetEntity(peo);
                if (per.Status == PromptStatus.OK) surfId = per.ObjectId;
            }

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    // Recolectar las Parts Lists disponibles en el dibujo
                    PartsStyles.PartsListCollection plSet = civilDoc.Styles.PartsListSet;
                    if (plSet.Count == 0)
                    {
                        ed.WriteMessage("\nNo hay Parts Lists en el dibujo. Usa una plantilla de Civil 3D que las incluya.");
                        tr.Abort();
                        return;
                    }
                    var nombres = new List<string>();
                    var idsPL = new List<ObjectId>();
                    for (int i = 0; i < plSet.Count; i++)
                    {
                        PartsStyles.PartsList pl = tr.GetObject(plSet[i], OpenMode.ForRead) as PartsStyles.PartsList;
                        nombres.Add(pl.Name);
                        idsPL.Add(plSet[i]);
                    }

                    // Mostrarlas y dejar que el usuario elija (Enter = Standard)
                    ed.WriteMessage("\nParts Lists disponibles: " + string.Join(", ", nombres));
                    PromptStringOptions plo = new PromptStringOptions("\nParts List a usar (Enter = Standard):");
                    plo.AllowSpaces = true;
                    PromptResult plr = ed.GetString(plo);
                    string pedida = (plr.Status == PromptStatus.OK && !string.IsNullOrWhiteSpace(plr.StringResult))
                                        ? plr.StringResult.Trim() : "Standard";

                    int idx = nombres.FindIndex(n => string.Equals(n, pedida, StringComparison.OrdinalIgnoreCase));
                    if (idx < 0)
                    {
                        idx = 0;
                        ed.WriteMessage($"\nNo se encontró la Parts List '{pedida}'. Uso la primera: '{nombres[0]}'.");
                    }
                    ObjectId partsListId = idsPL[idx];
                    string plName = nombres[idx];

                    // Crear la red (Create puede ajustar el nombre si ya existe -> por eso 'ref')
                    string nm = nombre;
                    ObjectId netId = CivilDB.Network.Create(civilDoc, ref nm);

                    CivilDB.Network net = (CivilDB.Network)tr.GetObject(netId, OpenMode.ForWrite);
                    net.PartsListId = partsListId;
                    if (surfId != ObjectId.Null) net.ReferenceSurfaceId = surfId;

                    tr.Commit();
                    ed.WriteMessage($"\n✓ Pipe Network '{nm}' creada. Parts List: '{plName}'." +
                                    (surfId != ObjectId.Null ? " Superficie de referencia asignada." : ""));
                    ed.WriteMessage("\n  Siguiente (Fase 2): AGREGAR_ESTRUCTURA y AGREGAR_TUBERIA.");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        // =====================================================================
        // LISTAR_PIEZAS — muestra, para una Parts List, las FAMILIAS (tipos) y
        //   TAMAÑOS disponibles de estructuras y de tuberías. Sirve para saber
        //   qué valores de "tipo"/"tamaño" existen antes de armar la red.
        //   Valida la navegación del catálogo (GetPartFamilyIdsByDomain + índices).
        // =====================================================================
        [CommandMethod("LISTAR_PIEZAS")]
        public void ListarPiezas()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    PartsStyles.PartsListCollection plSet = civilDoc.Styles.PartsListSet;
                    if (plSet.Count == 0) { ed.WriteMessage("\nNo hay Parts Lists en el dibujo."); tr.Abort(); return; }

                    // Parts List "Standard" si existe; si no, la primera
                    ObjectId plId = plSet[0];
                    for (int i = 0; i < plSet.Count; i++)
                    {
                        PartsStyles.PartsList p = tr.GetObject(plSet[i], OpenMode.ForRead) as PartsStyles.PartsList;
                        if (string.Equals(p.Name, "Standard", StringComparison.OrdinalIgnoreCase)) { plId = plSet[i]; break; }
                    }
                    PartsStyles.PartsList partsList = (PartsStyles.PartsList)tr.GetObject(plId, OpenMode.ForRead);
                    ed.WriteMessage($"\n=== Piezas en la Parts List '{partsList.Name}' ===");

                    // Recorrer estructuras y tuberías
                    foreach (CivilDB.DomainType dominio in new[] { CivilDB.DomainType.Structure, CivilDB.DomainType.Pipe })
                    {
                        ed.WriteMessage($"\n\n--- {(dominio == CivilDB.DomainType.Structure ? "ESTRUCTURAS (buzones)" : "TUBERÍAS")} ---");
                        ObjectIdCollection famIds = partsList.GetPartFamilyIdsByDomain(dominio);
                        if (famIds.Count == 0) { ed.WriteMessage("\n  (ninguna familia añadida a esta parts list)"); continue; }

                        foreach (ObjectId famId in famIds)
                        {
                            PartsStyles.PartFamily fam = tr.GetObject(famId, OpenMode.ForRead) as PartsStyles.PartFamily;
                            ed.WriteMessage($"\n  • {fam.Description}  ({fam.PartSizeCount} tamaño(s)):");
                            for (int i = 0; i < fam.PartSizeCount; i++)
                            {
                                PartsStyles.PartSize size = tr.GetObject(fam[i], OpenMode.ForRead) as PartsStyles.PartSize;
                                ed.WriteMessage($"\n       - {size.Name}");
                            }
                        }
                    }
                    ed.WriteMessage("\n===============================================");
                    tr.Commit();
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        // =====================================================================
        // CREAR_RED_DESDE_CSV — crea una Pipe Network desde un CSV de buzones.
        //   CSV: Name, X, Y, CotaSup, CotaInf  (una fila por buzón, en orden).
        //   - Buzón: tapa = CotaSup (o a ras de superficie si se da), fondo = CotaInf.
        //   - Tubería entre buzones consecutivos: de CotaInf(i) a CotaInf(i+1),
        //     CONECTADA a ambas estructuras.
        //   Test: Parts List "Standard"; usa la 1ª familia/tamaño de estructura y tubería.
        // =====================================================================
        [CommandMethod("CREAR_RED_DESDE_CSV")]
        public void CrearRedDesdeCsv()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            // Nombre de la red
            PromptStringOptions pso = new PromptStringOptions("\nNombre de la Pipe Network:");
            pso.AllowSpaces = true;
            PromptResult pnr = ed.GetString(pso);
            if (pnr.Status != PromptStatus.OK || string.IsNullOrWhiteSpace(pnr.StringResult)) return;
            string nombre = pnr.StringResult.Trim();

            // CSV
            PromptOpenFileOptions pfo = new PromptOpenFileOptions("\nSeleccione el CSV (Name,X,Y,CotaSup,CotaInf):");
            pfo.Filter = "CSV (*.csv)|*.csv|Todos (*.*)|*.*";
            PromptFileNameResult pfr = ed.GetFileNameForOpen(pfo);
            if (pfr.Status != PromptStatus.OK) return;

            // ¿Superficie de referencia (tapas a ras)?
            ObjectId surfId = ObjectId.Null;
            PromptKeywordOptions pk = new PromptKeywordOptions("\n¿Superficie de referencia (tapas a ras)? [Si/No] <No>:", "Si No");
            pk.AllowNone = true;
            PromptResult rk = ed.GetKeywords(pk);
            if (rk.Status == PromptStatus.OK && rk.StringResult == "Si")
            {
                PromptEntityOptions peo = new PromptEntityOptions("\nSeleccione la superficie (TIN):");
                peo.SetRejectMessage("\nDebe ser una superficie TIN.");
                peo.AddAllowedClass(typeof(CivilDB.TinSurface), true);
                PromptEntityResult per = ed.GetEntity(peo);
                if (per.Status == PromptStatus.OK) surfId = per.ObjectId;
            }

            // Leer y parsear el CSV (soporta separador ',' o ';' y decimal '.' o ',')
            var filas = new List<(string name, double x, double y, double sup, double inf)>();
            foreach (string ln in File.ReadAllLines(pfr.StringResult))
            {
                if (string.IsNullOrWhiteSpace(ln)) continue;
                char sep = ln.Contains(";") ? ';' : ',';
                string[] c = ln.Split(sep);
                if (c.Length < 5) continue;
                if (TryNum(c[1], out double x) && TryNum(c[2], out double y) &&
                    TryNum(c[3], out double sup) && TryNum(c[4], out double inf))
                    filas.Add((c[0].Trim(), x, y, sup, inf));
                // si no parsea (p. ej. fila de encabezado) se ignora
            }
            if (filas.Count < 2)
            {
                ed.WriteMessage("\nEl CSV necesita al menos 2 buzones válidos (Name,X,Y,CotaSup,CotaInf).");
                return;
            }

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    // Parts List "Standard" (o la primera)
                    PartsStyles.PartsListCollection plSet = civilDoc.Styles.PartsListSet;
                    if (plSet.Count == 0) { ed.WriteMessage("\nNo hay Parts Lists en el dibujo."); tr.Abort(); return; }
                    ObjectId partsListId = plSet[0];
                    for (int i = 0; i < plSet.Count; i++)
                    {
                        PartsStyles.PartsList p = tr.GetObject(plSet[i], OpenMode.ForRead) as PartsStyles.PartsList;
                        if (string.Equals(p.Name, "Standard", StringComparison.OrdinalIgnoreCase)) { partsListId = plSet[i]; break; }
                    }
                    PartsStyles.PartsList partsList = (PartsStyles.PartsList)tr.GetObject(partsListId, OpenMode.ForRead);

                    // 1ª familia/tamaño de estructura y de tubería
                    if (!PrimeraPieza(tr, partsList, CivilDB.DomainType.Structure, out ObjectId structFamId, out ObjectId structSizeId, out string structNom))
                    { ed.WriteMessage("\nLa Parts List no tiene familias de ESTRUCTURA. Añádelas (UI o AddPartFamily)."); tr.Abort(); return; }
                    if (!PrimeraPieza(tr, partsList, CivilDB.DomainType.Pipe, out ObjectId pipeFamId, out ObjectId pipeSizeId, out string pipeNom))
                    { ed.WriteMessage("\nLa Parts List no tiene familias de TUBERÍA. Añádelas (UI o AddPartFamily)."); tr.Abort(); return; }

                    ed.WriteMessage($"\nUsando estructura: '{structNom}' | tubería: '{pipeNom}'.");

                    // Crear la red
                    string nm = nombre;
                    ObjectId netId = CivilDB.Network.Create(civilDoc, ref nm);
                    CivilDB.Network net = (CivilDB.Network)tr.GetObject(netId, OpenMode.ForWrite);
                    net.PartsListId = partsListId;
                    if (surfId != ObjectId.Null) net.ReferenceSurfaceId = surfId;

                    // Crear estructuras
                    var structIds = new List<ObjectId>();
                    foreach (var f in filas)
                    {
                        ObjectId sid = ObjectId.Null;
                        net.AddStructure(structFamId, structSizeId, new Point3d(f.x, f.y, f.sup), 0.0, ref sid, true);
                        CivilDB.Structure st = (CivilDB.Structure)tr.GetObject(sid, OpenMode.ForWrite);
                        if (surfId != ObjectId.Null) st.AutomaticRimSurfaceAdjustment = true;
                        else st.RimElevation = f.sup;
                        st.SumpElevation = f.inf;
                        structIds.Add(sid);
                    }

                    // Crear tuberías entre consecutivos y conectarlas a las estructuras
                    int nPipes = 0;
                    for (int i = 0; i < filas.Count - 1; i++)
                    {
                        Point3d p1 = new Point3d(filas[i].x, filas[i].y, filas[i].inf);
                        Point3d p2 = new Point3d(filas[i + 1].x, filas[i + 1].y, filas[i + 1].inf);
                        ObjectId pid = ObjectId.Null;
                        net.AddLinePipe(pipeFamId, pipeSizeId, new LineSegment3d(p1, p2), ref pid, true);
                        CivilDB.Pipe pipe = (CivilDB.Pipe)tr.GetObject(pid, OpenMode.ForWrite);
                        pipe.ConnectToStructure(CivilDB.ConnectorPositionType.Start, structIds[i], true);
                        pipe.ConnectToStructure(CivilDB.ConnectorPositionType.End, structIds[i + 1], true);
                        nPipes++;
                    }

                    tr.Commit();
                    ed.WriteMessage($"\n✓ Red '{nm}' creada: {structIds.Count} buzones y {nPipes} tuberías (conectadas).");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        // =====================================================================
        // AGREGAR_FAMILIA — añade a la Parts List "Standard" una familia (tipo)
        //   de estructura o tubería tomada del CATÁLOGO, e intenta agregar sus
        //   tamaños. Requiere tener el catálogo seteado (LOMB o el de fábrica).
        // =====================================================================
        [CommandMethod("AGREGAR_FAMILIA")]
        public void AgregarFamilia()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            // Dominio
            PromptKeywordOptions pk = new PromptKeywordOptions("\n¿Qué familia añadir? [Estructura/Tuberia] <Estructura>:", "Estructura Tuberia");
            pk.AllowNone = true;
            PromptResult rk = ed.GetKeywords(pk);
            if (rk.Status != PromptStatus.OK && rk.Status != PromptStatus.None) return;
            CivilDB.DomainType dom = (rk.Status == PromptStatus.OK && rk.StringResult == "Tuberia")
                                        ? CivilDB.DomainType.Pipe : CivilDB.DomainType.Structure;

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    PartsStyles.PartsListCollection plSet = civilDoc.Styles.PartsListSet;
                    if (plSet.Count == 0) { ed.WriteMessage("\nNo hay Parts Lists."); tr.Abort(); return; }
                    ObjectId plId = plSet[0];
                    for (int i = 0; i < plSet.Count; i++)
                    {
                        PartsStyles.PartsList p = tr.GetObject(plSet[i], OpenMode.ForRead) as PartsStyles.PartsList;
                        if (string.Equals(p.Name, "Standard", StringComparison.OrdinalIgnoreCase)) { plId = plSet[i]; break; }
                    }
                    PartsStyles.PartsList partsList = (PartsStyles.PartsList)tr.GetObject(plId, OpenMode.ForWrite);

                    // Familias disponibles en el catálogo para ese dominio
                    PartsStyles.DataPartFamily[] disp = PartsStyles.PartsList.GetAvailablePartFamilies(dom);
                    if (disp == null || disp.Length == 0)
                    {
                        ed.WriteMessage("\nNo hay familias en el catálogo para ese dominio. ¿Seteaste el catálogo (Set Pipe Network Catalog)?");
                        tr.Abort(); return;
                    }

                    ed.WriteMessage($"\nFamilias disponibles ({disp.Length}):");
                    for (int i = 0; i < disp.Length; i++)
                        ed.WriteMessage($"\n  {i + 1}. {disp[i].Description}");

                    // Elegir por número
                    PromptIntegerOptions pio = new PromptIntegerOptions("\nNúmero de la familia a añadir:");
                    pio.LowerLimit = 1; pio.UpperLimit = disp.Length;
                    PromptIntegerResult pir = ed.GetInteger(pio);
                    if (pir.Status != PromptStatus.OK) { tr.Abort(); return; }
                    PartsStyles.DataPartFamily elegido = disp[pir.Value - 1];

                    // Añadir la familia (si ya está, no es error: seguimos con los tamaños)
                    try
                    {
                        partsList.AddPartFamilyByGuid(dom, elegido.GUID);
                        ed.WriteMessage("\nFamilia añadida a la parts list.");
                    }
                    catch (Exception exAdd)
                    {
                        ed.WriteMessage($"\n(La familia ya estaba en la lista; continúo con los tamaños.)  [{exAdd.Message}]");
                    }

                    // Localizar la familia (por GUID) e intentar agregar tamaños
                    int nSizes = 0;
                    ObjectIdCollection fams = partsList.GetPartFamilyIdsByDomain(dom);
                    foreach (ObjectId fid in fams)
                    {
                        PartsStyles.PartFamily fam = tr.GetObject(fid, OpenMode.ForWrite) as PartsStyles.PartFamily;
                        if (fam == null || !string.Equals(fam.GUID, elegido.GUID, StringComparison.OrdinalIgnoreCase)) continue;

                        try
                        {
                            PartsStyles.SizeFilterRecord filtro = new PartsStyles.SizeFilterRecord(fam);
                            // Marcar selección MÚLTIPLE en cada parámetro de lista editable
                            // -> AddPartSize agrega TODOS los tamaños disponibles (no solo el 1º).
                            for (int i = 0; i < filtro.ParamCount; i++)
                            {
                                PartsStyles.SizeFilterField campo = filtro[i];
                                if (campo != null && !campo.IsReadOnly && campo.IsFromList)
                                    campo.IsMultipleSelect = true;
                            }
                            fam.AddPartSize(filtro);
                        }
                        catch (Exception exSize)
                        {
                            ed.WriteMessage($"\n(No se pudieron agregar tamaños automáticamente: {exSize.Message})");
                        }
                        nSizes = fam.PartSizeCount;
                        break;
                    }

                    tr.Commit();
                    ed.WriteMessage($"\n✓ Familia '{elegido.Description}' añadida a 'Standard'. Tamaños: {nSizes}.");
                    if (nSizes == 0)
                        ed.WriteMessage("\n(Sin tamaños: agrégalos con 'Add part size' en la UI, o dime y lo afinamos.)");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        // =====================================================================
        // AGREGAR_TAMANOS — añade diámetros ESPECÍFICOS a una familia de la
        //   parts list (útil para tuberías paramétricas). Funciona si el campo
        //   de diámetro admite el valor (rango/paramétrico). Si es lista fija,
        //   solo entrarán los valores válidos del catálogo.
        // =====================================================================
        [CommandMethod("AGREGAR_TAMANOS")]
        public void AgregarTamanos()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            PromptKeywordOptions pk = new PromptKeywordOptions("\n¿Familia de? [Estructura/Tuberia] <Tuberia>:", "Estructura Tuberia");
            pk.AllowNone = true;
            PromptResult rk = ed.GetKeywords(pk);
            if (rk.Status != PromptStatus.OK && rk.Status != PromptStatus.None) return;
            CivilDB.DomainType dom = (rk.Status == PromptStatus.OK && rk.StringResult == "Estructura")
                                        ? CivilDB.DomainType.Structure : CivilDB.DomainType.Pipe;

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    PartsStyles.PartsListCollection plSet = civilDoc.Styles.PartsListSet;
                    if (plSet.Count == 0) { ed.WriteMessage("\nNo hay Parts Lists."); tr.Abort(); return; }
                    ObjectId plId = plSet[0];
                    for (int i = 0; i < plSet.Count; i++)
                    {
                        PartsStyles.PartsList p = tr.GetObject(plSet[i], OpenMode.ForRead) as PartsStyles.PartsList;
                        if (string.Equals(p.Name, "Standard", StringComparison.OrdinalIgnoreCase)) { plId = plSet[i]; break; }
                    }
                    PartsStyles.PartsList partsList = (PartsStyles.PartsList)tr.GetObject(plId, OpenMode.ForRead);

                    // Listar familias de la parts list
                    ObjectIdCollection fams = partsList.GetPartFamilyIdsByDomain(dom);
                    if (fams.Count == 0) { ed.WriteMessage("\nEsa parts list no tiene familias de ese dominio (usa AGREGAR_FAMILIA)."); tr.Abort(); return; }
                    ed.WriteMessage("\nFamilias en la parts list:");
                    for (int i = 0; i < fams.Count; i++)
                    {
                        PartsStyles.PartFamily fam = tr.GetObject(fams[i], OpenMode.ForRead) as PartsStyles.PartFamily;
                        ed.WriteMessage($"\n  {i + 1}. {fam.Description}  ({fam.PartSizeCount} tamaños)");
                    }

                    PromptIntegerOptions pio = new PromptIntegerOptions("\nNúmero de la familia:");
                    pio.LowerLimit = 1; pio.UpperLimit = fams.Count;
                    PromptIntegerResult pir = ed.GetInteger(pio);
                    if (pir.Status != PromptStatus.OK) { tr.Abort(); return; }
                    ObjectId famId = fams[pir.Value - 1];

                    // Diámetros a agregar
                    PromptStringOptions pdo = new PromptStringOptions("\nDiámetros a agregar (separados por espacio, ej. '110 160 200'):");
                    pdo.AllowSpaces = true;
                    PromptResult pdr = ed.GetString(pdo);
                    if (pdr.Status != PromptStatus.OK || string.IsNullOrWhiteSpace(pdr.StringResult)) { tr.Abort(); return; }
                    var diams = new List<double>();
                    foreach (string t in pdr.StringResult.Split(new[] { ' ', ',', ';', '\t' }, StringSplitOptions.RemoveEmptyEntries))
                        if (TryNum(t, out double d)) diams.Add(d);
                    if (diams.Count == 0) { ed.WriteMessage("\nNo se leyeron diámetros válidos."); tr.Abort(); return; }

                    PartsStyles.PartFamily fam2 = (PartsStyles.PartFamily)tr.GetObject(famId, OpenMode.ForWrite);
                    int antes = fam2.PartSizeCount;

                    foreach (double d in diams)
                    {
                        try
                        {
                            PartsStyles.SizeFilterRecord filtro = new PartsStyles.SizeFilterRecord(fam2);
                            // localizar el campo de "Diameter" editable
                            PartsStyles.SizeFilterField campoD = null;
                            for (int i = 0; i < filtro.ParamCount; i++)
                            {
                                PartsStyles.SizeFilterField f = filtro[i];
                                if (f != null && !f.IsReadOnly && f.Context.ToString().IndexOf("Diameter", StringComparison.OrdinalIgnoreCase) >= 0)
                                { campoD = f; break; }
                            }
                            if (campoD == null) { ed.WriteMessage("\n  No hallé un parámetro de diámetro editable en esta familia."); break; }

                            campoD.Value = d;              // fijar el diámetro deseado
                            fam2.AddPartSize(filtro);
                        }
                        catch (Exception exD)
                        {
                            ed.WriteMessage($"\n  Ø {d}: no se pudo agregar ({exD.Message})");
                        }
                    }

                    int desp = fam2.PartSizeCount;
                    tr.Commit();
                    ed.WriteMessage($"\n✓ Tamaños: antes {antes}, ahora {desp} (agregados {desp - antes}). Revisa con LISTAR_PIEZAS.");
                    if (desp == antes) ed.WriteMessage("\n(No entró ninguno: la familia usa lista fija del catálogo; esos diámetros no existen para ella.)");
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        // =====================================================================
        // CREAR_RED_COMPLETA — red 100% desde datos: DOS CSV.
        //   Buzones:  Name, X, Y, CotaSup, CotaInf, Type, Radius
        //   Tuberías: Desde, Hasta, Material, Diametro
        //   Cada tubería une dos buzones (por nombre), invert de CotaInf a CotaInf,
        //   conectada a ambas estructuras.
        // =====================================================================
        [CommandMethod("CREAR_RED_COMPLETA")]
        public void CrearRedCompleta()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            CivilDocument civilDoc = CivilApplication.ActiveDocument;

            PromptStringOptions pso = new PromptStringOptions("\nNombre de la Pipe Network:");
            pso.AllowSpaces = true;
            PromptResult pnr = ed.GetString(pso);
            if (pnr.Status != PromptStatus.OK || string.IsNullOrWhiteSpace(pnr.StringResult)) return;
            string nombre = pnr.StringResult.Trim();

            PromptOpenFileOptions pfoB = new PromptOpenFileOptions("\nCSV de BUZONES (Name,X,Y,CotaSup,CotaInf,Type,Radius):");
            pfoB.Filter = "CSV (*.csv)|*.csv|Todos (*.*)|*.*";
            PromptFileNameResult pfrB = ed.GetFileNameForOpen(pfoB);
            if (pfrB.Status != PromptStatus.OK) return;

            PromptOpenFileOptions pfoT = new PromptOpenFileOptions("\nCSV de TUBERÍAS (Desde,Hasta,Material,Diametro):");
            pfoT.Filter = "CSV (*.csv)|*.csv|Todos (*.*)|*.*";
            PromptFileNameResult pfrT = ed.GetFileNameForOpen(pfoT);
            if (pfrT.Status != PromptStatus.OK) return;

            ObjectId surfId = ObjectId.Null;
            PromptKeywordOptions pk = new PromptKeywordOptions("\n¿Superficie de referencia (tapas a ras)? [Si/No] <No>:", "Si No");
            pk.AllowNone = true;
            PromptResult rk = ed.GetKeywords(pk);
            if (rk.Status == PromptStatus.OK && rk.StringResult == "Si")
            {
                PromptEntityOptions peo = new PromptEntityOptions("\nSeleccione la superficie (TIN):");
                peo.SetRejectMessage("\nDebe ser una superficie TIN.");
                peo.AddAllowedClass(typeof(CivilDB.TinSurface), true);
                PromptEntityResult per = ed.GetEntity(peo);
                if (per.Status == PromptStatus.OK) surfId = per.ObjectId;
            }

            // Leer buzones
            var buzones = new List<(string name, double x, double y, double sup, double inf, string tipo, string radio)>();
            foreach (string ln in File.ReadAllLines(pfrB.StringResult))
            {
                if (string.IsNullOrWhiteSpace(ln)) continue;
                char sep = ln.Contains(";") ? ';' : ',';
                string[] c = ln.Split(sep);
                if (c.Length < 5) continue;
                if (!(TryNum(c[1], out double x) && TryNum(c[2], out double y) && TryNum(c[3], out double sup) && TryNum(c[4], out double inf))) continue;
                buzones.Add((c[0].Trim(), x, y, sup, inf, c.Length > 5 ? c[5].Trim() : "", c.Length > 6 ? c[6].Trim() : ""));
            }
            if (buzones.Count < 2) { ed.WriteMessage("\nEl CSV de buzones necesita al menos 2 filas válidas."); return; }

            // Leer tuberías
            var tramos = new List<(string desde, string hasta, string material, string diam)>();
            foreach (string ln in File.ReadAllLines(pfrT.StringResult))
            {
                if (string.IsNullOrWhiteSpace(ln)) continue;
                char sep = ln.Contains(";") ? ';' : ',';
                string[] c = ln.Split(sep);
                if (c.Length < 2) continue;
                if (string.Equals(c[0].Trim(), "Desde", StringComparison.OrdinalIgnoreCase)) continue; // encabezado
                tramos.Add((c[0].Trim(), c[1].Trim(), c.Length > 2 ? c[2].Trim() : "", c.Length > 3 ? c[3].Trim() : ""));
            }

            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                try
                {
                    PartsStyles.PartsListCollection plSet = civilDoc.Styles.PartsListSet;
                    if (plSet.Count == 0) { ed.WriteMessage("\nNo hay Parts Lists."); tr.Abort(); return; }
                    ObjectId partsListId = plSet[0];
                    for (int i = 0; i < plSet.Count; i++)
                    {
                        PartsStyles.PartsList p = tr.GetObject(plSet[i], OpenMode.ForRead) as PartsStyles.PartsList;
                        if (string.Equals(p.Name, "Standard", StringComparison.OrdinalIgnoreCase)) { partsListId = plSet[i]; break; }
                    }
                    PartsStyles.PartsList partsList = (PartsStyles.PartsList)tr.GetObject(partsListId, OpenMode.ForRead);

                    string nm = nombre;
                    ObjectId netId = CivilDB.Network.Create(civilDoc, ref nm);
                    CivilDB.Network net = (CivilDB.Network)tr.GetObject(netId, OpenMode.ForWrite);
                    net.PartsListId = partsListId;
                    if (surfId != ObjectId.Null) net.ReferenceSurfaceId = surfId;

                    // Buzones
                    var idByName = new Dictionary<string, ObjectId>(StringComparer.OrdinalIgnoreCase);
                    var invByName = new Dictionary<string, Point3d>(StringComparer.OrdinalIgnoreCase);
                    foreach (var f in buzones)
                    {
                        BuscarEstructura(tr, partsList, f.tipo, f.radio, out ObjectId sFam, out ObjectId sSize, out string sNom);
                        if (sFam == ObjectId.Null) { ed.WriteMessage($"\n(Sin familia para buzón '{f.name}'.) Saltado."); continue; }
                        ObjectId sid = ObjectId.Null;
                        net.AddStructure(sFam, sSize, new Point3d(f.x, f.y, f.sup), 0.0, ref sid, true);
                        CivilDB.Structure st = (CivilDB.Structure)tr.GetObject(sid, OpenMode.ForWrite);
                        if (surfId != ObjectId.Null) st.AutomaticRimSurfaceAdjustment = true;
                        else st.RimElevation = f.sup;
                        st.SumpElevation = f.inf;
                        idByName[f.name] = sid;
                        invByName[f.name] = new Point3d(f.x, f.y, f.inf);
                    }

                    // Tuberías
                    int nPipes = 0, saltadas = 0;
                    foreach (var t in tramos)
                    {
                        if (!idByName.ContainsKey(t.desde) || !idByName.ContainsKey(t.hasta))
                        { ed.WriteMessage($"\n(Tramo {t.desde}-{t.hasta}: buzón inexistente.) Saltado."); saltadas++; continue; }
                        if (!BuscarTuberia(tr, partsList, t.material, t.diam, out ObjectId pFam, out ObjectId pSize, out string pNom))
                        { ed.WriteMessage($"\n(Tramo {t.desde}-{t.hasta}: no hallé tubería '{t.material} {t.diam}'.) Saltado."); saltadas++; continue; }

                        ObjectId pid = ObjectId.Null;
                        net.AddLinePipe(pFam, pSize, new LineSegment3d(invByName[t.desde], invByName[t.hasta]), ref pid, true);
                        CivilDB.Pipe pipe = (CivilDB.Pipe)tr.GetObject(pid, OpenMode.ForWrite);
                        pipe.ConnectToStructure(CivilDB.ConnectorPositionType.Start, idByName[t.desde], true);
                        pipe.ConnectToStructure(CivilDB.ConnectorPositionType.End, idByName[t.hasta], true);
                        nPipes++;
                        ed.WriteMessage($"\n  + {t.desde} → {t.hasta}  ({pNom})");
                    }

                    tr.Commit();
                    ed.WriteMessage($"\n✓ Red '{nm}': {idByName.Count} buzones, {nPipes} tuberías creadas" + (saltadas > 0 ? $", {saltadas} tramo(s) saltado(s)." : "."));
                }
                catch (Exception ex)
                {
                    ed.WriteMessage($"\nError: {ex.Message}");
                    tr.Abort();
                }
            }
        }

        // Busca familia de tubería por 'material' (en Description) y tamaño por 'diam' (1er token del Name).
        // Keywords que identifican familias PERSONALIZADAS del proyecto GVR.
        // Estas familias solo deben usarse cuando el usuario las pide EXPLÍCITAMENTE
        // desde Python (por catalogId Aecc… o por Description exacta). NUNCA deben
        // servir como "default" para tuberías/buzones sin familia asignada — de lo
        // contrario, poner una familia custom a UNA sola pipe en Python la propagaría
        // a TODAS las demás pipes que no tenían familia asignada.
        private static readonly string[] KW_CUSTOM_PIPE = new[]
        {
            "bancoducto", "bancoductos",
            "banco de tubos", "bancos de tubos",
            "iluminacion", "iluminación"
        };
        private static readonly string[] KW_CUSTOM_STRUCT = new[] { "buzon", "buzón" };

        // internal (no private): PrepararFamilias.cs las reutiliza para detectar
        // qué familias referenciadas en el DXF son "nuevas"/personalizadas y
        // excluir las de fábrica — un solo lugar con la lista de keywords.
        internal static bool EsFamiliaCustomPipe(string desc)
        {
            if (string.IsNullOrEmpty(desc)) return false;
            string d = desc.ToLowerInvariant();
            foreach (var k in KW_CUSTOM_PIPE) if (d.Contains(k)) return true;
            return false;
        }
        internal static bool EsFamiliaCustomStruct(string desc)
        {
            if (string.IsNullOrEmpty(desc)) return false;
            string d = desc.ToLowerInvariant();
            foreach (var k in KW_CUSTOM_STRUCT) if (d.Contains(k)) return true;
            return false;
        }

        // Dado el ObjectId de una PartFamily del dibujo, dice si es una familia
        // custom del proyecto GVR (Bancoducto/Buzon/etc.). Se usa como red de
        // seguridad en el punto de asignación: si una pipe/estructura NO pidió
        // familia explícita pero el matcher devolvió una custom, la rechazamos.
        internal static bool EsFamiliaCustomPorId(Transaction tr, ObjectId fid, CivilDB.DomainType dom)
        {
            if (fid.IsNull) return false;
            try
            {
                var fam = tr.GetObject(fid, OpenMode.ForRead) as PartsStyles.PartFamily;
                if (fam == null) return false;
                return dom == CivilDB.DomainType.Pipe
                    ? EsFamiliaCustomPipe(fam.Description ?? "")
                    : EsFamiliaCustomStruct(fam.Description ?? "");
            }
            catch { return false; }
        }

        private bool BuscarTuberia(Transaction tr, PartsStyles.PartsList partsList, string material, string diam,
                                   out ObjectId familyId, out ObjectId sizeId, out string nombre)
        {
            familyId = ObjectId.Null; sizeId = ObjectId.Null; nombre = "";
            string mN = Norm(material), dN = Norm(diam);
            // Si el "material" pedido es en realidad un catalogId (Aecc...), usa el
            // matcher CamelCase que sabe traducir EN↔ES (mismo que BuscarEstructura).
            bool esCatalogId = !string.IsNullOrEmpty(material) &&
                               material.StartsWith("Aecc", StringComparison.OrdinalIgnoreCase);
            // ¿La búsqueda es "cualquier familia" (sin criterio)? Si sí, hay que
            // excluir familias custom para que no se conviertan en el default.
            bool criterioVacio = !esCatalogId && mN.Length == 0;
            foreach (ObjectId fid in partsList.GetPartFamilyIdsByDomain(CivilDB.DomainType.Pipe))
            {
                PartsStyles.PartFamily fam = tr.GetObject(fid, OpenMode.ForRead) as PartsStyles.PartFamily;
                if (fam == null || fam.PartSizeCount == 0) continue;
                bool famMatch;
                if (esCatalogId)
                    famMatch = fam.Description != null && MatchCatalogId(material, fam.Description);
                else
                    famMatch = mN.Length == 0 || (fam.Description != null && Norm(fam.Description).Contains(mN));
                if (!famMatch) continue;
                // Familias CUSTOM (Bancoducto/Buzon/etc.) solo se aceptan cuando el
                // usuario las pide con un criterio EXPLÍCITO — es decir:
                //   · esCatalogId=true (matcher CamelCase), o
                //   · el `material` es EXACTAMENTE la Description de la familia.
                // Cualquier otro camino (criterio vacío, o material genérico como
                // "concrete" que casualmente aparezca como sub-string en la
                // Description custom) se descarta. Sin esto, poner una familia
                // custom a UNA sola pipe la propaga a TODAS las demás.
                bool esCustom = EsFamiliaCustomPipe(fam.Description ?? "");
                if (esCustom && !esCatalogId)
                {
                    bool matchExacto = fam.Description != null &&
                        string.Equals(Norm(fam.Description), mN, StringComparison.Ordinal);
                    if (!matchExacto) continue;
                }
                // Tamaño: para tamaños RECTANGULARES ("W x H") comparar por el
                // VALOR NUMÉRICO real (PipeInnerWidth/Height, vía SizeMasCercano —
                // igual técnica que usa el paso de "más cercano" más abajo), NUNCA
                // por el nombre del PartSize. El nombre lleva un prefijo calculado
                // por la familia (p.ej. "Bancoducto CBA 6 in x 11 in" para la
                // familia "Bancoducto CBA"), así que comparar sn==dN contra el
                // string plano que manda Python ("6 in x 11 in", sin el prefijo)
                // NUNCA es realmente igual — y caer al "Contains" deja que un
                // ancho corto como "6" haga match por accidente DENTRO de "36"
                // (ambos terminan en "6"), sustituyendo silenciosamente "6 in x
                // 11 in" por "36 in x 11 in". El match por nombre solo se usa
                // como último recurso para tamaños NO rectangulares (diámetro).
                ObjectId sizeElegido = fam[0];
                string sizeNombre = (tr.GetObject(sizeElegido, OpenMode.ForRead) as PartsStyles.PartSize)?.Name;
                bool exacto = false;
                double? wPedido = null, hPedido = null;
                if (dN.Length > 0)
                {
                    if (TryParseRectSize(diam, out wPedido, out hPedido) && wPedido.HasValue && hPedido.HasValue)
                    {
                        ObjectId cercanoNum = SizeMasCercano(tr, fam, wPedido.Value, hPedido.Value,
                            CivilDB.PartContextType.PipeInnerWidth, CivilDB.PartContextType.PipeInnerHeight,
                            out string nombreCercanoNum, out bool esExactoNum);
                        if (cercanoNum != ObjectId.Null && esExactoNum)
                        { sizeElegido = cercanoNum; sizeNombre = nombreCercanoNum; exacto = true; }
                    }
                    if (!exacto)
                    {
                        for (int i = 0; i < fam.PartSizeCount; i++)
                        {
                            PartsStyles.PartSize sz = tr.GetObject(fam[i], OpenMode.ForRead) as PartsStyles.PartSize;
                            string sn = Norm(sz?.Name ?? "");
                            if (sn == dN)
                            { sizeElegido = fam[i]; sizeNombre = sz?.Name; exacto = true; break; }
                        }
                    }
                    if (!exacto && wPedido == null)
                    {
                        // Solo para tamaños que NO parsearon como "W x H" (p.ej.
                        // diámetro suelto) se permite la coincidencia parcial.
                        for (int i = 0; i < fam.PartSizeCount; i++)
                        {
                            PartsStyles.PartSize sz = tr.GetObject(fam[i], OpenMode.ForRead) as PartsStyles.PartSize;
                            string sn = Norm(sz?.Name ?? "");
                            if (sn.Contains(dN))
                            { sizeElegido = fam[i]; sizeNombre = sz?.Name; exacto = true; break; }
                        }
                    }
                }
                // Sin match exacto: NO se crea un tamaño nuevo en el catálogo — solo
                // se permite elegir entre los que YA existen. Si el pedido es
                // rectangular "W in x H in", buscamos el más cercano disponible;
                // si no, avisamos y usamos el primero de la familia.
                if (!exacto && dN.Length > 0)
                {
                    double? w, h;
                    string aviso;
                    if (TryParseRectSize(diam, out w, out h) && w.HasValue && h.HasValue)
                    {
                        ObjectId cercano = SizeMasCercano(tr, fam, w.Value, h.Value,
                            CivilDB.PartContextType.PipeInnerWidth, CivilDB.PartContextType.PipeInnerHeight,
                            out string nombreCercano, out bool esExacto);
                        if (cercano != ObjectId.Null)
                        {
                            sizeElegido = cercano; sizeNombre = nombreCercano;
                            aviso = esExacto ? null
                                : $"\n⚠ Tamaño '{diam}' no existe en el catálogo de '{fam.Description}' — usando el más cercano disponible '{nombreCercano}'. Para la medida exacta, agrégala en Part Builder.";
                        }
                        else
                            aviso = $"\n⚠ Tamaño '{diam}' no disponible en '{fam.Description}' — usando '{sizeNombre}' en su lugar. Para medidas personalizadas, usa Part Builder.";
                    }
                    else
                        aviso = $"\n⚠ Tamaño '{diam}' no disponible en '{fam.Description}' — usando '{sizeNombre}' en su lugar. Para medidas personalizadas, usa Part Builder.";
                    if (aviso != null)
                        try { Application.DocumentManager.MdiActiveDocument?.Editor?.WriteMessage(aviso); } catch { }
                }
                familyId = fid; sizeId = sizeElegido;
                nombre = $"{fam.Description} / {sizeNombre}";
                return true;
            }
            return false;
        }

        // Busca familia de estructura por 'tipo' (en Description) y tamaño por 'radio' (en Name).
        // Coincidencia tolerante (ignora espacios/comas/mayúsculas). Cae en la 1ª real si no hay match.
        private void BuscarEstructura(Transaction tr, PartsStyles.PartsList partsList, string tipo, string radio,
                                      out ObjectId familyId, out ObjectId sizeId, out string nombre)
        {
            familyId = ObjectId.Null; sizeId = ObjectId.Null; nombre = "";
            ObjectId anyFam = ObjectId.Null, anySize = ObjectId.Null; string anyNom = "";
            string tNorm = Norm(tipo);
            // Sin criterio → NO caer en familias custom como fallback. Solo se
            // usan cuando el usuario las pide explícitamente (por catalogId Aecc…
            // o por Description exacta).
            bool criterioVacio = string.IsNullOrEmpty(tNorm) &&
                                  (string.IsNullOrEmpty(tipo) ||
                                   !tipo.StartsWith("Aecc", StringComparison.OrdinalIgnoreCase));

            foreach (ObjectId fid in partsList.GetPartFamilyIdsByDomain(CivilDB.DomainType.Structure))
            {
                PartsStyles.PartFamily fam = tr.GetObject(fid, OpenMode.ForRead) as PartsStyles.PartFamily;
                if (fam == null || fam.PartSizeCount == 0) continue;
                string descBz = fam.Description ?? "";
                // Descartar Null/nula + no-buzones (headwall/embocadura/sección final/ala) EN/ES.
                if (descBz.IndexOf("Null", StringComparison.OrdinalIgnoreCase) >= 0 ||
                    descBz.IndexOf("nula", StringComparison.OrdinalIgnoreCase) >= 0 ||
                    descBz.IndexOf("Headwall", StringComparison.OrdinalIgnoreCase) >= 0 ||
                    descBz.IndexOf("Embocadura", StringComparison.OrdinalIgnoreCase) >= 0 ||
                    descBz.IndexOf("End Section", StringComparison.OrdinalIgnoreCase) >= 0 ||
                    descBz.IndexOf("Sección final", StringComparison.OrdinalIgnoreCase) >= 0 ||
                    descBz.IndexOf("seccion final", StringComparison.OrdinalIgnoreCase) >= 0 ||
                    descBz.IndexOf("Flared", StringComparison.OrdinalIgnoreCase) >= 0 ||
                    descBz.IndexOf("acampanada", StringComparison.OrdinalIgnoreCase) >= 0 ||
                    descBz.IndexOf("Winged", StringComparison.OrdinalIgnoreCase) >= 0 ||
                    descBz.IndexOf("en ala", StringComparison.OrdinalIgnoreCase) >= 0 ||
                    descBz.IndexOf("de ala", StringComparison.OrdinalIgnoreCase) >= 0 ||
                    descBz.IndexOf("aleta", StringComparison.OrdinalIgnoreCase) >= 0 ||
                    descBz.IndexOf("Culvert", StringComparison.OrdinalIgnoreCase) >= 0 ||
                    descBz.IndexOf("O.D.T.", StringComparison.OrdinalIgnoreCase) >= 0 ||
                    descBz.IndexOf("alcantarilla", StringComparison.OrdinalIgnoreCase) >= 0 ||
                    descBz.IndexOf("cabecero", StringComparison.OrdinalIgnoreCase) >= 0 ||
                    descBz.IndexOf("cabezal", StringComparison.OrdinalIgnoreCase) >= 0) continue;

                // Tamaño por defecto (barato): el primero de la familia. Solo se usa
                // de verdad si esta familia resulta ser la elegida (por 'tipo' o, en
                // último caso, como fallback 'anyFam').
                ObjectId elegidoSize = fam[0];
                string elegidoSizeName = (tr.GetObject(elegidoSize, OpenMode.ForRead) as PartsStyles.PartSize)?.Name;
                string nom = $"{fam.Description} / {elegidoSizeName}";
                // anyFam (fallback si el tipo no matchea nada) NO debe caer en custom
                // — solo se usa cuando el usuario no pidió tipo específico.
                bool esCustom = EsFamiliaCustomStruct(descBz);
                if (anyFam == ObjectId.Null && !esCustom)
                { anyFam = fid; anySize = elegidoSize; anyNom = nom; }

                bool famMatch = string.IsNullOrEmpty(tNorm) || (fam.Description != null && Norm(fam.Description).Contains(tNorm));
                bool matchPorCatalogId = false;
                if (!famMatch && fam.Description != null && MatchCatalogId(tipo, fam.Description))
                { famMatch = true; matchPorCatalogId = true; }
                // Familias CUSTOM (Buzones): solo cuando el usuario las pide EXPLÍCITAMENTE
                //   · vía catalogId Aecc… (matchPorCatalogId = true), o
                //   · con `tipo` que sea EXACTAMENTE la Description de la familia.
                // Con criterio vacío o genérico se descartan del recorrido para que
                // NUNCA sirvan como fallback.
                if (esCustom && !matchPorCatalogId)
                {
                    bool matchExacto = !string.IsNullOrEmpty(tNorm) && fam.Description != null &&
                        string.Equals(Norm(fam.Description), tNorm, StringComparison.Ordinal);
                    if (!matchExacto) continue;
                }
                // La búsqueda/creación de tamaño (cara, y muta la familia con
                // AddPartSize/RemovePartSize) SOLO se intenta en la familia que
                // realmente coincide con 'tipo' — antes corría para TODAS las
                // familias de estructura en cada llamada (aunque no fueran a usarse),
                // lo cual era lento y multiplicaba el riesgo de dejar tamaños
                // "- N" huérfanos si algún RemovePartSize fallaba en una familia
                // que ni siquiera era la elegida.
                if (!famMatch) continue;

                bool sizeExacto = false;
                if (!string.IsNullOrWhiteSpace(radio))
                {
                    // Mismo problema que en BuscarTuberia: el Name del PartSize lleva
                    // un prefijo calculado por la familia (p.ej. "Buzon CBA 24 in x 36
                    // in"), así que comparar contra el string plano que pide Python
                    // ("24 in x 36 in") nunca da igualdad exacta — y "Contains" deja
                    // que un valor corto (p.ej. "6") matchee por accidente DENTRO de
                    // otro que lo contiene como substring (p.ej. "36 in x ..."). Para
                    // tamaños "W x L" hay que comparar por el VALOR NUMÉRICO real
                    // (SizeMasCercano, igual que el paso de "más cercano" de abajo),
                    // no por el nombre — el match por nombre queda solo de último
                    // recurso para tamaños que no parseen como rectangulares.
                    string rNorm = Norm(radio);
                    double? wReq = null, lReq = null;
                    if (TryParseRectSize(radio, out wReq, out lReq) && wReq.HasValue && lReq.HasValue)
                    {
                        ObjectId cercanoNum = SizeMasCercano(tr, fam, wReq.Value, lReq.Value,
                            CivilDB.PartContextType.StructInnerWidth, CivilDB.PartContextType.StructInnerLength,
                            out string nombreCercanoNum, out bool esExactoNum);
                        if (cercanoNum != ObjectId.Null && esExactoNum)
                        { elegidoSize = cercanoNum; elegidoSizeName = nombreCercanoNum; sizeExacto = true; }
                    }
                    if (!sizeExacto)
                    {
                        for (int i = 0; i < fam.PartSizeCount; i++)
                        {
                            PartsStyles.PartSize sz = tr.GetObject(fam[i], OpenMode.ForRead) as PartsStyles.PartSize;
                            if (sz != null && Norm(sz.Name) == rNorm)
                            { elegidoSize = fam[i]; elegidoSizeName = sz.Name; sizeExacto = true; break; }
                        }
                    }
                    if (!sizeExacto && wReq == null)
                    {
                        for (int i = 0; i < fam.PartSizeCount; i++)
                        {
                            PartsStyles.PartSize sz = tr.GetObject(fam[i], OpenMode.ForRead) as PartsStyles.PartSize;
                            if (sz != null && Norm(sz.Name).Contains(rNorm))
                            { elegidoSize = fam[i]; elegidoSizeName = sz.Name; sizeExacto = true; break; }
                        }
                    }
                }
                // Sin match exacto: NO se crea un tamaño nuevo en el catálogo — solo
                // se permite elegir entre los que YA existen en la familia. Si el
                // 'radio' pedido tiene forma "W x L in", buscamos el más cercano
                // disponible; si no hay ninguno parseable, avisamos y usamos el
                // primero de la familia.
                if (!sizeExacto && !string.IsNullOrWhiteSpace(radio))
                {
                    double? wS, lS;
                    string aviso;
                    if (TryParseRectSize(radio, out wS, out lS) && wS.HasValue && lS.HasValue)
                    {
                        ObjectId cercano = SizeMasCercano(tr, fam, wS.Value, lS.Value,
                            CivilDB.PartContextType.StructInnerWidth, CivilDB.PartContextType.StructInnerLength,
                            out string nombreCercano, out bool esExacto);
                        if (cercano != ObjectId.Null)
                        {
                            elegidoSize = cercano; elegidoSizeName = nombreCercano;
                            aviso = esExacto ? null
                                : $"\n⚠ Tamaño '{radio}' no existe en el catálogo de '{fam.Description}' — usando el más cercano disponible '{nombreCercano}'. Para la medida exacta, agrégala en Part Builder.";
                        }
                        else
                            aviso = $"\n⚠ Tamaño '{radio}' no disponible en '{fam.Description}' — usando '{elegidoSizeName}' en su lugar. Para medidas personalizadas, usa Part Builder.";
                    }
                    else
                        aviso = $"\n⚠ Tamaño '{radio}' no disponible en '{fam.Description}' — usando '{elegidoSizeName}' en su lugar. Para medidas personalizadas, usa Part Builder.";
                    if (aviso != null)
                        try { Application.DocumentManager.MdiActiveDocument?.Editor?.WriteMessage(aviso); } catch { }
                }

                familyId = fid; sizeId = elegidoSize;
                nombre = $"{fam.Description} / {elegidoSizeName}";
                return;
            }
            if (anyFam != ObjectId.Null) { familyId = anyFam; sizeId = anySize; nombre = anyNom; }
        }

        private static string Norm(string s) => (s ?? "").Replace(" ", "").Replace(",", "").ToLowerInvariant();

        // Wrapper público para que ImportarRed pueda usar el mismo matcher.
        public static bool MatchCatalogIdPublic(string catalogId, string description)
            => MatchCatalogId(catalogId, description);

        // Compara un identificador del catálogo (basename de archivo .xml, ej
        // "AeccStructConcentricCylinderRectFrame_Imperial") contra la Description
        // real de una PartFamily. Extrae tokens del CamelCase del basename y los
        // busca en la Description con equivalencias EN↔ES. Todos deben aparecer.
        private static bool MatchCatalogId(string catalogId, string description)
        {
            if (string.IsNullOrEmpty(catalogId) || string.IsNullOrEmpty(description)) return false;
            string s = catalogId;
            // Familias custom del modelador (nombres arbitrarios como "Buzon ICT Imperial"):
            // matchear por igualdad case-insensitive contra la Description o su versión
            // sin extensión "_Imperial". Es lo que espera un nombre custom bien pareado.
            if (!s.StartsWith("Aecc", StringComparison.OrdinalIgnoreCase))
            {
                string a = s;
                if (a.EndsWith("_Imperial", StringComparison.OrdinalIgnoreCase))
                    a = a.Substring(0, a.Length - "_Imperial".Length);
                if (string.Equals(description, s, StringComparison.OrdinalIgnoreCase)) return true;
                if (string.Equals(description, a, StringComparison.OrdinalIgnoreCase)) return true;
                if (description.IndexOf(a, StringComparison.OrdinalIgnoreCase) >= 0) return true;
                return false;
            }
            foreach (var pref in new[] { "AeccStruct", "Aecc" })
                if (s.StartsWith(pref, StringComparison.OrdinalIgnoreCase)) { s = s.Substring(pref.Length); break; }
            if (s.EndsWith("_Imperial", StringComparison.OrdinalIgnoreCase))
                s = s.Substring(0, s.Length - "_Imperial".Length);

            // Exclusión "sin marco / without frame": si el catalogId NO tiene NF ni
            // WithoutFrame, entonces las descripciones que lleven "sin marco" /
            // "without frame" NO pueden matchear (evita que Concentric+Rect+Frame
            // caiga a "concéntrica sin marco" solo porque "marco" ⊂ "sin marco").
            bool pedidoSinMarco = s.IndexOf("NF", StringComparison.Ordinal) >= 0 ||
                                  s.IndexOf("WithoutFrame", StringComparison.OrdinalIgnoreCase) >= 0;
            string descLow = description.ToLowerInvariant();
            if (!pedidoSinMarco &&
                (descLow.Contains("sin marco") || descLow.Contains("without frame"))) return false;

            // Split CamelCase (y por '_') en tokens.
            var raw = System.Text.RegularExpressions.Regex.Split(
                s, @"(?<!^)(?=[A-Z][a-z])|(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|_");
            var tokens = new List<string[]>();
            int rawCount = 0;
            foreach (var r in raw)
            {
                if (string.IsNullOrWhiteSpace(r)) continue;
                rawCount++;
                var opts = SinonimosCatalogo(r);
                if (opts != null && opts.Length > 0) tokens.Add(opts);
            }
            if (tokens.Count == 0) return false;
            // Regla anti-match-débil: si el catalogId tiene ≥3 tokens raw pero solo
            // uno con sinónimo, y ese único es un adjetivo común (rect/tier), se
            // rechaza. Tokens muy específicos (cm, hdpe, pvc, di, headwall) sí
            // pueden matchear por sí solos porque discriminan bien.
            if (tokens.Count == 1 && rawCount >= 3)
            {
                var only = tokens[0];
                var specific = new HashSet<string>(new[] {
                    "cm", "corrugated metal", "hdpe", "pead", "pvc", "di",
                    "ductile", "iron", "headwall", "cabecero"
                });
                bool esEspecifico = false;
                foreach (var op in only)
                    if (specific.Contains(op.ToLowerInvariant())) { esEspecifico = true; break; }
                if (!esEspecifico) return false;
            }

            string desc = StripAcentos(description.ToLowerInvariant());
            foreach (var opts in tokens)
            {
                bool alguno = false;
                foreach (var op in opts)
                    if (desc.IndexOf(StripAcentos(op.ToLowerInvariant()),
                                     StringComparison.OrdinalIgnoreCase) >= 0)
                    { alguno = true; break; }
                if (!alguno) return false;
            }
            return true;
        }

        // Quita diacríticos: 'á' → 'a', 'ñ' → 'n', etc. Necesario para que el
        // matcher del catálogo compare correctamente ES vs EN (p.ej. "cilíndrica"
        // vs "cilindr"). System.Globalization + FormD descompone y filtra marcas.
        private static string StripAcentos(string s)
        {
            if (string.IsNullOrEmpty(s)) return s;
            var d = s.Normalize(System.Text.NormalizationForm.FormD);
            var sb = new System.Text.StringBuilder(d.Length);
            foreach (var c in d)
                if (System.Globalization.CharUnicodeInfo.GetUnicodeCategory(c)
                    != System.Globalization.UnicodeCategory.NonSpacingMark) sb.Append(c);
            return sb.ToString();
        }

        // Cada token del catálogo (EN) mapea a una lista de sinónimos que TAMBIÉN
        // podrían aparecer en Description (español). Se devuelve el token en LOWER.
        private static string[] SinonimosCatalogo(string t)
        {
            string k = t.ToLowerInvariant();
            switch (k)
            {
                case "concentric":  return new[] { "concentric", "concéntric", "concentric" };
                case "eccentric":   return new[] { "eccentric", "excéntric", "excentric" };
                case "cylinder":
                case "cylindrical": return new[] { "cylinder", "cylindrical", "cilíndric", "cilindric" };
                case "rectangular": return new[] { "rectangular", "marco" };   // "marco" matchea "O.D.T. marco de hormigón" (box culvert)
                case "rect":        return new[] { "rect", "rectangular", "marco" };
                case "frame":       return new[] { "frame", "marco" };
                case "junction":    return new[] { "junction", "conexión", "conexion" };
                case "structure":   return new[] { "structure", "estructura" };
                case "nf":          return new[] { "without frame", "sin marco", "without", "sin" };
                case "headwall":    return new[] { "headwall", "cabecero", "cabezal" };
                case "end":         return new[] { "end", "extremo", "boca" };
                case "section":     return new[] { "section", "sección", "seccion" };
                case "flared":      return new[] { "flared", "abocinad" };
                case "winged":      return new[] { "winged", "aletas" };
                case "wing":        return new[] { "wing", "aleta" };
                case "slab":        return new[] { "slab", "losa" };
                case "top":         return new[] { "top", "superior" };
                case "cyl":         return new[] { "cyl", "cilindr" };
                case "culvert":     return new[] { "culvert", "alcantarilla" };
                // "box" está definido más abajo con más sinónimos (rectangular)
                case "round":       return new[] { "round", "circular", "redond" };
                case "cmp":         return new[] { "cmp", "metal corrugado", "corrugated metal" };
                case "cm":          return new[] { "corrugated metal", "metal corrugado" };
                // Términos estructurales adicionales — incluyen "2-Tier"/"3-Tier"
                // que aparecen así en descripciones inglesas (con dígito, no palabra).
                case "two":         return new[] { "two", "2-tier", "2 tier", "2-nivel", "dos" };
                case "three":       return new[] { "three", "3-tier", "3 tier", "tres" };
                case "four":        return new[] { "four", "4-tier", "4 tier", "cuatro" };
                case "tier":        return new[] { "tier", "nivel", "niveles", "-tier" };
                case "base":        return null;   // muy genérico, se ignora
                case "simple":      return null;   // muy genérico, se ignora
                case "box":         return new[] { "box", "caja", "rectangular" };
                case "concentrictc": return null;
                case "eccentrictc":  return null;
                // Materiales de tuberías (dominio Pipe)
                case "concrete":    return new[] { "concrete", "hormigón", "hormigon" };
                case "corrugated":  return new[] { "corrugated", "corrugado" };
                case "hdpe":        return new[] { "hdpe", "pead" };
                case "pvc":         return new[] { "pvc" };
                case "di":          return new[] { "di", "fundición dúctil", "fundicion ductil",
                                                   "ductile iron", "fundición", "fundicion" };
                case "ductile":     return new[] { "ductile", "dúctil", "ductil" };
                case "iron":        return new[] { "iron", "hierro", "fundición", "fundicion" };
                case "elliptical":  return new[] { "elliptical", "elíptic", "eliptic" };
                case "egg":         return new[] { "egg", "sección ovalada", "seccion ovalada", "ovoide" };
                case "arch":        return new[] { "arch", "arco" };
                case "horizontal":  return new[] { "horizontal" };
                case "vertical":    return new[] { "vertical" };
                case "pipe":        return null;    // token genérico ("pipe"/"tubería" aparece en TODAS las descripciones)
                // "circular" también es genérico: los catálogos inglés/español usan
                // "Concrete Pipe", "HDPE Pipe" sin la palabra "circular" (aunque
                // están en la carpeta Circular Pipes). Discriminamos por material.
                case "circular":    return null;
                case "shaped":      return null;    // adjetivo genérico, se ignora
                case "varht":
                case "var":         return null;    // sin equivalente, se ignora
                default:            return null;    // token no significativo: se salta
            }
        }

        // Devuelve la 1ª familia y su 1er tamaño de un dominio (Structure/Pipe) de la parts list.
        private bool PrimeraPieza(Transaction tr, PartsStyles.PartsList partsList, CivilDB.DomainType dominio,
                                  out ObjectId familyId, out ObjectId sizeId, out string nombre)
        {
            familyId = ObjectId.Null; sizeId = ObjectId.Null; nombre = "";
            ObjectId anyFam = ObjectId.Null, anySize = ObjectId.Null; string anyNom = "";     // respaldo: cualquiera no-nula
            ObjectId prefFam = ObjectId.Null, prefSize = ObjectId.Null; string prefNom = "";  // preferida: buzón "real"
            bool esEstructura = dominio == CivilDB.DomainType.Structure;

            // Para buzones: descartar familias que NO son buzones (cabezales, culverts,
            // aliviaderos, embocaduras…) — EN/ES. Estas familias se dibujan como triángulos
            // con alas en planta y acortan la tubería al conectar, dañando el resultado.
            string[] noBuzon = {
                "Headwall", "End Section", "Flared", "Culvert", "Winged", "Wing", "Apron",
                "cabecero", "cabezal", "boca", "aleta", "alcantarilla",
                "Embocadura", "embocadura",           // Headwall en español
                "Sección final", "seccion final",     // End Section en español
                "en ala", "de ala",                   // Winged en español
                "acampanada",                          // Flared en español
                "O.D.T.",                              // Overflow Discharge Tube (variante local)
            };

            ObjectIdCollection fams = partsList.GetPartFamilyIdsByDomain(dominio);
            foreach (ObjectId fid in fams)
            {
                PartsStyles.PartFamily fam = tr.GetObject(fid, OpenMode.ForRead) as PartsStyles.PartFamily;
                if (fam == null || fam.PartSizeCount == 0) continue;
                string desc = fam.Description ?? "";
                if (desc.IndexOf("Null", StringComparison.OrdinalIgnoreCase) >= 0) continue; // "Null Structure"
                if (desc.IndexOf("nula", StringComparison.OrdinalIgnoreCase) >= 0) continue; // "Estructura nula"

                ObjectId sid = fam[0];
                PartsStyles.PartSize sz = tr.GetObject(sid, OpenMode.ForRead) as PartsStyles.PartSize;
                string nom = $"{fam.Description} / {sz?.Name}";

                // Familia custom del proyecto GVR (Bancoducto, Buzon…) NO debe
                // servir como default — solo cuando se pide explícitamente por
                // catalogId. De lo contrario, asignar la custom a UNA sola pipe
                // en Python la propagaría a TODAS las pipes sin familia asignada.
                bool esCustom = esEstructura
                    ? EsFamiliaCustomStruct(desc)
                    : EsFamiliaCustomPipe(desc);
                if (esCustom) continue;

                if (anyFam == ObjectId.Null) { anyFam = fid; anySize = sid; anyNom = nom; }

                if (!esEstructura)
                {
                    // tubería: la primera válida sirve
                    familyId = fid; sizeId = sid; nombre = nom;
                    return true;
                }

                // estructura: saltar lo que no es buzón
                bool esNoBuzon = noBuzon.Any(k => desc.IndexOf(k, StringComparison.OrdinalIgnoreCase) >= 0);
                if (esNoBuzon) continue;

                // preferir un buzón "Junction"/"Conexión" (buzón típico); si aparece, usarlo ya
                if (desc.IndexOf("Junction", StringComparison.OrdinalIgnoreCase) >= 0 ||
                    desc.IndexOf("Conexión", StringComparison.OrdinalIgnoreCase) >= 0 ||
                    desc.IndexOf("Conexion", StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    familyId = fid; sizeId = sid; nombre = nom;
                    return true;
                }
                // preferir también cilíndrico/concéntrico (buzones estándar)
                if (desc.IndexOf("Cylindrical", StringComparison.OrdinalIgnoreCase) >= 0 ||
                    desc.IndexOf("Cilíndrica", StringComparison.OrdinalIgnoreCase) >= 0 ||
                    desc.IndexOf("Cilindrica", StringComparison.OrdinalIgnoreCase) >= 0 ||
                    desc.IndexOf("Concentric", StringComparison.OrdinalIgnoreCase) >= 0 ||
                    desc.IndexOf("Concéntrica", StringComparison.OrdinalIgnoreCase) >= 0 ||
                    desc.IndexOf("Concentrica", StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    familyId = fid; sizeId = sid; nombre = nom;
                    return true;
                }
                // si no, recordar el primer buzón válido (cilíndrico/rectangular/etc.)
                if (prefFam == ObjectId.Null) { prefFam = fid; prefSize = sid; prefNom = nom; }
            }

            if (prefFam != ObjectId.Null) { familyId = prefFam; sizeId = prefSize; nombre = prefNom; return true; }
            if (anyFam != ObjectId.Null) { familyId = anyFam; sizeId = anySize; nombre = anyNom; return true; }
            return false;
        }

        // Parseo tolerante de número (acepta decimal con '.' o ',')
        private static bool TryNum(string s, out double value)
        {
            s = (s ?? "").Trim().Replace(',', '.');
            return double.TryParse(s, NumberStyles.Float, CultureInfo.InvariantCulture, out value);
        }
        // Parsea un tamaño rectangular tipo "W in x H in" o "W x H" (unidades opc.).
        private static bool TryParseRectSize(string s, out double? w, out double? h)
        {
            w = null; h = null;
            if (string.IsNullOrWhiteSpace(s)) return false;
            var m = System.Text.RegularExpressions.Regex.Match(
                s.ToLowerInvariant().Replace(",", "."),
                @"([0-9]+(?:\.[0-9]+)?)\s*(?:in|inch|"")?\s*x\s*([0-9]+(?:\.[0-9]+)?)\s*(?:in|inch|"")?");
            if (!m.Success) return false;
            if (!double.TryParse(m.Groups[1].Value, NumberStyles.Float, CultureInfo.InvariantCulture, out double wv)) return false;
            if (!double.TryParse(m.Groups[2].Value, NumberStyles.Float, CultureInfo.InvariantCulture, out double hv)) return false;
            w = wv; h = hv; return true;
        }

        // Busca, entre los PartSize YA EXISTENTES de la familia (sin crear nada
        // nuevo), el más cercano al W×H pedido (Ancho×Alto para tuberías,
        // Ancho×Largo para estructuras — ctxW/ctxH indican cuál).
        //
        // IMPORTANTE: comparamos por el valor INTERIOR real de cada PartSize
        // (PartSize.SizeDataRecord.GetDataFieldBy(context), confirmado por
        // reflexión sobre AeccDbMgd.dll), NO por los números que aparezcan en
        // PartSize.Name. El Name es una etiqueta calculada por la propia
        // fórmula de catálogo de cada familia (p.ej. algunas suman el espesor
        // de pared → "44 x 92" para un tamaño interior real de "24 x 72") —
        // parsear el Name podía hacer que se eligiera un tamaño vecino
        // equivocado en vez del que realmente coincide con lo pedido.
        // Devuelve ObjectId.Null si ningún tamaño de la familia se pudo leer.
        private static ObjectId SizeMasCercano(Transaction tr, PartsStyles.PartFamily fam, double w, double h,
                                                CivilDB.PartContextType ctxW, CivilDB.PartContextType ctxH,
                                                out string nombreOut, out bool esExacto)
        {
            nombreOut = ""; esExacto = false;
            ObjectId mejor = ObjectId.Null;
            double mejorDist = double.MaxValue;
            for (int i = 0; i < fam.PartSizeCount; i++)
            {
                var sz = tr.GetObject(fam[i], OpenMode.ForRead) as PartsStyles.PartSize;
                if (sz == null) continue;
                double? rw = null, rh = null;
                try
                {
                    var rec = sz.SizeDataRecord;
                    var fw = rec?.GetDataFieldBy(ctxW);
                    var fh = rec?.GetDataFieldBy(ctxH);
                    if (fw != null && fw.Value != null) rw = Convert.ToDouble(fw.Value, CultureInfo.InvariantCulture);
                    if (fh != null && fh.Value != null) rh = Convert.ToDouble(fh.Value, CultureInfo.InvariantCulture);
                }
                catch { rw = null; rh = null; }
                if (!rw.HasValue || !rh.HasValue)
                {
                    // Fallback: familia sin esos campos por contexto — parsear el Name.
                    if (!TryParseRectSize(sz.Name, out double? nw, out double? nh) || !nw.HasValue || !nh.HasValue) continue;
                    rw = nw; rh = nh;
                }
                double dist = Math.Abs(rw.Value - w) + Math.Abs(rh.Value - h);
                if (dist < mejorDist) { mejorDist = dist; mejor = fam[i]; nombreOut = sz.Name; }
            }
            esExacto = mejor != ObjectId.Null && mejorDist < 0.01;
            return mejor;
        }
    }
}

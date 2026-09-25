using System;
using System.Collections.Generic;
using System.Collections.Specialized;
using System.Globalization;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Runtime;
using AecPS = Autodesk.Aec.PropertyData.DatabaseServices;
using AecPD = Autodesk.Aec.PropertyData;
using Exception = System.Exception;

// ============================================================================
//  Property Set de los accesorios sólidos (Codo, Tee, Wye, Cruz)
//
//  El XDATA de la pieza (WyeSolido.GrabarXData) no se ve en la interfaz de
//  Civil 3D. Esto adjunta un Property Set REAL, «PDFCAD_Accesorio», que aparece
//  en la paleta Propiedades (pestaña «Datos extendidos»), se puede filtrar,
//  etiquetar y sacar a tablas/cómputos:
//
//    Tipo_Accesorio  Codo | Tee | Wye | Cruz      (pedido de material)
//    Angulo_Grados   ángulo característico         (pedido de material)
//    Diametro_Pulg   «12» o «12 x 8» si reduce     (pedido de material)
//    Material        material de la red            (pedido de material)
//    Cota_Eje_Pies   elevación del eje en la pieza (replanteo / perfil)
//
//  Se aplica solo al crear cada pieza (WyeSolido.Crear). PS_ACCESORIOS lo
//  agrega a las piezas de dibujos importados antes, leyendo su XDATA.
// ============================================================================

namespace Civil3DBasico
{
    internal static class AccesorioPropertySet
    {
        internal const string NOMBRE = "PDFCAD_Accesorio";

        private static readonly (string nombre, AecPD.DataType tipo, string descripcion)[] PROPIEDADES =
        {
            ("Tipo_Accesorio", AecPD.DataType.Text, "Tipo de accesorio: Codo, Tee, Wye o Cruz"),
            ("Angulo_Grados",  AecPD.DataType.Real, "Ángulo característico de la pieza, en grados"),
            ("Diametro_Pulg",  AecPD.DataType.Text, "Diámetro nominal en pulgadas (principal x ramal si reduce)"),
            ("Material",       AecPD.DataType.Text, "Material de la tubería que une"),
            ("Cota_Eje_Pies",  AecPD.DataType.Real, "Elevación del eje de la pieza, en pies"),
        };

        // Adjunta (o actualiza) el Property Set de la pieza a partir de su XDATA.
        // Devuelve true si quedaron escritos los valores.
        internal static bool AplicarDesdeXData(Database db, Transaction tr, Entity pieza, Editor ed)
        {
            var datos = LeerCampos(pieza);
            if (datos == null) return false;
            try
            {
                ObjectId psdId = AsegurarDefinicion(db, tr);
                if (psdId.IsNull) return false;

                if (!pieza.IsWriteEnabled) pieza.UpgradeOpen();
                ObjectId psId = PropertySetDe(tr, pieza, psdId);
                if (psId.IsNull)
                {
                    AecPS.PropertyDataServices.AddPropertySet(pieza, psdId);
                    psId = PropertySetDe(tr, pieza, psdId);
                }
                if (psId.IsNull)
                {
                    ed?.WriteMessage($"\n    ⚠ [PROPERTY SET] No se pudo adjuntar «{NOMBRE}» a la pieza.");
                    return false;
                }

                var ps = (AecPS.PropertySet)tr.GetObject(psId, OpenMode.ForWrite);
                string V(string k) => datos.TryGetValue(k, out string v) ? v : "";
                double pal = Num(V("DIAM_PRINCIPAL_IN")), ram = Num(V("DIAM_RAMAL_IN"));
                string diam = Math.Abs(pal - ram) < 0.05 || ram <= 0
                    ? pal.ToString("0.##", CultureInfo.InvariantCulture)
                    : $"{pal.ToString("0.##", CultureInfo.InvariantCulture)} x {ram.ToString("0.##", CultureInfo.InvariantCulture)}";

                Escribir(ps, "Tipo_Accesorio", NombreTipo(V("TIPO")));
                Escribir(ps, "Angulo_Grados", Math.Round(Num(V("ANGULO")), 1));
                Escribir(ps, "Diametro_Pulg", diam);
                Escribir(ps, "Material", V("MATERIAL"));
                Escribir(ps, "Cota_Eje_Pies", Math.Round(Num(V("COTA_EJE_FT")), 3));

                ed?.WriteMessage($"\n    · [PROPERTY SET] «{NOMBRE}»: {NombreTipo(V("TIPO"))}, " +
                    $"{Num(V("ANGULO")):F1}°, Ø{diam}\", {V("MATERIAL")}, eje {Num(V("COTA_EJE_FT")):F2} ft.");
                return true;
            }
            catch (Exception ex)
            {
                ed?.WriteMessage($"\n    ⚠ [PROPERTY SET] No se pudo escribir «{NOMBRE}»: {ex.Message}");
                return false;
            }
        }

        // La definición se crea una vez por dibujo. Si viene de una versión
        // anterior con menos campos, se le agregan los que falten.
        private static ObjectId AsegurarDefinicion(Database db, Transaction tr)
        {
            var dict = new AecPS.DictionaryPropertySetDefinitions(db);
            if (!dict.Has(NOMBRE, tr))
            {
                var psd = new AecPS.PropertySetDefinition();
                psd.SetToStandard(db);
                psd.SubSetDatabaseDefaults(db);
                psd.AlternateName = NOMBRE;
                psd.Description = "Accesorio de tubería generado por PDF-a-CAD (sólido 3D)";
                var filtro = new StringCollection { "AcDb3dSolid" };
                psd.SetAppliesToFilter(filtro, false);
                foreach (var p in PROPIEDADES) psd.Definitions.Add(NuevaPropiedad(db, p));
                dict.AddNewRecord(NOMBRE, psd);
                tr.AddNewlyCreatedDBObject(psd, true);
                return dict.GetAt(NOMBRE);
            }

            ObjectId id = dict.GetAt(NOMBRE);
            var existente = (AecPS.PropertySetDefinition)tr.GetObject(id, OpenMode.ForRead);
            var tiene = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (AecPS.PropertyDefinition pd in existente.Definitions) tiene.Add(pd.Name);
            foreach (var p in PROPIEDADES)
            {
                if (tiene.Contains(p.nombre)) continue;
                if (!existente.IsWriteEnabled) existente.UpgradeOpen();
                existente.Definitions.Add(NuevaPropiedad(db, p));
            }
            return id;
        }

        private static AecPS.PropertyDefinition NuevaPropiedad(
            Database db, (string nombre, AecPD.DataType tipo, string descripcion) p)
        {
            var pd = new AecPS.PropertyDefinition();
            pd.SetToStandard(db);
            pd.SubSetDatabaseDefaults(db);
            pd.Name = p.nombre;
            pd.Description = p.descripcion;
            pd.DataType = p.tipo;
            pd.DefaultData = p.tipo == AecPD.DataType.Real ? (object)0.0 : "";
            return pd;
        }

        private static ObjectId PropertySetDe(Transaction tr, Entity ent, ObjectId psdId)
        {
            try
            {
                ObjectIdCollection ids = AecPS.PropertyDataServices.GetPropertySets(ent);
                if (ids == null) return ObjectId.Null;
                foreach (ObjectId pid in ids)
                {
                    var ps = tr.GetObject(pid, OpenMode.ForRead) as AecPS.PropertySet;
                    if (ps != null && ps.PropertySetDefinition == psdId) return pid;
                }
            }
            catch { }
            return ObjectId.Null;
        }

        private static void Escribir(AecPS.PropertySet ps, string nombre, object valor)
        {
            int id = ps.PropertyNameToId(nombre);
            if (id >= 0) ps.SetAt(id, valor);
        }

        private static Dictionary<string, string> LeerCampos(Entity ent)
        {
            var lista = WyeSolido.LeerXData(ent);
            if (lista == null) return null;
            var d = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            foreach (string s in lista)
            {
                int eq = s.IndexOf('=');
                if (eq > 0) d[s.Substring(0, eq)] = s.Substring(eq + 1);
            }
            return d;
        }

        // El XDATA se grabó con la cultura del equipo: «12,0» o «12.0».
        private static double Num(string s) =>
            double.TryParse((s ?? "").Replace(',', '.'), NumberStyles.Float,
                CultureInfo.InvariantCulture, out double v) ? v : 0.0;

        private static string NombreTipo(string tipo)
        {
            switch ((tipo ?? "").ToUpperInvariant())
            {
                case "ELBOW": return "Codo";
                case "TEE": return "Tee";
                case "WYE": return "Wye";
                case "CROSS": return "Cruz";
                default: return tipo ?? "";
            }
        }
    }

    public class ComandosAccesorioPropertySet
    {
        // Dibujos importados antes de esta versión: sus piezas tienen XDATA pero
        // no el Property Set. Este comando se lo agrega (o lo actualiza) a todas.
        [CommandMethod("PS_ACCESORIOS")]
        public void AplicarATodos()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            Editor ed = doc.Editor;
            Database db = doc.Database;
            using (doc.LockDocument())
            using (Transaction tr = db.TransactionManager.StartTransaction())
            {
                var bt = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
                var ms = (BlockTableRecord)tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForRead);
                int ok = 0, total = 0;
                foreach (ObjectId id in ms)
                {
                    if (id.ObjectClass.DxfName != "3DSOLID") continue;
                    var ent = (Entity)tr.GetObject(id, OpenMode.ForRead);
                    if (WyeSolido.LeerXData(ent) == null) continue;
                    total++;
                    if (AccesorioPropertySet.AplicarDesdeXData(db, tr, ent, null)) ok++;
                }
                tr.Commit();
                ed.WriteMessage($"\n✓ Property Set «{AccesorioPropertySet.NOMBRE}» aplicado a {ok} de {total} accesorio(s).");
            }
        }
    }
}

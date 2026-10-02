using System;
using System.Collections.Generic;
using System.Collections.Specialized;
using System.Text;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using AecPS = Autodesk.Aec.PropertyData.DatabaseServices;
using AecPD = Autodesk.Aec.PropertyData;
using Exception = System.Exception;

// ============================================================================
//  Property Set de los SÓLIDOS (cajas cuadradas reconocidas del PDF)
//
//  «PDFCAD_Solido» se adjunta al Solid3d que dibuja ImportarRed.CrearSolidos:
//  código, medidas, cotas y TODOS los datos extendidos que la app guardó en la
//  estructura (XD_* = automáticos del reconocimiento: capa OCG, disciplina,
//  estado, origen…; XDU_* = campos del usuario). Aparece en la paleta
//  Propiedades (pestaña «Datos extendidos»), se puede filtrar y sacar a tablas.
//  Los campos extendidos varían por proyecto: la definición se amplía sola con
//  los que falten (nunca se borra ninguno).
// ============================================================================

namespace Civil3DBasico
{
    internal static class SolidoPropertySet
    {
        internal const string NOMBRE = "PDFCAD_Solido";

        private static readonly (string nombre, AecPD.DataType tipo, string descripcion)[] FIJAS =
        {
            ("Codigo",             AecPD.DataType.Text, "Código del sólido en la app (SÓLIDO-N)"),
            ("Largo_Pies",         AecPD.DataType.Real, "Largo (lado largo), en pies"),
            ("Ancho_Pies",         AecPD.DataType.Real, "Ancho (lado corto), en pies"),
            ("Altura_Pies",        AecPD.DataType.Real, "Altura del sólido, en pies"),
            ("Cota_Superior_Pies", AecPD.DataType.Real, "Elevación de la cara superior, en pies"),
            ("Cota_Base_Pies",     AecPD.DataType.Real, "Elevación de la base, en pies"),
        };

        /// <summary>Adjunta el Property Set al sólido con sus medidas y `extra`
        /// (clave XDATA → valor). Devuelve true si quedó escrito.</summary>
        internal static bool Aplicar(Database db, Transaction tr, Entity solido, Editor ed,
            string codigo, double largo, double ancho, double alto, double zTop, double zBase,
            IDictionary<string, string> extra)
        {
            try
            {
                var campos = new List<(string nombre, string clave)>();
                foreach (var kv in extra)
                {
                    string n = NombrePropiedad(kv.Key);
                    if (n.Length > 0) campos.Add((n, kv.Key));
                }
                ObjectId psdId = AsegurarDefinicion(db, tr, campos);
                if (psdId.IsNull) return false;
                if (!solido.IsWriteEnabled) solido.UpgradeOpen();
                ObjectId psId = PropertySetDe(tr, solido, psdId);
                if (psId.IsNull)
                {
                    AecPS.PropertyDataServices.AddPropertySet(solido, psdId);
                    psId = PropertySetDe(tr, solido, psdId);
                }
                if (psId.IsNull) return false;
                var ps = (AecPS.PropertySet)tr.GetObject(psId, OpenMode.ForWrite);
                Escribir(ps, "Codigo", codigo ?? "");
                Escribir(ps, "Largo_Pies", Math.Round(largo, 3));
                Escribir(ps, "Ancho_Pies", Math.Round(ancho, 3));
                Escribir(ps, "Altura_Pies", Math.Round(alto, 5));
                Escribir(ps, "Cota_Superior_Pies", Math.Round(zTop, 3));
                Escribir(ps, "Cota_Base_Pies", Math.Round(zBase, 3));
                foreach (var (nombre, clave) in campos) Escribir(ps, nombre, extra[clave] ?? "");
                return true;
            }
            catch (Exception ex)
            {
                ed?.WriteMessage($"\n    ⚠ [PROPERTY SET] No se pudo escribir «{NOMBRE}» en '{codigo}': {ex.Message}");
                return false;
            }
        }

        // XD_CAPA_OCG → «CAPA_OCG»; XDU_NOTA → «Usuario_NOTA». Solo letras,
        // dígitos y «_» (nombres válidos de propiedad).
        private static string NombrePropiedad(string clave)
        {
            string c = clave ?? "";
            string b = c.StartsWith("XDU_", StringComparison.OrdinalIgnoreCase) ? "Usuario_" + c.Substring(4)
                     : c.StartsWith("XD_", StringComparison.OrdinalIgnoreCase) ? c.Substring(3) : "";
            var sb = new StringBuilder();
            foreach (char ch in b) sb.Append(char.IsLetterOrDigit(ch) && ch < 128 ? ch : '_');
            string n = sb.ToString().Trim('_');
            return n.Length > 60 ? n.Substring(0, 60) : n;
        }

        private static ObjectId AsegurarDefinicion(Database db, Transaction tr, List<(string nombre, string clave)> extra)
        {
            var dict = new AecPS.DictionaryPropertySetDefinitions(db);
            ObjectId id;
            AecPS.PropertySetDefinition psd;
            if (!dict.Has(NOMBRE, tr))
            {
                psd = new AecPS.PropertySetDefinition();
                psd.SetToStandard(db);
                psd.SubSetDatabaseDefaults(db);
                psd.AlternateName = NOMBRE;
                psd.Description = "Sólido 3D de caja reconocida del PDF (PDF-a-CAD)";
                psd.SetAppliesToFilter(new StringCollection { "AcDb3dSolid" }, false);
                foreach (var p in FIJAS) psd.Definitions.Add(NuevaPropiedad(db, p.nombre, p.tipo, p.descripcion));
                dict.AddNewRecord(NOMBRE, psd);
                tr.AddNewlyCreatedDBObject(psd, true);
                id = dict.GetAt(NOMBRE);
            }
            else
            {
                id = dict.GetAt(NOMBRE);
                psd = (AecPS.PropertySetDefinition)tr.GetObject(id, OpenMode.ForRead);
            }
            var tiene = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (AecPS.PropertyDefinition pd in psd.Definitions) tiene.Add(pd.Name);
            foreach (var p in FIJAS)
                if (tiene.Add(p.nombre))
                {
                    if (!psd.IsWriteEnabled) psd.UpgradeOpen();
                    psd.Definitions.Add(NuevaPropiedad(db, p.nombre, p.tipo, p.descripcion));
                }
            foreach (var (nombre, clave) in extra)
                if (tiene.Add(nombre))
                {
                    if (!psd.IsWriteEnabled) psd.UpgradeOpen();
                    psd.Definitions.Add(NuevaPropiedad(db, nombre, AecPD.DataType.Text, "Dato extendido " + clave));
                }
            return id;
        }

        private static AecPS.PropertyDefinition NuevaPropiedad(Database db, string nombre,
            AecPD.DataType tipo, string descripcion)
        {
            var pd = new AecPS.PropertyDefinition();
            pd.SetToStandard(db);
            pd.SubSetDatabaseDefaults(db);
            pd.Name = nombre;
            pd.Description = descripcion;
            pd.DataType = tipo;
            pd.DefaultData = tipo == AecPD.DataType.Real ? (object)0.0 : "";
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
    }
}

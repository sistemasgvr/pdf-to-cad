using System;
using System.Collections.Generic;
using System.Collections.Specialized;
using System.Linq;
using System.Text;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Runtime;
using AecPS = Autodesk.Aec.PropertyData.DatabaseServices;
using AecPD = Autodesk.Aec.PropertyData;
using Exception = System.Exception;

// ============================================================================
//  Property Sets genéricos de PDF-a-CAD (los de la red: tuberías, estructuras,
//  accesorios de presión). Mismo esquema que SolidoPropertySet: la definición se
//  crea una vez por dibujo con sus campos fijos y se AMPLÍA sola con los datos
//  extendidos que traiga cada objeto (XD_* → sin prefijo; XDU_* → «Usuario_…»);
//  nunca se borra un campo. Se ve en Propiedades → pestaña «Datos extendidos».
//  Las clases a las que se aplica se piden a Civil 3D (RXObject.GetClass), así el
//  nombre es el real en cualquier versión.
// ============================================================================

namespace Civil3DBasico
{
    internal sealed class DefinicionPS
    {
        public string Nombre;
        public string Descripcion;
        public Type[] Tipos;                                         // clases .NET de Civil 3D
        public (string nombre, AecPD.DataType tipo, string descripcion)[] Fijas;
    }

    internal static class PropertySetPdfcad
    {
        /// <summary>XD_CAPA_OCG → «CAPA_OCG»; XDU_NOTA → «Usuario_NOTA» ("" si no es dato
        /// extendido). Solo letras ASCII, dígitos y «_» (nombres válidos de propiedad).</summary>
        internal static string NombrePropiedad(string clave)
        {
            string c = clave ?? "";
            string b = c.StartsWith("XDU_", StringComparison.OrdinalIgnoreCase) ? "Usuario_" + c.Substring(4)
                     : c.StartsWith("XD_", StringComparison.OrdinalIgnoreCase) ? c.Substring(3) : "";
            var sb = new StringBuilder();
            foreach (char ch in b) sb.Append(char.IsLetterOrDigit(ch) && ch < 128 ? ch : '_');
            string n = sb.ToString().Trim('_');
            return n.Length > 60 ? n.Substring(0, 60) : n;
        }

        /// <summary>Adjunta (o actualiza) el Property Set `def` en `ent` con los valores
        /// fijos y los datos extendidos `extra` (clave XDATA → valor).</summary>
        internal static bool Aplicar(Database db, Transaction tr, Entity ent, DefinicionPS def,
            IDictionary<string, object> fijas, IDictionary<string, string> extra, Editor ed)
        {
            try
            {
                var campos = new List<(string nombre, string clave)>();
                if (extra != null)
                    foreach (var kv in extra)
                    {
                        string n = NombrePropiedad(kv.Key);
                        if (n.Length > 0 && !campos.Any(c => c.nombre.Equals(n, StringComparison.OrdinalIgnoreCase)))
                            campos.Add((n, kv.Key));
                    }
                ObjectId psdId = AsegurarDefinicion(db, tr, def, campos);
                if (psdId.IsNull) return false;
                if (!ent.IsWriteEnabled) ent.UpgradeOpen();
                ObjectId psId = PropertySetDe(tr, ent, psdId);
                if (psId.IsNull)
                {
                    AecPS.PropertyDataServices.AddPropertySet(ent, psdId);
                    psId = PropertySetDe(tr, ent, psdId);
                }
                if (psId.IsNull) return false;
                var ps = (AecPS.PropertySet)tr.GetObject(psId, OpenMode.ForWrite);
                if (fijas != null)
                    foreach (var kv in fijas) Escribir(ps, kv.Key, kv.Value ?? "");
                foreach (var (nombre, clave) in campos) Escribir(ps, nombre, extra[clave] ?? "");
                return true;
            }
            catch (Exception ex)
            {
                ed?.WriteMessage($"\n    ⚠ [PROPERTY SET] No se pudo escribir «{def.Nombre}»: {ex.Message}");
                return false;
            }
        }

        private static StringCollection Clases(DefinicionPS def)
        {
            var sc = new StringCollection();
            foreach (var t in def.Tipos ?? Array.Empty<Type>())
            {
                try
                {
                    string n = RXObject.GetClass(t)?.Name;
                    if (!string.IsNullOrEmpty(n) && !sc.Contains(n)) sc.Add(n);
                }
                catch { }
            }
            return sc;
        }

        private static ObjectId AsegurarDefinicion(Database db, Transaction tr, DefinicionPS def,
            List<(string nombre, string clave)> extra)
        {
            var dict = new AecPS.DictionaryPropertySetDefinitions(db);
            ObjectId id;
            AecPS.PropertySetDefinition psd;
            var clases = Clases(def);
            if (!dict.Has(def.Nombre, tr))
            {
                psd = new AecPS.PropertySetDefinition();
                psd.SetToStandard(db);
                psd.SubSetDatabaseDefaults(db);
                psd.AlternateName = def.Nombre;
                psd.Description = def.Descripcion;
                psd.SetAppliesToFilter(clases, false);
                foreach (var p in def.Fijas) psd.Definitions.Add(NuevaPropiedad(db, p.nombre, p.tipo, p.descripcion));
                dict.AddNewRecord(def.Nombre, psd);
                tr.AddNewlyCreatedDBObject(psd, true);
                id = dict.GetAt(def.Nombre);
            }
            else
            {
                id = dict.GetAt(def.Nombre);
                psd = (AecPS.PropertySetDefinition)tr.GetObject(id, OpenMode.ForRead);
                // Una definición de una versión anterior puede no aplicarse a todas las clases.
                var actual = psd.AppliesToFilter ?? new StringCollection();
                bool falta = false;
                foreach (string c in clases) if (!actual.Contains(c)) { actual.Add(c); falta = true; }
                if (falta)
                {
                    if (!psd.IsWriteEnabled) psd.UpgradeOpen();
                    psd.SetAppliesToFilter(actual, false);
                }
            }
            var tiene = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (AecPS.PropertyDefinition pd in psd.Definitions) tiene.Add(pd.Name);
            foreach (var p in def.Fijas)
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
            pd.DefaultData = tipo == AecPD.DataType.Real ? (object)0.0
                           : tipo == AecPD.DataType.Integer ? (object)0 : "";
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

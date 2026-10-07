using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Xml.Linq;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using CivilDB = Autodesk.Civil.DatabaseServices;                 // alias: objetos de Civil 3D (Network, Structure, Pipe...)
using PartsStyles = Autodesk.Civil.DatabaseServices.Styles;      // alias: catálogo (PartsList, PartFamily, PartSize...)
using Exception = System.Exception;

// ============================================================================
//  GUÍA RÁPIDA (detalle en README.md, sección 4)
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
    /// Elección de familias y tamaños del catálogo para las redes que crea IMPORTAR_RED.
    /// </summary>
    public partial class ComandosRedes
    {
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

            // Reordenar las familias: EXACT match de Description primero (por si
            // el material pedido es exactamente el nombre de una familia — típico
            // cuando el pre-scan de ductbank pasa el nombre exacto de la familia
            // que aceptó la inyección). Sin esto, "HDPE Pipe" caía por substring
            // en "Corrugated HDPE Pipe" (primera alfabéticamente), que no tenía
            // el tamaño inyectado → fallback a tamaño default.
            var famIds = new List<ObjectId>();
            var famIdsResto = new List<ObjectId>();
            foreach (ObjectId fid in partsList.GetPartFamilyIdsByDomain(CivilDB.DomainType.Pipe))
            {
                var famPre = tr.GetObject(fid, OpenMode.ForRead) as PartsStyles.PartFamily;
                if (famPre == null || famPre.PartSizeCount == 0) continue;
                if (!esCatalogId && mN.Length > 0 &&
                    famPre.Description != null &&
                    string.Equals(Norm(famPre.Description), mN, StringComparison.Ordinal))
                    famIds.Add(fid);
                else
                    famIdsResto.Add(fid);
            }
            famIds.AddRange(famIdsResto);

            foreach (ObjectId fid in famIds)
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
                        // Coincidencia parcial por nombre (p.ej. "4" dentro de "4 in")
                        for (int i = 0; i < fam.PartSizeCount; i++)
                        {
                            PartsStyles.PartSize sz = tr.GetObject(fam[i], OpenMode.ForRead) as PartsStyles.PartSize;
                            string sn = Norm(sz?.Name ?? "");
                            if (sn.Contains(dN))
                            { sizeElegido = fam[i]; sizeNombre = sz?.Name; exacto = true; break; }
                        }
                    }
                    // Búsqueda por valor numérico del diámetro (idioma-agnóstica).
                    // Primero intenta SizeMasCercano (familias con InnerWidth);
                    // si no hay datos, extrae el número al inicio del nombre
                    // ("4 pulg. Tubería de PEAD" → 4.0).
                    if (!exacto && wPedido == null)
                    {
                        double dVal = 0;
                        var mDiam = System.Text.RegularExpressions.Regex.Match(
                            (diam ?? "").Trim(), @"^(\d+(?:\.\d+)?)");
                        if (mDiam.Success)
                            double.TryParse(mDiam.Groups[1].Value, NumberStyles.Float,
                                CultureInfo.InvariantCulture, out dVal);
                        if (dVal > 0)
                        {
                            ObjectId cercDiam = SizeMasCercano(tr, fam, dVal, dVal,
                                CivilDB.PartContextType.PipeInnerWidth, CivilDB.PartContextType.PipeInnerHeight,
                                out string nomDiam, out bool exDiam);
                            if (cercDiam != ObjectId.Null && exDiam)
                            { sizeElegido = cercDiam; sizeNombre = nomDiam; exacto = true; }
                        }
                        if (!exacto && dVal > 0)
                        {
                            for (int i = 0; i < fam.PartSizeCount; i++)
                            {
                                var szN = tr.GetObject(fam[i], OpenMode.ForRead) as PartsStyles.PartSize;
                                var mSz = System.Text.RegularExpressions.Regex.Match(
                                    (szN?.Name ?? "").Trim(), @"^(\d+(?:\.\d+)?)");
                                if (!mSz.Success) continue;
                                if (double.TryParse(mSz.Groups[1].Value, NumberStyles.Float,
                                        CultureInfo.InvariantCulture, out double szVal) &&
                                    Math.Abs(szVal - dVal) < 0.01)
                                { sizeElegido = fam[i]; sizeNombre = szN.Name; exacto = true; break; }
                            }
                        }
                    }
                }
                // Sin match exacto: intentar agregar el diámetro pedido al
                // catálogo (seteando el campo de diámetro del SizeFilterRecord).
                if (!exacto && dN.Length > 0)
                {
                    double diamNum = 0;
                    {
                        var mDN = System.Text.RegularExpressions.Regex.Match(
                            (diam ?? "").Trim(), @"^(\d+(?:\.\d+)?)");
                        if (mDN.Success)
                            double.TryParse(mDN.Groups[1].Value, NumberStyles.Float,
                                CultureInfo.InvariantCulture, out diamNum);
                    }
                    Editor edLocal = null;
                    try { edLocal = Application.DocumentManager.MdiActiveDocument?.Editor; } catch { }
                    if (wPedido.HasValue && hPedido.HasValue)
                    {
                        // «W x H» (bancoducto, elíptica…): ancho y alto EXACTOS del
                        // catálogo (tamaño agregado con el «+» de la app).
                        var vals = new Dictionary<CivilDB.PartContextType, double>
                        {
                            [CivilDB.PartContextType.PipeInnerWidth] = wPedido.Value,
                            [CivilDB.PartContextType.PipeInnerHeight] = hPedido.Value,
                        };
                        ObjectId reRect = SizeExacto(tr, fam, vals, out string nomRect);
                        if (reRect == ObjectId.Null && AgregarTamanoExacto(fam, vals, edLocal))
                            reRect = SizeExacto(tr, fam, vals, out nomRect);
                        if (reRect != ObjectId.Null)
                        { sizeElegido = reRect; sizeNombre = nomRect; exacto = true; }
                    }
                    else if (diamNum > 0 && AgregarTamañoPipe(tr, fam, diamNum, edLocal))
                    {
                        // Re-buscar: primero por InnerWidth, luego por número en el nombre
                        ObjectId reId = SizeMasCercano(tr, fam, diamNum, diamNum,
                            CivilDB.PartContextType.PipeInnerWidth, CivilDB.PartContextType.PipeInnerHeight,
                            out string reNom, out bool reExacto);
                        if (reId != ObjectId.Null && reExacto)
                        { sizeElegido = reId; sizeNombre = reNom; exacto = true; }
                        if (!exacto)
                        {
                            for (int ri = 0; ri < fam.PartSizeCount; ri++)
                            {
                                var szR = tr.GetObject(fam[ri], OpenMode.ForRead) as PartsStyles.PartSize;
                                var mR = System.Text.RegularExpressions.Regex.Match(
                                    (szR?.Name ?? "").Trim(), @"^(\d+(?:\.\d+)?)");
                                if (!mR.Success) continue;
                                if (double.TryParse(mR.Groups[1].Value, NumberStyles.Float,
                                        CultureInfo.InvariantCulture, out double rvl) &&
                                    Math.Abs(rvl - diamNum) < 0.01)
                                { sizeElegido = fam[ri]; sizeNombre = szR.Name; exacto = true; break; }
                            }
                        }
                    }
                    if (!exacto)
                    {
                        string aviso;
                        if (TryParseRectSize(diam, out double? w, out double? h) && w.HasValue && h.HasValue)
                        {
                            ObjectId cercano = SizeMasCercano(tr, fam, w.Value, h.Value,
                                CivilDB.PartContextType.PipeInnerWidth, CivilDB.PartContextType.PipeInnerHeight,
                                out string nombreCercano, out bool esExacto2);
                            if (cercano != ObjectId.Null)
                            {
                                sizeElegido = cercano; sizeNombre = nombreCercano;
                                aviso = esExacto2 ? null
                                    : $"\n⚠ Tamaño '{diam}' no existe en el catálogo de '{fam.Description}' — usando el más cercano disponible '{nombreCercano}'. Para la medida exacta, agrégala en Part Builder.";
                            }
                            else
                                aviso = $"\n⚠ Tamaño '{diam}' no disponible en '{fam.Description}' — usando '{sizeNombre}' en su lugar. Para medidas personalizadas, usa Part Builder.";
                        }
                        else
                            aviso = $"\n⚠ Tamaño '{diam}' no disponible en '{fam.Description}' — usando '{sizeNombre}' en su lugar. Para medidas personalizadas, usa Part Builder.";
                        if (aviso != null)
                            try { edLocal?.WriteMessage(aviso); } catch { }
                    }
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
                                      out ObjectId familyId, out ObjectId sizeId, out string nombre,
                                      string guid = "")
        {
            familyId = ObjectId.Null; sizeId = ObjectId.Null; nombre = "";
            ObjectId anyFam = ObjectId.Null, anySize = ObjectId.Null; string anyNom = "";
            string tNorm = Norm(tipo);
            // Preferir el GUID (estable, independiente del idioma): si viene, la
            // familia se elige por igualdad EXACTA de PartFamily.GUID — nunca cae
            // en 'anyFam' (la primera de la lista), que es lo que hacía aparecer
            // una familia distinta a la elegida.
            bool usaGuid = !string.IsNullOrWhiteSpace(guid);
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
                // Camino por GUID: familia elegida por igualdad EXACTA. Se saltan las
                // exclusiones por texto y el filtro custom (el usuario la pidió a
                // propósito), y se procede directo a elegir el tamaño más abajo.
                if (usaGuid && !MismoGuid(fam.GUID, guid))
                    continue;
                // Descartar Null/nula + no-buzones (headwall/embocadura/sección final/ala) EN/ES.
                if (!usaGuid && (
                    descBz.IndexOf("Null", StringComparison.OrdinalIgnoreCase) >= 0 ||
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
                    descBz.IndexOf("cabezal", StringComparison.OrdinalIgnoreCase) >= 0)) continue;

                // Tamaño por defecto (barato): el primero de la familia. Solo se usa
                // de verdad si esta familia resulta ser la elegida (por 'tipo' o, en
                // último caso, como fallback 'anyFam').
                ObjectId elegidoSize = fam[0];
                string elegidoSizeName = (tr.GetObject(elegidoSize, OpenMode.ForRead) as PartsStyles.PartSize)?.Name;
                string nom = $"{fam.Description} / {elegidoSizeName}";
                if (!usaGuid)
                {
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
                    // Solo se sigue en la familia que coincide con 'tipo'.
                    if (!famMatch) continue;
                }
                // La búsqueda/creación de tamaño (cara, y muta la familia con
                // AddPartSize/RemovePartSize) SOLO se intenta en la familia que
                // realmente coincide con 'tipo' — antes corría para TODAS las
                // familias de estructura en cada llamada (aunque no fueran a usarse),
                // lo cual era lento y multiplicaba el riesgo de dejar tamaños
                // "- N" huérfanos si algún RemovePartSize fallaba en una familia
                // que ni siquiera era la elegida.

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
                // Sin match exacto: si el catálogo TRAE esa medida (tamaño agregado
                // desde la app con el «+», CatalogoTamanos.cs) se agrega a la lista de
                // piezas del dibujo y se usa. Si no, NO se inventa: solo se elige
                // entre los que YA existen en la familia. Si el
                if (!sizeExacto && !string.IsNullOrWhiteSpace(radio))
                {
                    var vals = ValoresEstructura(radio);
                    var edS = Application.DocumentManager.MdiActiveDocument?.Editor;
                    string nomNuevo = "";
                    if (vals != null && (SizeExacto(tr, fam, vals, out nomNuevo) != ObjectId.Null
                                         || AgregarTamanoExacto(fam, vals, edS)))
                    {
                        ObjectId nuevo = SizeExacto(tr, fam, vals, out nomNuevo);
                        if (nuevo != ObjectId.Null)
                        { elegidoSize = nuevo; elegidoSizeName = nomNuevo; sizeExacto = true; }
                    }
                }
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
            // Fallback 'anyFam' SOLO en el camino por texto. Con GUID, si no se
            // encontró la familia exacta se deja familyId=Null (el llamante usará
            // el default explícito) en vez de poner una familia equivocada.
            if (!usaGuid && anyFam != ObjectId.Null) { familyId = anyFam; sizeId = anySize; nombre = anyNom; }
        }

        private static string Norm(string s) => (s ?? "").Replace(" ", "").Replace(",", "").ToLowerInvariant();

        // Compara dos GUIDs tolerando diferencias de formato (llaves {}, guiones,
        // mayúsculas): el XML del catálogo trae el GUID SIN llaves mientras que
        // PartFamily.GUID/DataPartFamily.GUID pueden traerlas. Se parsean como Guid
        // real cuando se puede; si no, comparación textual normalizada.
        internal static bool MismoGuid(string a, string b)
        {
            if (string.IsNullOrWhiteSpace(a) || string.IsNullOrWhiteSpace(b)) return false;
            if (System.Guid.TryParse(a, out var ga) && System.Guid.TryParse(b, out var gb))
                return ga == gb;
            return string.Equals(a.Trim(), b.Trim(), StringComparison.OrdinalIgnoreCase);
        }

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
        // Agrega un tamaño ESPECÍFICO (por diámetro en pulgadas) a una PartFamily
        // que ya está en la Parts List. Busca el campo de "diámetro interior" en el
        // SizeFilterRecord, setea su valor al pedido, y multi-selecciona el resto
        // (espesor de pared, etc.) para que se agreguen todas las variantes.
        // Devuelve true si se agregó al menos un tamaño nuevo.
        internal static bool AgregarTamañoPipePublico(Transaction tr, PartsStyles.PartFamily fam,
            double diamPulgadas, Editor ed) => AgregarTamañoPipe(tr, fam, diamPulgadas, ed);

        private static bool AgregarTamañoPipe(Transaction tr, PartsStyles.PartFamily fam,
            double diamPulgadas, Editor ed)
        {
            try
            {
                try { fam.UpgradeOpen(); } catch { }
                int antes = fam.PartSizeCount;
                var filtro = new PartsStyles.SizeFilterRecord(fam);
                bool cambioDiam = false;
                bool diamValueOk = false;
                string diamErr = "";
                for (int i = 0; i < filtro.ParamCount; i++)
                {
                    var campo = filtro[i];
                    if (campo == null || campo.IsReadOnly) continue;
                    string nmDbg = (campo.Name ?? "") + "/" + (campo.Description ?? "") + " IsFromList=" + campo.IsFromList;
                    if (!campo.IsFromList) { Dl(ed, $"\n    [ATP-SKIP] fam='{fam.Description}' d={diamPulgadas:F1} campo={nmDbg}"); continue; }
                    string nm = ((campo.Name ?? "") + " " + (campo.Description ?? "")).ToLowerInvariant();
                    bool esDiam = nm.Contains("diameter") || nm.Contains("diámetro") ||
                                  nm.Contains("diametro") || nm.Contains("inner width") ||
                                  nm.Contains("ancho interior");
                    bool esWall = nm.Contains("wall") || nm.Contains("thickness") ||
                                  nm.Contains("pared") || nm.Contains("grosor") ||
                                  nm.Contains("espesor");
                    // Log valores permitidos si es diameter (para saber si 1" está en la lista)
                    if (esDiam)
                    {
                        // Intentar listar valores permitidos vía reflexión
                        try
                        {
                            var t = campo.GetType();
                            string s = "";
                            foreach (var pn in new[] { "AllowedValues", "ListValues", "Values" })
                            {
                                var pi = t.GetProperty(pn);
                                if (pi != null)
                                {
                                    var vals = pi.GetValue(campo) as System.Collections.IEnumerable;
                                    if (vals != null) { foreach (var v in vals) s += v + ";"; break; }
                                }
                            }
                            Dl(ed, $"\n    [ATP-DIAM-VALS] fam='{fam.Description}' d={diamPulgadas:F1} allowed=[{s}]");
                        }
                        catch (Exception exV) { Dl(ed, $"\n    [ATP-DIAM-VALS-ERR] {exV.Message}"); }
                        try { campo.Value = diamPulgadas; cambioDiam = true; diamValueOk = true; }
                        catch (Exception exD) { diamErr = exD.Message; Dl(ed, $"\n    [ATP-DIAM-SET-FAIL] fam='{fam.Description}' d={diamPulgadas:F1} err={exD.Message}"); }
                    }
                    else if (esWall)
                    {
                        try { campo.IsMultipleSelect = false; } catch { }
                        try { campo.Value = 0.0; Dl(ed, $"\n    [ATP-WALL0-OK] fam='{fam.Description}'"); }
                        catch (Exception exW)
                        {
                            Dl(ed, $"\n    [ATP-WALL0-FAIL] fam='{fam.Description}' err={exW.Message} → multi-select");
                            try { campo.IsMultipleSelect = true; } catch { }
                        }
                    }
                    else
                        try { campo.IsMultipleSelect = true; } catch { }
                }
                if (!cambioDiam)
                {
                    Dl(ed, $"\n    [ATP-NO-DIAM-FIELD] fam='{fam.Description}' d={diamPulgadas:F1} paramCount={filtro.ParamCount} diamErr='{diamErr}'");
                    return false;
                }
                try
                {
                    fam.AddPartSize(filtro);
                }
                catch (Exception exAdd)
                {
                    Dl(ed, $"\n    [ATP-ADD-FAIL] fam='{fam.Description}' d={diamPulgadas:F1} err={exAdd.Message}");
                    return false;
                }
                int nuevos = fam.PartSizeCount - antes;
                if (nuevos > 0)
                {
                    ed.WriteMessage($"\n  + Tamaño {diamPulgadas:F0}\" agregado a " +
                        $"'{fam.Description}' ({nuevos} variante(s)).");
                    return true;
                }
                Dl(ed, $"\n    [ATP-NO-NEW] fam='{fam.Description}' d={diamPulgadas:F1} — AddPartSize no creó variantes nuevas");
                return false;
            }
            catch (Exception exOut) { Dl(ed, $"\n    [ATP-OUTER-ERR] fam='{fam.Description}' d={diamPulgadas:F1} err={exOut.Message}"); return false; }
        }

        // Comprueba si un diámetro (en pulgadas) ya existe como tamaño exacto
        // en alguna familia de tuberías del Parts List — parsing del nombre
        // ("4 pulg. Tubería de PEAD" → 4.0).
        internal static bool ExisteTamañoPipeExacto(Transaction tr,
            PartsStyles.PartsList partsList, double diamPulgadas)
        {
            foreach (ObjectId fid in partsList.GetPartFamilyIdsByDomain(CivilDB.DomainType.Pipe))
            {
                var fam = tr.GetObject(fid, OpenMode.ForRead) as PartsStyles.PartFamily;
                if (fam == null) continue;
                for (int i = 0; i < fam.PartSizeCount; i++)
                {
                    var sz = tr.GetObject(fam[i], OpenMode.ForRead) as PartsStyles.PartSize;
                    var m = System.Text.RegularExpressions.Regex.Match(
                        (sz?.Name ?? "").Trim(), @"^(\d+(?:\.\d+)?)");
                    if (m.Success && double.TryParse(m.Groups[1].Value, NumberStyles.Float,
                            CultureInfo.InvariantCulture, out double v) &&
                        Math.Abs(v - diamPulgadas) < 0.01)
                        return true;
                }
            }
            return false;
        }

        /// <summary>
        /// Inyecta un diámetro que NO existe en el catálogo XML de Autodesk,
        /// editando directamente el .xml de la familia dentro de ProgramData.
        /// Luego llama a AgregarTamañoPipe para que Civil 3D lo recoja.
        /// </summary>
        internal static bool InyectarTamañoEnCatalogo(Transaction tr,
            PartsStyles.PartFamily fam, double diamPulgadas, Editor ed,
            double? wallOverride = null)
        {
            try
            {
                string guid = fam.GUID;
                if (string.IsNullOrEmpty(guid)) return false;

                string xmlPath = BuscarXmlFamilia(guid);
                if (xmlPath == null)
                {
                    ed.WriteMessage($"\n  (No se encontró el XML del catálogo para '{fam.Description}')");
                    return false;
                }

                XDocument doc = XDocument.Load(xmlPath);
                XElement root = doc.Root;
                if (root == null) { ed?.WriteMessage($"\n  (XML raíz nula en '{xmlPath}')"); return false; }

                // Buscar la columna de diámetro interior (context=PipeInnerDiameter)
                XElement colPID = root.Elements("Column")
                    .FirstOrDefault(c => (string)c.Attribute("context") == "PipeInnerDiameter");
                if (colPID == null)
                {
                    Dl(ed, $"\n    [INJ-NO-COLPID] fam='{fam.Description}' d={diamPulgadas:F1} xml='{System.IO.Path.GetFileName(xmlPath)}' — familia sin columna PipeInnerDiameter");
                    return false;
                }
                Dl(ed, $"\n    [INJ-START] fam='{fam.Description}' d={diamPulgadas:F1} xml='{System.IO.Path.GetFileName(xmlPath)}'");

                // Verificar si el diámetro ya existe en el XML
                XElement colWThExisting = root.Elements("Column")
                    .FirstOrDefault(c => (string)c.Attribute("context") == "WallThickness");
                foreach (XElement row in colPID.Elements("Row"))
                {
                    if (double.TryParse(row.Value, NumberStyles.Float,
                            CultureInfo.InvariantCulture, out double v) &&
                        Math.Abs(v - diamPulgadas) < 0.01)
                    {
                        // Si estamos en modo conducto (wallOverride explícito), y la
                        // fila existente tiene un WallThickness distinto, actualizarla
                        // — sin esto, un tamaño inyectado previamente con wall grueso
                        // haría que el conducto sobresalga del duct bank en 3D.
                        if (wallOverride.HasValue && colWThExisting != null)
                        {
                            string rowId = (string)row.Attribute("id");
                            XElement wthRow = colWThExisting.Elements("Row")
                                .FirstOrDefault(r => (string)r.Attribute("id") == rowId);
                            if (wthRow != null && double.TryParse(wthRow.Value,
                                    NumberStyles.Float, CultureInfo.InvariantCulture,
                                    out double curW) &&
                                Math.Abs(curW - wallOverride.Value) > 0.001)
                            {
                                string bakPath2 = xmlPath + ".bak";
                                if (!File.Exists(bakPath2)) File.Copy(xmlPath, bakPath2);
                                wthRow.Value = wallOverride.Value.ToString(
                                    "F4", CultureInfo.InvariantCulture);
                                doc.Save(xmlPath);
                                ed.WriteMessage($"\n  ★ Grosor de pared de {diamPulgadas:F0}\" " +
                                    $"actualizado a {wallOverride.Value:F3}\" en '{fam.Description}' " +
                                    "(catálogo XML). Cierra y reabre Civil 3D para que surta efecto.");
                            }
                        }
                        // Ya existe en el XML pero no se pudo agregar vía SizeFilter
                        // (caché de C3D). Intentar de nuevo por si acaso.
                        return AgregarTamañoPipe(tr, fam, diamPulgadas, ed);
                    }
                }

                // Determinar el siguiente id de fila
                XElement colUUID = root.Elements("ColumnUnique").FirstOrDefault();
                if (colUUID == null)
                {
                    Dl(ed, $"\n    [INJ-NO-COLUUID] fam='{fam.Description}' d={diamPulgadas:F1} — XML sin ColumnUnique");
                    return false;
                }
                int maxRow = -1;
                foreach (XElement ru in colUUID.Elements("RowUnique"))
                {
                    string rid = (string)ru.Attribute("id") ?? "";
                    if (rid.StartsWith("r") && int.TryParse(rid.Substring(1), out int n) && n > maxRow)
                        maxRow = n;
                }
                int newIdx = maxRow + 1;
                string newId = $"r{newIdx}";

                // Interpolar grosor de pared desde los diámetros existentes
                XElement colWTh = root.Elements("Column")
                    .FirstOrDefault(c => (string)c.Attribute("context") == "WallThickness");
                double wallThickness = wallOverride ?? 0.35;
                if (colWTh != null && wallOverride == null)
                {
                    var pairs = new List<(double diam, double wth)>();
                    var pidRows = colPID.Elements("Row").ToList();
                    var wthRows = colWTh.Elements("Row").ToList();
                    for (int i = 0; i < Math.Min(pidRows.Count, wthRows.Count); i++)
                    {
                        if (double.TryParse(pidRows[i].Value, NumberStyles.Float,
                                CultureInfo.InvariantCulture, out double d) &&
                            double.TryParse(wthRows[i].Value, NumberStyles.Float,
                                CultureInfo.InvariantCulture, out double w))
                            pairs.Add((d, w));
                    }
                    if (pairs.Count >= 2)
                    {
                        pairs.Sort((a, b) => a.diam.CompareTo(b.diam));
                        if (diamPulgadas <= pairs[0].diam)
                            wallThickness = pairs[0].wth;
                        else if (diamPulgadas >= pairs[pairs.Count - 1].diam)
                            wallThickness = pairs[pairs.Count - 1].wth;
                        else
                        {
                            for (int i = 0; i < pairs.Count - 1; i++)
                            {
                                if (diamPulgadas >= pairs[i].diam && diamPulgadas <= pairs[i + 1].diam)
                                {
                                    double t2 = (diamPulgadas - pairs[i].diam) /
                                                (pairs[i + 1].diam - pairs[i].diam);
                                    wallThickness = pairs[i].wth + t2 * (pairs[i + 1].wth - pairs[i].wth);
                                    break;
                                }
                            }
                        }
                    }
                    else if (pairs.Count == 1)
                        wallThickness = pairs[0].wth;
                }

                // Backup del XML original
                string bakPath = xmlPath + ".bak";
                if (!File.Exists(bakPath))
                    File.Copy(xmlPath, bakPath);

                // Agregar la nueva fila en ColumnUnique (UUID)
                colUUID.Add(new XElement("RowUnique",
                    new XAttribute("id", newId), Guid.NewGuid().ToString().ToUpper()));

                // Agregar fila en columna PID (diámetro)
                colPID.Add(new XElement("Row",
                    new XAttribute("id", newId),
                    diamPulgadas.ToString("F4", CultureInfo.InvariantCulture)));

                // Agregar fila en columna WTh (grosor)
                if (colWTh != null)
                {
                    colWTh.Add(new XElement("Row",
                        new XAttribute("id", newId),
                        wallThickness.ToString("F4", CultureInfo.InvariantCulture)));
                }

                doc.Save(xmlPath);
                ed.WriteMessage($"\n  ★ Diámetro {diamPulgadas:F0}\" inyectado en catálogo XML " +
                    $"de '{fam.Description}' (grosor {wallThickness:F3}\").");

                // Intentar que C3D lo recoja inmediatamente
                if (AgregarTamañoPipe(tr, fam, diamPulgadas, ed))
                    return true;

                // Si no lo recogió, el caché de C3D está desactualizado.
                // El XML ya quedó modificado — funcionará al reabrir C3D.
                ed.WriteMessage($"\n  ⚠ El diámetro {diamPulgadas:F0}\" fue escrito en el catálogo " +
                    "pero Civil 3D no lo recogió (caché). Cierra y reabre Civil 3D, " +
                    "luego importa de nuevo y lo tomará.");
                return false;
            }
            catch (UnauthorizedAccessException)
            {
                ed.WriteMessage($"\n  ⚠ Sin permisos para escribir en el catálogo de Autodesk. " +
                    "Ejecuta Civil 3D como Administrador e intenta de nuevo.");
                return false;
            }
            catch (Exception ex)
            {
                ed.WriteMessage($"\n  (Error inyectando en catálogo: {ex.Message})");
                return false;
            }
        }

        /// <summary>
        /// Busca el .xml de una familia por su GUID en los catálogos de Autodesk
        /// (ProgramData\Autodesk\C3D *\*\Pipes Catalog\).
        /// </summary>
        private static string BuscarXmlFamilia(string guid)
        {
            string progData = Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData);
            string autoDir = Path.Combine(progData, "Autodesk");
            if (!Directory.Exists(autoDir)) return null;
            foreach (string c3d in Directory.GetDirectories(autoDir, "C3D *"))
            {
                foreach (string lang in Directory.GetDirectories(c3d))
                {
                    string pipes = Path.Combine(lang, "Pipes Catalog");
                    if (!Directory.Exists(pipes)) continue;
                    foreach (string xmlFile in Directory.GetFiles(pipes, "*.xml",
                                 SearchOption.AllDirectories))
                    {
                        try
                        {
                            // Lectura rápida: buscar el GUID sin parsear todo el XML
                            string content = File.ReadAllText(xmlFile);
                            if (content.IndexOf(guid, StringComparison.OrdinalIgnoreCase) >= 0)
                            {
                                // Confirmar que es el Catalog_PartID
                                XDocument xd = XDocument.Load(xmlFile);
                                var partId = xd.Root?.Elements("ColumnConst")
                                    .FirstOrDefault(c => (string)c.Attribute("context") == "Catalog_PartID");
                                if (partId != null &&
                                    string.Equals(partId.Value.Trim(), guid,
                                        StringComparison.OrdinalIgnoreCase))
                                    return xmlFile;
                            }
                        }
                        catch { }
                    }
                }
            }
            return null;
        }

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

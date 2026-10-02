using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.Civil;
using Autodesk.Civil.DatabaseServices.Styles;
using CivilDB = Autodesk.Civil.DatabaseServices;
using Exception = System.Exception;

// ============================================================================
//  ETIQUETAS DEL PERFIL — contenido y creación (DISENO.md H.3–H.5, G.5-3, G.7, G.9-4)
//   · Arma los Callout (nodos, cruces, EX. GRADE) y RotuloTramo con los textos
//     en inglés de PerfilTextos (saneados, H.8).
//   · Crea las StationElevationLabel nativas con el marcador invisible (reintento
//     con Null), escribe el texto con SetTextComponentOverride sobre el componente
//     "PDFCAD_TEXTO" y oculta el leader hasta la colocación (T4).
//   · Recrea con estilos nuevos (T2b) y aplica recortes/variantes/borrados (T3).
//   · Nunca se usa el setter obsoleto de Label.DraggedOffset.
//   · Callout.Lineas se guardan YA saneadas; RotuloTramo.L1..L3 en crudo (se
//     sanean al escribir).
// ============================================================================

namespace Civil3DBasico
{
    internal static class PerfilEtiquetas
    {
        private static Callout Nuevo(string id, string tipo, FranjaTipo f, int prio, bool mover, bool alternar, bool recortar,
                                     double est, double estAncla, double zAncla, IEnumerable<string> lineas)
        {
            return new Callout
            {
                Id = id, Tipo = tipo, Franja = f, Prioridad = prio, PuedeCambiarFranja = mover, PuedeAlternar = alternar, PuedeRecortar = recortar,
                Estacion = est, EstAncla = estAncla, ZAncla = zAncla, Lineas = lineas.Select(PerfilTextos.Sanear).ToList(),
            };
        }

        /// <summary>
        /// H.3 (T0): callouts de los nodos del recorrido (inicio/fin, tee, wye, cruz, codo, reducción, deflexión, quiebre, estructura),
        /// con franja/prioridad/flags de la tabla H.3, ancla (corona/fondo/rim; presión: extremo de tubo más cercano) y Lineas saneadas.
        /// </summary>
        internal static List<Callout> ArmarCallouts(Transaction tr, ContextoPerfil ctx)
        {
            var r = new List<Callout>();
            var rec = ctx.Rec; var red = ctx.Red;
            bool grav = red.Tipo == TipoRed.Gravedad, pres = red.Tipo == TipoRed.Presion;
            for (int i = 0; i < rec.Nodos.Count; i++)
            {
                try
                {
                    int nd = rec.Nodos[i]; var n = red.Nodos[nd];
                    double est = rec.EstNodo[nd];
                    var pin = i > 0 ? rec.Pasos[i - 1] : null;
                    var pout = i < rec.Pasos.Count ? rec.Pasos[i] : null;
                    var tref = (pin ?? pout).Tramo;
                    rec.Ramales.TryGetValue(nd, out var ramales); ramales = ramales ?? new List<Ramal>();
                    bool extremo = i == 0 || i == rec.Nodos.Count - 1;
                    // ancla de presión: extremo de tubo más cercano si el centro cae en el hueco
                    double estA = est;
                    if (pres && n.Tipo == TipoNodo.Accesorio)
                    {
                        var cand = new List<double>();
                        if (pin != null) cand.Add(pin.EstPFin);
                        if (pout != null) cand.Add(pout.EstPIni);
                        if (cand.Count > 0) estA = cand.OrderBy(e => Math.Abs(e - est)).First();
                    }
                    double top = PerfilEje.Corona(rec, estA), fondo = PerfilEje.Fondo(rec, estA);
                    string id = "N" + i;
                    double dm = double.IsNaN(n.DiamPrincipalIn) || n.DiamPrincipalIn <= 0 ? tref.DiamIn : n.DiamPrincipalIn;
                    double dr = !double.IsNaN(n.DiamRamalIn) && n.DiamRamalIn > 0 ? n.DiamRamalIn : (ramales.Count > 0 ? ramales[0].DiamIn : dm);
                    string lado = ramales.Count > 0 ? ramales[0].Lado : "";
                    double ang = !double.IsNaN(n.AnguloXData) ? n.AnguloXData : double.NaN;
                    // deflexiones del nodo interior (C.6)
                    double dh = 0, dv = 0;
                    if (pin != null && pout != null)
                    {
                        var ein = red.GAristas[pin.Tramo.Id]; var eout = red.GAristas[pout.Tramo.Id];
                        V2 llegada = (ein.A == nd ? ein.DirSalidaA : ein.DirSalidaB) * -1.0, salida = eout.A == nd ? eout.DirSalidaA : eout.DirSalidaB;
                        double d = PerfilRecorrido.Deflexion(llegada, salida); dh = double.IsNaN(d) ? 0 : d;
                        dv = PerfilRecorrido.DeflexionVertical(PerfilRecorrido.Pendiente(pin.ZIni, pin.ZFin, pin.Tramo.Longitud2D),
                                                               PerfilRecorrido.Pendiente(pout.ZIni, pout.ZFin, pout.Tramo.Longitud2D));
                    }
                    bool vertical = dv > dh;
                    if (double.IsNaN(ang)) ang = Math.Max(dh, dv);
                    Callout c = null;
                    if (grav && n.Tipo == TipoNodo.Estructura)
                    {
                        var ent = new List<EntradaInvert>();
                        if (pout != null) ent.Add(new EntradaInvert { Inv = PerfilGrafoCivil.InvertExtremo(tr, pout.Tramo, pout.Tramo.NodoA == nd), DiamIn = pout.Tramo.DiamIn });
                        double invOut = pin != null ? PerfilGrafoCivil.InvertExtremo(tr, pin.Tramo, pin.Tramo.NodoA == nd) : double.NaN;
                        foreach (var rm in ramales)
                        {
                            double inv = PerfilGrafoCivil.InvertExtremo(tr, rm.Tramo, rm.Tramo.NodoA == nd);
                            if (rm.EntraAlNodo || !double.IsNaN(invOut)) ent.Add(new EntradaInvert { Inv = inv, DiamIn = rm.DiamIn, Lado = rm.Lado, Ramal = true });
                            else invOut = inv;
                        }
                        double rim = double.IsNaN(n.Rim) ? top : n.Rim;
                        c = Nuevo(id, "ESTRUCTURA", FranjaTipo.Superior, 80, false, true, false, est, est, rim,
                                  PerfilTextos.LineasEstructura(est, n.Nombre, n.Rim, ent, invOut));
                    }
                    else if (n.Tipo == TipoNodo.Accesorio && n.Accesorio != TipoAccesorio.Ninguno)
                    {
                        switch (n.Accesorio)
                        {
                            case TipoAccesorio.Tee:
                                var lt = ramales.Count > 0 ? PerfilTextos.LineasTee(est, dm, dr, lado, top)
                                       : (n.RamalVertical && n.DiamRamalIn > 0 ? PerfilTextos.LineasTeeVertical(est, dm, dr, n.SentidoVertical, top)
                                                                               : PerfilTextos.LineasTeeTerminal(est, dm, dr, top));
                                c = Nuevo(id, "TEE", FranjaTipo.Superior, 90, false, true, true, est, estA, top, lt); break;
                            case TipoAccesorio.Wye:
                                c = Nuevo(id, "WYE", FranjaTipo.Superior, 90, false, true, true, est, estA, top,
                                          PerfilTextos.LineasWye(est, dm, dr, lado, ramales.Count > 0 ? ramales[0].AnguloDeg : ang, top)); break;
                            case TipoAccesorio.Cruz:
                                c = Nuevo(id, "CRUZ", FranjaTipo.Superior, 90, false, true, true, est, estA, top, PerfilTextos.LineasCruz(est, dm, dr, top)); break;
                            default:                                                  // codo (interior o en el extremo: vertical)
                                c = Nuevo(id, "CODO", FranjaTipo.Inferior, 70, true, true, true, est, estA, fondo,
                                          PerfilTextos.LineasCodo(est, tref.DiamIn, ang, extremo && ramales.Count == 0 ? true : vertical, tref.MaterialOriginal, top)); break;
                        }
                    }
                    else if (extremo)
                    {
                        double cota = grav ? PerfilGrafoCivil.InvertExtremo(tr, tref, tref.NodoA == nd) : top;
                        c = Nuevo(id, i == 0 ? "INICIO" : "FIN", FranjaTipo.Superior, 100, false, false, !grav, est, est, top,
                                  PerfilTextos.LineasExtremo(est, tref.DiamIn, tref.MaterialOriginal, grav, cota));
                    }
                    else if (pin != null && pout != null)
                    {
                        bool cambiaD = Math.Abs(Math.Round(pin.Tramo.DiamIn) - Math.Round(pout.Tramo.DiamIn)) >= 1;
                        double umbral = pres ? PerfilRecorrido.UMBRAL_PRESION_DEG : PerfilRecorrido.UMBRAL_CONDUIT_DEG;
                        if (cambiaD)
                            c = Nuevo(id, "REDUCCION", FranjaTipo.Inferior, 65, true, true, true, est, est, fondo,
                                      PerfilTextos.LineasReduccion(est, pin.Tramo.DiamIn, pout.Tramo.DiamIn, top));
                        else if (Math.Max(dh, dv) >= umbral || n.RamalVertical)
                            c = pres ? Nuevo(id, "DEFLEXION", FranjaTipo.Inferior, 60, true, true, true, est, est, fondo, PerfilTextos.LineasDeflexion(est, Math.Max(dh, dv), top))
                                     : Nuevo(id, "DEFLEXION", FranjaTipo.Inferior, 60, true, true, true, est, est, fondo, PerfilTextos.LineasQuiebreConduit(est, Math.Max(dh, dv), vertical, top));
                    }
                    if (c != null) r.Add(c);
                }
                catch (Exception ex) { PerfilLog.Error("ROTULO", "callout del nodo " + i, ex); }
            }
            return r;
        }

        /// <summary>
        /// H.4 (T0): rótulos de tramo por rachas (mismo diámetro redondeado, material, abandonado y, en gravedad, pendiente).
        /// Marca Omitido (F.7-1) y añade su línea INSTALL al callout del nodo inicial en <paramref name="callouts"/> (o avisa).
        /// </summary>
        internal static List<RotuloTramo> ArmarRotulos(ContextoPerfil ctx, List<Callout> callouts)
        {
            var r = new List<RotuloTramo>();
            var ps = ctx.Rec.Pasos;
            bool grav = ctx.Red.Tipo == TipoRed.Gravedad;
            var clase = (ClaseRed)(int)ctx.Red.Tipo;
            double S(PasoRecorrido p) { return PerfilRecorrido.Pendiente(p.ZIni, p.ZFin, p.Tramo.Longitud2D); }
            int i = 0;
            while (i < ps.Count)
            {
                int j = i;
                while (j + 1 < ps.Count && Math.Round(ps[j + 1].Tramo.DiamIn) == Math.Round(ps[i].Tramo.DiamIn)
                       && ps[j + 1].Tramo.Material == ps[i].Tramo.Material && ps[j + 1].Tramo.Abandonado == ps[i].Tramo.Abandonado
                       && (!grav || Math.Abs(S(ps[j + 1]) - S(ps[i])) < 0.0001)) j++;
                var t = ps[i].Tramo;
                double a = ps[i].EstDesde, b = ps[j].EstHasta;
                PerfilTextos.LineasTramo(clase, t.Abandonado, b - a, t.DiamIn, t.MaterialOriginal, S(ps[i]), out string l1, out string l2, out string l3);
                var rt = new RotuloTramo { Id = "T" + r.Count, EstIni = a, EstFin = b, L1 = l1, L2 = l2, L3 = l3 };
                if (PerfilDiseno.EsTramoOmitido(b - a, ctx.S))
                {
                    rt.Omitido = true;
                    var co = callouts.FirstOrDefault(c => c.Id == "N" + i);
                    string linea = PerfilTextos.Sanear(PerfilTextos.LineaTramoOmitido(b - a, t.DiamIn, t.MaterialOriginal));
                    if (co != null)
                    {
                        int pos = co.Lineas.FindLastIndex(l => l.StartsWith("TOP ELEV", StringComparison.Ordinal));
                        if (pos < 0) co.Lineas.Add(linea); else co.Lineas.Insert(pos, linea);
                    }
                    else PerfilLog.Aviso("ROTULO", "Tramo corto sin rótulo en " + PerfilTextos.FormatoEstacion(a, 2));
                }
                r.Add(rt);
                i = j + 1;
            }
            return r;
        }

        /// <summary>H.5 (T0): un Callout "CRUCE" por grupo (representante), con CruceIdx, franja según Encima y línea CLR si la cota no cabe.</summary>
        internal static List<Callout> ArmarCalloutsCruce(ContextoPerfil ctx)
        {
            var r = new List<Callout>();
            double v = ctx.V > 0 ? ctx.V : PerfilDiseno.ElegirV(ctx.S);
            foreach (var g in ctx.Cruces.Select((c, i) => (c, i)).Where(x => x.c.Grupo >= 0).GroupBy(x => x.c.Grupo))
            {
                var miembros = g.OrderBy(x => x.c.Estacion).ToList();
                var rep = miembros[0];
                var c = rep.c;
                List<string> lin;
                if (miembros.Count == 1)
                    lin = PerfilTextos.LineasCruceUno(c.DiamIn, c.Material, c.Abandonado, c.Red, c.EsGravedad, c.EsGravedad ? c.ZEje - c.RadioIntFt : c.ZEje + c.AltoExtFt / 2.0);
                else
                {
                    var tops = miembros.Select(x => x.c.ZEje + x.c.AltoExtFt / 2.0).ToList();
                    lin = PerfilTextos.LineasCruceGrupo(miembros.Count, miembros.Select(x => x.c.DiamIn).ToList(), c.Material,
                                                        !c.EsGravedad && !c.EsPresion, c.Red, tops.Min(), tops.Max());
                }
                if (Math.Abs(c.ClaroFt) <= 10 && !PerfilDiseno.CotaSeparacionCabe(Math.Abs(c.ClaroFt), v)) lin.Add(PerfilTextos.LineaClaro(c.ClaroFt));
                var co = Nuevo("C" + g.Key, "CRUCE", c.Encima ? FranjaTipo.Superior : FranjaTipo.Inferior, 55, false, true, true,
                               c.Estacion, c.Estacion, c.ZEje, lin);
                co.CruceIdx = rep.i;
                r.Add(co);
            }
            return r;
        }

        /// <summary>H.5 (T0): Callout "TERRENO" (EX. GRADE) en la estación k/6 más despejada con terreno válido; null si no hay terreno.</summary>
        internal static Callout ArmarRasante(ContextoPerfil ctx, IReadOnlyList<Callout> otros)
        {
            var rec = ctx.Rec;
            var anclas = (otros ?? new List<Callout>()).Where(c => c.Franja == FranjaTipo.Superior || c.Tipo == "CRUCE").Select(c => c.EstAncla).ToList();
            double mejor = double.NegativeInfinity, estBest = double.NaN;
            for (int k = 1; k <= 5; k++)
            {
                double e = rec.EstIni + k * (rec.EstFin - rec.EstIni) / 6.0;
                if (double.IsNaN(PerfilEje.TerrenoEn(rec, e))) continue;
                double d = anclas.Count == 0 ? double.MaxValue : anclas.Min(a => Math.Abs(a - e));
                if (d > mejor) { mejor = d; estBest = e; }
            }
            if (double.IsNaN(estBest)) return null;
            return Nuevo("TERRENO", "TERRENO", FranjaTipo.Superior, 50, false, true, false, estBest, estBest, PerfilEje.TerrenoEn(rec, estBest),
                         new[] { PerfilTextos.TEXTO_RASANTE });
        }

        /// <summary>Convierte un Callout en su BloqueTexto (mismos flags, líneas y ancla); lo guarda en c.Bloque y lo devuelve.</summary>
        internal static BloqueTexto ABloque(Callout c)
        {
            var b = new BloqueTexto
            {
                Id = c.Id, Franja = c.Franja, Prioridad = c.Prioridad, PuedeCambiarFranja = c.PuedeCambiarFranja,
                PuedeAlternar = c.PuedeAlternar, PuedeRecortar = c.PuedeRecortar, EstAncla = c.EstAncla, ZAncla = c.ZAncla,
                Lineas = c.Lineas.ToArray(), Vertical = true,
            };
            PerfilDiseno.PredecirBloque(b);
            c.Bloque = b;
            return b;
        }

        /// <summary>Convierte un RotuloTramo en su FilaTramo; lo guarda en r.Fila y lo devuelve.</summary>
        internal static FilaTramo AFila(RotuloTramo r)
        {
            var f = new FilaTramo { Id = r.Id, EstIni = r.EstIni, EstFin = r.EstFin, L1 = r.L1, L2 = r.L2, L3 = r.L3 };
            r.Fila = f;
            return f;
        }

        private static ObjectId EstiloCallout(EstilosPerfil e, Callout c)
        {
            if (c.Tipo == "TERRENO") return e.Rasante;
            return c.Franja == FranjaTipo.Inferior && c.Tipo != "TRAMO" ? e.CalloutInf : e.CalloutSup;
        }

        private static IEnumerable<string> LineasTramoSaneadas(FilaTramo f, int n) { return PerfilDiseno.LineasVariante(f, n).Select(PerfilTextos.Sanear); }

        /// <summary>
        /// G.5-3 (T1b): crea las etiquetas de los callouts (salvo "CRUCE", que las crea PerfilCruces), la rasante y los tramos
        /// (ancla en (estMedia, corona), variante v2) de la hoja; guarda EtiquetaId. Devuelve cuántas creó.
        /// </summary>
        internal static int CrearEtiquetas(Transaction tr, ContextoPerfil ctx, HojaPerfil hoja)
        {
            if (hoja.PvId.IsNull) return 0;
            int n = 0;
            foreach (var c in hoja.Callouts.Where(c => c.Tipo != "CRUCE"))
            {
                c.EtiquetaId = CrearStationElevation(tr, hoja.PvId, EstiloCallout(ctx.Estilos, c), ctx.Estilos.SinMarcador, c.EstAncla, c.ZAncla, c.Lineas);
                if (!c.EtiquetaId.IsNull) n++;
            }
            foreach (var r in hoja.Rotulos.Where(r => !r.Omitido))
            {
                double em = (r.EstIni + r.EstFin) / 2.0;
                var f = r.Fila ?? AFila(r);
                r.EtiquetaId = CrearStationElevation(tr, hoja.PvId, ctx.Estilos.Tramo, ctx.Estilos.SinMarcador, em, PerfilEje.Corona(ctx.Rec, em), LineasTramoSaneadas(f, 2));
                if (!r.EtiquetaId.IsNull) n++;
            }
            return n;
        }

        /// <summary>
        /// Crea una StationElevationLabel en (est, z) con el marcador dado (reintento con Null; si falla, Null con aviso),
        /// escribe <paramref name="lineas"/> y deja LeaderVisibility = AlwaysHide. Devuelve el id o Null.
        /// </summary>
        internal static ObjectId CrearStationElevation(Transaction tr, ObjectId pvId, ObjectId estilo, ObjectId marcador, double est, double z, IEnumerable<string> lineas)
        {
            if (estilo.IsNull || double.IsNaN(est) || double.IsNaN(z)) { PerfilLog.Aviso("ROTULO", "Rótulo omitido (sin estilo o sin cota)"); return ObjectId.Null; }
            ObjectId id = ObjectId.Null;
            try { id = CivilDB.StationElevationLabel.Create(pvId, estilo, marcador, est, z); }
            catch
            {
                try { id = CivilDB.StationElevationLabel.Create(pvId, estilo, ObjectId.Null, est, z); }
                catch (Exception ex) { PerfilLog.Error("ROTULO", $"StationElevationLabel en {est:0.##}", ex); PerfilLog.Aviso("Rótulo omitido en " + PerfilTextos.FormatoEstacion(est, 2)); return ObjectId.Null; }
            }
            try
            {
                var lbl = (CivilDB.Label)tr.GetObject(id, OpenMode.ForWrite);
                EscribirTexto(tr, lbl, lineas);
                Leaders(lbl, false, false);
            }
            catch (Exception ex) { PerfilLog.Error("ROTULO", "texto", ex); }
            return id;
        }

        /// <summary>
        /// G.5-3 / I-17: override del componente "PDFCAD_TEXTO" (o el primero, con aviso) con las líneas (ya saneadas) unidas
        /// por "\P" (nunca ""). La etiqueta debe estar abierta ForWrite. false si no hay componentes de texto.
        /// </summary>
        internal static bool EscribirTexto(Transaction tr, CivilDB.Label lbl, IEnumerable<string> lineas)
        {
            var ids = lbl.GetTextComponentIds();
            if (ids == null || ids.Count == 0) { PerfilLog.Aviso("ROTULO", "Etiqueta sin componente de texto"); return false; }
            ObjectId comp = ObjectId.Null;
            foreach (ObjectId cid in ids)
                try { if (((LabelStyleTextComponent)tr.GetObject(cid, OpenMode.ForRead)).Name == PerfilEstilosEtiquetas.COMPONENTE) { comp = cid; break; } } catch { }
            if (comp.IsNull) { comp = ids[0]; PerfilLog.Log("ROTULO", "sin componente PDFCAD_TEXTO: se usa el primero"); }
            string texto = string.Join("\\P", (lineas ?? new string[0]).Where(l => l != null));
            if (string.IsNullOrWhiteSpace(texto)) texto = " ";
            lbl.SetTextComponentOverride(comp, texto);
            return true;
        }

        /// <summary>Fija LeaderVisibility / LeaderTailVisibility (true = FromLabelStyle, false = AlwaysHide). Etiqueta ForWrite; en try.</summary>
        internal static void Leaders(CivilDB.Label lbl, bool leader, bool cola)
        {
            try { lbl.LeaderVisibility = leader ? LeaderVisibilityType.FromLabelStyle : LeaderVisibilityType.AlwaysHide; } catch (Exception ex) { PerfilLog.Log("ROTULO", "LeaderVisibility: " + ex.Message); }
            try { lbl.LeaderTailVisibility = cola ? LeaderTailVisibilityType.FromLabelStyle : LeaderTailVisibilityType.AlwaysHide; } catch (Exception ex) { PerfilLog.Log("ROTULO", "LeaderTailVisibility: " + ex.Message); }
        }

        /// <summary>Borra una etiqueta (ForWrite + Erase) en try; ignora ids nulos o ya borrados.</summary>
        internal static void Borrar(Transaction tr, ObjectId id)
        {
            if (id.IsNull || !id.IsValid || id.IsErased) return;
            try { tr.GetObject(id, OpenMode.ForWrite).Erase(); } catch (Exception ex) { PerfilLog.Log("ROTULO", "Erase: " + ex.Message); }
        }

        /// <summary>G.7 (T2b): borra y recrea todas las etiquetas de G.5-3 (callouts, rasante, tramos y cruces) con los estilos actuales de ctx.Estilos.</summary>
        internal static void RecrearEtiquetas(Transaction tr, ContextoPerfil ctx)
        {
            foreach (var h in ctx.Hojas)
            {
                foreach (var c in h.Callouts) { Borrar(tr, c.EtiquetaId); c.EtiquetaId = ObjectId.Null; }
                foreach (var r in h.Rotulos) { Borrar(tr, r.EtiquetaId); r.EtiquetaId = ObjectId.Null; }
            }
            foreach (var c in ctx.Cruces) { foreach (var id in c.EtiquetaIds) Borrar(tr, id); c.EtiquetaIds.Clear(); }
            foreach (var h in ctx.Hojas) { CrearEtiquetas(tr, ctx, h); PerfilCruces.CrearEtiquetas(tr, ctx, h); }
        }

        /// <summary>
        /// G.9-4 (T3): recortados → texto sin la última línea; tramos con variante ≠ v2 → texto de su variante; Descartado → Erase;
        /// AVertical → Erase del tramo y nuevo callout "TRAMO" con Callout Sup.
        /// </summary>
        internal static void AplicarCambiosTexto(Transaction tr, ContextoPerfil ctx, HojaPerfil hoja)
        {
            var bloques = hoja.EntradaFinal != null ? hoja.EntradaFinal.Bloques : new List<BloqueTexto>();
            foreach (var c in hoja.Callouts.ToList())
            {
                var b = bloques.FirstOrDefault(x => x.Id == c.Id) ?? c.Bloque;
                if (b == null || c.EtiquetaId.IsNull) continue;
                c.Bloque = b;
                try
                {
                    if (b.Descartado) { Borrar(tr, c.EtiquetaId); c.EtiquetaId = ObjectId.Null; continue; }
                    if (b.Recortado)
                    {
                        c.Lineas = b.Lineas.ToList();
                        EscribirTexto(tr, (CivilDB.Label)tr.GetObject(c.EtiquetaId, OpenMode.ForWrite), c.Lineas);
                    }
                }
                catch (Exception ex) { PerfilLog.Error("ROTULO", "cambio de " + c.Id, ex); }
            }
            foreach (var r in hoja.Rotulos.Where(r => !r.Omitido && r.Fila != null && !r.EtiquetaId.IsNull))
            {
                try
                {
                    if (r.Fila.AVertical)
                    {
                        Borrar(tr, r.EtiquetaId); r.EtiquetaId = ObjectId.Null;
                        var b = bloques.FirstOrDefault(x => x.Id == r.Id && !hoja.Callouts.Any(c => c.Id == x.Id));
                        if (b == null) continue;
                        var c = new Callout
                        {
                            Id = b.Id, Tipo = "TRAMO", Franja = FranjaTipo.Superior, Prioridad = b.Prioridad, Estacion = b.EstAncla,
                            EstAncla = b.EstAncla, ZAncla = b.ZAncla, Lineas = b.Lineas.Select(PerfilTextos.Sanear).ToList(), Hoja = hoja.Indice, Bloque = b,
                        };
                        c.EtiquetaId = CrearStationElevation(tr, hoja.PvId, ctx.Estilos.CalloutSup, ctx.Estilos.SinMarcador, c.EstAncla, c.ZAncla, c.Lineas);
                        hoja.Callouts.Add(c);
                    }
                    else if (r.Fila.NumLineas != 2)
                        EscribirTexto(tr, (CivilDB.Label)tr.GetObject(r.EtiquetaId, OpenMode.ForWrite), LineasTramoSaneadas(r.Fila, r.Fila.NumLineas));
                }
                catch (Exception ex) { PerfilLog.Error("ROTULO", "cambio de tramo " + r.Id, ex); }
            }
        }
    }
}

using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;
using Autodesk.Civil.ApplicationServices;
using Autodesk.Civil.Settings;
using CivilDB = Autodesk.Civil.DatabaseServices;
using Exception = System.Exception;

// ============================================================================
//  CREAR_PERFIL_RED — perfil longitudinal 100 % nativo de Civil 3D (DISENO.md G)
//   · Orquesta: G.0 preparación → prompt 1 → T0 (lectura) → prompt 2 →
//     T1a (creación) → T1b (overrides y etiquetas) → T2 (medición) → [T2b] →
//     Maquetar final → T3 (rango) → T4 (colocación) → T5 (corrección) →
//     T6 (verificación) → resumen G.13.
//   · No dibuja nada por sí mismo: todo lo hacen los módulos Perfil*.cs.
//   · CREAR_PERFIL_PRESION es un alias (sustituye al comando antiguo de
//     RedesPresionRamales.cs).
//   · Prompts fuera de las transacciones; flush de gráficos tras cada commit
//     que crea/mueve etiquetas o vistas; un fallo en T2…T6 conserva T1 (G.15).
// ============================================================================

namespace Civil3DBasico
{
    public class ComandosPerfil
    {
        /// <summary>Comando principal: perfil de la red de la tubería/estructura elegida (gravedad, conduit o presión). G.</summary>
        [CommandMethod("CREAR_PERFIL_RED")]
        public void CrearPerfilRed()
        {
            ContextoPerfil ctx = null;
            try { ctx = Preparar(); } catch (Exception ex) { PerfilLog.Error("CMD", "preparación", ex); }
            if (ctx == null) return;
            var ed = ctx.Ed;
            if (!PedirEntidad(ctx)) return;
            bool okT0;
            try { okT0 = T0(ctx); }
            catch (Exception ex) { PerfilLog.Error("CMD", "T0", ex); ed.WriteMessage("\n✗ No se pudo leer la red: " + ex.Message); return; }
            if (!okT0) return;
            if (!PedirInsercion(ctx)) return;
            bool okT1;
            try { okT1 = T1a(ctx); }
            catch (Exception ex) { PerfilLog.Error("CMD", "T1a", ex); ed.WriteMessage("\n✗ No se pudo crear el perfil: " + ex.Message); return; }
            if (!okT1) return;
            Fase("T1b", () => T1b(ctx));
            Fase("T2", () => T2(ctx));
            Fase("T3", () => T3(ctx));
            Fase("T4", () => T4(ctx));
            Fase("T5", () => T5(ctx));
            Fase("T6", () => T6(ctx));
            Resumen(ctx);
        }

        /// <summary>Alias de CREAR_PERFIL_RED (redes a presión). G.</summary>
        [CommandMethod("CREAR_PERFIL_PRESION")]
        public void CrearPerfilPresion() { CrearPerfilRed(); }

        private static CapturaPartes _captura;

        private static void Fase(string nombre, Action a)
        {
            try { a(); }
            catch (Exception ex)
            {
                PerfilLog.Error("CMD", nombre, ex);
                PerfilLog.Aviso("Fase " + nombre + " incompleta: " + ex.Message);
            }
        }

        // ------------------------------------------------------------ fases (C4)

        /// <summary>G.0: doc/ed/db/civDoc, PerfilLog.Iniciar, S (DrawingScale válido 0 &lt; S ≤ 1000; si no 20 con aviso) y unidades.</summary>
        private static ContextoPerfil Preparar()
        {
            Document doc = Application.DocumentManager.MdiActiveDocument;
            if (doc == null) return null;
            PerfilLog.Iniciar();
            var ctx = new ContextoPerfil { Doc = doc, Ed = doc.Editor, Db = doc.Database, CivDoc = CivilApplication.ActiveDocument };
            try
            {
                var u = ctx.CivDoc.Settings.DrawingSettings.UnitZoneSettings;
                double s = u.DrawingScale;
                if (s > 0 && s <= 1000) ctx.S = s;
                else
                {
                    string can = ""; try { can = ctx.Db.Cannoscale.Name; } catch { }
                    PerfilLog.Aviso("UNIDADES", $"DrawingScale no válido ({s}); se usa 1\"=20' (Cannoscale {can})");
                    ctx.S = 20;
                }
                ctx.Metros = u.DrawingUnits == DrawingUnitType.Meters;
                if (ctx.Metros) PerfilLog.Aviso("UNIDADES", "El dibujo está en metros: los textos pueden requerir calibración");
            }
            catch (Exception ex) { PerfilLog.Error("UNIDADES", "DrawingScale", ex); ctx.S = 20; }
            PerfilLog.Log("CMD", "S = " + ctx.S);
            return ctx;
        }

        /// <summary>G.1: prompt de entidad (Pipe, Structure, PressurePipe). false si se cancela.</summary>
        private static bool PedirEntidad(ContextoPerfil ctx)
        {
            var peo = new PromptEntityOptions("\nSeleccione una tubería o estructura de la red para el perfil:");
            peo.SetRejectMessage("\nDebe ser una tubería (gravedad/presión) o una estructura.");
            peo.AddAllowedClass(typeof(CivilDB.Pipe), true);
            peo.AddAllowedClass(typeof(CivilDB.Structure), true);
            peo.AddAllowedClass(typeof(CivilDB.PressurePipe), true);
            var r = ctx.Ed.GetEntity(peo);
            if (r.Status != PromptStatus.OK) return false;
            ctx.EntidadId = r.ObjectId;
            return true;
        }

        /// <summary>G.2 (T0, lectura): red, grafo, recorrido, traza, terreno, cruces, callouts, tramos, hojas, maquetación preliminar y nombre.</summary>
        private static bool T0(ContextoPerfil ctx)
        {
            var ed = ctx.Ed;
            using (Transaction tr = ctx.Db.TransactionManager.StartTransaction())
            {
                var red = PerfilGrafoCivil.IdentificarRed(tr, ctx.CivDoc, ctx.EntidadId, out string msg);
                if (red == null) { ed.WriteMessage("\n" + msg); tr.Commit(); return false; }
                ctx.Red = red;
                bool ok = red.Tipo == TipoRed.Presion ? PerfilGrafoCivil.ConstruirPresion(tr, ctx.Db, red) : PerfilGrafoCivil.ConstruirGravedad(tr, red);
                if (!ok) { ed.WriteMessage("\n✗ La red no tiene tuberías válidas para el perfil."); tr.Commit(); return false; }
                var rec = PerfilGrafoCivil.ArmarRecorrido(red, ctx.EntidadId, ctx.S, out msg);
                if (rec == null) { ed.WriteMessage("\n" + (string.IsNullOrEmpty(msg) ? "✗ No se pudo formar un recorrido desde esa entidad." : msg)); tr.Commit(); return false; }
                ctx.Rec = rec;
                ctx.SinSuperficie = !PerfilEje.MuestrearTerreno(tr, rec, red.SuperficieId);
                if (ctx.SinSuperficie) PerfilLog.Aviso("Sin superficie: no se dibuja terreno ni recubrimientos");
                ctx.Cruces = PerfilCruces.BuscarCandidatos(tr, ctx.CivDoc, rec, out var verts);
                ctx.VerticalesTodas = new List<VerticalConexion>(verts);
                ctx.VerticalesTodas.AddRange(red.Verticales);
                if (red.Tipo == TipoRed.Presion) PerfilGrafoCivil.MarcarRamalesVerticales(red, ctx.VerticalesTodas);
                int grupos = PerfilCruces.Agrupar(ctx.Cruces, ctx.S);
                ctx.FactorPlInicial = PerfilEstilos.FactorPlInicial(tr, ctx.CivDoc, ctx.Metros, out string origen);
                ctx.FactorPl = ctx.FactorPlInicial; ctx.OrigenFactorPl = origen;
                var callouts = PerfilEtiquetas.ArmarCallouts(tr, ctx);
                ctx.Rotulos = PerfilEtiquetas.ArmarRotulos(ctx, callouts);
                callouts.AddRange(PerfilEtiquetas.ArmarCalloutsCruce(ctx));
                var ras = PerfilEtiquetas.ArmarRasante(ctx, callouts);
                if (ras != null) callouts.Add(ras);
                ctx.Callouts = callouts;
                PerfilMaquetacion.PartirHojas(ctx);
                PerfilMaquetacion.MaquetarPreliminar(ctx);
                ctx.Nombre = PerfilEje.NombreUnico(tr, ctx.CivDoc, red.NombreRed, out int n);
                ctx.Numero = n;
                int ramales = rec.Ramales.Values.Sum(l => l.Count);
                tr.Commit();
                ed.WriteMessage($"\n· Recorrido: {rec.Pasos.Count} tubos, {rec.Nodos.Count} nodos, {rec.EstFin - rec.EstIni:0.00} ft, {ramales} ramales, " +
                                $"{ctx.Cruces.Count} cruces ({grupos} grupos), {ctx.Hojas.Count} hoja(s).");
                return true;
            }
        }

        /// <summary>G.3: prompt del punto de inserción. false si se cancela.</summary>
        private static bool PedirInsercion(ContextoPerfil ctx)
        {
            var r = ctx.Ed.GetPoint("\nPunto de inserción de la vista de perfil (esquina inferior izquierda):");
            if (r.Status != PromptStatus.OK) return false;
            ctx.PuntoInsercion = r.Value;
            return true;
        }

        /// <summary>G.4 (T1a): estilos, eje (fatal), estaciones definitivas, terreno, vistas y captura de partes. false = abortado.</summary>
        private static bool T1a(ContextoPerfil ctx)
        {
            _captura = new CapturaPartes();
            try
            {
                using (Transaction tr = ctx.Db.TransactionManager.StartTransaction())
                {
                    ctx.Estilos = PerfilEstilos.Asegurar(tr, ctx.Db, ctx.CivDoc, ctx.S, ctx.V, ctx.Int, ctx.FactorPl, ctx.FactorPlInicial);
                    PerfilEstilosEtiquetas.Diagnostico(tr, ctx.Db, ctx.CivDoc, ctx.FactorPl, ctx.OrigenFactorPl);
                    ctx.AlignId = PerfilEje.Crear(tr, ctx.Db, ctx.CivDoc, ctx.Rec, ctx.Nombre, ctx.Estilos);
                    if (ctx.AlignId.IsNull) { tr.Abort(); ctx.Ed.WriteMessage("\n✗ No se pudo crear el eje del perfil."); return false; }
                    PerfilEje.EstacionesDefinitivas(tr, ctx.AlignId, ctx.Rec, ctx.Cruces);
                    if (!ctx.SinSuperficie) ctx.TerrenoId = PerfilVista.CrearTerreno(tr, ctx);
                    if (!PerfilVista.CrearVistas(tr, ctx)) { tr.Abort(); ctx.Ed.WriteMessage("\n✗ No se pudo crear la vista de perfil."); return false; }
                    _captura.Suscribir(ctx.Db);
                    PerfilVista.AgregarPartes(tr, ctx, _captura);
                    tr.Commit();
                }
            }
            finally { _captura.Desuscribir(); }
            Flush(ctx.Doc);
            return true;
        }

        /// <summary>G.5 (T1b): resolución de partes, overrides por vista y etiquetas.</summary>
        private static void T1b(ContextoPerfil ctx)
        {
            using (Transaction tr = ctx.Db.TransactionManager.StartTransaction())
            {
                PerfilVista.ResolverPartes(tr, ctx, _captura ?? new CapturaPartes());
                PerfilVista.AplicarOverrides(tr, ctx);
                foreach (var h in ctx.Hojas.Where(h => !h.PvId.IsNull))
                {
                    PerfilEtiquetas.CrearEtiquetas(tr, ctx, h);
                    ctx.Resumen.GruposCruce += PerfilCruces.CrearEtiquetas(tr, ctx, h);
                }
                tr.Commit();
            }
            Flush(ctx.Doc);
        }

        /// <summary>G.6 + G.7 (T2/T2b): medición, calibración y, como mucho una vez, recalibración de FactorPl.</summary>
        private static void T2(ContextoPerfil ctx)
        {
            double r, disp;
            using (Transaction tr = ctx.Db.TransactionManager.StartTransaction())
            {
                PerfilMaquetacion.Medir(tr, ctx, out r, out disp);
                tr.Commit();
            }
            if (!PerfilMaquetacion.ProblemaUnidades(r, disp)) return;
            PerfilLog.Log("UNIDADES", $"r={r:G4} S={ctx.S} → FactorPl {ctx.FactorPl:G4} → {ctx.FactorPl / r:G4}");
            ctx.FactorPl /= r;
            using (Transaction tr = ctx.Db.TransactionManager.StartTransaction())
            {
                ctx.Estilos = PerfilEstilos.Asegurar(tr, ctx.Db, ctx.CivDoc, ctx.S, ctx.V, ctx.Int, ctx.FactorPl, ctx.FactorPlInicial);
                PerfilVista.CambiarEstilo(tr, ctx, ctx.Estilos.VistaStyle);
                PerfilEtiquetas.RecrearEtiquetas(tr, ctx);
                tr.Commit();
            }
            Flush(ctx.Doc);
            using (Transaction tr = ctx.Db.TransactionManager.StartTransaction())
            {
                PerfilMaquetacion.Medir(tr, ctx, out r, out disp);
                tr.Commit();
            }
            if (Math.Abs(r - 1.0) > 0.05) PerfilLog.Aviso("UNIDADES", $"Los textos siguen midiendo {r:0.##}× lo previsto; se usan las medidas reales");
        }

        /// <summary>G.8 + G.9 (T3): maquetación final, estilo de vista nuevo si cambió V, rango final, reapilado y cambios de texto.</summary>
        private static void T3(ContextoPerfil ctx)
        {
            bool cambioV = PerfilMaquetacion.MaquetarFinal(ctx);
            using (Transaction tr = ctx.Db.TransactionManager.StartTransaction())
            {
                if (cambioV)
                {
                    ObjectId nueva = PerfilEstilos.AsegurarVistaStyle(tr, ctx.CivDoc, ctx.S, ctx.V, ctx.Int, ctx.Estilos);
                    ctx.Estilos.VistaStyle = nueva;
                    PerfilVista.CambiarEstilo(tr, ctx, nueva);
                }
                PerfilVista.AplicarRangoFinal(tr, ctx);
                foreach (var h in ctx.Hojas.Where(h => !h.PvId.IsNull)) PerfilEtiquetas.AplicarCambiosTexto(tr, ctx, h);
                tr.Commit();
            }
            Flush(ctx.Doc);
        }

        /// <summary>G.10 (T4): colocación y etiquetas que dependen del rango (título, STATION, extremos, recubrimientos, separaciones, límites).</summary>
        private static void T4(ContextoPerfil ctx)
        {
            using (Transaction tr = ctx.Db.TransactionManager.StartTransaction())
            {
                foreach (var h in ctx.Hojas.Where(h => !h.PvId.IsNull && h.Final != null))
                {
                    PerfilEtiquetasVista.Colocar(tr, ctx, h);
                    PerfilEtiquetasVista.CrearEtiquetasDeVista(tr, ctx, h);
                    PerfilEtiquetasVista.CrearRecubrimientos(tr, ctx, h);
                    PerfilEtiquetasVista.CrearSeparaciones(tr, ctx, h);
                    PerfilEtiquetasVista.CrearLimites(tr, ctx, h);
                    PerfilEtiquetasVista.EnviarAlFondo(tr, h);
                }
                tr.Commit();
            }
            Flush(ctx.Doc);
        }

        /// <summary>G.11 (T5): hasta 3 iteraciones de corrección, cada una en su transacción.</summary>
        private static void T5(ContextoPerfil ctx)
        {
            for (int it = 0; it < PerfilMaquetacion.MAX_ITER_CORRECCION; it++)
            {
                int fuera = 0;
                using (Transaction tr = ctx.Db.TransactionManager.StartTransaction())
                {
                    foreach (var h in ctx.Hojas.Where(h => !h.PvId.IsNull && h.Final != null))
                    {
                        fuera += PerfilMaquetacion.Corregir(tr, ctx, h, it);
                        PerfilEtiquetasVista.ColocarEtiquetasDeVista(tr, ctx, h);
                    }
                    tr.Commit();
                }
                Flush(ctx.Doc);
                PerfilLog.Log("CORRECCION", $"iteración {it + 1}: {fuera} etiqueta(s) movidas");
                if (fuera == 0) break;
            }
        }

        /// <summary>G.12 (T6): verificación final con medidas reales (solo lectura).</summary>
        private static void T6(ContextoPerfil ctx)
        {
            using (Transaction tr = ctx.Db.TransactionManager.StartTransaction())
            {
                int n = PerfilMaquetacion.Verificar(tr, ctx);
                PerfilLog.Log("VERIFICACION", n + " problema(s)");
                tr.Commit();
            }
        }

        /// <summary>G.13: resumen en español en la línea de comandos.</summary>
        private static void Resumen(ContextoPerfil ctx)
        {
            var ed = ctx.Ed; var r = ctx.Resumen;
            r.Cruces = ctx.Cruces.Count;
            ed.WriteMessage($"\n✓ Perfil '{ctx.Nombre}' creado: {r.Hojas} vista(s), {r.Tubos} tubos, {r.Estructuras} estructuras, {r.Cruces} cruces " +
                            $"({r.GruposCruce} rótulos), {r.Callouts} rótulos, {r.Rotulos} tramos, {r.Profundidades} cotas de recubrimiento.");
            if (PerfilLog.Avisos.Count > 0) ed.WriteMessage($"\n⚠ {PerfilLog.Avisos.Count} aviso(s): {PerfilLog.ResumenAvisos(3)}");
            if (ctx.SinSuperficie) ed.WriteMessage("\n⚠ Sin superficie: no se dibuja terreno ni recubrimientos.");
            ed.WriteMessage("\n· Si cambia el rango de la vista, vuelva a ejecutar el comando (los rótulos quedan arrastrados).");
            ed.WriteMessage("\n· Detalle en " + PerfilLog.Ruta);
        }

        /// <summary>Regla transversal G: QueueForGraphicsFlush + FlushGraphics tras un commit, en try.</summary>
        internal static void Flush(Document doc)
        {
            try { doc.TransactionManager.QueueForGraphicsFlush(); doc.TransactionManager.FlushGraphics(); } catch { }
        }
    }
}

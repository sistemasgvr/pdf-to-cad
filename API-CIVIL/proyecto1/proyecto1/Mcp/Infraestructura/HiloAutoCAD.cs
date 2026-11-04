using System;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Threading;
using Autodesk.AutoCAD.ApplicationServices;
using AcadApp = Autodesk.AutoCAD.ApplicationServices.Application;

// ============================================================================
//  Paso al hilo de AutoCAD. La API de AutoCAD/Civil 3D SOLO se usa desde su hilo
//  principal: el servidor de la tubería corre en otro hilo y todo pasa por aquí.
//  - Leer: en contexto de aplicación, con el documento bloqueado.
//  - Escribir: en contexto de COMANDO (ExecuteInCommandContextAsync), así el cambio
//    es un paso de deshacer (U) y no choca con lo que hace el usuario.
//  El hilo de la tubería espera; el de AutoCAD nunca se bloquea esperando.
// ============================================================================

namespace Civil3DBasico.Mcp.Infraestructura
{
    internal static class HiloAutoCAD
    {
        public static readonly TimeSpan ESPERA_MAX = TimeSpan.FromMinutes(2);

        private static Dispatcher _dispatcher;

        /// <summary>Se llama UNA vez desde el hilo principal (al encender el servidor).</summary>
        public static void Capturar() => _dispatcher = Dispatcher.CurrentDispatcher;

        public static Document Documento()
        {
            Document d = AcadApp.DocumentManager.MdiActiveDocument;
            if (d == null) throw new Aplicacion.ErrorUsuario("No hay ningún dibujo abierto en Civil 3D.");
            return d;
        }

        public static string ComandoEnCurso(Document d)
        {
            try { return (d.CommandInProgress ?? "").Trim(); } catch { return ""; }
        }

        /// <summary>Ejecuta `fn` en el hilo de AutoCAD con el documento activo bloqueado.</summary>
        public static T Leer<T>(Func<Document, T> fn, bool permitirOcupado = false)
        {
            if (_dispatcher == null) throw new InvalidOperationException("Servidor MCP sin iniciar.");
            DispatcherOperation<T> op = _dispatcher.InvokeAsync(() =>
            {
                Document d = Documento();
                string cmd = ComandoEnCurso(d);
                if (!permitirOcupado && cmd.Length > 0)
                    throw new Aplicacion.ErrorUsuario($"Civil 3D está ocupado con el comando {cmd}. Terminarlo y volver a intentar.");
                using (d.LockDocument()) return fn(d);
            });
            if (!op.Task.Wait(ESPERA_MAX)) throw new TimeoutException("Civil 3D no respondió a tiempo.");
            return Desenvolver(op.Task);
        }

        /// <summary>Ejecuta `accion` en contexto de comando del documento activo.</summary>
        public static void Escribir(Action<Document> accion)
        {
            if (_dispatcher == null) throw new InvalidOperationException("Servidor MCP sin iniciar.");
            var hecho = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            _dispatcher.InvokeAsync(() =>
            {
                try
                {
                    Document d = Documento();
                    string cmd = ComandoEnCurso(d);
                    if (cmd.Length > 0)
                        throw new Aplicacion.ErrorUsuario($"Civil 3D está ocupado con el comando {cmd}. Terminarlo y volver a intentar.");
                    AcadApp.DocumentManager.ExecuteInCommandContextAsync(_ =>
                    {
                        try { accion(AcadApp.DocumentManager.MdiActiveDocument); hecho.TrySetResult(true); }
                        catch (Exception ex) { hecho.TrySetException(ex); }
                        return Task.CompletedTask;
                    }, null);
                }
                catch (Exception ex) { hecho.TrySetException(ex); }
            });
            if (!hecho.Task.Wait(ESPERA_MAX)) throw new TimeoutException("Civil 3D no aplicó el cambio a tiempo.");
            Desenvolver(hecho.Task);
        }

        private static T Desenvolver<T>(Task<T> t)
        {
            if (t.IsFaulted)
            {
                Exception ex = t.Exception?.GetBaseException() ?? new Exception("Error desconocido.");
                if (ex is Aplicacion.ErrorUsuario) throw ex;
                throw new Exception(ex.Message, ex);
            }
            return t.Result;
        }
    }
}

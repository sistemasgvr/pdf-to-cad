using System;
using System.Diagnostics;
using System.IO;
using System.IO.Pipes;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Civil3DBasico.Mcp.Aplicacion;
using Civil3DBasico.Mcp.Contratos;

// ============================================================================
//  Servidor LOCAL de la tubería con nombre (\\.\pipe\pdfcad-civil3d-<pid>). Solo
//  el usuario actual puede conectarse (PipeOptions.CurrentUserOnly). Un hilo por
//  conexión; cada línea es un Pedido y se responde con una línea Respuesta. No
//  sabe de MCP: lo traduce el host (PdfCadMcp.exe), que es quien habla con Claude
//  o con la app.
// ============================================================================

namespace Civil3DBasico.Mcp.Infraestructura
{
    internal sealed class ServidorTuberia : IDisposable
    {
        public const int CONEXIONES_MAX = 4;

        private readonly Despachador _despachador;
        private readonly CancellationTokenSource _cancelar = new CancellationTokenSource();
        public string Nombre { get; } = Protocolo.PREFIJO_TUBERIA + Process.GetCurrentProcess().Id;
        public int Atendidos;

        public ServidorTuberia(Despachador d) { _despachador = d; }

        public void Iniciar()
        {
            for (int i = 0; i < CONEXIONES_MAX; i++)
                new Thread(Escuchar) { IsBackground = true, Name = "PDFCAD-MCP-" + i }.Start();
        }

        private void Escuchar()
        {
            while (!_cancelar.IsCancellationRequested)
            {
                try
                {
                    using (var srv = new NamedPipeServerStream(Nombre, PipeDirection.InOut, CONEXIONES_MAX,
                               PipeTransmissionMode.Byte, PipeOptions.Asynchronous | PipeOptions.CurrentUserOnly))
                    {
                        srv.WaitForConnectionAsync(_cancelar.Token).GetAwaiter().GetResult();
                        Atender(srv);
                    }
                }
                catch (OperationCanceledException) { return; }
                catch (Exception) { Thread.Sleep(500); }   // conexión rota: volver a escuchar
            }
        }

        private void Atender(Stream s)
        {
            var utf8 = new UTF8Encoding(false);
            using (var lector = new StreamReader(s, utf8, false, 8192, leaveOpen: true))
            using (var escritor = new StreamWriter(s, utf8, 8192, leaveOpen: true) { AutoFlush = true, NewLine = "\n" })
            {
                string linea;
                while (!_cancelar.IsCancellationRequested && (linea = lector.ReadLine()) != null)
                {
                    if (linea.Trim().Length == 0) continue;
                    Respuesta r;
                    try
                    {
                        Pedido p = JsonSerializer.Deserialize<Pedido>(linea, Protocolo.Json);
                        r = _despachador.Ejecutar(p);
                    }
                    catch (JsonException ex) { r = Respuesta.Mal("", "JSON inválido: " + ex.Message); }
                    Interlocked.Increment(ref Atendidos);
                    escritor.WriteLine(JsonSerializer.Serialize(r, Protocolo.Json));
                }
            }
        }

        public void Dispose() => _cancelar.Cancel();
    }
}

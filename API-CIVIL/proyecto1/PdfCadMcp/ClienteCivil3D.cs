using System;
using System.IO;
using System.IO.Pipes;
using System.Linq;
using System.Text;
using System.Text.Json;
using Civil3DBasico.Mcp.Contratos;

// ============================================================================
//  Cliente de la tubería del plugin (\\.\pipe\pdfcad-civil3d-<pid>). Busca la
//  instancia de Civil 3D con la conexión de la IA encendida, mantiene la conexión
//  abierta y reconecta si Civil 3D se reinicia.
// ============================================================================

namespace PdfCadMcp
{
    internal sealed class ClienteCivil3D : IDisposable
    {
        public const int CONECTAR_MS = 3000;
        public const string SIN_CONEXION =
            "Civil 3D no está conectado. En Civil 3D: panel PANEL_REDES → «Encender conexión de la IA» (o comando PDFCAD_IA).";

        private NamedPipeClientStream _tubo;
        private StreamReader _lector;
        private StreamWriter _escritor;
        private readonly object _cerrojo = new object();

        /// <summary>Tuberías del plugin abiertas en esta PC (una por Civil 3D encendido).</summary>
        public static string[] Disponibles()
        {
            try
            {
                return Directory.GetFiles(@"\\.\pipe\")
                                .Select(Path.GetFileName)
                                .Where(n => n.StartsWith(Protocolo.PREFIJO_TUBERIA, StringComparison.OrdinalIgnoreCase))
                                .ToArray();
            }
            catch { return Array.Empty<string>(); }
        }

        public Respuesta Enviar(Pedido p)
        {
            lock (_cerrojo)
            {
                for (int intento = 0; intento < 2; intento++)
                {
                    try
                    {
                        if (_tubo == null || !_tubo.IsConnected) Conectar();
                        _escritor.WriteLine(JsonSerializer.Serialize(p, Protocolo.Json));
                        string linea = _lector.ReadLine();
                        if (linea == null) throw new IOException("Civil 3D cerró la conexión.");
                        return JsonSerializer.Deserialize<Respuesta>(linea, Protocolo.Json);
                    }
                    catch (SinCivil3D) { return Respuesta.Mal(p.Id, SIN_CONEXION); }
                    catch (Exception) { Cerrar(); }   // reintenta una vez (Civil 3D reiniciado)
                }
                return Respuesta.Mal(p.Id, SIN_CONEXION);
            }
        }

        private void Conectar()
        {
            Cerrar();
            string nombre = Disponibles().FirstOrDefault();
            if (nombre == null) throw new SinCivil3D();
            _tubo = new NamedPipeClientStream(".", nombre, PipeDirection.InOut, PipeOptions.CurrentUserOnly);
            _tubo.Connect(CONECTAR_MS);
            var utf8 = new UTF8Encoding(false);
            _lector = new StreamReader(_tubo, utf8, false, 8192, leaveOpen: true);
            _escritor = new StreamWriter(_tubo, utf8, 8192, leaveOpen: true) { AutoFlush = true, NewLine = "\n" };
        }

        private void Cerrar()
        {
            try { _lector?.Dispose(); _escritor?.Dispose(); _tubo?.Dispose(); } catch { }
            _tubo = null; _lector = null; _escritor = null;
        }

        public void Dispose() => Cerrar();

        private sealed class SinCivil3D : Exception { }
    }
}

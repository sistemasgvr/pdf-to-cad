using System;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.Runtime;
using Civil3DBasico.Mcp.Aplicacion;
using Civil3DBasico.Mcp.Infraestructura;
using AcadApp = Autodesk.AutoCAD.ApplicationServices.Application;

// ============================================================================
//  PDFCAD_IA — enciende / apaga la conexión de la IA (MCP) con este Civil 3D.
//  Es el ÚNICO comando nuevo (y un solo botón en el panel). Composición de la
//  arquitectura limpia: aquí se arman los adaptadores y el despachador.
//  Encendido, cualquier cliente MCP (Claude o la app con Qwen) que lance
//  PdfCadMcp.exe puede leer el dibujo y proponer cambios; aplicar siempre pide
//  confirmación y queda en «<dibujo>.pdfcad-ia.jsonl».
// ============================================================================

namespace Civil3DBasico.Mcp
{
    public class ComandoIA
    {
        private static ServidorTuberia _servidor;

        public static bool Encendido => _servidor != null;

        [CommandMethod("PDFCAD_IA")]
        public void Alternar()
        {
            var ed = AcadApp.DocumentManager.MdiActiveDocument?.Editor;
            try
            {
                if (_servidor != null)
                {
                    _servidor.Dispose();
                    _servidor = null;
                    ed?.WriteMessage("\n[IA] Conexión de la IA APAGADA.");
                    return;
                }
                HiloAutoCAD.Capturar();
                var despachador = new Despachador(
                    new Civil3DLector(),
                    new Civil3DEditor(),
                    new RegistroArchivo(() => HiloAutoCAD.Leer(d => d.Name, permitirOcupado: true)));
                _servidor = new ServidorTuberia(despachador);
                _servidor.Iniciar();
                ed?.WriteMessage($"\n[IA] Conexión de la IA ENCENDIDA ({_servidor.Nombre}). " +
                                 "Abre Claude (o el chat de la app) y pregunta por el dibujo. PDFCAD_IA otra vez para apagar.");
            }
            catch (System.Exception ex)
            {
                _servidor = null;
                ed?.WriteMessage("\n[IA] No se pudo encender: " + ex.Message);
            }
        }
    }
}

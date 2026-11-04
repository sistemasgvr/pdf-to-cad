using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using Civil3DBasico.Mcp.Aplicacion;
using Civil3DBasico.Mcp.Contratos;
using Civil3DBasico.Mcp.Dominio;

// ============================================================================
//  ADAPTADOR del registro de cambios: una línea JSON por cambio, en un archivo
//  JUNTO AL DWG («plano.dwg» → «plano.pdfcad-ia.jsonl»), así viaja con el proyecto
//  y no depende del historial del chat. Dibujo sin guardar → %APPDATA%.
// ============================================================================

namespace Civil3DBasico.Mcp.Infraestructura
{
    internal sealed class RegistroArchivo : IRegistroCambios
    {
        private readonly Func<string> _rutaDibujo;
        private readonly object _cerrojo = new object();

        public RegistroArchivo(Func<string> rutaDibujo) { _rutaDibujo = rutaDibujo; }

        internal static string RutaPara(string dibujo)
        {
            if (!string.IsNullOrEmpty(dibujo) && Path.IsPathRooted(dibujo) && Directory.Exists(Path.GetDirectoryName(dibujo)))
                return Path.ChangeExtension(dibujo, ".pdfcad-ia.jsonl");
            string dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                                      "pdf-to-cad", "civil3d-ia");
            Directory.CreateDirectory(dir);
            string nombre = string.IsNullOrEmpty(dibujo) ? "sin_nombre" : Path.GetFileNameWithoutExtension(dibujo);
            return Path.Combine(dir, nombre + ".pdfcad-ia.jsonl");
        }

        public void Anotar(RegistroCambio r)
        {
            string linea = JsonSerializer.Serialize(r, Protocolo.Json);
            lock (_cerrojo) File.AppendAllText(RutaPara(_rutaDibujo()), linea + "\n", new UTF8Encoding(false));
        }

        public List<RegistroCambio> Ultimos(int n)
        {
            string ruta = RutaPara(_rutaDibujo());
            if (!File.Exists(ruta)) return new List<RegistroCambio>();
            lock (_cerrojo)
                return File.ReadLines(ruta).Where(l => l.Trim().Length > 0).Reverse().Take(n)
                           .Select(l => { try { return JsonSerializer.Deserialize<RegistroCambio>(l, Protocolo.Json); } catch { return null; } })
                           .Where(x => x != null).ToList();
        }
    }
}

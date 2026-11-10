using Autodesk.AutoCAD.Runtime;
using Autodesk.AutoCAD.ApplicationServices;

// ============================================================================
//  ExtensionApp.cs - Punto de entrada del plugin para el Autoloader.
//  Sin este IExtensionApplication, Civil 3D 2025+ (net8.0) puede cargar el
//  DLL sin enumerar los tipos y los [CommandMethod] quedarian invisibles.
// ============================================================================

[assembly: ExtensionApplication(typeof(Civil3DBasico.AsistenteC3DExtension))]

namespace Civil3DBasico
{
    public class AsistenteC3DExtension : IExtensionApplication
    {
        public void Initialize()
        {
            // moño y caja de válvula en los perfiles: siguen a su vista en todo dibujo abierto (PerfilValvulasSeguir)
            try
            {
                foreach (Document d in Application.DocumentManager) PerfilValvulasSeguir.Activar(d);
                Application.DocumentManager.DocumentCreated += (s, e) => PerfilValvulasSeguir.Activar(e.Document);
            }
            catch { }
            try
            {
                var doc = Application.DocumentManager.MdiActiveDocument;
                if (doc != null)
                    doc.Editor.WriteMessage("\n[Asistente C3D] Escribe PANEL_REDES para abrir el panel.");
                else
                    Application.DocumentManager.DocumentActivated += OnFirstDocument;
            }
            catch { }
        }

        private void OnFirstDocument(object sender, DocumentCollectionEventArgs e)
        {
            try
            {
                e.Document.Editor.WriteMessage("\n[Asistente C3D] Escribe PANEL_REDES para abrir el panel.");
                Application.DocumentManager.DocumentActivated -= OnFirstDocument;
            }
            catch { }
        }

        public void Terminate() { }
    }
}

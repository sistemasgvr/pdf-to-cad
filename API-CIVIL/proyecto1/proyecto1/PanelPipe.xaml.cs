using System;
using System.IO;
using System.Reflection;
using System.Windows.Controls;
using AcadApp = Autodesk.AutoCAD.ApplicationServices.Application;

namespace Civil3DBasico
{
    public partial class PanelPipe : UserControl
    {
        public PanelPipe()
        {
            InitializeComponent();

            btnImportar.Click      += (s, e) => Ejecutar("IMPORTAR_RED");
            btnTuboCurvo.Click     += (s, e) => EjecutarConAddin("AGREGAR_TUBO_CURVO", "ElementosCurvos.dll");
            btnExportarPS.Click    += (s, e) => Ejecutar("EXPORTAR_TUBERIAS_PS");
            btnImportarPS.Click    += (s, e) => Ejecutar("IMPORTAR_TUBERIAS_PS");
            // Directo a STEP2 (sin la cadena de _PARTCATALOGREGEN): 100% automático,
            // detecta solas las familias nuevas del dibujo. PARTCATALOGREGEN solo
            // hace falta a mano, una vez, justo tras instalar una familia nueva en
            // esta sesión de Civil3D (comando PREPARAR_FAMILIAS, escrito a mano).
            btnPrepararFamilias.Click += (s, e) => Ejecutar("PREPARAR_FAMILIAS_STEP2");
            btnCotarTuberias.Click += (s, e) => Ejecutar("COTAR_TUBERIAS");
            btnCuadroBuzones.Click += (s, e) => Ejecutar("CUADRO_BUZONES");
            btnPerfilLongitudinal.Click += (s, e) => Ejecutar("CREAR_PERFIL_RED");
        }

        private void Ejecutar(string comando)
        {
            var doc = AcadApp.DocumentManager.MdiActiveDocument;
            if (doc != null)
                doc.SendStringToExecute(comando + " ", true, false, true);
        }

        // AGREGAR_TUBO_CURVO vive en ElementosCurvos.dll, un addin aparte (no
        // referenciado por este ensamblado): antes de mandar el comando hay que
        // asegurarse de que esté cargado. Se busca junto a proyecto1.dll (mismo
        // bundle) y se NETLOAD-ea si hace falta; si ya está cargado, LoadModule
        // con bOnce=true no hace nada.
        private void EjecutarConAddin(string comando, string dllName)
        {
            try
            {
                string dir = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
                string dllPath = Path.Combine(dir ?? "", dllName);
                if (File.Exists(dllPath))
                    Autodesk.AutoCAD.Runtime.SystemObjects.DynamicLinker.LoadModule(dllPath, false, true);
            }
            catch { /* si falla la carga, se intenta igual: puede que ya estuviera cargado a mano */ }
            Ejecutar(comando);
        }
    }
}

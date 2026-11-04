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
            btnTuboCurvo.Click     += (s, e) => Ejecutar("AGREGAR_TUBO_CURVO");
            btnExportarPS.Click    += (s, e) => Ejecutar("EXPORTAR_TUBERIAS_PS");
            btnImportarPS.Click    += (s, e) => Ejecutar("IMPORTAR_TUBERIAS_PS");
            btnPrepararFamilias.Click += (s, e) => Ejecutar("PREPARAR_FAMILIAS_STEP2");
            btnCotarTuberias.Click += (s, e) => Ejecutar("COTAR_TUBERIAS");
            btnCuadroBuzones.Click += (s, e) => Ejecutar("CUADRO_BUZONES");
            btnPerfilLongitudinal.Click += (s, e) => Ejecutar("CREAR_PERFIL_RED");
            btnAsistenteIA.Click += (s, e) =>
            {
                Ejecutar("PDFCAD_IA");
                // El comando corre en cola: el texto refleja el estado que tendrá.
                btnAsistenteIA.Content = Mcp.ComandoIA.Encendido ? "Encender conexión de la IA" : "Apagar conexión de la IA";
            };
        }

        private void Ejecutar(string comando)
        {
            var doc = AcadApp.DocumentManager.MdiActiveDocument;
            if (doc != null)
                doc.SendStringToExecute(comando + " ", true, false, true);
        }
    }
}

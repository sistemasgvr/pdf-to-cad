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
            btnExportarPS.Click    += (s, e) => Ejecutar("EXPORTAR_TUBERIAS_PS");
            btnImportarPS.Click    += (s, e) => Ejecutar("IMPORTAR_TUBERIAS_PS");
            btnDiagFamilias.Click  += (s, e) => Ejecutar("DIAG_FAMILIAS");
            btnCotarTuberias.Click += (s, e) => Ejecutar("COTAR_TUBERIAS");
        }

        private void Ejecutar(string comando)
        {
            var doc = AcadApp.DocumentManager.MdiActiveDocument;
            if (doc != null)
                doc.SendStringToExecute(comando + " ", true, false, true);
        }
    }
}

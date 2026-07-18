using System.Windows.Controls;
using AcadApp = Autodesk.AutoCAD.ApplicationServices.Application;

namespace Civil3DBasico
{
    public partial class PanelPipe : UserControl
    {
        public PanelPipe()
        {
            InitializeComponent();

            btnImportar.Click  += (s, e) => Ejecutar("IMPORTAR_RED");
            btnListar.Click    += (s, e) => Ejecutar("LISTAR_PIEZAS_PRESION");
            btnElemento.Click  += (s, e) =>
            {
                string tipo = (cboElemento.SelectedItem as ComboBoxItem)?.Content?.ToString() ?? "Codo";
                Ejecutar("AGREGAR_ELEMENTO_PRESION " + tipo);
            };
            btnUnir.Click      += (s, e) => Ejecutar("UNIR_TUBERIAS_PRESION");
            btnDescribir.Click += (s, e) => Ejecutar("DESCRIBIR_PIEZA_PRESION");
            btnPerfilGrav.Click  += (s, e) => Ejecutar("CREAR_PERFIL_RED");
            btnPerfilPres.Click  += (s, e) => Ejecutar("CREAR_PERFIL_PRESION");
            btnInvertirEje.Click += (s, e) => Ejecutar("INVERTIR_ALINEAMIENTO");
            btnSolidos.Click   += (s, e) => Ejecutar("EXTRAER_SOLIDOS_PRESION");
            btnExcel.Click     += (s, e) => Ejecutar("EXPORTAR_RED_EXCEL");
            btnPropSet.Click   += (s, e) => Ejecutar("ADJUNTAR_PROPERTY_SET");
        }

        private void Ejecutar(string comando)
        {
            var doc = AcadApp.DocumentManager.MdiActiveDocument;
            if (doc != null)
                doc.SendStringToExecute(comando + " ", true, false, true);
        }
    }
}

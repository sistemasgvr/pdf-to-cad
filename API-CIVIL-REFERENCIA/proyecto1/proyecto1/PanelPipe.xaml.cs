using System.Windows.Controls;
using AcadApp = Autodesk.AutoCAD.ApplicationServices.Application;

namespace Civil3DBasico
{
    /// <summary>
    /// Control WPF del panel de la red de gravedad. Cada botón LANZA su comando.
    /// </summary>
    public partial class PanelPipe : UserControl
    {
        public PanelPipe()
        {
            InitializeComponent();

            // 1) Preparar
            btnCrearRed.Click += (s, e) => Ejecutar("CREAR_RED");
            btnListaPz.Click  += (s, e) => Ejecutar("LISTAR_PIEZAS");
            btnFamilia.Click  += (s, e) => Ejecutar("AGREGAR_FAMILIA");
            btnTamanos.Click  += (s, e) => Ejecutar("AGREGAR_TAMANOS");

            // 2) Trazar y colocar
            btnPoli.Click     += (s, e) => Ejecutar("CREAR_RED_POLILINEA");
            btnCogo.Click     += (s, e) => Ejecutar("CREAR_RED_COGO");
            btnUnir.Click     += (s, e) => Ejecutar("UNIR_TUBERIAS_RED");
            btnPerfil.Click   += (s, e) => Ejecutar("CREAR_PERFIL_RED");
            btnInvEje.Click   += (s, e) => Ejecutar("INVERTIR_ALINEAMIENTO");
            btnCsv.Click      += (s, e) => Ejecutar("CREAR_RED_DESDE_CSV");
            btnCompleta.Click += (s, e) => Ejecutar("CREAR_RED_COMPLETA");

            // 3) Analizar y exportar
            btnDiag.Click     += (s, e) => Ejecutar("DIAGNOSTICAR_RED");
            btnSolidos.Click  += (s, e) => Ejecutar("EXTRAER_SOLIDOS_RED");
            btnExcel.Click    += (s, e) => Ejecutar("EXPORTAR_RED_CSV");
            btnPropSet.Click  += (s, e) => Ejecutar("ADJUNTAR_PROPERTY_SET");
        }

        private void Ejecutar(string comando)
        {
            var doc = AcadApp.DocumentManager.MdiActiveDocument;
            if (doc != null)
                doc.SendStringToExecute(comando + " ", true, false, true);
        }
    }
}

using System.Windows.Controls;
using AcadApp = Autodesk.AutoCAD.ApplicationServices.Application;

namespace Civil3DBasico
{
    /// <summary>
    /// Control WPF del panel de corredores. Cada botón LANZA su comando.
    /// </summary>
    public partial class PanelCorredor : UserControl
    {
        public PanelCorredor()
        {
            InitializeComponent();

            // 1) Crear corredor
            btnCorredor.Click     += (s, e) => Ejecutar("CORREDOR");
            btnCorredorCogo.Click += (s, e) => Ejecutar("CORREDOR_COGO");
            btnTramos.Click       += (s, e) => Ejecutar("CREAR_CORREDOR_TRAMOS");
            btnRegiones.Click     += (s, e) => Ejecutar("CREAR_CORREDOR_REGIONES");

            // 2) Eje y perfil
            btnInvEje.Click       += (s, e) => Ejecutar("INVERTIR_ALINEAMIENTO");
            btnPerfil.Click       += (s, e) => Ejecutar("CREAR_PROFILE_TERRENO");
            btnRasante.Click      += (s, e) => Ejecutar("CREAR_RASANTE_EN_VISTA");

            // 3) Targets y salida
            btnTargets.Click      += (s, e) => Ejecutar("ASIGNAR_TARGETS_CORREDOR");
            btnSupCor.Click       += (s, e) => Ejecutar("CREAR_SUPERFICIE_CORREDOR");
            btnSolidos.Click      += (s, e) => Ejecutar("EXTRAER_SOLIDOS_CORREDOR");
            btnSolCsv.Click       += (s, e) => Ejecutar("EXPORTAR_SOLIDOS_CSV");
        }

        private void Ejecutar(string comando)
        {
            var doc = AcadApp.DocumentManager.MdiActiveDocument;
            if (doc != null)
                doc.SendStringToExecute(comando + " ", true, false, true);
        }
    }
}

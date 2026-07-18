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

            btnProfTerreno.Click += (s, e) => Ejecutar("CREAR_PROFILE_TERRENO");
            btnVista.Click       += (s, e) => Ejecutar("CREAR_VISTA_PERFIL");
            btnRasante.Click     += (s, e) => Ejecutar("CREAR_RASANTE_EN_VISTA");

            btnFacil.Click       += (s, e) => Ejecutar("CREAR_CORREDOR_FACIL");
            btnTramos.Click      += (s, e) => Ejecutar("CREAR_CORREDOR_TRAMOS");
            btnRegiones.Click    += (s, e) => Ejecutar("CREAR_CORREDOR_REGIONES");

            btnTargets.Click     += (s, e) => Ejecutar("ASIGNAR_TARGETS_CORREDOR");
            btnSupCor.Click      += (s, e) => Ejecutar("CREAR_SUPERFICIE_CORREDOR");
            btnSolidos.Click     += (s, e) => Ejecutar("EXTRAER_SOLIDOS_CORREDOR");
        }

        private void Ejecutar(string comando)
        {
            var doc = AcadApp.DocumentManager.MdiActiveDocument;
            if (doc != null)
                doc.SendStringToExecute(comando + " ", true, false, true);
        }
    }
}

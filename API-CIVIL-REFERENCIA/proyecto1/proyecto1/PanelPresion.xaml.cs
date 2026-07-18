using System.Windows.Controls;
using AcadApp = Autodesk.AutoCAD.ApplicationServices.Application;

namespace Civil3DBasico
{
    /// <summary>
    /// Control WPF del panel de red a presión. Cada botón LANZA su comando
    /// (con SendStringToExecute), reutilizando la lógica que ya existe.
    /// Es una primera versión: se puede ampliar con campos, listas, etc.
    /// </summary>
    public partial class PanelPresion : UserControl
    {
        public PanelPresion()
        {
            InitializeComponent();

            // Conectar cada botón con su comando de AutoCAD
            btnCrearRed.Click += (s, e) => Ejecutar("CREAR_RED_PRESION");
            btnListar.Click   += (s, e) => Ejecutar("LISTAR_PIEZAS_PRESION");
            btnRun.Click      += (s, e) => Ejecutar("CREAR_RUN_PRESION");
            btnRunCogo.Click  += (s, e) => Ejecutar("CREAR_RUN_PRESION_COGO");
            btnTubo.Click     += (s, e) => Ejecutar("AGREGAR_TUBO_PRESION");
            btnPerfil.Click   += (s, e) => Ejecutar("CREAR_PERFIL_PRESION");
            btnInvEje.Click   += (s, e) => Ejecutar("INVERTIR_ALINEAMIENTO");
            btnRasante.Click  += (s, e) => Ejecutar("SEGUIR_RASANTE_PRESION");
            btnElemento.Click += (s, e) =>
            {
                // Toma el tipo del desplegable y lo pasa al comando (responde el keyword)
                string tipo = (cboElemento.SelectedItem as ComboBoxItem)?.Content?.ToString() ?? "Codo";
                Ejecutar("AGREGAR_ELEMENTO_PRESION " + tipo);
            };
            btnUnir.Click     += (s, e) => Ejecutar("UNIR_TUBERIAS_PRESION");
            btnUnirVarias.Click += (s, e) => Ejecutar("UNIR_VARIAS_PRESION");
            btnRamificar.Click  += (s, e) => Ejecutar("RAMIFICAR_PRESION");
            btnDescribir.Click += (s, e) => Ejecutar("DESCRIBIR_PIEZA_PRESION");
            btnSolidos.Click  += (s, e) => Ejecutar("EXTRAER_SOLIDOS_PRESION");
            btnSolidoPieza.Click += (s, e) => Ejecutar("EXTRAER_SOLIDO_PIEZA_PRESION");
            btnPropSet.Click  += (s, e) => Ejecutar("ADJUNTAR_PROPERTY_SET");
            btnExcel.Click    += (s, e) => Ejecutar("EXPORTAR_RED_PRESION_EXCEL");
        }

        // Envía el comando a la línea de comandos del dibujo activo.
        private void Ejecutar(string comando)
        {
            var doc = AcadApp.DocumentManager.MdiActiveDocument;
            if (doc != null)
                doc.SendStringToExecute(comando + " ", true, false, true);
        }
    }
}

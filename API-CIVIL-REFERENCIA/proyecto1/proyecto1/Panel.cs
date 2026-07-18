using System;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.Runtime;
using Autodesk.AutoCAD.Windows;

namespace Civil3DBasico
{
    /// <summary>
    /// Comando para mostrar la VENTANA/panel acoplable (PaletteSet) de la red a presión.
    /// El panel hospeda el control WPF 'PanelPresion' (ver PanelPresion.xaml).
    /// </summary>
    public class ComandosPanel
    {
        // Se guarda estático para reutilizar el mismo panel (no crear uno nuevo cada vez).
        private static PaletteSet _panel;

        // GUID fijo que identifica el panel (para que AutoCAD recuerde su posición).
        private static readonly Guid PanelGuid = new Guid("7F3A2C10-9B4E-4E21-A6C2-1B2C3D4E5F60");

        // =====================================================================
        // PANEL_PRESION — abre (o muestra) el panel acoplable de red a presión.
        // =====================================================================
        [CommandMethod("PANEL_PRESION")]
        public void MostrarPanelPresion()
        {
            if (_panel == null)
            {
                _panel = new PaletteSet("Red a Presión", PanelGuid);
                _panel.Style = PaletteSetStyles.ShowCloseButton | PaletteSetStyles.ShowAutoHideButton;
                _panel.MinimumSize = new System.Drawing.Size(240, 300);

                // Hospedar el control WPF dentro del panel
                _panel.AddVisual("Presión", new PanelPresion());
            }
            _panel.Visible = true;
        }

        // Panel de la red de GRAVEDAD (Pipe Network)
        private static PaletteSet _panelPipe;
        private static readonly Guid PanelPipeGuid = new Guid("7F3A2C10-9B4E-4E21-A6C2-1B2C3D4E5F61");

        // =====================================================================
        // PANEL_PIPE — abre (o muestra) el panel acoplable de red de gravedad.
        // =====================================================================
        [CommandMethod("PANEL_PIPE")]
        public void MostrarPanelPipe()
        {
            if (_panelPipe == null)
            {
                _panelPipe = new PaletteSet("Red de Gravedad", PanelPipeGuid);
                _panelPipe.Style = PaletteSetStyles.ShowCloseButton | PaletteSetStyles.ShowAutoHideButton;
                _panelPipe.MinimumSize = new System.Drawing.Size(240, 300);
                _panelPipe.AddVisual("Gravedad", new PanelPipe());
            }
            _panelPipe.Visible = true;
        }

        // Panel de CORREDORES
        private static PaletteSet _panelCor;
        private static readonly Guid PanelCorGuid = new Guid("7F3A2C10-9B4E-4E21-A6C2-1B2C3D4E5F62");

        // =====================================================================
        // PANEL_CORREDOR — abre (o muestra) el panel acoplable de corredores.
        // =====================================================================
        [CommandMethod("PANEL_CORREDOR")]
        public void MostrarPanelCorredor()
        {
            if (_panelCor == null)
            {
                _panelCor = new PaletteSet("Corredores", PanelCorGuid);
                _panelCor.Style = PaletteSetStyles.ShowCloseButton | PaletteSetStyles.ShowAutoHideButton;
                _panelCor.MinimumSize = new System.Drawing.Size(240, 300);
                _panelCor.AddVisual("Corredor", new PanelCorredor());
            }
            _panelCor.Visible = true;
        }
    }
}

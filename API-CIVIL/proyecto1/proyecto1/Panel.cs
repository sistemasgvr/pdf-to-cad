using System;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.Runtime;
using Autodesk.AutoCAD.Windows;

namespace Civil3DBasico
{
    public class ComandosPanel
    {
        private static PaletteSet _panel;
        private static readonly Guid PanelGuid = new Guid("7F3A2C10-9B4E-4E21-A6C2-1B2C3D4E5F60");

        [CommandMethod("PANEL_REDES")]
        public void MostrarPanelRedes()
        {
            if (_panel == null)
            {
                _panel = new PaletteSet("Redes de Tuberías", PanelGuid);
                _panel.Style = PaletteSetStyles.ShowCloseButton | PaletteSetStyles.ShowAutoHideButton;
                _panel.MinimumSize = new System.Drawing.Size(240, 300);
                _panel.AddVisual("Redes", new PanelPipe());
            }
            _panel.Visible = true;
        }

        // Panel de CORREDORES
        private static PaletteSet _panelCor;
        private static readonly Guid PanelCorGuid = new Guid("7F3A2C10-9B4E-4E21-A6C2-1B2C3D4E5F62");

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

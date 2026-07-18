using System.Collections.Generic;
using System.Windows;
using System.Windows.Controls;

namespace Civil3DBasico
{
    /// <summary>
    /// Ventana (WPF) para elegir un Property Set mediante BOTONES.
    /// Cada Property Set del dibujo aparece como un botón; al pulsarlo se elige y cierra.
    /// El resultado se lee en SelectedIndex (-1 si se cancela).
    /// </summary>
    public partial class VentanaPropertySet : Window
    {
        public int SelectedIndex { get; private set; } = -1;

        public VentanaPropertySet(List<string> nombres)
        {
            InitializeComponent();

            for (int i = 0; i < nombres.Count; i++)
            {
                int idx = i;   // capturar el índice para el evento
                Button b = new Button
                {
                    Content = "📦  " + nombres[i],
                    Style = (Style)FindResource("Boton")
                };
                b.Click += (s, e) => { SelectedIndex = idx; Close(); };
                pnlLista.Children.Add(b);
            }

            btnCancelar.Click += (s, e) => { SelectedIndex = -1; Close(); };
        }
    }
}

using System.Globalization;
using System.Windows;
using System.Windows.Controls;

// VENTANA de entrada (WPF). Solo pide datos y los valida con la lógica pura; no dibuja nada.
namespace Civil3DBasico.Ejemplo
{
    public sealed class VentanaBrida : Window
    {
        readonly ComboBox _diametro = new ComboBox { Margin = new Thickness(0, 4, 0, 12), MinWidth = 160 };
        readonly TextBlock _mensaje = new TextBlock { TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 0, 0, 12) };

        /// <summary>Diámetro elegido (pulgadas). Válido solo si ShowDialog devolvió true.</summary>
        public double DiametroIn { get; private set; }

        public VentanaBrida()
        {
            Title = "Brida de ejemplo";
            SizeToContent = SizeToContent.WidthAndHeight;
            ResizeMode = ResizeMode.NoResize;
            WindowStartupLocation = WindowStartupLocation.CenterOwner;

            foreach (double d in CalculoBrida.Diametros())
                _diametro.Items.Add(d.ToString("0.##", CultureInfo.InvariantCulture));
            _diametro.SelectedIndex = 0;

            var aceptar = new Button { Content = "Crear", IsDefault = true, MinWidth = 90, Margin = new Thickness(0, 0, 8, 0) };
            var cancelar = new Button { Content = "Cancelar", IsCancel = true, MinWidth = 90 };
            aceptar.Click += (s, e) => Aceptar();

            var botones = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right };
            botones.Children.Add(aceptar);
            botones.Children.Add(cancelar);

            var panel = new StackPanel { Margin = new Thickness(16) };
            panel.Children.Add(new TextBlock { Text = "Diámetro nominal (pulgadas):" });
            panel.Children.Add(_diametro);
            panel.Children.Add(_mensaje);
            panel.Children.Add(botones);
            Content = panel;
        }

        void Aceptar()
        {
            double d;
            if (!double.TryParse(_diametro.Text, NumberStyles.Float, CultureInfo.InvariantCulture, out d))
            {
                _mensaje.Text = "Escribe un número.";
                return;
            }
            ResultadoBrida r = CalculoBrida.Calcular(d);
            if (!r.Valido)
            {
                _mensaje.Text = r.Error;
                return;
            }
            DiametroIn = d;
            DialogResult = true;
        }
    }
}

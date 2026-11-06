using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using Civil3DBasico.Mcp.Contratos;
using Civil3DBasico.Mcp.Dominio;

// ============================================================================
//  CASOS DE USO del MCP (PURO). Recibe un Pedido (venga de Claude, de Qwen desde
//  la app o de cualquier cliente futuro) y devuelve una Respuesta compacta. Aquí
//  vive la política común: perfil, propuesta → confirmación y registro.
//  Cada TEMA registra sus herramientas en su archivo (Despachador*.cs →
//  `Registrar…`): nombre → función. Sin un switch que crezca con cada una.
// ============================================================================

namespace Civil3DBasico.Mcp.Aplicacion
{
    public sealed partial class Despachador
    {
        public const int LIMITE_DEFECTO = 30, LIMITE_MAX = 200;
        public static readonly TimeSpan VIGENCIA_PROPUESTA = TimeSpan.FromMinutes(30);

        private readonly IModeloLector _lector;
        private readonly IEditorDibujo _editor;
        private readonly IRegistroCambios _registro;
        private readonly Func<DateTime> _ahora;
        private readonly Dictionary<string, CambioPropuesto> _pendientes = new Dictionary<string, CambioPropuesto>();
        private readonly object _cerrojo = new object();
        private readonly Dictionary<string, Func<JsonObject, Pedido, object>> _casos =
            new Dictionary<string, Func<JsonObject, Pedido, object>>(StringComparer.OrdinalIgnoreCase);

        public Despachador(IModeloLector lector, IEditorDibujo editor, IRegistroCambios registro, Func<DateTime> ahora = null)
        {
            _lector = lector; _editor = editor; _registro = registro;
            _ahora = ahora ?? (() => DateTime.Now);
            RegistrarLecturas();
            RegistrarConflictos();
            RegistrarRed();
            RegistrarObra();
            RegistrarPlano();
            Caso("proponer_cambio", Proponer);
            Caso("confirmar_cambio", (a, p) => Confirmar(Requerido(a, "id"), p));
            Caso("cancelar_cambio", (a, p) => { lock (_cerrojo) return new { cancelado = _pendientes.Remove(Requerido(a, "id")) }; });
        }

        private void Caso(string nombre, Func<JsonObject, Pedido, object> fn) => _casos[nombre] = fn;

        /// <summary>Herramientas del catálogo sin caso, o casos sin herramienta (lo revisa una prueba).</summary>
        public IEnumerable<string> Descuadres() =>
            Catalogo.Todas.Select(h => h.Nombre).Where(n => !_casos.ContainsKey(n)).Select(n => "sin caso: " + n)
                   .Concat(_casos.Keys.Where(n => Catalogo.Buscar(n) == null).Select(n => "sin herramienta: " + n));

        public Respuesta Ejecutar(Pedido p)
        {
            if (p == null) return Respuesta.Mal("", "Pedido vacío.");
            if (p.V > Protocolo.VERSION)
                return Respuesta.Mal(p.Id, $"Versión de protocolo {p.V} no soportada (plugin: {Protocolo.VERSION}). Actualizar el plugin.");
            Herramienta h = Catalogo.Buscar(p.Herramienta);
            if (h == null) return Respuesta.Mal(p.Id, $"Herramienta desconocida: «{p.Herramienta}».");
            string perfil = string.IsNullOrEmpty(p.Perfil) ? Catalogo.PERFIL_COMPLETO : p.Perfil;
            if (!Catalogo.Permitida(perfil, h.Nombre))
                return Respuesta.Mal(p.Id, $"La herramienta «{h.Nombre}» no está en el perfil «{perfil}».");
            if (!_casos.TryGetValue(h.Nombre, out var fn))
                return Respuesta.Mal(p.Id, $"Herramienta sin caso de uso: {h.Nombre}.");
            try
            {
                return Respuesta.Bien(p.Id, fn(p.Args, p));
            }
            catch (ErrorUsuario ex) { return Respuesta.Mal(p.Id, ex.Message); }
            catch (Exception ex) { return Respuesta.Mal(p.Id, "Error en Civil 3D: " + ex.Message); }
        }

        // ------------------------------------------------------------ propuesta → confirmación

        private object Proponer(JsonObject a, Pedido p)
        {
            Modelo m = _lector.Leer();
            string handle = Elemento(m, a).Handle, tipo = Requerido(a, "tipo");
            CambioPropuesto c = ReglasCambio.Preparar(m, handle, tipo, Valor(m, handle, tipo, a), _lector.CapaExiste, out string error);
            if (c == null) throw new ErrorUsuario(error);
            return Propuesta(c, a, p, "");
        }

        /// <summary>Deja el cambio pendiente (con id) hasta que el usuario lo confirme o venza, y devuelve su tarjeta.</summary>
        private object Propuesta(CambioPropuesto c, JsonObject a, Pedido p, string motivo)
        {
            c.Motivo = Args.Texto(a, "motivo", motivo);
            c.Id = "C" + Guid.NewGuid().ToString("N").Substring(0, 8);
            c.Creado = _ahora();
            c.Origen = p.Origen; c.Usuario = p.Usuario;
            lock (_cerrojo)
            {
                foreach (var k in _pendientes.Where(kv => _ahora() - kv.Value.Creado > VIGENCIA_PROPUESTA).Select(kv => kv.Key).ToList())
                    _pendientes.Remove(k);
                _pendientes[c.Id] = c;
            }
            return c.Resumen();
        }

        private object Confirmar(string id, Pedido p)
        {
            CambioPropuesto c;
            lock (_cerrojo)
            {
                if (!_pendientes.TryGetValue(id, out c)) throw new ErrorUsuario($"No hay ningún cambio pendiente con id {id} (¿ya se aplicó o venció?).");
                if (_ahora() - c.Creado > VIGENCIA_PROPUESTA)
                { _pendientes.Remove(id); throw new ErrorUsuario("La propuesta venció: volver a proponerla."); }
            }
            // El dibujo pudo cambiar desde la propuesta: cada tipo de cambio sabe comprobarlo.
            string error = c.Vigente(_lector.Leer(), _lector.CapaExiste);
            if (error != null) throw new ErrorUsuario(error);

            _editor.Aplicar(c);
            lock (_cerrojo) _pendientes.Remove(id);
            _registro.Anotar(new RegistroCambio
            {
                Fecha = _ahora().ToString("yyyy-MM-dd HH:mm:ss"),
                Origen = string.IsNullOrEmpty(p.Origen) ? c.Origen : p.Origen,
                Usuario = string.IsNullOrEmpty(p.Usuario) ? c.Usuario : p.Usuario,
                Handle = c.Handle, Elemento = c.Elemento, Tipo = c.Tipo, Antes = c.Antes, Despues = c.Despues, Motivo = c.Motivo,
            });
            return new { aplicado = true, c.Id, c.Elemento, c.Tipo, c.Antes, c.Despues, deshacer = "Comando U en Civil 3D." };
        }

        // ------------------------------------------------------------ argumentos

        /// <summary>El elemento por «elemento» (nombre como lo dice el usuario, o handle) o por «handle».</summary>
        private static Referencia Elemento(Modelo m, JsonObject a)
        {
            string q = Args.Texto(a, "elemento");
            if (string.IsNullOrWhiteSpace(q)) q = Args.Texto(a, "handle");
            if (string.IsNullOrWhiteSpace(q)) throw new ErrorUsuario("No se indicó qué elemento (su nombre, p. ej. «ELECTRICO-4 - (1)»).");
            return Resolver(m, q);
        }

        private static Referencia Resolver(Modelo m, string q)
        {
            Referencia r = Referencias.Resolver(m, q, out string error);
            if (r == null) throw new ErrorUsuario(error);
            return r;
        }

        /// <summary>«valor» tal cual, o «sumar» (ft, negativo = bajar) sobre la cota actual del extremo.</summary>
        private static string Valor(Modelo m, string handle, string tipo, JsonObject a)
        {
            double? sumar = Args.Numero(a, "sumar");
            string valor = Args.Texto(a, "valor");
            if (!sumar.HasValue) return valor;
            string x = (tipo ?? "").Trim().ToLowerInvariant();
            if (x != TiposCambio.COTA_INICIO && x != TiposCambio.COTA_FIN) throw new ErrorUsuario("«sumar» solo vale para cotas.");
            Tuberia t = m.Tuberias.FirstOrDefault(y => Calculos.Igual(y.Handle, handle));
            if (t == null) throw new ErrorUsuario("Las cotas solo se cambian en tuberías.");
            double? z = x == TiposCambio.COTA_INICIO ? t.CotaIni : t.CotaFin;
            if (!z.HasValue) throw new ErrorUsuario($"{t.Nombre} no tiene cota en ese extremo: hay que dar la cota exacta.");
            return ReglasCambio.F(z.Value + sumar.Value);
        }

        private static string Requerido(JsonObject a, string clave)
        {
            string v = Args.Texto(a, clave);
            if (string.IsNullOrWhiteSpace(v)) throw new ErrorUsuario($"Falta el argumento '{clave}'.");
            return v.Trim();
        }

        private static object Tabla(int total, int limite, string[] columnas, IEnumerable<object[]> filas)
        {
            var f = filas.ToList();
            return new
            {
                total,
                mostradas = f.Count,
                nota = total > f.Count ? $"Hay {total - f.Count} más: afinar los filtros o subir 'limite' (máx. {LIMITE_MAX})." : null,
                columnas,
                filas = f,
            };
        }
    }

    /// <summary>Error que se explica al usuario tal cual (no es una falla del programa).</summary>
    public sealed class ErrorUsuario : Exception
    {
        public ErrorUsuario(string mensaje) : base(mensaje) { }
    }
}

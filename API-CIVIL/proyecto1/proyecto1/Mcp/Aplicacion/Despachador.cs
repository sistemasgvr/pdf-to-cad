using System;
using System.Collections.Generic;
using System.Linq;
using Civil3DBasico.Mcp.Contratos;
using Civil3DBasico.Mcp.Dominio;

// ============================================================================
//  CASOS DE USO del MCP (PURO). Recibe un Pedido (venga de Claude, de Qwen desde
//  la app o de cualquier cliente futuro) y devuelve una Respuesta compacta. Aquí
//  vive TODA la política: perfil, validación, propuesta → confirmación y registro.
//  Las salidas son tablas (columnas + filas) con topes: menos tokens.
// ============================================================================

namespace Civil3DBasico.Mcp.Aplicacion
{
    public sealed class Despachador
    {
        public const int LIMITE_DEFECTO = 30, LIMITE_MAX = 200;
        public static readonly TimeSpan VIGENCIA_PROPUESTA = TimeSpan.FromMinutes(30);

        private readonly IModeloLector _lector;
        private readonly IEditorDibujo _editor;
        private readonly IRegistroCambios _registro;
        private readonly Func<DateTime> _ahora;
        private readonly Dictionary<string, CambioPropuesto> _pendientes = new Dictionary<string, CambioPropuesto>();
        private readonly object _cerrojo = new object();

        public Despachador(IModeloLector lector, IEditorDibujo editor, IRegistroCambios registro, Func<DateTime> ahora = null)
        {
            _lector = lector; _editor = editor; _registro = registro;
            _ahora = ahora ?? (() => DateTime.Now);
        }

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
            try
            {
                return Respuesta.Bien(p.Id, Despachar(h.Nombre, p));
            }
            catch (ErrorUsuario ex) { return Respuesta.Mal(p.Id, ex.Message); }
            catch (Exception ex) { return Respuesta.Mal(p.Id, "Error en Civil 3D: " + ex.Message); }
        }

        private object Despachar(string nombre, Pedido p)
        {
            var a = p.Args;
            switch (nombre)
            {
                case "estado": return _lector.Estado();
                case "resumen_modelo":
                    return new { redes = Calculos.Resumen(_lector.Leer(), Args.Texto(a, "red")) };
                case "buscar_tuberias": return BuscarTuberias(a);
                case "buscar_estructuras": return BuscarEstructuras(a);
                case "buscar_textos": return BuscarTextos(a);
                case "detalle_elemento": return Detalle(Elemento(_lector.Leer(), a).Handle);
                case "ir_a":
                    var pedidos = Args.Lista(a, "handles").Concat(Args.Lista(a, "elementos")).Take(LIMITE_MAX).ToList();
                    if (pedidos.Count == 0 && !string.IsNullOrWhiteSpace(Args.Texto(a, "elemento"))) pedidos.Add(Args.Texto(a, "elemento"));
                    if (pedidos.Count == 0) throw new ErrorUsuario("No se indicó qué elemento mostrar.");
                    Modelo mi = _lector.Leer();
                    var hs = new List<string>(); var faltan = new List<string>();
                    foreach (string x in pedidos)
                    {
                        Referencia r = Referencias.Resolver(mi, x, out string _);
                        if (r != null) hs.Add(r.Handle); else faltan.Add(x);
                    }
                    if (hs.Count == 0) throw new ErrorUsuario(Referencias.Resolver(mi, pedidos[0], out string err) == null ? err : "No encontré esos elementos.");
                    return new { encontrados = _editor.IrA(hs), pedidos = pedidos.Count, no_encontrados = faltan };
                case "proponer_cambio": return Proponer(a, p);
                case "confirmar_cambio": return Confirmar(Requerido(a, "id"), p);
                case "cancelar_cambio":
                    lock (_cerrojo) return new { cancelado = _pendientes.Remove(Requerido(a, "id")) };
                case "historial":
                    return new { cambios = _registro.Ultimos(Args.Entero(a, "limite", 20, 1, LIMITE_MAX)) };
            }
            throw new ErrorUsuario($"Herramienta sin caso de uso: {nombre}.");
        }

        // ------------------------------------------------------------ lecturas

        private object BuscarTuberias(System.Text.Json.Nodes.JsonObject a)
        {
            var f = new FiltroTuberias
            {
                Red = Args.Texto(a, "red"), Capa = Args.Texto(a, "capa"), Texto = Args.Texto(a, "texto"),
                DiamMin = Args.Numero(a, "diametro_min_in"), DiamMax = Args.Numero(a, "diametro_max_in"),
                PendienteMax = Args.Numero(a, "pendiente_max_pct"),
            };
            int lim = Args.Entero(a, "limite", LIMITE_DEFECTO, 1, LIMITE_MAX);
            var todas = _lector.Leer().Tuberias.Where(f.Cumple).ToList();
            return Tabla(todas.Count, lim,
                new[] { "handle", "nombre", "red", "diam_in", "tamano", "largo_ft", "cota_ini", "cota_fin", "pend_pct", "capa" },
                todas.Take(lim).Select(t => new object[]
                {
                    t.Handle, t.Nombre, t.Red, Math.Round(t.DiametroIn, 2), t.Tamano, Calculos.R2(t.LargoFt),
                    Calculos.R2(t.CotaIni), Calculos.R2(t.CotaFin), Calculos.R2(Calculos.Pendiente(t)), t.Capa,
                }));
        }

        private object BuscarEstructuras(System.Text.Json.Nodes.JsonObject a)
        {
            var f = new FiltroEstructuras
            {
                Red = Args.Texto(a, "red"), Texto = Args.Texto(a, "texto"),
                ProfundidadMin = Args.Numero(a, "profundidad_min_ft"),
            };
            int lim = Args.Entero(a, "limite", LIMITE_DEFECTO, 1, LIMITE_MAX);
            var todas = _lector.Leer().Estructuras.Where(f.Cumple).ToList();
            return Tabla(todas.Count, lim,
                new[] { "handle", "nombre", "red", "tamano", "rim", "sump", "prof_ft", "conexiones" },
                todas.Take(lim).Select(e => new object[]
                {
                    e.Handle, e.Nombre, e.Red, e.Tamano, Calculos.R2(e.Rim), Calculos.R2(e.Sump),
                    Calculos.R2(e.Profundidad()), e.Conexiones,
                }));
        }

        private object BuscarTextos(System.Text.Json.Nodes.JsonObject a)
        {
            var f = new FiltroTextos { Texto = Args.Texto(a, "texto"), Capa = Args.Texto(a, "capa") };
            int lim = Args.Entero(a, "limite", LIMITE_DEFECTO, 1, LIMITE_MAX);
            var todos = _lector.Leer().Textos.Where(f.Cumple).ToList();
            return Tabla(todos.Count, lim,
                new[] { "handle", "tipo", "texto", "capa", "x", "y", "altura" },
                todos.Take(lim).Select(t => new object[]
                {
                    t.Handle, t.Tipo, Recortar(t.Contenido), t.Capa, Calculos.R2(t.X), Calculos.R2(t.Y), Calculos.R2(t.Altura),
                }));
        }

        private const int TEXTO_MAX = 300;
        private static string Recortar(string s) => s == null || s.Length <= TEXTO_MAX ? s : s.Substring(0, TEXTO_MAX) + "…";

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

        private object Detalle(string handle)
        {
            Modelo m = _lector.Leer();
            object basico = (object)m.Tuberias.FirstOrDefault(t => Calculos.Igual(t.Handle, handle))
                         ?? m.Estructuras.FirstOrDefault(e => Calculos.Igual(e.Handle, handle));
            var extra = _lector.Detalle(handle);
            if (basico == null && extra == null) throw new ErrorUsuario($"No existe el elemento {handle}.");
            return new { elemento = basico, datos = extra };
        }

        // ------------------------------------------------------------ cambios

        private object Proponer(System.Text.Json.Nodes.JsonObject a, Pedido p)
        {
            Modelo m = _lector.Leer();
            string handle = Elemento(m, a).Handle, tipo = Requerido(a, "tipo");
            CambioPropuesto c = ReglasCambio.Preparar(m, handle, tipo, Valor(m, handle, tipo, a),
                                                      _lector.CapaExiste, out string error);
            if (c == null) throw new ErrorUsuario(error);
            c.Id = "C" + Guid.NewGuid().ToString("N").Substring(0, 8);
            c.Motivo = Args.Texto(a, "motivo", "");
            c.Creado = _ahora();
            c.Origen = p.Origen; c.Usuario = p.Usuario;
            lock (_cerrojo)
            {
                foreach (var k in _pendientes.Where(kv => _ahora() - kv.Value.Creado > VIGENCIA_PROPUESTA).Select(kv => kv.Key).ToList())
                    _pendientes.Remove(k);
                _pendientes[c.Id] = c;
            }
            return new
            {
                c.Id, c.Handle, c.Elemento, c.Tipo, c.Antes, c.Despues, c.Consecuencias, c.Advertencias,
                instruccion = "Mostrar al usuario. Aplicar solo con confirmar_cambio si acepta.",
            };
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
            // El dibujo pudo cambiar desde la propuesta: se revisa que el «antes» siga igual.
            CambioPropuesto ahora = ReglasCambio.Preparar(_lector.Leer(), c.Handle, c.Tipo, c.Despues, _lector.CapaExiste, out string error);
            if (ahora == null) throw new ErrorUsuario(error);
            if (!string.Equals(ahora.Antes ?? "", c.Antes ?? "", StringComparison.Ordinal))
                throw new ErrorUsuario($"El elemento cambió desde la propuesta (antes «{c.Antes}», ahora «{ahora.Antes}»). Volver a proponer.");

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

        /// <summary>El elemento por «elemento» (nombre como lo dice el usuario, o handle) o por «handle».</summary>
        private static Referencia Elemento(Modelo m, System.Text.Json.Nodes.JsonObject a)
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
        private static string Valor(Modelo m, string handle, string tipo, System.Text.Json.Nodes.JsonObject a)
        {
            double? sumar = Args.Numero(a, "sumar");
            string valor = Args.Texto(a, "valor");
            if (!sumar.HasValue) return valor;
            if (!EsCota(tipo)) throw new ErrorUsuario("«sumar» solo vale para cotas.");
            Tuberia t = m.Tuberias.FirstOrDefault(x => Calculos.Igual(x.Handle, handle));
            if (t == null) throw new ErrorUsuario("Las cotas solo se cambian en tuberías.");
            double? z = tipo.Trim().ToLowerInvariant() == TiposCambio.COTA_INICIO ? t.CotaIni : t.CotaFin;
            if (!z.HasValue) throw new ErrorUsuario($"{t.Nombre} no tiene cota en ese extremo: hay que dar la cota exacta.");
            return ReglasCambio.F(z.Value + sumar.Value);
        }

        private static bool EsCota(string tipo)
        {
            string x = (tipo ?? "").Trim().ToLowerInvariant();
            return x == TiposCambio.COTA_INICIO || x == TiposCambio.COTA_FIN;
        }

        private static string Requerido(System.Text.Json.Nodes.JsonObject a, string clave)
        {
            string v = Args.Texto(a, clave);
            if (string.IsNullOrWhiteSpace(v)) throw new ErrorUsuario($"Falta el argumento '{clave}'.");
            return v.Trim();
        }
    }

    /// <summary>Error que se explica al usuario tal cual (no es una falla del programa).</summary>
    public sealed class ErrorUsuario : Exception
    {
        public ErrorUsuario(string mensaje) : base(mensaje) { }
    }
}

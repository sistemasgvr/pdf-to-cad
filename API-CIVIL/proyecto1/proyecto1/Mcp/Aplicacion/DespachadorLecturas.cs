using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using Civil3DBasico.Mcp.Contratos;
using Civil3DBasico.Mcp.Dominio;

// ============================================================================
//  CASOS DE USO: lecturas (PURO). Tablas compactas (columnas + filas) con topes.
// ============================================================================

namespace Civil3DBasico.Mcp.Aplicacion
{
    public sealed partial class Despachador
    {
        private void RegistrarLecturas()
        {
            Caso("estado", (a, p) => _lector.Estado());
            Caso("resumen_modelo", (a, p) => new { redes = Calculos.Resumen(_lector.Leer(), Args.Texto(a, "red")) });
            Caso("buscar_tuberias", (a, p) => BuscarTuberias(a));
            Caso("buscar_estructuras", (a, p) => BuscarEstructuras(a));
            Caso("buscar_textos", (a, p) => BuscarTextos(a));
            Caso("buscar_accesorios", (a, p) => BuscarAccesorios(a));
            Caso("detalle_elemento", (a, p) => Detalle(Elemento(_lector.Leer(), a).Handle));
            Caso("ir_a", (a, p) => IrA(a));
            Caso("revisar_buzones", (a, p) => RevisarBuzones(a));
            Caso("metrados", (a, p) => Metrados.Calcular(_lector.Leer(), Args.Texto(a, "red")));
            Caso("datos_red", (a, p) => DatosRed(a));
            Caso("historial", (a, p) => new { cambios = _registro.Ultimos(Args.Entero(a, "limite", 20, 1, LIMITE_MAX)) });
        }

        private object BuscarTuberias(JsonObject a)
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

        private object BuscarEstructuras(JsonObject a)
        {
            var f = new FiltroEstructuras
            {
                Red = Args.Texto(a, "red"), Texto = Args.Texto(a, "texto"), ProfundidadMin = Args.Numero(a, "profundidad_min_ft"),
            };
            int lim = Args.Entero(a, "limite", LIMITE_DEFECTO, 1, LIMITE_MAX);
            var todas = _lector.Leer().Estructuras.Where(e => !e.Nula && f.Cumple(e)).ToList();
            return Tabla(todas.Count, lim,
                new[] { "handle", "nombre", "red", "tamano", "rim", "sump", "prof_ft", "conexiones" },
                todas.Take(lim).Select(e => new object[]
                {
                    e.Handle, e.Nombre, e.Red, e.Tamano, Calculos.R2(e.Rim), Calculos.R2(e.Sump), Calculos.R2(e.Profundidad()), e.Conexiones,
                }));
        }

        private object BuscarTextos(JsonObject a)
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

        private object BuscarAccesorios(JsonObject a)
        {
            Modelo m = _lector.Leer();
            string tipo = Args.Texto(a, "tipo"), red = Args.Texto(a, "red");
            int lim = Args.Entero(a, "limite", LIMITE_DEFECTO, 1, LIMITE_MAX);
            var todos = Metrados.Accesorios(m).Where(x =>
                (string.IsNullOrWhiteSpace(tipo) || Calculos.Contiene(x.Tipo, tipo.Trim()) ||
                 Calculos.Contiene(SolucionesRed.Nombre(new Accesorio { Tipo = x.Tipo }), tipo.Trim())) &&
                (string.IsNullOrWhiteSpace(red) || Calculos.Igual(x.Red, red))).ToList();
            return Tabla(todos.Count, lim, new[] { "id", "tipo", "red", "x", "y", "cota_eje", "une" },
                todos.Take(lim).Select(x => new object[]
                {
                    x.Id, x.Tipo, x.Red, Calculos.R2(x.X), Calculos.R2(x.Y), Calculos.R2(x.ZEje),
                    string.Join(", ", Metrados.Tuberias(m, x).Select(t => t.Nombre).Take(4)),
                }));
        }

        private object RevisarBuzones(JsonObject a)
        {
            var avisos = Buzones.Revisar(_lector.Leer(), Args.Texto(a, "red"));
            int lim = Args.Entero(a, "limite", LIMITE_DEFECTO, 1, LIMITE_MAX);
            return Tabla(avisos.Count, lim, new[] { "estructura", "tuberia", "tipo", "diferencia_ft", "aviso" },
                avisos.Take(lim).Select(x => new object[]
                {
                    x.Estructura.Nombre, x.Tuberia?.Nombre, x.Tipo, Calculos.R2(x.DiferenciaFt), x.Texto,
                }));
        }

        private object DatosRed(JsonObject a)
        {
            Modelo m = _lector.Leer();
            string red = Args.Texto(a, "red");
            bool Es(string r) => string.IsNullOrWhiteSpace(red) || Calculos.Igual(r, red);
            return new
            {
                tuberias = new
                {
                    columnas = new[] { "handle", "nombre", "red", "tipo_red", "utilidad", "numero", "tipo", "material", "diam_in",
                                       "x_ini", "y_ini", "x_fin", "y_fin", "cota_ini", "cota_fin", "est_ini", "est_fin", "tamano", "largo_ft" },
                    filas = m.Tuberias.Where(t => Es(t.Red)).Select(t => new object[]
                    {
                        t.Handle, t.Nombre, t.Red, t.TipoRed == Dominio.TipoRed.Presion ? "presion" : "gravedad", t.UtilidadCapa, t.UtilidadNumero,
                        t.TipoApp, t.Material(), Math.Round(t.DiametroIn, 3), R3(t.XIni), R3(t.YIni), R3(t.XFin), R3(t.YFin),
                        R3(t.CotaIni), R3(t.CotaFin), t.EstructuraIni, t.EstructuraFin, t.Tamano, R3(t.LargoFt),
                    }).ToList(),
                },
                estructuras = new
                {
                    columnas = new[] { "handle", "nombre", "red", "x", "y", "rim", "sump", "tamano", "nula" },
                    filas = m.Estructuras.Where(e => Es(e.Red)).Select(e => new object[]
                    {
                        e.Handle, e.Nombre, e.Red, R3(e.X), R3(e.Y), R3(e.Rim), R3(e.Sump), e.Tamano, e.Nula,
                    }).ToList(),
                },
                accesorios = new
                {
                    columnas = new[] { "id", "tipo", "red", "x", "y", "cota_eje", "une" },
                    filas = Metrados.Accesorios(m).Where(x => Es(x.Red) || string.IsNullOrEmpty(x.Red)).Select(x => new object[]
                    {
                        x.Id, x.Tipo, x.Red, R3(x.X), R3(x.Y), R3(x.ZEje), string.Join(", ", Metrados.Tuberias(m, x).Select(t => t.Nombre)),
                    }).ToList(),
                },
            };
        }

        private object IrA(JsonObject a)
        {
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

        private const int TEXTO_MAX = 300;
        private static string Recortar(string s) => s == null || s.Length <= TEXTO_MAX ? s : s.Substring(0, TEXTO_MAX) + "…";
        private static double? R3(double? v) => v.HasValue ? Math.Round(v.Value, 3) : (double?)null;
    }
}

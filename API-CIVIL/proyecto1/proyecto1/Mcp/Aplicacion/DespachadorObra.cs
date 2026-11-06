using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using Civil3DBasico.Mcp.Contratos;
using Civil3DBasico.Mcp.Dominio;

// ============================================================================
//  CASOS DE USO: buzones, válvulas, accesorios, conexiones verticales, mover en
//  planta y choques 3D (PURO). Todo cambio queda PENDIENTE hasta confirmar_cambio.
// ============================================================================

namespace Civil3DBasico.Mcp.Aplicacion
{
    public sealed partial class Despachador
    {
        private void RegistrarObra()
        {
            Caso("proponer_buzon", ProponerBuzon);
            Caso("proponer_valvula", ProponerValvula);
            Caso("proponer_quitar_accesorio", QuitarAccesorio);
            Caso("proponer_conexion_vertical", ConexionVertical);
            Caso("proponer_mover_planta", MoverEnPlanta);
            Caso("buscar_choques_3d", (a, p) => ChoquesReales(a));
        }

        private object ProponerBuzon(JsonObject a, Pedido p)
        {
            Modelo m = _lector.Leer();
            Referencia r = Elemento(m, a);
            Estructura e = m.Estructuras.FirstOrDefault(x => Calculos.Igual(x.Handle, r.Handle))
                           ?? throw new ErrorUsuario($"{r.Nombre} no es un buzón ni una caja.");
            double? rim = Args.Numero(a, "tapa"), sump = Args.Numero(a, "fondo");
            double? st = Args.Numero(a, "sumar_tapa"), sf = Args.Numero(a, "sumar_fondo");
            if (st.HasValue) rim = (e.Rim ?? throw new ErrorUsuario($"{e.Nombre} no tiene tapa: dime la cota.")) + st.Value;
            if (sf.HasValue) sump = (e.Sump ?? throw new ErrorUsuario($"{e.Nombre} no tiene fondo: dime la cota.")) + sf.Value;
            var cp = Buzones.Proponer(m, e, rim, sump, Args.Numero(a, "altura"), out string error);
            if (cp == null) throw new ErrorUsuario(error);
            return Propuesta(cp, a, p, "Buzón");
        }

        private object ProponerValvula(JsonObject a, Pedido p)
        {
            Modelo m = _lector.Leer();
            string accion = (Args.Texto(a, "accion", "poner") ?? "").Trim().ToLowerInvariant();
            CambioValvula cp;
            string error;
            if (accion.StartsWith("quit"))
                cp = CambiosObra.QuitarValvula(m, Accesorio(m, a, "elemento"), out error);
            else
            {
                Tuberia t = UnaTuberia(m, Args.Texto(a, "elemento"), "elemento");
                string union = Args.Texto(a, "union", "FLG");
                double largo = ValvulaReceta.Receta(Math.Max(t.DiametroIn, 1.0), union).Largo;
                cp = CambiosObra.PonerValvula(m, t, Args.Numero(a, "x"), Args.Numero(a, "y"), Args.Numero(a, "distancia_ft"), union, largo, out error);
            }
            if (cp == null) throw new ErrorUsuario(error);
            return Propuesta(cp, a, p, "Válvula");
        }

        private object QuitarAccesorio(JsonObject a, Pedido p)
        {
            Modelo m = _lector.Leer();
            var cp = CambiosObra.QuitarAccesorio(m, Accesorio(m, a, "accesorio"), out string error);
            if (cp == null) throw new ErrorUsuario(error);
            return Propuesta(cp, a, p, "No va accesorio");
        }

        /// <summary>El accesorio por su id A# (de buscar_accesorios) o el más cercano a (x, y).</summary>
        private static GrupoAccesorio Accesorio(Modelo m, JsonObject a, string arg)
        {
            var todos = Metrados.Accesorios(m);
            string q = Args.Texto(a, arg) ?? Args.Texto(a, "accesorio");
            double? x = Args.Numero(a, "x"), y = Args.Numero(a, "y");
            if (!string.IsNullOrWhiteSpace(q))
            {
                string id = NormalizarId(q, "A");
                return todos.FirstOrDefault(k => Calculos.Igual(k.Id, id))
                       ?? throw new ErrorUsuario($"No hay un accesorio «{q}». Usar buscar_accesorios para ver sus ids (A1…).");
            }
            if (!x.HasValue || !y.HasValue) throw new ErrorUsuario("Dime qué accesorio: su id A# o 'x','y'.");
            var cerca = todos.OrderBy(k => Metrados.D(k.X, k.Y, x.Value, y.Value)).FirstOrDefault();
            if (cerca == null || Metrados.D(cerca.X, cerca.Y, x.Value, y.Value) > Math.Max(cerca.RadioFt, 3.0))
                throw new ErrorUsuario("No hay ningún accesorio en ese punto.");
            return cerca;
        }

        private object ConexionVertical(JsonObject a, Pedido p)
        {
            Modelo m = _lector.Leer();
            Tuberia ta, tb;
            string k = Args.Texto(a, "conflicto");
            if (!string.IsNullOrWhiteSpace(k))
            {
                var c = Conflictos.Buscar(m, Reglas(a), out int _).FirstOrDefault(x => Calculos.Igual(x.Id, NormalizarId(k, "K")))
                        ?? throw new ErrorUsuario($"No hay un conflicto «{k}».");
                ta = c.A; tb = c.B;
            }
            else
            {
                var dos = Args.Lista(a, "elementos");
                if (dos.Count != 2) throw new ErrorUsuario("Dime las dos tuberías (o el conflicto K#).");
                ta = UnaTuberia(m, dos[0], "elementos"); tb = UnaTuberia(m, dos[1], "elementos");
            }
            var cp = CambiosObra.ConexionVertical(m, ta, tb, out string error);
            if (cp == null) throw new ErrorUsuario(error);
            return Propuesta(cp, a, p, "Conexión vertical");
        }

        private object MoverEnPlanta(JsonObject a, Pedido p)
        {
            Modelo m = _lector.Leer();
            string q = Args.Texto(a, "elemento");
            if (string.IsNullOrWhiteSpace(q)) throw new ErrorUsuario("Dime qué utilidad o tubería mover.");
            bool soloTramo = Calculos.Contiene(Args.Texto(a, "solo_tramo", ""), "s") || Calculos.Contiene(Args.Texto(a, "solo_tramo", ""), "true");
            var grupo = soloTramo ? new List<Tuberia> { UnaTuberia(m, q, "elemento") } : Utilidad(m, q);
            if (grupo.Count == 1 && !soloTramo) grupo = SolucionesRed.Grupo(m, grupo[0]);
            var v = MoverPlanta.Vector(grupo[0], Args.Numero(a, "dx"), Args.Numero(a, "dy"), Args.Texto(a, "lado"), Args.Numero(a, "distancia"), out string error);
            if (v == null) throw new ErrorUsuario(error);
            var cp = MoverPlanta.Proponer(m, grupo, v.Value.dx, v.Value.dy, Reglas(a), out error);
            if (cp == null) throw new ErrorUsuario(error);
            return Propuesta(cp, a, p, "Mover en planta");
        }

        private object ChoquesReales(JsonObject a)
        {
            string red = Args.Texto(a, "red");
            var cuerpos = _lector.Cuerpos();
            var pares = Choques3D.Pares(cuerpos)
                                 .Where(x => string.IsNullOrWhiteSpace(red) || Calculos.Igual(x.a.Red, red) || Calculos.Igual(x.b.Red, red))
                                 .Select(x => (x.a.Handle, x.b.Handle)).ToList();
            var hay = pares.Count == 0 ? new List<Interferencia>() : _lector.Interferencias(pares);
            int lim = Args.Entero(a, "limite", LIMITE_DEFECTO, 1, LIMITE_MAX);
            object tabla = Choques3D.Tabla(cuerpos, hay, lim, out int total);
            return new
            {
                choques = tabla,
                probados = pares.Count,
                cuerpos = cuerpos.Count,
                nota = total == 0 ? "Ningún sólido se mete en otro (las uniones a propósito no cuentan)."
                    : "Para cada choque entre tuberías: buscar_conflictos y proponer_solucion, o proponer_mover_planta.",
            };
        }
    }
}

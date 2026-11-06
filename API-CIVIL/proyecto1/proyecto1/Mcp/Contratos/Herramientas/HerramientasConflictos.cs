using System.Collections.Generic;

// ============================================================================
//  Herramientas de CONFLICTOS: cruces entre tuberías (con las separaciones de la
//  normativa de la app), choques 3D con todo lo dibujado, y sus soluciones.
// ============================================================================

namespace Civil3DBasico.Mcp.Contratos
{
    internal static class HerramientasConflictos
    {
        public static readonly List<Herramienta> Lista = new List<Herramienta>
        {
            new Herramienta
            {
                Nombre = "buscar_conflictos", Tipo = TipoHerramienta.Lectura, Basico = true,
                Descripcion = "Choques y cruces entre tuberías: dónde se cruzan, cuánto espacio libre queda entre sus paredes y cuánto pide la normativa. Ids K1, K2…",
                Esquema = E.Obj(E.Reglas(), E.Limite()),
            },
            new Herramienta
            {
                Nombre = "buscar_choques_3d", Tipo = TipoHerramienta.Lectura, Basico = true,
                Descripcion = "Choques 3D reales entre TODO lo dibujado (tuberías, buzones, accesorios, válvulas, sólidos y bancoductos), con sus sólidos. Ids S1…",
                Esquema = E.Obj(E.Texto("red", "solo los que tocan esa red (opcional)"), E.Limite()),
            },
            new Herramienta
            {
                Nombre = "proponer_solucion", Tipo = TipoHerramienta.Cambio, Basico = true,
                Descripcion = "Prepara la solución de un conflicto (K1…): sube o baja una utilidad entera lo justo según la normativa, " +
                              "probando que no cree otros conflictos ni separe uniones. Para otra opción: 'mover', 'accion' (bajar|subir) u 'opcion' (P2…).",
                Esquema = E.Req(new[] { "conflicto" }, E.Texto("conflicto", "id del conflicto, p. ej. K3"),
                                E.Texto("mover", "utilidad o tubería a mover (opcional)"), E.Opciones("accion", new[] { "bajar", "subir" }),
                                E.Texto("opcion", "P1, P2… (opcional)"), E.Reglas(), E.Motivo()),
            },
            new Herramienta
            {
                Nombre = "proponer_mover_planta", Tipo = TipoHerramienta.Cambio, Basico = true,
                Descripcion = "Prepara mover en PLANTA una utilidad (o una tubería) para esquivar un choque de lado: 'dx'/'dy' ft, o 'lado' " +
                              "(izquierda/derecha según su sentido) y 'distancia' ft. Dice qué conflictos resuelve o crea.",
                Esquema = E.Obj(E.Elemento("utilidad (AGUA-20) o tubería"), E.Num("dx"), E.Num("dy"),
                                E.Opciones("lado", new[] { "izquierda", "derecha" }), E.Num("distancia"),
                                E.Texto("solo_tramo", "si/no: mover solo esa tubería y no toda su utilidad"), E.Reglas(), E.Motivo()),
            },
        };
    }
}

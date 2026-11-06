using System.Collections.Generic;

// ============================================================================
//  Herramientas de LECTURA: no cambian el dibujo.
// ============================================================================

namespace Civil3DBasico.Mcp.Contratos
{
    internal static class HerramientasLectura
    {
        private static Herramienta L(string n, bool basico, string d, string esquema) =>
            new Herramienta { Nombre = n, Tipo = TipoHerramienta.Lectura, Basico = basico, Descripcion = d, Esquema = esquema };

        public static readonly List<Herramienta> Lista = new List<Herramienta>
        {
            L("estado", true, "Dibujo abierto en Civil 3D: nombre, unidades, sistema de coordenadas y cuántas redes hay. Llamar primero.",
              E.Obj()),
            L("resumen_modelo", true, "Resumen por red: tipo (gravedad/presión), nº de tuberías y estructuras, largo total (ft), diámetros (in) y capas. Usar antes de pedir detalle.",
              E.Obj(E.Texto("red", "Nombre de una red (opcional)"))),
            L("buscar_tuberias", true, "Tuberías que cumplen los filtros (nombre, red, diámetro, cotas, pendiente), con sus COTAS de inicio y fin (solera) y pendiente. Máx. 'limite' filas; dice cuántas más hay.",
              E.Obj(E.Texto("red"), E.Texto("capa"), E.Num("diametro_min_in"), E.Num("diametro_max_in"),
                    E.Num("pendiente_max_pct", "p. ej. 0 = contrapendiente o nula"),
                    E.Texto("texto", "busca en nombre, tamaño y descripción"), E.Limite())),
            L("buscar_estructuras", true, "Estructuras (buzones/cajas) que cumplen los filtros: rim, sump, profundidad. Máx. 'limite'.",
              E.Obj(E.Texto("red"), E.Texto("texto"), E.Num("profundidad_min_ft"), E.Limite())),
            L("buscar_textos", true, "Textos del dibujo (TEXT y MTEXT): qué dicen, capa y posición. Sin 'texto' lista todos; con 'texto' busca los que lo contienen.",
              E.Obj(E.Texto("texto", "palabras a buscar (opcional)"), E.Texto("capa"), E.Limite())),
            L("buscar_accesorios", true, "Accesorios (codos, Tees, Wyes, cruces, válvulas…) con su id A1…, tipo, red, posición y tuberías que une.",
              E.Obj(E.Texto("tipo", "p. ej. valve, tee, codo (opcional)"), E.Texto("red"), E.Limite())),
            L("detalle_elemento", true, "Todo lo que se sabe de un elemento (por su nombre): geometría, cotas, conexiones y Property Sets PDFCAD.",
              E.Obj(E.Elemento(), E.Texto("handle"))),
            L("ir_a", true, "Encuadra y resalta en Civil 3D uno o varios elementos (por nombre) para que el usuario los vea.",
              E.Obj(E.Lista("elementos", "nombres tal como los dice el usuario"), E.Lista("handles"))),
            L("revisar_buzones", true, "Buzones/cajas con problemas: tubería que llega bajo el fondo, corona sobre la tapa, tapa bajo el fondo o sin cotas.",
              E.Obj(E.Texto("red"), E.Limite())),
            L("metrados", true, "Metrados: largo de tubería por utilidad, diámetro y material; accesorios por tipo; buzones por tamaño.",
              E.Obj(E.Texto("red", "solo esa red (opcional)"))),
            L("datos_red", true, "Todas las tuberías, estructuras y accesorios con utilidad, tipo, material, diámetro, puntas y cotas (la app revisa con esto sus normativas).",
              E.Obj(E.Texto("red"))),
            L("historial", false, "Últimos cambios hechos por la IA en este dibujo (quién, cuándo, qué, antes/después).",
              E.Obj(E.Limite(20))),
        };
    }
}

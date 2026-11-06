using System.Collections.Generic;

// ============================================================================
//  Herramientas de REVISIÓN DEL PLANO: anotaciones (textos, rótulos, guías,
//  cotas) como las revisa un dibujante, y sus arreglos (siempre propuestos).
// ============================================================================

namespace Civil3DBasico.Mcp.Contratos
{
    internal static class HerramientasPlano
    {
        public static readonly List<Herramienta> Lista = new List<Herramienta>
        {
            new Herramienta
            {
                Nombre = "revisar_plano", Tipo = TipoHerramienta.Lectura, Basico = true,
                Descripcion = "Revisión de calidad del plano: guías que cruzan textos o cotas, flechas sueltas, textos que se tapan " +
                              "y textos o cotas dentro de tramas. Puntos numerados Q1… con dónde están.",
                Esquema = E.Obj(E.Texto("capa", "solo esa capa (opcional)"),
                                E.Texto("tipo", "guia_cruza_texto | guia_cruza_cota | flecha_suelta | texto_sobre_texto | cota_sobre_texto | texto_en_trama"),
                                E.Limite(40)),
            },
            new Herramienta
            {
                Nombre = "buscar_cotas", Tipo = TipoHerramienta.Lectura, Basico = true,
                Descripcion = "Acotaciones del plano (DIMENSIONES: líneas de medida con su texto): qué dicen, medida real, estilo, " +
                              "decimales, flecha y capa. NO son las elevaciones de tuberías o buzones (ésas: buscar_tuberias, " +
                              "buscar_estructuras, detalle_elemento).",
                Esquema = E.Obj(E.Texto("texto", "lo que dice la cota (opcional)"), E.Texto("estilo"), E.Texto("capa"), E.Limite()),
            },
            new Herramienta
            {
                Nombre = "proponer_arreglo_revision", Tipo = TipoHerramienta.Cambio, Basico = true,
                Descripcion = "Prepara el arreglo de un punto de revisar_plano (Q#): mover lo justo el texto o la cota, borrar la flecha " +
                              "suelta o ponerle máscara al texto sobre una trama.",
                Esquema = E.Req(new[] { "punto" }, E.Texto("punto", "Q# de revisar_plano"), E.Motivo()),
            },
            new Herramienta
            {
                Nombre = "proponer_texto", Tipo = TipoHerramienta.Cambio, Basico = true,
                Descripcion = "Prepara cambiar textos o rótulos (TEXT, MTEXT, MLEADER): 'reemplazar' una parte por 'por' (vacío = quitarla), " +
                              "mover ('dx','dy'), 'altura' o 'mascara'. Cuáles: 'elemento' (uno) o 'buscar' (todos los que dicen eso).",
                Esquema = E.Obj(E.Elemento("handle o texto exacto de UN texto"), E.Texto("buscar", "todos los textos que contienen esto"),
                                E.Texto("capa"), E.Texto("reemplazar", "parte del texto a cambiar"), E.Texto("por", "lo nuevo (vacío = quitar)"),
                                E.Num("dx"), E.Num("dy"), E.Num("altura"), E.Opciones("mascara", new[] { "si", "no" }), E.Motivo()),
            },
            new Herramienta
            {
                Nombre = "proponer_cota", Tipo = TipoHerramienta.Cambio, Basico = true,
                Descripcion = "Prepara crear una cota alineada ('x1','y1','x2','y2', 'desplazamiento') o corregir cotas existentes " +
                              "('cotas' o 'buscar'/'estilo_actual'): 'estilo', 'decimales', 'flecha', 'altura_texto', 'texto' (vacío = medida real).",
                Esquema = E.Obj(E.Opciones("accion", new[] { "crear", "cambiar" }), E.Num("x1"), E.Num("y1"), E.Num("x2"), E.Num("y2"),
                                E.Num("desplazamiento"), E.Lista("cotas", "handles de buscar_cotas"), E.Texto("buscar", "cotas que dicen esto"),
                                E.Texto("estilo_actual", "todas las de ese estilo"), E.Texto("estilo", "estilo nuevo"),
                                E.Ent("decimales", 2), E.Num("flecha"), E.Num("altura_texto"), E.Texto("texto"), E.Motivo()),
            },
        };
    }
}

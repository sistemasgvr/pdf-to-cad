using System.Collections.Generic;

// ============================================================================
//  Herramientas de CAMBIO: todas PROPONEN (nada se aplica) y devuelven id +
//  antes/después + consecuencias; solo confirmar_cambio (botón del usuario) aplica.
// ============================================================================

namespace Civil3DBasico.Mcp.Contratos
{
    internal static class HerramientasCambios
    {
        private static Herramienta C(string n, bool basico, string d, string esquema) =>
            new Herramienta { Nombre = n, Tipo = TipoHerramienta.Cambio, Basico = basico, Descripcion = d, Esquema = esquema };

        public static readonly List<Herramienta> Lista = new List<Herramienta>
        {
            C("proponer_cambio", true,
              "Prepara un cambio SIN aplicarlo. Tipos: cota_inicio | cota_fin (rasante de tubería de gravedad, ft), capa, descripcion. " +
              "Para subir o bajar una cota usar 'sumar' (ft); para fijarla, 'valor'.",
              E.Req(new[] { "tipo" }, E.Elemento(), E.Texto("handle"),
                    E.Opciones("tipo", new[] { "cota_inicio", "cota_fin", "capa", "descripcion" }),
                    E.Texto("valor", "cota final en ft, nombre de capa o texto"),
                    E.Num("sumar", "ft a sumar a la cota actual (negativo = bajar)"), E.Motivo())),
            C("proponer_pendiente", true,
              "Prepara rasantes nuevas para tuberías de gravedad: la pendiente de la normativa de la app (solo las que no cumplen) " +
              "o 'pendiente_pct' si el usuario la dice. Avisa fondos de buzón y saltos.",
              E.Obj(E.Elemento(), E.Elementos(), E.Texto("red", "todas las tuberías de esa red"),
                    E.Num("pendiente_pct", "solo si el usuario la dice"),
                    E.Opciones("mantener", new[] { "inicio", "fin" }, "qué rasante no se mueve (defecto: inicio)"),
                    E.Objeto("objetivos", "pendiente de la normativa por tubería (la pone la app)"), E.Motivo())),
            C("proponer_tamano", true, "Prepara otro diámetro y/o material para tuberías, eligiendo de la lista de piezas de su red.",
              E.Obj(E.Elemento(), E.Elementos(), E.Texto("red"),
                    E.Num("diametro_in", "diámetro nuevo en pulgadas (opcional)"),
                    E.Texto("material", "material nuevo, p. ej. PVC (opcional)"), E.Motivo())),
            C("crear_perfil", true, "Prepara un perfil longitudinal de una red: desde una tubería hasta otra ('hasta' opcional = todo el recorrido).",
              E.Req(new[] { "desde" }, E.Texto("desde", "tubería donde empieza"), E.Texto("hasta", "tubería donde termina (opcional)"),
                    E.Texto("nombre"))),
            C("proponer_buzon", true, "Prepara tapa (rim), fondo (sump) o altura de un buzón/caja: 'valor' o 'sumar' (ft). Avisa tuberías bajo el fondo.",
              E.Req(new[] { "elemento" }, E.Elemento("nombre del buzón o caja"),
                    E.Num("tapa"), E.Num("fondo"), E.Num("altura", "fondo = tapa − altura"),
                    E.Num("sumar_tapa"), E.Num("sumar_fondo"), E.Motivo())),
            C("proponer_valvula", true,
              "Prepara poner una válvula de compuerta en una tubería a presión (en su medio, en 'x','y' o a 'distancia_ft' del inicio) " +
              "o quitar una válvula ('accion'=quitar con su id A#).",
              E.Obj(E.Opciones("accion", new[] { "poner", "quitar" }), E.Elemento("tubería (poner) o válvula A# (quitar)"),
                    E.Num("x"), E.Num("y"), E.Num("distancia_ft"), E.Opciones("union", new[] { "FLG", "RG" }), E.Motivo())),
            C("proponer_quitar_accesorio", true,
              "«Aquí no va codo/Tee»: prepara quitar un accesorio (id A# o 'x','y'); sus tuberías llegan a su centro sin unirse.",
              E.Obj(E.Texto("accesorio", "id A# de buscar_accesorios"), E.Num("x"), E.Num("y"), E.Motivo())),
            C("proponer_conexion_vertical", true,
              "Prepara una conexión vertical entre dos utilidades que se tocan en planta a distinta cota (dos tuberías o un conflicto K#).",
              E.Obj(E.Lista("elementos", "las dos tuberías"), E.Texto("conflicto", "o el id K# de buscar_conflictos"), E.Reglas(), E.Motivo())),
            C("confirmar_cambio", true, "Aplica en Civil 3D un cambio propuesto (id). Solo tras el sí del usuario. Se puede deshacer con U.",
              E.Req(new[] { "id" }, E.Texto("id"))),
            C("cancelar_cambio", true, "Descarta un cambio propuesto (id).", E.Req(new[] { "id" }, E.Texto("id"))),
        };
    }
}

"""Agente de Civil 3D con la IA local (PURO): la ENTRADA 1 del MCP.

El modelo (Qwen en Ollama, con *tool calling* nativo) elige qué herramienta del plugin usar; el plugin
calcula y valida; el agente solo pasa mensajes. Reglas (las mismas que con Claude):
  - El modelo NUNCA confirma: `confirmar_cambio`/`cancelar_cambio` no se le ofrecen; cada `proponer_cambio`
    vuelve en `Resultado.propuestas` y la VENTANA las confirma con `Agente.confirmar(id)` (botón del usuario).
  - Tope de pasos por pregunta (`MAX_PASOS`) y de texto por resultado (`MAX_RESULTADO`): menos tokens.
  - El historial guarda solo preguntas y respuestas (no el tráfico de herramientas).
  - Lo que es de la APP (sus normativas, su proyecto, sus herramientas propias como `revisar_normativas`,
    `exportar_cuadro`, `comparar_con_app`) lo pone `civil3d_locales.Locales`: el modelo no ve ni cambia las reglas,
    y cada propuesta se revisa con el validador de la app antes de llegar a la tarjeta.
`pedir_modelo(mensajes, herramientas)` → {"content", "tool_calls"}: `pedir_ollama(config)` o uno falso en pruebas.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from ia.proveedor import CONTEXTO_TOKENS, ErrorIA, Ollama
from traduccion.i18n_core import t

MAX_PASOS = 14                           # con conflictos: buscar + una propuesta por conflicto
MAX_RESULTADO = 6000                     # caracteres de cada resultado que ve el modelo
MAX_HISTORIAL = 10                       # turnos (pregunta + respuesta) que se reenvían
SOLO_USUARIO = {"confirmar_cambio", "cancelar_cambio"}
PROPONEN = {"proponer_cambio", "proponer_solucion", "proponer_pendiente", "proponer_tamano", "crear_perfil",
            "proponer_buzon", "proponer_valvula", "proponer_quitar_accesorio", "proponer_conexion_vertical",
            "proponer_mover_planta", "traer_a_la_app", "proponer_arreglo_revision", "proponer_texto", "proponer_cota"}
_PENSAR = re.compile(r"<think>.*?</think>\s*", re.S)
# Lo enviado tiene que CABER en la ventana de contexto: si no, Ollama quita los mensajes más viejos —también la
# pregunta— y responde 500 «no user query found in messages» (reporte 2026-11-06: varios conflictos, 14 pasos con
# resultados de 6000 caracteres, y las 28 herramientas + el sistema ya ocupan ~6 300 tokens de 16 384).
RESERVA_RESPUESTA = 2048                 # tokens que quedan para lo que escribe el modelo
CARS_POR_TOKEN = 3.0                     # estimación prudente (JSON y español van de 3 a 4)
RESUMEN_HERRAMIENTA = 700                # caracteres que conserva un resultado viejo
RESUMEN_MINIMO = 250                     # último recurso
RECORDATORIO = ("(Recordatorio de la app: no consultaste el dibujo en esta pregunta. Consulta con las herramientas "
                "antes de responder; no repitas resultados anteriores.)")

CIERRE = "Ya no puedes consultar más. Responde ahora con lo que tienes; si no hay certeza, dilo."


class ConImagen(str):
    """La salida de una herramienta con imágenes (PNG en base64) para que el modelo las vea."""

    def __new__(cls, texto, imagenes=()):
        o = super().__new__(cls, texto)
        o.imagenes = list(imagenes)
        return o


SISTEMA = (
    "Eres el asistente de PDF-a-CAD para un dibujo de Civil 3D. Hablas con un ingeniero: responde en español, "
    "breve, en lenguaje simple.\n"
    "Usa las herramientas para obtener los datos; nunca inventes cifras.\n"
    "Ante cualquier pregunta sobre el dibujo (tuberías, redes, estructuras, textos…) CONSULTA primero con las "
    "herramientas y responde con lo que encuentres. Nunca preguntes al usuario qué dice, dónde está o cómo se "
    "llama algo que puedes buscar. Los textos (TEXT/MTEXT) se leen con buscar_textos (sin filtro = todos).\n"
    "Los elementos se nombran como los dice el usuario (p. ej. «ELECTRICO-4 - (1)»): pásalos en el argumento "
    "'elemento' y el plugin los encuentra. Nunca pidas un handle ni lo inventes.\n"
    "Si el pedido es claro, actúa: no preguntes antes. «Súbela 10 pies» = proponer_cambio con tipo cota_inicio "
    "o cota_fin y sumar=10 («bájala» = negativo; sin decir el extremo, el inicio). «Ponla en 100.5» = valor.\n"
    "Para cambiar algo usa proponer_cambio: el usuario lo aplica con el botón de la tarjeta (tú no puedes). "
    "Después de proponer, di en una o dos frases qué cambia y si hay advertencias.\n"
    "Choques, cruces o conflictos entre tuberías: buscar_conflictos (ya usa las normativas de la app) y luego "
    "proponer_solucion con el id de cada conflicto (K1, K2…), empezando por los choques. El plugin calcula cuánto "
    "subir o bajar cada utilidad y prueba que no cree otros conflictos: tú no calculas cotas. Si una propuesta dice "
    "que también resuelve otros conflictos, no propongas para ésos. Por cada propuesta di en una frase qué utilidad "
    "se mueve, cuánto y por qué, y que hay otras opciones. Si el usuario prefiere otra («mejor baja la de agua», "
    "«la opción 2»), proponer_solucion con 'mover', 'accion' u 'opcion'.\n"
    "Normativas («¿cumple la normativa?», «revisa el diseño»): revisar_normativas y resume los avisos por tipo, "
    "con las tuberías más graves. Para arreglar pendientes: proponer_pendiente con la utilidad, red o tubería "
    "(sin 'pendiente_pct' usa la de la normativa; ponla solo si el usuario la dice). Para cambiar diámetro o "
    "material: proponer_tamano con 'diametro_in' y/o 'material' tal como los dice el usuario. Para un perfil "
    "longitudinal: crear_perfil con 'desde' y, si lo dice, 'hasta'. Una utilidad de la app se nombra «AGUA-20».\n"
    "Buzones: revisar_buzones (tuberías bajo el fondo, coronas sobre la tapa) y proponer_buzon (tapa, fondo o "
    "altura). Válvulas: proponer_valvula (poner en una tubería a presión, o quitar con su id A#). «Aquí no va codo/Tee»: "
    "buscar_accesorios y proponer_quitar_accesorio. Dos utilidades que se tocan a distinta cota: "
    "proponer_conexion_vertical. Choques con buzones, sólidos o bancoductos: buscar_choques_3d. Esquivar de lado: "
    "proponer_mover_planta. Metrados: metrados. Excel o Word: exportar_cuadro (di la ruta del archivo). Qué se "
    "cambió a mano en Civil 3D: comparar_con_app y, si el usuario quiere conservarlo, traer_a_la_app.\n"
    "Revisión del plano («revisa el plano», «qué hay que corregir en la lámina»): revisar_plano y muestra la lista "
    "numerada (Q1, Q2…) con qué es y dónde, como un revisor; el usuario elige cuáles arreglar y para cada uno "
    "proponer_arreglo_revision con su Q#. Textos y rótulos: proponer_texto («quita ALONG BW» = reemplazar con "
    "'por' vacío; mover, altura, máscara). Cotas: buscar_cotas y proponer_cota (crear o corregir estilo, decimales, "
    "flecha, altura, texto). Contra el PDF original: comparar_con_pdf.\n"
    "«Cotas» de tuberías o buzones son ELEVACIONES (solera o rasante de inicio y fin, tapa, fondo): buscar_tuberias, "
    "buscar_estructuras o detalle_elemento; contra el proyecto de la app (el PDF): comparar_con_app, que compara las "
    "rasantes. El PDF no trae elevaciones: comparar_con_pdf solo mira la planta. buscar_cotas es solo para las "
    "acotaciones (líneas de medida) del plano.\n"
    "Nunca digas que comparaste, revisaste o contaste algo si no llamaste la herramienta en ESTA pregunta: el dibujo "
    "pudo cambiar; vuelve a consultarlo.\n"
    "Si una herramienta da un error, explícalo con palabras simples o elige otra forma de buscarlo.\n"
    "Nunca muestres al usuario handles, nombres de herramientas, argumentos ni JSON.\n"
)


@dataclass
class Resultado:
    texto: str
    propuestas: list = field(default_factory=list)      # dicts de proponer_cambio (id, antes, despues…)
    llamadas: list = field(default_factory=list)        # [(herramienta, ok)]
    sin_conexion: bool = False                          # Civil 3D no tiene la IA encendida


def herramientas_ollama(tools_mcp):
    """Catálogo MCP → formato `tools` de Ollama, sin las que solo decide el usuario o usa la app, ni los argumentos
    que pone la app (`reglas`, `objetivos`)."""
    from ia.civil3d_locales import OCULTOS, SOLO_APP
    out = []
    for h in tools_mcp:
        if h.get("name") in SOLO_USUARIO or h.get("name") in SOLO_APP:
            continue
        esquema = dict(h.get("inputSchema") or {"type": "object", "properties": {}})
        props = esquema.get("properties") or {}
        if OCULTOS & set(props):
            esquema["properties"] = {k: v for k, v in props.items() if k not in OCULTOS}
        out.append({"type": "function",
                    "function": {"name": h["name"], "description": h.get("description", ""), "parameters": esquema}})
    return out


class Agente:
    def __init__(self, cliente, pedir_modelo, max_pasos=MAX_PASOS, reglas=None, normas_cat=None, proyecto=None,
                 sistema=None, cerrar=False):
        """`reglas()` = separaciones de la normativa de la app; `normas_cat()` = su catálogo de normativas;
        `proyecto()` = (pipes, pies por px) del proyecto abierto en la app, o None; `sistema` = otras instrucciones
        (el agente del chat del proyecto); `cerrar` = al agotar los pasos, responder sin herramientas."""
        from ia.civil3d_locales import Locales
        self.cliente = cliente
        self.pedir_modelo = pedir_modelo
        self.max_pasos = max_pasos
        self.historial = []
        self.app = Locales(cliente, normas_cat=normas_cat, reglas=reglas, proyecto=proyecto)
        catalogo = cliente.herramientas()
        self._tools = herramientas_ollama(catalogo) + self.app.herramientas(catalogo)
        self._base = sistema if sistema is not None else SISTEMA
        self.cerrar = cerrar                            # al agotar los pasos, responder sin herramientas

    @property
    def _sistema(self):
        """Se arma en cada paso: `cliente.instrucciones` puede traer el plan que la propia IA se escribió."""
        extra = getattr(self.cliente, "instrucciones", "")
        return self._base + ("\n" + extra if extra else "")

    def preguntar(self, texto, cancelado=None, al_paso=None, al_llamada=None) -> Resultado:
        """`al_paso(nombre)` antes de cada herramienta (la ventana muestra «Consultando Civil 3D: …»);
        `al_llamada(nombre, args)` igual, con sus argumentos."""
        self.app.nuevo_turno()
        msgs = [{"role": "system", "content": self._sistema}] + self.historial[-2 * MAX_HISTORIAL:]
        msgs.append({"role": "user", "content": texto})
        res = Resultado(texto="")
        insistio = False
        for _ in range(self.max_pasos):
            if cancelado and cancelado():
                res.texto = t("Detenido.")
                break
            msgs[0]["content"] = self._sistema
            m = self.pedir_modelo(ajustar(msgs, self._tools), self._tools)
            llamadas = m.get("tool_calls") or []
            msgs.append({"role": "assistant", "content": m.get("content") or "", "tool_calls": llamadas})
            if not llamadas:
                if not res.llamadas and not insistio and pide_datos(texto):
                    # Respondió un pedido de datos SIN consultar el dibujo (reporte 2026-11-06: «Comparé…» con
                    # «Sin consultar el dibujo»): una vez más, pidiéndole que consulte.
                    insistio = True
                    msgs.append({"role": "user", "content": RECORDATORIO + " " + texto})
                    continue
                res.texto = _PENSAR.sub("", m.get("content") or "").strip()
                break
            for c in llamadas:
                f = c.get("function") or {}
                nombre, args = f.get("name", ""), _args(f.get("arguments"))
                if nombre in SOLO_USUARIO:
                    ok, salida = False, t("Solo el usuario puede confirmar o cancelar un cambio (botón en la app).")
                else:
                    if al_paso:
                        al_paso(nombre)
                    if al_llamada:
                        al_llamada(nombre, args)
                    ok, salida = self.app.llamar(nombre, args)
                res.llamadas.append((nombre, ok))
                if not ok and "PDFCAD_IA" in salida:
                    res.sin_conexion = True
                if ok and nombre in PROPONEN:
                    try:
                        res.propuestas.append(json.loads(salida))
                    except ValueError:
                        pass
                respuesta = {"role": "tool", "tool_name": nombre, "content": _recortar(salida)}
                if getattr(salida, "imagenes", None):
                    for x in msgs:                     # solo la última: cada imagen ocupa mucho contexto
                        x.pop("images", None)
                    respuesta["images"] = list(salida.imagenes)
                msgs.append(respuesta)
            if res.sin_conexion:
                res.texto = salida
                break
        else:
            if self.cerrar and not (cancelado and cancelado()):
                m = self.pedir_modelo(msgs + [{"role": "user", "content": CIERRE}], [])
                res.texto = _PENSAR.sub("", m.get("content") or "").strip()
            res.texto = res.texto or t("No terminé en {n} pasos: pregunta algo más concreto.").format(n=self.max_pasos)
        self.historial += [{"role": "user", "content": texto}, {"role": "assistant", "content": res.texto}]
        return res

    # Lo deciden los botones de la ventana, nunca el modelo.
    def confirmar(self, id_cambio):
        return self.cliente.llamar("confirmar_cambio", {"id": id_cambio})

    def cancelar(self, id_cambio):
        return self.cliente.llamar("cancelar_cambio", {"id": id_cambio})


_PIDE_DATOS = re.compile(r"\b(compar|revis|cu[aá]nt|busc|list|dame|d[aá]me|mu[eé]str|resum|cota|verific|chequ|"
                         r"hay\b|qu[eé] (tuber|buz|red|accesor|conflict)|d[oó]nde|cu[aá]l)", re.I)


def pide_datos(texto):
    """¿La pregunta pide datos del dibujo? (si la IA responde sin consultar nada, se le insiste una vez)."""
    return bool(_PIDE_DATOS.search(texto or ""))


IMAGEN_TOKENS = 1300                     # lo que ocupa una captura que ve el modelo (no su base64)


def tokens(obj):
    """Tokens aproximados de lo que se envía (por lo alto). Las imágenes (`images`, del agente del chat) no cuentan por
    su base64 sino por `IMAGEN_TOKENS` cada una."""
    if isinstance(obj, list) and any(isinstance(m, dict) and m.get("images") for m in obj):
        sin = [{k: v for k, v in m.items() if k != "images"} if isinstance(m, dict) else m for m in obj]
        n = sum(len(m.get("images") or ()) for m in obj if isinstance(m, dict))
        return len(json.dumps(sin, ensure_ascii=False)) / CARS_POR_TOKEN + n * IMAGEN_TOKENS
    return len(json.dumps(obj, ensure_ascii=False)) / CARS_POR_TOKEN


def _resumido(m, largo):
    c = m.get("content") or ""
    if len(c) <= largo:
        return m
    return dict(m, content=c[:largo] + " …" + t("(resultado viejo resumido para que quepa en la memoria del modelo)"))


def ajustar(msgs, tools, limite=CONTEXTO_TOKENS):
    """Una COPIA de `msgs` que cabe en la ventana de contexto (`limite` − respuesta − herramientas). En orden, hasta
    que quepa: 1) se quitan los turnos más viejos del historial; 2) los resultados de herramientas viejos (menos los
    dos últimos) quedan en `RESUMEN_HERRAMIENTA` caracteres; 3) también los dos últimos; 4) todos a
    `RESUMEN_MINIMO`. El sistema y la pregunta actual NUNCA se tocan."""
    cupo = limite - RESERVA_RESPUESTA - tokens(tools)
    out = list(msgs)
    if tokens(out) <= cupo:
        return out
    u = max((k for k, m in enumerate(out) if m.get("role") == "user"), default=0)   # la pregunta actual
    while u > 2 and tokens(out) > cupo:                  # 1) historial: el turno más viejo (pregunta + respuesta)
        del out[1:3]
        u -= 2
    herramientas = [k for k in range(u + 1, len(out)) if out[k].get("role") == "tool"]
    for viejos, largo in ((herramientas[:-2], RESUMEN_HERRAMIENTA), (herramientas, RESUMEN_HERRAMIENTA),
                          (herramientas, RESUMEN_MINIMO)):
        if tokens(out) <= cupo:
            break
        for k in viejos:
            out[k] = _resumido(out[k], largo)
    return out


def _args(a):
    if isinstance(a, dict):
        return a
    try:
        return json.loads(a) if a else {}
    except ValueError:
        return {}


def _recortar(s):
    return s if len(s) <= MAX_RESULTADO else s[:MAX_RESULTADO] + " …(recortado: usar filtros o 'limite')"


def pedir_agente(config):
    """`pedir_modelo` del proveedor configurado: Gemini con sus herramientas, si no Ollama."""
    if getattr(config, "proveedor", "") == "gemini":
        from ia.proveedor_gemini import Gemini
        prov = Gemini(config)
        return lambda mensajes, herramientas: prov.pedir_con_herramientas(mensajes, herramientas)
    return pedir_ollama(config)


def pedir_ollama(config):
    """`pedir_modelo` sobre /api/chat de Ollama con `tools` (sin streaming: hace falta el mensaje entero)."""
    prov = Ollama(config)

    def pedir(mensajes, herramientas):
        cuerpo = {"model": config.modelo, "messages": mensajes, "tools": herramientas, "stream": False,
                  "think": False, "keep_alive": "30m", "options": {"temperature": config.temperatura, "num_ctx": CONTEXTO_TOKENS}}
        with prov._pedir("/api/chat", cuerpo) as r:
            datos = json.loads(r.read().decode("utf-8"))
        if "message" not in datos:
            raise ErrorIA(str(datos.get("error") or datos)[:300])
        return datos["message"]

    return pedir

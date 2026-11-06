"""Agente de Civil 3D con la IA local (PURO): la ENTRADA 1 del MCP.

El modelo (Qwen en Ollama, con *tool calling* nativo) elige qué herramienta del plugin usar; el plugin
calcula y valida; el agente solo pasa mensajes. Reglas (las mismas que con Claude):
  - El modelo NUNCA confirma: `confirmar_cambio`/`cancelar_cambio` no se le ofrecen; cada `proponer_cambio`
    vuelve en `Resultado.propuestas` y la VENTANA las confirma con `Agente.confirmar(id)` (botón del usuario).
  - Tope de pasos por pregunta (`MAX_PASOS`) y de texto por resultado (`MAX_RESULTADO`): menos tokens.
  - El historial guarda solo preguntas y respuestas (no el tráfico de herramientas).
`pedir_modelo(mensajes, herramientas)` → {"content", "tool_calls"}: `pedir_ollama(config)` o uno falso en pruebas.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from ia.proveedor import CONTEXTO_TOKENS, ErrorIA, Ollama
from traduccion.i18n_core import t

MAX_PASOS = 8
MAX_RESULTADO = 6000                     # caracteres de cada resultado que ve el modelo
MAX_HISTORIAL = 10                       # turnos (pregunta + respuesta) que se reenvían
SOLO_USUARIO = {"confirmar_cambio", "cancelar_cambio"}
_PENSAR = re.compile(r"<think>.*?</think>\s*", re.S)

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
    """Catálogo MCP → formato `tools` de Ollama, sin las que solo decide el usuario."""
    return [{"type": "function",
             "function": {"name": h["name"], "description": h.get("description", ""),
                          "parameters": h.get("inputSchema") or {"type": "object", "properties": {}}}}
            for h in tools_mcp if h.get("name") not in SOLO_USUARIO]


class Agente:
    def __init__(self, cliente, pedir_modelo, max_pasos=MAX_PASOS, sistema=None, cerrar=False):
        self.cliente = cliente
        self.pedir_modelo = pedir_modelo
        self.max_pasos = max_pasos
        self.historial = []
        self._tools = herramientas_ollama(cliente.herramientas())
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
        msgs = [{"role": "system", "content": self._sistema}] + self.historial[-2 * MAX_HISTORIAL:]
        msgs.append({"role": "user", "content": texto})
        res = Resultado(texto="")
        for _ in range(self.max_pasos):
            if cancelado and cancelado():
                res.texto = t("Detenido.")
                break
            msgs[0]["content"] = self._sistema
            m = self.pedir_modelo(msgs, self._tools)
            llamadas = m.get("tool_calls") or []
            msgs.append({"role": "assistant", "content": m.get("content") or "", "tool_calls": llamadas})
            if not llamadas:
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
                    ok, salida = self.cliente.llamar(nombre, args)
                res.llamadas.append((nombre, ok))
                if not ok and "PDFCAD_IA" in salida:
                    res.sin_conexion = True
                if ok and nombre == "proponer_cambio":
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


def _args(a):
    if isinstance(a, dict):
        return a
    try:
        return json.loads(a) if a else {}
    except ValueError:
        return {}


def _recortar(s):
    return s if len(s) <= MAX_RESULTADO else s[:MAX_RESULTADO] + " …(recortado: usar filtros o 'limite')"


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

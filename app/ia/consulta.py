"""«Pregúntale al proyecto» (PURO): una pregunta en lenguaje natural → respuesta con los datos REALES.

    pregunta ─┬─ contexto.seleccionar  (resumen + conflictos/avisos/utilidades que vienen al caso)
              ├─ memoria.buscar        (lo que el equipo ya le enseñó en este proyecto)
              └─ proveedor.chat        (Ollama hoy, Claude después) ──→ Resultado
                                                                       ├─ referencias [C-12] [AGUA-5] → al plano
                                                                       └─ cifras que no salen de los datos → aviso

Cada pregunta queda en `conversaciones.jsonl`; «Útil», «No útil» y «Corregir» van a `ensenanzas.jsonl` y la
próxima vez entran en el pedido (así «aprende» sin reentrenar el modelo).
"""
from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field

from ia import memoria as M
from ia.texto import no_respaldados, numeros
from traduccion.i18n_core import get_lang, t

VERSION_PROMPT = 1
HISTORIAL = 4                      # pares pregunta/respuesta anteriores que van en el pedido
ENSENANZAS_MAX = 6
_REF = re.compile(r"\[?\b([A-Za-z]+-\d+)\b\]?")

SISTEMA = """Eres el asistente técnico de PDF-a-CAD, una app de ingeniería de redes de utilidades (agua, \
alcantarillado, drenaje, gas, eléctrico y telecomunicaciones). Respondes preguntas sobre UN proyecto usando los \
DATOS DEL PROYECTO que vienen en el mensaje.
Reglas:
1. Usa SOLO esos datos y las enseñanzas del equipo. No inventes normas, valores, distancias ni utilidades.
2. Cada número que escribas debe estar en los datos. Si te piden algo que no está, dilo y sugiere dónde verlo en la \
app (Tabla de datos, Normativas, Vista 3D).
3. Nombra cada elemento con su código entre corchetes, por ejemplo [C-12], [N-3] o [AGUA-5]: así el usuario va \
a él en el plano.
4. Responde en {idioma}, breve y directo (pocas líneas o una lista corta). Unidades: pies (ft) y pulgadas (in).
5. Si una enseñanza del equipo contradice tu respuesta, manda la enseñanza. Si el mensaje NO trae la sección de enseñanzas del equipo, no menciones ninguna: no hay."""


@dataclass
class Resultado:
    id: str
    pregunta: str
    texto: str
    referencias: list = field(default_factory=list)       # códigos citados que existen en el proyecto
    sin_respaldo: list = field(default_factory=list)      # cifras que no salen de los datos enviados
    segundos: float = 0.0
    modelo: str = ""
    usadas: int = 0                                       # enseñanzas que fueron en el pedido


def idioma():
    return "English" if get_lang() == "en" else "español"


def _ensenanza(reg):
    tipo = reg.get("tipo")
    if tipo == M.NOTA:
        return "- " + t("Nota del equipo: {t}").format(t=reg.get("texto", ""))
    if tipo == M.SOLUCION:
        return "- " + t("Solución aplicada antes: {t}").format(t=reg.get("texto", ""))
    if tipo == M.CORRECCION:
        return "- " + t("Ante «{p}», la respuesta correcta es: {t}").format(p=reg.get("pregunta", ""),
                                                                           t=reg.get("texto", ""))
    return "- " + t("Ante «{p}», esta respuesta fue útil: {t}").format(p=reg.get("pregunta", ""),
                                                                       t=(reg.get("respuesta") or "")[:400])


def armar_pedido(pregunta, datos, memoria=None):
    """(texto del pedido, enseñanzas usadas). Separado de `preguntar` para medirlo y probarlo sin IA."""
    fichas, utils = datos.seleccionar(pregunta)
    partes = []
    ens = memoria.buscar(pregunta, k=ENSENANZAS_MAX) if memoria is not None else []
    if ens:
        partes += ["## " + t("Enseñanzas del equipo para este proyecto"), *(_ensenanza(r) for r in ens), ""]
    partes += ["## " + t("Datos del proyecto"), "### " + t("Resumen"), datos.resumen, ""]
    if fichas:
        partes += ["### " + t("Conflictos y avisos que vienen al caso ({n} de {total})").format(
            n=len(fichas), total=len(datos.lineas_fichas)), *(ln.texto for ln in fichas), ""]
    if utils:
        partes += ["### " + t("Utilidades que vienen al caso ({n} de {total})").format(
            n=len(utils), total=len(datos.utilidades)), *(ln.texto for ln in utils), ""]
    partes += ["## " + t("Pregunta"), pregunta.strip()]
    return "\n".join(partes), len(ens)


def preguntar(proveedor, pregunta, datos, memoria=None, historial=(), al_texto=None, cancelado=None):
    """Responde `pregunta`. `historial` = [(pregunta, respuesta), …] de esta conversación."""
    pedido, usadas = armar_pedido(pregunta, datos, memoria)
    msgs = []
    for p, r in list(historial)[-HISTORIAL:]:
        msgs += [{"role": "user", "content": p}, {"role": "assistant", "content": r}]
    msgs.append({"role": "user", "content": pedido})
    t0 = time.perf_counter()
    resp = proveedor.chat(msgs, sistema=SISTEMA.format(idioma=idioma()), al_texto=al_texto, cancelado=cancelado)
    texto = resp.texto.strip()
    refs = []
    for m in _REF.finditer(texto):
        c = m.group(1).upper()
        if datos.ref(c) is not None and c not in refs:
            refs.append(c)
    res = Resultado(uuid.uuid4().hex[:12], pregunta.strip(), texto, refs,
                    no_respaldados(texto, numeros(pedido) + [len(datos.utilidades), len(datos.lineas_fichas)]),
                    time.perf_counter() - t0, resp.modelo, usadas)
    if memoria is not None:
        memoria.agregar(M.CONVERSACIONES, id=res.id, pregunta=res.pregunta, respuesta=res.texto,
                        referencias=res.referencias, modelo=res.modelo, segundos=round(res.segundos, 2),
                        version=VERSION_PROMPT)
    return res


def valorar(memoria, res, util: bool):
    """«Útil» / «No útil»: queda como enseñanza (las útiles vuelven como ejemplo)."""
    return memoria.ensenar(M.VALORACION, "", id=res.id, valor=1 if util else -1, pregunta=res.pregunta,
                           respuesta=res.texto, modelo=res.modelo)


def corregir(memoria, res, correccion: str):
    """«Corregir»: la respuesta buena, en palabras del usuario. Manda sobre lo que diga el modelo."""
    return memoria.ensenar(M.CORRECCION, correccion, id=res.id, pregunta=res.pregunta, respuesta=res.texto,
                           modelo=res.modelo)


def ensenar_nota(memoria, nota: str):
    """«Enseñarle algo»: una regla o dato del proyecto («los cruces con drenaje se resuelven bajando el agua»)."""
    return memoria.ensenar(M.NOTA, nota)

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
import threading
import time
import uuid
from dataclasses import dataclass, field

from ia import alcance as A
from ia import memoria as M
from ia.texto import no_respaldados, numeros
from traduccion.i18n_core import get_lang, t

VERSION_PROMPT = 2                 # 2: reglas de alcance + pregunta delimitada (ia/alcance)
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
5. Si una enseñanza del equipo contradice tu respuesta, manda la enseñanza. Si el mensaje NO trae la sección de enseñanzas del equipo, no menciones ninguna: no hay.""" + A.REGLAS_SISTEMA


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
    fuera: str = ""                                       # «ajeno» / «codigo» / «inyeccion»: no se respondió
    capitulos: list = field(default_factory=list)         # pregunta de AYUDA: [(n.º, título)] del manual
    origen: str = "proyecto"                              # «proyecto» o «manual» (ia/ayuda_chat)
    pasos: list = field(default_factory=list)             # lo que hizo el agente, en palabras
    propuestas: list = field(default_factory=list)        # lo que deja para que decida el usuario


MAX_PASOS_HERRAMIENTAS = 8
SISTEMA_HERRAMIENTAS = """
Eres un agente: decide tú cómo resolver cada pedido. Si necesita varios pasos, empieza con definir_plan: tu objetivo, tus pasos y cómo sabrás que terminaste serán tus instrucciones. Si los DATOS DEL PROYECTO no alcanzan, consulta y mira el plano en vez de pedirle al usuario lo que puedes ver tú. En las capturas la línea investigada va en MAGENTA. Un rótulo vale para una línea solo si su flecha o guía llega a ella o está escrito sobre ella. Si ves un rótulo cerca, acércate y sigue su flecha antes de descartarlo. No repitas una vista: si dos vistas distintas no dan nada, dilo. Si te piden señalar, abrir o mostrar algo, busca la función y úsala. Tú nunca aplicas cambios: los propones y decide el usuario. Nunca nombres las herramientas al usuario."""


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
    textos = datos.textos_para(pregunta) if hasattr(datos, "textos_para") else []
    if textos:
        partes += ["### " + t("Texto del plano que viene al caso ({n} de {total}; TX-n lleva al lugar)").format(
            n=len(textos), total=len(datos.texto)), *textos, ""]
    partes += ["## " + t("Pregunta"), A.envolver(pregunta)]
    return "\n".join(partes), len(ens)


def preguntar(proveedor, pregunta, datos, memoria=None, historial=(), al_texto=None, cancelado=None,
              manual=None, agente=None, cliente=None, al_paso=None):
    """Responde `pregunta`. `historial` = [(pregunta, respuesta), …] de esta conversación. Con `manual` (el
    `ayuda_manual.Indice` del manual de usuario), una pregunta de cómo usar la app se responde con el MANUAL
    (`ia/ayuda_chat`, 2026-10-30) y el resultado trae sus capítulos.

    Lo que no es del proyecto ni de la app (o quiere saltarse las reglas) no llega al modelo: respuesta fija
    (`ia/alcance`). Lo que el modelo responda con código o con su marca de rechazo también se cambia por ella."""
    motivo = A.revisar(pregunta, datos, historial)
    from ia import ayuda_chat
    # Una pregunta de cómo usar la app que el manual responde va al manual aunque sus palabras no estén en el
    # vocabulario del alcance («¿cómo dibujo un centerline?» salía como ajena, 2026-10-30). Inyección y código no.
    if (motivo in (A.OK, A.AJENO) and manual is not None
            and ayuda_chat.es_de_ayuda(pregunta, manual, datos)):
        return _del_manual(proveedor, pregunta, manual, memoria, al_texto, cancelado)
    if motivo != A.OK:
        return _fuera(pregunta, motivo, memoria, al_texto)
    pedido, usadas = armar_pedido(pregunta, datos, memoria)
    if agente is not None and proveedor.herramientas():
        return _con_herramientas(proveedor, pregunta, datos, memoria, historial, pedido, usadas, agente, cancelado,
                                 al_texto, cliente, al_paso)
    msgs = []
    for p, r in list(historial)[-HISTORIAL:]:
        msgs += [{"role": "user", "content": p}, {"role": "assistant", "content": r}]
    msgs.append({"role": "user", "content": pedido})
    t0 = time.perf_counter()
    resp = proveedor.chat(msgs, sistema=SISTEMA.format(idioma=idioma()), al_texto=_vigilado(al_texto),
                          cancelado=cancelado)
    return _resultado(pregunta, resp.texto, resp.modelo, datos, memoria, pedido, usadas, t0, al_texto)


def _con_herramientas(proveedor, pregunta, datos, memoria, historial, pedido, usadas, pedir_modelo, cancelado, al_texto,
                      cliente=None, al_paso=None):
    """La IA consulta el proyecto con herramientas de solo lectura antes de responder. La respuesta se revisa igual
    que la de siempre, sumando a los datos lo que devolvieron las herramientas."""
    from ia import herramientas
    from ia.civil3d_agente import Agente
    cliente = cliente or herramientas.ClienteProyecto(datos)
    ag = Agente(cliente, _cancelable(pedir_modelo, cancelado), max_pasos=MAX_PASOS_HERRAMIENTAS,
                sistema=SISTEMA.format(idioma=idioma()) + SISTEMA_HERRAMIENTAS, cerrar=True)
    pasos = []

    def anotar(nombre, args):
        pasos.append(herramientas.describir(nombre, args))
        if al_paso is not None:
            al_paso(pasos[-1])
    for p, r in list(historial)[-HISTORIAL:]:
        ag.historial += [{"role": "user", "content": p}, {"role": "assistant", "content": r}]
    t0 = time.perf_counter()
    res = ag.preguntar(pedido, cancelado=cancelado, al_llamada=anotar)
    if cancelado is not None and cancelado():          # «Detener»: no se guarda como respuesta
        return Resultado(uuid.uuid4().hex[:12], pregunta.strip(), t("Detenido."), segundos=time.perf_counter() - t0,
                         modelo=proveedor.config.modelo, usadas=usadas, pasos=pasos,
                         propuestas=list(getattr(cliente, "propuestas", ())))
    pedido_total = pedido + "\n" + "\n".join(cliente.salidas) + "\n" + "\n".join(getattr(cliente, "textos", ()))
    r = _resultado(pregunta, res.texto, proveedor.config.modelo, datos, memoria, pedido_total, usadas, t0, al_texto)
    r.pasos, r.propuestas = pasos, list(getattr(cliente, "propuestas", ()))
    return r


def _cancelable(pedir_modelo, cancelado):
    """La llamada al modelo no se puede cortar: se espera en otro hilo para que «Detener» responda al momento."""
    if cancelado is None:
        return pedir_modelo

    def pedir(mensajes, tools):
        caja = {}

        def correr():
            try:
                caja["r"] = pedir_modelo(mensajes, tools)
            except Exception as e:                     # noqa: BLE001 (se relanza en quien pidió)
                caja["e"] = e
        hilo = threading.Thread(target=correr, name="pdfcad-ia-herramientas", daemon=True)
        hilo.start()
        while hilo.is_alive():
            hilo.join(0.1)
            if cancelado():
                return {"content": ""}
        if "e" in caja:
            raise caja["e"]
        return caja["r"]
    return pedir


def _resultado(pregunta, texto, modelo, datos, memoria, pedido, usadas, t0, al_texto):
    texto = texto.strip()
    motivo = A.salida_valida(texto)
    if motivo != A.OK:
        return _fuera(pregunta, motivo, memoria, al_texto, modelo=modelo, segundos=time.perf_counter() - t0)
    refs = []
    for m in _REF.finditer(texto):
        c = m.group(1).upper()
        if datos.ref(c) is not None and c not in refs:
            refs.append(c)
    res = Resultado(uuid.uuid4().hex[:12], pregunta.strip(), texto, refs,
                    no_respaldados(texto, numeros(pedido) + [len(datos.utilidades), len(datos.lineas_fichas)]),
                    time.perf_counter() - t0, modelo, usadas)
    if memoria is not None:
        memoria.agregar(M.CONVERSACIONES, id=res.id, pregunta=res.pregunta, respuesta=res.texto,
                        referencias=res.referencias, modelo=res.modelo, segundos=round(res.segundos, 2),
                        version=VERSION_PROMPT)
    return res


def _del_manual(proveedor, pregunta, manual, memoria, al_texto, cancelado):
    """Pregunta de ayuda: la responde el manual (ia/ayuda_manual, con su caché y sus reglas)."""
    from ia import ayuda_manual as AM
    t0 = time.perf_counter()
    texto, origen, caps = AM.responder(proveedor, manual, pregunta, al_texto=_vigilado(al_texto),
                                       cancelado=cancelado)
    if origen == "memoria" and al_texto is not None:      # guardada: no hubo trozos en vivo
        al_texto(texto)
    texto = (texto or "").strip()
    if A.salida_valida(texto) != A.OK:
        return _fuera(pregunta, A.salida_valida(texto), memoria, al_texto, segundos=time.perf_counter() - t0)
    modelo = "" if origen != "ia" else getattr(getattr(proveedor, "config", None), "modelo", "") or ""
    res = Resultado(uuid.uuid4().hex[:12], pregunta.strip(), texto, [], [], time.perf_counter() - t0, modelo, 0,
                    capitulos=list(caps or []), origen="manual")
    if memoria is not None:
        memoria.agregar(M.CONVERSACIONES, id=res.id, pregunta=res.pregunta, respuesta=res.texto, referencias=[],
                        modelo=res.modelo, segundos=round(res.segundos, 2), version=VERSION_PROMPT,
                        manual=[c for _n, c in res.capitulos])
    return res


def _vigilado(al_texto):
    """Pasa los trozos en vivo hasta que lo escrito trae código o la marca de rechazo: desde ahí no muestra más
    (al terminar, la respuesta entera se cambia por el texto fijo)."""
    if al_texto is None:
        return None
    hecho = []

    def f(trozo):
        hecho.append(trozo)
        if A.salida_valida("".join(hecho)) == A.OK:
            al_texto(trozo)
    return f


def _fuera(pregunta, motivo, memoria, al_texto, modelo="", segundos=0.0):
    texto = A.rechazo(motivo)
    if al_texto is not None:
        al_texto(texto)
    res = Resultado(uuid.uuid4().hex[:12], pregunta.strip(), texto, [], [], segundos, modelo, 0, motivo)
    if memoria is not None:
        memoria.agregar(M.CONVERSACIONES, id=res.id, pregunta=res.pregunta, respuesta=res.texto, referencias=[],
                        modelo=modelo, segundos=round(segundos, 2), version=VERSION_PROMPT, fuera=motivo)
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

"""La IA recomienda una de las soluciones que la APP ya validó y explica por qué (PURO). Pedido del usuario
2026-10-23 (punto 3: «sugerir la solución de cada conflicto»).

La IA no calcula nada: recibe el conflicto (la ficha del informe) y las propuestas con sus números y su resultado
(resuelve o no, qué problemas nuevos crearía) y responde:

    RECOMENDADA: P2
    <por qué, en 2 a 4 frases>

Solo puede recomendar una propuesta VÁLIDA (si nombra otra, se toma la mejor de la app); si su texto trae cifras
que no están en los datos, sale la explicación de la plantilla. Lo que el equipo aplicó antes en el proyecto
(enseñanzas «solucion» y notas) va en el pedido. La respuesta queda guardada en la memoria del proyecto: el mismo
conflicto con las mismas propuestas no vuelve a preguntar.
"""
from __future__ import annotations

import hashlib
import json
import re

from ia import memoria as M
from ia.consulta import idioma
from ia.texto import no_respaldados, numeros
from nucleo.informe_redaccion import consejo, datos_para_ia
from traduccion.i18n_core import t

VERSION_PROMPT = 1
_REC = re.compile(r"^\s*RECOMENDADA\s*:\s*([A-Za-z]*\d*|ninguna|none)\s*$", re.I | re.M)

SISTEMA = """Eres un ingeniero de redes de utilidades que ayuda a resolver un conflicto del dibujo de un proyecto. \
La aplicación ya calculó y probó las soluciones posibles: tú eliges la mejor y explicas por qué, en {idioma}.
Reglas:
1. Solo puedes recomendar una propuesta con "valida": true. Si ninguna es válida, responde «RECOMENDADA: ninguna» y \
explica qué hacer a mano.
2. No escribas números que no estén en los datos. No inventes normas.
3. Criterios: mover la tubería más chica o la de servicio antes que la principal, el menor cambio de cota, y bajar \
antes que subir (cuida el recubrimiento), salvo que las indicaciones del equipo digan otra cosa.
4. Formato exacto: la primera línea «RECOMENDADA: P1» (el id), luego de 2 a 4 frases."""


def _clave(*partes):
    return hashlib.sha1(json.dumps(partes, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def plantilla(ficha, propuestas):
    """(id recomendado o None, texto) sin IA: la mejor propuesta de la app."""
    validas = [p for p in propuestas if p.valida]
    if validas:
        p = validas[0]
        return p.id, t("La app recomienda {id}: {txt} Resuelve el conflicto sin crear otros problemas.").format(
            id=p.id, txt=p.texto)
    if propuestas:
        return None, t("Ninguna propuesta automática resuelve el conflicto sin crear otros problemas.") + " " + \
            t("Qué hacer: {c}").format(c=consejo(ficha) or t("revisa el dibujo y las cotas en ese punto."))
    return None, t("Este conflicto se arregla cambiando el dibujo; la app no tiene una propuesta automática.") + \
        (" " + t("Qué hacer: {c}").format(c=consejo(ficha)) if consejo(ficha) else "")


def clave_de(ficha, propuestas, modelo=""):
    datos = json.loads(datos_para_ia(ficha))
    datos.pop("id", None)                              # el número C-n cambia al renumerar: no es parte del caso
    datos.pop("zona", None)
    return _clave("solucion", modelo, VERSION_PROMPT, idioma(), datos, [p.datos() for p in propuestas])


def recomendar(proveedor, ficha, propuestas, memoria=None, al_texto=None, cancelado=None):
    """(id recomendado o None, texto, origen) con origen = «memoria» | «ia» | «plantilla» (la IA escribió cifras que
    no están en los datos). Con la IA caída lanza `ErrorIA` (quien llama usa `plantilla`)."""
    clave = clave_de(ficha, propuestas, proveedor.config.modelo)
    if memoria is not None:
        guardada = memoria.redaccion(clave)
        if guardada:
            rec, txt = _leer(guardada, propuestas)
            return rec, txt, "memoria"
    lecciones = memoria.buscar(f"{ficha['titulo']} " + " ".join(u["capa"] for u in ficha["utilidades"]), k=5) \
        if memoria is not None else []
    partes = []
    if lecciones:
        partes += [t("Lo que el equipo decidió antes en este proyecto:")] + \
                  ["- " + (r.get("texto") or r.get("respuesta") or "")[:300] for r in lecciones] + [""]
    datos = json.loads(datos_para_ia(ficha))
    datos["sugerencia"] = consejo(ficha)
    partes += [t("Conflicto:"), json.dumps(datos, ensure_ascii=False), "",
               t("Propuestas de la app (ya probadas en una copia del proyecto):")]
    partes += [json.dumps(p.datos(), ensure_ascii=False) for p in propuestas] or [t("(ninguna)")]
    r = proveedor.chat([{"role": "user", "content": "\n".join(partes)}], sistema=SISTEMA.format(idioma=idioma()),
                       al_texto=al_texto, cancelado=cancelado)
    rec, txt = _leer(r.texto, propuestas)
    fuentes = numeros(json.dumps(datos)) + [v for p in propuestas for v in numeros(json.dumps(p.datos()))]
    if not txt or no_respaldados(txt, fuentes):
        return (*plantilla(ficha, propuestas), "plantilla")
    if memoria is not None:
        memoria.guardar_redaccion(clave, f"RECOMENDADA: {rec or 'ninguna'}\n{txt}", proveedor.config.modelo)
    return rec, txt, "ia"


def _leer(texto, propuestas):
    """(id válido o None, explicación) de la respuesta «RECOMENDADA: Pn\\n…»."""
    m = _REC.search(texto or "")
    pedido = m.group(1).upper() if m else ""
    txt = _REC.sub("", texto or "", count=1).strip()
    validas = [p.id for p in propuestas if p.valida]
    rec = pedido if pedido in validas else (validas[0] if validas else None)
    return rec, " ".join(txt.replace("[", "").replace("]", "").split())


def aprender(memoria, ficha, prop):
    """El equipo aplicó `prop`: queda como enseñanza («en cruces de agua con drenaje se bajó el agua»)."""
    if memoria is None:
        return None
    capas = " × ".join(sorted({u["capa"] for u in ficha["utilidades"]}))
    return memoria.ensenar(M.SOLUCION, t("En «{tit}» ({c}) se aplicó: {txt}").format(
        tit=ficha["titulo"], c=capas, txt=prop.texto), accion=prop.accion)

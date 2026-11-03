"""La IA del diámetro SEÑALA de qué habla (PURO; pedido del usuario 2026-11-03: «me indica la línea magenta, pero en el
plano no está de esa manera… que actúe como un agente: que me diga “a esta línea me estoy refiriendo”»).

Es un agente ACOTADO, con la regla de siempre: la app lee y mide, la IA solo elige ids. Aquí se resuelve qué ids se
marcan en el plano (`marcas`), los códigos del texto pasan a enlaces (`enlazar`), se quitan del texto los colores de la
imagen que recibe el modelo y que el usuario no ve (`sin_colores`) y, cuando el usuario pregunta qué línea es cuál, la
respuesta la da la geometría, sin el modelo (`respuesta_directa`): así no puede equivocarse de ramal.
"""
from __future__ import annotations

import re
from dataclasses import replace

from traduccion.i18n_core import t

_COLOR = r"(?:magenta|turquesa|fucsia|fuchsia|turquoise)"
_RX_LINEA_COLOR = re.compile(rf"\b(?:(?:la|una|esta)\s+)?(?:l[ií]nea|tuber[ií]a|tubo)\s+(?:de\s+color\s+|en\s+)?{_COLOR}\b"
                             rf"|\b(?:the|this)\s+{_COLOR}\s+(?:line|pipe)\b", re.I)
_RX_RESTO = re.compile(rf"\s*\b(?:en|de|in)\s+(?:color\s+)?{_COLOR}\b|\s*\b{_COLOR}\b"
                       r"|\s*\b(?:en|de)\s+(?:la\s+imagen|el\s+recorte)\b|\s*\bin\s+the\s+(?:image|crop)\b", re.I)
_RX_ID = re.compile(r"\b([LR]\d+)\b")

_RX_PIDE = re.compile(r"\b(?:cu[aá]l(?:es)?|qu[eé]|d[oó]nde|mu[eé]stra\w*|se[nñ]ala\w*|ind[ií]ca\w*|which|where|show)\b",
                      re.I)
_RX_DE_LINEA = re.compile(r"\b(?:ramal(?:es)?|lateral(?:es)?|principal|colector|vecinas?|l[ií]neas?|tuber[ií]as?|"
                          r"branch|main|line|pipe)\b", re.I)
_RX_NO_DIRECTA = re.compile(r"por\s*qu[eé]|porque|\bwhy\b|di[aá]metro|diameter|\bmide\b|tama[nñ]o|\bsize\b|\d", re.I)
_RX_RAMAL = re.compile(r"\b(?:ramal(?:es)?|lateral(?:es)?|branch)\b", re.I)
_RX_PRINCIPAL = re.compile(r"\b(?:principal|colector|main)\b", re.I)
_RX_VECINAS = re.compile(r"\b(?:vecinas?|conectadas?|neighbou?r\w*)\b", re.I)


def sin_colores(texto: str) -> str:
    """El texto sin los colores ni «la imagen» del recorte: el usuario ve el plano, no esa imagen."""
    def esta(m):
        return t("Esta línea") if m.group(0)[0].isupper() else t("esta línea")
    return " ".join(_RX_RESTO.sub("", _RX_LINEA_COLOR.sub(esta, texto or "")).split())


def vecina(f: dict, ident) -> dict | None:
    return next((v for v in f.get("vecinas") or [] if v["id"] == ident), None)


def rotulo(f: dict, ident) -> dict | None:
    return next((e for e in f.get("rotulos") or [] if e["id"] == ident), None)


def validas(ids, f: dict) -> list:
    """Los ids que existen en la ficha (L…, R…), sin repetir: lo demás que diga el modelo no se marca."""
    out = []
    for x in ids if isinstance(ids, (list, tuple)) else ():
        x = str(x).strip().upper()
        if x not in out and (vecina(f, x) or rotulo(f, x)):
            out.append(x)
    return out


def ids_de_lineas(f: dict, lineas) -> list:
    return [v["id"] for v in f.get("vecinas") or [] if v["linea"] in (lineas or ())]


def marcas(s, f: dict) -> list:
    """Los ids a marcar en el plano para la sugerencia `s`: lo que señaló, su rótulo, las líneas de su continuidad y
    lo que nombra en el texto."""
    ids = list(getattr(s, "senaladas", None) or [])
    if s.rotulo:
        ids.append(s.rotulo)
    ids += ids_de_lineas(f, (s.analisis.get("opcion") or {}).get("lineas"))
    ids += _RX_ID.findall(f"{s.motivo} {s.pista}")
    return validas(ids, f)


def rol_txt(rol: str) -> str:
    return {"principal": t("principal"), "ramal": t("ramal"), "sigue": t("sigue de frente"),
            "toca": t("se toca")}.get(rol, "")


def _estado(v: dict) -> str:
    if v.get("diam_in"):
        return t('{d}" confirmados').format(d=f'{float(v["diam_in"]):g}')
    return t("sin diámetro confirmado")


def _lista(vs) -> str:
    return ", ".join(f'{v["id"]} ({_estado(v)})' for v in vs)


def enlazar(texto_html: str, f: dict, color: str = "") -> str:
    """Los ids y nombres de líneas del texto (ya escapado) como enlaces `ia:ID`: un clic lleva a ese lugar del plano."""
    nombres = {v["nombre"]: v["id"] for v in f.get("vecinas") or [] if v.get("nombre")}
    claves = sorted(nombres, key=len, reverse=True)
    rx = re.compile(r"\b(" + "|".join([re.escape(n) for n in claves] + [r"[LR]\d+"]) + r")\b")
    estilo = f" style='color:{color}'" if color else ""

    def enlace(m):
        ident = nombres.get(m.group(1), m.group(1))
        v = vecina(f, ident)
        if v is None and rotulo(f, ident) is None:
            return m.group(0)
        return f"<a href='ia:{ident}'{estilo}>{v['nombre'] if v else ident}</a>"
    return rx.sub(enlace, texto_html)


def es_pregunta_de_lineas(mensaje: str) -> bool:
    m = mensaje or ""
    return bool(_RX_PIDE.search(m) and _RX_DE_LINEA.search(m)) and not _RX_NO_DIRECTA.search(m)


def pide_vecinas(mensaje: str) -> bool:
    return bool(_RX_VECINAS.search(mensaje or ""))


def _texto_directo(f: dict, mensaje: str):
    vs = f.get("vecinas") or []
    prin = [v for v in vs if v["rol"] == "principal"]
    ram = [v for v in vs if v["rol"] == "ramal"]
    if not vs:
        return t("No encontré líneas de esta utilidad conectadas a esta."), []
    if _RX_RAMAL.search(mensaje):
        if prin:
            return t("Esta línea es el ramal: llega a {p}.").format(p=_lista(prin)), prin
        if ram:
            return t("Los ramales que llegan a esta línea son: {r}.").format(r=_lista(ram)), ram
        return t("Aquí no hay ningún ramal. Las líneas conectadas son: {l}.").format(l=_lista(vs)), vs
    if _RX_PRINCIPAL.search(mensaje):
        if prin:
            return t("La principal es {p}.").format(p=_lista(prin)), prin
        if ram:
            return t("Esta línea es la principal: a ella llega {r}.").format(r=_lista(ram)), ram
        return t("La geometría no me dice cuál es la principal. Las líneas conectadas son: {l}.").format(l=_lista(vs)), vs
    return t("Las líneas conectadas a esta son: {l}.").format(
        l=", ".join(f'{v["id"]} ({rol_txt(v["rol"])}, {_estado(v)})' for v in vs)), vs


def respuesta_directa(f: dict, mensaje: str, anterior):
    """«¿Cuál es el ramal?»: lo contesta la app con la geometría, sin el modelo. None si no es esa clase de pregunta.
    La propuesta que había sigue igual."""
    from ia.diametro_ia import Sugerencia
    if "vecinas" not in f or not es_pregunta_de_lineas(mensaje):
        return None
    texto, lineas = _texto_directo(f, mensaje)
    ids = [v["id"] for v in lineas]
    if ids:
        texto += " " + t("Te las señalé en el plano.")
    if anterior is None:
        return Sugerencia(None, None, "alta", texto, "", "descartada", senaladas=ids)
    return replace(anterior, motivo=texto, pista="", senaladas=ids)

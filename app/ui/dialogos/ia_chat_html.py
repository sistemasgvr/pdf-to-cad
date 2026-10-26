"""La conversación de «Pregúntale al proyecto» en HTML (lo que muestra el QTextBrowser del chat).

Sin estado: recibe los turnos y los colores del tema y devuelve el HTML. Burbujas distintas para «Tú» (derecha,
color suave del tema) y la IA (izquierda, con su icono), hora y modelo discretos, códigos (C-12, AGUA-5) como
«fichas» que llevan al plano, aviso de cifras en una tarjeta ámbar y las acciones como iconos (su texto va en el
globo de ayuda: `TIPS`). Los iconos se piden como `ico:<nombre>` (los da `ia_chat.VistaChat.loadResource`).
"""
from __future__ import annotations

import html
import re

from traduccion.i18n import t as _tr
from traduccion.i18n_core import N_

_COD = re.compile(r"\[?\b([A-Z][A-Z0-9]*-\d+)\b\]?")
_NEGRITA = re.compile(r"\*\*(.+?)\*\*")
ICONOS = {"util": "mdi:thumb-up-outline", "noutil": "mdi:thumb-down-outline", "corr": "mdi:pencil-outline",
          "copiar": "mdi:content-copy", "repetir": "mdi:refresh", "ia": "mdi:robot-outline",
          "aviso": "mdi:alert-outline"}
# Texto del globo de cada acción (por el esquema del enlace).
TIPS = {"util": N_("Útil: la IA lo tendrá en cuenta"), "noutil": N_("No útil: la IA no volverá a usarla"),
        "corr": N_("Corregir la respuesta…"), "copiar": N_("Copiar la respuesta"),
        "repetir": N_("Volver a preguntar"), "ref": N_("Ver en el plano"), "preg": N_("Preguntar esto"),
        "config": N_("Configurar IA…")}
PUNTOS = ("●○○", "○●○", "○○●")
ERROR_OSCURO = "#ff9b94"


def contraste(a, b):
    """Relación de contraste WCAG entre dos colores «#rrggbb»."""
    def lum(h):
        c = [int(h.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    x, y = sorted((lum(a), lum(b)), reverse=True)
    return (x + 0.05) / (y + 0.05)


def colores_aviso(oscuro):
    """(fondo, texto) de la tarjeta ámbar: contraste ≥ 4.5:1 en los dos temas."""
    return ("#4a3a12", "#ffd98a") if oscuro else ("#fff4d6", "#6b4500")


def formato(texto, existe, tk):
    """Texto de la IA → HTML: negritas y cada código que existe en el proyecto como ficha enlazada."""
    s = _NEGRITA.sub(r"<b>\1</b>", html.escape(texto))

    def enlazar(m):
        c = m.group(1)
        if not existe(c):
            return m.group(0)
        return (f"<a href='ref:{c}' style='color:{tk.soft_text}; background-color:{tk.soft}; "
                f"text-decoration:none'>&nbsp;{c}&nbsp;</a>")
    return _COD.sub(enlazar, s).replace("\n", "<br>")


def siguientes(res):
    """Preguntas para seguir, a partir de lo que nombró la respuesta (máx. 2)."""
    out = []
    for c in (res.referencias or [])[:2]:
        out.append(_tr("¿Por qué ocurre {c} y cómo se resuelve?").format(c=c) if c.startswith("C-")
                   else _tr("Más detalle sobre {c}").format(c=c))
    return out


def _burbuja_tu(tu, tk):
    return (f"<table width='100%' cellspacing='0' cellpadding='0' style='margin-top:14px'><tr>"
            f"<td width='18%'></td><td bgcolor='{tk.soft}' style='padding:10px 12px; color:{tk.soft_text}'>"
            f"<span style='font-size:small'>{html.escape(_tr('Tú'))} · {html.escape(tu.get('hora', ''))}"
            f"</span><br>{html.escape(tu['pregunta']).replace(chr(10), '<br>')}</td></tr></table>")


def _acciones(i, tu, tk):
    if tu["corregido"]:
        hecho = _tr("Corregida: la IA lo tendrá en cuenta")
    elif tu["valor"]:
        hecho = _tr("Marcada como útil") if tu["valor"] > 0 else _tr("Marcada como no útil")
    else:
        hecho = ""
    claves = ("copiar", "repetir") if hecho else ("util", "noutil", "corr", "copiar", "repetir")
    iconos = "&nbsp;&nbsp;".join(f"<a href='{k}:{i}'><img src='ico:{k}' width='18' height='18'></a>"
                                 for k in claves)
    if hecho:
        iconos = f"<span style='color:{tk.text}'>✔ {html.escape(hecho)}</span>&nbsp;&nbsp;" + iconos
    return iconos


def _burbuja_ia(i, tu, tk, existe, ahora, ultimo):
    oscuro = tk.name == "dark"
    partes = []
    if tu["estado"] == "error":
        rojo = ERROR_OSCURO if oscuro else tk.danger      # el «danger» del tema oscuro no llega a 4.5:1
        cuerpo = f"<span style='color:{rojo}'>{tu['error']}</span>"
    elif tu["texto"]:
        cuerpo = formato(tu["texto"], existe, tk)
    else:
        seg = max(0, int(ahora - tu.get("t0", ahora)))
        cuerpo = (f"<span style='color:{tk.text_muted}'>{PUNTOS[seg % 3]}&nbsp; "
                  + html.escape(_tr("Pensando… {s} s").format(s=seg)) + "</span>")
    res = tu["res"]
    cab = _tr("IA")
    if res is not None:
        cab += " · " + _tr("{m} · {s} s").format(m=res.modelo, s=f"{res.segundos:.1f}")
    elif tu["estado"] == "escribiendo" and tu["texto"]:
        cab += " · " + _tr("escribiendo…")
    partes.append(f"<span style='font-size:small; color:{tk.text_muted}'>{html.escape(cab)}</span><br>{cuerpo}")
    if res is not None and res.sin_respaldo:
        fondo, letra = colores_aviso(oscuro)
        cifras = ", ".join(f"{v:g}" for v in res.sin_respaldo)
        partes.append(f"<table width='100%' cellspacing='0' cellpadding='6' style='margin-top:8px'><tr>"
                      f"<td bgcolor='{fondo}' style='color:{letra}'><img src='ico:aviso' width='16' height='16'>"
                      "&nbsp;" + html.escape(_tr("Revisa estas cifras: no salen de los datos del proyecto: {c}")
                                             .format(c=cifras)) + "</td></tr></table>")
    if res is not None:
        fuente = _tr("Según los datos del proyecto")
        if res.usadas:
            fuente += " · " + _tr("usó {n} enseñanzas").format(n=res.usadas)
        partes.append(f"<p style='margin-top:8px; font-size:small; color:{tk.text_muted}'>"
                      f"{html.escape(fuente)}<br>{_acciones(i, tu, tk)}</p>")
        if ultimo and tu.get("siguientes"):
            fichas = " ".join(f"<a href='preg:{k}' style='color:{tk.text_info}'>{html.escape(q)}</a>"
                              for k, q in enumerate(tu["siguientes"]))
            partes.append(f"<p style='font-size:small'>{fichas}</p>")
    return (f"<table width='100%' cellspacing='0' cellpadding='0' style='margin-top:10px'><tr>"
            f"<td width='30' valign='top' style='padding-top:4px'><img src='ico:ia' width='20' height='20'></td>"
            f"<td bgcolor='{tk.surface_alt}' style='padding:10px 12px; color:{tk.text}'>{''.join(partes)}</td>"
            f"<td width='8%'></td></tr></table>")


def conversacion(turnos, tk, existe, ahora):
    """HTML completo de la conversación."""
    partes = [f"<div style='color:{tk.text}'>"]
    if not turnos:                                       # estado vacío: centrado, con el icono de la IA
        partes.append(
            "<table width='100%' height='100%' cellspacing='0' cellpadding='0'><tr><td align='center' "
            "valign='middle' style='padding:40px 24px'><img src='ico:ia' width='44' height='44'><br><br>"
            f"<span style='font-size:large; font-weight:600; color:{tk.text}'>"
            + html.escape(_tr("¿En qué te ayudo?")) + "</span><br><br>"
            f"<span style='color:{tk.text_muted}'>" + html.escape(_tr(
                "Pregunta lo que quieras sobre este proyecto: conflictos, normativas, utilidades, zonas. La IA "
                "responde solo con los datos del proyecto y cada código (C-12, AGUA-5) lleva al plano.")) +
            "</span></td></tr></table>")
    ultimo = max((i for i, x in enumerate(turnos) if "nota" not in x), default=-1)
    for i, tu in enumerate(turnos):
        if "nota" in tu:
            partes.append(f"<p style='margin-top:12px; color:{tk.text_muted}'>✎ " + html.escape(
                _tr("Anotado para este proyecto: {n}").format(n=tu["nota"])) + "</p>")
            continue
        partes.append(_burbuja_tu(tu, tk))
        partes.append(_burbuja_ia(i, tu, tk, existe, ahora, i == ultimo))
    partes.append("</div>")
    return "".join(partes).replace("<a href='config:", f"<a style='color:{tk.text_info}' href='config:")

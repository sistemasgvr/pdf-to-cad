"""Tarjetas del Copiloto en el chat (HTML para el `QTextBrowser`: las acciones son enlaces `cop:`)."""
from __future__ import annotations

import html

from traduccion.i18n import t as _tr

MAX_FILAS = 30                                         # filas visibles en una tarjeta; las demás, «y N más»
MAX_CAPTURAS = 30
CAPTURAS = {}                                          # id → PNG de las capturas que el agente adjunta a sus propuestas


def guardar_captura(png):
    while len(CAPTURAS) >= MAX_CAPTURAS:
        CAPTURAS.pop(next(iter(CAPTURAS)))
    clave = f"c{id(png)}"
    CAPTURAS[clave] = png
    return clave


def _enlace(href, texto, tk):
    return f"<a href='{href}' style='color:{tk.text_info}'>{html.escape(texto)}</a>"


def _boton(href, texto, tk, principal=False):
    if principal:
        return (f"<td bgcolor='{tk.accent}'><a href='{href}' style='color:{tk.text_on_accent}; text-decoration:none; "
                f"font-weight:600'>&nbsp;{html.escape(texto)}&nbsp;</a></td>")
    return (f"<td bgcolor='{tk.surface}' style='border:1px solid {tk.border}'><a href='{href}' style='color:{tk.text}; "
            f"text-decoration:none'>&nbsp;{html.escape(texto)}&nbsp;</a></td>")


def _botones(celdas):
    return ("<table cellspacing='0' cellpadding='7' style='margin-top:6px'><tr>" + "<td width='8'></td>".join(celdas)
            + "</tr></table>")


def _resultado(cop, tk):
    color = tk.text if cop.get("estado") == "hecho" else tk.text_muted
    return f"<p style='margin-top:8px; color:{color}'>{html.escape(cop.get('resultado') or '')}</p>"


def _casilla(href, marcada):
    return f"<a href='{href}'><img src='ico:{'marcado' if marcada else 'vacio'}' width='18' height='18'></a>"


def _pie_bitacora(tk):
    return "<p style='margin-top:6px; font-size:small'>" + _enlace("cop:bitacora", _tr("Ver la bitácora"), tk) + "</p>"


def _notas(e, tk):
    out = []
    if "conflictos_ocultos" in e.notas:
        out.append(html.escape(_tr("«Mostrar cruces/conflictos» está apagado: no puedo saber cuántos conflictos hay."))
                   + " " + _enlace("cop:ver_conflictos", _tr("Encenderlo"), tk))
    if "sin_escala" in e.notas:
        out.append(html.escape(_tr("La hoja no tiene escala: sin ella no puedo revisar los avisos.")))
    return "".join(f"<p style='margin-top:4px'>{x}</p>" for x in out)


def _estado(_i, tu, tk):
    e = tu["cop"]["estado"]
    if e.listo:
        return "<b>" + html.escape(_tr("Todo listo para exportar: no queda nada pendiente.")) + "</b>" + _pie_bitacora(tk)
    filas = []
    for g in e.grupos:
        if not g.pendientes:
            continue
        href = "cop:conflictos" if g.clave == "conflictos" else f"cop:revisar:{g.clave}"
        filas.append(f"<li>{_enlace(href, _tr(g.titulo), tk)}: " + html.escape(
            _tr("{n} pendiente(s)").format(n=g.pendientes)) + "</li>")
    lista = ""
    if filas:
        lista = ("<b>" + html.escape(_tr("Esto falta para exportar:")) + f"</b><ul style='margin-top:4px'>{''.join(filas)}</ul>"
                 f"<span style='color:{tk.text_muted}; font-size:small'>"
                 + html.escape(_tr("Toca un grupo para empezar a revisarlo.")) + "</span>")
    return lista + _notas(e, tk) + _pie_bitacora(tk)


def _espera(_i, tu, tk):
    return f"<span style='color:{tk.text_muted}'>{html.escape(tu['cop']['texto'])}</span>"


def _seguro(i, tu, tk):
    cop = tu["cop"]
    items = cop["items"]
    partes = ["<b>" + html.escape(_tr("Estos {n} datos los mide la app:").format(n=len(items))) + "</b>"]
    filas = []
    for k, x in enumerate(items[:MAX_FILAS]):
        valor = f'{x.valor:g}"' if isinstance(x.valor, float) else str(x.valor)
        casilla = _casilla(f"cop:marca:{i}:{k}", k in cop["marcados"]) if cop["estado"] == "confirmar" else ""
        filas.append(f"<tr><td valign='top'>{casilla}</td><td>{_enlace(f'cop:ir:{i}:{k}', x.etiqueta, tk)} → "
                     f"<b>{html.escape(valor)}</b><br><span style='color:{tk.text_muted}; font-size:small'>"
                     f"{html.escape(x.motivo)}</span></td></tr>")
    partes.append(f"<table cellspacing='0' cellpadding='3' style='margin-top:6px'>{''.join(filas)}</table>")
    if len(items) > MAX_FILAS:
        resto = set(range(MAX_FILAS, len(items)))
        casilla = _casilla(f"cop:marca:{i}:resto", resto <= cop["marcados"]) if cop["estado"] == "confirmar" else ""
        partes.append(f"<p style='color:{tk.text_muted}'>{casilla} " + html.escape(_tr("y {n} más").format(n=len(resto)))
                      + "</p>")
    if cop["estado"] == "confirmar":
        partes.append(_botones([_boton(f"cop:aplicar:{i}", _tr("Aplicar las marcadas ({n})").format(
            n=len(cop["marcados"])), tk, True), _boton(f"cop:no:{i}", _tr("Ahora no"), tk)]))
    else:
        partes.append(_resultado(cop, tk))
    return "".join(partes)


def _linea(i, tu, tk):
    cop = tu["cop"]
    x, s = cop["item"], cop["sug"]
    if s is None and cop["estado"] == "pensando":
        return f"<b>{html.escape(x.etiqueta)}</b>: <span style='color:{tk.text_muted}'>" + html.escape(
            _tr("Revisando esta línea…")) + "</span>"
    if s is None:
        return f"<b>{html.escape(x.etiqueta)}</b>: " + html.escape(cop["resultado"])
    partes = [f"<b>{html.escape(x.etiqueta)}</b>: " + html.escape(_tr("te propongo {d}").format(d=f'{s.diam_in:g}"')),
              f"<br><span style='color:{tk.text_muted}'>{html.escape(s.motivo or '')}</span>"]
    if cop.get("captura"):
        origen = _tr("Leído en el texto del plano") if cop.get("leido") else _tr("Solo lectura visual: revísalo en la captura")
        partes.append(f"<p style='margin-top:6px'><img src='cap:{cop['captura']}' width='300'><br>"
                      f"<span style='font-size:small; color:{tk.text_muted}'>{html.escape(origen)}</span></p>")
    if cop["estado"] == "confirmar":
        partes.append(_botones([_boton(f"cop:aprobar:{i}", _tr("Aprobar"), tk, True),
                                _boton(f"cop:otro:{i}", _tr("Otro valor"), tk), _boton(f"cop:saltar:{i}", _tr("Saltar"), tk),
                                _boton(f"cop:pausa:{i}", _tr("Pausar"), tk)]))
        if cop["falta"]:
            partes.append(f"<p style='color:{tk.text_muted}; font-size:small'>" + html.escape(
                _tr("Quedan {n} línea(s) por revisar.").format(n=cop["falta"])) + "</p>")
    else:
        partes.append(_resultado(cop, tk))
    return "".join(partes)


def _grupos(i, tu, tk):
    filas = []
    for k, g in enumerate(tu["cop"]["grupos"]):
        x = g["items"][0]
        n = len(g["items"])
        titulo = html.escape(x.aviso.mensaje) + (" " + html.escape(_tr("({n} casos)").format(n=n)) if n > 1 else "")
        if g["hecho"]:
            filas.append(f"<li style='color:{tk.text_muted}'>{titulo}: " + html.escape(_tr("aprobado")) + "</li>")
        else:
            filas.append(f"<li>{titulo}<br>{_enlace(f'cop:grupo:{i}:{k}', _tr('Aprobar con nota'), tk)} &nbsp; "
                         f"{_enlace(f'cop:abrir:{i}:{k}', _tr('Ver el primero'), tk)}</li>")
    fin = f"<p style='color:{tk.text_muted}'>{html.escape(tu['cop']['resultado'])}</p>" if tu["cop"].get("resultado") else ""
    return ("<b>" + html.escape(_tr("Esto lo decides tú:")) + f"</b><ul style='margin-top:4px'>{''.join(filas[:MAX_FILAS])}</ul>"
            + fin)


def _funcion(i, tu, tk):
    cop = tu["cop"]
    texto = html.escape(_tr("¿Uso «{f}»?").format(f=cop["texto"]))
    if cop["estado"] == "confirmar":
        return texto + _botones([_boton(f"cop:funsi:{i}", _tr("Sí, úsala"), tk, True), _boton(f"cop:funno:{i}", _tr("No"), tk)])
    return _resultado(cop, tk)


def _fin(i, tu, tk):
    n = tu["cop"]["saltados"]
    texto = html.escape(_tr("Terminé la revisión."))
    if n:
        texto += " " + html.escape(_tr("Dejaste {n} para después:").format(n=n)) + " " + _enlace(
            "cop:ver_saltados", _tr("volver a verlos"), tk)
    if tu["cop"].get("investigar"):
        texto += "<br>" + _enlace(f"cop:investigar:{i}", _tr("Investigar {n} línea(s) sin dato: miro el plano por mi cuenta").format(
            n=len(tu["cop"]["investigar"])), tk)
    return texto


def _conflictos(i, tu, tk):
    cop = tu["cop"]
    filas = cop["filas"]
    con, sin = [(k, f) for k, f in enumerate(filas) if f.prop], [(k, f) for k, f in enumerate(filas) if not f.prop]
    espera = cop["estado"] == "confirmar"
    partes = []
    if con:
        partes.append("<b>" + html.escape(_tr("Probé estas soluciones y quedan limpias:")) + "</b><br>"
                      f"<span style='color:{tk.text_muted}; font-size:small'>" + html.escape(
                          _tr("Cambian cotas de redes existentes: revísalas antes de marcarlas.")) + "</span>")
        lineas = []
        for k, f in con:                               # todas: nada se aplica sin verse
            casilla = _casilla(f"cop:cmarca:{i}:{k}", k in cop["marcados"]) if espera else ""
            lineas.append(f"<tr><td valign='top'>{casilla}</td><td>{_enlace(f'cop:irc:{i}:{k}', f.c.id, tk)}: "
                          f"{html.escape(f.prop.texto)}</td></tr>")
        partes.append(f"<table cellspacing='0' cellpadding='3' style='margin-top:6px'>{''.join(lineas)}</table>")
    if sin:
        partes.append("<p style='margin-top:8px'><b>" + html.escape(_tr("Estos necesitan tu criterio:")) + "</b></p>")
        partes.append("<ul style='margin-top:2px'>" + "".join(
            f"<li>{_enlace(f'cop:abrirc:{f.c.id}', f.c.id, tk)}: {html.escape(f.motivo)}</li>" for _k, f in sin[:MAX_FILAS])
            + "</ul>")
    if not filas:
        partes.append(html.escape(_tr("No hay conflictos.")))
    if con and espera:
        partes.append(_botones([_boton(f"cop:caplicar:{i}", _tr("Aplicar las marcadas ({n})").format(
            n=len(cop["marcados"])), tk, True), _boton(f"cop:climpias:{i}", _tr("Marcar todas las limpias"), tk)]))
    elif not espera:
        partes.append(_resultado(cop, tk))
    return "".join(partes)


def _bitacora(_i, tu, tk):
    cop = tu["cop"]
    if not cop["entradas"]:
        return html.escape(_tr("Todavía no hay nada en la bitácora."))
    filas = []
    for e in cop["entradas"]:
        marca = f" <i>({html.escape(_tr('deshecha'))})</i>" if e.get("deshecha") else ""
        filas.append(f"<li>{html.escape(e['fecha'])} · {html.escape(e['usuario'] or '')}: "
                     f"<b>{html.escape(e['resumen'])}</b>{marca}")
        filas.append("<br><span style='font-size:small; color:" + tk.text_muted + "'>" + html.escape("; ".join(
            f"{d['codigo']}: {d['despues']}" for d in e["detalle"][:5])) + "</span>")
        if e["id"] == cop["ultima"]:
            filas.append("<br>" + _enlace(f"cop:deshacer:{e['id']}", _tr("Deshacer esta tanda"), tk))
        filas.append("</li>")
    return "<b>" + html.escape(_tr("Bitácora del Copiloto")) + f"</b><ul style='margin-top:4px'>{''.join(filas)}</ul>"


TARJETAS = {"bitacora": _bitacora, "estado": _estado, "espera": _espera, "seguro": _seguro, "linea": _linea, "grupos": _grupos, "fin": _fin,
            "conflictos": _conflictos, "funcion": _funcion}


def tarjeta(i, tu, tk):
    return TARJETAS[tu["cop"]["tipo"]](i, tu, tk)

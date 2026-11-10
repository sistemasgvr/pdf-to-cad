"""La conversación del chat «Civil 3D» en HTML (QTextBrowser), con el MISMO aspecto que «Pregúntale al proyecto»
(`ia_chat_html`: burbujas Tú / IA, «Pensando… N s», iconos `ico:`), más la TARJETA DE PROPUESTA de un cambio:
elemento y handle, antes → después, consecuencias, advertencias en ámbar y «Aplicar en Civil 3D» / «Descartar».
Solo el usuario aplica (el modelo nunca confirma). Sin estado: recibe los turnos y los colores del tema.

Enlaces: `aplicar:<turno>.<k>`, `descartar:<turno>.<k>`, `ira:<handle>` (ver en Civil 3D), `preg:<k>`,
`copiar:<turno>`, `repetir:<turno>`, `config:`, `reconectar:`.
"""
from __future__ import annotations

import html

from traduccion.i18n import t as _tr
from traduccion.i18n_core import N_
from ui.dialogos import ia_chat_html as H

TIPS = {"aplicar": N_("Aplicar el cambio en Civil 3D (se deshace con U)"), "descartar": N_("Descartar la propuesta"),
        "ira": N_("Encuadrar en Civil 3D"), "copiar": N_("Copiar la respuesta"), "repetir": N_("Volver a preguntar"),
        "preg": N_("Preguntar esto"), "config": N_("Configurar IA…"), "reconectar": N_("Volver a buscar Civil 3D")}
# Nombre legible de cada herramienta del plugin («Consultando Civil 3D: …»).
PASOS = {"estado": N_("estado del dibujo"), "resumen_modelo": N_("resumen de redes"),
         "buscar_tuberias": N_("buscar tuberías"), "buscar_estructuras": N_("buscar estructuras"),
         "buscar_textos": N_("leer textos"),
         "detalle_elemento": N_("detalle de un elemento"), "ir_a": N_("encuadrar"),
         "proponer_cambio": N_("preparar un cambio"), "historial": N_("historial de cambios"),
         "buscar_conflictos": N_("buscar choques entre tuberías"), "proponer_solucion": N_("preparar una solución"),
         "revisar_normativas": N_("revisar las normativas"), "datos_red": N_("leer las redes"),
         "proponer_pendiente": N_("preparar las pendientes"), "proponer_tamano": N_("preparar el cambio de tamaño"),
         "crear_perfil": N_("preparar el perfil"), "buscar_accesorios": N_("buscar accesorios"),
         "revisar_buzones": N_("revisar los buzones"), "metrados": N_("calcular metrados"),
         "proponer_buzon": N_("preparar el buzón"), "proponer_valvula": N_("preparar la válvula"),
         "proponer_quitar_accesorio": N_("preparar quitar el accesorio"),
         "proponer_conexion_vertical": N_("preparar la conexión vertical"),
         "buscar_choques_3d": N_("buscar choques en 3D"), "proponer_mover_planta": N_("preparar el movimiento en planta"),
         "exportar_cuadro": N_("guardar el cuadro de datos"), "comparar_con_app": N_("comparar con la app"),
         "traer_a_la_app": N_("preparar los cambios para la app"), "revisar_plano": N_("revisar el plano"),
         "buscar_cotas": N_("leer las cotas"), "proponer_arreglo_revision": N_("preparar el arreglo"),
         "proponer_texto": N_("preparar el cambio de texto"), "proponer_cota": N_("preparar la cota"),
         "comparar_con_pdf": N_("comparar con el PDF")}
TIPOS = {"cota_inicio": N_("Rasante de inicio (ft)"), "cota_fin": N_("Rasante de fin (ft)"),
         "capa": N_("Capa"), "descripcion": N_("Descripción"), "desplazar_vertical": N_("Rasantes (ft)"),
         "pendiente": N_("Pendiente"), "tamano": N_("Tamaño"), "perfil": N_("Perfil longitudinal"),
         "buzon": N_("Buzón"), "poner_valvula": N_("Válvula"), "quitar_valvula": N_("Quitar válvula"),
         "quitar_accesorio": N_("Quitar accesorio"), "conexion_vertical": N_("Conexión vertical"),
         "mover_planta": N_("Mover en planta"), "traer_app": N_("Traer a la app"), "texto": N_("Texto"),
         "borrar_anotacion": N_("Borrar"), "cota": N_("Cota")}


def paso(nombre):
    return _tr(PASOS.get(nombre, nombre))


def _boton(href, texto, tk, principal):
    if principal:
        return (f"<td bgcolor='{tk.accent}'><a href='{href}' style='color:{tk.text_on_accent}; "
                f"text-decoration:none; font-weight:600'>&nbsp;{html.escape(texto)}&nbsp;</a></td>")
    return (f"<td bgcolor='{tk.surface}' style='border:1px solid {tk.border}'><a href='{href}' "
            f"style='color:{tk.text}; text-decoration:none'>&nbsp;{html.escape(texto)}&nbsp;</a></td>")


def _propuesta(i, k, p, tk):
    """Tarjeta de un cambio propuesto (dict de proponer_cambio + «estado» y «resultado» que pone la ventana)."""
    oscuro = tk.name == "dark"
    tipo = _tr(TIPOS.get(p.get("tipo", ""), p.get("tipo", "")))
    antes = p.get("antes") or "—"
    elem = html.escape(str(p.get("elemento") or ""))
    en_app = p.get("destino") == "app"
    ver = ("" if en_app or not p.get("handle") else
           f" &nbsp;<a href='ira:{html.escape(str(p.get('handle', '')))}' style='color:{tk.text_info}; font-size:small'>"
           + html.escape(_tr("Ver en Civil 3D")) + "</a>")
    filas = [f"<span style='color:{tk.text_muted}; font-size:small'>" +
             html.escape(_tr("Propuesta para la app") if en_app else _tr("Propuesta de cambio")) +
             f"</span><br><b>{elem}</b>{ver}",
             f"<p style='margin-top:6px; margin-bottom:0'>{html.escape(tipo)}: "
             f"<span style='color:{tk.text_muted}'>{html.escape(str(antes))}</span> &nbsp;→&nbsp; "
             f"<b>{html.escape(str(p.get('despues', '')))}</b></p>"]
    for c in p.get("consecuencias") or []:
        filas.append(f"<p style='margin-top:2px; margin-bottom:0; color:{tk.text_muted}'>· {html.escape(c)}</p>")
    adv = p.get("advertencias") or []
    if adv:
        fondo, letra = H.colores_aviso(oscuro)
        filas.append(f"<table width='100%' cellspacing='0' cellpadding='6' style='margin-top:8px'><tr>"
                     f"<td bgcolor='{fondo}' style='color:{letra}'><img src='ico:aviso' width='16' height='16'>&nbsp;"
                     + "<br>".join(html.escape(a) for a in adv) + "</td></tr></table>")
    estado = p.get("estado", "pendiente")
    if estado == "pendiente":
        filas.append("<table cellspacing='0' cellpadding='7' style='margin-top:10px'><tr>"
                     + _boton(f"aplicar:{i}.{k}", _tr("Aplicar en la app") if en_app else _tr("Aplicar en Civil 3D"), tk, True)
                     + "<td width='8'></td>"
                     + _boton(f"descartar:{i}.{k}", _tr("Descartar"), tk, False) + "</tr></table>")
    elif estado == "aplicando":
        filas.append(f"<p style='margin-top:8px; color:{tk.text_muted}'>" + html.escape(_tr("Aplicando en Civil 3D…"))
                     + "</p>")
    else:
        color = {"aplicado": tk.success, "error": H.ERROR_OSCURO if oscuro else tk.danger}.get(estado, tk.text_muted)
        marca = "✔ " if estado == "aplicado" else ""
        filas.append(f"<p style='margin-top:8px; color:{color}'>{marca}{html.escape(p.get('resultado', ''))}</p>")
    return (f"<table width='100%' cellspacing='0' cellpadding='10' style='margin-top:8px'><tr>"
            f"<td bgcolor='{tk.surface}' style='border:1px solid {tk.border}'>{''.join(filas)}</td></tr></table>")


def _burbuja_ia(i, tu, tk, ahora, ultimo):
    oscuro = tk.name == "dark"
    if tu["estado"] == "error" and tu.get("reporte") is not None:
        from ui.comun import error_html
        cuerpo = error_html.tarjeta(tu["reporte"], tk, f"copiarerror:{i}")
    elif tu["estado"] == "error":
        cuerpo = f"<span style='color:{H.ERROR_OSCURO if oscuro else tk.danger}'>{tu['error']}</span>"
    elif tu["texto"]:
        cuerpo = H.formato(tu["texto"], lambda _c: False, tk)
    else:
        seg = max(0, int(ahora - tu.get("t0", ahora)))
        que = (_tr("Consultando Civil 3D: {p}…").format(p=paso(tu["pasos"][-1])) if tu.get("pasos")
               else _tr("Pensando… {s} s").format(s=seg))
        cuerpo = f"<span style='color:{tk.text_muted}'>{H.PUNTOS[seg % 3]}&nbsp; {html.escape(que)}</span>"
    cab = _tr("App") if tu.get("local") else _tr("IA")
    if tu.get("segundos") is not None:
        cab += " · " + _tr("{m} · {s} s").format(m=tu.get("modelo", ""), s=f"{tu['segundos']:.1f}")
    partes = [f"<span style='font-size:small; color:{tk.text_muted}'>{html.escape(cab)}</span><br>{cuerpo}"]
    for k, p in enumerate(tu.get("propuestas") or []):
        partes.append(_propuesta(i, k, p, tk))
    if tu["estado"] == "listo":
        usados = list(dict.fromkeys(tu.get("pasos") or []))
        fuente = (_tr("Según el dibujo de Civil 3D · consultó: {p}").format(p=", ".join(paso(x) for x in usados))
                  if usados else _tr("Respuesta de la app") if tu.get("local") else _tr("Sin consultar el dibujo"))
        iconos = "&nbsp;&nbsp;".join(f"<a href='{k}:{i}'><img src='ico:{k}' width='18' height='18'></a>"
                                     for k in ("copiar", "repetir"))
        partes.append(f"<p style='margin-top:8px; font-size:small; color:{tk.text_muted}'>"
                      f"{html.escape(fuente)}<br>{iconos}</p>")
    return (f"<table width='100%' cellspacing='0' cellpadding='0' style='margin-top:10px'><tr>"
            f"<td width='30' valign='top' style='padding-top:4px'><img src='ico:ia' width='20' height='20'></td>"
            f"<td bgcolor='{tk.surface_alt}' style='padding:10px 12px; color:{tk.text}'>{''.join(partes)}</td>"
            f"<td width='8%'></td></tr></table>")


def conversacion(turnos, tk, ahora):
    partes = [f"<div style='color:{tk.text}'>"]
    if not turnos:
        partes.append(
            "<table width='100%' cellspacing='0' cellpadding='0'><tr><td align='center' valign='middle' "
            "style='padding:40px 24px'><img src='ico:ia' width='44' height='44'><br><br>"
            f"<span style='font-size:large; font-weight:600; color:{tk.text}'>"
            + html.escape(_tr("Pregúntale al dibujo de Civil 3D")) + "</span><br><br>"
            f"<span style='color:{tk.text_muted}'>" + html.escape(_tr(
                "La IA lee las redes del DWG abierto (tuberías, estructuras, cotas, capas), lo revisa con tus "
                "normativas y puede proponer pendientes, diámetros, materiales, buzones, válvulas, conexiones "
                "verticales, perfiles y la solución de los choques; también saca metrados, guarda un cuadro en Excel o "
                "Word y compara el dibujo con la app. Ningún cambio se aplica sin tu «Aplicar»; cada uno se deshace "
                "con U en Civil 3D."))
            + "</span></td></tr></table>")
    ultimo = len(turnos) - 1
    for i, tu in enumerate(turnos):
        partes.append(H._burbuja_tu(tu, tk))
        partes.append(_burbuja_ia(i, tu, tk, ahora, i == ultimo))
    partes.append("</div>")
    return "".join(partes)

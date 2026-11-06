"""Tarjeta de error para los chats de la IA (QTextBrowser), pedido del usuario 2026-11-06: título claro, qué pasó,
qué hacer, el pedido de enviar una CAPTURA al equipo de desarrollo y los detalles técnicos (`ia/reporte_error`).
HTML que entiende QTextBrowser (tablas, sin CSS moderno); los colores, del tema."""
from __future__ import annotations

import html

from traduccion.i18n import t as _tr


def tarjeta(rep, tk, href_copiar=""):
    """HTML de la tarjeta de `rep` (Reporte). `href_copiar` = enlace del botón «Copiar detalles» (o sin botón)."""
    oscuro = tk.name == "dark"
    rojo = "#ff8a8a" if oscuro else tk.danger
    e = html.escape
    filas = "".join(
        f"<tr><td valign='top' style='color:{tk.text_muted}; padding:1px 10px 1px 0' nowrap>{e(k)}</td>"
        f"<td style='color:{tk.text}; padding:1px 0'>{e(str(v))}</td></tr>" for k, v in rep.detalles)
    copiar = (f"&nbsp;&nbsp;<a href='{href_copiar}' style='color:{tk.accent}'>{e(_tr('Copiar detalles'))}</a>"
              if href_copiar else "")
    registro = (f"<p style='margin-top:6px; font-size:small; color:{tk.text_muted}'>"
                f"{e(_tr('También quedó guardado en el registro: {r}').format(r=rep.registro))}</p>"
                if rep.registro else "")
    return (
        f"<table width='100%' cellspacing='0' cellpadding='0'><tr>"
        f"<td width='4' bgcolor='{rojo}'></td>"
        f"<td style='padding:2px 0 2px 10px'>"
        f"<p style='margin:0; color:{rojo}'><b>{e(rep.titulo)}</b></p>"
        f"<p style='margin-top:4px; color:{tk.text}'>{e(rep.explicacion)}</p>"
        f"<p style='margin-top:4px; color:{tk.text}'><b>{e(_tr('Qué hacer:'))}</b> {e(rep.que_hacer)}</p>"
        f"<table width='100%' cellspacing='0' cellpadding='8' style='margin-top:8px'><tr>"
        f"<td bgcolor='{tk.warning_soft}' style='color:{tk.text}'>"
        f"<b>{e(_tr('Si el problema sigue:'))}</b> "
        f"{e(_tr('toma una captura de este mensaje (con los detalles de abajo) y envíala al equipo de desarrollo.'))}"
        f"{copiar}</td></tr></table>"
        f"<p style='margin-top:8px; margin-bottom:2px; font-size:small; color:{tk.text_muted}'>"
        f"<b>{e(_tr('Detalles para el equipo de desarrollo'))}</b></p>"
        f"<table cellspacing='0' cellpadding='0' style='font-size:small'>{filas}</table>"
        f"{registro}</td></tr></table>")

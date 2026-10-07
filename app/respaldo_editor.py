"""respaldo_editor.py — «Cancelar» en el asistente deja el editor como estaba.

Pedido del usuario (2026-10-07): con lo reconocido ya importado, Herramientas →
«Componer hoja de trabajo…» y Cancelar (en el compositor tras volver de «Capas», en
«Capas de la hoja» o en la vista previa) dejaba la hoja SIN líneas: al aceptar el
compositor la hoja se vuelve a cargar (`Main._apply_composite` → `_load_page` →
`_reset_model`) ANTES de los pasos siguientes.

`tomar(win)` guarda, al abrir el asistente desde un editor con trabajo
(`hay_trabajo`: líneas, estructuras, marcas, georreferencia…), todo lo que éste toca:
el PDF de trabajo ABIERTO (y su temporal), la composición y sus capas, la imagen de
la hoja y la vista, el modelo (utilidades, estructuras, georreferencia…),
deshacer/rehacer y la marca de «cambios sin guardar». `reponer` lo devuelve tal
cual, sin volver a leer el PDF; `soltar` (al importar) cierra el PDF viejo y borra
su temporal. Mientras haya respaldo, `Main._apply_composite` no cierra ese PDF ni
borra su temporal (`lo_guarda`).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from PySide6 import QtCore

import composite as composite_mod

# Lo que cambian el asistente, `_apply_composite` y `_load_page`: la hoja de trabajo…
_HOJA = ("doc", "work_pdf_path", "_tmp_composite", "src_pdfs", "composite",
         "hidden_ocgs_by_source", "hidden_ocgs", "_scale_override", "_composite_layout",
         "page_idx", "_recog_ready", "_recognition_utilities", "_letters_off",
         "_layer_roles_by_utility", "_join_routes",
         "scale", "rot", "W", "H", "derot", "pageH_px", "leader_hpx", "gray")
# …lo que vacía `_reset_model`…
_MODELO = ("cur_pts", "pipes", "leaders", "text_marks", "erase_regions", "_erase_pts",
           "structures", "ref_centerlines", "_cl_pts", "duct_banks", "cross_connections",
           "normas_estado", "georef")
# …y la marca de cambios sin guardar (se repone SIN el setter de `_dirty`: borraría
# la copia automática y tomaría como «guardado» lo que no lo está).
_CAMBIOS = ("_dirty_flag", "_clean_sig", "_forzar_cambios")
CLAVES = _HOJA + _MODELO + _CAMBIOS
# Trabajo que «Cancelar» no debe perder. Sin nada de esto el asistente sigue como
# siempre (cancelar en «Capas» deja cargada la hoja nueva, para dibujar a mano).
_TRABAJO = ("pipes", "structures", "leaders", "text_marks", "erase_regions",
            "ref_centerlines", "duct_banks", "cross_connections")


def hay_trabajo(win) -> bool:
    """¿Hay en el editor algo hecho por el usuario (o importado) que se perdería?"""
    d = win.__dict__
    if any(d.get(k) for k in _TRABAJO):
        return True
    georef = d.get("georef")
    return bool(georef is not None and (georef.points or georef.active()))


@dataclass
class Respaldo:
    valores: dict                      # atributos de la ventana (los de CLAVES que tenía)
    faltan: tuple                      # los de CLAVES que no tenía (se quitan al reponer)
    deshacer: list = field(default_factory=list)
    rehacer: list = field(default_factory=list)
    imagen: object = None              # QPixmap de la hoja (compartido: no copia la imagen)
    vista: tuple | None = None         # (QTransform, nivel de zoom, centro en la escena)


def _copia(valor):
    """Copia de lo que el asistente podría cambiar EN SU LUGAR (los objetos del
    modelo no: `_reset_model` los reemplaza por listas nuevas)."""
    if isinstance(valor, composite_mod.Composite):
        return composite_mod.Composite.from_dict(valor.to_dict())
    if isinstance(valor, dict):
        return {k: (list(v) if isinstance(v, list) else v) for k, v in valor.items()}
    if isinstance(valor, (list, set)):
        return type(valor)(valor)
    return valor


def tomar(win) -> Respaldo:
    """Foto del editor (ventana `Main`) antes de que el asistente lo toque."""
    d = win.__dict__
    canvas = win.canvas
    item = canvas.pixmap_item
    vista = None
    if item is not None:
        centro = canvas.mapToScene(canvas.viewport().rect().center())
        vista = (canvas.transform(), getattr(canvas, "_zoom_level", 1.0), centro)
    return Respaldo(
        valores={k: _copia(d[k]) for k in CLAVES if k in d},
        faltan=tuple(k for k in CLAVES if k not in d),
        deshacer=list(win._undo), rehacer=list(win._redo),
        imagen=item.pixmap() if item is not None else None, vista=vista)


def lo_guarda(r: Respaldo | None, *, doc=None, tmp=None) -> bool:
    """¿Ese PDF abierto / ese temporal es el de la hoja respaldada? (no cerrarlo ni borrarlo)."""
    if r is None:
        return False
    if doc is not None and r.valores.get("doc") is doc:
        return True
    return bool(tmp) and r.valores.get("_tmp_composite") == tmp


def _cerrar(doc, tmp):
    if doc is not None:
        try:
            doc.close()
        except Exception:
            pass
    if tmp and os.path.isfile(tmp):
        try:
            os.remove(tmp)
        except Exception:
            pass


def soltar(win, r: Respaldo | None) -> None:
    """El asistente dejó una hoja nueva en el editor: el PDF y el temporal del
    respaldo se cierran/borran si ya no son los de la ventana."""
    if r is None:
        return
    doc = r.valores.get("doc")
    tmp = r.valores.get("_tmp_composite")
    _cerrar(doc if doc is not win.__dict__.get("doc") else None,
            tmp if tmp != win.__dict__.get("_tmp_composite") else None)


def reponer(win, r: Respaldo) -> None:
    """Devuelve el editor a `r`: cierra la hoja que dejó el asistente (salvo que sea
    la misma) y repone hoja, imagen, vista, modelo, deshacer y cambios sin guardar."""
    d = win.__dict__
    doc, tmp = d.get("doc"), d.get("_tmp_composite")
    _cerrar(doc if doc is not None and not lo_guarda(r, doc=doc) else None,
            tmp if not lo_guarda(r, tmp=tmp) else None)
    win._close_editor()
    d.update(r.valores)
    for k in r.faltan:
        d.pop(k, None)
    win._undo[:] = r.deshacer
    win._redo[:] = r.rehacer
    if r.imagen is not None:
        win.canvas.set_image(r.imagen)
        transform, nivel, centro = r.vista
        win.canvas.setTransform(transform)
        win.canvas._zoom_level = nivel
        win.canvas.centerOn(centro)
    win._overlay = []                       # sus ítems se fueron con la escena
    win.sel_pipe = win.sel_leader = win.sel_region = win.sel_text = win.sel_cl = -1
    win._extending = False
    win.set_mode("idle")
    win._refresh_lists(); win._update_ui(); win._redraw(); win._update_geo_status()
    win._update_page_label(); win._refresh_scale_label()
    win._update_undo_tooltips(); win._update_title()
    # Al vaciar el modelo, el setter de `_dirty` dejó pendiente tomar la «huella de
    # guardado» del contenido (`_take_clean_sig`): si corriera ahora, lo repuesto sin
    # guardar pasaría por guardado. Esto va DESPUÉS en la cola y deja la de antes.
    firma = r.valores.get("_clean_sig")

    def _firma_de_antes():
        if firma is not None:
            win._clean_sig = firma
        elif not win._dirty:
            win._clean_sig = win._content_sig()
        else:
            win._clean_sig = None
    QtCore.QTimer.singleShot(0, _firma_de_antes)

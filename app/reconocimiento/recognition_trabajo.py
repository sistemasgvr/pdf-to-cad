"""recognition_trabajo.py — el reconocimiento de UNA hoja, como trabajo de fondo (PURO).

Lo que hacía `RecognitionWorker.run` (movido tal cual): un documento y una lectura de las
letras del linetype para todas las utilidades, y `recognize_page` por utilidad. Corre en el
proceso trabajador (`ui.comun.proceso`, pedido del usuario 2026-10-14: que reconocer una hoja
compuesta no trabe la ventana ni deje la RAM ocupada) o, sin proceso, en el hilo de siempre.

`progreso(...)` recibe, en orden:
  · ("utilidad", i, n, utilidad)  antes de cada utilidad,
  · ("capa", i, n, utilidad, k, m) al empezar cada capa de esa utilidad,
  · ("trazos", i, n, utilidad, lote) durante la reconstrucción, como vista provisional,
  · ("hecha", i, n, utilidad, trazos) al terminarla: sustituye la vista provisional
    con los puntos (px) de las líneas ya ajustadas de esa utilidad.
"""
from __future__ import annotations

from typing import Callable, Optional
import time


class FlujoTrazos:
    """Lotes acotados de líneas para la vista en vivo: copias, sin referencias al resultado que se sigue
    modificando. Una línea larga se parte compartiendo el extremo: no se pierde ningún tramo."""
    MAX_LINEAS = 64
    MAX_PUNTOS = 4096
    CADA_S = .05

    def __init__(self, publicar):
        self.publicar = publicar
        self.pendientes = []
        self.puntos = 0
        self.ultimo = 0.

    def agregar(self, pts):
        for inicio in range(0, len(pts) - 1, self.MAX_PUNTOS - 1):
            piece = [(float(x), float(y)) for x, y in pts[inicio:inicio + self.MAX_PUNTOS]]
            if self.puntos + len(piece) > self.MAX_PUNTOS:
                self.vaciar()
            self.pendientes.append(piece)
            self.puntos += len(piece)
            if (len(self.pendientes) >= self.MAX_LINEAS or self.puntos >= self.MAX_PUNTOS
                    or time.perf_counter() - self.ultimo >= self.CADA_S):
                self.vaciar()

    def vaciar(self):
        if self.pendientes:
            batch, self.pendientes = self.pendientes, []
            self.puntos = 0
            self.ultimo = time.perf_counter()
            self.publicar(batch)


def _leer_valvulas(page, zoom, hidden, roles_by_utility, results):
    """Complemento: una falla aquí nunca tumba el reconocimiento de las líneas."""
    from reconocimiento import recognition_valvulas as RV
    try:
        valvulas = RV.completar(RV.leer_hoja(page, zoom, hidden or (), roles_by_utility), results, zoom)
        RV.ramales(page, valvulas, results, zoom, hidden or ())
    except Exception:                                  # noqa: BLE001
        return
    for r in results:
        r.valvulas = valvulas
    if results:
        results[0].warnings = list(results[0].warnings) + RV.avisos(valvulas)


def reconocer_hoja(pdf_path, page_index, zoom=1.0, utilities=("ELECTRICO",), hidden_ocgs=(),
                   layer_roles=None, roles_by_utility=None, join_routes=True, scale_ft_per_pt=None,
                   letters_off=(), progreso: Optional[Callable] = None, perfiles_de=()):
    import fitz
    from reconocimiento import recognition as rec
    utilities = rec.normalize_utilities(utilities)
    roles_by_utility = {str(k): dict(v or {}) for k, v in (roles_by_utility or {}).items()}
    layer_roles = dict(layer_roles or {})
    letters_off = set(letters_off or ())
    avisar = progreso or (lambda *a: None)
    results = []
    # un solo documento y UNA lectura de las letras del linetype para todas las
    # utilidades (`recognition.page_letters`, ~0.5–1 s por hoja); y los vectores de la hoja
    # se leen UNA vez para las letras y todas las utilidades (`pdf_styles.lectura_unica`)
    from hoja import pdf_styles
    with fitz.open(pdf_path) as doc, pdf_styles.lectura_unica(doc):
        letters = None
        if any(not (roles_by_utility.get(u) or layer_roles) for u in utilities):
            letters = rec.page_letters(doc[page_index])
        for i, utility in enumerate(utilities):
            avisar("utilidad", i, len(utilities), utility)
            flujo = FlujoTrazos(lambda batch, i=i, u=utility: avisar("trazos", i, len(utilities), u, batch))
            roles = roles_by_utility.get(utility) or layer_roles or None
            mine = letters
            if letters is not None:
                # una capa que el usuario asignó a mano («Ajustar capas…») a OTRA
                # utilidad no se toma aquí por sus letras: manda su elección
                claimed = {name for u, r in roles_by_utility.items() if u != utility
                           for name in [*(r.get(rec.ROLE_LINEAS) or ()), *(r.get(rec.ROLE_BUZONES) or ())]}
                mine = {k: v for k, v in letters.items()
                        if k not in claimed and k not in letters_off}
            res = rec.recognize_page(
                pdf_path, page_index=page_index,
                utility=utility, zoom=zoom, doc=doc,
                hidden_ocgs=list(hidden_ocgs or ()), layer_roles=roles,
                join_routes=join_routes,
                scale_ft_per_pt=scale_ft_per_pt, letters=mine,
                al_trazo=flujo.agregar if progreso is not None else None,
                avance=lambda k, m, i=i, u=utility: avisar("capa", i, len(utilities), u, k, m))
            flujo.vaciar()
            results.append(res)
            avisar("hecha", i, len(utilities), utility,
                   [[(float(x), float(y)) for x, y in pl.pts_pdf] for pl in res.drawable])
        _leer_valvulas(doc[page_index], zoom, hidden_ocgs, roles_by_utility, results)
    # los perfiles de los laterales dicen el diámetro de las tuberías que los cruzan: con TODAS las
    # utilidades (si van en procesos aparte, lo hace `RecognitionWorker` al juntarlas). En una hoja
    # compuesta, los perfiles de sus hojas de origen (`perfiles_de`: [(pdf, hoja)])
    from reconocimiento import recognition_grosor_cruces
    if perfiles_de and results:
        from dataclasses import replace
        from reconocimiento import recognition_grosor_perfiles
        from traduccion.i18n_core import t as _tr
        avisar("detalle", _tr("Perfiles de las hojas de origen"), None, None)
        propios = {pv.nombre for r in results for pv in (r.perfiles or [])}
        escala = results[0].scale_ft_per_pt or 0.0
        extra = [replace(pv, planta_px_por_pie=zoom / escala)
                 for pv in recognition_grosor_perfiles.de_hojas(perfiles_de) if pv.nombre not in propios] if escala else []
        if extra:
            for r in results:
                r.perfiles = list(r.perfiles or []) + extra
    recognition_grosor_cruces.aplicar(results)
    return results

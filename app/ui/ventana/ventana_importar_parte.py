"""Importar UNA parte reconocida ENCIMA de lo dibujado (plan 2026-11-16, «reconocimiento desde el editor», Tarea 4).

Cada ▶ del panel «Reconocer» reconoce una parte de la hoja del editor en el trabajador
(`recognition_trabajo.reconocer_parte`) y su resultado entra aquí:

  · una utilidad → [RecognitionResult]: las líneas entran con `_import_recognized_pipes` (los MISMOS pasos de datos del
    asistente) sin las que ya están dibujadas (`nucleo.reconocer_mas`, la tolerancia de «Reconocer más capas»); su capa
    se enciende en «Capas ▾» y las válvulas del plano que habían quedado sin tubería se pegan a la red nueva.
    `reemplazar=True` quita antes SOLO lo que salió de esa parte (`pipe["reconocida"]`), nunca lo dibujado a mano;
  · "VALVULAS" → {"valvulas", "avisos"}: `_guardar_valvulas` (pegadas a su tubería si ya está);
  · "DIAMETROS" → los resultados con los diámetros de los perfiles: `diam_plano` (y el diámetro, si nadie lo eligió) de
    las tuberías ya importadas de esas utilidades (`pipe["reconocida_idx"]` = su polilínea en `result.drawable`);
  · "ROTULOS" → {"anotaciones"}: `_guardar_anotaciones`.

Un solo paso de deshacer por llamada (el estado de ANTES; ninguno si nada cambió) y sin `respaldo_editor`: lo de antes
no se toca, así que no hay nada que reponer.
"""
from __future__ import annotations

import contextlib
import math
from types import SimpleNamespace

from nucleo import valvulas as V
from traduccion.i18n import t as _tr

VALVULAS, DIAMETROS, ROTULOS = "VALVULAS", "DIAMETROS", "ROTULOS"     # = recognition_trabajo
MISMA_PUNTA_PT = 1.0               # DIAMETROS: una punta de la tubería a ≤ esto (pt) de la de su polilínea


TOL_REPETIDA_FT = 0.5          # una línea nueva a ≤ esto de una del editor (toda ella) ya está dibujada


class ImportarParteMixin:
    def importar_parte(self, parte, resultado, reemplazar: bool = False, firma=None) -> int:
        """Suma al editor lo reconocido de `parte` → cuántas cosas agregó (o actualizó, en DIAMETROS). `firma` = la
        lectura de la hoja de donde salió (`reconocer_parte`): queda en las tuberías nuevas (`reconocida_firma`) y
        DIAMETROS solo toca las de la misma lectura."""
        from nucleo import memo_modelo
        parte = str(parte).strip().upper()
        antes = self._snap_state()
        huella = memo_modelo.firma(self.pipes, self.structures, getattr(self, "valvulas", None),
                                   getattr(self, "anotaciones", None))
        sucio = self._dirty
        with self._sin_pasos_internos():
            if parte == VALVULAS:
                n = self._guardar_valvulas([SimpleNamespace(valvulas=list((resultado or {}).get("valvulas") or []))])
            elif parte == DIAMETROS:
                n = self._aplicar_diametros_parte(resultado, firma)
            elif parte == ROTULOS:
                n = self._guardar_anotaciones(
                    [SimpleNamespace(anotaciones=list((resultado or {}).get("anotaciones") or []))])
            else:
                n = self._importar_utilidad_parte(parte, resultado, reemplazar, firma)
        cambio = memo_modelo.firma(self.pipes, self.structures, getattr(self, "valvulas", None),
                                   getattr(self, "anotaciones", None)) != huella or huella is None
        if not cambio:
            self._dirty_flag = sucio                       # (sin el setter: no toca la copia automática)
            return 0
        self._undo.append(antes); self._redo.clear()
        if len(self._undo) > 400:
            self._undo.pop(0)
        self._dirty = True
        if hasattr(self, "_update_undo_tooltips"):
            self._update_undo_tooltips()
        self._refresh_lists(); self._redraw()
        if hasattr(self, "_sync_boton_capas"):
            self._sync_boton_capas()
        return n

    @contextlib.contextmanager
    def _sin_pasos_internos(self):
        """Los pasos de datos del asistente hacen su propio `_push`: aquí el paso es UNO, el de antes."""
        self._push = lambda *a, **k: None
        try:
            yield
        finally:
            self.__dict__.pop("_push", None)

    def _sin_repetidas(self, pipes):
        """Al importar una parte encima de lo dibujado: quita las líneas nuevas que ya están dibujadas
        (`nucleo.reconocer_mas`; lo llama `_import_recognized_pipes` mientras `_tol_repetidas` está puesto)."""
        tol = getattr(self, "_tol_repetidas", None)
        if not tol:
            return pipes
        from nucleo import reconocer_mas
        quedan, n = reconocer_mas.quitar_repetidas(self.pipes, pipes, tol)
        self._repetidas_quitadas = getattr(self, "_repetidas_quitadas", 0) + n
        return quedan

    # ── una utilidad ─────────────────────────────────────────────────────
    def _importar_utilidad_parte(self, parte, resultado, reemplazar, firma=None):
        results = list(resultado) if isinstance(resultado, (list, tuple)) else [resultado]
        if reemplazar:
            self._quitar_reconocidas(parte)
        n_pipes = len(self.pipes)
        n_sueltas = sum(1 for s in self.structures if s.get("standalone"))
        fpp = self.scale / self.zoom if self.scale and self.zoom else 0.0
        self._tol_repetidas = max(2.0, TOL_REPETIDA_FT / fpp) if fpp else 2.0
        self._repetidas_quitadas = 0
        try:
            self._import_recognized_pipes(results)
        finally:
            self._tol_repetidas = None
        if firma is not None:
            for p in self.pipes[n_pipes:]:
                if p.get("reconocida"):
                    p["reconocida_firma"] = firma
        n = (len(self.pipes) - n_pipes) + max(0, sum(1 for s in self.structures if s.get("standalone")) - n_sueltas)
        utils = [u for u in dict.fromkeys(getattr(x, "utility", None) or parte for x in results) if u]
        if n:
            self._repegar_valvulas(utils)
            self._encender_utilidades(utils)
        if self._repetidas_quitadas:
            self._info(self.lbl_info.text() + " " + _tr(
                "Ya dibujadas en el editor (no se repiten): {n}.").format(n=self._repetidas_quitadas))
        return n

    def _quitar_reconocidas(self, parte):
        """Las tuberías que salieron de esta parte (y sus cajas sueltas); lo dibujado a mano queda. En un proyecto de
        antes del panel, las reconocidas de esa utilidad (`reconocer_estado.de_reconocimiento`)."""
        from nucleo import reconocer_estado as RE
        filas = [i for i, p in enumerate(self.pipes) if RE.de_reconocimiento(p, parte)]
        if filas:
            self._delete_pipes(filas)
        self.structures = [s for s in self.structures
                           if not (s.get("standalone") and s.get("utility") == parte)]
        self._refresh_lists()                      # los buzones de los vértices quitados se van con ellos

    def _encender_utilidades(self, utils):
        """Lo reconocido se ve («Capas ▾»), como en «Reconocer más capas»."""
        apagadas = getattr(self, "capas_apagadas", None)
        if not apagadas:
            return
        quedan = {c for c in apagadas if "/" not in c or c.split("/")[0] not in utils} - set(utils)
        if quedan != apagadas:
            self.capas_apagadas = quedan
            if hasattr(self, "_aplicar_capas"):
                self._aplicar_capas()

    def _repegar_valvulas(self, utils):
        """Válvulas del plano importadas ANTES que su red: quedaron donde estaba el símbolo (`x_pdf`, `y_pdf`); ahora
        que la red está, su ramal y su tubería (`_guardar_valvulas` hace lo mismo con las nuevas)."""
        vs = getattr(self, "valvulas", None) or []
        zoom = float(self.zoom or 1.0)
        sueltas = [k for k, v in enumerate(vs)
                   if (v.get("origen") or V.MANUAL) != V.MANUAL and "x_pdf" in v
                   and (not v.get("utilidad") or v["utilidad"] in utils)
                   and (float(v["x"]), float(v["y"])) == (float(v["x_pdf"]), float(v["y_pdf"]))]   # sin pegar
        if not sueltas:
            return
        self._poner_ramales([vs[k] for k in sueltas], zoom)        # primero todos los ramales…
        cerca = self._cerca_valv_al_dia()                          # …y el índice UNA vez, ya con ellos
        for k in sueltas:
            vs[k] = V.pegar(vs[k], self.pipes, V.tol_pt(vs[k]) * zoom, cerca)

    # ── diámetros ────────────────────────────────────────────────────────
    def _aplicar_diametros_parte(self, resultado, firma=None):
        """Lo que dicen los perfiles, en las tuberías ya importadas de esas utilidades. El diámetro solo si nadie lo
        eligió (ni el usuario ni una lectura anterior del plano); `diam_plano` siempre (es lo que dice el plano)."""
        from nucleo import diametro_plano
        tol = MISMA_PUNTA_PT * float(self.zoom or 1.0)
        por_parte = {}
        for r in resultado or []:
            por_parte[str(getattr(r, "utility", "") or "")] = r.drawable
        n = 0
        for p in self.pipes:
            dib = por_parte.get(p.get("reconocida") or "")
            k = p.get("reconocida_idx")
            if dib is None or not isinstance(k, int) or not 0 <= k < len(dib):
                continue
            if firma is not None and p.get("reconocida_firma") not in (None, firma):
                continue                                # otra lectura de la hoja: su índice no es éste
            pl = dib[k]
            if not _misma_linea(p.get("pts") or (), pl.pts_pdf, tol):
                continue                                # otra hoja / otra lectura, o el usuario la cambió
            cambio = False
            dp = diametro_plano.de_grosor(getattr(pl, "grosor", None))
            if dp and p.get("diam_plano") != dp:
                p["diam_plano"] = dp; cambio = True
            d = getattr(pl, "diam_in", None)
            if d and not (p.get("pipe_size") or "").strip() and not p.get("diam_elegido"):
                p["diam"], p["diam_elegido"] = float(d), True; cambio = True
            n += cambio
        return n


def _misma_linea(pts, pts_pdf, tol):
    """¿Es la tubería de esa polilínea? Alguna de sus puntas sigue donde la dejó el reconocimiento (en cualquier
    sentido): importar le suma vértices (bóvedas, acometidas) y le quita quiebres, pero no le mueve las puntas."""
    if len(pts) < 2 or len(pts_pdf) < 2:
        return False
    a, b = pts[0], pts[-1]
    c, d = pts_pdf[0], pts_pdf[-1]
    return any(math.dist(x[:2], y[:2]) <= tol for x, y in ((a, c), (b, d), (a, d), (b, c)))

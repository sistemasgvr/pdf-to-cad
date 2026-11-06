"""Válvulas de compuerta en agua y gas (pedido del usuario 2026-11-04): herramienta «Válvula» de Dibujar, igual
que el buzón — clic sobre la tubería y la app pone la válvula en un TRAMO RECTO donde cabe (la corre si hace
falta). La lógica es pura (`nucleo/valvulas`); aquí van el modo, la pista verde, el dibujo, el menú del clic
derecho y los cambios (un paso de deshacer cada uno). `Main.valvulas` va al .digproj, al deshacer, al respaldo
del asistente y al DXF (`PDFCAD_VALVULA`)."""
from __future__ import annotations

from PySide6 import QtGui, QtWidgets

from nucleo import model_ops
from nucleo import valvulas as V
from nucleo.model import Z_MARK
from traduccion.i18n import t as _tr
from ui.comun import valvula_item
from ui.comun.ui_common import layer_qcolor


class ValvulasMixin:
    # ── datos ────────────────────────────────────────────────────────────
    def _ft_px_valv(self):
        return self.scale / self.zoom if self.scale and self.zoom else 0.0

    def _cerca_valv(self, x, y, r):
        return self._utilidades_cerca(x, y, r, todas=True)

    def _lugares_valvulas(self):
        """[Lugar] de cada válvula guardada (dónde está y si sigue cabiendo)."""
        ft = self._ft_px_valv()
        vs = getattr(self, "valvulas", None) or []
        if not vs or not ft:
            return [V.Lugar(motivo=_tr("Falta la escala de la hoja.")) for _ in vs]
        return V.ubicar_todas(self.pipes, self.structures, vs, ft, cerca=self._cerca_valv)

    def _valvulas_perfil(self):
        """Las válvulas que caben, como dicts, para el perfil longitudinal (`perfil_datos.armar`)."""
        return [dict(x=l.x, y=l.y, pipe=l.pipe, tramo=l.tramo, diam_in=l.diam_in, union=l.union, bloque=l.bloque,
                     largo_ft=l.largo_ft) for l in self._lugares_valvulas() if l.ok]

    def _firma_perfil(self):
        """Lo que decide el perfil: el modelo y las válvulas (no van en `_firma_modelo`)."""
        vs = getattr(self, "valvulas", None) or []
        return (self._firma_modelo(), tuple((round(float(v["x"]), 4), round(float(v["y"]), 4), v.get("union") or "")
                                            for v in vs))

    def _otras_valvulas(self, salvo=-1):
        return [{"x": l.x, "y": l.y, "largo_ft": l.largo_ft}
                for k, l in enumerate(self._lugares_valvulas()) if l.ok and k != salvo]

    def _valvula_en(self, x, y):
        """El Lugar de una válvula NUEVA con el cursor en (x, y)."""
        r = 14.0 / max(self.canvas.transform().m11(), 1e-6)
        return V.ubicar(self.pipes, self.structures, x, y, self._ft_px_valv(), r,
                        otras=self._otras_valvulas(), cerca=self._cerca_valv)

    # ── herramienta ──────────────────────────────────────────────────────
    def insertar_valvula(self):
        if not hay_lineas_para_valvula(self):
            self._info(motivo_sin_lineas())
            return
        self.set_mode("insert_valv")
        self._info(_tr("Clic sobre una tubería de agua o gas para poner una válvula (Esc para salir)."))

    def _pista_valvula(self, x, y):
        """Al mover el ratón en «Válvula»: el moño verde donde quedará (en un tramo recto) o el motivo."""
        sc = self.canvas.scene()
        for it in getattr(self, "_pista_valv", None) or []:
            try: sc.removeItem(it)
            except (RuntimeError, ValueError): pass
        self._pista_valv = []
        if self.mode != "insert_valv":
            return
        lug = self._valvula_en(x, y)
        if not lug.ok:
            self._info(lug.motivo)
            return
        ft = self._ft_px_valv()
        self._pista_valv = valvula_item.agregar(sc, lug.x, lug.y, lug.ux, lug.uy, lug.largo_ft / ft,
                                                lug.brida_ft / ft, QtGui.QColor(30, 200, 60, 160), True, Z_MARK + 20)
        texto = _tr("Clic para poner una válvula de {d}\" ({b}) sobre {u} (Esc para salir).").format(
            d=f"{lug.diam_in:g}", b=lug.bloque, u=model_ops.nombre_por_defecto(self.pipes[lug.pipe], lug.pipe))
        if lug.movida:
            texto += " " + _tr("Se corre para caber en el tramo recto.")
        self._info(texto)

    def _do_insert_valvula(self, x, y):
        lug = self._valvula_en(x, y)
        if not lug.ok:
            self._info(lug.motivo)
            QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), lug.motivo, self.canvas)
            return
        self._push()
        self.valvulas = list(getattr(self, "valvulas", None) or []) + [V.nueva(lug)]
        self._dirty = True
        self.set_mode("idle")
        self._pista_valvula(x, y)                   # quita el moño verde
        self._info(_tr("Válvula de {d}\" puesta. Clic derecho sobre ella para cambiar la unión o quitarla.").format(
            d=f"{lug.diam_in:g}"))

    # ── dibujo ───────────────────────────────────────────────────────────
    def _draw_valvulas(self):
        vs = getattr(self, "valvulas", None) or []
        self._valv_lugares = []
        if not vs:
            return
        ft = self._ft_px_valv()
        lugares = self._lugares_valvulas()
        self._valv_lugares = lugares
        sc = self.canvas.scene()
        apagadas = getattr(self, "capas_apagadas", None) or ()
        for v, lug in zip(vs, lugares):
            if lug.ok and self.pipes[lug.pipe].get("layer") in apagadas:
                continue
            if lug.ok and ft:
                color = layer_qcolor(self.pipes[lug.pipe].get("layer"))
                globo = globo_valvula(lug)
                its = valvula_item.agregar(sc, lug.x, lug.y, lug.ux, lug.uy, lug.largo_ft / ft, lug.brida_ft / ft,
                                           color, True, Z_MARK + 2, globo)
            else:
                r = 10.0
                its = valvula_item.agregar(sc, float(v["x"]), float(v["y"]), 1.0, 0.0, 2 * r, 1.4 * r,
                                           QtGui.QColor(230, 40, 40), False, Z_MARK + 2,
                                           _tr("Válvula fuera de lugar: {m}").format(m=lug.motivo))
            self._overlay += its

    # ── clic derecho ─────────────────────────────────────────────────────
    def _menu_valvula(self, menu, x, y):
        r = 14.0 / max(self.canvas.transform().m11(), 1e-6)
        k = V.en(getattr(self, "valvulas", None), getattr(self, "_valv_lugares", None), x, y, r)
        if k < 0:
            return False
        v = self.valvulas[k]
        lug = (self._valv_lugares or [None] * (k + 1))[k]
        sub = menu.addMenu(_tr("Válvula"))
        for u, txt in (("FLG", _tr("Unión con bridas (FLG)")), ("RG", _tr("Junta mecánica (RG)"))):
            a = sub.addAction(txt, lambda u=u: self.cambiar_valvula(k, union=u))
            a.setCheckable(True)
            a.setChecked((v.get("union") or "FLG") == u)
            if u == "RG" and lug is not None and lug.ok and lug.diam_in > V.RG_MAX_IN:
                a.setEnabled(False)
        mat = sub.addMenu(_tr("Material"))
        for m in ("",) + V.MATERIALES:
            txt = _tr("El de la tubería") if not m else m
            a = mat.addAction(txt, lambda m=m: self.cambiar_valvula(k, material=m))
            a.setCheckable(True)
            a.setChecked((v.get("material") or "") == m)
        sub.addSeparator()
        sub.addAction(_tr("Quitar la válvula"), lambda: self.quitar_valvula(k))
        menu.addSeparator()
        return True

    def cambiar_valvula(self, k, union=None, material=None):
        vs = list(getattr(self, "valvulas", None) or [])
        if not (0 <= k < len(vs)):
            return False
        v = dict(vs[k])
        if union is not None:
            v["union"] = union if union in V.UNIONES else "FLG"
        if material is not None:
            v["material"] = material if material in V.MATERIALES else ""
        if v == vs[k]:
            return False
        self._push()
        vs[k] = v
        self.valvulas = vs
        self._redraw()
        return True

    def quitar_valvula(self, k):
        vs = list(getattr(self, "valvulas", None) or [])
        if not (0 <= k < len(vs)):
            return False
        self._push()
        del vs[k]
        self.valvulas = vs
        self._redraw()
        self._info(_tr("Válvula quitada (Ctrl+Z para deshacer)."))
        return True


def globo_valvula(lug):
    t = _tr("Válvula de compuerta {d}\" · {b} · {m} · largo {L} ft").format(
        d=f"{lug.diam_in:g}", b=lug.bloque, m=lug.material, L=f"{lug.largo_ft:.2f}")
    return "\n".join([t] + list(lug.avisos))


def motivo_sin_lineas():
    return _tr("Válvula: hace falta una tubería de agua o gas (las válvulas van en redes a presión).")


def hay_lineas_para_valvula(w) -> bool:
    return any(len(p.get("pts") or ()) >= 2 and V.es_presion(p) for p in getattr(w, "pipes", ()) or ())

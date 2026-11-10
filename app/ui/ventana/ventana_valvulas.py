"""Válvulas en la ventana — UN SOLO MODELO (unión con dev_santos_v2, 2026-11-06; `nucleo/valvulas`).

Las pone el usuario (Dibujar → Accesorios → Válvula, 2026-11-04: clic sobre la tubería y la app la pone en un TRAMO
RECTO donde cabe, la corre si hace falta) o las lee el reconocimiento del PDF (2026-11-05, `_guardar_valvulas`: se
pegan a su tubería con `valvulas.pegar`). Aquí van el modo, la pista verde, el dibujo (la pieza real; una reconocida
«por confirmar», hueca; una que no cabe en su tramo recto, roja «por revisar» con el motivo y fuera del DXF), la capa
«VALVULAS» de «Capas ▾», el globo, el menú del clic derecho (tipo, unión, material, confirmar, correr al lugar libre,
quitar) y las filas de la Tabla de datos. Un paso de deshacer por cambio. `Main.valvulas` va al .digproj, al deshacer,
al respaldo del asistente y al DXF (`PDFCAD_VALVULA`).
"""
from __future__ import annotations

import math

from PySide6 import QtGui, QtWidgets

from nucleo import model_ops
from nucleo import valvulas as V
from nucleo.model import Z_MARK
from traduccion.i18n import t as _tr
from ui.comun import valvula_item
from ui.comun.ui_common import layer_qcolor

CLIC_PX = 14.0                     # radio del clic y del globo, en pantalla
def nombre_tipo(tipo):
    """«Válvula de compuerta», o «… · en el plano: Purga» si el plano dice su tipo. Todas se dibujan igual (compuerta, pedido del
    usuario 2026-11-08: una sola válvula genérica); el tipo del plano queda solo como dato."""
    t = (tipo or "").strip()
    if not t or t in ("Válvula", "Compuerta"):
        return _tr("Válvula de compuerta")
    return _tr("Válvula de compuerta · en el plano: {t}").format(t=_tr(t))


class ValvulasMixin:
    # ── datos ────────────────────────────────────────────────────────────
    def _ft_px_valv(self):
        return self.scale / self.zoom if self.scale and self.zoom else 0.0

    def _cerca_valv(self, x, y, r):
        return self._utilidades_cerca(x, y, r, todas=True) if self.pipes else []

    def _lugares_valvulas(self):
        """[Lugar] de cada válvula guardada (dónde está y si sigue cabiendo)."""
        ft = self._ft_px_valv()
        vs = getattr(self, "valvulas", None) or []
        if not vs or not ft:
            return [V.Lugar(motivo=_tr("Falta la escala de la hoja.")) for _ in vs]
        return V.ubicar_todas(self.pipes, self.structures, vs, ft, cerca=self._cerca_valv)

    def _valvulas_perfil(self):
        """Las válvulas que van a Civil 3D, como dicts, para el perfil longitudinal (`perfil_datos.armar`)."""
        vs = getattr(self, "valvulas", None) or []
        return [dict(x=l.x, y=l.y, pipe=l.pipe, tramo=l.tramo, diam_in=l.diam_in, union=l.union, bloque=l.bloque,
                     largo_ft=l.largo_ft, tipo=v.get("tipo") or "")
                for v, l in zip(vs, self._lugares_valvulas()) if V.exportable(v, l)]

    def _firma_perfil(self):
        """Lo que decide el perfil: el modelo y las válvulas (no van en `_firma_modelo`)."""
        vs = getattr(self, "valvulas", None) or []
        return (self._firma_modelo(), tuple((round(float(v["x"]), 4), round(float(v["y"]), 4), v.get("union") or "",
                                             v.get("tipo") or "", v.get("certeza") or "") for v in vs))

    def _otras_valvulas(self, salvo=-1):
        return [{"x": l.x, "y": l.y, "largo_ft": l.largo_ft}
                for k, l in enumerate(self._lugares_valvulas()) if l.ok and k != salvo]

    def _lugar_valvula_nueva(self, x, y, salvo=-1):
        """El Lugar de una válvula NUEVA (o de la `salvo`, al correrla) con el cursor en (x, y)."""
        r = CLIC_PX / max(self.canvas.transform().m11(), 1e-6)
        return V.ubicar(self.pipes, self.structures, x, y, self._ft_px_valv(), r,
                        otras=self._otras_valvulas(salvo), cerca=self._cerca_valv)

    def _valvula_en(self, x, y) -> int:
        """Índice de la válvula bajo el punto (px de la hoja), o −1. Con la capa «VALVULAS» apagada no se elige."""
        vs = getattr(self, "valvulas", None) or []
        if not vs or V.CAPA in (getattr(self, "capas_apagadas", None) or ()):
            return -1
        r = CLIC_PX / max(1e-6, self.canvas.transform().m11())
        return V.en(vs, getattr(self, "_valv_lugares", None), x, y, r)

    def _texto_valvula(self, v, lug=None) -> str:
        """Una línea para el globo y la barra de estado."""
        partes = [nombre_tipo(v.get("tipo"))]
        if lug is not None and lug.ok:
            partes.append(f'{lug.diam_in:g}" {lug.union}')
        if v.get("utilidad"):
            partes.append(self._tipo(v["utilidad"]))
        if v.get("estado"):
            partes.append(_tr(v["estado"]))
        if v.get("certeza") == V.POR_CONFIRMAR:
            partes.append(_tr("por confirmar"))
        if v.get("origen") and v.get("origen") != V.MANUAL:
            partes.append(_tr("del plano"))
        return " · ".join(partes)

    def _filas_valvulas(self):
        """[(válvula, índice de su tubería o None, diámetro o None, rumbo°)] para la Tabla de datos."""
        out = []
        for v, lug in zip(getattr(self, "valvulas", None) or [], self._lugares_valvulas()):
            if lug.ok:
                rumbo = math.degrees(math.atan2(-lug.uy, lug.ux)) % 180.0
                out.append((v, lug.pipe, lug.diam_in, rumbo))
            else:
                out.append((v, None, None, 0.0))
        return out

    # ── reconocimiento ───────────────────────────────────────────────────
    def _guardar_valvulas(self, results) -> int:
        """Al importar: las de la hoja (la misma lista en cada utilidad), pegadas a su tubería, se suman a las del
        proyecto (sin repetir). Devuelve cuántas nuevas."""
        if not getattr(self, "_reconocer_valvulas", True):
            return 0
        nuevas = next((list(r.valvulas) for r in results if getattr(r, "valvulas", None)), [])
        zoom = float(self.zoom or 1.0)
        nuevas = [V.pegar(dict(V.nueva(v["x"], v["y"]), **v), self.pipes, V.tol_pt(v) * zoom, self._cerca_valv)
                  for v in nuevas]
        antes = len(self.valvulas)
        self.valvulas = V.juntar(self.valvulas, nuevas)
        return len(self.valvulas) - antes

    # ── herramienta ──────────────────────────────────────────────────────
    def insertar_valvula(self):
        """Herramienta «Válvula» (Dibujar → Accesorios → Válvula): una sola válvula genérica (compuerta)."""
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
        lug = self._lugar_valvula_nueva(x, y)
        if not lug.ok:
            self._info(lug.motivo)
            return
        ft = self._ft_px_valv()
        self._pista_valv = valvula_item.agregar(sc, lug.x, lug.y, lug.ux, lug.uy, lug.largo_ft / ft,
                                                lug.brida_ft / ft, QtGui.QColor(30, 200, 60, 160), True, Z_MARK + 20)
        texto = _tr("Clic para poner: {v} de {d}\" ({b}) sobre {u} (Esc para salir).").format(
            v=nombre_tipo(""), d=f"{lug.diam_in:g}", b=lug.bloque,
            u=model_ops.nombre_por_defecto(self.pipes[lug.pipe], lug.pipe))
        if lug.movida:
            texto += " " + _tr("Se corre para caber en el tramo recto.")
        self._info(texto)

    def _do_insert_valvula(self, x, y):
        lug = self._lugar_valvula_nueva(x, y)
        if not lug.ok:
            self._info(lug.motivo)
            QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), lug.motivo, self.canvas)
            return
        self._push()
        nueva = V.de_lugar(lug, utilidad=self.pipes[lug.pipe].get("layer") or "")
        self.valvulas = list(getattr(self, "valvulas", None) or []) + [nueva]
        self._dirty = True
        self.set_mode("idle")
        self._pista_valvula(x, y)                   # quita el moño verde
        self._sync_boton_capas()
        self._info(_tr("Válvula de {d}\" puesta. Clic derecho sobre ella para cambiar la unión o quitarla.").format(
            d=f"{lug.diam_in:g}"))

    # ── dibujo ───────────────────────────────────────────────────────────
    def _draw_valvulas(self):
        vs = getattr(self, "valvulas", None) or []
        self._valv_lugares = []
        self._valv_items = []
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
                globo = globo_valvula(lug, v)
                its = valvula_item.agregar(sc, lug.x, lug.y, lug.ux, lug.uy, lug.largo_ft / ft, lug.brida_ft / ft,
                                           color, True, Z_MARK + 2, globo,
                                           hueca=v.get("certeza") == V.POR_CONFIRMAR)
            else:
                r = 10.0
                its = valvula_item.agregar(sc, float(v["x"]), float(v["y"]), 1.0, 0.0, 2 * r, 1.4 * r,
                                           QtGui.QColor(230, 40, 40), False, Z_MARK + 2,
                                           _tr("Válvula por revisar: {m}").format(m=lug.motivo))
            self._overlay += its
            self._valv_items += its
        self._sync_capa_valvulas()

    def _sync_capa_valvulas(self):
        """«Capas ▾» → VALVULAS: encender o apagar sin redibujar."""
        ver = V.CAPA not in (getattr(self, "capas_apagadas", None) or ())
        for it in getattr(self, "_valv_items", None) or []:
            try:
                it.setVisible(ver)
            except RuntimeError:
                pass

    def _elegir_valvula(self, x, y) -> bool:
        """Clic sobre una válvula: se elige en Inventario → Accesorios (como los demás accesorios)."""
        hit = self._accesorio_bajo_clic(x, y) if hasattr(self, "_accesorio_bajo_clic") else None
        if hit is None or hit[0] != "valv" or self._valvula_en(x, y) < 0:
            return False
        return self._elegir_accesorio_en(x, y)

    # ── clic derecho ─────────────────────────────────────────────────────
    def _menu_valvula(self, menu, x, y):
        k = self._valvula_en(x, y)
        if k < 0:
            return False
        v = self.valvulas[k]
        lug = (getattr(self, "_valv_lugares", None) or [None] * (k + 1))[k]
        sub = menu.addMenu(_tr("Válvula"))
        titulo = sub.addAction(self._texto_valvula(v, lug))
        titulo.setEnabled(False)
        sub.addSeparator()
        if v.get("certeza") == V.POR_CONFIRMAR:
            sub.addAction(_tr("Confirmar válvula"), lambda: self.confirmar_valvula(k))
        if lug is not None and not lug.ok:
            sub.addAction(_tr("Correr al lugar libre más cercano"), lambda: self.correr_valvula(k))
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

    def confirmar_valvula(self, k):
        """Una reconocida «por confirmar» pasa a segura (y entonces va a Civil 3D si cabe)."""
        vs = list(getattr(self, "valvulas", None) or [])
        if not (0 <= k < len(vs)) or vs[k].get("certeza") != V.POR_CONFIRMAR:
            return False
        self._push()
        vs[k] = dict(vs[k], certeza=V.SEGURA)
        self.valvulas = vs
        self._redraw()
        return True

    def correr_valvula(self, k):
        """Una «por revisar» (no cabe donde está) al sitio libre más cercano de su tramo recto."""
        vs = list(getattr(self, "valvulas", None) or [])
        if not (0 <= k < len(vs)):
            return False
        lug = self._lugar_valvula_nueva(float(vs[k]["x"]), float(vs[k]["y"]), salvo=k)
        if not lug.ok:
            self._info(lug.motivo)
            QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), lug.motivo, self.canvas)
            return False
        d = math.hypot(lug.x - float(vs[k]["x"]), lug.y - float(vs[k]["y"])) * self._ft_px_valv()
        self._push()
        vs[k] = dict(vs[k], x=float(lug.x), y=float(lug.y))
        self.valvulas = vs
        self._redraw()
        self._info(_tr("Válvula corrida {d} ft al lugar libre de su tramo recto.").format(d=f"{d:.2f}"))
        return True

    def quitar_valvula(self, k):
        vs = list(getattr(self, "valvulas", None) or [])
        if not (0 <= k < len(vs)):
            return False
        self._push()
        del vs[k]
        self.valvulas = vs
        self._redraw()
        self._sync_boton_capas()
        self._info(_tr("Válvula quitada (Ctrl+Z para deshacer)."))
        return True

    # nombres de dev_santos_v2
    def _confirmar_valvula(self, i):
        return self.confirmar_valvula(i)

    def _borrar_valvula(self, i):
        return self.quitar_valvula(i)


def globo_valvula(lug, v=None):
    v = v or {}
    t = _tr("{v} {d}\" · {b} · {m} · largo {L} ft").format(
        v=nombre_tipo(v.get("tipo")), d=f"{lug.diam_in:g}", b=lug.bloque, m=lug.material,
        L=f"{lug.largo_ft:.2f}")
    extra = []
    if v.get("certeza") == V.POR_CONFIRMAR:
        extra.append(_tr("Reconocida del plano, por confirmar: no va a Civil 3D hasta confirmarla (clic derecho)."))
    if v.get("estado"):
        extra.append(_tr("Estado: {e}").format(e=_tr(v["estado"])))
    return "\n".join([t] + extra + list(lug.avisos))


def motivo_sin_lineas():
    return _tr("Válvula: hace falta una tubería de agua o gas (las válvulas van en redes a presión).")


def hay_lineas_para_valvula(w) -> bool:
    return any(len(p.get("pts") or ()) >= 2 and V.es_presion(p) for p in getattr(w, "pipes", ()) or ())


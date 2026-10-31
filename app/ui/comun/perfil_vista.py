"""Dibujo del PERFIL LONGITUDINAL (pedido del usuario 2026-10-31, referencia «PROFILE 8 - 12 INCH MAIN»).

Como la vista de perfil de Civil 3D que arma `CREAR_PERFIL_RED`: marco con rejilla (cotas a los dos lados,
estaciones abajo), fila de tramos arriba («INSTALL … LF OF / NEW 8" … PIPE») con sus verticales de límite,
tubería con sus paredes, estructuras, terreno (EX. GRADE) a trazos, cruces como elipses con su rótulo y el
claro, callouts verticales en los nodos (arriba accesorios/estructuras/puntas, abajo codos y deflexiones) y el
título bajo la vista. Los datos los arma `nucleo/perfil_datos` (puro); aquí solo se dibuja.

Edición: arrastrar el punto de un nodo hacia arriba/abajo cambia su cota (se aplica al soltar: `cotaCambiada`);
con un nodo elegido ↑/↓ = ±0.10 ft (Mayús ±1 ft). Rueda = acercar en el cursor; arrastrar con el botón central o
el derecho = desplazar; doble clic = encuadrar. ← → / Inicio / Fin recorren los nodos.

UX (2026-10-31): `detalle` «basico» deja en cada callout solo la línea que dice QUÉ es (accesorio, buzón, cruce);
`estacionHover` avisa la estación bajo el ratón (la ventana la marca en el plano) y `set_cursor` pinta la que llega
del plano; los callouts de arriba esquivan las verticales de la fila; foco visible.
"""
from __future__ import annotations

import math

from PySide6 import QtCore, QtGui, QtWidgets

from nucleo import perfil_textos as T
from traduccion.i18n import t
from ui.comun.theme import THEME_BUS, tokens

M_IZQ, M_DER, M_ARR, M_ABA = 70, 70, 10, 72      # márgenes del marco (px): cotas, estaciones y título
LETRA_PT = 8
HUECO = 6
RADIO_NODO = 5
ATRAPAR_PX = 9
FILAS_BASICO = 2                                  # filas de etiquetas horizontales en el modo básico


def _filas_etiquetas(items):
    """Cuántas filas (≤ FILAS_BASICO) hacen falta para etiquetas [(x, ancho)] sin encimarse."""
    fines = []
    for x, w in sorted(items):
        izq = x - w / 2
        k = next((i for i, f in enumerate(fines) if izq >= f + HUECO), None)
        if k is None:
            if len(fines) < FILAS_BASICO:
                fines.append(izq + w)
                continue
            k = min(range(len(fines)), key=lambda i: fines[i])
            izq = fines[k] + HUECO
        fines[k] = izq + w
    return len(fines)


def _fila_corta(lineas):
    """«INSTALL 112 LF OF / NEW 8" PVC PIPE / @ 1.61%» → «112 LF · 8" PVC · 1.61%»."""
    import re
    m = re.search(r"(\d+) LF", lineas[0]) if lineas else None
    partes = [m.group(1) + " LF" if m else (lineas[0] if lineas else "")]
    if len(lineas) > 1:
        partes.append(re.sub(r"^NEW |\s*(PIPE|CONDUIT)(\s*\(ABANDONED\))?$", "", lineas[1]).strip()
                      + (" (AB)" if "ABANDONED" in lineas[1] else ""))
    if len(lineas) > 2:
        partes.append(lineas[2].replace("@ ", ""))
    return " · ".join(p for p in partes if p)


class VistaPerfil(QtWidgets.QWidget):
    cotaCambiada = QtCore.Signal(int, float)      # índice de nodo, solera nueva (ft)
    nodoElegido = QtCore.Signal(int)              # -1 = ninguno
    pasoElegido = QtCore.Signal(int)
    estacionHover = QtCore.Signal(float)          # NaN = el ratón salió del dibujo
    nodoHover = QtCore.Signal(int)                # -1 = ninguno
    ramalPedido = QtCore.Signal(int)              # clic en el rótulo de una T/Y/cruz: ver el perfil de su ramal

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setMinimumHeight(160)
        self.p = None
        self.color = QtGui.QColor("#4f6bed")
        self.color_de = lambda j: QtGui.QColor("#888888")
        self.ve = None                            # exageración vertical (None = la del perfil: s / v)
        self._zoom, self._pan = 1.0, None        # pan None = encuadre automático
        self._auto = True                         # el encuadre sigue al tamaño hasta que el usuario mueve la vista
        self._sel_nodo, self._sel_paso, self._hover = -1, -1, -1
        self._arrastre = None                     # (nodo, z) mientras se arrastra
        self._desplazando = None
        self._geo = None
        self.detalle = "auto"                     # «auto» | «completo» | «basico»
        self._basico = False                      # «auto»: básico si los rótulos completos no caben
        self._cursor_e = None                     # estación que llega del plano
        self.aviso_vacio = ""                     # texto del estado vacío (lo pone la ventana)
        self.alertas = []                         # nucleo/perfil_validar.Alerta
        self.con_ramal = set()                    # nodos cuyo rótulo abre el perfil de su ramal (enlace)
        self._zonas = []                          # [(QRectF del rótulo, nodo)] del último dibujo
        self.setAccessibleName(t("Perfil longitudinal"))
        THEME_BUS.changed.connect(self.update)

    # ------------------------------------------------------------------ datos

    def set_perfil(self, perfil, color=None, color_de=None, encuadrar=False):
        self.p = perfil
        if color is not None:
            self.color = QtGui.QColor(color)
        if color_de is not None:
            self.color_de = color_de
        if encuadrar:
            self._zoom, self._pan = 1.0, None; self._auto = True
        if perfil is None or not (0 <= self._sel_nodo < len(perfil.nodos)):
            self._sel_nodo = -1
        self._arrastre = None
        self.update()

    def exageracion(self):
        if self.ve:
            return self.ve
        return (self.p.s / self.p.v) if self.p else 1.0

    def set_exageracion(self, ve):
        self.ve = ve
        self._zoom, self._pan = 1.0, None; self._auto = True
        self.update()

    def encuadrar(self):
        self._zoom, self._pan = 1.0, None; self._auto = True
        self.update()

    def set_detalle(self, detalle):
        self.detalle = detalle
        self._zoom, self._pan = 1.0, None; self._auto = True
        self.update()

    def set_alertas(self, alertas):
        self.alertas = list(alertas or [])
        self.update()

    def alertas_de_nodo(self, k):
        return [a for a in self.alertas if a.nodo == k]

    def alertas_de_paso(self, i):
        return [a for a in self.alertas if a.paso == i and a.nodo < 0 and a.cruce < 0]

    # ---- edición precisa

    def editar_cota_nodo(self, k, z=None):
        """Escribir la solera del nodo `k` (sin `z`: la pregunta)."""
        if not self.p or not (0 <= k < len(self.p.nodos)) or not self.p.nodos[k].editable:
            return False
        if z is None:
            z, ok = QtWidgets.QInputDialog.getDouble(
                self, t("Cota del punto"), t("Solera (invert) en {e}, ft:").format(e=T.estacion(self.p.nodos[k].e)),
                round(self._z_nodo(k), 2), -100000.0, 100000.0, 2)
            if not ok:
                return False
        self.cotaCambiada.emit(k, round(float(z), 2))
        return True

    def fijar_pendiente(self, i, pct=None):
        """Fija la pendiente (%) del paso `i`: se mueve la cota de su FINAL (el nodo i + 1)."""
        p = self.p
        if not p or not (0 <= i < len(p.pasos)) or not p.nodos[i + 1].editable:
            return False
        ps = p.pasos[i]
        if pct is None:
            pct, ok = QtWidgets.QInputDialog.getDouble(
                self, t("Pendiente del tramo"),
                t("Pendiente de {a} a {b}, en % (se mueve la cota del final):").format(
                    a=T.estacion(ps.e0), b=T.estacion(ps.e1)),
                round(ps.pendiente * 100, 2), -100.0, 100.0, 2)
            if not ok:
                return False
        self.cotaCambiada.emit(i + 1, round(ps.z0 + float(pct) / 100.0 * (ps.e1 - ps.e0), 2))
        return True

    def _menu(self, pos, global_pos):
        k = self._nodo_en(pos)
        i = self._paso_en(pos)
        m = QtWidgets.QMenu(self)
        if k >= 0:
            m.addAction(t("Escribir la cota…"), lambda: self.editar_cota_nodo(k))
        if i >= 0 and self.p.nodos[i + 1].editable:
            m.addAction(t("Fijar la pendiente de este tramo…"), lambda: self.fijar_pendiente(i))
        if m.isEmpty():
            return
        m.exec(global_pos)

    def set_cursor(self, e):
        """Estación que señala el ratón en el PLANO (None = ninguna)."""
        if e != self._cursor_e:
            self._cursor_e = e
            self.update()

    def lineas(self, lineas, cruce=False):
        """Lo que se escribe de un callout según el nivel de detalle."""
        basico = self.detalle == "basico" or (self.detalle == "auto" and self._basico)
        if not basico or len(lineas) <= 1:
            return lineas
        if cruce:
            return lineas[:1]
        return [lineas[1]] if len(lineas) > 2 else lineas[:1]

    def elegir_nodo(self, k):
        self._sel_nodo = k
        self.nodoElegido.emit(k)
        self.update()

    # ------------------------------------------------------------------ geometría

    def _fuente(self, negrita=False, pt=LETRA_PT):
        f = QtGui.QFont(self.font())
        f.setPointSizeF(pt)
        f.setBold(negrita)
        return f

    def _basico_ahora(self):
        return self.detalle == "basico" or (self.detalle == "auto" and self._basico)

    def _bloque(self, lineas, fm):
        """(ancho, alto) de un callout VERTICAL (se lee de abajo arriba); en básico, una ETIQUETA horizontal en
        hasta dos filas (`FILAS_BASICO`)."""
        if self._basico_ahora():
            return max((fm.horizontalAdvance(s) for s in lineas), default=0) + 8, FILAS_BASICO * (fm.lineSpacing() + 4)
        largo = max((fm.horizontalAdvance(s) for s in lineas), default=0)
        return len(lineas) * fm.lineSpacing(), largo

    def _calcular(self):
        p = self.p
        fm = QtGui.QFontMetricsF(self._fuente())
        cm, cmen, em, emen = p.intervalos
        pad = max(5.0, (p.e_fin - p.e_ini) * 0.04)
        e_lo = math.floor((p.e_ini - pad) / emen) * emen
        e_hi = math.ceil((p.e_fin + pad) / emen) * emen
        z_lo = math.floor((p.z_min - 1.0) / cmen) * cmen
        z_hi = math.ceil((p.z_max + 1.0) / cmen) * cmen
        filas = max((len(c.lineas) for c in p.celdas), default=0)
        alto_fila = filas * fm.lineSpacing() + 2 * HUECO if filas else 0
        W = max(100.0, self.width() - M_IZQ - M_DER)
        H = max(60.0, self.height() - M_ARR - M_ABA)

        def bandas():
            if self._basico_ahora():                  # etiquetas horizontales: las filas que hacen falta
                kx0 = W / max(e_hi - e_lo, 1e-6)
                alto_et = fm.lineSpacing() + 4
                af = (fm.lineSpacing() + 2 * HUECO) if p.celdas else 0
                filas = []
                for lado in (True, False):
                    items = [(n.e, self.lineas(n.lineas)) for n in p.nodos if n.lineas and n.arriba == lado]
                    items += [(c.e, self.lineas(c.lineas, True)) for c in p.cruces if c.encima == lado]
                    filas.append(_filas_etiquetas([((e - e_lo) * kx0, fm.horizontalAdvance(ls[0]) + 8)
                                                   for e, ls in items]))
                return (af + (filas[0] * alto_et + 2 * HUECO if filas[0] else HUECO),
                        filas[1] * alto_et + 2 * HUECO if filas[1] else HUECO)
            arriba = [self._bloque(self.lineas(n.lineas), fm)[1] for n in p.nodos if n.lineas and n.arriba]
            abajo = [self._bloque(self.lineas(n.lineas), fm)[1] for n in p.nodos if n.lineas and not n.arriba]
            arriba += [self._bloque(self.lineas(c.lineas, True), fm)[1] for c in p.cruces if c.encima]
            abajo += [self._bloque(self.lineas(c.lineas, True), fm)[1] for c in p.cruces if not c.encima]
            return (alto_fila + (max(arriba) + 3 * HUECO if arriba else HUECO),
                    max(abajo) + 3 * HUECO if abajo else HUECO)
        self._basico = False
        basico_fijo = self.detalle == "basico"
        self._basico = basico_fijo
        h_arr, h_aba = bandas()
        if self.detalle == "auto" and h_arr + h_aba > 0.6 * H:   # no caben: rótulos básicos
            self._basico = True
            h_arr, h_aba = bandas()
        if self._basico_ahora():
            alto_fila = (fm.lineSpacing() + 2 * HUECO) if p.celdas else 0
        ve = self.exageracion()
        # llena el ANCHO (como una hoja); si no cabe de alto se desplaza (botón derecho) y arranca centrado en
        # la tubería. Con poco alto, achica hasta la mitad del ancho antes de pasarse.
        kx = W / max(e_hi - e_lo, 1e-6)
        if self.ve is None and h_arr + (z_hi - z_lo) * kx * ve + h_aba > H:
            # «Automática»: la exageración se adapta al alto del panel (nunca menos de ×1)
            ve = max(1.0, (H - h_arr - h_aba) / max((z_hi - z_lo) * kx, 1e-6))
        self._ve_efectiva = ve
        if h_arr + (z_hi - z_lo) * kx * ve + h_aba > H:
            kx = max(kx * 0.25, (H - h_arr - h_aba) / ((z_hi - z_lo) * ve)) if H > h_arr + h_aba else kx * 0.25
        kz = kx * ve
        kxz, kzz = kx * self._zoom, kz * self._zoom
        alto_d = (z_hi - z_lo) * kzz
        alto = h_arr + alto_d + h_aba
        if self._pan is None or self._auto:           # encuadre automático
            dy = 0.0
            if alto > H:                              # la corona más alta a ~60 % del alto: se ven la fila,
                dy = 0.62 * H - (h_arr + (z_hi - p.z_max) * kzz)   # los rótulos de arriba y la tubería
                dy = max(H - alto, min(0.0, dy))
            dx = max(0.0, (W - (e_hi - e_lo) * kxz) / 2)   # más angosto que el panel: centrado
            self._pan = QtCore.QPointF(dx, dy)
        marco = QtCore.QRectF(M_IZQ + self._pan.x(), M_ARR + self._pan.y(), (e_hi - e_lo) * kxz, alto)
        vista = QtCore.QRectF(M_IZQ, M_ARR, W, H)
        self._geo = dict(e_lo=e_lo, e_hi=e_hi, z_lo=z_lo, z_hi=z_hi, kx=kx, kz=kz, marco=marco, vista=vista,
                         base=marco.top() + h_arr + alto_d, alto_fila=alto_fila, fm=fm, h_arr=h_arr)
        return self._geo

    def X(self, e):
        g = self._geo
        return g["marco"].left() + (e - g["e_lo"]) * g["kx"] * self._zoom

    def Z(self, z):
        g = self._geo
        return g["base"] - (z - g["z_lo"]) * g["kz"] * self._zoom

    def z_de(self, y):
        g = self._geo
        return g["z_lo"] + (g["base"] - y) / (g["kz"] * self._zoom)

    def e_de(self, x):
        g = self._geo
        return g["e_lo"] + (x - g["marco"].left()) / (g["kx"] * self._zoom)

    def _z_nodo(self, k):
        """Solera del recorrido en el nodo k (la del arrastre si se está moviendo)."""
        if self._arrastre and self._arrastre[0] == k:
            return self._arrastre[1]
        p = self.p
        if k < len(p.pasos):
            return p.pasos[k].z0
        return p.pasos[k - 1].z1

    def _z_paso(self, i):
        p = self.p
        z0, z1 = p.pasos[i].z0, p.pasos[i].z1
        if self._arrastre:
            k, z = self._arrastre
            if k == i:
                z0 = z
            if k == i + 1:
                z1 = z
        return z0, z1

    # ------------------------------------------------------------------ pintar

    def paintEvent(self, _ev):
        tk = tokens()
        pt = QtGui.QPainter(self)
        pt.setRenderHint(QtGui.QPainter.Antialiasing)
        pt.fillRect(self.rect(), QtGui.QColor(tk.grid_bg))
        if not self.p or not self.p.pasos:
            self._vacio(pt, tk)
            return
        g = self._calcular()
        marco = g["marco"]
        pt.setFont(self._fuente())
        self._rejilla(pt, tk, g)
        pt.save()
        pt.setClipRect(marco.intersected(g["vista"]))
        self._terreno(pt, tk)
        self._tuberia(pt, tk)
        self._cruces(pt, tk)
        self._alertas(pt, tk)
        self._fila(pt, tk, g)
        self._callouts(pt, tk, g)
        self._cursor(pt, tk, g)
        pt.restore()
        pt.save()
        pt.setClipRect(g["vista"].adjusted(-1, -1, 1, 1))
        pt.setPen(QtGui.QPen(QtGui.QColor(tk.text), 1.2))
        pt.setBrush(QtCore.Qt.NoBrush)
        pt.drawRect(marco)
        pt.restore()
        self._titulo(pt, tk, g)
        if self.hasFocus():                           # foco visible (teclado)
            pt.setPen(QtGui.QPen(QtGui.QColor(tk.accent), 2))
            pt.setBrush(QtCore.Qt.NoBrush)
            pt.drawRoundedRect(QtCore.QRectF(self.rect()).adjusted(1, 1, -1, -1), 6, 6)

    def _alertas(self, pt, tk):
        """Tramos con alerta con borde rojo, nodos con anillo rojo y una marca «!» donde va cada una."""
        if not self.alertas:
            return
        rojo = QtGui.QColor(tk.danger)
        ambar = QtGui.QColor(tk.warning)
        hechos = set()
        for a in self.alertas:
            col = rojo if a.nivel == "ERROR" else ambar
            if a.paso >= 0 and a.nodo < 0 and a.cruce < 0 and ("p", a.paso) not in hechos:
                hechos.add(("p", a.paso))
                ps = self.p.pasos[a.paso]
                z0, z1 = self._z_paso(a.paso)
                pen = QtGui.QPen(col, 2.5)
                pt.setPen(pen)
                pt.setBrush(QtCore.Qt.NoBrush)
                pt.drawPolygon(QtGui.QPolygonF([
                    QtCore.QPointF(self.X(ps.e0), self.Z(z0) + 3), QtCore.QPointF(self.X(ps.e1), self.Z(z1) + 3),
                    QtCore.QPointF(self.X(ps.e1), self.Z(z1 + ps.alto_ft) - 3),
                    QtCore.QPointF(self.X(ps.e0), self.Z(z0 + ps.alto_ft) - 3)]))
            if a.nodo >= 0 and ("n", a.nodo) not in hechos:
                hechos.add(("n", a.nodo))
                pt.setPen(QtGui.QPen(col, 2.5))
                pt.setBrush(QtCore.Qt.NoBrush)
                pt.drawEllipse(QtCore.QPointF(self.X(self.p.nodos[a.nodo].e), self.Z(self._z_nodo(a.nodo))),
                               RADIO_NODO + 5, RADIO_NODO + 5)
        # una marca «!» por estación (bajo la tubería), con el número si hay varias
        fm = self._geo["fm"]
        grupos = {}
        for a in self.alertas:
            grupos.setdefault(round(self.X(a.e) / 14), []).append(a)
        for _k, lst in grupos.items():
            a = lst[0]
            ps = self.p.pasos[a.paso] if a.paso >= 0 else min(self.p.pasos, key=lambda q: min(abs(q.e0 - a.e), abs(q.e1 - a.e)))
            f = max(0.0, min(1.0, (a.e - ps.e0) / max(ps.e1 - ps.e0, 1e-6)))
            z = ps.z0 + (ps.z1 - ps.z0) * f
            c = QtCore.QPointF(self.X(a.e), self.Z(z) + 16)
            col = rojo if any(x.nivel == "ERROR" for x in lst) else ambar
            pt.setPen(QtCore.Qt.NoPen)
            pt.setBrush(col)
            pt.drawEllipse(c, 8, 8)
            pt.setPen(QtGui.QColor("#ffffff" if col == rojo else "#1a1a1a"))
            pt.setFont(self._fuente(True))
            pt.drawText(QtCore.QRectF(c.x() - 8, c.y() - 8, 16, 16), QtCore.Qt.AlignCenter,
                        "!" if len(lst) == 1 else str(len(lst)))
            pt.setFont(self._fuente())

    def alertas_en(self, pos):
        """Las alertas de la marca «!» bajo el ratón (por estación ±10 px)."""
        if not self._geo:
            return []
        return [a for a in self.alertas if abs(self.X(a.e) - pos.x()) <= 10]

    def _vacio(self, pt, tk):
        """Estado vacío que guía: flecha hacia el plano (arriba) y qué hacer."""
        r = QtCore.QRectF(self.rect())
        c = r.center()
        col = QtGui.QColor(tk.text_muted)
        pt.setPen(QtGui.QPen(col, 2))
        a, b = QtCore.QPointF(c.x(), c.y() - 18), QtCore.QPointF(c.x(), c.y() - 58)
        pt.drawLine(a, b)
        pt.setBrush(col)
        pt.drawPolygon(QtGui.QPolygonF([b, QtCore.QPointF(b.x() - 7, b.y() + 10),
                                        QtCore.QPointF(b.x() + 7, b.y() + 10)]))
        pt.setFont(self._fuente(True, LETRA_PT + 3))
        pt.setPen(QtGui.QColor(tk.text))
        pt.drawText(QtCore.QRectF(r.left(), c.y() - 10, r.width(), 24), QtCore.Qt.AlignCenter,
                    t("Haz clic en una utilidad del plano"))
        pt.setFont(self._fuente(False, LETRA_PT + 1))
        pt.setPen(col)
        pt.drawText(QtCore.QRectF(r.left() + 20, c.y() + 18, r.width() - 40, 40),
                    QtCore.Qt.AlignHCenter | QtCore.Qt.TextWordWrap,
                    self.aviso_vacio or t("Se arma solo el perfil de su tramo, siguiendo la red de frente en cada unión."))

    def _cursor(self, pt, tk, g):
        """La estación señalada en el plano: línea vertical y punto sobre la tubería."""
        e = self._cursor_e
        if e is None or not (self.p.e_ini <= e <= self.p.e_fin):
            return
        x = self.X(e)
        col = QtGui.QColor(tk.accent)
        pt.setPen(QtGui.QPen(col, 1, QtCore.Qt.DashLine))
        pt.drawLine(QtCore.QPointF(x, g["marco"].top() + g["alto_fila"]), QtCore.QPointF(x, g["marco"].bottom()))
        ps = next((q for q in self.p.pasos if q.e0 <= e <= q.e1), None)
        if ps is not None:
            f = (e - ps.e0) / max(ps.e1 - ps.e0, 1e-6)
            z = ps.z0 + (ps.z1 - ps.z0) * f + ps.alto_ft / 2
            pt.setPen(QtGui.QPen(QtGui.QColor(tk.text_on_accent), 1.5))
            pt.setBrush(col)
            pt.drawEllipse(QtCore.QPointF(x, self.Z(z)), 4.5, 4.5)
            pt.setPen(QtGui.QColor(tk.text))
            pt.drawText(QtCore.QPointF(x + 6, self.Z(z) - 8), T.estacion(e))

    def _rejilla(self, pt, tk, g):
        marco, fm = g["marco"], g["fm"]
        vis = marco.intersected(g["vista"])            # lo que se ve del marco: ahí se anclan los rótulos
        cm, cmen, em, emen = self.p.intervalos
        menor, mayor = QtGui.QColor(tk.grid_line_minor), QtGui.QColor(tk.grid_line_major)
        texto = QtGui.QColor(tk.text_muted)
        z_bot, z_top = self.z_de(vis.bottom()), self.z_de(vis.top())
        z = math.floor(z_bot / cmen) * cmen
        while z <= z_top + 1e-9:
            y = self.Z(z)
            if vis.top() <= y <= vis.bottom():
                es_mayor = abs(z / cm - round(z / cm)) < 1e-6
                pt.setPen(QtGui.QPen(mayor if es_mayor else menor, 1))
                pt.drawLine(QtCore.QPointF(vis.left(), y), QtCore.QPointF(vis.right(), y))
                if es_mayor:
                    pt.setPen(texto)
                    s = f"{z:g}"
                    pt.drawText(QtCore.QPointF(vis.left() - fm.horizontalAdvance(s) - 6, y + fm.ascent() / 3), s)
                    pt.drawText(QtCore.QPointF(vis.right() + 6, y + fm.ascent() / 3), s)
            z += cmen
        e_izq, e_der = self.e_de(vis.left()), self.e_de(vis.right())
        y_est = vis.bottom() + fm.height() + 2
        e = math.ceil(e_izq / em) * em
        etiquetas = [(T.estacion(e_izq, 0), vis.left())]
        while e <= e_der + 1e-9:
            x = self.X(e)
            pt.setPen(QtGui.QPen(mayor, 1))
            pt.drawLine(QtCore.QPointF(x, vis.top()), QtCore.QPointF(x, vis.bottom()))
            etiquetas.append((T.estacion(e, 0), x))
            e += em
        etiquetas.append((T.estacion(e_der, 0), vis.right()))
        pt.setPen(texto)
        fin = -1e9
        for k, (s, x) in enumerate(etiquetas):         # sin encimarse (gana la de la rejilla)
            w = fm.horizontalAdvance(s)
            x0 = x - w / 2
            if x0 < fin + 4 and 0 < k < len(etiquetas) - 1:
                continue
            if x0 < fin + 4:
                continue
            pt.drawText(QtCore.QPointF(x0, y_est), s)
            fin = x0 + w
        s = T.TITULO_ESTACION
        pt.drawText(QtCore.QPointF(vis.center().x() - fm.horizontalAdvance(s) / 2, y_est + fm.height() + 4), s)
        for x, ang in ((vis.left() - 52, -90), (vis.right() + 52, 90)):
            pt.save()
            pt.translate(x, vis.center().y())
            pt.rotate(ang)
            s = T.TITULO_ELEVACION
            pt.drawText(QtCore.QPointF(-fm.horizontalAdvance(s) / 2, fm.ascent() / 2), s)
            pt.restore()

    def _terreno(self, pt, tk):
        ter = self.p.terreno
        if len(ter) < 2:
            return
        pen = QtGui.QPen(QtGui.QColor(tk.text_muted), 1.3, QtCore.Qt.DashLine)
        pt.setPen(pen)
        pts = [QtCore.QPointF(self.X(e), self.Z(z)) for e, z in ter]
        pt.drawPolyline(QtGui.QPolygonF(pts))
        pt.drawText(pts[0] + QtCore.QPointF(4, -4), T.TEXTO_RASANTE)

    def _tuberia(self, pt, tk):
        p = self.p
        base = QtGui.QColor(self.color)
        relleno = QtGui.QColor(base)
        relleno.setAlpha(60)
        for i, ps in enumerate(p.pasos):
            z0, z1 = self._z_paso(i)
            a0, a1 = QtCore.QPointF(self.X(ps.e0), self.Z(z0)), QtCore.QPointF(self.X(ps.e1), self.Z(z1))
            c0 = QtCore.QPointF(self.X(ps.e0), self.Z(z0 + ps.alto_ft))
            c1 = QtCore.QPointF(self.X(ps.e1), self.Z(z1 + ps.alto_ft))
            sel = i == self._sel_paso
            pt.setPen(QtCore.Qt.NoPen)
            pt.setBrush(QtGui.QColor(tk.accent if sel else relleno))
            pt.drawPolygon(QtGui.QPolygonF([a0, a1, c1, c0]))
            pen = QtGui.QPen(base, 2.0 if sel else 1.4)
            if ps.ab:
                pen.setStyle(QtCore.Qt.DashLine)
            pt.setPen(pen)
            pt.drawLine(a0, a1)
            pt.drawLine(c0, c1)
        for k, n in enumerate(p.nodos):
            x = self.X(n.e)
            z = self._z_nodo(k)
            if n.tipo == "estructura":
                g = self._geo
                w = max(8.0, 4.0 * g["kx"] * self._zoom)
                arriba = n.rim if n.rim is not None else z + 5.0
                r = QtCore.QRectF(x - w / 2, self.Z(arriba), w, self.Z(z - 0.5) - self.Z(arriba))
                pt.setPen(QtGui.QPen(QtGui.QColor(tk.text), 1.2))
                pt.setBrush(QtGui.QColor(tk.surface))
                pt.drawRect(r)
            elif n.tipo == "extremo":
                ps = p.pasos[min(k, len(p.pasos) - 1)]
                pt.setPen(QtGui.QPen(base, 1.4))
                pt.drawLine(QtCore.QPointF(x, self.Z(z)), QtCore.QPointF(x, self.Z(z + ps.alto_ft)))
            if n.editable:
                elegido = k in (self._sel_nodo, self._hover) or (self._arrastre and self._arrastre[0] == k)
                pt.setPen(QtGui.QPen(QtGui.QColor(tk.text_on_accent if elegido else tk.text), 1))
                pt.setBrush(QtGui.QColor(tk.accent if elegido else tk.surface))
                pt.drawEllipse(QtCore.QPointF(x, self.Z(z)), RADIO_NODO, RADIO_NODO)
        if self._arrastre:
            k, z = self._arrastre
            s = T.cota(z)
            pt.setPen(QtGui.QColor(tk.text))
            pt.drawText(QtCore.QPointF(self.X(p.nodos[k].e) + 8, self.Z(z) - 8), s)

    def _cruces(self, pt, tk):
        p = self.p
        fm = self._geo["fm"]
        for c in p.cruces:
            col = QtGui.QColor(self.color_de(c.pipe))
            cx, cz = self.X(c.e), self.Z(c.z_solera + c.alto_ft / 2)
            rx = max(3.0, c.alto_ft / 2 * self._geo["kx"] * self._zoom)
            rz = max(3.0, c.alto_ft / 2 * self._geo["kz"] * self._zoom)
            pt.setPen(QtGui.QPen(col, 1.5))
            relleno = QtGui.QColor(col)
            relleno.setAlpha(50)
            pt.setBrush(relleno)
            pt.drawEllipse(QtCore.QPointF(cx, cz), rx, rz)
            # claro entre paredes
            ps = next((q for q in p.pasos if q.e0 <= c.e <= q.e1), None)
            if ps is not None:
                t_ = (c.e - ps.e0) / max(ps.e1 - ps.e0, 1e-6)
                z_run = ps.z0 + (ps.z1 - ps.z0) * t_
                if c.encima:
                    y0, y1 = self.Z(z_run + ps.alto_ft), self.Z(c.z_solera)
                else:
                    y0, y1 = self.Z(z_run), self.Z(c.z_solera + c.alto_ft)
                mal = any(a.cruce == p.cruces.index(c) for a in self.alertas)
                pt.setPen(QtGui.QPen(QtGui.QColor(tk.danger if mal else tk.text), 1.5 if mal else 1))
                xd = cx + rx + 6
                pt.drawLine(QtCore.QPointF(xd, y0), QtCore.QPointF(xd, y1))
                for y in (y0, y1):
                    pt.drawLine(QtCore.QPointF(xd - 3, y), QtCore.QPointF(xd + 3, y))
                pt.drawText(QtCore.QPointF(xd + 4, (y0 + y1) / 2 + fm.ascent() / 2), T.cota(c.claro))

    def _fila(self, pt, tk, g):
        p, fm, marco = self.p, g["fm"], g["marco"]
        if not p.celdas:
            return
        alto = g["alto_fila"]
        base = marco.top() + alto
        pt.setPen(QtGui.QPen(QtGui.QColor(tk.grid_line_major), 1))
        pt.drawLine(QtCore.QPointF(marco.left(), base), QtCore.QPointF(marco.right(), base))
        texto = QtGui.QColor(tk.text)
        for c in p.celdas:
            x0, x1 = self.X(c.e0), self.X(c.e1)
            pt.setPen(QtGui.QPen(QtGui.QColor(tk.text_muted), 1))
            for e in (c.e0, c.e1):
                x = self.X(e)
                k = min(range(len(p.pasos)), key=lambda i: min(abs(p.pasos[i].e0 - e), abs(p.pasos[i].e1 - e)))
                ps = p.pasos[k]
                z = (self._z_paso(k)[0] if abs(ps.e0 - e) <= abs(ps.e1 - e) else self._z_paso(k)[1]) + ps.alto_ft
                pt.drawLine(QtCore.QPointF(x, marco.top()), QtCore.QPointF(x, self.Z(z)))
            pt.setPen(texto)
            y = marco.top() + HUECO + fm.ascent()
            for s in ([_fila_corta(c.lineas)] if self._basico_ahora() else c.lineas):
                ancho = fm.horizontalAdvance(s)
                if ancho <= (x1 - x0) - 4:
                    pt.drawText(QtCore.QPointF((x0 + x1) / 2 - ancho / 2, y), s)
                y += fm.lineSpacing()

    def _callouts(self, pt, tk, g):
        p, fm, marco = self.p, g["fm"], g["marco"]
        tope_arr = marco.top() + g["alto_fila"] + HUECO
        bloques = []                                   # (x deseada, lineas, arriba, punto ancla, nodo | -1)
        self._zonas = []
        for k, n in enumerate(p.nodos):
            if not n.lineas:
                continue
            z = n.z_ancla + (self._z_nodo(k) - (p.pasos[k].z0 if k < len(p.pasos) else p.pasos[k - 1].z1))
            bloques.append((self.X(n.e), self.lineas(n.lineas), n.arriba, QtCore.QPointF(self.X(n.e), self.Z(z)), k))
        for c in p.cruces:
            z = c.z_solera + (c.alto_ft if c.encima else 0.0)
            bloques.append((self.X(c.e), self.lineas(c.lineas, True), c.encima,
                            QtCore.QPointF(self.X(c.e), self.Z(z)), -1))
        texto = QtGui.QColor(tk.text)
        if self._basico_ahora():
            self._etiquetas(pt, tk, g, bloques, tope_arr)
            return
        paredes = sorted({self.X(c.e0) for c in p.celdas} | {self.X(c.e1) for c in p.celdas})
        for arriba in (True, False):
            fin_prev = -1e9
            for x, lineas, _a, ancla, nodo in sorted((b for b in bloques if b[2] == arriba), key=lambda b: b[0]):
                ancho, largo = self._bloque(lineas, fm)
                izq = max(x - ancho / 2, fin_prev + HUECO)
                if arriba:                            # sin cruzar una vertical de la fila de tramos
                    for xv in paredes:
                        if izq - 2 < xv < izq + ancho + 2:
                            izq = xv + 3 if x >= xv else xv - ancho - 3
                    izq = max(izq, fin_prev + HUECO)
                fin_prev = izq + ancho
                if arriba:
                    pie = tope_arr + largo                # el bloque se apoya hacia abajo desde la fila
                    y_cola = pie
                else:
                    pie = marco.bottom() - HUECO
                    y_cola = pie - largo
                # texto vertical: se lee de abajo arriba (el de una T/Y/cruz con ramal, como enlace)
                enlace = nodo in self.con_ramal
                pt.setPen(QtGui.QColor(tk.accent) if enlace else texto)
                if enlace:
                    self._zonas.append((QtCore.QRectF(izq, pie - largo, ancho, largo), nodo))
                pt.save()
                pt.translate(izq, pie)
                pt.rotate(-90)
                y = fm.ascent()
                for s in lineas:
                    pt.drawText(QtCore.QPointF(0, y), s)
                    y += fm.lineSpacing()
                pt.restore()
                # cola bajo la 1.ª línea + leader con flecha hasta el ancla
                xc = izq + fm.lineSpacing() + 1
                pt.setPen(QtGui.QPen(texto, 1))
                pt.drawLine(QtCore.QPointF(xc, pie), QtCore.QPointF(xc, pie - largo))
                desde = QtCore.QPointF(xc, pie if arriba else pie - largo)
                pt.drawLine(desde, ancla)
                self._flecha(pt, desde, ancla, texto)

    def _etiquetas(self, pt, tk, g, bloques, tope_arr):
        """Modo básico: cada punto con una etiqueta HORIZONTAL de una línea y su leader; si se encima con la
        anterior baja/sube a la segunda fila."""
        fm, marco = g["fm"], g["marco"]
        alto = fm.lineSpacing() + 4
        tope_arr = marco.top() + g["alto_fila"] + HUECO
        texto = QtGui.QColor(tk.text)
        fondo = QtGui.QColor(tk.surface)
        borde = QtGui.QColor(tk.border)
        for arriba in (True, False):
            fines = [-1e9] * FILAS_BASICO
            for x, lineas, _a, ancla, nodo in sorted((b for b in bloques if b[2] == arriba), key=lambda b: b[0]):
                s = lineas[0] if lineas else ""
                ancho = fm.horizontalAdvance(s) + 8
                izq = x - ancho / 2
                fila = next((i for i, f in enumerate(fines) if izq >= f + HUECO), None)
                if fila is None:
                    fila = min(range(FILAS_BASICO), key=lambda i: fines[i])
                    izq = fines[fila] + HUECO
                fines[fila] = izq + ancho
                if arriba:
                    top = tope_arr + fila * alto
                else:
                    top = marco.bottom() - HUECO - (fila + 1) * alto
                r = QtCore.QRectF(izq, top, ancho, alto - 2)
                desde = QtCore.QPointF(r.center().x(), r.bottom() if arriba else r.top())
                pt.setPen(QtGui.QPen(texto, 1))
                pt.drawLine(desde, ancla)
                self._flecha(pt, desde, ancla, texto)
                enlace = nodo in self.con_ramal
                pt.setPen(QtGui.QPen(QtGui.QColor(tk.accent) if enlace else borde, 1))
                pt.setBrush(fondo)
                pt.drawRoundedRect(r, 4, 4)
                pt.setPen(QtGui.QColor(tk.accent) if enlace else texto)
                pt.drawText(r, QtCore.Qt.AlignCenter, s)
                if enlace:
                    self._zonas.append((r, nodo))

    def ramal_en(self, pos):
        """Nodo del rótulo-enlace bajo el ratón (T/Y/cruz con ramal) o -1."""
        for r, k in self._zonas:
            if r.adjusted(-3, -3, 3, 3).contains(pos):
                return k
        return -1

    def _flecha(self, pt, a, b, color):
        ang = math.atan2(b.y() - a.y(), b.x() - a.x())
        L = 7
        p1 = QtCore.QPointF(b.x() - L * math.cos(ang - 0.35), b.y() - L * math.sin(ang - 0.35))
        p2 = QtCore.QPointF(b.x() - L * math.cos(ang + 0.35), b.y() - L * math.sin(ang + 0.35))
        pt.setPen(QtCore.Qt.NoPen)
        pt.setBrush(color)
        pt.drawPolygon(QtGui.QPolygonF([b, p1, p2]))

    def _titulo(self, pt, tk, g):
        marco = g["marco"]
        pt.setPen(QtGui.QColor(tk.text))
        f = self._fuente(True, LETRA_PT + 2)
        pt.setFont(f)
        fm = QtGui.QFontMetricsF(f)
        vis = marco.intersected(g["vista"])
        y = vis.bottom() + 2 * g["fm"].height() + 10 + fm.ascent()
        pt.drawText(QtCore.QPointF(vis.left(), y), self.p.titulo[0])
        pt.setFont(self._fuente())
        pt.drawText(QtCore.QPointF(vis.left(), y + g["fm"].lineSpacing() + 2), self.p.titulo[1])

    # ------------------------------------------------------------------ ratón y teclado

    def _nodo_en(self, pos):
        if not self.p or not self._geo:
            return -1
        mejor = (ATRAPAR_PX, -1)
        for k, n in enumerate(self.p.nodos):
            if not n.editable:
                continue
            d = math.hypot(self.X(n.e) - pos.x(), self.Z(self._z_nodo(k)) - pos.y())
            if d <= mejor[0]:
                mejor = (d, k)
        return mejor[1]

    def _paso_en(self, pos):
        if not self.p or not self._geo:
            return -1
        for i, ps in enumerate(self.p.pasos):
            x0, x1 = self.X(ps.e0), self.X(ps.e1)
            if x0 <= pos.x() <= x1:
                f = (pos.x() - x0) / max(x1 - x0, 1e-6)
                z0, z1 = self._z_paso(i)
                z = z0 + (z1 - z0) * f
                if self.Z(z + ps.alto_ft) - 4 <= pos.y() <= self.Z(z) + 4:
                    return i
        return -1

    def mousePressEvent(self, e):
        pos = e.position()
        if e.button() in (QtCore.Qt.MiddleButton, QtCore.Qt.RightButton):
            self._desplazando = (pos, QtCore.QPointF(self._pan or QtCore.QPointF()))
            self._movido = False
            self._boton = e.button()
            return
        if e.button() != QtCore.Qt.LeftButton:
            return
        kr = self.ramal_en(pos)
        if kr >= 0 and self._nodo_en(pos) < 0:
            self.ramalPedido.emit(kr)
            return
        k = self._nodo_en(pos)
        if k >= 0:
            self.elegir_nodo(k)
            self._arrastre = (k, self._z_nodo(k))
            self._agarre_y = pos.y()
            self._z_ini = self._arrastre[1]
            return
        i = self._paso_en(pos)
        self._sel_paso = i
        self.elegir_nodo(-1)
        self.pasoElegido.emit(i)

    def mouseMoveEvent(self, e):
        pos = e.position()
        if self._desplazando:
            a, pan = self._desplazando
            if not self._movido and (pos - a).manhattanLength() < 4:
                return
            if not self._movido:
                self._movido = True
                self._auto = False
                self.setCursor(QtCore.Qt.ClosedHandCursor)
            self._pan = pan + (pos - a)
            self.update()
            return
        if self._arrastre:
            dz = (self._agarre_y - pos.y()) / (self._geo["kz"] * self._zoom)
            self._arrastre = (self._arrastre[0], round(self._z_ini + dz, 2))
            self.update()
            return
        if self._geo and self.p and self.p.pasos and self._geo["vista"].contains(pos):
            e = self.e_de(pos.x())
            self.estacionHover.emit(e if self.p.e_ini <= e <= self.p.e_fin else float("nan"))
        k = self._nodo_en(pos)
        kr = self.ramal_en(pos) if k < 0 else -1
        if k != self._hover:
            self.nodoHover.emit(k)
            self._hover = k
            self.update()
        self.setCursor(QtCore.Qt.SizeVerCursor if k >= 0 else
                       QtCore.Qt.PointingHandCursor if kr >= 0 else QtCore.Qt.ArrowCursor)
        if kr >= 0:
            QtWidgets.QToolTip.showText(e.globalPosition().toPoint(), t("Clic: ver el perfil de este ramal"), self)
            return
        texto = []
        if k >= 0 and self.p.nodos[k].lineas:
            texto += self.p.nodos[k].lineas
        al = self.alertas_en(pos) if self.p else []
        if al:
            texto += [""] * bool(texto) + ["• " + a.mensaje for a in al]
        if texto:
            QtWidgets.QToolTip.showText(e.globalPosition().toPoint(), "\n".join(texto), self)

    def mouseReleaseEvent(self, e):
        if self._desplazando:
            self._desplazando = None
            self.setCursor(QtCore.Qt.ArrowCursor)
            if not self._movido and self._boton == QtCore.Qt.RightButton and self.p:
                self._menu(e.position(), e.globalPosition().toPoint())
            return
        if self._arrastre:
            k, z = self._arrastre
            self._arrastre = None
            if abs(z - self._z_ini) >= 0.005:
                self.cotaCambiada.emit(k, z)
            self.update()

    def mouseDoubleClickEvent(self, e):
        k = self._nodo_en(e.position())
        if k >= 0 and e.button() == QtCore.Qt.LeftButton:
            self._arrastre = None
            self.editar_cota_nodo(k)
            return
        self.encuadrar()

    def wheelEvent(self, e):
        if not self._geo or self._pan is None:
            return
        f = 1.15 if e.angleDelta().y() > 0 else 1 / 1.15
        nz = min(40.0, max(0.3, self._zoom * f))
        pos = e.position()
        g = self._geo
        e_c, z_c = self.e_de(pos.x()), self.z_de(pos.y())
        if abs(nz - 1.0) < 1e-9:
            self._zoom, self._pan = 1.0, None; self._auto = True
            self.update()
            return
        self._zoom = nz
        self._auto = False
        alto_d = (g["z_hi"] - g["z_lo"]) * g["kz"] * nz
        # el punto bajo el cursor se queda quieto
        px = pos.x() - M_IZQ - (e_c - g["e_lo"]) * g["kx"] * nz
        py = pos.y() - M_ARR - g["h_arr"] - alto_d + (z_c - g["z_lo"]) * g["kz"] * nz
        self._pan = QtCore.QPointF(px, py)
        self.update()

    def keyPressEvent(self, e):
        k = self._sel_nodo
        if k >= 0 and e.key() in (QtCore.Qt.Key_Up, QtCore.Qt.Key_Down) and self.p.nodos[k].editable:
            paso = 1.0 if e.modifiers() & QtCore.Qt.ShiftModifier else 0.10
            z = self._z_nodo(k) + (paso if e.key() == QtCore.Qt.Key_Up else -paso)
            self.cotaCambiada.emit(k, round(z, 2))
            return
        if k >= 0 and e.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            self.editar_cota_nodo(k)
            return
        if e.key() in (QtCore.Qt.Key_Home, QtCore.Qt.Key_End) and self.p and self.p.nodos:
            self.elegir_nodo(0 if e.key() == QtCore.Qt.Key_Home else len(self.p.nodos) - 1)
            return
        if e.key() in (QtCore.Qt.Key_Left, QtCore.Qt.Key_Right) and self.p and self.p.nodos:
            n = len(self.p.nodos)
            k = 0 if k < 0 else (k + (1 if e.key() == QtCore.Qt.Key_Right else -1)) % n
            self.elegir_nodo(k)
            return
        super().keyPressEvent(e)

    def leaveEvent(self, _e):
        self.estacionHover.emit(float("nan"))
        if self._hover >= 0:
            self._hover = -1
            self.nodoHover.emit(-1)
            self.update()

    def focusInEvent(self, e):
        super().focusInEvent(e)
        self.update()

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.update()

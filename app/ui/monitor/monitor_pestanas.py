"""Pestañas del monitor: Ahora · Congelamientos · Trabajos · Reconocimiento · Pasos y etapas.

Cada una tiene `refrescar(sesion, resumen)`: `sesion` = `nucleo.vigilante_vivo.Sesion` (estado en vivo) y `resumen`
= `nucleo.vigilante_informe.resumir` de sus sucesos (agregados), que la ventana recalcula solo cuando llega algo.
"""
from __future__ import annotations

import time

from PySide6 import QtCore, QtWidgets

from traduccion.i18n import t as _tr
from ui.monitor.monitor_grafico import GraficoMemoria
from ui.monitor.monitor_util import Tabla, dur, funcion_legible, hora, mb, tarjeta

RECONOCER = ("reconoc", "interpretar", "recognition", "letras", "válvulas", "diámetros", "lectura retenida")


def nombre_proceso(nombre: str) -> str:
    n = nombre or ""
    if n == "ventana":
        return _tr("Ventana (interfaz)")
    if n == "monitor":
        return _tr("Monitor")
    if n.startswith("pdfcad-teselas"):
        return _tr("Teselas {n}").format(n=n.rsplit("-", 1)[-1])
    if n.startswith("pdfcad-"):
        return _tr("Trabajador «{n}»").format(n=n[len("pdfcad-"):])
    if n.startswith(("SpawnProcess", "Process", "ForkProcess")) or n == "grupo":
        return _tr("Grupo de procesos")
    return n or "?"


def objetivo_corto(obj: str) -> str:
    """«reconocimiento.recognition_trabajo:reconocer_hoja» → «reconocer_hoja (recognition_trabajo)»."""
    mod, _, fn = (obj or "").rpartition(":")
    return f"{fn} ({mod.rsplit('.', 1)[-1]})" if mod else (obj or "?")


class VistaPerfil(QtWidgets.QWidget):
    """El perfil de un trabajo o de una pausa: cada función con su tiempo propio y total."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.lbl = QtWidgets.QLabel()
        self.lbl.setWordWrap(True)
        self.lbl.setProperty("rol", "t2")
        self.tabla = Tabla([_tr("Función"), _tr("Propio"), _tr("Total")])
        self.tabla.anchos(0, 90, 90)
        self.tabla.setToolTip(_tr("Propio = tiempo en la función misma. Total = con todo lo que llama."))
        lay.addWidget(self.lbl)
        lay.addWidget(self.tabla, 1)

    def poner(self, perfil, encabezado: str = "") -> None:
        perfil = perfil or {}
        propio = dict(perfil.get("propio") or [])
        total = dict(perfil.get("total") or [])
        nombres = sorted(set(propio) | set(total), key=lambda n: -(total.get(n) or propio.get(n) or 0))
        self.tabla.poner([(funcion_legible(n), (dur(propio.get(n)), propio.get(n, 0.0)),
                           (dur(total.get(n)), total.get(n, 0.0))) for n in nombres], alinear_der=(1, 2))
        self.tabla.ordenar(1)
        self.lbl.setText(encabezado or _tr("{n} muestras de la pila").format(n=perfil.get("muestras", 0)))


def _divisor(arriba, abajo, vertical=True):
    s = QtWidgets.QSplitter(QtCore.Qt.Vertical if vertical else QtCore.Qt.Horizontal)
    s.addWidget(arriba)
    s.addWidget(abajo)
    s.setChildrenCollapsible(False)
    s.setStretchFactor(0, 3)
    s.setStretchFactor(1, 2)
    return s


class PestanaAhora(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 8, 0, 0)
        f1, l1 = tarjeta(_tr("Procesos de la app"))
        self.tabla = Tabla([_tr("Proceso"), _tr("PID"), _tr("Haciendo ahora"), _tr("CPU"), _tr("Memoria"),
                            _tr("Pico"), _tr("Trabajos")], estirar=2)
        self.tabla.anchos(190, 70, 0, 70, 90, 90, 80)
        l1.addWidget(self.tabla)
        f2, l2 = tarjeta(_tr("Memoria"))
        self.grafico = GraficoMemoria()
        l2.addWidget(self.grafico)
        lay.addWidget(_divisor(f1, f2), 1)

    def refrescar(self, ses, _res, estado_ventana):
        ahora = time.time()
        filas, datos = [], []
        for p in sorted(ses.procesos.values(), key=lambda p: (not p.vivo, p.inicio or 0)):
            if p.pid == ses.pid_ventana:
                haciendo = estado_ventana
            elif p.trabajo:
                haciendo = f"{objetivo_corto(p.trabajo[0])} · {dur(ahora - p.trabajo[1])}"
                if p.etapa:
                    haciendo += "  —  " + p.etapa[0]
            elif p.vivo:
                haciendo = _tr("Esperando trabajo")
            else:
                haciendo = _tr("Terminó")
            filas.append((nombre_proceso(p.nombre), (str(p.pid), p.pid), haciendo,
                          ("—" if p.cpu_pct is None or not p.vivo else f"{p.cpu_pct:.0f} %", p.cpu_pct or 0.0),
                          (mb(p.priv_mb) if p.vivo else "—", p.priv_mb or 0.0), (mb(p.pico_mb), p.pico_mb),
                          (str(p.trabajos), p.trabajos)))
            datos.append(p)
        self.tabla.poner(filas, datos, alinear_der=(1, 3, 4, 5, 6))
        pausas = [(e["t"], e.get("dur", 0.0)) for e in ses.de_tipo("congelamiento")]
        self.grafico.poner(ses.serie, pausas)


class PestanaCongelamientos(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 8, 0, 0)
        f1, l1 = tarjeta(_tr("Pausas de la ventana (no atendió al usuario)"))
        self.tabla = Tabla([_tr("Hora"), _tr("Duración"), _tr("Qué hacía"), _tr("Dónde estaba")], estirar=2)
        self.tabla.anchos(80, 90, 0, 340)
        l1.addWidget(self.tabla)
        f2, l2 = tarjeta(_tr("Detalle de la pausa elegida"))
        self.perfil = VistaPerfil()
        l2.addWidget(self.perfil)
        lay.addWidget(_divisor(f1, f2), 1)
        self.tabla.elegida.connect(self._ver)

    def refrescar(self, ses, _res, _estado):
        filas, datos = [], []
        for e in ses.de_tipo("congelamiento"):
            if e.get("suspension"):
                continue
            que = e.get("carga") or e.get("etapa") or " › ".join(e.get("bloques") or []) or _tr("(sin dato)")
            arriba = ((e.get("perfil") or {}).get("propio") or [["", 0]])[0][0]
            d = e.get("dur", 0.0)
            filas.append(((hora(e["t"]), e["t"]), (("⚠ " if e.get("no_responde") else "") + dur(d), d), que,
                          funcion_legible(arriba)))
            datos.append(e)
        self.tabla.poner(filas, datos, alinear_der=(1,))

    def _ver(self, e):
        if e is None:
            return
        fuente = _tr("muestreo de la pila") if e.get("fuente") == "muestreo" else \
            _tr("volcados de faulthandler (la ventana tenía tomado el intérprete: código en C)")
        texto = _tr("{d} a las {h}. Qué hacía: {q}. Medido con {f}.").format(
            d=dur(e.get("dur")), h=hora(e.get("t")),
            q=e.get("carga") or e.get("etapa") or " › ".join(e.get("bloques") or []) or _tr("(sin dato)"), f=fuente)
        self.perfil.poner(e.get("perfil"), texto)


class PestanaTrabajos(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 8, 0, 0)
        f1, l1 = tarjeta(_tr("Trabajos de los procesos (y de los hilos de la ventana)"))
        self.tabla = Tabla([_tr("Hora"), _tr("Proceso"), _tr("Trabajo"), _tr("Espera"), _tr("Duración"),
                            _tr("Memoria"), _tr("Estado")], estirar=2)
        self.tabla.anchos(80, 170, 0, 80, 90, 90, 90)
        l1.addWidget(self.tabla)
        f2, l2 = tarjeta(_tr("Detalle del trabajo elegido"))
        self.pasos = Tabla([_tr("Paso o etapa"), _tr("Duración")])
        self.pasos.anchos(0, 90)
        self.perfil = VistaPerfil()
        abajo = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        abajo.addWidget(self.pasos)
        abajo.addWidget(self.perfil)
        abajo.setChildrenCollapsible(False)
        l2.addWidget(abajo)
        lay.addWidget(_divisor(f1, f2), 1)
        self.tabla.elegida.connect(self._ver)
        self._ses = None

    def refrescar(self, ses, _res, _estado):
        self._ses = ses
        esperas = {(e.get("objetivo"), e.get("tid")): e.get("espera") for e in ses.de_tipo("encargo")}
        filas, datos = [], []
        ahora = time.time()
        for p in ses.procesos.values():
            if p.trabajo:
                filas.append(((hora(p.trabajo[1]), p.trabajo[1]), nombre_proceso(p.nombre),
                              objetivo_corto(p.trabajo[0]), "—", (dur(ahora - p.trabajo[1]), ahora - p.trabajo[1]),
                              "—", _tr("En curso")))
                datos.append(None)
        for e in ses.de_tipo("trabajo"):
            ini = e["t"] - (e.get("dur") or 0.0)
            espera = esperas.get((e.get("objetivo"), e.get("tid")))
            estado = _tr("Bien") if not e.get("error") else e["error"]
            filas.append(((hora(ini), ini), nombre_proceso(ses.nombre(e.get("pid"))), objetivo_corto(e.get("objetivo")),
                          (dur(espera), espera or 0.0), (dur(e.get("dur")), e.get("dur") or 0.0),
                          (mb(e.get("mem_pico_mb")), e.get("mem_pico_mb") or 0.0), estado))
            datos.append(e)
        self.tabla.poner(filas, datos, alinear_der=(3, 4, 5))

    def _ver(self, e):
        if e is None or self._ses is None:
            return
        pasos = []
        for s in self._ses.dentro_de(e):
            nombre = s.get("nombre") if s.get("tipo") == "bloque" else s.get("texto")
            if s.get("utilidad"):
                nombre = f"{nombre} · {s['utilidad']}"
            pasos.append((nombre or "?", (dur(s.get("dur")), s.get("dur") or 0.0)))
        self.pasos.poner(pasos, alinear_der=(1,))
        self.pasos.ordenar(1)
        self.perfil.poner(e.get("perfil"), f"{e.get('objetivo')}: {dur(e.get('dur'))}")


class PestanaReconocimiento(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 8, 0, 0)
        f1, l1 = tarjeta(_tr("Pasos del reconocimiento"))
        self.tabla = Tabla([_tr("Paso"), _tr("Veces"), _tr("Total"), _tr("Media"), _tr("Máx")])
        self.tabla.anchos(0, 70, 90, 90, 90)
        l1.addWidget(self.tabla)
        f2, l2 = tarjeta(_tr("Dónde se va el tiempo (todas las funciones, sumadas)"))
        self.perfil = VistaPerfil()
        l2.addWidget(self.perfil)
        lay.addWidget(_divisor(f1, f2, vertical=False), 1)

    def refrescar(self, _ses, res, _estado):
        filas = []
        for a in res["bloques"] + res["trabajos"]:
            if any(r in a["nombre"].lower() for r in RECONOCER):
                filas.append((a["nombre"], (str(a["veces"]), a["veces"]), (dur(a["total"]), a["total"]),
                              (dur(a["media"]), a["media"]), (dur(a["max"]), a["max"])))
        self.tabla.poner(filas, alinear_der=(1, 2, 3, 4))
        self.tabla.ordenar(2)
        perfil = {"propio": res["perfil_reconocer_propio"], "total": res["perfil_reconocer_total"],
                  "muestras": len(filas)}
        self.perfil.poner(perfil, _tr("Suma de los perfiles de todos los trabajos de reconocimiento de la sesión."))


class PestanaPasos(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 8, 0, 0)
        f, lt = tarjeta()
        self.buscar = QtWidgets.QLineEdit()
        self.buscar.setPlaceholderText(_tr("Buscar un paso, etapa o trabajo…"))
        self.buscar.setClearButtonEnabled(True)
        lt.addWidget(self.buscar)
        self.tabla = Tabla([_tr("Tipo"), _tr("Qué"), _tr("Veces"), _tr("Total"), _tr("Media"), _tr("Máx")], estirar=1)
        self.tabla.anchos(110, 0, 70, 90, 90, 90)
        lt.addWidget(self.tabla)
        lay.addWidget(f, 1)
        self.buscar.textChanged.connect(lambda _t: self._llenar())
        self._res = None

    def refrescar(self, _ses, res, _estado):
        self._res = res
        self._llenar()

    def _llenar(self):
        if self._res is None:
            return
        filtro = self.buscar.text().strip().lower()
        filas = []
        for tipo, campo in ((_tr("Paso"), "bloques"), (_tr("Etapa"), "etapas"), (_tr("Espera visible"), "cargas"),
                            (_tr("Trabajo"), "trabajos"), (_tr("Repetido"), "acumulados")):
            for a in self._res[campo]:
                if filtro and filtro not in a["nombre"].lower():
                    continue
                filas.append((tipo, a["nombre"], (str(a["veces"]), a["veces"]), (dur(a["total"]), a["total"]),
                              (dur(a["media"]), a["media"]), (dur(a["max"]), a["max"])))
        self.tabla.poner(filas, alinear_der=(2, 3, 4, 5))
        self.tabla.ordenar(3)

"""UNA barra de avance PRECISA para un trabajo largo de varias etapas, en la capa «Cargando…» (pedido del
usuario 2026-10-20: «que el usuario no sienta que es un bug»). La usan exportar a DXF, abrir y guardar el
proyecto, «Revisar y limpiar el dibujo» y la Tabla de datos (y su Excel).

Las etapas van EN ORDEN (el de `partes`): cuando empieza una, las anteriores quedan completas. Cada etapa
tiene una CLAVE, un texto (`textos`, con «{i} de {n}» si lo sabe) y un costo estimado (ms, medido
con AGUA 2: `nucleo.avance_pesado.Barra`). Las etapas avisan con `recibir(clave, i, n)` —directo, o desde el
código puro con `nucleo.avance.avisar` dentro de `escuchar()` o de `en_hilo.ejecutar(avance=…)`—. La barra
suma lo hecho / el total y NUNCA retrocede; una etapa que no sabe cuánto lleva avanza sola según su costo
estimado (hasta `TOPE_SOLA` de su parte) y salta al terminar.

La capa va en modo «foto» (`busy.begin(foto=True)`): repintarla cuesta ~3 ms en vez de redibujar el plano
entero debajo (~90 ms con 16 761 utilidades), así avisar seguido no hace más lento el trabajo.
"""
from __future__ import annotations

import time

from PySide6 import QtCore

from nucleo import avance
from nucleo.avance_pesado import Barra
from traduccion.i18n import t as _tr
from ui.comun import busy

TOPE_SOLA = 0.9                        # una etapa sin «i de n» avanza sola hasta aquí de su parte
TICK_MS = 100
PINTAR_S = 0.05                        # repintar como mucho cada esto (trabajo en el hilo de la ventana)


class AvancePesado(QtCore.QObject):
    """La barra de UN trabajo: `abrir` (pone la capa), avisos (`recibir`/`escuchar`), `terminada` y `cerrar`
    (siempre). `partes` = {clave: costo estimado}; `textos` = {clave: texto con N_()}."""

    def __init__(self, host, partes, textos, cursor=True):
        super().__init__(host)
        self.host = host
        self.barra = Barra(partes)
        self.textos = dict(textos)
        self.ov = busy.overlay_for(host)
        self.cursor = cursor
        self.abierta = False
        self._etapa, self._desde, self._sola = None, 0.0, False
        self._listas = set()
        self._detalle = ""
        self._pintado = 0.0
        self._t = QtCore.QTimer(self, interval=TICK_MS, timeout=self._tick)

    # ── capa ──
    def abrir(self, texto):
        self.ov.begin(texto, cursor=self.cursor, foto=True)
        self.abierta = True
        self._t.start()
        return self

    def cerrar(self):
        self._t.stop()
        if self.abierta:
            self.abierta = False
            self.ov.end()

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.cerrar()
        return False

    # ── estimaciones ──
    def costos_nuevos(self, cambios):
        self.barra.costos_nuevos(cambios)

    def terminada(self, *partes):
        """Partes que ya se hicieron o que esta vez no se hacen."""
        for p in partes:
            if p in self.barra.costos:
                self.barra.lista(p)
            self._listas.add(p)
        self._mostrar(pump=False)

    # ── avisos ──
    def escuchar(self):
        """`with av.escuchar():` lo que corre en el hilo de la ventana avisa aquí (y repinta)."""
        return avance.escuchar(lambda etapa, i, n: self.recibir(etapa, i, n, pump=True))

    def clave(self, etapa):
        """La clave de la barra para una etapa avisada (las subclases pueden traducirla)."""
        return etapa

    def recibir(self, etapa, i=None, n=None, pump=False):
        etapa = self.clave(etapa)
        if etapa not in self.textos or etapa in self._listas:
            return
        if etapa != self._etapa:
            # las etapas van en el orden de `partes`: si empieza ésta, las anteriores terminaron (o esta vez
            # no se hicieron o no alcanzaron a avisar: p. ej. menos filas que las que hay entre aviso y aviso)
            previas = list(self.barra.costos)
            previas = previas[:previas.index(etapa)] if etapa in previas else []
            for p in previas:
                if p not in self._listas:
                    self.barra.lista(p)
                    self._listas.add(p)
            if self._etapa is not None and self._etapa not in self._listas:
                self.barra.lista(self._etapa)
                self._listas.add(self._etapa)
            self._etapa, self._desde = etapa, time.perf_counter()
        self._al_recibir(etapa, i, n)
        self._sola = i is None or not n
        if not self._sola:
            self.barra.parte(etapa, i / n)
        texto = _tr(self.textos[etapa])
        if "{i}" in texto:
            texto = texto.format(i=i, n=n) if n else texto.split(":")[0] + "…"
        self._detalle = texto
        self._mostrar(pump=pump)

    def _al_recibir(self, etapa, i, n):
        """Gancho de las subclases (p. ej. corregir costos cuando se sabe cuánto hay)."""

    def _tick(self):
        if not self.abierta:
            return
        if self._sola and self._etapa is not None:    # sin «i de n»: avanza sola según lo estimado
            estimado = max(0.5, self.barra.costos.get(self._etapa, 0.0) / 1000.0)
            self.barra.parte(self._etapa, min(TOPE_SOLA, (time.perf_counter() - self._desde) / estimado))
        self._mostrar(pump=False)

    def _mostrar(self, pump):
        if not self.abierta:
            return
        ahora = time.perf_counter()
        if pump and ahora - self._pintado < PINTAR_S:
            return                                    # en el hilo de la ventana: no repintar a cada aviso
        self._pintado = ahora
        mil = self.barra.milesimas
        detalle = _tr("{etapa} · {p} %").format(etapa=self._detalle, p=mil // 10) if self._detalle else ""
        self.ov.step(detail=detalle, done=mil, total=1000, pump=pump)

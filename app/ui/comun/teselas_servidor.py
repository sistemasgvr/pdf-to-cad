"""teselas_servidor.py — Del lado de la ventana: los procesos de las teselas, los pedidos y la caché.

Ver `teselas.py`. Un `Servidor` por aplicación (`servidor()`):

  · cada vista que muestra una hoja (`teselas_vista.Superficie`) le dice qué teselas quiere, en
    orden (las del centro primero, luego un anillo alrededor); el servidor junta los pedidos de
    todas, quita las que ya tiene y los reparte entre sus procesos (`teselas_hijo`; varios a la
    vez, `cuantos()`), que dibujan en ese orden y REEMPLAZAN su lista con cada pedido: lo que
    dejó de verse no se dibuja. Una tesela ya repartida sigue en el mismo proceso;
  · lo que llega se guarda en una caché (LRU, `MAX_MB`; nunca se suelta una tesela que alguien
    está mirando) y se avisa a la superficie, que repinta solo ese cuadro;
  · los mensajes a cada proceso salen por un hilo (un PDF de 30 MB no traba la ventana mientras
    el proceso termina su tesela) y las respuestas se leen con un temporizador (`SONDEO_MS`);
  · el PDF va por su ruta (el hijo lo lee a memoria) o, si se abrió de memoria, por sus bytes;
    las capas apagadas viajan como el estado de `layer_ui_configs` (su `firma` va en la clave:
    con otras capas, otras teselas).

Sin procesos (`PDFCAD_PROCESO=0`: las pruebas) o si no arrancan, las teselas se dibujan aquí
mismo al pedirlas, con el mismo código (`teselas.dibujar`): los mismos píxeles.
"""
from __future__ import annotations

import itertools
import multiprocessing as mp
import os
import queue
import threading
import time
import weakref
import zlib
from collections import OrderedDict
from typing import Dict, List, Optional

from PySide6 import QtCore, QtGui

from ui.comun import proceso, proceso_hijo, teselas as T, teselas_hijo

MAX_MB = 384                 # caché de teselas en la ventana (1024² px ≈ 4 MB cada una)
MAX_PROCESOS = 3             # dibujantes a la vez (cada uno con su lista de dibujo de la hoja)
MB_POR_PROCESO = 700
SONDEO_MS = 15
LEER_MAX_S = 0.03            # por vuelta del temporizador: la ventana sigue respondiendo
REINTENTOS = 3               # procesos que mueren → se dibuja aquí mismo
OLVIDAR_MS = 4000            # un PDF que ninguna vista muestra se cierra en los procesos tras este rato


class Tesela:
    __slots__ = ("pm", "x", "y", "w", "h", "nivel", "bytes")

    def __init__(self, pm, x, y, w, h, nivel):
        self.pm, self.x, self.y, self.w, self.h, self.nivel = pm, x, y, w, h, nivel
        self.bytes = w * h * 4


def _pixmap(w, h, stride, datos) -> QtGui.QPixmap:
    img = QtGui.QImage(datos, w, h, stride, QtGui.QImage.Format_RGB888).copy()
    return QtGui.QPixmap.fromImage(img)


def estado_capas(doc):
    """(firma, ((número, encendida), …)) de las capas del PDF tal como las ve la ventana."""
    try:
        ons = tuple((int(c["number"]), int(bool(c["on"]))) for c in doc.layer_ui_configs())
    except Exception:
        ons = ()
    return zlib.crc32(repr(ons).encode()) if ons else 0, ons


def fuente(doc):
    """Cómo abre el proceso este PDF: por su ruta si es un archivo sin cambios, si no sus bytes."""
    nombre = getattr(doc, "name", "") or ""
    sucio = bool(getattr(doc, "is_dirty", False))
    if nombre and os.path.isfile(nombre) and not sucio and getattr(doc, "is_pdf", True):
        st = os.stat(nombre)
        return ("ruta", nombre, st.st_size, st.st_mtime_ns)
    datos = getattr(doc, "stream", None)
    if datos is not None and not sucio:
        return ("datos", bytes(datos))
    return ("datos", doc.tobytes())


def cuantos() -> int:
    """Procesos dibujantes: hasta `MAX_PROCESOS`, según núcleos y memoria libre."""
    return proceso_hijo.paralelos(MAX_PROCESOS, MB_POR_PROCESO)


class _Proc:
    """Un proceso dibujante: un tubo de ida (con su hilo de envío) y otro de vuelta."""

    def __init__(self, i: int):
        ctx = mp.get_context("spawn")
        rx_hijo, self.tx = ctx.Pipe(duplex=False)
        self.rx, tx_hijo = ctx.Pipe(duplex=False)
        self.p = ctx.Process(target=teselas_hijo.bucle, name=f"pdfcad-teselas-{i}",
                             args=((rx_hijo, tx_hijo), proceso.tope_mb()), daemon=True)
        self.p.start()
        rx_hijo.close(); tx_hijo.close()
        self.cola: "queue.Queue" = queue.Queue()
        self.hilo = threading.Thread(target=self._envio, args=(self.tx, self.cola),
                                     name=f"pdfcad-teselas-envio-{i}", daemon=True)
        self.hilo.start()
        self.docs: set = set()                       # tokens ya enviados
        self.capas: Dict[str, int] = {}              # token → firma enviada
        self.enviado: Optional[list] = None          # última lista pedida

    @staticmethod
    def _envio(tx, cola):
        while True:
            msg = cola.get()
            if msg is StopIteration:
                return
            try:
                tx.send(msg)
            except Exception:
                return

    def vivo(self) -> bool:
        return self.p.is_alive()

    def enviar(self, msg) -> None:
        self.cola.put(msg)

    def parar(self) -> None:
        self.cola.put(StopIteration)
        for c in (self.tx, self.rx):
            try:
                c.close()
            except Exception:
                pass
        try:
            self.p.terminate()
            self.p.join(2)
        except Exception:
            pass


class Servidor(QtCore.QObject):
    _ids = itertools.count(1)

    def __init__(self, local: Optional[bool] = None):
        super().__init__()
        self.local = (not proceso.activo()) if local is None else bool(local)
        self.con_proceso = not self.local
        self._cache: "OrderedDict[tuple, Tesela]" = OrderedDict()
        self._bytes = 0
        self._duenos: Dict[int, tuple] = {}          # id → (superficie, page, [(prioridad, clave, visible)])
        self._fallidas: set = set()
        self._procs: List[Optional[_Proc]] = []
        self._asignada: Dict[tuple, int] = {}        # clave → proceso que la dibuja
        self._rotos: set = set()                     # tokens de PDF que el proceso no pudo abrir
        self._muertes = 0
        self._ocioso = 0
        self._hojas_local = None
        self._firma_local: Dict[str, int] = {}
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(SONDEO_MS)
        self._timer.timeout.connect(self._leer)
        self._superficies = weakref.WeakSet()           # las que muestran una hoja (`mostrando`)
        self._t_olvidar = QtCore.QTimer(self)
        self._t_olvidar.setSingleShot(True)
        self._t_olvidar.setInterval(OLVIDAR_MS)
        self._t_olvidar.timeout.connect(self._olvidar_docs)

    # ── documentos ────────────────────────────────────────────────────
    def preparar(self, page):
        """(token, firma) de la hoja: el PDF queda registrado en los procesos con sus capas."""
        doc = page.parent
        tok = getattr(doc, "_pdfcad_tesela", None)
        if tok is None:
            tok = f"d{next(self._ids)}"
            doc._pdfcad_tesela = tok
        firma, ons = estado_capas(doc)
        if not self.local:
            self._asegurar()
        if self.local:
            if self._firma_local.get(tok) != firma and self._hojas_local is not None:
                self._hojas_local.soltar()
            self._firma_local[tok] = firma
            return tok, firma
        src = None
        for pr in self._procs:
            if pr is None:
                continue
            if tok not in pr.docs:
                try:
                    src = src or fuente(doc)
                    pr.enviar(("doc", tok, src))
                except Exception:
                    pass
                pr.docs.add(tok)
            if pr.capas.get(tok) != firma:
                pr.enviar(("capas", tok, firma, ons))
                pr.capas[tok] = firma
        return tok, firma

    def calentar(self, page):
        """La lista de dibujo de la hoja se prepara en los procesos antes del primer zoom."""
        if self.local:
            return
        try:
            tok, firma = self.preparar(page)
            for pr in self._procs:
                if pr is not None:
                    pr.enviar(("calentar", tok, firma, page.number))
        except Exception:
            pass

    # ── pedidos ───────────────────────────────────────────────────────
    def tesela(self, clave) -> Optional[Tesela]:
        t = self._cache.get(clave)
        if t is not None:
            self._cache.move_to_end(clave)
        return t

    def pedir(self, dueno, page, pedidos) -> None:
        """`pedidos` = [(prioridad, clave, visible)] de `dueno` (REEMPLAZA los anteriores)."""
        if pedidos:
            self._duenos[id(dueno)] = (dueno, page, list(pedidos))
        else:
            self._duenos.pop(id(dueno), None)
        if self.local:
            self._dibujar_aqui(dueno, page, pedidos)
            return
        self._despachar()

    def olvidar(self, dueno) -> None:
        if self._duenos.pop(id(dueno), None) is not None and not self.local:
            self._despachar()

    # ── PDF que ya no se ven ──────────────────────────────────────────
    def mostrando(self, sup, si: bool = True) -> None:
        """La superficie `sup` muestra (o dejó de mostrar) una hoja. Un rato después, los PDF que
        ninguna muestra se cierran en los procesos (`_olvidar_docs`)."""
        if si:
            self._superficies.add(sup)
        else:
            self._superficies.discard(sup)
        if not self.local and self._procs:
            self._t_olvidar.start()

    def _olvidar_docs(self) -> None:
        """Cada proceso guardaba hasta 6 PDF con la lista de dibujo y las cajas de letras de su hoja
        (reporte 2026-10-24, agregar una utilidad: el agua de antes, la hoja calcada y la combinada,
        ~1 GB por proceso con 36 mapas cada una). Ahora cierra los que ninguna vista a la vista
        muestra; si uno vuelve a verse (Cancelar repone el editor) se le manda otra vez."""
        if self.local:
            return
        vivos = set()
        for sup in list(self._superficies):
            try:
                if sup.viva() and sup.a_la_vista():
                    tok = getattr(sup.page.parent, "_pdfcad_tesela", None)
                    if tok:
                        vivos.add(tok)
            except RuntimeError:
                continue
        for d, p, lst in list(self._duenos.values()):      # y los que aún esperan teselas
            if lst and d.viva():
                vivos.add(getattr(p.parent, "_pdfcad_tesela", None))
        for pr in self._procs:
            if pr is None:
                continue
            for tok in [t for t in pr.docs if t not in vivos]:
                pr.enviar(("olvidar", tok))
                pr.docs.discard(tok)
                pr.capas.pop(tok, None)

    def _queridas(self):
        """Claves que alguien está mirando (no se sueltan de la caché)."""
        return {c for _d, _p, lst in self._duenos.values() for _pr, c, _v in lst}

    def _despachar(self):
        for k in [k for k, (d, _p, _l) in self._duenos.items() if not d.viva()]:
            del self._duenos[k]
        todas = sorted((pr, c) for _d, _p, lst in self._duenos.values() for pr, c, _v in lst
                       if c not in self._cache and c not in self._fallidas and c[0] not in self._rotos)
        vistas, lista = set(), []
        for _pr, c in todas:
            if c not in vistas:
                vistas.add(c)
                lista.append(c)
        if lista and not self._asegurar():
            for d, p, lst in list(self._duenos.values()):       # sin procesos: aquí mismo
                self._dibujar_aqui(d, p, lst)
            return
        for _d, p, _lst in list(self._duenos.values()):          # proceso nuevo: los PDF otra vez
            try:
                if any(pr is not None and getattr(p.parent, "_pdfcad_tesela", None) not in pr.docs
                       for pr in self._procs):
                    self.preparar(p)
            except Exception:
                pass
        # reparto: una tesela ya repartida sigue en su proceso; las nuevas, al que tenga menos
        vivos = [i for i, pr in enumerate(self._procs) if pr is not None]
        partes: Dict[int, list] = {i: [] for i in vivos}
        asignada = {}
        for c in lista:
            i = self._asignada.get(c)
            if i not in partes:
                i = min(vivos, key=lambda j: (len(partes[j]), j)) if vivos else None
            if i is None:
                continue
            partes[i].append(c)
            asignada[c] = i
        self._asignada = asignada
        for i in vivos:
            pr = self._procs[i]
            if partes[i] != pr.enviado:
                pr.enviado = partes[i]
                pr.enviar(("pedir", partes[i]))
        if lista:
            self._ocioso = 0
            self._timer.start()

    # ── llegada ───────────────────────────────────────────────────────
    def _guardar(self, clave, t: Tesela):
        viejo = self._cache.pop(clave, None)
        if viejo is not None:
            self._bytes -= viejo.bytes
        self._cache[clave] = t
        self._bytes += t.bytes
        if self._bytes > MAX_MB * 2**20:
            protegidas = self._queridas()
            for k in list(self._cache):
                if self._bytes <= MAX_MB * 2**20 * 0.85:
                    break
                if k in protegidas or k == clave:
                    continue
                self._bytes -= self._cache.pop(k).bytes

    def _avisar(self, clave):
        for d, _p, lst in list(self._duenos.values()):
            if any(c == clave for _pr, c, _v in lst):
                d.recibida(clave)

    def _leer(self):
        t0 = time.perf_counter()
        hubo = False
        for i, pr in enumerate(self._procs):
            if pr is None:
                continue
            leidos = 0
            try:
                while pr.rx.poll():
                    self._mensaje(pr.rx.recv(), pr)
                    leidos += 1
                    if time.perf_counter() - t0 > LEER_MAX_S:
                        break
            except (EOFError, OSError):
                self._muere(i)
                continue
            hubo = hubo or leidos > 0
            if not leidos and not pr.vivo():
                self._muere(i)
        if hubo:
            self._ocioso = 0
            return
        self._ocioso += 1
        if self._ocioso > 1000 // SONDEO_MS and not any(
                c not in self._cache and c not in self._fallidas for c in self._queridas()):
            self._timer.stop()                   # nada pendiente: deja de sondear

    def _mensaje(self, msg, pr=None):
        if msg[0] == "t":
            _, clave, x, y, w, h, stride, datos = msg
            self._asignada.pop(clave, None)
            pm = _pixmap(w, h, stride, datos)
            if not pm.isNull():
                self._guardar(clave, Tesela(pm, x, y, w, h, clave[3]))
                self._avisar(clave)
        elif msg[0] == "x":
            clave = msg[1]
            self._asignada.pop(clave, None)
            if msg[2] == "sin documento" and pr is not None and clave[0] not in self._rotos:
                # el proceso soltó ese PDF (guarda pocos a la vez): se le manda otra vez
                pr.docs.discard(clave[0])
                pr.capas.pop(clave[0], None)
                pr.enviado = None
                QtCore.QTimer.singleShot(0, self._despachar)
            else:
                self._fallidas.add(clave)
        elif msg[0] == "d":                          # el PDF no abrió: nada de ese token
            self._rotos.add(msg[1])
            self._fallidas.update(c for c in self._queridas() if c[0] == msg[1])

    # ── sin procesos ──────────────────────────────────────────────────
    def _dibujar_aqui(self, dueno, page, pedidos):
        from ui.comun.recorte_nitido import Hojas
        if self._hojas_local is None:
            self._hojas_local = Hojas(max_hojas=4)
        for _pr, clave, visible in pedidos:
            if not visible or clave in self._cache or clave in self._fallidas:
                continue
            _tok, _firma, _num, nivel, tx, ty = clave
            try:
                pix = T.dibujar(self._hojas_local, page, nivel, tx, ty)
            except Exception:
                pix = None
            if pix is None:
                self._fallidas.add(clave)
                continue
            self._guardar(clave, Tesela(_pixmap(pix.width, pix.height, pix.stride, pix.samples),
                                        pix.x, pix.y, pix.width, pix.height, nivel))
            dueno.recibida(clave)

    # ── procesos ──────────────────────────────────────────────────────
    def _asegurar(self) -> bool:
        """Arranca los procesos que falten; False si hay que dibujar aquí mismo."""
        if self.local:
            return False
        if not self._procs:
            self._procs = [None] * max(1, cuantos())
        for i, pr in enumerate(self._procs):
            if pr is not None and pr.vivo():
                continue
            if pr is not None:
                pr.parar()
                self._procs[i] = None
            if self._muertes >= REINTENTOS:
                break
            try:
                self._procs[i] = _Proc(i)
            except Exception:
                self._muertes = REINTENTOS
                break
        if not any(pr is not None for pr in self._procs):
            self.local = True
            self.parar()
            return False
        return True

    def _muere(self, i: int):
        pr = self._procs[i]
        if pr is None:
            return
        self._muertes += 1
        pr.parar()
        self._procs[i] = None
        self._asignada = {c: j for c, j in self._asignada.items() if j != i}
        if self._duenos:
            QtCore.QTimer.singleShot(0, self._despachar)

    def parar(self):
        self._timer.stop()
        for pr in self._procs:
            if pr is not None:
                pr.parar()
        self._procs = [None] * len(self._procs) if self._procs else []


_SERVIDOR: Optional[Servidor] = None


def servidor() -> Servidor:
    """El servidor de la aplicación. Si `PDFCAD_PROCESO` cambió (las pruebas lo cambian), uno
    nuevo con el modo que corresponde."""
    global _SERVIDOR
    activo = proceso.activo()
    if _SERVIDOR is not None and _SERVIDOR.con_proceso != activo:
        _SERVIDOR.parar()
        _SERVIDOR = None
    if _SERVIDOR is None:
        _SERVIDOR = Servidor()
        _SERVIDOR.con_proceso = activo
        app = QtCore.QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(_SERVIDOR.parar)
    return _SERVIDOR

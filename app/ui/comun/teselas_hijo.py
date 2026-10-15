"""teselas_hijo.py — El proceso que DIBUJA las teselas (sin Qt: el hijo no carga la interfaz).

Ver `teselas.py` y `teselas_servidor.py`. El hijo tiene abiertos los PDF que se ven (los lee a
memoria: no deja el archivo abierto, la ventana puede borrar sus temporales), con las mismas
capas apagadas que la ventana, y por hoja su lista de dibujo y las cajas de sus letras Type3
(`recorte_nitido.Hojas`). Atiende mensajes de la ventana por un `Pipe`:

  ("doc", token, fuente)        fuente = ("ruta", ruta, tamaño, mtime_ns) | ("datos", bytes)
  ("capas", token, firma, ons)  estado de cada capa (`layer_ui_configs` de la ventana); se
                                aplica al dibujar una tesela de esa firma
  ("pedir", [clave, …])         las teselas que faltan, en orden; REEMPLAZA a las anteriores
  ("calentar", token, firma, hoja)  preparar la lista de dibujo (y letras) sin esperar
  ("olvidar", token)            cerrar ese PDF
  None                          terminar

y contesta («t», clave, x, y, ancho, alto, stride, píxeles RGB) o («x», clave, motivo). Entre
tesela y tesela lee lo nuevo: una vista que ya se movió no hace esperar a la siguiente.
Clave = (token, firma, hoja, nivel, tx, ty).
"""
from __future__ import annotations

import os
import time
from collections import OrderedDict

MAX_DOCS = 6                 # PDF abiertos a la vez (el editor, el compositor y sus orígenes); el
                             # que se suelta y vuelve a hacer falta lo manda otra vez la ventana
MAX_HOJAS = 16               # listas de dibujo por PDF (piezas del compositor a la vista)
RECIENTE_S = 1.5             # una tesela recién enviada no se dibuja otra vez si se repite el pedido


class _Docs:
    def __init__(self):
        self.d: "OrderedDict[str, dict]" = OrderedDict()

    def abrir(self, token, fuente):
        import fitz
        from ui.comun.recorte_nitido import Hojas
        if token in self.d:
            return
        if fuente[0] == "ruta":
            _, ruta, tam, mtime = fuente
            st = os.stat(ruta)
            if st.st_size != tam or st.st_mtime_ns != mtime:
                raise OSError("el archivo cambió")
            with open(ruta, "rb") as f:
                datos = f.read()
        else:
            datos = fuente[1]
        doc = fitz.open(stream=datos, filetype="pdf")
        self.d[token] = {"doc": doc, "firma": None, "estados": {}, "hojas": Hojas(max_hojas=MAX_HOJAS)}
        while len(self.d) > MAX_DOCS:
            self._cerrar(next(iter(self.d)))

    def capas(self, token, firma, ons):
        e = self.d.get(token)
        if e is not None:
            e["estados"][firma] = ons

    def _aplicar(self, e, firma) -> bool:
        if e["firma"] == firma:
            return True
        ons = e["estados"].get(firma)
        if ons is None:
            return False
        doc = e["doc"]
        try:
            actual = {c["number"]: c["on"] for c in doc.layer_ui_configs()}
            for num, on in ons:
                if num in actual and bool(actual[num]) != bool(on):
                    doc.set_layer_ui_config(num, 0 if on else 2)
        except Exception:
            pass
        e["firma"] = firma
        e["hojas"].soltar()                  # la lista de dibujo guarda lo que se veía
        return True

    def hoja(self, token, firma, num):
        e = self.d.get(token)
        if e is None or not self._aplicar(e, firma):
            return None, None
        self.d.move_to_end(token)
        return e, e["doc"][num]

    def _cerrar(self, token):
        e = self.d.pop(token, None)
        if e is not None:
            e["hojas"].soltar()
            try:
                e["doc"].close()
            except Exception:
                pass

    olvidar = _cerrar


def _log(*partes):
    """Diagnóstico: con `PDFCAD_TESELAS_LOG=1` el hijo dice cuánto tarda cada cosa."""
    if os.environ.get("PDFCAD_TESELAS_LOG") == "1":
        import sys
        print("[teselas]", *partes, file=sys.stderr, flush=True)


def bucle(conns, tope_mb: int = 0):
    """Punto de entrada del proceso («spawn»): `conns` = (entrada, salida), dos `Pipe` de un
    sentido (un PDF grande que llega no frena las teselas que salen)."""
    from ui.comun import proceso_hijo
    from ui.comun import teselas as T
    proceso_hijo.bajar_prioridad()
    proceso_hijo.poner_tope(tope_mb)
    entrada, salida = conns
    docs = _Docs()
    st = {"pend": [], "calentar": [], "recientes": {}}

    def atender(msg) -> bool:
        if msg is None:
            return False
        tipo = msg[0]
        try:
            if tipo == "pedir":
                ahora = time.monotonic()
                rec = st["recientes"]
                for k in [k for k, t in rec.items() if ahora - t > RECIENTE_S]:
                    del rec[k]
                st["pend"] = [k for k in msg[1] if k not in rec]
            elif tipo == "doc":
                docs.abrir(msg[1], msg[2])
            elif tipo == "capas":
                docs.capas(msg[1], msg[2], msg[3])
            elif tipo == "calentar":
                if msg[1:] not in st["calentar"]:
                    st["calentar"].append(msg[1:])
            elif tipo == "olvidar":
                docs.olvidar(msg[1])
        except Exception as exc:              # un PDF que no abre: sus teselas fallarán
            _log("error", tipo, repr(exc))
            if tipo == "doc":
                salida.send(("d", msg[1], repr(exc)))
        return True

    while True:
        try:
            if not st["pend"] and not st["calentar"]:
                if not atender(entrada.recv()):
                    return
            while entrada.poll():
                if not atender(entrada.recv()):
                    return
        except (EOFError, OSError):
            return
        if st["pend"]:
            clave = st["pend"].pop(0)
            tok, firma, num, nivel, col, fila = clave
            try:
                e, page = docs.hoja(tok, firma, num)
                if page is None:
                    salida.send(("x", clave, "sin documento"))
                    continue
                t0 = time.perf_counter()
                pix = T.dibujar(e["hojas"], page, nivel, col, fila)
                _log("tesela", clave[2:], "%.3f s" % (time.perf_counter() - t0), "faltan", len(st["pend"]))
                if pix is None:
                    salida.send(("x", clave, "fuera de la hoja"))
                    continue
                salida.send(("t", clave, pix.x, pix.y, pix.width, pix.height, pix.stride, pix.samples))
                st["recientes"][clave] = time.monotonic()
            except MemoryError:
                try:
                    salida.send(("x", clave, "memoria"))
                except Exception:
                    pass
                return
            except (EOFError, OSError):
                return                        # la ventana se cerró
            except Exception as exc:
                _log("error", clave, repr(exc))
                try:
                    salida.send(("x", clave, repr(exc)))
                except Exception:
                    return
        elif st["calentar"]:
            tok, firma, num = st["calentar"].pop(0)
            try:
                t0 = time.perf_counter()
                e, page = docs.hoja(tok, firma, num)
                if page is not None:
                    e["hojas"].lista(page)
                    e["hojas"].cajas(page)
                _log("calentar", num, "%.2f s" % (time.perf_counter() - t0))
            except Exception as exc:
                _log("error calentar", repr(exc))

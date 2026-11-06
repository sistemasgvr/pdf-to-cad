"""Rótulos del plano en la ventana (pedido del usuario 2026-11-03): los MLeader (texto + guía) y los MText de los
mapas que reconoce `reconocimiento/recognition_anotaciones` quedan en `self.anotaciones` al importar (.digproj,
deshacer, respaldo del asistente) y el DXF los exporta (`exportar/dxf_anotaciones`).

IA → «Leer rótulos ilegibles con la IA…»: los rótulos cuya guía se ve pero cuyo texto no es texto del PDF (SHX
dibujado con trazos) se mandan, de a uno, con su recorte a un modelo con visión (`ia/anotaciones_ia`); lo que lee
con confianza alta o media queda como texto del rótulo (`fuente="ia"`), con deshacer. Corre en un hilo con la
tarjeta de avance y «Cancelar»; no traba la ventana.
"""
from ia import reporte_error as RE
import base64
import threading

from ui.ventana.ventana_comun import *  # noqa: F401,F403


class _SenalesAnot(QtCore.QObject):
    uno = QtCore.Signal(object, int, object)          # (token, índice, respuesta o str con el error)
    fin = QtCore.Signal(object)


class AnotacionesMixin:
    def _guardar_anotaciones(self, results) -> int:
        """Al importar: los rótulos de la hoja (la misma lista en cada utilidad) se suman a los del proyecto."""
        from nucleo import anotaciones as AN
        nuevas = next((list(r.anotaciones) for r in results if getattr(r, "anotaciones", None)), [])
        if not nuevas:
            return 0
        antes = len(getattr(self, "anotaciones", None) or [])
        self.anotaciones = AN.juntar(getattr(self, "anotaciones", None) or [], nuevas)
        return len(self.anotaciones) - antes

    # ── leer con la IA ──
    def _anot_imagen(self, a):
        """PNG (base64) de la zona del rótulo con su guía marcada, de la hoja de trabajo."""
        doc = getattr(self, "doc", None)
        if doc is None or not self.zoom:
            return None
        try:
            from hoja import recorte_diametro
            z = float(self.zoom)
            page = doc[getattr(self, "page_idx", 0)]
            guia = [(x / z, y / z) for x, y in ((a.get("guias") or [[]])[0] or [])]
            guia += [(x / z, y / z) for x, y in (a.get("puntas") or [])[:1]]
            caja = tuple(v / z for v in a["caja"])
            pts = guia if len(guia) >= 2 else [(caja[0], caja[3]), (caja[2], caja[3])]
            return base64.b64encode(recorte_diametro.recorte(page, pts, {"T": caja}, lado_px=768,
                                                             margen_pt=12.0)).decode("ascii")
        except Exception:                                  # noqa: BLE001 (sin imagen no se pregunta)
            return None

    def leer_anotaciones_con_ia(self):
        """IA → «Leer rótulos ilegibles con la IA…»."""
        from nucleo import anotaciones as AN
        pendientes = AN.ilegibles(getattr(self, "anotaciones", None) or [])
        if not pendientes:
            self.informar(_tr("Rótulos del plano"), _tr("No hay rótulos ilegibles: todos los rótulos con guía de "
                                                        "la hoja se leyeron del PDF."))
            return
        if getattr(self, "_anot_tok", None) is not None:
            return                                         # ya está leyendo
        from ia import proveedor as P
        cfg = P.Config.de(self._config_ia())
        prov = P.crear(cfg) if cfg.con_ia else None
        if prov is None or not prov.vision():
            self.informar(_tr("Rótulos del plano"), _tr("Para leer los rótulos ilegibles hace falta un modelo de IA "
                                                        "con visión (IA → Configurar IA…)."))
            return
        imagenes = {k: self._anot_imagen(self.anotaciones[k]) for k in pendientes}
        mem = self._ia_memoria()
        tok = object()
        self._anot_tok = tok
        self._anot_leidas = {}
        self._anot_senales = _SenalesAnot()
        self._anot_senales.uno.connect(self._anot_uno)
        self._anot_senales.fin.connect(self._anot_fin)
        self._anot_total = len(pendientes)
        self._anot_capa = _busy_mod.overlay_for(self)
        self._anot_capa.begin(_tr("Leyendo rótulos con la IA…"), cancel=self._anot_cancelar)
        from ia import anotaciones_ia as AI

        def correr():
            for n, k in enumerate(pendientes):
                if self._anot_tok is not tok:
                    break
                try:
                    r = AI.leer(prov, imagenes.get(k), mem, cancelado=lambda: self._anot_tok is not tok)
                except Exception as e:                      # noqa: BLE001 (ErrorIA, red)
                    r = RE.texto_corto(RE.armar(e, "Leer rótulos con la IA"))
                self._anot_senales.uno.emit(tok, k, r)
            self._anot_senales.fin.emit(tok)
        threading.Thread(target=correr, name="pdfcad-ia-anotaciones", daemon=True).start()

    def _anot_uno(self, tok, k, r):
        if tok is not getattr(self, "_anot_tok", None):
            return
        self._anot_leidas[k] = r
        try:
            self._anot_capa.step(detail=_tr("Rótulo {i} de {n}").format(i=len(self._anot_leidas), n=self._anot_total),
                                 done=len(self._anot_leidas), total=self._anot_total, pump=False)
        except Exception:                                  # noqa: BLE001
            pass

    def _anot_cancelar(self):
        self._anot_tok = None
        self._anot_terminar()

    def _anot_terminar(self):
        capa = getattr(self, "_anot_capa", None)
        if capa is not None:
            try:
                capa.end()
            except Exception:                              # noqa: BLE001
                pass
        self._anot_capa = None

    def _anot_fin(self, tok):
        if tok is not getattr(self, "_anot_tok", None):
            return
        self._anot_tok = None
        self._anot_terminar()
        from nucleo import anotaciones as AN
        leidas = {k: r for k, r in self._anot_leidas.items() if isinstance(r, dict) and r.get("texto")}
        errores = [r for r in self._anot_leidas.values() if isinstance(r, str)]
        if leidas:
            self._push()
            for k, r in leidas.items():
                if 0 <= k < len(self.anotaciones):
                    self.anotaciones[k] = AN.releer(self.anotaciones[k], r["texto"], "ia", r.get("confianza", ""))
            self._dirty = True
        quedan = len(AN.ilegibles(self.anotaciones))
        texto = _tr("La IA leyó {n} de {t} rótulos ilegibles; quedan {q} sin leer.").format(
            n=len(leidas), t=self._anot_total, q=quedan)
        if errores:
            texto += " " + _tr("La IA no respondió: {e}").format(e=errores[0])
        self.informar(_tr("Rótulos del plano"), texto)

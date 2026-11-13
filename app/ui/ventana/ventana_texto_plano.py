"""Texto del plano en el proyecto (`hoja.indice_texto`): se arma solo, se guarda y lo consulta la IA.

Pedido del usuario 2026-11-13: todo lo que dice el plano (calles, lugares, servicios, notas, rótulos) queda en el
proyecto y la IA lo usa al responder, sin mandarle todo: la app busca lo que viene al caso de cada pregunta
(`ia.texto_plano`). `Main.texto_plano` = {"clave", "version", "hojas", "lineas"} o None.

- Se arma en el proceso de trabajo «fondo» (lectura del PDF fuera de la ventana; ~0.1 s por hoja) cada vez que se
  carga una hoja (`_load_page`) y al abrir un proyecto que no lo trae o lo trae de otra hoja (`clave`).
- Va al .digproj como `texto_plano.json` APARTE del modelo (puede pesar MB: la copia automática no lo reescribe).
- No marca cambios: es un dato derivado del PDF, que va dentro del proyecto; si no se guarda, se rearma al abrir.
Clase mezcla de `Main`.
"""
import hashlib
import json
import os

from PySide6 import QtCore

from hoja import indice_texto as IT

ARCHIVO = "texto_plano.json"


class TextoPlanoMixin:
    def _texto_plano_clave(self):
        """Qué hoja es (PDF de origen, composición, hoja, zoom): un índice de OTRA hoja no vale."""
        if (getattr(self, "doc", None) is None or getattr(self, "blank_canvas", False)
                or self.canvas.pixmap_item is None):
            return None
        try:
            from reconocimiento import recognition_cache
            comp = recognition_cache.composition_signature(self.composite) if self.composite else ""
        except Exception:
            comp = repr(self.composite.to_dict()) if self.composite else ""
        # los PDF por su NOMBRE: los bytes de `sources/NNN.pdf` no son los del archivo original (se reescriben al
        # guardar) y con su huella el índice se rearmaba en cada apertura
        fuentes = (tuple(str(e.get("name", "")) for e in self.src_pdfs) if getattr(self, "src_pdfs", None)
                   else os.path.basename(getattr(self, "pdf_path", "") or ""))
        return hashlib.sha1(repr((comp, fuentes, int(self.page_idx), round(float(self.zoom or 1.0), 4),
                                  IT.VERSION)).encode("utf-8", "replace")).hexdigest()

    def _texto_plano_piezas(self):
        """[(rect pt, etiqueta)] de las piezas de una hoja compuesta (lo de fuera no se ve), o None."""
        comp = getattr(self, "composite", None)
        lay = getattr(self, "_composite_layout", None)
        if comp is None or not comp.pieces or not lay or len(comp.pieces) < 2:
            return None
        names = [e.get("name", "") for e in (self.src_pdfs or [])]
        single = len({p.source for p in comp.pieces}) == 1
        name0 = names[comp.pieces[0].source] if names and comp.pieces[0].source < len(names) else ""
        return [(tuple(float(v) for v in rect), f"{name0} · {label}" if single and name0 else str(label))
                for rect, label in lay]

    def _texto_plano_origen(self):
        names = [e.get("name", "") for e in (getattr(self, "src_pdfs", None) or [])]
        name = names[0] if names and names[0] else os.path.basename(getattr(self, "pdf_path", "") or "")
        return f"{name} · Hoja {int(self.page_idx) + 1}" if name else f"Hoja {int(self.page_idx) + 1}"

    def _texto_plano_pedir(self):
        """Arma el índice de la hoja de ahora si falta o es de otra hoja (en el proceso de trabajo)."""
        clave = self._texto_plano_clave()
        if clave is None:
            self.texto_plano = None
            return
        tp = getattr(self, "texto_plano", None)
        if tp and tp.get("clave") == clave:
            return
        if getattr(self, "_texto_plano_pendiente", None) == clave:
            return
        ruta = getattr(self, "work_pdf_path", None) or getattr(self, "pdf_path", None)
        if not ruta or not os.path.isfile(ruta):
            return
        args = (ruta, int(self.page_idx), float(self.zoom or 1.0), self._texto_plano_piezas(),
                self._texto_plano_origen())
        self._texto_plano_pendiente = clave
        from ui.comun import proceso
        if proceso.activo():
            t = proceso.Tarea("hoja.indice_texto:trabajo", args)
            t.terminado.connect(lambda r, e, clave=clave: self._texto_plano_listo(clave, r, e))
            self._texto_plano_tarea = t
            proceso.trabajador("fondo").enviar(t)
        else:                                          # pruebas (PDFCAD_PROCESO=0): aquí mismo
            try:
                self._texto_plano_listo(clave, IT.trabajo(*args), "")
            except Exception as e:                     # noqa: BLE001
                self._texto_plano_listo(clave, None, str(e))

    def _texto_plano_listo(self, clave, res, error):
        if getattr(self, "_texto_plano_pendiente", None) == clave:
            self._texto_plano_pendiente = None
        if error or not isinstance(res, dict):
            if error and error != "cancelado":
                try:
                    from nucleo import diagnostico
                    diagnostico.registrar(str(error), "Texto del plano")
                except Exception:
                    pass
            return
        if clave != self._texto_plano_clave():
            return                                     # mientras tanto se cargó otra hoja
        res["clave"] = clave
        self.texto_plano = res

    def _texto_plano_programar(self):
        """Después de cargar una hoja: armar el índice cuando la ventana quede libre."""
        QtCore.QTimer.singleShot(0, self, self._texto_plano_pedir)

    # ── .digproj ──
    def _texto_plano_entrada_zip(self):
        tp = getattr(self, "texto_plano", None)
        if not tp or not tp.get("lineas"):
            return []
        return [(ARCHIVO, json.dumps(tp, ensure_ascii=False, separators=(",", ":")))]

    def _texto_plano_de_zip(self, arch):
        datos = arch.get(ARCHIVO) if arch else None
        self.texto_plano = None
        if datos:
            try:
                tp = json.loads(datos.decode("utf-8") if isinstance(datos, (bytes, bytearray)) else datos)
                if isinstance(tp, dict) and tp.get("version") == IT.VERSION and isinstance(tp.get("lineas"), list):
                    self.texto_plano = tp
            except (ValueError, TypeError):
                self.texto_plano = None
        self._texto_plano_programar()                  # si es de otra hoja (o falta), se rearma

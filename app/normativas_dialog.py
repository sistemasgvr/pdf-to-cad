"""Ventana flotante «Normativas de diseño» (HTML en QtWebEngine + QWebChannel).

La página (`docs/normativas_ui.html`) no trae textos propios: todo lo que se ve
llega traducido desde aquí (`_TEXTOS`), junto con los colores del tema y el
estado (reglas, campos de cada tipo y resultados). La página llama al puente
(`PuenteNormas`) para activar/desactivar, cambiar valores, restablecer, quitar,
ir al plano e importar/exportar el Excel (`normativas_excel`); el puente guarda
el catálogo global, marca el proyecto y redibuja la ventana principal, que
devuelve los resultados nuevos (`refrescar`).

No modal: se puede dejar abierta mientras se dibuja; se refresca sola."""
from __future__ import annotations

import datetime
import json
import os

from PySide6 import QtCore, QtGui, QtWidgets

import normativas
import theme as _theme
from i18n import t as _tr, N_
from i18n_core import get_lang
from model import TIPOS as TIPOS_UTILIDAD, VERSION

_HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "normativas_ui.html")
_QS = ("pdf-to-cad", "app")
FUENTE_DEF, FUENTE_MIN, FUENTE_MAX = 17, 13, 26

# Textos de la página (clave = texto en español, como en el resto de la app).
_TEXTOS = {
    "titulo": N_("Normativas de diseño"),
    "texto_menor": N_("Reducir el tamaño del texto"),
    "texto_mayor": N_("Aumentar el tamaño del texto"),
    "resumen": N_("{a} de {t} reglas activas en este proyecto"),
    "fuera": N_("fuera de norma"),
    "nota": N_("Los valores valen para todos tus proyectos; activar o desactivar una regla solo cambia este proyecto."),
    "buscar": N_("Buscar regla…"),
    "importar": N_("Importar Excel"),
    "exportar": N_("Exportar Excel"),
    "categorias": N_("Categorías"),
    "incumplimientos": N_("Incumplimientos"),
    "sin_incumplimientos": N_("Todo cumple las normativas activas."),
    "activa": N_("Activa en este proyecto"),
    "obligatoria": N_("Obligatoria"),
    "recomendada": N_("Recomendada"),
    "importancia": N_("Importancia"),
    "fuente": N_("Fuente"),
    "referencias": N_("Referencias"),
    "notas": N_("Notas"),
    "texto_original": N_("Texto original"),
    "medido": N_("Medido desde"),
    "detalles": N_("Detalles"),
    "agregar": N_("Agregar"),
    "quitar": N_("Quitar {v}"),
    "quitar_regla": N_("Quitar esta regla"),
    "nuevo_angulo": N_("Nuevo ángulo en grados"),
    "grados": N_("grados"),
    "pies": N_("pies"),
    "restablecer": N_("Restablecer valores iniciales"),
    "modificada": N_("Valores cambiados"),
    "revisar": N_("Revisar"),
    "revisar_ayuda": N_("La conversión del Excel no entendió del todo esta regla: mira su texto original."),
    "ver_plano": N_("Ver en el plano"),
    "cumple": N_("✓ {n}"),
    "cumple_ayuda": N_("Cumple: {n} revisado(s)."),
    "incumple": N_("✗ {k} de {n}"),
    "nada": N_("Sin casos"),
    "pendiente": N_("Aún no se revisa en el plano"),
    "desactivada": N_("Desactivada"),
    "sin_resultados": N_("Ninguna regla coincide con la búsqueda."),
    "sin_escala": N_("El plano no tiene escala: no se pueden medir los accesorios. Fija la escala en la barra de estado."),
    "guardado": N_("Cambios guardados."),
}


def _utilidades():
    return [{"id": cod, "nombre": _tr(nombre)} for nombre, cod in TIPOS_UTILIDAD]


def _campo_valor(regla, campo):
    if campo.tipo == "utilidades":
        return list(regla.get("utilidades") or [])
    return (regla.get("params") or {}).get(campo.clave)


class PuenteNormas(QtCore.QObject):
    """Lo que la página puede pedir. Todo entra y sale como JSON (texto)."""

    cambio = QtCore.Signal(str)

    def __init__(self, win, parent=None):
        super().__init__(parent)
        self.win = win

    # ── estado completo que pinta la página ──
    def estado_dict(self):
        w = self.win
        res = getattr(w, "_normas_res", None) or {}
        lista = getattr(w, "_normas_lista", None) or []
        anexos = getattr(w, "normas_anexos", None) or {}
        refs = anexos.get("referencias") or {}
        notas = {n.get("id"): n.get("texto", "") for n in anexos.get("notas") or []}
        indice = {id(inc): n for n, (inc, _r) in enumerate(lista)}
        reglas = []
        for r in w.normas:
            tipo = normativas.TIPOS.get(r.get("tipo"))
            if tipo is None:
                continue
            p = r.get("params") or {}
            rr = res.get(r["id"])
            items = [{"i": indice.get(id(inc), -1), "texto": inc.mensaje}
                     for inc in (rr.incumplimientos if rr else [])]
            ref_txt = [f"{x}: {(refs.get(x) or {}).get('texto', '') if isinstance(refs.get(x), dict) else refs.get(x, '')}"
                       for x in p.get("referencias") or []]
            utils = r.get("utilidades") or []
            reglas.append({
                "id": r["id"], "categoria": tipo.categoria,
                "grupo": ", ".join(_tr(normativas.CONTRAS.get(u, u)) for u in utils),
                "titulo": normativas.titulo_de(r), "resumen": normativas.resumen_valor(r),
                "descripcion": _tr(r.get("descripcion", "")) or p.get("descripcion", ""),
                "fuente": _tr(r.get("fuente", "")), "tipo_nombre": _tr(tipo.nombre),
                "obligatoria": bool(r.get("obligatoria", True)),
                "activa": normativas.activa_en(r, w.normas_estado),
                "modificada": normativas.modificada(r), "base": normativas.es_base(r["id"]),
                "revisar": p.get("estado") == "Revisar",
                "detalle": {"texto_original": p.get("texto_original", ""), "medido": p.get("medido_desde", ""),
                            "referencias": ref_txt,
                            "notas": [f"{x}: {notas.get(x, '')}" for x in p.get("notas") or []]},
                "campos": [{"clave": c.clave, "tipo": c.tipo, "etiqueta": _tr(c.etiqueta),
                            "ayuda": _tr(c.ayuda) if c.ayuda else "", "min": c.minimo, "max": c.maximo,
                            "opciones": list(c.opciones), "opcional": c.opcional,
                            "valor": _campo_valor(r, c)} for c in tipo.campos],
                "resultado": {"evaluados": rr.evaluados if rr else 0, "items": items,
                              "evaluada": bool(rr and rr.activa), "pendiente": bool(rr and rr.pendiente)},
            })
        cats = [{"id": k, "nombre": _tr(v), "reglas": [r["id"] for r in reglas if r["categoria"] == k]}
                for k, v in normativas.CATEGORIAS.items()]
        activas = [r for r in reglas if r["activa"]]
        return {
            "idioma": get_lang(),
            "t": {k: _tr(v) for k, v in _TEXTOS.items()},
            "tema": _tema(),
            "fuente": _fuente(),
            "utilidades": _utilidades(),
            "categorias": [c for c in cats if c["reglas"]],
            "reglas": reglas,
            "sin_escala": not (w.scale and w.zoom),
            "resumen": {"activas": len(activas), "total": len(reglas),
                        "revisados": sum(r["resultado"]["evaluados"] for r in activas),
                        "fuera": len(lista)},
            "incumplimientos": [{"i": n, "texto": inc.mensaje, "obligatoria": bool(reg.get("obligatoria", True)),
                                 "regla": normativas.titulo_de(reg)} for n, (inc, reg) in enumerate(lista)],
        }

    def emitir(self):
        self.cambio.emit(json.dumps(self.estado_dict(), ensure_ascii=False))

    @QtCore.Slot(result=str)
    def estado(self):
        return json.dumps(self.estado_dict(), ensure_ascii=False)

    def _aplicado(self, guardar_global):
        w = self.win
        if guardar_global:
            try:
                normativas.guardar_catalogo(w.normas, anexos=getattr(w, "normas_anexos", None))
            except OSError as e:
                return _tr("No se pudo guardar: {e}").format(e=e)
        w._redraw()                  # re-evalúa, repinta etiquetas y llama a refrescar()
        self.emitir()
        return ""

    def _regla(self, rid):
        return next((r for r in self.win.normas if r["id"] == rid), None)

    @QtCore.Slot(str, bool, result=str)
    def activar(self, rid, on):
        r = self._regla(rid)
        if r is None:
            return _tr("Regla desconocida.")
        w = self.win
        if bool(on) == bool(r.get("activa", True)):
            w.normas_estado.pop(rid, None)          # igual que el catálogo: sin ajuste propio
        else:
            w.normas_estado[rid] = bool(on)
        w._dirty = True
        return self._aplicado(False)

    @QtCore.Slot(str, str, str, result=str)
    def cambiar(self, rid, clave, valor_json):
        r = self._regla(rid)
        if r is None:
            return _tr("Regla desconocida.")
        try:
            valor = json.loads(valor_json)
        except ValueError:
            return _tr("Valor no válido.")
        err = normativas.aplicar_cambio(r, clave, valor)
        if err:
            self.emitir()
            return err
        return self._aplicado(True)

    @QtCore.Slot(str, result=str)
    def restablecer(self, rid):
        normativas.restablecer(self.win.normas, rid)
        return self._aplicado(True)

    @QtCore.Slot(str, result=str)
    def quitar(self, rid):
        r = self._regla(rid)
        if r is None or normativas.es_base(rid):
            return _tr("Regla desconocida.")
        resp = QtWidgets.QMessageBox.question(
            self.win._normas_dlg or self.win, _tr("Quitar esta regla"),
            _tr("¿Quitar la regla «{r}»? Puedes volver a traerla importando el Excel.").format(
                r=normativas.titulo_de(r)))
        if resp != QtWidgets.QMessageBox.Yes:
            return ""
        normativas.quitar(self.win.normas, rid)
        self.win.normas_estado.pop(rid, None)
        return self._aplicado(True)

    @QtCore.Slot(int)
    def ir_a(self, n):
        self.win._normas_ir_a(n)

    @QtCore.Slot(int)
    def fuente(self, px):
        px = max(FUENTE_MIN, min(FUENTE_MAX, int(px)))
        QtCore.QSettings(*_QS).setValue("normas_font", px)

    # ── Excel ──
    def _padre(self):
        return getattr(self.win, "_normas_dlg", None) or self.win

    @QtCore.Slot(result=str)
    def exportar(self):
        from ui_common import DOWNLOADS
        nombre = "Normativas_{f}.xlsx".format(f=datetime.date.today().strftime("%Y-%m-%d"))
        ruta, _ = QtWidgets.QFileDialog.getSaveFileName(
            self._padre(), _tr("Exportar Excel"), os.path.join(DOWNLOADS, nombre), _tr("Excel (*.xlsx)"))
        return self.exportar_a(ruta) if ruta else ""

    def exportar_a(self, ruta):
        import normativas_simple
        try:
            normativas_simple.exportar(self.win.normas, getattr(self.win, "normas_anexos", None) or {},
                                      ruta, VERSION)
        except (OSError, PermissionError) as e:
            return _tr("No se pudo guardar: {e}").format(e=e)
        return _tr("Exportadas {n} reglas a {archivo}.").format(n=len(self.win.normas),
                                                                 archivo=os.path.basename(ruta))

    @QtCore.Slot(result=str)
    def importar(self):
        from ui_common import DOWNLOADS
        ruta, _ = QtWidgets.QFileDialog.getOpenFileName(
            self._padre(), _tr("Importar Excel"), DOWNLOADS, _tr("Excel (*.xlsx *.xlsm)"))
        return self.importar_de(ruta) if ruta else ""

    def importar_de(self, ruta, confirmar=True):
        """Lee la plantilla (o el Excel de «clearance tables»), enseña qué se va a
        importar y los errores por fila, y lo incorpora al catálogo."""
        import normativas_excel
        try:
            nuevas, anexos, errores, formato = normativas_excel.importar(ruta)
        except Exception as e:                       # archivo dañado, abierto en Excel…
            return _tr("No se pudo leer el archivo: {e}").format(e=e)
        if not nuevas:
            msg = "\n".join(f"{_tr('Fila')} {f}: {m}" if f else m for f, m in errores[:10]) \
                or _tr("El archivo no trae reglas.")
            QtWidgets.QMessageBox.warning(self._padre(), _tr("Importar Excel"), msg)
            return msg
        ids = {r["id"] for r in self.win.normas}
        n_nuevas = sum(1 for r in nuevas if r["id"] not in ids)
        revisar = sum(1 for r in nuevas if (r.get("params") or {}).get("estado") == "Revisar")
        texto = _tr("Se importarán {n} reglas: {a} nuevas y {b} que ya existían (se actualizan).").format(
            n=len(nuevas), a=n_nuevas, b=len(nuevas) - n_nuevas)
        if formato == "clearance":
            texto += "\n\n" + _tr("El archivo tiene el formato de tablas de los ingenieros: se convirtió a reglas. "
                                  "Exporta el Excel para revisarlo en la plantilla nueva.")
        if revisar:
            texto += "\n\n" + _tr("{n} quedan marcadas «Revisar» (no se entendieron del todo).").format(n=revisar)
        if errores:
            texto += "\n\n" + _tr("{n} fila(s) con error no se importan:").format(n=len(errores)) + "\n" + \
                "\n".join(f"• {_tr('Fila')} {f}: {m}" for f, m in errores[:10])
        if confirmar and QtWidgets.QMessageBox.question(self._padre(), _tr("Importar Excel"), texto) \
                != QtWidgets.QMessageBox.Yes:
            return ""
        w = self.win
        normativas.fusionar(w.normas, nuevas)
        actual = getattr(w, "normas_anexos", None) or {"referencias": {}, "notas": [], "documento": {}}
        actual.setdefault("referencias", {}).update(anexos.get("referencias") or {})
        por_id = {n.get("id"): n for n in actual.setdefault("notas", [])}
        for n in anexos.get("notas") or []:
            por_id[n.get("id")] = n
        actual["notas"] = list(por_id.values())
        if anexos.get("documento"):
            actual["documento"] = anexos["documento"]
        w.normas_anexos = actual
        err = self._aplicado(True)
        return err or _tr("Importadas {n} reglas.").format(n=len(nuevas))


def _fuente():
    try:
        return int(QtCore.QSettings(*_QS).value("normas_font", FUENTE_DEF))
    except (TypeError, ValueError):
        return FUENTE_DEF


def _tema():
    tk = _theme.tokens()
    claves = ("window", "surface", "surface_alt", "header", "input_bg", "text", "text_muted",
              "text_on_accent", "accent", "accent_hover", "danger", "focus", "success", "border",
              "border_soft", "hover")
    d = {k: getattr(tk, k) for k in claves}
    d["oscuro"] = _theme.is_dark()
    return d


def _qwebchannel_js():
    f = QtCore.QFile(":/qtwebchannel/qwebchannel.js")
    if f.open(QtCore.QIODevice.ReadOnly):
        try:
            return bytes(f.readAll()).decode("utf-8")
        finally:
            f.close()
    return ""


class NormativasDialog(QtWidgets.QDialog):
    def __init__(self, win):
        super().__init__(win)
        from PySide6.QtWebChannel import QWebChannel
        from PySide6.QtWebEngineWidgets import QWebEngineView
        self.win = win
        self.setWindowTitle(_tr("Normativas de diseño"))
        self.setWindowFlag(QtCore.Qt.WindowMaximizeButtonHint, True)
        self.setModal(False)
        self.resize(1080, 760)
        lay = QtWidgets.QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0)
        self.view = QWebEngineView(self)
        self.view.setContextMenuPolicy(QtCore.Qt.NoContextMenu)
        lay.addWidget(self.view)
        self.puente = PuenteNormas(win, self)
        self.canal = QWebChannel(self)
        self.canal.registerObject("puente", self.puente)
        self.view.page().setWebChannel(self.canal)
        self._timer = QtCore.QTimer(self); self._timer.setSingleShot(True); self._timer.setInterval(250)
        self._timer.timeout.connect(self.puente.emitir)
        self._cargar()
        _theme.THEME_BUS.changed.connect(lambda *_: self.refrescar())
        QtGui.QShortcut(QtGui.QKeySequence("Esc"), self, activated=self.close)

    def _cargar(self):
        try:
            with open(_HTML, encoding="utf-8") as f:
                html = f.read()
        except OSError:
            html = "<p>normativas_ui.html</p>"
        html = html.replace("/*QWEBCHANNEL*/", _qwebchannel_js())
        self.view.setHtml(html, QtCore.QUrl("qrc:///"))

    def refrescar(self):
        """Pide a la página que se repinte (diferido: agrupa redibujos seguidos)."""
        self._timer.start()


def abrir(win):
    """Abre (o trae al frente) la ventana de normativas de `win`."""
    dlg = getattr(win, "_normas_dlg", None)
    if dlg is None:
        try:
            dlg = NormativasDialog(win)
        except ImportError:
            QtWidgets.QMessageBox.warning(win, _tr("Normativas de diseño"),
                                          _tr("Falta el componente de navegador integrado (QtWebEngine)."))
            return None
        win._normas_dlg = dlg
    dlg.show(); dlg.raise_(); dlg.activateWindow()
    dlg.refrescar()
    return dlg


def resumen_estado(win):
    """Texto corto para la barra de estado ('' si todo cumple)."""
    lista = getattr(win, "_normas_lista", None) or []
    if not lista:
        return ""
    return "✗ " + _tr("{n} fuera de normativa").format(n=len(lista))

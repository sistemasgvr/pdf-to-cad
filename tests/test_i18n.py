"""test_i18n.py — cobertura y estructura de la traducción ES → EN.

Recorre el AST de todos los módulos de app/ y exige que:
  - toda clave que llega a ``t()`` / ``bind()`` / ``bind_item()`` / ``N_()`` sea
    una constante (nunca un f-string ni una concatenación) y esté traducida;
  - ningún texto visible (setText, QLabel, QMessageBox, …) quede sin envolver;
  - las traducciones conserven los marcadores ``{x}`` y los saltos de línea;
  - el diccionario no arrastre claves que ya nadie usa;
  - las tablas de datos que se muestran (utilidades, materiales, historial…)
    estén traducidas, y el manual exista en ambos idiomas.
Además comprueba en vivo que ``bind`` re-traduce al cambiar el idioma.
"""
import ast
import os
import re

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import i18n  # noqa: E402
import i18n_core  # noqa: E402

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
EN = i18n.TRANSLATIONS["en"]
DATA_FILES = {"i18n_en.py", "i18n_en_changelog.py"}
MOTOR = {"i18n.py", "i18n_core.py"}

# Textos que se muestran igual en ambos idiomas (filtros de archivo, siglas).
INVARIANTES = {"Excel", "DWG", "Error", "OK", "PDF (*.pdf)", "DXF (*.dxf)", "Civil 3D:"}

T_NAMES = {"t", "_tr", "_t", "tr_text", "N_"}
KEY_ARG = {"bind": 2, "_bind": 2, "bind_item": 1, "_bind_item": 1}
# Helpers locales de Main que reciben una clave y acaban en _bind.
LOCAL_HELPERS = {"_menu": 1, "_act": 1, "_page": 0, "tact": 1}

CTORS = {"QLabel", "QPushButton", "QCheckBox", "QRadioButton", "QGroupBox", "QAction",
         "QToolButton", "QMenu", "QTableWidgetItem", "QListWidgetItem", "QTreeWidgetItem",
         "QProgressDialog", "QCommandLinkButton"}
SETTERS = {"setText", "setToolTip", "setStatusTip", "setWhatsThis", "setWindowTitle",
           "setTitle", "setPlaceholderText", "setSuffix", "setPrefix", "addItem",
           "insertItem", "setItemText", "addTab", "insertTab", "setTabText", "addMenu",
           "showMessage", "setSpecialValueText", "setLabelText", "setInformativeText",
           "setDetailedText", "setButtonText", "setHtml", "setPlainText", "setTabToolTip",
           "setItemToolTip", "setCancelButtonText", "addAction", "setAccessibleName",
           "_info", "_busy", "_warn", "_show_html", "_set_status", "_msg", "_toast"}
FIRST_ARG = {"addRow", "addButton", "addWidget"}
LISTS = {"setHorizontalHeaderLabels", "setVerticalHeaderLabels", "setHeaderLabels", "addItems"}
STATIC = {"QMessageBox": ({"information", "warning", "critical", "question", "about"}, slice(1, 3)),
          "QInputDialog": ({"getText", "getDouble", "getInt", "getItem", "getMultiLineText"}, slice(1, 3))}
FILE_DIALOG = {"getOpenFileName", "getSaveFileName", "getExistingDirectory", "getOpenFileNames"}
KW_TEXT = {"text", "toolTip", "title", "windowTitle", "placeholderText"}


def _es_texto(s):
    """¿Tiene palabras? Se ignoran marcado HTML/CSS, colores y los invariantes."""
    if s in INVARIANTES or re.fullmatch(r"#[0-9a-fA-F]{3,8}", s):
        return False
    s = re.sub(r"<[^>]*>", " ", s)
    if "<" in s or "style" in s:
        s = re.sub(r"[\w-]+\s*:\s*[^;'\"]*;?", " ", s)
    return bool(re.search(r"[A-Za-zÁÉÍÓÚáéíóúñÑ]{2,}", s))


def _nombre(call):
    f = call.func
    if isinstance(f, ast.Name):
        return f.id, None
    if isinstance(f, ast.Attribute):
        b = f.value
        return f.attr, (b.id if isinstance(b, ast.Name) else getattr(b, "attr", None))
    return None, None


I18N_MODS = (None, "i18n", "_i18n", "i18n_core")


class _Auditor(ast.NodeVisitor):
    def __init__(self, path):
        self.path = path
        self.claves, self.sin_traducir, self.dinamicas, self.sin_envolver = set(), [], [], []

    def _donde(self, node, txt):
        return f"{self.path}:{node.lineno}: {txt[:100]!r}"

    def _clave(self, call):
        n, b = _nombre(call)
        if b not in I18N_MODS:
            return None
        if n in T_NAMES:
            return call.args[0] if call.args else None
        if n in KEY_ARG and len(call.args) > KEY_ARG[n]:
            return call.args[KEY_ARG[n]]
        if b is None and n in LOCAL_HELPERS and len(call.args) > LOCAL_HELPERS[n]:
            return call.args[LOCAL_HELPERS[n]]
        return None

    def _revisar_clave(self, a, call):
        if isinstance(a, (ast.List, ast.Tuple)):
            for e in a.elts:
                self._revisar_clave(e, call)
        elif isinstance(a, ast.IfExp):
            self._revisar_clave(a.body, call)
            self._revisar_clave(a.orelse, call)
        elif isinstance(a, ast.Constant) and isinstance(a.value, str):
            self.claves.add(a.value)
            if a.value not in EN and _es_texto(a.value):
                self.sin_traducir.append(self._donde(call, a.value))
        elif isinstance(a, (ast.JoinedStr, ast.BinOp)):
            # La clave debe ser una plantilla fija: t("… {x}").format(x=…).
            self.dinamicas.append(self._donde(call, ast.unparse(a)))

    def _revisar_visible(self, a, call):
        if isinstance(a, ast.IfExp):
            self._revisar_visible(a.body, call)
            self._revisar_visible(a.orelse, call)
        elif isinstance(a, ast.BoolOp):
            for v in a.values:
                self._revisar_visible(v, call)
        elif isinstance(a, ast.Subscript) and isinstance(a.value, ast.Dict):
            for v in a.value.values:
                self._revisar_visible(v, call)
        elif isinstance(a, ast.Call) and isinstance(a.func, ast.Attribute):
            base = a.func.value
            if a.func.attr == "get" and isinstance(base, ast.Dict):
                for v in base.values:
                    self._revisar_visible(v, call)
            elif (a.func.attr == "format" and isinstance(base, ast.Constant)
                  and isinstance(base.value, str) and _es_texto(base.value)):
                self.sin_envolver.append(self._donde(call, base.value))
        elif isinstance(a, ast.Constant) and isinstance(a.value, str) and _es_texto(a.value):
            self.sin_envolver.append(self._donde(call, a.value))
        elif isinstance(a, ast.JoinedStr):
            fijo = "".join(v.value for v in a.values if isinstance(v, ast.Constant))
            if _es_texto(fijo):
                self.sin_envolver.append(self._donde(call, ast.unparse(a)))
        elif isinstance(a, ast.BinOp):
            partes = list(ast.walk(a))
            traducida = any(isinstance(p, ast.Call) and self._clave(p) is not None for p in partes)
            if not traducida and any(isinstance(p, ast.Constant) and isinstance(p.value, str)
                                     and _es_texto(p.value) for p in partes):
                self.sin_envolver.append(self._donde(call, ast.unparse(a)))

    def visit_Call(self, node):
        clave = self._clave(node)
        if clave is not None:
            self._revisar_clave(clave, node)
        else:
            n, b = _nombre(node)
            cands = []
            if n in CTORS or n in SETTERS:
                cands = list(node.args)
            elif n in FIRST_ARG:
                cands = node.args[:1]
            elif n in LISTS and node.args and isinstance(node.args[0], (ast.List, ast.Tuple)):
                cands = list(node.args[0].elts)
            elif b in STATIC and n in STATIC[b][0]:
                cands = node.args[STATIC[b][1]]
            elif b == "QFileDialog" and n in FILE_DIALOG:
                cands = [node.args[i] for i in (1, 3) if len(node.args) > i]
            cands += [k.value for k in node.keywords if k.arg in KW_TEXT]
            for c in cands:
                self._revisar_visible(c, node)
        self.generic_visit(node)


def _modulos():
    for root, _dirs, files in os.walk(APP):
        if "__pycache__" in root:
            continue
        for f in files:
            if f.endswith(".py") and f not in DATA_FILES | MOTOR:
                p = os.path.join(root, f)
                yield os.path.relpath(p, APP), ast.parse(open(p, encoding="utf-8").read())


@pytest.fixture(scope="module")
def auditoria():
    total = _Auditor("")
    constantes = set()
    for rel, tree in _modulos():
        a = _Auditor(rel)
        a.visit(tree)
        total.claves |= a.claves
        total.sin_traducir += a.sin_traducir
        total.dinamicas += a.dinamicas
        total.sin_envolver += a.sin_envolver
        constantes |= {n.value for n in ast.walk(tree)
                       if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    total.constantes = constantes
    return total


def test_toda_clave_esta_traducida(auditoria):
    assert not auditoria.sin_traducir, "Sin traducción en i18n_en.py:\n" + "\n".join(auditoria.sin_traducir)


def test_claves_son_plantillas_fijas(auditoria):
    assert not auditoria.dinamicas, (
        "Clave armada en tiempo de ejecución (usar t('… {x}').format(x=…)):\n"
        + "\n".join(auditoria.dinamicas))


def test_textos_visibles_envueltos(auditoria):
    assert not auditoria.sin_envolver, "Texto visible sin t()/bind():\n" + "\n".join(auditoria.sin_envolver)


def test_sin_claves_muertas(auditoria):
    muertas = [k for k in EN if k not in auditoria.constantes]
    assert not muertas, "Claves que ya no usa ningún módulo:\n" + "\n".join(map(repr, muertas))


def test_claves_sin_espaciado_de_borde():
    # El espaciado de maquetación va fuera de la clave: "  " + t("Guardar").
    malas = [k for k in EN if k != k.strip(" \n")]
    assert not malas, malas


@pytest.mark.parametrize("es", sorted(EN))
def test_traduccion_conserva_formato(es):
    en = EN[es]
    assert en.strip(), f"traducción vacía: {es!r}"
    assert sorted(re.findall(r"\{[^{}]*\}", es)) == sorted(re.findall(r"\{[^{}]*\}", en)), es
    assert es.count("\n") == en.count("\n"), es


def test_tablas_de_datos_traducidas():
    import model
    import pdf_layers
    textos = ([label for label, _layer in model.TIPOS]
              + [label for _oid, label in model.LEADER_ORIENT]
              + list(model.PIPE_MATERIALS)
              + [label for _k, label in pdf_layers.UTILITIES]
              + [txt for _v, items in model.CHANGELOG for _k, txt in items])
    faltan = [x for x in textos if x not in EN]
    assert not faltan, faltan


def test_modulos_puros_traducen_sin_qt():
    # La lógica pura traduce con i18n_core (sin Qt); i18n.py es la capa de UI.
    for nombre in ("i18n_core.py", "i18n_en.py", "i18n_en_changelog.py", "duct_bank.py",
                   "recognition.py", "civil_catalog.py", "composite.py"):
        src = open(os.path.join(APP, nombre), encoding="utf-8").read()
        assert "PySide6" not in src, nombre
        assert not re.search(r"^\s*(import i18n\b|from i18n import)", src, re.M), nombre


def test_manual_en_ambos_idiomas():
    for lang in i18n.SUPPORTED_LANGS:
        assert os.path.isfile(os.path.join(APP, "docs", f"manual.{lang}.html")), lang


@pytest.fixture
def qapp():
    from PySide6 import QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    previo = i18n.get_lang()
    yield app
    i18n_core._current_lang = previo     # sin set_lang: no tocar QSettings del usuario
    i18n.retranslate_all()


def test_bind_retraduce_en_vivo(qapp, monkeypatch):
    from PySide6 import QtWidgets
    monkeypatch.setattr(i18n, "_settings", lambda: type("S", (), {"setValue": lambda *a: None})())
    i18n_core._current_lang = "es"
    lbl = i18n.bind(QtWidgets.QLabel(), "setText", "Utilidades", pre="▸ ")
    combo = QtWidgets.QComboBox()
    i18n.bind_item(combo, "Horizontal", "h")
    tip = i18n.bind(QtWidgets.QLabel(), "setToolTip", "Lienzo {n} · 1\"={e:g}'", fmt={"n": "A4", "e": 20})
    assert lbl.text() == "▸ Utilidades"

    i18n.set_lang("en")
    assert lbl.text() == "▸ " + EN["Utilidades"]
    assert combo.itemText(0) == EN["Horizontal"] and combo.itemData(0) == "h"
    assert tip.toolTip() == EN["Lienzo {n} · 1\"={e:g}'"].format(n="A4", e=20)

    i18n.set_lang("es")
    assert lbl.text() == "▸ Utilidades"


def test_listas_del_panel_derecho_se_traducen(qapp, monkeypatch):
    # Las listas muestran el TIPO traducido, nunca el código interno de la capa
    # («AGUA», «DRENAJE»…), y se rehacen solas al cambiar el idioma.
    from app_window import Main
    import model
    monkeypatch.setattr(i18n, "_settings", lambda: type("S", (), {"setValue": lambda *a: None})())
    i18n_core._current_lang = "es"
    w = Main()
    w.pipes = [{"layer": capa, "pts": [(0, 0), (10, 0)], "name": ""} for _lbl, capa in model.TIPOS]
    w.leaders = [{"orient": "h", "pts": [(0, 0), (5, 5)]}]
    w._refresh_lists()
    filas = [w.pipe_list.item(i).text() for i in range(w.pipe_list.count())]
    assert filas[0].startswith("1. Agua")

    i18n.set_lang("en")
    filas = [w.pipe_list.item(i).text() for i in range(w.pipe_list.count())]
    for (lbl, capa), fila in zip(model.TIPOS, filas):
        assert capa not in fila, fila
        assert EN[lbl].split(" (")[0] in fila, fila
    assert "vért." not in " ".join(filas)
    assert w.sleader_list.item(0).text() == EN["{n}. Leader {orientacion}"].format(
        n=1, orientacion=EN["Horizontal"].lower())
    i18n.set_lang("es")
    w.close()

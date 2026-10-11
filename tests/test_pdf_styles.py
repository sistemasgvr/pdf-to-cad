import fitz

from hoja import pdf_layers, pdf_styles
from reconocimiento import recognition as rec


def test_flat_styles_distinguish_dash_fill_and_width_and_survive_reopen(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    page.draw_line((40, 40), (200, 40), width=.73)
    page.draw_line((40, 60), (200, 60), width=.73)
    page.draw_line((40, 80), (200, 80), width=.73, dashes="[4 2] 0")
    page.draw_line((40, 100), (200, 100), width=.36)
    page.draw_rect((40, 120, 70, 140), color=None, fill=(0, 0, 0))
    layers = pdf_layers.page_layers(doc, 0)
    assert len(layers) == 4
    assert layers[0]["path_count"] == 2
    assert all(L["source"] == "style" for L in layers)
    names = {L["name"] for L in layers}
    pdf_layers.set_hidden(doc, names)
    assert all(not L["on"] for L in pdf_layers.page_layers(doc, 0))
    target = tmp_path / "flat.pdf"
    doc.save(target)
    with fitz.open(target) as reopened:
        assert {L["name"] for L in pdf_layers.page_layers(reopened, 0)} == names
    pdf_layers.set_hidden(doc, ())
    assert pdf_layers.hidden_layers(doc) == set()


def test_native_ocgs_keep_original_rows_and_drawings():
    doc = fitz.open()
    oc = doc.add_ocg("C-WATR-UNGD-E")
    page = doc.new_page()
    page.draw_line((30, 40), (250, 40), oc=oc)
    page.draw_line((30, 60), (250, 60))
    assert [L["name"] for L in pdf_layers.page_layers(doc, 0)] == ["C-WATR-UNGD-E"]
    assert not any((d.get("layer") or "").startswith(pdf_styles.PREFIX)
                   for d in pdf_styles.drawings(page))


def test_style_roles_and_hidden_layers_reach_recognition(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    page.draw_line((40, 50), (250, 50), width=.73)
    page.draw_line((40, 90), (250, 90), width=.36)
    target = tmp_path / "flat.pdf"
    doc.save(target)
    layers = pdf_layers.page_layers(doc, 0)
    chosen = next(L["name"] for L in layers if "0.73 pt" in L["short"])
    roles = {rec.ROLE_LINEAS: [chosen], rec.ROLE_BUZONES: []}
    result = rec.recognize_page(target, utility="AGUA", layer_roles=roles, zoom=1,
                                scale_ft_per_pt=1)
    assert result.drawable
    assert {p.layer_ocg for p in result.polylines} == {chosen}
    assert all(not p.abandoned for p in result.polylines)
    hidden = rec.recognize_page(target, utility="AGUA", layer_roles=roles,
                               hidden_ocgs=[chosen], zoom=1, scale_ft_per_pt=1)
    assert not hidden.drawable


def test_image_only_page_does_not_invent_vector_layers():
    doc = fitz.open()
    page = doc.new_page()
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 10, 10), False)
    pix.clear_with(200)
    page.insert_image(page.rect, pixmap=pix)
    assert pdf_layers.page_layers(doc, 0) == []


def test_flat_sheet_ui_allows_utility_selection_and_style_highlighting():
    from PySide6 import QtWidgets
    from ui.asistente.layer_dialog import SheetLayersDialog
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    doc = fitz.open()
    page = doc.new_page()
    page.draw_line((40, 50), (250, 50), width=.73)
    dlg = SheetLayersDialog(None, doc, 0)
    try:
        # sin estilo asignado no hay nada que reconocer: «Continuar» apagado con la guía
        assert not any(cb.isEnabled() for cb in dlg._recog_checks.values())
        assert not dlg.btn_ok.isEnabled()
        strong, _, _ = dlg._focus_sets({"layers": [dlg._layers[0]["name"]]})
        assert sum(len(v) for v in strong.values()) == 1
        name = dlg._layers[0]["name"]
        dlg.tree.setCurrentItem(dlg._items_by_name[name][0])
        dlg.assignment_utility.setCurrentIndex(dlg.assignment_utility.findData("AGUA"))
        assert dlg._recog_checks["AGUA"].isEnabled() and dlg.btn_ok.isEnabled()
        assert not dlg._recog_checks["ALCANTARILLADO"].isEnabled()
        assert dlg.recognition_utilities() == ("AGUA",)
    finally:
        dlg._timer.stop()
        dlg._stop_legend()
        dlg.deleteLater()
        app.processEvents()
        doc.close()


def test_direct_assignment_regroups_and_reaches_recognition(tmp_path):
    from PySide6 import QtWidgets
    from ui.asistente.layer_dialog import SheetLayersDialog
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    doc = fitz.open()
    for _ in range(2):
        doc.new_page().draw_line((40, 50), (250, 50), width=.73)
    target = tmp_path / "direct.pdf"
    doc.save(target)
    dlg = SheetLayersDialog(None, doc, 0)
    try:
        name = dlg._layers[0]['name']
        dlg.tree.setCurrentItem(dlg._items_by_name[name][0])
        dlg.assignment_utility.setCurrentIndex(dlg.assignment_utility.findData("AGUA"))
        assert dlg.group_item("AGUA").childCount() == 1
        assert dlg.roles_by_utility()["AGUA"][rec.ROLE_LINEAS] == [name]
        dlg._load_sheet(1)
        assert dlg._layers[0]['utility'] == "AGUA"
        result = rec.recognize_page(target, utility="AGUA", page_index=1,
            zoom=1, scale_ft_per_pt=1, layer_roles=dlg.roles_by_utility()["AGUA"])
        assert result.drawable
        dlg.tree.setCurrentItem(dlg._items_by_name[name][0])
        dlg.assignment_utility.setCurrentIndex(dlg.assignment_utility.findData("ALCANTARILLADO"))
        assert dlg.roles_by_utility()["AGUA"][rec.ROLE_LINEAS] == []
        assert dlg.roles_by_utility()["ALCANTARILLADO"][rec.ROLE_LINEAS] == [name]
        dlg.assignment_role.setCurrentIndex(dlg.assignment_role.findData(rec.ROLE_BUZONES))
        assert dlg.roles_by_utility()["ALCANTARILLADO"][rec.ROLE_BUZONES] == [name]
        dlg.assignment_utility.setCurrentIndex(dlg.assignment_utility.findData("OTRAS"))
        assert all(name not in names for roles in dlg.roles_by_utility().values() for names in roles.values())
    finally:
        dlg._timer.stop()
        dlg._stop_legend()
        dlg.deleteLater()
        app.processEvents()
        doc.close()


def test_role_table_rows_fit_themed_controls(tmp_path, monkeypatch):
    from PySide6 import QtWidgets
    from ui.comun import theme
    from ui.asistente.recognition_dialog import LayerRolesDialog
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    previous = app.styleSheet()
    monkeypatch.setattr(theme, "_arrow_dir", str(tmp_path))
    monkeypatch.setattr(theme, "save_preference", lambda name: None)
    theme.apply_theme(app, "dark")
    dlg = LayerRolesDialog(None, [dict(name=f"layer-{i}", short=f"Capa {i}", path_count=i + 1)
                                  for i in range(12)], utility="AGUA")
    try:
        dlg.show()
        app.processEvents()
        for row in range(dlg.table.rowCount()):
            combo = dlg.table.cellWidget(row, 2)
            assert dlg.table.rowHeight(row) >= combo.sizeHint().height() + 6
            assert dlg.table.visualRect(dlg.table.model().index(row, 2)).height() >= combo.height()
    finally:
        dlg.close()
        dlg.deleteLater()
        app.setStyleSheet(previous)


def test_adjust_roles_dialog_preserves_direct_assignment():
    from PySide6 import QtWidgets
    from ui.asistente.recognition_dialog import LayerRolesDialog
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    current = {rec.ROLE_LINEAS: ["style-layer"], rec.ROLE_BUZONES: []}
    dlg = LayerRolesDialog(None, [dict(name="style-layer", short="Negro 0.38 pt", path_count=279)],
                           utility="AGUA", current_roles=current)
    try:
        assert dlg.roles() == current
    finally:
        dlg.deleteLater()
        app.processEvents()

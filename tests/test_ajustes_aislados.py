"""Las pruebas no tocan los ajustes reales de Windows (`conftest._ajustes_de_pruebas_aparte`)."""
from PySide6 import QtCore
from PySide6.QtCore import QSettings


def test_qsettings_de_la_app_van_a_un_archivo_temporal():
    for ajustes in (QSettings("pdf-to-cad", "app"), QtCore.QSettings("pdf-to-cad", "vista3d")):
        assert ajustes.format() == QSettings.IniFormat
        assert "pdfcad_ajustes" in ajustes.fileName()

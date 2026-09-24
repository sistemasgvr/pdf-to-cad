"""Nombres de capa del estándar BOE/NCS («CADD Standards» del Bureau of
Engineering de Los Ángeles, §8.1) además de las variantes de los planos APDU
que ya se reconocían. Lo nuevo SUMA: ninguna capa de los PDF de prueba cambia
de clasificación (verificado con las 1182 capas de DU06/DU08/DU10/LABOE)."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (os.path.join(ROOT, "app"), ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

import recognition as rec  # noqa: E402
import xdata  # noqa: E402

LINE_D = rec.utility_line_kind("DRENAJE")
LINE_E = rec.utility_line_kind("ELECTRICO")


@pytest.mark.parametrize("name,kind", [
    # lo que ya se reconocía (planos APDU): igual que antes
    ("PS89616000-A1-UD-REF-EXIST_SD|C-STRM-UNGD-E", LINE_D),
    ("C-STRM-UNGD-E-NPLT", LINE_D),
    ("C-STRM-UNGD-WALL-N", None), ("C-STRM-UNGD-CASE-N", None), ("C-STRM-UNGD-STRC-N", None),
    ("C-STRM-STRC-N", "structure"), ("C-STRM-CTCH-BASN-E", "structure"), ("V-STRM-MANH", "structure"),
    ("C-STRM-ANNO-TEXT-N", None), ("C-WATR-UNGD-E-DSTRM", None),
    # estándar BOE: underground UGND, piping, manhole, headwall
    ("C-STRM-UGND-N", LINE_D), ("C-STRM-UGND", LINE_D), ("C-STRM-PIPE", LINE_D),
    ("C-STRM-PIPE-RCON-E", LINE_D), ("C-STRM-PIPE-CMTL", LINE_D),
    ("C-STRM-MHOL-N", "structure"), ("C-STRM-HWAL", "structure"),
    ("C-STRM-PROF", None), ("C-STRM-STAN", None), ("C-STRM-UGND-TEXT", None),
    # disciplina de nivel 2 (CU = Civil Utilities) y relleno «~»
    ("CU-STRM-UGND-N", LINE_D), ("CU-STRM-MHOL", "structure"), ("XREF|CU-STRM-PIPE~-E", LINE_D),
])
def test_drenaje(name, kind):
    assert rec.classify_ocg(name, "DRENAJE") == kind


@pytest.mark.parametrize("name,kind", [
    ("C-ELEC-UNGD-E", LINE_E), ("C-ELEC-UGND-N__UA2-3", LINE_E), ("C-ELEC-3MI-UGND-N", LINE_E),
    ("C-ELEC-UNGD-WALL-N", None), ("C-ELEC-VALT-E", "structure"),
    ("CU-ELEC-UGND-N", LINE_E), ("C-ELEC-MHOL-E", "structure"), ("CU-ELEC-VALT", "structure"),
])
def test_electrico(name, kind):
    assert rec.classify_ocg(name, "ELECTRICO") == kind


def test_nombre_normalizado():
    assert rec.standard_short_name("XR|CU-GAS~-PIPE-E") == "C-GAS-PIPE-E"
    assert rec.standard_short_name("C-STRM-UNGD-N") == "C-STRM-UNGD-N"
    assert rec.standard_short_name("UA-FOO") == "UA-FOO"          # U: disciplina no usada → no se toca


@pytest.mark.parametrize("name,field,value", [
    ("CU-STRM-UGND-N", xdata.F_DISC, "CU — Civil – utilidades"),
    ("CX-STRM-UGND", xdata.F_DISC, "CX — Civil (subconjunto X)"),
    ("B-SOIL-BORE", xdata.F_DISC, "B — Geotecnia"),
    ("W-POWR-UGND-E", xdata.F_DISC, "W — Distribución de energía"),
    ("C-GAS~-PIPE-E", xdata.F_SYSTEM, "GAS — Gas"),
    ("C-SSWR-PIPE-RCON-2", xdata.F_STATUS, "2 — Fase 2"),
    ("C-SSWR-PIPE-RCON-2", xdata.F_MODS, "PIPE-RCON (tubería, concreto reforzado)"),
    ("C-SSWR-FORC-M", xdata.F_STATUS, "M — A retirar"),
    ("C-STRM-PIPE-X", xdata.F_STATUS, "X — Fuera de contrato"),
    ("C-ELEC-UGND-N__UA2-3", xdata.F_STATUS, "N — Nueva (obra nueva)"),     # el «3» del paquete no es fase
    ("C-ELEC-UGND-N__UA2-3", xdata.F_MODS, "__UA2-3 (paquete UA2-3)"),
    ("C-ROAD-A001-IDEN", xdata.F_MODS, "A001-IDEN (vista A001, identificación)"),
    ("C-SSWR-UNDG-SCRN-N", xdata.F_LOCATION, "UNDG — Subterránea"),
])
def test_datos_extendidos_segun_el_estandar(name, field, value):
    assert xdata.parse_layer(name).get(field) == value

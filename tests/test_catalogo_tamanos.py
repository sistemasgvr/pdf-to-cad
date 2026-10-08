"""Agregar un tamaño a una familia del catálogo de Civil 3D (catalogo_tamanos).

Todo sobre un ProgramData SINTÉTICO en tmp_path (nunca el catálogo real):
C3D 2025 en español y C3D 2027 en inglés, con una tubería por FILAS, un buzón
por LISTAS y una familia de PRESIÓN (SQLite)."""
import os
import sqlite3
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(HERE, "..", "app"), os.path.join(HERE, "..")]

from catalogo import catalogo_tamanos as T          # noqa: E402
from catalogo import civil_catalog as cc            # noqa: E402

TUBO = "AeccCircularConcretePipe_Imperial"
BUZON = "Buzon CBA Imperial"
PRES = "Imperial_AWWA_PushOn|pipe-push on-ductile iron-250 psi"

_TUBO_XML = """<?xml version="1.0" encoding="utf-8"?>
<LandPart desc="Part Table" version="1.0" xmlns:xlink="http://www.w3.org/1999/xlink" fixColumn="C1">
  <ColumnConstView desc="v" id="CCV1" viewKey="3d" viewName="AeccPartRecipe" pathsRelativeTo="Table">
    <Images>
      <Image>
        <URL xlink:title="img" xlink:href="{fid}.bmp" />
      </Image>
    </Images>
  </ColumnConstView>
  <ColumnUnique desc="Primary Key" datatype="string" name="UUID" visible="0">
    <RowUnique id="r0">C724014D-B9F0-4D12-A6E1-21540B37111F</RowUnique>
    <RowUnique id="r1">7499EFD3-99D4-406A-856D-9B38F9A53DBF</RowUnique>
  </ColumnUnique>
  <Column desc="{desc}" dataType="float" unit="inch" name="PID" id="C1" visible="1" context="PipeInnerDiameter" index="0">
    <Row id="r0">12.0000</Row>
    <Row id="r1">18.0000</Row>
  </Column>
  <Column desc="{wth}" dataType="float" unit="inch" name="WTh" id="C2" visible="1" context="WallThickness" index="0">
    <Row id="r0">2.0000</Row>
    <Row id="r1">2.5000</Row>
  </Column>
</LandPart>
"""

_BUZON_XML = """<?xml version="1.0" encoding="utf-8"?>
<LandPart desc="Part Table" version="1.0">
\t<ColumnConstList desc="Inner Structure Width" dataType="float" unit="inch" name="SIW" id="CCL1" visible="1" context="StructInnerWidth" index="0">
\t\t<Item id="i0">24.0000</Item>
\t\t<Item id="i1">48.0000</Item>
\t</ColumnConstList>
\t<ColumnConstList desc="Inner Structure Length" dataType="float" unit="inch" name="SIL" id="CCL2" visible="1" context="StructInnerLength" index="0">
\t\t<Item id="i0">72.0000</Item>
\t\t<Item id="i1">24.0000</Item>
\t</ColumnConstList>
</LandPart>
"""


def _xml(path, texto, crlf=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if crlf:
        texto = texto.replace("\n", "\r\n")
    with open(path, "wb") as fh:
        fh.write(b"\xef\xbb\xbf" + texto.encode("utf-8"))


def _sqlite(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE WA_PIPE_MODEL (FID INTEGER, PID TEXT, PART_FAMILY_NAME TEXT, DESCRIPTION TEXT,"
              " DIAMETER_NOMINAL TEXT, DIAMETER_INSIDE REAL, DIAMETER_OUTSIDE REAL, THICKNESS REAL)")
    c.execute("CREATE TABLE WA_CONNECTION_POINT (FID INTEGER, PID TEXT, NOMINAL_DIAMETER REAL,"
              " OUTER_DIAMETER REAL, WALL_THICKNESS REAL, POSITION_3D_X REAL)")
    c.execute("CREATE TABLE WA_ELBOW_MODEL (FID INTEGER, PID TEXT, PART_FAMILY_NAME TEXT, DESCRIPTION TEXT,"
              " DIAMETER_NOMINAL TEXT)")
    fam = PRES.split("|")[1]
    for i, d in enumerate((8, 10)):
        c.execute("INSERT INTO WA_PIPE_MODEL VALUES (?,?,?,?,?,?,?,?)",
                  (i + 1, f"P{d}", fam, f"pipe-{d} in-push on-ductile iron-250 psi-AWWA C151",
                   f"{d} in x {d} in", d + 0.2, d + 1.0, 0.3 + d / 100))
        for k in range(2):
            c.execute("INSERT INTO WA_CONNECTION_POINT VALUES (?,?,?,?,?,?)",
                      (10 + 2 * i + k, f"P{d}", d, d + 1.0, 0.3, 0.0))
        c.execute("INSERT INTO WA_ELBOW_MODEL VALUES (?,?,?,?,?)",
                  (50 + i, f"E{d}", "elbow-45-push on", f"elbow-{d} in-45-push on", f"{d} in x {d} in"))
        c.execute("INSERT INTO WA_CONNECTION_POINT VALUES (?,?,?,?,?,?)", (60 + i, f"E{d}", d, d + 1.0, 0.3, 4.0))
    c.commit(); c.close()


@pytest.fixture
def pd(tmp_path, monkeypatch):
    """ProgramData sintético: 2025/esp (todo) y 2027/enu (sin el buzón)."""
    for year, lang, desc, wth in ((2025, "esp", "Diámetro de tubería interior", "Grosor de pared"),
                                  (2027, "enu", "Inner Pipe Diameter", "Wall Thickness")):
        base = tmp_path / "Autodesk" / f"C3D {year}" / lang
        _xml(str(base / "Pipes Catalog" / "US Imperial Pipes" / "Circular Pipes" / f"{TUBO}.xml"),
             _TUBO_XML.format(fid=TUBO, desc=desc, wth=wth), crlf=(lang == "esp"))
        os.makedirs(base / "Pipes Catalog" / "US Imperial Structures", exist_ok=True)
        if year == 2025:
            _xml(str(base / "Pipes Catalog" / "US Imperial Structures" / "Buzones" / f"{BUZON}.xml"), _BUZON_XML)
        _sqlite(str(base / "Pressure Pipes Catalog" / "Imperial" / "Imperial_AWWA_PushOn.sqlite"))
    monkeypatch.setenv("ProgramData", str(tmp_path))
    viejo = cc._current_lang
    yield tmp_path
    cc.set_current_lang(viejo)


DESTINOS = [(2025, "esp"), (2027, "enu")]


def test_instalaciones_y_ubicacion(pd):
    assert T.instalaciones() == DESTINOS
    assert T.ubicar("pipe", TUBO, 2027, "enu").endswith(TUBO + ".xml")
    assert T.ubicar("structure", BUZON, 2027, "enu") is None
    assert T.ubicar("pressure", PRES, 2025, "esp").endswith("Imperial_AWWA_PushOn.sqlite")


def test_filas_agrega_en_las_dos_instalaciones(pd):
    f = T.formato("pipe", TUBO, 2025, "esp")
    assert f.modo == "filas" and [e.clave for e in f.ejes] == ["PID"] and [e.clave for e in f.extras] == ["WTh"]
    assert f.existentes == ["12 in", "18 in"]
    prop = T.proponer("pipe", TUBO, 2025, "esp", {"PID": 15})
    assert prop["WTh"] == pytest.approx(2.25)                    # interpolado entre 12 y 18
    res = T.agregar("pipe", TUBO, {"PID": 15}, DESTINOS, prop)
    assert [r.estado for r in res] == ["agregado", "agregado"]
    for year, lang in DESTINOS:
        cc.set_current_lang(lang)
        texto = T.texto_tamano("pipe", TUBO, {"PID": 15}, year, lang)
        assert texto in cc.pipe_sizes(year, TUBO)               # se puede elegir en la app
        path = T.ubicar("pipe", TUBO, year, lang)
        raw = open(path, "rb").read()
        assert raw.startswith(b"\xef\xbb\xbf") and b"xmlns:xlink" in raw   # BOM y xlink intactos
        assert (b"\r\n" in raw) == (lang == "esp")                          # fin de línea intacto
        assert os.path.isfile(path + ".pdfcad.bak")
        root = T._leer_xml(path)
        assert len(root.find("ColumnUnique").findall("RowUnique")) == 3
        assert [r.text for r in root.find("Column[@name='WTh']").findall("Row")][-1] == "2.2500"
        marca = os.path.join(cc._lang_root(year, lang), "Pipes Catalog", T.MARCA_REGEN)
        assert open(marca, encoding="utf-8").read().strip() == f"pipe|{TUBO}|15"
    # El mismo UUID en las dos instalaciones (determinista).
    ids = [T._leer_xml(T.ubicar("pipe", TUBO, y, lg)).find("ColumnUnique").findall("RowUnique")[-1].text
           for y, lg in DESTINOS]
    assert ids[0] == ids[1]


def test_repetir_no_duplica(pd):
    T.agregar("pipe", TUBO, {"PID": 15}, DESTINOS)
    antes = open(T.ubicar("pipe", TUBO, 2025, "esp"), "rb").read()
    res = T.agregar("pipe", TUBO, {"PID": 15}, DESTINOS)
    assert [r.estado for r in res] == ["ya_existia", "ya_existia"]
    assert open(T.ubicar("pipe", TUBO, 2025, "esp"), "rb").read() == antes


def test_listas_buzon_y_familia_ausente(pd):
    f = T.formato("structure", BUZON, 2025, "esp")
    assert f.modo == "listas" and [e.clave for e in f.ejes] == ["SIW", "SIL"]
    res = T.agregar("structure", BUZON, {"SIW": 30, "SIL": 30}, DESTINOS)
    assert [r.estado for r in res] == ["agregado", "sin_familia"]
    root = T._leer_xml(T.ubicar("structure", BUZON, 2025, "esp"))
    for nombre in ("SIW", "SIL"):
        items = root.find(f"ColumnConstList[@name='{nombre}']").findall("Item")
        assert (items[-1].get("id"), items[-1].text) == ("i2", "30.0000")
    texto = T.texto_tamano("structure", BUZON, {"SIW": 30, "SIL": 30}, 2025, "esp")
    cc.set_current_lang("esp")
    assert texto in cc.structure_sizes(2025, BUZON)
    # Solo un valor nuevo: el otro eje ya existía.
    res = T.agregar("structure", BUZON, {"SIW": 24, "SIL": 30}, [(2025, "esp")])
    assert res[0].estado == "ya_existia"


def test_presion_clona_tubo_y_accesorios(pd):
    f = T.formato("pressure", PRES, 2025, "esp")
    assert f.modo == "presion" and f.existentes == ["8 in x 8 in", "10 in x 10 in"]
    prop = T.proponer("pressure", PRES, 2025, "esp", {"DIAMETER_NOMINAL": 9})
    assert prop["DIAMETER_INSIDE"] == pytest.approx(9.2)
    res = T.agregar("pressure", PRES, {"DIAMETER_NOMINAL": 9}, DESTINOS)
    assert [r.estado for r in res] == ["agregado", "agregado"]
    db = T.ubicar("pressure", PRES, 2025, "esp")
    c = sqlite3.connect(db)
    fila = c.execute("SELECT PID, DESCRIPTION, DIAMETER_NOMINAL, DIAMETER_OUTSIDE FROM WA_PIPE_MODEL "
                     "WHERE DIAMETER_NOMINAL='9 in x 9 in'").fetchone()
    assert fila[1] == "pipe-9 in-push on-ductile iron-250 psi-AWWA C151"   # lo que lee el plugin
    assert fila[3] == pytest.approx(10.0)
    assert c.execute("SELECT COUNT(*) FROM WA_CONNECTION_POINT WHERE PID=?", (fila[0],)).fetchone()[0] == 2
    codo = c.execute("SELECT PID, DESCRIPTION FROM WA_ELBOW_MODEL WHERE DIAMETER_NOMINAL='9 in x 9 in'").fetchone()
    assert codo[1] == "elbow-9 in-45-push on"
    fids = [r[0] for t in ("WA_PIPE_MODEL", "WA_CONNECTION_POINT", "WA_ELBOW_MODEL")
            for r in c.execute(f"SELECT FID FROM {t}")]
    assert len(fids) == len(set(fids))                                      # sin FID repetidos
    c.close()
    cc.set_current_lang("esp")
    assert T.texto_tamano("pressure", PRES, {"DIAMETER_NOMINAL": 9}, 2025, "esp") in cc.pressure_pipe_sizes(2025, PRES)
    # Gravedad no se toca en presión: sin marca de regeneración.
    assert not os.path.exists(os.path.join(cc._lang_root(2025, "esp"), "Pipes Catalog", T.MARCA_REGEN))
    assert T.agregar("pressure", PRES, {"DIAMETER_NOMINAL": 9}, DESTINOS)[0].estado == "ya_existia"


def test_catalogo_bloqueado_da_error_legible(pd):
    db = T.ubicar("pressure", PRES, 2025, "esp")
    bloqueo = sqlite3.connect(db)
    bloqueo.execute("BEGIN EXCLUSIVE")
    try:
        res = T.agregar("pressure", PRES, {"DIAMETER_NOMINAL": 9}, [(2025, "esp")])
    finally:
        bloqueo.rollback(); bloqueo.close()
    assert res[0].estado == "error" and "Civil 3D" in res[0].mensaje

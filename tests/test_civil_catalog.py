"""Pruebas de humo del catálogo (civil_catalog.py).

Cubren el criterio clave de emparejamiento de familias:
  - `family_guid` SOLO devuelve GUID para familias por defecto de Autodesk
    (nombre 'Aecc…'); para custom o presión devuelve "" (esas se emparejan por
    Descripción en el plugin). Esto se valida sin tocar disco.
  - La lectura del GUID (`Catalog_PartID`) y de la descripción localizada
    (`Catalog_PartDesc`) del XML, con un fixture pequeño.
"""
import civil_catalog as cc


SAMPLE_XML = """<?xml version="1.0"?><LandPart>
  <ColumnConst context="Catalog_PartName">AeccStructTwoTierEccentricCyl_Imperial</ColumnConst>
  <ColumnConst context="Catalog_PartDesc">Estructura de prueba</ColumnConst>
  <ColumnConst context="Catalog_PartID">96687C16-D953-4AC9-AF53-338951DA21C9</ColumnConst>
</LandPart>"""


def test_family_guid_vacio_para_custom_y_presion():
    # Custom (no arranca con 'Aecc') → sin GUID, se empareja por Descripción.
    assert cc.family_guid(2025, "Buzon CBA Imperial", "structure") == ""
    # Presión (formato '<subcat>|<name>', catálogo SQLite) → sin GUID.
    assert cc.family_guid(2025, "Reductores|algo", "pipe") == ""
    # fid vacío → "".
    assert cc.family_guid(2025, "", "structure") == ""


def test_family_guid_lee_el_partid_del_xml(tmp_path, monkeypatch):
    xml = tmp_path / "AeccStructTwoTierEccentricCyl_Imperial.xml"
    xml.write_text(SAMPLE_XML, encoding="utf-8")
    # family_guid resuelve la ruta del XML por familia; la interceptamos para
    # apuntar a nuestro fixture (así no depende del catálogo instalado).
    monkeypatch.setattr(cc, "structure_family_xml", lambda year, fid: str(xml))
    guid = cc.family_guid(2025, "AeccStructTwoTierEccentricCyl_Imperial", "structure")
    assert guid == "96687C16-D953-4AC9-AF53-338951DA21C9"


def test_extract_family_desc_lee_descripcion_localizada(tmp_path):
    xml = tmp_path / "fam.xml"
    xml.write_text(SAMPLE_XML, encoding="utf-8")
    assert cc._extract_family_desc(str(xml)) == "Estructura de prueba"

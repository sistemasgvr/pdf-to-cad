"""Los trabajos del proceso aparte se nombran con un TEXTO («paquete.modulo:funcion»): PyInstaller no
los ve. Si el módulo no va en `hiddenimports`, en el .exe el trabajo falla con ModuleNotFoundError."""
import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parents[1]
OBJETIVO = re.compile(r"\"([a-z_]+(?:\.[a-z_0-9]+)+):[a-zA-Z_0-9]+\"")


def test_cada_trabajo_del_proceso_va_en_el_ejecutable():
    objetivos = {m for f in (RAIZ / "app").rglob("*.py")
                 for m in OBJETIVO.findall(f.read_text(encoding="utf-8"))}
    assert "hoja.planos_trabajo" in objetivos
    spec = (RAIZ / "PDF-a-CAD.spec").read_text(encoding="utf-8")
    faltan = sorted(m for m in objetivos if f'"{m}"' not in spec)
    assert not faltan, f"Faltan en hiddenimports de PDF-a-CAD.spec: {faltan}"

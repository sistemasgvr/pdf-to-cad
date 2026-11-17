"""Lo que el INSTALADOR necesita (2026-11-11, pedido del usuario: «prevenir que todo funcione bien en el
instalador»). Sin compilar: spec, setup.iss, build_plugin.bat y la autoprueba que corre dentro del .exe.
Con el instalador ya armado, `python scripts/verificar_instalador.py` revisa además el .exe, el plugin y el MCP
(lo hace `build_all.bat`)."""
import os
import pathlib
import re
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))

import verificar_instalador as V  # noqa: E402


def test_spec_setup_y_build_plugin_consistentes():
    errores = V.revisar_spec() + V.revisar_iss(compilado=False)
    assert not errores, "\n".join(errores)


def test_la_app_busca_pdfcadmcp_donde_lo_instala_setup_iss():
    """`civil3d_mcp.ruta_exe` en el .exe mira {carpeta del .exe}\\PdfCadMcp\\PdfCadMcp.exe."""
    from ia import civil3d_mcp
    src = (RAIZ / "app" / "ia" / "civil3d_mcp.py").read_text(encoding="utf-8")
    assert 'os.path.join(os.path.dirname(sys.executable), "PdfCadMcp", "PdfCadMcp.exe")' in src
    assert callable(civil3d_mcp.ruta_exe)
    assert re.search(r'DestDir:\s*"\{app\}\\PdfCadMcp"', (RAIZ / "installer" / "setup.iss").read_text("utf-8-sig"))


def test_bundle_del_plugin_copia_todas_las_dll_publicadas():
    """Una lista fija dejaba fuera Sqlite y las dependencias de ClosedXML (comandos rotos en el plugin instalado)."""
    bat = (RAIZ / "installer" / "build_plugin.bat").read_text(encoding="utf-8")
    assert re.search(r'copy /y "%PUBDIR%\\\*\.dll" "%BUNDLE%\\Contents\\"', bat)


def test_datos_que_la_app_lee_van_en_el_spec():
    """Iconos, manual y entrenamiento de producción: cada búsqueda «frozen» tiene su `datas`."""
    spec = (RAIZ / "PDF-a-CAD.spec").read_text(encoding="utf-8")
    for origen, destino in (("app/icons", "icons"), ("app/docs", "docs"),
                            ("entrenamiento_ia/produccion.json", "entrenamiento_ia")):
        assert f"('{origen}', '{destino}')" in spec
        assert (RAIZ / origen).exists()


def test_autoprueba_en_desarrollo_da_todo_bien():
    """La misma autoprueba que corre el .exe (`--autoprueba`), aquí con un proceso hijo real."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import autoprueba
    inf = autoprueba.correr(hijo=True)
    assert inf["modulos"] == {} and inf["terceros"] == {} and inf["datos"] == {}, inf
    assert inf["hijo"]["ok"], inf["hijo"]
    assert inf["ok"]


def test_ningun_widget_se_conecta_al_tema_con_una_lambda_suelta():
    """Una lambda en THEME_BUS sigue viva cuando el widget se borra: cambiar el tema tras cerrar la ventana
    daba «Internal C++ object … already deleted» (instalador, 2026-11-11). Usar `theme.al_tema(obj, fn)`."""
    malos = [f"{p.relative_to(RAIZ)}:{i}" for p in (RAIZ / "app").rglob("*.py")
             for i, l in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
             if "THEME_BUS.changed.connect(lambda" in l]
    assert not malos, malos


def test_build_all_no_genera_instalador_si_falla_una_comprobacion():
    """Lista de entrega (2026-11-13): pruebas y arnés del plugin ANTES de compilar, la verificación del
    .exe sin la pregunta «¿generar de todos modos?» y el informe al final. Antes se podía seguir con errores."""
    bat = next(RAIZ.glob("*build_all.bat")).read_text(encoding="utf-8")
    pos = {k: bat.find(k) for k in ("verificar_entorno_build.py", "verificar_entrega.py fuentes",
                                    r"installer\build_plugin.bat", "PyInstaller", "verificar_entrega.py exe",
                                    '"%ISCC%" "%ISS%"', "verificar_entrega.py final")}
    assert all(v >= 0 for v in pos.values()), pos
    orden = list(pos.values())
    assert orden == sorted(orden), pos
    assert "SEGUIR" not in bat and "de todos modos" not in bat
    import verificar_entrega as E                       # sin los PDF dorados (pedido 2026-11-13)
    assert not any("regresion" in " ".join(c) for f in E.PASOS.values() for _n, _d, c, _w in f)
    for fase in ("fuentes", "exe"):
        i = bat.find(f"verificar_entrega.py {fase}")
        assert "if errorlevel 1" in bat[i:i + 200] and "exit /b 1" in bat[i:i + 600]


def test_verificar_entrega_falla_si_un_paso_falla_y_lo_anota(tmp_path, monkeypatch):
    import verificar_entrega as E
    monkeypatch.setattr(E, "DIST", str(tmp_path))
    monkeypatch.setattr(E, "INFORME", str(tmp_path / "informe_entrega.md"))
    monkeypatch.setattr(E, "LOGS", str(tmp_path / "entrega"))
    py = sys.executable
    monkeypatch.setitem(E.PASOS, "exe", [
        ("bien", "Paso que pasa", [py, "-c", "print('todo en orden')"], str(tmp_path)),
        ("mal", "Paso que falla", [py, "-c", "import sys; print('se cayó'); sys.exit(3)"], str(tmp_path))])
    assert E.main(["exe"]) == 1
    informe = (tmp_path / "informe_entrega.md").read_text(encoding="utf-8")
    assert "Paso que pasa | ✔ bien" in informe and "Paso que falla | ✖ FALLÓ" in informe
    assert "No se generó el instalador" in informe and "commit" in informe
    assert (tmp_path / "entrega" / "mal.log").read_text(encoding="utf-8").strip() == "se cayó"
    monkeypatch.setitem(E.PASOS, "exe", [("bien", "Paso que pasa", [py, "-c", "pass"], str(tmp_path))])
    assert E.main(["exe"]) == 0
    inst = tmp_path / "setup.exe"
    inst.write_bytes(b"x" * 10)
    assert E.main(["final", "--instalador", str(inst)]) == 0
    assert "SHA-256" in (tmp_path / "informe_entrega.md").read_text(encoding="utf-8")

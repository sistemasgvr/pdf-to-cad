"""Gestión del proyecto (2026-11-11): funciones, versiones y catálogo en `gestion/`, sitio del cliente y vista de
administrador. Lo que importa: el cliente solo ve lo APROBADO y nada interno; proponer no cambia el estado."""
import importlib
import os
import shutil
import sys
import threading
import urllib.error
import urllib.request

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "scripts", "gestion"))


@pytest.fixture
def g(tmp_path, monkeypatch):
    """Copia de gestion/ en tmp (para no tocar los datos reales) con una ficha de prueba."""
    dst = tmp_path / "gestion"
    shutil.copytree(os.path.join(RAIZ, "gestion"), dst, ignore=shutil.ignore_patterns("_salida", "regresion"))
    for v in (dst / "versiones").glob("*.toml"):            # las pruebas parten de versiones sin publicar
        v.write_text(v.read_text(encoding="utf-8").replace("publicada = true", "publicada = false"), encoding="utf-8")
    monkeypatch.setenv("PDFCAD_GESTION", str(dst))
    import datos
    importlib.reload(datos)
    mods = {}
    for m in ("drawio", "sitio", "reporte", "publicar", "admin"):
        mods[m] = importlib.reload(importlib.import_module(m))
    ficha = dst / "catalogo" / "piezas-3d" / "valvulas" / "compuerta"
    ficha.mkdir(parents=True)
    (ficha / "ficha.toml").write_text(
        'nombre = "Válvula de compuerta"\ntipo = "valvulas"\narea = "piezas-3d"\nresponsable = "Jean"\n'
        'descripcion = "Pieza de prueba"\npropuesto = "falta_probar"\npropuesto_por = "Jean"\n'
        'propuesto_nota = "NOTA-INTERNA-XYZ"\n', encoding="utf-8")
    (ficha / "captura.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    return type("G", (), dict(D=datos, dir=dst, **mods))


def test_datos_reales_validos():
    sys.path.insert(0, os.path.join(RAIZ, "scripts", "gestion"))
    import datos
    importlib.reload(datos)
    pr = datos.leer()
    # una versión publicada con cambios por aprobar es ESTADO del proyecto (lo ve el administrador), no un error
    assert [e for e in datos.validar(pr) if not e.startswith("Versión ")] == []
    assert len(pr.funciones) > 100 and {g.id for g in pr.raices()} >= {"app", "plugin"}


def test_importar_drawio_lee_estados_por_color():
    """Leyenda del diagrama del equipo: verde = OK, magenta = TESTEAR, rojo = OPTIMIZAR. Las cajas sin flecha
    cuelgan de la que tienen encima; el bloque MCP es un área propia; la leyenda no es una función."""
    import drawio
    pr = drawio.importar(os.path.join(RAIZ, "docs", "Diagrama funciones", "funciones-eeuu.drawio"))
    estados = {f.estado for f in pr.funciones}
    assert {"probado", "falta_probar", "optimizar"} <= estados and len(pr.funciones) > 150
    nombres = {f.nombre for f in pr.funciones}
    assert not nombres & {"OK", "TESTEAR", "OPTIMIZAR", "v1", "a"}
    assert {g.id for g in pr.raices()} == {"app", "plugin", "mcp"}
    herramientas = [f.nombre for f in pr.funciones if f.grupo == "mcp.herramientas"]
    assert any(n.startswith("Normativas") for n in herramientas)          # caja sin flecha, debajo del grupo
    assert pr.grupo("app.tabla-de-datos").padre == "app"                 # grupo colgado de una función → al área


def test_proponer_no_cambia_el_estado_y_aprobar_si(g):
    pr = g.D.leer()
    f = pr.funciones[0]
    antes = f.estado
    f.propuesto, f.propuesto_por = "optimizar", "Santos"
    g.D.guardar_funciones(pr)
    pr = g.D.leer()
    f = pr.funciones[0]
    assert f.estado == antes and f.por_revisar
    g.D.aprobar(pr, f, "optimizar")
    g.D.guardar_funciones(pr)
    f = g.D.leer().funciones[0]
    assert f.estado == "optimizar" and f.aprobado.startswith(pr.admin) and not f.propuesto


def test_guardar_y_leer_es_identico(g):
    pr = g.D.leer()
    g.D.guardar_funciones(pr)
    pr2 = g.D.leer()
    assert [f.__dict__ for f in pr.funciones] == [f.__dict__ for f in pr2.funciones]
    assert [x.__dict__ for x in pr.grupos] == [x.__dict__ for x in pr2.grupos]


def test_sitio_publico_sin_nada_interno(g):
    pr = g.D.leer()
    pr.funciones[0].nota = "NOTA-INTERNA-FUNCION"
    pr.funciones[0].propuesto, pr.funciones[0].propuesto_por = "con_bug", "ResponsableSecreto"
    archivos = g.sitio.generar(pr, str(g.dir / "_salida" / "publico"))
    texto = "".join(open(g.dir / "_salida" / "publico" / a, encoding="utf-8").read() for a in archivos)
    for prohibido in ("NOTA-INTERNA", "ResponsableSecreto", "propuesto", "Jean", "Válvula de compuerta"):
        assert prohibido not in texto, prohibido          # la ficha aún no está aprobada: no sale
    assert "version-2.0.0.html" not in archivos            # versión no publicada: no sale
    v = pr.versiones[0]
    v.publicada = True
    fi = pr.fichas[0]
    g.D.aprobar(pr, fi, "falta_probar")
    archivos = g.sitio.generar(pr, str(g.dir / "_salida" / "publico"))
    assert f"version-{v.numero}.html" in archivos
    cat = open(g.dir / "_salida" / "publico" / "catalogo.html", encoding="utf-8").read()
    assert "Válvula de compuerta" in cat and "En pruebas" in cat and "Jean" not in cat
    assert (g.dir / "_salida" / "publico" / "catalogo" / "piezas-3d" / "valvulas" / "compuerta" / "captura.png").exists()


def test_admin_aprueba_rechaza_y_publica_version(g):
    m, e = g.admin.accion("aprobar", {"tipo": ["ficha"], "id": ["piezas-3d/valvulas/compuerta"],
                                      "estado": ["falta_probar"]})
    assert not e
    fi = g.D.leer().fichas[0]
    assert fi.estado == "falta_probar" and not fi.propuesto
    pr = g.D.leer()
    fid = pr.funciones[1].id
    pr.funciones[1].propuesto = "probado"
    g.D.guardar_funciones(pr)
    g.admin.accion("rechazar", {"tipo": ["funcion"], "id": [fid], "motivo": ["falta probar en DU08"]})
    f = next(x for x in g.D.leer().funciones if x.id == fid)
    assert not f.propuesto and "falta probar en DU08" in f.nota
    pr = g.D.leer()
    for f in pr.funciones:                                  # todo aprobado: la versión ya se puede publicar
        f.estado = f.estado or "probado"
    g.D.guardar_funciones(pr)
    g.admin.accion("version", {"numero": ["2.0.0"], "publicada": ["1"]})
    assert next(v for v in g.D.leer().versiones if v.numero == "2.0.0").publicada
    html = g.admin.pagina_principal(g.D.leer())
    assert "Administrador" in html and "Todas las funciones" in html


def test_admin_solo_responde_en_local(g):
    srv = g.admin.ThreadingHTTPServer(("127.0.0.1", 0), g.admin._Manejador)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    puerto = srv.server_address[1]
    try:
        assert b"Administrador" in urllib.request.urlopen(f"http://127.0.0.1:{puerto}/").read()
        req = urllib.request.Request(f"http://127.0.0.1:{puerto}/version", data=b"numero=2.0.0&publicada=1",
                                     headers={"Origin": "https://otro-sitio.com"})
        with pytest.raises(urllib.error.HTTPError) as ex:
            urllib.request.urlopen(req)
        assert ex.value.code == 403 and not g.D.leer().versiones[0].publicada
    finally:
        srv.shutdown()


def test_reporte_pdf_y_whatsapp(g):
    import fitz
    pdf, txt = g.reporte.generar("2.0.0", destino=str(g.dir / "_salida" / "reportes"))
    with fitz.open(pdf) as doc:
        texto = "".join(p.get_text() for p in doc)
    assert "Versión 2.0.0" in texto and "Correcciones" in texto
    assert open(txt, encoding="utf-8").read().startswith(f"*{g.D.leer().nombre} · Versión 2.0.0*")


def test_drawio_por_version_solo_lo_mencionado(g, tmp_path):
    pr = g.D.leer()
    g.drawio.exportar(pr, str(tmp_path / "todo.drawio"))
    g.drawio.exportar(pr, str(tmp_path / "v.drawio"), "2.0.0")
    todo = (tmp_path / "todo.drawio").read_text(encoding="utf-8")
    v = (tmp_path / "v.drawio").read_text(encoding="utf-8")
    assert todo.count("vertex=") > v.count("vertex=") > 3
    assert "Preguntas sobre el proyecto" in v and "Proyectos recientes" not in v


def test_cada_cambio_de_una_version_va_asociado_a_una_funcion_aprobada(g):
    """Regla del administrador (2026-11-11): no se publica una versión con un cambio sin función del diagrama, con
    una función que no existe o con una sin estado aprobado."""
    pr = g.D.leer()
    v = pr.versiones[0]
    f = next(x for x in pr.funciones if x.estado)
    sin_estado = next(x for x in pr.funciones if not x.estado)
    v.novedades = [dict(tipo="nuevo", titulo="Bien", funciones=[f.id])]
    v.publicada = False
    g.D.guardar_version(v)
    assert g.D.pendientes_version(pr, v) == []
    for funciones, motivo in (([], "ninguna función"), (["no.existe"], "no existe"),
                              ([sin_estado.id], "estado aprobado")):
        v.novedades = [dict(tipo="nuevo", titulo="Cambio", funciones=funciones)]
        g.D.guardar_version(v)
        assert motivo in " ".join(g.D.pendientes_version(g.D.leer(), v))
        m, e = g.admin.accion("version", {"numero": [v.numero], "publicada": ["1"]})
        assert "no se puede publicar" in e and not g.D.leer().versiones[0].publicada
    v.publicada = True                                     # publicada a mano en el archivo: el sitio no se arma
    g.D.guardar_version(v)
    with pytest.raises(ValueError):
        g.publicar.construir()

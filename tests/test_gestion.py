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
    for m in ("drawio", "sitio", "reporte", "publicar", "admin_version", "admin_funciones", "admin"):
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
    assert "Más opciones" in html and "Versiones" in html


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
    import pymupdf as fitz
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


def test_admin_agrega_edita_quita_y_colorea(g):
    """Pedido 2026-11-17: el administrador agrega funciones/grupos, los edita, los quita y cambia colores."""
    pr = g.D.leer()
    raiz = pr.raices()[0].id
    m, e = g.admin.accion("nuevo_grupo", {"padre": [raiz], "nombre": ["Grupo Nuevo"], "detalle": ["sub"]})
    assert not e
    gid = next(x.id for x in g.D.leer().grupos if x.nombre == "Grupo Nuevo")
    m, e = g.admin.accion("nueva_funcion", {"grupo": [gid], "nombre": ["Mi función"], "estado": ["en_desarrollo"]})
    f = next(x for x in g.D.leer().funciones if x.nombre == "Mi función")
    assert not e and f.estado == "en_desarrollo" and f.aprobado and f.grupo == gid
    otro = pr.grupos[1].id
    g.admin.accion("editar_funcion", {"id": [f.id], "nombre": ["Renombrada"]})
    g.admin.accion("editar_funcion", {"id": [f.id], "grupo": [otro]})
    f2 = next(x for x in g.D.leer().funciones if x.id == f.id)
    assert f2.nombre == "Renombrada" and f2.grupo == otro
    # estado propio con su color: se guarda, se usa y el sitio lo pinta
    g.admin.accion("nuevo_estado", {"nombre": ["Revisión cliente"], "cliente": ["En revisión"],
                                    "fondo": ["#7b61ff"], "texto": ["#ffffff"]})
    eid = next(e["id"] for e in g.D.leer().estados)
    g.admin.accion("estado", {"tipo": ["funcion"], "id": [f.id], "estado": [eid]})
    pr = g.D.leer()
    assert next(x for x in pr.funciones if x.id == f.id).estado == eid and not g.D.validar(pr)
    assert "#7b61ff" in g.sitio.pill(eid)
    with pytest.raises(ValueError):                          # en uso: no se quita
        g.admin.accion("quitar_estado", {"id": [eid]})
    # color de un estado de siempre y volver al original
    g.admin.accion("estado_color", {"id": ["probado"], "nombre": ["Probado"], "cliente": ["Disponible"],
                                    "fondo": ["#00aa00"], "texto": ["#ffffff"]})
    g.D.leer()
    assert g.D.ESTADOS["probado"][2] == "#00aa00"
    g.admin.accion("quitar_estado", {"id": ["probado"]})
    g.D.leer()
    assert g.D.ESTADOS["probado"][2] == g.D.ESTADOS_BASE["probado"][2]
    # quitar la función y el grupo vacío
    assert not g.admin.accion("quitar_funcion", {"id": [f.id]})[1]
    assert not g.admin.accion("quitar_grupo", {"id": [gid]})[1]
    pr = g.D.leer()
    assert f.id not in {x.id for x in pr.funciones} and gid not in {x.id for x in pr.grupos}
    html = g.admin.pagina_principal(pr)
    assert "Estados y colores" in html and "+ Agregar función" in g.admin_funciones.JS


def test_admin_no_quita_una_funcion_usada_en_una_version(g):
    pr = g.D.leer()
    usada = next(fid for v in pr.versiones for n in v.novedades for fid in n.get("funciones", []))
    with pytest.raises(ValueError):
        g.admin.accion("quitar_funcion", {"id": [usada]})
    assert usada in {x.id for x in g.D.leer().funciones}


def test_editor_de_version_arma_la_version_a_mano(g):
    """Pedido 2026-11-18: el administrador arma la versión sobre la vista del cliente (nada se sugiere): crea la
    versión, agrega cambios, asocia funciones que elige él o las crea ahí, y se guarda solo."""
    m, e, destino = g.admin.accion("nueva_version", {"numero": ["9.9.0"], "titulo": ["Prueba"]})
    assert not e and destino == "/editar/9.9.0"
    pr = g.D.leer()
    v = next(x for x in pr.versiones if x.numero == "9.9.0")
    assert v.novedades == [] and v.titulo == "Prueba"            # vacía: ninguna función sugerida
    html = g.admin_version.pagina(pr, v)
    assert "+ Asociar función" in g.admin_version.JS and '"numero": "9.9.0"' in html
    # el editor manda la versión entera; una función que elijo yo y otra que creo ahí mismo
    f = pr.funciones[0]
    grupo = pr.grupos[-1].id
    nueva = g.admin_version.api("api/funcion", {"grupo": grupo, "nombre": "Función del editor", "estado": "probado"})
    assert nueva["ok"] and nueva["funcion"]["estado"] == "probado"
    datos_v = dict(numero="9.9.0", fecha="2026-11-18", titulo="Prueba", resumen="r", novedades=[
        dict(tipo="nuevo", titulo="  Cambio A ", detalle="d", funciones=[f.id, f.id, nueva["funcion"]["id"]]),
        dict(tipo="mejora", titulo="", funciones=[])], pendientes=[dict(titulo="Luego", detalle=""), dict(titulo="")])
    res = g.admin_version.api("api/version", datos_v)
    assert res["ok"]
    assert "Hay un cambio sin título" in res["pendientes"]
    v = next(x for x in g.D.leer().versiones if x.numero == "9.9.0")
    assert v.novedades[0]["titulo"] == "Cambio A" and v.novedades[0]["funciones"] == [f.id, nueva["funcion"]["id"]]
    assert [p["titulo"] for p in v.pendientes] == ["Luego"]
    # una versión publicada no se edita (primero a borrador)
    v.publicada = True
    g.D.guardar_version(v)
    with pytest.raises(ValueError):
        g.admin_version.actualizar_version(g.D.leer(), "9.9.0", datos_v)
    m, e, destino = g.admin.accion("version", {"numero": ["9.9.0"], "publicada": ["0"], "volver": ["1"]})
    assert destino == "/editar/9.9.0" and not next(x for x in g.D.leer().versiones if x.numero == "9.9.0").publicada
    with pytest.raises(ValueError, match="ya existe"):
        g.admin.accion("nueva_version", {"numero": ["9.9.0"]})


def test_un_segundo_administrador_no_se_pega_al_puerto_del_viejo(g):
    """Reporte 2026-11-18: con un administrador viejo abierto, abrir otro en Windows tomaba el MISMO puerto y el
    navegador seguía viendo el viejo. Ahora el puerto es exclusivo y el nuevo usa el siguiente libre."""
    viejo = g.admin.abrir_servidor(0)
    puerto = viejo.server_address[1]
    try:
        nuevo = g.admin.abrir_servidor(puerto, intentos=5)
        try:
            assert nuevo.server_address[1] != puerto
        finally:
            nuevo.server_close()
    finally:
        viejo.server_close()


def test_editor_de_funciones_sobre_la_vista_del_cliente(g):
    """Pedido 2026-11-18: el diagrama se edita sobre la misma vista del cliente: filas y tarjetas nuevas, nombres,
    estado y arrastrar filas; cada cambio se guarda al momento."""
    pr = g.D.leer()
    html = g.admin_funciones.pagina(pr)
    assert "+ Agregar función" in g.admin_funciones.JS and "Funciones del proyecto" in html
    api = g.admin_funciones.api
    area = pr.raices()[0].id
    t = api("api/g/nuevo", {"padre": area, "nombre": "Tarjeta nueva"})["grupo"]
    api("api/g/editar", {"id": t["id"], "detalle": "subtítulo"})
    f1 = api("api/f/nueva", {"grupo": t["id"], "nombre": "Uno", "estado": "probado"})["funcion"]
    f2 = api("api/f/nueva", {"grupo": t["id"], "nombre": "Dos", "estado": "en_desarrollo"})["funcion"]
    api("api/f/editar", {"id": f1["id"], "nombre": "Uno bis", "estado": "falta_probar"})
    api("api/f/mover", {"id": f2["id"], "grupo": t["id"], "antes": f1["id"]})          # Dos antes que Uno
    pr = g.D.leer()
    assert [f.nombre for f in pr.funciones_de(t["id"])] == ["Dos", "Uno bis"]
    assert pr.grupo(t["id"]).detalle == "subtítulo"
    uno = next(f for f in pr.funciones if f.id == f1["id"])
    assert uno.estado == "falta_probar" and uno.aprobado
    otra = pr.funciones[0].grupo                                                       # a otra tarjeta, al final
    api("api/f/mover", {"id": f1["id"], "grupo": otra, "antes": None})
    assert g.D.leer().funciones_de(otra)[-1].id == f1["id"]
    usada = next(fid for v in pr.versiones for n in v.novedades for fid in n.get("funciones", []))
    with pytest.raises(ValueError):                                # una función de una versión no se quita
        api("api/f/quitar", {"id": usada})
    api("api/g/quitar", {"id": t["id"]})                           # tarjeta con sus funciones
    pr = g.D.leer()
    assert pr.grupo(t["id"]) is None and f2["id"] not in {f.id for f in pr.funciones}


def test_privado_no_llega_al_cliente_y_la_vista_previa_se_arma_igual(g):
    """Pedido 2026-11-18: funciones, tarjetas o áreas privadas nunca se publican (sitio ni reporte). La vista previa
    se arma aunque falte aprobar algo (antes mostraba un error en vez del sitio)."""
    api = g.admin_funciones.api
    pr = g.D.leer()
    area = pr.raices()[0].id
    t = api("api/g/nuevo", {"padre": area, "nombre": "TARJETA-SECRETA"})["grupo"]
    api("api/f/nueva", {"grupo": t["id"], "nombre": "FUNCION-EN-TARJETA-SECRETA", "estado": "probado"})
    api("api/g/editar", {"id": t["id"], "privado": True})
    suelta = api("api/f/nueva", {"grupo": pr.funciones[0].grupo, "nombre": "FUNCION-SECRETA", "estado": "probado"})
    api("api/f/editar", {"id": suelta["funcion"]["id"], "privado": True})
    pr = g.D.leer()
    assert next(f for f in pr.funciones if f.id == suelta["funcion"]["id"]).privado
    assert "privado = true" in (g.dir / "funciones.toml").read_text(encoding="utf-8")
    assert "privado = false" not in (g.dir / "funciones.toml").read_text(encoding="utf-8")
    # una versión publicada con algo sin aprobar: la vista previa igual se arma, publicar no
    pr.versiones[-1].publicada = True
    g.D.guardar_version(pr.versiones[-1])
    with pytest.raises(ValueError):
        g.publicar.construir()
    archivos = g.publicar.construir(estricto=False)
    texto = "".join((g.dir / "_salida" / "publico" / a).read_text(encoding="utf-8") for a in archivos)
    for secreto in ("TARJETA-SECRETA", "FUNCION-EN-TARJETA-SECRETA", "FUNCION-SECRETA"):
        assert secreto not in texto
    # una novedad con una función privada no se puede publicar
    v = pr.versiones[-1]
    v.novedades.append(dict(tipo="nuevo", titulo="X", funciones=[suelta["funcion"]["id"]]))
    assert any("es privada" in x for x in g.D.pendientes_version(g.D.leer(), v))
    # la entrada del administrador es el editor; lo demás en /panel
    assert "Publicar en Cloudflare" in g.admin_funciones.pagina(g.D.leer())

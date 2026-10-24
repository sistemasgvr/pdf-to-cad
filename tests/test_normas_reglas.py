"""Tabla única de reglas (pedido del usuario 2026-10-21): lo que se puede revisar ahora además de lo de antes —
separaciones con otras utilidades (en paralelo y en el cruce), pendientes, largo, material, buzones (distancia,
caída, quiebres), «llega a» otra tubería— con sus condiciones, niveles y aprobaciones."""
from nucleo import normas_aprobacion as ap
from nucleo import normas_catalogo as nc
from nucleo import normas_reglas as NR
from nucleo import normas_validar as nv

FT = 0.1                                     # 10 px = 1 ft


def _p(layer, tipo, d, pts, **k):
    return dict(layer=layer, tipo=tipo, pts=[tuple(q) for q in pts], name="", diam=float(d), pipe_size=f"{d:g} in", **k)


def _cat(*reglas, tipos=()):
    return nc.normalizar({"tipos": [list(t) for t in tipos], "reglas": [NR.regla_vacia(**r) for r in reglas]})


def _av(cat, pipes, structs=(), conexiones=()):
    return nv.validar(cat, pipes, [], FT, (), list(structs), conexiones)


def test_separacion_en_paralelo_entre_bordes_y_ejes():
    cat = _cat(dict(utilidad="AGUA", revisar="sep_h", min=10, con_utilidad="ALCANTARILLADO"),
               dict(utilidad="AGUA", revisar="sep_h_ejes", min=4, con_utilidad=NR.CUALQUIERA))
    agua = _p("AGUA", "", 12, [(0, 0), (2000, 0)])
    lejos = _p("ALCANTARILLADO", "", 12, [(0, 120), (2000, 120)])          # 12 ft entre ejes, 11 entre bordes
    cerca = _p("ALCANTARILLADO", "", 12, [(0, -100), (2000, -100)])        # 10 ft entre ejes, 9 entre bordes
    corto = _p("ALCANTARILLADO", "", 12, [(2000, 30), (3000, 30)])         # solo se toca la punta: no corre al lado
    av = _av(cat, [agua, lejos, cerca, corto])
    assert [(a.pipe, a.clase) for a in av] == [(0, "separacion")]
    assert "«ALCANTARILLADO #3»" in av[0].mensaje and "9 ft" in av[0].mensaje and "entre bordes" in av[0].mensaje
    assert av[0].y == 0.0 and 0.0 <= av[0].x <= 2000.0                      # sobre la propia utilidad


def test_cruce_por_encima_y_sin_cotas_no_se_mide():
    cat = _cat(dict(utilidad="AGUA", revisar="encima", min=1, con_utilidad="ALCANTARILLADO"))
    agua = _p("AGUA", "", 12, [(0, 0), (2000, 0)], inv_start=10.0, inv_end=10.0)
    bajo = _p("ALCANTARILLADO", "", 12, [(500, -500), (500, 500)], inv_start=7.5, inv_end=7.5)   # 1,5 ft libres
    alto = _p("ALCANTARILLADO", "", 12, [(1500, -500), (1500, 500)], inv_start=9.5, inv_end=9.5)  # -0,5 ft
    sin_cotas = _p("ALCANTARILLADO", "", 12, [(1000, -500), (1000, 500)])
    av = _av(cat, [agua, bajo, alto, sin_cotas])
    assert [(a.pipe, round(a.x), round(a.y)) for a in av] == [(0, 1500, 0)]
    assert "-0,5 ft por encima" in av[0].mensaje


def test_cualquiera_no_cuenta_la_misma_utilidad_ni_las_conexiones_aprobadas():
    cat = _cat(dict(utilidad="ELECTRICO", revisar="sep_v", min=0.5, con_utilidad=NR.CUALQUIERA))
    e1 = _p("ELECTRICO", "", 4, [(0, 0), (2000, 0)], inv_start=5.0, inv_end=5.0)
    e2 = _p("ELECTRICO", "", 4, [(500, -500), (500, 500)], inv_start=5.0, inv_end=5.0)       # misma utilidad
    t1 = _p("TELECOM", "", 4, [(1500, -500), (1500, 500)], inv_start=5.2, inv_end=5.2)
    assert [a.pipe for a in _av(cat, [e1, e2, t1])] == [0]
    assert not _av(cat, [e1, e2, t1], conexiones=[{"pipe_a": 0, "pipe_b": 2}])


def test_misma_utilidad_unida_no_es_paralela():
    cat = _cat(dict(utilidad="ELECTRICO", revisar="sep_h", min=1, con_utilidad="ELECTRICO"))
    a = _p("ELECTRICO", "", 2, [(0, 0), (1000, 0)])
    b = _p("ELECTRICO", "", 2, [(1000, 0), (2000, 3)])                       # sigue de la punta: unida
    c = _p("ELECTRICO", "", 2, [(0, 5), (1000, 5)])                          # al lado, suelta: 0,33 ft
    av = _av(cat, [a, b, c])
    assert {(x.pipe, x.mensaje.split("«")[1].split("»")[0]) for x in av} == {(0, "ELECTRICO #3"), (2, "ELECTRICO #1")}


def test_pendiente_por_tramo_solo_con_cotas_y_con_condicion_de_diametro():
    cat = _cat(dict(utilidad="ALCANTARILLADO", revisar="pendiente", min=0.44, si_diam=[8, 8]))
    pts = [(0, 0), (1000, 0), (2000, 0)]                                     # dos tramos de 100 ft
    ok = _p("ALCANTARILLADO", "", 8, pts, inv_start=10.0, inv_end=9.0)      # 0,5 %
    plana = _p("ALCANTARILLADO", "", 8, pts, inv_start=10.0, inv_end=9.8)   # 0,1 %
    grande = _p("ALCANTARILLADO", "", 12, pts, inv_start=10.0, inv_end=9.8)  # otra condición
    sin = _p("ALCANTARILLADO", "", 8, pts)
    av = _av(cat, [ok, plana, grande, sin])
    assert [a.pipe for a in av] == [1] and "T1 0,1 %" in av[0].mensaje and "(y 1 tramo más)" in av[0].mensaje


def test_buzones_distancia_caida_y_quiebre():
    cat = _cat(dict(utilidad="DRENAJE", elemento="BUZON", revisar="dist_buzones", max=250),
               dict(utilidad="DRENAJE", elemento="BUZON", revisar="caida", max=0.6),
               dict(utilidad="DRENAJE", revisar="quiebre", max=10))
    pts = [(0, 0), (2000, 0), (4000, 0), (4000, 1000)]
    p = _p("DRENAJE", "", 24, pts, inv_start=10.0, inv_end=5.0, vertex_inv={"1": 9.0}, vertex_inv_in={"1": 9.8})
    estr = [dict(x=0.0, y=0.0), dict(x=2000.0, y=0.0), dict(x=4000.0, y=0.0, hidden=True), dict(x=4000.0, y=1000.0)]
    av = _av(cat, [p], estr)
    clases = sorted(a.mensaje.split(" ")[0] for a in av)
    assert clases == ["Caída", "Distancia", "Quiebre"]
    dist = next(a for a in av if a.mensaje.startswith("Distancia"))
    assert "300 ft" in dist.mensaje and dist.x > 2000                        # el tramo de 300 ft (2000→4000→4000,1000)


def test_llega_a_otra_tuberia_con_diametro_menor():
    cat = _cat(dict(utilidad="ALCANTARILLADO", tipo="CONEXION DOMICILIARIA", revisar="llega_menos", min=2),
               tipos=[("ALCANTARILLADO", "COLECTOR"), ("ALCANTARILLADO", "CONEXION DOMICILIARIA")])
    col = _p("ALCANTARILLADO", "COLECTOR", 8, [(0, 0), (3000, 0)])
    hc6 = _p("ALCANTARILLADO", "CONEXION DOMICILIARIA", 6, [(1000, 500), (1000, 0)])
    hc8 = _p("ALCANTARILLADO", "CONEXION DOMICILIARIA", 8, [(2000, 500), (2000, 0)])
    av = _av(cat, [col, hc6, hc8])
    assert [(a.pipe, (a.x, a.y)) for a in av] == [(2, (2000.0, 0.0))] and "«ALCANTARILLADO #1»" in av[0].mensaje


def test_material_condicion_de_material_nivel_y_referencia():
    cat = _cat(dict(utilidad="DRENAJE", revisar="material", valores=["Hormigón armado"], nivel="ERROR"),
               dict(utilidad="DRENAJE", elemento="CURVA", revisar="radio", min=280, si_material=["PVC"],
                    nivel="INFO"),
               dict(utilidad="DRENAJE", revisar="referencia", nota="Velocidad mínima 3 fps"))
    pts = [(0, 0), (1000, 0), (1000, 1000)]
    curva = [dict(x=1000.0, y=0.0, curve=True, radius_ft=100.0)]
    pvc = _p("DRENAJE", "", 8, pts, material="PVC")
    rcp = _p("DRENAJE", "", 8, pts, material="Hormigón armado")
    sin = _p("DRENAJE", "", 8, pts, material="Material sin definir")        # sin definir: no se juzga
    av = _av(cat, [pvc, rcp, sin], curva)
    assert sorted((a.pipe, a.clase, a.nivel, a.info) for a in av) == [(0, "material", "ERROR", False),
                                                                       (0, "radio", "INFO", True)]


def test_aprobacion_de_una_pendiente_vuelve_a_pendiente_si_cambian_las_cotas():
    cat = _cat(dict(utilidad="ALCANTARILLADO", revisar="pendiente", min=1))
    p = _p("ALCANTARILLADO", "", 8, [(0, 0), (1000, 0)], inv_start=10.0, inv_end=9.95)
    av = _av(cat, [p])
    reg = []
    ap.aprobar(reg, av, [p], "ok", usuario="u")
    assert not ap.marcar(_av(cat, [p]), [p], reg)                            # misma situación: sigue aprobado
    p["inv_end"] = 9.9
    assert ap.marcar(_av(cat, [p]), [p], reg)                                # otras cotas: ya no aplica


def test_leer_fila_y_alcance():
    tipos = {("AGUA", "DISTRIBUCION PRINCIPAL")}
    r, mal = NR.leer_fila(["", "agua", "Distribución principal", "codo", "", "", "", "", "", "", "", "ángulo (°)",
                           "", "", "45; 90", "", "", "", "", ""], tipos)
    assert not mal and r["utilidad"] == "AGUA" and r["elemento"] == "CODO" and r["valores"] == [45, 90]
    assert r["revisar"] == "angulo" and r["nivel"] == "AVISO" and r["activa"]
    r2 = dict(r, valores=[11.25])
    assert NR.alcance(r) == NR.alcance(r2)                                    # mismo alcance: se suman
    assert NR.alcance(r) != NR.alcance(dict(r, si_diam=[6, 8]))

"""Números FIJOS de los conflictos (2026-10-29): resolver uno no renumera los demás."""
import sys, os
sys.path[:0] = [os.path.join(os.path.dirname(__file__), "..", "app")]

from nucleo import conflictos as C


def _it(x, y, pipes, clave="cruce"):
    return dict(clave=clave, x=x, y=y, pipes=pipes)


def test_resolver_uno_no_renumera_y_queda_resuelto():
    reg = C.Registro()
    todos = [_it(10, 10, [0, 1]), _it(50, 10, [2, 3]), _it(10, 90, [4, 5])]
    assert [c.id for c in C.numerar_fijo(todos, reg)] == ["C-1", "C-2", "C-3"]
    sin_el_1 = C.numerar_fijo(todos[1:], reg)                    # C-1 resuelto
    assert [c.id for c in sin_el_1] == ["C-2", "C-3"]
    assert [e["n"] for e in reg.resueltos()] == [1]
    nuevo = C.numerar_fijo(todos[1:] + [_it(5, 5, [6, 7])], reg)  # uno nuevo: el siguiente libre
    assert [c.id for c in nuevo] == ["C-2", "C-3", "C-4"]
    vuelve = C.numerar_fijo(todos, reg)                          # Ctrl+Z: vuelve con su número
    assert {c.id for c in vuelve} == {"C-1", "C-2", "C-3"}


def test_registro_va_y_vuelve_del_proyecto():
    reg = C.Registro()
    C.numerar_fijo([_it(10, 10, [0, 1]), _it(50, 10, [2, 3])], reg)
    C.numerar_fijo([_it(50, 10, [2, 3])], reg)
    otro = C.Registro.de_dict(reg.a_dict())
    assert [c.id for c in C.numerar_fijo([_it(50, 10, [2, 3])], otro)] == ["C-2"]
    assert otro.siguiente == {"C": 3}


def test_quitar_repetidos_por_celdas_da_lo_mismo_que_mirar_todos_y_es_rapido():
    """Mismo proyecto (2026-11-14): `_sin_repetidos` comparaba cada conflicto con todos los ya puestos y la ventana
    quedaba congelada ~20 s cada vez que llegaban los cálculos. Por celdas: los mismos, en el mismo orden."""
    import random
    import time
    from nucleo import conflictos as C

    def viejo(items):
        out = []
        for c in items:
            clave = (c["clave"], frozenset(i for i in c.get("pipes") or [] if i is not None))
            if any((o["clave"], frozenset(i for i in o.get("pipes") or [] if i is not None)) == clave
                   and (float(o["x"]) - float(c["x"])) ** 2 + (float(o["y"]) - float(c["y"])) ** 2 <= C.MISMO_PX ** 2
                   for o in out):
                continue
            out.append(c)
        return out

    rnd = random.Random(11)
    items = []
    for _ in range(1500):                                  # muchos casi en el mismo punto, a uno y otro lado de 1.5 px
        x, y = rnd.uniform(0, 60), rnd.uniform(0, 60)
        pipes = [rnd.randrange(4), rnd.randrange(4), None][:rnd.randrange(1, 4)]
        for _k in range(rnd.randrange(1, 4)):
            items.append(dict(clave=rnd.choice(["cruce", "choque", "escalon"]), pipes=list(pipes),
                              x=x + rnd.uniform(-1.6, 1.6), y=y + rnd.uniform(-1.6, 1.6)))
    assert [id(c) for c in C._sin_repetidos(items)] == [id(c) for c in viejo(items)]
    muchos = [dict(clave="cruce", pipes=[k, k + 1], x=(k % 300) * 9.0, y=(k // 300) * 9.0) for k in range(40000)]
    t = time.perf_counter()
    assert len(C._sin_repetidos(muchos)) == 40000
    assert time.perf_counter() - t < 3.0


def test_agrupar_por_celdas_da_lo_mismo_que_mirar_todos_y_es_rapido():
    """Proyecto de 29 mil utilidades (2026-11-13): `agrupar` miraba todos los grupos por cada conflicto y congelaba la
    ventana ~16 s («todo en blanco»). Por celdas: mismos grupos, mismo orden, y lineal."""
    import random
    import time
    from types import SimpleNamespace as N
    from nucleo import conflictos as C

    def viejo(lista, tol):
        grupos = []
        for c in lista:
            g = next((g for g in grupos if (g[0].x - c.x) ** 2 + (g[0].y - c.y) ** 2 <= tol * tol), None)
            if g is None:
                grupos.append([c])
            else:
                g.append(c)
        return grupos

    rnd = random.Random(7)
    for caso in range(40):
        n, tol = rnd.randint(0, 400), rnd.choice([0.0, 0.5, 4.0, 12.0])
        centros = [(rnd.uniform(-60, 60), rnd.uniform(-60, 60)) for _ in range(max(1, n // 6))]
        lista = []
        for i in range(n):                                  # amontonados (cadenas y bordes de celda) + sueltos
            if rnd.random() < 0.7:
                x, y = rnd.choice(centros)
                lista.append(N(x=x + rnd.uniform(-tol, tol) * 1.2, y=y + rnd.uniform(-tol, tol) * 1.2, i=i))
            else:
                lista.append(N(x=rnd.uniform(-80, 80), y=rnd.uniform(-80, 80), i=i))
        a = [[c.i for c in g] for g in viejo(lista, tol)]
        b = [[c.i for c in g] for g in C.agrupar(lista, tol)]
        assert a == b, (caso, n, tol)
    grandes = [N(x=rnd.uniform(0, 50000), y=rnd.uniform(0, 50000)) for _ in range(40000)]
    t = time.perf_counter()
    C.agrupar(grandes, 4.0)
    assert time.perf_counter() - t < 2.0


def test_conflicto_solo_cuando_se_tocan_tuberias_y_lo_demas_es_observacion():
    """Terminología 2026-11-13/14: C-n = dos o más tuberías se cruzan, chocan o se tocan; lo demás = observación, con
    un código por tipo (OC cotas, OU unión no constructible, OG geométrica, OV conexión vertical) y su numeración."""
    assert {k for k in C.TITULOS if C.categoria_de(k) == C.CONFLICTO} == {"cruce", "choque", "redes"}
    assert set(C.SUBTIPOS) == set(C.TITULOS) - C.CLAVES_CONFLICTO      # toda observación tiene subtipo
    items = [_it(10, 10, [0, 1]), _it(20, 10, [2], "escalon"), _it(30, 10, [3, 4], "choque"),
             _it(40, 10, [5], "codos"), _it(50, 10, [6, 7], "redes"), _it(60, 10, [8], "exceso"),
             _it(70, 10, [9], "retorno"), _it(80, 10, [1, 2], "pendiente"), _it(90, 10, [3], "inclinada")]
    cs = C.numerar(items)
    assert [(c.id, c.clave) for c in cs] == [("C-1", "cruce"), ("OC-1", "escalon"), ("C-2", "choque"),
                                             ("OG-1", "codos"), ("C-3", "redes"), ("OU-1", "exceso"),
                                             ("OG-2", "retorno"), ("OV-1", "pendiente"), ("OV-2", "inclinada")]
    assert {C.prefijo_de(k) for k in C.SUBTIPOS} == set(C.PREFIJOS_OBSERVACION)   # un código por tipo
    por = {c.clave: c for c in cs}
    assert por["cruce"].es_conflicto and por["cruce"].subtipo == "Conflicto"
    assert not por["escalon"].es_conflicto and por["escalon"].subtipo == "Observación de cotas"
    assert por["exceso"].subtipo == "Unión no constructible" and por["codos"].subtipo == "Observación geométrica"
    # en la lista: primero los conflictos y luego las observaciones, cada uno por número
    assert [c.id for c in C.numerar_fijo(items, C.Registro())] == ["C-1", "C-2", "C-3", "OC-1", "OU-1", "OG-1",
                                                                   "OG-2", "OV-1", "OV-2"]
    assert C.es_codigo("oc-12") and C.es_codigo("C-3") and C.es_codigo("OV-1")
    assert not C.es_codigo("N-3") and not C.es_codigo("AGUA-5") and not C.es_codigo("O-3")


def test_numeros_fijos_por_codigo_y_resolver_no_renumera():
    reg = C.Registro()
    todos = [_it(10, 10, [0, 1]), _it(50, 10, [2], "escalon"), _it(90, 10, [3, 4]), _it(130, 10, [5], "escalon")]
    assert [c.id for c in C.numerar_fijo(todos, reg)] == ["C-1", "C-2", "OC-1", "OC-2"]
    nuevo = C.numerar_fijo(todos[1:] + [_it(5, 50, [9], "retorno")], reg)   # C-1 resuelto, una observación nueva
    assert [c.id for c in nuevo] == ["C-2", "OC-1", "OC-2", "OG-1"]
    sin_oc1 = C.numerar_fijo([todos[2], todos[3]], reg)                     # se resuelve OC-1: OC-2 sigue OC-2
    assert [c.id for c in sin_oc1] == ["C-2", "OC-2"]
    assert sorted(reg.codigo(e) for e in reg.resueltos()) == ["C-1", "OC-1", "OG-1"]
    vuelve = C.numerar_fijo([_it(130, 10, [5], "escalon"), _it(55, 10, [2], "escalon")], reg)
    assert [c.id for c in vuelve] == ["OC-1", "OC-2"]                       # Ctrl+Z: con su número de siempre
    otro = C.Registro.de_dict(reg.a_dict())                                 # guardado y abierto
    assert otro.siguiente == {"C": 3, "OC": 3, "OG": 2}
    assert [c.id for c in C.numerar_fijo([_it(50, 10, [2], "escalon"), _it(9, 9, [7, 8])], otro)] == ["C-3", "OC-1"]


def test_proyecto_viejo_conserva_sus_numeros():
    """Registros de antes (todo C-n, o C-n y O-n): ningún número cambia; la observación toma su código por tipo con el
    MISMO número, y un código nuevo nunca reutiliza un número ya dado."""
    v1 = {"siguiente": 5, "entradas": [dict(n=1, clave="cruce", pipes=[0, 1], x=10, y=10, resuelto=False),
                                       dict(n=2, clave="escalon", pipes=[2], x=50, y=10, resuelto=False),
                                       dict(n=3, clave="codos", pipes=[3], x=90, y=10, resuelto=True),
                                       dict(n=4, clave="choque", pipes=[4, 5], x=130, y=10, resuelto=False)]}
    r1 = C.Registro.de_dict(v1)
    cs = C.numerar_fijo([_it(10, 10, [0, 1]), _it(50, 10, [2], "escalon"), _it(130, 10, [4, 5], "choque"),
                         _it(200, 10, [6], "exceso")], r1)
    assert [c.id for c in cs] == ["C-1", "C-4", "OC-2", "OU-5"]               # mismos números; el nuevo, el 5
    v2 = {"version": 2, "siguiente": {"C": 2, "O": 4},
          "entradas": [dict(n=1, clave="cruce", pipes=[0, 1], x=10, y=10, resuelto=False),
                       dict(n=3, clave="retorno", pipes=[2], x=50, y=10, resuelto=False)]}
    r2 = C.Registro.de_dict(v2)
    cs = C.numerar_fijo([_it(10, 10, [0, 1]), _it(50, 10, [2], "retorno"), _it(90, 10, [3], "escalon")], r2)
    assert [c.id for c in cs] == ["C-1", "OC-4", "OG-3"]                       # OC antes que OG en la lista


def test_avisos_de_normativa_con_numero_fijo():
    """Pedido 2026-11-14: los N-n (y R-n) se contaban en orden de lectura en cada informe: resolver uno los corría."""
    from types import SimpleNamespace as A
    reg = C.Registro()
    a1, a2, a3 = (A(clase="diametro", pipe=0, x=10, y=10), A(clase="material", pipe=1, x=50, y=10),
                  A(clase="diametro", pipe=2, x=90, y=10))
    rec, sin_tipo = A(clase="grosor", pipe=3, x=5, y=5), A(clase="tipo", pipe=4, x=1, y=1)
    cod = C.numerar_avisos([a1, a2, a3, rec, sin_tipo], reg)
    assert [cod[id(a)] for a in (a1, a2, a3, rec)] == ["N-1", "N-2", "N-3", "R-1"] and id(sin_tipo) not in cod
    cod = C.numerar_avisos([a1, a3, rec], reg)                               # se resolvió N-2
    assert [cod[id(a)] for a in (a1, a3, rec)] == ["N-1", "N-3", "R-1"]
    nuevo = A(clase="pendiente", pipe=5, x=0, y=0)
    cod = C.numerar_avisos([nuevo, a1, a3, rec], reg)
    assert cod[id(nuevo)] == "N-4"                                           # el siguiente; nada se corre
    # avisos y conflictos comparten el registro sin pisarse
    assert [c.id for c in C.numerar_fijo([_it(10, 10, [0, 1])], reg)] == ["C-1"]
    assert C.numerar_avisos([a1, a3, rec, nuevo], reg)[id(a3)] == "N-3"
    assert [reg.codigo(e) for e in reg.resueltos("avisos")] == ["N-2"]
    assert reg.resueltos() == []                                             # «Resolver» no lista avisos

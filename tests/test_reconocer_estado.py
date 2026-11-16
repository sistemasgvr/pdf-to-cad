"""Estado PURO de las filas del panel «Reconocer» (`nucleo/reconocer_estado`)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT / "app"), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from nucleo import reconocer_estado as RE  # noqa: E402


def _capa(name, **kw):
    d = {"name": name, "short": name, "path_count": 5, "on": True, "source": "ocg"}
    d.update(kw)
    return d


def _interp(layers=(), simbolos=(), rotulos_n=0):
    return {"layers": list(layers), "simbolos": list(simbolos), "rotulos_n": rotulos_n}


CAPAS = [_capa("C-ELEC-UNGD-E"), _capa("C-STRM-UGND-E")]


def test_partes_siguen_el_orden_del_reconocimiento():
    from reconocimiento import recognition
    assert RE.PARTES[:6] == tuple(recognition.SUPPORTED_UTILITIES)
    assert RE.PARTES[6:] == ("VALVULAS", "DIAMETROS", "ROTULOS")


def test_de_interpretacion_bloquea_utilidad_sin_capas():
    e = RE.de_interpretacion(RE.nuevo(), _interp(CAPAS), "h1")
    assert e.filas["GAS"].estado == "bloqueada"
    assert e.filas["GAS"].motivo
    assert e.filas["ELECTRICO"].estado == "pendiente"
    assert e.filas["ELECTRICO"].fuentes >= 1


def test_estilos_sin_asignar_bloquea():
    capas = [_capa("PDF_STYLE:x", source="style")]
    e = RE.de_interpretacion(RE.nuevo(), _interp(capas), "h1", roles_by_utility={})
    assert e.filas["AGUA"].estado == "bloqueada"
    assert "estilo" in e.filas["AGUA"].motivo.lower()
    e = RE.de_interpretacion(RE.nuevo(), _interp(capas), "h1",
                             roles_by_utility={"AGUA": {"lineas": ["PDF_STYLE:x"]}})
    assert e.filas["AGUA"].estado == "pendiente"
    assert e.filas["AGUA"].fuentes == 1


def test_capas_todas_ocultas_bloquea():
    e = RE.de_interpretacion(RE.nuevo(), _interp(CAPAS), "h1", hidden=("C-ELEC-UNGD-E",))
    assert e.filas["ELECTRICO"].estado == "bloqueada"
    assert "ocultas" in e.filas["ELECTRICO"].motivo


def test_valvulas_y_rotulos_por_conteo():
    e = RE.de_interpretacion(RE.nuevo(), _interp(CAPAS), "h1")
    assert e.filas["VALVULAS"].estado == "bloqueada"
    assert e.filas["ROTULOS"].estado == "bloqueada"
    e = RE.de_interpretacion(RE.nuevo(), _interp(CAPAS, simbolos=[{}, {}], rotulos_n=3), "h1")
    assert e.filas["VALVULAS"].fuentes == 2 and e.filas["VALVULAS"].estado == "pendiente"
    assert e.filas["ROTULOS"].fuentes == 3 and e.filas["ROTULOS"].estado == "pendiente"


def test_reinterpretar_misma_hoja_conserva_reconocidas_y_otra_hoja_reinicia():
    e = RE.de_interpretacion(RE.nuevo(), _interp(CAPAS), "h1")
    f = e.filas["ELECTRICO"]
    f.estado, f.firma, f.hechos = "reconocida", "A", 7
    e2 = RE.de_interpretacion(e, _interp(CAPAS), "h1")
    assert e2.filas["ELECTRICO"].estado == "reconocida"
    assert e2.filas["ELECTRICO"].firma == "A" and e2.filas["ELECTRICO"].hechos == 7
    e3 = RE.de_interpretacion(e2, _interp(CAPAS), "h2")
    assert e3.filas["ELECTRICO"].estado == "pendiente"
    assert e3.filas["ELECTRICO"].firma is None


def test_cambio_de_firma_desactualiza():
    e = RE.de_interpretacion(RE.nuevo(), _interp(CAPAS), "h1")
    f = e.filas["ELECTRICO"]
    f.estado, f.firma = "reconocida", "A"
    RE.marcar_cambios(e, {"ELECTRICO": "A"})
    assert e.filas["ELECTRICO"].estado == "reconocida"
    RE.marcar_cambios(e, {"ELECTRICO": "B"})
    assert e.filas["ELECTRICO"].estado == "desactualizada"


def test_firma_parte_estable_y_sensible():
    a = RE.firma_parte("AGUA", ["x", "y"], {"AGUA": {"l": ["a"]}}, [], 20.0, True)
    assert a == RE.firma_parte("AGUA", ["y", "x"], {"AGUA": {"l": ["a"]}}, [], 20.0, True)
    assert a != RE.firma_parte("AGUA", ["x"], {"AGUA": {"l": ["a"]}}, [], 20.0, True)
    assert a != RE.firma_parte("AGUA", ["x", "y"], {"AGUA": {"l": ["a"]}}, [], 20.0, False)


def test_diametros_necesita_una_utilidad():
    e = RE.de_interpretacion(RE.nuevo(), _interp(CAPAS), "h1")
    ok, clave, datos = RE.puede(e, "DIAMETROS")
    assert not ok and clave == RE.M_DIAMETROS
    assert datos == {"faltan": ["ELECTRICO", "DRENAJE"]}
    e.filas["ELECTRICO"].estado = "reconocida"
    assert RE.puede(e, "DIAMETROS")[0]
    assert RE.puede(e, "ELECTRICO")[0]
    ok, clave, datos = RE.puede(e, "GAS")
    assert not ok and clave == RE.M_SIN_CAPAS and datos == {}


def test_diametros_sin_utilidades_pendientes_sin_guion():
    vacia = RE.de_interpretacion(RE.nuevo(), _interp([]), "h1")
    ok, clave, datos = RE.puede(vacia, "DIAMETROS")
    assert not ok and clave == RE.M_DIAMETROS_NINGUNA and datos == {}
    assert "-" not in clave


def test_puede_explica_sin_interpretar_y_reconociendo():
    e = RE.nuevo()
    ok, clave, _ = RE.puede(e, "AGUA")
    assert not ok and clave == RE.M_SIN_INTERPRETAR
    e = RE.de_interpretacion(e, _interp(CAPAS), "h1")
    e.filas["ELECTRICO"].estado = "reconociendo"
    ok, clave, _ = RE.puede(e, "ELECTRICO")
    assert not ok and clave == RE.M_RECONOCIENDO


def test_valvulas_necesitan_una_utilidad_reconocida():
    e = RE.de_interpretacion(RE.nuevo(), _interp(CAPAS, simbolos=[{}]), "h1")
    ok, clave, _ = RE.puede(e, "VALVULAS")
    assert not ok and clave == RE.M_VALVULAS
    e.filas["DRENAJE"].estado = "reconocida"
    assert RE.puede(e, "VALVULAS") == (True, "", {})
    # sin símbolos, el motivo es ése aunque haya utilidades reconocidas
    e2 = RE.de_interpretacion(RE.nuevo(), _interp(CAPAS), "h1")
    e2.filas["DRENAJE"].estado = "reconocida"
    assert RE.puede(e2, "VALVULAS")[1] == RE.M_SIN_VALVULAS


def test_orden_todo():
    e = RE.de_interpretacion(RE.nuevo(), _interp(CAPAS, simbolos=[{}], rotulos_n=1), "h1")
    assert RE.orden_todo(e) == ["ELECTRICO", "DRENAJE", "VALVULAS", "DIAMETROS", "ROTULOS"]
    # sin ninguna utilidad que reconocer, ni válvulas ni diámetros entran
    vacia = RE.de_interpretacion(RE.nuevo(), _interp([], simbolos=[{}], rotulos_n=1), "h1")
    assert RE.orden_todo(vacia) == ["ROTULOS"]


def test_tras_reconocer_marca_la_fila_y_desactualiza_valvulas_y_diametros():
    e = RE.de_interpretacion(RE.nuevo(), _interp(CAPAS, simbolos=[{}]), "h1")
    for p in ("ELECTRICO", "VALVULAS", "DIAMETROS"):
        e.filas[p].estado, e.filas[p].firma = "reconocida", "A"
    e = RE.tras_reconocer(e, "DRENAJE", "F", 12, [{"k": 1}])
    f = e.filas["DRENAJE"]
    assert (f.estado, f.firma, f.hechos, f.verificar) == ("reconocida", "F", 12, [{"k": 1}])
    assert e.filas["VALVULAS"].estado == "desactualizada"
    assert e.filas["DIAMETROS"].estado == "desactualizada"
    assert e.filas["ELECTRICO"].estado == "reconocida"
    # reconocer válvulas no desactualiza nada más
    e = RE.tras_reconocer(e, "VALVULAS", "V", 3, [])
    assert e.filas["VALVULAS"].estado == "reconocida"
    assert e.filas["DIAMETROS"].estado == "desactualizada"
    # una fila pendiente de válvulas no pasa a desactualizada
    e2 = RE.de_interpretacion(RE.nuevo(), _interp(CAPAS, simbolos=[{}]), "h1")
    e2 = RE.tras_reconocer(e2, "ELECTRICO", "F", 1, [])
    assert e2.filas["VALVULAS"].estado == "pendiente"


def test_firma_parte_con_conjuntos_es_determinista():
    a = RE.firma_parte("AGUA", {"y", "x"}, {"AGUA": {"lineas": {"b", "a", "c"}}}, {"q", "p"}, 20.0, True)
    b = RE.firma_parte("AGUA", ["x", "y"], {"AGUA": {"lineas": ["a", "b", "c"]}}, ["p", "q"], 20.0, True)
    assert a == b


def test_ida_y_vuelta_dict():
    e = RE.de_interpretacion(RE.nuevo(), _interp(CAPAS), "h1")
    e.filas["ELECTRICO"].verificar = [{"k": 1}]
    e.filas["ELECTRICO"].unir_tramos = False
    assert RE.de_dict(RE.a_dict(e)) == e


def test_de_dict_viejo_sin_claves():
    e = RE.de_dict({})
    assert e.firma_hoja is None and set(e.filas) == set(RE.PARTES)
    e = RE.de_dict({"filas": {"GAS": {"estado": "reconocida"}}, "extra": 1})
    assert e.filas["GAS"].estado == "reconocida" and e.filas["GAS"].hechos == 0


def test_etiquetas_de_utilidades_como_el_reconocimiento():
    from reconocimiento import recognition
    for u in RE.UTILIDADES:
        assert RE.ETIQUETAS[u] == recognition.UTILITY_LABELS[u]
    assert set(RE.ETIQUETAS) == set(RE.PARTES)


def _capas_firma():
    def c(name, **kw):
        d = {"name": name, "short": name, "path_count": 5, "on": True, "source": "ocg"}
        d.update(kw)
        return d
    return [c("C-ELEC-UNGD-E"), c("C-WATR-UNGD-E"), c("G-XREF", letter_utilities=["AGUA"])]


def test_firma_de_utilidad_no_cambia_con_capas_de_otra():
    capas = _capas_firma()
    a = RE.firma_utilidad("AGUA", [], {}, [], 20.0, True, capas=capas)
    e = RE.firma_utilidad("ELECTRICO", [], {}, [], 20.0, True, capas=capas)
    assert RE.firma_utilidad("AGUA", ["C-ELEC-UNGD-E"], {}, [], 20.0, True, capas=capas) == a
    assert RE.firma_utilidad("ELECTRICO", ["C-ELEC-UNGD-E"], {}, [], 20.0, True, capas=capas) != e
    assert RE.firma_utilidad("AGUA", ["C-WATR-UNGD-E"], {}, [], 20.0, True, capas=capas) != a
    assert RE.firma_utilidad("AGUA", ["G-XREF"], {}, [], 20.0, True, capas=capas) != a    # su capa por letras


def test_firma_de_utilidad_roles_propios_y_reclamadas():
    capas = _capas_firma()
    base = {"AGUA": {}, "ELECTRICO": {}}
    a = RE.firma_utilidad("AGUA", [], base, [], 20.0, True, capas=capas)
    e = RE.firma_utilidad("ELECTRICO", [], base, [], 20.0, True, capas=capas)
    roles = {"AGUA": {"lineas": ["C-WATR-UNGD-E"]}, "ELECTRICO": {}}
    assert RE.firma_utilidad("AGUA", [], roles, [], 20.0, True, capas=capas) != a
    assert RE.firma_utilidad("ELECTRICO", [], roles, [], 20.0, True, capas=capas) == e
    # reclamar para GAS la capa que el agua tenía por sus letras cambia la del agua (no la del eléctrico)
    gas = {"GAS": {"lineas": ["G-XREF"]}}
    assert RE.firma_utilidad("AGUA", [], gas, [], 20.0, True, capas=capas) != a
    assert RE.firma_utilidad("ELECTRICO", [], gas, [], 20.0, True, capas=capas) == e


def test_firma_de_utilidad_sin_interpretacion_usa_todo():
    a = RE.firma_utilidad("AGUA", [], {}, [], 20.0, True)
    assert RE.firma_utilidad("AGUA", ["C-ELEC-UNGD-E"], {}, [], 20.0, True) != a
    assert RE.firma_utilidad("AGUA", [], {"GAS": {"lineas": ["X"]}}, [], 20.0, True) != a
    assert RE.firma_utilidad("AGUA", [], {}, [], 20.0, False) != a
    assert RE.firma_utilidad("AGUA", [], {}, [], 30.0, True) != a

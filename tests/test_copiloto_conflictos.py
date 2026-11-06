"""Copiloto: conflictos en tanda. La app prueba; el usuario marca; se aplica en un paso de deshacer."""
import pytest

from test_diametro_ia_ventana import _esperar
from test_ia_soluciones import _ventana


def tarjeta(d):
    return next((t["cop"] for t in reversed(d.turnos) if (t.get("cop") or {}).get("tipo") == "conflictos"), None)


def indice(d):
    return next(k for k in range(len(d.turnos) - 1, -1, -1) if (d.turnos[k].get("cop") or {}).get("tipo") == "conflictos")


@pytest.fixture
def esc(tmp_path):
    from ui.dialogos.ia_chat import PreguntaDialog
    w = _ventana(tmp_path)
    d = PreguntaDialog(w)
    d.enviar("resuelve los conflictos")
    _esperar(w, lambda: tarjeta(d) is not None, s=60)
    yield w, d
    w._dirty = False


def test_casillas_empiezan_desmarcadas_y_nada_se_aplica_solo(esc):
    w, d = esc
    assert tarjeta(d)["marcados"] == set() and not w._undo and any(f.prop for f in tarjeta(d)["filas"])
    d._enlace_copiloto(f"caplicar:{indice(d)}")
    assert not w._undo


def test_marcar_limpias_y_aplicar_es_un_ctrl_z(esc):
    w, d = esc
    t = indice(d)
    n = len(w._conflictos)
    d._enlace_copiloto(f"climpias:{t}")
    assert tarjeta(d)["marcados"] == {k for k, f in enumerate(tarjeta(d)["filas"]) if f.prop}
    d._enlace_copiloto(f"caplicar:{t}")
    assert len(w._undo) == 1 and w.bitacora[-1]["tipo"] == "conflictos" and w.bitacora[-1]["detalle"][0]["despues"]
    w._resultados_al_dia()
    assert len(w._conflictos) < n
    w.undo()
    w._resultados_al_dia()
    assert len(w._conflictos) == n and w.bitacora[-1]["deshecha"]


def test_marcar_una_a_mano(esc):
    w, d = esc
    t = indice(d)
    k = next(k for k, f in enumerate(tarjeta(d)["filas"]) if f.prop)
    d._enlace_copiloto(f"cmarca:{t}:{k}")
    assert tarjeta(d)["marcados"] == {k}
    d._enlace_copiloto(f"cmarca:{t}:{k}")
    assert tarjeta(d)["marcados"] == set()


def test_revalida_entre_aplicaciones(esc):
    w, d = esc
    c = tarjeta(d)
    f = next(f for f in c["filas"] if f.prop)
    aplicadas, saltadas = w.copiloto_aplicar_conflictos([f, f], c["firma"], c["sesion"])
    assert len(aplicadas) == 1 and len(saltadas) == 1 and saltadas[0][1]


def test_proyecto_cambiado_no_aplica(esc):
    w, d = esc
    t = indice(d)
    d._enlace_copiloto(f"climpias:{t}")
    w._push()
    w.pipes[0]["material"] = "PVC"
    pasos = len(w._undo)
    d._enlace_copiloto(f"caplicar:{t}")
    assert tarjeta(d)["estado"] == "caducado" and len(w._undo) == pasos


def test_doble_clic_aplica_una_vez(esc):
    w, d = esc
    t = indice(d)
    d._enlace_copiloto(f"climpias:{t}")
    d._enlace_copiloto(f"caplicar:{t}")
    d._enlace_copiloto(f"caplicar:{t}")
    assert len(w._undo) == 1


def test_fallo_en_mitad_de_la_tanda_no_deja_cambios(esc, monkeypatch):
    import copy
    from nucleo import soluciones
    w, d = esc
    c = tarjeta(d)
    filas = [f for f in c["filas"] if f.prop][:2]
    assert len(filas) == 2
    antes = copy.deepcopy(w.pipes)
    real, n = soluciones.aplicar, []

    def falla(pipes, prop):
        n.append(1)
        if len(n) == 4:                                # validar 1, aplicar 1, validar 2, aplicar 2
            raise RuntimeError("x")
        return real(pipes, prop)
    monkeypatch.setattr(soluciones, "aplicar", falla)
    with pytest.raises(RuntimeError):
        w.copiloto_aplicar_conflictos(filas, c["firma"], c["sesion"])
    assert w.pipes == antes and not w._undo and not w.bitacora


def test_causado_por_accesorio_no_lleva_casilla(tmp_path, monkeypatch):
    from ui.dialogos.ia_chat import PreguntaDialog
    w = _ventana(tmp_path)
    monkeypatch.setattr(w, "accesorio_de_conflicto", lambda cid: {"tipo": "codo"})
    d = PreguntaDialog(w)
    d.enviar("resuelve los conflictos")
    _esperar(w, lambda: tarjeta(d) is not None, s=60)
    assert tarjeta(d)["filas"] and all(f.prop is None and f.motivo for f in tarjeta(d)["filas"])
    w._dirty = False


def test_ir_a_un_conflicto_no_cierra_el_asistente(esc):
    w, d = esc
    w.mostrar_asistente(True, "chat")
    d._enlace_copiloto(f"irc:{indice(d)}:0")
    assert w.pila_derecha.currentIndex() == 1


def test_conflicto_que_desaparece_mientras_se_prueba_no_rompe_el_chat(tmp_path, monkeypatch):
    from ui.dialogos.ia_chat import PreguntaDialog
    w = _ventana(tmp_path)
    monkeypatch.setattr(w, "soluciones_de", lambda cid: (None, []))
    d = PreguntaDialog(w)
    d.enviar("resuelve los conflictos")
    _esperar(w, lambda: tarjeta(d) is not None, s=60)
    assert tarjeta(d)["filas"] == []
    d._pintar()
    w._dirty = False


def test_la_tarjeta_muestra_todo_lo_que_se_puede_marcar(tmp_path):
    from types import SimpleNamespace as N
    from ui.comun import theme
    from ui.dialogos import ia_chat_copiloto_html as HC
    filas = [N(c=N(id=f"C-{k}"), prop=N(texto="Bajar"), motivo="") for k in range(60)]
    html = HC.tarjeta(0, {"cop": {"tipo": "conflictos", "filas": filas, "marcados": set(), "estado": "confirmar",
                                  "resultado": ""}}, theme.tokens())
    assert "C-59" in html

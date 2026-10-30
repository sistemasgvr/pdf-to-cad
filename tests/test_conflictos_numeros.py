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
    assert otro.siguiente == 3

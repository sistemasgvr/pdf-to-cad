"""El recorrido del perfil está escrito dos veces: en la app (`nucleo/perfil_recorrido`) y en el plugin
(`PerfilRecorrido.cs`). Estas pruebas fallan si sus reglas se separan (deuda técnica cerrada 2026-11-08)."""
import os
import random
import re

from nucleo import perfil_recorrido as PR

CS = os.path.join(os.path.dirname(__file__), "..", "API-CIVIL", "proyecto1", "proyecto1", "PerfilRecorrido.cs")


def _cs():
    return open(CS, encoding="utf-8").read()


def _const(nombre):
    m = re.search(r"const double %s\s*=\s*([-0-9.]+)" % nombre, _cs())
    assert m, nombre
    return float(m.group(1))


def test_mismas_constantes():
    assert PR.TOL_FT == _const("TOL_COINCIDE")
    assert PR.DEFLEXION_MAX_DEG == _const("DEFLEXION_MAX_DEG")
    assert PR.EMPATE_DEG == _const("EMPATE_DEG")
    assert PR.ESTACION_INICIAL_FT == _const("EST_INICIAL")


def test_misma_regla_oeste_sur():
    """`DebeInvertirOesteSur` del plugin (Y hacia ARRIBA) = `_al_reves` de la app (Y del lienzo hacia ABAJO)."""
    cuerpo = re.search(r"DebeInvertirOesteSur\(.*?\{(.*?)\}", _cs(), re.S).group(1)
    razon = float(re.search(r"Math\.Abs\(dx\)\s*<\s*([0-9.]+)\s*\*", cuerpo).group(1))
    assert razon == PR.OESTE_SUR_RAZON
    assert "return y0 > y1" in cuerpo and "return x0 > x1" in cuerpo

    def plugin(x0, y0, x1, y1):                       # transcripción de la función C#
        dx, dy = x1 - x0, y1 - y0
        if abs(dx) < razon * abs(dy):
            return y0 > y1
        return x0 > x1

    class G:
        tipo = "pressure"
        nodos = []
    rnd = random.Random(7)
    for _ in range(500):
        a = (rnd.uniform(-100, 100), rnd.uniform(-100, 100))
        b = (rnd.uniform(-100, 100), rnd.uniform(-100, 100))
        g = G()
        g.nodos = [a, b]
        app = PR._al_reves(g, [0, 1], [0])
        assert app == plugin(a[0], -a[1], b[0], -b[1]), (a, b)   # el lienzo tiene la Y invertida

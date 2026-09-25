"""Resumen visual de la vista previa: clasificación PURA de los avisos."""
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT / "app"), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import recognition_summary as rs  # noqa: E402


def test_avisos_se_clasifican_con_etiqueta_corta():
    c = rs.classify_warning
    assert c("No se encontraron líneas de drenaje en esta hoja.").level == rs.PROBLEM
    n = c("Bóvedas sin línea cercana: 2.")
    assert (n.level, n.label) == (rs.REVIEW, "2 bóvedas sin línea")
    n = c("Curvas que quedan como polilínea: 1 tramo(s) — curva compuesta (radio variable) o …")
    assert (n.level, n.label) == (rs.REVIEW, "1 curva queda como polilínea")
    assert c("Codos como esquina + radio: 16.").level == rs.INFO
    n = c("Codos como esquina + radio: 5 (2 aproximado(s), a trazos: …; desvío máx. 2.1 pt).")
    assert (n.level, n.label) == (rs.REVIEW, "2 de 5 codos aproximados")
    assert c("Cobertura de guiones: 100.0%.").level == rs.INFO
    assert c("Cobertura de guiones: 97.2% (5 sin cubrir, en naranja).").level == rs.REVIEW
    assert c("Trazos repetidos (idénticos, en la misma capa): 404 — se usan una sola vez.").label \
        == "404 trazos repetidos (usados una vez)"
    assert c("Patrón «//» en una capa que no es «-A»: 2 línea(s) — …").level == rs.INFO
    assert c("Existentes A ABANDONAR (capa «-D», …): 3 línea(s) — hoy se importan activas; revisar.").level \
        == rs.REVIEW


def test_aviso_desconocido_no_se_esconde():
    n = rs.classify_warning("Algo nuevo que nadie clasificó todavía.", "AGUA")
    assert n.level == rs.REVIEW and n.utility == "AGUA"


def test_orden_y_cifras():
    pl = lambda ab=False, fil=0: SimpleNamespace(abandoned=ab, fillets={i: {} for i in range(fil)})
    r1 = SimpleNamespace(utility="ELECTRICO", drawable=[pl(), pl(True), pl(fil=2)], vault_pts=[(0, 0)],
                         coverage=1.0, warnings=["Codos como esquina + radio: 2.", "Bóvedas sin línea cercana: 1."])
    r2 = SimpleNamespace(utility="AGUA", drawable=[pl(True)], vault_pts=[], coverage=0.97,
                         warnings=["Esta hoja no tiene capas: …"])
    ns = rs.notices_for([r1, r2])
    assert [n.level for n in ns] == [rs.PROBLEM, rs.REVIEW, rs.INFO]
    st = [rs.stats_for(r) for r in (r1, r2)]
    assert (st[0].tramos, st[0].abandonadas, st[0].activas, st[0].codos, st[0].estructuras) == (3, 1, 2, 2, 1)
    tot = rs.totals(st)
    assert (tot.tramos, tot.abandonadas, tot.coverage) == (4, 2, 0.97)

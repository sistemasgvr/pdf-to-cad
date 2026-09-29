"""Codos desde la TINTA (2.ª pasada de `recognition.fit_fillets`, `recognition_arcs`).

AutoCAD exporta cada arco aplanado en cuerdas de flecha constante (~0.025 pt) y cada
recta como UN segmento; con eso la 2.ª pasada ve la curva en la tinta aunque la
centerline del núcleo la haya dejado en 1–2 vértices. Casos sintéticos (a zoom 1,
px = pt) y la hoja real que reportó el usuario (DU08 h.26: ramal de telecom que sale
TANGENTE a la vertical y termina libre).
"""
import math
from pathlib import Path

import pytest

import recognition as rec
import recognition_arcs as ra

SAG = 0.025          # flecha del aplanado de AutoCAD (medida en los 4 PDFs)


def _arc(ctr, r, a0, a1):
    """Arco aplanado como lo exporta AutoCAD (cuerdas de flecha ~SAG)."""
    step = 2.0 * math.acos(1.0 - SAG / r)
    n = max(2, int(math.ceil(abs(a1 - a0) / step)))
    return [(ctr[0] + r * math.cos(a0 + (a1 - a0) * k / n), ctr[1] + r * math.sin(a0 + (a1 - a0) * k / n))
            for k in range(n + 1)]


def _fit(pts, kinds, strokes, through=None, glyphs=()):
    pcs, sls = ra.arc_pieces(strokes, 1.0, glyphs)
    return rec.fit_fillets(pts, kinds, tol_px=1.0, arcs=pcs, ink_lines=sls, through_ink=through or {})


def test_trozos_de_arco_y_rectas_de_un_trazo():
    """Un trazo recta–arco–recta: un trozo de arco sobre el círculo y dos rectas."""
    arc = _arc((100.0, -150.0), 150.0, math.pi / 2, math.pi / 2 - math.radians(30))
    st = [(0.0, 0.0)] + arc + [(arc[-1][0] + 100 * math.cos(math.radians(30)),
                                arc[-1][1] - 100 * math.sin(math.radians(30)))]
    pcs, sls = ra.arc_pieces([st], 1.0)
    assert len(pcs) == 1
    assert pcs[0].r == pytest.approx(150.0, abs=0.2)
    assert len(sls) == 2 and all(math.dist(a, b) > 90 for a, b in sls)


def test_curva_abierta_que_el_nucleo_dejo_en_quiebres():
    """Recta → arco r=150 de 30° → recta. El núcleo la dejó en quiebres `bend`
    (centerline a ≤1 pt de la tinta): la 1.ª pasada no la intenta; la 2.ª la ve en
    la tinta y pone la esquina en la intersección de las rectas con el radio del plano."""
    import recognition_geom as geom
    a30 = math.radians(30)
    arc = _arc((100.0, -150.0), 150.0, math.pi / 2, math.pi / 2 - a30)
    end = (arc[-1][0] + 100 * math.cos(a30), arc[-1][1] - 100 * math.sin(a30))
    st = [(0.0, 0.0)] + arc + [end]
    pts = geom._douglas_peucker(st, 1.0)
    assert len(pts) >= 3
    out, kinds, fil = _fit(pts, ["end"] + ["bend"] * (len(pts) - 2) + ["end"], [st])
    assert len(fil) == 1
    (i, f), = fil.items()
    assert kinds[i] == "fillet" and len(out) == 3            # recta – codo – recta
    assert f["r_px"] == pytest.approx(150.0, abs=0.3)
    T = 150.0 * math.tan(a30 / 2)
    assert math.dist(out[i], (100.0 + T, 0.0)) < 0.3
    assert not f["loose"]


def test_ramal_tangente_a_otra_linea_que_termina_libre():
    """El caso del usuario (DU08 h.26): el ramal nace TANGENTE a una vertical (su
    extremo es `end` apoyado en ella) y termina libre. Recta = la línea que pasa por
    el extremo; el arco muere en el extremo libre (`node_b`)."""
    r = 30.0
    arc = _arc((r, 0.0), r, math.pi, math.pi + math.radians(80))       # sube y gira a la derecha
    pts = [arc[0], arc[len(arc) // 3], arc[2 * len(arc) // 3], arc[-1]]
    through = {(round(arc[0][0], 1), round(arc[0][1], 1)): (0.0, 1.0)}   # vertical que pasa
    out, kinds, fil = _fit(pts, ["end", "curve", "curve", "end"], [arc], through)
    assert len(fil) == 1
    (i, f), = fil.items()
    assert f["r_px"] == pytest.approx(r, abs=0.3)
    assert f["node_b"] and not f["loose"]
    assert abs(out[i][0]) < 0.3                         # la esquina está sobre la vertical
    assert math.dist(out[-1], arc[-1]) < 1e-6           # el extremo libre no se mueve


def test_curva_en_U_dos_codos_con_la_recta_del_medio():
    """Extremo libre → arco 90° → recta de 17 pt → arco 90° → bóveda: dos codos que
    comparten la recta del medio; el ancla compartido queda SOBRE esa recta, entre las
    dos tangencias (así ningún radio se recorta en el editor ni en el plugin)."""
    r = 10.8
    a1 = _arc((0.0, r), r, -math.pi / 2, 0.0)                          # (0,0) → (r, r)
    a2 = _arc((0.0, r + 17.0), r, 0.0, math.pi / 2)                    # (r, r+17) → (0, r+17+r)
    stop = (-11.0, 2 * r + 17.0)
    st = a1 + a2 + [stop]
    pts = [a1[0], a1[len(a1) // 2], a1[-1], a2[0], a2[len(a2) // 2], a2[-1], stop]
    out, kinds, fil = _fit(pts, ["end", "curve", "curve", "curve", "curve", "curve", "stop"], [st])
    assert len(fil) == 2
    assert all(f["r_px"] == pytest.approx(r, abs=0.3) for f in fil.values())
    i1, i2 = sorted(fil)
    assert i2 - i1 >= 2                                 # esquina · ancla(s) · esquina
    for q in out[i1 + 1:i2]:                            # anclas SOBRE la recta, entre las tangencias
        assert abs(q[0] - r) < 0.1 and r - 0.1 <= q[1] <= r + 17.1


def test_linea_poligonal_no_es_arco():
    """Guiones RECTOS con quiebres cada 80 pt sobre un círculo de r=500: los quiebres
    caen en el círculo pero los guiones se apartan 1.6 pt: no es un arco del plano."""
    R = 500.0
    verts = [(R * math.sin(t), R - R * math.cos(t)) for t in [k * 80.0 / R for k in range(5)]]
    strokes = []
    for a, b in zip(verts, verts[1:]):                  # guiones de 20 pt con huecos de 6
        L = math.dist(a, b)
        u = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        s = 0.0
        while s < L:
            e = min(L, s + 20.0)
            strokes.append([(a[0] + u[0] * s, a[1] + u[1] * s), (a[0] + u[0] * e, a[1] + u[1] * e)])
            s = e + 6.0
    kinds = ["end"] + ["bend"] * (len(verts) - 2) + ["end"]
    out, kinds2, fil = _fit(verts, kinds, strokes)
    assert fil == {}
    assert out == verts


def test_letras_del_linetype_no_son_arcos():
    """La panza de una letra (una «e» o «S» de 5 pt pegada a la línea) es un arco
    aplanado: dentro de la caja de un glifo del núcleo no cuenta."""
    e = _arc((50.0, 0.0), 2.5, 0.0, math.radians(300))
    assert ra.arc_pieces([e], 1.0)[0]                                  # sin cajas: parece arco
    assert ra.arc_pieces([e], 1.0, [(47.0, -3.0, 53.0, 3.0)])[0] == []


def test_esquina_de_linea_continua_no_queda_como_curva():
    """Agua/gas: línea continua con una esquina de 30° que el núcleo marcó `curve`.
    Sin tinta curva cerca es una esquina: se reetiqueta (la geometría no cambia)."""
    pts = [(0.0, 0.0), (100.0, 0.0), (100.0 + 86.6, 50.0)]
    st = [list(pts)]
    out, kinds, fil = _fit(pts, ["end", "curve", "end"], st)
    assert fil == {} and out == pts
    assert kinds == ["end", "corner", "end"]


def test_sin_tinta_la_primera_pasada_no_cambia():
    """Sin `arcs` (llamada de la 1.ª pasada sola) nada cambia: ni codos nuevos ni
    reetiquetado."""
    pts = [(0.0, 0.0), (100.0, 0.0), (186.6, 50.0)]
    assert rec.fit_fillets(pts, ["end", "curve", "end"], tol_px=1.0) == (pts, ["end", "curve", "end"], {})


DOCS = Path(r"C:/Users/bernu/OneDrive/Documentos/docs prueba")
DU08 = DOCS / "03-DU08_09_10-APDU-SEG-B-SEWER-PLAN_100P.pdf"


@pytest.mark.skipif(not DU08.is_file(), reason="PDF DU08 no disponible")
def test_du08_h26_ramal_de_telecom_es_codo_con_radio():
    """Reporte del usuario (2026-09-28): en DU08 h.26 el ramal de telecom existente
    que sale de la vertical y gira hacia la derecha quedaba como polilínea
    («end, curve, corner, curve, end»). Ahora es un codo de r≈27 pt (7.5 ft) con la
    esquina sobre la vertical, y la «U» de la misma capa son dos codos de r≈10.8 pt."""
    Z = 2.0
    res = rec.recognize_page(DU08, 25, utility="TELECOM", zoom=Z)
    fil = [(pl.pts_pdf[i], f) for pl in res.drawable for i, f in (pl.fillets or {}).items()]

    def near(x, y, tol=1.5):
        return [f for C, f in fil if math.dist((C[0] / Z, C[1] / Z), (x, y)) <= tol]
    ramal = near(1088.3, 298.4)
    assert ramal and ramal[0]["r_px"] / Z == pytest.approx(27.1, abs=0.5)
    assert not ramal[0]["loose"]
    u = near(1851.3, 587.1) + near(1851.3, 623.0)
    assert len(u) == 2 and all(f["r_px"] / Z == pytest.approx(10.8, abs=0.4) for f in u)
    # 2.º reporte: la curva en «S» junto a la bóveda (una curva hacia cada lado, con
    # una diagonal corta entre ellas) son DOS codos; la recta larga de arriba la
    # comparte con el codo de la 1.ª pasada junto a la bóveda (r≈44.7 pt)
    s = near(1134.8, 905.8) + near(1166.5, 938.3) + near(1140.8, 439.0)
    assert len(s) == 3 and all(f["r_px"] / Z == pytest.approx(45.0, abs=0.6) for f in s)
    assert not any(f["loose"] for f in s)

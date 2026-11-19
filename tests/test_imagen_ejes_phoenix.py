"""Ejes de la red en IMAGEN (`hoja/imagen_ejes`) sobre los mapas «QS SD» de Phoenix (Tarea 5): lo que da
`recognize_page` con DRENAJE ← la capa de línea de imagen, medido con `scripts/audit_ejes_imagen.py`.

Las mismas medidas de la auditoría: cobertura = tinta del color (sin sus símbolos) a ≤ w/2 + 1 px de lo DIBUJADO
(rectas entre tangencias y el arco de cada codo); «sin tinta» = un trozo de lo dibujado de más de 8 pt sin tinta
(fuera de las bóvedas). Se saltan si falta el PDF."""
import math
import os
import sys

import fitz
import pytest

_R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(_R, "app"), _R, os.path.join(_R, "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import audit_ejes_imagen as A  # noqa: E402
from hoja import imagen_ejes as IE  # noqa: E402

# 95 % de lo medido el 2026-11-18 (informe de la Tarea 5, ronda de corrección 1: h.7 con el canal fino en su capa
# es «continua»: 188 líneas, 114 diámetros)
# (2026-11-19, `recognition_imagen_rectas`: las piezas de una misma tubería se unen y los restos de la rejilla de los
# sumideros se van → menos líneas, mismos tramos; antes 236/178 líneas y 45/108 diámetros. `imagen_aros`: las patitas
# de la «M» de los buzones de aro fino ya no son líneas: h.3 176, h.7 176)
# 2026-11-19 (proyecto «Preuba lineas imagen»): las piezas de la MISMA tubería se unen (texto encima, costura,
# serrucho) y los lados de una rejilla no reconocida no son líneas: medido h.3 112, h.7 128
_MIN_LINEAS = {3: 105, 7: 120}
_MIN_DIAM = {3: 30, 7: 80}         # (2026-11-19, piezas unidas: 32/122 y 85/128; la misma proporción o más)
_RES = {}


def _sd_south():
    if not os.path.exists(A.PDFS["south"]):
        pytest.skip("falta el PDF de Phoenix SD South")
    if "doc" not in _RES:
        _RES["doc"] = fitz.open(A.PDFS["south"])
    return _RES["doc"]


def _reconocer_sd(doc, hoja):
    """(resultado, cobertura, tramos sin tinta) de la hoja `hoja` (1-based), memorizado."""
    if hoja not in _RES:
        page = doc[hoja - 1]
        cs = IE.capas(page)
        capa = A.capa_red(cs)
        assert capa is not None
        r = A.reconocer(doc, hoja - 1, capa)
        rgb = IE.rgb_de(capa)
        ejes = A.lineas_de(cs, capa)
        anchos = [p["width"] for p in cs if p["layer"] == capa and p["items"]]
        sim = [fitz.Rect(p["rect"]) for p in cs if IE.tipo_imagen(p["layer"]) == "sym" and IE.rgb_de(p["layer"]) == rgb]
        tinta = A.Tinta(page, rgb, sim, A.otras_lineas(cs, capa))
        der = page.derotation_matrix
        pls = [[tuple(fitz.Point(p) * der) for p in t] for pl in r.drawable for t in A.dibujado(pl)]
        w = A.ancho_tipico(anchos, ejes)
        cob, sin, _n = tinta.medir(pls, [A.ancho_de(pl, ejes, anchos, w) for pl in pls], A.cajas_bovedas(r, der))
        _RES[hoja] = (r, cob, [s for s in sin if s[1] > A.HUECO_GUION_PT])
    return _RES[hoja]


def _cobertura(res):
    return res[1]


def _tramos_sin_tinta(res):
    return len(res[2])


@pytest.mark.parametrize("hoja", [3, 7])
def test_sd_reconoce_drenaje(hoja):
    res = _reconocer_sd(_sd_south(), hoja)
    r = res[0]
    assert len(r.polylines) >= _MIN_LINEAS[hoja]
    assert sum(1 for pl in r.polylines if pl.diam_in) >= _MIN_DIAM[hoja]


# h.7 (y h.4, h.8): el azul trae, además de las bandas de la red, líneas FINAS a guiones (el canal). Van a su propia
# capa («fino», `imagen_grosores`): la de la red queda «continua» y sin uniones inventadas. Antes: cobertura 0.90,
# 8 tramos sin tinta.
@pytest.mark.parametrize("hoja", [3, 7])
def test_sd_cobertura_sin_tinta(hoja):
    res = _reconocer_sd(_sd_south(), hoja)
    # 0.96 (antes 0.97): la red en imagen va RECTA de buzón a buzón (pedido 2026-11-19) y no sigue el serrucho de la
    # banda pixelada; sin enderezar da 0.980/0.979, enderezada 0.976/0.969
    # 0.94 (2026-11-19): además las piezas de una tubería se unen en UNA recta y los lados de una rejilla no
    # reconocida quedan sin reconocer: medido 0.948/0.957
    assert _cobertura(res) >= 0.94
    assert _tramos_sin_tinta(res) == 0


def _cerca(pls, q):
    def d(a, b):
        ax, ay = a
        bx, by = b
        dx, dy = bx - ax, by - ay
        L = dx * dx + dy * dy
        t = 0.0 if L == 0 else max(0.0, min(1.0, ((q[0] - ax) * dx + (q[1] - ay) * dy) / L))
        return math.hypot(ax + t * dx - q[0], ay + t * dy - q[1])
    return min(pls, key=lambda pl: min(d(a, b) for a, b in zip(pl.pts_pdf, pl.pts_pdf[1:])))


def test_pioneer_preparatory_diametros():
    # hoja 4, junto a «PIONEER PREPARATORY» (vista): la vertical de la izquierda «24" HDPE» y la horizontal de
    # arriba «18" HDPE» (con el buzón M en medio)
    r = _reconocer_sd(_sd_south(), 4)[0]
    assert _cerca(r.polylines, (1157.0, 1060.0)).diam_in == 24
    assert _cerca(r.polylines, (1400.0, 910.0)).diam_in == 18


def _dist_a(pls, q):
    mejor = math.inf
    for pl in pls:
        for (ax, ay), (bx, by) in zip(pl, pl[1:]):
            dx, dy = bx - ax, by - ay
            L = dx * dx + dy * dy
            t = 0.0 if L == 0 else max(0.0, min(1.0, ((q[0] - ax) * dx + (q[1] - ay) * dy) / L))
            mejor = min(mejor, math.hypot(ax + t * dx - q[0], ay + t * dy - q[1]))
    return mejor


def _compuesta(doc, tmp_path):
    """South h.4 + h.5 ENTERAS, una al lado de la otra (sin puentes). Devuelve (comp, documento, ancho de la 1.ª,
    (dx, dy) = traslado de las piezas en la hoja compuesta: `composite.sheet_geometry` deja un margen)."""
    from hoja import composite as C
    W = doc[3].rect.width
    comp = C.Composite(pieces=[C.Piece(source=0, page=3, clip=[0, 0, 1, 1], x=0.0, y=0.0, src_scale=1.0),
                               C.Piece(source=0, page=4, clip=[0, 0, 1, 1], x=W, y=0.0, src_scale=1.0)],
                       scale_ft_per_pt=1.0, bridges=False)
    out = tmp_path / "sd_4_5.pdf"
    C.build_document(comp, [doc], {}, []).save(str(out))
    _w, _h, dx, dy = C.sheet_geometry(comp, lambda pz: (doc[pz.page].rect.width, doc[pz.page].rect.height))
    return comp, fitz.open(str(out)), W, (dx, dy)


# Ronda de corrección 1 (2026-11-18): la compuesta ya NO lee su imagen; los ejes de cada pieza son los de su hoja
# de origen llevados con `piece_map` (`imagen_compuesta`). Antes: la pieza h.4 daba 861 ejes contra 539 suelta y solo
# 51–56 % de los vértices reconocidos a ≤ 0.25 pt de la suelta.
def _medir_compuesta(tmp_path_factory):
    """(diferencia máx. de los ejes llevados contra los de la hoja suelta, [(hoja, nº ejes llevados, nº sueltos)],
    medidas de lo reconocido, ¿continua? (comp., h.4, h.5)), memorizado."""
    if "comp" in _RES:
        return _RES["comp"]
    from hoja import composite as C
    from hoja import leyenda_mapa_lectura as LML
    doc = _sd_south()
    comp, dc, W, (dx, dy) = _compuesta(doc, tmp_path_factory.mktemp("comp"))
    cs_c = IE.capas(dc[0])
    capa = A.capa_red(cs_c)
    assert capa == A.capa_red(IE.capas(doc[3]))
    inicios = LML.inicios_de_piezas(dc[0])
    dmax, cuentas = 0.0, []
    for k, hoja in enumerate((4, 5)):
        page = doc[hoja - 1]
        fn0 = C.piece_map(comp.pieces[k], (page.rect.width, page.rect.height), 1.0)
        rm = page.rotation_matrix

        def fn(q, fn0=fn0, rm=rm):
            v = fitz.Point(q) * rm
            a = fn0(v.x, v.y)
            return (a[0] + dx, a[1] + dy)
        sueltos = sorted((p["layer"], tuple(fn(q) for it in p["items"] for q in it[1:]))
                         for p in IE.capas(page) if IE.tipo_imagen(p["layer"]) == "line")
        llevados = sorted((p["layer"], tuple(tuple(q) for it in p["items"] for q in it[1:]))
                          for p in cs_c if IE.tipo_imagen(p["layer"]) == "line" and p["seqno"] == inicios[k])
        cuentas.append((hoja, len(llevados), len(sueltos)))
        for (la, a), (lb, b) in zip(sueltos, llevados):
            assert la == lb and len(a) == len(b)
            dmax = max(dmax, max(math.dist(x, y) for x, y in zip(a, b)))
    rc = A.reconocer(dc, 0, capa)
    medidas = []
    for k, hoja in enumerate((4, 5)):
        page = doc[hoja - 1]
        rs = A.reconocer(doc, hoja - 1, capa).drawable
        suelta = [pl.pts_pdf for pl in rs]
        un = C.piece_unmap(comp.pieces[k], (page.rect.width, page.rect.height), 1.0)
        dentro = [pl for pl in rc.drawable
                  if (k == 0) == (sum(p[0] for p in pl.pts_pdf) / len(pl.pts_pdf) - dx < W)]
        llevadas = [[un(x - dx, y - dy) for x, y in pl.pts_pdf] for pl in dentro]
        ds = [_dist_a(suelta, q) for pl in llevadas for q in pl]
        inv = [_dist_a(llevadas, q) for pl in suelta for q in pl]
        cortes_c = sum(1 for pl in dentro for p, kk in zip(pl.pts_pdf, pl.kinds)
                       if kk == "cut" and abs(p[0] - dx - W) > 5.0)
        cortes_s = sum(1 for pl in rs for kk in pl.kinds if kk == "cut")
        medidas.append((hoja, len(dentro), len(suelta), round(sum(d <= 0.25 for d in ds) / len(ds), 4),
                        round(sum(d <= 0.25 for d in inv) / len(inv), 4), cortes_c, cortes_s,
                        round(sum(d <= 1.0 for d in ds) / len(ds), 4), round(sum(d <= 1.0 for d in inv) / len(inv), 4)))
    continua = [any("trazo continuo" in x for x in r.warnings) for r in [rc] + [A.reconocer(doc, h, capa) for h in (3, 4)]]
    # (hoja, líneas comp., líneas suelta, vértices comp. a <= 0.25 pt de la suelta, vértices suelta a <= 0.25 pt de
    # la comp., cortes comp. fuera de la costura, cortes suelta, ídem a <= 1 pt)
    sys.stdout.write("\nejes: dif. máx %.2g pt %r; continua (comp., h.4, h.5): %r\ncompuesta vs sueltas: %r\n"
                     % (dmax, cuentas, continua, medidas))
    _RES["comp"] = (dmax, cuentas, medidas, continua)
    return _RES["comp"]


def test_compuesta_igual_a_sueltas(tmp_path_factory):
    # los EJES de cada pieza = los de su hoja suelta llevados a la compuesta (hojas enteras: sin recorte), a ≤ 1e-3 pt
    # (la matriz de la pieza va escrita en el PDF con 5 decimales); y lo reconocido sin cortes de más
    dmax, cuentas, medidas, _c = _medir_compuesta(tmp_path_factory)
    assert all(n_c == n_s > 0 for _h, n_c, n_s in cuentas), cuentas
    assert dmax <= 1e-3
    for _h, _nc, _ns, _fc, _fs, cortes_c, cortes_s, *_ in medidas:
        assert cortes_c <= cortes_s, medidas


# Lo RECONOCIDO: la decisión «trazo continuo» (tinta = eje) o núcleo se toma POR PIEZA en las capas de imagen de una
# compuesta (`recognition_imagen_piezas`, ronda de corrección 2): h.4 suelta es continua y h.5 no (sus bandas «en caja»
# salen en trozos). Antes, decidida en toda la hoja, la pieza h.4 daba 74 líneas contra 146 y 71 % / 68 % de los
# vértices a ≤ 0.25 pt; ahora 146 = 146 y 100 % / 100 % (h.5: 68 / 67, 100 % / 100 %).
def test_compuesta_reconoce_igual_que_sueltas(tmp_path_factory):
    _d, _c, medidas, _cont = _medir_compuesta(tmp_path_factory)
    for _h, _nc, _ns, f_c, f_s, *_ in medidas:
        assert f_c >= 0.95 and f_s >= 0.95, medidas

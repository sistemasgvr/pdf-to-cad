"""Pruebas del reconocedor OCG (eléctricas) — headless, sin Qt."""
import math
from pathlib import Path

import pytest

import recognition as rec

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "DU06_09_UD_Drainage_20251216(SUBMITTAL SET).pdf"

# Hoja 3 (índice 2) tiene C-ELEC-UNGD-E abundante según inspección previa.
ELEC_PAGE = 2


pytest.importorskip("fitz")


def test_selector_de_reconocimiento_ofrece_ambas_o_cada_utilidad():
    assert rec.normalize_utilities(None) == ("ELECTRICO", "DRENAJE")
    choices = rec.recognition_choices({"ELECTRICO", "DRENAJE"})
    assert [value for value, _label in choices] == [
        ("ELECTRICO", "DRENAJE"), ("ELECTRICO",), ("DRENAJE",)]
    assert rec.recognition_choices({"DRENAJE"})[0][0] == ("DRENAJE",)


def _poly_length(pts):
    return sum(
        math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
        for i in range(len(pts) - 1)
    )


@pytest.mark.skipif(not PDF.is_file(), reason="PDF de prueba DU06 no está en el repo")
def test_classify_ocg_elec_tokens():
    assert rec.classify_ocg("PS896|C-ELEC-UNGD-E") == "elec_ungd"
    assert rec.classify_ocg("C-ELEC-UNGD-A") == "elec_ungd"
    assert rec.classify_ocg("C-ELEC-OVHD-E") == "elec_ovhd"
    assert rec.classify_ocg("V-ELEC-POLE") == "structure"
    assert rec.classify_ocg("C-ELEC-VALT-E") == "structure"
    assert rec.classify_ocg("U-PROP-ESFV-ELEC-STRUCT") == "structure"
    # telecom / otras utilidades
    assert rec.classify_ocg("C-TELE-UNGD-E") is None
    assert rec.classify_ocg("C-STRM-UNGD-E") is None
    assert rec.classify_ocg("C-WATR-UNGD-E") is None
    assert rec.classify_ocg("C-NGAS-E") is None


def test_classify_ocg_variantes_de_otros_paquetes():
    """DU08/DU10 (carpeta de pruebas): las líneas PROPUESTAS «—E—» vienen como
    «UGND» (no «UNGD») y con un segmento de paquete en medio; los muros del
    ducto y la camisa del drenaje son contornos auxiliares, no centerline."""
    assert rec.classify_ocg("X|C-ELEC-3MI-UGND-N") == "elec_ungd"
    assert rec.classify_ocg("X|C-ELEC-UGND-N__UA4") == "elec_ungd"
    assert rec.classify_ocg("C-ELEC-UGND-N_LADWP-SELF-PERF-UNDEFINED-PKG") == "elec_ungd"
    assert rec.classify_ocg("C-ELEC-3MI-STRC-N") == "structure"
    assert rec.classify_ocg("C-ELEC-3MI-ANNO-TEXT-N--_") is None
    assert rec.classify_ocg("C-ELEC-UNGD-WALL-N") is None
    assert rec.classify_ocg("C-STRM-UNGD-CASE-N", "DRENAJE") is None


def test_classify_ocg_drainage_profile_separates_centerlines_and_structures():
    classify = lambda name: rec.classify_ocg(name, "DRENAJE")
    assert classify("XREF|C-STRM-UNGD-E") == "drain_ungd"
    assert classify("C-STRM-UNGD-N") == "drain_ungd"
    assert classify("V-STRM-MANH") == "structure"
    assert classify("V-STRM-CBSN") == "structure"
    assert classify("V-STRM-DRAN") == "structure"
    assert classify("C-STRM-CTCH-BASN-N") == "structure"
    assert classify("C-STRM-STRC-E") == "structure"
    # Muros, símbolos auxiliares y track drainage no son centerline.
    # «-NPLT» es sufijo del xref: la línea está impresa en el PDF (DU06 h.4).
    assert classify("XREF|C-STRM-UNGD-E-NPLT") == "drain_ungd"
    assert classify("C-STRM-UNGD-WALL-NPLT") is None
    assert classify("C-STRM-UNGD-WALL-E") is None
    assert classify("C-STRM-UNGD-STRC-N") is None
    assert classify("C-STRM-TRK-DRN-N") is None
    assert classify("C-ELEC-UNGD-E") is None


@pytest.mark.skipif(not PDF.is_file(), reason="PDF de prueba DU06 no está en el repo")
def test_recognize_page_drainage_reuses_geometry_without_electrical_layers():
    result = rec.recognize_page(PDF, page_index=2, utility="DRENAJE", zoom=1.0)
    assert result.utility == "DRENAJE"
    assert result.drawable
    assert result.vaults_geo
    for pl in result.drawable:
        short = pl.layer_ocg.split("|")[-1].upper()
        assert pl.kind == "drain_ungd"
        assert pl.utility_hint == "DRENAJE"
        assert "C-STRM-UNGD-" in short
        assert "WALL" not in short and "STRC" not in short
    pipes = rec.pipes_from_recognition(result, layer="DRENAJE")
    assert pipes and all(pipe["layer"] == "DRENAJE" for pipe in pipes)


@pytest.mark.skipif(not PDF.is_file(), reason="PDF de prueba DU06 no está en el repo")
def test_drenaje_hoja_de_perfil_no_se_reconoce_como_planta():
    """Hoja 17 (UD-215, «OFFSET MANHOLE PROFILES»): son 8 perfiles de
    estación/elevación, cada uno con escala vertical distinta de la
    horizontal. `C-STRM-UNGD-N` ahí dibuja el símbolo de la tubería en
    corte, no una centerline de planta — antes salían 9 «rutas» fabricadas
    con esa geometría; ahora `profile_view_regions` las excluye."""
    result = rec.recognize_page(PDF, page_index=16, utility="DRENAJE", zoom=1.0)
    assert result.drawable == []
    assert any("PERFIL" in w.upper() for w in result.warnings)


@pytest.mark.skipif(not PDF.is_file(), reason="PDF de prueba DU06 no está en el repo")
def test_drenaje_hoja_mixta_conserva_la_planta_y_excluye_solo_el_perfil():
    """Hoja 3 tiene 3 perfiles pequeños arriba (CB-201/201.5/203 LATERAL
    PROFILE) y la planta real abajo: solo se excluye lo de arriba."""
    result = rec.recognize_page(PDF, page_index=2, utility="DRENAJE", zoom=1.0)
    assert result.drawable
    assert any("PERFIL" in w.upper() for w in result.warnings)


@pytest.mark.skipif(not PDF.is_file(), reason="PDF de prueba DU06 no está en el repo")
def test_drenaje_sin_falso_marcador_de_abandonada_por_la_d_de_sd():
    """El linetype de drenaje embebe "sd" (dos letras); la «d» sale partida
    en dos paths del PDF (asta recta + bucle) y esa asta, sin
    `GLYPH_STROKE_MIN_REPEAT`, se confundía con la barra «/» de abandonada
    — activa en TODAS las hojas de planta de drenaje. La «e» de eléctrico
    (una sola letra, sin asta huérfana) no tiene ese problema."""
    for page_index in range(2, 16):
        result = rec.recognize_page(PDF, page_index=page_index, utility="DRENAJE", zoom=1.0)
        assert not any("marcadores" in w.lower() and "activa" in w.lower() for w in result.warnings), (
            page_index, result.warnings)


@pytest.mark.skipif(not PDF.is_file(), reason="PDF de prueba DU06 no está en el repo")
def test_drenaje_cobertura_cerca_del_100_en_las_hojas_de_planta():
    """Con el asta de la «d» ya no confundida con guión de línea y el
    guión que entra en una bóveda/esquina ya no contado «sin cubrir»
    (`_touches_vault`/`_touches_corner`), la cobertura de las 14 hojas de
    planta de drenaje del DU06 debe quedar prácticamente al 100 %."""
    low = []
    for page_index in range(2, 16):
        result = rec.recognize_page(PDF, page_index=page_index, utility="DRENAJE", zoom=1.0)
        if result.drawable and result.coverage < 0.995:
            low.append((page_index, result.coverage))
    assert not low, low


@pytest.mark.skipif(not PDF.is_file(), reason="PDF de prueba DU06 no está en el repo")
def test_drenaje_huerfanos_no_cuentan_postes_ni_cajas_bajo_vault_min_ft():
    """«Bóvedas sin línea cercana» solo debe contar símbolos que de verdad
    califican como bóveda (≥ VAULT_MIN_FT); antes de filtrar por tamaño en
    el mismo punto donde se cuentan (no solo al armar `vaults_geo`), una
    hoja sin ninguna línea de drenaje (hoja 2, «KEY MAP») igual reportaba
    decenas de huérfanos: eran símbolos pequeños del fondo, no bóvedas."""
    result = rec.recognize_page(PDF, page_index=1, utility="DRENAJE", zoom=1.0)
    assert result.vault_orphans_px == []


@pytest.mark.skipif(not PDF.is_file(), reason="PDF de prueba DU06 no está en el repo")
def test_recognize_page_elec_ungd():
    result = rec.recognize_page(PDF, page_index=ELEC_PAGE, zoom=1.0)
    assert result.utility == "ELECTRICO"
    assert result.page_index == ELEC_PAGE
    assert result.scale_ft_per_pt > 0

    drawable = result.drawable
    assert len(drawable) >= 1, "debe haber al menos una polilínea eléctrica"

    # Todas las dibujables son elec_ungd con pts
    for pl in drawable:
        assert pl.kind == "elec_ungd"
        assert pl.utility_hint == "ELECTRICO"
        assert len(pl.pts_pdf) >= 2
        assert "ELEC" in pl.layer_ocg.upper()
        assert "TELE" not in pl.layer_ocg.upper()
        assert "STRM" not in pl.layer_ocg.upper()
        assert "WATR" not in pl.layer_ocg.upper()

    # Resumen incluye C-ELEC-UNGD
    ocgs = " ".join(s["ocg"].upper() for s in result.ocg_summary)
    assert "C-ELEC-UNGD" in ocgs
    # No debe reportar agua/drenaje/telecom como electrical
    for s in result.ocg_summary:
        up = s["ocg"].upper()
        assert "C-WATR" not in up and "C-STRM" not in up
        assert "C-TELE" not in up and "TELE-" not in up.replace("C-TELE", "")


@pytest.mark.skipif(not PDF.is_file(), reason="PDF de prueba DU06 no está en el repo")
def test_centerlines_are_clean_not_glyph_sized():
    """Las polilíneas dibujables deben ser centerlines (largas), no restos de «e»."""
    result = rec.recognize_page(PDF, page_index=ELEC_PAGE, zoom=1.0)
    drawable = result.drawable
    assert drawable, "hace falta al menos una centerline"

    for pl in drawable:
        assert _poly_length(pl.pts_pdf) >= rec.MIN_CHAIN_LEN_PT * 0.9

    # Con limpieza activa no deberían quedar cadenas diminutas tipo glifo
    short = [pl for pl in drawable if _poly_length(pl.pts_pdf) < rec.MIN_CHAIN_LEN_PT]
    assert short == []


@pytest.mark.skipif(not PDF.is_file(), reason="PDF de prueba DU06 no está en el repo")
def test_bridge_yields_longer_continuous_runs():
    """Con puente 80 pt, las centerlines deben ser menos fragmentadas que guiones sueltos."""
    # Hoja 13 (índice 12): muchas eléctricas con linetype de letra
    page = 12
    result = rec.recognize_page(PDF, page_index=page, zoom=1.0)
    drawable = result.drawable
    assert drawable, "debe reconocer eléctricas en hoja 13"
    lengths = sorted(_poly_length(pl.pts_pdf) for pl in drawable)
    # Al menos una corrida larga (varios guiones cosidos, >> un guion ~22 pt)
    assert lengths[-1] >= 80.0, f"max len={lengths[-1]}"
    # Mediana no debería ser solo un guion aislado (~22 pt)
    med = lengths[len(lengths) // 2]
    assert med >= 40.0, f"median len={med}, n={len(lengths)}"


@pytest.mark.skipif(not PDF.is_file(), reason="PDF de prueba DU06 no está en el repo")
def test_merge_collinear_respects_max_bridge():
    import fitz
    import vector_pipeline as VP
    # Dos guiones colineales con hueco 50 pt (como letra e)
    a0, a1 = fitz.Point(0, 0), fitz.Point(20, 0)
    b0, b1 = fitz.Point(70, 0), fitz.Point(90, 0)  # gap 50
    segs = [(a0, a1), (b0, b1)]
    narrow = VP.merge_collinear_segments(segs, max_bridge=20.0)
    assert len(narrow) == 2  # no puentea
    wide = VP.merge_collinear_segments(segs, max_bridge=80.0)
    assert len(wide) == 1
    assert abs(wide[0][3] - 90.0) < 1e-6  # span 0..90


@pytest.mark.skipif(not PDF.is_file(), reason="PDF de prueba DU06 no está en el repo")
def test_pipes_from_recognition_electrico():
    result = rec.recognize_page(PDF, page_index=ELEC_PAGE, zoom=1.0)
    pipes = rec.pipes_from_recognition(result, layer="ELECTRICO")
    assert pipes, "debe producir al menos un pipe"
    for p in pipes:
        assert p["layer"] == "ELECTRICO"
        assert len(p["pts"]) >= 2
        assert p["ab"] is False
        assert p["diam_unit"] == "in"
        assert "material" in p


@pytest.mark.skipif(not PDF.is_file(), reason="PDF de prueba DU06 no está en el repo")
def test_recognize_title_page_warns():
    # Página 0 suele ser portada sin C-ELEC-UNGD
    result = rec.recognize_page(PDF, page_index=0, zoom=1.0)
    assert result.page_index == 0
    assert len(result.drawable) == 0
    assert any("No se encontraron" in w or "Ninguna capa" in w for w in result.warnings)


def test_suggest_layer_role():
    assert rec.suggest_layer_role("PS|C-ELEC-UNGD-E") == rec.ROLE_LINEAS
    assert rec.suggest_layer_role("PS|C-ELEC-VALT-E") == rec.ROLE_BUZONES
    assert rec.suggest_layer_role("PS|V-ELEC-MANH") == rec.ROLE_BUZONES
    assert rec.suggest_layer_role("PS|C-ROAD-CURB") == rec.ROLE_IGNORAR


def test_inject_vault_vertices_snaps_to_pipe():
    pipes = [{"layer": "ELECTRICO", "pts": [(0.0, 0.0), (100.0, 0.0)], "ab": False}]
    snapped, skipped = rec.inject_vault_vertices(pipes, [(50.0, 5.0)], max_dist=20.0)
    assert snapped == 1 and skipped == 0
    assert len(pipes[0]["pts"]) == 3
    assert abs(pipes[0]["pts"][1][0] - 50.0) < 1e-6
    # lejos → skip
    snapped2, skipped2 = rec.inject_vault_vertices(pipes, [(50.0, 500.0)], max_dist=20.0)
    assert snapped2 == 0 and skipped2 == 1


@pytest.mark.skipif(not PDF.is_file(), reason="PDF de prueba DU06 no está en el repo")
def test_layer_roles_force_ungd_and_valt():
    """Con roles explícitos se reconocen líneas y bóvedas en hoja con eléctricas."""
    page = 13  # UD-212 / hoja 14 UI
    import fitz
    doc = fitz.open(str(PDF))
    drawings = doc[page].get_drawings()
    ungd = next((d.get("layer") for d in drawings if d.get("layer") and "C-ELEC-UNGD" in d["layer"].upper()), None)
    valt = next((d.get("layer") for d in drawings if d.get("layer") and "C-ELEC-VALT" in d["layer"].upper()), None)
    doc.close()
    assert ungd and valt
    roles = {rec.ROLE_LINEAS: [ungd], rec.ROLE_BUZONES: [valt]}
    result = rec.recognize_page(PDF, page_index=page, zoom=1.0, layer_roles=roles)
    assert result.drawable, "debe haber centerlines con roles"
    assert result.vault_pts, "debe haber centroides de bóveda"
    pipes = rec.pipes_from_recognition(result)
    assert pipes and all(len(p["pts"]) >= 2 for p in pipes)
    n_before = sum(len(p["pts"]) for p in pipes)
    snapped, skipped = rec.inject_vault_vertices(pipes, result.vault_pts, max_dist=200.0)
    assert snapped + skipped == len(result.vault_pts)
    assert sum(len(p["pts"]) for p in pipes) >= n_before


def _chain_length(pts):
    return sum(
        math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
        for i in range(len(pts) - 1)
    )


@pytest.mark.skipif(not PDF.is_file(), reason="PDF de prueba DU06 no está en el repo")
def test_sheet14_quality_via_public_api():
    """Hoja 14 (UD-212): cobertura alta, bóvedas como vértices, tipos de vértice
    coherentes y sin polilíneas degeneradas."""
    result = rec.recognize_page(PDF, page_index=13, zoom=1.0)
    assert result.coverage >= 0.98, result.coverage
    chains = result.drawable
    assert chains and len(chains) <= 16      # incluye stubs y ticks que tocan bóvedas
    for pl in chains:
        assert len(pl.kinds) == len(pl.pts_pdf)
        assert pl.kinds[0] != "curve" and pl.kinds[-1] != "curve"
        # Trozos cortos que tocan una bóveda se conservan (regla del usuario: todo
        # lo que hay en la capa); el resto debe ser una centerline real.
        if "stop" not in pl.kinds:
            assert _chain_length(pl.pts_pdf) >= rec.MIN_CHAIN_LEN_PT
    kinds = [k for pl in chains for k in pl.kinds]
    # Nodo interior solo donde una línea atraviesa la bóveda (hoja 14: la de
    # 988,1223); las demás llegadas paran en el borde ("stop").
    assert kinds.count("vault") >= 3 and kinds.count("stop") >= 3
    assert len(result.vault_pts) >= 1
    # Cada bóveda reportada coincide con un vértice de alguna polilínea
    verts = [p for pl in chains for p in pl.pts_pdf]
    for vx, vy in result.vault_pts:
        assert any(math.hypot(vx - x, vy - y) < 0.5 for x, y in verts)
    lengths = sorted(_chain_length(c.pts_pdf) for c in chains)
    assert lengths[-1] >= 80.0


@pytest.mark.skipif(not PDF.is_file(), reason="PDF de prueba DU06 no está en el repo")
def test_pipes_carry_vertex_kinds():
    result = rec.recognize_page(PDF, page_index=13, zoom=1.0)
    pipes = rec.pipes_from_recognition(result)
    assert pipes
    for p in pipes:
        assert p["origen"] == "reconocido"
        assert len(p["vertex_kinds"]) == len(p["pts"])


def test_is_abandoned_ocg():
    assert rec.is_abandoned_ocg("PS89616000-A1-UE-REF-EXIST_ELEC|C-ELEC-UNGD-A")
    assert rec.is_abandoned_ocg("C-WATR-UNGD-A") and rec.is_abandoned_ocg("C-ELEC-ABND")
    assert not rec.is_abandoned_ocg("C-ELEC-UNGD-E") and not rec.is_abandoned_ocg("PS-A1-UE|C-ELEC-VALT-E")
    assert not rec.is_abandoned_ocg("") and not rec.is_abandoned_ocg(None)


@pytest.mark.skipif(not PDF.is_file(), reason="PDF de prueba DU06 no está en el repo")
def test_hoja9_abandonadas_se_reconocen_aparte_y_marcadas_ab():
    """Hoja 9: C-ELEC-UNGD-A (linetype «──/── e ──», bóveda dibujada en la misma
    capa). Salen como pipes aparte con ab=True; las barras «/» no quedan sin
    cubrir; la línea para en el borde del contorno (no lo cruza ni lo dibuja)."""
    result = rec.recognize_page(PDF, 8, zoom=1.0)
    ab = [p for p in result.drawable if p.abandoned]
    act = [p for p in result.drawable if not p.abandoned]
    assert len(ab) >= 4 and len(act) >= 6
    assert all("C-ELEC-UNGD-A" in p.layer_ocg for p in ab) and all("C-ELEC-UNGD-A" not in p.layer_ocg for p in act)
    assert result.coverage >= 0.97
    # ninguna abandonada pasa por el interior del contorno (1562..1620 × 1001..1037 pt, zoom 1 → px)
    for p in ab:
        for (x, y), k in zip(p.pts_pdf, p.kinds):
            assert not (1564 < x < 1618 and 1003 < y < 1035), (x, y, k)
    stops = [(x, y) for p in ab for (x, y), k in zip(p.pts_pdf, p.kinds) if k == "stop"]
    assert len(stops) >= 4
    summ = {s["ocg"].split("|")[-1]: s for s in result.ocg_summary}
    assert summ["C-ELEC-UNGD-A"]["abandoned"] and not summ["C-ELEC-UNGD-E"]["abandoned"]
    pipes = rec.pipes_from_recognition(result)
    assert sum(1 for p in pipes if p["ab"]) == len(ab) and len(pipes) == len(ab) + len(act)


@pytest.mark.skipif(not PDF.is_file(), reason="PDF de prueba DU06 no está en el repo")
def test_cada_capa_se_reconstruye_sola_no_mezcla_esfv():
    """Hoja 4: C-ELEC-UNGD-E y U-PROP-ESFV-ELEC-STRUCT son OCGs distintas.
    Aunque las dos se marquen como «líneas», cada pipe pertenece a UNA capa
    y la geometría UNGD no cambia al incluir ESFV."""
    page = 3  # UI hoja 4
    import fitz
    doc = fitz.open(str(PDF))
    names = sorted({d.get("layer") or "" for d in doc[page].get_drawings() if d.get("layer")})
    doc.close()
    ungd = next((n for n in names if "C-ELEC-UNGD-E" in n.upper() and "-A" not in n.split("|")[-1].upper()), None)
    esfv = next((n for n in names if "ESFV-ELEC-STRUCT" in n.upper()), None)
    valt = next((n for n in names if "C-ELEC-VALT-E" in n.upper()), None)
    assert ungd and esfv
    only = rec.recognize_page(
        PDF, page_index=page, zoom=1.0,
        layer_roles={rec.ROLE_LINEAS: [ungd], rec.ROLE_BUZONES: [valt] if valt else []})
    both = rec.recognize_page(
        PDF, page_index=page, zoom=1.0,
        layer_roles={rec.ROLE_LINEAS: [ungd, esfv], rec.ROLE_BUZONES: [valt] if valt else []})
    ungd_only = [p for p in only.drawable]
    ungd_both = [p for p in both.drawable if p.layer_ocg == ungd]
    esfv_both = [p for p in both.drawable if p.layer_ocg == esfv]
    assert ungd_only and all(p.layer_ocg == ungd for p in ungd_only)
    assert all("+" not in p.layer_ocg for p in both.drawable)
    # UNGD no absorbe la otra capa: mismas polilíneas (mismos n° de pts)
    assert [len(p.pts_pdf) for p in ungd_only] == [len(p.pts_pdf) for p in ungd_both]
    # ESFV como línea produce pipes propias, no mezcla vértices en UNGD
    if esfv_both:
        assert all(p.layer_ocg == esfv for p in esfv_both)


@pytest.mark.skipif(not PDF.is_file(), reason="PDF de prueba DU06 no está en el repo")
def test_esfv_como_buzon_no_deforma_ungd():
    """Marcar ESFV-STRUCT como bóveda no debe cambiar las centerlines UNGD."""
    page = 3
    import fitz
    doc = fitz.open(str(PDF))
    names = sorted({d.get("layer") or "" for d in doc[page].get_drawings() if d.get("layer")})
    doc.close()
    ungd = next((n for n in names if "C-ELEC-UNGD-E" in n.upper() and "-A" not in n.split("|")[-1].upper()), None)
    esfv = next((n for n in names if "ESFV-ELEC-STRUCT" in n.upper()), None)
    valt = next((n for n in names if "C-ELEC-VALT-E" in n.upper()), None)
    assert ungd and esfv
    base = rec.recognize_page(
        PDF, page_index=page, zoom=1.0,
        layer_roles={rec.ROLE_LINEAS: [ungd], rec.ROLE_BUZONES: [valt] if valt else []})
    mixed = rec.recognize_page(
        PDF, page_index=page, zoom=1.0,
        layer_roles={rec.ROLE_LINEAS: [ungd],
                     rec.ROLE_BUZONES: ([valt] if valt else []) + [esfv]})
    a = [(tuple(p.pts_pdf), tuple(p.kinds)) for p in base.drawable]
    b = [(tuple(p.pts_pdf), tuple(p.kinds)) for p in mixed.drawable]
    assert a == b


# ─────────────── patrón de marcadores «/» (abandonadas) ───────────────
def _abandoned_doc(tmp_path, lines):
    """PDF sintético con capas OCG reales. `lines` = [(ocg, a, b, marker_every | None, double)]:
    línea a guiones (21.6/3.6) y, si `marker_every`, barras «/» (o «//») cada tanto."""
    import fitz
    doc = fitz.open(); page = doc.new_page(width=1000, height=800)
    ocgs = {}
    for ocg, a, b, every, double in lines:
        if ocg not in ocgs:
            ocgs[ocg] = doc.add_ocg(ocg)
        ax, ay = a; bx, by = b
        L = math.hypot(bx - ax, by - ay); ux, uy = (bx - ax) / L, (by - ay) / L
        nx, ny = -uy, ux
        t = 0.0
        while t < L:
            e = min(L, t + 21.6)
            sh = page.new_shape(); sh.draw_line(fitz.Point(ax + ux * t, ay + uy * t), fitz.Point(ax + ux * e, ay + uy * e))
            sh.finish(color=(0.5, 0.5, 0.5), width=0.7, oc=ocgs[ocg], closePath=False); sh.commit()
            t = e + 3.6
        if every:
            t = every / 2 if every > 0 else L / 2
            step = every if every > 0 else L * 10
            while t < L:
                for off in ((-1.6, 1.6) if double else (0.0,)):
                    cx, cy = ax + ux * (t + off), ay + uy * (t + off)
                    dx, dy = ux * 1.9 + nx * 3.3, uy * 1.9 + ny * 3.3
                    sh = page.new_shape(); sh.draw_line(fitz.Point(cx - dx, cy - dy), fitz.Point(cx + dx, cy + dy))
                    sh.finish(color=(0.5, 0.5, 0.5), width=0.7, oc=ocgs[ocg], closePath=False); sh.commit()
                t += step
    out = tmp_path / "ab.pdf"; doc.save(str(out)); doc.close()
    return out


def test_abandonada_exige_capa_A_y_patron_de_marcadores(tmp_path):
    """Capa «-A» con «/» a paso regular en toda la línea → abandonada; el ramal
    corto de la misma capa (más corto que el paso) hereda el veredicto."""
    pdf = _abandoned_doc(tmp_path, [
        ("C-ELEC-UNGD-A", (100, 300), (700, 300), 60.0, False),
        ("C-ELEC-UNGD-A", (400, 300), (400, 340), None, False),
    ])
    res = rec.recognize_page(pdf, 0, zoom=1.0)
    assert res.drawable and all(p.abandoned for p in res.drawable), [(p.layer_ocg, p.abandoned) for p in res.drawable]
    assert res.coverage >= 0.99


def test_dos_barras_sueltas_no_hacen_abandonada(tmp_path):
    """Capa «-A» pero con un solo «//» en toda la línea: no sigue el patrón →
    NO se marca abandonada y el preview lo avisa."""
    pdf = _abandoned_doc(tmp_path, [("C-ELEC-UNGD-A", (100, 300), (700, 300), -1, True)])
    res = rec.recognize_page(pdf, 0, zoom=1.0)
    assert res.drawable and not any(p.abandoned for p in res.drawable)
    assert any("NO se marcan como abandonadas" in w for w in res.warnings)
    assert res.coverage >= 0.99                                    # el «//» sigue siendo glifo


def test_patron_de_marcadores_en_capa_activa_no_abandona(tmp_path):
    """El patrón «/» simple regular en una capa ACTIVA no la vuelve abandonada
    (manda la capa), pero se avisa para revisar."""
    pdf = _abandoned_doc(tmp_path, [("C-ELEC-UNGD-E", (100, 300), (700, 300), 60.0, False)])
    res = rec.recognize_page(pdf, 0, zoom=1.0)
    assert res.drawable and not any(p.abandoned for p in res.drawable)
    assert any("capa ACTIVA" in w for w in res.warnings)
    assert res.coverage >= 0.99


def test_patron_doble_slash_en_capa_activa_abandona(tmp_path):
    """Regla del usuario (2026-09-25): el «//» a paso regular es abandonada en
    cualquier capa, aunque no sea «-A»; se avisa."""
    pdf = _abandoned_doc(tmp_path, [("C-ELEC-UNGD-E", (100, 300), (700, 300), 60.0, True)])
    res = rec.recognize_page(pdf, 0, zoom=1.0)
    assert res.drawable and all(p.abandoned for p in res.drawable)
    assert any("Patrón «//»" in w for w in res.warnings)
    assert res.coverage >= 0.99


def test_marker_pattern_puro_espaciado_irregular_no_es_patron():
    import recognition_geom as G
    pl = G.Polyline([(0.0, 0.0), (600.0, 0.0)], ["end", "end"])
    regular = [G.Glyph(x, 0.0, 7.5) for x in (30, 90, 150, 210, 270, 330, 390, 450, 510, 570)]
    mp = G.marker_pattern([pl], regular)
    assert mp.period and abs(mp.period - 60) < 1 and mp.verdict == [True]
    # «//»: dos glifos pegados cuentan como uno
    double = [g for x in (30, 90, 150, 210, 270, 330, 390, 450, 510, 570) for g in (G.Glyph(x - 1.6, 0.0, 7.5), G.Glyph(x + 1.6, 0.0, 7.5))]
    assert G.marker_pattern([pl], double).verdict == [True]
    # solo al principio: paso aprendido pero no cubre la línea
    assert G.marker_pattern([pl], regular[:3]).verdict == [False]
    # irregular: no hay paso
    assert G.marker_pattern([pl], [G.Glyph(x, 0.0, 7.5) for x in (30, 100, 250, 520)]).period is None


def test_doble_slash_es_abandonada_en_cualquier_capa():
    """Regla del usuario (2026-09-25): «//» = abandonada en cualquier utilidad y
    capa (no hace falta «-A»); la «/» simple no. Un «//» intercalado (ramal junto
    a una T, DU08 h.21) no tumba el veredicto de una línea larga."""
    import recognition_geom as G
    pl = G.Polyline([(0.0, 0.0), (600.0, 0.0)], ["end", "end"])
    xs = (30, 90, 150, 210, 270, 330, 390, 450, 510, 570)
    single = [G.Glyph(x, 0.0, 7.5) for x in xs]
    mp = G.marker_pattern([pl], single)
    assert mp.doubles == [False] and mp.double_verdict == [False] and not mp.has_double_pattern
    extra = [G.Glyph(x, 0.0, 7.5) for x in (*xs, 115)]
    double = [g for m in extra for g in (G.Glyph(m.cx - 1.6, 0.0, 7.5), G.Glyph(m.cx + 1.6, 0.0, 7.5))]
    stub = G.Polyline([(0.0, 50.0), (30.0, 50.0)], ["end", "end"])
    mp = G.marker_pattern([pl, stub], double)
    assert mp.verdict[0] is False                    # el juicio estricto falla por el intruso
    assert mp.doubles[0] and mp.double_verdict == [True, None] and mp.has_double_pattern


# ─────────────── codos: el arco es EXACTAMENTE el trazo curvo del PDF ───────────────
def _layer_ink(page, ocg_suffix, n=4):
    """(curvas, guiones) de la capa en pt. Curvas = trazos de ≥3 items «l» (arcos
    aplanados por el plot) o Béziers, muestreados; guiones = trazos de un solo
    «l» (la línea recta del linetype) como segmentos (a, b)."""
    curves, dashes, glyphs = [], [], []
    for d in page.get_drawings(extended=True):
        if d.get("type") not in ("s", "fs") or not str(d.get("layer") or "").endswith(ocg_suffix):
            continue
        items = d.get("items") or []
        if len(items) == 1 and items[0][0] == "l":
            dashes.append(((items[0][1].x, items[0][1].y), (items[0][2].x, items[0][2].y)))
            continue
        if len(items) < 3 and not any(it[0] == "c" for it in items):
            continue
        rc = d.get("rect")
        if rc is not None and max(rc.width, rc.height) <= 12.0:      # letra «e» del linetype, no curva
            glyphs.append(((rc.x0 + rc.x1) / 2, (rc.y0 + rc.y1) / 2))
            continue
        for it in items:
            if it[0] == "l":
                p0, p1 = it[1], it[2]
                curves += [(p0.x + (p1.x - p0.x) * k / n, p0.y + (p1.y - p0.y) * k / n) for k in range(n + 1)]
            elif it[0] == "c":
                p0, p1, p2, p3 = it[1], it[2], it[3], it[4]
                for k in range(3 * n + 1):
                    t = k / (3 * n); u = 1 - t
                    curves.append((u**3 * p0.x + 3*u*u*t * p1.x + 3*u*t*t * p2.x + t**3 * p3.x,
                                   u**3 * p0.y + 3*u*u*t * p1.y + 3*u*t*t * p2.y + t**3 * p3.y))
    _layer_ink.glyphs = glyphs           # letras «e» del linetype (centros): también son tinta sobre la línea
    return curves, dashes


def _on_dash_line(pt, direction, dashes, reach=30.0, ang_tol_deg=1.0, off_tol=0.5):
    """¿Hay un guión de la capa a ≤`reach` pt cuyo rumbo coincide con `direction`
    y cuya RECTA pasa a ≤`off_tol` pt de `pt`? (la tangente es la línea del plano)"""
    ux, uy = direction
    for a, b in dashes:
        dx, dy = b[0] - a[0], b[1] - a[1]; L = math.hypot(dx, dy)
        if L < 1e-6:
            continue
        dx, dy = dx / L, dy / L
        if abs(dx * ux + dy * uy) < math.cos(math.radians(ang_tol_deg)):
            continue
        if min(math.dist(pt, a), math.dist(pt, b)) > reach:
            continue
        if abs((pt[0] - a[0]) * dy - (pt[1] - a[1]) * dx) <= off_tol:
            return True
    return False


def _seg_d0(q, a, b):
    vx, vy = b[0] - a[0], b[1] - a[1]; L2 = vx * vx + vy * vy
    t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((q[0] - a[0]) * vx + (q[1] - a[1]) * vy) / L2))
    return math.hypot(q[0] - a[0] - vx * t, q[1] - a[1] - vy * t)


def _audit_fillets(page_index, n_expected, strict_tangents):
    """Auditoría «no inventar» de los codos de una hoja: donde el PDF tiene tinta
    curva, el arco reconocido (A→B sobre el círculo) la cubre en ≥70 % de su
    largo (el resto: letras «e» y huecos del linetype) y TODA la tinta curva del
    sector está sobre el círculo (desvío radial ≤1 pt); con `strict_tangents`
    (patas = guiones rectos) cada tangente A/B está sobre la RECTA de un guión
    de la capa (≤0.5 pt, mismo rumbo ±1°); y el arco que dibuja el editor /
    genera el plugin (esquina + radio en pies) es el mismo arco."""
    import fitz
    import model_ops
    Z = 2.0
    res = rec.recognize_page(PDF, page_index, zoom=Z)
    page = fitz.open(str(PDF))[page_index]
    curves, dashes = _layer_ink(page, "C-ELEC-UNGD-E")
    assert curves and dashes
    fil = [(pl, i, f) for pl in res.drawable for i, f in (pl.fillets or {}).items()]
    assert len(fil) == n_expected
    # Ningún codo puede apoyarse en guiones RECTOS: sobre el círculo, un guión de
    # cuerda L se aparta de su recta r − √(r²−(L/2)²); si el plano lo dibujó
    # recto, ahí hay un chaflán (el quiebre va en el hueco), no una curva.
    strokes = [st for st in rec.ink_strokes(
        [d for d in fitz.open(str(PDF))[page_index].get_drawings(extended=True)
         if str(d.get("layer") or "").endswith("C-ELEC-UNGD-E")], lambda q: q)]
    for pl, i, f in fil:
        ctr = (f["center"][0] / Z, f["center"][1] / Z); r = f["r_px"] / Z
        a0 = math.atan2(f["a"][1] / Z - ctr[1], f["a"][0] / Z - ctr[0])
        a1 = math.atan2(f["b"][1] / Z - ctr[1], f["b"][0] / Z - ctr[0])
        sweep = (a1 - a0 + 3 * math.pi) % (2 * math.pi) - math.pi
        lo_a, hi_a = sorted((a0, a0 + sweep))
        # tinta CURVA que sostiene el arco: se muestrea el arco y se mira si la
        # tinta más cercana viene de un guión curvado como pide el radio
        def _kind(st):
            L = math.dist(st[0], st[-1])
            exp = r - math.sqrt(max(0.0, r * r - (L / 2) ** 2))
            if L < 12.0 or exp < 0.5:
                return "neutral"
            sag = max((_seg_d0(q, st[0], st[-1]) for q in st[1:-1]), default=0.0)
            return "curved" if sag >= 0.5 * exp else "straight"
        curved_pts = [q for st in strokes if _kind(st) == "curved"
                      for a, b in zip(st, st[1:])
                      for k in range(9)
                      for q in ((a[0] + (b[0] - a[0]) * k / 8, a[1] + (b[1] - a[1]) * k / 8),)]
        hit = 0
        for k in range(37):
            ang = a0 + sweep * k / 36
            q = (ctr[0] + r * math.cos(ang), ctr[1] + r * math.sin(ang))
            if curved_pts and min(math.dist(q, c) for c in curved_pts) <= 1.0:
                hit += 1
        assert hit / 37 >= rec.FILLET_INK_COVER, (pl.pts_pdf[i], hit / 37)
    pipes = rec.pipes_from_recognition(res, layer="ELECTRICO", zoom=Z)
    by_pl = {id(pl): p for pl, p in zip(res.drawable, pipes)}
    for pl, i, f in fil:
        cx, cy = f["center"]; r = f["r_px"]
        a0 = math.atan2(f["a"][1] - cy, f["a"][0] - cx); a1 = math.atan2(f["b"][1] - cy, f["b"][0] - cx)
        sweep = (a1 - a0 + 3 * math.pi) % (2 * math.pi) - math.pi
        assert abs(math.degrees(sweep)) >= 8
        dev = []
        for k in range(41):
            ang = a0 + sweep * k / 40
            x, y = (cx + r * math.cos(ang)) / Z, (cy + r * math.sin(ang)) / Z     # px → pt (hoja sin /Rotate)
            d_curve = min(math.hypot(x - sx, y - sy) for sx, sy in curves)
            # el empalme con el guión recto (≤ FILLET_ARC_DEV_PT de la tinta) también es tinta
            d_dash = min((_seg_d0((x, y), a, b) for a, b in dashes), default=1e9)
            dash_lim = rec.FILLET_LOOSE_TOL_PT if f.get("loose") else rec.FILLET_ARC_DEV_PT
            d_glyph = min((math.hypot(x - gx, y - gy) for gx, gy in _layer_ink.glyphs), default=1e9)
            dev.append(min(d_curve, d_dash if d_dash <= dash_lim else 1e9, d_glyph if d_glyph <= 6.0 else 1e9))
        assert sum(1 for d in dev if d <= 3.0) >= (0.6 if f.get("loose") else 0.7) * len(dev), dev
        C_pt, r_pt = (cx / Z, cy / Z), r / Z
        lo, hi = sorted((a0, a0 + sweep))
        arc_pts = [((cx + r * math.cos(a0 + sweep * k / 40)) / Z, (cy + r * math.sin(a0 + sweep * k / 40)) / Z)
                   for k in range(41)]
        # tinta de OTRA ruta pegada (líneas paralelas a pocos pt) no cuenta:
        # cada punto de tinta se asigna a la polilínea más cercana
        others = [[(x / Z, y / Z) for x, y in q.pts_pdf] for q in res.drawable if q is not pl]
        def _seg_d(q, a, b):
            vx, vy = b[0] - a[0], b[1] - a[1]; L2 = vx * vx + vy * vy
            t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((q[0] - a[0]) * vx + (q[1] - a[1]) * vy) / L2))
            return math.hypot(q[0] - a[0] - vx * t, q[1] - a[1] - vy * t)
        radial = []
        for sx, sy in curves:
            ang = math.atan2(sy - C_pt[1], sx - C_pt[0])
            ang = ang if lo <= ang <= hi else (ang + 2 * math.pi if ang + 2 * math.pi <= hi else ang - 2 * math.pi)
            if not (lo <= ang <= hi) or abs(math.dist((sx, sy), C_pt) - r_pt) > 3.0:
                continue
            d_arc = min(math.dist((sx, sy), q) for q in arc_pts)
            d_other = min((_seg_d((sx, sy), a, b) for o in others for a, b in zip(o, o[1:])), default=1e9)
            if d_other < d_arc:
                continue
            radial.append(abs(math.dist((sx, sy), C_pt) - r_pt))
        # El criterio de producción es el RMS del círculo contra la tinta de ESA
        # línea (≤1 pt); aquí se comprueba además, con la tinta muestreada aparte,
        # que ningún punto del sector se aparte más de 2 pt del círculo.
        assert f["dev_px"] / Z <= (rec.FILLET_LOOSE_TOL_PT if f.get("loose") else 1.0), f["dev_px"] / Z
        lim = rec.FILLET_LOOSE_TOL_PT if f.get("loose") else 2.0
        n_min = 8 if f.get("loose") else 12
        assert len(radial) >= n_min and max(radial) <= lim, (len(radial), max(radial) if radial else None)
        P, N = pl.pts_pdf[i - 1], pl.pts_pdf[i + 1]
        A, B = (f["a"][0] / Z, f["a"][1] / Z), (f["b"][0] / Z, f["b"][1] / Z)
        C = pl.pts_pdf[i]     # (en un ramal tangente a un tee, B ES el tee: la recta es C→N)
        ta = (P[0] - C[0], P[1] - C[1]); la = math.hypot(*ta); ta = (ta[0] / la, ta[1] / la)
        tb = (N[0] - C[0], N[1] - C[1]); lb = math.hypot(*tb); tb = (tb[0] / lb, tb[1] / lb)
        if strict_tangents:
            # (un extremo que MUERE en un nodo del plano no tiene recta después:
            #  su tangente es la del propio arco, no la de un guión)
            if not f.get("node_a"):
                assert _on_dash_line(A, ta, dashes), (A, ta)
            if not f.get("node_b"):
                assert _on_dash_line(B, tb, dashes), (B, tb)
        p = by_pl[id(pl)]
        r_px = p["fillets"][i] / res.scale_ft_per_pt * Z
        # (max_frac=1: la tangencia siempre cabe en las rectas; el margen del 10 %
        # del plugin/editor solo recorta el radio en patas muy justas)
        geo = model_ops.fillet_geo(p["pts"][i - 1], p["pts"][i], p["pts"][i + 1], r_px, max_frac=1.0)
        assert geo and not geo["clamped"]
        assert math.dist(geo["t1"], f["a"]) < 0.05 and math.dist(geo["t2"], f["b"]) < 0.05
        assert math.dist(geo["center"], f["center"]) < 0.05


@pytest.mark.skipif(not PDF.is_file(), reason="PDF de prueba DU06 no está en el repo")
def test_hoja4_arcos_de_codo_caen_sobre_los_trazos_curvos_del_pdf():
    """Hoja 4: ocho codos entre guiones rectos (vertical/horizontal/diagonal), dos
    de ellos aproximados (la curva del plano es una polilínea «a mano», ≤3 pt):
    tangentes EXACTAS sobre los guiones. Antes: el empalme run↔curva torcía la
    tangente 4.75° y dejaba la esquina 3.7 pt fuera (lo vio el usuario)."""
    _audit_fillets(3, 8, strict_tangents=True)


@pytest.mark.skipif(not PDF.is_file(), reason="PDF de prueba DU06 no está en el repo")
def test_hoja3_arcos_de_curva_compuesta_sobre_la_tinta():
    """Hoja 3: curva larga compuesta (arcos encadenados con patas cortas): cada
    arco sigue sobre la tinta curva del PDF (radial ≤1 pt).

    7, no 6 (auditoría de reconocimiento de drenaje, 2026-09-23): la «e» del
    linetype a veces sale partida en dos paths (asta + bucle, igual que la
    «d» de "sd" en drenaje) y antes de que `classify_paths` reconociera esa
    asta como parte de la letra (ver `GLYPH_STROKE_MIN_REPEAT`), esos guiones
    sueltos rompían la topología cerca de (908,1123) y tapaban un codo real
    (arco sobre tinta curva verificada, r≈77 pt) — quedaba como esquina."""
    _audit_fillets(2, 7, strict_tangents=False)


@pytest.mark.skipif(not PDF.is_file(), reason="PDF de prueba DU06 no está en el repo")
def test_hoja3_codos_no_dependen_del_zoom_de_reconocimiento():
    """La densidad de muestreo de tinta se conserva en unidades del PDF.

    Antes, el codo cercano a (876, 1048) pt aparecía con zoom 1 y desaparecía
    con zoom 2 porque las muestras se separaban 1.5 píxeles en ambos casos.
    """
    def fillets_at(zoom):
        res = rec.recognize_page(PDF, 2, zoom=zoom)
        found = []
        for pl in res.drawable:
            for i, fillet in (pl.fillets or {}).items():
                corner = pl.pts_pdf[i]
                found.append((corner[0] / zoom, corner[1] / zoom,
                              fillet["r_px"] / zoom))
        return sorted(found)

    at_one = fillets_at(1.0)
    at_two = fillets_at(2.0)
    assert len(at_one) == len(at_two) == 7
    for expected, actual in zip(at_one, at_two):
        assert actual == pytest.approx(expected, abs=0.05)


@pytest.mark.skipif(not PDF.is_file(), reason="PDF de prueba DU06 no está en el repo")
def test_du06_ningun_tramo_sin_tinta_debajo():
    """Auditoría «no inventar» hoja por hoja: todo segmento de centerline de más
    de 6 pt que NO vaya por dentro de una bóveda tiene que tener tinta de la capa
    debajo (≥50 % de sus muestras a ≤2 pt). Lo reportó el usuario: en la hoja 3
    salía un abanico de líneas hacia el nodo de una bóveda grande y un extremo se
    prolongaba 29 pt sin tinta para alcanzarla."""
    import fitz
    import recognition_geom as geom
    Z = 2.0
    doc = fitz.open(str(PDF))
    try:
        for pno in range(doc.page_count):
            res = rec.recognize_page(PDF, pno, zoom=Z)
            if not res.drawable:
                continue
            page = doc[pno]
            lp, _vp, _c, _k = rec.gather_paths(page, rec.classify_ocg, set(), None)
            px = lambda q: (q[0] * Z, q[1] * Z)                       # noqa: E731
            by = {}
            for p_ in lp:
                by.setdefault(p_.get("layer") or "", []).append(p_)
            ink = []
            for v in by.values():
                ink += [(q[0], q[1]) for q in rec.ink_samples(rec.ink_strokes(v, px))]
            cell = 12.0
            grid = {}
            for q in ink:
                grid.setdefault((int(q[0] // cell), int(q[1] // cell)), []).append(q)

            def near(q, tol=2.0 * Z):
                cx, cy = int(q[0] // cell), int(q[1] // cell)
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        for i in grid.get((cx + dx, cy + dy), ()):
                            if math.dist(q, i) <= tol:
                                return True
                return False

            boxes = []
            for vg in (res.vaults_geo or []):
                if vg.get("corners"):
                    xs = [c[0] for c in vg["corners"]]; ys = [c[1] for c in vg["corners"]]
                    boxes.append((min(xs) - 3 * Z, min(ys) - 3 * Z, max(xs) + 3 * Z, max(ys) + 3 * Z))

            def in_vault(q):
                return any(b[0] <= q[0] <= b[2] and b[1] <= q[1] <= b[3] for b in boxes)

            for pl in res.drawable:
                for i, (a, b) in enumerate(zip(pl.pts_pdf, pl.pts_pdf[1:])):
                    if math.dist(a, b) / Z <= 6:
                        continue
                    if (pl.fillets or {}).get(i) or (pl.fillets or {}).get(i + 1):
                        continue                    # la cuerda de un codo: el arco sí va sobre la tinta
                    n = max(2, int(math.dist(a, b) / Z / 1.5))
                    pts = [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(n + 1)]
                    out = [q for q in pts if not in_vault(q)]
                    if len(out) < 0.5 * len(pts):
                        continue                    # el tramo va por dentro de la bóveda
                    hit = sum(1 for q in out if near(q))
                    assert hit / len(out) >= 0.5, (pno + 1, (a[0] / Z, a[1] / Z), (b[0] / Z, b[1] / Z), hit / len(out))
    finally:
        doc.close()


@pytest.mark.skipif(not PDF.is_file(), reason="PDF de prueba DU06 no está en el repo")
def test_du06_nodos_de_boveda_dentro_del_simbolo():
    """El nodo interior (la CAJA) tiene que caer DENTRO del recuadro de la bóveda:
    el usuario vio un triángulo de líneas apuntando a un vértice fuera de ella."""
    import fitz
    import recognition_geom as geom
    doc = fitz.open(str(PDF))
    try:
        for pno in range(doc.page_count):
            page = doc[pno]
            lp, vp, _c, _k = rec.gather_paths(page, rec.classify_ocg, set(), None)
            if not lp:
                continue
            by = {}
            for p_ in lp:
                by.setdefault(p_.get("layer") or "", []).append(p_)
            for paths in by.values():
                g = geom.reconstruct(paths, vp)
                for vi, v in enumerate(g.vaults):
                    for n in g.nodes:
                        if n.kind == "vault" and n.vault_idx == vi:
                            assert v.x0 - 1 <= n.x <= v.x1 + 1 and v.y0 - 1 <= n.y <= v.y1 + 1, (pno + 1, n.x, n.y)
    finally:
        doc.close()


def _near(pl, x, y, tol=3.0):
    return any(math.hypot(px - x, py - y) <= tol for px, py in pl.pts_pdf)


@pytest.mark.skipif(not PDF.is_file(), reason="PDF de prueba DU06 no está en el repo")
def test_drenaje_hoja4_lineas_como_estan_en_el_plano():
    """Casos del usuario en la hoja 4 (índice 3), drenaje:
    · el lateral «sd» de `C-STRM-UNGD-E-NPLT` (541,1157)→(588,894) se reconoce;
    · el tramo MH (1051,834) → caja de captación (1115,832) sale UNA vez (antes
      un guión a 1.03° armaba otra corrida y la línea quedaba doble);
    · la «sd» muere en el borde de SU caja (1014), no cruza hasta la vecina;
    · la línea «ps» llega a su caja grande (992.5) y no muere en la cajita de al
      lado (a 2.8 pt, antes fundidas en una sola bóveda);
    · la «ps», repetida trazo por trazo en dos xrefs, se reconoce una sola vez."""
    r = rec.recognize_page(PDF, page_index=3, utility="DRENAJE", zoom=1.0)
    lines = r.drawable
    nplt = [p for p in lines if p.layer_ocg.upper().endswith("C-STRM-UNGD-E-NPLT")]
    assert len(nplt) == 1 and _near(nplt[0], 541.4, 1157.2) and _near(nplt[0], 587.9, 893.0, 2.0)

    exist = [p for p in lines if p.layer_ocg.endswith("EXIST_SD|C-STRM-UNGD-E")]

    def covers(pl, x, y):      # algún tramo de la polilínea pasa por (x, y)
        pts = pl.pts_pdf
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            L = math.hypot(bx - ax, by - ay)
            if L < 1e-9:
                continue
            t = ((x - ax) * (bx - ax) + (y - ay) * (by - ay)) / L ** 2
            if 0 <= t <= 1 and abs((x - ax) * (by - ay) - (y - ay) * (bx - ax)) / L <= 1.5:
                return True
        return False

    assert sum(covers(p, 1090.0, 832.6) for p in exist) == 1
    sd = [p for p in exist if covers(p, 1025.0, 835.4)]
    assert len(sd) == 1
    assert min(x for x, _ in sd[0].pts_pdf) > 1012.0          # borde de su caja, no la vecina

    ps = [p for p in lines if "GLINE" in p.layer_ocg and covers(p, 1100.0, 826.1)]
    assert len(ps) == 1                                        # una sola vez (dos xrefs)
    assert abs(min(x for x, _ in ps[0].pts_pdf) - 993.5) <= 1.5
    assert any("repetidas" in w for w in r.warnings)


DU08 = Path(r"C:/Users/bernu/OneDrive/Documentos/docs prueba/03-DU08_09_10-APDU-SEG-B-SEWER-PLAN_100P.pdf")


@pytest.mark.skipif(not DU08.is_file(), reason="PDF DU08 (carpeta de pruebas) no disponible")
def test_du08_h39_curva_abandonada_completa_y_marcada():
    """Caso del usuario: la curva de `C-ELEC-UNGD-A` (con «/») sale entera —su
    punta ya no queda «fuera de patrón»— y marcada abandonada."""
    r = rec.recognize_page(DU08, page_index=38, utility="ELECTRICO", zoom=1.0)
    ab = [p for p in r.drawable if p.layer_ocg.endswith("C-ELEC-UNGD-A")]
    assert ab and all(p.abandoned for p in ab)
    assert any(_near(p, 897.0, 1287.0, 2.5) for p in ab)
    assert r.offpattern_px == []

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

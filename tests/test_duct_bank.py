"""Pruebas del modelo de Duct Bank (headless, sin Qt)."""
import duct_bank as db_mod
from duct_bank import DuctBank, Conduit, snap, validate, conduits_overlap, conduit_fits_envelope


def test_snap_quarter_inch():
    assert snap(0.10) == 0.0
    assert snap(0.13) == 0.25
    assert snap(0.24) == 0.25
    assert snap(0.375) == 0.5   # bankers-rounding: 0.375/0.25=1.5 → 2 → 0.5
    assert snap(1.30, step=0.5) == 1.5
    assert snap(3.14, step=0) == 3.14   # step<=0 = sin ajuste


def test_conduit_fits_envelope():
    d = DuctBank(width_in=12, height_in=8)
    inside = Conduit(cx=3, cy=3, diam=4)          # radio 2; 2..10 en x, 2..6 en y → OK
    edge = Conduit(cx=2, cy=2, diam=4)            # justo tocando la esquina TL
    outside = Conduit(cx=1, cy=3, diam=4)         # radio 2 pero cx=1 → sobresale por izquierda
    assert conduit_fits_envelope(d, inside)
    assert conduit_fits_envelope(d, edge)
    assert not conduit_fits_envelope(d, outside)


def test_conduits_overlap():
    a = Conduit(cx=3, cy=3, diam=4)   # radio 2
    b_far = Conduit(cx=8, cy=3, diam=4)   # centros a 5, radios suman 4 → no solapa
    b_touch = Conduit(cx=7, cy=3, diam=4)  # centros a 4 = suma de radios → borde
    b_over = Conduit(cx=5, cy=3, diam=4)   # centros a 2 < 4 → solapa
    assert not conduits_overlap(a, b_far)
    assert not conduits_overlap(a, b_touch)   # tocan pero no solapan
    assert conduits_overlap(a, b_over)


def test_roundtrip():
    d = DuctBank(name="24 kV Trunk", width_in=16, height_in=10,
                 conduits=[Conduit(cx=3, cy=3, diam=4, label="A1"),
                           Conduit(cx=8, cy=3, diam=4, label="A2")])
    d2 = DuctBank.from_dict(d.to_dict())
    assert d2.name == "24 kV Trunk"
    assert d2.width_in == 16 and d2.height_in == 10
    assert len(d2.conduits) == 2
    assert d2.conduits[0].label == "A1" and d2.conduits[1].diam == 4


def test_validate_ok():
    # Desactivamos las reglas nuevas (v1.1+: margen 3", separación 2", borde 3")
    # y márgenes para probar solo la geometría básica: dos conductos que caben
    # dentro de la envolvente y no se solapan.
    d = DuctBank(width_in=12, height_in=8,
                 margin_top=0, margin_right=0, margin_bottom=0, margin_left=0,
                 rules_enabled=False,
                 conduits=[Conduit(cx=3, cy=3, diam=4), Conduit(cx=9, cy=3, diam=4)])
    assert validate(d) == []


def test_validate_flags_outside_and_overlap():
    d = DuctBank(width_in=12, height_in=8,
                 conduits=[Conduit(cx=3, cy=3, diam=4),
                           Conduit(cx=4, cy=3, diam=4),        # solapa con la anterior
                           Conduit(cx=1, cy=3, diam=4),        # fuera por izquierda
                           Conduit(cx=6, cy=6, diam=-1)])      # diámetro inválido
    errs = validate(d)
    joined = " | ".join(errs)
    assert "solapan" in joined
    assert "envolvente" in joined
    assert "diámetro" in joined.lower() or "diametro" in joined.lower()


def test_inner_rect_and_defaults():
    # Sin márgenes → interior == envolvente. Los defaults v1.1+ son 3" por lado
    # (típico de un bancoducto de concreto); aquí los desactivamos para probar
    # el cálculo puro de inner_rect.
    d = DuctBank(width_in=16, height_in=10,
                 margin_top=0, margin_right=0, margin_bottom=0, margin_left=0)
    assert d.inner_rect() == (0.0, 0.0, 16.0, 10.0)
    assert not d.has_margin() and not d.has_rounded_corners()
    # Con márgenes: recorta cada lado; nunca negativo
    d.margin_top = 1; d.margin_bottom = 1; d.margin_left = 2; d.margin_right = 2
    assert d.inner_rect() == (2.0, 1.0, 12.0, 8.0)
    assert d.has_margin()
    # Margen exagerado → interior colapsa a 0, no negativo
    d.margin_left = 20
    x, y, w, h = d.inner_rect()
    assert w == 0.0


def test_roundtrip_preserves_margin_and_corners():
    d = DuctBank(width_in=16, height_in=10,
                 margin_top=0.5, margin_right=0.5, margin_bottom=0.75, margin_left=1.0,
                 corner_tl=0.25, corner_tr=0.25, corner_br=0.5, corner_bl=0.5)
    d2 = DuctBank.from_dict(d.to_dict())
    assert (d2.margin_top, d2.margin_right, d2.margin_bottom, d2.margin_left) == \
           (0.5, 0.5, 0.75, 1.0)
    assert (d2.corner_tl, d2.corner_tr, d2.corner_br, d2.corner_bl) == \
           (0.25, 0.25, 0.5, 0.5)
    assert d2.has_margin() and d2.has_rounded_corners()


def test_from_dict_defaults_for_old_projects():
    # Proyecto viejo sin campos nuevos: no debe romperse
    d = DuctBank.from_dict({"name": "old", "width_in": 12, "height_in": 8,
                            "conduits": [{"cx": 3, "cy": 3, "diam": 4}]})
    assert d.margin_top == 0 and d.corner_tl == 0
    assert d.pipe_idx == -1
    assert not d.has_margin() and not d.has_rounded_corners()
    assert len(d.conduits) == 1


def test_guide_defaults_and_cell_size():
    # Márgenes en 0 para verificar el cálculo puro (los defaults v1.1+ son 3").
    d = DuctBank(width_in=12, height_in=8,
                 margin_top=0, margin_right=0, margin_bottom=0, margin_left=0)
    # Sin guía y con defaults 1x1: la celda es todo el interior
    assert d.guide_show is False
    assert d.guide_rows == 1 and d.guide_cols == 1
    assert d.guide_cell_size() == (12.0, 8.0)
    # Con márgenes de 1" cada lado → interior 10×6; 2 col × 3 fil → 5×2
    d.margin_top = d.margin_bottom = d.margin_left = d.margin_right = 1
    d.guide_cols = 2; d.guide_rows = 3
    cw, ch = d.guide_cell_size()
    assert cw == 5.0 and ch == 2.0
    # Interior colapsado → celda 0
    d.margin_left = 20
    cw, ch = d.guide_cell_size()
    assert cw == 0.0


def test_guide_roundtrip():
    d = DuctBank(width_in=16, height_in=10,
                 guide_show=True, guide_rows=4, guide_cols=6)
    d2 = DuctBank.from_dict(d.to_dict())
    assert d2.guide_show is True and d2.guide_rows == 4 and d2.guide_cols == 6


def test_pipe_idx_roundtrip():
    d = DuctBank(width_in=12, height_in=8, pipe_idx=3)
    d2 = DuctBank.from_dict(d.to_dict())
    assert d2.pipe_idx == 3
    d3 = DuctBank(width_in=12, height_in=8)
    assert d3.pipe_idx == -1


def test_copy_is_independent():
    d = DuctBank(width_in=10, height_in=6, conduits=[Conduit(cx=2, cy=2, diam=2)])
    d2 = d.copy()
    d2.conduits[0].diam = 99
    assert d.conduits[0].diam == 2       # el original no cambia


# ── Reglas de diseño custom ─────────────────────────────────────────────────

def _dbk_two_conduits(sep_between_centers=6.0):
    """Envolvente 27×20 con 2 conductos alineados horizontalmente."""
    return DuctBank(width_in=27, height_in=20,
                    conduits=[Conduit(cx=5.0, cy=10.0, diam=4.0, label="A"),
                              Conduit(cx=5.0 + sep_between_centers,
                                      cy=10.0, diam=4.0, label="B")])


def test_rule_min_conduit_sep_flags_violation():
    # 2 conductos Ø4" con centros a 5" → hueco borde-borde = 5 - 4 = 1".
    d = _dbk_two_conduits(sep_between_centers=5.0)
    d.rules_enabled = True; d.rule_min_conduit_sep_in = 2.0
    errs = validate(d)
    # Debe reportar violación de separación
    assert any("separación" in e or "separaci" in e for e in errs)


def test_rule_min_conduit_sep_passes_when_ok():
    # Centros a 7" → hueco = 3". Regla pide 2" → pasa.
    d = _dbk_two_conduits(sep_between_centers=7.0)
    d.rules_enabled = True; d.rule_min_conduit_sep_in = 2.0
    errs = validate(d)
    assert not any("separaci" in e for e in errs)


def test_rule_min_edge_clearance_flags_violation():
    # Conducto Ø4" en cx=3 → borde izquierdo del conducto a 1" del borde envolvente.
    d = DuctBank(width_in=27, height_in=20,
                 conduits=[Conduit(cx=3.0, cy=10.0, diam=4.0)])
    d.rules_enabled = True; d.rule_min_edge_clearance_in = 3.0
    errs = validate(d)
    assert any("borde" in e for e in errs)


def test_rules_disabled_skips_custom_rules():
    # Mismo diseño que test_rule_min_conduit_sep_flags_violation
    d = _dbk_two_conduits(sep_between_centers=5.0)
    d.rules_enabled = False   # OFF → no aplica reglas custom
    d.rule_min_conduit_sep_in = 2.0
    errs = validate(d)
    assert not any("separación" in e or "separaci" in e for e in errs)


def test_rules_zero_value_means_no_rule():
    # rules_enabled=True pero valores en 0 → no aplica esos chequeos.
    d = _dbk_two_conduits(sep_between_centers=5.0)
    d.rules_enabled = True
    d.rule_min_conduit_sep_in = 0.0
    d.rule_min_edge_clearance_in = 0.0
    errs = validate(d)
    assert not any("separaci" in e for e in errs)
    assert not any("borde" in e for e in errs)


def test_rules_and_render_envelope_roundtrip():
    d = DuctBank(width_in=27, height_in=20,
                 rules_enabled=False,
                 rule_min_conduit_sep_in=2.5,
                 rule_min_edge_clearance_in=3.0,
                 render_envelope=False)
    d2 = DuctBank.from_dict(d.to_dict())
    assert d2.rules_enabled is False
    assert d2.rule_min_conduit_sep_in == 2.5
    assert d2.rule_min_edge_clearance_in == 3.0
    assert d2.render_envelope is False
    # Defaults en un DuctBank fresco (v1.1+): 2" separación conductos,
    # 3" resguardo al borde, márgenes 3" en los 4 lados — valores típicos
    # de un bancoducto de concreto. Proyectos viejos sin estos campos
    # mantienen 0 al deserializarse (via from_dict fallback).
    d3 = DuctBank(width_in=12, height_in=8)
    assert d3.rules_enabled is True
    assert d3.rule_min_conduit_sep_in == 2.0
    assert d3.rule_min_edge_clearance_in == 3.0
    assert d3.render_envelope is True
    assert d3.margin_top == 3.0 and d3.margin_right == 3.0
    assert d3.margin_bottom == 3.0 and d3.margin_left == 3.0

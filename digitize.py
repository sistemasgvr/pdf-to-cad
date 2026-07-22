"""
digitize.py — Router PDF -> DXF.

Detecta automáticamente si cada página es vectorizada o rasterizada y
despacha al pipeline correspondiente. Genera un único DXF con capas
nombradas (AGUA, ALCANTARILLADO, GAS, EJE_VIA, METRO_RW, TEXTO, ...).

Uso:
    python digitize.py entrada.pdf salida.dxf
    python digitize.py entrada.pdf salida.dxf --force-raster
    python digitize.py entrada.pdf salida.dxf --force-vector

Programático:
    from digitize import main
    warnings = main("plan.pdf", "plan.dxf")
"""
import sys
from collections import Counter

# Consola Windows: forzar UTF-8 para los caracteres de los reportes.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import fitz
import ezdxf

import config as C
from detect import classify_page


# ─────────────────────────────────────────────────────────────────────────────
# Validación QA
# ─────────────────────────────────────────────────────────────────────────────
# Capas de utilidad: al menos UNA debe tener geometría (un plano puede ser de
# una sola utilidad, p.ej. mapa de agua -> no exigir gas ni alcantarillado).
UTILITY_LAYERS = ["AGUA", "ALCANTARILLADO", "DRENAJE_PLUVIAL", "GAS",
                  "ELECTRICO", "ELECTRICO_AEREO", "TELECOM", "TELECOM_AEREO"]

# Capas que representan geometría/anotación del PLANO (no metadata). Si alguna de
# estas entidades cae dentro de una zona de exclusión = zona contaminada.
_PLAN_LAYERS_FOR_CONTAMINATION = set(UTILITY_LAYERS) | {
    "EJE_VIA", "METRO_RW", "TOPO", "ESTRUCTURAS", "PREDIOS",
    "LIMITE_MAPA", "ANOTACION", "TEXTO", C.FALLBACK_LAYER,
}

# Términos que NUNCA deben aparecer como TEXTO del plano (son leyenda de pothole
# o campos del membrete). Si aparecen -> capa contaminada.
_FORBIDDEN_TEXT_TERMS = [k.upper() for k in (
    getattr(C, "POTHOLE_LEGEND_KEYWORDS", []) +
    getattr(C, "TITLEBLOCK_FIELD_KEYWORDS", [])
)]


def _entity_point(e):
    """Punto representativo de una entidad (para test dentro de zona)."""
    t = e.dxftype()
    try:
        if t in ("TEXT", "MTEXT"):
            return (e.dxf.insert.x, e.dxf.insert.y)
        if t == "LINE":
            return ((e.dxf.start.x + e.dxf.end.x) / 2.0,
                    (e.dxf.start.y + e.dxf.end.y) / 2.0)
        if t == "LWPOLYLINE":
            pts = [(p[0], p[1]) for p in e.get_points()]
            if pts:
                return (sum(p[0] for p in pts) / len(pts),
                        sum(p[1] for p in pts) / len(pts))
        if t in ("CIRCLE", "ARC", "POINT"):
            return (e.dxf.center.x, e.dxf.center.y) if t != "POINT" else (e.dxf.location.x, e.dxf.location.y)
    except Exception:
        return None
    return None


def _entity_text(e):
    t = e.dxftype()
    try:
        if t == "TEXT":
            return (e.dxf.text or "")
        if t == "MTEXT":
            return (e.text or "")
    except Exception:
        return ""
    return ""


def _in_zone(pt, zones):
    x, y = pt
    for _tag, (x0, y0, x1, y1) in zones:
        if x0 <= x <= x1 and y0 <= y <= y1:
            return _tag
    return None


def validate(msp, zones=None):
    warnings = []
    zones = zones or []
    counts = Counter(e.dxf.layer for e in msp)
    total = sum(counts.values())

    if not any(counts.get(ln, 0) > 0 for ln in UTILITY_LAYERS):
        warnings.append("Ninguna capa de utilidad tiene geometría "
                        f"({'/'.join(UTILITY_LAYERS)}) — revisa LAYER_TOKENS")

    if total < 50:
        warnings.append(f"POCAS entidades: {total} (¿extracción incompleta?)")
    if total > 80000:
        warnings.append(f"MUCHAS entidades: {total} (¿duplicados / sin filtrar?)")

    fb = counts.get(C.FALLBACK_LAYER, 0)
    # Solo alerta si el fallback domina y no es una capa esperada de geometría real.
    if total and fb > total * 0.5:
        warnings.append(
            f"ALTO {C.FALLBACK_LAYER}: {fb}/{total} "
            f"({fb/total*100:.0f}%) — revisa LAYER_TOKENS en config.py"
        )

    # ── Regla de CAPA CONTAMINADA ────────────────────────────────────────────
    # (a) Geometría/anotación del plano DENTRO de una zona de exclusión
    #     (leyenda de pothole / membrete): debería ser CERO.
    if zones:
        by_tag = Counter()
        for e in msp:
            if e.dxf.layer not in _PLAN_LAYERS_FOR_CONTAMINATION:
                continue
            pt = _entity_point(e)
            if pt is None:
                continue
            tag = _in_zone(pt, zones)
            if tag:
                by_tag[tag] += 1
        for tag, n in by_tag.items():
            warnings.append(
                f"CONTAMINADA: {n} entidad(es) dentro de la zona de exclusión "
                f"'{tag}' (leyenda/membrete NO debe digitalizarse)")

    # (b) TEXTO con términos de leyenda de pothole o campos del membrete que se
    #     hayan colado en capas del plano (utilities/anotación).
    if _FORBIDDEN_TEXT_TERMS:
        leaked = Counter()
        for e in msp:
            if e.dxftype() not in ("TEXT", "MTEXT"):
                continue
            if e.dxf.layer not in _PLAN_LAYERS_FOR_CONTAMINATION:
                continue
            up = _entity_text(e).upper()
            if any(term in up for term in _FORBIDDEN_TEXT_TERMS):
                leaked[e.dxf.layer] += 1
        if leaked:
            det = ", ".join(f"{lyr}:{n}" for lyr, n in leaked.items())
            warnings.append(
                f"CONTAMINADA: texto de leyenda/membrete en capas del plano ({det}) "
                f"— revisa zonas de exclusión / LAYER_TOKENS")

    return warnings, counts


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main(pdf_path, dxf_out, force=None, verbose=True):
    """
    force: None (auto) | 'vector' | 'raster'
    Devuelve lista de warnings de QA.
    """
    import vector_pipeline

    doc = fitz.open(pdf_path)
    dxf_doc = ezdxf.new("R2010", setup=True)
    C.apply_imperial_header(dxf_doc)   # $INSUNITS=pies + $MEASUREMENT=0 (imperial)
    msp = dxf_doc.modelspace()

    def log(*a):
        if verbose:
            print(*a)

    log(f"PDF: {pdf_path}  ({len(doc)} pág.)")

    all_callouts = []
    all_zones = []
    last_scale = C.DEFAULT_SCALE_FT_PER_PT
    for i, page in enumerate(doc):
        kind, info = classify_page(page)
        if force in ("vector", "raster"):
            kind = force
        log(f"\n── Página {i}: {kind.upper()} ──")
        log(f"   rot={info['rotation']}  mediabox={info['mediabox']}  "
            f"paths={info['n_paths']}  imgs={info['n_images']}  "
            f"img_cover={info['max_image_cover']}")

        if kind == "vector":
            stats = vector_pipeline.run(page, dxf_doc)
        else:
            import raster_pipeline
            stats = raster_pipeline.run(page, dxf_doc)
        page_callouts = stats.pop("callouts", None) or []
        all_callouts.extend(page_callouts)
        all_zones.extend(stats.pop("exclusion_zones_cad", None) or [])
        last_scale = stats.get("scale_ft_per_pt", last_scale)
        log("   ", stats)

    dxf_doc.saveas(dxf_out)
    log(f"\n✓ Guardado: {dxf_out}")

    # Reporte de nomenclatura de callouts (si se leyó texto por OCR).
    if all_callouts:
        import os
        import callout_ocr
        report_path = os.path.splitext(dxf_out)[0] + "_callouts.txt"
        n_tot, n_nom = callout_ocr.write_report(
            all_callouts, report_path, os.path.basename(pdf_path), last_scale)
        log(f"✓ Reporte de callouts: {report_path}  "
            f"({n_nom}/{n_tot} con nomenclatura)")

    warnings, counts = validate(msp, all_zones)
    log("\n── Entidades por capa ──")
    for layer in sorted(counts):
        log(f"   {layer:18s} {counts[layer]}")
    log(f"   {'TOTAL':18s} {sum(counts.values())}")

    log("\n── Validación QA ──")
    if warnings:
        for w in warnings:
            log(f"   ⚠ {w}")
    else:
        log("   ✓ Todas las verificaciones pasaron")

    doc.close()
    return warnings


def _cli():
    import os
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    if not args:
        print(__doc__)
        sys.exit(1)
    pdf_path = args[0]
    if len(args) > 1:
        dxf_out = args[1]
    else:
        # Sin ruta de salida: usa carpeta output/ con el nombre del PDF.
        base = os.path.splitext(os.path.basename(pdf_path))[0]
        dxf_out = os.path.join(C.OUTPUT_DIR, base + ".dxf")
    # Si la ruta no tiene carpeta, la mete en output/.
    if not os.path.dirname(dxf_out):
        dxf_out = os.path.join(C.OUTPUT_DIR, dxf_out)
    os.makedirs(os.path.dirname(dxf_out), exist_ok=True)
    force = "raster" if "--force-raster" in flags else "vector" if "--force-vector" in flags else None
    main(pdf_path, dxf_out, force=force)


if __name__ == "__main__":
    _cli()

"""
detect.py — Detección automática vectorizado vs rasterizado.

Heurística: un PDF de plano CAD ploteado tiene cientos/miles de trazos
(`get_drawings`) Y además texto real (objetos de texto / fuentes) o capas OCG.
Un escaneo tiene 0-pocos trazos y una imagen grande que cubre casi toda la
página… o, si pasó por un vectorizador (raster → vector), miles de trazos
«calcados» pero NINGÚN texto, fuente ni capa: ese caso se trata como raster
(se rasteriza la página y sigue el flujo manual), nunca como ploteado.
"""
import fitz


def classify_page(page, min_vector_paths=80, image_cover_frac=0.6, min_text_chars=20):
    """
    Devuelve ('vector'|'raster', info_dict) para una página.

    - 'vector' si hay >= min_vector_paths trazos de dibujo Y evidencia de
      plot CAD: texto (>= min_text_chars caracteres o alguna fuente) o capas OCG.
    - 'raster' si una imagen cubre >= image_cover_frac de la página sin capas
      (escaneo, aunque lleve anotaciones vectoriales encima), si hay pocos
      trazos, o si los trazos son un escaneo vectorizado (sin texto/fuentes/
      capas: `info["traced"] = True`).
    """
    drawings = page.get_drawings()
    n_paths = len(drawings)
    images = page.get_images(full=True)

    page_area = abs(page.rect.width * page.rect.height) or 1.0
    max_img_cover = 0.0
    for img in images:
        for r in page.get_image_rects(img[0]):
            max_img_cover = max(max_img_cover, abs(r.width * r.height) / page_area)

    text_chars = len(page.get_text().strip())
    try:
        n_fonts = len(page.get_fonts())
    except Exception:
        n_fonts = 0
    try:
        doc = page.parent
        n_ocgs = len(doc.get_ocgs()) if doc is not None else 0
    except Exception:
        n_ocgs = 0

    info = {
        "n_paths": n_paths,
        "n_images": len(images),
        "max_image_cover": round(max_img_cover, 3),
        "rotation": page.rotation,
        "mediabox": (round(page.mediabox.width), round(page.mediabox.height)),
        "text_chars": text_chars,
        "n_fonts": n_fonts,
        "n_ocgs": n_ocgs,
        "traced": False,
    }

    cad_evidence = text_chars >= min_text_chars or n_fonts > 0 or n_ocgs > 0
    if max_img_cover >= image_cover_frac and n_ocgs == 0:
        kind = "raster"                      # escaneo (con o sin anotaciones encima)
    elif n_paths >= min_vector_paths and cad_evidence:
        kind = "vector"
    elif n_paths >= min_vector_paths:
        kind = "raster"                      # escaneo vectorizado: trazos calcados, sin texto ni capas
        info["traced"] = True
    elif max_img_cover >= image_cover_frac:
        kind = "raster"
    else:
        # Sin geometría vectorial significativa ni imagen dominante:
        # tratamos como raster (rasterizamos la página completa) por seguridad.
        kind = "raster"

    info["kind"] = kind
    return kind, info


def classify_pdf(pdf_path, **kwargs):
    """Clasifica cada página del PDF. Devuelve lista de (page_index, kind, info)."""
    doc = fitz.open(pdf_path)
    out = []
    for i, page in enumerate(doc):
        kind, info = classify_page(page, **kwargs)
        out.append((i, kind, info))
    doc.close()
    return out


if __name__ == "__main__":
    import sys
    for i, kind, info in classify_pdf(sys.argv[1]):
        print(f"Página {i}: {kind.upper()}  {info}")

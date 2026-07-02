"""
detect.py — Detección automática vectorizado vs rasterizado.

Heurística: un PDF de plano CAD vectorizado tiene cientos/miles de
trazos (`get_drawings`). Un escaneo tiene 0-pocos trazos y una imagen
grande que cubre casi toda la página.
"""
import fitz


def classify_page(page, min_vector_paths=80, image_cover_frac=0.6):
    """
    Devuelve ('vector'|'raster', info_dict) para una página.

    - 'vector' si hay >= min_vector_paths trazos de dibujo.
    - 'raster' si hay pocos trazos pero una imagen cubre >= image_cover_frac
      del área de la página.
    """
    drawings = page.get_drawings()
    n_paths = len(drawings)
    images = page.get_images(full=True)

    page_area = abs(page.rect.width * page.rect.height) or 1.0
    max_img_cover = 0.0
    for img in images:
        for r in page.get_image_rects(img[0]):
            max_img_cover = max(max_img_cover, abs(r.width * r.height) / page_area)

    info = {
        "n_paths": n_paths,
        "n_images": len(images),
        "max_image_cover": round(max_img_cover, 3),
        "rotation": page.rotation,
        "mediabox": (round(page.mediabox.width), round(page.mediabox.height)),
        "text_chars": len(page.get_text().strip()),
    }

    if n_paths >= min_vector_paths:
        kind = "vector"
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

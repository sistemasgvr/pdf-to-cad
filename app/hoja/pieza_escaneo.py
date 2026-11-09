"""pieza_escaneo.py — ¿esta hoja del PDF es un escaneo (imagen)? PURO (solo fitz).

Compositor ÚNICO (pedido del usuario 2026-11-09: «componer entre vectorial y escaneo»): en la misma hoja
compuesta pueden ir piezas vectoriales (se reconocen) y piezas escaneadas (se alinean con regla, transportador
y enderezar, y se dibujan a mano). El modo deja de ser de toda la hoja y pasa a ser de cada pieza.

Criterio de `detect.classify_page`, del lado prudente: escaneo = imagen que domina la hoja sin capas, o escaneo
vectorizado (muchos trazos sin texto, fuentes ni capas: `traced`). Primero lo barato (capas, imágenes, texto y
fuentes, unos milisegundos); los vectores (`get_drawings`, segundos en un mapa SIG) solo se leen en una hoja sin
ningún texto. Cualquier hoja con texto o capas es vectorial: no pierde el reconocimiento.
"""
from __future__ import annotations

IMAGEN_DOMINA = 0.6          # = detect.classify_page(image_cover_frac)
TEXTO_MIN = 20               # = detect.classify_page(min_text_chars)
PIXELES_ESCANEO = 250_000    # una imagen con menos píxeles no es un escaneo de la hoja (≈ 500 × 500)


def _usa_capas(page) -> bool:
    try:
        from hoja import pdf_layers as PL
        return bool(PL.page_uses_layers(page.parent, page.number))
    except Exception:                                   # noqa: BLE001 — ante la duda, vectorial
        return True


def cobertura_imagen(page) -> float:
    """Fracción de la hoja que tapa su imagen más grande."""
    area = abs(page.rect.width * page.rect.height) or 1.0
    mayor = 0.0
    try:
        # solo si hay alguna imagen con píxeles de escaneo (un icono no es un escaneo): ubicar las imágenes
        # relee el contenido de la hoja (una hoja compuesta grande con iconos, 3 s). Una pasada para todas
        # (`get_image_rects` por imagen: 1.5 s con las 498 de un mapa SIG)
        if not any(img[2] * img[3] >= PIXELES_ESCANEO for img in page.get_images(full=True)):
            return 0.0
        for info in page.get_image_info():
            if info.get("width", 0) * info.get("height", 0) < PIXELES_ESCANEO:
                continue
            x0, y0, x1, y1 = info["bbox"]
            mayor = max(mayor, abs((x1 - x0) * (y1 - y0)) / area)
    except Exception:                                   # noqa: BLE001
        return 0.0
    return mayor


def es_escaneo(page) -> bool:
    """True si la hoja es un escaneo / PDF imagen (se compone y se dibuja a mano)."""
    if _usa_capas(page):
        return False
    if cobertura_imagen(page) >= IMAGEN_DOMINA:
        return True
    try:
        if page.get_fonts():                            # rápido; el texto de una hoja grande tarda segundos
            return False
        if len(page.get_text().strip()) >= TEXTO_MIN:
            return False
    except Exception:                                   # noqa: BLE001
        return False
    # sin ninguna evidencia CAD: escaneo solo si es un escaneo VECTORIZADO (muchos trazos calcados). Una hoja con
    # pocos trazos sin texto sigue siendo vectorial: así ninguna hoja de plano deja de reconocerse.
    try:
        import detect
        return bool(detect.classify_page(page)[1].get("traced"))
    except Exception:                                   # noqa: BLE001
        return False

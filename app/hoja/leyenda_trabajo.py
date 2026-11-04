"""Lectura de la leyenda en un proceso aislado, sin compartir MuPDF con la UI."""


def leer(sources, progreso=None, detener=None):
    import fitz
    from hoja import pdf_legend
    out = []
    stop = detener or (lambda: False)
    for src in sources:
        if stop():
            break
        with (fitz.open(stream=src["data"], filetype="pdf") if src.get("data")
              else fitz.open(src["path"])) as doc:
            rows = pdf_legend.document_legend(doc, stop)
            images = {}
            for page in sorted({r.page for r in rows}):
                mine = [r.sample for r in rows if r.page == page]
                region = (min(s[0] for s in mine) - 2, min(s[1] for s in mine) - 2,
                          max(s[2] for s in mine) + 2, max(s[3] for s in mine) + 2)
                pix = doc[page].get_pixmap(matrix=fitz.Matrix(3, 3), clip=fitz.Rect(*region), alpha=False)
                images[page] = (pix.tobytes("png"), region)
            out.append({"name": src.get("name", ""), "rows": rows, "images": images})
    return out

"""Auditoría de los ejes de una red que viene como IMAGEN (`hoja/imagen_ejes`) en los mapas «QS SD» de
Phoenix: cuánto de la tinta de color cubren los ejes, si algún eje pasa por donde no hay tinta, y qué da
`recognize_page` con DRENAJE ← la capa de línea.

    python scripts/audit_ejes_imagen.py [south|north] [--hojas 1,4,8] [--compuesta 4,5]

Por hoja (número 1-based) imprime: colores (capas) y nº de trazos y símbolos; de los EJES extraídos y de las
líneas RECONOCIDAS: cobertura de la tinta (píxeles de la máscara del color, sin los símbolos, a ≤ w/2+1 px de
un eje) y tramos sin tinta (un trozo del eje de más de `SIN_TINTA_PX` píxeles seguidos sin tinta a ≤ w/2+1 px);
líneas, cobertura de guiones del núcleo y diámetros leídos; y los tiempos.

Medido (2026-11-18, South, ronda de corrección 1 de la Tarea 5: el canal fino del mismo azul en su propia capa
«fino», `imagen_grosores`; 4.17 px/pt, w ≈ 3.3 pt; la cobertura es de la tinta del color SIN la de la capa fina):

    hoja  ejes  sím.(capas)  cob. ejes  sin tinta  líneas  cob. rec.  sin tinta  diám.  capa      t ejes + t rec.
    S 1    335   112 (5)      0.974       34        267     0.980        0       52    continua  26.6 + 4.5 s
    S 3    301   161 (7)      0.981       16        249     0.984        0       48    continua  37.2 + 4.8 s
    S 4    187   185 (12)     0.968        0        146     0.968        0       73    continua  35.7 + 3.7 s
    S 5    185   116 (8)      0.978        6         67     0.924        0       33    núcleo    17.2 + 2.8 s
    S 7    248   224 (14)     0.981        1        188     0.980        0      114    continua  51.5 + 4.5 s
    S 8    221   144 (7)      0.977        2        153     0.977        0       60    continua  48.9 + 4.1 s

(antes de la ronda, con bandas y canal fino en UNA capa, h.4/h.7/h.8 iban al núcleo: cobertura 0.918/0.904/0.949,
12/8/4 tramos sin tinta, 59/89/44 diámetros). h.1 y h.3 no cambian: sus trazos finos son trocitos sueltos (contornos de
símbolos y uniones, 0.10 de su largo en líneas), no un canal. h.5 sigue en el núcleo por sus bandas «en caja» en trozos
(32 % de las puntas enfrentadas a un hueco; umbral del reconocimiento 25 %).

«sin tinta» de los EJES = trozos de > 2 px (0.5 pt) sin tinta (no revisados uno por uno; lo esperable: el centro de una
banda que pasa por una cajita blanca, la punta alargada medio grosor).

La máscara es la de la extracción (`imagen_paleta.mascara`: el color ± absorbidos), pintada por teselas
igual que `imagen_ejes`; la distancia a la tinta se mide con `cv2.distanceTransform` en cada tesela.
"""
from __future__ import annotations

import argparse
import collections
import math
import os
import sys
import time

_R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(_R, "app"), _R):
    if _p not in sys.path:
        sys.path.insert(0, _p)
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("PDFCAD_PROCESO", "0")

import cv2  # noqa: E402
import fitz  # noqa: E402
import numpy as np  # noqa: E402

from hoja import imagen_ejes as IE  # noqa: E402
from hoja import imagen_paleta as IP  # noqa: E402
from hoja import imagen_solo as IS  # noqa: E402

CARPETA = r"C:/Users/bernu/OneDrive/Documentos/DOCS DE PRUEBA IND"
PDFS = {"south": os.path.join(CARPETA, "QS SD_Indian School_South.pdf"),
        "north": os.path.join(CARPETA, "QS SD_Indian School_North.pdf")}
SIN_TINTA_PX = 2          # más de esto seguido sin tinta = tramo sin tinta (de un EJE: va todo sobre su tinta)
HUECO_GUION_PT = 8.0      # una línea RECONOCIDA cruza los huecos de un tipo de línea a guiones: solo cuenta más
                          # que esto (`audit_sin_tinta.MIN_GAP_PT`)
MARGEN_PX = 1.0           # tinta «del eje»: a ≤ w/2 + esto


def capa_red(cs) -> str | None:
    """La capa de LÍNEA de imagen de color (no acromática) con más TINTA (largo × grosor; con más trazos ganaba un
    rayado fino partido en cientos de trocitos)."""
    c = collections.Counter()
    for p in cs:
        if IE.tipo_imagen(p["layer"]) == "line" and p["items"]:
            c[p["layer"]] += p["width"] * sum(math.dist(it[1], it[2]) for it in p["items"])
    cand = [k for k in c if not IE._acromatico([v / 255.0 for v in IE.rgb_de(k)])]
    return max(cand, key=lambda k: (c[k], k)) if cand else None


class Tinta:
    """Tinta del color `rgb` de la hoja por teselas, como la ve la extracción: NÚCLEO (`mascara`: el color ±
    absorbidos; para la cobertura) y núcleo + FAMILIA (los tonos de su antialias: el contorno de 1 px de la
    banda; para «sin tinta»). Sin los recuadros de los símbolos de ese color, ni (para la cobertura) la tinta de
    `otras` = [(pts, grosor)] las OTRAS capas de línea del mismo color (la «fina» de `imagen_grosores`: no es de la
    red; a ≤ grosor/2 + `MARGEN_PX` de su eje)."""

    def __init__(self, page, rgb, simbolos=(), otras=()):
        imgs = IS.imagenes_utiles(page)
        self.escala = IS.px_por_pt(imgs)
        tes = list(IS.teselas(page, self.escala, IE.LADO_PX, IE.SOLAPE_PX))
        pal = IP.paleta([img for _r, img in tes], IP.indexada(page))
        color = next(c for c in pal if tuple(c.rgb) == tuple(rgb))
        otros = [o for o in pal if o is not color]
        self.teselas = []
        for r, img in tes:
            with IP.misma_imagen(img):
                m = IP.mascara(img, color).astype(np.uint8)
                f = (IP.familia(img, color, otros) | (m > 0)).astype(np.uint8)
            for s in simbolos:                   # los símbolos del color no son tinta de línea
                x0, y0 = int(math.floor((s.x0 - r.x0) * self.escala)), int(math.floor((s.y0 - r.y0) * self.escala))
                x1, y1 = int(math.ceil((s.x1 - r.x0) * self.escala)), int(math.ceil((s.y1 - r.y0) * self.escala))
                if x1 > 0 and y1 > 0 and x0 < m.shape[1] and y0 < m.shape[0]:
                    m[max(0, y0):y1, max(0, x0):x1] = 0
            if otras:
                fuera = np.zeros_like(m)
                for pl, ancho in otras:
                    q = np.array([((x - r.x0) * self.escala - 0.5, (y - r.y0) * self.escala - 0.5) for x, y in pl])
                    cv2.polylines(fuera, [np.round(q * 16).astype(np.int32).reshape(-1, 1, 2)], False, 1,
                                  max(1, int(round(ancho * self.escala + 2 * MARGEN_PX))), cv2.LINE_8, 4)
                m[fuera > 0] = 0
            self.teselas.append((r, m, f))
        u = fitz.Rect(tes[0][0])
        for r, _img in tes[1:]:
            u |= r
        self.union = u
        IS.soltar(page.parent)

    def _px(self, r, pts):
        return np.array([((x - r.x0) * self.escala - 0.5, (y - r.y0) * self.escala - 0.5) for x, y in pts])

    def medir(self, lineas, anchos, cajas=()):
        """(cobertura, tramos sin tinta [((x, y) pt, largo pt)], píxeles de tinta) de las polilíneas `lineas` (pt) con su
        grosor `anchos` (pt): tinta «del eje» = a ≤ grosor/2 + `MARGEN_PX`. Lo que cae en `cajas` (las bóvedas: el
        símbolo del buzón no es tinta de línea) no cuenta como «sin tinta»."""
        tinta = cubierta = 0
        sin = []
        s = IE.SOLAPE_PX // 2
        for r, m, f in self.teselas:
            h, w = m.shape
            # el núcleo de la tesela (como `imagen_ejes`): el solape no se cuenta dos veces
            nx0 = 0 if r.x0 <= self.union.x0 + 1e-9 else s
            ny0 = 0 if r.y0 <= self.union.y0 + 1e-9 else s
            nx1 = w if r.x1 >= self.union.x1 - 1e-9 else w - s
            ny1 = h if r.y1 >= self.union.y1 - 1e-9 else h - s
            cerca = np.zeros((h, w), np.uint8)
            d_tinta = cv2.distanceTransform((f == 0).astype(np.uint8), cv2.DIST_L2, 5)
            for pl, ancho in zip(lineas, anchos):
                xs = [p[0] for p in pl]
                ys = [p[1] for p in pl]
                if max(xs) < r.x0 - 5 or min(xs) > r.x1 + 5 or max(ys) < r.y0 - 5 or min(ys) > r.y1 + 5:
                    continue
                rad = ancho * self.escala / 2.0 + MARGEN_PX
                q = self._px(r, pl)
                cv2.polylines(cerca, [np.round(q * 16).astype(np.int32).reshape(-1, 1, 2)], False, 1,
                              max(1, int(round(2 * rad))), cv2.LINE_8, 4)
                corrida, ini = 0, None
                muestras = []
                for a, b in zip(q, q[1:]):
                    n = max(1, int(math.ceil(np.hypot(*(b - a)))))
                    muestras += [a + (b - a) * k / n for k in range(n)]
                muestras.append(q[-1])
                for x, y in muestras + [(-1e9, -1e9)]:          # (centinela: cierra la última corrida)
                    ix, iy = int(round(x)), int(round(y))
                    px_, py_ = r.x0 + (x + 0.5) / self.escala, r.y0 + (y + 0.5) / self.escala
                    if (nx0 <= ix < nx1 and ny0 <= iy < ny1 and d_tinta[iy, ix] > rad
                            and not any(c.contains(fitz.Point(px_, py_)) for c in cajas)):
                        corrida += 1
                        ini = ini or (px_, py_)
                        continue
                    if corrida > SIN_TINTA_PX:
                        sin.append((ini, corrida / self.escala))
                    corrida, ini = 0, None
            zona = m[ny0:ny1, nx0:nx1] > 0
            tinta += int(zona.sum())
            cubierta += int((zona & (cerca[ny0:ny1, nx0:nx1] > 0)).sum())
        return (cubierta / tinta if tinta else 1.0), sin, tinta


def ancho_tipico(anchos, lineas) -> float:
    """Grosor (pt) medio por LARGO: el de la tubería, no el de las letras."""
    pares = sorted((a, sum(math.dist(p, q) for p, q in zip(pl, pl[1:]))) for a, pl in zip(anchos, lineas))
    total = sum(l for _a, l in pares)
    acum = 0.0
    for a, l in pares:
        acum += l
        if acum >= total / 2:
            return a
    return pares[-1][0] if pares else 0.0


def ancho_de(pl, ejes, anchos, defecto) -> float:
    """Grosor de una línea reconocida: el mayor de los ejes cuyo punto medio cae sobre ella (≤ 1 pt)."""
    from reconocimiento import recognition_ink_lines as ink
    mejor = 0.0
    caja = fitz.Rect(min(p[0] for p in pl) - 2, min(p[1] for p in pl) - 2, max(p[0] for p in pl) + 2,
                     max(p[1] for p in pl) + 2)
    for e, a in zip(ejes, anchos):
        m = e[len(e) // 2] if len(e) > 2 else ((e[0][0] + e[-1][0]) / 2, (e[0][1] + e[-1][1]) / 2)
        if a > mejor and caja.contains(fitz.Point(m)) and min(ink._seg_dist(m, p, q)[1] for p, q in zip(pl, pl[1:])) <= 1.0:
            mejor = a
    return mejor or defecto


def dibujado(pl, paso=0.5):
    """Lo que el editor DIBUJA de una línea reconocida (vista): rectas entre tangencias y el ARCO de cada codo
    (el vértice «fillet» es la esquina virtual; medir la esquina daba «sin tinta» falsos en las curvas)."""
    pts, fl = pl.pts_pdf, pl.fillets or {}
    out = []
    for k in range(len(pts) - 1):
        s = tuple(fl[k]["b"]) if k in fl else tuple(pts[k])
        e = tuple(fl[k + 1]["a"]) if k + 1 in fl else tuple(pts[k + 1])
        out.append([s, e])
    for f in fl.values():
        c, r = f.get("center"), f.get("r_px")
        if not c or not r:
            out.append([tuple(f["a"]), tuple(f["b"])])
            continue
        a0 = math.atan2(f["a"][1] - c[1], f["a"][0] - c[0])
        a1 = math.atan2(f["b"][1] - c[1], f["b"][0] - c[0])
        sw = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
        n = max(2, int(abs(sw) * r / paso))
        out.append([(c[0] + r * math.cos(a0 + sw * i / n), c[1] + r * math.sin(a0 + sw * i / n)) for i in range(n + 1)])
    return out


def cajas_bovedas(r, der) -> list:
    """Recuadros (coords de `get_drawings`) de las bóvedas reconocidas, +1 pt."""
    out = []
    for vg in (r.vaults_geo or []):
        if vg.get("corners"):
            q = [fitz.Point(c) * der for c in vg["corners"]]
        elif vg.get("circle"):
            cx, cy, rr = vg["circle"]
            q = [fitz.Point(cx - rr, cy - rr) * der, fitz.Point(cx + rr, cy + rr) * der]
        else:
            continue
        out.append(fitz.Rect(min(p.x for p in q) - 1, min(p.y for p in q) - 1,
                             max(p.x for p in q) + 1, max(p.y for p in q) + 1))
    return out


def otras_lineas(cs, capa):
    """[(pts, grosor)] de las OTRAS capas de línea de imagen del mismo color que `capa` (la «fina»)."""
    rgb = IE.rgb_de(capa)
    return [(pl, p["width"]) for p in cs if IE.tipo_imagen(p["layer"]) == "line" and p["layer"] != capa
            and IE.rgb_de(p["layer"]) == rgb and p["items"]
            for pl in [[(p["items"][0][1].x, p["items"][0][1].y)] + [(it[2].x, it[2].y) for it in p["items"]]]]


def lineas_de(cs, capa):
    """Polilíneas (pt) de los trazos de `capa`."""
    return [[(p["items"][0][1].x, p["items"][0][1].y)] + [(it[2].x, it[2].y) for it in p["items"]]
            for p in cs if p["layer"] == capa and p["items"]]


def reconocer(doc, i, capa, utilidad="DRENAJE"):
    from reconocimiento import recognition as rec
    return rec.recognize_page(doc.name, page_index=i, utility=utilidad, doc=doc,
                              layer_roles={rec.ROLE_LINEAS: [capa], rec.ROLE_BUZONES: []}, zoom=1.0)


def auditar(doc, i, salida=print):
    page = doc[i]
    t0 = time.time()
    cs = IE.capas(page)
    t_ejes = time.time() - t0
    cnt = collections.Counter(p["layer"] for p in cs)
    capa = capa_red(cs)
    fila = {"hoja": i + 1, "t_ejes": t_ejes, "capas": len(cnt),
            "sim_capas": sum(1 for k in cnt if IE.tipo_imagen(k) == "sym")}
    if capa is None:
        salida(f"h.{i + 1}: sin capa de línea de color ({len(cnt)} capas, {t_ejes:.1f} s)")
        return fila
    rgb = IE.rgb_de(capa)
    simbolos = [fitz.Rect(p["rect"]) for p in cs if IE.tipo_imagen(p["layer"]) == "sym" and IE.rgb_de(p["layer"]) == rgb]
    ejes = lineas_de(cs, capa)
    anchos = [p["width"] for p in cs if p["layer"] == capa and p["items"]]
    w = ancho_tipico(anchos, ejes)
    tinta = Tinta(page, rgb, simbolos, otras_lineas(cs, capa))
    cob_e, sin_e, _n = tinta.medir(ejes, anchos)
    t1 = time.time()
    r = reconocer(doc, i, capa)
    t_rec = time.time() - t1
    der = page.derotation_matrix                 # pts_pdf van en la vista (hoja girada): a las de get_drawings
    pls = [[tuple(fitz.Point(p) * der) for p in trozo] for pl in r.drawable for trozo in dibujado(pl)]
    cob_r, sin_r, _n = tinta.medir(pls, [ancho_de(pl, ejes, anchos, w) for pl in pls], cajas_bovedas(r, der))
    fila.update(capa=IE.etiqueta(capa), ejes=len(ejes), simbolos=len(simbolos), w=w, cob_ejes=cob_e,
                sin_ejes=len(sin_e), lineas=len(r.polylines), cob_rec=cob_r, sin_rec=len(sin_r),
                guiones=r.coverage, diam=sum(1 for pl in r.polylines if pl.diam_in), t_rec=t_rec,
                sin_rec_pts=sin_r, sin_ejes_pts=sin_e,
                continua=any("trazo continuo" in x for x in r.warnings))
    sin_r = [(p, l) for p, l in sin_r if l > HUECO_GUION_PT]
    fila.update(sin_rec=len(sin_r), sin_rec_pts=[(tuple(fitz.Point(p) * page.rotation_matrix), l) for p, l in sin_r])
    salida(f"h.{i + 1}: {fila['capa']}  ejes {len(ejes)}  sím. {len(simbolos)} ({fila['sim_capas']} capas)  "
           f"w {w:.2f} pt | ejes: cob {cob_e:.3f} sin tinta {len(sin_e)} | rec: {len(r.polylines)} líneas "
           f"cob {cob_r:.3f} sin tinta {len(sin_r)} guiones {r.coverage:.3f} diám {fila['diam']} "
           f"{'continua' if fila['continua'] else 'núcleo'} | {t_ejes:.1f}+{t_rec:.1f} s")
    for p, l in fila["sin_rec_pts"][:8]:
        salida(f"    sin tinta (rec) {l:.1f} pt en ({p[0]:.1f}, {p[1]:.1f}) de la vista")
    return fila


def compuesta(doc, hojas):
    """Hoja compuesta (en un temporal) con las `hojas` enteras una al lado de la otra, sin puentes."""
    import tempfile
    from hoja import composite as C
    piezas, x = [], 0.0
    for h in hojas:
        piezas.append(C.Piece(source=0, page=h, clip=[0, 0, 1, 1], x=x, y=0.0, src_scale=1.0))
        x += doc[h].rect.width
    ruta = os.path.join(tempfile.mkdtemp(), "compuesta.pdf")
    C.build_document(C.Composite(pieces=piezas, scale_ft_per_pt=1.0, bridges=False), [doc], {}, []).save(ruta)
    return fitz.open(ruta)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cual", nargs="?", default="south", choices=sorted(PDFS))
    ap.add_argument("--hojas", default="")
    ap.add_argument("--compuesta", default="", help="hojas (1-based) ENTERAS una al lado de la otra, p. ej. 4,5")
    a = ap.parse_args(argv)
    doc = fitz.open(PDFS[a.cual])
    if a.compuesta:
        filas = [auditar(compuesta(doc, [int(h) - 1 for h in a.compuesta.split(",")]), 0)]
    else:
        hojas = [int(h) - 1 for h in a.hojas.split(",") if h.strip()] or range(doc.page_count)
        filas = [auditar(doc, i) for i in hojas]
    con = [f for f in filas if "lineas" in f]
    if con:
        print(f"TOTAL {a.cual}: {len(con)} hojas, líneas {sum(f['lineas'] for f in con)}, "
              f"diám {sum(f['diam'] for f in con)}, cob. rec. mín {min(f['cob_rec'] for f in con):.3f}, "
              f"sin tinta rec {sum(f['sin_rec'] for f in con)}, ejes sin tinta {sum(f['sin_ejes'] for f in con)}, "
              f"tiempo ejes medio {sum(f['t_ejes'] for f in con) / len(con):.1f} s")


if __name__ == "__main__":
    main()

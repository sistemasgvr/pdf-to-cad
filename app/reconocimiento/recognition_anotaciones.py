"""recognition_anotaciones.py — los RÓTULOS del plano con su guía (MLeader / MText), PUROS (pedido del usuario
2026-11-03: «reconocer su mtext o los leaders, esas flechas que señalan cada línea… guardarlo en el proyecto y que
al exportar se tenga en cuenta TODA esa información»).

El grosor del plano (`recognition_grosor`) ya lee los rótulos CON DIÁMETRO y sus guías; aquí se toma TODO bloque de
texto (MText: líneas a paso constante, `recognition_grosor_texto.rotulos`) del que sale una guía (raya bajo el texto o
recta que nace en su borde, hasta una punta con o sin flecha: `recognition_grosor_guias.Guias`), diga lo que diga
(«EX 8" VCP SEWER», «JOIN EX. 84" RCP SD / STA 549+55.37», «ABANDON IN PLACE», «CB-208»…). En las cuatro
direcciones de los ejes (texto girado 90°, `recognition_grosor_marcos`). Nada del reconocimiento cambia: es una
lista aparte que viaja en `RecognitionResult.anotaciones`.

Guía SIN texto legible (el texto es SHX dibujado con trazos: no hay texto en el PDF) = anotación «ilegible» con la
zona donde debería ir el texto; la IA puede leerla mirando la imagen (`ia/anotaciones_ia`).

Mapas sin capas (SIG): no hay guías; sus rótulos van paralelos a la tubería («8"», «12" DIP»): `de_mapa` los da
como MText con su giro.

Todo en px de la vista (los de `recognize_page`). Formato de cada anotación (dict, va tal cual al .digproj):
  {"tipo": "multileader"|"mtext", "texto", "caja": [x0, y0, x1, y1], "tam", "angulo" (grados, antihorario),
   "guias": [[(x, y)…] de la raya a la punta], "puntas": [(x, y)], "estado": "leido"|"ilegible",
   "utilidad", "diam_in", "material", "fuente": "pdf"|"ia"|"usuario"}
"""
from __future__ import annotations

import math
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from reconocimiento import recognition_grosor_guias as GG
from reconocimiento import recognition_grosor_marcos as MK
from reconocimiento import recognition_grosor_texto as GT

Pt = Tuple[float, float]

RAYA_SOLA_MIN_PT = 10.0       # raya sin texto: al menos esto de largo (las rayitas de las letras SHX no)
ZONA_ALTO_PT = 14.0           # alto de la zona del texto ilegible, sobre su raya
MAX_ILEGIBLES = 400           # por hoja: más es un dibujo (rejas, cuadros), no rótulos


def _bloques(lin) -> Tuple[Dict[int, Tuple], Dict[int, List[str]]]:
    """(cajas, textos) de cada bloque de texto horizontal (en el marco de `lin`)."""
    _rots, cajas = GT.rotulos(lin)
    texto_de = {tuple(bb): t for t, bb, _tam, _d in lin}
    textos = {b: [texto_de.get(tuple(l[0]), "") for l in ls] for b, ls in (cajas.lineas or {}).items()}
    return cajas, textos


def _guias_de_bloques(cajas, gs: GG.Guias) -> Tuple[Dict[int, List[Tuple[List[Pt], Pt]]], set]:
    """{bloque: [(cadena, punta)]} de cada guía que sale de un bloque (raya o arranque), y los tramos usados."""
    out: Dict[int, List[Tuple[List[Pt], Pt]]] = {}
    usados, vistos = set(), set()
    indice = GG._Cajas(cajas)

    def probar(blq, k, desde, minimo):
        if blq is None:
            return
        x0, y0, x1, y1, tam = cajas[blq]
        tol = GG.LANDING_TOL * tam
        for cadena, punta in gs.seguir(k, desde):
            if x0 - tol <= punta[0] <= x1 + tol and y0 - tol <= punta[1] <= y1 + tol:
                continue
            largo = sum(math.dist(p, q) for p, q in zip(cadena, cadena[1:]))
            if largo < GG.GUIA_MIN_PT * gs.zoom or len(cadena) < minimo:
                continue
            clave = (blq, GG._clave(punta))
            if clave not in vistos:
                vistos.add(clave)
                out.setdefault(blq, []).append((cadena, punta))
                usados.add(k)
    for k, (a, b) in enumerate(gs.tramos):
        if abs(b[1] - a[1]) <= 0.05 * max(abs(b[0] - a[0]), 1e-9):
            blq = GG._bloque_de_raya(a, b, indice, gs.zoom)
            for desde in (a, b):
                probar(blq, k, desde, 3)
            continue
        for e, otro in ((a, b), (b, a)):
            if gs.vecinos(e, k):
                continue
            probar(GG._bloque_de_arranque(e, otro, indice, gs.zoom), k, e, 2)
    return out, usados


def _rayas_sin_texto(gs: GG.Guias, usados: set, cajas) -> List[Tuple[Tuple[Pt, Pt], List[Pt], Pt]]:
    """Rayas horizontales sin bloque de texto con una guía que termina en una FLECHA: el texto existe pero no es
    texto del PDF (SHX dibujado)."""
    out = []
    indice = GG._Cajas(cajas) if cajas else None
    for k, (a, b) in enumerate(gs.tramos):
        if k in usados or abs(b[1] - a[1]) > 0.05 * max(abs(b[0] - a[0]), 1e-9):
            continue
        if abs(b[0] - a[0]) < RAYA_SOLA_MIN_PT * gs.zoom:
            continue
        if indice is not None and GG._bloque_de_raya(a, b, indice, gs.zoom) is not None:
            continue
        for desde in (a, b):
            for cadena, punta in gs.seguir(k, desde):
                if len(cadena) >= 3 and gs._flecha_en(cadena[-1]) is not None:
                    out.append(((a, b), cadena, punta))
                    break
        if len(out) > MAX_ILEGIBLES:
            return []
    return out


def _util_diam(textos: Sequence[str]):
    """(utilidad, diámetro único o None, material) de las líneas de un bloque."""
    util = next((u for u in (GT.utilidad_de(t) for t in textos) if u), "")
    diams = sorted({v for t in textos for v, _n in GT.lecturas(t)})
    mat = next((m for m in (GT.material_de(t) for t in textos) if m), "")
    return util, (diams[0] if len(diams) == 1 else None), mat


def _angulo(d: Pt) -> float:
    """Grados antihorarios del texto que se lee en la dirección d (px, y hacia abajo)."""
    return round(math.degrees(math.atan2(-d[1], d[0])) % 360.0, 3)


def leer(lineas: Sequence, gs: Optional[GG.Guias], zoom: float,
         fuera: Optional[Callable[[Pt], bool]] = None, con_mtext: bool = False) -> List[dict]:
    """Anotaciones de la hoja. `lineas` = `recognition_grosor_texto.lineas_texto` (px), `gs` = guías de la hoja,
    `fuera(punto)` = True en las vistas de perfil (sus rótulos no son de la planta). `con_mtext` = también los
    bloques SIN guía."""
    out: List[dict] = []
    usados_todos: set = set()
    cajas_h = None
    for d in MK.DIRECCIONES:
        if d == MK.DIRECCIONES[0]:
            lin, g, volver = lineas, gs, (lambda q: q)
        else:
            if not any(MK._en_direccion(l[3], d) for l in lineas):
                continue
            f = (lambda p, d=d: MK.al_marco(d, p))
            lin = [(t, MK._caja(f, bb), tam, MK.al_marco(d, dd)) for t, bb, tam, dd in lineas]
            g = (GG.Guias([(f(a), f(b)) for a, b in gs.tramos], [[f(v) for v in fl] for fl in gs.flechas], zoom)
                 if gs is not None else None)
            volver = (lambda q, d=d: MK.de_marco(d, q))
        # solo las líneas que se leen en esta dirección (las demás quedan horizontales en otro marco)
        lin = [l for l in lin if abs(l[3][1]) < 0.05 and l[3][0] > 0]
        if not lin:
            continue
        cajas, textos = _bloques(lin)
        if d == MK.DIRECCIONES[0]:
            cajas_h = cajas
        guias, usados = _guias_de_bloques(cajas, g) if g is not None else ({}, set())
        if d == MK.DIRECCIONES[0]:
            usados_todos = usados
        for b, (x0, y0, x1, y1, tam) in cajas.items():
            txt = [t for t in textos.get(b, []) if t.strip()]
            if not txt or (b not in guias and not con_mtext):
                continue
            caja = MK._caja(volver, (x0, y0, x1, y1))
            centro = ((caja[0] + caja[2]) / 2.0, (caja[1] + caja[3]) / 2.0)
            if fuera is not None and fuera(centro):
                continue
            util, diam, mat = _util_diam(txt)
            cads = guias.get(b, [])
            out.append(dict(tipo="multileader" if cads else "mtext", texto="\n".join(txt),
                            caja=[round(v, 3) for v in caja], tam=round(float(tam), 3), angulo=_angulo(d),
                            guias=[[(round(p[0], 3), round(p[1], 3)) for p in (volver(q) for q in cad)]
                                   for cad, _pt in cads],
                            puntas=[tuple(round(v, 3) for v in volver(pt)) for _cad, pt in cads],
                            estado="leido", utilidad=util, diam_in=diam, material=mat, fuente="pdf"))
    if gs is not None:
        for (a, b), cad, punta in _rayas_sin_texto(gs, usados_todos, cajas_h):
            x0, x1 = min(a[0], b[0]), max(a[0], b[0])
            y = (a[1] + b[1]) / 2.0
            caja = [round(x0, 3), round(y - ZONA_ALTO_PT * zoom, 3), round(x1, 3), round(y + 0.2 * zoom, 3)]
            if fuera is not None and fuera(((x0 + x1) / 2.0, y)):
                continue
            out.append(dict(tipo="multileader", texto="", caja=caja, tam=0.0, angulo=0.0,
                            guias=[[(round(p[0], 3), round(p[1], 3)) for p in cad]],
                            puntas=[(round(punta[0], 3), round(punta[1], 3))], estado="ilegible", utilidad="",
                            diam_in=None, material="", fuente="pdf"))
    return out


def leer_hoja(page, px: Callable[[Pt], Pt], zoom: float, ocultas=(), perfiles=()) -> List[dict]:
    """`leer` de la hoja (memorizado por hoja y transformación dentro de `pdf_styles.lectura_unica`: es el mismo
    para todas las utilidades)."""
    from hoja import pdf_styles
    perfiles = tuple(tuple(round(float(v), 3) for v in b) for b in perfiles or ())

    def fuera(q):
        return any(b[0] <= q[0] <= b[2] and b[1] <= q[1] <= b[3] for b in perfiles)

    def calcular():
        lineas = GT.lineas_texto(page, px, zoom)
        gs = GG.guias(page, px, zoom, ocultas, pdf_styles.drawings(page))
        return leer(lineas, gs, zoom, fuera if perfiles else None)
    huella = tuple(round(v, 6) for q in (px((0.0, 0.0)), px((1000.0, 0.0)), px((0.0, 1000.0))) for v in q)
    return pdf_styles.memo(page, ("anotaciones", huella, tuple(sorted(ocultas or ())), perfiles), calcular)


def de_mapa(rotulos_px: Sequence) -> List[dict]:
    """Los rótulos de un mapa sin capas (`recognition_grosor_mapa.RotuloMapa` en px) como MText con su giro."""
    out = []
    for r in rotulos_px:
        d, (cx, cy) = r.dir, r.centro
        up = (d[1], -d[0])
        h, w = r.tam * 0.6, r.largo / 2.0
        cs = [(cx + sx * w * d[0] + sy * h * up[0], cy + sx * w * d[1] + sy * h * up[1])
              for sx in (-1, 1) for sy in (-1, 1)]
        out.append(dict(tipo="mtext", texto=r.texto, caja=[round(min(c[0] for c in cs), 3),
                                                            round(min(c[1] for c in cs), 3),
                                                            round(max(c[0] for c in cs), 3),
                                                            round(max(c[1] for c in cs), 3)],
                        tam=round(float(r.tam), 3), angulo=_angulo(d), guias=[], puntas=[], estado="leido",
                        utilidad="", diam_in=float(r.pulg) if r.pulg else None, material=r.material or "",
                        fuente="pdf", acometida=bool(r.acometida)))
    return out

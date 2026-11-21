"""calcado_completar.py — la 2.ª pasada de `hoja_calcada.calcar`: lo que la cuadrícula común no cubrió.

Pedido del usuario 2026-11-17: la utilidad que se agrega puede venir en OTRA cuadrícula (una hoja
nueva cae mitad y mitad sobre dos hojas del editor, o cubre solo una parte) o dibujada DISTINTO (otra
exportación del mismo mapa, o el mapa base como imagen: el drenaje de Phoenix). La 1.ª pasada de
`calcar` (trazos idénticos, una hoja nueva por pieza del editor) no cambia; aquí, solo para las piezas
que quedaron sin cubrir:

  1. las hojas nuevas que la 1.ª pasada no usó se ubican sobre la hoja del editor ENTERA por lo que se
     ve (`encaje_imagen`; con la escala de otra hoja ya ubicada del mismo PDF la búsqueda es corta);
  2. `calcado_parcial.repartir` decide qué rectángulo dibuja cada una (área útil = el recuadro del
     mapa, o la hoja; solapes partidos por la mitad; nada fuera de las piezas sin cubrir);
  3. cada trozo es una pieza nueva en su lugar (`hoja_calcada.colocar`).

PURO: fitz, numpy, OpenCV.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from hoja import calcado_parcial as P
from hoja import composite as C
from hoja import encaje_imagen as EI
from hoja import encaje_imagen_lote as LOTE
from hoja import encaje_mapa_base as E
from nucleo import avance
from traduccion.i18n_core import t as _tr

VISTA_MIN_FRAC = 0.15        # (como `composicion_ficha`) un recuadro de mapa ocupa al menos esto…
VISTA_MAX_FRAC = 0.95        # …y no es la hoja entera
ESCALA_CONOCIDA_FACTOR = 1.03  # con la escala de otra hoja del mismo PDF: se busca ±3 %…
PASO_CONOCIDA = 0.01
ESCALA_LIBRE_FACTOR = 3.3      # sin ella: de 1/3.3 a 3.3 veces lo que mide una pieza del editor
MAX_SIN_UBICAR = 3           # hojas de un PDF sin ubicar (y ninguna ubicada): ese PDF es de otro lugar
MIN_SERIE = 2                # por imagen: hojas del mismo PDF que deben coincidir en la escala…
SERIE_TOL = 0.005            # …a ±0.5 %
Z_HOJA_UNICA_EXTRA = 4.0     # un PDF de una sola hoja no tiene con qué confirmarse: pico más claro
MIN_FRACCION_TRAZOS = 0.05   # por trazos: coinciden al menos esto de los trazos de la pieza del editor


def vista_mapa(page) -> Optional[Tuple[float, float, float, float]]:
    """El recuadro del mapa en la hoja visible: el recorte grande más interior (o None)."""
    import fitz
    m = page.rotation_matrix
    W, H = page.rect.width, page.rect.height
    clips = []
    for p in page.get_cdrawings(extended=True):
        if p.get("type") != "clip" or not p.get("scissor"):
            continue
        r = fitz.Rect(p["scissor"]) * m
        r.normalize()
        if VISTA_MIN_FRAC * W * H <= r.width * r.height <= VISTA_MAX_FRAC * W * H:
            clips.append((r.x0, r.y0, r.x1, r.y1))
    if not clips:
        return None
    return min(clips, key=lambda v: (v[2] - v[0]) * (v[3] - v[1]))


def area_util(page) -> Tuple[float, float, float, float]:
    return vista_mapa(page) or (0.0, 0.0, page.rect.width, page.rect.height)


def lienzo_del_editor(editor: C.Composite, sizes, docs_editor, target_editor: float, solo=None):
    """La hoja del editor para `encaje_imagen` + la caja de cada pieza en la hoja compuesta. `solo` =
    las piezas que se dibujan (una capa del mapa base: `hoja_calcada.referencia`; None = todas)."""
    import fitz
    piezas, cajas, fuentes = [], [], []
    usar = None if solo is None else set(solo)
    for k, p in enumerate(editor.pieces):
        size = sizes(p)
        caja = tuple(float(v) for v in C.piece_rect(p, size, target_editor))
        cajas.append(caja)
        if usar is not None and k not in usar:
            continue
        if abs(((p.rotation + 180.0) % 360.0) - 180.0) > 1e-6:
            continue                                      # (piezas giradas: no se dibujan aquí)
        piezas.append((docs_editor[p.source][p.page], fitz.Rect(C.clip_rect_pt(size, p.clip)), caja))
        fuentes.append((p.source, p.page))
    lz = EI.Lienzo(piezas) if piezas else None
    if lz is not None:
        lz.fuentes = fuentes                              # (fuente, hoja) de cada pieza: `encaje_imagen_lote`
    return lz, cajas


def _por_trazos(editor, sizes, target_editor, libres, f, doc, encajes, leer_nueva, trazos_pieza,
                usadas, cancelado) -> List[P.HojaUbicada]:
    """PDF de la MISMA plantilla que el editor (la 1.ª pasada ya halló trazos idénticos): cada hoja
    sin usar se busca, con la escala ya conocida, contra las piezas del editor sin cubrir (exacto)."""
    from hoja.hoja_calcada import mapa_pieza
    out: List[P.HojaUbicada] = []
    for h in range(doc.page_count):
        if (f, h) in usadas or (cancelado is not None and cancelado()):
            continue
        B = leer_nueva(f, h)
        if len(B) < E.MIN_VOTOS:
            continue
        mejor = None
        for k in libres:
            p = editor.pieces[k]
            e0 = encajes.get(p.source)
            if e0 is None:
                continue
            A = trazos_pieza(k)
            minimo = max(E.MIN_VOTOS, MIN_FRACCION_TRAZOS * len(A))
            e = E.encajar(B, A, escala=e0.escala) if len(A) >= E.MIN_VOTOS else None
            if e is not None and e.votos >= minimo and (mejor is None or e.votos > mejor[0].votos):
                mejor = (e, p)
        if mejor is None:
            continue
        e, p = mejor
        m = E.componer(e, *mapa_pieza(p, sizes(p), target_editor)).tupla()
        out.append(P.HojaUbicada(f, h, m, area_util(doc[h]), e.votos, e.rms))
    return out


# ─────────────────────────── celdas (la «georreferencia» de los mapas en cuadrícula) ───────────────────────────
# Pedido del usuario 2026-11-18: «que el plano entrante tome solo su lugar en el mapa, sin sufrir armando la
# composición». Los mapas de cuadrícula (cuartos de sección de Phoenix: «16-10», «17-13»…) dicen en cada hoja
# en qué cuadro del terreno caen: una hoja nueva va sobre la pieza del editor de su MISMA celda. La primera de
# cada PDF se busca solo alrededor de esa celda; las demás se PREVÉN con la primera (la misma plantilla pone
# cada cuadro en el mismo lugar de su hoja) y solo se comprueban (`encaje_imagen.ubicar_cerca`).

def _celda_txt(txt: str) -> Optional[Tuple[int, int]]:
    try:
        a, b = txt.split("-")
        return int(a), int(b)
    except (ValueError, AttributeError):
        return None


def celdas_editor(editor: C.Composite, docs_editor, piezas: Sequence[int]) -> Dict[Tuple[int, int], List[int]]:
    """{celda: [piezas del editor]} (la etiqueta que puso la composición sugerida o, si no, lo que dice la hoja)."""
    from hoja import composicion_ficha as F
    from hoja.hoja_calcada import _celda_de
    out: Dict[Tuple[int, int], List[int]] = {}
    leidas: Dict[Tuple[int, int], Optional[Tuple[int, int]]] = {}
    for k in piezas:
        p = editor.pieces[k]
        c = _celda_txt(_celda_de(p.label))
        if c is None:
            if (p.source, p.page) not in leidas:
                try:
                    leidas[(p.source, p.page)] = F.ficha(docs_editor[p.source][p.page], p.source).celda
                except Exception:
                    leidas[(p.source, p.page)] = None
            c = leidas[(p.source, p.page)]
        if c is not None:
            out.setdefault(tuple(c), []).append(k)
    return out


def celda_hoja(page) -> Optional[Tuple[int, int]]:
    from hoja import composicion_ficha as F
    try:
        c = F.ficha(page, 0).celda
    except Exception:
        return None
    return tuple(c) if c is not None else None


def _compuesta(m1, m2):
    """m1 ∘ m2 (similaridades (a, b, tx, ty))."""
    a1, b1, x1, y1 = m1
    a2, b2, x2, y2 = m2
    return (a1 * a2 - b1 * b2, a1 * b2 + b1 * a2, a1 * x2 - b1 * y2 + x1, b1 * x2 + a1 * y2 + y1)


def _inversa(m):
    a, b, tx, ty = m
    n = a * a + b * b
    ai, bi = a / n, -b / n
    return ai, bi, -(ai * tx - bi * ty), -(bi * tx + ai * ty)


def _caja_de(cajas, ks):
    cs = [cajas[k] for k in ks]
    return min(c[0] for c in cs), min(c[1] for c in cs), max(c[2] for c in cs), max(c[3] for c in cs)


def _zona_celda(cajas, ks):
    """La celda de la hoja y sus vecinas (pt de la hoja compuesta), o None sin celda."""
    if not ks:
        return None
    x0, y0, x1, y1 = _caja_de(cajas, ks)
    w, hh = x1 - x0, y1 - y0
    return (x0 - w, y0 - hh, x1 + w, y1 + hh)


def _por_imagen(lz, cajas, f, doc, usadas, cancelado, aviso, celdas=None, mapa_pieza=None,
                lado_pieza=None, previa=None, lote=None) -> List[P.HojaUbicada]:
    """PDF dibujado distinto: cada hoja se ubica por lo que se ve (`encaje_imagen`). La primera con la
    escala libre; las demás con esa escala. Solo vale si al menos `MIN_SERIE` hojas coinciden en la
    escala (una ubicación suelta puede ser casualidad; un PDF de una hoja pide un pico más claro).
    Con `celdas` ({celda: piezas del editor}) cada hoja se busca en SU celda, la primera alrededor de ella y
    las demás donde las pone la primera (`mapa_pieza(k)` = hoja del editor → hoja compuesta); una hoja cuya
    celda no está en el editor no se busca (cae fuera). `cajas` = las del editor (por índice de pieza).
    `previa` (dict, entrada y salida) = la hoja ya ubicada de OTRO PDF de la misma utilidad («North» → «South»,
    misma plantilla): la primera hoja de este se prevé con ella antes de buscarla.
    `lote` (`encaje_imagen_lote`): cuando la escala y la referencia ya no pueden cambiar, las hojas que faltan
    se ubican en otros procesos (mismas cuentas) y se toman en orden."""
    if lado_pieza is None:
        lado_pieza = float(np.median([max(c[2] - c[0], c[3] - c[1]) for c in cajas]))
    escala: Optional[float] = None
    fallos = 0
    previa = previa if previa is not None else {}
    ref = previa.get("ref")                         # (m de una hoja ya ubicada, pieza del editor de su celda)
    de_otro = ref is not None                       # la referencia es de otro PDF: si falla, se busca
    out: List[Tuple[P.HojaUbicada, float]] = []
    hojas = [h for h in range(doc.page_count) if (f, h) not in usadas]
    if celdas:
        celda_de = lote.celdas(f, hojas, doc) if lote is not None else {h: celda_hoja(doc[h]) for h in hojas}
    else:
        celda_de = {}
    if celdas:
        hojas = [h for h in hojas if celda_de[h] is None or celda_de[h] in celdas]
    repartidas = None                               # {hoja: encargo} desde que la escala y la referencia quedan fijas
    for i, h in enumerate(hojas):
        if cancelado is not None and cancelado():
            break
        aviso()
        page = doc[h]
        ks = celdas.get(celda_de.get(h)) if celdas else None
        if lote is not None and escala is not None and (not celdas or (ref is not None and not de_otro)):
            # de aquí en adelante nada de lo que se halle cambia la escala ni la referencia (sin celdas no hay
            # referencia que cambie): cada hoja es lo mismo que el camino de abajo con ellas fijas
            # (`encaje_imagen_lote.ubicar_hoja`)
            def pedido(h2):
                k2 = celdas.get(celda_de.get(h2)) if celdas else None
                previsto = None
                if ref is not None and k2 and mapa_pieza is not None:
                    m_ref, k_ref = ref
                    previsto = _compuesta(_compuesta(mapa_pieza(k2[0]), _inversa(mapa_pieza(k_ref))), m_ref)
                return (previsto, EI.escalas_alrededor(escala, ESCALA_CONOCIDA_FACTOR, PASO_CONOCIDA),
                        EI.Z_CONOCIDA, _zona_celda(cajas, k2))
            if repartidas is None:
                repartidas = {}
                for h2 in hojas[i:]:
                    ped = pedido(h2)
                    repartidas[h2] = (lote.ubicar(f, h2, ped), ped)
            fut, ped = repartidas.pop(h)
            res = lote.resultado(fut, lz, page, ped)
            if res is None:
                fallos += 1
                continue
            (s_, tx_, ty_, z_, dom_), area = res
            u = EI.Ubicado(s_, tx_, ty_, z_, dom_)
            out.append((P.HojaUbicada(f, h, u.tupla(), area, int(round(u.z * 100)), 0.0,
                                      celda=tuple(ks) if ks else ()), u.s))
            continue
        u = None
        if ref is not None and ks and mapa_pieza is not None:
            m_ref, k_ref = ref
            previsto = _compuesta(_compuesta(mapa_pieza(ks[0]), _inversa(mapa_pieza(k_ref))), m_ref)
            u = EI.ubicar_cerca(lz, page, previsto)
            if u is None and de_otro and escala is None:
                ref = None                             # la plantilla del otro PDF no sirve: se busca
        if u is None:
            if escala is None and fallos >= MAX_SIN_UBICAR:
                break                                  # ese PDF no dibuja este lugar
            if escala is not None:
                escalas = EI.escalas_alrededor(escala, ESCALA_CONOCIDA_FACTOR, PASO_CONOCIDA)
                z_min = EI.Z_CONOCIDA
            else:
                escalas = EI.escalas_alrededor(lado_pieza / max(page.rect.width, page.rect.height),
                                               ESCALA_LIBRE_FACTOR)
                z_min = EI.Z_LIBRE if doc.page_count > 1 else EI.Z_LIBRE + Z_HOJA_UNICA_EXTRA
            zona = _zona_celda(cajas, ks)              # su celda y las vecinas
            u = EI.ubicar(lz, page, escalas, cancelado=cancelado, z_min=z_min, zona=zona)
        if u is None:
            fallos += 1
            continue
        escala = escala or u.s
        if ks and (ref is None or de_otro):
            ref, de_otro = (u.tupla(), ks[0]), False
            previa["ref"] = ref
        out.append((P.HojaUbicada(f, h, u.tupla(), area_util(page), int(round(u.z * 100)), 0.0,
                                  celda=tuple(ks) if ks else ()), u.s))
    if doc.page_count > 1:
        r = float(np.median([s for _h, s in out])) if out else 0.0
        out = [(hu, s) for hu, s in out if abs(math.log(s / r)) <= SERIE_TOL]
        if len(out) < MIN_SERIE:
            return []
    return [hu for hu, _s in out]


def completar(editor: C.Composite, sizes, docs_editor, docs_nuevos, target_editor: float, target: float,
              libres: Sequence[int], ocupado: Sequence[Tuple[float, float, float, float]], usadas: set,
              nombres_nuevos=(), cancelado=None, plantilla: Optional[Dict[int, Dict[int, object]]] = None,
              leer_nueva=None, trazos_pieza=None, referencia=None):
    """→ (piezas nuevas, ubicaciones [(fuente, hoja, piezas del editor que toca, m, votos, rms)]).
    `plantilla` = {fuente nueva: {fuente del editor: encaje de la 1.ª pasada}} (PDF que comparten trazos
    idénticos con el editor: se siguen buscando así); los demás PDF, por imagen."""
    from hoja.hoja_calcada import colocar, _celda_de, mapa_pieza
    if not libres:
        return [], []
    plantilla = plantilla or {}
    cajas = [tuple(float(v) for v in C.piece_rect(p, sizes(p), target_editor)) for p in editor.pieces]
    ubicadas: List[P.HojaUbicada] = []
    lz = None
    lote = None
    total = sum(d.page_count for d in docs_nuevos)
    hechas = [0]

    def aviso():
        avance.avisar(_tr("Buscando hojas que caen entre las del editor…"), hechas[0], total)
        hechas[0] += 1
    try:
        for f, doc in enumerate(docs_nuevos):
            if cancelado is not None and cancelado():
                break
            if f in plantilla:
                hechas[0] += doc.page_count
                aviso()
                ubicadas += _por_trazos(editor, sizes, target_editor, libres, f, doc, plantilla[f], leer_nueva,
                                        trazos_pieza, usadas, cancelado)
                continue
            if lz is None:
                lz, _c = lienzo_del_editor(editor, sizes, docs_editor, target_editor, referencia)
                if lz is None:
                    break
                previa: dict = {}
                ref = list(referencia) if referencia is not None else list(range(len(editor.pieces)))
                celdas = celdas_editor(editor, docs_editor, ref)
                lado = float(np.median([max(cajas[k][2] - cajas[k][0], cajas[k][3] - cajas[k][1]) for k in libres]))
                # este PDF y los que siguen van por imagen: sus hojas se reparten en procesos (la celda de cada
                # una se lee ya, por adelantado)
                por_img = {f2: [h for h in range(d2.page_count) if (f2, h) not in usadas]
                           for f2, d2 in enumerate(docs_nuevos) if f2 >= f and f2 not in plantilla}
                lote = LOTE.crear(lz, getattr(lz, "fuentes", ()), docs_editor, docs_nuevos,
                                  sum(len(v) for v in por_img.values()))
                if lote is not None and celdas:
                    for f2, hs in por_img.items():
                        lote.adelantar_celdas(f2, hs)
            ubicadas += _por_imagen(lz, cajas, f, doc, usadas, cancelado, aviso, celdas=celdas, previa=previa,
                                    mapa_pieza=lambda k: mapa_pieza(editor.pieces[k], sizes(editor.pieces[k]),
                                                                    target_editor),
                                    lado_pieza=lado, lote=lote)
    finally:
        if lote is not None:
            lote.cerrar()
    if total:
        avance.avisar(_tr("Buscando hojas que caen entre las del editor…"), total, total)
    # una pieza por hoja: la que sabe su celda toma el cuadro de esa celda (sin recortarla a la cuadrícula del
    # editor ni dejar huecos); las demás se reparten como siempre
    con_celda = [hu for hu in ubicadas if hu.celda]
    reparto, tomado = P.repartir_celdas(con_celda, [_caja_de(cajas, hu.celda) for hu in con_celda],
                                        [cajas[k] for k in libres], ocupado)
    reparto += P.repartir([hu for hu in ubicadas if not hu.celda], [cajas[k] for k in libres], tomado)
    piezas, ubic = [], []
    for hu, r, ks in reparto:
        doc = docs_nuevos[hu.fuente]
        size = (doc[hu.hoja].rect.width, doc[hu.hoja].rect.height)
        clip = C.normalize_clip(P.clip_en_hoja(hu, r, size))
        k = libres[ks[0]]
        nombre = nombres_nuevos[hu.fuente] if hu.fuente < len(nombres_nuevos) else ""
        label = " · ".join(x for x in (nombre, str(hu.hoja + 1), _celda_de(editor.pieces[k].label)) if x)
        q = colocar(C.Piece(hu.fuente, hu.hoja, clip, label=label), size, hu.m, target)
        piezas.append(q)
        ubic.append((hu.fuente, hu.hoja, [libres[i] for i in ks], hu.m, hu.votos, hu.rms))
    return piezas, ubic

"""hoja_calcada.py — la hoja de OTRA utilidad, calcada sobre la hoja del editor.

Pedido del usuario 2026-10-23: con una utilidad ya importada (p. ej. agua, de dos PDF de 18
mapas cada uno), agregar otra que viene en sus propios PDF (alcantarillado) a la MISMA hoja,
«ubicándola por el plano, coordenadas, coincidencias», para tener todas las utilidades juntas.

En vez de mover lo que ya está en el editor, la hoja de la utilidad nueva se arma CALCADA
sobre la del editor: por cada pieza del editor (una hoja de su PDF, con su área y su lugar)
se busca la hoja del PDF nuevo que dibuja el mismo lugar y se mide cómo cae sobre ella por
el mapa base que comparten (`encaje_mapa_base`); la pieza nueva toma la MISMA área (llevada
a su hoja) y el mismo lugar en la hoja compuesta. Con el mismo `marco`, la hoja nueva mide
lo mismo que la del editor y tiene sus mismas coordenadas: lo que se reconozca en ella cae
justo sobre la hoja del editor sin transformar nada. Al importar, la hoja del editor pasa a
ser las piezas de antes + las nuevas (`combinar`), fundidas (modo oscurecer).

Qué hoja nueva corresponde a cada pieza: dos PDF con la misma plantilla repiten el MISMO
encaje en todas sus hojas (agua ↔ alcantarillado de Phoenix: ×1.02856 y la misma traslación
en las 18), así que tras encontrarlo en una hoja (`encajar`, buscando la escala) las demás se
reconocen al instante (`verificar`: 25–77 % de los trazos coinciden en la hoja correcta,
0 % en las otras). Sin esa suerte, se busca hoja por hoja.

PURO: fitz y numpy. `calcar_trabajo` es la entrada del proceso trabajador.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from hoja import calcado_completar as completar_mod
from hoja import calcado_parcial as P
from hoja import composite as C
from hoja import encaje_mapa_base as E
from nucleo import avance
from traduccion.i18n_core import t as _tr

MIN_FRACCION = 0.1          # la hoja correcta: coinciden al menos esta parte de los trazos de la pieza
INTENTOS_POR_PAR = 2        # piezas sin pareja tras las que un par de PDF ya no se recorre entero
INTENTOS_SIN_NINGUNA = 3    # …y sin NINGUNA hoja ubicada tras tantas piezas, el PDF no es de este lugar
SIN_GIRO_DEG = 1e-6
COBERTURA_MIN = 0.97        # la hoja nueva cubre así la pieza del editor (si no, la completa la 2.ª pasada)
ENCIMADA_FRAC = 0.9         # pieza de otro plano cubierta así por las ya elegidas: no se usa para buscar

Rect = Tuple[float, float, float, float]


@dataclass
class Ubicacion:
    """Dónde cae una hoja del PDF nuevo en la hoja compuesta del editor."""
    fuente: int                                  # índice entre las fuentes NUEVAS
    hoja: int
    pieza: int                                   # pieza del editor que cubre
    m: Tuple[float, float, float, float]         # hoja nueva (pt visibles) → hoja compuesta (pt)
    votos: int = 0
    rms: float = 0.0

    def to_dict(self) -> dict:
        return dict(fuente=self.fuente, hoja=self.hoja, pieza=self.pieza, m=list(self.m),
                    votos=self.votos, rms=self.rms)

    @classmethod
    def from_dict(cls, d: dict) -> "Ubicacion":
        return cls(int(d["fuente"]), int(d["hoja"]), int(d["pieza"]), tuple(float(v) for v in d["m"]),
                   int(d.get("votos", 0)), float(d.get("rms", 0.0)))


@dataclass
class Calco:
    comp: Optional[C.Composite]                  # hoja calcada (None: ninguna hoja coincide)
    ubicaciones: List[Ubicacion] = field(default_factory=list)
    sin_pareja: List[int] = field(default_factory=list)   # piezas del editor sin hoja nueva


# ─────────────────────────── geometría ───────────────────────────
def mapa_pieza(piece: C.Piece, size: Tuple[float, float], target: float) -> Tuple[float, float, float, float]:
    """`composite.piece_map` como similaridad (a, b, tx, ty) — hoja origen → hoja compuesta."""
    x0, y0, x1, y1 = C.clip_rect_pt(size, piece.clip)
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    f = C.piece_factor(piece, target)
    w, h = C.piece_size(piece, size, target)
    dX, dY = piece.x + w / 2.0, piece.y + h / 2.0
    th = math.radians(piece.rotation)
    a, b = f * math.cos(th), -f * math.sin(th)
    return a, b, dX - a * cx + b * cy, dY - b * cx - a * cy


def huella(piece: C.Piece, size: Tuple[float, float]) -> List[Tuple[float, float]]:
    """Lo visible de la pieza en SU hoja (pt visibles): el cuadrilátero o las esquinas del clip."""
    if piece.polygon:
        return [(x * size[0], y * size[1]) for x, y in piece.polygon]
    x0, y0, x1, y1 = C.clip_rect_pt(size, piece.clip)
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def colocar(piece: C.Piece, size: Tuple[float, float], m: Sequence[float], target: float) -> C.Piece:
    """La pieza (con su área ya elegida) en el lugar que da la similaridad `m` (hoja → hoja
    compuesta): factor, giro y posición para que `piece_map` sea exactamente `m`."""
    a, b, tx, ty = (float(v) for v in m)
    f = math.hypot(a, b)
    giro = math.degrees(math.atan2(-b, a)) % 360.0
    if abs(((giro + 180.0) % 360.0) - 180.0) < SIN_GIRO_DEG:
        giro = 0.0
    piece.rotation = giro
    piece.src_scale = f * target
    x0, y0, x1, y1 = C.clip_rect_pt(size, piece.clip)
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    X, Y = a * cx - b * cy + tx, b * cx + a * cy + ty
    w, h = C.piece_size(piece, size, target)
    piece.x, piece.y = X - w / 2.0, Y - h / 2.0
    return piece


def _normalizado(pts, size) -> List[Tuple[float, float]]:
    return [(min(1.0, max(0.0, x / size[0])), min(1.0, max(0.0, y / size[1]))) for x, y in pts]


def pieza_calcada(editor_piece: C.Piece, editor_size, nueva_size, encaje: E.Encaje,
                  fuente: int, hoja: int, target_editor: float, target: float, label: str = "") -> Optional[C.Piece]:
    """Pieza de la hoja nueva que cubre lo mismo que `editor_piece`: su huella llevada a la
    hoja nueva (el inverso del encaje) y el mismo lugar en la hoja compuesta."""
    pts = [encaje.inversa(x, y) for x, y in huella(editor_piece, editor_size)]
    norm = _normalizado(pts, nueva_size)
    xs, ys = [p[0] for p in norm], [p[1] for p in norm]
    clip = C.normalize_clip([min(xs), min(ys), max(xs), max(ys)])
    if (clip[2] - clip[0]) * nueva_size[0] < 2 * C.MIN_PIECE_PT or (clip[3] - clip[1]) * nueva_size[1] < 2 * C.MIN_PIECE_PT:
        return None                                    # la hoja nueva no llega a esa área
    girada = abs(encaje.giro_deg) >= E.GIRO_LIBRE_DEG       # el área ya no es un rectángulo en su hoja
    polygon = C.normalize_polygon(norm) if (editor_piece.polygon or girada) else []
    piece = C.Piece(fuente, hoja, clip, label=label, polygon=polygon)
    m = E.componer(encaje, *mapa_pieza(editor_piece, editor_size, target_editor)).tupla()
    # la pieza nueva va a la escala de la hoja calcada (`target`); el lugar no cambia
    return colocar(piece, nueva_size, m, target)


def _cobertura(q: C.Piece, q_size, target: float, p: C.Piece, p_size, target_editor: float) -> float:
    """Qué parte de la pieza `p` del editor cubre la pieza nueva `q` (en la hoja compuesta)."""
    a = C.piece_rect(p, p_size, target_editor)
    b = C.piece_rect(q, q_size, target)
    r = P.interseccion(tuple(a), tuple(b))
    return P.area(r) / max(1e-9, P.area(tuple(a)))


def marco_de(comp: C.Composite, page_sizes) -> List[float]:
    """Rectángulo de la hoja del editor en coordenadas de su hoja compuesta: el marco que ya
    tenía, la hoja misma (una sola hoja entera: no se materializa) o piezas + margen."""
    if comp.marco is not None:
        return [float(v) for v in comp.marco]
    if comp.is_single_full_page():
        return [float(v) for v in C.piece_rect(comp.pieces[0], page_sizes(comp.pieces[0]), comp.target_scale())]
    w, h, dx, dy = C.sheet_geometry(comp, page_sizes)
    return [-dx, -dy, w - dx, h - dy]


def _rect_huella(piece: C.Piece, size) -> Rect:
    pts = huella(piece, size)
    return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))


def _celda_de(label: str) -> str:
    """«QS Water…pdf · 1 · 17-10» → «17-10» (la etiqueta que puso la composición sugerida)."""
    partes = [p.strip() for p in (label or "").split("·")]
    ult = partes[-1] if partes else ""
    return ult if ult and ult[0].isdigit() and "-" in ult else ""


def referencia(editor: C.Composite, sizes, target_editor: float) -> List[int]:
    """Las piezas del editor con que se busca: UNA capa del mapa base. Con utilidades ya agregadas
    (reporte 2026-11-18, agua + alcantarillado → drenaje) la hoja trae un plano por grupo, uno
    ENCIMA del otro: buscar en todos duplicaba el trabajo y repetía trozos. Primero el plano 0;
    de los demás, solo las piezas que cubren algo que el 0 no cubre."""
    orden = sorted(range(len(editor.pieces)), key=lambda k: (int(editor.pieces[k].grupo), k))
    elegidas: List[int] = []
    cajas: List[Rect] = []
    for k in orden:
        p = editor.pieces[k]
        c = tuple(float(v) for v in C.piece_rect(p, sizes(p), target_editor))
        if int(p.grupo) != int(editor.pieces[orden[0]].grupo):
            resto = [c]
            for o in cajas:
                resto = [r for q in resto for r in P._restar(q, o)]
            if sum(P.area(r) for r in resto) <= (1.0 - ENCIMADA_FRAC) * P.area(c):
                continue
        elegidas.append(k)
        cajas.append(c)
    return sorted(elegidas)


# ─────────────────────────── calcar ───────────────────────────
def _parecido(a: str, b: str) -> float:
    """Nombres de archivo parecidos («…_North» con «…_North»): esas se prueban primero."""
    import re
    ta = {t for t in re.split(r"[^0-9a-záéíóúñ]+", (a or "").lower()) if t}
    tb = {t for t in re.split(r"[^0-9a-záéíóúñ]+", (b or "").lower()) if t}
    return len(ta & tb) / max(1, len(ta | tb))


def calcar(editor: C.Composite, docs_editor: Sequence, docs_nuevos: Sequence,
           nombres_nuevos: Sequence[str] = (), escala: Optional[float] = None,
           cancelado=None, nombres_editor: Sequence[str] = (), solo: Optional[Iterable] = None,
           al_ubicar=None, ocupado: Sequence[Rect] = ()) -> Calco:
    """Hoja calcada de los PDF nuevos sobre la hoja `editor` (su composición). `escala` =
    pies por pt de la hoja del editor (None: la de su composición). `solo` = las hojas nuevas
    (fuente, hoja) a buscar (None: todas); `al_ubicar(fuente, hoja, pieza, m)` avisa cada pieza ubicada;
    `ocupado` = lo que ya cubren hojas nuevas ubicadas antes (hoja compuesta: la 2.ª pasada no lo repite)."""
    target_editor = editor.target_scale()
    target = float(escala or target_editor)
    tam = lambda doc, i: (doc[i].rect.width, doc[i].rect.height)  # noqa: E731
    sizes = lambda p: tam(docs_editor[p.source], p.page)          # noqa: E731
    marco = marco_de(editor, sizes)
    ref = set(referencia(editor, sizes, target_editor))
    permitidas = None if solo is None else {(int(f), int(h)) for f, h in solo}
    fuera = set() if permitidas is None else {(f, h) for f, d in enumerate(docs_nuevos)
                                              for h in range(d.page_count) if (f, h) not in permitidas}
    n_nuevas = sum(d.page_count for d in docs_nuevos)
    leidas: Dict[Tuple[int, int], object] = {}
    del_editor: Dict[Tuple[int, int], object] = {}

    def nuevas(f: int, h: int):
        if (f, h) not in leidas:
            avance.avisar(_tr("Leyendo el mapa base de las hojas nuevas…"), len(leidas), n_nuevas)   # (lo YA leído)
            leidas[(f, h)] = E.trazos(docs_nuevos[f][h])
        return leidas[(f, h)]

    def _nom(lista, i):
        return lista[i] if i < len(lista) else ""

    conocidos: Dict[Tuple[int, int], E.Encaje] = {}   # (fuente del editor, fuente nueva) → encaje
    fallidos: Dict[Tuple[int, int], int] = {}         # búsquedas sin resultado por par de PDF
    ubic: List[Ubicacion] = []
    sin: List[int] = []
    piezas: List[C.Piece] = []
    buscadas_en_vano = 0
    usadas: set = set()                               # (fuente nueva, hoja) ya usadas

    def _ubicada(f, h, q, m):
        if al_ubicar is not None:
            al_ubicar(f, h, q, m)
    parciales: List[int] = []                         # piezas del editor cubiertas solo en parte
    tomado: List[Rect] = [tuple(float(v) for v in r) for r in ocupado]   # lo que ya cubren hojas nuevas
    for k, p in enumerate(editor.pieces):
        if cancelado is not None and cancelado():
            break
        if k not in ref:
            continue
        if not conocidos and buscadas_en_vano >= INTENTOS_SIN_NINGUNA:
            sin.extend(j for j in range(k, len(editor.pieces)) if j in ref)   # otro mapa base: no seguir buscando
            break
        avance.avisar(_tr("Buscando dónde cae cada hoja sobre la hoja del editor…"), k, len(editor.pieces))
        size = sizes(p)
        if (p.source, p.page) not in del_editor:
            del_editor[(p.source, p.page)] = E.trazos(docs_editor[p.source][p.page])
        A = E.preparar(del_editor[(p.source, p.page)], _rect_huella(p, size))
        if len(A) < E.MIN_VOTOS:
            sin.append(k)
            continue
        minimo = max(E.MIN_VOTOS, MIN_FRACCION * len(A))
        mejor: Optional[Tuple[E.Encaje, int, int]] = None
        # 1) el encaje de otra hoja del mismo par de PDF, en las hojas nuevas (la del mismo número
        # primero: en la hoja equivocada no coincide nada, así que la clara se toma sin mirar más)
        for (fe, fn), e in conocidos.items():
            if fe != p.source:
                continue
            for h in sorted(range(docs_nuevos[fn].page_count), key=lambda h: (h != p.page, abs(h - p.page))):
                if (fn, h) in fuera:
                    continue
                v = E.verificar(nuevas(fn, h), A, e)
                if v is not None and v.votos >= minimo and (mejor is None or v.votos > mejor[0].votos):
                    mejor = (v, fn, h)
                    if v.votos >= 2 * minimo:
                        break
            if mejor is not None and mejor[0].votos >= 2 * minimo:
                break
        # 2) buscarlo: el PDF de nombre más parecido y la hoja del mismo número primero. Un
        # par de PDF que ya falló en varias hojas no se vuelve a recorrer entero.
        if mejor is None:
            orden_pdf = sorted(range(len(docs_nuevos)), key=lambda f: -_parecido(
                _nom(nombres_editor, p.source), _nom(nombres_nuevos, f)))
            for fn in orden_pdf:
                if (p.source, fn) in conocidos or fallidos.get((p.source, fn), 0) >= INTENTOS_POR_PAR:
                    continue
                doc = docs_nuevos[fn]
                orden = [h for h in sorted(range(doc.page_count), key=lambda h: (h != p.page, abs(h - p.page)))
                         if (fn, h) not in fuera]
                for h in orden:
                    if cancelado is not None and cancelado():
                        break
                    v = E.encajar(nuevas(fn, h), A)
                    if v is not None and v.votos >= minimo and (mejor is None or v.votos > mejor[0].votos):
                        mejor = (v, fn, h)
                        if v.votos >= 2 * minimo:       # claro: no hace falta mirar las demás
                            break
                if mejor is not None:
                    break
                fallidos[(p.source, fn)] = fallidos.get((p.source, fn), 0) + 1
        if mejor is None:
            buscadas_en_vano += 1
            sin.append(k)
            continue
        e, fn, h = mejor
        conocidos.setdefault((p.source, fn), e)
        nombre = _nom(nombres_nuevos, fn)
        celda = _celda_de(p.label)
        label = " · ".join(x for x in (nombre, str(h + 1), celda) if x)
        q = pieza_calcada(p, size, tam(docs_nuevos[fn], h), e, fn, h, target_editor, target, label)
        m_hoja = E.componer(e, *mapa_pieza(p, size, target_editor)).tupla()
        if q is None:
            sin.append(k)
            continue
        piezas.append(q)
        _ubicada(fn, h, q, m_hoja)
        usadas.add((fn, h))
        ubic.append(Ubicacion(fn, h, k, m_hoja, e.votos, e.rms))
        tomado.append(tuple(C.piece_rect(q, tam(docs_nuevos[fn], h), target)))
        if _cobertura(q, tam(docs_nuevos[fn], h), target, p, size, target_editor) < COBERTURA_MIN:
            parciales.append(k)          # la hoja nueva cubre solo una parte (otra cuadrícula): la 2.ª pasada sigue
    if editor.pieces:                  # (arriba, lo YA hecho al empezar cada pieza; aquí el final)
        avance.avisar(_tr("Buscando dónde cae cada hoja sobre la hoja del editor…"), len(editor.pieces),
                      len(editor.pieces))
    n_fase1 = len(ubic)
    libres = sorted(set(sin) | set(parciales))
    if libres and (cancelado is None or not cancelado()):
        # 2.ª pasada: hojas de otra cuadrícula o dibujadas distinto (`calcado_completar`)
        def trazos_pieza(k):
            q = editor.pieces[k]
            if (q.source, q.page) not in del_editor:
                del_editor[(q.source, q.page)] = E.trazos(docs_editor[q.source][q.page])
            return E.preparar(del_editor[(q.source, q.page)], _rect_huella(q, sizes(q)))
        plantilla = {fn: {fe: e for (fe, f2), e in conocidos.items() if f2 == fn} for (_fe, fn) in conocidos}
        extra, ub2 = completar_mod.completar(
            editor, sizes, docs_editor, docs_nuevos, target_editor, target, libres, tomado, usadas | fuera,
            list(nombres_nuevos), cancelado, plantilla=plantilla, leer_nueva=nuevas, trazos_pieza=trazos_pieza,
            referencia=sorted(ref))
        for q, (f, h, _ks, m, _v, _r) in zip(extra, ub2):
            _ubicada(f, h, q, tuple(m))
        piezas += extra
        ubic += [Ubicacion(f, h, ks[0], tuple(m), int(v), float(r)) for f, h, ks, m, v, r in ub2]
        cubiertas = {k for _f, _h, ks, *_r in ub2 for k in ks}
        sin = [k for k in sin if k not in cubiertas]
    if not piezas:
        return Calco(None, ubic, sin)
    por_imagen = len(ubic) > n_fase1
    # sin puentes si alguna hoja se ubicó por la 2.ª pasada (mapas: los puentes unían líneas de piezas
    # vecinas a través de huecos y bordes; 1003 en el drenaje de Phoenix)
    comp = C.Composite(piezas, scale_ft_per_pt=target, bridges=editor.bridges and not por_imagen,
                       bridge_max_pt=editor.bridge_max_pt, seam_blend=editor.seam_blend, marco=list(marco))
    return Calco(comp, ubic, sin)


def recolocar(comp: C.Composite, ubicaciones: Sequence[Ubicacion], marco: Sequence[float],
              target: float, page_size) -> Tuple[C.Composite, List[C.Piece]]:
    """Tras «Componer hoja» en el modo «agregar utilidad»: cada pieza vuelve al lugar que da el
    mapa base de su hoja (el usuario elige hojas y áreas; el lugar lo pone el encaje). Las de
    una hoja sin encaje se quitan (no se sabe dónde caen). → (hoja calcada, piezas quitadas)."""
    por_hoja = {(u.fuente, u.hoja): u.m for u in ubicaciones}
    quedan: List[C.Piece] = []
    quitadas: List[C.Piece] = []
    for p in comp.pieces:
        m = por_hoja.get((p.source, p.page))
        if m is None:
            quitadas.append(p)
            continue
        quedan.append(colocar(p, page_size(p), m, target))
    nuevo = C.Composite.from_dict(comp.to_dict())
    nuevo.pieces = quedan
    nuevo.scale_ft_per_pt = target
    nuevo.marco = [float(v) for v in marco]
    return nuevo, quitadas


def combinar(editor: C.Composite, nueva: C.Composite, n_fuentes_editor: int, marco: Sequence[float],
             escala: Optional[float] = None) -> C.Composite:
    """La hoja del editor con la utilidad agregada: sus piezas tal cual + las de `nueva`
    (fuentes corridas tras las del editor, en un grupo propio), con el marco de antes y
    fundidas (el papel de una no tapa la tinta de la otra)."""
    out = C.Composite.from_dict(editor.to_dict())
    target = float(escala or editor.target_scale())
    if abs(target - out.target_scale()) > 1e-12:          # misma escala del editor, mismo lugar
        k = target / out.target_scale()
        for p in out.pieces:
            p.src_scale *= k
    out.scale_ft_per_pt = target
    grupo = max((p.grupo for p in out.pieces), default=0) + 1
    k = target / nueva.target_scale()
    for p in nueva.pieces:
        q = C.Piece.from_dict(p.to_dict())
        q.source += n_fuentes_editor
        q.src_scale *= k
        q.grupo = grupo
        out.pieces.append(q)
    out.marco = [float(v) for v in marco]
    out.seam_blend = True
    return out


# ─────────────────────────── trabajo de fondo ───────────────────────────
def grupos(comp: Optional[C.Composite]) -> List[int]:
    """Los grupos de piezas de la hoja (0 = la del editor, 1… = cada utilidad agregada), si son
    varios y la hoja tiene `marco` (hoja con utilidades agregadas); si no, []."""
    if comp is None or comp.marco is None:
        return []
    gs = sorted({int(p.grupo) for p in comp.pieces})
    return gs if len(gs) > 1 else []


def solo_grupo(comp: C.Composite, grupo: int) -> C.Composite:
    """El plano ORIGINAL de un grupo: la misma hoja (mismo `marco`: mismo tamaño y coordenadas)
    con solo sus piezas. Materializada, se ve como era antes de agregar las demás."""
    return solo_grupos(comp, (grupo,))


def solo_grupos(comp: C.Composite, grupos_: Iterable[int]) -> C.Composite:
    """Como `solo_grupo` con VARIOS grupos (planos encendidos en «Capas»): sus piezas en el orden de
    la hoja, el mismo `marco`."""
    quedan = {int(g) for g in grupos_}
    out = C.Composite.from_dict(comp.to_dict())
    out.pieces = [p for p in out.pieces if int(p.grupo) in quedan]
    out.utilidades_grupo = {}
    return out


def calcar_trabajo(editor_dict: dict, fuentes_editor: Sequence[bytes], fuentes_nuevas: Sequence[bytes],
                   nombres_nuevos: Sequence[str], escala: Optional[float] = None,
                   nombres_editor: Sequence[str] = (), solo=None, ocupado=None, progreso=None) -> dict:
    """Entrada del proceso trabajador: abre los PDF, calca y devuelve datos simples."""
    import fitz
    editor = C.Composite.from_dict(editor_dict)
    de = [fitz.open(stream=b, filetype="pdf") for b in fuentes_editor]
    dn = [fitz.open(stream=b, filetype="pdf") for b in fuentes_nuevas]
    try:
        cal = calcar(editor, de, dn, list(nombres_nuevos), escala, nombres_editor=list(nombres_editor), solo=solo,
                     al_ubicar=(lambda f, h, q, m: progreso("ubicada", f, h, q.to_dict(), list(m)))
                     if progreso is not None else None, ocupado=[tuple(r) for r in (ocupado or ())])
    finally:
        for d in de + dn:
            d.close()
    return dict(comp=cal.comp.to_dict() if cal.comp is not None else None,
                ubicaciones=[u.to_dict() for u in cal.ubicaciones], sin_pareja=list(cal.sin_pareja))

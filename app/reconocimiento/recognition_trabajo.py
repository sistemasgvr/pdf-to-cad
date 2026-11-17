"""recognition_trabajo.py — el reconocimiento de UNA hoja, como trabajo de fondo (PURO).

Lo que hacía `RecognitionWorker.run` (movido tal cual): un documento y una lectura de las
letras del linetype para todas las utilidades, y `recognize_page` por utilidad. Corre en el
proceso trabajador (`ui.comun.proceso`, pedido del usuario 2026-10-14: que reconocer una hoja
compuesta no trabe la ventana ni deje la RAM ocupada) o, sin proceso, en el hilo de siempre.

`progreso(...)` recibe, en orden:
  · ("utilidad", i, n, utilidad)  antes de cada utilidad,
  · ("capa", i, n, utilidad, k, m, hechos, total) al empezar cada capa de esa utilidad (k = capas YA hechas)
    y al terminar la última (m de m); hechos/total = trazos de esas capas / de todas (el peso real de cada capa),
  · ("trazos", i, n, utilidad, lote) durante la reconstrucción, como vista provisional,
  · ("hecha", i, n, utilidad, trazos) al terminarla: sustituye la vista provisional
    con los puntos (px) de las líneas ya ajustadas de esa utilidad.

`reconocer_parte` (plan 2026-11-16, «reconocimiento desde el editor») hace UNA parte — una utilidad (con i=0, n=1
en esos avisos), las válvulas, los diámetros o los rótulos — con el mismo código, sobre la lectura de la hoja que
queda retenida en el trabajador «reconocer» (`lectura_retenida`).
"""
from __future__ import annotations

import contextlib
from typing import Callable, Optional
import time


class FlujoTrazos:
    """Lotes acotados de líneas para la vista en vivo: copias, sin referencias al resultado que se sigue
    modificando. Una línea larga se parte compartiendo el extremo: no se pierde ningún tramo."""
    MAX_LINEAS = 64
    MAX_PUNTOS = 4096
    CADA_S = .05

    def __init__(self, publicar):
        self.publicar = publicar
        self.pendientes = []
        self.puntos = 0
        self.ultimo = 0.

    def agregar(self, pts):
        for inicio in range(0, len(pts) - 1, self.MAX_PUNTOS - 1):
            piece = [(float(x), float(y)) for x, y in pts[inicio:inicio + self.MAX_PUNTOS]]
            if self.puntos + len(piece) > self.MAX_PUNTOS:
                self.vaciar()
            self.pendientes.append(piece)
            self.puntos += len(piece)
            if (len(self.pendientes) >= self.MAX_LINEAS or self.puntos >= self.MAX_PUNTOS
                    or time.perf_counter() - self.ultimo >= self.CADA_S):
                self.vaciar()

    def vaciar(self):
        if self.pendientes:
            batch, self.pendientes = self.pendientes, []
            self.puntos = 0
            self.ultimo = time.perf_counter()
            self.publicar(batch)


def _leer_valvulas(page, zoom, hidden, roles_by_utility, results):
    """Complemento: una falla aquí nunca tumba el reconocimiento de las líneas."""
    salida = _valvulas_de(page, zoom, hidden, roles_by_utility, results)
    if salida is not None:
        poner_valvulas(results, salida)


def _valvulas_de(page, zoom, hidden, roles_by_utility, results):
    """{"valvulas", "avisos"} de la hoja junto a las líneas de `results` (que no se tocan); None si falló."""
    from reconocimiento import recognition_valvulas as RV
    try:
        valvulas = RV.completar(RV.leer_hoja(page, zoom, hidden or (), roles_by_utility), results, zoom)
        RV.ramales(page, valvulas, results, zoom, hidden or ())
    except Exception:                                  # noqa: BLE001
        return None
    return {"valvulas": valvulas, "avisos": RV.avisos(valvulas)}


def poner_valvulas(results, salida) -> None:
    """Lo que `reconocer_hoja` hace con las válvulas leídas: cada resultado las lleva y el primero suma sus avisos
    (también para la parte «VALVULAS» de `reconocer_parte`)."""
    for r in results:
        r.valvulas = salida["valvulas"]
    if results:
        results[0].warnings = list(results[0].warnings) + list(salida["avisos"])


@contextlib.contextmanager
def _valvulas_adelantadas(doc, page_index):
    """Las válvulas de una leyenda en imagen se dibujan en otros procesos MIENTRAS se reconocen las líneas
    (`recognition_valvulas.adelantar`, 2026-11-15: ~20 s de la compuesta de Southwest); al salir se suelta lo que
    nadie recogió. Dentro de `pdf_styles.lectura_unica`."""
    from reconocimiento import recognition_valvulas as RV, recognition_valvulas_tinta
    RV.adelantar(doc[page_index])
    try:
        yield
    finally:
        recognition_valvulas_tinta.soltar(doc)


def reconocer_hoja(pdf_path, page_index, zoom=1.0, utilities=("ELECTRICO",), hidden_ocgs=(),
                   layer_roles=None, roles_by_utility=None, join_routes=True, scale_ft_per_pt=None,
                   letters_off=(), progreso: Optional[Callable] = None, perfiles_de=()):
    import fitz
    from reconocimiento import recognition as rec
    utilities = rec.normalize_utilities(utilities)
    roles_by_utility = {str(k): dict(v or {}) for k, v in (roles_by_utility or {}).items()}
    layer_roles = dict(layer_roles or {})
    letters_off = set(letters_off or ())
    avisar = progreso or (lambda *a: None)
    results = []
    # un solo documento y UNA lectura de las letras del linetype para todas las
    # utilidades (`recognition.page_letters`, ~0.5–1 s por hoja); y los vectores de la hoja
    # se leen UNA vez para las letras y todas las utilidades (`pdf_styles.lectura_unica`)
    from hoja import pdf_styles
    with fitz.open(pdf_path) as doc, pdf_styles.lectura_unica(doc), _valvulas_adelantadas(doc, page_index):
        letters = None
        if any(not (roles_by_utility.get(u) or layer_roles) for u in utilities):
            letters = rec.page_letters(doc[page_index])
        for i, utility in enumerate(utilities):
            results.append(_reconocer_utilidad(
                doc, pdf_path, page_index, utility, i, len(utilities), letters, zoom=zoom,
                hidden_ocgs=hidden_ocgs, layer_roles=layer_roles, roles_by_utility=roles_by_utility,
                letters_off=letters_off, join_routes=join_routes, scale_ft_per_pt=scale_ft_per_pt,
                avisar=avisar, en_vivo=progreso is not None))
        _leer_valvulas(doc[page_index], zoom, hidden_ocgs, roles_by_utility, results)
    _aplicar_diametros(results, zoom, perfiles_de, avisar)
    return results


def _reconocer_utilidad(doc, pdf_path, page_index, utility, i, n, letters, *, zoom, hidden_ocgs, layer_roles,
                        roles_by_utility, letters_off, join_routes, scale_ft_per_pt, avisar, en_vivo):
    """Una utilidad (el cuerpo del bucle de `reconocer_hoja`, también la parte de una utilidad de
    `reconocer_parte`): `letters` = `page_letters` de la hoja o None si ninguna utilidad las usa."""
    from reconocimiento import recognition as rec
    avisar("utilidad", i, n, utility)
    flujo = FlujoTrazos(lambda batch: avisar("trazos", i, n, utility, batch))
    roles = roles_by_utility.get(utility) or layer_roles or None
    mine = letters
    if letters is not None:
        # una capa que el usuario asignó a mano («Ajustar capas…») a OTRA
        # utilidad no se toma aquí por sus letras: manda su elección
        claimed = {name for u, r in roles_by_utility.items() if u != utility
                   for name in [*(r.get(rec.ROLE_LINEAS) or ()), *(r.get(rec.ROLE_BUZONES) or ())]}
        mine = {k: v for k, v in letters.items()
                if k not in claimed and k not in letters_off}
    res = rec.recognize_page(
        pdf_path, page_index=page_index,
        utility=utility, zoom=zoom, doc=doc,
        hidden_ocgs=list(hidden_ocgs or ()), layer_roles=roles,
        join_routes=join_routes,
        scale_ft_per_pt=scale_ft_per_pt, letters=mine,
        al_trazo=flujo.agregar if en_vivo else None,
        avance=lambda k, m, *trazos: avisar("capa", i, n, utility, k, m, *trazos))
    flujo.vaciar()
    avisar("hecha", i, n, utility,
           [[(float(x), float(y)) for x, y in pl.pts_pdf] for pl in res.drawable])
    return res


def _aplicar_diametros(results, zoom, perfiles_de, avisar):
    """Los perfiles de los laterales dicen el diámetro de las tuberías que los cruzan: con TODAS las
    utilidades (si van en procesos aparte, lo hace `RecognitionWorker` al juntarlas). En una hoja
    compuesta, los perfiles de sus hojas de origen (`perfiles_de`: [(pdf, hoja)])."""
    from reconocimiento import recognition_grosor_cruces
    if perfiles_de and results:
        from dataclasses import replace
        from reconocimiento import recognition_grosor_perfiles
        from traduccion.i18n_core import t as _tr
        avisar("detalle", _tr("Perfiles de las hojas de origen"), None, None)
        propios = {pv.nombre for r in results for pv in (r.perfiles or [])}
        escala = results[0].scale_ft_per_pt or 0.0
        extra = [replace(pv, planta_px_por_pie=zoom / escala)
                 for pv in recognition_grosor_perfiles.de_hojas(perfiles_de) if pv.nombre not in propios] if escala else []
        if extra:
            for r in results:
                r.perfiles = list(r.perfiles or []) + extra
    recognition_grosor_cruces.aplicar(results)


# ── por PARTES (plan 2026-11-16, «reconocimiento desde el editor») ─────────────────────────────────────
VALVULAS, DIAMETROS, ROTULOS = "VALVULAS", "DIAMETROS", "ROTULOS"


def reconocer_parte(ruta, hoja, parte, firma, *, zoom=1.0, hidden_ocgs=(), roles_by_utility=None, letters_off=(),
                    join_routes=True, scale_ft_per_pt=None, perfiles_de=(), resultados_previos=None,
                    layer_roles=None, progreso: Optional[Callable] = None):
    """UNA parte del reconocimiento de la hoja (un ▶ del panel «Reconocer»), sobre la lectura RETENIDA de la hoja
    (`lectura_retenida`, por `firma`) y con el MISMO código de `reconocer_hoja`:

      · una utilidad → `[RecognitionResult]` (el cuerpo de su bucle; mismas letras, mismos roles);
      · "VALVULAS" → {"valvulas", "avisos"} junto a las líneas de `resultados_previos` (que no cambian; quien
        importa las pone con `poner_valvulas`, como `reconocer_hoja`);
      · "DIAMETROS" → los perfiles de los laterales sobre `resultados_previos` (los devuelve, ya aplicados);
      · "ROTULOS" → {"anotaciones"}: los rótulos del plano que hoy toma la importación (los del primer resultado
        que los trae; sin ninguno, los mismos leídos aquí).

    Utilidades + VALVULAS + DIAMETROS en ese orden = `reconocer_hoja` con todas (`tests/test_lectura_retenida.py`)."""
    from reconocimiento import lectura_retenida
    from reconocimiento import recognition as rec
    hoja = int(hoja)
    parte = str(parte).strip().upper()
    roles_by_utility = {str(k): dict(v or {}) for k, v in (roles_by_utility or {}).items()}
    layer_roles = dict(layer_roles or {})
    avisar = progreso or (lambda *a: None)
    previos = list(resultados_previos or [])
    doc = lectura_retenida.abrir(ruta, firma)
    lectura_retenida.reponer(doc)                    # como un `fitz.open` recién hecho, igual que `reconocer_hoja`
    if parte == VALVULAS:
        with _valvulas_adelantadas(doc, hoja):
            salida = _valvulas_de(doc[hoja], zoom, hidden_ocgs, roles_by_utility, previos)
        return salida if salida is not None else {"valvulas": [], "avisos": []}
    if parte == DIAMETROS:
        _aplicar_diametros(previos, zoom, perfiles_de, avisar)
        return previos
    if parte == ROTULOS:
        hechos = next((list(r.anotaciones) for r in previos if getattr(r, "anotaciones", None)), None)
        if hechos is None:
            hechos = _rotulos_de_hoja(doc[hoja], zoom, hidden_ocgs, roles_by_utility, layer_roles)
        return {"anotaciones": hechos}
    if parte not in rec.SUPPORTED_UTILITIES:
        raise ValueError(f"parte desconocida: {parte}")
    letters = None
    if not (roles_by_utility.get(parte) or layer_roles):
        letters = rec.page_letters(doc[hoja])
    return [_reconocer_utilidad(
        doc, str(ruta), hoja, parte, 0, 1, letters, zoom=zoom, hidden_ocgs=hidden_ocgs, layer_roles=layer_roles,
        roles_by_utility=roles_by_utility, letters_off=set(letters_off or ()), join_routes=join_routes,
        scale_ft_per_pt=scale_ft_per_pt, avisar=avisar, en_vivo=progreso is not None)]


def _rotulos_de_hoja(page, zoom, hidden_ocgs, roles_by_utility, layer_roles) -> list:
    """Los rótulos del plano sin reconocer ninguna utilidad: las MISMAS llamadas de `recognize_page` (misma
    transformación sin recorte, mismas vistas de perfil, mismas capas ocultas). Con capas: los multileaders
    (`recognition_anotaciones.leer_hoja`); mapa con leyenda: sus rótulos (`recognition_grosor_mapa`); sin capas ni
    leyenda, con estilos asignados a mano: `recognition_grosor_registros`. Complemento: nunca tumba."""
    from hoja import leyenda_mapa, pdf_styles
    from reconocimiento import recognition as rec
    from reconocimiento import recognition_anotaciones as A
    try:
        px = rec.px_de_hoja(page, zoom)
        con_capas = any((p.get("layer") or "") and not p["layer"].startswith(pdf_styles.PREFIX)
                        for p in pdf_styles.drawings(page) if p.get("type") not in ("clip", "group"))
        if con_capas:
            perfiles = []
            for x0, y0, x1, y1 in rec.profile_view_regions(page, None):
                cs = [px((x0, y0)), px((x1, y0)), px((x1, y1)), px((x0, y1))]
                perfiles.append((min(c[0] for c in cs), min(c[1] for c in cs),
                                 max(c[0] for c in cs), max(c[1] for c in cs)))
            return A.leer_hoja(page, px, zoom, set(hidden_ocgs or ()), perfiles)
        from reconocimiento import recognition_grosor_mapa as GM, recognition_grosor_registros as GR
        if leyenda_mapa.aplica(page):
            return A.de_mapa(GM.a_px(GM.rotulos(page), px, zoom))
        estilos = {n for r in [*roles_by_utility.values(), layer_roles] for n in (r.get(rec.ROLE_LINEAS) or ())
                   if str(n).startswith(pdf_styles.PREFIX)}
        if estilos:
            return A.de_mapa(GM.a_px(GR.rotulos(page), px, zoom))
    except Exception:                                  # noqa: BLE001 (complemento, como en `recognize_page`)
        pass
    return []

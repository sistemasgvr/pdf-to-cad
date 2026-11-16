"""roles_iniciales.py — los roles por utilidad con que el asistente dejaba una hoja al pulsar «Continuar» en «Capas de
la hoja» SIN tocar nada (plan 2026-11-16, «reconocimiento desde el editor», Tarea 9).

Al abrir un PDF ya no hay paso «Capas de la hoja»: la hoja se INTERPRETA (`hoja.interpretar_trabajo`) y el panel
«Reconocer» se llena solo. En una hoja SIN capas (mapas SIG, PDF aplanado) el diálogo dejaba asignados los estilos
que dice la leyenda del mapa (`leyenda_mapa.asignaciones`) o, sin leyenda, los que deduce del texto y los rótulos
del plano (`estilos_sugeridos`); con eso las mismas utilidades que hoy quedan listas para el ▶ sin abrir «Capas y
estilos…». `roles_iniciales` repite EXACTAMENTE lo que hacían `LayerAssignmentsMixin._init_assignments` +
`roles_by_utility()` (y `EstilosSugeridosMixin._apply_estilos_sugeridos`) con lo que leyó la interpretación, sin
armar el diálogo. Una prueba compara con el diálogo de verdad (`tests/test_flujo_abrir_interpretar.py`).

En una hoja CON capas (CAD) el diálogo devolvía los roles tal cual los recibía: aquí también.
"""
from __future__ import annotations

from typing import Callable, Optional

from hoja import estilos_sugeridos as ES, leyenda_mapa
from reconocimiento import recognition as rec


def _copia(roles) -> dict:
    return {u: {k: list(v) if isinstance(v, (list, tuple, set)) else v for k, v in (r or {}).items()}
            for u, r in (roles or {}).items()}


def roles_iniciales(layers, ley=None, sugeridos=None, base_roles=None,
                    textos_fuentes: Optional[Callable[[], list]] = None) -> dict:
    """Los roles por utilidad de la hoja: `layers` = `pdf_layers.page_layers` (los de la interpretación), `ley` = la
    leyenda del mapa (o None), `sugeridos` = `estilos_sugeridos.sugerir` (o None), `base_roles` = los que ya había
    (`Main._roles_de_la_hoja`) y `textos_fuentes()` = el texto de las hojas de ORIGEN (una hoja compuesta: su cajetín
    quedó fuera del recorte; `layer_sugeridos.textos_de_fuentes`)."""
    layers = list(layers or ())
    base = _copia(base_roles)
    asignadas = {}
    tocadas = set(base)
    cambio = False
    for u, r in base.items():
        for rol in (rec.ROLE_LINEAS, rec.ROLE_BUZONES, rec.ROLE_VALVULAS):
            for nombre in r.get(rol, ()):
                asignadas[nombre] = (u, rol)
    esta_hoja = (any(leyenda_mapa.CLAVE_LEYENDA in r for r in base.values())
                 and not any(r.get(leyenda_mapa.SUMAR_LEYENDA) for r in base.values()))
    ley_por_u = None
    con_estilos = any(L.get("source") == "style" for L in layers)
    hubo_leyenda = False
    # ── `_apply_map_legend` ──
    if con_estilos and ley is not None and ley.filas:
        if esta_hoja:
            ley_por_u = {u: list(r.get(leyenda_mapa.CLAVE_LEYENDA) or ())
                         for u, r in base.items() if leyenda_mapa.CLAVE_LEYENDA in r}
        else:
            hubo_leyenda = True
            en_mapa = {L["name"]: int(L.get("path_count") or 0) for L in layers}
            asig, _amb = leyenda_mapa.asignaciones(ley, en_mapa)
            ley_por_u = {}
            a_mano = {n for r in base.values() for rol in (rec.ROLE_LINEAS, rec.ROLE_BUZONES) for n in r.get(rol) or ()}
            for nombre, (u, rol) in asig.items():
                ley_por_u.setdefault(u, []).append(nombre)
                if nombre in a_mano:
                    continue
                asignadas[nombre] = (u, rol)
                tocadas.add(u)
            if asig:
                cambio = True
    if not hubo_leyenda and ley_por_u is None:
        if esta_hoja:
            ley_por_u = {u: list(r.get(leyenda_mapa.CLAVE_LEYENDA) or ())
                         for u, r in base.items() if leyenda_mapa.CLAVE_LEYENDA in r}
        elif con_estilos and sugeridos is not None:
            # ── `_apply_estilos_sugeridos` ──
            sug = sugeridos
            if sug.utilidad is None and sug.motivo in (ES.OK, ES.SIN_UTILIDAD) and textos_fuentes is not None:
                u, cuenta = ES.utilidad_de_texto(textos_fuentes())
                if u:
                    sug = ES.Sugerencia(**{**sug.__dict__, "utilidad": u, "menciones": cuenta, "motivo": ES.OK})
            if sug.motivo == ES.OK and sug.utilidad in rec.SUPPORTED_UTILITIES:
                en_hoja = {L["name"] for L in layers}
                a_mano = {n for r in base.values()
                          for rol in (rec.ROLE_LINEAS, rec.ROLE_BUZONES, rec.ROLE_VALVULAS) for n in r.get(rol) or ()}
                ley_por_u = {sug.utilidad: []}
                for nombre in sug.lineas:
                    if nombre not in en_hoja:
                        continue
                    ley_por_u[sug.utilidad].append(nombre)
                    if nombre in a_mano:
                        continue
                    asignadas[nombre] = (sug.utilidad, rec.ROLE_LINEAS)
                    tocadas.add(sug.utilidad)
                    cambio = True
    if not cambio:
        return base
    # ── `roles_by_utility()` ──
    from ui.asistente.recognition_dialog import _suggest_role
    out = {}
    for u in rec.SUPPORTED_UTILITIES:
        if u not in tocadas:
            continue
        roles = {rec.ROLE_LINEAS: [], rec.ROLE_BUZONES: [], rec.ROLE_VALVULAS: []}
        for L in layers:
            nombre = L["name"]
            if nombre in asignadas:
                dueno, rol = asignadas[nombre]
                if dueno != u:
                    continue
            elif u in base:
                rol = next((r for r in roles if nombre in base[u].get(r, ())), rec.ROLE_IGNORAR)
            else:
                rol = _suggest_role(L, u)
            if rol in roles:
                roles[rol].append(nombre)
        for nombre, (dueno, rol) in asignadas.items():
            if dueno == u and rol in roles and nombre not in roles[rol]:
                roles[rol].append(nombre)
        if ley_por_u is not None:
            roles[leyenda_mapa.CLAVE_LEYENDA] = list(ley_por_u.get(u, ()))
        out[u] = roles
    return out

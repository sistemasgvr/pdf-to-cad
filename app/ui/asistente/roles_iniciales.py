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

Red en IMAGEN (plan 2026-11-18 «Ejes de la red en imagen», Tarea 7): `Sugerencia.capas` (`hoja.certeza_capas`) dice
por cada capa de línea de imagen de qué utilidad es y si es SEGURO. Lo seguro se asigna solo (líneas de su utilidad y
sus símbolos como estructuras) y viaja como lo que asigna una leyenda (`CLAVE_LEYENDA`: solo en esta hoja); lo dudoso
no se asigna. La respuesta del usuario (`respuestas`, {capa: utilidad | `NO_RED`}, las del PDF de origen de la hoja)
MANDA y queda como asignación a mano (pasa a otras hojas). En esas hojas los estilos vectoriales que deducía el texto
(`Sugerencia.lineas`) ya no se asignan: la red es la de la imagen.
"""
from __future__ import annotations

from typing import Callable, Optional, Sequence

from hoja import estilos_sugeridos as ES, leyenda_mapa
from reconocimiento import recognition as rec

NO_RED = "NO_RED"                  # respuesta «No es una red» (`ventana_capas_imagen`)


def _copia(roles) -> dict:
    return {u: {k: list(v) if isinstance(v, (list, tuple, set)) else v for k, v in (r or {}).items()}
            for u, r in (roles or {}).items()}


def roles_iniciales(layers, ley=None, sugeridos=None, base_roles=None,
                    textos_fuentes: Optional[Callable[[], list]] = None, respuestas: Optional[dict] = None,
                    nombres_fuentes: Optional[Callable[[], Sequence[str]]] = None,
                    rehacer_imagen: bool = False) -> dict:
    """Los roles por utilidad de la hoja: `layers` = `pdf_layers.page_layers` (los de la interpretación), `ley` = la
    leyenda del mapa (o None), `sugeridos` = `estilos_sugeridos.sugerir` (o None), `base_roles` = los que ya había
    (`Main._roles_de_la_hoja`) y `textos_fuentes()` = el texto de las hojas de ORIGEN (una hoja compuesta: su cajetín
    quedó fuera del recorte; `layer_sugeridos.textos_de_fuentes`), `respuestas` = {capa de imagen: utilidad | `NO_RED`}
    que dio el usuario y `nombres_fuentes()` = los nombres de los PDF de ORIGEN (en una compuesta el PDF de trabajo es
    un temporal: su nombre no dice la red). Las capas de imagen que traen los roles de OTRA hoja (o todas, con
    `rehacer_imagen`: deshacer una respuesta) se quitan y se deciden otra vez aquí: lo seguro de esta hoja y las
    respuestas de SU PDF; así una respuesta dada para otro PDF nunca asigna una capa dudosa de éste."""
    layers = list(layers or ())
    base = _copia(base_roles)
    capas = list(getattr(sugeridos, "capas", None) or ())
    esta_hoja = (any(leyenda_mapa.CLAVE_LEYENDA in r for r in base.values())
                 and not any(r.get(leyenda_mapa.SUMAR_LEYENDA) for r in base.values()))
    if capas and (rehacer_imagen or not esta_hoja):
        base = _sin_imagen(base)
    asignadas = {}
    tocadas = set(base)
    cambio = False
    for u, r in base.items():
        for rol in (rec.ROLE_LINEAS, rec.ROLE_BUZONES, rec.ROLE_VALVULAS):
            for nombre in r.get(rol, ()):
                asignadas[nombre] = (u, rol)
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
        elif con_estilos and sugeridos is not None and not getattr(sugeridos, "capas", None):
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
    if capas and con_estilos:
        ley_capas = {} if ley_por_u is None else ley_por_u
        if aplicar_capas(capas, base, asignadas, tocadas, ley_capas, respuestas,
                         seguras=rehacer_imagen or not esta_hoja,
                         nombres_fuentes=nombres_fuentes):
            cambio = True
            ley_por_u = ley_capas
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


def _sin_imagen(base: dict) -> dict:
    """`base` sin ninguna capa de imagen (`imagen_ejes`) en sus roles ni en lo que asignó la leyenda."""
    from hoja import imagen_ejes
    return {u: {k: [n for n in v if not imagen_ejes.tipo_imagen(n)] if isinstance(v, list) else v
                for k, v in r.items()}
            for u, r in base.items()}


def _con_nombres(c, nombres):
    """La capa sin ninguna evidencia (`sin_evidencia` y nada más en contra) con UNA utilidad en el nombre de los PDF
    de origen: la misma regla que `certeza_capas.evaluar` con ese nombre (el «nombre» pesa más que todo)."""
    if c.seguro or list(c.en_contra) != ["sin_evidencia"] or not nombres:
        return c
    from hoja import composicion_hermanos as CH
    from hoja.certeza_capas import CapaCerteza
    us = {u for u in (CH.utilidad(n) for n in nombres) if u}
    if len(us) != 1:
        return c
    return CapaCerteza(c.capa, next(iter(us)), True, ["nombre"] + list(c.a_favor), [], list(c.simbolos))


def aplicar_capas(capas, base, asignadas, tocadas, ley_por_u, respuestas=None, seguras=True,
                  nombres_fuentes=None) -> bool:
    """Aplica las `CapaCerteza` de la hoja sobre `asignadas` ({capa: (utilidad, rol)}), `tocadas` y `ley_por_u`
    ({utilidad: capas que asignó «la leyenda»}) → True si cambió algo. La respuesta del usuario manda (sale de donde
    estuviera y, si no es `NO_RED`, va a mano a su utilidad); lo seguro (solo con `seguras`: en la MISMA hoja con
    roles elegidos en ella no se vuelve a poner) va como la leyenda, salvo lo ya asignado a mano."""
    respuestas = respuestas or {}
    a_mano = {n for r in (base or {}).values()
              for rol in (rec.ROLE_LINEAS, rec.ROLE_BUZONES, rec.ROLE_VALVULAS) for n in r.get(rol) or ()}
    nombres = None
    cambio = False
    for c in capas:
        resp = respuestas.get(c.capa)
        propias = [c.capa] + [s for s in c.simbolos or () if s != c.capa]
        if resp is not None:
            if resp != NO_RED and resp not in rec.SUPPORTED_UTILITIES:
                continue
            for n in propias:
                asignadas[n] = (None, rec.ROLE_IGNORAR)          # de nadie (sale de donde estuviera)
                for lst in ley_por_u.values():
                    while n in lst:
                        lst.remove(n)
            if resp != NO_RED:
                asignadas[c.capa] = (resp, rec.ROLE_LINEAS)
                for s in propias[1:]:
                    asignadas[s] = (resp, rec.ROLE_BUZONES)
                tocadas.add(resp)
            cambio = True
            continue
        if not seguras:
            continue
        if nombres is None:
            nombres = list(nombres_fuentes() or ()) if nombres_fuentes is not None else []
        c = _con_nombres(c, nombres)
        if not c.seguro or c.utilidad not in rec.SUPPORTED_UTILITIES or c.capa in a_mano:
            continue
        u = c.utilidad
        lst = ley_por_u.setdefault(u, [])
        for n, rol in [(c.capa, rec.ROLE_LINEAS)] + [(s, rec.ROLE_BUZONES) for s in propias[1:]]:
            if n in a_mano:
                continue
            if n not in lst:
                lst.append(n)
            asignadas[n] = (u, rol)
        tocadas.add(u)
        cambio = True
    return cambio

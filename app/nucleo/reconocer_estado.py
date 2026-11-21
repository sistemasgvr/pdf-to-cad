"""Estado PURO de las filas del panel «Reconocer» del editor (sin Qt ni fitz).

Una fila por cosa que se puede reconocer de la hoja (cada utilidad, válvulas,
diámetros, rótulos). Aquí solo viven los datos y las reglas: qué fuentes tiene cada
fila, cuándo está bloqueada, cuándo un cambio la deja desactualizada y qué se puede
pedir. Los textos de `motivo` son claves en español (`N_`): la interfaz los traduce
con `t()` al mostrarlos.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from traduccion.i18n_core import N_

# Las utilidades, en el orden de `reconocimiento.recognition.SUPPORTED_UTILITIES`
# (una prueba lo compara: aquí no se importa fitz).
UTILIDADES = ("ELECTRICO", "DRENAJE", "AGUA", "ALCANTARILLADO", "GAS", "TELECOM")
PARTES = UTILIDADES + ("VALVULAS", "DIAMETROS", "ROTULOS")

ESTADOS = ("sin_interpretar", "pendiente", "bloqueada", "reconociendo",
           "reconocida", "desactualizada", "error")
_HECHAS = ("reconocida", "desactualizada")

M_SIN_CAPAS = N_("No hay capas de esta utilidad en la hoja.")
M_OCULTAS = N_("Todas sus capas están ocultas.")
M_SIN_ESTILOS = N_("Asigna al menos un estilo de trazo a esta utilidad.")
M_SIN_VALVULAS = N_("No se encontraron válvulas en la hoja.")
M_SIN_ROTULOS = N_("No hay rótulos con guía en la hoja.")
M_DIAMETROS = N_("Reconoce antes al menos una utilidad: {faltan}.")
M_DIAMETROS_NINGUNA = N_("Reconoce antes al menos una utilidad.")
M_DIAMETROS_FALTAN = N_("Aún sin reconocer: {faltan}.")
M_VALVULAS = N_("Reconoce antes las líneas de su red.")
M_SIN_INTERPRETAR = N_("Interpreta la hoja antes de reconocer.")
M_RECONOCIENDO = N_("Ya se está reconociendo.")

# Nombre de cada fila (claves en español; la interfaz las traduce). Las de las utilidades
# son las de `recognition.UTILITY_LABELS` (una prueba lo compara).
ETIQUETAS = {"ELECTRICO": N_("Eléctrico"), "DRENAJE": N_("Drenaje"), "AGUA": N_("Agua"),
             "ALCANTARILLADO": N_("Alcantarillado"), "GAS": N_("Gas"),
             "TELECOM": N_("Telecomunicaciones"), "VALVULAS": N_("Válvulas"),
             "DIAMETROS": N_("Diámetros"), "ROTULOS": N_("Rótulos del plano")}


@dataclass
class Fila:
    parte: str
    estado: str = "sin_interpretar"
    fuentes: int = 0
    motivo: str = ""
    hechos: int = 0
    firma: Optional[str] = None
    verificar: List[dict] = field(default_factory=list)      # {texto, nivel, rect, ..., visto (✔ revisado)}
    unir_tramos: bool = True


@dataclass
class Estado:
    firma_hoja: Optional[str] = None
    filas: Dict[str, Fila] = field(default_factory=dict)


def nuevo() -> Estado:
    return Estado(None, {p: Fila(p) for p in PARTES})


def _estilos_asignados(roles_by_utility, u) -> int:
    """Nombres de estilo distintos asignados a `u` (cualquier rol)."""
    nombres = set()
    for valor in ((roles_by_utility or {}).get(u) or {}).values():
        if isinstance(valor, (list, tuple, set)):
            nombres.update(valor)
    return len(nombres)


def _fuentes_utilidad(u, interp, hidden, roles_by_utility) -> Tuple[int, str]:
    layers = list(interp.get("layers") or [])
    if layers and all(L.get("source") == "style" for L in layers):
        n = _estilos_asignados(roles_by_utility, u)
        return n, ("" if n else M_SIN_ESTILOS)
    from hoja import leyenda_estandar as le          # importa fitz: solo al usarse
    lineas, estructuras = le.capas_que_reconoce(layers, u)
    n = len(lineas) + len(estructuras)
    if not n:
        return 0, M_SIN_CAPAS
    if le.sin_capas_visibles(layers, hidden or (), [u]):
        return n, M_OCULTAS
    return n, ""


def _poner(fila: Fila, fuentes: int, motivo: str) -> None:
    fila.fuentes, fila.motivo = fuentes, motivo
    if fila.estado in _HECHAS or fila.estado == "reconociendo":
        return                                       # lo hecho se conserva
    fila.estado = "bloqueada" if motivo else "pendiente"


def de_interpretacion(estado: Estado, interp: dict, firma_hoja: str,
                      hidden=(), roles_by_utility=None) -> Estado:
    """Fuentes, bloqueos y estado de cada fila según lo que se leyó de la hoja.
    Con la misma hoja las filas ya reconocidas se conservan; otra hoja reinicia todo. Un estado sin hoja
    (`firma_hoja` None: un proyecto viejo, `de_proyecto_viejo`) es de ESTA hoja: lo reconocido se conserva."""
    if estado is None or (estado.firma_hoja is not None and estado.firma_hoja != firma_hoja):
        estado = nuevo()
    estado.firma_hoja = firma_hoja
    for u in UTILIDADES:
        _poner(estado.filas[u], *_fuentes_utilidad(u, interp, hidden, roles_by_utility))
    n = len(interp.get("simbolos") or ())
    _poner(estado.filas["VALVULAS"], n, "" if n else M_SIN_VALVULAS)
    n = int(interp.get("rotulos_n") or 0)
    _poner(estado.filas["ROTULOS"], n, "" if n else M_SIN_ROTULOS)
    fd = estado.filas["DIAMETROS"]
    fd.fuentes = 0
    if fd.estado not in _HECHAS and fd.estado != "reconociendo":
        fd.estado, fd.motivo = "pendiente", ""
    return estado


def _portable(v):
    """Datos para la huella: conjuntos como listas ORDENADAS (el orden de un `set` no es fijo)."""
    if isinstance(v, dict):
        return {str(k): _portable(x) for k, x in v.items()}
    if isinstance(v, (set, frozenset)):
        return sorted((_portable(x) for x in v),
                      key=lambda x: json.dumps(x, sort_keys=True, default=str))
    if isinstance(v, (list, tuple)):
        return [_portable(x) for x in v]
    return v


def firma_parte(parte, hidden, roles, letters_off, escala, unir) -> str:
    """Huella de lo que cambia el resultado de reconocer `parte`."""
    datos = {"parte": parte, "hidden": sorted(hidden or ()), "roles": _portable(roles or {}),
             "letters_off": sorted(letters_off or ()), "escala": escala, "unir": bool(unir)}
    crudo = json.dumps(datos, sort_keys=True, default=str, ensure_ascii=True)
    return hashlib.sha1(crudo.encode("utf-8")).hexdigest()


_ROLES_RECLAMAN = ("lineas", "buzones")      # = recognition.ROLE_LINEAS / ROLE_BUZONES (lo que `claimed` mira)


def _nombres(roles, claves=None) -> set:
    out = set()
    for k, v in (roles or {}).items():
        if (claves is None or k in claves) and isinstance(v, (list, tuple, set, frozenset)):
            out.update(str(x) for x in v)
    return out


def firma_utilidad(parte, hidden, roles_by_utility, letters_off, escala, unir, capas=None) -> str:
    """`firma_parte` de una UTILIDAD con solo lo que puede cambiar SU resultado (cambiar las capas de otra no la deja
    desactualizada): sus roles (con lo que puso la leyenda), las capas que otras utilidades reclaman a mano (el
    reconocimiento no las toma por sus letras: `recognition_trabajo._reconocer_utilidad`), las capas que no se toman
    por letras y las capas ocultas que esta utilidad podría usar. `capas` = las de la interpretación de la hoja
    (`pdf_layers.page_layers`, con `letter_utilities`); sin ellas, todas las ocultas y todas las reclamadas."""
    roles_by_utility = roles_by_utility or {}
    propios = roles_by_utility.get(parte) or {}
    reclamadas = set()
    for u, r in roles_by_utility.items():
        if u != parte:
            reclamadas |= _nombres(r, _ROLES_RECLAMAN)
    hidden = set(hidden or ())
    if capas:
        from hoja import leyenda_estandar as le          # importa fitz: solo al usarse
        capas = list(capas)
        por_letras = {c.get("name") for c in capas if parte in (c.get("letter_utilities") or ())}
        lineas, estructuras = le.capas_que_reconoce(capas, parte)
        suyas = set(lineas) | set(estructuras) | por_letras | _nombres(propios)
        hidden &= suyas
        reclamadas &= por_letras
    roles = {"propios": propios, "reclamadas": sorted(reclamadas)}
    return firma_parte(parte, hidden, roles, letters_off, escala, unir)


def marcar_cambios(estado: Estado, nuevas_firmas: Dict[str, str]) -> Estado:
    """Una fila reconocida cuya firma cambió pasa a «desactualizada»."""
    for parte, firma in (nuevas_firmas or {}).items():
        f = estado.filas.get(parte)
        if f and f.estado == "reconocida" and f.firma is not None and f.firma != firma:
            f.estado = "desactualizada"
    return estado


def _hechas(estado: Estado) -> List[str]:
    return [u for u in UTILIDADES if estado.filas[u].estado in _HECHAS]


def sin_reconocer(estado: Estado) -> List[str]:
    """Utilidades de la hoja que se pueden reconocer y aún no lo están (la fila «Diámetros» las nombra: sus
    diámetros no entran hasta reconocerlas)."""
    return [u for u in UTILIDADES if estado.filas[u].estado in ("pendiente", "error")]


def faltan_para_agregar(estado: Optional[Estado]) -> List[str]:
    """Partes que aún hay que reconocer antes de agregar una utilidad desde otro PDF (2026-11-21: agregar sobre
    una hoja a medio reconocer daba errores). Cuentan las utilidades, válvulas, diámetros y rótulos que están
    pendientes, con error, desactualizadas, o reconociéndose; las bloqueadas (la hoja no las
    tiene) no. Sin estado (proyecto sin panel Reconocer) no se exige nada."""
    if estado is None:
        return []
    return [p for p in PARTES if estado.filas[p].estado in
            ("pendiente", "error", "desactualizada", "reconociendo")]


def puede(estado: Estado, parte: str) -> Tuple[bool, str, dict]:
    """¿Se puede reconocer `parte` ahora? (sí/no, clave del motivo, datos del motivo).
    La interfaz muestra `t(clave).format(**datos)`."""
    f = estado.filas[parte]
    if f.estado == "sin_interpretar":
        return False, M_SIN_INTERPRETAR, {}
    if f.estado == "reconociendo":
        return False, M_RECONOCIENDO, {}
    if parte == "DIAMETROS":
        if _hechas(estado):
            return True, "", {}
        faltan = [u for u in UTILIDADES if estado.filas[u].estado != "bloqueada"]
        if faltan:
            return False, M_DIAMETROS, {"faltan": faltan}
        return False, M_DIAMETROS_NINGUNA, {}
    if f.estado == "bloqueada":
        return False, f.motivo, {}
    if parte == "VALVULAS" and not _hechas(estado):
        # `recognition_valvulas.completar` descarta las válvulas de utilidades no reconocidas
        return False, M_VALVULAS, {}
    return True, "", {}


def tras_reconocer(estado: Estado, parte: str, firma, hechos: int, verificar) -> Estado:
    """La fila `parte` queda reconocida. Una utilidad nueva cambia lo que dan válvulas y diámetros:
    si ya estaban reconocidas, pasan a «desactualizada»."""
    f = estado.filas[parte]
    f.estado, f.firma, f.hechos = "reconocida", firma, int(hechos or 0)
    f.verificar = list(verificar or [])
    if parte in UTILIDADES:
        for otra in ("VALVULAS", "DIAMETROS"):
            g = estado.filas[otra]
            if g.estado == "reconocida":
                g.estado = "desactualizada"
    return estado


def orden_todo(estado: Estado) -> List[str]:
    """Plan de «Reconocer todo»: utilidades → válvulas → diámetros → rótulos. Válvulas y diámetros
    entran si alguna utilidad estará reconocida cuando les toque."""
    plan = [u for u in UTILIDADES if puede(estado, u)[0]]
    hay_utilidad = bool(plan) or bool(_hechas(estado))
    fv = estado.filas["VALVULAS"]
    if hay_utilidad and fv.estado not in ("bloqueada", "sin_interpretar", "reconociendo"):
        plan.append("VALVULAS")
    if hay_utilidad and estado.filas["DIAMETROS"].estado not in ("sin_interpretar", "reconociendo"):
        plan.append("DIAMETROS")
    if puede(estado, "ROTULOS")[0]:
        plan.append("ROTULOS")
    return plan


def a_dict(estado: Estado) -> dict:
    return {"firma_hoja": estado.firma_hoja,
            "filas": {p: {"estado": f.estado, "fuentes": f.fuentes, "motivo": f.motivo,
                          "hechos": f.hechos, "firma": f.firma, "verificar": [dict(v) if isinstance(v, dict) else v for v in f.verificar],
                          "unir_tramos": f.unir_tramos}
                      for p, f in estado.filas.items()}}


def de_reconocimiento(pipe, parte) -> bool:
    """¿La tubería salió del reconocimiento de `parte`? Con el panel: su marca `reconocida`; de antes (sin la
    marca): `origen` «reconocido» y su capa (lo dibujado a mano no lo lleva)."""
    if not isinstance(pipe, dict):
        return False
    if "reconocida" in pipe:
        return pipe.get("reconocida") == parte
    return pipe.get("origen") == "reconocido" and pipe.get("layer") == parte


def avisos_diametro(estado: Optional[Estado]) -> bool:
    """¿Se muestran los avisos «Diámetro del plano» (`diametro_plano.avisos`)? Pedido del usuario (2026-11-17): no
    antes de reconocer la fila «Diámetros» (salían al importar las tuberías). Sin panel (`estado` None) o hoja que
    nunca se interpretó con él (proyecto de antes, `firma_hoja` None): como siempre, sí."""
    if estado is None or estado.firma_hoja is None:
        return True
    f = estado.filas.get("DIAMETROS")
    return f is None or f.estado in _HECHAS


def de_proyecto_viejo(pipes) -> Estado:
    """Proyecto guardado antes del panel «Reconocer»: nada interpretado; cada utilidad que ya tiene líneas
    RECONOCIDAS del PDF (`origen` «reconocido»; lo dibujado a mano no cuenta) queda «reconocida» (sin firma: no se
    sabe con qué capas) y el panel ofrece «Interpretar la hoja»."""
    e = nuevo()
    for p in pipes or ():
        u = (p or {}).get("layer") if isinstance(p, dict) else None
        if u in UTILIDADES and de_reconocimiento(p, u):
            f = e.filas[u]
            f.estado, f.hechos = "reconocida", f.hechos + 1
    return e


def al_abrir(estado: Estado) -> Estado:
    """Lo guardado a mitad de un ▶ («reconociendo») vuelve a como estaba: reconocida si ya tenía firma."""
    for f in estado.filas.values():
        if f.estado == "reconociendo":
            f.estado = "reconocida" if f.firma is not None else "pendiente"
    return estado


def de_dict(d: Optional[dict]) -> Estado:
    """Tolerante: claves faltantes o desconocidas no rompen."""
    d = d or {}
    e = nuevo()
    e.firma_hoja = d.get("firma_hoja")
    for p, v in (d.get("filas") or {}).items():
        if p not in e.filas or not isinstance(v, dict):
            continue
        f = e.filas[p]
        if v.get("estado") in ESTADOS:
            f.estado = v["estado"]
        f.fuentes = int(v.get("fuentes") or 0)
        f.motivo = v.get("motivo") or ""
        f.hechos = int(v.get("hechos") or 0)
        f.firma = v.get("firma")
        f.verificar = [dict(x) if isinstance(x, dict) else x for x in (v.get("verificar") or [])]
        f.unir_tramos = bool(v.get("unir_tramos", True))
    return e

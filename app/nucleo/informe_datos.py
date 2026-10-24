"""Datos del INFORME AUTOMÁTICO (PURO: sin Qt). Pedido del usuario 2026-10-23: un informe en Word de
conflictos y/o normativas, con capturas 2D, 3D o ambas, rápido aun con miles de utilidades.

Todo se pasa a FICHAS: un dict por conflicto o aviso con lo que ya midió la app (utilidades, cotas,
regla, fuente, lugar). Es el contrato con quien redacta (`informe_redaccion`): hoy plantillas; mañana
la IA recibe estas mismas fichas en JSON y solo redacta (los números los pone la app). Ver
`docs/pendientes_ia.md`.

Las fichas se juntan en ZONAS (rejilla de `ZONA_FT`; si salen más de `MAX_ZONAS`, la celda se agranda
al doble hasta que quepan): una captura por zona, no una por aviso. «Sin tipo» no va en zonas (con
miles de utilidades recién importadas serían miles): solo se cuenta en el resumen.

Los avisos del RECONOCIMIENTO («Diámetro del plano», `diametro_plano.CLASE`; merge con dev_santos_v2,
2026-10-24) van APARTE (decisión del usuario): fichas `tipo` «reconocimiento», ids R-1, R-2…, fuera de las
zonas y de los conteos de normativa; el Word les da su propia sección (`Opciones.reconocimiento`).
"""
from __future__ import annotations

import datetime as _dt
import math
from dataclasses import dataclass, field

ZONA_FT = 150.0               # lado de la celda con la que se juntan las fichas en zonas
MAX_ZONAS = 40                # más zonas = celdas más grandes (una captura por zona)
MARGEN_FT = 25.0              # aire alrededor de lo que muestra cada captura
LADO_MIN_FT = 80.0            # una captura nunca muestra menos que esto
ASPECTO = 1.6                 # ancho / alto de las capturas
NIVEL_CONFLICTO = "ERROR"     # los conflictos C-n son alertas rojas
CLASE_RECONOCIMIENTO = "grosor"   # = nucleo.diametro_plano.CLASE (sin importarlo: arrastra normas_validar)
ORDEN_TIPO = {"conflicto": 0, "aviso": 1, "reconocimiento": 2}


@dataclass
class Opciones:
    conflictos: bool = True
    normativas: bool = True
    capturas_2d: bool = True
    capturas_3d: bool = False
    reconocimiento: bool = True               # avisos del reconocimiento (diámetro del plano), aparte


@dataclass
class Zona:
    numero: int
    caja: tuple                                   # (x0, y0, x1, y1) en px del lienzo, ya con margen y aspecto
    fichas: list = field(default_factory=list)


@dataclass
class Informe:
    titulo: str
    fecha: str
    opciones: Opciones
    fichas: list                                  # todas (conflictos y avisos), en orden de lectura
    zonas: list                                   # [Zona]
    resumen: dict                                 # conteos (ver `resumen`)
    caja_total: tuple = None                      # lo dibujado (px), para el mapa general
    extra: dict = field(default_factory=dict)     # lo que quiera sumar quien llama (escala, proyecto…)


def utilidad(pipes, i):
    """Lo que la ficha dice de una utilidad (lo mismo que verá la IA)."""
    if i is None or not (0 <= i < len(pipes)):
        return None
    p = pipes[i]
    try:
        diam = float(p.get("diam") or 0.0) or None
    except (TypeError, ValueError):
        diam = None
    return {"indice": i, "numero": i + 1, "capa": p.get("layer") or "", "nombre": (p.get("name") or "").strip(),
            "codigo": f"{(p.get('layer') or '').strip()}-{i + 1}", "tipo": (p.get("tipo") or "").strip(),
            "diametro_in": diam, "material": (p.get("material") or "").strip()}


def ficha_conflicto(c, pipes):
    """`c` = `nucleo.conflictos.Conflicto` (C-n)."""
    utils = [u for u in (utilidad(pipes, i) for i in c.pipes or []) if u]
    for u, z in zip(utils, c.cotas or []):
        u["cota_ft"] = z
    return {"tipo": "conflicto", "id": c.id, "clase": c.clave, "titulo": c.titulo, "nivel": NIVEL_CONFLICTO,
            "info": False, "x": float(c.x), "y": float(c.y), "utilidades": utils,
            "valores": {"diferencia_ft": c.diferencia}, "mensaje_app": c.mensaje or "", "fuente": "",
            "aprobado": None}


def ficha_aviso(a, pipes, n):
    """`a` = `nucleo.normas_validar.Aviso`; `n` = su número en el informe (N-1, N-2…)."""
    from nucleo.normas_validar import CLASES
    u = utilidad(pipes, a.pipe)
    aprob = a.aprobado or None
    return {"tipo": "aviso", "id": f"N-{n}", "clase": a.clase, "titulo": CLASES.get(a.clase, a.clase),
            "nivel": "INFO" if a.info else (getattr(a, "nivel", "") or "AVISO"), "info": bool(a.info),
            "x": float(a.x), "y": float(a.y), "utilidades": [u] if u else [], "valores": {},
            "mensaje_app": a.mensaje or "", "fuente": getattr(a, "fuente", "") or "",
            "aprobado": ({k: aprob.get(k) for k in ("usuario", "fecha", "nota")} if aprob else None)}


def ficha_reconocimiento(a, pipes, n):
    """Aviso del reconocimiento (diámetro del plano) → ficha R-n, aparte de la normativa."""
    f = ficha_aviso(a, pipes, n)
    f.update(tipo="reconocimiento", id=f"R-{n}")
    return f


def _lectura(f):
    return (round(f["y"] / 8.0), f["x"])                  # como los C-n: de arriba abajo, de izquierda a derecha


def fichas(conflictos, avisos, pipes, opciones):
    """Las fichas del informe según `opciones` y cuántos «sin tipo» quedaron fuera."""
    out = [ficha_conflicto(c, pipes) for c in conflictos or []] if opciones.conflictos else []
    sin_tipo = 0
    orden = sorted((a for a in avisos or []), key=lambda a: (round(a.y / 8.0), a.x))
    n = r = 0
    for a in orden:
        if a.clase == CLASE_RECONOCIMIENTO:
            if getattr(opciones, "reconocimiento", True):
                r += 1
                out.append(ficha_reconocimiento(a, pipes, r))
        elif not opciones.normativas:
            continue
        elif a.clase == "tipo":
            sin_tipo += 1
        else:
            n += 1
            out.append(ficha_aviso(a, pipes, n))
    return out, sin_tipo


def zonas(lista, ft_per_px, zona_ft=ZONA_FT, maximo=MAX_ZONAS):
    """Agrupa las fichas por celdas; con más de `maximo` zonas la celda crece al doble. Cada zona trae su
    caja de captura (con margen, lado mínimo y proporción `ASPECTO`), numeradas en orden de lectura."""
    if not lista:
        return []
    px_ft = 1.0 / max(ft_per_px or 0.0, 1e-9)
    lado = zona_ft * px_ft
    while True:
        celdas = {}
        for f in lista:
            celdas.setdefault((math.floor(f["x"] / lado), math.floor(f["y"] / lado)), []).append(f)
        if len(celdas) <= maximo:
            break
        lado *= 2.0
    grupos = sorted(celdas.values(), key=lambda fs: min(_lectura(f) for f in fs))
    out = []
    for k, fs in enumerate(grupos, 1):
        x0, x1 = min(f["x"] for f in fs), max(f["x"] for f in fs)
        y0, y1 = min(f["y"] for f in fs), max(f["y"] for f in fs)
        m = MARGEN_FT * px_ft
        w, h = (x1 - x0) + 2 * m, (y1 - y0) + 2 * m
        w, h = max(w, LADO_MIN_FT * px_ft), max(h, LADO_MIN_FT * px_ft / ASPECTO)
        w, h = max(w, h * ASPECTO), max(h, w / ASPECTO)
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        z = Zona(k, (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2), sorted(fs, key=_lectura))
        for f in z.fichas:
            f["zona"] = k
        out.append(z)
    return out


def resumen(lista, sin_tipo, pipes):
    """Conteos para la portada: totales, por nivel, por título y por utilidad."""
    por_titulo, por_utilidad, por_nivel = {}, {}, {}
    pendientes = aprobados = info = 0
    for f in lista:
        por_titulo[(f["tipo"], f["titulo"])] = por_titulo.get((f["tipo"], f["titulo"]), 0) + 1
        por_nivel[f["nivel"]] = por_nivel.get(f["nivel"], 0) + 1
        for u in f["utilidades"]:
            por_utilidad[u["capa"]] = por_utilidad.get(u["capa"], 0) + 1
        if f.get("aprobado"):
            aprobados += 1
        elif f["info"]:
            info += 1
        else:
            pendientes += 1
    return {"utilidades": sum(1 for p in pipes if not p.get("world") and len(p.get("pts") or []) >= 2),
            "conflictos": sum(1 for f in lista if f["tipo"] == "conflicto"),
            "avisos": sum(1 for f in lista if f["tipo"] == "aviso"), "pendientes": pendientes,
            "reconocimiento": sum(1 for f in lista if f["tipo"] == "reconocimiento"),
            "avisos_pendientes": sum(1 for f in lista if f["tipo"] == "aviso" and not f["info"]
                                     and not f.get("aprobado")),
            "aprobados": aprobados, "info": info, "sin_tipo": sin_tipo, "por_nivel": por_nivel,
            "por_titulo": sorted(por_titulo.items(), key=lambda kv: -kv[1]),
            "por_utilidad": sorted(por_utilidad.items(), key=lambda kv: -kv[1])}


def caja_de(pipes):
    xs = [q[0] for p in pipes if not p.get("world") for q in p.get("pts") or []]
    ys = [q[1] for p in pipes if not p.get("world") for q in p.get("pts") or []]
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def armar(conflictos, avisos, pipes, ft_per_px, opciones, titulo="", ahora=None):
    lista, sin_tipo = fichas(conflictos, avisos, pipes, opciones)
    lista.sort(key=lambda f: (ORDEN_TIPO.get(f["tipo"], 9), _lectura(f)))
    fecha = (ahora or _dt.datetime.now()).strftime("%Y-%m-%d %H:%M")
    en_zonas = [f for f in lista if f["tipo"] != "reconocimiento"]           # los de reconocimiento, aparte
    return Informe(titulo=titulo, fecha=fecha, opciones=opciones, fichas=lista,
                   zonas=zonas(en_zonas, ft_per_px), resumen=resumen(lista, sin_tipo, pipes),
                   caja_total=caja_de(pipes))

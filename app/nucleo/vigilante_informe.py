"""vigilante_informe.py — lee una sesión del vigilante (`nucleo/vigilante.py`) y dice DÓNDE se fue el tiempo.

`leer(carpeta)` → sucesos de todos los procesos; `resumir(sucesos)` → dict con congelamientos, trabajos, etapas,
bloques, cargas, memoria y el perfil sumado del reconocimiento; `markdown(resumen)` → informe legible;
`comparar(a, b)` → antes/después de dos sesiones (misma tarea, otro código). Sin Qt: lo usan
`scripts/rendimiento/vigilante.py` y, más adelante, la ventana del monitor.
"""
from __future__ import annotations

import glob
import json
import os
import re
from typing import Dict, List, Optional

from nucleo import vigilante as V

_NUM = re.compile(r"\d+(?:[.,]\d+)?")
RECONOCER = ("reconoc", "interpretar", "recognition")


def sesiones() -> List[str]:
    b = V.base()
    if not os.path.isdir(b):
        return []
    return sorted(os.path.join(b, d) for d in os.listdir(b) if os.path.isdir(os.path.join(b, d)))


def ultima() -> Optional[str]:
    s = sesiones()
    return s[-1] if s else None


def leer(carpeta: str) -> List[dict]:
    out = []
    for ruta in sorted(glob.glob(os.path.join(carpeta, "proc-*.jsonl"))):
        with open(ruta, encoding="utf-8", errors="replace") as f:
            for linea in f:
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    out.append(json.loads(linea))
                except ValueError:
                    pass                       # una línea cortada (el proceso murió escribiendo)
    out.sort(key=lambda e: e.get("t", 0))
    return out


def _clave(texto: str) -> str:
    return _NUM.sub("#", texto or "").strip()


def _agregar(filas, clave_fn, dur_fn=lambda e: e.get("dur") or 0.0) -> List[dict]:
    g: Dict[str, dict] = {}
    for e in filas:
        k = clave_fn(e)
        d = float(dur_fn(e) or 0.0)
        a = g.setdefault(k, {"nombre": k, "veces": 0, "total": 0.0, "max": 0.0})
        a["veces"] += 1
        a["total"] += d
        a["max"] = max(a["max"], d)
    for a in g.values():
        a["media"] = a["total"] / a["veces"] if a["veces"] else 0.0
    return sorted(g.values(), key=lambda a: -a["total"])


def _sumar_perfiles(perfiles, campo: str) -> List[list]:
    s: Dict[str, float] = {}
    for p in perfiles:
        for n, v in (p or {}).get(campo) or []:
            s[n] = s.get(n, 0.0) + v
    return sorted(([n, v] for n, v in s.items()), key=lambda x: -x[1])


def resumir(sucesos: List[dict]) -> dict:
    por = {}
    for e in sucesos:
        por.setdefault(e.get("tipo"), []).append(e)
    procesos = {}
    for e in por.get("inicio", []):
        procesos[e["pid"]] = {"pid": e["pid"], "nombre": e.get("nombre") or e.get("proc"), "inicio": e.get("t"),
                              "version": e.get("version")}
    pico: Dict[int, float] = {}
    ram_min = None
    for e in por.get("sistema", []):
        if e.get("ram_libre_mb") is not None:
            ram_min = e["ram_libre_mb"] if ram_min is None else min(ram_min, e["ram_libre_mb"])
        for p in e.get("procesos") or []:
            pid = p.get("pid")
            pico[pid] = max(pico.get(pid, 0.0), p.get("priv_mb") or 0.0)
            procesos.setdefault(pid, {"pid": pid, "nombre": p.get("exe"), "inicio": e.get("t")})
    for pid, v in pico.items():
        procesos[pid]["pico_mb"] = v
    t0 = min((e.get("t", 0) for e in sucesos), default=0)
    t1 = max((e.get("t", 0) for e in sucesos), default=0)
    congel = [e for e in por.get("congelamiento", []) if not e.get("suspension")]
    trabajos = por.get("trabajo", [])
    rec = [e for e in trabajos if any(r in (e.get("objetivo") or "").lower() for r in RECONOCER)]
    return {
        "duracion_s": t1 - t0, "procesos": sorted(procesos.values(), key=lambda p: p.get("inicio") or 0),
        "ram_libre_min_mb": ram_min,
        "congelamientos": sorted(congel, key=lambda e: -e.get("dur", 0)),
        "congelado_total_s": sum(e.get("dur", 0) for e in congel),
        "no_responde": sum(1 for e in congel if e.get("no_responde")),
        "trabajos": _agregar(trabajos, lambda e: e.get("objetivo") or "?"),
        "trabajos_lentos": sorted(trabajos, key=lambda e: -e.get("dur", 0))[:10],
        "encargos": _agregar(por.get("encargo", []), lambda e: f"{e.get('trabajador')} · {e.get('objetivo')}",
                             lambda e: e.get("total") or 0.0),
        "espera_cola": _agregar(por.get("encargo", []), lambda e: e.get("trabajador") or "?",
                                lambda e: e.get("espera") or 0.0),
        "etapas": _agregar(por.get("etapa", []),
                           lambda e: (f"[{e['dentro'].split(' › ')[-1]}] " if e.get("dentro") else "")
                           + _clave(e.get("texto"))),
        "bloques": _agregar(por.get("bloque", []),
                            lambda e: e.get("nombre", "?") + (f" · {e['utilidad']}" if e.get("utilidad") else "")),
        "cargas": _agregar(por.get("carga", []), lambda e: _clave(e.get("texto"))),
        "acumulados": _agregar(por.get("acumulado", []), lambda e: e.get("nombre", "?")),
        "perfil_reconocer_propio": _sumar_perfiles([e.get("perfil") for e in rec], "propio")[:40],
        "perfil_reconocer_total": _sumar_perfiles([e.get("perfil") for e in rec], "total")[:40],
        "perfil_congelado_propio": _sumar_perfiles([e.get("perfil") for e in congel], "propio")[:30],
        "perfil_congelado_total": _sumar_perfiles([e.get("perfil") for e in congel], "total")[:30],
    }


def _s(v) -> str:
    return f"{v:.2f} s" if v is not None else "—"


def _tabla(filas, n=25) -> List[str]:
    out = ["| Qué | Veces | Total | Media | Máx |", "|---|---:|---:|---:|---:|"]
    for a in filas[:n]:
        out.append(f"| {a['nombre']} | {a['veces']} | {_s(a['total'])} | {_s(a['media'])} | {_s(a['max'])} |")
    return out


def _funcs(lista, n=20) -> List[str]:
    out = ["| Función | Tiempo |", "|---|---:|"]
    for nombre, v in lista[:n]:
        out.append(f"| `{nombre}` | {_s(v)} |")
    return out


def markdown(r: dict) -> str:
    L = [f"# Rendimiento de la sesión ({r['duracion_s'] / 60:.1f} min)", ""]
    L += ["## Congelamientos de la ventana", "",
          f"{len(r['congelamientos'])} pausas, {_s(r['congelado_total_s'])} en total; "
          f"{r['no_responde']} de 5 s o más («No responde»).", ""]
    for c in r["congelamientos"][:15]:
        donde = c.get("carga") or c.get("etapa") or " › ".join(c.get("bloques") or []) or "—"
        arriba = ", ".join(f"`{n}` {v:.2f}s" for n, v in ((c.get("perfil") or {}).get("propio") or [])[:3])
        L.append(f"- **{_s(c['dur'])}** — {donde}. Arriba de la pila: {arriba or '—'}")
    if r["perfil_congelado_total"]:
        L += ["", "Funciones donde estuvo la ventana trabada (total, incluye lo que llaman):", ""]
        L += _funcs(r["perfil_congelado_total"])
    L += ["", "## Trabajos (procesos aparte)", ""] + _tabla(r["trabajos"])
    L += ["", "Espera en la cola de cada trabajador:", ""] + _tabla(r["espera_cola"], 10)
    if r["perfil_reconocer_propio"]:
        L += ["", "## Reconocimiento: dónde se va el tiempo", "", "Tiempo PROPIO (la función misma):", ""]
        L += _funcs(r["perfil_reconocer_propio"], 30)
        L += ["", "Tiempo TOTAL (con lo que llama):", ""] + _funcs(r["perfil_reconocer_total"], 30)
    L += ["", "## Bloques medidos", ""] + _tabla(r["bloques"], 40)
    L += ["", "## Etapas avisadas", ""] + _tabla(r["etapas"], 40)
    L += ["", "## Esperas con la tarjeta «Cargando…»", ""] + _tabla(r["cargas"])
    if r["acumulados"]:
        L += ["", "## Repetidos (teselas)", ""] + _tabla(r["acumulados"])
    L += ["", "## Procesos", "", "| PID | Nombre | Pico memoria |", "|---:|---|---:|"]
    for p in r["procesos"]:
        pm = p.get("pico_mb")
        L.append(f"| {p['pid']} | {p.get('nombre') or '?'} | {f'{pm:.0f} MB' if pm else '—'} |")
    if r["ram_libre_min_mb"] is not None:
        L += ["", f"RAM libre mínima del equipo: {r['ram_libre_min_mb']:.0f} MB."]
    return "\n".join(L) + "\n"


def comparar(a: dict, b: dict, n: int = 30) -> str:
    """Antes (`a`) y después (`b`): media de cada trabajo, bloque y etapa que aparece en las dos."""
    L = ["# Antes → después", "",
         f"Congelamientos: {len(a['congelamientos'])} ({_s(a['congelado_total_s'])}) → "
         f"{len(b['congelamientos'])} ({_s(b['congelado_total_s'])})", ""]
    for titulo, campo in (("Trabajos", "trabajos"), ("Bloques", "bloques"), ("Etapas", "etapas"),
                          ("Cargas", "cargas")):
        ia = {x["nombre"]: x for x in a[campo]}
        filas = []
        for y in b[campo]:
            x = ia.get(y["nombre"])
            if x is None or not x["media"]:
                continue
            filas.append((y["nombre"], x["media"], y["media"], (y["media"] - x["media"]) / x["media"] * 100))
        if not filas:
            continue
        filas.sort(key=lambda f: -max(f[1], f[2]))
        L += [f"## {titulo}", "", "| Qué | Antes | Después | Cambio |", "|---|---:|---:|---:|"]
        L += [f"| {nm} | {_s(x)} | {_s(y)} | {d:+.0f} % |" for nm, x, y, d in filas[:n]]
        L.append("")
    return "\n".join(L) + "\n"

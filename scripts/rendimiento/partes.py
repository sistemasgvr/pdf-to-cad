"""Tarea 12 del plan 2026-11-16 («reconocimiento desde el editor»): el reconocimiento POR PARTES (interpretar + un ▶
por utilidad → válvulas → diámetros → rótulos, sobre la lectura retenida) da lo MISMO que `reconocer_hoja` de una vez,
y cuánto tarda cada paso.

    python scripts/rendimiento/partes.py plano.pdf 3 --modo viejo --foto viejo.json
    python scripts/rendimiento/partes.py plano.pdf 3 --modo nuevo --foto nuevo.json
    python scripts/rendimiento/partes.py --diff viejo.json nuevo.json        # 0 diferencias = mismo resultado

Cada modo en su PROPIO proceso (las memorias de un camino no aceleran al otro). Zoom 3.5 como la ventana, las 6
utilidades, roles automáticos (lo que deja «Capas de la hoja» sin tocar nada en una hoja con capas).
"""
import argparse
import json
import sys
import time

import comun


def _r(v):
    return round(float(v), 6) if isinstance(v, float) else v


def _plano(o):
    """Cualquier cosa → JSON estable (dataclasses, tuplas, floats redondeados)."""
    import dataclasses
    if dataclasses.is_dataclass(o) and not isinstance(o, type):
        o = dataclasses.asdict(o)
    if isinstance(o, dict):
        return {str(k): _plano(v) for k, v in sorted(o.items(), key=lambda kv: str(kv[0]))}
    if isinstance(o, (list, tuple, set, frozenset)):
        lista = [_plano(v) for v in o]
        return sorted(lista, key=lambda v: json.dumps(v, sort_keys=True)) if isinstance(o, (set, frozenset)) else lista
    if isinstance(o, float):
        return _r(o)
    if isinstance(o, (str, int, bool)) or o is None:
        return o
    return str(o)


def foto(results, anotaciones):
    from reconocer import foto_de
    out = foto_de(results)
    for res in results:                                    # válvulas y grosor completos, no solo cuántas
        u = str(res.utility)
        out[u]["valvulas_det"] = _plano(getattr(res, "valvulas", None) or [])
        out[u]["grosor_det"] = [_plano(getattr(pl, "grosor", None) or {}) for pl in res.polylines]
    out["_anotaciones"] = _plano(anotaciones or [])
    return out


def viejo(pdf, hoja, zoom, utilidades):
    from reconocimiento import recognition_trabajo as RT
    t0 = time.perf_counter()
    res = RT.reconocer_hoja(pdf, hoja, zoom=zoom, utilities=utilidades, roles_by_utility={})
    tiempos = {"reconocer_hoja (todo)": time.perf_counter() - t0}
    anot = next((list(r.anotaciones) for r in res if getattr(r, "anotaciones", None)), [])
    return res, anot, tiempos


def nuevo(pdf, hoja, zoom, utilidades):
    from hoja import interpretar_trabajo as IT
    from reconocimiento import lectura_retenida as LR
    from reconocimiento import recognition_trabajo as RT
    firma = f"partes-{hoja}"
    tiempos = {}
    t0 = time.perf_counter()
    IT.interpretar(pdf, hoja, firma=firma)
    tiempos["interpretar"] = time.perf_counter() - t0
    kw = dict(zoom=zoom, roles_by_utility={})
    res = []
    for u in utilidades:
        t = time.perf_counter()
        res += RT.reconocer_parte(pdf, hoja, u, firma, **kw)
        tiempos[f"▶ {u}"] = time.perf_counter() - t
    t = time.perf_counter()
    salida = RT.reconocer_parte(pdf, hoja, RT.VALVULAS, firma, resultados_previos=res, **kw)
    RT.poner_valvulas(res, salida)
    tiempos["▶ VALVULAS"] = time.perf_counter() - t
    t = time.perf_counter()
    res = RT.reconocer_parte(pdf, hoja, RT.DIAMETROS, firma, resultados_previos=res, **kw)
    tiempos["▶ DIAMETROS"] = time.perf_counter() - t
    t = time.perf_counter()
    anot = RT.reconocer_parte(pdf, hoja, RT.ROTULOS, firma, resultados_previos=res, **kw)["anotaciones"]
    tiempos["▶ ROTULOS"] = time.perf_counter() - t
    tiempos["total"] = time.perf_counter() - t0
    LR.soltar()
    return res, anot, tiempos


def diferencias(a, b, ruta="", out=None, maximo=30):
    out = [] if out is None else out
    if len(out) >= maximo:
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append(f"{ruta}/{k}: solo en {'nuevo' if k not in a else 'viejo'}")
            else:
                diferencias(a[k], b[k], f"{ruta}/{k}", out, maximo)
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            diferencias(x, y, f"{ruta}[{i}]", out, maximo)
    elif a != b:
        out.append(f"{ruta}: {str(a)[:120]} ≠ {str(b)[:120]}")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", nargs="?"); ap.add_argument("hoja", type=int, nargs="?", default=0)
    ap.add_argument("--modo", choices=("viejo", "nuevo"))
    ap.add_argument("--zoom", type=float, default=3.5)
    ap.add_argument("--foto"); ap.add_argument("--diff", nargs=2)
    a = ap.parse_args()
    if a.diff:
        x, y = (json.load(open(p, encoding="utf-8")) for p in a.diff)
        d = diferencias(x["foto"], y["foto"])
        for linea in d:
            print("  ", linea)
        n = sum(len(v["lineas"]) for k, v in x["foto"].items() if not k.startswith("_"))
        print(f"{len(d)} diferencias · {n} líneas · {len(x['foto']['_anotaciones'])} rótulos · "
              f"{sum(len(v['valvulas_det']) for k, v in x['foto'].items() if not k.startswith('_'))} válvulas")
        sys.exit(1 if d else 0)
    comun.preparar()
    from reconocimiento import recognition as rec
    utilidades = tuple(rec.SUPPORTED_UTILITIES)
    res, anot, tiempos = (viejo if a.modo == "viejo" else nuevo)(a.pdf, a.hoja, a.zoom, utilidades)
    for k, v in tiempos.items():
        print(f"{k:28s} {v:7.2f} s")
    if a.foto:
        with open(a.foto, "w", encoding="utf-8") as f:
            json.dump({"tiempos": tiempos, "foto": foto(res, anot)}, f, ensure_ascii=False)


if __name__ == "__main__":
    main()

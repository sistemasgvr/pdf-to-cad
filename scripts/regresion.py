"""regresion.py — regresión automática con «casos dorados».

Reconoce unas hojas conocidas (lista en `gestion/casos_dorados.toml`) y compara el resultado con
la FOTO guardada en `gestion/regresion/fotos/<id>.json`. Así, antes de cada entrega, se ve si algo
que ya funcionaba cambió.

Uso (desde la raíz del repo):
  python scripts/regresion.py                    compara todos los casos con sus fotos
  python scripts/regresion.py --casos a,b        solo esos casos
  python scripts/regresion.py --foto             (re)guarda la foto de todos los casos
  python scripts/regresion.py --foto a b         (re)guarda la foto de esos casos

Sale con 0 si no hay diferencias (y no faltó nada) y con 1 si hay. Escribe además
`gestion/regresion/ultimo_informe.md`.

Carpeta de los PDF: variable de entorno PDFCAD_DORADOS o `[config] carpeta` del toml. Un
`archivo` que empieza con «@repo/» se busca dentro del repositorio (p. ej. tests/fixtures).

La foto NO guarda geometría completa: por caso × hoja × utilidad guarda conteos, largo, huella de
cada polilínea (vértices redondeados a 0.1 pt), tipos de vértice, codos, bóvedas, diámetros y
avisos. Es pequeña, legible en un diff de Git y suficiente para notar cualquier cambio.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
for _p in (str(RAIZ / "app"), str(RAIZ)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

TOML = RAIZ / "gestion" / "casos_dorados.toml"
FOTOS = RAIZ / "gestion" / "regresion" / "fotos"
INFORME = RAIZ / "gestion" / "regresion" / "ultimo_informe.md"

UTILIDADES = ("ELECTRICO", "DRENAJE", "AGUA", "ALCANTARILLADO", "GAS", "TELECOM")
CAMPOS_CASO = ("id", "archivo", "hojas", "utilidades", "zoom", "descripcion")
VERSION_FOTO = 1
DEC_PT = 1          # vértices redondeados a 0.1 pt


# ── configuración ────────────────────────────────────────────────────────────

def leer_config(ruta: Path = TOML) -> dict:
    import tomllib
    with open(ruta, "rb") as f:
        return tomllib.load(f)


def validar_config(cfg: dict) -> list[str]:
    """Problemas del toml (lista vacía = bien)."""
    errores = []
    casos = cfg.get("caso")
    if not isinstance(casos, list) or not casos:
        return ["no hay ningún [[caso]]"]
    vistos = set()
    for i, c in enumerate(casos):
        nombre = c.get("id", f"#{i + 1}")
        for campo in CAMPOS_CASO:
            if campo not in c:
                errores.append(f"{nombre}: falta «{campo}»")
        if nombre in vistos:
            errores.append(f"{nombre}: id repetido")
        vistos.add(nombre)
        hojas = c.get("hojas", [])
        if not isinstance(hojas, list) or not hojas or not all(isinstance(h, int) and h >= 0 for h in hojas):
            errores.append(f"{nombre}: «hojas» debe ser una lista de enteros ≥ 0")
        utils = c.get("utilidades", [])
        if not isinstance(utils, list) or not utils:
            errores.append(f"{nombre}: «utilidades» vacía")
        else:
            for u in utils:
                if u not in UTILIDADES:
                    errores.append(f"{nombre}: utilidad desconocida «{u}»")
        z = c.get("zoom")
        if not isinstance(z, (int, float)) or z <= 0:
            errores.append(f"{nombre}: «zoom» debe ser un número > 0")
        if isinstance(c.get("archivo"), str) and os.path.isabs(c["archivo"]):
            errores.append(f"{nombre}: «archivo» debe ser relativo a la carpeta dorada")
    return errores


def carpeta_dorada(cfg: dict) -> Path:
    return Path(os.environ.get("PDFCAD_DORADOS") or cfg.get("config", {}).get("carpeta", ""))


def ruta_pdf(cfg: dict, caso: dict) -> Path:
    archivo = caso["archivo"]
    if archivo.startswith("@repo/"):
        return RAIZ / archivo[len("@repo/"):]
    return carpeta_dorada(cfg) / archivo


# ── foto ─────────────────────────────────────────────────────────────────────

def _sha1(ruta: Path) -> str:
    h = hashlib.sha1()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def _huella_polilinea(pl, zoom: float) -> str:
    """Huella de UNA polilínea: vértices en pt redondeados, en el sentido «menor» (no depende del
    sentido en que salió) + sus tipos de vértice + si es abandonada."""
    pts = [(round(x / zoom, DEC_PT), round(y / zoom, DEC_PT)) for x, y in pl.pts_pdf]
    kinds = list(pl.kinds or [])
    if list(reversed(pts)) < pts:
        pts, kinds = list(reversed(pts)), list(reversed(kinds))
    texto = json.dumps([pts, kinds, bool(pl.abandoned), pl.layer_ocg or ""])
    return hashlib.blake2b(texto.encode(), digest_size=5).hexdigest()


def _largo(pts) -> float:
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def _clave_aviso(texto: str, utilidad: str) -> str:
    from reconocimiento import recognition_summary as RS
    n = RS.classify_warning(texto, utilidad)
    return n.key or re.sub(r"\d+(?:[.,]\d+)?", "N", n.label)


def foto_utilidad(res, zoom: float) -> dict:
    lineas = res.drawable
    kinds = Counter(k for pl in lineas for k in (pl.kinds or []))
    radios = sorted(round(f.get("r_px", 0.0) / zoom, DEC_PT) for pl in lineas for f in (pl.fillets or {}).values())
    diam = Counter("sin dato" if pl.diam_in is None else f'{pl.diam_in:g}"' for pl in lineas)
    estados = Counter((pl.grosor or {}).get("estado", "—") for pl in lineas)
    bovedas = list(res.vaults_geo or [])
    return {
        "polilineas": len(lineas),
        "abandonadas": sum(1 for pl in lineas if pl.abandoned),
        "vertices": sum(len(pl.pts_pdf) for pl in lineas),
        "largo_pt": round(sum(_largo(pl.pts_pdf) for pl in lineas) / zoom, 1),
        "huellas": sorted(_huella_polilinea(pl, zoom) for pl in lineas),
        "kinds": dict(sorted(kinds.items())),
        "codos": len(radios),
        "radios_pt": radios,
        "codos_aproximados": sum(1 for pl in lineas for f in (pl.fillets or {}).values() if f.get("loose")),
        "bovedas": len(bovedas),
        "bovedas_importables": sum(1 for v in bovedas if v.get("importable")),
        "diametros": dict(sorted(diam.items())),
        "grosor_estados": dict(sorted(estados.items())),
        "cobertura": round(float(res.coverage or 0.0), 4),
        "avisos": sorted(_clave_aviso(w, res.utility) for w in (res.warnings or [])),
        "avisos_texto": sorted(res.warnings or []),
    }


def reconocer_caso(cfg: dict, caso: dict) -> dict:
    from reconocimiento.recognition_trabajo import reconocer_hoja
    pdf = ruta_pdf(cfg, caso)
    zoom = float(caso["zoom"])
    hojas = {}
    for h in caso["hojas"]:
        results = reconocer_hoja(str(pdf), h, zoom=zoom, utilities=tuple(caso["utilidades"]))
        por_u = {r.utility: foto_utilidad(r, zoom) for r in results}
        hojas[str(h)] = {
            "utilidades": por_u,
            "valvulas": len(results[0].valvulas or []) if results else 0,
            "anotaciones": len(results[0].anotaciones or []) if results else 0,
        }
    return {"version": VERSION_FOTO, "id": caso["id"], "archivo": caso["archivo"], "sha1": _sha1(pdf),
            "zoom": zoom, "utilidades": list(caso["utilidades"]), "hojas": hojas}


# ── comparación ──────────────────────────────────────────────────────────────

_NOMBRES = {
    "polilineas": "polilíneas", "abandonadas": "abandonadas", "vertices": "vértices",
    "largo_pt": "largo (pt)", "codos": "codos", "codos_aproximados": "codos aproximados",
    "bovedas": "bóvedas", "bovedas_importables": "bóvedas importables", "cobertura": "cobertura",
}
_ESCALARES = tuple(_NOMBRES)
_TOL = {"largo_pt": 0.05, "cobertura": 0.00005}


def _dif_conteo(nombre: str, a: dict, b: dict) -> str | None:
    if a == b:
        return None
    partes = []
    for k in sorted(set(a) | set(b)):
        va, vb = a.get(k, 0), b.get(k, 0)
        if va != vb:
            partes.append(f"{k} {va} → {vb}")
    return f"{nombre}: " + ", ".join(partes)


def _dif_listas(nombre: str, a: list, b: list, mostrar: bool = True) -> str | None:
    ca, cb = Counter(a), Counter(b)
    if ca == cb:
        return None
    quitados = list((ca - cb).elements())
    nuevos = list((cb - ca).elements())
    if not mostrar:
        return f"{nombre}: {len(quitados)} ya no están, {len(nuevos)} nuevas"
    texto = []
    if quitados:
        texto.append("faltan " + ", ".join(map(str, quitados[:8])) + (" …" if len(quitados) > 8 else ""))
    if nuevos:
        texto.append("nuevos " + ", ".join(map(str, nuevos[:8])) + (" …" if len(nuevos) > 8 else ""))
    return f"{nombre}: " + "; ".join(texto)


def comparar_utilidad(a: dict, b: dict) -> list[str]:
    """Diferencias legibles entre la foto guardada `a` y la nueva `b` de una utilidad."""
    out = []
    escalares = []
    for k in _ESCALARES:
        va, vb = a.get(k), b.get(k)
        if va == vb:
            continue
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)) and abs(va - vb) <= _TOL.get(k, 0):
            continue
        escalares.append(f"{_NOMBRES[k]} {va} → {vb}")
    if escalares:
        out.append(", ".join(escalares))
    d = _dif_listas("polilíneas con vértices distintos", a.get("huellas", []), b.get("huellas", []), mostrar=False)
    if d:
        out.append(d)
    for clave, nombre in (("kinds", "tipos de vértice"), ("diametros", "diámetros"),
                          ("grosor_estados", "estado del diámetro")):
        d = _dif_conteo(nombre, a.get(clave, {}), b.get(clave, {}))
        if d:
            out.append(d)
    d = _dif_listas("radios de codos (pt)", a.get("radios_pt", []), b.get("radios_pt", []))
    if d:
        out.append(d)
    d = _dif_listas("avisos", a.get("avisos", []), b.get("avisos", []))
    if d:
        out.append(d)
    elif sorted(a.get("avisos_texto", [])) != sorted(b.get("avisos_texto", [])):
        out.append("avisos: mismos tipos, cambia su texto/cifras")
    return out


def comparar_foto(vieja: dict, nueva: dict) -> list[str]:
    """Lista de líneas legibles con lo que cambió (vacía = igual)."""
    out = []
    if vieja.get("sha1") != nueva.get("sha1"):
        out.append("OJO: el PDF no es el mismo de la foto (sha1 distinto)")
    if vieja.get("zoom") != nueva.get("zoom"):
        out.append(f"zoom {vieja.get('zoom')} → {nueva.get('zoom')}")
    hv, hn = vieja.get("hojas", {}), nueva.get("hojas", {})
    for h in sorted(set(hv) | set(hn), key=int):
        hh = f"h.{int(h) + 1}"                      # como se nombran las hojas en el proyecto (1-based)
        if h not in hv:
            out.append(f"{hh}: nueva (sin foto)")
            continue
        if h not in hn:
            out.append(f"{hh}: ya no se reconoce")
            continue
        uv, un = hv[h].get("utilidades", {}), hn[h].get("utilidades", {})
        for u in sorted(set(uv) | set(un)):
            if u not in uv:
                out.append(f"{hh} · {u}: nueva (sin foto)")
            elif u not in un:
                out.append(f"{hh} · {u}: ya no se reconoce")
            else:
                for linea in comparar_utilidad(uv[u], un[u]):
                    out.append(f"{hh} · {u}: {linea}")
        for k, nombre in (("valvulas", "válvulas"), ("anotaciones", "rótulos del plano")):
            if hv[h].get(k) != hn[h].get(k):
                out.append(f"{hh}: {nombre} {hv[h].get(k)} → {hn[h].get(k)}")
    return out


# ── principal ────────────────────────────────────────────────────────────────

def _preparar_entorno():
    os.environ["PDFCAD_PROCESO"] = "0"
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")


def _guardar(foto: dict):
    FOTOS.mkdir(parents=True, exist_ok=True)
    with open(FOTOS / f"{foto['id']}.json", "w", encoding="utf-8") as f:
        json.dump(foto, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")


def _resumen_hoja(foto: dict) -> str:
    partes = []
    for h, d in foto["hojas"].items():
        n = sum(u["polilineas"] for u in d["utilidades"].values())
        c = sum(u["codos"] for u in d["utilidades"].values())
        partes.append(f"h.{int(h) + 1}: {n} líneas, {c} codos")
    return "; ".join(partes)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Regresión con casos dorados")
    ap.add_argument("--foto", nargs="*", metavar="ID", help="(re)guardar la foto (todos o esos ids)")
    ap.add_argument("--casos", help="ids separados por coma")
    args = ap.parse_args(argv)
    _preparar_entorno()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                               # noqa: BLE001
        pass

    cfg = leer_config()
    errores = validar_config(cfg)
    if errores:
        print("El toml tiene problemas:\n  " + "\n  ".join(errores))
        return 1
    casos = cfg["caso"]
    filtro = set()
    if args.casos:
        filtro |= {s.strip() for s in args.casos.split(",") if s.strip()}
    if args.foto:
        filtro |= set(args.foto)
    if filtro:
        desconocidos = filtro - {c["id"] for c in casos}
        if desconocidos:
            print("Casos desconocidos: " + ", ".join(sorted(desconocidos)))
            return 1
        casos = [c for c in casos if c["id"] in filtro]
    modo_foto = args.foto is not None

    print(f"Carpeta dorada: {carpeta_dorada(cfg)}")
    lineas_md = [f"# Regresión — {time.strftime('%Y-%m-%d %H:%M')}", "",
                 f"Modo: {'guardar fotos' if modo_foto else 'comparar'} · carpeta: `{carpeta_dorada(cfg)}`", ""]
    resumen = {"iguales": [], "distintos": [], "faltan": [], "sin_foto": [], "errores": []}
    total0 = time.perf_counter()
    for caso in casos:
        cid = caso["id"]
        pdf = ruta_pdf(cfg, caso)
        if not pdf.is_file():
            print(f"[FALTA]   {cid}: no está {pdf}")
            resumen["faltan"].append(cid)
            lineas_md.append(f"## {cid} — FALTA el PDF\n\n`{pdf}`\n")
            continue
        t0 = time.perf_counter()
        try:
            nueva = reconocer_caso(cfg, caso)
        except Exception as e:                      # noqa: BLE001
            print(f"[ERROR]   {cid}: {type(e).__name__}: {e}")
            resumen["errores"].append(cid)
            lineas_md.append(f"## {cid} — ERROR\n\n`{type(e).__name__}: {e}`\n")
            continue
        seg = time.perf_counter() - t0
        if modo_foto:
            _guardar(nueva)
            print(f"[FOTO]    {cid} ({seg:.1f} s): {_resumen_hoja(nueva)}")
            resumen["iguales"].append(cid)
            lineas_md.append(f"## {cid} — foto guardada ({seg:.1f} s)\n\n{_resumen_hoja(nueva)}\n")
            continue
        ruta_foto = FOTOS / f"{cid}.json"
        if not ruta_foto.is_file():
            print(f"[SIN FOTO] {cid} ({seg:.1f} s): corre --foto {cid}")
            resumen["sin_foto"].append(cid)
            lineas_md.append(f"## {cid} — sin foto ({seg:.1f} s)\n")
            continue
        with open(ruta_foto, encoding="utf-8") as f:
            vieja = json.load(f)
        difs = comparar_foto(vieja, nueva)
        if difs:
            print(f"[CAMBIÓ]  {cid} ({seg:.1f} s)")
            for d in difs:
                print(f"            {d}")
            resumen["distintos"].append(cid)
            lineas_md.append(f"## {cid} — CAMBIÓ ({seg:.1f} s)\n\n_{caso['descripcion']}_\n")
            lineas_md += [f"- {d}" for d in difs] + [""]
        else:
            print(f"[IGUAL]   {cid} ({seg:.1f} s)")
            resumen["iguales"].append(cid)
            lineas_md.append(f"## {cid} — igual ({seg:.1f} s)\n")

    total = time.perf_counter() - total0
    texto = (f"Resumen: {len(resumen['iguales'])} {'guardados' if modo_foto else 'iguales'}, "
             f"{len(resumen['distintos'])} con cambios, {len(resumen['faltan'])} sin PDF, "
             f"{len(resumen['sin_foto'])} sin foto, {len(resumen['errores'])} con error · {total:.0f} s")
    print("\n" + texto)
    for k, nombre in (("distintos", "Con cambios"), ("faltan", "Sin PDF"), ("sin_foto", "Sin foto"),
                      ("errores", "Con error")):
        if resumen[k]:
            print(f"  {nombre}: {', '.join(resumen[k])}")
    lineas_md[3:3] = [f"**{texto}**", ""]
    INFORME.parent.mkdir(parents=True, exist_ok=True)
    INFORME.write_text("\n".join(lineas_md) + "\n", encoding="utf-8")
    hay_problema = resumen["distintos"] or resumen["faltan"] or resumen["sin_foto"] or resumen["errores"]
    return 1 if hay_problema else 0


if __name__ == "__main__":
    sys.exit(main())

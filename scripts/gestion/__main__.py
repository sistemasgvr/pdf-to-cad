"""Gestión del proyecto (2026-11-11). Uso:  python scripts/gestion <comando>

  admin                      Vista de administrador (local): aprobar, estados, versiones, reporte, publicar
  validar                    Revisa funciones.toml, versiones y fichas
  generar                    Arma el sitio del cliente en gestion/_salida/publico (sin subir)
  publicar                   Arma y sube el sitio a Cloudflare Pages
  reporte <versión>          PDF + texto de WhatsApp de una entrega (gestion/_salida/reportes)
  drawio [versión]           Exporta el diagrama a .drawio (general o solo esa versión)
  nueva-version <versión>    Crea gestion/versiones/<versión>.toml para llenar
  humo <versión>             Copia la lista de humo a gestion/entregas/<versión>/humo.md
  proponer <id> <estado> --por NOMBRE [--nota TEXTO]
                             Propone el estado de una función o ficha (no lo aprueba)
  ficha <area>/<tipo>/<id> --nombre NOMBRE --por NOMBRE
                             Crea la carpeta y la ficha de una pieza del catálogo
  etiquetas                  Crea las etiquetas de GitHub Issues (necesita GITHUB_TOKEN)
"""
import argparse
import datetime
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

import datos as D  # noqa: E402


def _proponer(a):
    pr = D.leer()
    if a.estado not in D.ESTADOS or not a.estado:
        raise SystemExit(f"Estado inválido. Usa uno de: {', '.join(e for e in D.ORDEN_ESTADOS if e)}")
    it = next((f for f in pr.funciones if f.id == a.id), None)
    if it is None:
        it = next((fi for fi in pr.fichas if fi.id == a.id), None)
        if it is None:
            raise SystemExit(f"No existe la función ni la ficha «{a.id}»")
        it.propuesto, it.propuesto_por, it.propuesto_nota = a.estado, a.por, a.nota or ""
        D.guardar_ficha(it)
    else:
        it.propuesto, it.propuesto_por, it.propuesto_nota = a.estado, a.por, a.nota or ""
        D.guardar_funciones(pr)
    print(f"Propuesto «{it.nombre}» → {D.ESTADOS[a.estado][0]} (queda por revisar del administrador)")


def _ficha(a):
    carpeta = D.ruta("catalogo", *a.ruta.split("/"))
    if os.path.exists(os.path.join(carpeta, "ficha.toml")):
        raise SystemExit(f"Ya existe {carpeta}")
    os.makedirs(carpeta, exist_ok=True)
    partes = a.ruta.split("/")
    fi = D.Ficha(carpeta=carpeta, nombre=a.nombre, area=partes[0], tipo=partes[1] if len(partes) > 2 else "",
                 responsable=a.por, propuesto="en_desarrollo", propuesto_por=a.por)
    D.guardar_ficha(fi)
    print(f"Ficha creada: {carpeta}\\ficha.toml  (agrega las capturas .png en esa carpeta)")


def _nueva_version(numero):
    path = D.ruta("versiones", f"{numero}.toml")
    if os.path.exists(path):
        raise SystemExit(f"Ya existe {path}")
    v = D.Version(archivo=path, numero=numero, fecha=datetime.date.today().isoformat(),
                  novedades=[dict(tipo="nuevo", titulo="", detalle="", funciones=[], observacion="")],
                  pendientes=[dict(titulo="", detalle="")])
    D.guardar_version(v)
    print(f"Creada {path}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="gestion", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("admin"); s.add_argument("--puerto", type=int, default=8765); s.add_argument("--sin-abrir", action="store_true")
    sub.add_parser("validar"); sub.add_parser("generar"); sub.add_parser("publicar"); sub.add_parser("etiquetas")
    s = sub.add_parser("reporte"); s.add_argument("version")
    s = sub.add_parser("drawio"); s.add_argument("version", nargs="?")
    s = sub.add_parser("nueva-version"); s.add_argument("version")
    s = sub.add_parser("humo"); s.add_argument("version")
    s = sub.add_parser("proponer"); s.add_argument("id"); s.add_argument("estado")
    s.add_argument("--por", required=True); s.add_argument("--nota")
    s = sub.add_parser("ficha"); s.add_argument("ruta"); s.add_argument("--nombre", required=True)
    s.add_argument("--por", required=True)
    a = p.parse_args(argv)

    if a.cmd == "admin":
        import admin
        admin.servir(a.puerto, abrir=not a.sin_abrir)
    elif a.cmd == "validar":
        errores = D.validar(D.leer())
        print("\n".join(errores) if errores else "OK: sin problemas.")
        return 1 if errores else 0
    elif a.cmd == "generar":
        import publicar
        print("Sitio en", publicar.PUBLICO(), "→", ", ".join(publicar.construir()))
    elif a.cmd == "publicar":
        import publicar
        ok, _ = publicar.publicar()
        return 0 if ok else 1
    elif a.cmd == "reporte":
        import reporte
        print("\n".join(reporte.generar(a.version)))
    elif a.cmd == "drawio":
        import drawio
        os.makedirs(D.ruta("_salida"), exist_ok=True)
        destino = D.ruta("_salida", f"funciones{'-' + a.version if a.version else ''}.drawio")
        drawio.exportar(D.leer(), destino, a.version)
        print(destino)
    elif a.cmd == "nueva-version":
        _nueva_version(a.version)
    elif a.cmd == "humo":
        dst = D.ruta("entregas", a.version, "humo.md")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.exists(dst):
            raise SystemExit(f"Ya existe {dst}")
        with open(D.ruta("lista_humo.md"), encoding="utf-8") as f:
            texto = f.read()
        cab = (f"# Prueba de humo · versión {a.version}\n\nFecha: {datetime.date.today().isoformat()} · "
               "Probó: ______ · Instalador probado: ______\n\n")
        with open(dst, "w", encoding="utf-8") as f:
            f.write(cab + texto.split("\n", 1)[1])
        print(dst)
    elif a.cmd == "proponer":
        _proponer(a)
    elif a.cmd == "ficha":
        _ficha(a)
    elif a.cmd == "etiquetas":
        import github
        github.crear_etiquetas()
    return 0


if __name__ == "__main__":
    sys.exit(main())

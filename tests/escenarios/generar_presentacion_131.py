"""Genera `presentacion_1_3_1.digproj`: lienzo en blanco para PRESENTAR la versión 1.3.1.

  Filas 1–5 (N01–N54)  cada regla del Excel de normativas `normativas_1_3_1.xlsx` (el v4 del
                       ingeniero: rangos en columnas MIN/MAX, listas y RADIO CURVA FIJO),
                       el caso que cumple, el del borde y el que no. Casos en
                       `presentacion_131_casos.py`.
  Filas 6–7 (X01–X13)  las otras novedades que se ven sin PDF: editar en bloque, copiar y
                       pegar propiedades (con COTAS, 1.3.1), unir utilidades, la revisión antes
                       de exportar, choques, bancoducto en dos utilidades, sólido y diámetro
                       por defecto.

Cada celda dice qué hoja del Excel prueba, la regla en palabras simples y qué aviso debe
salir. Las normativas SE LEEN DEL EXCEL `normativas_1_3_1.xlsx` (una copia del v3 del
ingeniero): el proyecto no guarda normativas, así que para presentarlo primero hay que
importar ese Excel en la app (Normativas → Normativas de diseño → «Importar Excel…»).

Uso:
    python tests/escenarios/generar_presentacion_131.py   # regenera el .digproj
    pytest tests/escenarios/test_presentacion_131.py       # valida lo esperado

Se construye con el código REAL de la app (Main sin ventana), como los demás escenarios.
"""
import copy
import os
import sys
import textwrap

_AQUI = os.path.dirname(os.path.abspath(__file__))
_RAIZ = os.path.dirname(os.path.dirname(_AQUI))
for _p in (os.path.join(_AQUI, "cruces"), os.path.join(_RAIZ, "app"), _RAIZ):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from generar_escenarios import Lienzo, pol  # noqa: E402
from presentacion_131_casos import CASOS_N, DP, L, recta  # noqa: E402

SALIDA = os.path.join(_AQUI, "presentacion_1_3_1.digproj")
EXCEL = os.path.join(_AQUI, "normativas_1_3_1.xlsx")

# ARCH E apaisada (48 × 36 in) a 1" = 60' → 2880 × 2160 pies.
HOJA = dict(name="ARCH E", w_pt=48 * 72.0, h_pt=36 * 72.0, ft_per_inch=60.0,
            scale_ft_per_pt=60.0 / 72.0, unit="in", landscape=True)
ANCHO_FT, ALTO_FT = 48 * 60.0, 36 * 60.0
TITULO_FT = 90.0                              # franja de arriba con el título
COLS, FILAS = 12, 7
CELDA_X, CELDA_Y = ANCHO_FT / COLS, (ALTO_FT - TITULO_FT) / FILAS     # 240 × 295.7 ft
FILAS_N = 5                                   # filas de normativas; las X empiezan en la 6.ª
ALTO_TEXTO = 6.0
ANCHO_ETIQUETA = 52

TITULO = (
    "PDF a CAD 1.3.1 · Normativas del Excel corregido (rangos MIN/MAX y radio de curva) y novedades\n"
    "ANTES DE MIRAR: importa tests/escenarios/normativas_1_3_1.xlsx (Normativas → Normativas de diseño → "
    "«Importar Excel…»). Los avisos dependen de las normativas cargadas.\n"
    "Filas 1-5 (N01-N54): una regla del Excel por celda: el caso que cumple, el del borde del rango y el que no. "
    "Filas 6-7 (X01-X13): otras novedades.\n"
    "Avisos: circulito ámbar «!» en el lugar (celeste «i» = solo información), etiqueta del accesorio en ámbar y "
    "«N avisos de normativa» en la barra de estado (clic = lista; ahí también se APRUEBAN). «Sin tipo» no se "
    "dibuja: se ve en el panel y en la lista.")


# ─────────────────────────── utilidades con tamaño de catálogo ───────────────────────────
# El diámetro que miran las normativas es el del TAMAÑO elegido (`model_ops.diametro`):
# sin `pipe_size` vale 12" (por defecto). Se busca una familia del catálogo de Civil 3D
# instalado que tenga ese tamaño, para que el panel lo muestre; sin catálogo queda solo
# el tamaño (las normativas lo leen igual).
_PREFERIDAS = {"pressure": ("C115", "C901", "C900"),
               "conduit": ("Pvc", "DIPipe", "HDPE"), "gravity": ("Pvc", "Concrete")}


def _familias(win, kind):
    from catalogo import civil_catalog as cc
    try:
        fams = cc.pressure_pipes(win.civil_year) if kind == "pressure" else cc.imperial_pipes(win.civil_year)
    except Exception:
        return []
    out = []
    for f in fams:
        try:
            tam = (cc.pressure_pipe_sizes(win.civil_year, f["id"]) if kind == "pressure"
                   else cc.pipe_sizes(win.civil_year, f["id"]))
        except Exception:
            tam = []
        out.append((f["id"], tam))
    pref = _PREFERIDAS.get(kind, ())
    return sorted(out, key=lambda f: next((k for k, p in enumerate(pref) if p.lower() in f[0].lower()), 99))


class Dibujo(Lienzo):
    def __init__(self, win):
        super().__init__(win)
        self._fams = {}

    def familia_con(self, capa, diam):
        from nucleo.model import network_kind
        kind = network_kind(capa)
        if kind not in self._fams:
            self._fams[kind] = _familias(self.w, kind)
        tam = f"{diam:g} in"
        return next((fid for fid, tams in self._fams[kind] if tam in tams), ""), tam

    def util(self, capa, pts, diam=None, tipo="", amp=None, inv=(-4.0, -4.0), **extra):
        """Utilidad con tipo, amperaje y TAMAÑO de catálogo (`diam` None = por defecto)."""
        if diam is not None:
            fid, tam = self.familia_con(capa, diam)
            extra.update(pipe_family=fid, pipe_size=tam)
        i = self.tubo(capa, pts, diam if diam is not None else 12.0, inv, **extra)
        p = self.w.pipes[i]
        if tipo:
            p["tipo"] = tipo
        if amp is not None:
            p["amperaje"] = float(amp)
        return i


# ─────────────────────────── otras novedades (X) ───────────────────────────
# (código, título, cómo mostrarlo, función, avisos de normativa, revisión antes de exportar)
# Revisión = [(tipo de `limpieza`, arreglado)]. Telecom lleva tipo DP: en el Excel 1.3.1
# telecom tiene tipos y sin tipo saldría «Sin tipo» en cada línea.

def tel(dz, pts, **k):
    return dz.util("TELECOM", pts, 4, DP, **k)


def tel_recta(dz, P, largo=120, **k):
    return tel(dz, [(P[0] - largo / 2, P[1]), (P[0] + largo / 2, P[1])], **k)


def x_bloque(dz, P):
    for k in range(4):
        recta(dz, "ELECTRICO", (P[0], P[1] + 30 - 20 * k), 4, largo=120)


def x_copiar(dz, P):
    recta(dz, "AGUA", (P[0], P[1] + 30), 8, DP, largo=120, name="Fuente", inv=(-5.5, -7.25))
    for k in range(2):
        recta(dz, "AGUA", (P[0], P[1] - 10 - 25 * k), 12, largo=120)


def x_unir(dz, P):
    a, b, c, d = (P[0] - 90, P[1]), (P[0] - 30, P[1]), (P[0] + 30, P[1] + 12), (P[0] + 90, P[1] + 12)
    for u, v in ((a, b), (b, c), (c, d)):
        dz.util("DRENAJE", [u, v], 18, inv=(-6.0, -6.2))


def x_punta(dz, P):
    tel_recta(dz, P)
    tel(dz, [(P[0], P[1] - 0.5), (P[0], P[1] - L)])


def x_corta(dz, P):
    tel_recta(dz, P)
    tel(dz, [(P[0] + 60, P[1]), (P[0] + 60.6, P[1])])


def x_repetida(dz, P):
    tel_recta(dz, P)
    tel_recta(dz, P)


def x_suelta(dz, P):
    tel_recta(dz, (P[0], P[1] + 20))
    tel(dz, [(P[0] - 1.5, P[1] - 30), (P[0] + 1.5, P[1] - 30)])


def x_quiebres(dz, P):
    b = pol(P, 30, 0.3)
    tel(dz, [(P[0] - L, P[1]), P, b, (b[0] + L, b[1])])


def x_curva_t(dz, P):
    x0 = P[0] - 30
    tel(dz, [(x0, P[1] - 50), (x0, P[1] + 50)])
    esquina = (x0 + 30.0, P[1])
    tel(dz, [(x0, P[1]), esquina, (esquina[0], P[1] + 50)])
    ex, ey = dz.px(*esquina)
    dz.w.structures.append({"cod": "", "x": ex, "y": ey, "curve": True, "radius_ft": 29.9,
                            "net": "conduit", "world": False, "hidden": False, "rim": None,
                            "sump": None, "part": "", "part_size": "", "covered": True})


def x_choque(dz, P):
    tel_recta(dz, P, inv=(-6.0, -6.0))
    dz.util("DRENAJE", [(P[0], P[1] - 50), (P[0], P[1] + 50)], 18, inv=(-6.0, -6.0))


def x_bancoducto(dz, P):
    from nucleo.duct_bank import Conduit, DuctBank
    a = tel_recta(dz, (P[0], P[1] + 15))
    b = tel_recta(dz, (P[0], P[1] - 25))
    db = DuctBank(name="DB-PRESENTACION", width_in=24.0, height_in=16.0,
                  conduits=[Conduit(7.0, 8.0, 4.0, "T1"), Conduit(17.0, 8.0, 4.0, "T2")])
    db.assign([a, b])
    dz.w.duct_banks.append(db)


def x_solido(dz, P):
    fin = (P[0] + 40, P[1])
    tel(dz, [(P[0] - 70, P[1]), fin])
    largo, ancho = 10.0, 6.0
    esquinas = [(fin[0] - largo / 2, fin[1] - ancho / 2), (fin[0] + largo / 2, fin[1] - ancho / 2),
                (fin[0] + largo / 2, fin[1] + ancho / 2), (fin[0] - largo / 2, fin[1] + ancho / 2)]
    cx, cy = dz.px(*fin)
    dz.w.structures.append({"cod": "", "x": cx, "y": cy, "net": "conduit", "shape": "rect",
                            "outline": [dz.px(*q) for q in esquinas], "width_ft": ancho,
                            "length_ft": largo, "rot_deg": 0.0, "world": False, "hidden": False,
                            "rim": None, "sump": None, "part": "", "part_size": "", "covered": True})


def x_defecto(dz, P):
    recta(dz, "AGUA", P, None, DP, largo=120)


CASOS_X = [
    ("X01", "Editar en bloque (4 eléctricas sin tipo)",
     "Ctrl+clic en las 4 → Ctrl+E → Tipo = DISTRIBUCION PRINCIPAL: se van los 4 avisos «Sin tipo». "
     "Ctrl+Z lo deshace.", x_bloque, ["tipo"] * 4, []),
    ("X02", "Copiar y pegar propiedades (con cotas, 1.3.1)",
     "Selecciona «Fuente» (DP Ø8\", rasantes -5.5 / -7.25) → Ctrl+Shift+C; selecciona las otras dos → "
     "Ctrl+Shift+V: con «Pegar también las cotas» marcada pasan tipo, tamaño Y rasantes.",
     x_copiar, ["tipo"] * 2, []),
    ("X03", "Unir utilidades (3 tramos de drenaje)",
     "Ctrl+clic en los 3 tramos → Ctrl+J: queda UNA utilidad (vista previa verde).", x_unir, [], []),
    ("X04", "Punta que casi toca otra línea (0.5 ft)",
     "Exportar DXF → «Antes de exportar»: «líneas que casi tocan a otra: se unirán».", x_punta, [],
     [("punta", True)]),
    ("X05", "Utilidad de 0.6 ft", "Antes de exportar: «utilidades muy cortas: se borrarán».", x_corta, [],
     [("corta", True)]),
    ("X06", "Utilidad repetida (dos iguales)", "Antes de exportar: «utilidades repetidas: se borrará una».",
     x_repetida, [], [("duplicada", True)]),
    ("X07", "Utilidad suelta de 3 ft", "Herramientas → Revisar y limpiar el dibujo: solo AVISO (no se toca).",
     x_suelta, [], [("suelta", False)]),
    ("X08", "Tramo de 0.3 ft entre dos quiebres",
     "En Civil 3D sería una tubería diminuta: el DXF sale SIEMPRE sin ella (se quita un vértice).",
     x_quiebres, [], [("tramo", True)]),
    ("X09", "Curva que llega a 0.1 ft de la T",
     "Tubería diminuta entre la T y la curva: la curva se estira hasta la T (r 29.9 → 30 ft).",
     x_curva_t, [], [("tramo", True)]),
    ("X10", "Telecom × drenaje a la misma cota", "Alerta roja «Tuberías que chocan» con su número C-1.",
     x_choque, [], []),
    ("X11", "Un bancoducto en DOS utilidades",
     "Selecciona una: el panel dice su bancoducto; en el DXF va un PDFCAD_DUCTBANK por utilidad.",
     x_bancoducto, [], []),
    ("X12", "Sólido al final de una línea de telecom",
     "Buzones → SÓLIDO-1: Largo/Ancho/Altura y Cota superior automática (el eje llega al centro).",
     x_solido, [], []),
    ("X13", "Agua DP sin tamaño elegido", "Panel: Diámetro 12\" (Por defecto); 12\" está en DP: sin aviso.",
     x_defecto, [], []),
]


# ─────────────────────────── armado ───────────────────────────

def centro(i):
    col, fila = i % COLS, i // COLS
    return (col * CELDA_X + CELDA_X / 2, ALTO_FT - TITULO_FT - (fila * CELDA_Y + CELDA_Y / 2) - 45)


def _etiqueta(dz, P, lineas):
    x0, y0 = P[0] - CELDA_X / 2 + 6, P[1] + 128           # justo encima del dibujo (llega a +60)
    dz.texto((x0, y0), "\n".join(lineas), ALTO_TEXTO)


def _lineas(cod, titulo, partes):
    out = textwrap.wrap(f"{cod} · {titulo}", ANCHO_ETIQUETA)
    for p in partes:
        out += textwrap.wrap(p, ANCHO_ETIQUETA, subsequent_indent="   ")
    return out


def normativas():
    """El catálogo de `normativas_1_3_1.xlsx` (error si alguna celda no se entiende)."""
    from nucleo import normas_excel
    problemas = []
    cat, faltan = normas_excel.importar(EXCEL, problemas)
    assert not faltan and not problemas, (faltan, problemas)
    return cat


def construir(win):
    """Dibuja todos los casos en `win`. Devuelve {código: dict(P, pipes, avisos, revision)}."""
    win.blank_canvas = True
    win.paper = dict(HOJA)
    win._load_blank_page(HOJA)
    dz = Dibujo(win)
    dz.texto((10, ALTO_FT - 8), TITULO, 9.0)
    datos = {}
    todos = [(c, _lineas(c, t, [f"Hoja: {hoja}", f"Regla: {regla}", f"Debe salir: {esp}"]), fn, av, [])
             for c, t, hoja, regla, esp, fn, av in CASOS_N]
    todos += [(c, _lineas(c, t, [f"Cómo: {como}"]), fn, av, rev) for c, t, como, fn, av, rev in CASOS_X]
    for i, (cod, lineas, fn, avisos, revision) in enumerate(todos):
        P = centro(i if cod.startswith("N") else COLS * FILAS_N + (i - len(CASOS_N)))
        antes = len(win.pipes)
        fn(dz, P)
        datos[cod] = dict(P=P, pipes=list(range(antes, len(win.pipes))), avisos=avisos, revision=revision)
        _etiqueta(dz, P, lineas)
    win._rebuild_structures()
    win._refresh_lists()
    win._redraw()
    return datos


def _caso_de(datos, pipe):
    return next((c for c, d in datos.items() if pipe in d["pipes"]), None)


def avisos_por_caso(win, datos):
    """{código: [clases de aviso]} con lo que dice la app ahora."""
    out = {c: [] for c in datos}
    for a in win._normas_avisos:
        c = _caso_de(datos, a.pipe)
        out.setdefault(c, []).append(a.clase)
    return out


def revision_por_caso(win, datos):
    """{código: [(tipo, arreglado)]} de la revisión antes de exportar (sobre COPIAS)."""
    from nucleo import limpieza
    ft = win.scale / win.zoom
    res = limpieza.limpiar(copy.deepcopy(win.pipes), copy.deepcopy(win.structures), ft)
    out = {c: [] for c in datos}
    for ch in res.cambios:
        out.setdefault(_caso_de(datos, ch.pipe), []).append((ch.tipo, ch.arreglado))
    return out


def comparar(win, datos):
    """[(código, qué, esperado, obtenido)] de lo que NO coincide."""
    malos = []
    av, rev = avisos_por_caso(win, datos), revision_por_caso(win, datos)
    for c in sorted(set(datos) | set(av) | set(rev), key=str):
        esp = datos.get(c, {})
        if sorted(av.get(c, [])) != sorted(esp.get("avisos", [])):
            malos.append((c, "avisos", sorted(esp.get("avisos", [])), sorted(av.get(c, []))))
        if sorted(rev.get(c, [])) != sorted(esp.get("revision", [])):
            malos.append((c, "revisión", sorted(esp.get("revision", [])), sorted(rev.get(c, []))))
    return malos


def generar(ruta=SALIDA):
    import tempfile
    os.environ.setdefault("PDFCAD_NORMAS_TABLAS", os.path.join(tempfile.mkdtemp(), "normas.json"))
    from PySide6 import QtWidgets
    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from ui.ventana.app_window import Main
    win = Main()
    win.normas_cat = normativas()                     # las del Excel corregido, no las de fábrica
    datos = construir(win)
    win.project_path = ruta
    win._write_project(ruta)
    return win, datos


if __name__ == "__main__":
    win, datos = generar()
    print(f"Proyecto: {SALIDA}")
    print(f"{len(CASOS_N)} casos de normativas + {len(CASOS_X)} novedades · {len(win.pipes)} utilidades · "
          f"{len(win.structures)} estructuras · {sum(1 for a in win._normas_avisos if not a.info)} avisos")
    malos = comparar(win, datos)
    for c, que, esp, obt in malos:
        print(f"  XX {c} {que}: esperado {esp}, obtenido {obt}")
    print("Todo como se esperaba." if not malos else f"{len(malos)} diferencias.")
    win._dirty = False

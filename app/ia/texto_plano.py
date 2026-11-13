"""El TEXTO del plano para la IA (PURO): buscar lo que viene al caso de cada pregunta, nunca mandarlo todo.

Pedido del usuario 2026-11-13: «a la IA no le vamos a mandar toda la información; cuando le pregunten algo, que agarre
esa información y busque lo que le sirve». `IndiceTexto(texto_plano, pipes)` (el índice que arma `hoja.indice_texto`
y guarda el proyecto) da:
  - `resumen()`: UNA línea para el contexto (cuántas calles, lugares, rótulos… y las calles más nombradas);
  - `buscar(consulta)`: las líneas del plano que mejor encajan con la pregunta (texto exacto primero, luego palabras
    en común), cada una con su código TX-n (enlace al lugar), su tipo, su hoja y las utilidades que tiene cerca;
  - `calles()`: cada calle una vez, con cuántas veces aparece, dónde y qué utilidades cruza o corren junto a ella;
  - `vocabulario`: las palabras del plano (el filtro de alcance acepta «¿dónde está Thomas Rd?»).
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

from hoja.indice_texto import nombre_calle
from ia.texto import normalizar, raices
from traduccion.i18n_core import N_, t

CERCA_PT = 60.0          # utilidades «cerca» de un texto: a ≤ esto (pt del plano) de alguno de sus tramos
MAX_RESULTADOS = 30
SUFIJOS = {"AVE", "AVENUE", "RD", "ROAD", "ST", "STREET", "BLVD", "DR", "DRIVE", "LN", "LANE", "WAY", "PKWY", "CIR",
           "CT", "PL", "LOOP", "HWY", "FWY", "FREEWAY", "TER", "TRL", "ALY", "N", "S", "E", "W"}
# tipos en palabras (el dato guardado no se traduce)
TIPOS = {"calle": N_("calle"), "tuberia": N_("rótulo de tubería"), "largo": N_("largo"),
         "direccion": N_("dirección"), "servicio": N_("servicio / orden"), "lugar": N_("lugar"), "nota": N_("nota"),
         "estacion": N_("estación"), "celda": N_("hoja"), "otro": N_("texto")}
_GENERICAS = {"donde", "esta", "estan", "cual", "cuales", "como", "plano", "hoja", "hojas", "texto", "dice", "calle",
              "calles", "tuberia", "tuberias", "linea", "lineas", "proyecto", "cerca", "junto", "todas", "todos"}


def _tipo(cat):
    return t(TIPOS.get(cat, "texto"))


class IndiceTexto:
    def __init__(self, texto_plano, pipes=(), zoom=1.0):
        self.zoom = float(zoom or 1.0)
        self.pipes = list(pipes or ())
        tp = texto_plano or {}
        self.hojas = list(tp.get("hojas") or [])
        self.lineas = []                    # (código, texto, x, y, tipo, hoja, norm, raíces)
        for n, l in enumerate(tp.get("lineas") or ()):
            try:
                texto, x, y, cat, k = l[0], float(l[1]), float(l[2]), str(l[3]), int(l[4])
            except (IndexError, TypeError, ValueError):
                continue
            hoja = self.hojas[k] if 0 <= k < len(self.hojas) else ""
            self.lineas.append((f"TX-{n + 1}", str(texto), x, y, cat, hoja, normalizar(texto), raices(texto)))
        # palabras del plano (≥4 letras) y números largos (servicios, órdenes: ≥5 cifras)
        self.vocabulario = {r for *_c, rs in self.lineas for r in rs
                            if (len(r) >= 4 and not r.isdigit()) or (r.isdigit() and len(r) >= 5)}
        self._por_codigo = {normalizar(c): (x, y) for c, _t, x, y, *_r in self.lineas}
        self._cajas = None

    def __len__(self):
        return len(self.lineas)

    # ── dónde ──
    def ref(self, codigo):
        xy = self._por_codigo.get(normalizar(codigo))
        return None if xy is None else {"objeto": None, "indice": -1, "x": xy[0], "y": xy[1]}

    def _utilidades_cerca(self, x, y, r_px):
        """Códigos de las utilidades con un tramo a ≤ r_px de (x, y), la más cercana primero."""
        from nucleo import informe_datos
        if self._cajas is None:
            self._cajas = []
            for i, p in enumerate(self.pipes):
                pts = p.get("pts") or []
                if p.get("world") or len(pts) < 2:
                    continue
                xs, ys = [q[0] for q in pts], [q[1] for q in pts]
                self._cajas.append((i, min(xs), min(ys), max(xs), max(ys)))
        out = []
        for i, x0, y0, x1, y1 in self._cajas:
            if x < x0 - r_px or x > x1 + r_px or y < y0 - r_px or y > y1 + r_px:
                continue
            pts = self.pipes[i]["pts"]
            d = min(_dist_seg(x, y, a, b) for a, b in zip(pts, pts[1:]))
            if d <= r_px:
                out.append((d, i))
        out.sort()
        return [informe_datos.utilidad(self.pipes, i)["codigo"] for _d, i in out[:4]]

    def _fila(self, ln, con_cerca=True):
        codigo, texto, x, y, cat, hoja, *_r = ln
        partes = [codigo, _tipo(cat), f"«{texto}»"]
        if hoja:
            partes.append(t("hoja {h}").format(h=hoja))
        if con_cerca and self.pipes:
            cerca = self._utilidades_cerca(x, y, CERCA_PT * self.zoom)
            if cerca:
                partes.append(t("cerca de {u}").format(u=", ".join(cerca)))
        return " | ".join(partes)

    # ── búsqueda ──
    def buscar(self, consulta, tipo="", maximo=MAX_RESULTADOS):
        """Filas de texto de las líneas que mejor encajan con `consulta` (vacía = todas las del tipo)."""
        q = normalizar(consulta or "").strip()
        qr = {r for r in raices(consulta or "") if r not in _GENERICAS}
        tipo = normalizar(tipo or "").strip()
        puntos = []
        for k, ln in enumerate(self.lineas):
            if tipo and ln[4] != tipo:
                continue
            s = 0.0
            if q and len(q) >= 3 and q in ln[6]:
                s += 10.0
            comun = qr & ln[7]
            if comun:
                s += len(comun) + sum(0.5 for r in comun if any(c.isdigit() for c in r))
            if s > 0 or not (q or qr):
                puntos.append((-s, k))
        puntos.sort()
        if puntos and -puntos[0][0] >= 2:             # con un buen resultado, fuera los que solo comparten «RD»
            tope = -puntos[0][0] * 0.75
            puntos = [pk for pk in puntos if -pk[0] >= tope]
        return [self._fila(self.lineas[k]) for _s, k in puntos[:maximo]], len(puntos)

    def calles(self, maximo=80):
        """Cada calle una vez: «THOMAS RD — 14 veces · hojas 14-6, 14-7 · cerca de GAS-3 · TX-12»."""
        por = defaultdict(list)
        for ln in self.lineas:
            if ln[4] != "calle":
                continue
            nombre = nombre_calle(ln[1])
            if all(p in SUFIJOS for p in nombre.split()) or re.match(r"^\d{3,5}\s", nombre):
                continue                            # «AVE» suelto o una dirección («9301 W THOMAS RD»)
            por[nombre].append(ln)
        filas = []
        for nombre, lns in sorted(por.items(), key=lambda kv: -len(kv[1]))[:maximo]:
            hojas = list(dict.fromkeys(l[5] for l in lns if l[5]))
            cerca = []
            for l in lns:
                for c in (self._utilidades_cerca(l[2], l[3], CERCA_PT * self.zoom) if self.pipes else ()):
                    if c not in cerca:
                        cerca.append(c)
            partes = [nombre, t("1 vez") if len(lns) == 1 else t("{n} veces").format(n=len(lns))]
            if hojas:
                partes.append(t("hojas {h}").format(h=", ".join(hojas[:6]) + ("…" if len(hojas) > 6 else "")))
            if cerca:
                partes.append(t("cerca de {u}").format(u=", ".join(cerca[:6])))
            partes.append(lns[0][0])
            filas.append(" | ".join(partes))
        return filas, len(por)

    def resumen(self):
        if not self.lineas:
            return ""
        cuenta = Counter(ln[4] for ln in self.lineas)
        calles, n_calles = self.calles(maximo=12)
        partes = [t("{n} {tipo}").format(n=v, tipo=_tipo(k)) for k, v in cuenta.most_common() if k != "otro"]
        s = t("Texto del plano: {n} líneas ({p}); {c} calles distintas.").format(
            n=len(self.lineas), p=", ".join(partes), c=n_calles)
        if calles:
            s += " " + t("Las más nombradas: {c}.").format(c=", ".join(f.split(" | ")[0] for f in calles))
        return s + " " + t("Para calles, lugares, direcciones, servicios o notas, busca en el texto del plano.")

    def nombra(self, pregunta):
        """¿La pregunta nombra algo que dice el plano? (para el filtro de alcance)."""
        return any(r in self.vocabulario for r in raices(pregunta) if r not in _GENERICAS and len(r) >= 4)


def _dist_seg(px, py, a, b):
    ax, ay = a[0], a[1]
    dx, dy = b[0] - ax, b[1] - ay
    l2 = dx * dx + dy * dy
    u = 0.0 if l2 <= 1e-12 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
    return math.hypot(ax + dx * u - px, ay + dy * u - py)

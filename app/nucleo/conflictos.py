"""Conflictos del dibujo con NÚMERO (PURO: sin Qt).

Junta en una sola lista los cruces a la misma cota que el plugin no une y todas las
alertas rojas del lienzo (5+ tuberías en un punto, escalones de cota, tramos cortos
entre codos, codos de retorno, uniones con pendiente, conexiones verticales con
pendiente, redes distintas que chocan, cruces sin conexión) y les da un número en orden
de LECTURA del plano (de arriba abajo y de izquierda a derecha). El mismo número se ve en
el lienzo, en la Vista 3D, en la Tabla de datos y en su Excel.

Terminología (pedido del usuario 2026-11-13/14): CONFLICTO (C-1, C-2…) es SOLO cuando dos o más
tuberías se cruzan, chocan o se tocan (`cruce`, `choque`, `redes`); lo demás es una OBSERVACIÓN: algo
que Civil 3D no podrá construir tal como está dibujado, con un código por tipo (OC observación de cotas,
OU unión no constructible, OG observación geométrica, OV observación de conexión vertical). Cada código
lleva su propia numeración; todos siguen en la misma lista (`Conflicto.categoria` dice cuál es).

Los avisos de normativa (N-n) y de reconocimiento (R-n) usan el MISMO registro (`numerar_avisos`): todo
código que se dio queda fijo; nada se renumera al resolver otro (pedido 2026-11-14).

Los números son FIJOS (pedido del usuario 2026-10-29: resolver uno con el asistente renumeraba
todos y el usuario se perdía): con un `Registro`, cada conflicto conserva el número que tuvo la
primera vez (mismo tipo, mismas utilidades y cerca del mismo lugar); uno resuelto queda en el
registro como «resuelto» con su número (si vuelve —Ctrl+Z—, vuelve con él) y uno nuevo toma el
siguiente número libre. Sin registro (o vacío) se numera en orden de lectura, como siempre.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from traduccion.i18n_core import N_

TITULOS = {
    "cruce": N_("Cruce a la misma cota"),
    "exceso": N_("5 o más tuberías en un punto"),
    "escalon": N_("Escalón de cota"),
    "codos": N_("Tramo muy corto entre codos"),
    "retorno": N_("Codo de retorno"),
    "pendiente": N_("Unión con pendiente"),
    "inclinada": N_("Conexión vertical con pendiente"),
    "redes": N_("Choque entre redes distintas"),
    "choque": N_("Cruce sin conexión"),
}
# Conflictos: dos o más tuberías se cruzan, chocan o se tocan. Lo demás son observaciones.
CLAVES_CONFLICTO = frozenset(("cruce", "choque", "redes"))
CONFLICTO, OBSERVACION = "conflicto", "observacion"
# Código de cada tipo (2026-11-14: uno por tipo de observación, no «O» para todas)
PREFIJOS = {"cruce": "C", "choque": "C", "redes": "C",
            "escalon": "OC", "exceso": "OU", "codos": "OG", "retorno": "OG", "pendiente": "OV", "inclinada": "OV"}
PREFIJOS_CONFLICTO = ("C",)
PREFIJOS_OBSERVACION = ("OC", "OU", "OG", "OV")
AVISO, RECONOCIMIENTO = "N", "R"            # avisos de normativa y de reconocimiento (`numerar_avisos`)
FAMILIAS = {"conflictos": PREFIJOS_CONFLICTO + PREFIJOS_OBSERVACION, "avisos": (AVISO, RECONOCIMIENTO)}
# Subtipo de cada observación (lo que se lee en el manual, el panel y el informe)
SUBTIPOS = {
    "escalon": N_("Observación de cotas"),
    "exceso": N_("Unión no constructible"),
    "codos": N_("Observación geométrica"),
    "retorno": N_("Observación geométrica"),
    "pendiente": N_("Observación de conexión vertical"),
    "inclinada": N_("Observación de conexión vertical"),
}
NOMBRE_CATEGORIA = {CONFLICTO: N_("Conflicto"), OBSERVACION: N_("Observación")}


def categoria_de(clave):
    """«conflicto» (dos o más tuberías se tocan) u «observacion» (lo demás)."""
    return CONFLICTO if clave in CLAVES_CONFLICTO else OBSERVACION


def prefijo_de(clave):
    """Código de la clave: «C», «OC», «OU», «OG», «OV»; «N» o «R» para los avisos («aviso:…» / «rec:…»)."""
    if clave.startswith("aviso:"):
        return AVISO
    if clave.startswith("rec:"):
        return RECONOCIMIENTO
    return PREFIJOS.get(clave, "OG" if categoria_de(clave) == OBSERVACION else "C")


def partes(codigo):
    """«OC-12» → («OC», 12); None si no es un código numerado."""
    s = str(codigo or "").strip().upper()
    pre, _, n = s.rpartition("-")
    return (pre, int(n)) if pre and n.isdigit() else None


def categoria_de_codigo(codigo):
    """«conflicto», «observacion» o None (no es un código de conflicto ni de observación)."""
    p = partes(codigo)
    if p is None:
        return None
    return CONFLICTO if p[0] in PREFIJOS_CONFLICTO else OBSERVACION if p[0] in PREFIJOS_OBSERVACION else None


def es_codigo(codigo):
    """«C-12», «OC-3», «OU-1», «OG-2», «OV-5» (cualquier caja)."""
    return categoria_de_codigo(codigo) is not None


FILA_PX = 8.0           # puntos a menos de esto en vertical van en la misma «fila» de lectura


@dataclass
class Conflicto:
    id: str                                  # «C-1» (conflicto) u «OC-1», «OU-1»… (observación)
    clave: str                               # TITULOS
    x: float                                 # lugar en el lienzo (px)
    y: float
    mensaje: str = ""
    pipes: list = field(default_factory=list)       # índices de las utilidades
    cotas: list = field(default_factory=list)       # cotas (ft) en el punto, una por utilidad (o vacío)

    @property
    def titulo(self):
        return TITULOS.get(self.clave, self.clave)

    @property
    def categoria(self):
        """«conflicto» u «observacion» (ver `CLAVES_CONFLICTO`)."""
        return categoria_de(self.clave)

    @property
    def es_conflicto(self):
        return self.categoria == CONFLICTO

    @property
    def subtipo(self):
        """«Conflicto» o el subtipo de la observación («Observación de cotas»…)."""
        return NOMBRE_CATEGORIA[CONFLICTO] if self.es_conflicto else SUBTIPOS.get(self.clave, NOMBRE_CATEGORIA[OBSERVACION])

    @property
    def diferencia(self):
        """Diferencia de cota entre las dos utilidades (ft), o None."""
        z = [c for c in self.cotas if c is not None]
        return abs(z[0] - z[1]) if len(z) >= 2 else None


MISMO_PX = 1.5          # el mismo conflicto visto por varios pares de tramos (cruce en un vértice)


def _sin_repetidos(items):
    """Un cruce en un VÉRTICE lo ven varios pares de tramos de las mismas dos utilidades: es UN
    conflicto (antes salían C-10…C-13 en el mismo punto)."""
    # Mismo resultado que comparar cada uno con TODOS los ya puestos, pero mirando solo los de su misma clave y
    # utilidades en las celdas vecinas (2026-11-14: con miles de conflictos, todos contra todos dejaba la ventana
    # congelada ~20 s cada vez que llegaban los cálculos).
    out = []
    r2 = MISMO_PX ** 2
    puestos = {}                                     # (clave, utilidades, celda) → [(x, y)]
    for c in items:
        clave = (c["clave"], frozenset(i for i in c.get("pipes") or [] if i is not None))
        x, y = float(c["x"]), float(c["y"])
        ci, cj = math.floor(x / MISMO_PX), math.floor(y / MISMO_PX)
        if any((ox - x) ** 2 + (oy - y) ** 2 <= r2
               for i in (ci - 1, ci, ci + 1) for j in (cj - 1, cj, cj + 1)
               for ox, oy in puestos.get((clave, i, j), ())):
            continue
        puestos.setdefault((clave, ci, cj), []).append((x, y))
        out.append(c)
    return out


def numerar(items):
    """[Conflicto] con su número. `items` = [{clave, x, y, mensaje, pipes, cotas}]."""
    filas, actual = [], []
    for c in sorted(_sin_repetidos(items), key=lambda c: (float(c["y"]), float(c["x"]))):
        if actual and float(c["y"]) - float(actual[0]["y"]) > FILA_PX:      # otra fila de lectura
            filas.append(actual); actual = []
        actual.append(c)
    if actual:
        filas.append(actual)
    orden = [c for fila in filas for c in sorted(fila, key=lambda c: (float(c["x"]), c["clave"]))]
    cuenta = {}
    out = []
    for c in orden:                                          # cada código con su numeración: C-1… / OC-1…
        pre = prefijo_de(c["clave"])
        cuenta[pre] = cuenta.get(pre, 0) + 1
        out.append(Conflicto(f"{pre}-{cuenta[pre]}", c["clave"], float(c["x"]), float(c["y"]), c.get("mensaje", ""),
                             [int(i) for i in c.get("pipes") or [] if i is not None],
                             [None if z is None else float(z) for z in c.get("cotas") or []]))
    return out


def numero(c):
    """El número de «C-12» / «OC-3» → 12."""
    return partes(c.id)[1]


_ORDEN_PREFIJO = {p: i for i, p in enumerate(PREFIJOS_CONFLICTO + PREFIJOS_OBSERVACION)}


def orden_lista(conflictos):
    """Conflictos primero (por número) y luego las observaciones, por código (OC, OU, OG, OV) y número."""
    return sorted(conflictos, key=lambda c: (_ORDEN_PREFIJO.get(partes(c.id)[0], 99), numero(c)))


SIGUE_PX = 40.0         # un conflicto que se corrió hasta esto (otra cota, el dibujo retocado) es el mismo


class Registro:
    """Números ya dados: [{n, clave, pipes (frozenset), x, y, resuelto}] y el siguiente libre de CADA código
    (`siguiente` = {«C»: n, «OC»: n, …, «N»: n, «R»: n}). El código de una entrada es «<prefijo de su clave>-n»
    (`codigo`). Un número dado no se vuelve a dar ni cambia (2026-11-14), aunque se resuelva otro."""

    VERSION = 3
    # 1 = un contador para todo (todo C-n); 2 = «C» y «O» (2026-11-13). Al abrirlos se CONSERVA cada número: un
    # escalón que era C-7 (o O-7) pasa a OC-7, y ningún código nuevo reutiliza un número ya dado.

    def __init__(self):
        self.entradas = []
        self.siguiente = {}

    @staticmethod
    def codigo(e):
        return f"{prefijo_de(e['clave'])}-{e['n']}"

    def resueltos(self, familia="conflictos"):
        pres = FAMILIAS[familia]
        return [e for e in self.entradas if e["resuelto"] and prefijo_de(e["clave"]) in pres]

    def tomar(self, clave):
        """El siguiente número libre del código de `clave` (y lo reserva)."""
        pre = prefijo_de(clave)
        n = self.siguiente.get(pre, 1)
        self.siguiente[pre] = n + 1
        return n

    def a_dict(self):
        return {"version": self.VERSION, "siguiente": dict(self.siguiente),
                "entradas": [dict(e, pipes=sorted(e["pipes"])) for e in self.entradas]}

    @classmethod
    def de_dict(cls, d):
        r = cls()
        if not isinstance(d, dict):
            return r
        try:
            r.entradas = [dict(e, n=int(e["n"]), pipes=frozenset(int(i) for i in e.get("pipes") or []),
                               x=float(e["x"]), y=float(e["y"]), resuelto=bool(e.get("resuelto")))
                          for e in d.get("entradas") or []]
            version = d.get("version") or 1
            sig = d.get("siguiente")
            usados = {}
            for e in r.entradas:
                pre = prefijo_de(e["clave"])
                usados[pre] = max(usados.get(pre, 0), e["n"])
            if version == 1:                     # un solo contador: los números no se repiten entre tipos
                tope = max([int(sig or 1) - 1] + [e["n"] for e in r.entradas])
                for pre in PREFIJOS_CONFLICTO + PREFIJOS_OBSERVACION:
                    r.siguiente[pre] = tope + 1
            elif version == 2:                   # «C» y «O»: cada observación sigue el contador de «O»
                sig = sig or {}
                r.siguiente["C"] = max(int(sig.get("C") or 1), usados.get("C", 0) + 1)
                tope_o = max([int(sig.get("O") or 1) - 1] + [usados.get(p, 0) for p in PREFIJOS_OBSERVACION])
                for pre in PREFIJOS_OBSERVACION:
                    r.siguiente[pre] = tope_o + 1
            else:
                r.siguiente = {str(k): int(v) for k, v in (sig or {}).items()}
            for pre, n in usados.items():        # nunca por debajo de lo ya dado
                r.siguiente[pre] = max(r.siguiente.get(pre, 1), n + 1)
        except (KeyError, TypeError, ValueError, AttributeError):
            return cls()
        return r


def _asignar(items, registro, familia):
    """Pone a cada ítem (en el orden dado: el de lectura) el número que ya tenía en el registro (misma clave, mismas
    utilidades y a ≤ `SIGUE_PX`) o el siguiente libre de su código; marca «resuelto» las entradas de esa `familia`
    que no aparecieron. Devuelve [(ítem, código)] en el mismo orden."""
    pres = FAMILIAS[familia]
    libres = [e for e in registro.entradas if prefijo_de(e["clave"]) in pres]
    por_clave = {}                               # (clave, utilidades) → entradas, en su orden (mismo resultado que
    for e in libres:                             # recorrerlas todas; con decenas de miles de avisos, sin trabar)
        por_clave.setdefault((e["clave"], e["pipes"]), []).append(e)
    usados = set()
    out = []
    nuevos = []
    for k, it in enumerate(items):
        clave, pipes, x, y = it
        cand = [e for e in por_clave.get((clave, pipes), ()) if id(e) not in usados
                and (e["x"] - x) ** 2 + (e["y"] - y) ** 2 <= SIGUE_PX ** 2]
        if not cand:
            nuevos.append(k)
            out.append(None)
            continue
        e = min(cand, key=lambda e: ((e["x"] - x) ** 2 + (e["y"] - y) ** 2, e["n"]))
        usados.add(id(e))
        e.update(x=x, y=y, resuelto=False)
        out.append(Registro.codigo(e))
    for e in libres:
        if id(e) not in usados:
            e["resuelto"] = True
    for k in nuevos:
        clave, pipes, x, y = items[k]
        e = dict(n=registro.tomar(clave), clave=clave, pipes=pipes, x=x, y=y, resuelto=False)
        registro.entradas.append(e)
        out[k] = Registro.codigo(e)
    return out


def numerar_fijo(items, registro):
    """Como `numerar`, pero con los números de `registro` (y lo pone al día). Devuelve los conflictos y
    observaciones vigentes: primero los conflictos y luego las observaciones, cada código por número."""
    cs = numerar(items)                                       # orden de lectura: los nuevos se numeran así
    codigos = _asignar([(c.clave, frozenset(c.pipes), c.x, c.y) for c in cs], registro, "conflictos")
    for c, cod in zip(cs, codigos):
        c.id = cod
    return orden_lista(cs)


def clave_aviso(a, clase_reconocimiento="grosor"):
    """Clave del registro para un aviso de `normas_validar`: «aviso:<clase>» o «rec:<clase>» (reconocimiento)."""
    return ("rec:" if a.clase == clase_reconocimiento else "aviso:") + str(a.clase)


def numerar_avisos(avisos, registro, clase_reconocimiento="grosor"):
    """{id(aviso): «N-n» / «R-n»} con números FIJOS (2026-11-14; antes se contaban en orden de lectura cada vez y
    resolver uno renumeraba los demás). La identidad de un aviso = su clase, su utilidad y su lugar (el de la regla,
    `Aviso.lugar`, si lo hay: el punto dibujado puede correrse). Los avisos «sin tipo» no llevan número (como antes)."""
    def lugar(a):
        q = getattr(a, "lugar", None)
        return (float(q[0]), float(q[1])) if q else (float(a.x), float(a.y))
    orden = sorted((a for a in avisos or [] if a.clase != "tipo"), key=lambda a: (round(a.y / 8.0), a.x))
    items = [(clave_aviso(a, clase_reconocimiento),
              frozenset([int(a.pipe)] if getattr(a, "pipe", None) is not None and a.pipe >= 0 else []),
              *lugar(a)) for a in orden]
    return {id(a): cod for a, cod in zip(orden, _asignar(items, registro, "avisos"))}


def agrupar(conflictos, tol):
    """Los conflictos en el MISMO lugar (≤ tol px) juntos, para una sola etiqueta «C-10 · OC-3»
    (si no, una tapa a la otra). Devuelve [[Conflicto, …]] en el orden de numeración."""
    # Mismo resultado que mirar todos los grupos en orden (va al PRIMER grupo cuyo primer conflicto está a ≤ tol),
    # pero buscando solo en las celdas vecinas: con decenas de miles de conflictos (proyecto de 29 mil utilidades,
    # 2026-11-13) mirar todos dejaba la ventana congelada ~16 s y Windows la mostraba en blanco.
    grupos = []
    celda = max(float(tol), 1e-9)
    celdas = {}
    t2 = tol * tol
    for c in conflictos or []:
        cx, cy = int(c.x // celda), int(c.y // celda)
        mejor = None
        for i in range(cx - 1, cx + 2):
            for j in range(cy - 1, cy + 2):
                for k in celdas.get((i, j), ()):
                    if (mejor is None or k < mejor) and (grupos[k][0].x - c.x) ** 2 + (grupos[k][0].y - c.y) ** 2 <= t2:
                        mejor = k
        if mejor is None:
            celdas.setdefault((cx, cy), []).append(len(grupos))
            grupos.append([c])
        else:
            grupos[mejor].append(c)
    return grupos


def en_punto(conflictos, x, y, tol):
    """Conflictos a ≤ tol (px) del punto."""
    return [c for c in conflictos or [] if (c.x - x) ** 2 + (c.y - y) ** 2 <= tol * tol]

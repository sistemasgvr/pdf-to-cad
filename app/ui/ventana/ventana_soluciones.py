"""Soluciones de un conflicto C-n en la ventana (pedido del usuario 2026-10-23): proponer (`nucleo/soluciones`),
VALIDAR cada propuesta y aplicarla con un solo paso de deshacer.

Validar = aplicar la propuesta a una COPIA de la zona (la utilidad que cambia + las que la rodean) y recalcular
conflictos y avisos de normativa con el MISMO código del plano (`calculo_fondo.Calculo`), antes y después. La
propuesta vale si el conflicto desaparece y no aparece ningún problema nuevo (otro conflicto, un aviso de normativa
o una unión de la red que queda a cotas distintas). Con 16 762 utilidades solo se recalcula la zona: rápido.
"""
from __future__ import annotations

import copy
import dataclasses

from nucleo import soluciones
from traduccion.i18n import t as _tr

MARGEN_FT = 60.0            # aire alrededor de la utilidad que cambia: lo que puede verse afectado
CERCA_PX = 3.0              # mismo conflicto antes/después (posición en el plano)


class SolucionesMixin:
    def _conflicto_por_id(self, cid):
        return next((c for c in getattr(self, "_conflictos", None) or [] if c.id == cid), None)

    def soluciones_de(self, cid):
        """(conflicto, [Propuesta] validadas y ordenadas: la mejor primero). Sin propuestas automáticas: []."""
        self._resultados_al_dia()
        c = self._conflicto_por_id(cid)
        if c is None:
            return None, []
        c = self._con_utilidades(c)
        self._sol_antes = {}                           # problemas de cada zona ANTES (uno por zona)
        props = soluciones.proponer(c, self.pipes, self._pipe_z_at, getattr(self, "normas_cat", None))
        for p in props:
            self._validar_propuesta(c, p)
        props.sort(key=lambda p: (not p.valida, len(p.nuevos), -p.otros_resueltos, abs(p.delta_ft),
                                  p.accion != "bajar"))
        return c, props

    def _con_utilidades(self, c):
        """«Choque entre redes distintas» no guarda qué utilidades son: las dos que se cruzan ahí a la misma cota."""
        if c.clave != "redes" or c.pipes:
            return c
        ft = self.scale / self.zoom if self.scale and self.zoom else 0.0
        tol = max(1.0, 0.5 / ft) if ft else 3.0           # 0.5 ft: los tramos que pasan por el punto
        cerca = []
        for i in self._utilidades_cerca(c.x, c.y, tol, todas=True):
            pts = self.pipes[i].get("pts") or []
            d, k = min(((_dist_seg((c.x, c.y), pts[k], pts[k + 1]), k) for k in range(len(pts) - 1)),
                       default=(None, -1))
            if k >= 0 and d <= tol:
                cerca.append((d, i, self._pipe_z_at(i, k, c.x, c.y)))
        pares = sorted((da + db, ia, ib, za, zb) for n, (da, ia, za) in enumerate(cerca) for (db, ib, zb) in cerca[n + 1:]
                       if self.pipes[ia].get("layer") != self.pipes[ib].get("layer") and za is not None
                       and zb is not None and abs(za - zb) <= 0.10)
        if pares:
            _d, ia, ib, za, zb = pares[0]
            return dataclasses.replace(c, clave="cruce", pipes=[ia, ib], cotas=[za, zb])
        return c

    # ── validar en una copia ──
    def _validar_propuesta(self, c, prop):
        ft = self.scale / self.zoom if self.scale and self.zoom else 0.0
        sub = self._zona_de(prop.pipe, c, ft)
        antes = [self.pipes[i] for i in sub]
        despues = copy.deepcopy(antes)
        local = {g: k for k, g in enumerate(sub)}
        soluciones.aplicar(despues, dataclasses.replace(prop, pipe=local[prop.pipe]))
        clave = tuple(sub)
        if clave not in self._sol_antes:
            self._sol_antes[clave] = self._problemas(antes, sub, ft)
        f0 = self._sol_antes[clave]
        f1 = self._problemas(despues, sub, ft)
        objetivo = (c.clave if c.clave != "redes" else "cruce", frozenset(i for i in c.pipes or [] if i is not None))
        prop.resuelve = not any(_es(f, objetivo, c) or (f[0] == "redes" and _cerca(f, c)) for f in f1)
        nuevos = [f for f in f1 - f0 if not _es(f, objetivo, c)]
        prop.nuevos = [_describir(f, self.pipes) for f in nuevos]
        tol = 0.5 / ft if ft else 3.0
        for a, b in soluciones.uniones_rotas(antes, despues, [local[prop.pipe]], tol):
            prop.nuevos.append(_tr("separa la unión entre {a} y {b}").format(a=a, b=b))
        prop.otros_resueltos = max(0, len(f0 - f1) - (0 if prop.resuelve is False else 1))

    def _zona_de(self, i, c, ft):
        """Índices (ordenados) de la utilidad `i` y las que tocan su recuadro (+ `MARGEN_FT`) o el conflicto."""
        m = MARGEN_FT / ft if ft else 200.0
        xs = [q[0] for q in self.pipes[i]["pts"]] + [c.x]
        ys = [q[1] for q in self.pipes[i]["pts"]] + [c.y]
        x0, y0, x1, y1 = min(xs) - m, min(ys) - m, max(xs) + m, max(ys) + m
        sub = []
        for j, p in enumerate(self.pipes):
            pts = p.get("pts") or []
            if not pts or p.get("world"):
                continue
            px = [q[0] for q in pts]
            py = [q[1] for q in pts]
            if max(px) >= x0 and min(px) <= x1 and max(py) >= y0 and min(py) <= y1:
                sub.append(j)
        return sub

    def _problemas(self, pipes_zona, sub, ft):
        """Firmas de los conflictos y avisos de normativa de la zona (índices del proyecto)."""
        from ui.ventana.calculo_fondo import Calculo
        local = {g: k for k, g in enumerate(sub)}
        cruzadas = []
        for cc in getattr(self, "cross_connections", None) or []:
            a, b = local.get(int(cc["pipe_a"])), local.get(int(cc["pipe_b"]))
            if a is not None and b is not None:
                cruzadas.append(dict(cc, pipe_a=min(a, b), pipe_b=max(a, b)))
        xs = [q[0] for p in pipes_zona for q in p["pts"]]
        ys = [q[1] for p in pipes_zona for q in p["pts"]]
        caja = (min(xs) - 5, min(ys) - 5, max(xs) + 5, max(ys) + 5)
        estructuras = [s for s in self.structures if s.get("x") is not None and caja[0] <= s["x"] <= caja[2]
                       and caja[1] <= s["y"] <= caja[3]]
        calc = Calculo({"pipes": pipes_zona, "structures": estructuras, "cross_connections": cruzadas,
                        "normas_cat": getattr(self, "normas_cat", None), "normas_aprobados": [], "duct_banks": [],
                        "scale": self.scale, "zoom": self.zoom}, True)
        calc.correr()
        g = sub.__getitem__
        out = set()
        for (cx, cy, ia, ib, _ka, _kb, za, zb, estado) in getattr(calc, "_conflict_hits", []) or []:
            if estado == "conflicto" and not calc._union_civil(ia, ib, cx, cy, za, zb):
                out.add(("cruce", frozenset((g(ia), g(ib))), round(cx, 1), round(cy, 1)))
        for clave, lista in (("exceso", "_exceso_hits"), ("redes", "_redes_hits")):
            for e in getattr(calc, lista, []) or []:
                out.add((clave, frozenset(), round(e["x"], 1), round(e["y"], 1)))
        for clave, lista in (("escalon", "_escalon_hits"), ("codos", "_codos_hits"), ("retorno", "_retorno_hits")):
            for e in getattr(calc, lista, []) or []:
                out.add((clave, frozenset((g(e["pipe"]),)), round(e["x"], 1), round(e["y"], 1)))
        for clave, lista in (("pendiente", "_pendiente_hits"), ("choque", "_choque_hits")):
            for e in getattr(calc, lista, []) or []:
                out.add((clave, frozenset((g(e["ia"]), g(e["ib"]))), round(e["x"], 1), round(e["y"], 1)))
        for a in calc.datos.get(("normas", ft), []) if ft else []:
            if not a.info:
                quien = frozenset((g(a.pipe),)) if a.pipe is not None and 0 <= a.pipe < len(sub) else frozenset()
                out.add(("norma:" + a.clase, quien, round(a.x, 1), round(a.y, 1)))
        return out

    # ── abrir ──
    def abrir_soluciones(self, cid=None):
        """IA → «Resolver conflictos…» (no modal; una sola ventana)."""
        if getattr(self, "_incrustar_ok", lambda: False)():    # 2.0.0: en el panel del Asistente
            self.mostrar_asistente(True, "conflictos")
            dlg = self._dlg_soluciones
            dlg.elegir(cid)
            return dlg
        from ui.dialogos.ia_soluciones import SolucionesDialog
        dlg = getattr(self, "_dlg_soluciones", None)
        if dlg is None:
            dlg = self._dlg_soluciones = SolucionesDialog(self)
        dlg.show(); dlg.raise_(); dlg.activateWindow()
        dlg.elegir(cid)
        return dlg

    def _menu_conflicto(self, menu, x, y):
        """Clic derecho junto a una marca C-n: «Resolver C-n…»."""
        r = 14.0 / max(self.canvas.transform().m11(), 1e-6)
        cerca = [(abs(c.x - x) + abs(c.y - y), c) for c in getattr(self, "_conflictos", None) or []
                 if abs(c.x - x) <= r and abs(c.y - y) <= r]
        if cerca:
            c = min(cerca, key=lambda t: t[0])[1]
            menu.addAction(_tr("Resolver {c}: ver soluciones…").format(c=c.id), lambda: self.abrir_soluciones(c.id))
            menu.addSeparator()

    # ── aplicar ──
    def aplicar_propuesta(self, prop):
        """La propuesta en el proyecto, en UN paso de deshacer; queda como enseñanza en la memoria de la IA."""
        if not (0 <= prop.pipe < len(self.pipes)):
            return False
        self._push()
        soluciones.aplicar(self.pipes, prop)
        self._tras_editar_3d(prop.pipe)              # panel al día + redibujo (y la Vista 3D)
        return True


def _es(f, objetivo, c):
    return f[0] == objetivo[0] and f[1] == objetivo[1] and _cerca(f, c)


def _cerca(f, c):
    return abs(f[2] - c.x) <= CERCA_PX and abs(f[3] - c.y) <= CERCA_PX


def _describir(f, pipes):
    from nucleo.conflictos import TITULOS
    from nucleo.normas_validar import CLASES
    clave = f[0]
    titulo = (_tr(CLASES.get(clave[6:], clave[6:])) if clave.startswith("norma:") else _tr(TITULOS.get(clave, clave)))
    quien = ", ".join(soluciones.codigo(pipes, i) for i in sorted(f[1]) if 0 <= i < len(pipes))
    return f"{titulo} ({quien})" if quien else titulo


def _dist_seg(p, a, b):
    ax, ay = a
    dx, dy = b[0] - ax, b[1] - ay
    L2 = dx * dx + dy * dy
    u = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L2))
    return ((p[0] - ax - u * dx) ** 2 + (p[1] - ay - u * dy) ** 2) ** 0.5

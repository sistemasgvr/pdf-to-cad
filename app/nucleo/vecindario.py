"""vecindario.py — lo que está ALREDEDOR de una tubería (PURO), para los pasos que solo miran cerca.

Pedido del usuario 2026-10-23 (36 + 36 mapas de Phoenix: la vista previa y la importación
dejaban la ventana «No responde» varios minutos): `quiebres_curvas.curvas_en_quiebres`
comparaba cada quiebre con TODAS las tuberías y TODAS las estructuras de la hoja, pero todo lo
que mira está junto a los vértices de su tubería: otros vértices a ≤ tol px, estructuras a ≤ tol
px (o el contorno / anillo que contiene un vértice) y, en un chaflán, el cruce de sus rectas.

`de(ip, margen)` = (tuberías, posición de la tubería entre ellas, estructuras) que pueden estar a
≤ `margen` de la caja de la tubería, EN EL ORDEN ORIGINAL de cada lista: quien llama hace lo de
siempre sobre esas listas (mismas cuentas, mismos desempates por orden) y `aplicar` lleva a la
lista completa lo que cambió en las estructuras (quitadas; agregadas al final, en su orden) y
pone al día las cajas de la tubería y de lo que se movió. Una estructura entra por su punto, su
anillo (`width_ft` en px) y su contorno; sin coordenadas numéricas, siempre.
"""
from __future__ import annotations

import math


class Vecindario:
    CELDA = 256.0

    def __init__(self, pipes, structures, ft_per_px):
        self.pipes = pipes
        self.structures = structures
        self.fpp = float(ft_per_px) if ft_per_px else 0.0
        self._celdas_p = {}
        self._caja_p = {}
        self._celdas_s = {}
        self._caja_s = {}            # id(s) → caja
        self._orden = {}             # id(s) → nº de orden (el de la lista; las nuevas, al final)
        self._obj = {}               # id(s) → s
        self._siempre = {}           # id(s) → s (sin coordenadas)
        self._n = 0
        for ip in range(len(pipes)):
            self._poner_p(ip)
        for s in structures:
            self._poner_s(s)

    # ── cajas y celdas ──
    def _celdas(self, caja):
        c = self.CELDA
        x0, y0, x1, y1 = caja
        for cx in range(math.floor(x0 / c), math.floor(x1 / c) + 1):
            for cy in range(math.floor(y0 / c), math.floor(y1 / c) + 1):
                yield (cx, cy)

    def _caja_tuberia(self, ip):
        pts = self.pipes[ip].get("pts") or ()
        try:
            xs = [float(q[0]) for q in pts]
            ys = [float(q[1]) for q in pts]
        except (TypeError, ValueError, IndexError):
            return None
        if not xs:
            return None
        return min(xs), min(ys), max(xs), max(ys)

    def _poner_p(self, ip):
        caja = self._caja_tuberia(ip)
        self._caja_p[ip] = caja
        if caja is None:
            return
        for k in self._celdas(caja):
            self._celdas_p.setdefault(k, set()).add(ip)

    def _quitar_p(self, ip):
        caja = self._caja_p.pop(ip, None)
        if caja is None:
            return
        for k in self._celdas(caja):
            self._celdas_p.get(k, set()).discard(ip)

    def _caja_estructura(self, s):
        try:
            x, y = float(s["x"]), float(s["y"])
            if not (math.isfinite(x) and math.isfinite(y)):
                return None
        except (KeyError, TypeError, ValueError):
            return None
        r = 0.0
        try:
            if s.get("width_ft") and self.fpp > 0:
                r = abs(float(s["width_ft"])) / self.fpp       # el anillo de un buzón redondo
        except (TypeError, ValueError):
            return None
        x0, y0, x1, y1 = x - r, y - r, x + r, y + r
        out = s.get("outline")
        if out:
            try:
                xs = [float(q[0]) for q in out]
                ys = [float(q[1]) for q in out]
            except (TypeError, ValueError, IndexError):
                return None
            if xs:
                x0, y0, x1, y1 = min(x0, *xs), min(y0, *ys), max(x1, *xs), max(y1, *ys)
        return x0, y0, x1, y1

    def _poner_s(self, s):
        k = id(s)
        if k not in self._orden:
            self._orden[k] = self._n
            self._n += 1
        self._obj[k] = s
        caja = self._caja_estructura(s)
        self._caja_s[k] = caja
        if caja is None:
            self._siempre[k] = s
            return
        for c in self._celdas(caja):
            self._celdas_s.setdefault(c, set()).add(k)

    def _quitar_s(self, s, olvidar=True):
        k = id(s)
        caja = self._caja_s.pop(k, None)
        self._siempre.pop(k, None)
        if caja is not None:
            for c in self._celdas(caja):
                self._celdas_s.get(c, set()).discard(k)
        if olvidar:
            self._orden.pop(k, None)
            self._obj.pop(k, None)

    # ── consultas ──
    def de(self, ip, margen):
        """(tuberías, posición de `ip` entre ellas, estructuras) junto a la tubería `ip`."""
        caja = self._caja_tuberia(ip)
        if caja is None:
            return list(self.pipes), ip, list(self.structures)
        x0, y0, x1, y1 = caja[0] - margen, caja[1] - margen, caja[2] + margen, caja[3] + margen
        cand_p = set()
        cand_s = set(self._siempre)
        for c in self._celdas((x0, y0, x1, y1)):
            cand_p.update(self._celdas_p.get(c, ()))
            cand_s.update(self._celdas_s.get(c, ()))
        cand_p.add(ip)
        sel_p = sorted(j for j in cand_p
                       if j == ip or (self._caja_p.get(j) is not None and _toca(self._caja_p[j], (x0, y0, x1, y1))))
        sel_s = sorted((k for k in cand_s
                        if self._caja_s.get(k) is None or _toca(self._caja_s[k], (x0, y0, x1, y1))),
                       key=self._orden.__getitem__)
        return [self.pipes[j] for j in sel_p], sel_p.index(ip), [self._obj[k] for k in sel_s]

    def aplicar(self, ip, antes, despues):
        """Lo que cambió en las estructuras de `de(ip)` (quitadas / agregadas al final / movidas)
        pasa a la lista completa; la caja de la tubería `ip`, al día."""
        ids_antes = {id(s) for s in antes}
        ids_desp = {id(s) for s in despues}
        quitadas = {id(s) for s in antes if id(s) not in ids_desp}
        if quitadas:
            self.structures[:] = [s for s in self.structures if id(s) not in quitadas]
            for s in antes:
                if id(s) in quitadas:
                    self._quitar_s(s)
        for s in despues:
            if id(s) not in ids_antes:
                self.structures.append(s)
                self._poner_s(s)
            else:                                      # pudo moverse (chaflán): su caja de ahora
                self._quitar_s(s, olvidar=False)
                self._poner_s(s)
        self._quitar_p(ip)
        self._poner_p(ip)


def _toca(a, b):
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]

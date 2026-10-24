"""UNA barra de avance para un trabajo de varias partes (PURO; pedido del usuario 2026-10-20: «un loader
preciso, que no parezca bug»). La usan la Vista 3D (`avance3d`) y la exportación a DXF.

Cada parte pesa su costo ESTIMADO (unidades × lo que tarda cada unidad, medido; la unidad da igual
mientras todas las partes usen la misma). `parte(nombre, fracción)` dice cuánto va de esa parte; la barra
= lo hecho / el total, en milésimas, y NUNCA retrocede (si una estimación se corrige con `costo` y el total
crece, la barra espera a que el trabajo la alcance).
"""
from __future__ import annotations


class Barra:
    def __init__(self, costos=None):
        self.costos = dict(costos or {})
        self.hecho = dict.fromkeys(self.costos, 0.0)
        self.milesimas = 0

    def costo(self, parte, valor):
        """Corrige (o agrega) el costo estimado de una parte; lo hecho de ella sigue en la misma fracción."""
        return self.costos_nuevos({parte: valor})

    def costos_nuevos(self, cambios):
        """Varias correcciones JUNTAS: la barra se recalcula una vez (corregirlas de a una dejaba la barra
        trabada en el valor de un total a medio corregir: nunca retrocede)."""
        for parte, valor in cambios.items():
            anterior = self.costos.get(parte, 0.0)
            frac = self.hecho.get(parte, 0.0) / anterior if anterior > 0 else 0.0
            self.costos[parte] = max(0.0, float(valor))
            self.hecho[parte] = self.costos[parte] * frac
        return self._calcular()

    def parte(self, parte, fraccion):
        """Van `fraccion` (0–1) de `parte`; devuelve las milésimas de toda la barra."""
        f = min(1.0, max(0.0, float(fraccion)))
        self.hecho[parte] = max(self.hecho.get(parte, 0.0), self.costos.get(parte, 0.0) * f)
        return self._calcular()

    def lista(self, parte):
        return self.parte(parte, 1.0)

    def _calcular(self):
        total = sum(self.costos.values())
        frac = sum(self.hecho.values()) / total if total > 0 else 0.0
        self.milesimas = max(self.milesimas, min(1000, int(frac * 1000)))
        return self.milesimas

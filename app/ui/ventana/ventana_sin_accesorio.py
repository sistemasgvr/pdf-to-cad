"""«No hay codo / T / Y / cruz» (pedido del usuario 2026-10-30): marcar que en un punto NO va el accesorio que la
app y el plugin pondrían (`nucleo/sin_accesorio`). Se puede desde «Resolver» (2D y 3D) en un conflicto causado
por un accesorio, desde la ficha de un accesorio en 3D y con clic derecho en el plano. Un paso de deshacer."""
from __future__ import annotations

from nucleo import sin_accesorio as SA
from traduccion.i18n import t as _tr
from traduccion.i18n_core import N_

TEXTO_NO_HAY = {"codo": N_("No hay codo"), "tee": N_("No hay T"), "wye": N_("No hay Y"), "cruz": N_("No hay cruz")}
TEXTO_PONER = {"codo": N_("Volver a poner el codo"), "tee": N_("Volver a poner la T"),
               "wye": N_("Volver a poner la Y"), "cruz": N_("Volver a poner la cruz")}
RADIO_CONFLICTO_FT = 10.0       # un conflicto de codos marca el tramo corto: el codo puede quedar a unos pies


def texto_no_hay(tipo):
    return _tr(TEXTO_NO_HAY.get(tipo, "No hay accesorio"))


class SinAccesorioMixin:
    def _ft_px_sa(self):
        return self.scale / self.zoom if self.scale and self.zoom else 0.0

    def accesorio_de_conflicto(self, cid):
        """El accesorio (dict) que causa el conflicto C-n `cid`, si lo hay y no está ya marcado."""
        self._resultados_al_dia()
        c = self._conflicto_por_id(cid) if hasattr(self, "_conflicto_por_id") else None
        ft = self._ft_px_sa()
        if c is None or not ft:
            return None
        if c.clave == "redes" and hasattr(self, "_con_utilidades"):
            c = self._con_utilidades(c)
        tol = SA.tol_px(ft)
        accs = SA.filtrar(getattr(self, "_accs_todos", None) or [], getattr(self, "sin_accesorio", None), tol)
        return SA.de_conflicto(accs, c, tol, RADIO_CONFLICTO_FT / ft)

    def accesorio_en(self, x, y, r_px):
        """El accesorio más cercano a (x, y) a ≤ r_px (sin los ya marcados), o None."""
        tol = SA.tol_px(self._ft_px_sa())
        cerca = [((a["x"] - x) ** 2 + (a["y"] - y) ** 2, a)
                 for a in SA.filtrar(getattr(self, "_accs_todos", None) or [], getattr(self, "sin_accesorio", None), tol)
                 if abs(a["x"] - x) <= r_px and abs(a["y"] - y) <= r_px]
        return min(cerca, key=lambda t: t[0])[1] if cerca else None

    def marcar_sin_accesorio(self, acc, conflicto=None):
        """En ese punto no va accesorio (un paso de deshacer)."""
        if acc is None:
            return False
        self._push()
        self.sin_accesorio = list(getattr(self, "sin_accesorio", None) or []) + [SA.marca(acc, conflicto)]
        self._redraw()
        aviso = getattr(self, "aviso_breve", None)
        if aviso is not None:
            aviso(texto_no_hay(acc.get("tipo")),
                  _tr("Ahí no se pondrá accesorio (ni en Civil 3D). Ctrl+Z para deshacer."))
        return True

    def quitar_sin_accesorio(self, m):
        marcas = list(getattr(self, "sin_accesorio", None) or [])
        if m not in marcas:
            return False
        self._push()
        marcas.remove(m)
        self.sin_accesorio = marcas
        self._redraw()
        return True

    def _menu_sin_accesorio(self, menu, x, y):
        """Clic derecho junto a un accesorio: «No hay …»; junto a un punto marcado: «Volver a poner …»."""
        r = 14.0 / max(self.canvas.transform().m11(), 1e-6)
        m = SA.en(getattr(self, "sin_accesorio", None), x, y, r)
        if m is not None:
            menu.addAction(_tr(TEXTO_PONER.get(m.get("tipo"), "Volver a poner el accesorio")),
                           lambda: self.quitar_sin_accesorio(m))
            menu.addSeparator()
            return
        a = self.accesorio_en(x, y, r)
        if a is not None:
            menu.addAction(texto_no_hay(a.get("tipo")), lambda: self.marcar_sin_accesorio(a))
            menu.addSeparator()

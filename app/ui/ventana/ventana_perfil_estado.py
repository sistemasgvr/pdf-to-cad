"""Textos y alertas del perfil (mezcla de `PerfilMixin`): título, por qué se cortó, barra de datos y alertas.

Movido tal cual de `ventana_perfil` (2026-11-08)."""
from __future__ import annotations

from nucleo import perfil_textos as PT
from nucleo import perfil_textos as T
from traduccion.i18n import t as _tr
from ui.comun.theme import tokens
from ui.comun.icons import icon


class EstadoPerfilMixin:
    def _perfil_titulo(self):
        d = self._perfil_datos
        if d is None:
            self.lbl_perfil.setText(_tr("Perfil longitudinal"))
            return
        nombre = getattr(self, "_perfil_nombre", None) or d.red
        if getattr(self, "_perfil_pila", None):
            nombre = _tr("Ramal de {n}").format(n=self._perfil_pila[-1][2])
        self.lbl_perfil.setText(_tr("{n} · {l} ft").format(n=nombre, l=f"{d.e_fin - d.e_ini:.1f}"))

    def _perfil_corte(self):
        """Por qué el recorrido termina donde termina (empate en una unión)."""
        rec = self._perfil_rec
        ini = rec is not None and rec.ambiguo_ini
        fin = rec is not None and rec.ambiguo_fin
        lados = (_tr("el inicio y el final") if ini and fin else _tr("el inicio") if ini
                 else _tr("el final") if fin else "")
        if not lados:
            self.lbl_perfil_corte.hide()
            return
        self.lbl_perfil_corte.setText(
            _tr("El recorrido se detiene en {l}: en esa unión hay dos caminos casi igual de rectos. "
                       "Haz clic en la ficha «A» o «B» y luego en el camino que sigue.").format(l=lados))
        self.lbl_perfil_corte.setStyleSheet(f"color: {tokens().warning};")
        self.lbl_perfil_corte.show()

    def _perfil_barra(self):
        """Barra de datos: el nodo bajo el ratón o, si no, el elegido."""
        lbl = getattr(self, "lbl_perfil_datos", None)
        if lbl is None:
            return
        d, v = getattr(self, "_perfil_datos", None), self.perfil_vista
        k = v._hover if v._hover >= 0 else v._sel_nodo
        if d is None:
            lbl.setText("")
            return
        if not (0 <= k < len(d.nodos)):
            lbl.setText(_tr("{n} tramos · {c} cruces · elige un punto (clic o ← →) para ver sus datos").format(
                n=len(d.pasos), c=len(d.cruces)))
            return
        n = d.nodos[k]
        llega = d.pasos[k - 1] if k > 0 else None
        sale = d.pasos[k] if k < len(d.pasos) else None
        ref = llega or sale
        z = llega.z1 if llega else sale.z0
        partes = [T.estacion(n.e)]
        if n.cod:
            partes.append(n.cod)
        partes.append(_tr("solera {z}").format(z=T.cota(z)))
        partes.append(_tr("corona {z}").format(z=T.cota(z + ref.alto_ft)))
        if n.rim is not None:
            partes.append(_tr("tapa {z}").format(z=T.cota(n.rim)))
        if llega:
            partes.append(_tr("llega {p}").format(p=f"{llega.pendiente * 100:+.2f} %"))
        if sale:
            partes.append(_tr("sale {p}").format(p=f"{sale.pendiente * 100:+.2f} %"))
        if not n.editable:
            partes.append(_tr("(cota no editable aquí: es una T a mitad de tramo)"))
        texto = "  ·  ".join(partes)
        al = v.alertas_de_nodo(k) + [a for i in (k - 1, k) if 0 <= i < len(d.pasos) for a in v.alertas_de_paso(i)]
        if al:
            texto += "<br><span style='color:%s'>%s</span>" % (
                tokens().danger, "  ·  ".join(dict.fromkeys(a.mensaje for a in al)))
            lbl.setText("<span>" + texto + "</span>")
        else:
            lbl.setText(texto)

    def _perfil_alertas(self):
        """Alertas del perfil (normativa del plano, recubrimiento, contrapendiente) y el botón que las cuenta."""
        d = getattr(self, "_perfil_datos", None)
        alertas = []
        if d is not None:
            from nucleo import perfil_validar
            from nucleo.model import COVER_MIN_FT
            capa = self.pipes[d.pasos[0].pipe].get("layer") or "" if d.pasos else ""
            ft = self._ft()
            tol = max(2.0 / ft, 3.0) if ft else 3.0
            try:
                alertas = perfil_validar.validar(d, getattr(self, "_normas_avisos", None) or [],
                                                 COVER_MIN_FT.get(capa), tol)
            except Exception:
                import traceback
                traceback.print_exc()
        self.perfil_vista.set_alertas(alertas)
        b = self.btn_perfil_alertas
        if alertas:
            error = any(a.nivel == "ERROR" for a in alertas)
            b.setIcon(icon("mdi:alert-outline", color=tokens().danger if error else tokens().warning))
            b.setText(_tr("{n} alertas").format(n=len(alertas)) if len(alertas) != 1 else _tr("1 alerta"))
            b.show()
        else:
            b.hide()
        self._perfil_alerta_k = -1

    def perfil_siguiente_alerta(self):
        """Elige el punto de la siguiente alerta y la explica en la barra de datos."""
        v = self.perfil_vista
        al = v.alertas
        if not al:
            return None
        self._perfil_alerta_k = (getattr(self, "_perfil_alerta_k", -1) + 1) % len(al)
        a = al[self._perfil_alerta_k]
        d = self._perfil_datos
        k = a.nodo if a.nodo >= 0 else min(range(len(d.nodos)), key=lambda i: abs(d.nodos[i].e - a.e))
        v.elegir_nodo(k)
        v.set_cursor(a.e)
        self.lbl_perfil_datos.setText(
            "<span style='color:%s'>%s</span>" % (tokens().danger if a.nivel == "ERROR" else tokens().warning,
                                                  _tr("Alerta {i} de {n} · {e} · {m}").format(
                                                      i=self._perfil_alerta_k + 1, n=len(al),
                                                      e=PT.estacion(a.e),
                                                      m=a.mensaje)))
        return a

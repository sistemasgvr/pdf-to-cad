"""Órdenes del chat de la IA (pedido del usuario 2026-10-30): la ventana PRUEBA la orden en una copia de la zona
(los mismos cálculos de «Resolver conflictos»: `SolucionesMixin._zona_de`/`_problemas`) para decir sus
consecuencias ANTES de confirmar, y la HACE en un solo paso de deshacer cuando el usuario confirma.

La interpretación (qué quiso decir el usuario) la da la IA (`ia/acciones.interpretar`); la validación, la
descripción y las consecuencias las pone la app. Nada se cambia sin la confirmación del usuario.
"""
from __future__ import annotations

import copy
from collections import Counter
from types import SimpleNamespace

from ia import acciones as AC
from ui.ventana.ventana_soluciones import _dist_seg
from nucleo import model
from nucleo import normas_catalogo, soluciones
from traduccion.i18n import t as _tr

MAX_LISTA = 4                                      # cuántos conflictos se nombran (los demás, «y N más»)
NOMBRES_VENTANAS = {"vista3d": "Vista 3D", "tabla": "Tabla de datos", "normativas": "Normativas",
                    "exportar": "Exportar", "georreferenciar": "Georreferenciar", "informe": "Informe automático"}


class AccionesIAMixin:
    # ── lo que la IA necesita saber ──
    def _ia_opciones_orden(self):
        """(materiales, tipos por capa, función tipos de una utilidad)."""
        cat = getattr(self, "normas_cat", None)
        capas = sorted({p.get("layer") or "" for p in self.pipes})
        tipos = {c: list(normas_catalogo.tipos_de(cat, c)) for c in capas if c}
        return (list(model.PIPE_MATERIALS), tipos,
                lambda i: list(normas_catalogo.tipos_de(cat, self.pipes[i].get("layer") or "")))

    def _nombre_ventana(self, clave):
        return _tr(NOMBRES_VENTANAS.get(clave, clave))

    # ── antes de confirmar ──
    def orden_preparar(self, interp, datos):
        """`interp` de `ia/acciones.interpretar` → (Orden, qué hará, [consecuencias]). Con `orden.error`, lo demás
        vacío: hay que preguntar de nuevo."""
        materiales, _tipos, tipos_de = self._ia_opciones_orden()
        o = AC.validar(interp, datos, materiales, tipos_de)
        if o.error:
            return o, "", []
        nombres = {k: self._nombre_ventana(k) for k in NOMBRES_VENTANAS}
        que = AC.describir(o, nombres)
        try:
            cons = self._orden_consecuencias(o)
        except Exception as e:                          # noqa: BLE001 (una consecuencia no calculada no bloquea)
            cons = [_tr("No pude calcular las consecuencias ({e}).").format(e=e)]
        return o, que, cons

    def _px_por_ft(self):
        return float(self.zoom) / self.scale if self.scale else 0.0

    def _orden_consecuencias(self, o):
        if not o.modifica:
            return [_tr("No cambia nada del proyecto.")]
        if o.accion == "resolver_conflicto":
            return self._consecuencias_resolver(o)
        out = []
        if o.accion == "mover_utilidad" and not self._px_por_ft():
            o.error = _tr("La escala del plano no está definida: no puedo mover en pies.")
            return []
        ft = self.scale / self.zoom if self.scale and self.zoom else 0.0
        idx = o.parametros["pipes"]
        borrar = o.accion == "borrar_utilidades"
        # la zona: las utilidades de la orden y todo lo que toca sus recuadros
        sub = set()
        for i in idx:
            pts = self.pipes[i].get("pts") or [(0, 0)]
            centro = SimpleNamespace(x=pts[len(pts) // 2][0], y=pts[len(pts) // 2][1])
            sub |= set(self._zona_de(i, centro, ft))
        sub = sorted(sub)
        antes = [self.pipes[g] for g in sub]
        f0 = self._problemas(antes, sub, ft) if ft else set()
        if borrar:
            resto = [g for g in sub if g not in set(idx)]
            f1 = self._problemas([self.pipes[g] for g in resto], resto, ft) if ft and resto else set()
        else:
            despues = copy.deepcopy(antes)
            local = {g: k for k, g in enumerate(sub)}
            AC.aplicar_a_utilidades(despues, o, self._px_por_ft(), self._con_bancoducto(idx), indices=local)
            f1 = self._problemas(despues, sub, ft) if ft else set()
        resueltos, nuevos = _diferencia(f0, f1)
        if resueltos:
            out.append(_tr("Se van {n} conflicto(s) o aviso(s): {l}").format(
                n=len(resueltos), l=self._lista_problemas(resueltos)))
        if nuevos:
            out.append(_tr("⚠ Aparecerían {n} conflicto(s) o aviso(s) nuevos: {l}").format(
                n=len(nuevos), l=self._lista_problemas(nuevos)))
        if not resueltos and not nuevos and ft:
            out.append(_tr("No cambian los conflictos ni los avisos de normativa de la zona."))
        out += self._consecuencias_propias(o, idx)
        out.append(_tr("Se puede deshacer con Ctrl+Z."))
        return out

    def _consecuencias_propias(self, o, idx):
        out = []
        if o.accion == "mover_utilidad":
            sueltas = self._unidas_en_puntas(idx)
            if sueltas:
                out.append(_tr("Sus puntas quedarían separadas de: {u}.").format(u=", ".join(sueltas)))
        if o.accion == "borrar_utilidades":
            db = [i for i in idx if self._duct_bank_for_pipe(i) is not None]
            if db:
                out.append(_tr("{n} lleva(n) bancoducto: se le quita.").format(n=len(db)))
            cc = [c for c in getattr(self, "cross_connections", None) or []
                  if int(c.get("pipe_a", -1)) in idx or int(c.get("pipe_b", -1)) in idx]
            if cc:
                out.append(_tr("Se quitan {n} conexión(es) vertical(es) aprobada(s).").format(n=len(cc)))
        if o.accion == "cambiar_diametro":
            con_db = self._con_bancoducto(idx)
            if con_db:
                out.append(_tr("{n} lleva(n) bancoducto: su diámetro no cambia.").format(n=len(con_db)))
        return out

    def _consecuencias_resolver(self, o):
        c, props = self.soluciones_de(o.parametros["conflicto"])
        if c is None:
            o.error = _tr("Ese conflicto ya no está en el dibujo.")
            return []
        pid = o.parametros.get("propuesta")
        p = next((x for x in props if x.id == pid), None) if pid else next((x for x in props if x.valida), None)
        if p is None:
            o.error = (_tr("Para {c} no hay una solución automática que lo resuelva sin crear otros problemas.")
                       if not pid else _tr("{c} no tiene la propuesta {p}.")).format(c=c.id, p=pid)
            return []
        o.parametros["_propuesta"] = p
        out = [_tr("Se hará: {p}").format(p=p.texto)]
        if p.valida:
            out.append(_tr("La app la probó: resuelve {c} sin crear otros problemas.").format(c=c.id))
            if p.otros_resueltos:
                out.append(_tr("Además resuelve {n} problema(s) más.").format(n=p.otros_resueltos))
        else:
            out.append(_tr("⚠ La app la probó y no queda limpia: {r}").format(
                r="; ".join(p.nuevos[:3]) or _tr("no resuelve el conflicto")))
        out.append(_tr("Se puede deshacer con Ctrl+Z."))
        return out

    def _con_bancoducto(self, idx):
        return [i for i in idx if self._duct_bank_for_pipe(i) is not None]

    def _unidas_en_puntas(self, idx):
        """Códigos de las utilidades que tocan las puntas de las que se mueven (se separarían)."""
        ft = self.scale / self.zoom if self.scale and self.zoom else 0.0
        tol = (0.5 / ft) if ft else 3.0
        mover = set(idx)
        out = []
        for i in idx:
            pts = self.pipes[i].get("pts") or []
            for q in pts[:1] + pts[-1:]:
                for j in self._utilidades_cerca(q[0], q[1], tol, todas=True):   # candidatas: se mide aquí
                    if j in mover:
                        continue
                    qs = self.pipes[j].get("pts") or []
                    if not any(_dist_seg(q, qs[k], qs[k + 1]) <= tol for k in range(len(qs) - 1)):
                        continue
                    cod = soluciones.codigo(self.pipes, j)
                    if cod not in out:
                        out.append(cod)
        return out

    def _lista_problemas(self, firmas):
        from ui.ventana.ventana_soluciones import _describir
        cuenta = Counter(_describir(f, self.pipes) for f in firmas)       # los iguales juntos: «… ×3»
        textos = [f"{t_} ×{n}" if n > 1 else t_ for t_, n in list(cuenta.items())[:MAX_LISTA]]
        resto = len(cuenta) - len(textos)
        return "; ".join(textos) + (" " + _tr("y {n} más").format(n=resto) if resto > 0 else "")

    # ── confirmado: hacerlo ──
    def orden_ejecutar(self, o):
        """Hace la orden ya confirmada. Devuelve el mensaje para el chat."""
        a, pr = o.accion, o.parametros
        if a == "ir_a":
            ref = (self._ia_datos().ref(pr["codigo"]) if hasattr(self, "_ia_datos") else None)
            if ref is None:
                return _tr("No encontré «{c}».").format(c=pr["codigo"])
            self._ir_a_elemento(ref["x"], ref["y"], "pipe" if ref["objeto"] == "pipe" else None, ref["indice"],
                                activar=False)
            return _tr("Listo: el plano muestra {c}.").format(c=pr["codigo"].upper())
        if a == "abrir":
            {"vista3d": self.abrir_vista3d, "tabla": self.abrir_tabla_datos, "normativas": self.open_normativas,
             "exportar": self.abrir_exportar, "georreferenciar": self.open_georef,
             "informe": self.generar_informe}[pr["ventana"]]()
            return _tr("Abrí {v}.").format(v=self._nombre_ventana(pr["ventana"]))
        if a == "resolver_conflicto":
            p = pr.get("_propuesta")
            if p is None or not self.aplicar_propuesta(p):
                return _tr("No se pudo aplicar la propuesta.")
            return _tr("Hecho: {p} (Ctrl+Z para deshacer).").format(p=p.texto)
        idx = pr["pipes"]
        self._push()
        if a == "borrar_utilidades":
            self._delete_pipes(idx)
        else:
            if a == "mover_utilidad":                    # los buzones y curvas de sus vértices van con ella
                pf = self._px_por_ft()
                dx, dy = pr["dx_ft"] * pf, -pr["dy_ft"] * pf
                for i in idx:
                    for (x, y) in self.pipes[i].get("pts") or []:
                        self._drag_structures_at((x, y), dx, dy)
            AC.aplicar_a_utilidades(self.pipes, o, self._px_por_ft(), self._con_bancoducto(idx))
        self._dirty = True
        self._refresh_lists()
        self._redraw()
        return _tr("Hecho: {q} (Ctrl+Z para deshacer).").format(q=AC.describir(o).rstrip("."))


def _clave(f):
    """Un conflicto por QUÉ es y entre QUIÉNES (no por dónde): al mover una utilidad su conflicto se corre."""
    return (f[0], f[1]) if f[1] else f


def _diferencia(f0, f1):
    a, b = Counter(_clave(f) for f in f0), Counter(_clave(f) for f in f1)
    por0 = {}
    for f in f0:
        por0.setdefault(_clave(f), f)
    por1 = {}
    for f in f1:
        por1.setdefault(_clave(f), f)
    resueltos = [por0[k] for k in (a - b) for _ in range((a - b)[k])]
    nuevos = [por1[k] for k in (b - a) for _ in range((b - a)[k])]
    return resueltos, nuevos



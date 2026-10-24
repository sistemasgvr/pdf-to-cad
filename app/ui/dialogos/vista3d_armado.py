"""Armar la escena de la Vista 3D (mezcla de `Vista3DDialog`).

Pedido del usuario 2026-10-20 (16 761 utilidades: «al cambiar diámetros y pendientes se lagea»):
  • ARMADO COMPLETO en un PROCESO aparte (`ui/comun/proceso`, trabajador «vista3d»; ~100 s con AGUA 2):
    antes iba en un hilo que peleaba el GIL con la ventana. Los datos van como UNA copia en bytes (pickle,
    ~0.3 s; antes `deepcopy` + json ~1.5 s) y su huella es el hash de esos bytes. Un cambio nuevo CANCELA el
    armado en curso; mientras el plano calcula conflictos y avisos (`win._provisional`) se espera a que
    termine (si no, se armaría dos veces).
  • PARCHE LOCAL inmediato (`parche_local` → `nucleo/modelo3d_parche`): al editar desde 3D se rehacen solo
    la utilidad, sus vecinas, sus accesorios y sus buzones (~0.15–0.3 s con AGUA 2), con los mismos números
    que el armado completo. El completo llega después y pone al día avisos, conflictos y el suelo.
Con `PDFCAD_PROCESO=0` (pruebas) el armado va en un hilo, como antes.
"""
from __future__ import annotations

import copy
import hashlib
import pickle

from nucleo import conexiones_verticales, modelo3d
from nucleo import modelo3d_parche as MP
from traduccion.i18n import t as _tr
from ui.comun import busy, proceso
from ui.comun.ui_common import layer_qcolor

TRABAJADOR = "vista3d"
SIN_SUELO = -100000.0


class ArmadoMixin:
    # ── datos ──
    def _colores(self):
        out = {}
        for p in self.win.pipes:
            capa = p.get("layer")
            if capa not in out:
                c = layer_qcolor(capa)
                out[capa] = (c.redF(), c.greenF(), c.blueF())
        return out

    def _datos(self, copiar=True, pipes=None):
        """Lo que necesita `modelo3d.construir`. `copiar=False`: las listas del proyecto tal cual (quien las
        use NO las cambia: el pickle del armado o el parche); `pipes` = otra lista de utilidades (vista previa)."""
        w = self.win
        pipes = w.pipes if pipes is None else pipes
        ft = w.scale / w.zoom if w.scale and w.zoom else 0.0
        dbs = [dict(name=d.name, width_in=d.width_in, height_in=d.height_in,
                    conduits=[c.to_dict() for c in d.conduits], pipes=list(d.assigned()))
               for d in getattr(w, "duct_banks", []) or []]
        avisos = [dict(x=a.x, y=a.y, clase=a.clase, mensaje=a.mensaje, pipe=a.pipe, info=a.info,
                    aprobado=bool(a.aprobado))
                  for a in getattr(w, "_normas_avisos", []) or []]
        conflictos = [dict(id=c.id, titulo=c.titulo, x=c.x, y=c.y, mensaje=c.mensaje, pipes=list(c.pipes),
                           cotas=list(c.cotas)) for c in getattr(w, "_conflictos", []) or []]
        suelo = None if self.spn_suelo.value() <= SIN_SUELO else self.spn_suelo.value()
        cruces = copy.deepcopy(getattr(w, "cross_connections", []) or [])
        conexiones_verticales.actualizar_cotas(pipes, cruces)      # con las cotas actuales
        return dict(pipes=copy.deepcopy(pipes) if copiar else pipes,
                    structures=copy.deepcopy(w.structures) if copiar else w.structures, ft=ft,
                    colores=self._colores(), duct_banks=dbs, cruces=cruces,
                    avisos=avisos, conflictos=conflictos,
                    ocultas=[c for c, chk in self._capas.items() if not chk.isChecked()],
                    ver=dict({k: c.isChecked() for k, c in self.chk.items()}, rotulos=True), suelo_z=suelo)

    def programar(self):
        """El plano cambió: actualizar en un momento (agrupa cambios seguidos)."""
        self._cajas_parche = None                           # la geometría pudo cambiar
        if self.isVisible():
            self._t.start()

    def _capa_carga(self, encender, detalle=""):
        """Capa «Cargando…» con la barra de avance sobre el visor mientras se arma la PRIMERA escena
        (pedido del usuario 2026-10-20: con miles de utilidades tardaba ~30 s sin decir nada). Solo
        tapa el visor; el plano y el panel siguen usables (sin reloj de arena en toda la app)."""
        ov = busy.overlay_for(self.pila)
        if encender and not self._cargando:
            self._cargando = True
            ov.begin(_tr("Armando la vista 3D…"), detalle, cursor=False)
        elif encender:
            ov.step(detail=detalle, pump=False)
        elif self._cargando:
            self._cargando = False
            ov.end()

    def _avance(self, texto, milesimas):
        """Avance del armado (`nucleo/avance3d`): barra y porcentaje."""
        pct = milesimas // 10
        if self._cargando:
            busy.overlay_for(self.pila).step(detail=_tr("{etapa} · {p} %").format(etapa=texto, p=pct),
                                             done=milesimas, total=1000, pump=False)
        self.lbl_estado.setText(_tr("Actualizando la vista 3D… {p} %").format(p=pct))

    # ── armado completo ──
    def actualizar(self, forzar=False):
        w = self.win
        if not self._primera and getattr(w, "_provisional", False) and not forzar:
            self._t.start()                                 # el plano aún calcula avisos: esperar a que termine
            return
        if self._primera and self._trabajo is None:
            self._capa_carga(True, _tr("Preparando los datos…"))
        capas = {}
        for p in w.pipes:
            capas[p.get("layer")] = capas.get(p.get("layer"), 0) + 1
        self._capas_visibles(capas)
        datos = pickle.dumps(self._datos(copiar=False), pickle.HIGHEST_PROTOCOL)
        firma = hashlib.blake2b(datos, digest_size=20).hexdigest()
        if firma == self._firma and not forzar:
            self._capa_carga(False)
            return
        if self._trabajo is not None:
            if self._trabajo_firma == firma and not forzar:
                return                                      # ya se está armando esto mismo
            viejo, self._trabajo = self._trabajo, None
            viejo.cancelar()                                # un cambio nuevo: el armado anterior ya no sirve
        self.lbl_estado.setText(_tr("Actualizando la vista 3D…"))
        tarea = proceso.Tarea("nucleo.modelo3d:construir_datos", (datos,))
        tarea.avance.connect(self._avance_tarea)
        tarea.terminado.connect(lambda res, err, t=tarea, f=firma: self._terminado(t, res, err, f))
        self._trabajo, self._trabajo_firma = tarea, firma
        proceso.trabajador(TRABAJADOR).enviar(tarea)

    def _avance_tarea(self, msg):
        if isinstance(msg, tuple) and len(msg) >= 3 and msg[0] == "detalle":
            self._avance(str(msg[1]), int(msg[2] or 0))

    def _terminado(self, tarea, escena, error, firma):
        if tarea is not self._trabajo or error == "cancelado":
            return                                          # uno viejo (cancelado)
        if error:
            print("[vista3d] el armado falló:" + chr(10) + str(error))
            escena = modelo3d.Escena()                      # nunca tumbar la app por la vista 3D
        self._listo(escena, firma)

    def _listo(self, escena, firma):
        self._trabajo = None
        self._firma = firma
        self.escena = escena
        self._cajas_parche = None
        self.spn_suelo.auto = float(escena.suelo_z or 0.0)
        if self._cargando:                                    # la tarjeta de video recibe la escena
            ov = busy.overlay_for(self.pila)
            ov.step(detail=_tr("Mostrando la escena…"), done=1000, total=1000, pump=False)
            ov.repaint()
        self.pila.setCurrentIndex(1 if escena.vacia else 0)
        self.visor.set_escena(escena, encuadrar=self._primera and not escena.vacia)
        self._capa_carga(False)
        if not escena.vacia:
            self._primera = False
        self._ficha_id = None                                 # los datos pudieron cambiar
        self.seleccion_del_plano(encuadrar=False)
        self._resumen()
        if self.visor.error:
            self.lbl_vacio.setText(_tr("No se pudo iniciar la vista 3D (OpenGL 2.1): {e}").format(e=self.visor.error))
            self.pila.setCurrentIndex(1)

    # ── parche local (editar desde 3D) ──
    def parche_local(self, cambios):
        """Rehace en la escena SOLO las utilidades `cambios` = {índice: utilidad (dict)} —una copia con lo que
        se está editando, o None = la del proyecto— y lo que depende de ellas. Devuelve True si se aplicó."""
        w = self.win
        if self.escena is None or self.escena.vacia or not cambios:
            return False
        pipes = list(w.pipes)
        for i, p in cambios.items():
            if p is not None and 0 <= i < len(pipes):
                pipes[i] = p
        d = self._datos(copiar=False, pipes=pipes)
        if self._cajas_parche is None or len(self._cajas_parche) != len(pipes):
            self._cajas_parche = MP._cajas(pipes)
        try:
            nueva = MP.parche(self.escena, pipes, d["structures"], d["ft"], set(cambios), d["colores"],
                              d["duct_banks"], d["cruces"], d["ocultas"], d["ver"], cajas=self._cajas_parche)
        except Exception as e:                               # el armado completo lo pondrá al día
            print("[vista3d] parche:", e)
            return False
        if nueva is None:
            return False
        self.escena = nueva
        self._firma = None                                  # el próximo armado completo no se salta
        self.visor.set_escena(nueva)
        return True

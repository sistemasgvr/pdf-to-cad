"""Página «Reconocer» del riel: conecta el panel (`ui/comun/panel_reconocer.py`) con el estado de las filas
(`nucleo.reconocer_estado`, `Main.reconocer_estado`) y con los trabajos.

El ▶, ▶ Todo y Cancelar están en `ventana_reconocer_cola` (Tarea 6), el 👁 en `ventana_reconocer_vista` (Tarea 7),
«Capas y estilos…» en `ventana_capas_estilos` (Tarea 8) e «Interpretar la hoja» en `ventana_interpretar` (Tarea 9),
del plan `docs/superpowers/plans/2026-11-16-reconocimiento-desde-el-editor.md`.
"""
from nucleo import reconocer_estado as RE
from ui.ventana.ventana_capas_estilos import CapasEstilosMixin
from ui.ventana.ventana_interpretar import InterpretarMixin
from ui.ventana.ventana_reconocer_cola import ReconocerColaMixin
from ui.ventana.ventana_reconocer_vista import ReconocerVistaMixin


def panel_reconocer(win):
    """La página del riel (la arma `ShellMixin._build_shell`)."""
    from ui.comun.panel_reconocer import PanelReconocer
    p = PanelReconocer()
    win.panel_reconocer = p
    if getattr(win, "reconocer_estado", None) is None:
        win.reconocer_estado = RE.nuevo()
    p.reproducir.connect(win._reconocer_desde_panel)
    p.ver.connect(win._ver_desde_panel)
    p.capas.connect(win._capas_desde_panel)
    p.ajustar.connect(win._ajustar_desde_panel)
    p.unir_tramos.connect(win._unir_tramos_parte)
    p.rotulos_ia.connect(win._rotulos_ia_desde_panel)
    p.todo.connect(win._todo_desde_panel)
    p.cancelar.connect(win._cancelar_desde_panel)
    p.interpretar.connect(win._interpretar_desde_panel)
    p.por_verificar.connect(win._por_verificar_desde_panel)
    p.ir_a_verificar.connect(win._verificar_ir)
    p.visto.connect(win._verificar_visto)
    p.aviso.connect(win._aviso_reconocer)
    win._refrescar_panel_reconocer()
    return p


class ReconocerMixin(ReconocerColaMixin, ReconocerVistaMixin, CapasEstilosMixin, InterpretarMixin):
    reconocer_estado = None          # nucleo.reconocer_estado.Estado (la crea `panel_reconocer`)
    _reconocer_ultimo = None         # (parte, cuántos) de lo último reconocido: pie del panel

    @property
    def avisos_diametro(self) -> bool:
        """`reconocer_estado.avisos_diametro`: los avisos de diámetro solo con «Diámetros» reconocido."""
        return RE.avisos_diametro(getattr(self, "reconocer_estado", None))

    def _refrescar_panel_reconocer(self):
        p = getattr(self, "panel_reconocer", None)
        if p is None:
            return
        if self.reconocer_estado is None:
            self.reconocer_estado = RE.nuevo()
        interp = getattr(self, "_interpretacion", None) or {}
        capas = list(interp.get("layers") or [])
        estilos = bool(capas) and all(c.get("source") == "style" for c in capas)
        p.mostrar(self.reconocer_estado, ultimo=self._reconocer_ultimo,
                  escaneo=bool(getattr(self, "_reconocer_escaneo", False)),
                  unidad_capas="estilos" if estilos else "capas",
                  interpretando=bool(getattr(self, "_interp_tarea", None) is not None),
                  diametros=self._diametros_por_revisar())

    def _diametros_por_revisar(self):
        """(dudosas, sin dato): tuberías con el aviso «Diámetro del plano» (`diametro_plano.avisos`: el plano no dijo
        su diámetro con certeza y siguen con el de por defecto). Solo si alguna utilidad ya está reconocida."""
        e = self.reconocer_estado
        if not any(e.filas[u].estado in ("reconocida", "desactualizada") for u in RE.UTILIDADES):
            return None
        if not RE.avisos_diametro(e):                    # aún sin reconocer «Diámetros»: no hay avisos
            return None
        from nucleo import diametro_plano
        pipes = self.pipes or []
        dudosas = sin_dato = 0
        for a in diametro_plano.avisos(pipes):
            if (pipes[a.pipe].get("diam_plano") or {}).get("estado") == "dudoso":
                dudosas += 1
            else:
                sin_dato += 1
        return dudosas, sin_dato

    # ── señales del panel → métodos (los de la ventana se pueden cambiar en pruebas) ──
    def _reconocer_desde_panel(self, parte):
        self.reconocer_parte(parte)

    def _ver_desde_panel(self, parte):
        self.ver_parte(parte)

    def _capas_desde_panel(self, parte):
        self.abrir_capas_estilos(parte)

    def _ajustar_desde_panel(self, parte):
        self.ajustar_capas_parte(parte)

    def _rotulos_ia_desde_panel(self):
        self.leer_anotaciones_con_ia()

    def _todo_desde_panel(self):
        self.reconocer_todo()

    def _cancelar_desde_panel(self):
        self.cancelar_reconocer()

    def _interpretar_desde_panel(self):
        self._interpretar_hoja()

    def _por_verificar_desde_panel(self):
        self.ir_a_por_verificar()

    def _aviso_reconocer(self, motivo):
        """Por qué un ▶ o un 👁 no hace nada: en la barra de estado (como `ventana_dibujar._bloqueado`)."""
        if hasattr(self, "_info"):
            self._info(motivo)

    def _unir_tramos_parte(self, parte, unir):
        """«Unir tramos» de una utilidad: se guarda en su fila (el ▶ lo usa). Si ya estaba reconocida, cambia lo que
        daría: la fila queda «Cambió · reconocer de nuevo»."""
        if self.reconocer_estado is None or parte not in self.reconocer_estado.filas:
            return
        self.reconocer_estado.filas[parte].unir_tramos = bool(unir)
        RE.marcar_cambios(self.reconocer_estado, {parte: self._firma_parte_actual(parte)})
        self._refrescar_panel_reconocer()

    # ── deshacer / rehacer (`Main._snap_state` / `_restore`) ──
    def _rec_para_deshacer(self):
        """Lo del panel que va en cada paso de deshacer: solo el estado de las filas (los resultados no)."""
        e = getattr(self, "reconocer_estado", None)
        if e is None:
            return None
        d = RE.a_dict(e)
        act = getattr(self, "_rec_actual", None)          # el paso de ANTES de un ▶ se toma con su fila corriendo
        fila = d["filas"].get((act or {}).get("parte"))
        if fila is not None and fila["estado"] == "reconociendo":
            fila["estado"] = act.get("previo") or "pendiente"
        return d

    def _rec_al_deshacer(self, d):
        """Deshacer un ▶ quita sus líneas: su fila vuelve a como estaba en ese paso. Solo lo que cambia un ▶ (reconocida
        o no, firma, cuántos, «para verificar»); bloqueos y «unir tramos» son los de ahora. De otra hoja, o con un ▶
        en curso, no se toca."""
        e = getattr(self, "reconocer_estado", None)
        if not isinstance(d, dict) or e is None or getattr(self, "_rec_actual", None) is not None:
            return
        if d.get("firma_hoja") != e.firma_hoja:
            return
        antes = RE.de_dict(d)
        hechas = ("reconocida", "desactualizada")
        cambiadas = []
        for p, f in e.filas.items():
            g = antes.filas.get(p)
            if g is None or f.estado == "reconociendo" or (f.estado not in hechas and g.estado not in hechas):
                continue
            if g.estado in hechas:
                if (f.estado, f.firma, f.hechos) == (g.estado, g.firma, g.hechos):
                    continue
                f.estado, f.firma, f.hechos, f.verificar = g.estado, g.firma, g.hechos, list(g.verificar)
            else:
                f.estado = "bloqueada" if f.motivo else "pendiente"
                f.firma, f.hechos, f.verificar = None, 0, []
            cambiadas.append(p)
        if not cambiadas:
            return
        RE.marcar_cambios(e, {p: self._firma_parte_actual(p) for p in cambiadas})
        res = getattr(self, "_resultados_partes", None)
        if res:
            for u in [u for u in res if u in e.filas and e.filas[u].estado not in hechas]:
                del res[u]                                # las válvulas y los diámetros ya no la usan
        self._refrescar_panel_reconocer()

    # ── trabajos: ▶ en `ventana_reconocer_cola` (T6), 👁 y «Para verificar» en `ventana_reconocer_vista` (T7),
    #    «Capas y estilos…» en `ventana_capas_estilos` (T8), interpretar la hoja en `ventana_interpretar` (T9) ──

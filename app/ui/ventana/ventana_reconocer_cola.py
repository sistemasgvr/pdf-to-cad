"""▶ y ▶ Todo del panel «Reconocer» en segundo plano (plan 2026-11-16, «reconocimiento desde el editor», Tarea 6).

Cada ▶ reconoce UNA parte de la hoja del editor (una utilidad, las válvulas, los diámetros o los rótulos) con
`recognition_trabajo.reconocer_parte` en el trabajador «reconocer» (`proceso.RETENEDOR`: la lectura de la hoja queda
retenida ahí y la reusan todos los ▶) y el resultado entra solo al plano con `importar_parte` (encima de lo dibujado,
sin repetir, UN paso de deshacer), sin vista previa. Mientras corre: la tarjeta de avance y las líneas provisionales
del asistente (`_avance_reconocer`), se puede acercar y desplazar el plano pero no editar.

  · Un ▶ a la vez; ▶ Todo = cola en el orden de `reconocer_estado.orden_todo`, y cada fila se vuelve a mirar
    (`puede`) cuando le toca: si el agua falló, las válvulas ya no se pueden.
  · Los resultados de cada parte quedan en la memoria de la ventana (`_resultados_partes`, nunca en el .digproj):
    válvulas, diámetros y rótulos se reconocen junto a los de las utilidades ya reconocidas; si falta alguno (tras
    reabrir el proyecto), esa utilidad se reconoce de nuevo en el trabajador SIN importarla.
  · Caché por parte (`recognition_cache.clave_parte`): un ▶ repetido sin cambios no pide otro trabajo.
  · Volver a reconocer una utilidad ya reconocida pregunta: reemplazar lo de esa utilidad o agregar lo que falta.
  · Cancelar mata el trabajo, la fila vuelve a como estaba y el editor no se toca. Lo que llega tarde (de un ▶
    cancelado, o de antes de abrir otro proyecto / cambiar de hoja) se descarta por la generación
    (`_recog_generation`, la del asistente).
"""
from __future__ import annotations

import copy
import hashlib
from types import SimpleNamespace

from PySide6 import QtCore

from nucleo import reconocer_estado as RE
from reconocimiento import recognition_cache
from traduccion.i18n import t as _tr
from traduccion.i18n_core import N_

OBJETIVO = "reconocimiento.recognition_trabajo:reconocer_parte"
DEPENDIENTES = ("VALVULAS", "DIAMETROS", "ROTULOS")
MAX_CACHE_PARTES = 24
M_FALLO = N_("No se pudo reconocer.")
M_CANCELADO = N_("Reconocimiento cancelado — el editor queda como estaba.")
_HECHAS = ("reconocida", "desactualizada")


class ReconocerColaMixin:
    _rec_actual = None               # el ▶ en curso: {parte, previo, firma, firma_parte, clave, reemplazar, pasos, tarea, gen}
    _rec_cola = ()                   # lo que falta de ▶ Todo (lista propia de cada ▶ Todo)
    _rec_avance_abierto = False      # la tarjeta de avance es de este ▶ (y no del asistente)
    _resultados_partes = None        # {parte: resultado} de esta hoja (memoria de la ventana)
    _cache_partes = None

    # ── API ──────────────────────────────────────────────────────────────
    def reconocer_parte(self, parte, importar=True, ver=False):
        """Reconoce `parte` en segundo plano e importa el resultado. Sin `importar` (el 👁 sin resultado) solo lo
        reconoce, sin tocar el editor ni la fila; con `ver` abre después la vista previa (`ventana_reconocer_vista`)."""
        parte = str(parte).strip().upper()
        if self._rec_actual is not None:
            self._aviso_reconocer(_tr(RE.M_RECONOCIENDO))
            return
        self._rec_cola = []
        if not self._rec_lanzar(parte, en_todo=False, importar=importar, ver=ver):
            self._rec_fin_cola()

    def reconocer_todo(self):
        """Reconoce en cola: utilidades → válvulas → diámetros → rótulos (`reconocer_estado.orden_todo`)."""
        if self._rec_actual is not None:
            self._aviso_reconocer(_tr(RE.M_RECONOCIENDO))
            return
        self._rec_cola = list(RE.orden_todo(self._rec_estado()))
        if not self._rec_cola:
            self._aviso_reconocer(_tr("No hay nada que reconocer en la hoja."))
            return
        self._rec_siguiente()

    def cancelar_reconocer(self):
        """Cancela el ▶ en curso (y lo que quedaba de ▶ Todo): la fila vuelve a como estaba, el editor no cambia."""
        self._rec_cola = []
        act, self._rec_actual = self._rec_actual, None
        if act is None:
            return
        self._rec_volver_fila(act)
        t = act.get("tarea")
        if t is not None and not t.hecha:
            t.cancelar()
        self._rec_fin_cola()
        self._info(_tr(M_CANCELADO))

    def _rec_interrumpido(self):
        """La tarjeta de avance del ▶ la cierra otro (el asistente de siempre empieza a reconocer): el ▶ se cancela
        como con Cancelar, sin cerrar la tarjeta (la cierra quien la pidió)."""
        self._rec_avance_abierto = False
        self._rec_cola = []
        act, self._rec_actual = self._rec_actual, None
        if act is None:
            return
        self._rec_volver_fila(act)
        t = act.get("tarea")
        if t is not None and not t.hecha:
            t.cancelar()

    def _soltar_reconocer(self):
        """Otro proyecto u otra hoja: el ▶ en curso se cancela, lo que llegue tarde se descarta y los resultados y el
        estado de las filas de la hoja anterior ya no valen."""
        self._recog_generation = getattr(self, "_recog_generation", 0) + 1
        self._rec_cola = []
        act, self._rec_actual = self._rec_actual, None
        if act is not None:
            t = act.get("tarea")
            if t is not None and not t.hecha:
                t.cancelar()
            self._rec_fin_cola()
        self._resultados_partes = {}                     # objetos NUEVOS (no `clear`): «Cancelar» del asistente
        self._cache_partes = None                        # repone los de antes (`respaldo_editor.CLAVES`)
        if hasattr(self, "cancelar_interpretacion"):     # la interpretación de la hoja anterior (ventana_interpretar)
            self.cancelar_interpretacion(aviso=False)
            self._soltar_rec_hoja()
        self._interpretacion = None
        self._reconocer_escaneo = False
        if getattr(self, "reconocer_estado", None) is not None:
            self.reconocer_estado = RE.nuevo()
            self._refrescar_panel_reconocer()

    def _preguntar_reemplazo(self, parte):
        """Volver a reconocer una utilidad ya reconocida → "reemplazar" | "agregar" | None (cancelar). Sin la ventana
        a la vista (pruebas) agrega: nunca se pierde lo editado sin preguntar."""
        if not self.isVisible():
            return "agregar"
        from PySide6 import QtWidgets
        nombre = _tr(RE.ETIQUETAS.get(parte, parte))
        box = QtWidgets.QMessageBox(self)
        box.setIcon(QtWidgets.QMessageBox.Question)
        box.setWindowTitle(_tr("Reconocer de nuevo"))
        box.setText(_tr("{u} ya está reconocida. ¿Qué hago con lo que ya está en el plano?").format(u=nombre))
        box.setInformativeText(_tr("Reemplazar quita las líneas reconocidas de {u}, también los cambios que les "
                                   "hiciste. Lo dibujado a mano no se toca.").format(u=nombre))
        b_reemplazar = box.addButton(_tr("Reemplazar lo reconocido"), QtWidgets.QMessageBox.DestructiveRole)
        b_agregar = box.addButton(_tr("Agregar solo lo que falta"), QtWidgets.QMessageBox.AcceptRole)
        box.addButton(_tr("Cancelar"), QtWidgets.QMessageBox.RejectRole)
        box.setDefaultButton(b_agregar)
        box.exec()
        return {id(b_reemplazar): "reemplazar", id(b_agregar): "agregar"}.get(id(box.clickedButton()))

    # ── firmas y caché ───────────────────────────────────────────────────
    def _firma_hoja_actual(self):
        """La lectura de la hoja (la misma que pone la interpretación, Tarea 9): composición, PDF de origen, hoja y
        capas ocultas. Con una utilidad agregada (`_rec_hoja`, ventana_agregar) la de su hoja."""
        ov = getattr(self, "_rec_hoja", None)
        if ov is not None:
            return ov["firma"]
        documento = (self._src_fingerprints(self.src_pdfs) if self.src_pdfs
                     else ("path", self.work_pdf_path or self.pdf_path))
        datos = (recognition_cache.composition_signature(self.composite), recognition_cache.freeze(documento),
                 int(self.page_idx), tuple(sorted(self.hidden_ocgs or ())))
        return hashlib.sha1(repr(datos).encode("utf-8")).hexdigest()

    def _firma_lectura(self):
        e = self._rec_estado()
        return e.firma_hoja or self._firma_hoja_actual()

    def _firma_parte_actual(self, parte):
        """`reconocer_estado.firma_parte` con lo que hoy decide el resultado de `parte`: una utilidad solo con lo suyo
        (`firma_utilidad`); válvulas, diámetros y rótulos con todo (además dependen de las utilidades por `previas`)."""
        roles = self._roles_de_la_hoja(self.page_idx)
        if parte in RE.UTILIDADES:
            capas = (getattr(self, "_interpretacion", None) or {}).get("layers")
            return RE.firma_utilidad(parte, self.hidden_ocgs, roles, self._letters_off, self._scale_override,
                                     self._rec_unir(parte), capas=capas)
        return RE.firma_parte(parte, self.hidden_ocgs, roles, self._letters_off, self._scale_override,
                              self._rec_unir(parte))

    def _rec_cache(self):
        if self._cache_partes is None:
            self._cache_partes = recognition_cache.RecognitionCache(MAX_CACHE_PARTES)
        return self._cache_partes

    def _rec_clave(self, parte, firma, firma_parte):
        previas = ()
        if parte in DEPENDIENTES:
            e = self._rec_estado()
            previas = tuple((u, e.filas[u].firma) for u in RE.UTILIDADES if e.filas[u].estado in _HECHAS)
        return recognition_cache.clave_parte(firma, parte, firma_parte, self.zoom, self._scale_override, previas)

    def _rec_estado(self):
        if getattr(self, "reconocer_estado", None) is None:
            self.reconocer_estado = RE.nuevo()
        return self.reconocer_estado

    def _rec_unir(self, parte):
        f = self._rec_estado().filas.get(parte)
        return bool(f.unir_tramos) if parte in RE.UTILIDADES and f is not None else bool(self._join_routes)

    # ── cola ─────────────────────────────────────────────────────────────
    def _rec_siguiente(self):
        while self._rec_cola and self._rec_actual is None:
            if self._rec_lanzar(self._rec_cola.pop(0), en_todo=True):
                return
        if self._rec_actual is None:
            self._rec_fin_cola()

    def _rec_lanzar(self, parte, en_todo, importar=True, ver=False) -> bool:
        """Empieza `parte` → True si quedó corriendo en el trabajador (de la caché o sin poder: False)."""
        from ui.comun.panel_reconocer import texto_motivo
        estado = self._rec_estado()
        if parte not in estado.filas:
            return False
        ok, clave, datos = RE.puede(estado, parte)
        if not ok:
            if not en_todo:
                self._aviso_reconocer(texto_motivo(clave, datos))
            return False
        fila = estado.filas[parte]
        firma_parte = self._firma_parte_actual(parte)
        if en_todo and fila.estado == "reconocida" and fila.firma == firma_parte:
            return False                                 # ▶ Todo: ya está y nada cambió
        reemplazar = False
        if importar and parte in RE.UTILIDADES and fila.estado in _HECHAS:
            r = self._preguntar_reemplazo(parte)
            if r is None:
                return False
            reemplazar = r == "reemplazar"
        firma = self._firma_lectura()
        act = {"parte": parte, "previo": fila.estado, "motivo": fila.motivo, "firma": firma,
               "firma_parte": firma_parte, "reemplazar": reemplazar, "tarea": None, "gen": None,
               "importar": bool(importar), "ver": bool(ver),
               "clave": self._rec_clave(parte, firma, firma_parte)}
        guardado = self._rec_cache().get(act["clave"])
        if guardado is not None:
            self._info(_tr("Sin cambios: se usa el reconocimiento anterior."))
            self._rec_actual = act
            self._rec_hecho(act, copy.deepcopy(guardado[0]))    # importar cambia el resultado: una copia
            return False
        act["pasos"] = [(u, False) for u in self._rec_faltan(parte)] + [(parte, True)]
        fila.estado = "reconociendo"
        self._rec_actual = act
        self._refrescar_panel_reconocer()
        self._rec_correr()
        return self._rec_actual is act

    def _rec_faltan(self, parte):
        """Utilidades reconocidas sin resultado en memoria (tras reabrir): hay que reconocerlas antes, sin importar."""
        if parte not in DEPENDIENTES:
            return []
        if self._resultados_partes is None:
            self._resultados_partes = {}
        e, faltan = self._rec_estado(), []
        for u in RE.UTILIDADES:
            if e.filas[u].estado not in _HECHAS or u in self._resultados_partes:
                continue
            guardado = self._rec_cache().get(self._rec_clave(u, self._firma_lectura(), self._firma_parte_actual(u)))
            if guardado is not None:
                self._resultados_partes[u] = copy.deepcopy(list(guardado[0] or []))
            else:
                faltan.append(u)
        return faltan

    def _rec_previas(self):
        e, res = self._rec_estado(), self._resultados_partes or {}
        return [r for u in RE.UTILIDADES if e.filas[u].estado in _HECHAS for r in (res.get(u) or [])]

    # ── trabajo ──────────────────────────────────────────────────────────
    def _rec_kwargs(self, paso):
        from ui.comun import proceso
        kw = dict(zoom=self.zoom, hidden_ocgs=tuple(self.hidden_ocgs or ()),
                  roles_by_utility=self._roles_de_la_hoja(self.page_idx),
                  letters_off=tuple(sorted(self._letters_off or ())), join_routes=self._rec_unir(paso),
                  scale_ft_per_pt=self._scale_override)
        if paso in DEPENDIENTES:
            previas = self._rec_previas()
            if paso == "DIAMETROS":
                kw["perfiles_de"] = tuple(self._perfiles_de())
                if not proceso.activo():
                    previas = copy.deepcopy(previas)     # los diámetros cambian los resultados (sin proceso: aquí)
            kw["resultados_previos"] = previas
        return kw

    def _rec_correr(self):
        """El primer paso pendiente del ▶ en curso, al trabajador «reconocer»."""
        from ui.comun import proceso
        act = self._rec_actual
        paso = act["pasos"][0][0]
        ruta, hoja = self._rec_ruta_hoja()
        t = proceso.Tarea(OBJETIVO, args=(ruta, hoja, paso, act["firma"]), kwargs=self._rec_kwargs(paso))
        if not ruta:                                     # la hoja de la utilidad agregada no se pudo armar
            act["tarea"], act["gen"] = t, self._recog_generation
            self._rec_terminado(t, self._recog_generation, None,
                                _tr("No se pudo armar la hoja de la utilidad agregada."))
            return
        self._rec_abrir_avance(paso)                     # (abrir la tarjeta sube la generación: después)
        gen = self._recog_generation
        act["tarea"], act["gen"] = t, gen
        self._recog_linea = ""
        t.avance.connect(lambda a, t=t, gen=gen: self._rec_avance(t, gen, a))
        t.terminado.connect(lambda r, e, t=t, gen=gen: self._rec_terminado(t, gen, r, e))
        try:
            proceso.trabajador(proceso.RETENEDOR).enviar(t)
        except Exception:
            import traceback
            self._rec_terminado(t, gen, None, traceback.format_exc())

    def _rec_vigente(self, t, gen):
        act = self._rec_actual
        return act is not None and act.get("tarea") is t and getattr(self, "_recog_generation", 0) == gen

    def _rec_abrir_avance(self, paso):
        texto = _tr("Reconociendo {u}…").format(u=_tr(RE.ETIQUETAS.get(paso, paso)))
        detalle = _tr("Hoja {n} · en segundo plano").format(n=int(self.page_idx) + 1)
        ov = getattr(self, "_recog_busy", None)
        if self._rec_avance_abierto and ov is not None:
            ov.step(text=texto, detail=detalle)
            return
        self._avance_reconocer(texto, detalle, cancel=self.cancelar_reconocer)
        self._rec_avance_abierto = True

    def _rec_avance(self, t, gen, a):
        if not self._rec_vigente(t, gen) or not a:
            return
        tipo, ov = a[0], getattr(self, "_recog_busy", None)
        if tipo == "capa" and ov is not None and a[5]:
            k, m = int(a[4]), int(a[5])
            self._recog_linea = "" if k >= m else _tr("{u} · capa {k} de {m}").format(
                u=_tr(RE.ETIQUETAS.get(a[3], a[3])), k=k + 1, m=m)
            # la cuenta de la barra = los TRAZOS de las capas ya hechas (una capa grande pesa más que una chica);
            # sin ellos (otro trabajo) las capas
            hechos, total = (a[6], a[7]) if len(a) >= 8 and a[7] else (k, m)
            ov.step(detail=self._recog_linea or None, done=hechos, total=total, pump=False, clave="capas")
        elif tipo == "trazos":
            self._recognition_strokes(a[3], a[4])
        elif tipo == "hecha":
            self._recognition_partial(a[3], a[4])
        elif tipo == "detalle":
            self._rec_etapa(ov, a[1], a[2], a[3])

    def _rec_etapa(self, ov, texto, i, n):
        """Qué está haciendo ahora, debajo de la utilidad y su capa. Dentro de una capa («Reconstruyendo las
        líneas de la capa X…») la cuenta es la de los trazos que dio el aviso «capa»; las demás etapas (ajustar
        las rutas, las bóvedas, los diámetros…) cuentan lo suyo o, sin cuenta, son una etapa aparte que la barra
        estima (antes TODO lo que venía después de la primera capa seguía siendo «capas» con la cuenta de la
        última: la barra marcaba 8 de 9 capas con tres cuartos del trabajo por hacer)."""
        if ov is None:
            return
        from ui.comun import busy as _busy_mod
        linea = getattr(self, "_recog_linea", "")
        dentro = bool(linea) and texto.startswith(_tr("Reconstruyendo las líneas de la capa {c}…").split("{c}")[0])
        salto = chr(10)
        detalle = (linea + salto if linea else "") + _busy_mod.detalle_de(texto, None if dentro else i,
                                                                          None if dentro else n)
        if dentro:
            ov.step(detail=detalle, pump=False, clave="capas")
        else:
            self._recog_linea = ""
            ov.step(detail=detalle, done=i if n else None, total=n or None, pump=False)

    def _rec_terminado(self, t, gen, res, err):
        if not self._rec_vigente(t, gen):
            return                                       # cancelado, o de otra hoja / otro proyecto
        act = self._rec_actual
        act["tarea"] = None
        if err == "cancelado":                           # el trabajador se detuvo (p. ej. al salir): como Cancelar
            self.cancelar_reconocer()
            return
        if err:
            self._rec_fallo(act, err)
        else:
            try:
                paso, importar = act["pasos"].pop(0)
                if not importar:                         # una utilidad que los demás necesitan: solo en memoria
                    self._resultados_partes[paso] = list(res or [])
                    self._rec_cache().put(self._rec_clave(paso, act["firma"], self._firma_parte_actual(paso)),
                                          [copy.deepcopy(list(res or []))])
                    self._rec_correr()
                    return
                self._rec_hecho(act, res)
            except Exception:
                import traceback
                self._rec_fallo(act, traceback.format_exc())
        self._rec_siguiente()

    def _rec_hecho(self, act, res):
        """El resultado de la parte entra al plano y su fila queda reconocida. Sin `importar` (👁) solo queda en la
        caché y, con `ver`, se abre la vista previa; la fila vuelve a como estaba."""
        parte = act["parte"]
        self._rec_cache().put(act["clave"], [copy.deepcopy(res)])   # antes de importar: la caché queda intacta
        dibujo = getattr(self, "_recog_dibujo", None)
        if dibujo is not None:
            dibujo.reemplazar(parte, [])                 # las provisionales se van: entran las de verdad
        if not act.get("importar", True):
            self._rec_actual = None
            self._rec_volver_fila(act)
            if act.get("ver"):
                firma = act["firma"]
                QtCore.QTimer.singleShot(0, self, lambda: self._ver_resultado(parte, res, firma))
            return
        self._rec_aplicar(parte, res, act["reemplazar"], act["firma"], act["firma_parte"])
        self._rec_actual = None
        self._refrescar_panel_reconocer()

    def _rec_aplicar(self, parte, res, reemplazar, firma, firma_parte):
        """Importa `res` al editor y deja la fila reconocida: el MISMO camino del ▶ y del «Importar» de la vista previa."""
        if self._resultados_partes is None:
            self._resultados_partes = {}
        if parte in RE.UTILIDADES:
            self._resultados_partes[parte] = list(res or [])
        ov = getattr(self, "_rec_hoja", None)
        if ov is not None:                               # utilidad agregada: datos extendidos de SU pieza
            self._origen_desde_fuente = ov["desde"]
        try:
            n = self.importar_parte(parte, res, reemplazar=reemplazar, firma=firma)
        finally:
            if ov is not None:
                self._origen_desde_fuente = None
        if ov is not None and parte in RE.UTILIDADES and hasattr(self, "_agregado_utilidad"):
            self._agregado_utilidad(ov, parte)
        antes = self.avisos_diametro
        RE.tras_reconocer(self._rec_estado(), parte, firma_parte, _cuantos(parte, res), _verificar(parte, res))
        if self.avisos_diametro != antes:                # «Diámetros» reconocido: ahora sí sus avisos
            self._redraw()
        self._reconocer_ultimo = (parte, n)
        self._refrescar_panel_reconocer()
        return n

    def _rec_fallo(self, act, err):
        from nucleo import diagnostico
        self._rec_actual = None
        if err == "memoria":
            texto = _tr("La hoja necesita más memoria de la que hay libre en el equipo. Prueba con menos hojas en "
                        "la composición, menos utilidades a la vez o cerrando otros programas.")
        else:
            diagnostico.registrar(err, "Reconocimiento")
            texto = diagnostico.resumen(err)
        fila = self._rec_estado().filas[act["parte"]]
        if act["previo"] in _HECHAS:
            self._rec_volver_fila(act)                   # lo ya reconocido sigue en el plano
        else:
            fila.estado, fila.motivo = "error", M_FALLO
        self._info(_tr("No se pudo reconocer {u}: {e}").format(
            u=_tr(RE.ETIQUETAS.get(act["parte"], act["parte"])), e=texto))
        self._refrescar_panel_reconocer()

    def _rec_volver_fila(self, act):
        fila = self._rec_estado().filas.get(act["parte"])
        if fila is not None:
            fila.estado, fila.motivo = act["previo"], act.get("motivo", fila.motivo)
        self._refrescar_panel_reconocer()

    def _rec_fin_cola(self):
        if self._rec_avance_abierto:
            self._rec_avance_abierto = False
            self._end_recognition_busy()
        self._refrescar_panel_reconocer()


def _cuantos(parte, res) -> int:
    """Lo que dice la fila al terminar: líneas, válvulas, rótulos o líneas con diámetro."""
    if parte == "VALVULAS":
        return len((res or {}).get("valvulas") or [])
    if parte == "ROTULOS":
        return len((res or {}).get("anotaciones") or [])
    lineas = [pl for r in (res or []) for pl in (getattr(r, "drawable", None) or [])]
    if parte == "DIAMETROS":
        return sum(1 for pl in lineas if getattr(pl, "diam_in", None))
    return len(lineas)


def _verificar(parte, res) -> list:
    """Los «Para verificar» de la parte (como en la vista previa: `classify_warning` + `targets_for`), con su lugar
    en px del plano; sin los avisos informativos."""
    from reconocimiento import recognition_summary as RS
    if parte == "VALVULAS":
        vs = list((res or {}).get("valvulas") or [])
        resultados = [SimpleNamespace(utility="", warnings=list((res or {}).get("avisos") or []), valvulas=vs,
                                      drawable=[])]
    elif parte == "ROTULOS":
        resultados = []
    else:
        resultados = list(res or [])
    out = []
    for r in resultados:
        for w in getattr(r, "warnings", None) or []:
            n = RS.classify_warning(w, getattr(r, "utility", "") or "")
            if n.level == RS.INFO:
                continue
            try:
                rects = [list(map(float, b)) for b in (RS.targets_for(n.key, r) if n.key else [])]
            except Exception:                            # noqa: BLE001 — un lugar que no se encuentra no estorba
                rects = []
            out.append({"texto": n.text, "etiqueta": n.label, "nivel": n.level, "clave": n.key,
                        "utilidad": n.utility, "rect": rects[0] if rects else None, "rects": rects})
    return out

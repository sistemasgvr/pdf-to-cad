"""El Copiloto en el chat (mezcla de `PreguntaDialog`): botones rápidos, intención y enlaces `cop:` de sus tarjetas.

Funciona sin servidor de IA: `enviar` pregunta aquí ANTES de exigir un proveedor. Una revisión va por etapas: tanda de
seguros → propuestas línea por línea → decisiones por grupo. Cada acción de una tarjeta es un enlace `cop:<acción>:…`.
"""
from __future__ import annotations

import time

from PySide6 import QtCore, QtGui, QtWidgets

from ia import alcance as A
from ia import copiloto_intencion as CI
from ui.comun.responsive import GridAdaptable
from ui.dialogos import ia_chat_copiloto_html as HC
from traduccion.i18n import t as _tr
from traduccion.i18n_core import N_

BOTONES = ((N_("¿Cómo vamos?"), CI.ESTADO), (N_("Revisar avisos"), CI.REVISION), (N_("Resolver conflictos"), CI.CONFLICTOS))
CONFIRMAR, HECHO, CANCELADO, CADUCADO, ERROR = "confirmar", "hecho", "cancelado", "caducado", "error"
PENSANDO = "pensando"
MAX_BITACORA = 20


class CopilotoChatMixin:
    _cop_trabajo = None                               # clasificación en curso
    _cop_forzada = None                               # intención que pidió un botón
    _cop_inv = ()                                     # códigos que faltan por investigar
    _cop_rev = None                                   # {"cola", "firma", "sesion", "clase"} de la revisión abierta

    def _barra_copiloto(self):
        barra = QtWidgets.QWidget()
        lay = GridAdaptable(barra, max_cols=len(BOTONES), spacing=6)    # en el panel angosto bajan de línea
        self._botones_cop = []
        for texto, intencion in BOTONES:
            b = QtWidgets.QPushButton(_tr(texto))
            b.setProperty("kind", "chip")
            b.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
            b.clicked.connect(lambda _c=False, s=texto, i=intencion: self._cop_boton(s, i))
            lay.addWidget(b)
            self._botones_cop.append(b)
        return barra

    def _cop_boton(self, texto, intencion):
        """Un botón pide la acción directamente: no depende del idioma ni de cómo se lea la frase."""
        if self._activo is None:
            self._cop_forzada = intencion
            self.enviar(_tr(texto))

    def _turno_copiloto(self, turno):
        """¿Lo atiende el Copiloto? Una orden a medias y lo que el alcance bloquea siguen su camino de siempre."""
        q = turno["pregunta"]
        i, self._cop_forzada = self._cop_forzada, None
        if i is None and (self._orden_pendiente is not None or A.revisar(q) in (A.INYECCION, A.CODIGO)):
            return False
        i = i or CI.intencion(q)
        if i is None:
            return False
        turno["cop"] = {"tipo": "estado", "estado": self.win.copiloto_estado()}
        turno["estado"] = "listo"
        self._pintar(abajo=True)
        if i == CI.REVISION:
            self._cop_revisar()
        elif i == CI.CONFLICTOS and not self.win.copiloto_conflictos_ocultos():
            self._cop_conflictos()
        return True

    def _turno_cop(self, cop, texto=""):
        """Una tarjeta del Copiloto sin pregunta del usuario. Devuelve su índice."""
        self.turnos.append({"pregunta": "", "sistema": True, "texto": texto, "estado": "listo", "res": None, "error": "",
                            "valor": 0, "corregido": "", "hora": time.strftime("%H:%M"), "t0": time.time(),
                            "siguientes": [], "cop": cop})
        self._pintar(abajo=True)
        return len(self.turnos) - 1

    # ── revisión ──
    def _cop_revisar(self, clase=None, previa=None):
        """Clasifica los avisos pendientes y empieza por lo seguro. `previa` = la revisión que sigue tras un cambio
        del proyecto: conserva lo ya visto y no vuelve a ofrecer la tanda rechazada."""
        firma, sesion = self.win.copiloto_firma()      # de ANTES de clasificar: un cambio en medio la hace caducar
        t = self._turno_cop({"tipo": "espera", "texto": _tr("Clasificando los avisos…")})
        cop = self.turnos[t]["cop"]
        self._activo = {"cancelado": False}
        self._ocupado(True)

        def al_paso(k, n):
            cop["texto"] = _tr("Clasificando los avisos: {k} de {n}").format(k=k, n=n)

        def al_terminar(cola, error):
            self._cop_trabajo = None
            self._terminar()
            if sesion != self.win._cop_sesion:         # otro proyecto: esto ya no vale
                return
            if error is not None or cola is None:
                self.win._cop_revisando = None
                cop["texto"] = _tr("No pude clasificar los avisos: {e}").format(e=error) if error else _tr("Detenido.")
                self._pintar()
            else:
                cop["texto"] = _tr("Avisos clasificados.")
                vistos = set((previa or {}).get("vistos") or ())
                for x in cola.items:                  # lo ya visto en esta revisión no se vuelve a preguntar
                    if x.nivel == "propuesta" and x.clave in vistos:
                        x.nivel = "decision"
                self._cop_rev = {"cola": cola, "firma": firma, "sesion": sesion, "clase": clase, "vistos": vistos,
                                 "sin_seguros": bool((previa or {}).get("sin_seguros")), "ia_caida": False, "fin": False,
                                 "sin_certeza": 0}
                self._cop_etapa_seguros()
        self._cop_trabajo = self.win.copiloto_cola(clase, al_paso, al_terminar)

    # ── conflictos ──
    def _cop_ver_conflictos(self):
        self.win.chk_show_conflicts.setChecked(True)
        self._turno_cop({"tipo": "estado", "estado": self.win.copiloto_estado()})

    def _cop_conflictos(self):
        if self.win.copiloto_conflictos_ocultos():     # apagados no se calculan: la lista saldría vacía
            self._turno_cop({"tipo": "estado", "estado": self.win.copiloto_estado()})
            return
        firma, sesion = self.win.copiloto_firma()
        t = self._turno_cop({"tipo": "espera", "texto": _tr("Probando las soluciones…")})
        cop = self.turnos[t]["cop"]
        self._activo = {"cancelado": False}
        self._ocupado(True)

        def al_paso(k, n):
            cop["texto"] = _tr("Probando las soluciones: {k} de {n}").format(k=k, n=n)

        def al_terminar(filas, error):
            self._cop_trabajo = None
            self._terminar()
            if error is not None:
                cop["texto"] = _tr("No pude probar las soluciones: {e}").format(e=error)
                self._pintar()
            elif filas is not None:
                cop["texto"] = _tr("Soluciones probadas.")
                self._turno_cop({"tipo": "conflictos", "filas": filas, "marcados": set(), "firma": firma, "sesion": sesion,
                                 "estado": CONFIRMAR, "resultado": ""})
        self._cop_trabajo = self.win.copiloto_probar_conflictos(al_paso, al_terminar)

    def _cop_cmarca(self, t, k):
        cop = self._cop_de(t, "conflictos")
        if cop is not None and str(k).isdigit() and int(k) < len(cop["filas"]) and cop["filas"][int(k)].prop:
            cop["marcados"] ^= {int(k)}
            self._pintar()

    def _cop_climpias(self, t):
        cop = self._cop_de(t, "conflictos")
        if cop is not None:
            cop["marcados"] = {k for k, f in enumerate(cop["filas"]) if f.prop}
            self._pintar()

    def _cop_caplicar(self, t):
        cop = self._cop_de(t, "conflictos")
        if cop is None or not cop["marcados"]:
            return
        cop["estado"] = HECHO                          # antes de aplicar: un doble clic no aplica dos veces
        filas = [f for k, f in enumerate(cop["filas"]) if k in cop["marcados"]]
        try:
            aplicadas, saltadas = self.win.copiloto_aplicar_conflictos(filas, cop["firma"], cop["sesion"])
        except Exception as e:                         # noqa: BLE001 (se dice en el chat)
            cop["estado"], cop["resultado"] = ERROR, _tr("No se pudo aplicar: {e}").format(e=e)
            return self._pintar(abajo=True)
        if saltadas == CADUCADO:
            cop["estado"], cop["resultado"] = CADUCADO, _tr("El proyecto cambió: vuelve a pedir la prueba.")
        else:
            cop["resultado"] = _tr("Apliqué {n}. Se deshace con un Ctrl+Z.").format(n=len(aplicadas))
            if saltadas:
                cop["resultado"] += " " + _tr("Salté {n}: {m}").format(
                    n=len(saltadas), m="; ".join(f"{f.c.id}: {m}" for f, m in saltadas[:5]))
        self._pintar(abajo=True)

    # ── bitácora ──
    def _cop_bitacora(self):
        self._turno_cop({"tipo": "bitacora", "entradas": list(reversed(self.win.bitacora))[:MAX_BITACORA],
                         "ultima": self.win.copiloto_ultima_tanda()})

    def _cop_deshacer(self, ident):
        if ident and ident == self.win.copiloto_ultima_tanda():
            self.win.undo()
            for tu in self.turnos:                     # sus tarjetas ya no ofrecen deshacer
                if (tu.get("cop") or {}).get("tipo") == "bitacora":
                    tu["cop"]["ultima"] = None
            self._pintar(abajo=True)

    def _cop_irc(self, t, k):
        cop = self.turnos[int(t)].get("cop") if str(t).isdigit() and int(t) < len(self.turnos) else None
        if cop and str(k).isdigit() and int(k) < len(cop.get("filas", ())):
            c = cop["filas"][int(k)].c
            self.win._ir_a_elemento(c.x, c.y, activar=False)

    def _cop_abrirc(self, cid):
        self.win.abrir_soluciones(cid)

    def _detener_copiloto(self):
        self._cop_inv = []
        if self._cop_trabajo is not None:
            self._cop_trabajo.cancelar()

    # ── lo que el agente deja para decidir ──
    def _cop_tras_agente(self, res):
        for p in getattr(res, "propuestas", None) or []:
            {"diametro": self._cop_agente_diametro, "orden": self._cop_agente_orden,
             "funcion": self._cop_agente_funcion}[p["tipo"]](p)
        if self._cop_inv:
            QtCore.QTimer.singleShot(0, self, self._cop_investigar_siguiente)

    def _cop_agente_diametro(self, p):
        item, sug = self.win.agente_item(p)
        firma, sesion = self.win.copiloto_firma()
        self._turno_cop({"tipo": "linea", "item": item, "sug": sug, "estado": CONFIRMAR, "resultado": "", "falta": 0,
                         "firma": firma, "sesion": sesion, "captura": HC.guardar_captura(p["captura"]), "leido": p["leido"]})

    def _cop_agente_orden(self, p):
        self.turnos.append({"pregunta": "", "sistema": True, "texto": p["que"], "estado": "listo", "res": None, "error": "",
                            "valor": 0, "corregido": "", "hora": time.strftime("%H:%M"), "t0": time.time(), "siguientes": [],
                            "orden": {"obj": p["obj"], "que": p["que"], "cons": p["cons"], "estado": "confirmar",
                                      "pedido": p["que"], "entendido": "", "resultado": ""}})
        self._pintar(abajo=True)

    def _cop_agente_funcion(self, p):
        self._turno_cop({"tipo": "funcion", "texto": p["texto"], "accion": p["accion"], "estado": CONFIRMAR, "resultado": ""})

    def _cop_funsi(self, t):
        cop = self._cop_de(t, "funcion")
        if cop is not None:
            cop["estado"], cop["resultado"] = HECHO, _tr("Abrí «{f}».").format(f=cop["texto"])
            self._pintar(abajo=True)
            cop["accion"].trigger()

    def _cop_funno(self, t):
        cop = self._cop_de(t, "funcion")
        if cop is not None:
            cop["estado"], cop["resultado"] = CANCELADO, _tr("No lo usé.")
            self._pintar(abajo=True)

    def _cop_investigar_lista(self, etiquetas):
        """El agente revisa esas líneas una tras otra; cada propuesta queda en su tarjeta. «Detener» corta."""
        self._cop_inv = list(etiquetas)
        self._cop_investigar_siguiente()

    def _cop_investigar_siguiente(self):
        if self._cop_inv and self._activo is None:
            self.enviar(_tr("Investiga el diámetro de {c}: mira el plano y propón un valor solo si tienes evidencia.").format(
                c=self._cop_inv.pop(0)))

    def _cop_investigar(self, t):
        cop = self.turnos[int(t)].get("cop") if str(t).isdigit() and int(t) < len(self.turnos) else None
        if cop and cop.get("investigar") and self._activo is None:
            lista, cop["investigar"] = cop["investigar"], []
            self._pintar()
            self._cop_investigar_lista(lista)

    def _copiloto_soltar(self):
        """Otro proyecto: lo que estaba en curso se corta y las tarjetas ya no sirven."""
        self._detener_copiloto()
        self._cop_rev = None

    def _cop_etapa_seguros(self):
        rev = self._cop_rev
        seguros = [] if rev["sin_seguros"] else rev["cola"].seguros()
        if not seguros:
            return self._cop_siguiente_etapa()
        self._turno_cop({"tipo": "seguro", "items": seguros, "marcados": set(range(len(seguros))), "firma": rev["firma"],
                         "sesion": rev["sesion"], "estado": CONFIRMAR, "resultado": ""})

    def _cop_propuestas(self):
        rev = self._cop_rev
        return [x for x in rev["cola"].propuestas() if x.clave not in rev["vistos"]]

    def _cop_siguiente_etapa(self):
        """Lo que sigue: la próxima línea o, sin más líneas, las decisiones por grupo."""
        rev = self._cop_rev
        if rev is None or rev["sesion"] != self.win._cop_sesion:
            return
        if not self.win._copiloto_vigente(rev["firma"], rev["sesion"]):
            self._cop_rev = None                      # el proyecto cambió: se clasifica de nuevo, sin perder lo visto
            return self._cop_revisar(rev["clase"], rev)
        pendientes = self._cop_propuestas()
        if rev["ia_caida"] or self.win._diam_ia_proveedor() is None:
            for x in pendientes:
                x.nivel, x.motivo = "decision", _tr("La IA no respondió.")
            pendientes = []
        if not pendientes:
            return self._cop_etapa_grupos()
        self._cop_linea(pendientes[0])

    def _cop_linea(self, item):
        rev = self._cop_rev
        rev["vistos"].add(item.clave)
        a = item.aviso
        self.win._cop_revisando = a.pipe
        self.win._ir_a_elemento(a.x, a.y, "pipe", a.pipe, activar=False)
        t = self._turno_cop({"tipo": "linea", "item": item, "sug": None, "estado": PENSANDO, "resultado": "",
                             "falta": len(self._cop_propuestas()), "firma": rev["firma"], "sesion": rev["sesion"]})
        cop = self.turnos[t]["cop"]
        al_listo = lambda it, r: self._cop_llego(cop, it, r)  # noqa: E731
        if not self.win.copiloto_esperar(item, al_listo):
            self.win.copiloto_pedir(item, al_listo)

    def _cop_llego(self, cop, item, r):
        rev = self._cop_rev
        if rev is None or cop["estado"] != PENSANDO:
            return
        if isinstance(r, str):
            rev["ia_caida"] = True
            item.nivel, item.motivo = "decision", r
        elif not r.diam_in:
            item.nivel, item.motivo = "decision", r.motivo
        else:
            cop["sug"], cop["estado"] = r, CONFIRMAR
            self._pintar(abajo=True)
            siguiente = self._cop_propuestas()
            if siguiente:                              # mientras decides, ya revisa la que sigue
                self.win.copiloto_pedir(siguiente[0])
            return
        cop["estado"], cop["resultado"] = CANCELADO, _tr("Sin certeza: queda para tu decisión.")
        rev["sin_certeza"] += 1
        if self.turnos and self.turnos[-1].get("cop") is cop:
            self.turnos.pop()                          # sin propuesta no hay nada que mirar: va a los grupos
        self._pintar(abajo=True)
        QtCore.QTimer.singleShot(0, self, self._cop_siguiente_etapa)   # sin apilar una llamada por línea

    def _cop_etapa_grupos(self):
        """Lo que queda lo decide el usuario: un grupo por aviso igual."""
        rev = self._cop_rev
        grupos = [{"items": items, "hecho": False} for items in rev["cola"].grupos().values()]
        if grupos:
            self._turno_cop({"tipo": "grupos", "grupos": grupos, "firma": rev["firma"], "sesion": rev["sesion"],
                             "resultado": ""})
        saltados = len(self.win.revision.get("saltados") or ())
        investigar = []
        if not rev["ia_caida"] and self.win.agente_disponible():
            investigar = [x.etiqueta for x in rev["cola"].items if x.nivel == "decision" and x.aviso.clase == "grosor"]
        self._turno_cop({"tipo": "fin", "saltados": saltados, "investigar": investigar})
        self._cop_fin()

    def _cop_grupo_de(self, t, k):
        cop = self.turnos[int(t)].get("cop") if str(t).isdigit() and int(t) < len(self.turnos) else None
        if cop and cop.get("tipo") == "grupos" and str(k).isdigit() and int(k) < len(cop["grupos"]):
            return cop["grupos"][int(k)]
        return None

    def _cop_grupo(self, t, k):
        g = self._cop_grupo_de(t, k)
        if g is None or g["hecho"]:
            return
        nota, ok = QtWidgets.QInputDialog.getMultiLineText(
            self, _tr("Aprobar estos avisos"), _tr("¿Por qué se aprueban? Queda en la bitácora y en el proyecto."))
        if not ok:
            return
        cop = self.turnos[int(t)]["cop"]
        if self.win.copiloto_aprobar_grupo(g["items"], nota, cop["firma"], cop["sesion"]):
            g["hecho"] = True
            cop["firma"], cop["sesion"] = self.win.copiloto_firma()      # aprobar es un cambio nuestro
            self._cop_rev_refrescar()
        elif nota.strip():
            cop["resultado"] = _tr("El proyecto cambió: vuelve a pedir la revisión.")
        self._pintar(abajo=True)

    def _cop_abrir(self, t, k):
        g = self._cop_grupo_de(t, k)
        if g is not None:
            a = g["items"][0].aviso
            self.win._ir_a_elemento(a.x, a.y, "pipe", a.pipe)

    def _cop_ver_saltados(self):
        self.win.revision["saltados"] = []
        self.win._dirty = True
        self._cop_revisar()

    def _cop_fin(self):
        if self._cop_rev is not None:
            self._cop_rev["fin"] = True
        self.win._cop_revisando = None

    def _cop_decidir(self, t, accion, valor=None):
        cop = self._cop_de(t, "linea")
        if cop is None:
            return
        motivo = self.win.copiloto_decidir(cop["item"], accion, cop["firma"], cop["sesion"], valor, cop["sug"])
        if motivo == CADUCADO:
            cop["estado"], cop["resultado"] = CADUCADO, _tr("Esta línea cambió: la dejo aquí.")
        elif motivo:
            cop["resultado"] = _tr("La familia de esta utilidad no tiene ese tamaño: elige otro valor.")
            return self._pintar(abajo=True)
        else:
            cop["estado"] = HECHO
            cop["resultado"] = _tr("La dejé para después.") if accion == "saltar" else _tr("Hecho. Ctrl+Z lo deshace.")
            if accion != "saltar":
                vieja = cop["firma"]
                self._cop_rev_refrescar()
                firma, sesion = self.win.copiloto_firma()
                for tu in self.turnos:                 # el cambio es nuestro: las demás tarjetas siguen valiendo
                    otra = tu.get("cop") or {}
                    if otra.get("tipo") == "linea" and otra.get("estado") == CONFIRMAR and otra.get("firma") == vieja:
                        otra["firma"], otra["sesion"] = firma, sesion
        self._pintar(abajo=True)
        self._cop_siguiente_etapa()

    def _cop_aprobar(self, t):
        self._cop_decidir(t, "aprobar")

    def _cop_saltar(self, t):
        self._cop_decidir(t, "saltar")

    def _cop_otro(self, t):
        cop = self._cop_de(t, "linea")
        if cop is None:
            return
        valor, ok = QtWidgets.QInputDialog.getDouble(self, _tr("Otro diámetro"), _tr("Diámetro (pulgadas):"),
                                                     float(cop["sug"].diam_in), 0.125, 240.0, 3)
        if ok:
            self._cop_decidir(t, "otro", valor)

    def _cop_pausa(self, t):
        cop = self._cop_de(t, "linea")
        if cop is None:
            return
        cop["estado"], cop["resultado"] = CANCELADO, _tr("Revisión en pausa: «Revisar avisos» la retoma.")
        self._cop_rev = None
        self.win._cop_revisando = None
        self._pintar(abajo=True)

    def _cop_de(self, valor, tipo):
        """El turno `valor` si es una tarjeta `tipo` esperando respuesta."""
        i = int(valor) if str(valor).isdigit() else -1
        cop = self.turnos[i].get("cop") if 0 <= i < len(self.turnos) else None
        return cop if cop and cop.get("tipo") == tipo and cop.get("estado") == CONFIRMAR else None

    def _cop_marca(self, t, k):
        cop = self._cop_de(t, "seguro")
        if cop is None:
            return
        if k == "resto":                               # las que no caben en la tarjeta se marcan juntas
            resto = set(range(HC.MAX_FILAS, len(cop["items"])))
            cop["marcados"] = cop["marcados"] - resto if resto <= cop["marcados"] else cop["marcados"] | resto
        elif str(k).isdigit():
            cop["marcados"] ^= {int(k)}
        self._pintar()

    def _cop_aplicar(self, t):
        cop = self._cop_de(t, "seguro")
        if cop is None:
            return
        cop["estado"] = HECHO                          # antes de aplicar: un doble clic no aplica dos veces
        items = [x for k, x in enumerate(cop["items"]) if k in cop["marcados"]]
        n, motivo = self.win.copiloto_aplicar_seguros(items, cop["firma"], cop["sesion"])
        if motivo == CADUCADO:
            cop["estado"], cop["resultado"] = CADUCADO, _tr("El proyecto cambió: esta tanda ya no vale.")
        elif motivo:
            cop["estado"], cop["resultado"] = ERROR, _tr("No se pudo aplicar: {e}").format(e=motivo)
        else:
            cop["resultado"] = _tr("Hecho: {n} utilidad(es). Se deshace con un Ctrl+Z.").format(n=n)
            self._cop_rev_refrescar()
        self._pintar(abajo=True)
        if cop["estado"] in (HECHO, CADUCADO):         # si cambió, `_cop_siguiente_etapa` clasifica de nuevo
            self._cop_siguiente_etapa()

    def _cop_no(self, t):
        cop = self._cop_de(t, "seguro")
        if cop is None:
            return
        cop["estado"], cop["resultado"] = CANCELADO, _tr("No apliqué nada de esta tanda.")
        self._pintar(abajo=True)
        self._cop_siguiente_etapa()

    def _cop_rev_refrescar(self):
        """El proyecto cambió por una decisión de la revisión: lo pendiente sigue, con la firma nueva."""
        if self._cop_rev is not None:
            self._cop_rev["firma"], self._cop_rev["sesion"] = self.win.copiloto_firma()

    def _cop_ir(self, t, k):
        cop = self.turnos[int(t)].get("cop") if str(t).isdigit() and int(t) < len(self.turnos) else None
        if cop and str(k).isdigit() and int(k) < len(cop.get("items", ())):
            a = cop["items"][int(k)].aviso
            self.win._ir_a_elemento(a.x, a.y, "pipe", a.pipe, activar=False)

    def _enlace_copiloto(self, valor):
        """Enlaces `cop:<acción>:…` de las tarjetas."""
        accion, *args = str(valor).split(":")
        if accion in ("revisar", "conflictos", "ver_saltados") and self._activo is not None:
            return                                     # ya hay algo en curso
        acciones = {"revisar": self._cop_revisar, "marca": self._cop_marca, "aplicar": self._cop_aplicar,
                    "no": self._cop_no, "ir": self._cop_ir, "aprobar": self._cop_aprobar, "saltar": self._cop_saltar,
                    "otro": self._cop_otro, "pausa": self._cop_pausa, "grupo": self._cop_grupo,
                    "abrir": self._cop_abrir, "ver_saltados": self._cop_ver_saltados,
                    "conflictos": self._cop_conflictos, "cmarca": self._cop_cmarca, "climpias": self._cop_climpias,
                    "caplicar": self._cop_caplicar, "irc": self._cop_irc, "abrirc": self._cop_abrirc,
                    "bitacora": self._cop_bitacora, "deshacer": self._cop_deshacer,
                    "ver_conflictos": self._cop_ver_conflictos, "funsi": self._cop_funsi, "funno": self._cop_funno,
                    "investigar": self._cop_investigar}
        if accion in acciones:
            acciones[accion](*args)

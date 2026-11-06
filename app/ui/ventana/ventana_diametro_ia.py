"""Tarjeta «Diámetro según la IA» del inspector (pedido del usuario 2026-10-29; spec
`docs/superpowers/specs/2026-10-29-ia-diametro-plano-design.md`).

Actualización: revisa al abrir el aviso, con reintento manual. Sin lectura segura
del plano ofrece una propuesta normativa con sus supuestos; aprobar o introducir
otro diámetro son las únicas acciones que cambian el modelo (con deshacer).

Con la IA configurada se revisa únicamente la utilidad seleccionada con aviso
pendiente, en un hilo cancelable al cambiar de selección. «Aprobar» aplica la
propuesta y «Otro diámetro…» permite sustituirla (ambos con Ctrl+Z).
El resultado NO va a `pipes` (cambiaría la firma del modelo y se recalcularía todo el plano): vive en
`self._diam_ia` (por ficha) y en la caché de la memoria de la IA.
"""
from ia import reporte_error as RE
import base64
import html
import json
import threading
import time

from ui.ventana.ventana_comun import *  # noqa: F401,F403
from ui.comun import rediseno as R
from ui.ventana.ventana_diametro_ia_replica import ReplicaDiametroMixin
from ui.ventana.ventana_diametro_ia_senales import SenalesDiametroMixin


_ESPERA_FICHA_MS = 150                               # si se sigue eligiendo líneas, no se arma la de cada una
_MAX_FICHAS = 64
_ESPERA_REVELAR_MS = 40


class _Senales(QtCore.QObject):
    listo = QtCore.Signal(object, object)            # (token, Sugerencia | str con el error)
    etapa = QtCore.Signal(object, str)
    puente = QtCore.Signal(object, object)           # (función, caja): hace algo de la hoja en la ventana


class _TextoAnalisis(QtWidgets.QLabel):
    """No permite que el formulario comprima la última línea de texto enriquecido."""
    def _ajustar_alto(self):
        if self.wordWrap() and self.width() > 0 and not getattr(self,"_midiendo",False):
            self._midiendo = True
            try:
                # QLabel incluye el mínimo anterior en heightForWidth: quitarlo
                # al medir permite encoger una respuesta o ampliar el panel.
                self.setMinimumHeight(0)
                self.setMinimumHeight(max(0,self.heightForWidth(self.width())))
            finally:
                self._midiendo = False

    def setText(self, texto):  # noqa: N802 (API Qt)
        super().setText(texto)
        self._ajustar_alto()

    def resizeEvent(self, evento):  # noqa: N802
        super().resizeEvent(evento)
        self._ajustar_alto()

    def changeEvent(self, evento):  # noqa: N802
        super().changeEvent(evento)
        if evento.type() in (QtCore.QEvent.FontChange, QtCore.QEvent.StyleChange):
            self._ajustar_alto()


class _TarjetaIA(QtWidgets.QFrame):
    """El QFormLayout del inspector reparte mal el alto de una fila que depende de su ancho: a esta le daba
    12–20 px de menos y el botón quedaba encima del texto. Su mínimo es siempre lo que pide su contenido."""

    def _ajustar_minimo(self):
        lay = self.layout()
        if lay is not None and self.width() > 0:
            alto = lay.totalHeightForWidth(self.width())
            if alto != self.minimumHeight():
                self.setMinimumHeight(alto)

    def event(self, evento):
        if evento.type() == QtCore.QEvent.LayoutRequest:
            self._ajustar_minimo()
        return super().event(evento)

    def resizeEvent(self, evento):  # noqa: N802
        super().resizeEvent(evento)
        self._ajustar_minimo()


class DiametroIAMixin(ReplicaDiametroMixin, SenalesDiametroMixin):
    # ── la tarjeta ──
    def _diam_ia_construir(self):
        """La tarjeta (la pone `ventana_inspector_campos.reorganizar` en la sección Normativa)."""
        self._diam_ia = {}
        self._diam_ia_evidencias = {}
        self._diam_ia_textos = {}
        self._diam_ia_originales_cache = {}
        self._diam_ia_origenes = {}
        self._diam_ia_auto = True
        self._diam_ia_intentadas = set()
        self._diam_ia_tok = 0
        self._diam_ia_t0 = 0.0
        self._diam_ia_senales = _Senales()
        self._diam_ia_senales.listo.connect(self._diam_ia_listo)
        self._diam_ia_senales.etapa.connect(self._diam_ia_progreso)
        self._diam_ia_senales.puente.connect(self._diam_ia_puente)
        self._diam_ia_reloj = QtCore.QTimer(self)
        self._diam_ia_reloj.setInterval(500)
        self._diam_ia_reloj.timeout.connect(self._diam_ia_tic)
        self._diam_ia_fichas = {}
        self._diam_ia_carga = QtCore.QTimer(self)
        self._diam_ia_carga.setSingleShot(True)
        self._diam_ia_carga.setInterval(_ESPERA_FICHA_MS)
        self._diam_ia_carga.timeout.connect(self._diam_ia_cargar)
        f = self.tarjeta_diam_ia = _TarjetaIA()
        f.setObjectName("tarjetaSuave")
        f.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        sl = QtWidgets.QVBoxLayout(f)
        sl.setContentsMargins(12, 10, 12, 10)
        sl.setSpacing(6)
        cab = QtWidgets.QHBoxLayout()
        self._ic_diam_ia = QtWidgets.QLabel()
        cab.addWidget(self._ic_diam_ia)
        cab.addWidget(R.texto("Diámetro según la IA", "h3", True), 1)
        # 2.ª vuelta (2026-11-03): la tarjeta es un CHAT; «Ver análisis» va arriba, discreto
        self.btn_diam_ia_detalles = self._diam_ia_boton("Ver análisis", "ghost", self.ver_analisis_diametro_ia)
        self.btn_diam_ia_detalles.setIcon(_icon("mdi:selection-search"))
        cab.addWidget(self.btn_diam_ia_detalles)
        self.btn_diam_ia_detalles.hide()
        sl.addLayout(cab)
        # turnos anteriores de la conversación (burbujas: ventana_diametro_ia_replica)
        self._diam_ia_hilo = R.transparente(QtWidgets.QWidget())
        hl = QtWidgets.QVBoxLayout(self._diam_ia_hilo)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(6)
        sl.addWidget(self._diam_ia_hilo)
        self.lbl_diam_ia = _TextoAnalisis()
        self.lbl_diam_ia.setWordWrap(True)
        self.lbl_diam_ia.setTextFormat(QtCore.Qt.RichText)
        self.lbl_diam_ia.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.lbl_diam_ia.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse | QtCore.Qt.LinksAccessibleByMouse)
        self.lbl_diam_ia.linkActivated.connect(self._diam_ia_ir)
        sl.addWidget(self._diam_ia_burbuja(self.lbl_diam_ia, ia=True))   # el mensaje actual de la IA
        self._diam_ia_acciones = R.transparente(QtWidgets.QWidget())
        bt = GridAdaptable(self._diam_ia_acciones, max_cols=2, spacing=6)
        self.btn_diam_ia_preguntar = self._diam_ia_boton("Revisar con la IA", "primary", self.preguntar_diametro_ia)
        self.btn_diam_ia_preguntar.setIcon(_icon("mdi:refresh", color=_theme.tokens().text_on_accent))
        self.btn_diam_ia_usar = self._diam_ia_boton("", "primary", self.usar_diametro_ia)
        self.btn_diam_ia_vecinas = self._diam_ia_boton("", "", self.usar_diametro_en_vecinas)
        self.btn_diam_ia_vecinas.setProperty("soft", True)
        self.btn_diam_ia_no = self._diam_ia_boton("Otro diámetro…", "ghost", self.cambiar_diametro_ia)
        self.btn_diam_ia_detener = self._diam_ia_boton("Detener", "ghost", self._diam_ia_detener)
        for b in (self.btn_diam_ia_preguntar, self.btn_diam_ia_usar, self.btn_diam_ia_vecinas, self.btn_diam_ia_no,
                  self.btn_diam_ia_detener):
            bt.addWidget(b)
        sl.addWidget(self._diam_ia_acciones)
        self._diam_ia_replica_construir(sl)          # «Responder a la IA» (ventana_diametro_ia_replica)
        f.setVisible(False)
        return f

    def _diam_ia_boton(self, texto, kind, fn):
        b = QtWidgets.QPushButton()
        if texto:
            _bind(b, "setText", texto)
        b.setProperty("kind", kind)
        b.clicked.connect(lambda _c=False: fn())
        return b

    # ── qué utilidad y qué evidencia ──
    def _diam_ia_actual(self):
        """Índice de la utilidad elegida con su aviso «Diámetro del plano» pendiente, o None."""
        i = getattr(self, "sel_pipe", -1)
        if not (0 <= i < len(self.pipes)) or self._current_tab() != TAB_PIPE:
            return None
        if not any(getattr(a, "clase", "") == "grosor" and getattr(a, "pipe", None) == i
                   and not getattr(a, "aprobado", False) for a in getattr(self, "_normas_avisos", None) or ()):
            return None
        return i

    def _diam_ia_proveedor(self):
        from ia import proveedor as P
        cfg = P.Config.de(self._config_ia())
        return P.crear(cfg) if cfg.con_ia else None

    def _diam_ia_clave_ficha(self, i):
        """Lo que decide la ficha de `i`: su utilidad, el modelo del último redibujo y la hoja."""
        import pickle
        m = getattr(self, "_memo_redibujo", None)
        return (i, pickle.dumps(self.pipes[i], protocol=4), getattr(m, "firma", None), id(getattr(self, "doc", None)),
                getattr(self, "page_idx", 0), self.zoom)

    def _diam_ia_ficha(self, i):
        """La ficha de `i`, armada una sola vez: leer los textos y las hojas de origen cuesta, y una misma
        selección la pedía hasta seis veces."""
        clave = self._diam_ia_clave_ficha(i)
        f = self._diam_ia_fichas.get(clave)
        if f is None:
            f = self._diam_ia_fichas[clave] = self._diam_ia_armar_ficha(i)
            if len(self._diam_ia_fichas) > _MAX_FICHAS:
                self._diam_ia_fichas.pop(next(iter(self._diam_ia_fichas)))
        return f

    def _diam_ia_armar_ficha(self, i):
        from ia import diametro_ia as DI
        from nucleo import diametro_plano, diametro_contexto
        from reconocimiento.recognition import utility_label
        p = self.pipes[i]
        cat = getattr(self, "normas_cat", None)
        permit = {e["id"]: diametro_plano.permitido(cat, p, e["diam_in"])
                  for e in (p.get("diam_plano") or {}).get("cerca") or []}
        ft_px = self.scale / self.zoom if self.scale and self.zoom else 0.0
        pts = p.get("pts") or []
        largo = sum(math.dist(a, b) for a, b in zip(pts, pts[1:])) * ft_px if ft_px else None
        contexto = diametro_contexto.reunir(p, self.pipes, ft_px or None, getattr(self,"structures",()))
        doc = getattr(self,"doc",None)
        documento = {}
        planes, originales = [], []
        if doc is not None and self.zoom:
            try:
                from hoja import contexto_diametro
                idx = getattr(self,"page_idx",0)
                page = doc[idx]
                clave = (id(doc), idx)
                if clave not in self._diam_ia_textos:
                    self._diam_ia_textos = {clave:contexto_diametro.bloques(page)}
                contexto["textos_pdf"] = contexto_diametro.textos(
                    page, [(x/self.zoom,y/self.zoom) for x,y in pts], self._diam_ia_textos[clave])
                documento = dict(nombre=doc.name or "hoja de trabajo", pagina=idx+1,
                                 ancho_pt=page.rect.width, alto_pt=page.rect.height, sesion=id(doc))
            except Exception:
                contexto["textos_pdf"] = []
            from hoja import contexto_original
            apoyo, planes, originales = contexto_original.reunir(
                getattr(self,"src_pdfs",()) or (),getattr(self,"composite",None),
                [(x/self.zoom,y/self.zoom) for x,y in pts],getattr(self,"page_idx",0),p.get("layer") or "",
                referencias=[e.get("texto","") for e in (p.get("diam_plano") or {}).get("cerca") or []],
                cache=self._diam_ia_originales_cache,trabajo=doc)
            contexto["hojas_originales"] = apoyo
            vistos=set()
            for hoja in apoyo["hojas"]:
                for ref in hoja.get("diametros_contextuales") or []:
                    if ref["diam_in"] in vistos:
                        continue
                    vistos.add(ref["diam_in"])
                    contexto["evidencias"].append(dict(id=f'E{len(contexto["evidencias"])+1}',clase="hoja_original",
                        diam_in=ref["diam_in"],texto=ref["texto"],documento=hoja["documento"],pagina=hoja["pagina"],
                        asociacion="Referencia de la misma utilidad en la hoja original; no asignada a esta línea"))
        # continuidad con la red: líneas confirmadas que siguen de frente, ramal/principal (ingeniería)
        from nucleo import diametro_continuidad
        try:
            cont = diametro_continuidad.analizar(i, self.pipes, ft_px or None, getattr(self, "structures", ()))
            for o in cont["opciones"]:
                o["normativa"] = diametro_plano.permitido(cat, p, o["diam_in"])
        except Exception:                             # noqa: BLE001 (complemento: sin ella se revisa igual)
            cont = None
        from nucleo import diametro_vecinas, model_ops
        f = DI.ficha(p, utility_label(p.get("layer") or ""), permit, largo, catalogo=cat, contexto=contexto,
                     continuidad=cont, nombre=(p.get("name") or "").strip() or model_ops.nombre_por_defecto(p, i),
                     vecinas=diametro_vecinas.vecinas(i, self.pipes, ft_px or None, (cont or {}).get("lados")),
                     tramo=diametro_vecinas.tramo_sin_diametro(i, self.pipes, ft_px or None,
                                                               getattr(self, "structures", ())))
        f["documento"] = documento
        self._diam_ia_origenes[self._diam_ia_clave(f)] = dict(planes=planes,originales=originales)
        if len(self._diam_ia_origenes)>64:
            self._diam_ia_origenes.pop(next(iter(self._diam_ia_origenes)))
        return f

    def _diam_ia_clave(self, f):
        return json.dumps(f, sort_keys=True, ensure_ascii=False)

    def _diam_ia_sug(self, i):
        """La sugerencia ya conocida de la utilidad `i` (de esta sesión o de la caché de la IA), o None."""
        p = self.pipes[i] if 0 <= i < len(self.pipes) else {}
        if "cerca" not in (p.get("diam_plano") or {}):
            return None
        f = self._diam_ia_ficha(i)
        s = self._diam_ia.get(self._diam_ia_clave(f))
        if s is None:
            prov = self._diam_ia_proveedor()
            if prov is not None:
                from ia import diametro_ia as DI
                guardada = self._ia_memoria().redaccion(DI.clave_de(f, prov.config.modelo))
                if guardada:
                    s = DI.Sugerencia.de_dict(json.loads(guardada))
                    self._diam_ia[self._diam_ia_clave(f)] = s
        return s

    # ── mostrar ──
    def _diam_ia_refrescar(self):
        if getattr(self, "tarjeta_diam_ia", None) is None:
            return
        i = self._diam_ia_actual() if self._diam_ia_proveedor() is not None else None
        cambia_seleccion = i != getattr(self, "_diam_ia_pipe", None)
        if cambia_seleccion and getattr(self, "_diam_ia_pedido", None) is not None:
            self._diam_ia_detener()                      # otra utilidad: el pedido anterior no sigue
        self._diam_ia_pipe = i
        self.tarjeta_diam_ia.setVisible(i is not None)
        if i is None or cambia_seleccion:
            self._diam_ia_quitar_senales()
        if i is None:
            return
        if cambia_seleccion:
            self._diam_ia_revelar(i)
        self._ic_diam_ia.setPixmap(_icon("mdi:creation", color=_theme.tokens().accent).pixmap(16, 16))
        self.btn_diam_ia_detalles.setVisible(False)
        for b in (self.btn_diam_ia_preguntar, self.btn_diam_ia_usar, self.btn_diam_ia_vecinas, self.btn_diam_ia_no,
                  self.btn_diam_ia_detener):
            b.setVisible(False)
        self._diam_ia_replica_mostrar(i, False)
        if getattr(self, "_diam_ia_pedido", None) is not None:
            self._diam_ia_tic()
            self.btn_diam_ia_detener.setVisible(True)
            return
        if "cerca" not in (self.pipes[i].get("diam_plano") or {}):
            self.lbl_diam_ia.setText(html.escape(_tr("Vuelve a reconocer la hoja para que pueda revisar esta "
                                                   "línea con lo que dice el plano.")))
            return
        if self.isVisible() and self._diam_ia_clave_ficha(i) not in self._diam_ia_fichas:
            # La selección se muestra ya; la ficha se arma después, sin hacer esperar al panel.
            self.lbl_diam_ia.setText(html.escape(_tr("Preparando la revisión de esta línea…")))
            self._diam_ia_carga.start()
            return
        s = self._diam_ia_sug(i)
        if s is None:
            self.lbl_diam_ia.setText(html.escape(_tr("Voy a revisar los rótulos y las líneas vecinas; si no hay una "
                                                   "lectura segura, te propongo un diámetro según la continuidad de la "
                                                   "red y tu normativa.")))
            self.btn_diam_ia_preguntar.setVisible(True)
            f = self._diam_ia_ficha(i)
            clave = self._diam_ia_clave(f)
            if self._diam_ia_auto and clave not in self._diam_ia_intentadas:
                self._diam_ia_intentadas.add(clave)
                def revisar():
                    if (self._diam_ia_actual() == i and self._diam_ia_clave(self._diam_ia_ficha(i)) == clave
                            and getattr(self, "_diam_ia_pedido", None) is None):
                        self.preguntar_diametro_ia(i)
                QtCore.QTimer.singleShot(0, revisar)
            return
        self._diam_ia_mostrar(i, s)
        self._diam_ia_senalar(i, s)

    def _diam_ia_cargar(self):
        i = self._diam_ia_actual() if self._diam_ia_proveedor() is not None else None
        if i is None or i != getattr(self, "_diam_ia_pipe", None):
            return
        self._diam_ia_ficha(i)
        self._diam_ia_refrescar()
        self._diam_ia_revelar(i)                     # creció: que su botón siga a la vista

    def _diam_ia_mostrar(self, i, s):
        from ia import diametro_agente as DA
        from nucleo import normas_catalogo as nc
        f = self._diam_ia_ficha(i)
        acento = _theme.tokens().accent
        self.btn_diam_ia_detalles.setVisible(bool(s.analisis))
        motivo = " ".join(s.motivo.split())
        if len(motivo) > 240:
            motivo = motivo[:237].rsplit(" ", 1)[0] + "…"
        if s.diam_in:
            def breve(v, n=110):
                txt = " ".join(str(v or "").split())
                return html.escape(txt if len(txt) <= n else txt[:n-1].rsplit(" ",1)[0]+"…")
            def fila(nombre, valor, n=110):
                return "<br><b>" + html.escape(_tr(nombre)) + "</b> " + breve(valor, n)
            t = _theme.tokens()
            # chat (2.ª vuelta 2026-11-03): la IA habla en primera persona; los datos van abajo, en chico
            txt = (f"<span style='color:{t.accent}; font-size:15px'><b>"
                   + html.escape(_tr("Propuesta: {d}").format(d=nc.texto_pulgadas(s.diam_in))) + "</b></span>")
            if motivo:
                txt += "<br>" + DA.enlazar(breve(motivo, 320), f, acento)
            txt += f"<div style='margin-top:6px; color:{t.text_muted}; font-size:11px'>"
            norma = s.analisis.get("opcion") or {}
            if norma:
                if norma.get("criterio") and " ".join(str(norma["criterio"]).split()) != motivo:
                    txt += fila("Criterio:", norma.get("criterio"))
                txt += fila("Fuente:", norma.get("fuente"), 75)
            elif s.rotulo:
                txt += fila("Criterio:", _tr("Rótulo asociado a esta línea"))
                txt += fila("Fuente:", _tr("Plano PDF"))
            elif s.origen == "usuario":
                txt += fila("Criterio:", _tr("Diámetro que indicaste en la conversación"))
            elif s.origen == "zona":
                txt += fila("Criterio:", _tr("Texto del plano fuera de la línea: confirma que vale para ella"))
            entrada = s.analisis.get("entrada") or {}
            contexto = entrada.get("contexto") or {}
            ruta = contexto.get("trayecto") or {}
            referencias = []
            if ruta.get("largo_ft") is not None:
                referencias.append(_tr("{l} ft de recorrido").format(l=f'{ruta["largo_ft"]:g}'))
            if ruta.get("giros_mayores_10_grados") is not None:
                referencias.append(_tr("{n} giros").format(n=ruta["giros_mayores_10_grados"]))
            if contexto.get("contactos"):
                referencias.append(_tr("{n} contactos geométricos").format(n=len(contexto["contactos"])))
            hojas=(contexto.get("hojas_originales") or {}).get("hojas") or []
            if hojas:
                referencias.append(_tr("1 hoja original") if len(hojas)==1 else
                                   _tr("{n} hojas originales").format(n=len(hojas)))
            if s.rotulo:
                referencias.append(s.rotulo)
            if referencias:
                txt += fila("Referencia:", " · ".join(referencias))
            if norma.get("tipo_supuesto"):
                txt += fila("Por confirmar:", norma.get("tipo"))
            txt += self._diam_ia_en_plano(s, f)
            txt += "</div>"
            cambia_texto = self.lbl_diam_ia.text() != txt
            self.lbl_diam_ia.setText(txt)
            self.btn_diam_ia_usar.setText(_tr("Aprobar {d}").format(d=nc.texto_pulgadas(s.diam_in)))
            self.btn_diam_ia_usar.setVisible(True)
            self.btn_diam_ia_no.setVisible(True)
            self._diam_ia_oferta_vecinas(i, s, f)
            self._diam_ia_replica_mostrar(i, True)
            if cambia_texto:
                self._diam_ia_revelar(i)
            return
        conv = self._diam_ia_conv_de(i)
        txt = "" if conv else "<b>" + html.escape(_tr("No encontré el diámetro de esta línea con certeza.")) + "</b><br>"
        txt += DA.enlazar(html.escape(motivo), f, acento)
        if s.pista:
            # en la conversación, la pista es la pregunta que la IA te hace a ti (sin intermediarios)
            txt += "<br><br>" + (html.escape(s.pista) if conv else html.escape(_tr("Una pista: {p}").format(p=s.pista)))
        en_plano = self._diam_ia_en_plano(s, f)
        if en_plano:
            txt += f"<div style='margin-top:6px; color:{_theme.tokens().text_muted}; font-size:11px'>{en_plano}</div>"
        cambia_texto = self.lbl_diam_ia.text() != txt
        self.lbl_diam_ia.setText(txt)
        self.btn_diam_ia_no.setVisible(True)
        self.btn_diam_ia_preguntar.setVisible(True)
        self._diam_ia_replica_mostrar(i, True)
        if cambia_texto:
            self._diam_ia_revelar(i)

    def _diam_ia_revelar(self, i):
        """Tras recalcular el alto, desplaza el inspector para acceder a la propuesta y sus acciones."""
        def revelar():
            if not self.isVisible() or self._diam_ia_actual() != i or self.tarjeta_diam_ia.isHidden():
                return
            pila = getattr(self, "pila_derecha", None)
            if pila is None or pila.currentIndex() != 0:
                return
            area = pila.widget(0)
            if not isinstance(area, QtWidgets.QScrollArea):
                return
            tarjeta = self.tarjeta_diam_ia
            destino = tarjeta
            if tarjeta.height() > area.viewport().height() - 24:
                # Una respuesta larga sigue siendo desplazable; el botón para
                # aplicarla debe poder alcanzarse incluso en ventanas pequeñas.
                destino = self._diam_ia_acciones
            area.ensureWidgetVisible(destino, 0, 12)
        QtCore.QTimer.singleShot(_ESPERA_REVELAR_MS, self, revelar)   # cuando el panel ya tomó su nuevo alto

    def _diam_ia_tic(self):
        if getattr(self, "_diam_ia_pedido", None) is not None:
            etapa = getattr(self,"_diam_ia_etapa",None) or _tr("Revisando con la IA")
            t = _theme.tokens()
            self.lbl_diam_ia.setText(f"<i style='color:{t.text_muted}'>" + html.escape(_tr("Pensando… {etapa} · {s} s").format(
                etapa=etapa, s=int(time.monotonic() - self._diam_ia_t0))) + "</i>")

    def _diam_ia_progreso(self, tok, etapa):
        pedido = getattr(self,"_diam_ia_pedido",None)
        if pedido is None or pedido[0] != tok:
            return
        self._diam_ia_etapa = etapa
        self._diam_ia_tic()

    # ── preguntar ──
    def preguntar_diametro_ia(self, i=None):
        i = self._diam_ia_actual() if i is None else i
        prov = self._diam_ia_proveedor()
        if i is None or prov is None or "cerca" not in (self.pipes[i].get("diam_plano") or {}):
            return
        from ia import diametro_ia as DI, diametro_zonas as DZ
        f = self._diam_ia_ficha(i)
        self._diam_ia_intentadas.add(self._diam_ia_clave(f))
        imagen = self._diam_ia_imagen(i, f)
        origen = self._diam_ia_origenes.get(self._diam_ia_clave(f),{})
        capturas=[]
        errores_captura=[]
        try:
            from hoja import contexto_original
            capturas=contexto_original.capturas(getattr(self,"src_pdfs",()) or (),origen.get("planes") or [],
                                               trabajo=getattr(self,"doc",None))
        except Exception as e:
            errores_captura.append("No se pudo generar una captura original: "+str(e)[:150])
        self._diam_ia_evidencias[self._diam_ia_clave(f)] = dict(imagen=imagen, ficha=f, capturas=capturas,
                                                              originales=origen.get("originales") or [],
                                                              advertencias=errores_captura,modelo=prov.config.modelo)
        if len(self._diam_ia_evidencias)>8:
            self._diam_ia_evidencias.pop(next(iter(self._diam_ia_evidencias)))
        mem = self._ia_memoria()
        self._diam_ia_tok += 1
        tok = self._diam_ia_tok
        self._diam_ia_pedido = (tok, i, self._diam_ia_clave(f))
        self._diam_ia_etapa = _tr("Contexto y captura preparados") if imagen else _tr("Contexto preparado")
        self._diam_ia_t0 = time.monotonic()
        self._diam_ia_reloj.start()
        self._diam_ia_refrescar()

        def correr():
            try:
                parar = lambda: self._diam_ia_tok != tok  # noqa: E731
                estado = lambda etapa: self._diam_ia_senales.etapa.emit(tok, etapa)  # noqa: E731
                r = DI.sugerir(prov, f, imagen, mem, cancelado=parar, al_estado=estado, capturas=capturas)
                if DZ.necesita(r):                    # sin certeza: ella decide dónde más mirar
                    r = DZ.revisar(prov, f, r, self._diam_ia_explorador(i, f, tok, prov), parar, estado)
            except Exception as e:                    # noqa: BLE001 (ErrorIA, red: el aviso queda como está)
                r = RE.texto_corto(RE.armar(e, "Diámetro según la IA"))
            self._diam_ia_senales.listo.emit(tok, r)
        threading.Thread(target=correr, name="pdfcad-ia-diametro", daemon=True).start()

    def _diam_ia_imagen(self, i, f):
        """PNG (base64) de la zona de los rótulos con la línea marcada, de la hoja de TRABAJO (donde se reconoció)."""
        doc = getattr(self, "doc", None)
        if doc is None or not self.zoom:
            return None
        try:
            from hoja import recorte_diametro
            page = doc[getattr(self, "page_idx", 0)]
            z = float(self.zoom)
            pts = [(x / z, y / z) for x, y in self.pipes[i]["pts"]]
            from ia import diametro_ia as DI
            # los rótulos que pueden ser suyos primero: el recorte se centra en el primero (`ZONA_MAX_PT`)
            orden = sorted(f["rotulos"], key=lambda e: not DI.elegible(e, f))
            cajas = {e["id"]: tuple(v / z for v in e["caja"]) for e in orden}
            puntas = [(q[0] / z, q[1] / z) for e in f["rotulos"] for q in e.get("puntas") or ()]
            return base64.b64encode(recorte_diametro.recorte(
                # mapa sin capas: letras chicas, la zona de sus rótulos (el trayecto entero las dejaba ilegibles)
                page, pts, cajas, puntos=puntas,
                trayecto_completo=not (f.get("mapa") and cajas))).decode("ascii")
        except Exception:                             # noqa: BLE001 (sin imagen se pregunta igual)
            return None

    def ver_analisis_diametro_ia(self):
        i = self._diam_ia_actual()
        s = self._diam_ia_sug(i) if i is not None else None
        if s is None:
            return
        f = self._diam_ia_ficha(i)
        ev = self._diam_ia_evidencias.get(self._diam_ia_clave(f), {})
        imagen = ev.get("imagen")
        if not ev.get("capturas") and s.analisis.get("capturas_originales"):
            try:
                from hoja import contexto_original
                plan=self._diam_ia_origenes.get(self._diam_ia_clave(f),{}).get("planes") or []
                ev=dict(ev,capturas=contexto_original.capturas(getattr(self,"src_pdfs",()) or (),plan,
                                                               trabajo=getattr(self,"doc",None)))
            except Exception:
                pass
        # La caché conserva el hash de la captura, no imágenes dentro del modelo.
        if imagen is None and s.analisis.get("imagen_usada"):
            import hashlib
            candidata = self._diam_ia_imagen(i, f)
            if candidata and hashlib.sha256(candidata.encode()).hexdigest() == s.analisis.get("imagen_sha256"):
                imagen = candidata
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(_tr("Análisis del diámetro"))
        dlg.resize(820, 700)
        lay = QtWidgets.QVBoxLayout(dlg)
        tabs = QtWidgets.QTabWidget()
        lay.addWidget(tabs, 1)
        vista = QtWidgets.QScrollArea()
        vista.setWidgetResizable(True)
        foto = QtWidgets.QLabel()
        foto.setAlignment(QtCore.Qt.AlignCenter)
        if imagen and s.analisis.get("imagen_usada"):
            pix = QtGui.QPixmap()
            pix.loadFromData(base64.b64decode(imagen))
            foto.setPixmap(pix)
        else:
            foto.setWordWrap(True)
            foto.setText(_tr("Este análisis no usó imagen, o su captura original ya no está disponible."))
        vista.setWidget(foto)
        tabs.addTab(vista, _tr("Imagen analizada"))
        for c in ev.get("capturas") or []:
            if c.get("sha256_png") not in {x.get("sha256_png") for x in s.analisis.get("capturas_originales") or []}:
                continue
            visor=QtWidgets.QScrollArea()
            visor.setWidgetResizable(True)
            caja=QtWidgets.QWidget()
            v=QtWidgets.QVBoxLayout(caja)
            texto=QtWidgets.QLabel(f'{c["documento"]} · {_tr("Hoja {n}").format(n=c["pagina"])} · {c["zona"]}')
            texto.setWordWrap(True)
            v.addWidget(texto)
            foto_original=QtWidgets.QLabel()
            pix=QtGui.QPixmap()
            pix.loadFromData(base64.b64decode(c["imagen"]))
            foto_original.setPixmap(pix)
            v.addWidget(foto_original)
            visor.setWidget(caja)
            tabs.addTab(visor,_tr("Original {n}").format(n=tabs.count()))
        datos = QtWidgets.QPlainTextEdit()
        datos.setReadOnly(True)
        datos.setPlainText(json.dumps(s.analisis.get("entrada") or f, ensure_ascii=False, indent=2))
        tabs.addTab(datos, _tr("Datos enviados") if s.analisis.get("consulta_realizada",True) else _tr("Datos considerados"))
        razon = QtWidgets.QPlainTextEdit()
        razon.setReadOnly(True)
        razon.setPlainText(_tr("Las observaciones y la explicación del modelo son interpretaciones pendientes de revisión.")
                          + "\n\n" + json.dumps(dict(resultado=s.a_dict(),
                                           modelo=ev.get("modelo") or self._config_ia().get("modelo")),
                                       ensure_ascii=False, indent=2))
        tabs.addTab(razon, _tr("Detalle de la decisión"))
        originales=ev.get("originales") or self._diam_ia_origenes.get(self._diam_ia_clave(f),{}).get("originales") or []
        if originales:
            completo=QtWidgets.QPlainTextEdit()
            completo.setReadOnly(True)
            completo.setPlainText(json.dumps(originales,ensure_ascii=False,indent=2))
            tabs.addTab(completo,_tr("Texto completo de origen"))
        cerrar = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        cerrar.rejected.connect(dlg.reject)
        lay.addWidget(cerrar)
        dlg.exec()

    def _diam_ia_listo(self, tok, r):
        pedido = getattr(self, "_diam_ia_pedido", None)
        if pedido is None or pedido[0] != tok:
            return                                    # cancelado: no deja resultado ni pisa la tarjeta
        self._diam_ia_pedido = None
        self._diam_ia_reloj.stop()
        self._diam_ia_replica_lista(pedido[2], r)    # era una réplica: se anota el turno
        if isinstance(r, str):
            self._diam_ia_refrescar()
            self.lbl_diam_ia.setText(html.escape(_tr("No pude responderte: {e}").format(e=r)))
            self._diam_ia_revelar(pedido[1])
            return
        self._diam_ia[pedido[2]] = r
        self._diam_ia_guardar_zonas(pedido[2], r)
        self._diam_ia_refrescar()

    def _diam_ia_detener(self):
        self._diam_ia_tok += 1
        self._diam_ia_pedido = None
        self._diam_ia_replica_pendiente = None
        self._diam_ia_reloj.stop()
        if getattr(self, "_diam_ia_pipe", None) is not None:
            self._diam_ia_refrescar()

    # ── usar / no es correcto ──
    def usar_diametro_ia(self, i=None):
        i = self._diam_ia_actual() if i is None else i
        s = self._diam_ia_sug(i) if i is not None else None
        if s is None or not s.diam_in:
            return
        f = self._diam_ia_ficha(i)                    # antes de aplicar: después la ficha cambia
        conv = self._diam_ia_conv_de(i)
        if self._diam_ia_aplicar(i, s.diam_in) and conv:
            from ia import diametro_ia_replica as DR
            DR.aprender(self._ia_memoria(), f, conv, s.diam_in)

    def _diam_ia_aplicar(self, i, diam):
        from nucleo import edicion3d, edicion_bloque
        p = self.pipes[i]
        if (p.get("pipe_family") or "").strip():
            cb = self.prop_size
            k = next((k for k in range(cb.count()) if cb.itemData(k) and
                      abs(edicion_bloque.diam_de_tamano(cb.itemData(k)) - diam) < 1e-6), -1)
            if k < 0 or not self.editar_diametro_3d(i, cb.itemData(k)):
                from nucleo import normas_catalogo as nc
                self.informar(_tr("Diámetro según la IA"), _tr("La familia de esta utilidad no tiene un tamaño de {d}: "
                                                           "elige el tamaño en el panel.").format(
                    d=nc.texto_pulgadas(diam)))
                return False
            return True
        self._push()
        edicion3d.aplicar_diametro(p, edicion_bloque.dato_diam(diam))
        self._dirty = True
        self._refresh_lists()
        self._reselect_pipes([i])
        self._redraw()
        return True

    def cambiar_diametro_ia(self):
        i = self._diam_ia_actual()
        if i is None:
            return
        from nucleo import model_ops
        s = self._diam_ia_sug(i)
        d = s.diam_in if s and s.diam_in else model_ops.diametro(self.pipes[i])[0]
        valor, ok = QtWidgets.QInputDialog.getDouble(
            self, _tr("Diámetro personalizado"), _tr("Diámetro (pulgadas):"), float(d), 0.125, 240.0, 3)
        if not ok:
            return
        # Conserva la ficha anterior: al aplicar cambia la clave y desaparece el aviso.
        f = self._diam_ia_ficha(i)
        if self._diam_ia_aplicar(i, valor) and s and s.diam_in:
            from ia import diametro_ia as DI
            DI.aprender_error(self._ia_memoria(), f, s)

    def rechazar_diametro_ia(self, i=None):
        i = self._diam_ia_actual() if i is None else i
        s = self._diam_ia_sug(i) if i is not None else None
        if s is None or not s.diam_in:
            return
        from ia import diametro_ia as DI
        f = self._diam_ia_ficha(i)
        mem = self._ia_memoria()
        DI.aprender_error(mem, f, s)
        no = self._diam_ia[self._diam_ia_clave(f)] = DI.Sugerencia(
            None, s.rotulo, "alta", _tr("Marcado como incorrecto: el equipo dijo que ese rótulo no es su diámetro."),
            "", "descartada")
        prov = self._diam_ia_proveedor()
        if prov is not None:                         # la caché tampoco la vuelve a mostrar
            mem.guardar_redaccion(DI.clave_de(f, prov.config.modelo), json.dumps(no.a_dict(), ensure_ascii=False),
                                  prov.config.modelo)
        self._diam_ia_refrescar()

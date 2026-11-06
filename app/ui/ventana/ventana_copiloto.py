"""El Copiloto del proyecto en la ventana (spec `docs/superpowers/specs/2026-11-04-copiloto-bloque1-design.md`).

La app mide, prueba y aplica; la IA solo elige entre opciones ya validadas. Nada cambia sin la confirmación del usuario.
"""
from __future__ import annotations

import threading

from PySide6 import QtCore

from nucleo import bitacora, copiloto_cola as CC, copiloto_estado, edicion_bloque, model_ops, normas_catalogo as nc, soluciones
from traduccion.i18n import t as _tr

CADUCADO = "caducado"
SIN_TAMANO = "sin_tamano"
TOPE_DESHACER = 400                                    # `Main._push`


class _Senales(QtCore.QObject):
    listo = QtCore.Signal(object, object)              # (Item, Sugerencia | texto del error)


class CopilotoMixin:
    _cop_sesion = 0                                    # sube al cambiar de proyecto: las tarjetas viejas caducan
    _cop_revisando = None                              # línea en revisión: el inspector no consulta esa por su cuenta
    _cop_senales = None
    _cop_en_vuelo = None                               # clave de la línea que la IA está revisando
    _cop_espera = ()                                   # [(item, al_listo)] pedidos detrás del que está en vuelo

    def copiloto_estado(self):
        """Qué falta para exportar, con los avisos ya calculados."""
        self._resultados_al_dia()
        return copiloto_estado.armar(getattr(self, "_conflictos", None) or [],
                                     getattr(self, "_normas_avisos", None) or [],
                                     conflictos_ocultos=self.copiloto_conflictos_ocultos(),
                                     sin_escala=bool(self.pipes) and not (self.scale and self.zoom))

    def copiloto_conflictos_ocultos(self):
        return not self.chk_show_conflicts.isChecked()

    def copiloto_tamano(self, i, diam):
        """El dato de tamaño de `diam` para la utilidad i, o None si su familia no lo tiene."""
        p = self.pipes[i]
        fid = (p.get("pipe_family") or "").strip()
        if not fid:
            return edicion_bloque.dato_diam(diam)
        if not self.civil_year:
            return None
        from catalogo import civil_catalog as _cc
        sizes = (_cc.pressure_pipe_sizes(self.civil_year, fid) if (p.get("net_type") or "") == "pressure"
                 else _cc.pipe_sizes(self.civil_year, fid))
        return next((s for s in sizes or [] if abs(edicion_bloque.diam_de_tamano(s) - diam) < 1e-6), None)

    def _copiloto_entrada(self):
        """Lo que necesita la clasificación, leído en la ventana: el hilo no toca nada vivo."""
        from ia import diametro_ia as DI
        self._resultados_al_dia()
        ft = self.scale / self.zoom if self.scale and self.zoom else None
        con_db = {i for i in range(len(self.pipes)) if self._duct_bank_for_pipe(i) is not None}
        return dict(avisos=list(getattr(self, "_normas_avisos", None) or []), pipes=self.pipes,
                    normas_cat=getattr(self, "normas_cat", None), ft_px=ft, estructuras=list(self.structures),
                    con_bancoducto=con_db, tamano_de=self.copiloto_tamano,
                    saltados=list(self.revision.get("saltados") or ()),
                    elegible=lambda e, p: DI.elegible(e, {"utilidad": p.get("layer") or ""}))

    def copiloto_cola(self, clase=None, al_paso=None, al_terminar=None):
        """Clasifica los avisos pendientes en un hilo; `al_terminar(cola, error)`. Devuelve el `TrabajoPasos`."""
        from ui.comun.trabajo_pasos import TrabajoPasos
        e = self._copiloto_entrada()
        if clase:
            e["avisos"] = [a for a in e["avisos"] if a.clase == clase]

        def pasos():
            return (yield ("hilo", lambda: CC.clasificar(e["avisos"], e["pipes"], e["normas_cat"], e["ft_px"],
                                                         e["estructuras"], e["con_bancoducto"], e["tamano_de"],
                                                         e["saltados"], al_paso, e["elegible"])))
        return TrabajoPasos(self, pasos(), al_terminar=al_terminar).empezar()

    def copiloto_firma(self):
        return self._firma_modelo(), self._cop_sesion

    def _copiloto_vigente(self, firma, sesion):
        return sesion == self._cop_sesion and firma == self._firma_modelo()

    def copiloto_aplicar_seguros(self, items, firma, sesion):
        """(aplicados, motivo). Un solo paso de deshacer. Si el proyecto cambió desde que se clasificó, no aplica."""
        if not self._copiloto_vigente(firma, sesion):
            return 0, CADUCADO
        if not items:
            return 0, ""
        self._push()
        try:
            detalle = [self._copiloto_aplicar_item(x) for x in items]
        except Exception as e:                         # noqa: BLE001 (se dice en el chat; no queda a medias)
            self._restore(self._undo.pop())
            return 0, str(e)
        bitacora.agregar(self.bitacora, "tanda", _tr("Tanda segura: {n} utilidad(es)").format(n=len(detalle)), detalle,
                         paso=len(self._undo))
        self._dirty = True
        self._refresh_lists()
        self._redraw()
        return len(detalle), ""

    def _copiloto_aplicar_item(self, x):
        i = x.aviso.pipe
        p = self.pipes[i]
        if isinstance(x.valor, str):
            antes, despues, cambios = p.get("tipo") or "", x.valor, {"tipo": x.valor}
            evidencia = _tr("Único tipo posible en las normativas")
        else:
            antes = nc.texto_pulgadas(model_ops.diametro(p)[0])
            despues, cambios = nc.texto_pulgadas(x.valor), {"tamano": self.copiloto_tamano(i, x.valor)}
            evidencia = _tr("Continuidad de la red")
        edicion_bloque.aplicar(self.pipes, [i], cambios)
        return dict(codigo=soluciones.codigo(self.pipes, i), antes=antes, despues=despues,
                    por_que=x.motivo or evidencia, evidencia=evidencia)

    # ── línea por línea ──
    def copiloto_pedir(self, item, al_listo=None):
        """La sugerencia de la IA para `item`, sin depender de la selección: `al_listo(item, Sugerencia | texto)`. Un
        solo pedido en vuelo; los demás esperan su turno. Sin `al_listo` es adelantar la línea que sigue."""
        i = item.aviso.pipe
        prov = self._diam_ia_proveedor()
        aviso = None
        if not 0 <= i < len(self.pipes):               # se borraron utilidades mientras esperaba su turno
            aviso = _tr("Esta línea ya no está.")
        elif prov is None:
            aviso = _tr("La IA no está configurada.")
        elif "cerca" not in (self.pipes[i].get("diam_plano") or {}):
            aviso = _tr("Vuelve a reconocer la hoja para que la IA pueda revisar esta línea.")
        s = None if aviso else self._diam_ia_sug(i)
        if aviso or s is not None:
            if al_listo is not None:
                al_listo(item, aviso or s)
            return
        if self._cop_en_vuelo is not None:
            self._cop_espera = list(self._cop_espera) + [(item, al_listo)]
            return
        self._copiloto_lanzar(item, al_listo, prov)

    def _copiloto_lanzar(self, item, al_listo, prov):
        if self._cop_senales is None:
            self._cop_senales = _Senales(self)
            self._cop_senales.listo.connect(self._copiloto_listo)
        i, sesion, tok = item.aviso.pipe, self._cop_sesion, self._diam_ia_tok
        f, imagen, capturas = self._diam_ia_insumos(i, prov)
        clave, mem = self._diam_ia_clave(f), self._ia_memoria()
        self._cop_en_vuelo = (item, al_listo, clave, sesion)

        def correr():
            try:
                r = self._diam_ia_consultar(prov, f, imagen, capturas, i, tok, mem, lambda: sesion != self._cop_sesion,
                                            lambda _etapa: None)
            except Exception as e:                     # noqa: BLE001 (ErrorIA, red: se dice en el chat)
                r = str(e)
            self._cop_senales.listo.emit(item, r)
        threading.Thread(target=correr, name="pdfcad-copiloto", daemon=True).start()

    def _copiloto_listo(self, item, r):
        _i, al_listo, clave, sesion = self._cop_en_vuelo
        self._cop_en_vuelo = None
        if sesion != self._cop_sesion:                 # era del proyecto anterior
            return
        if not isinstance(r, str):
            self._diam_ia[clave] = r
        if al_listo is not None:
            al_listo(item, r)
        for k, (otro, cb) in enumerate(self._cop_espera):
            self._cop_espera = self._cop_espera[k + 1:]
            self.copiloto_pedir(otro, cb)
            break

    def copiloto_esperar(self, item, al_listo):
        """Si `item` ya va en vuelo o en espera, que avise a `al_listo`; devuelve False si no estaba pedido."""
        vuelo = self._cop_en_vuelo
        if vuelo is not None and vuelo[0].clave == item.clave:
            self._cop_en_vuelo = (vuelo[0], al_listo, vuelo[2], vuelo[3])
            return True
        for k, (otro, _cb) in enumerate(self._cop_espera):
            if otro.clave == item.clave:
                self._cop_espera[k] = (otro, al_listo)
                return True
        return False

    def copiloto_decidir(self, item, accion, firma, sesion, valor=None, sug=None):
        """aprobar | otro | saltar. Devuelve "" si se hizo, `CADUCADO` o `SIN_TAMANO`. Si el proyecto cambió desde que se
        clasificó (`firma`) no se hace: los índices pueden ser de otra utilidad."""
        if not self._copiloto_vigente(firma, sesion):
            return CADUCADO
        if accion == "saltar":
            self.revision.setdefault("saltados", []).append(item.clave)
            self._dirty = True
            return ""
        from ia import diametro_ia as DI, diametro_ia_replica as DR
        i = item.aviso.pipe
        p = self.pipes[i]
        d = sug.diam_in if accion == "aprobar" else valor
        f, conv = self._diam_ia_ficha(i), self._diam_ia_conv_de(i)       # antes de aplicar: después cambian
        antes, codigo = nc.texto_pulgadas(model_ops.diametro(p)[0]), soluciones.codigo(self.pipes, i)
        if not self._diam_ia_aplicar(i, d):
            return SIN_TAMANO
        if accion == "aprobar" and conv:
            DR.aprender(self._ia_memoria(), f, conv, d)
        elif accion == "otro" and sug is not None and sug.diam_in:
            DI.aprender_error(self._ia_memoria(), f, sug)
        por_que = (sug.motivo if accion == "aprobar" else _tr("Lo indicó el usuario")) or ""
        bitacora.agregar(self.bitacora, "decision", _tr("{c}: diámetro {d}").format(c=codigo, d=nc.texto_pulgadas(d)),
                         [dict(codigo=codigo, antes=antes, despues=nc.texto_pulgadas(d), por_que=por_que,
                               evidencia=getattr(sug, "origen", "") if accion == "aprobar" else "")],
                         paso=len(self._undo))
        return ""

    # ── decisiones por grupo ──
    def copiloto_aprobar_grupo(self, items, nota, firma, sesion):
        """Aprueba esos avisos con su motivo, en un paso de deshacer. Sin nota no: una aprobación en grupo sin motivo no
        deja trazabilidad. Los datos de las utilidades no cambian."""
        nota = (nota or "").strip()
        if not nota or not items or not self._copiloto_vigente(firma, sesion):
            return 0
        n = self.aprobar_avisos([x.aviso for x in items], nota)
        bitacora.agregar(self.bitacora, "aprobacion", _tr("{n} aviso(s) aprobado(s)").format(n=n),
                         [dict(codigo=x.etiqueta, antes=x.aviso.mensaje, despues=_tr("Aprobado"), por_que=nota,
                               evidencia=x.motivo) for x in items], paso=len(self._undo))
        return n

    # ── bitácora ──
    def copiloto_ultima_tanda(self):
        """El id de la entrada que es el último paso de deshacer, o None. Revertir una anterior dejando lo posterior
        podría romper lo que vino después."""
        e = next((x for x in reversed(self.bitacora) if not x.get("deshecha")), None)
        if e is None or len(self._undo) >= TOPE_DESHACER:   # en el tope la cuenta ya no dice qué paso es
            return None
        return e["id"] if e.get("paso") == len(self._undo) else None

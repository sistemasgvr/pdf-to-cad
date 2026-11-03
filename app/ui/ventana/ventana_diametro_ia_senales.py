"""La IA del diámetro te muestra en el plano de qué habla (pedido del usuario 2026-11-03; lo puro en `ia/diametro_agente`
y `nucleo/diametro_vecinas`).

Las líneas y rótulos que la IA nombra quedan marcados mientras la tarjeta muestra esa línea (`_diam_ia_senalar`) y sus
códigos en el chat son enlaces que llevan a ese lugar sin cambiar la selección (`_diam_ia_ir`: elegir otra línea
cerraría la conversación). Si la propuesta vale también para las líneas sin dato que siguen de frente, se marcan y un
botón las aprueba de una vez, en UN paso de deshacer (`usar_diametro_en_vecinas`): nada cambia sin ese clic.

Mezcla de `DiametroIAMixin`: usa `_diam_ia_*` de esa clase.
"""
import html
import json
import threading

from ui.ventana.ventana_comun import *  # noqa: F401,F403
from ui.comun.marcas_ia import MarcasIA

_ESPERA_ZONA_S = 60


class _Explorador:
    """Las zonas del plano para `ia/diametro_zonas`: la IA corre en un hilo y la hoja se lee en la ventana."""

    def __init__(self, win, i, f, tok, prov):
        self._win, self._i, self._f, self._tok, self._prov = win, i, f, tok, prov
        self._menu = None

    def _pedir(self, fn):
        caja = {"listo": threading.Event()}
        self._win._diam_ia_senales.puente.emit(fn, caja)
        for _ in range(_ESPERA_ZONA_S * 10):
            if caja["listo"].wait(0.1):
                return caja.get("r")
            if self._win._diam_ia_tok != self._tok:
                break
        return None

    def menu(self):
        if self._menu is None:
            vision = self._prov.vision()
            self._menu = self._pedir(lambda: self._win._diam_ia_menu_zonas(self._f, vision)) or []
        return self._menu

    def ver(self, zona):
        return self._pedir(lambda: self._win._diam_ia_ver_zona(self._i, self._f, zona))


class SenalesDiametroMixin:
    def _diam_ia_marcas(self):
        if getattr(self, "_diam_ia_mi", None) is None:
            self._diam_ia_mi = MarcasIA(self.canvas)
            self._diam_ia_mi_clave = None
        return self._diam_ia_mi

    def _diam_ia_quitar_senales(self):
        if getattr(self, "_diam_ia_mi", None) is not None:
            self._diam_ia_mi.quitar()
            self._diam_ia_mi_clave = None
        self._diam_ia_extra = None

    def _diam_ia_centro(self, j):
        pts = self._pipe_display_pts(self.pipes[j])
        return pts[len(pts) // 2]

    # ── las zonas que pide la IA (`ia/diametro_zonas`; misma ruta en todos los flujos: las hojas de origen) ──
    def _diam_ia_explorador(self, i, f, tok, prov):
        return _Explorador(self, i, f, tok, prov)

    def _diam_ia_puente(self, fn, caja):
        try:
            caja["r"] = fn()
        except Exception:                             # noqa: BLE001 (buscar es un complemento: sin zona sigue igual)
            caja["r"] = None
        caja["listo"].set()

    def _diam_ia_menu_zonas(self, f, vision):
        from hoja import zonas_diametro
        origen = self._diam_ia_origenes.get(self._diam_ia_clave(f)) or {}
        zonas = zonas_diametro.menu(getattr(self, "src_pdfs", ()) or (), origen.get("planes"),
                                    trabajo=getattr(self, "doc", None), con_imagen=vision)
        comp = getattr(self, "composite", None)
        if comp is None or comp.is_single_full_page():   # la hoja de trabajo es la original: se puede marcar
            for z in zonas:
                if z["hoja"] == getattr(self, "page_idx", 0):
                    z["caja_px"] = [v * self.zoom for v in z["region"]]
        return zonas

    def _diam_ia_ver_zona(self, i, f, zona):
        from hoja import zonas_diametro
        from nucleo import diametro_plano
        visto = zonas_diametro.leer(getattr(self, "src_pdfs", ()) or (), zona, trabajo=getattr(self, "doc", None))
        cat = getattr(self, "normas_cat", None)
        for o in visto["opciones"]:
            o["normativa"] = diametro_plano.permitido(cat, self.pipes[i], o["diam_in"])
        ev = self._diam_ia_evidencias.get(self._diam_ia_clave(f))
        if ev is not None and visto["captura"]:
            ev["capturas"] = list(ev.get("capturas") or []) + [visto["captura"]]   # para «Ver análisis»
        return visto

    def _diam_ia_guardar_zonas(self, clave, s):
        """Lo que halló buscando queda en la caché, para no volver a mirar lo mismo."""
        prov = self._diam_ia_proveedor()
        if prov is not None and getattr(s, "zonas", None):
            from ia import diametro_ia as DI
            self._ia_memoria().guardar_redaccion(DI.clave_de(json.loads(clave), prov.config.modelo),
                                                 json.dumps(s.a_dict(), ensure_ascii=False), prov.config.modelo)

    # ── marcar ──
    def _diam_ia_senalar(self, i, s):
        from ia import diametro_agente as DA
        f = self._diam_ia_ficha(i)
        ids = DA.marcas(s, f)
        extra = getattr(self, "_diam_ia_extra", None)
        if extra and extra not in ids:
            ids.append(extra)
        tramo = self._diam_ia_tramo(s, f)
        marcas = self._diam_ia_marcas()
        zonas = [z for z in getattr(s, "zonas", None) or [] if z.get("caja_px")]
        clave = (i, tuple(ids), tuple(tramo), tuple(z["id"] for z in zonas))
        if clave == self._diam_ia_mi_clave and marcas.vigentes():
            return
        lineas, rotulos = [], []
        for ident in ids:
            v, e = DA.vecina(f, ident), DA.rotulo(f, ident)
            if v is not None and 0 <= v["linea"] < len(self.pipes):
                rol = DA.rol_txt(v["rol"])
                lineas.append((self._pipe_display_pts(self.pipes[v["linea"]]), f'{v["nombre"]} · {rol}',
                               self._diam_ia_centro(v["linea"])))
            elif e is not None and e.get("caja"):
                rotulos.append((*e["caja"], ident))
        rotulos += [(*z["caja_px"], _tr("Miré aquí")) for z in zonas]
        if lineas or rotulos or tramo:
            lineas.append((self._pipe_display_pts(self.pipes[i]), _tr("Esta línea"), self._diam_ia_centro(i)))
        for j in tramo:
            lineas.append((self._pipe_display_pts(self.pipes[j]), _tr("Sigue de frente, sin diámetro"),
                           self._diam_ia_centro(j)))
        marcas.poner(lineas, rotulos)
        self._diam_ia_mi_clave = clave

    def _diam_ia_en_plano(self, s, f):
        """«En el plano: …» con un enlace por cada cosa señalada (html), o ""."""
        from ia import diametro_agente as DA
        from ia import diametro_zonas as DZ
        ids = DA.marcas(s, f)
        txt = ""
        if ids:
            enlaces = DA.enlazar(html.escape(", ".join(ids)), f, _theme.tokens().accent)
            txt = "<br><b>" + html.escape(_tr("En el plano:")) + "</b> " + enlaces
        miradas = DZ.resumen_vistas(s)
        if miradas:
            txt += "<br><b>" + html.escape(_tr("Miré:")) + "</b> " + html.escape(miradas)
        return txt

    def _diam_ia_ir(self, enlace):
        """Clic en un código del chat: lleva el plano a ese lugar y lo deja marcado, sin cambiar la selección."""
        from ia import diametro_agente as DA
        i = self._diam_ia_actual()
        if i is None:
            return
        ident = str(enlace).split(":", 1)[-1]
        f = self._diam_ia_ficha(i)
        v, e = DA.vecina(f, ident), DA.rotulo(f, ident)
        if v is not None and 0 <= v["linea"] < len(self.pipes):
            x, y = v.get("punto") or self._diam_ia_centro(v["linea"])
        elif e is not None and e.get("caja"):
            x0, y0, x1, y1 = e["caja"]
            x, y = (x0 + x1) / 2, (y0 + y1) / 2
        else:
            return
        self._diam_ia_extra = ident
        s = self._diam_ia_sug(i)
        if s is not None:
            self._diam_ia_senalar(i, s)
        self._ir_a_elemento(x, y, activar=False)

    # ── aprobar también en las que siguen ──
    def _diam_ia_tramo(self, s, f):
        """Las líneas que siguen de frente a las que se les puede ofrecer el diámetro propuesto."""
        from nucleo import diametro_plano
        if not s.diam_in:
            return []
        cat = getattr(self, "normas_cat", None)
        return [j for j in f.get("tramo") or [] if 0 <= j < len(self.pipes) and self._duct_bank_for_pipe(j) is None
                and diametro_plano.permitido(cat, self.pipes[j], s.diam_in)]

    def _diam_ia_oferta_vecinas(self, i, s, f):
        n = len(self._diam_ia_tramo(s, f))
        self.btn_diam_ia_vecinas.setVisible(n > 0)
        if n:
            self.btn_diam_ia_vecinas.setText(_tr("Aprobar en esta y {n} más").format(n=n))
            self.btn_diam_ia_vecinas.setToolTip(_tr(
                "También en las líneas marcadas: siguen de frente a esta, sin diámetro confirmado y sin un buzón o "
                "caja entre medio. Se deshace con Ctrl+Z."))

    def _diam_ia_dato(self, p, diam):
        """El tamaño de `diam` para la utilidad `p`, o None si su familia no lo tiene."""
        from nucleo import edicion_bloque
        fid = (p.get("pipe_family") or "").strip()
        if not fid:
            return edicion_bloque.dato_diam(diam)
        if not self.civil_year:
            return None
        from catalogo import civil_catalog as cc
        from nucleo.model import network_kind
        tamanos = (cc.pressure_pipe_sizes if network_kind(p.get("layer") or "") == "pressure" else cc.pipe_sizes)(
            self.civil_year, fid)
        return next((z for z in tamanos if abs(edicion_bloque.diam_de_tamano(z) - diam) < 1e-6), None)

    def usar_diametro_en_vecinas(self, i=None):
        from ia import diametro_ia_replica as DR
        from nucleo import edicion3d, normas_catalogo as nc
        i = self._diam_ia_actual() if i is None else i
        s = self._diam_ia_sug(i) if i is not None else None
        if s is None or not s.diam_in:
            return
        f = self._diam_ia_ficha(i)                    # antes de aplicar: después la ficha cambia
        conv = self._diam_ia_conv_de(i)
        tramo = self._diam_ia_tramo(s, f)
        datos = {j: self._diam_ia_dato(self.pipes[j], s.diam_in) for j in [i] + tramo}
        titulo = _tr("Diámetro según la IA")
        if datos[i] is None:
            self.informar(titulo, _tr("La familia de esta utilidad no tiene un tamaño de {d}: elige el tamaño en el "
                                      "panel.").format(d=nc.texto_pulgadas(s.diam_in)))
            return
        hechas = [j for j, dato in datos.items() if dato is not None]
        self._push()
        for j in hechas:
            edicion3d.aplicar_diametro(self.pipes[j], datos[j])
        self._dirty = True
        self._refresh_lists()
        self._reselect_pipes([i])
        self._redraw()
        if conv:
            DR.aprender(self._ia_memoria(), f, conv, s.diam_in)
        texto = _tr("{d} en {n} líneas. Ctrl+Z lo deshace.").format(d=nc.texto_pulgadas(s.diam_in), n=len(hechas))
        faltan = len(datos) - len(hechas)
        if faltan:
            texto += " " + _tr("{n} no cambiaron: su familia no tiene ese tamaño.").format(n=faltan)
        self.informar(titulo, texto)

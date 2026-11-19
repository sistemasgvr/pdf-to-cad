"""Respuestas del usuario sobre las capas de red en IMAGEN (plan 2026-11-18 «Ejes de la red en imagen», Tarea 7).

Una capa de línea de imagen que `certeza_capas` no da por segura no se reconoce sola: se le pregunta al usuario (la
tarjeta es la Tarea 8). Su respuesta —una utilidad o «No es una red» (`NO_RED`)— se guarda en
`Main.capas_imagen_respuestas` = {sha1 del PDF de origen: {capa: utilidad | NO_RED}}: vale en cualquier hoja de ese
PDF (otro PDF vuelve a decidir), va al .digproj y a `respaldo_editor.CLAVES` (el dict se REEMPLAZA, nunca se cambia en
su lugar: «Cancelar» lo deja como estaba). Los roles de la hoja se rehacen con `roles_iniciales` (la respuesta manda).
"""
from __future__ import annotations

from ui.asistente.roles_iniciales import NO_RED  # noqa: F401 — la constante pública vive aquí también


class CapasImagenMixin:
    capas_imagen_respuestas: dict | None = None   # `Main.__init__` pone un dict propio; siempre se REEMPLAZA

    # ── de qué PDF es la hoja ──────────────────────────────────────────────
    def _indices_de_hoja(self) -> list:
        """Índices en `src_pdfs` de los PDF de origen de la hoja que se reconoce: los de sus piezas (con una utilidad
        agregada, los de su grupo); sin hoja compuesta, todos."""
        n = len(getattr(self, "src_pdfs", None) or ())
        piezas = list(getattr(getattr(self, "composite", None), "pieces", None) or ())
        ov = getattr(self, "_rec_hoja", None)
        if ov is not None:
            piezas = [p for p in piezas if int(getattr(p, "grupo", 0) or 0) == int(ov.get("grupo") or 0)]
        usados = sorted({int(p.source) for p in piezas if 0 <= int(p.source) < n})
        return usados or list(range(n))

    def _sha1_de_hoja(self) -> list:
        """El sha1 de cada PDF de origen de la hoja (la MISMA huella de `_clave_hoja`/`recognition_key`)."""
        if not getattr(self, "src_pdfs", None):
            return []
        huellas = self._src_fingerprints(self.src_pdfs)
        return [huellas[i] for i in self._indices_de_hoja()]

    def _nombres_de_fuentes(self) -> list:
        """Los nombres de los PDF de origen de la hoja (sin `src_pdfs`, el del PDF abierto: como `_legend_sources`).
        Los usan `roles_iniciales`, el panel y «Capas y estilos…» (`layer_sugeridos._capas_dudosas`): la misma regla
        `_con_nombres` en los tres."""
        fuentes = self.src_pdfs or []
        if not fuentes:
            import os
            ruta = getattr(self, "pdf_path", None)
            return [os.path.basename(ruta)] if ruta else []
        return [str(fuentes[i].get("name") or "") for i in self._indices_de_hoja() if fuentes[i].get("name")]

    def _respuestas_de_hoja(self) -> dict:
        """{capa: utilidad | NO_RED} que dio el usuario para los PDF de origen de esta hoja."""
        guardadas = getattr(self, "capas_imagen_respuestas", None) or {}
        out = {}
        for h in self._sha1_de_hoja():
            out.update(guardadas.get(h) or {})
        return out

    # ── la pregunta del panel «Reconocer» (Tarea 8) ────────────────────────
    def _capas_imagen_de_hoja(self):
        """(dudosas sin respuesta, {utilidad: pistas}) de la hoja interpretada: las `CapaCerteza` que no son seguras
        (con los nombres de los PDF de origen, como `roles_iniciales`), sin respuesta y sin utilidad a mano; y, por
        utilidad, de dónde salió lo que se asignó solo (o «respuesta» si lo dijo el usuario)."""
        res = getattr(self, "_interpretacion", None) or {}
        capas = list(getattr(res.get("sugeridos"), "capas", None) or ())
        if not capas:
            return [], {}
        from reconocimiento import recognition as rec
        from ui.asistente.roles_iniciales import _con_nombres
        resp = self._respuestas_de_hoja()
        nombres = list(self._nombres_de_fuentes())
        roles = self._roles_de_la_hoja(int(self.page_idx)) or {}
        lineas = {n: u for u, r in roles.items() for n in (r.get(rec.ROLE_LINEAS) or ())}
        dudosas, por = [], {}
        for c in capas:
            u = lineas.get(c.capa)
            if c.capa in resp:
                if resp[c.capa] != NO_RED and u == resp[c.capa]:
                    por.setdefault(u, []).append("respuesta")
                continue
            c = _con_nombres(c, nombres)
            if c.seguro:
                if u is not None and u == c.utilidad:
                    por.setdefault(u, []).extend(c.a_favor)
            elif u is None:
                dudosas.append(c)
        return dudosas, por

    def _capa_imagen_elegida(self, capa, utilidad):
        self.responder_capa_imagen(capa, utilidad)

    def _ubicar_capa_imagen(self, capa):
        """⌖: «Capas y estilos…» con esa capa resaltada y encuadrada (el resaltado de siempre)."""
        self.abrir_capas_estilos(None, capa=capa)

    # ── responder ──────────────────────────────────────────────────────────
    def responder_capa_imagen(self, capa: str, utilidad):
        """El usuario dice de qué red es `capa` (None = «No es una red»): se guarda bajo el sha1 de cada PDF de
        origen de la hoja, se rehacen los roles de la hoja y se refresca el panel «Reconocer». Un paso de deshacer
        (`_snap_state` guarda las respuestas: Ctrl+Z la quita y rehace los roles)."""
        from reconocimiento import recognition as rec
        if utilidad is not None and utilidad not in rec.SUPPORTED_UTILITIES:
            raise ValueError("utilidad desconocida: %r" % (utilidad,))
        valor = NO_RED if utilidad is None else str(utilidad)
        self._push()
        self._guardar_respuestas_imagen({capa: valor})
        self._capas_imagen_roles()

    def _guardar_respuestas_imagen(self, valores: dict):
        """{capa: utilidad | NO_RED} bajo el sha1 de cada PDF de origen de la hoja (sin `_push` ni roles)."""
        nuevas = {h: dict(v) for h, v in (getattr(self, "capas_imagen_respuestas", None) or {}).items()}
        for h in self._sha1_de_hoja():
            nuevas.setdefault(h, {}).update(valores)
        self.capas_imagen_respuestas = nuevas            # REEMPLAZA (respaldo_editor lo guarda por referencia)

    def _respuestas_de_roles(self, dudosas, roles) -> dict:
        """{capa: utilidad} de las capas `dudosas` (sin respuesta) que el usuario puso como LÍNEAS de una utilidad en
        «Capas y estilos…»: asignarla ahí también responde (spec §7.6). Las que dejó sin tocar siguen dudosas."""
        from reconocimiento import recognition as rec
        out = {}
        for c in dudosas or ():
            for u, r in (roles or {}).items():
                if u in rec.SUPPORTED_UTILITIES and c.capa in (r.get(rec.ROLE_LINEAS) or ()):
                    out[c.capa] = u
                    break
        return out

    def _capas_imagen_al_deshacer(self, respuestas):
        """`_restore`: si las respuestas del paso son otras, se reponen y las capas de imagen de la hoja se deciden
        otra vez (lo seguro + esas respuestas)."""
        respuestas = respuestas or {}
        if respuestas == (getattr(self, "capas_imagen_respuestas", None) or {}):
            return
        self.capas_imagen_respuestas = {h: dict(v) for h, v in respuestas.items()}
        self._capas_imagen_roles(rehacer=True)

    def _capas_imagen_roles(self, rehacer=False):
        """Rehace los roles de la hoja interpretada con las respuestas de su PDF (`roles_iniciales`)."""
        from nucleo import reconocer_estado as RE
        res = getattr(self, "_interpretacion", None)
        if not res:
            return
        from ui.asistente import roles_iniciales as RI
        hoja = int(self.page_idx)
        roles = RI.roles_iniciales(res.get("layers"), res.get("leyenda"), res.get("sugeridos"),
                                   base_roles=self._roles_de_la_hoja(hoja), respuestas=self._respuestas_de_hoja(),
                                   nombres_fuentes=self._nombres_de_fuentes, rehacer_imagen=rehacer)
        self._layer_roles_by_utility = roles
        self._layer_roles_hoja = self._clave_hoja(hoja)
        firma = res.get("firma") or getattr(self._rec_estado(), "firma_hoja", None)
        self.reconocer_estado = RE.de_interpretacion(self._rec_estado(), res, firma, hidden=self.hidden_ocgs,
                                                     roles_by_utility=self._roles_de_la_hoja(hoja))
        self._refrescar_panel_reconocer()

"""«Capas de la hoja» en una hoja SIN capas ni leyenda: la red ya viene asignada (`hoja.estilos_sugeridos`).

Reporte del usuario 2026-11-14 («Southwest Gas Combined 811 Records»: el PDF dice que es gas y no se
marcaba nada; había que asignar cada estilo a mano y, en la hoja compuesta, el mismo estilo salía con
otro grosor en cada pieza). Al abrir el paso:

- la utilidad sale del texto del plano (y de las hojas de ORIGEN de una hoja compuesta: su cajetín
  quedó fuera del recorte);
- los estilos de la red, de los rótulos de tubería y de dónde nacen las acometidas; con sus GEMELOS
  (el mismo estilo con otro grosor por la escala de su pieza, `pdf_styles.gemelos`);
- quedan asignados como líneas de esa utilidad (el usuario los revisa y cambia como cualquier
  asignación) y viajan como lo que asigna una leyenda (`leyenda_mapa.CLAVE_LEYENDA`: no pasan a
  otra hoja).

Si no se puede deducir, `lbl_map_legend` lo dice (en ámbar) y el usuario asigna a mano.
Clase mezcla de `SheetLayersDialog`.
"""
from __future__ import annotations

from hoja import estilos_sugeridos as ES, pdf_layers, pdf_styles
from reconocimiento import recognition as rec
from traduccion.i18n import t as _tr

_TEXTOS_FUENTE: dict = {}          # (nombre, tamaño) → textos de sus hojas (se leen una vez)


def sugerencia_de_hoja(doc, hoja: int):
    """`Sugerencia` de la hoja (memorizada en el documento; la deja `capas_previas` si se leyó en
    el proceso trabajador)."""
    cache = doc.__dict__.setdefault("_pdfcad_estilos_sugeridos", {})
    if int(hoja) not in cache:
        try:
            cache[int(hoja)] = ES.sugerir(doc[int(hoja)])
        except Exception:                                  # noqa: BLE001 — nunca tumba el paso
            from nucleo import diagnostico
            diagnostico.registrar("estilos_sugeridos.sugerir", "Capas de la hoja")
            cache[int(hoja)] = None
    return cache[int(hoja)]


def textos_de_fuentes(fuentes) -> list:
    import pymupdf as fitz
    out = []
    for s in fuentes or ():
        clave = (s.get("name"), len(s.get("data") or b"") or s.get("path"))
        if clave not in _TEXTOS_FUENTE:
            try:
                with (fitz.open(stream=s["data"], filetype="pdf") if s.get("data")
                      else fitz.open(s["path"])) as d:
                    _TEXTOS_FUENTE[clave] = ES.textos_de_documento(d)
            except Exception:                              # noqa: BLE001
                _TEXTOS_FUENTE[clave] = []
        out.extend(_TEXTOS_FUENTE[clave])
    return out


class EstilosSugeridosMixin:
    def _apply_estilos_sugeridos(self):
        """Sin leyenda de mapa: lo que dicen el texto y los rótulos del plano, asignado."""
        self._sugeridos = None
        if not any(L.get("source") == "style" for L in self._layers_raw):
            return
        if self._roles_de_esta_hoja():                     # volver de la vista previa: lo elegido manda
            return
        sug = sugerencia_de_hoja(self._doc, self._page_index)
        if sug is None:
            return
        if sug.utilidad is None and sug.motivo in (ES.OK, ES.SIN_UTILIDAD):
            u, cuenta = ES.utilidad_de_texto(textos_de_fuentes(getattr(self, "_fuentes_texto", None)))
            if u:
                sug = ES.Sugerencia(**{**sug.__dict__, "utilidad": u, "menciones": cuenta, "motivo": ES.OK})
        self._sugeridos = sug
        if sug.motivo != ES.OK or sug.utilidad not in rec.SUPPORTED_UTILITIES:
            return
        en_hoja = {L["name"] for L in self._layers_raw}
        a_mano = {n for r in self._base_roles.values()
                  for role in (rec.ROLE_LINEAS, rec.ROLE_BUZONES, rec.ROLE_VALVULAS) for n in r.get(role) or ()}
        self._ley_por_utilidad = {sug.utilidad: []}
        for name in sug.lineas:
            if name not in en_hoja:
                continue
            self._ley_por_utilidad[sug.utilidad].append(name)
            if name in a_mano:
                continue
            self._assignments[name] = (sug.utilidad, rec.ROLE_LINEAS)
            self._touched_utilities.add(sug.utilidad)
            self._assignments_changed = True

    def _sugeridos_summary(self):
        """(texto, detalle, es_aviso) de lo que se dedujo sin leyenda; ("", "", False) si no aplica."""
        sug = getattr(self, "_sugeridos", None)
        if sug is None:
            return "", "", False
        if sug.motivo == ES.OK:
            u = _tr(rec.utility_label(sug.utilidad))
            n = len({pdf_styles.style_label(x).split(" ")[0] for x in sug.lineas})
            det = [pdf_layers.short_name(x) + f" → {u} · " + _tr("Líneas") for x in sug.lineas]
            return (_tr("Sin capas ni leyenda: el plano dice que es {u} y sus rótulos de tubería van junto a "
                        "{n} estilo(s) — ya asignados como líneas de {u}. Revísalos y cambia lo que haga "
                        "falta.").format(u=u, n=n), "\n".join(det), False)
        if sug.motivo == ES.SIN_UTILIDAD:
            return (_tr("Sin capas ni leyenda: los rótulos de tubería van junto a {n} estilo(s), pero el plano "
                        "no dice de qué red es. Asígnales la utilidad abajo.").format(n=len(sug.lineas)),
                    "\n".join(pdf_layers.short_name(x) for x in sug.lineas), True)
        if sug.motivo == ES.SIN_ESTILO:
            return (_tr("Sin capas ni leyenda: hay rótulos de tubería, pero no van claramente junto a un "
                        "estilo. Asigna abajo el estilo de la red."), "", True)
        return (_tr("Sin capas, leyenda ni rótulos de tubería: no se puede saber qué estilo es la red. "
                    "Asígnalo abajo (o Cancelar para dibujar a mano)."), "", True)

    def _gemelos_de(self, name) -> list:
        """Los estilos de la hoja que son `name` con otro grosor (otra pieza de la hoja compuesta)."""
        if not (name or "").startswith(pdf_styles.PREFIX):
            return []
        nombres = [L["name"] for L in self._layers_raw if L.get("source") == "style"]
        return [n for n in pdf_styles.gemelos([name], nombres) if n != name]

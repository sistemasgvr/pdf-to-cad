"""interpretar_trabajo.py — INTERPRETAR la hoja compuesta en el proceso trabajador (sin Qt; plan 2026-11-16,
«reconocimiento desde el editor»).

Al abrir un PDF ya no hay paso «Capas de la hoja»: tras componer la hoja, este trabajo lee lo que el PDF trae y el
panel «Reconocer» del editor lo usa (`nucleo.reconocer_estado.de_interpretacion`). Devuelve:

  · `layers`, `leyenda`, `visibles`, `sugeridos` — EXACTAMENTE lo de `capas_trabajo.leer` (misma función,
    `capas_trabajo.leer_doc`, sobre el mismo documento).
  · `letras` — `recognition.page_letters(page)`, leídas con todas las capas encendidas (el mismo estado en que
    `page_layers` ya las leyó: sale de su memo `_LETRAS_MEMO`, sin volver a leerlas); copias que viajan por la
    tubería del proceso (`_letras_portables`).
  · `simbolos` — las FUENTES de válvulas de la hoja, BARATAS (no se ubica ninguna válvula: eso es
    `recognition_valvulas.leer_hoja`, en el ▶ de la fila): dicts {fuente, nombre} con fuente
      «capa»   capa con trazos cuyo nombre es de válvulas (`recognition_valvulas.es_capa_valvula`),
      «leyenda» fila con símbolo de la leyenda del mapa que dice válvula (`es_fila_valvula`),
      «imagen» símbolo de válvula de una leyenda en imagen conocida (`leyendas_imagen.conocida`),
      «simbolo» capa virtual de un glifo de fuente de símbolos (`simbolos_fuente`, hoja sin leyenda: el usuario
               decide cuál es válvula),
      «forma»  hoja sin capas, sin leyenda ni leyenda en imagen: el reconocimiento busca el moño dibujado
               (`recognition_valvulas._de_forma`); no se sabe si hay hasta reconocer, pero se puede pedir.
  · `rotulos_n` — cuántos rótulos lee el reconocimiento: con capas, los de `recognition_anotaciones.leer_hoja`
    (en pt de la hoja, sin quitar las vistas de perfil ni las capas que el usuario apague: es una CUENTA, la lista
    de verdad sale al reconocer); mapa con leyenda, `recognition_grosor_mapa.rotulos`; sin capas ni leyenda,
    `recognition_grosor_registros.rotulos` — los mismos de `recognize_page`. Medido: DU06 h.3 0.24 s, Phoenix
    Water South h.4 0.02 s (el texto ya leído por la leyenda); ninguno vale un sustituto.
  · `escala` — la dada, o `vector_pipeline.detect_scale(page)` si no se da (en una compuesta grande ~18 s: quien
    ya la sabe la pasa).
  · `firma` — la que se pidió, tal cual (quien llama decide si el resultado sigue valiendo). La lectura de la
    hoja queda RETENIDA en el proceso bajo esa firma (`reconocimiento.lectura_retenida`): los ▶ que siguen no la
    vuelven a leer.

Avisa cada etapa por `nucleo.avance` (`ETAPAS`); `progreso` = quien escucha (en el trabajador, la ventana). Además,
al terminar cada parte, `progreso("parte", clave, n)` (pedido 2026-11-17: el panel Reconocer muestra punto por
punto qué ya se interpretó): cada utilidad con sus capas de línea y estructura (n None = mapa sin capas: sus
estilos los decide la leyenda al final), «VALVULAS» con sus fuentes, «ROTULOS» con los rótulos y «ESCALA» con los
pies por punto. `progreso("etapa", k)` = empieza la etapa k de `ETAPAS`.
Lo que no se pudo leer de lo opcional (símbolos, rótulos) queda vacío: nunca tumba la interpretación.
"""
from __future__ import annotations

import contextlib
from typing import List, Optional, Sequence

from nucleo import avance
from traduccion.i18n_core import N_, t as _tr

ETAPAS = (N_("Leyendo las capas y la leyenda de la hoja…"), N_("Leyendo las letras de las líneas…"),
          N_("Buscando los símbolos de válvulas…"), N_("Contando los rótulos del plano…"),
          N_("Leyendo la escala del plano…"))


def interpretar(ruta: str, hoja: int, ons: Sequence = (), estilos_ocultos: Sequence[str] = (), firma: str = "",
                progreso=None, escala: Optional[float] = None) -> dict:
    """{firma, layers, leyenda, visibles, sugeridos, letras, simbolos, rotulos_n, escala} — ver el docstring."""
    from hoja import capas_trabajo
    from reconocimiento import lectura_retenida
    oir = avance.escuchar(progreso) if progreso is not None else contextlib.nullcontext()
    with oir:
        # la lectura de la hoja QUEDA en el proceso para los ▶ que siguen (`lectura_retenida`, por `firma`)
        doc = lectura_retenida.abrir(ruta, firma)
        lectura_retenida.reponer(doc)
        return interpretar_doc(doc, hoja, ons, estilos_ocultos, firma, escala,
                               leer=capas_trabajo.leer_doc, avisar_parte=progreso)


def interpretar_doc(doc, hoja: int, ons: Sequence = (), estilos_ocultos: Sequence[str] = (), firma: str = "",
                    escala: Optional[float] = None, leer=None, avisar_parte=None) -> dict:
    """`interpretar` sobre un documento ya abierto, dentro de su `pdf_styles.lectura_unica`."""
    def etapa(k):
        if avisar_parte is not None:
            avisar_parte("etapa", k)
        avance.avisar(_tr(ETAPAS[k]))

    def parte(clave, n):
        if avisar_parte is not None:
            try:
                avisar_parte("parte", clave, n)
            except Exception:                          # noqa: BLE001 — avisar nunca tumba la interpretación
                pass
    if leer is None:
        from hoja.capas_trabajo import leer_doc as leer
    from reconocimiento import recognition as rec
    hoja = int(hoja)
    etapa(0)
    out = dict(leer(doc, hoja, ons, estilos_ocultos))          # deja todas las capas encendidas
    out.setdefault("sugeridos", None)
    page = doc[hoja]
    etapa(1)
    out["letras"] = _letras_portables(rec.page_letters(page))
    layers = out["layers"]
    con_capas = any(L.get("source") != "style" and L.get("path_count") for L in layers)
    for u, n in _capas_por_utilidad(layers):
        parte(u, n)
    etapa(2)
    out["simbolos"] = _simbolos(page, layers, out["leyenda"], con_capas)
    parte("VALVULAS", len(out["simbolos"] or ()))
    etapa(3)
    out["rotulos_n"] = _rotulos_n(page, out["leyenda"], con_capas, layers)
    parte("ROTULOS", int(out["rotulos_n"] or 0))
    if escala is None:
        etapa(4)
        import vector_pipeline
        escala = vector_pipeline.detect_scale(page)
    parte("ESCALA", escala)
    out["escala"] = escala
    out["firma"] = firma
    return out


def _capas_por_utilidad(layers) -> list:
    """(utilidad, capas de línea + estructura que reconocería) — lo mismo que cuenta la fila del panel
    (`reconocer_estado._fuentes_utilidad`). Mapa sin capas: None (los estilos los asigna la leyenda después)."""
    from nucleo import reconocer_estado as RE
    layers = list(layers or [])
    if not layers or all(L.get("source") == "style" for L in layers):
        return [(u, None) for u in RE.UTILIDADES]
    from hoja import leyenda_estandar as le
    out = []
    for u in RE.UTILIDADES:
        lineas, estructuras = le.capas_que_reconoce(layers, u)
        out.append((u, len(lineas) + len(estructuras)))
    return out


def _letras_portables(letras: dict) -> dict:
    """Copias de cada `LayerLetters` con el reparto por línea YA hecho y sin su función perezosa (una clausura
    sobre los trazos: no viaja por la tubería del proceso). Mismo resultado al pedirlo: `_line_split` devuelve lo
    guardado. Medido: DU06 h.3, 14 capas más por repartir = 0.11 s."""
    import dataclasses
    out = {}
    for nombre, lt in letras.items():
        split = lt._line_split()
        out[nombre] = dataclasses.replace(lt, _split=split, _splitter=None)
    return out


def _simbolos(page, layers, ley, con_capas) -> List[dict]:
    from hoja import pdf_styles
    from reconocimiento import recognition_valvulas as RV
    out: List[dict] = []
    try:
        out += [{"fuente": "capa", "nombre": L["name"]} for L in layers
                if L.get("source") != "style" and L.get("path_count") and RV.es_capa_valvula(L["name"])]
        if con_capas:
            return out
        if ley is not None:
            vistos = set()                     # una por fila (en una compuesta cada pieza repite su leyenda)
            for f in ley.filas:
                if f.simbolo and RV.es_fila_valvula(f.texto) and f.texto not in vistos:
                    vistos.add(f.texto)
                    out.append({"fuente": "leyenda", "nombre": f.texto})
            return out
        from hoja import leyendas_imagen
        imagen = leyendas_imagen.conocida(page)
        if imagen is not None:
            out += [{"fuente": "imagen", "nombre": s.texto} for s in imagen.simbolos.values()]
        out += [{"fuente": "simbolo", "nombre": L["name"]} for L in layers
                if L.get("path_count") and pdf_styles.is_symbol(L["name"])]
        if imagen is None:
            out.append({"fuente": "forma", "nombre": "moño"})
    except Exception:                                          # noqa: BLE001 — opcional: nunca tumba
        pass
    return out


def _rotulos_n(page, ley, con_capas, layers) -> int:
    try:
        if con_capas:
            from reconocimiento import recognition_anotaciones as A
            return len(A.leer_hoja(page, lambda q: q, 1.0))
        if not layers:
            return 0
        if ley is not None:
            from reconocimiento import recognition_grosor_mapa as GM
            return len(GM.rotulos(page))
        from reconocimiento import recognition_grosor_registros as GR
        return len(GR.rotulos(page))
    except Exception:                                          # noqa: BLE001 — opcional: nunca tumba
        return 0

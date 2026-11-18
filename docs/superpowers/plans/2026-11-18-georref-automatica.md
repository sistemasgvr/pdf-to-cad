# Georreferencia automática (cuartos de sección de Phoenix) — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Al componer una hoja de mapas cuyas piezas dicen su cuarto de sección de Phoenix, el proyecto queda
georreferenciado solo (EPSG 2868), con el error medido; nada cambia en planos sin celda.

**Architecture:** Fuentes PURAS en `app/geo/auto/`. Un índice de mapas en cuadrícula guardado como datos
(`app/geo/indices/phoenix_qs.json.gz`) da, por cada pieza confirmada, un ancla «centro del recuadro → centroide
del cuadro». `ajuste.py` las lleva a px del lienzo y usa `georef.fit` (similaridad). Una mezcla de la ventana lo
aplica tras componer, solo si no hay georreferencia.

**Tech Stack:** Python, PyMuPDF, numpy, PySide6, pytest.

**Spec:** `docs/superpowers/specs/2026-11-18-georref-automatica-design.md`

## Global Constraints

- Sin red en tiempo de ejecución: la tabla va en el repo y en el instalador.
- EPSG 2868 (NAD83(HARN) / Arizona Central, pie internacional), `cs_code` = `sistemas_cs.codigo_civil3d(2868)` = `AZHP-CIF`.
- Umbrales: `RMS_MAX_FT = 25`, `PIEZA_MAX_FT = 60`, `ESCALA_TOL = 0.02`.
- Nunca pisar una georreferencia activa; nunca aplicar una dudosa sin que el usuario lo pida.
- Pieza sin `ficha.celda` → ninguna fuente la mira (DU06/CAD idéntico).
- Archivos < 500 líneas, español, textos visibles con `t()` + traducción en `i18n_en.py`. Sin commits (los hace el usuario).

## Review Focus

- Hoja con «17-10» pero de otra ciudad (sin PLSS ni «City of Phoenix») → sin ancla. (Tarea 2)
- Hoja suelta (una sola pieza = hoja entera, sin materializar) → ancla con escala de la hoja y giro 0. (Tarea 3)
- Hoja de trabajo con `/Rotate` (Sewer North tiene 90) → el centro del recuadro en coordenadas VISIBLES. (Tarea 3)
- Celda que no está en la tabla (fila fuera de Phoenix) → sin ancla, sin error. (Tarea 2)
- Proyecto reabierto ya georreferenciado → no se recalcula ni se pisa. (Tarea 4)

---

### Task 1: Tabla del índice QS y lector

**Files:**
- Create: `scripts/datos/indice_phoenix_qs.py`, `app/geo/auto/__init__.py`, `app/geo/auto/indice_mapas.py`, `app/geo/indices/phoenix_qs.json.gz`
- Test: `tests/test_georef_auto.py`

**Interfaces:**
- Produces: `indice_mapas.Indice` (dataclass: `id, nombre, epsg, palabras: List[str], fecha, fuente_url, celdas: Dict[Tuple[int,int], Celda]`), `Celda(poligono: List[Tuple[float,float]], plss: Tuple[str,str,int,str])` (township «2N», range «1E», sección, cuarto «NE»), `Celda.centroide() -> Tuple[float,float]` (promedio de vértices sin repetir el último), `indice_mapas.cargar(id: str) -> Indice` (memorizado, lee `app/geo/indices/<id>.json.gz`; en el .exe `sys._MEIPASS/geo/indices`), `indice_mapas.disponibles() -> List[str]`.

- [ ] **Step 1: Script de descarga.** `scripts/datos/indice_phoenix_qs.py` consulta `https://maps.phoenix.gov/pub/rest/services/Public/STR_QSMapIndex/MapServer/0/query` en páginas de 1000 (`outSR=2868`, campos `TILE, PLS_TOWNSHIP, PLS_RANGE, PLS_SECTION, QTR_SECTION`), salta `TILE` vacío y escribe el `.json.gz` con `{id:"phoenix_qs", nombre:"City of Phoenix — Quarter Section", epsg:2868, palabras:["CITY OF PHOENIX"], fecha, fuente_url, celdas:{"17-10": {"p": [[x,y],…] redondeado a 0.01 ft, "plss": ["2N","1E",23,"SE"]}}}`. Correrlo y comprobar 3 708 celdas.
- [ ] **Step 2: Pruebas que fallan.**
```python
def test_tabla_phoenix_16_10():
    ix = indice_mapas.cargar("phoenix_qs")
    c = ix.celdas[(16, 10)]
    assert ix.epsg == 2868 and len(ix.celdas) >= 3700
    assert c.plss == ("2N", "1E", 26, "NE")
    x, y = c.centroide()
    assert abs(x - 606045) < 30 and abs(y - 906300) < 30
    assert ix.celdas[(17, 10)].centroide()[1] > y      # la fila crece hacia el norte
```
- [ ] **Step 3: Implementar `indice_mapas.py`** y correr `pytest tests/test_georef_auto.py -k tabla -v` → PASS.

### Task 2: Fuente «índice de mapas» con confirmación

**Files:**
- Create: `app/geo/auto/fuentes.py`
- Test: `tests/test_georef_auto.py`

**Interfaces:**
- Consumes: `indice_mapas.cargar`, `composicion_ficha.Ficha` (`.celda`), `composicion_encaje.caja(ficha)`, `texto_pdf.corridas(page)`.
- Produces: `Ancla(hoja_pt: Tuple[float,float], mundo: Tuple[float,float], motivo: str)`, `Ubicacion(epsg: int, cs_code: str, anclas: List[Ancla], fuente: str, etiqueta: str)`, `fuentes.ubicar(page, ficha) -> Optional[Ubicacion]` (recorre `FUENTES`, la primera que responde), `fuentes.confirma(texto: str, celda: Celda, indice: Indice) -> bool`.

- [ ] **Step 1: Pruebas que fallan.**
```python
def test_confirma_por_plss_o_ciudad():
    ix = indice_mapas.cargar("phoenix_qs"); c = ix.celdas[(16, 10)]
    assert fuentes.confirma("NE 1/4 SEC.26, T.2N, R.1E", c, ix)
    assert fuentes.confirma("City of Phoenix", c, ix)
    assert not fuentes.confirma("SW 1/4 SEC.26, T.2N, R.1E", c, ix)   # PLSS de otra celda
    assert not fuentes.confirma("QS 16-10  County of Tucson", c, ix)

@PDFS  # skip si no están los PDF de Indian School
def test_ubicar_hoja_water_south():
    p = _doc("QS Water_Indian School_South")[0]
    u = fuentes.ubicar(p, cf.ficha(p, 0))
    assert u.epsg == 2868 and u.cs_code == "AZHP-CIF" and len(u.anclas) == 1
    assert u.anclas[0].mundo == pytest.approx(indice_mapas.cargar("phoenix_qs").celdas[(16, 10)].centroide())

def test_sin_celda_o_celda_desconocida_no_ubica():   # ficha falsa: celda None; celda (999, 1)
    ...  # ambas → None
```
- [ ] **Step 2: Implementar.** Texto de la hoja = `page.get_text()` + texto de `texto_pdf.corridas(page)` (solo si `get_text` no trae letras), en mayúsculas. `confirma`: regex sobre `(NE|NW|SE|SW)\s*1/4\s*SEC\.?\s*(\d+)\s*,?\s*T\.?\s*(\d+[NS])\s*,?\s*R\.?\s*(\d+[EW])`; si hay algún PLSS en el texto, vale solo si coincide con el de la celda; si no hay PLSS, vale si aparece una de `indice.palabras`. Ancla = centro de `caja(ficha)` (coordenadas visibles) → `celda.centroide()`. Sin `caja` → None.
- [ ] **Step 3:** `pytest tests/test_georef_auto.py -v` → PASS.

### Task 3: Ajuste de la hoja compuesta

**Files:**
- Create: `app/geo/auto/ajuste.py`, `tests/datos/phoenix_cruces.json` (4 cruces de calles arteriales en los cuadros de Sewer North, tomados de `Public/STR_StreetIntersections` en EPSG 2868, con la URL y la fecha)
- Test: `tests/test_georef_auto.py`

**Interfaces:**
- Consumes: `fuentes.ubicar`, `composite.piece_map`, `composite.sheet_geometry`, `georef.fit`.
- Produces: `Resultado(matrix: list, epsg: int, cs_code: str, rms_ft: float, residuos: Dict[str, float], escala_ft_px: float, aceptada: bool, motivo: str, puntos: list, etiquetas: List[str])`; `ajuste.georref_hoja(comp, docs, pagina_trabajo, zoom: float, escala_ft_pt: float) -> Optional[Resultado]` (None = ninguna pieza ubicada). `docs[i]` = `fitz.Document` del PDF de origen i; `pagina_trabajo` = la `fitz.Page` de trabajo (para su `/Rotate`) o None.

- [ ] **Step 1: Pruebas que fallan** (con `composicion_sugerida.analizar` + `armar` sobre los PDF, como `scripts`/medición de las notas):
```python
@PDFS
def test_sewer_north_queda_en_sus_cuadros():
    r = _georref_compuesta("QS Sewer_Indian School_North")
    assert r.aceptada and r.epsg == 2868
    assert r.rms_ft <= 10 and max(r.residuos.values()) <= 15
    print("RMS", r.rms_ft, "máx", max(r.residuos.values()))

@PDFS
def test_esquinas_contra_cruces_de_calles():          # verdad independiente
    r = _georref_compuesta("QS Sewer_Indian School_North")
    for cruce in json.load(open(DATOS / "phoenix_cruces.json"))["cruces"]:
        assert _dist_a_esquina_mas_cercana(r, cruce) <= 25

@PDFS
def test_water_south_queda_dudosa():
    r = _georref_compuesta("QS Water_Indian School_South")
    assert not r.aceptada and r.rms_ft > 25

@PDFS
def test_hoja_suelta_usa_la_escala_y_giro_cero():     # una pieza, hoja entera, /Rotate 90
    r = _georref_hoja("QS Sewer_Indian School_North", 2)
    assert r.aceptada and r.matrix[0][1] == pytest.approx(0, abs=1e-9)
```
  `_dist_a_esquina_mas_cercana` = distancia del cruce a la esquina del cuadro más cercana (es la prueba de que la tabla y la hoja coinciden). Si alguna esquina no cae en un cruce real, ajustar el dato del cruce elegido, nunca el umbral.
- [ ] **Step 2: Implementar.** Por cada pieza: `ficha(doc[pz.source][pz.page])`, `ubicar`; el ancla en pt visibles de su hoja → `piece_map` → `+ (dx, dy)` de `sheet_geometry` → rotar con `pagina_trabajo.rotation_matrix` si tiene giro → `× zoom` = px. Hoja suelta (`comp is None` o `is_single_full_page()`): el ancla tal cual en pt visibles × zoom. Con ≥2 anclas `georef.fit(px, mundo, "similarity")`; con 1, matriz de escala `escala_ft_pt / zoom` (pies internacionales: EPSG 2868 ya está en pies), sin giro, eje Y invertido, trasladada al centroide. Aceptada si `rms ≤ RMS_MAX_FT`, residuo máximo ≤ `PIEZA_MAX_FT` y, con ≥2 anclas, `|escala_ajustada/escala_ft_pt·zoom − 1| ≤ ESCALA_TOL`. `puntos` = `[{"px":[x,y], "utm":[E,N], "fuente":"phoenix_qs", "celda":"16-10"}]`.
- [ ] **Step 3:** `pytest tests/test_georef_auto.py -v -s` → PASS, con las cifras impresas.

### Task 4: En la ventana

**Files:**
- Create: `app/ui/ventana/ventana_georef_auto.py` (`GeorefAutoMixin`)
- Modify: `app/ui/ventana/app_window.py` (heredar la mezcla; llamar `self._georef_automatica()` tras `_apply_composite()` exitoso en el flujo de componer, línea ~658, y al final de abrir un PDF de una hoja), `app/traduccion/i18n_en.py`, `PDF-a-CAD.spec` (datos `app/geo/indices` → `geo/indices`), `app/autoprueba.py` (comprueba que `indice_mapas.cargar("phoenix_qs")` abre), `app/nucleo/model.py` (VERSION/CHANGELOG), `app/docs/manual.es.html` + `manual.en.html` (capítulo de georreferenciación), `CLAUDE.md` (una entrada corta)
- Test: `tests/test_georef_auto_ventana.py`

**Interfaces:**
- Consumes: `ajuste.georref_hoja`, `georef.Georef`, `Main.aviso_breve(titulo, detalle, accion, tono)`, `Main._push`, `Main._update_geo_status`.
- Produces: `Main._georef_automatica() -> Optional[Resultado]`, `Main.aplicar_georef_auto(r: Resultado)`.

- [ ] **Step 1: Pruebas que fallan** (ventana real offscreen, `PDFCAD_PROCESO=0`):
```python
def test_componer_sewer_north_georreferencia_sola(win):      # @PDFS
    _componer(win, "QS Sewer_Indian School_North")
    assert win.georef.active() and win.georef.epsg == 2868 and win.georef.cs_code == "AZHP-CIF"
    win._undo_action(); assert not win.georef.active()        # Ctrl+Z la quita

def test_water_south_no_se_aplica_y_avisa(win):              # @PDFS
    _componer(win, "QS Water_Indian School_South")
    assert not win.georef.active() and win._georef_auto_dudosa is not None

def test_no_pisa_una_georref_a_mano(win): ...                # Georef activo antes → igual después
def test_du06_sin_cambios(win): ...                          # georef inactivo y DXF idéntico al de antes
```
- [ ] **Step 2: Implementar `GeorefAutoMixin`.** `_georef_automatica`: sale si `self.georef.active()`; llama `georref_hoja(self.composite, docs_de_origen, self.doc[self.page_idx] o equivalente, self.zoom, self.scale·72)` en try (cualquier error → None, nunca rompe componer). Aceptada → `aplicar_georef_auto`: `_push()`, `self.georef = Georef(matrix, 2868, "similarity", rms, puntos, cs_code)`, `_update_geo_status()`, `aviso_breve(t("Georreferenciada sola por cuarto de sección"), t("{celdas} · error {e} ft").format(…), accion=(t("Deshacer"), self._undo_action))`. Dudosa → `self._georef_auto_dudosa = r` y `aviso_breve(t("No se georreferenció sola"), t("Las hojas no coinciden con sus cuadros: {e} ft. Revisa la composición."), accion=(t("Aplicar igual"), lambda: self.aplicar_georef_auto(r)), tono="aviso")`. Usar los nombres reales de deshacer/estado de georef que existan en la ventana (buscar `_update_geo_status` y la acción de deshacer).
- [ ] **Step 3:** `python scripts/pruebas.py interfaz` y `pytest tests/test_georef_auto.py tests/test_georef_auto_ventana.py tests/test_i18n.py tests/test_instalador.py -v` → PASS; `python scripts/regresion.py` → 0 diferencias.

## Ejecución

Sin commits: los cambios quedan para que el usuario los revise en VS Code.

# Ejes de la red en imagen — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** En una hoja sin capas OCG cuya red viene como IMAGEN (Phoenix «QS SD»), sacar de cada color sus ejes, ofrecerlos como capas virtuales, asignar la utilidad sola cuando hay certeza y preguntar cuando no.

**Architecture:** Cuatro módulos PUROS en `app/hoja/`: dibujar solo las imágenes, descubrir colores, esqueleto → líneas/símbolos/rellenos, y capas virtuales. Esas capas se enganchan en `pdf_styles._drawings`, en la rama sin capas, igual que `simbolos_fuente`. La certeza amplía `estilos_sugeridos` con un detalle POR CAPA, que aplica `roles_iniciales`. La pregunta va en el panel «Reconocer». El reconocimiento no cambia: solo `pdf_styles.is_symbol` reconoce también los símbolos de imagen.

**Tech Stack:** Python 3, PyMuPDF (fitz), numpy, OpenCV (`cv2`), scikit-image (`skimage.morphology.skeletonize`), PySide6, pytest.

**Spec:** `docs/superpowers/specs/2026-11-18-ejes-de-imagen-design.md` (incluye §8b, decisiones tras la revisión).

**Cambio respecto al diseño (§7.2, hoja compuesta):** la lógica pura no tiene acceso a los PDF de origen (`Main.src_pdfs`), así que en la hoja compuesta los ejes se sacan de la página materializada. Se dibujan SOLO sus imágenes, a la resolución nativa de cada imagen. El criterio del diseño sigue igual: compuesta = sueltas. La Tarea 5 lo prueba.

## Global Constraints

- Solo hojas SIN OCG con imágenes «gráficas». En cualquier otra hoja `imagen_ejes.capas(page) == []`, sin decodificar ninguna imagen. Los escaneos enteros y las hojas CAD con capas no se tocan.
- No cerrar huecos con morfología. La unión de los trazos la hace el reconocimiento.
- Ningún color fijo: la paleta se descubre en cada hoja.
- Hojas sin imágenes de red (Phoenix agua/alcantarillado, Southwest Gas 36/37, DU06 h.3/h.4, LABOE h.26) → foto antes/después = 0 diferencias en `pdf_styles.drawings` y en el reconocimiento.
- Nombres de capa (con `pdf_styles.PREFIX`):
  - línea: `PDF_STYLE:["img","line",[r,g,b]]`
  - símbolo: `PDF_STYLE:["img","sym",[r,g,b],"<forma>"]`
  - relleno: `PDF_STYLE:["img","fill",[r,g,b]]`
  - `r,g,b` son enteros 0–255: exactos si la imagen es indexada; si es RGB, redondeados a múltiplos de 32 (`min(255, round(v/32)*32)`).
- Trazo virtual de un eje: `type "s"`, `color` = rgb/255, `width` = grosor medido en pt, `dashes "[] 0"`, `fill None`, `items` = segmentos `("l", Point, Point)`, `rect`, `seqno` = −2 (los nativos son ≥0 y los símbolos de fuente −1), `level 0`, `imagen True`, `layer`. Mismas coordenadas que `page.get_drawings()` de esa hoja.
- Etiquetas: «Azul #004DA8 · imagen», «Símbolo #004DA8 (cuadro 4×4 pt) · imagen», «Relleno #80A6D4 · imagen».
- El trabajo pesado corre en el proceso trabajador (lo llama `pdf_styles.drawings` dentro de la interpretación o el reconocimiento), con `nucleo.avance.avisar` y memoria con `pdf_styles.memo(page, "imagen_ejes", …)`.
- Lógica pura sin Qt; archivos de menos de 500 líneas; español; textos visibles con `t()` + `i18n_en.py`.
- Lo nuevo que viaja en el `.digproj` va también a `respaldo_editor.CLAVES`. Las clases nuevas guardadas en la interpretación van a `interpretacion_guardada.CLASES`.
- **Sin commits:** el usuario hace los commits; cada tarea termina dejando los cambios sin commit.
- Pruebas: `python -m pytest tests/<archivo> -q` desde la raíz. PDF reales en `C:/Users/bernu/OneDrive/Documentos/DOCS DE PRUEBA IND/`; las pruebas que los usan se saltan si faltan (`pytest.skip`), como las de Phoenix existentes.

## Review Focus

1. **Imagen fotográfica o logo en una hoja sin capas** (ortofoto de fondo, logo de la ciudad en el cajetín) → no aparece ninguna capa de imagen. Prueba en la Tarea 2: `test_foto_no_da_colores`.
2. **Trazo azul cruzado por una línea de lote o un rótulo vectorial negro** → el eje sigue entero, porque se dibujan solo las imágenes. Prueba en la Tarea 1: `test_vector_encima_no_corta_la_imagen`.
3. **Hoja con `/Rotate 90`** (todas las de Phoenix SD) → el eje cae sobre la tinta azul en coordenadas de `get_drawings`. Prueba en la Tarea 4: `test_hoja_girada_eje_sobre_su_tinta`.
4. **Dos colores de línea y nombre de PDF neutro** → nada se asigna solo y aparece la pregunta. Prueba en la Tarea 6: `test_dos_colores_es_dudoso`; y en la Tarea 8 el flujo de responder.
5. **Hoja compuesta de dos hojas SD** → mismas líneas que las sueltas, sin cortes extra en la costura por un tono distinto. Prueba en la Tarea 5: `test_compuesta_igual_a_sueltas`.

---

### Task 1: Dibujar solo las imágenes de la hoja

**Files:**
- Create: `app/hoja/imagen_solo.py`
- Test: `tests/test_imagen_ejes.py` (archivo compartido por las Tareas 1–4; ayudante `_pdf_sintetico(...)` que arma un PDF con una imagen PNG insertada con `page.insert_image` y vectores negros encima)

**Interfaces:**
- Produces:
  - `imagenes_utiles(page) -> list[dict]` — `page.get_image_info(xrefs=True)` filtrada: cada imagen con `bbox` ≥ `AREA_MIN_PT2` (= 400 pt²); [] si la hoja tiene OCG (`page.parent.get_ocgs()` no vacío).
  - `px_por_pt(imgs) -> float` — mediana de `width / lado en pt` (el lado que corresponde al ancho según la transformación), con tope `PX_POR_PT_MAX` = 6.0.
  - `pintar(page, clip: fitz.Rect, escala: float) -> np.ndarray` — imagen RGB uint8 de SOLO las imágenes de `clip` (coordenadas de `get_drawings`), a `escala` px/pt, fondo blanco; respeta transformaciones, giros, recortes de formas y máscaras.
  - `teselas(page, escala, lado_px=4096, solape_px=64) -> Iterator[tuple[fitz.Rect, np.ndarray]]` — recorre la unión de los `bbox` de `imagenes_utiles`.

- [ ] **Step 1: Write the failing tests**

```python
def test_vector_encima_no_corta_la_imagen(tmp_path):
    doc = _pdf_sintetico(tmp_path, trazos_azules=[((100, 300), (500, 300), 6)],   # px de la imagen, grosor
                         vectores_negros=[((300, 100), (300, 500), 0.5)])          # cruza el trazo azul
    img = IS.pintar(doc[0], doc[0].rect, 4.0)
    fila = img[round(300 / IS_ESCALA_SINT * 4.0)]                                  # fila del trazo
    azul = (abs(fila.astype(int) - (0, 77, 168)).max(1) <= 2)
    assert azul[...].all()          # el tramo entero de x=100..500 (convertido a px de salida) sigue azul

def test_solo_imagenes_coincide_con_render_en_el_color(tmp_path): ...
    # zona sin vectores encima: IS.pintar == page.get_pixmap(matrix=4, clip) en los píxeles azules (±1 px)

def test_sin_imagenes_o_con_capas_no_hay_nada(tmp_path):
    assert IS.imagenes_utiles(_pdf_sin_imagenes(tmp_path)[0]) == []
    assert IS.imagenes_utiles(_pdf_con_ocg_e_imagen(tmp_path)[0]) == []

def test_phoenix_sd_h4_px_por_pt():
    page = _sd_south()[3]
    assert 4.1 < IS.px_por_pt(IS.imagenes_utiles(page)) < 4.25
```

- [ ] **Step 2: Correr:** `python -m pytest tests/test_imagen_ejes.py -q -k "vector_encima or solo_imagenes or sin_imagenes or px_por_pt"`. Esperado: FAIL (no existe `hoja.imagen_solo`).

- [ ] **Step 3: Implementar `app/hoja/imagen_solo.py`.** Para `pintar`, primero probar el filtro de contenido de MuPDF (`fitz.mupdf.pdf_sanitize_filter_options` con un `culler` que descarte `FZ_CULL_PATH_*` y `FZ_CULL_GLYPH`, `recurse=1` para entrar en las formas), aplicado a una COPIA de la hoja en un documento temporal en memoria (`insert_pdf`), y luego `get_pixmap(matrix=Matrix(escala, escala), clip=…)`. Si en la versión instalada de PyMuPDF no se puede, componer cada imagen decodificada (`fitz.Pixmap(doc, xref)`, con su `transform` de `get_image_info`) con `cv2.warpAffine` sobre un lienzo blanco. Recortar a `page.rect` y, en la hoja compuesta, al clip de cada forma. La que elijas tiene que pasar las cuatro pruebas.

- [ ] **Step 4: Correr las mismas pruebas.** Esperado: PASS.

- [ ] **Step 5:** Dejar sin commit.

---

### Task 2: Descubrir los colores de la imagen

**Files:**
- Create: `app/hoja/imagen_paleta.py`
- Test: `tests/test_imagen_ejes.py`

**Interfaces:**
- Consumes: imágenes RGB de `imagen_solo.pintar`.
- Produces:
  - `@dataclass ColorImagen: rgb: tuple[int,int,int]; pixeles: int; exacto: bool`
  - `paleta(imgs: Sequence[np.ndarray], indexada: bool) -> list[ColorImagen]` — sin fondo (L* > 92 y croma < 8 en Lab, o el color que cubre > 60 % de los píxeles no transparentes), solo colores con ≥ `PIXELES_MIN` = 200 px; [] si la imagen es fotográfica.
  - `es_fotografica(img: np.ndarray) -> bool` — los `N_PRINCIPALES` = 12 grupos cubren < `CUBRE_MIN` = 0.85 de los píxeles no-fondo.
  - `normalizar(rgb, exacto) -> tuple[int,int,int]` — exacto: tal cual; si no, múltiplos de 32 con tope 255.
  - `mascara(img, color: ColorImagen, delta_e=12.0) -> np.ndarray[bool]` — exacto: igualdad ±2 por canal; si no, ΔE76 en Lab ≤ `delta_e`.
  - `indexada(page) -> bool` — todas las `imagenes_utiles` tienen `cs-name` que empieza con «Indexed».

- [ ] **Step 1: Write the failing tests**

```python
def test_paleta_indexada_exacta():
    img = _img_con({(0, 77, 168): 5000, (128, 166, 212): 9000, (255, 255, 255): 10**6})
    assert [c.rgb for c in IP.paleta([img], indexada=True)] == [(128, 166, 212), (0, 77, 168)]   # por píxeles

def test_paleta_rgb_agrupa_antialias():
    img = _img_rgb_con_antialias(color=(200, 30, 30))          # bordes mezclados con blanco
    cols = IP.paleta([img], indexada=False)
    assert len(cols) == 1 and cols[0].rgb == IP.normalizar((200, 30, 30), False) == (192, 32, 32)

def test_foto_no_da_colores():
    assert IP.paleta([_img_degradado_ruidoso()], indexada=False) == []

def test_phoenix_sd_h4_colores():
    cols = {c.rgb for c in _paleta_real(_sd_south()[3])}
    assert (0, 77, 168) in cols and (128, 166, 212) in cols
```

- [ ] **Step 2: Correr** `-k "paleta or foto or colores"`. Esperado: FAIL.
- [ ] **Step 3: Implementar.** Para RGB, k-means de `cv2.kmeans` en Lab sobre una muestra de ≤ 200 000 píxeles no-fondo, con k = 8. Después se unen los centros a ΔE < 10 y se asigna cada píxel al centro más cercano si ΔE ≤ `delta_e`.
- [ ] **Step 4: Correr.** Esperado: PASS.
- [ ] **Step 5:** Dejar sin commit.

---

### Task 3: De una máscara, líneas, símbolos y rellenos

**Files:**
- Create: `app/hoja/imagen_trazos.py`
- Test: `tests/test_imagen_ejes.py`

**Interfaces:**
- Consumes: `mascara(...)` de la Tarea 2.
- Produces:
  - `@dataclass Simbolo: cx: float; cy: float; ancho: float; alto: float; forma: str` (px de la máscara; `forma` = «cuadro 4×4», «círculo 3», «otro 5×2», con medidas en pt redondeadas a 1 y la escala pasada).
  - `@dataclass Piezas: lineas: list[list[tuple[float,float]]]; grosores: list[float]; simbolos: list[Simbolo]; relleno: bool`
  - `trazos(mask: np.ndarray, escala: float) -> Piezas` — coordenadas en px de `mask`; grosores en pt (= px / escala). Constantes: `ALARGADA_K` = 3.0, `ESPOLON_W` = 1.5, `RUIDO_PX` = 12, `RAYADO_MIN` = 8 (mínimo de líneas paralelas cortas en una región para que sea rayado), `DP_W` = 0.25 (Douglas–Peucker = 0.25·w, con tope de 0.5 pt·escala).

- [ ] **Step 1: Write the failing tests** (máscaras sintéticas dibujadas con `cv2.line` / `cv2.rectangle` / `cv2.ellipse`, escala 4)

```python
def test_trazo_recto_eje_al_centro_y_largo_completo():
    m = _mask_linea((40, 100), (400, 100), grosor=6)
    p = IT.trazos(m, 4.0)
    (a, b), = [(l[0], l[-1]) for l in p.lineas]
    assert abs(a[1] - 100) <= 0.25 and abs(b[1] - 100) <= 0.25
    assert abs(a[0] - 40) <= 1.0 and abs(b[0] - 400) <= 1.0          # punta alargada w/2
    assert abs(p.grosores[0] - 6 / 4.0) < 0.3

def test_discontinua_da_un_trazo_por_guion_sin_unir():
    m = _mask_guiones((40, 100), (400, 100), largo=30, hueco=12, grosor=6)
    assert len(IT.trazos(m, 4.0).lineas) == _n_guiones                 # nada se cierra

def test_curva_y_te(): ...      # arco: un trazo a ≤0.5 px del arco; «T»: 3 trazos que comparten el punto del nudo
def test_simbolo_sobre_linea_se_separa():
    p = IT.trazos(_mask_linea_con_rejilla(), 4.0)
    assert len(p.simbolos) == 1 and p.simbolos[0].forma.startswith("cuadro")
    assert len(p.lineas) == 2 and all(_fuera_del_simbolo(l) for l in p.lineas)
def test_rayado_es_relleno():
    p = IT.trazos(_mask_rayado(), 4.0)
    assert p.relleno and p.lineas == []
def test_paralelas_cercanas_no_se_juntan():
    p = IT.trazos(_mask_paralelas(sep_px=4), 4.0)
    assert len(p.lineas) == 2
```

- [ ] **Step 2: Correr** `-k "trazo or discontinua or curva or simbolo or rayado or paralelas"`. Esperado: FAIL.
- [ ] **Step 3: Implementar.** Pasos: componentes con `cv2.connectedComponentsWithStats` (8-vecinos); esqueleto de cada una con `skeletonize`; grosor w = área / largo del esqueleto; poda de espolones < `ESPOLON_W`·w; recorrido entre puntas y nudos (como el script de referencia, pero por componente y sin `MORPH_CLOSE`); Douglas–Peucker (`cv2.approxPolyDP`); alargar cada punta libre w/2 en su rumbo.
  - **Símbolo:** componente no alargada (largo < `ALARGADA_K`·w), o la zona de nudos densos (≥ 4 nudos en un círculo de 2·w), que se recorta antes de recorrer.
  - **Relleno:** ≥ `RAYADO_MIN` líneas cortas paralelas (±5°) a paso regular dentro de la caja de una componente. Si el rayado es la mayoría de las componentes del color, `relleno=True` y no se devuelven líneas.
- [ ] **Step 4: Correr.** Esperado: PASS.
- [ ] **Step 5:** Dejar sin commit.

---

### Task 4: Capas virtuales en `pdf_styles`

**Files:**
- Create: `app/hoja/imagen_ejes.py`
- Modify: `app/hoja/pdf_styles.py` (`_drawings`, rama «sin leyenda» y rama con leyenda: agregar `out.extend(memo(page, "imagen_ejes", lambda: imagen_ejes.capas(page)))` al final de las dos; `is_symbol` también para `["img","sym"`; `_style_label` para los tres tipos)
- Test: `tests/test_imagen_ejes.py`, `tests/test_pdf_styles.py`

**Interfaces:**
- Consumes: Tareas 1–3.
- Produces:
  - `capas(page) -> list[dict]` — trazos virtuales (forma en Global Constraints). Los símbolos van como círculos (`simbolos_fuente._circulo`) con `"symbol": True`; los rellenos como UN trazo rectangular por componente (para que la capa se liste) con `"imagen_relleno": True`.
  - `nombre(tipo: str, rgb: tuple[int,int,int], forma: str | None = None) -> str`
  - `es_imagen(name) -> bool`, `tipo_imagen(name) -> str | None` («line» | «sym» | «fill»), `rgb_de(name) -> tuple[int,int,int] | None`
  - Avance: `avance.avisar(t("Leyendo la imagen de la hoja… {k} de {n}"), k, n)` por tesela.

- [ ] **Step 1: Write the failing tests**

```python
def test_capas_sintetico_nombres_y_etiquetas(tmp_path):
    names = {p["layer"] for p in IE.capas(_pdf_sintetico(tmp_path, ...)[0])}
    assert 'PDF_STYLE:["img","line",[0,77,168]]' in names
    assert pdf_styles.style_label('PDF_STYLE:["img","line",[0,77,168]]') == "Azul #004DA8 · imagen"
    assert pdf_styles.is_symbol(next(n for n in names if IE.tipo_imagen(n) == "sym"))

def test_hoja_girada_eje_sobre_su_tinta():
    page = _sd_south()[3]                                         # /Rotate 90
    ejes = [p for p in pdf_styles.drawings(page) if IE.tipo_imagen(p.get("layer") or "") == "line"]
    assert ejes
    # cada punto medio de segmento cae sobre un píxel #004DA8 de page.get_pixmap(matrix=4) a ≤1 px

def test_sin_imagenes_igual_que_antes():
    for page in _hojas_foto():          # Phoenix agua/alcantarillado, Southwest 37, DU06 h.4, LABOE h.26 (si están)
        assert not any(IE.es_imagen(p.get("layer") or "") for p in pdf_styles.drawings(page))

def test_compositor_no_ve_los_ejes():
    # diseño §8b-5: composite.page_drawings, composicion_ficha y el encaje leen get_drawings nativo
    assert not any(IE.es_imagen(p.get("layer") or "") for p in composite.page_drawings(_sd_south()[3]))

def test_rotulos_vectoriales_junto_al_eje():
    # hoja 4 de South: el rótulo «18" HDPE» de PIONEER PREPARATORY queda a ≤ 3 letras de un eje (misma coordenada)
```

- [ ] **Step 2: Correr** `python -m pytest tests/test_imagen_ejes.py tests/test_pdf_styles.py -q`. Esperado: FAIL en las nuevas.
- [ ] **Step 3: Implementar `capas`.**
  - `imagenes_utiles` vacío → `[]`.
  - Si no: para cada tesela de `teselas`, sacar la paleta, la máscara por color y `trazos`; llevar px → coordenadas de `get_drawings` con el origen de la tesela y la escala (sin derrotar: `pintar` ya trabaja en esas coordenadas).
  - Se descartan las piezas que nacen en el borde de solape y que la tesela vecina contiene enteras.
  - Las curvas se emiten como segmentos.
- [ ] **Step 4: Correr.** Esperado: PASS. Correr también `tests/test_pdf_styles.py tests/test_mapas_sin_capas.py tests/test_estilos_sugeridos.py tests/test_simbolos*.py -q`. Esperado: lo mismo que antes del cambio.
- [ ] **Step 5:** Dejar sin commit.

---

### Task 5: Medir con Phoenix SD y ajustar la extracción

**Files:**
- Create: `scripts/audit_ejes_imagen.py` (`python scripts/audit_ejes_imagen.py [south|north] [--hojas 1,4] [--compuesta 3,4]`). Por hoja imprime: colores; nº de trazos y símbolos; cobertura de la tinta del color por los ejes (píxeles de la máscara a ≤ w/2+1 px de un eje); tramos sin tinta (segmento del eje con > 2 px seguidos fuera de la máscara); y el resultado de `recognize_page` con DRENAJE ← la capa de línea: líneas, cobertura y diámetros leídos.
- Modify: constantes de `app/hoja/imagen_trazos.py` según lo medido.
- Test: `tests/test_imagen_ejes_phoenix.py`

**Interfaces:**
- Consumes: `imagen_ejes.capas`, `recognition.recognize_page` (como en `tests/test_mapas_sin_capas.py`, con `roles_by_utility={"DRENAJE": {LINEAS: [capa]}}`).
- Produces: nada nuevo; umbrales afinados.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize("hoja", [3, 7])
def test_sd_reconoce_drenaje(hoja):
    r = _reconocer_sd(_sd_south(), hoja)
    assert len(r.polylines) >= _MIN_LINEAS[hoja]                 # fijar tras la 1.ª medición (Step 3)
    assert _cobertura(r) >= 0.97
    assert _tramos_sin_tinta(r) == 0
    assert sum(1 for pl in r.polylines if pl.diam_in) >= _MIN_DIAM[hoja]

def test_pioneer_preparatory_diametros():
    # hoja 4, zona de la figura del diseño: la línea vertical de la izquierda lee 24" y la horizontal de arriba 18"

def test_compuesta_igual_a_sueltas():
    # compuesta South h.4 + h.5 (composite.build_document con las dos hojas enteras, una al lado de la otra):
    # las líneas de cada pieza, llevadas a la hoja suelta con composite.piece_unmap, coinciden a ≤0.25 pt
    # con las de la hoja suelta, y no hay más cortes «cut» que en las sueltas fuera de la costura
```

- [ ] **Step 2: Correr** `python scripts/audit_ejes_imagen.py south --hojas 1,4,8` y anotar las cifras en el docstring del script.
- [ ] **Step 3: Ajustar la extracción, nunca el núcleo.** Si `learn_pattern` no aprende el patrón de los guiones, revisar el alargado de las puntas y el grosor. Si la capa sale «continua», verificar que `ink_reconstruct` dé la línea. Fijar `_MIN_LINEAS` y `_MIN_DIAM` en el 95 % de lo medido.
- [ ] **Step 4: Correr** `python -m pytest tests/test_imagen_ejes_phoenix.py -q`. Esperado: PASS. Tiempo por hoja impreso por la auditoría: anotarlo.
- [ ] **Step 5:** Dejar sin commit.

---

### Task 6: Certeza por capa

**Files:**
- Create: `app/hoja/certeza_capas.py`
- Modify: `app/hoja/estilos_sugeridos.py` (`Sugerencia.capas: list[CapaCerteza]` con `default_factory=list`; `sugerir(page, paths=None, corridas=None, textos=(), nombres=())` llama a `certeza_capas.evaluar` al final, también cuando `motivo` ≠ OK), `app/hoja/capas_trabajo.py` (pasa `nombres=(doc.name,)`), `app/hoja/interpretacion_guardada.py` (`CLASES` + `"hoja.certeza_capas:CapaCerteza"`)
- Test: `tests/test_certeza_capas.py`

**Interfaces:**
- Consumes: `imagen_ejes.es_imagen/tipo_imagen/rgb_de`, `composicion_hermanos.utilidad(nombre)`, `estilos_sugeridos.utilidad_de_texto`, `recognition_grosor_registros.RX_DIAM`, `recognition_grosor_mapa.MATERIALES`.
- Produces:
  - `@dataclass CapaCerteza: capa: str; utilidad: str | None; seguro: bool; a_favor: list[str]; en_contra: list[str]; simbolos: list[str]` — evidencias como claves: `"nombre"`, `"leyenda"`, `"texto"`, `"rotulos"`, `"trayectoria"`, `"contradice:<UTIL>"`, `"varios_colores"`, `"sin_evidencia"`.
  - `evaluar(paths, corridas, utilidad_texto: str | None, nombres: Sequence[str], leyenda=None) -> list[CapaCerteza]` — una por capa de LÍNEA de imagen. Reglas:
    - **Seguro** = una sola utilidad candidata por nombre, leyenda o texto; además la capa es la única de línea de COLOR de la hoja (imagen o vector, sin negro ni gris) o tiene ≥ `MIN_VOTOS` rótulos de diámetro a ≤ `CERCA_LETRAS` letras; y no hay `contradice:*`.
    - **Negro/gris de imagen** (máx − mín < 0.02·255 o máx < 0.02·255): nunca seguro sin leyenda o rótulos.
    - **`simbolos`** = capas de símbolo del mismo color con ≥ `FRACCION_EN_PUNTAS` = 0.3 de sus centros a ≤ 1.5·r de una punta o un vértice de los ejes.
    - **Trayectoria** = esa misma condición (cuenta como `a_favor`, no decide).

- [ ] **Step 1: Write the failing tests**

```python
def test_phoenix_sd_es_drenaje_seguro():
    caps = _sugerir(_sd_south()[3], nombres=["QS SD_Indian School_South.pdf"]).capas
    c, = [c for c in caps if c.capa.endswith("[0,77,168]]")]
    assert c.utilidad == "DRENAJE" and c.seguro and "nombre" in c.a_favor and "rotulos" in c.a_favor
    assert c.simbolos                                    # sumideros en las puntas

def test_relleno_no_es_capa_de_linea():
    assert not any(c.capa.endswith("[128,166,212]]") for c in _sugerir(_sd_south()[3], nombres=[...]).capas)

def test_dos_colores_es_dudoso():
    caps = ES.sugerir(_pdf_dos_colores()[0], nombres=["plano.pdf"]).capas
    assert caps and not any(c.seguro for c in caps) and all("varios_colores" in c.en_contra or "sin_evidencia" in c.en_contra for c in caps)

def test_rotulo_de_otra_utilidad_contradice():
    c, = ES.sugerir(_pdf_sd_con_rotulo_water()[0], nombres=["QS SD_x.pdf"]).capas
    assert not c.seguro and "contradice:AGUA" in c.en_contra

def test_interpretacion_guardada_roundtrip_con_capas():
    s = ES.Sugerencia(capas=[CapaCerteza("x", "DRENAJE", True, ["nombre"], [], [])])
    assert IG.decodificar(IG.codificar(s)) == s
```

- [ ] **Step 2: Correr** `python -m pytest tests/test_certeza_capas.py -q`. Esperado: FAIL.
- [ ] **Step 3: Implementar** `evaluar` y los cambios de `sugerir`, `capas_trabajo` e `interpretacion_guardada`. Pasar los textos de las hojas de ORIGEN en la compuesta: `nombres` también recibe `src_names` (ver Tarea 7).
- [ ] **Step 4: Correr** el archivo nuevo + `tests/test_estilos_sugeridos.py tests/test_flujo_abrir_interpretar.py -q`. Esperado: PASS; las existentes sin cambios.
- [ ] **Step 5:** Dejar sin commit.

---

### Task 7: Aplicar lo seguro y las respuestas del usuario

**Files:**
- Modify: `app/ui/asistente/roles_iniciales.py` (nuevo parámetro `respuestas: dict | None = None` y `nombres_fuentes: Callable[[], Sequence[str]] | None = None`; después del bloque de `_apply_estilos_sugeridos`, aplicar cada `CapaCerteza`: si hay respuesta del usuario para esa capa, manda ella; si `seguro`, rol LÍNEAS de su utilidad + `simbolos` como `ROLE_BUZONES`, anotados en `CLAVE_LEYENDA`; respuesta «NO_RED» = nada)
- Modify: `app/ui/ventana/ventana_interpretar.py` (`_interp_aplicar` pasa `respuestas=self._respuestas_de_hoja()` y `nombres_fuentes`), `app/ui/ventana/app_window.py` (atributo `capas_imagen_respuestas: dict = {}`, que vacía `_reset_model`), `app/project_io.py` (clave `capas_imagen_respuestas` en el modelo), `app/ui/ventana/respaldo_editor.py` (`CLAVES`)
- Create: `app/ui/ventana/ventana_capas_imagen.py` (`CapasImagenMixin`: `_respuestas_de_hoja() -> dict[str, str]` = las del sha1 de cada PDF de origen de la hoja; `responder_capa_imagen(capa: str, utilidad: str | None)` = guarda bajo el sha1 de los PDF de origen de la hoja, con `None` → «NO_RED», recalcula los roles con `roles_iniciales` y refresca el panel; un `_push`)
- Test: `tests/test_capas_imagen_respuestas.py`

**Interfaces:**
- Consumes: `CapaCerteza` (Tarea 6).
- Produces: `Main.capas_imagen_respuestas: dict[str, dict[str, str]]` (sha1 → {capa: utilidad | "NO_RED"}); `Main.responder_capa_imagen(capa, utilidad)`; `NO_RED = "NO_RED"` en `ventana_capas_imagen`.

- [ ] **Step 1: Write the failing tests**

```python
def test_seguro_se_asigna_solo():
    roles = RI.roles_iniciales(layers, None, sug_seguro_drenaje)
    assert CAPA_AZUL in roles["DRENAJE"][rec.ROLE_LINEAS]
    assert CAPA_SUMIDERO in roles["DRENAJE"][rec.ROLE_BUZONES]

def test_dudoso_no_se_asigna():
    roles = RI.roles_iniciales(layers, None, sug_dudoso)
    assert not any(CAPA_AZUL in r.get(rec.ROLE_LINEAS, ()) for r in roles.values())

def test_respuesta_manda_y_vale_en_otra_hoja(win_sd):        # ventana real, PDCAD_PROCESO=0
    win_sd.responder_capa_imagen(CAPA_AZUL, "ALCANTARILLADO")
    win_sd._change_page(4)                                    # otra hoja del mismo PDF
    assert CAPA_AZUL in win_sd._layer_roles_by_utility["ALCANTARILLADO"][rec.ROLE_LINEAS]

def test_respuestas_van_al_digproj_y_cancelar_las_repone(win_sd, tmp_path): ...
```

- [ ] **Step 2: Correr** `python -m pytest tests/test_capas_imagen_respuestas.py -q`. Esperado: FAIL.
- [ ] **Step 3: Implementar.** La respuesta del usuario se guarda con `SUMAR_LEYENDA` (asignación a mano que pasa a otras hojas); lo seguro va como la leyenda, solo en esa hoja.
- [ ] **Step 4: Correr** el archivo + `tests/test_flujo_abrir_interpretar.py tests/test_respaldo_editor.py -q`. Esperado: PASS.
- [ ] **Step 5:** Dejar sin commit.

---

### Task 8: Preguntarle al usuario (panel «Reconocer» y «Capas y estilos…»)

**Files:**
- Create: `app/ui/comun/tarjeta_capa_imagen.py` (`TarjetaCapaImagen(QFrame)`: muestra del color, «Hay líneas en la imagen de la hoja que no sé de qué red son», porqué en una frase (`porque(c: CapaCerteza) -> str`), botones de las utilidades —primero las candidatas, luego «Otra…» (menú con las demás) y «No es una red»—, ⌖. Diseño: texto arriba, botones debajo. Señales `elegida(str capa, object utilidad)`, `ubicar(str capa)`)
- Modify: `app/ui/comun/panel_reconocer.py` (`PanelReconocer.poner_dudosas(capas: list)`: una tarjeta por capa dudosa sin respuesta, arriba de las filas; la fila de una utilidad asignada sola dice «asignada por: …» en su detalle), `app/ui/ventana/ventana_reconocer.py` (conecta las señales: `elegida` → `responder_capa_imagen`, `ubicar` → resalta los ejes de la capa en el plano con el resaltado de «Capas y estilos…» y encuadra), `app/ui/asistente/layer_assignments.py` o el árbol de capas (capa dudosa con icono «?» y el porqué en el globo)
- Modify: `app/traduccion/i18n_en.py`
- Test: `tests/test_panel_reconocer.py` (casos nuevos), `tests/test_capas_imagen_respuestas.py`

**Interfaces:**
- Consumes: `CapaCerteza`, `Main.responder_capa_imagen`.
- Produces: `PanelReconocer.poner_dudosas`, `TarjetaCapaImagen`.

- [ ] **Step 1: Write the failing tests**

```python
def test_tarjeta_aparece_y_responder_la_quita(win_dudosa):
    tarjetas = win_dudosa.panel_reconocer.findChildren(TarjetaCapaImagen)
    assert len(tarjetas) == 2
    tarjetas[0].elegida.emit(tarjetas[0].capa, "DRENAJE")
    assert len(win_dudosa.panel_reconocer.findChildren(TarjetaCapaImagen)) == 1
    assert win_dudosa.reconocer_estado.filas["DRENAJE"].estado == "pendiente"

def test_no_es_red_no_reconoce(win_dudosa): ...
def test_seguro_no_muestra_tarjeta(win_sd): assert not win_sd.panel_reconocer.findChildren(TarjetaCapaImagen)
def test_textos_traducidos(): ...      # tests/test_i18n.py sigue pasando
```

- [ ] **Step 2: Correr** `python -m pytest tests/test_panel_reconocer.py tests/test_capas_imagen_respuestas.py tests/test_i18n.py -q`. Esperado: FAIL en las nuevas.
- [ ] **Step 3: Implementar.** La tarjeta usa los tokens de `theme` (sin colores de utilidad ni de control de calidad) y `ui_common.fila_lista` si hay listas. Se suma a `tests/test_asistente_sin_amontonar.py` si el panel lo cubre.
- [ ] **Step 4: Correr** lo mismo + `tests/test_paneles.py -q` (comparar con el estado previo: `test_paneles` ya tenía fallas conocidas). Esperado: PASS en las nuevas, sin fallas nuevas.
- [ ] **Step 5:** Dejar sin commit.

---

### Task 9: Punta a punta, documentación y versión

**Files:**
- Test: `tests/test_ejes_imagen_flujo.py` — ventana real: abrir `QS SD_Indian School_South.pdf` hoja 4 → interpretar → fila DRENAJE pendiente sin preguntar → ▶ → importar → DXF con `PDFCAD_PIPE` NET_KIND=gravity, al menos un DIAMETER=18 y vértices de bóveda en los sumideros.
- Modify: `CLAUDE.md` (corregir «trae los LOTES COMO IMAGEN» → la red es imagen y los lotes son vector; sección nueva «Ejes de la red en imagen» con módulos, nombres de capa, certeza y respuestas), `app/nucleo/model.py` (`VERSION` 2.1.0 → 2.2.0, entrada de `CHANGELOG`), `app/traduccion/i18n_en_changelog.py`, `app/docs/manual.es.html` + `manual.en.html` (en el capítulo de mapas sin capas: «Redes que vienen como imagen» y la tarjeta de pregunta).
- Modify: `PDF-a-CAD.spec` y `app/autoprueba.py` (`skimage.morphology` y los módulos nuevos de `hoja/` en `hiddenimports` / `MODULOS_POR_NOMBRE`).

- [ ] **Step 1: Escribir `tests/test_ejes_imagen_flujo.py`** con lo de arriba (se salta si falta el PDF).
- [ ] **Step 2: Correr.** Esperado: PASS (si falla, el arreglo va en la tarea dueña).
- [ ] **Step 3: Foto antes/después.** `python scripts/pruebas.py mapas reconocimiento` y `tests/test_instalador.py -q`. Esperado: sin fallas nuevas respecto a HEAD (anotar las que ya fallaban).
- [ ] **Step 4: Actualizar la documentación y la versión** (archivos de arriba).
- [ ] **Step 5:** Dejar sin commit; avisar al usuario qué archivos cambiaron.

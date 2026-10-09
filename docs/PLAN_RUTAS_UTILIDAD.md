# Plan: trazar la RUTA de cada utilidad (unir tramos reconocidos en recorridos)

## 1. Objetivo

Hoy el reconocimiento entrega la geometría bien: cada línea de la capa sale
como polilínea con sus quiebres, y en cada T / junction / bóveda la polilínea
**se corta** (así lo hace `assemble`: encadena solo por nodos de grado 2 y
corta en nodos de grado ≥ 3). El resultado es correcto pero "picado": una
utilidad que recorre toda la calle queda en 5–10 tramos cortados en cada
punto donde le llega un ramal.

Lo que queremos añadir, **después** del reconocimiento y **sin tocar** el
núcleo geométrico:

- Una utilidad **empieza** en un punto y desde ahí se **sigue la ruta**: en
  cada nodo donde llegan varios tramos, la ruta continúa por el que sigue la
  trayectoria (el "de frente"); el que se desvía es un **ramal**, que a su vez
  es el inicio de otra ruta.
- Donde **no hay trayectoria clara** (una Y simétrica, dos candidatos casi
  iguales), **no se une nada**: se deja como está.
- La geometría no cambia: **cero puntos nuevos, cero puntos movidos**. Solo se
  concatenan polilíneas que ya comparten un vértice. Cobertura, bóvedas,
  `kinds` y la regla de oro quedan intactos.

## 2. Técnica: «strokes» por buena continuación (Thomson & Richardson)

Es exactamente el problema clásico de generalización de redes viales:
construir **strokes** = cadenas de segmentos que un ojo humano ve como "una
misma línea" por el principio gestáltico de *buena continuación*. El
algoritmo (Thomson & Richardson, 1999; variante *every-best-fit*) es:

1. Construir el grafo: nodos = vértices compartidos, aristas = polilíneas.
2. En cada nodo, para cada par de aristas incidentes calcular el **ángulo de
   deflexión** (cuánto habría que girar para pasar de una a la otra).
3. Emparejar aristas en el nodo de menor a mayor deflexión, aceptando un par
   solo si ambas están libres y la deflexión ≤ umbral. Lo que queda sin
   pareja **termina** ahí.
4. Los pares definen las cadenas (strokes): recorrerlas y concatenar.

Ventajas para nosotros: es puro, O(E log E), determinista, no inventa
geometría, y "dejar como está" sale gratis (no emparejar = cortar, que es lo
que ya hay hoy). El único juicio es el umbral de deflexión y la regla de
ambigüedad.

## 3. Dónde encaja (sin alterar lo que ya funciona)

```
recognition_geom.reconstruct(paths por capa)  → GeomResult.polylines   (NO se toca)
        │
        ▼
routes.build_routes(polylines, pattern)       → polilíneas unidas + route_id   (NUEVO, puro)
        │
        ▼
recognition.recognize_page  → RecognizedPolyline (px)  → preview → pipes_from_recognition
```

- Módulo **nuevo** `app/routes.py`, PURO (sin Qt ni fitz), como
  `recognition_geom.py`. Trabaja sobre `recognition_geom.Polyline` (`pts`,
  `kinds`) en coordenadas PDF (pt), **por capa** (se llama una vez por cada
  `GeomResult` de cada capa OCG: nunca une capas distintas ni activas con
  abandonadas — eso ya lo garantiza `recognize_page`, que reconstruye por
  `by_ocg`).
- `recognize_page` recibe `join_routes: bool = True`. Si es `False` devuelve
  exactamente lo de hoy. Así el cambio es opt-in y reversible desde la UI.
- `RecognizedPolyline` gana dos campos: `route_id: int` (rutas numeradas por
  capa) y `n_segments: int` (cuántos tramos originales une; 1 = sin cambios).
- `pipes_from_recognition` NO cambia de contrato: una polilínea = una pipe.
  Solo que ahora hay menos pipes y más largas. Los `vertex_kinds` viajan
  igual; el vértice de unión conserva su tipo (`tee`/`junction`/`vault`), así
  `hide_soft_vertex_structures` y las cajas siguen funcionando igual.
- **DXF / plugin**: sin cambios de contrato. En Civil 3D salen menos
  polilíneas (pipe runs) y más largas; las estructuras en los vértices de
  unión siguen ahí porque el ramal comparte ese vértice.

## 4. Diseño detallado de `app/routes.py`

### 4.1 Constantes (arriba del módulo, con comentario)

```python
NODE_TOL_PT = 0.6           # dos extremos a ≤0.6 pt son el mismo nodo (new_node une a 0.5)
LOOKAHEAD_FACTOR = 3.0      # rumbo de llegada medido a 3 guiones largos del nodo (~66 pt)
LOOKAHEAD_MIN_PT = 20.0     # …y nunca menos de 20 pt
THETA_JUNCTION_DEG = 35.0   # en nodo de grado ≥3: continúa "de frente" si gira ≤35°
THETA_DEG2_DEG = 100.0      # en nodo de grado 2: una esquina (≤100°) sigue siendo la misma ruta
AMBIGUOUS_DELTA_DEG = 10.0  # si el 2.º mejor par difiere <10° del mejor, no hay trayectoria clara
TERMINAL_KINDS = ("cut",)   # marco de la vista: nunca se cruza
```

### 4.2 Grafo

```python
@dataclass
class _Edge:
    idx: int                 # índice en la lista de polilíneas de entrada
    pl: Polyline
    node_a: int              # nodo del primer vértice
    node_b: int              # nodo del último vértice

class _Graph:
    nodes: List[Pt]                     # posición representativa
    node_kind: List[str]                # kind "más fuerte" visto en ese nodo (vault > junction > tee > …)
    incident: Dict[int, List[Tuple[int, str]]]   # nodo → [(edge_idx, "a"|"b")]
```

Construcción:

1. `_node_of(p)`: hash espacial por celda de 2 pt; devuelve el nodo existente
   a ≤ `NODE_TOL_PT` o crea uno. (Los extremos que `resolve_nodes` unió
   comparten coordenadas exactas; la tolerancia cubre redondeos.)
2. Por cada polilínea con ≥ 2 puntos: edge con `node_a = _node_of(pts[0])`,
   `node_b = _node_of(pts[-1])`. Polilíneas cerradas (`node_a == node_b`)
   se registran igual (loop).
3. **Solo los extremos** de cada polilínea crean nodos. Los vértices
   interiores (`edge`, `bend`, `tee` interior de una línea que ya atraviesa,
   `vault` interior) NO son nodos del grafo: la polilínea ya pasa por ahí y
   no hay nada que decidir. (Un ramal que nace en un `tee` interior de otra
   polilínea tiene su extremo en ese punto → crea el nodo → el nodo queda con
   grado 1 desde el punto de vista del grafo → el ramal simplemente empieza
   ahí. Correcto: la línea principal ya es continua a través de ese `tee`.)
4. Grado = `len(incident[n])`. Un loop cuenta 2.

### 4.3 Rumbo de llegada a un nodo (robusto a quiebres pequeños)

```python
def _heading_into(edge, side, lookahead) -> (ux, uy):
    """Vector unitario con el que la arista LLEGA al nodo `side`.
    Se toma el punto de la polilínea a `lookahead` de arco hacia atrás
    (interpolando sobre el segmento) y se apunta desde ese punto al nodo.
    Si la polilínea es más corta que lookahead, se usa el otro extremo."""
```

`lookahead = max(LOOKAHEAD_MIN_PT, LOOKAHEAD_FACTOR * pattern.dash_long)`
(si `pattern` es None → `LOOKAHEAD_MIN_PT`). Así un codo de transición de 5
pt junto al nodo no decide el rumbo; lo decide la dirección general de la
línea.

Deflexión entre dos aristas `e`, `f` en el nodo:
`deflection = angle_between(heading_into(e), -heading_into(f))` — es decir,
cuánto gira quien viene por `e` para salir por `f`. 0° = perfectamente de
frente; 180° = vuelta en U.

### 4.4 Emparejamiento en cada nodo (every-best-fit)

```python
for n in nodes:
    inc = incident[n]
    if node_kind[n] in TERMINAL_KINDS:      # 'cut': marco → todo termina aquí
        continue
    deg = len(inc)
    if deg == 1: continue
    theta = THETA_DEG2_DEG if deg == 2 else THETA_JUNCTION_DEG
    pairs = sorted(((defl(e, f), e, f) for e, f in combinations(inc, 2)), key=first)
    free = {e: True for e in inc}
    for k, (d, e, f) in enumerate(pairs):
        if d > theta: break
        if not free[e] or not free[f]: continue
        # ambigüedad: otro par que comparte arista con este y casi igual de bueno → no unir
        rival = min((d2 for d2, e2, f2 in pairs[k+1:]
                     if free[e2] and free[f2] and {e2, f2} & {e, f}), default=None)
        if rival is not None and rival - d < AMBIGUOUS_DELTA_DEG:
            free[e] = free[f] = False        # ambas quedan cortadas en este nodo
            continue
        link(e, f)                            # partner[(e, side_e)] = (f, side_f)
        free[e] = free[f] = False
```

Notas:
- `e`, `f` son `(edge_idx, side)`; una misma arista puede aparecer dos veces
  en un nodo solo si es un loop; en ese caso no se empareja consigo misma.
- En grado 2 con deflexión > `THETA_DEG2_DEG` (horquilla / vuelta en U): no
  se une. Son dos líneas que mueren en el mismo punto, no una ruta.
- En una **bóveda** (kind `vault` en el nodo) se aplica lo mismo: la línea
  que atraviesa (deflexión ~0°) se une; los ramales empiezan ahí.
- `stop` (llegada a bóveda sin nodo interior): nodo de grado 1 → fin de ruta.
  Dos `stop` en bordes opuestos de una bóveda son puntos distintos → no se
  unen (regla del usuario: dentro de la bóveda no se inventa nada).
- `end`/`end` coincidentes (dos polilíneas que mueren en el mismo punto): es
  un nodo de grado 2 normal → se unen si giran ≤ 100°.

### 4.5 Recorrido y concatenación

```python
visited = set()
routes = []
for e in edges (orden: primero las que tienen un extremo sin pareja):
    if e in visited: continue
    # ir hacia atrás hasta un extremo sin pareja (o cerrar el loop), luego avanzar
    chain = walk(e)                 # lista de (edge, orientación)
    pts, kinds = concat(chain)      # se elimina el punto duplicado en cada unión;
                                    # el vértice de unión conserva el kind "más fuerte"
                                    # (vault > junction > tee > corner > bend > end)
    routes.append(Polyline(pts, kinds), n_segments=len(chain))
```

Orientación / "dónde empieza": el extremo inicial es el terminal con esta
prioridad: `cut` o `end` primero (inicio real de la utilidad), luego `stop`,
luego el que quede; a igualdad, el de menor `x`, luego menor `y`
(determinista, y coincide con "de izquierda a derecha" en el plano). Un loop
empieza en su vértice de menor `x`.

Invariantes a comprobar al salir (asserts en tests, no en producción):
- Cada polilínea de entrada aparece en exactamente una ruta (partición).
- Suma de longitudes = suma de longitudes de entrada (±1e-6).
- Ningún punto nuevo: el multiconjunto de vértices de salida = el de entrada
  menos los puntos de unión duplicados.

### 4.6 API pública

```python
@dataclass
class Route:
    pl: Polyline          # polilínea unida
    n_segments: int       # tramos originales que la componen
    members: List[int]    # índices de las polilíneas de entrada, en orden

def build_routes(polylines: Sequence[Polyline], pattern: Optional[Pattern]) -> List[Route]
```

## 5. Cambios fuera del módulo

| Archivo | Cambio |
|---|---|
| `app/routes.py` | NUEVO (todo lo de §4). < 300 líneas. |
| `app/recognition.py` | `recognize_page(..., join_routes: bool = True)`. Tras `geom.reconstruct(...)` por capa: `routes = build_routes(g.polylines, g.pattern) if join_routes else [Route(pl, 1, [i]) …]`. Convertir a px cada `route.pl` (mismo bucle `clean/kinds` de hoy). `RecognizedPolyline` gana `route_id: int = 0`, `n_segments: int = 1`. `RecognitionResult` gana `n_routes: int`, `n_segments_total: int` (para el QA). El resto (bóvedas = vértices `vault`, cobertura, huérfanas) queda igual — la cobertura se calcula en `reconstruct`, antes de unir. |
| `app/recognition_dialog.py` | Resumen: «Rutas: N (unen M tramos)». Casilla **«Unir tramos en rutas»** (marcada por defecto) en el panel: al cambiarla se vuelve a llamar `recognize_page` con `join_routes` invertido (es rápido) o, mejor, el preview guarda las dos variantes. Dibujo: cada ruta con un punto más grande en su inicio (para ver "dónde empieza") — opcional. |
| `app/app_window.py` | `_start_recognition` pasa `join_routes=self._join_routes` (atributo, default True). Mensaje al importar: «Importadas N rutas (M tramos)». |
| `app/workers.py` | `RecognitionWorker` acepta y reenvía `join_routes`. |
| `app/model.py` | `VERSION` + `CHANGELOG`: «Los tramos reconocidos se unen en rutas por buena continuación…». |
| `CLAUDE.md` | Párrafo en el mapa del repo para `routes.py` (técnica, umbrales, "no une capas ni inventa puntos"). |
| `tests/test_routes.py` | NUEVO (ver §6). |

`recognition_geom.py` **no se toca**.

## 6. Pruebas (`tests/test_routes.py`)

Usar el generador `Sheet` de `tests/test_recognition_geom.py` (importarlo) y
pasar `G.reconstruct(...).polylines` a `build_routes`. Casos:

1. **T**: horizontal + ramal vertical que muere en ella → 2 rutas; la
   horizontal es una sola ruta que conserva el vértice `tee` en el medio; el
   ramal empieza en ese punto (`kinds[0] == "tee"`).
2. **Cruce X con junction** (dos líneas que se cruzan y comparten nodo): 2
   rutas, cada una de frente.
3. **Y simétrica** (dos ramales a ±30° del tronco): ambiguo → 3 rutas, sin
   unir (`n_segments == 1` en todas).
4. **Y asimétrica** (uno a 5°, otro a 40°): el de 5° continúa el tronco; el
   de 40° es ramal → 2 rutas.
5. **Esquina en L** partida en dos polilíneas (grado 2, 90°) → 1 ruta.
6. **Horquilla** (dos líneas que mueren en el mismo punto a 170°) → 2 rutas.
7. **Bóveda atravesada + stub**: la línea que atraviesa (kinds `edge, vault,
   edge`) es 1 ruta; el stub que llega al borde con `stop` es otra.
8. **`cut`** (marco): nunca se une a través de un nodo `cut`.
9. **Invariantes** sobre el DU06 (hojas 3, 4, 9, 13, 14): partición, suma
   de longitudes, sin puntos nuevos, `n_routes <= n_polylines`, cobertura
   idéntica con `join_routes=True/False`. Hoja 13: las dos líneas «PROP COMM
   DB» y la vertical de Haynes St quedan en ≤ 3 rutas.
10. **Determinismo**: dos llamadas dan el mismo orden y orientación.

## 7. Orden de implementación sugerido

1. `routes.py` con grafo + heading + emparejamiento + recorrido (§4), tests
   sintéticos 1–8. No conectar nada aún.
2. Tests de invariantes sobre el DU06 (9–10). Ajustar umbrales solo si un
   caso real lo pide, y anotar por qué.
3. Conectar en `recognize_page` con `join_routes` (default True) + campos
   nuevos. Verificar que con `False` la salida es byte a byte la de hoy.
4. Preview: resumen y casilla. Importar: mensaje.
5. CHANGELOG / versión / CLAUDE.md / recompilar.

## 8. Decisiones abiertas (si quieres cambiarlas, es un número)

- `THETA_JUNCTION_DEG = 35°`: por debajo de eso, en un cruce, "de frente".
  Con 45° una diagonal suave también seguiría; con 25° solo lo casi recto.
- `THETA_DEG2_DEG = 100°`: una esquina cuadrada (90°) sí es la misma ruta.
- `AMBIGUOUS_DELTA_DEG = 10°`: margen para declarar "no hay trayectoria clara".
- Inicio de ruta: hoy propongo terminal `end/cut` y luego menor `x`. Si
  prefieres "empieza en la bóveda más a la izquierda", es cambiar la
  prioridad en §4.5.

# Gestión del proyecto

Todo lo de seguimiento vive aquí, en el repo. Los comandos se corren desde la raíz:
`python scripts/gestion <comando>`, o con doble clic en `gestion.bat`, que abre el administrador.

| Qué | Dónde |
|---|---|
| Funciones (fuente del diagrama) | `gestion/funciones.toml` |
| Lo que trae cada entrega | `gestion/versiones/<versión>.toml` |
| Piezas de Jean y Elvis (ficha + capturas) | `gestion/catalogo/<área>/<tipo>/<id>/` |
| Casos dorados y regresión | `gestion/casos_dorados.toml`, `scripts/regresion.py` |
| Lista de humo | `gestion/lista_humo.md` → `gestion/entregas/<versión>/humo.md` |
| Observaciones, bugs y consultas | GitHub Issues (plantillas en `.github/ISSUE_TEMPLATE`) |
| Plantilla de plugin C# para Jean y Elvis | `plantillas/plugin-civil3d/` |

## Regla de revisión
- **Cualquiera del equipo, o su Claude**, propone: `python scripts/gestion proponer <id> <estado> --por Nombre --nota "…"`.
- **Solo el administrador** aprueba, en `python scripts/gestion admin`. El cliente ve únicamente el `estado` aprobado.
- En el administrador también se **agregan** funciones y grupos (quedan aprobados), se **editan** nombre, grupo, estado y nota de cualquier función, se **quitan** (no si una versión la usa) y, en «Estados y colores», se cambia el color de un estado o se crean estados propios (`[[estado]]` en `funciones.toml`).
- **Entrada del administrador** = el diagrama editable (igual al del cliente). Versiones, propuestas por revisar, estados y piezas van en «Más opciones» (`/panel`). La vista previa se arma aunque falte aprobar algo; publicar no.
- **Privado**: el 🔒 de una fila, tarjeta o área la deja fuera de todo lo que ve el cliente (sitio y reporte; `privado = true` en `funciones.toml`). Una novedad de versión no puede apoyarse en una función privada.
- **Funciones**: la página de entrada abre el diagrama tal como lo ve el cliente y ahí se escribe encima: nombres, títulos y subtítulos de tarjetas y áreas; clic en el estado de una fila para cambiarlo; «+ Agregar función» (Enter crea y deja escribir la siguiente), «+ Nueva tarjeta», «+ Nueva área»; ✕ quita (no si la función está en una versión) y las filas se arrastran por su asa ⋮⋮. Todo se guarda al momento.
- **Versiones**: «Nueva versión» y «Editar» abren la versión tal como la ve el cliente, y ahí se escribe encima: «+ Agregar» en cada sección, ↑ ↓ ✕ por cambio, y las funciones se buscan y asocian a mano en «+ Asociar función…» (o se crean ahí mismo). Nada se sugiere solo; todo se guarda solo y cada cambio dice en rojo qué le falta para publicar. Una versión publicada se ve en solo lectura hasta pasarla a borrador.

**Cada cambio de una versión va asociado a funciones del diagrama** (`funciones = [...]` en cada `[[novedad]]`), y cada una debe existir y tener estado aprobado. Si falta algo, la versión no se puede marcar como publicada, y si ya lo está, el sitio no se publica. El administrador muestra qué falta. Si el cambio es de algo que aún no está en el diagrama, primero se agrega la función (con `propuesto`) y se aprueba.

Estados (entre paréntesis, lo que ve el cliente):
- `probado` 🟢 (Disponible)
- `falta_probar` 🌸 (En pruebas)
- `optimizar` 🟠 (En mejora)
- `en_desarrollo` 🔵 (En desarrollo)
- `con_bug` 🔴 (En corrección)
- `planificado` ⚪ (Planificado)
- vacío = sin clasificar

## Ciclo de 2 semanas
1. **Reunión con el cliente.** Cada observación pasa a un issue «Observación del cliente», con captura. Para crear el archivo de la entrega: `python scripts/gestion nueva-version 2.0.1`.
2. **Desarrollo.** Integración con Santos, Jean y Elvis en días fijos: lunes y jueves.
3. **Congelamiento** (2 días antes de entregar). Ya no entra nada nuevo; solo se prueba:
   - `build_all.bat`, que también verifica el instalador;
   - `python scripts/regresion.py`, que debe dar 0 diferencias;
   - `python scripts/gestion humo 2.0.1` → la lista de humo la hace Jean o Elvis con el instalador.
4. **Entrega:**
   - completar `versiones/2.0.1.toml` con títulos simples y la observación que atiende cada punto;
   - en el administrador, aprobar estados, marcar la versión como publicada, «Reporte PDF» y «Publicar en Cloudflare»;
   - enviar el PDF y el texto de WhatsApp (`gestion/_salida/reportes/`).

## Cloudflare (sitio del cliente)
- **Primera vez en esta PC:** `npx wrangler login`. Después basta el botón «Publicar en Cloudflare» o `python scripts/gestion publicar`.
- **Link:** `https://pdfacad-funciones.pages.dev`. El nombre del proyecto está en `[proyecto] cloudflare` de `funciones.toml`. Hay que anotar el link en `sitio`, porque sale en el reporte.
- **Qué se publica:** solo `gestion/_salida/publico`, que tiene únicamente lo aprobado y está marcado `noindex`. El administrador es local (127.0.0.1) y nunca se sube.

## GitHub Issues
- **Etiquetas, una vez:** crear un token fine-grained con permiso «Issues: read and write», luego `set GITHUB_TOKEN=…` y `python scripts/gestion etiquetas`.
- **Tablero:** GitHub → Projects → New project → «Board», con las columnas Pendiente · En desarrollo · Por probar · Probado · Entregado.
- **Hitos:** un *Milestone* por versión (2.0.1, 2.1.0…).
- **Jean y Elvis** no necesitan Git para reportar: una cuenta de GitHub, «New issue» y pegar las capturas con Ctrl+V.

## Diagrama en draw.io
`python scripts/gestion drawio [versión]` crea `gestion/_salida/funciones.drawio` desde los datos, con los colores de cada estado. La fuente de verdad es `funciones.toml`: si retocas el .drawio, es solo para presentar.

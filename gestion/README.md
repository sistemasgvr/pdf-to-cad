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

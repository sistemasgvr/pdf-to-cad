# IA ↔ Civil 3D (MCP)

La IA consulta el dibujo abierto en Civil 3D y **propone** cambios; el usuario los confirma. Funciona con dos
entradas que usan el mismo servidor:

1. **La app (Qwen local)** — `app/ia/civil3d_mcp.py` + `app/ia/civil3d_agente.py` (perfil `basico`).
2. **Claude Code / Claude Desktop** — se registra el servidor y listo (perfil `completo`).

## Arquitectura (limpia)

```
Claude (Code/Desktop) ─┐                           ┌───────────── plugin (dentro de Civil 3D) ─────────────┐
App Python + Qwen ─────┴─ MCP stdio ─► PdfCadMcp.exe ─ tubería ─► Infraestructura ─► Aplicación ─► Dominio
                                       (Presentación)  \\.\pipe\   (Civil 3D API)    (casos de uso) (reglas)
```

| Capa | Carpeta | Depende de |
|---|---|---|
| Contratos | `API-CIVIL/proyecto1/proyecto1/Mcp/Contratos` — protocolo de la tubería y **catálogo cerrado** de herramientas | nada |
| Dominio | `…/Mcp/Dominio` — foto del modelo (ft / in), resúmenes, filtros, reglas de cada cambio | nada |
| Aplicación | `…/Mcp/Aplicacion` — `Despachador` (perfil, validación, propuesta → confirmación, registro) y puertos | Dominio, Contratos |
| Infraestructura | `…/Mcp/Infraestructura` — lector/editor de Civil 3D, hilo de AutoCAD, registro `.jsonl`, servidor de la tubería | Aplicación + Autodesk |
| Presentación | `API-CIVIL/proyecto1/PdfCadMcp` — servidor MCP por stdio (JSON-RPC 2.0) | solo Contratos |

Ni Dominio ni Aplicación conocen Autodesk ni MCP: se prueban sin Civil 3D (`McpPruebas`). Un cliente nuevo
(Slack, chat dentro de C3D) es solo otro adaptador; las reglas no se tocan.

## Lineamientos

- Unidades imperiales: cotas y largos en pies, diámetros en pulgadas.
- Los números los calcula el plugin; la IA elige herramientas y redacta.
- **Ningún cambio sin confirmación**: `proponer_cambio` devuelve id + antes/después + consecuencias +
  advertencias; `confirmar_cambio` solo tras el sí del usuario (en la app, solo el botón: el modelo no lo ve).
  Si el elemento cambió desde la propuesta, se rechaza; las propuestas vencen a los 30 min.
- Cada cambio = un paso de deshacer (**U**) y una línea en `<dibujo>.pdfcad-ia.jsonl` junto al DWG
  (quién, origen claude/qwen, cuándo, antes/después, motivo). Dibujo sin guardar → `%APPDATA%\pdf-to-cad\civil3d-ia\`.
- Los elementos se piden por su NOMBRE como lo dice el usuario (`elemento`: «electrico 4 (1)» = «ELECTRICO-4 - (1)»,
  `Dominio/Referencias.cs`); el handle sigue valiendo. Ambiguo o inexistente → el error lista los parecidos.
- Lista cerrada de herramientas; nada de código libre en AutoCAD. La tubería solo acepta al usuario actual.
- Pocos tokens: salidas en tabla (`columnas` + `filas`), topes (`limite`, máx. 200) con «hay N más»,
  descripciones cortas, foto del modelo cacheada hasta que el dibujo cambia.

## Herramientas

| Nombre | Tipo | Perfil básico |
|---|---|---|
| `estado` | lectura | sí |
| `resumen_modelo` | lectura | sí |
| `buscar_tuberias` (red, capa, diámetro, pendiente, texto) | lectura | sí |
| `buscar_estructuras` (red, texto, profundidad) | lectura | no |
| `detalle_elemento` (por nombre → geometría, conexiones, Property Sets) | lectura | sí |
| `ir_a` (encuadra y selecciona) | lectura | sí |
| `proponer_cambio` (`cota_inicio`, `cota_fin`, `capa`, `descripcion`; `valor` o `sumar` ft) | cambio | sí |
| `confirmar_cambio` / `cancelar_cambio` | cambio | sí (en la app, solo el usuario) |
| `historial` | lectura | no |

Agregar una herramienta: catálogo (`McpHerramientas.cs`) + caso en `Despachador.cs` (+ puerto/adaptador si
hace falta leer o escribir algo nuevo) + prueba en `McpPruebas`. Un cambio nuevo: `TiposCambio` y
`ReglasCambio.Preparar` (Dominio) + `Civil3DEditor.Aplicar`. Contratos: solo se AGREGAN campos.

## Uso

1. En Civil 3D: `PANEL_REDES` → **«Encender conexión de la IA»** (o el comando `PDFCAD_IA`; otra vez = apagar).
2. Comprobar (opcional):
   ```powershell
   & "API-CIVIL\proyecto1\PdfCadMcp\bin\Release\net8.0\PdfCadMcp.exe" --probar
   ```
3. **Claude Code**:
   ```powershell
   claude mcp add pdfcad-civil3d -- "D:\…\PdfCadMcp\bin\Release\net8.0\PdfCadMcp.exe" --origen claude
   ```
   **Claude Desktop** (`%APPDATA%\Claude\claude_desktop_config.json`):
   ```json
   { "mcpServers": { "pdfcad-civil3d": {
       "command": "D:\\…\\PdfCadMcp.exe", "args": ["--origen", "claude"] } } }
   ```
4. **App (Qwen)**: Asistente → pestaña **Civil 3D** (`ui/dialogos/ia_civil3d.py` + `ia_civil3d_html.py`, mismo aspecto que el Chat; tarjeta de propuesta con «Aplicar en Civil 3D» / «Descartar»). Por código: `ClienteMCP(perfil="basico", origen="qwen")` + `Agente(cliente, pedir_ollama(config))`;
   `preguntar(texto)` → `Resultado(texto, propuestas)` y la ventana confirma con `agente.confirmar(id)`.
   El modelo debe soportar *tools* en Ollama.

## Compilar y probar

```powershell
dotnet build -c Release API-CIVIL\proyecto1\proyecto1      # plugin (incluye el MCP)
dotnet build -c Release API-CIVIL\proyecto1\PdfCadMcp      # host MCP
cd API-CIVIL\proyecto1\McpPruebas; dotnet run -c Release   # 54 pruebas, incluida la de punta a punta
python -m pytest tests/test_civil3d_mcp.py                 # entrada 1 (app)
```

## Pendiente

- `PdfCadMcp.exe` en el instalador (`build_all.bat` / Inno Setup).
- Más cambios: diámetro/tamaño (por catálogo de familias), mover, perfiles.
- Probado sin Civil 3D (dobles + host real + tubería real); falta la prueba en Civil 3D con un dibujo real.

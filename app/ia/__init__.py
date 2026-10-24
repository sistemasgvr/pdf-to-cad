"""IA de la app (pedido del usuario 2026-10-23), PURA: sin Qt. La interfaz la usa; esto nunca importa la interfaz.

- `proveedor`  quién responde: `Ollama` (servidor propio por Tailscale, hoy) o Claude (después). Todo lo demás
               habla con la interfaz `Proveedor`, así cambiar de modelo es cambiar la configuración.
- `memoria`    lo que la IA aprende de cada proyecto, en TEXTO PLANO (JSONL) en una carpeta junto al .digproj.
- `contexto`   los datos REALES del proyecto en texto compacto (lo único que la IA puede citar).
- `consulta`   «Pregúntale al proyecto»: pregunta → contexto + memoria → respuesta con referencias al plano.
- `redactor_ia` el Informe automático redactado por la IA (con la plantilla de respaldo).
- `texto`      utilidades de texto: números, JSON, normalizar.

Regla de oro: los NÚMEROS los pone la app; la IA solo redacta. Lo que la IA escribe se revisa contra los datos y,
si falla o no responde, sale la plantilla. Pendientes y cómo seguir: `docs/pendientes_ia.md`.
"""

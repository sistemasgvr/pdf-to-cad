# Servidor Ollama (IA) — cómo encontrarlo y diagnosticarlo

La IA de la app usa un servidor Ollama en la red de **Tailscale**. Hoy:

- Máquina: `serversistemas` (Linux)
- Dirección: `http://100.82.39.116:11434`
- Modelo: `qwen3-vl:8b-instruct`

## 1. ¿Dónde está el servidor? (desde Windows, PowerShell)

```powershell
tailscale status
```

Busca la fila `serversistemas`: la primera columna es su IP (100.x.x.x). Debe decir `active` o `-`; si dice
`offline`, la máquina está apagada o sin Tailscale.

También sirve el nombre en lugar de la IP (no cambia aunque cambie la IP):

```powershell
tailscale ip -4 serversistemas
```

## 2. ¿Responde Ollama?

```powershell
Invoke-RestMethod http://100.82.39.116:11434/api/tags
```

- Devuelve la lista de modelos → todo bien.
- «No es posible conectar con el servidor remoto» → seguir con el paso 3.

Para separar red y Ollama:

```powershell
Test-NetConnection 100.82.39.116 -Port 11434
```

| PingSucceeded | TcpTestSucceeded | Qué pasa |
|---|---|---|
| False | False | La máquina no está en Tailscale (apagada / desconectada). |
| True | False | La máquina está, pero Ollama no está corriendo o solo escucha en `127.0.0.1`. |
| True | True | Ollama responde. |

## 3. En el servidor (Linux)

```bash
systemctl status ollama          # ¿está corriendo?
ss -tlnp | grep 11434            # debe decir 0.0.0.0:11434 o *:11434, NO 127.0.0.1:11434
```

Si dice `127.0.0.1:11434`:

```bash
sudo systemctl edit ollama
```

Escribir entre los comentarios del principio:

```
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
```

Guardar (`Ctrl+O`, `Enter`, `Ctrl+X`) y luego:

```bash
sudo systemctl restart ollama
sudo ufw allow 11434/tcp         # solo si el firewall ufw está activo
ollama list                      # modelos instalados
```

## 4. Actualizar la app

En la app: **Ajustes → Asistente IA** («Configurar IA…») → URL `http://<IP>:11434` → «Buscar modelos» → «Probar».
Se guarda por usuario en cada PC (registro `HKCU\Software\pdf-to-cad\app\ia`, valor `url`).

"""Un servidor Gemini SIMULADO (API v1beta) para las pruebas: `models`, `:streamGenerateContent?alt=sse` y
`:generateContent`. `responder(cuerpo) -> str | dict` decide cada respuesta (dict = `candidates[0].content.parts`
completo, para llamadas a herramientas). Anota los pedidos y las cabeceras de clave."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class GeminiFalso:
    def __init__(self, responder, modelos=None, clave="clave-buena", codigo_error=None, saturado=0, demora=0.0):
        self.responder = responder
        self.saturado, self.demora = saturado, demora   # nº de 503 antes de responder; segundos de espera
        self.clave = clave
        self.codigo_error = codigo_error
        self.modelos = modelos if modelos is not None else [
            {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/gemini-2.5-pro", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/text-embedding-004", "supportedGenerationMethods": ["embedContent"]},
            {"name": "models/gemini-2.5-flash-preview-tts", "supportedGenerationMethods": ["generateContent"]},
        ]
        self.pedidos, self.rutas, self.claves = [], [], []
        falso = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *_a):
                pass

            def _json(self, d, code=200):
                b = json.dumps(d).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def _autorizado(self):
                falso.rutas.append(self.path)
                falso.claves.append(self.headers.get("x-goog-api-key"))
                if falso.codigo_error:
                    self._json({"error": {"code": falso.codigo_error, "status": "RESOURCE_EXHAUSTED",
                                          "message": "Quota exceeded"}}, falso.codigo_error)
                    return False
                if self.headers.get("x-goog-api-key") != falso.clave:
                    self._json({"error": {"code": 400, "status": "INVALID_ARGUMENT",
                                          "message": "API key not valid. Please pass a valid API key."}}, 400)
                    return False
                return True

            def do_GET(self):
                if not self._autorizado():
                    return
                if self.path.startswith("/v1beta/models"):
                    self._json({"models": falso.modelos})
                else:
                    self._json({"error": {"code": 404, "message": "no"}}, 404)

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                cuerpo = json.loads(self.rfile.read(n) or b"{}")
                if not self._autorizado():
                    return
                if falso.saturado:
                    falso.saturado -= 1
                    self._json({"error": {"code": 503, "status": "UNAVAILABLE",
                                          "message": "This model is currently experiencing high demand."}}, 503)
                    return
                if falso.demora:
                    import time
                    time.sleep(falso.demora)
                falso.pedidos.append(cuerpo)
                r = falso.responder(cuerpo)
                if ":streamGenerateContent" in self.path:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.end_headers()
                    texto = r if isinstance(r, str) else ""
                    trozos = [texto[i:i + 7] for i in range(0, len(texto), 7)] or [""]
                    for k, tr in enumerate(trozos):
                        d = {"candidates": [{"content": {"role": "model", "parts": [{"text": tr}]}}]}
                        if k == len(trozos) - 1:
                            d["usageMetadata"] = {"candidatesTokenCount": len(trozos)}
                        self.wfile.write(("data: " + json.dumps(d) + "\r\n\r\n").encode())
                else:
                    partes = r if isinstance(r, list) else [{"text": r}]
                    self._json({"candidates": [{"content": {"role": "model", "parts": partes}}]})

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}/v1beta"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def cerrar(self):
        self.srv.shutdown()
        self.srv.server_close()

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        self.cerrar()

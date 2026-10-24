"""Un servidor Ollama SIMULADO para las pruebas de la IA (sin red ni modelo): responde /api/tags y /api/chat
(en trozos NDJSON, como el real). `responder(cuerpo) -> str` decide el texto de cada respuesta."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class OllamaFalso:
    def __init__(self, responder, modelos=("qwen3-vl:8b",), demora=0.0):
        self.responder = responder
        self.modelos = list(modelos)
        self.pedidos = []
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

            def do_GET(self):
                if self.path == "/api/tags":
                    self._json({"models": [{"name": m} for m in falso.modelos]})
                else:
                    self._json({"error": "no"}, 404)

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                cuerpo = json.loads(self.rfile.read(n) or b"{}")
                falso.pedidos.append(cuerpo)
                if cuerpo.get("model") not in falso.modelos:
                    self._json({"error": f"model '{cuerpo.get('model')}' not found"}, 404)
                    return
                if demora:
                    import time
                    time.sleep(demora)
                texto = falso.responder(cuerpo)
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson")
                self.end_headers()
                trozos = [texto[i:i + 7] for i in range(0, len(texto), 7)] or [""]
                for tr in trozos:
                    self.wfile.write((json.dumps({"message": {"role": "assistant", "content": tr},
                                                  "done": False}) + "\n").encode())
                self.wfile.write((json.dumps({"message": {"role": "assistant", "content": ""}, "done": True,
                                              "eval_count": len(trozos)}) + "\n").encode())

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def cerrar(self):
        self.srv.shutdown()
        self.srv.server_close()

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        self.cerrar()

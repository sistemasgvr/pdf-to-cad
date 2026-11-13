"""Crea/actualiza las etiquetas de GitHub Issues (tipo, área, prioridad) con la API REST. Necesita un token en
GITHUB_TOKEN (fine-grained, permiso «Issues: Read and write» sobre el repo). Sin dependencias."""
from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request

ETIQUETAS = [
    # tipo
    ("observación-cliente", "d93f0b", "Viene de una observación del cliente (PDF, reunión, WhatsApp)"),
    ("bug", "d73a4a", "Algo que funcionaba mal o dejó de funcionar"),
    ("mejora", "a2eeef", "Mejora o función nueva"),
    ("consulta", "d4c5f9", "Pregunta que hay que responder"),
    # área
    ("área: app", "1d76db", "Aplicación de escritorio"),
    ("área: reconocimiento", "0e8a16", "Reconocimiento automático del PDF (Santos)"),
    ("área: plugin", "5319e7", "Plugin de Civil 3D"),
    ("área: piezas 3D", "fbca04", "Sólidos de piezas automáticas (Jean)"),
    ("área: laminado", "c2e0c6", "Laminado del modelo 3D (Elvis)"),
    ("área: IA / MCP", "bfdadc", "Asistente IA y conexión con Civil 3D"),
    ("área: instalador", "6f42c1", "Instalador y actualización"),
    # prioridad / seguimiento
    ("prioridad: alta", "b60205", "Bloquea al cliente"),
    ("falta responder", "e99695", "El cliente espera una respuesta"),
    ("por probar", "f9d0c4", "Hecho, falta probar antes de entregar"),
]


def repo_de_git():
    url = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True).stdout.strip()
    url = url.removesuffix(".git")
    return "/".join(url.replace(":", "/").split("/")[-2:])


def _api(metodo, ruta, token, cuerpo=None):
    req = urllib.request.Request(f"https://api.github.com{ruta}", method=metodo,
                                 data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
                                 headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                          "User-Agent": "gestion-proyecto"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or b"null")


def crear_etiquetas(repo=None, token=None, al_texto=print):
    token = token or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("Falta GITHUB_TOKEN (token de GitHub con permiso de Issues sobre el repo).")
    repo = repo or repo_de_git()
    for nombre, color, desc in ETIQUETAS:
        cuerpo = {"name": nombre, "color": color, "description": desc}
        try:
            _api("POST", f"/repos/{repo}/labels", token, cuerpo)
            al_texto(f"  + {nombre}")
        except urllib.error.HTTPError as e:
            if e.code != 422:                       # 422 = ya existe → se actualiza
                raise
            _api("PATCH", f"/repos/{repo}/labels/{urllib.parse.quote(nombre)}", token, cuerpo)
            al_texto(f"  = {nombre}")

"""Cliente MCP de Civil 3D (PURO, solo la biblioteca estándar).

Lanza `PdfCadMcp.exe` (el host MCP del plugin, `API-CIVIL/proyecto1/PdfCadMcp`) y habla con él por stdio
(JSON-RPC 2.0, una línea por mensaje): `herramientas()` = el catálogo del perfil, `llamar(nombre, args)` =
lo que devuelve el plugin. Es la ENTRADA 1 (la app con la IA local); Claude Code/Desktop usa el mismo .exe
(entrada 2). Las reglas (perfil, validación, propuesta → confirmación, registro) viven en el plugin, no aquí.

Ruta del .exe: `PDFCAD_MCP_EXE`, junto al .exe de la app (`PdfCadMcp/`) o la compilación del repo.
"""
from __future__ import annotations

import itertools
import json
import os
import subprocess
import sys
import threading

from traduccion.i18n_core import t

PERFIL_BASICO, PERFIL_COMPLETO = "basico", "completo"
VERSION_MCP = "2025-06-18"
ESPERA_S = 150                                       # el plugin espera a Civil 3D hasta 2 min

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_COMPILADO = os.path.join(_RAIZ, "API-CIVIL", "proyecto1", "PdfCadMcp", "bin", "Release", "net8.0", "PdfCadMcp.exe")


class ErrorMCP(Exception):
    """El host MCP no arrancó o no respondió (no es un error de Civil 3D: ese vuelve en el resultado)."""


def ruta_exe():
    """Dónde está PdfCadMcp.exe, o "" si no se encuentra."""
    candidatas = [os.environ.get("PDFCAD_MCP_EXE", "")]
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        candidatas += [os.path.join(base, "PdfCadMcp", "PdfCadMcp.exe"),
                       os.path.join(os.path.dirname(sys.executable), "PdfCadMcp", "PdfCadMcp.exe")]
    candidatas.append(_COMPILADO)
    return next((c for c in candidatas if c and os.path.isfile(c)), "")


class ClienteMCP:
    """Un host MCP vivo. Usar con `with` o `cerrar()`. Seguro entre hilos (un pedido a la vez)."""

    def __init__(self, exe=None, perfil=PERFIL_BASICO, origen="qwen"):
        self.exe = exe or ruta_exe()
        if not self.exe:
            raise ErrorMCP(t("No se encontró PdfCadMcp.exe (conexión de la IA con Civil 3D)."))
        crear = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self._p = subprocess.Popen([self.exe, "--perfil", perfil, "--origen", origen],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                       creationflags=crear)
        except OSError as e:
            raise ErrorMCP(t("No se pudo iniciar PdfCadMcp.exe: {e}").format(e=e)) from e
        self._ids = itertools.count(1)
        self._cerrojo = threading.Lock()
        self._herramientas = None
        self.instrucciones = ""
        r = self._rpc("initialize", {"protocolVersion": VERSION_MCP, "capabilities": {},
                                     "clientInfo": {"name": "pdf-to-cad", "version": "1"}})
        self.instrucciones = r.get("instructions", "")
        self._enviar({"jsonrpc": "2.0", "method": "notifications/initialized"})

    # ------------------------------------------------------------------ protocolo

    def _enviar(self, msg):
        try:
            self._p.stdin.write((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
            self._p.stdin.flush()
        except (OSError, ValueError) as e:
            raise ErrorMCP(t("Se cortó la conexión con PdfCadMcp.exe.")) from e

    def _rpc(self, metodo, params=None):
        with self._cerrojo:
            mid = next(self._ids)
            self._enviar({"jsonrpc": "2.0", "id": mid, "method": metodo, "params": params or {}})
            linea = _leer_linea(self._p.stdout, ESPERA_S)
            if not linea:
                raise ErrorMCP(t("Se cortó la conexión con PdfCadMcp.exe."))
            r = json.loads(linea.decode("utf-8"))
            if "error" in r:
                raise ErrorMCP(r["error"].get("message", "?"))
            return r.get("result") or {}

    # ------------------------------------------------------------------ uso

    def herramientas(self):
        """[{name, description, inputSchema, annotations}] (se pide una vez)."""
        if self._herramientas is None:
            self._herramientas = self._rpc("tools/list").get("tools", [])
        return self._herramientas

    def llamar(self, nombre, args=None):
        """(ok, texto). `texto` = JSON compacto del plugin, o el error explicado (p. ej. Civil 3D sin conectar)."""
        r = self._rpc("tools/call", {"name": nombre, "arguments": args or {}})
        texto = "".join(c.get("text", "") for c in r.get("content", []) if c.get("type") == "text")
        return not r.get("isError", False), texto

    def cerrar(self):
        try:
            self._p.stdin.close()
            self._p.wait(3)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            self._p.kill()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.cerrar()


def _leer_linea(flujo, espera):
    """readline con tope de tiempo (un hilo: en Windows no hay select sobre tuberías)."""
    caja = []
    hilo = threading.Thread(target=lambda: caja.append(flujo.readline()), daemon=True)
    hilo.start()
    hilo.join(espera)
    if hilo.is_alive():
        raise ErrorMCP(t("PdfCadMcp.exe no respondió a tiempo."))
    return caja[0] if caja else b""

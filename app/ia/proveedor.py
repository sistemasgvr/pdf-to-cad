"""Quién responde (PURO, solo la biblioteca estándar: sin dependencias nuevas en el .exe).

`Config` = proveedor, url y modelo (QSettings «pdf-to-cad»/«app», claves `ia/*`). `crear(config)` da un
`Proveedor` o None («plantilla» = sin IA). Un proveedor sabe:
  - `chat(mensajes, sistema=, json=, al_texto=, maximo=)` → `Respuesta` (con `al_texto` va llegando el texto
    mientras se genera: la ventana lo muestra al momento);
  - `modelos()` → los modelos instalados; `probar()` → (ok, mensaje).

Para Claude: escribir `Anthropic(Proveedor)` con la misma interfaz (Messages API) y sumarlo a `PROVEEDORES`;
nada más de la app cambia (ver `docs/pendientes_ia.md`).
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from traduccion.i18n_core import t

PLANTILLA, OLLAMA, ANTHROPIC = "plantilla", "ollama", "anthropic"
URL_OLLAMA = "http://100.64.200.58:11434"            # «localollama» en la red Tailscale de la oficina
MODELO_OLLAMA = "qwen3-vl:8b"
ESPERA_S = 180                                       # tope por respuesta (el modelo puede estar cargándose)
CONTEXTO_TOKENS = 16384                              # ventana de contexto pedida a Ollama (cabe en 8 GB)
_PENSAR = re.compile(r"<think>.*?</think>\s*", re.S)


class ErrorIA(Exception):
    """La IA no respondió (red, servidor, modelo): quien llama usa la plantilla."""


@dataclass
class Config:
    proveedor: str = PLANTILLA
    url: str = URL_OLLAMA
    modelo: str = MODELO_OLLAMA
    paralelo: int = 2                                # pedidos a la vez al redactar el informe
    temperatura: float = 0.2

    @classmethod
    def de(cls, d):
        d = dict(d or {})
        c = cls()
        c.proveedor = (str(d.get("proveedor") or PLANTILLA)).strip().lower()
        c.url = (str(d.get("url") or URL_OLLAMA)).strip().rstrip("/")
        c.modelo = (str(d.get("modelo") or MODELO_OLLAMA)).strip()
        try:
            c.paralelo = max(1, min(8, int(d.get("paralelo") or 2)))
        except (TypeError, ValueError):
            c.paralelo = 2
        return c

    @property
    def con_ia(self):
        return self.proveedor != PLANTILLA


@dataclass
class Respuesta:
    texto: str
    segundos: float = 0.0
    tokens: int = 0
    modelo: str = ""
    extra: dict = field(default_factory=dict)


class Proveedor:
    """Interfaz común. `mensajes` = [{"role": "user"|"assistant", "content": str}, …]."""
    nombre = "base"

    def __init__(self, config: Config):
        self.config = config

    def chat(self, mensajes, sistema="", json=False, al_texto=None, maximo=None, cancelado=None) -> Respuesta:
        raise NotImplementedError

    def modelos(self):
        return []

    def probar(self):
        try:
            r = self.chat([{"role": "user", "content": "Responde solo: OK"}], maximo=20)
        except ErrorIA as e:
            return False, str(e)
        return True, t("Responde en {s} s con «{m}».").format(s=f"{r.segundos:.1f}", m=r.modelo or self.config.modelo)


class Ollama(Proveedor):
    """Servidor Ollama (https://github.com/ollama/ollama/blob/main/docs/api.md): /api/chat y /api/tags."""
    nombre = OLLAMA

    def _pedir(self, ruta, cuerpo=None, espera=ESPERA_S):
        datos = None if cuerpo is None else json.dumps(cuerpo).encode("utf-8")
        req = urllib.request.Request(self.config.url + ruta, data=datos,
                                     headers={"Content-Type": "application/json"})
        try:
            return urllib.request.urlopen(req, timeout=espera)   # noqa: S310 (URL de la configuración)
        except urllib.error.HTTPError as e:
            detalle = e.read().decode("utf-8", "replace")[:300]
            raise ErrorIA(t("El servidor de IA respondió {c}: {d}").format(c=e.code, d=detalle)) from e
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            raise ErrorIA(t("No se pudo conectar con el servidor de IA ({u}): {e}").format(
                u=self.config.url, e=getattr(e, "reason", e))) from e

    def modelos(self):
        with self._pedir("/api/tags", espera=10) as r:
            return [m.get("name", "") for m in json.loads(r.read().decode("utf-8")).get("models", [])]

    def chat(self, mensajes, sistema="", json=False, al_texto=None, maximo=None, cancelado=None):
        msgs = ([{"role": "system", "content": sistema}] if sistema else []) + list(mensajes)
        opciones = {"temperature": self.config.temperatura, "num_ctx": CONTEXTO_TOKENS}
        if maximo:
            opciones["num_predict"] = int(maximo)
        cuerpo = {"model": self.config.modelo, "messages": msgs, "stream": True, "think": False,
                  "keep_alive": "30m", "options": opciones}
        if json:
            cuerpo["format"] = "json"
        t0 = time.perf_counter()
        partes, tokens = [], 0
        with self._pedir("/api/chat", cuerpo) as r:
            for linea in r:                              # una línea JSON por trozo (NDJSON)
                if cancelado is not None and cancelado():
                    break
                if not linea.strip():
                    continue
                try:
                    d = _json_loads(linea)
                except ValueError:
                    continue
                if d.get("error"):
                    raise ErrorIA(str(d["error"]))
                trozo = (d.get("message") or {}).get("content") or ""
                if trozo:
                    partes.append(trozo)
                    if al_texto is not None:
                        al_texto(trozo)
                if d.get("done"):
                    tokens = int(d.get("eval_count") or 0)
                    break
        texto = _PENSAR.sub("", "".join(partes)).strip()
        return Respuesta(texto, time.perf_counter() - t0, tokens, self.config.modelo)


def _json_loads(linea):
    return json.loads(linea.decode("utf-8") if isinstance(linea, bytes) else linea)


PROVEEDORES = {OLLAMA: Ollama}


def crear(config) -> Proveedor | None:
    """El proveedor de `config` (Config o dict), o None si es «plantilla» o no existe todavía."""
    c = config if isinstance(config, Config) else Config.de(config)
    cls = PROVEEDORES.get(c.proveedor)
    return cls(c) if cls else None

"""Gemini de Google como proveedor de la IA (PURO, solo la biblioteca estándar; pedido del usuario 2026-11-11).

Misma interfaz que `Ollama` (`ia/proveedor.Proveedor`): el resto de la app no cambia. API REST v1beta
(https://ai.google.dev/api): `models/{m}:streamGenerateContent?alt=sse` (texto en vivo), `models/{m}:generateContent`
(herramientas, mensaje entero) y `models` (lista para «Buscar modelos»). La clave va en la cabecera `x-goog-api-key`,
NUNCA en la URL (la URL sale en los reportes de error).

Traducción de los mensajes de la app (formato Ollama) a los de Gemini (`contenidos`):
  - rol «assistant» → «model»; «system» → `systemInstruction`; turnos seguidos del mismo rol se juntan.
  - `images` (png/jpg en base64) → partes `inlineData`.
  - `tool_calls` del modelo → partes `functionCall` (se devuelve la parte ORIGINAL, `_parte`: los modelos que piensan
    exigen su `thoughtSignature` en el turno siguiente) y rol «tool» → parte `functionResponse` en un turno «user».
"""
from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request

from ia.proveedor import ErrorIA, Proveedor, Respuesta, _PENSAR
from traduccion.i18n_core import t

GEMINI = "gemini"
URL_GEMINI = "https://generativelanguage.googleapis.com/v1beta"
MODELO_GEMINI = "gemini-3.5-flash"   # medido 2026-11-11: la familia 2.5 ya no se da a cuentas nuevas (404)
ESPERA_GEMINI_S = 60                # sin respuesta en este tiempo = saturado (3.7/3.8 colgaban minutos)
ESPERA_PROBAR_S = 20                # «Probar»: una respuesta corta
REINTENTO_S = 1.5                   # 503 «high demand»: un reintento tras esta pausa
MARGEN_PENSAR = 2048                 # tokens de más cuando el modelo piensa: lo pensado cuenta en maxOutputTokens
_NO_CHAT = ("embedding", "aqa", "tts", "-image", "imagen", "veo", "native-audio", "live", "computer-use")


def _mime(b64):
    return "image/jpeg" if str(b64).startswith("/9j/") else "image/png"


def _pensar(modelo, maximo):
    """`generationConfig` según el modelo: la app pide respuestas rápidas (como `think: false` en Ollama). 2.5 Flash
    deja apagar el pensamiento; 2.5 Pro no (presupuesto mínimo); 3.x por nivel. Devuelve (thinkingConfig, maxOutput)."""
    m = (modelo or "").lower()
    if m.startswith("gemini-2.5") and "flash" in m:
        return {"thinkingBudget": 0}, maximo
    if m.startswith("gemini-2.5"):
        return {"thinkingBudget": 128}, (maximo + MARGEN_PENSAR) if maximo else None
    if m.startswith("gemini-3"):
        return {"thinkingLevel": "low"}, (maximo + MARGEN_PENSAR) if maximo else None
    return None, maximo


def contenidos(mensajes, sistema=""):
    """(systemInstruction o None, contents) de Gemini desde los mensajes de la app."""
    sis = [sistema] if sistema else []
    out = []

    def poner(rol, partes):
        if not partes:
            return
        if out and out[-1]["role"] == rol:
            out[-1]["parts"].extend(partes)
        else:
            out.append({"role": rol, "parts": list(partes)})

    for m in mensajes:
        rol = m.get("role")
        texto = m.get("content") or ""
        imagenes = [{"inlineData": {"mimeType": _mime(b), "data": b}} for b in m.get("images") or ()]
        if rol == "system":
            if texto:
                sis.append(texto)
        elif rol == "assistant":
            partes = [{"text": texto}] if texto else []
            for c in m.get("tool_calls") or ():
                parte = c.get("_parte")
                if parte is None:
                    f = c.get("function") or {}
                    args = f.get("arguments")
                    if isinstance(args, str):
                        try:
                            args = json.loads(args) if args else {}
                        except ValueError:
                            args = {}
                    parte = {"functionCall": {"name": f.get("name", ""), "args": args or {}}}
                partes.append(parte)
            poner("model", partes)
        elif rol == "tool":
            resp = {"functionResponse": {"name": m.get("tool_name") or m.get("name") or "",
                                         "response": {"content": texto}}}
            poner("user", [resp] + imagenes)
        else:
            poner("user", ([{"text": texto}] if texto else []) + imagenes)
    instr = {"parts": [{"text": "\n\n".join(sis)}]} if sis else None
    return instr, out


def herramientas_gemini(herramientas):
    """Herramientas de la app (formato Ollama/OpenAI) → `tools` de Gemini (esquema JSON tal cual)."""
    decl = []
    for h in herramientas or ():
        f = h.get("function") or h
        d = {"name": f.get("name", ""), "description": f.get("description", "")}
        if f.get("parameters"):
            d["parametersJsonSchema"] = f["parameters"]
        decl.append(d)
    return [{"functionDeclarations": decl}] if decl else []


def _partes(datos):
    cands = datos.get("candidates") or []
    return ((cands[0].get("content") or {}).get("parts") or []) if cands else []


def _texto(partes):
    return "".join(p.get("text", "") for p in partes if p.get("text") and not p.get("thought"))


def _bloqueo(datos):
    """Motivo si Gemini no respondió por sus filtros (sin candidatos o cortado), si no ""."""
    pf = datos.get("promptFeedback") or {}
    if pf.get("blockReason"):
        return pf["blockReason"]
    cands = datos.get("candidates") or []
    if cands and cands[0].get("finishReason") in ("SAFETY", "RECITATION", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII"):
        return cands[0]["finishReason"]
    return ""


class Gemini(Proveedor):
    nombre = GEMINI

    espera_s = ESPERA_GEMINI_S

    def _agotado(self, url, espera, e=None):
        return ErrorIA(t("Gemini no respondió en {s} s: el modelo «{m}» puede estar saturado.").format(
            s=int(espera), m=self.config.modelo), detalle=f"timeout {int(espera)} s", url=url.split("?")[0],
            modelo=self.config.modelo)

    def _pedir(self, ruta, cuerpo=None, espera=None, reintento=True):
        espera = espera or self.espera_s
        clave = (self.config.clave or "").strip()
        url = URL_GEMINI + ruta
        if not clave:
            raise ErrorIA(t("Falta la clave de API de Gemini (Configurar IA…)."), detalle="API key missing",
                          url=url.split("?")[0], modelo=self.config.modelo)
        datos = None if cuerpo is None else json.dumps(cuerpo).encode("utf-8")
        req = urllib.request.Request(url, data=datos, headers={"Content-Type": "application/json",
                                                               "x-goog-api-key": clave})
        try:
            return urllib.request.urlopen(req, timeout=espera)   # noqa: S310 (URL fija de Google)
        except urllib.error.HTTPError as e:
            if e.code == 503 and reintento:              # «high demand»: suele pasar en segundos
                time.sleep(REINTENTO_S)
                return self._pedir(ruta, cuerpo, espera, reintento=False)
            crudo = e.read().decode("utf-8", "replace")
            try:
                err = json.loads(crudo).get("error") or {}
                detalle = f"{err.get('status', '')} {err.get('message', '')}".strip()[:300]
            except ValueError:
                detalle = crudo[:300]
            raise ErrorIA(t("Gemini respondió {c}: {d}").format(c=e.code, d=detalle), codigo_http=e.code,
                          detalle=detalle, url=url.split("?")[0], modelo=self.config.modelo) from e
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            if _es_tiempo(e):
                raise self._agotado(url, espera, e) from e
            raise ErrorIA(t("No se pudo conectar con Gemini: {e}").format(e=getattr(e, "reason", e)),
                          detalle=str(getattr(e, "reason", e)), url=url.split("?")[0],
                          modelo=self.config.modelo) from e

    def modelos(self):
        nombres, pagina = [], ""
        for _ in range(20):
            ruta = "/models?pageSize=1000" + (f"&pageToken={pagina}" if pagina else "")
            with self._pedir(ruta, espera=15) as r:
                d = json.loads(r.read().decode("utf-8"))
            for m in d.get("models") or ():
                n = (m.get("name") or "").removeprefix("models/")
                if ("generateContent" in (m.get("supportedGenerationMethods") or ())
                        and not any(x in n for x in _NO_CHAT)):
                    nombres.append(n)
            pagina = d.get("nextPageToken") or ""
            if not pagina:
                break
        # el recomendado primero, luego los Gemini estables (sin «preview»/«exp») y el resto
        return sorted(nombres, key=lambda n: (n != MODELO_GEMINI, not n.startswith("gemini"),
                                              "preview" in n or "exp" in n, n))

    def probar(self):
        self.espera_s = ESPERA_PROBAR_S
        try:
            return super().probar()
        finally:
            self.espera_s = ESPERA_GEMINI_S

    def vision(self):
        return True                                      # los Gemini y Gemma de la API aceptan imágenes

    def herramientas(self):
        return (self.config.modelo or "").startswith("gemini")

    def _cuerpo(self, mensajes, sistema="", json_=False, maximo=None, herramientas=None):
        instr, conts = contenidos(mensajes, sistema)
        pensar, max_out = _pensar(self.config.modelo, int(maximo) if maximo else None)
        gen = {"temperature": self.config.temperatura}
        if max_out:
            gen["maxOutputTokens"] = int(max_out)
        if pensar:
            gen["thinkingConfig"] = pensar
        if json_:
            gen["responseMimeType"] = "application/json"
        cuerpo = {"contents": conts, "generationConfig": gen}
        if instr:
            cuerpo["systemInstruction"] = instr
        tools = herramientas_gemini(herramientas)
        if tools:
            cuerpo["tools"] = tools
        return cuerpo

    def chat(self, mensajes, sistema="", json=False, al_texto=None, maximo=None, cancelado=None):
        cuerpo = self._cuerpo(mensajes, sistema, json, maximo)
        t0 = time.perf_counter()
        partes, tokens, motivo = [], 0, ""
        ruta = f"/models/{self.config.modelo}:streamGenerateContent?alt=sse"
        with self._pedir(ruta, cuerpo) as r:
            for linea in _lineas(r, lambda e: self._agotado(URL_GEMINI + ruta, self.espera_s, e)):  # SSE «data:»
                if cancelado is not None and cancelado():
                    break
                linea = linea.decode("utf-8", "replace").strip() if isinstance(linea, bytes) else linea.strip()
                if not linea.startswith("data:"):
                    continue
                try:
                    d = _json_mod.loads(linea[5:].strip())
                except ValueError:
                    continue
                if d.get("error"):
                    raise ErrorIA(str(d["error"].get("message") or d["error"]), modelo=self.config.modelo)
                motivo = _bloqueo(d) or motivo
                trozo = _texto(_partes(d))
                if trozo:
                    partes.append(trozo)
                    if al_texto is not None:
                        al_texto(trozo)
                uso = d.get("usageMetadata") or {}
                tokens = int(uso.get("candidatesTokenCount") or tokens)
        texto = _PENSAR.sub("", "".join(partes)).strip()
        if not texto and motivo:
            raise ErrorIA(t("Gemini no respondió por sus filtros de contenido ({m}).").format(m=motivo),
                          detalle=motivo, modelo=self.config.modelo)
        return Respuesta(texto, time.perf_counter() - t0, tokens, self.config.modelo)

    def pedir_con_herramientas(self, mensajes, herramientas):
        """Para los agentes (`civil3d_agente`): un paso con `tools`, sin streaming. Devuelve el mensaje en el formato
        de Ollama: {"role", "content", "tool_calls": [{"function": {"name", "arguments"}, "_parte"}]}."""
        cuerpo = self._cuerpo(mensajes, herramientas=herramientas)
        ruta = f"/models/{self.config.modelo}:generateContent"
        with self._pedir(ruta, cuerpo) as r:
            try:
                d = _json_mod.loads(r.read().decode("utf-8"))
            except (TimeoutError, socket.timeout, OSError) as e:
                if _es_tiempo(e):
                    raise self._agotado(URL_GEMINI + ruta, self.espera_s, e) from e
                raise
        partes = _partes(d)
        llamadas = [{"function": {"name": p["functionCall"].get("name", ""),
                                  "arguments": p["functionCall"].get("args") or {}}, "_parte": p}
                    for p in partes if p.get("functionCall")]
        texto = _texto(partes)
        if not texto and not llamadas and _bloqueo(d):
            raise ErrorIA(t("Gemini no respondió por sus filtros de contenido ({m}).").format(m=_bloqueo(d)),
                          detalle=_bloqueo(d), modelo=self.config.modelo)
        return {"role": "assistant", "content": texto, "tool_calls": llamadas}


def _es_tiempo(e):
    razon = getattr(e, "reason", e)
    return isinstance(e, (TimeoutError, socket.timeout)) or isinstance(razon, (TimeoutError, socket.timeout))         or "timed out" in str(razon).lower()


def _lineas(r, agotado):
    """Las líneas de la respuesta; un corte por tiempo a mitad del texto = `agotado(e)` (ErrorIA)."""
    try:
        yield from r
    except (TimeoutError, socket.timeout, OSError) as e:
        if _es_tiempo(e):
            raise agotado(e) from e
        raise


_json_mod = json                                         # `chat` tiene un parámetro llamado `json`

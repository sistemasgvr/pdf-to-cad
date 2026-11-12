"""Reporte de un error de la IA para el usuario final y para el desarrollador (pedido del usuario 2026-11-06). PURO.

El usuario ve: un título claro, qué pasó en palabras simples, qué hacer y el pedido de tomar una CAPTURA y enviarla
al equipo de desarrollo; debajo, los DETALLES técnicos (código de referencia, hora, dónde, versión de la app, modelo,
servidor, respuesta HTTP, tipo y mensaje del error, dónde saltó en el código, herramientas consultadas, la pregunta).
Con la captura basta para revisarlo; además queda escrito en el registro de diagnóstico de la sesión
(`nucleo/diagnostico`, `%LOCALAPPDATA%/pdf-to-cad/diagnosticos/`) con el mismo código y la pila completa.
"""
from __future__ import annotations

import datetime
import hashlib
import re
import traceback
from dataclasses import dataclass, field

from traduccion.i18n_core import N_, t

LARGO_MENSAJE = 600            # caracteres del mensaje del error en la tarjeta (el registro lo guarda entero)
LARGO_PREGUNTA = 200


@dataclass
class Reporte:
    codigo: str
    titulo: str
    explicacion: str
    que_hacer: str
    detalles: list = field(default_factory=list)       # [(etiqueta, valor)]
    registro: str = ""                                 # archivo del registro de diagnóstico (o "")

    def texto(self):
        """Todo en texto plano (para «Copiar detalles» y el registro)."""
        lineas = [self.titulo, self.explicacion, t("Qué hacer: {q}").format(q=self.que_hacer), ""]
        lineas += [f"{k}: {v}" for k, v in self.detalles]
        return "\n".join(lineas)


# (patrón sobre el mensaje y lo que respondió el servidor, título, explicación, qué hacer). La primera que calza.
CAUSAS = (
    (r"no user query found|context.*(length|window)|too many tokens|exceeds.*context",
     N_("La conversación no cupo en la memoria de la IA"),
     N_("La conversación, con los datos que la IA consultó, era más larga de lo que el modelo puede leer de una vez, "
        "y se perdió la pregunta."),
     N_("Vuelve a preguntar con algo más concreto o empieza una conversación nueva.")),
    (r"api_key_invalid|api key not valid|api key expired|permission_denied|unauthenticated|"
     r"falta la clave de api de gemini|gemini respondió 40[13]|gemini responded 40[13]|gemini api key is missing",
     N_("La clave de Gemini no sirve"),
     N_("Google rechazó la clave de API: falta, está mal copiada, venció o se borró."),
     N_("Crea una clave en Google AI Studio y pégala en «Configurar IA…».")),
    (r"resource_exhausted|quota|rate limit|gemini respondió 429|gemini responded 429",
     N_("Se alcanzó el límite de Gemini"),
     N_("Tu cuenta de Gemini llegó al máximo de pedidos permitidos por minuto o por día."),
     N_("Espera un momento y vuelve a intentarlo, o baja «Pedidos a la vez» en «Configurar IA…».")),
    (r"no se pudo conectar con gemini|could not connect to gemini",
     N_("No se pudo conectar con Gemini"),
     N_("La app no pudo llegar a los servidores de Google."),
     N_("Revisa la conexión a internet y vuelve a intentarlo.")),
    (r"no longer available|gemini respondió 404|gemini responded 404",
     N_("Ese modelo de Gemini ya no está disponible"),
     N_("Google retiró el modelo elegido o no lo da a cuentas nuevas."),
     N_("En «Configurar IA…» pulsa «Buscar modelos» y elige otro (el primero de la lista es el recomendado).")),
    (r"high demand|gemini respondió 503|gemini responded 503|gemini no respondió en|gemini did not respond in",
     N_("Gemini está saturado"),
     N_("El modelo elegido tiene mucha demanda ahora y no respondió."),
     N_("Espera un momento o elige otro modelo en «Configurar IA…».")),
    (r"model .*not found|model .*not exist|pull the model|\b404\b",
     N_("El modelo de IA no está instalado"),
     N_("El servidor de IA no tiene el modelo elegido."),
     N_("Instálalo en Ollama o elige otro modelo en «Configurar IA…».")),
    (r"out of memory|requires more system memory|cuda error|insufficient memory|not enough memory",
     N_("La IA se quedó sin memoria"),
     N_("El equipo no tiene memoria libre suficiente para el modelo de IA."),
     N_("Cierra otros programas o elige un modelo más chico en «Configurar IA…».")),
    (r"timed out|timeout|tiempo de espera",
     N_("La IA tardó demasiado en responder"),
     N_("El servidor de IA no respondió a tiempo (puede estar cargando el modelo o muy ocupado)."),
     N_("Espera unos segundos y vuelve a intentarlo.")),
    (r"no se pudo conectar con el servidor de ia|connection refused|actively refused|denegó|urlopen error|"
     r"getaddrinfo|winerror 10061",
     N_("No se pudo conectar con la IA local"),
     N_("El servidor de IA (Ollama) no respondió en la dirección configurada."),
     N_("Revisa que Ollama esté abierto y la dirección en «Configurar IA…».")),
    (r"pdfcadmcp|civil 3d|pdfcad_ia",
     N_("Se cortó la conexión con Civil 3D"),
     N_("La app no pudo hablar con Civil 3D a través de su conexión de IA."),
     N_("En Civil 3D, revisa que la conexión de la IA (PDFCAD_IA) esté encendida y vuelve a intentarlo.")),
)
GENERICO = (N_("Algo salió mal"), N_("Ocurrió un error inesperado."),
            N_("Vuelve a intentarlo. Si se repite, avisa al equipo de desarrollo."))


def _causa(texto):
    bajo = texto.lower()
    for patron, titulo, explicacion, que in CAUSAS:
        if re.search(patron, bajo):
            return titulo, explicacion, que
    return GENERICO


def _donde_salto(error):
    """«archivo.py:línea en función» del último marco de la pila (o "")."""
    tb = getattr(error, "__traceback__", None)
    if tb is None:
        return ""
    marcos = traceback.extract_tb(tb)
    if not marcos:
        return ""
    m = marcos[-1]
    archivo = re.split(r"[\\/]", m.filename)[-1]
    return f"{archivo}:{m.lineno} ({m.name})"


def _version():
    try:
        from nucleo.model import VERSION
        return VERSION
    except Exception:                                   # noqa: BLE001 (el reporte nunca falla)
        return "?"


def armar(error, donde, modelo="", servidor="", pregunta="", pasos=(), ahora=None, registrar=True):
    """El reporte de `error` (excepción o texto) que pasó en `donde` (p. ej. «Chat Civil 3D»)."""
    ahora = ahora or datetime.datetime.now()
    if isinstance(error, BaseException):
        tipo, mensaje = type(error).__name__, str(error)
    else:
        tipo, mensaje = "", str(error)
    http = getattr(error, "codigo_http", None)
    detalle = getattr(error, "detalle", "") or ""
    url = getattr(error, "url", "") or servidor
    modelo = getattr(error, "modelo", "") or modelo
    titulo, explicacion, que = _causa(mensaje + " " + detalle)
    huella = hashlib.sha1(f"{tipo}|{mensaje}".encode("utf-8", "replace")).hexdigest()[:4].upper()
    codigo = f"E-{ahora:%y%m%d-%H%M%S}-{huella}"
    detalles = [(t("Código"), codigo), (t("Fecha y hora"), f"{ahora:%Y-%m-%d %H:%M:%S}"), (t("Dónde"), donde),
                (t("Versión de la app"), _version())]
    if modelo:
        detalles.append((t("Modelo"), modelo))
    if url:
        detalles.append((t("Servidor"), url))
    if http:
        detalles.append((t("Respuesta del servidor"), f"HTTP {http}" + (f" · {detalle}" if detalle else "")))
    if tipo:
        detalles.append((t("Tipo de error"), tipo))
    corto = mensaje if len(mensaje) <= LARGO_MENSAJE else mensaje[:LARGO_MENSAJE] + "…"
    detalles.append((t("Mensaje"), corto or "—"))
    lugar = _donde_salto(error)
    if lugar:
        detalles.append((t("En el código"), lugar))
    pasos = [p for p in pasos or () if p]
    if pasos:
        detalles.append((t("Consultó"), ", ".join(dict.fromkeys(pasos))))
    if pregunta:
        q = " ".join(str(pregunta).split())
        detalles.append((t("Pregunta"), q if len(q) <= LARGO_PREGUNTA else q[:LARGO_PREGUNTA] + "…"))
    rep = Reporte(codigo, t(titulo), t(explicacion), t(que), detalles)
    if registrar:
        rep.registro = _registrar(rep, error)
    return rep


def _registrar(rep, error):
    """El reporte (y la pila completa si hay excepción) al registro de diagnóstico de la sesión."""
    try:
        from nucleo import diagnostico
        pila = ""
        if isinstance(error, BaseException) and error.__traceback__ is not None:
            pila = "\n" + "".join(traceback.format_exception(type(error), error, error.__traceback__))
        return diagnostico.registrar(rep.texto() + pila, f"Error de la IA {rep.codigo}") or ""
    except Exception:                                   # noqa: BLE001 (el reporte nunca falla)
        return ""


def texto_corto(rep):
    """Una línea para los lugares que solo muestran texto: «Título: qué pasó (código E-…)»."""
    return t("{titulo}: {explicacion} Código {codigo}.").format(titulo=rep.titulo, explicacion=rep.explicacion,
                                                               codigo=rep.codigo)

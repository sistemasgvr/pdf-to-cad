"""«¿Cómo hago…?» en Ayuda → Manual de usuario (PURO). Pedido del usuario 2026-10-23: un campo para preguntarle a
la IA cómo hacer cualquier cosa en el programa, con respuesta RÁPIDA.

Para que sea rápida no se manda el manual entero (~25 mil tokens): se parte en trozos por capítulo y subtítulo
(`trozos`) y se buscan los que vienen al caso con BM25 sobre raíces de palabras (`Indice.buscar`, ~1 ms; el índice
se arma una vez por idioma y manual). La IA recibe solo esos trozos (≤ `MAX_CONTEXTO` caracteres), responde en
pocos pasos (`MAXIMO_TOKENS`) y la respuesta se GUARDA: la misma pregunta (normalizada) con el mismo manual sale al
instante (entrenamiento compartido de la IA, `ia.memoria`: sección «redaccion», ámbito «ayuda»). Los capítulos hallados
se muestran ANTES de que responda la IA (y sin IA, son la respuesta).
"""
from __future__ import annotations

import hashlib
import html
import json
import math
import re

from ia.consulta import idioma
from ia.memoria import Memoria
from ia.texto import normalizar, palabras, raiz
from traduccion.i18n_core import t

VERSION_PROMPT = 2
MAX_TROZO = 900                 # caracteres por trozo
MAX_CONTEXTO = 4800             # caracteres del manual que recibe la IA
K = 6                           # trozos como mucho
CANDIDATOS = 20                 # se eligen entre los mejores, como mucho `POR_CAPITULO` de cada capítulo
POR_CAPITULO = 2
PREFIJO = 5                     # raíz = las primeras letras: «dibujo» encuentra «dibujar», «exporto» a «exportar»
MAXIMO_TOKENS = 450
_K1, _B = 1.4, 0.75
# palabras de la PREGUNTA que no dicen de qué trata («¿cómo puedo hacer…?»)
_VACIAS = frozenset("hago hacer hace puedo puede quiero quisiera necesito debo forma manera pasos paso usar uso "
                    "programa app aplicacion favor ayuda cosa algun alguna hacerlo como do can i want need use "
                    "the app program way steps".split())

SISTEMA = """Eres la ayuda de PDF-a-CAD, una aplicación de escritorio para digitalizar planos PDF de redes de \
utilidades y exportarlos a Civil 3D. Respondes en {idioma} a usuarios que no son expertos.
Reglas:
1. Usa SOLO los fragmentos del manual que recibes. No inventes menús, botones ni atajos.
2. Si los fragmentos no dicen cómo hacerlo, dilo en una frase y sugiere el capítulo más cercano.
3. Si el manual da VARIAS formas de hacerlo (en el plano y su panel, en la Vista 3D, en la Tabla de datos o Excel…), nómbralas todas, primero la del plano, cada una con su capítulo.
4. Respuesta breve: una frase y luego pasos numerados (máximo 8), con los nombres de menús y botones tal cual \
aparecen en **negrita**. Al final: «Más en: <capítulo>»."""

_SECCION = re.compile(r'<section\s+data-title="([^"]+)"\s*>(.*?)</section>', re.S)
_TITULO = re.compile(r"<h[234][^>]*>(.*?)</h[234]>", re.S)
_BLOQUE = re.compile(r"</(?:p|li|h[1-6]|tr|div|ol|ul|table)>|<br\s*/?>", re.I)
_ETIQUETA = re.compile(r"<[^>]+>")
_CELDA = re.compile(r"</t[dh]>(?=\s*<t[dh])", re.I)
_ESTILO = re.compile(r"<style>.*?</style>", re.S)
_indices = {}
_memorias = {}


def _texto(fragmento):
    s = _CELDA.sub(": ", fragmento)               # «Elevación inicial / final: Cota del fondo…», no pegadas
    s = _BLOQUE.sub("\n", s)
    s = html.unescape(_ETIQUETA.sub("", s))
    s = re.sub(r"\{\{[a-z_]+\}\}", "", s)
    lineas = [" ".join(x.split()) for x in s.split("\n")]
    return "\n".join(x for x in lineas if x)


def trozos(doc):
    """[(n.º de capítulo (0…), capítulo, subtítulo, texto)] del manual en HTML."""
    out = []
    for n, m in enumerate(_SECCION.finditer(_ESTILO.sub("", doc))):
        cap, cuerpo = m.group(1), m.group(2)
        partes = _TITULO.split(cuerpo)            # [antes, título1, cuerpo1, título2, cuerpo2…]
        bloques = [("", partes[0])] + [(_texto(partes[i]), partes[i + 1]) for i in range(1, len(partes) - 1, 2)]
        for sub, frag in bloques:
            texto = _texto(frag)
            if not texto:
                continue
            actual = ""
            for linea in texto.split("\n"):
                if actual and len(actual) + len(linea) > MAX_TROZO:
                    out.append((n, cap, sub, actual))
                    actual = ""
                actual = (actual + "\n" + linea).strip()
            if actual:
                out.append((n, cap, sub, actual))
    return out


def _raices(texto, preguntar=False):
    ps = palabras(texto)
    if preguntar:
        ps = [p for p in ps if p not in _VACIAS]
    return [raiz(p)[:PREFIJO] for p in ps]


class Indice:
    """BM25 sobre los trozos del manual (el capítulo y el subtítulo pesan como el texto, repetidos)."""

    def __init__(self, doc):
        self.huella = hashlib.sha1(doc.encode("utf-8")).hexdigest()[:16]
        self.trozos = trozos(doc)
        self.tf, self.largo = [], []
        df = {}
        for _n, cap, sub, texto in self.trozos:
            rs = _raices(f"{cap} {cap} {sub} {sub} {texto}")
            tf = {}
            for r in rs:
                tf[r] = tf.get(r, 0) + 1
            self.tf.append(tf)
            self.largo.append(len(rs) or 1)
            for r in tf:
                df[r] = df.get(r, 0) + 1
        n = len(self.trozos) or 1
        self.idf = {r: math.log(1 + (n - d + 0.5) / (d + 0.5)) for r, d in df.items()}
        self.medio = sum(self.largo) / n if self.largo else 1.0

    def buscar(self, pregunta, k=K):
        """Los trozos que vienen al caso: [(puntaje, índice del trozo)], el mejor primero. Como mucho
        `POR_CAPITULO` por capítulo: si no, un capítulo con mucho de lo mismo (la Vista 3D) tapaba a otro que
        explica otra forma de hacerlo (el panel del plano)."""
        q = set(_raices(pregunta, preguntar=True))
        puntos = []
        for i, tf in enumerate(self.tf):
            s = 0.0
            for r in q:
                f = tf.get(r)
                if f:
                    s += self.idf[r] * f * (_K1 + 1) / (f + _K1 * (1 - _B + _B * self.largo[i] / self.medio))
            if s > 0:
                puntos.append((s, i))
        puntos.sort(key=lambda x: (-x[0], x[1]))
        if not puntos:
            return []
        tope = puntos[0][0] * 0.35                  # lo que apenas roza la pregunta no entra
        out, por_cap = [], {}
        for s, i in puntos[:CANDIDATOS]:
            n = self.trozos[i][0]
            if s < tope or por_cap.get(n, 0) >= POR_CAPITULO:
                continue
            por_cap[n] = por_cap.get(n, 0) + 1
            out.append((s, i))
            if len(out) >= k:
                break
        return out

    def contexto(self, hallados):
        """Texto para la IA (≤ MAX_CONTEXTO) y los capítulos usados [(n.º, título)] sin repetir."""
        partes, caps, total = [], [], 0
        for _s, i in hallados:
            n, cap, sub, texto = self.trozos[i]
            cab = f"[{cap}{' › ' + sub if sub else ''}]"
            bloque = cab + "\n" + texto
            queda = MAX_CONTEXTO - total
            if queda < 200:
                break
            bloque = bloque[:queda]                   # recortado, no saltado: cada capítulo hallado llega
            partes.append(bloque)
            total += len(bloque)
            if (n, cap) not in caps:
                caps.append((n, cap))
        return "\n\n".join(partes), caps

    def capitulos(self, pregunta):
        return self.contexto(self.buscar(pregunta))[1]


def indice(doc):
    h = hashlib.sha1(doc.encode("utf-8")).hexdigest()[:16]
    ix = _indices.get(h)
    if ix is None:
        ix = _indices[h] = Indice(doc)
    return ix


def memoria():
    from ia.memoria import ruta_archivo
    r = ruta_archivo()
    m = _memorias.get(r)
    if m is None:
        m = _memorias[r] = Memoria(ambito="ayuda")
    return m


def clave(ix, pregunta):
    q = " ".join(normalizar(pregunta).split()).strip(" ?¿!¡.")
    return hashlib.sha1(json.dumps(["ayuda", VERSION_PROMPT, idioma(), ix.huella, q],
                                   ensure_ascii=False).encode("utf-8")).hexdigest()


def guardada(ix, pregunta):
    return memoria().redaccion(clave(ix, pregunta))


def responder(proveedor, ix, pregunta, al_texto=None, cancelado=None):
    """(texto, origen, capítulos) con origen «memoria» o «ia». Lanza `ErrorIA` si la IA no responde."""
    contexto, caps = ix.contexto(ix.buscar(pregunta))
    k = clave(ix, pregunta)
    previa = memoria().redaccion(k)
    if previa:
        return previa, "memoria", caps
    if not contexto:
        return t("El manual no habla de eso. Prueba con otras palabras o mira el índice."), "manual", caps
    msg = t("Fragmentos del manual:") + "\n" + contexto + "\n\n" + t("Pregunta del usuario:") + " " + pregunta
    r = proveedor.chat([{"role": "user", "content": msg}], sistema=SISTEMA.format(idioma=idioma()),
                       al_texto=al_texto, maximo=MAXIMO_TOKENS, cancelado=cancelado)
    texto = r.texto.strip()
    if texto and not (cancelado and cancelado()):
        memoria().guardar_redaccion(k, texto, r.modelo)
    return texto, "ia", caps

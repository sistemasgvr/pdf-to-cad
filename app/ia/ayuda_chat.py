"""El chat también responde la AYUDA de la app (PURO). Pedido del usuario 2026-10-30: se quitó la pestaña «Ayuda» del
Asistente y el chat reconoce las preguntas de «¿cómo hago…?» / «¿dónde está…?»: las responde con el MANUAL
(`ia/ayuda_manual`: BM25 + IA, guardado) y la respuesta lleva los capítulos para abrir el manual de usuario.

Una pregunta es de ayuda si pide cómo hacer algo, dónde está algo o para qué sirve algo en la app, no nombra un
código del proyecto (C-12, AGUA-5: eso es del proyecto) y el manual tiene algo de eso. Las preguntas sobre los
datos («¿cuántos conflictos…?», «¿por qué ocurre C-3?») siguen yendo al proyecto.
"""
from __future__ import annotations

import re

from ia.texto import normalizar

# «cómo hago / cómo se / cómo puedo…», «dónde está / dónde encuentro…», «para qué sirve», «qué hace el botón…»,
# «pasos para…», y lo mismo en inglés.
_AYUDA = [re.compile(p) for p in (
    r"\bcomo\s+(hago|hacer|se|puedo|podria|debo|tengo|le|lo|la|los|las|uso|usar|funciona|cambio|cambiar|agrego|"
    r"agregar|pongo|poner|quito|quitar|borro|borrar|elimino|eliminar|abro|abrir|guardo|guardar|exporto|"
    r"exportar|importo|importar|dibujo|dibujar|creo|crear|edito|editar|activo|activar|desactivo|muevo|mover|"
    r"uno|unir|apago|apagar|enciendo|encender|configuro|configurar|georreferencio|georreferenciar|reconozco|"
    r"reconocer|calibro|calibrar|veo|ver|selecciono|seleccionar)\b",
    r"\bdonde\s+(esta|estan|encuentro|se|queda|quedan|veo|puedo|aparece|aparecen)\b",
    r"\bpara\s+que\s+sirve",
    r"\bque\s+hace\s+(el|la|los|las|este|esta|ese|esa)\b",
    r"\bpasos\s+para\b",
    r"\b(manual|tutorial|atajo|atajos|tecla|teclas)\b",
    r"\bhow\s+(do|can|to|does|should)\b",
    r"\bwhere\s+(is|are|can|do)\b",
    r"\bwhat\s+does\s+(the|this|that)\b",
    r"\bsteps\s+to\b",
)]
_CODIGO = re.compile(r"\b[a-z]+-\d+\b")


def es_de_ayuda(pregunta, indice, datos=None):
    """¿Es una pregunta sobre CÓMO USAR la app que el manual responde?"""
    q = normalizar(pregunta)
    if not any(p.search(q) for p in _AYUDA):
        return False
    if datos is not None and any(datos.ref(c.upper()) is not None for c in _CODIGO.findall(q)):
        return False                                     # nombra algo del proyecto: va a sus datos
    return bool(indice is not None and indice.buscar(pregunta))

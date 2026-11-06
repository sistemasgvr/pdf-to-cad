"""La cola de la revisión guiada (PURO): cada aviso pendiente en su nivel de certeza.

    SEGURO     lo mide la app: se aplica en tanda, con una confirmación
    PROPUESTA  hay evidencia que la IA puede juzgar: una línea a la vez
    DECISION   sin dato, o normativa: decide el usuario, por grupos

Un aviso de normativa nunca es SEGURO: no se arregla cambiando datos para que cumpla.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from nucleo import diametro_continuidad, diametro_plano, normas_aprobacion, soluciones
from nucleo import normas_catalogo as nc
from nucleo.copiloto_estado import OCULTAS
from traduccion.i18n_core import t

SEGURO, PROPUESTA, DECISION = "seguro", "propuesta", "decision"
PASO_AVISO = 50                                    # cada cuántos avisos se informa el avance
_CIFRA = re.compile(r"\d+(?:[.,]\d+)?")


def clave_de(aviso, pipes):
    return normas_aprobacion.clave(aviso, pipes)


@dataclass
class Item:
    clave: str
    aviso: object
    nivel: str
    valor: object = None                           # SEGURO: el diámetro (float) o el tipo (str)
    motivo: str = ""
    grupo: str = ""
    etiqueta: str = ""                             # el código de la utilidad, como se nombra


@dataclass
class Cola:
    items: list = field(default_factory=list)

    def seguros(self):
        return [x for x in self.items if x.nivel == SEGURO]

    def propuestas(self):
        return [x for x in self.items if x.nivel == PROPUESTA]

    def grupos(self):
        out = {}
        for x in self.items:
            if x.nivel == DECISION:
                out.setdefault(x.grupo, []).append(x)
        return out


def _grupo(aviso):
    """Clase + mensaje sin cifras: dos avisos iguales que solo cambian en sus números van juntos."""
    return aviso.clase + "|" + _CIFRA.sub("#", aviso.mensaje or "")


def _diametro(item, p, i, pipes, cat, ft_px, estructuras, con_bancoducto, tamano_de, indice, elegible):
    if "cerca" not in (p.get("diam_plano") or {}):      # reconocida antes de esto: la IA no tiene qué mirar
        item.motivo = t("Vuelve a reconocer la hoja para que la IA pueda revisar esta línea.")
        return
    cont = diametro_continuidad.analizar(i, pipes, ft_px, estructuras, indice)
    ops = cont["opciones"]
    if len(ops) == 1 and ops[0]["fuerza"] == "alta" and diametro_plano.permitido(cat, p, ops[0]["diam_in"]) \
            and i not in con_bancoducto and tamano_de(i, ops[0]["diam_in"]) is not None:
        item.nivel, item.valor, item.motivo = SEGURO, ops[0]["diam_in"], ops[0]["texto"]
    elif i not in con_bancoducto and (ops or any(elegible is None or elegible(e, p)
                                                 for e in (p.get("diam_plano") or {}).get("cerca") or [])):
        item.nivel = PROPUESTA


def _tipo(item, p, cat):
    tipos = nc.tipos_de(cat, p.get("layer"))
    if len(tipos) == 1 and not (p.get("tipo") or "").strip():
        item.nivel, item.valor = SEGURO, tipos[0]


def clasificar(avisos, pipes, normas_cat, ft_px, estructuras, con_bancoducto, tamano_de, saltados=(), al_paso=None,
               elegible=None):
    """`tamano_de(i, diam)` = el dato de ese tamaño para la utilidad i, o None si su familia no lo tiene.
    `elegible(rotulo, p)` = ¿ese rótulo puede ser de esa línea? (lo decide `ia/diametro_ia`)."""
    saltados, con_bancoducto = set(saltados), set(con_bancoducto)
    indice = diametro_continuidad.indice(pipes)
    pendientes = [a for a in avisos or [] if not a.info and not getattr(a, "aprobado", None)
                  and a.clase not in OCULTAS]
    cola = Cola()
    for k, a in enumerate(pendientes):
        if al_paso is not None and k % PASO_AVISO == 0:
            al_paso(k, len(pendientes))
        clave = clave_de(a, pipes)
        if clave in saltados:
            continue
        item = Item(clave, a, DECISION, grupo=_grupo(a))
        p = pipes[a.pipe] if a.pipe is not None and 0 <= a.pipe < len(pipes) else None
        item.etiqueta = soluciones.codigo(pipes, a.pipe) if p is not None else ""
        if p is not None and a.clase == diametro_plano.CLASE:
            _diametro(item, p, a.pipe, pipes, normas_cat, ft_px, estructuras, con_bancoducto, tamano_de, indice, elegible)
        elif p is not None and a.clase == "tipo":
            _tipo(item, p, normas_cat)
        cola.items.append(item)
    return cola

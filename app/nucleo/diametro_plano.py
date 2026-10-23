"""El diámetro que dijo el PLANO de cada utilidad reconocida y sus avisos (PURO: sin Qt).

Pedido del usuario 2026-10-22: «si alguna línea no tiene información, o no estamos 100 % seguros de
que esa información le pertenece, no hay que ponerla automáticamente: hay que dejar una alerta para
que el usuario sepa que se dejó por defecto ese tramo». El reconocimiento de un PDF con capas
(`recognition_grosor`) deja en cada línea `grosor["estado"]`: «leido» (el diámetro se puso),
«dudoso» (el plano dice algo pero no es seguro) o «sin_dato». Al importar, `de_grosor` lo guarda en
la utilidad (`diam_plano`) y `avisos` pone un aviso —como los de normativa: se marca en el plano,
se lista, se aprueba— a cada utilidad dudosa o sin dato que siga con el diámetro por defecto. En
cuanto el usuario elige un diámetro o un tamaño, el aviso desaparece; aprobarlo = dejar el de por
defecto a sabiendas.
"""
from __future__ import annotations

from nucleo import model_ops
from nucleo import normas_catalogo as nc
from nucleo.normas_validar import Aviso, _medio
from traduccion.i18n_core import t

CLASE = "grosor"
MAX_TEXTOS = 4


def de_grosor(g) -> dict:
    """Lo que se guarda en la utilidad de `RecognizedPolyline.grosor` (o {} si no hay)."""
    g = g or {}
    if not g.get("estado"):
        return {}
    out = {"estado": g["estado"]}
    for k in ("fuente", "paredes", "paredes_in", "material"):
        if g.get(k):
            out[k] = g[k]
    if g.get("textos"):
        out["textos"] = list(g["textos"])[:MAX_TEXTOS]
    if g.get("candidatos"):
        out["candidatos"] = [float(v) for v in g["candidatos"]]
    if g.get("perfil_in"):                       # lo que dicen los perfiles de los laterales que cruza
        out["perfil_in"] = [float(v) for v in g["perfil_in"]]
        out["perfil_textos"] = list(g.get("perfil_textos") or [])[:MAX_TEXTOS]
    return out


def _lista(vals):
    return ", ".join(nc.texto_pulgadas(v) for v in vals)


def mensaje(dp: dict, d: float) -> str:
    """Texto del aviso de una utilidad con `diam_plano` dudoso o sin dato (d = su diámetro)."""
    d_txt = nc.texto_pulgadas(d)
    if dp.get("estado") == "sin_dato":
        return t("Diámetro no encontrado en el plano: queda {d} por defecto. Elige el suyo, o aprueba "
                 "el aviso para dejarlo.").format(d=d_txt)
    fuente, cands = dp.get("fuente") or "", dp.get("candidatos") or []
    perfil = dp.get("perfil_in") or []
    if fuente == "mezcla":
        motivo = t("sus rótulos dicen {lista}").format(lista=_lista(cands))
    elif fuente == "perfil":
        motivo = t("los perfiles de los laterales que cruza dicen {lista}").format(lista=_lista(cands))
    elif fuente == "plano≠perfil":
        motivo = t("la planta dice {a} y el perfil de un lateral que cruza dice {b}").format(
            a=_lista([v for v in cands if v not in perfil] or cands), b=_lista(perfil))
    elif fuente == "rotulo≠paredes":
        rot = [v for v in cands if v != dp.get("paredes_in")] or cands
        motivo = t("el rótulo dice {r} y sus paredes miden {w}").format(
            r=_lista(rot), w=nc.texto_pulgadas(dp.get("paredes_in") or 0))
    else:
        motivo = t("sus paredes miden {w}, pero ningún rótulo de la hoja dice si son las de adentro o las "
                   "de afuera del tubo").format(w=nc.texto_pulgadas(dp.get("paredes_in") or (cands or [0])[0]))
    msg = t("Diámetro dudoso en el plano: {motivo}. Queda {d} por defecto hasta que elijas el suyo.").format(
        motivo=motivo, d=d_txt)
    textos = list(dict.fromkeys(list(dp.get("textos") or []) + list(dp.get("perfil_textos") or [])))
    if textos:
        msg += " " + t("Rótulos: {textos}.").format(textos=", ".join(f"«{x}»" for x in textos[:MAX_TEXTOS]))
    return msg


def avisos(pipes) -> list:
    """Un aviso (clase «grosor») por utilidad reconocida cuyo diámetro el plano no dijo con certeza
    y que sigue con el de por defecto."""
    out = []
    for i, p in enumerate(pipes or ()):
        dp = p.get("diam_plano") or {}
        pts = p.get("pts") or []
        if dp.get("estado") not in ("dudoso", "sin_dato") or len(pts) < 2 or p.get("world"):
            continue
        d, defecto = model_ops.diametro(p)
        if not defecto:
            continue                       # el usuario ya eligió su diámetro o tamaño
        out.append(Aviso(*_medio(pts), CLASE, mensaje(dp, d), i))
    return out

"""Del formato de CUATRO tablas (2026-10-09 → 10-20: TIPOS, PRESION-DIAMETROS, PRESION-ACCESORIOS,
ELECT-TELECOM) a la tabla única de reglas (PURO). Lo usan el Excel viejo al importarlo y el catálogo guardado
viejo; cada fila vieja da las reglas que revisan LO MISMO:

  PRESION-DIAMETROS   lista / MIN-MAX → «Diámetro (in)» (la nota «SOLO SE PERMITE EN» va a NOTA si no repite
                      el tipo: «calles sin salida» sigue saliendo como información).
  PRESION-ACCESORIOS  PROHIBIDO USO → «Se permite» NO en ese tipo; SOLO SE PERMITE EN → «Solo en tipos» (en el
                      Codo es dónde valen sus ángulos: va como TIPO); DIAMETRO PRINCIPAL → «Diámetro de la
                      principal» (en la T - Domiciliaria era el del ramal); -1 → «Ramal: tamaños menos…»;
                      ANGULOS → «Ángulo (°)». Las filas del mismo accesorio con varios «solo en» se juntan.
  ELECT-TELECOM       AMPERAJE / LONGITUD → condiciones SI; DIAMETRO FIJO/MIN/MAX → «Diámetro (in)»; RADIO
                      CURVA → «Radio (ft)» de la curva. ESTRUCTURA BANCODUCTO: aún no se revisaba (no pasa).
"""
from __future__ import annotations

from nucleo import normas_catalogo as nc
from nucleo import normas_reglas as NR

_ELEMENTO = {"wye": NR.Y, "tee": NR.T, "cruz": NR.CRUZ, "codo": NR.CODO, "tee_dom": NR.T_DOM}


def _dice_lo_mismo(nota, tipo):
    """«TUBERIA DE DISTRIBUCION PRINCIPAL» repite el tipo; «CALLES SIN SALIDA…» no (singular = plural)."""
    def raiz(w):
        return w[:-2] if w.endswith("ES") and len(w) > 4 else w[:-1] if w.endswith("S") else w

    def raices(s):
        return {raiz(w) for w in nc.clave(s).split() if len(w) > 2}
    return bool(raices(tipo)) and raices(tipo) <= raices(nota)


def _r(**k):
    return NR.regla_vacia(**k)


def reglas_de_v1(cat):
    """Las reglas equivalentes al catálogo de cuatro tablas `cat`."""
    out = []
    for f in cat.get("diametros") or []:
        nota = (f.get("nota") or "").strip()
        if nota and _dice_lo_mismo(nota, f.get("tipo") or ""):
            nota = ""
        lista, lo, hi = f.get("diametros") or [], f.get("diam_min"), f.get("diam_max")
        if lista:
            out.append(_r(utilidad=f["utilidad"], tipo=f.get("tipo") or "", revisar="diametro",
                          valores=list(lista), nota=nota))
        if lo is not None or hi is not None:
            out.append(_r(utilidad=f["utilidad"], tipo=f.get("tipo") or "", revisar="diametro", min=lo, max=hi,
                          nota=nota))
    solo = {}
    for f in cat.get("accesorios") or []:
        e = _ELEMENTO.get(nc.ACCESORIOS.get(nc.clave(f.get("accesorio"))))
        if e is None:
            continue
        u, solo_en, prohibido = f["utilidad"], nc.clave(f.get("solo_en")), nc.clave(f.get("prohibido_en"))
        base = dict(utilidad=u, elemento=e)
        if prohibido:
            out.append(_r(tipo=prohibido, revisar="permitido", valores=[NR.NO], **base))
        if e == NR.T_DOM:
            if f.get("diam_principal"):
                out.append(_r(revisar="diam_ramal", valores=list(f["diam_principal"]), **base))
            if f.get("angulos"):
                out.append(_r(revisar="angulo", valores=list(f["angulos"]), **base))
            continue
        if solo_en and e != NR.CODO:
            if (u, e) not in solo:
                solo[(u, e)] = _r(revisar="solo_en", valores=[], **base)
                out.append(solo[(u, e)])
            if solo_en not in solo[(u, e)]["valores"]:
                solo[(u, e)]["valores"].append(solo_en)
        tipo = solo_en
        if f.get("diam_principal"):
            out.append(_r(tipo=tipo, revisar="diam_principal", valores=list(f["diam_principal"]), **base))
        if f.get("ramal") is not None and e in (NR.Y, NR.T):
            out.append(_r(tipo=tipo, revisar="ramal_pasos", valores=[float(int(f["ramal"]))], **base))
        if f.get("angulos"):
            out.append(_r(tipo=tipo, revisar="angulo", valores=list(f["angulos"]), **base))
    for f in cat.get("electricas") or []:
        if nc.clave(f.get("estructura")) not in ("", "SIMPLE"):
            continue                                   # bancoducto: todavía no se revisaba
        cond = dict(utilidad=f["utilidad"], tipo=nc.clave(f.get("tipo")),
                    si_amp=list(f["amperaje"]) if f.get("amperaje") else None,
                    si_largo=list(f["longitud"]) if f.get("longitud") else None)
        # fijo Y mínimo/máximo en la MISMA regla: había que cumplir las dos cosas (no una u otra)
        if f.get("diam_fijo") or f.get("diam_min") is not None or f.get("diam_max") is not None:
            out.append(_r(revisar="diametro", valores=list(f.get("diam_fijo") or []), min=f.get("diam_min"),
                          max=f.get("diam_max"), **cond))
        if f.get("radio_fijo") or f.get("radio_min") is not None or f.get("radio_max") is not None:
            out.append(_r(elemento=NR.CURVA, revisar="radio", valores=list(f.get("radio_fijo") or []),
                          min=f.get("radio_min"), max=f.get("radio_max"), **cond))
    for r in out:
        if r.get("si_amp") is not None and r["utilidad"] != "ELECTRICO":
            r["si_amp"] = None                         # (telecom no lleva amperaje)
    return out


def de_v1(cat):
    """Catálogo nuevo (tipos + reglas) del de cuatro tablas."""
    return {"version": 2, "tipos": [list(t) for t in cat.get("tipos") or []], "reglas": reglas_de_v1(cat)}

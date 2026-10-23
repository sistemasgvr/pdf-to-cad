"""Quién REDACTA el informe (PURO). Hoy, plantillas; mañana, la IA (`docs/pendientes_ia.md`).

Un `Redactor` recibe FICHAS (`informe_datos`: lo que la app ya midió) y devuelve texto legible:
`resumen(informe)`, `zona(zona)` y `ficha(ficha)`. El informe en Word (`exportar/informe_word`) solo habla
con esta interfaz, así cambiar plantilla por IA es cambiar el redactor, no el informe.

`crear(config)` = la plantilla (y el motivo si se pidió otro proveedor). El redactor con IA está en
`ia/redactor_ia.py` (`crear(config, memoria)`, que cae aquí si la IA no está). Regla para la IA: los NÚMEROS los
pone la app (vienen en la ficha); la IA solo redacta y, si falla, sale la plantilla.
"""
from __future__ import annotations

import json

from nucleo import model
from traduccion.i18n_core import N_, t

# Qué revisar, por tipo de conflicto (clave de `nucleo.conflictos`) o clase de aviso (`normas_validar.CLASES`).
CONSEJOS = {
    "cruce": N_("Cambia la cota de una de las dos tuberías para que pasen a distinta altura, o únelas si "
                "debían conectarse."),
    "exceso": N_("Reparte las conexiones: en un mismo punto Civil 3D no arma más de cuatro tuberías."),
    "escalon": N_("Iguala la cota de llegada y la de salida en ese vértice, o pon un buzón si el escalón es "
                  "intencional."),
    "codos": N_("Alarga el tramo entre los dos codos o junta los codos en uno."),
    "retorno": N_("Revisa el trazo: la tubería vuelve casi sobre sí misma."),
    "pendiente": N_("Da espacio a la unión o ajusta las cotas para que la pieza entre."),
    "inclinada": N_("La conexión vertical debe ser vertical: iguala la ubicación en planta de sus dos puntas."),
    "redes": N_("Separa las dos redes o confirma que deben unirse."),
    "choque": N_("Las tuberías se tocan sin conexión: sepáralas en altura o en planta."),
    "diametro": N_("Cambia el diámetro a uno de los permitidos o revisa el tipo de la utilidad."),
    "electrico": N_("Revisa el amperaje y el largo de la línea y elige el diámetro que pide la tabla."),
    "accesorio": N_("Revisa el accesorio, el tipo de la línea principal y los diámetros de principal y ramal."),
    "radio": N_("Cambia el radio de la curva al permitido."),
    "pendiente_n": N_("Ajusta las cotas del tramo para llegar a la pendiente pedida."),
    "largo": N_("Revisa el largo de la tubería o pártela con un buzón."),
    "material": N_("Cambia el material al permitido por la norma."),
    "buzon": N_("Revisa la ubicación de los buzones y las cotas en ellos."),
    "separacion": N_("Aleja las dos utilidades o cambia sus cotas para cumplir la separación."),
    "nota": N_("Confirma que se cumple la condición de uso indicada."),
}


def consejo(f):
    clave = "pendiente_n" if f["tipo"] == "aviso" and f["clase"] == "pendiente" else f["clase"]
    return t(CONSEJOS[clave]) if clave in CONSEJOS else ""


def nombre_utilidad(capa):
    """«AGUA» → «Agua» (el nombre visible, traducido; la capa es un código interno)."""
    lbl = next((lbl for lbl, c in model.TIPOS if c == capa), capa or "?")
    return t(lbl).split(" (")[0]


def _quien(f):
    nombres = []
    for u in f.get("utilidades") or []:
        nombres.append(u["codigo"] + (f" ({u['nombre']})" if u.get("nombre") else ""))
    return ", ".join(nombres)


class Redactor:
    """Interfaz: lo que el informe le pide a quien redacta."""
    nombre = "base"

    def resumen(self, informe):
        raise NotImplementedError

    def zona(self, zona):
        raise NotImplementedError

    def ficha(self, ficha):
        raise NotImplementedError


class RedactorPlantilla(Redactor):
    """Frases armadas con los datos de la ficha (sin IA)."""
    nombre = "plantilla"

    def resumen(self, informe):
        r = informe.resumen
        partes = [t("Utilidades revisadas: {n}.").format(n=r["utilidades"])]
        if informe.opciones.conflictos:
            partes.append(t("Conflictos en el dibujo: {n}.").format(n=r["conflictos"]) if r["conflictos"]
                          else t("No hay conflictos en el dibujo."))
        if informe.opciones.normativas:
            partes.append(t("Avisos de normativa: {n} (pendientes: {p}, aprobados: {a}, informativos: {i}).").format(
                n=r["avisos"], p=r["avisos_pendientes"], a=r["aprobados"], i=r["info"]) if r["avisos"]
                else t("Todo cumple las normativas."))
            if r["sin_tipo"]:
                partes.append(t("Utilidades sin tipo asignado: {n} (sin tipo no se revisan las reglas propias de "
                                "cada tipo).").format(n=r["sin_tipo"]))
        if informe.zonas:
            partes.append(t("Zonas del plano con algo que revisar: {n}; cada una tiene su ficha más abajo.").format(
                n=len(informe.zonas)))
        return " ".join(partes)

    def zona(self, zona):
        nc = sum(1 for f in zona.fichas if f["tipo"] == "conflicto")
        na = len(zona.fichas) - nc
        capas = sorted({nombre_utilidad(u["capa"]) for f in zona.fichas for u in f["utilidades"]})
        txt = t("Zona {z} · conflictos: {c} · avisos: {a}.").format(z=zona.numero, c=nc, a=na)
        if capas:
            txt += " " + t("Utilidades involucradas: {u}.").format(u=", ".join(capas))
        return txt

    def ficha(self, f):
        txt = " ".join(f["mensaje_app"].split())
        if txt and not txt.endswith("."):
            txt += "."
        quien = _quien(f)
        if quien and f["tipo"] == "aviso":
            txt = t("{u}: {m}").format(u=quien, m=txt)
        if f.get("fuente"):
            txt += " " + t("Fuente: {f}.").format(f=f["fuente"])
        if f.get("aprobado"):
            ap = f["aprobado"]
            txt += " " + t("Aprobado por {u} el {fecha}.").format(u=ap.get("usuario") or "?", fecha=ap.get("fecha") or "?")
            if ap.get("nota"):
                txt += " " + t("Nota: {nota}").format(nota=ap["nota"])
        elif not f["info"]:
            que_hacer = consejo(f)
            if que_hacer:
                txt += " " + t("Qué hacer: {c}").format(c=que_hacer)
        return txt


def crear(config=None):
    """(redactor, motivo): el de `config["proveedor"]`, o la plantilla (y por qué) si no está disponible."""
    proveedor = ((config or {}).get("proveedor") or "plantilla").lower()
    if proveedor == "plantilla":
        return RedactorPlantilla(), ""
    return RedactorPlantilla(), t("La redacción con IA («{p}») aún no está disponible: se usaron plantillas.").format(
        p=proveedor)


def datos_para_ia(ficha):
    """La ficha como JSON: lo que recibirá la IA (sin el lugar en px del lienzo, que no le sirve)."""
    return json.dumps({k: v for k, v in ficha.items() if k not in ("x", "y")}, ensure_ascii=False)

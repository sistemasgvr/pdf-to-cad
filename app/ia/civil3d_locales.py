"""Lo que la APP pone en el chat «Civil 3D» (PURO): sus herramientas propias y sus normativas.

El plugin lee y cambia el dibujo; las NORMATIVAS y el PROYECTO son de la app. Aquí:
  - Herramientas de la app que el modelo ve como cualquier otra: `revisar_normativas` (validador de la app sobre
    `datos_red`), `exportar_cuadro` (Excel/Word), `comparar_con_app` y `traer_a_la_app` (proyecto abierto).
  - Lo que se inyecta en cada llamada al plugin (el modelo no lo ve ni lo cambia): las separaciones de la normativa
    (`reglas`) y la pendiente objetivo de cada tubería (`objetivos`).
  - Cada propuesta con `efecto` se revisa con las normativas de la app antes de llegar a la tarjeta
    (`civil3d_normativas_cambios.con_normativa`).
`Locales(cliente, normas_cat=, reglas=, proyecto=)`: `proyecto()` = {pipes, ft, a_px, a_mundo, tinta} de la app o None
(ver `civil3d_pdf`).
"""
from __future__ import annotations

import json

from traduccion.i18n_core import t

SOLO_APP = {"datos_red"}                     # la usa la app, no el modelo (mucho texto)
CON_REGLAS = {"buscar_conflictos", "proponer_solucion", "proponer_mover_planta", "proponer_conexion_vertical"}
OCULTOS = {"reglas", "objetivos", "normas"}   # argumentos que pone la app


class Locales:
    def __init__(self, cliente, normas_cat=None, reglas=None, proyecto=None):
        self.cliente = cliente
        self.normas_cat = normas_cat
        self.reglas = reglas
        self.proyecto = proyecto
        self._datos = None
        self._difs = []
        self.pendientes_app = {}             # id → propuesta para la app (la aplica la ventana)

    def nuevo_turno(self):
        self._datos = None                   # el dibujo pudo cambiar entre preguntas

    # ---------------------------------------------------------------- catálogo

    def herramientas(self, catalogo_mcp):
        """Las de la app que se pueden ofrecer con este plugin y esta ventana."""
        if not any(h.get("name") == "datos_red" for h in catalogo_mcp):
            return []
        from ia import civil3d_comparar, civil3d_cuadro, civil3d_normativas
        out = [civil3d_cuadro.herramienta()]
        if self.normas_cat:
            out.append(civil3d_normativas.herramienta())
        if self.proyecto:
            from ia import civil3d_pdf
            out += civil3d_comparar.herramientas() + [civil3d_pdf.herramienta()]
        return out

    def es_local(self, nombre):
        return nombre in ("revisar_normativas", "exportar_cuadro", "comparar_con_app", "traer_a_la_app", "comparar_con_pdf")

    # ---------------------------------------------------------------- llamar

    def datos(self):
        if self._datos is None:
            ok, salida = self.cliente.llamar("datos_red", {})
            if not ok:
                raise ValueError(salida)
            self._datos = json.loads(salida)
        return self._datos

    def cat(self):
        return self.normas_cat() if self.normas_cat else None

    def llamar(self, nombre, args):
        """(ok, texto) de una herramienta: la de la app, o la del plugin con lo que pone la app."""
        try:
            if self.es_local(nombre):
                return self._local(nombre, args)
            if nombre in SOLO_APP:
                return False, t("Esa herramienta no está disponible.")
            args = {k: v for k, v in (args or {}).items() if k not in OCULTOS}
            if nombre in CON_REGLAS:
                args["reglas"] = self.reglas() if self.reglas else []
            if nombre == "proponer_pendiente" and self.cat():
                from ia import civil3d_normativas_cambios as NC
                args["objetivos"] = NC.objetivos_pendiente(self.datos(), self.cat())
            ok, salida = self.cliente.llamar(nombre, args)
            if ok and self.cat():
                salida = self._con_normativa(salida)
            return ok, salida
        except ValueError as e:
            return False, str(e)

    def _con_normativa(self, salida):
        try:
            d = json.loads(salida)
        except ValueError:
            return salida
        if not isinstance(d, dict) or not d.get("efecto"):
            return salida
        from ia import civil3d_normativas_cambios as NC
        return json.dumps(NC.con_normativa(d, self.datos(), self.cat()), ensure_ascii=False)

    def _local(self, nombre, args):
        args = args or {}
        if nombre == "revisar_normativas":
            if not self.cat():
                return False, t("La revisión de normativas no está disponible aquí.")
            from ia import civil3d_normativas as CN
            r = CN.revisar(self.datos(), self.cat(), args.get("utilidad"), args.get("red"))
            return ("error" not in r), (r.get("error") or json.dumps(r, ensure_ascii=False))
        if nombre == "exportar_cuadro":
            from ia import civil3d_cuadro
            return civil3d_cuadro.ejecutar(self.cliente, self.cat(), self.reglas() if self.reglas else [], args)
        if not self.proyecto or self.proyecto() is None:
            return False, t("No hay un proyecto abierto en la app para comparar.")
        pr = self.proyecto()
        if nombre == "comparar_con_pdf":
            if not pr.get("tinta"):
                return False, t("La app no tiene el PDF cargado para comparar.")
            from ia import civil3d_pdf
            puntos = civil3d_pdf.comparar(self.datos(), pr, float(args.get("tolerancia_ft") or civil3d_pdf.TOL_FT))
            return True, json.dumps(civil3d_pdf.resumen(puntos), ensure_ascii=False)
        from ia import civil3d_comparar as CC
        pipes, ft = pr["pipes"], pr["ft"]
        if nombre == "comparar_con_app" or not self._difs:
            self._difs = CC.comparar(self.datos(), pipes, ft)
            if nombre == "comparar_con_app":
                return True, json.dumps(CC.resumen(self._difs), ensure_ascii=False)
        p = CC.propuesta(self._difs, args.get("diferencias") or ["todas"], pipes)
        if p is None:
            return False, t("No hay diferencias que se puedan traer a la app (o esos ids no existen).")
        self.pendientes_app[p["id"]] = p
        return True, json.dumps(p, ensure_ascii=False)

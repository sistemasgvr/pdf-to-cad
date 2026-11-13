"""Herramientas de SOLO LECTURA del proyecto para la IA (PURO): el `cliente` que recibe `civil3d_agente.Agente`.

La IA decide qué consultar; no hay ninguna herramienta que cambie algo. Cada salida queda en `salidas`: las cifras de la
respuesta se revisan también contra ellas.
"""
from __future__ import annotations

from ia.texto import normalizar
from nucleo import model_ops
from traduccion.i18n_core import t

MAX_FILAS = 40

_TEXTO = {"type": "string"}
_CATALOGO = (
    ("buscar_lineas", "Busca utilidades por filtros y devuelve una línea de texto por cada una.",
     {"utilidad": dict(_TEXTO, description="AGUA, ALCANTARILLADO, DRENAJE, GAS, ELECTRICO o TELECOM"),
      "sin_diametro": {"type": "boolean", "description": "solo las que siguen con el diámetro por defecto"},
      "sin_tipo": {"type": "boolean", "description": "solo las que no tienen tipo"}}, []),
    ("ver_ficha", "Los datos de una utilidad, conflicto o aviso por su código.",
     {"codigo": dict(_TEXTO, description="p. ej. AGUA-5, C-12 o N-3")}, ["codigo"]),
    ("listar_avisos", "Los avisos de normativa, opcionalmente de una clase.",
     {"clase": dict(_TEXTO, description="grosor (diámetro del plano), diametro, material, pendiente, separacion, "
                                        "buzon…")}, []),
    ("listar_conflictos", "Los conflictos del proyecto.", {}, []),
    ("buscar_texto", "Busca en TODO el texto del plano (calles, lugares, direcciones, números de servicio, notas, "
                     "rótulos de tubería). Cada resultado trae su código TX-n (lleva al lugar), su hoja y las "
                     "utilidades que tiene cerca.",
     {"texto": dict(_TEXTO, description="lo que buscas, p. ej. THOMAS RD, 9701461994, CHURCH, 2\" PE"),
      "tipo": dict(_TEXTO, description="opcional: calle, tuberia, direccion, servicio, lugar, nota, estacion, largo")},
     ["texto"]),
    ("listar_calles", "Las calles que nombra el plano, cada una una vez, con sus hojas y las utilidades cerca.", {}, []),
    ("definir_plan", "Escribe tu propio plan para un pedido de varios pasos: serán tus instrucciones hasta terminar.",
     {"objetivo": _TEXTO, "pasos": _TEXTO, "como_saber": dict(_TEXTO, description="cómo sabrás que terminaste")},
     ["objetivo", "pasos"]),
)


class ClienteProyecto:
    def __init__(self, datos, seleccion=""):
        self.datos = datos
        self.salidas = []
        self.seleccion = seleccion                     # lo que el usuario tiene elegido: «esto»
        self.plan = ""

    @property
    def instrucciones(self):
        """Lo que se suma al sistema en cada paso; el plan lo escribió la propia IA."""
        partes = []
        if self.seleccion:
            partes.append(t("El usuario tiene elegido: {c}. «Esto» se refiere a eso.").format(c=self.seleccion))
        if self.plan:
            partes.append(t("TU PLAN (lo escribiste tú, síguelo):") + "\n" + self.plan)
        return "\n".join(partes)

    def herramientas(self):
        return [{"name": n, "description": d, "inputSchema": {"type": "object", "properties": p, "required": r}}
                for n, d, p, r in _CATALOGO]

    def llamar(self, nombre, args=None):
        fn = {"buscar_lineas": self._buscar, "ver_ficha": self._ficha, "listar_avisos": self._avisos,
              "listar_conflictos": self._conflictos, "definir_plan": self._definir_plan,
              "buscar_texto": self._buscar_texto, "listar_calles": self._calles}.get(nombre)
        if fn is None:
            return False, t("Esa herramienta no existe.")
        ok, salida = fn(args if isinstance(args, dict) else {})
        self.salidas.append(salida)
        return ok, salida

    def _definir_plan(self, a):
        self.plan = "\n".join(str(a.get(k) or "") for k in ("objetivo", "pasos", "como_saber") if a.get(k))
        return True, t("Plan anotado.")

    def _filas(self, lineas):
        filas = [ln.texto for ln in lineas]
        if not filas:
            return True, t("No hay resultados.")
        resto = len(filas) - MAX_FILAS
        return True, "\n".join(filas[:MAX_FILAS] + ([t("hay {n} más").format(n=resto)] if resto > 0 else []))

    def _pipe_de(self, codigo):
        r = self.datos.ref(codigo)
        return self.datos.pipes[r["indice"]] if r and r.get("objeto") == "pipe" else {}

    def _buscar(self, a):
        capa = normalizar(str(a.get("utilidad") or "")).upper()
        out = []
        for ln in self.datos.utilidades:
            p = self._pipe_de(ln.codigo)
            if capa and ln.capa != capa:
                continue
            if a.get("sin_diametro") is True and not model_ops.diametro(p)[1]:
                continue
            if a.get("sin_tipo") is True and (p.get("tipo") or "").strip():
                continue
            out.append(ln)
        return self._filas(out)

    def _ficha(self, a):
        c = normalizar(str(a.get("codigo") or ""))
        for ln in list(self.datos.utilidades) + list(self.datos.lineas_fichas):
            if normalizar(ln.codigo) == c:
                return True, ln.texto
        return False, t("No encuentro ese código en el proyecto.")

    def _fichas_de(self, tipo, clase=""):
        ids = {f["id"] for f in self.datos.fichas if f["tipo"] in tipo and (not clase or f.get("clase") == clase)}
        return [ln for ln in self.datos.lineas_fichas if ln.codigo in ids]

    def _avisos(self, a):
        clase = normalizar(str(a.get("clase") or ""))
        if clase == "tipo":                            # no van en las fichas: son tantos como utilidades sin tipo
            return True, t("Usa buscar_lineas con sin_tipo.")
        return self._filas(self._fichas_de(("aviso", "reconocimiento"), clase))

    def _conflictos(self, _a):
        return self._filas(self._fichas_de(("conflicto",)))

    def _buscar_texto(self, a):
        tx = getattr(self.datos, "texto", None)
        if tx is None or not len(tx):
            return True, t("Este proyecto no tiene texto del plano (PDF escaneado, o aún se está leyendo).")
        filas, total = tx.buscar(str(a.get("texto") or ""), str(a.get("tipo") or ""))
        if not filas:
            return True, t("El plano no dice «{q}».").format(q=a.get("texto") or "")
        extra = [t("hay {n} más").format(n=total - len(filas))] if total > len(filas) else []
        return True, "\n".join(filas + extra)

    def _calles(self, _a):
        tx = getattr(self.datos, "texto", None)
        if tx is None or not len(tx):
            return True, t("Este proyecto no tiene texto del plano (PDF escaneado, o aún se está leyendo).")
        filas, total = tx.calles()
        if not filas:
            return True, t("El plano no nombra calles.")
        extra = [t("hay {n} más").format(n=total - len(filas))] if total > len(filas) else []
        return True, "\n".join(filas + extra)


_PASOS = {"ver_plano": "Miré el plano: {que_buscar}", "listar_zonas": "Busqué zonas con más datos", "ver_zona": "Miré la zona {zona}",
          "senalar": "Señalé en el plano", "buscar_funcion": "Busqué una función: {texto}", "usar_funcion": "Usé: {nombre}",
          "definir_plan": "Me hice un plan: {objetivo}", "ver_ficha": "Leí la ficha de {codigo}", "buscar_lineas": "Busqué líneas",
          "listar_avisos": "Revisé los avisos", "listar_conflictos": "Revisé los conflictos", "ir_a": "Te llevé a {codigo}",
          "proponer_diametro": "Te propuse un diámetro", "proponer_accion": "Te propuse un cambio",
          "buscar_texto": "Busqué en el texto del plano: {texto}", "listar_calles": "Revisé las calles del plano",
          "quitar_senales": "Quité las señales"}


def describir(nombre, args):
    """El paso del agente en palabras del usuario."""
    plantilla = _PASOS.get(nombre)
    if plantilla is None:
        return nombre
    a = args if isinstance(args, dict) else {}
    try:
        return t(plantilla).format(**{k: str(v)[:80] for k, v in a.items()})
    except (KeyError, IndexError):
        return t(plantilla).split(":")[0]

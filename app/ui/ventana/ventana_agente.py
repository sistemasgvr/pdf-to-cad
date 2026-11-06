"""El agente del chat en la ventana: lo que mira y lo que puede hacer en la app.

`ClienteVentana` suma a `ia/herramientas.ClienteProyecto` las herramientas que necesitan el plano o la ventana. La IA
corre en un hilo: lo que toca PyMuPDF o Qt pasa a la ventana por la señal `puente`. Mirar, señalar y encender vistas se
hace al momento; lo que cambia el proyecto o usa otra función queda como propuesta para que decida el usuario.
"""
from __future__ import annotations

import base64
import threading

from PySide6 import QtCore, QtGui

from ia import acciones as AC
from ia.civil3d_agente import ConImagen
from ia.herramientas import ClienteProyecto
from ia.texto import normalizar
from nucleo import diametro_plano, normas_catalogo as nc, soluciones
from traduccion.i18n import t as _tr
from ui.comun.marcas_ia import MarcasIA

MARGEN_PT = 60.0
MARGEN_MIN, MARGEN_MAX = 20.0, 400.0
MAX_FUNCIONES = 10
GRUPOS_SEGUROS = ("Ver",)                              # encender y apagar vistas no cambia el proyecto
ACCIONES = ("cambiar_cotas", "poner_rasantes", "cambiar_diametro", "cambiar_material", "cambiar_tipo",
            "marcar_abandonada", "resolver_conflicto")  # nunca borrar ni mover

_CODIGO = {"type": "string", "description": "código, p. ej. AGUA-5"}
_EXTRAS = (
    ("ver_plano", "Captura del plano alrededor de una utilidad, marcada en MAGENTA, y el texto cercano del PDF.",
     {"codigo": _CODIGO, "que_buscar": {"type": "string", "description": "lo que vas a buscar, con tus palabras"},
      "margen_pt": {"type": "number", "description": "aire alrededor de la línea en puntos: 40 cerca, 200 lejos"}},
     ["codigo", "que_buscar"]),
    ("listar_zonas", "Las zonas donde puede haber más datos de una utilidad: lados, membrete, leyenda, notas, también "
                     "fuera del área recortada y en otras hojas del PDF.", {"codigo": _CODIGO}, ["codigo"]),
    ("ver_zona", "Captura y texto de una zona de listar_zonas.",
     {"codigo": _CODIGO, "zona": {"type": "string", "description": "id de la zona"}}, ["codigo", "zona"]),
    ("senalar", "Señala utilidades en el plano del usuario y las encuadra. No cambia nada.",
     {"codigos": {"type": "array", "items": {"type": "string"}}}, ["codigos"]),
    ("quitar_senales", "Quita lo señalado.", {}, []),
    ("ir_a", "Lleva el plano a una utilidad o a un conflicto. No cambia nada.", {"codigo": _CODIGO}, ["codigo"]),
    ("buscar_funcion", "Busca entre las funciones de la app, por lo que hacen.",
     {"texto": {"type": "string"}}, ["texto"]),
    ("usar_funcion", "Usa una función de buscar_funcion. Las de ver se hacen; las demás las confirma el usuario.",
     {"nombre": {"type": "string", "description": "el nombre exacto"}}, ["nombre"]),
    ("proponer_diametro", "Propone un diámetro al usuario, con la evidencia. Antes hay que haber mirado esa línea.",
     {"codigo": _CODIGO, "pulgadas": {"type": "number"},
      "evidencia": {"type": "string", "description": "el texto exacto del rótulo y por qué es de esta línea"}},
     ["codigo", "pulgadas", "evidencia"]),
    ("proponer_accion", "Propone un cambio al usuario, que lo confirma con un botón. Acciones: " + ", ".join(ACCIONES),
     {"accion": {"type": "string"}, "parametros": {"type": "object"}}, ["accion", "parametros"]),
)


class _Senales(QtCore.QObject):
    puente = QtCore.Signal(object, object)


class ClienteVentana(ClienteProyecto):
    def __init__(self, datos, win, cancelado, seleccion=""):
        super().__init__(datos, seleccion)
        self.win = win
        self.cancelado = cancelado
        self.propuestas = []
        self.miradas = {}                              # índice de utilidad → última captura (bytes)
        self.textos = []                               # lo que la app leyó en lo que miró
        self._vistas = set()

    def herramientas(self):
        extra = [{"name": n, "description": d, "inputSchema": {"type": "object", "properties": p, "required": r}}
                 for n, d, p, r in _EXTRAS]
        return super().herramientas() + extra

    def llamar(self, nombre, args=None):
        fn = getattr(self, "_h_" + nombre, None) if nombre in {e[0] for e in _EXTRAS} else None
        if fn is None:
            return super().llamar(nombre, args)
        a = args if isinstance(args, dict) else {}
        try:
            ok, salida = fn(a)
        except Exception as e:                         # noqa: BLE001 (el modelo lo lee y busca otro camino)
            ok, salida = False, _tr("No se pudo: {e}").format(e=e)
        self.salidas.append(str(salida))
        return ok, salida

    def _en_ventana(self, fn):
        if threading.current_thread() is threading.main_thread():
            return fn()
        caja = {"listo": threading.Event()}
        self.win._agente_senal().puente.emit(fn, caja)
        while not caja["listo"].wait(0.1):
            if self.cancelado():
                return None
        if "e" in caja:
            raise caja["e"]
        return caja.get("r")

    def _indice(self, codigo):
        r = self.datos.ref(str(codigo or ""))
        return r["indice"] if r and r.get("objeto") == "pipe" else None

    def _no_existe(self, codigo):
        return False, _tr("No encuentro «{c}» en el proyecto.").format(c=codigo)

    # ── mirar ──
    def _h_ver_plano(self, a):
        i = self._indice(a.get("codigo"))
        if i is None:
            return self._no_existe(a.get("codigo"))
        try:
            m = float(a.get("margen_pt") or MARGEN_PT)
        except (TypeError, ValueError):
            m = MARGEN_PT
        m = max(MARGEN_MIN, min(MARGEN_MAX, m))
        clave = (i, round(m / 20))
        if clave in self._vistas:
            return True, _tr("Ya viste esta zona con ese zoom. Mira otra zona o termina con lo que tienes.")
        r = self._en_ventana(lambda: self.win.agente_captura(i, m))
        if r is None:
            return False, _tr("No hay PDF en esta hoja: no puedo mirar el plano.")
        png, textos = r
        self._vistas.add(clave)
        self.miradas[i] = png
        self.textos += textos
        cuerpo = "\n".join(textos) or _tr("(el PDF no da texto cerca de esta línea)")
        return True, ConImagen(_tr("Captura: la línea va en magenta. Texto cercano del PDF:") + "\n" + cuerpo,
                               [base64.b64encode(png).decode("ascii")])

    def _h_listar_zonas(self, a):
        i = self._indice(a.get("codigo"))
        if i is None:
            return self._no_existe(a.get("codigo"))
        zonas = self._en_ventana(lambda: self.win.agente_zonas(i)) or []
        self._zonas = {z["id"]: z for z in zonas}
        if not zonas:
            return True, _tr("No hay otras zonas para esta utilidad.")
        return True, "\n".join(f'{z["id"]}: {z["titulo"]} (hoja {z["pagina"]}) {z.get("adelanto") or ""}' for z in zonas)

    def _h_ver_zona(self, a):
        i = self._indice(a.get("codigo"))
        if i is None:
            return self._no_existe(a.get("codigo"))
        z = getattr(self, "_zonas", {}).get(str(a.get("zona") or ""))
        if z is None:
            return False, _tr("Primero pide las zonas de esa utilidad.")
        if (i, z["id"]) in self._vistas:
            return True, _tr("Ya viste esta zona. Mira otra o termina con lo que tienes.")
        v = self._en_ventana(lambda: self.win.agente_ver_zona(i, z))
        if v is None:
            return False, _tr("No pude leer esa zona.")
        self._vistas.add((i, z["id"]))
        self.textos.append(v.get("texto") or "")
        cap = v.get("captura") or {}
        if cap.get("imagen"):
            self.miradas[i] = base64.b64decode(cap["imagen"])
        return True, ConImagen(v.get("texto") or _tr("(sin texto)"), [cap["imagen"]] if cap.get("imagen") else [])

    # ── señalar y usar la app ──
    def _h_senalar(self, a):
        cods = a.get("codigos") or []
        cods = [cods] if isinstance(cods, str) else [str(c) for c in cods]
        malos = [c for c in cods if self._indice(c) is None]
        if malos or not cods:
            return False, _tr("No encuentro: {c}").format(c=", ".join(malos) or "-")
        idx = [self._indice(c) for c in cods]
        self._en_ventana(lambda: self.win.agente_senalar(idx))
        return True, _tr("Señalé {n} en el plano.").format(n=len(idx))

    def _h_quitar_senales(self, _a):
        self._en_ventana(self.win.agente_quitar_senales)
        return True, _tr("Listo.")

    def _h_ir_a(self, a):
        r = self.datos.ref(str(a.get("codigo") or ""))
        if r is None:
            return self._no_existe(a.get("codigo"))
        self._en_ventana(lambda: self.win._ir_a_elemento(r["x"], r["y"], "pipe" if r["objeto"] == "pipe" else None,
                                                         r["indice"], activar=False))
        return True, _tr("El plano muestra {c}.").format(c=a.get("codigo"))

    def _h_buscar_funcion(self, a):
        fs = self._en_ventana(lambda: self.win.agente_funciones(str(a.get("texto") or ""))) or []
        return True, "\n".join(f"{g}: {t}" + (f" ({k})" if k else "") for g, t, k, _a in fs) or _tr("No hay resultados.")

    def _h_usar_funcion(self, a):
        nombre = str(a.get("nombre") or "")
        r = self._en_ventana(lambda: self.win.agente_funcion(nombre))
        if r is None:
            return False, _tr("No encuentro esa función.")
        grupo, texto, _k, accion = r
        if grupo in GRUPOS_SEGUROS:
            self._en_ventana(accion.trigger)
            return True, _tr("Hecho: {f}").format(f=texto)
        self.propuestas.append({"tipo": "funcion", "texto": texto, "accion": accion})
        return True, _tr("Le pregunté al usuario si usa «{f}».").format(f=texto)

    # ── proponer ──
    def _h_proponer_diametro(self, a):
        i = self._indice(a.get("codigo"))
        if i is None:
            return self._no_existe(a.get("codigo"))
        if i not in self.miradas:
            return False, _tr("Antes mira esa línea en el plano.")
        try:
            d = float(a.get("pulgadas"))
        except (TypeError, ValueError):
            d = 0.0
        if d <= 0:
            return False, _tr("Di el diámetro en pulgadas.")
        cat = getattr(self.win, "normas_cat", None)
        if not self._en_ventana(lambda: diametro_plano.permitido(cat, self.win.pipes[i], d)):
            return False, _tr("La normativa no permite {d} en esa utilidad.").format(d=nc.texto_pulgadas(d))
        from hoja import zonas_diametro
        leido = any(abs(v - d) < 1e-6 for t in self.textos for v in zonas_diametro.diametros(t))
        self.propuestas.append({"tipo": "diametro", "pipe": i, "diam_in": d, "evidencia": str(a.get("evidencia") or ""),
                                "leido": leido, "captura": self.miradas[i]})
        return True, _tr("Se lo mostré al usuario para que decida.")

    def _h_proponer_accion(self, a):
        accion = str(a.get("accion") or "")
        if accion not in ACCIONES:
            return False, _tr("Esa acción no se puede proponer aquí.")
        interp = {"accion": accion, "parametros": a.get("parametros") or {}, "entendido": ""}
        o, que, cons = self._en_ventana(lambda: self.win.orden_preparar(interp, self.datos))
        if o.error:
            return False, o.error
        self.propuestas.append({"tipo": "orden", "obj": o, "que": que, "cons": cons})
        return True, _tr("Se lo mostré al usuario para que decida.")


class AgenteMixin:
    _agente_sen = None
    _agente_mi = None

    def _agente_senal(self):
        if self._agente_sen is None:
            self._agente_sen = _Senales(self)
            self._agente_sen.puente.connect(self._agente_puente)
        return self._agente_sen

    def _agente_puente(self, fn, caja):
        """Método de la ventana, no función suelta: así Qt lo corre en su hilo y no en el de la IA."""
        try:
            caja["r"] = fn()
        except Exception as e:                         # noqa: BLE001 (se relanza en el hilo de la IA)
            caja["e"] = e
        caja["listo"].set()

    def agente_cliente(self, datos, cancelado):
        self._agente_senal()
        i = getattr(self, "sel_pipe", -1)
        sel = soluciones.codigo(self.pipes, i) if 0 <= i < len(self.pipes) else ""
        return ClienteVentana(datos, self, cancelado, sel)

    def agente_captura(self, i, margen):
        """(PNG, textos cercanos) de la utilidad i con la línea marcada, o None sin PDF."""
        doc = getattr(self, "doc", None)
        if doc is None or not self.zoom:
            return None
        from hoja import contexto_diametro, recorte_diametro
        page = doc[getattr(self, "page_idx", 0)]
        z = float(self.zoom)
        pts = [(x / z, y / z) for x, y in self.pipes[i]["pts"]]
        png = recorte_diametro.recorte(page, pts, {}, margen_pt=margen, trayecto_completo=True)
        return png, [t["texto"] for t in contexto_diametro.textos(page, pts, contexto_diametro.bloques(page))]

    def agente_zonas(self, i):
        return self._diam_ia_menu_zonas(self._diam_ia_ficha(i), True)

    def agente_ver_zona(self, i, zona):
        return self._diam_ia_ver_zona(i, self._diam_ia_ficha(i), zona)

    def _agente_marcas(self):
        if self._agente_mi is None:
            self._agente_mi = MarcasIA(self.canvas)
        return self._agente_mi

    def agente_senalar(self, idx):
        lineas = []
        for i in idx:
            pts = self._pipe_display_pts(self.pipes[i])
            lineas.append((pts, soluciones.codigo(self.pipes, i), pts[len(pts) // 2]))
        self._agente_marcas().poner(lineas)
        xs = [q[0] for pts, _e, _d in lineas for q in pts]
        ys = [q[1] for pts, _e, _d in lineas for q in pts]
        caja = QtCore.QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)).adjusted(-40, -40, 40, 40)
        self.canvas.fitInView(caja, QtCore.Qt.KeepAspectRatio)

    def agente_quitar_senales(self):
        self._agente_marcas().quitar()

    def _agente_todas(self):
        from ui.comun import rediseno as R
        out, vistas = [], set()
        for titulo, menu in getattr(self, "_menus", {}).items():
            for a in R.acciones_de(menu):
                if a.text() and a.isVisible() and a.isEnabled() and id(a) not in vistas:
                    vistas.add(id(a))
                    out.append((titulo, a.text().replace("&", ""), R.atajo_legible(a.shortcut()), a))
        return out

    def agente_funciones(self, texto):
        """Las funciones de la app que más se parecen a `texto`."""
        palabras = normalizar(texto).split()
        puntos = [(sum(p in normalizar(f[1]) for p in palabras), k, f) for k, f in enumerate(self._agente_todas())]
        return [f for n, _k, f in sorted(puntos, key=lambda x: (-x[0], x[1])) if n][:MAX_FUNCIONES]

    def agente_funcion(self, nombre):
        n = normalizar(nombre).strip()
        return next((f for f in self._agente_todas() if normalizar(f[1]).strip() == n), None)

    def agente_disponible(self):
        """¿Hay un modelo que sepa usar herramientas? Sin servidor, no."""
        from ia import proveedor as P
        prov = P.crear(self._config_ia())
        return bool(prov is not None and prov.herramientas())

    def agente_item(self, p):
        """(Item, Sugerencia) de una propuesta de diámetro: la misma tarjeta de la revisión."""
        from ia.diametro_ia import Sugerencia
        from nucleo import copiloto_cola as CC
        from nucleo.normas_validar import Aviso
        i = p["pipe"]
        pts = self.pipes[i]["pts"]
        x, y = pts[len(pts) // 2]
        a = next((a for a in getattr(self, "_normas_avisos", None) or [] if a.pipe == i and a.clase == diametro_plano.CLASE),
                 None) or Aviso(x, y, diametro_plano.CLASE, "", i)
        item = CC.Item(CC.clave_de(a, self.pipes), a, CC.PROPUESTA, etiqueta=soluciones.codigo(self.pipes, i))
        return item, Sugerencia(p["diam_in"], None, "media", p["evidencia"], origen="agente")

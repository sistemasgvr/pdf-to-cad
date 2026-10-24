"""El Informe automático redactado por la IA (PURO). Misma interfaz que la plantilla (`Redactor`): el Word no cambia.

`preparar(informe)` pide todo ANTES de escribir el Word, en paralelo y por lotes:
  - una petición por lote de ≤ `LOTE` fichas de una zona (la primera de la zona trae además su párrafo) y una para
    el resumen; con `Config.paralelo` pedidos a la vez;
  - la respuesta es JSON {"zona": …, "fichas": {ID: texto}}; cada texto se REVISA: no vacío, no muy largo y sin
    cifras que no estén en su ficha (`texto.no_respaldados`). Lo que no pasa → plantilla;
  - lo ya redactado queda en `redaccion.jsonl` de la memoria (clave = modelo + versión + idioma + ficha + notas del
    equipo): repetir el informe no vuelve a preguntar;
  - avisa «informe_ia» i de n (barra precisa) y se puede cancelar: lo que falte sale con la plantilla.

Más de `MAX_FICHAS_IA` fichas: las más graves con IA y el resto con plantilla (el informe dice cuántas).
"""
from __future__ import annotations

import concurrent.futures as cf
import hashlib
import json
import threading

from ia import proveedor as P
from ia.consulta import idioma
from ia.texto import leer_json, no_respaldados, numeros
from nucleo import avance
from nucleo.informe_redaccion import Redactor, RedactorPlantilla, consejo, datos_para_ia, nombre_utilidad
from traduccion.i18n_core import t

VERSION_PROMPT = 1
LOTE = 8
MAX_FICHAS_IA = 400
LARGO_MAX = 900
_ORDEN_NIVEL = {"ERROR": 0, "AVISO": 1, "INFO": 2}

SISTEMA = """Eres un ingeniero de redes de utilidades que redacta un informe técnico de revisión de un proyecto. \
Escribe en {idioma}, con tono profesional y claro.
Reglas:
1. Usa SOLO los datos de cada ficha y las indicaciones del equipo. No inventes normas, valores ni distancias.
2. No escribas ningún número que no esté en los datos de esa misma ficha.
3. Por ficha, de 1 a 3 frases: qué pasa, con qué utilidades (por su código, sin corchetes) y qué hacer (puedes \
apoyarte en la «sugerencia» de la app). No repitas la fuente ni la aprobación: la app las agrega.
4. Responde SOLO con JSON."""


def _clave(*partes):
    return hashlib.sha1(json.dumps(partes, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


class RedactorIA(Redactor):
    nombre = "ia"

    def __init__(self, proveedor, memoria=None, paralelo=2, max_fichas=MAX_FICHAS_IA):
        self.proveedor = proveedor
        self.memoria = memoria
        self.paralelo = max(1, paralelo)
        self.max_fichas = max_fichas
        self.respaldo = RedactorPlantilla()
        self._textos, self._zonas, self._resumen = {}, {}, None
        self._lock = threading.Lock()
        self._cancelado = False
        notas = [r.get("texto", "") for r in memoria.notas()] if memoria is not None else []
        self._notas = notas[-12:]
        self._base = (getattr(proveedor.config, "modelo", ""), VERSION_PROMPT, idioma(), self._notas)
        self.cuenta = {"ia": 0, "memoria": 0, "plantilla": 0, "revisadas": 0}
        self._total = 0
        self.error = ""

    # ── interfaz del Word ──
    def resumen(self, informe):
        return self._resumen or self.respaldo.resumen(informe)

    def zona(self, zona):
        return self._zonas.get(zona.numero) or self.respaldo.zona(zona)

    def ficha(self, f):
        txt = self._textos.get(f["id"])
        if not txt:
            return self.respaldo.ficha(f)
        # lo que es DATO (fuente de la regla, quién aprobó) va siempre, lo haya escrito la IA o no
        if f.get("fuente") and f["fuente"] not in txt:
            txt += " " + t("Fuente: {f}.").format(f=f["fuente"])
        ap = f.get("aprobado")
        if ap:
            txt += " " + t("Aprobado por {u} el {fecha}.").format(u=ap.get("usuario") or "?", fecha=ap.get("fecha") or "?")
            if ap.get("nota"):
                txt += " " + t("Nota: {nota}").format(nota=ap["nota"])
        return txt

    def cancelar(self):
        self._cancelado = True

    def nota(self):
        """Frase para el resumen del Word: quién redactó y cuántas fichas."""
        c = self.cuenta
        hechas = c["ia"] + c["memoria"]
        s = t("Redactado con IA ({m}): {n} fichas; con plantilla: {p}.").format(
            m=self.proveedor.config.modelo, n=hechas, p=max(0, self._total - hechas))
        if c["revisadas"]:
            s += " " + t("{n} textos de la IA no pasaron la revisión de cifras y salieron con plantilla.").format(
                n=c["revisadas"])
        if self.error:
            s += " " + t("La IA no respondió en parte: {e}").format(e=self.error)
        return s

    # ── preparar ──
    def verificar(self):
        """El servidor responde y tiene el modelo; si no, `ErrorIA` (quien llama usa la plantilla)."""
        instalados = self.proveedor.modelos()
        modelo = self.proveedor.config.modelo
        if instalados and modelo not in instalados:
            raise P.ErrorIA(t("el modelo «{m}» no está en el servidor").format(m=modelo))

    def preparar(self, informe, sin_red=False):
        """Redacta todo lo que falta. `sin_red` = el servidor no está: solo lo ya redactado (memoria)."""
        self._total = len(informe.fichas)
        fichas = sorted(informe.fichas, key=lambda f: (_ORDEN_NIVEL.get(f["nivel"], 3), bool(f.get("aprobado"))))
        con_ia = {f["id"] for f in fichas[:self.max_fichas]}
        tareas = [] if self._resumen_de_memoria(informe) else [("resumen", informe, None)]
        for z in informe.zonas:
            pend, primera = [], True
            for f in z.fichas:
                if f["id"] not in con_ia:
                    continue
                txt = self._de_memoria(f)
                if txt is not None:
                    self._textos[f["id"]] = txt
                    self.cuenta["memoria"] += 1
                else:
                    pend.append(f)
            zona_mem = self._de_memoria_zona(z)
            if zona_mem is not None:
                self._zonas[z.numero] = zona_mem
                primera = False
            for k in range(0, len(pend), LOTE) or ([0] if primera else []):
                tareas.append(("zona", z, (pend[k:k + LOTE], primera)))
                primera = False
        if sin_red:
            tareas = []
        n = len(tareas)
        avance.avisar("informe_ia", 0, n)
        hechas = 0
        with cf.ThreadPoolExecutor(max_workers=self.paralelo, thread_name_prefix="pdfcad-ia") as ex:
            futuros = [ex.submit(self._tarea, *tarea) for tarea in tareas]
            for fut in cf.as_completed(futuros):
                hechas += 1
                avance.avisar("informe_ia", hechas, n)
                try:
                    fut.result()
                except P.ErrorIA as e:
                    self.error = str(e)
                    self._cancelado = True              # el servidor no está: no seguir esperando pedido a pedido
                except Exception as e:                  # noqa: BLE001 (una respuesta rara no corta el informe)
                    self.error = str(e)
        self.cuenta["plantilla"] = self._total - self.cuenta["ia"] - self.cuenta["memoria"]
        return self.cuenta

    def _tarea(self, tipo, obj, extra):
        if self._cancelado:
            return
        if tipo == "resumen":
            self._pedir_resumen(obj)
        else:
            self._pedir_zona(obj, *extra)

    def _pedir(self, mensaje):
        r = self.proveedor.chat([{"role": "user", "content": mensaje}], sistema=SISTEMA.format(idioma=idioma()),
                                json=True, cancelado=lambda: self._cancelado)
        return leer_json(r.texto) or {}

    def _notas_txt(self):
        if not self._notas:
            return ""
        return t("Indicaciones del equipo para este proyecto:") + "\n" + "\n".join("- " + n for n in self._notas) + "\n\n"

    def _pedir_zona(self, z, fichas, con_zona):
        datos = []
        for f in fichas:
            d = json.loads(datos_para_ia(f))
            d["sugerencia"] = consejo(f)
            for u in d.get("utilidades") or []:
                u["utilidad"] = nombre_utilidad(u.get("capa", ""))
            datos.append(d)
        pide = t("Redacta las fichas de la zona {z}.").format(z=z.numero)
        forma = '{"fichas": {"ID": "texto"}}'
        if con_zona:
            pide += " " + t("Además, en «zona», 1 o 2 frases que resuman lo que hay en la zona {z} ({n} conflictos y "
                            "avisos en total).").format(z=z.numero, n=len(z.fichas))
            pide += "\n" + t("Contenido de la zona: {c}").format(c=json.dumps(_contenido(z), ensure_ascii=False))
            forma = '{"zona": "texto", "fichas": {"ID": "texto"}}'
        msg = (self._notas_txt() + pide + "\n" + t("Formato de respuesta: {f}").format(f=forma) + "\n" +
               t("Fichas:") + "\n" + "\n".join(json.dumps(d, ensure_ascii=False) for d in datos))
        r = self._pedir(msg)
        textos = r.get("fichas") if isinstance(r.get("fichas"), dict) else {}
        for f in fichas:
            txt = _limpio(textos.get(f["id"]))
            if txt and self._cifras_ok(txt, [datos_para_ia(f), consejo(f)]):
                self._guardar(f, txt)
            elif txt:
                with self._lock:
                    self.cuenta["revisadas"] += 1
        zt = _limpio(r.get("zona"))
        if con_zona and zt and self._cifras_ok(zt, [str(z.numero), str(len(z.fichas)),
                                                    json.dumps(_contenido(z))] + [datos_para_ia(f) for f in z.fichas]):
            self._zonas[z.numero] = zt
            if self.memoria is not None:
                self.memoria.guardar_redaccion(self._clave_zona(z), zt, self.proveedor.config.modelo)

    def _datos_resumen(self, informe):
        r = dict(informe.resumen)
        r["por_titulo"] = {tit: n for (_tipo, tit), n in r.get("por_titulo", [])}
        r["por_utilidad"] = {nombre_utilidad(c): n for c, n in r.get("por_utilidad", [])}
        r["zonas"] = len(informe.zonas)
        r["incluye"] = {"conflictos": informe.opciones.conflictos, "normativas": informe.opciones.normativas}
        datos = json.dumps(r, ensure_ascii=False)
        return datos, _clave("resumen", *self._base, datos)

    def _resumen_de_memoria(self, informe):
        _datos, clave = self._datos_resumen(informe)
        txt = self.memoria.redaccion(clave) if self.memoria is not None else None
        if txt:
            self._resumen = txt
        return bool(txt)

    def _pedir_resumen(self, informe):
        datos, clave = self._datos_resumen(informe)
        msg = (self._notas_txt() + t("Redacta el resumen ejecutivo del informe (3 a 5 frases) con estos conteos.") +
               "\n" + t("Formato de respuesta: {f}").format(f='{"resumen": "texto"}') + "\n" + datos)
        txt = _limpio(self._pedir(msg).get("resumen"))
        if txt and self._cifras_ok(txt, [datos]):
            self._resumen = txt
            if self.memoria is not None:
                self.memoria.guardar_redaccion(clave, txt, self.proveedor.config.modelo)

    # ── revisar y recordar ──
    @staticmethod
    def _cifras_ok(texto, fuentes):
        conocidos = [v for s in fuentes for v in numeros(s)]
        return not no_respaldados(texto, conocidos)

    def _clave_ficha(self, f):
        return _clave("ficha", *self._base, datos_para_ia(f))

    def _clave_zona(self, z):
        return _clave("zona", *self._base, z.numero, [datos_para_ia(f) for f in z.fichas])

    def _de_memoria(self, f):
        return self.memoria.redaccion(self._clave_ficha(f)) if self.memoria is not None else None

    def _de_memoria_zona(self, z):
        return self.memoria.redaccion(self._clave_zona(z)) if self.memoria is not None else None

    def _guardar(self, f, txt):
        with self._lock:
            self._textos[f["id"]] = txt
            self.cuenta["ia"] += 1
        if self.memoria is not None:
            self.memoria.guardar_redaccion(self._clave_ficha(f), txt, self.proveedor.config.modelo)


def _contenido(z):
    """Lo que hay en la zona, contado (para su párrafo): cuántos de cada clase y qué utilidades."""
    por, utils = {}, {}
    for f in z.fichas:
        por[f["titulo"]] = por.get(f["titulo"], 0) + 1
        for u in f.get("utilidades") or []:
            utils[u["codigo"]] = nombre_utilidad(u.get("capa", ""))
    return {"por_clase": por, "utilidades": utils}


def _limpio(v):
    if not isinstance(v, str):
        return ""
    s = " ".join(v.replace("[", "").replace("]", "").split())
    return s if 0 < len(s) <= LARGO_MAX else ""


def crear(config, memoria=None):
    """(redactor, motivo), SIN tocar la red: con IA si está configurada (quien lo usa llama `verificar` en otro
    hilo); si no, la plantilla y por qué (el motivo va en el resumen del Word)."""
    c = config if isinstance(config, P.Config) else P.Config.de(config)
    if not c.con_ia:
        return RedactorPlantilla(), ""
    prov = P.crear(c)
    if prov is None:
        return RedactorPlantilla(), t("La redacción con IA («{p}») aún no está disponible: se usaron plantillas.").format(
            p=c.proveedor)
    return RedactorIA(prov, memoria, c.paralelo), ""

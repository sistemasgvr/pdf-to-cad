"""Los datos REALES del proyecto para la IA (PURO): lo único que puede citar.

`DatosProyecto(pipes, fichas, ft_per_px)` arma UNA vez (la ventana lo guarda mientras el modelo no cambie):
  - un RESUMEN por utilidad (cantidad, largo, diámetros, tipos, materiales, abandonadas) y de conflictos/avisos;
  - una línea compacta por utilidad («AGUA-5 | Agua | DISTRIBUCION PRINCIPAL | Ø 8 in | …») y por ficha
    («C-12 | Cruce sin conexión | AGUA-5 (cota 101.2 ft) × DRENAJE-3 (…) | diferencia 0.4 ft | zona 3»);
  - `refs`: cada código (C-12, N-3, AGUA-5) → dónde está en el plano, para que la respuesta lleve al lugar.

`seleccionar(pregunta)` elige qué líneas van en el pedido: los códigos que nombra, la zona, las utilidades y las
palabras en común (cruce, pendiente, diámetro…). Con miles de utilidades nunca va todo: el resumen responde los
totales y la selección el detalle. Más adelante, con Claude, estas mismas funciones pueden ser «herramientas» que
la IA llama sola (ver `docs/pendientes_ia.md`).
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from ia.texto import normalizar, raices
from nucleo import informe_datos, model, model_ops
from nucleo.informe_redaccion import nombre_utilidad
from traduccion.i18n_core import t

MAX_FICHAS = 40
MAX_UTILIDADES = 40
_CODIGO = re.compile(r"\b([a-z]+)-(\d+)\b")
_ZONA = re.compile(r"\bzonas?\s+(\d+)")
# otras formas de nombrar cada utilidad (además del nombre de la app y su código)
SINONIMOS = {"AGUA": ("agua", "potable", "water"), "ALCANTARILLADO": ("alcantarillado", "desague", "sanitario",
             "sewer", "cloaca"), "DRENAJE": ("drenaje", "pluvial", "storm"), "GAS": ("gas",),
             "ELECTRICO": ("electrico", "electrica", "electricas", "electricos", "energia", "electrical"),
             "TELECOM": ("telecom", "telecomunicaciones", "comunicaciones", "fibra", "telefonia")}


def _n(v, dec=2):
    if v is None:
        return "?"
    s = f"{float(v):.{dec}f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


@dataclass
class Linea:
    codigo: str
    texto: str
    raices: set
    capa: str = ""
    zona: int | None = None
    nivel: str = ""
    utilidades: tuple = ()


@dataclass
class DatosProyecto:
    pipes: list
    fichas: list
    ft_per_px: float
    titulo: str = ""
    utilidades: list = field(default_factory=list)     # Linea por utilidad
    lineas_fichas: list = field(default_factory=list)  # Linea por conflicto/aviso
    refs: dict = field(default_factory=dict)            # código → {objeto, indice, x, y}
    resumen: str = ""

    @classmethod
    def armar(cls, pipes, fichas, ft_per_px, titulo=""):
        d = cls(pipes, fichas, ft_per_px or 0.0, titulo)
        d._armar_utilidades()
        d._armar_fichas()
        d.resumen = d._resumen()
        return d

    # ── líneas ──
    def _armar_utilidades(self):
        ft = self.ft_per_px
        for i, p in enumerate(self.pipes):
            pts = p.get("pts") or []
            if p.get("world") or len(pts) < 2:
                continue
            u = informe_datos.utilidad(self.pipes, i)
            partes = [u["codigo"], nombre_utilidad(u["capa"])]
            if u["nombre"]:
                partes.append(t("nombre «{n}»").format(n=u["nombre"]))
            partes.append(u["tipo"] or t("sin tipo"))
            partes.append(t("Ø {d} in").format(d=_n(model_ops.diametro(p)[0])))
            if u["material"] and u["material"] != model.DEFAULT_PIPE_MATERIAL:
                partes.append(u["material"])
            if ft:
                partes.append(t("largo {l} ft").format(l=_n(model_ops.largo_planta_ft(p, ft), 1)))
            if p.get("inv_start") is not None or p.get("inv_end") is not None:
                partes.append(t("cotas {a} → {b} ft").format(a=_n(p.get("inv_start")), b=_n(p.get("inv_end"))))
                pend = model_ops.pendiente_total(p, ft) if ft else None
                if pend is not None:
                    partes.append(t("pendiente {s} %").format(s=_n(pend, 3)))
            if p.get("ab"):
                partes.append(t("abandonada"))
            texto = " | ".join(partes)
            self.utilidades.append(Linea(u["codigo"], texto, raices(texto) | raices(" ".join(
                SINONIMOS.get(u["capa"], ()))), u["capa"]))
            x, y = pts[len(pts) // 2]
            self.refs[normalizar(u["codigo"])] = {"objeto": "pipe", "indice": i, "x": float(x), "y": float(y)}

    def _armar_fichas(self):
        for f in self.fichas:
            us = []
            for u in f.get("utilidades") or []:
                s = f"{u['codigo']} ({nombre_utilidad(u['capa'])}"
                if u.get("tipo"):
                    s += ", " + u["tipo"]
                if u.get("diametro_in"):
                    s += ", Ø " + _n(u["diametro_in"]) + " in"
                if u.get("cota_ft") is not None:
                    s += ", " + t("cota {z} ft").format(z=_n(u["cota_ft"]))
                us.append(s + ")")
            partes = [f["id"], f["titulo"], f["nivel"]]
            if us:
                partes.append(" × ".join(us))
            for k, v in (f.get("valores") or {}).items():
                if v is not None:
                    partes.append(t("diferencia {v} ft").format(v=_n(v)) if k == "diferencia_ft" else f"{k} {v}")
            if f.get("zona"):
                partes.append(t("zona {z}").format(z=f["zona"]))
            partes.append(t("aprobado") if f.get("aprobado") else t("informativo") if f.get("info")
                          else t("pendiente"))
            if f.get("mensaje_app"):
                partes.append(" ".join(str(f["mensaje_app"]).split()))
            if f.get("fuente"):
                partes.append(t("fuente: {f}").format(f=f["fuente"]))
            texto = " | ".join(partes)
            capas = tuple(sorted({u["capa"] for u in f.get("utilidades") or []}))
            sin = " ".join(s for c in capas for s in SINONIMOS.get(c, ()))
            self.lineas_fichas.append(Linea(f["id"], texto, raices(texto + " " + sin + " " + f.get("clase", "")),
                                            zona=f.get("zona"), nivel=f["nivel"],
                                            utilidades=tuple(u["codigo"] for u in f.get("utilidades") or [])))
            self.refs[normalizar(f["id"])] = {"objeto": f["tipo"], "indice": -1, "x": f["x"], "y": f["y"]}

    def _resumen(self):
        ft = self.ft_per_px
        por = {}
        for i, p in enumerate(self.pipes):
            if p.get("world") or len(p.get("pts") or []) < 2:
                continue
            c = por.setdefault(p.get("layer") or "?", {"n": 0, "largo": 0.0, "diam": Counter(), "tipo": Counter(),
                                                       "mat": Counter(), "ab": 0})
            c["n"] += 1
            c["largo"] += model_ops.largo_planta_ft(p, ft) if ft else 0.0
            c["diam"][_n(model_ops.diametro(p)[0])] += 1
            c["tipo"][(p.get("tipo") or "").strip() or t("sin tipo")] += 1
            mat = (p.get("material") or "").strip()
            if mat and mat != model.DEFAULT_PIPE_MATERIAL:
                c["mat"][mat] += 1
            c["ab"] += 1 if p.get("ab") else 0
        lineas = [t("Proyecto: {p}").format(p=self.titulo)] if self.titulo else []
        lineas.append(t("Unidades: pies (ft); diámetros en pulgadas (in)."))
        lineas.append(t("Utilidades: {n}.").format(n=sum(c["n"] for c in por.values())))
        orden = {c: k for k, (_l, c) in enumerate(model.TIPOS)}
        for capa, c in sorted(por.items(), key=lambda kv: orden.get(kv[0], 99)):
            def top(cnt, suf=""):
                return ", ".join(f"{k}{suf}: {v}" for k, v in cnt.most_common(8))
            s = t("{u} ({c}): {n} utilidades").format(u=nombre_utilidad(capa), c=capa, n=c["n"])
            if ft:
                s += "; " + t("largo total {l} ft").format(l=_n(c["largo"], 1))
            s += "; " + t("diámetros (in) {d}").format(d=top(c["diam"]))
            s += "; " + t("tipos {t}").format(t=top(c["tipo"]))
            if c["mat"]:
                s += "; " + t("materiales {m}").format(m=top(c["mat"]))
            if c["ab"]:
                s += "; " + t("abandonadas {a}").format(a=c["ab"])
            lineas.append(s + ".")
        conf = [f for f in self.fichas if f["tipo"] == "conflicto"]
        avis = [f for f in self.fichas if f["tipo"] == "aviso"]
        lineas.append(t("Conflictos (C-n): {n}.").format(n=len(conf)) + (" " + _conteo(conf) if conf else ""))
        lineas.append(t("Avisos de normativa (N-n): {n} (pendientes {p}, aprobados {a}, informativos {i}).").format(
            n=len(avis), p=sum(1 for f in avis if not f.get("aprobado") and not f.get("info")),
            a=sum(1 for f in avis if f.get("aprobado")), i=sum(1 for f in avis if f.get("info") and not
                                                               f.get("aprobado"))) + (" " + _conteo(avis) if avis else ""))
        zonas = Counter(f.get("zona") for f in self.fichas if f.get("zona"))
        if zonas:
            lineas.append(t("Zonas: {z}.").format(z=", ".join(t("zona {z} ({n})").format(z=z, n=n)
                                                              for z, n in sorted(zonas.items()))))
        return "\n".join(lineas)

    # ── selección ──
    def seleccionar(self, pregunta, max_fichas=MAX_FICHAS, max_utilidades=MAX_UTILIDADES):
        """(líneas de fichas, líneas de utilidades) que van en el pedido para esta pregunta."""
        q = normalizar(pregunta)
        codigos = {f"{a}-{b}" for a, b in _CODIGO.findall(q)}
        zonas = {int(z) for z in _ZONA.findall(q)}
        capas = {c for c, sin in SINONIMOS.items() if any(re.search(rf"\b{s}", q) for s in sin)}
        qr = raices(pregunta)

        def puntos(ln):
            s = 0.0
            if normalizar(ln.codigo) in codigos:
                s += 100
            if any(normalizar(u) in codigos for u in ln.utilidades):
                s += 50
            if ln.zona in zonas:
                s += 30
            s += len(qr & ln.raices)
            return s

        fichas = sorted(((puntos(ln), -k, ln) for k, ln in enumerate(self.lineas_fichas)), key=lambda x: x[:2],
                        reverse=True)
        elegidas = [ln for s, _k, ln in fichas if s >= 2 or not (codigos or zonas or capas)][:max_fichas]
        if capas:
            elegidas = [ln for ln in elegidas if not ln.raices.isdisjoint(_raices_capas(capas)) or
                        normalizar(ln.codigo) in codigos][:max_fichas]
        nombradas = codigos | {normalizar(u) for ln in elegidas for u in ln.utilidades}
        utils = [ln for ln in self.utilidades if normalizar(ln.codigo) in nombradas]
        if len(utils) < max_utilidades and (capas or not codigos):
            # de la utilidad nombrada, las que más palabras comparten con la pregunta; sin utilidad nombrada,
            # solo las que comparten al menos dos (el resumen ya da los totales)
            ya = {id(ln) for ln in utils}
            extra = sorted(((len(qr & ln.raices), -k, ln) for k, ln in enumerate(self.utilidades)
                            if (not capas or ln.capa in capas) and id(ln) not in ya), key=lambda x: x[:2],
                           reverse=True)
            utils += [ln for s, _k, ln in extra if capas or s >= 2][:max_utilidades - len(utils)]
        return elegidas, utils[:max_utilidades]

    def ref(self, codigo):
        return self.refs.get(normalizar(codigo))


def _raices_capas(capas):
    return raices(" ".join(s for c in capas for s in SINONIMOS.get(c, ())))


def _conteo(fichas):
    c = Counter(f["titulo"] for f in fichas)
    return t("Por clase: {c}.").format(c=", ".join(f"{k}: {v}" for k, v in c.most_common()))


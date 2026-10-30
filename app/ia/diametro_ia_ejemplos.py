"""Ejemplos resueltos para la petición de `ia/diametro_ia` (few-shot). Casos tipo de DU06 revisados a la vista:
el rótulo cuya guía llega a la línea; un rótulo de OTRA utilidad pegado a la línea; un número de nota en una caja
que no es diámetro (la app no lo lee como diámetro: el caso es «nada sirve» → null). Mismo formato que
`diametro_ia.ficha`; las respuestas en español (el modelo las imita en el idioma pedido)."""


def _rot(id_, texto, d, util="", material="", guia="esta", dist=0.0, otra=None, **k):
    return dict(id=id_, texto=texto, diam_in=d, material=material, util=util, es_de=True, dist_pt=dist,
                guia=guia, otra=otra, caja=[0, 0, 0, 0], estacion=False, union=False, varios=1, normativa=True, **k)


def _ficha(util, nombre, capa, rotulos, estado=""):
    return dict(utilidad=util, utilidad_nombre=nombre, capa=capa, sistema="", estado_capa=estado, abandonada=False,
                largo_ft=None, por_defecto_in=12.0, estado_plano="sin_dato", paredes_in=None, perfil_in=[],
                rotulos=rotulos)


EJEMPLOS = [
    (_ficha("DRENAJE", "Drenaje", "16000-A1-UD-REF-EXIST_SD|C-STRM-UNGD-E", [
        _rot("R1", 'LAT CB-226 / 18" RCP', 18.0, material="RCP", dist=2.1),
        _rot("R2", 'EX. 84" RCP SD, LACFCD', 84.0, util="DRENAJE", material="RCP", guia="otra", dist=35.0,
             otra={"utilidad": "DRENAJE", "capa": "C-STRM-UNGD-E", "dist_pt": 0.8}),
    ], "E · Existente"),
     {"rotulo": "R1", "confianza": "alta",
      "motivo": "La guía del rótulo R1 llega a esta línea; R2 apunta a la tubería principal.", "pista": None}),
    (_ficha("AGUA", "Agua", "16000-A1-UW-REF-EXIST_WATER|C-WATR-UNGD-E", [
        _rot("R1", '84" RCP SD, LACFCD / REMAIN IN PLACE', 84.0, util="DRENAJE", material="RCP", guia="sin",
             dist=6.0),
    ], "E · Existente"),
     {"rotulo": None, "confianza": "alta",
      "motivo": "El único rótulo cercano es de drenaje (SD), no de esta línea de agua.",
      "pista": "Revisar el perfil o el plano de agua."}),
    (_ficha("AGUA", "Agua", "16000-A1-UW-REF-EXIST_WATER|C-WATR-UNGD-A", [
        _rot("R1", 'PROP 8" WA', 8.0, util="AGUA", guia="otra", dist=40.0,
             otra={"utilidad": "AGUA", "capa": "C-WATR-UNGD-N", "dist_pt": 1.2}),
        _rot("R2", '12" W', 12.0, util="AGUA", guia="nada", dist=55.0),
    ], "A · Abandonada"),
     {"rotulo": None, "confianza": "alta",
      "motivo": "R1 llega a la línea propuesta, no a esta; R2 no llega a ninguna línea.", "pista": None}),
]
for _f, _r in EJEMPLOS:                 # el rótulo que nombra otra utilidad no es de ésta
    for _e in _f["rotulos"]:
        if _e["util"] and _e["util"] != _f["utilidad"]:
            _e["es_de"] = False

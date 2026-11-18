"""Descarga el índice de cuartos de sección (QS) de la ciudad de Phoenix y lo guarda como datos de la app
(`app/geo/indices/phoenix_qs.json.gz`). La app NUNCA consulta la red: este script se corre a mano cuando la
ciudad cambie la capa (2026-11-18, georreferencia automática, `app/geo/auto/`).

    python scripts/datos/indice_phoenix_qs.py
"""
import datetime
import gzip
import json
import os
import urllib.parse
import urllib.request

URL = "https://maps.phoenix.gov/pub/rest/services/Public/STR_QSMapIndex/MapServer/0/query"
CAMPOS = "TILE,PLS_TOWNSHIP,PLS_RANGE,PLS_SECTION,QTR_SECTION"
SALIDA = os.path.join(os.path.dirname(__file__), "..", "..", "app", "geo", "indices", "phoenix_qs.json.gz")


def _pagina(desde):
    q = urllib.parse.urlencode(dict(where="1=1", outFields=CAMPOS, returnGeometry="true", outSR=2868,
                                    resultOffset=desde, resultRecordCount=1000, orderByFields="OBJECTID", f="json"))
    with urllib.request.urlopen(URL + "?" + q, timeout=60) as r:
        return json.load(r).get("features", [])


def main():
    celdas, desde = {}, 0
    while True:
        fs = _pagina(desde)
        if not fs:
            break
        for f in fs:
            a = f["attributes"]
            t = (a.get("TILE") or "").strip()
            if not t:
                continue
            anillo = f["geometry"]["rings"][0]
            if anillo[0] == anillo[-1]:
                anillo = anillo[:-1]
            celdas[t] = {"p": [[round(x, 2), round(y, 2)] for x, y in anillo],
                         "plss": [a["PLS_TOWNSHIP"].strip(), a["PLS_RANGE"].strip(), int(a["PLS_SECTION"]),
                                  a["QTR_SECTION"].strip()]}
        desde += len(fs)
    datos = {"id": "phoenix_qs", "nombre": "City of Phoenix — Quarter Section", "epsg": 2868,
             "palabras": ["CITY OF PHOENIX"],
             # ancho en el mundo del recuadro del mapa de cada hoja QS (medido 2026-11-18: 2 797–2 801 ft en Water
             # y Sewer de Indian School): da la escala de la hoja, la del cajetín es la del plano SIN reducir
             "recuadro_ft": 2800.0, "fecha": datetime.date.today().isoformat(),
             "fuente_url": URL.rsplit("/query", 1)[0], "celdas": celdas}
    with gzip.open(SALIDA, "wt", encoding="utf-8") as f:
        json.dump(datos, f, separators=(",", ":"))
    print(len(celdas), "celdas ->", os.path.abspath(SALIDA))


if __name__ == "__main__":
    main()

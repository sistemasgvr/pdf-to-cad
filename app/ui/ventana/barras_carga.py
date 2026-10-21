"""Las barras de carga PRECISAS de los trabajos largos (pedido del usuario 2026-10-20): abrir y guardar el
proyecto, «Revisar y limpiar el dibujo», la Tabla de datos y su Excel. Cada una es una
`ui/comun/barra_pesada.AvancePesado` con sus etapas, sus textos y lo que tarda cada unidad (ms, medido con
AGUA 2: 16 762 utilidades, hoja de 115 Mpx, 64 MB entre imagen y PDF).
"""
from __future__ import annotations

import os
import struct
import zipfile

from traduccion.i18n_core import N_
from ui.comun.barra_pesada import AvancePesado

# ── abrir / guardar el proyecto ──
MS_POR_MB_LEER = 6.6                   # leer el .digproj (descomprimir)
MS_POR_MPX_HOJA = 18.7                 # decodificar la imagen de la hoja (PNG)
MS_POR_MPX_GRIS = 7.2                  # su copia en grises (el imán a la tinta)
MS_POR_UTIL_MODELO = 0.02              # leer / armar los datos
MS_POR_UTIL_LISTAS = 0.036             # las listas del panel
MS_POR_UTIL_DIBUJO = 0.09              # dibujar el plano
MS_BASE_DIBUJO = 300.0
MS_POR_MPX_PNG = 43.0                  # codificar la imagen de la hoja (solo si cambió)
MS_POR_MB_PDF = 170.0                  # el PDF de trabajo como bytes
MS_POR_MB_ZIP = 58.0                   # comprimir y escribir el .digproj
MB = 1e6

TEXTOS_ARCHIVO = {
    "leer": N_("Leyendo el archivo: {i} de {n} bytes"),
    "hoja": N_("Preparando la imagen de la hoja…"),
    "gris": N_("Preparando la hoja para el imán…"),
    "modelo": N_("Leyendo las utilidades…"),
    "listas": N_("Armando las listas…"),
    "dibujo": N_("Dibujando el plano…"),
    "datos": N_("Juntando los datos del proyecto…"),
    "imagen": N_("Guardando la imagen de la hoja…"),
    "pdf": N_("Guardando el PDF…"),
    "comprimir": N_("Comprimiendo el proyecto: {i} de {n} bytes"),
}


# ── revisar y limpiar el dibujo (ms por utilidad) ──
MS_LIMPIEZA = {"copiar": 0.07, "duplicadas": 0.036, "cortas": 0.005, "puntas": 0.125, "tramos": 0.046,
               "sueltas": 0.057}
_ETAPA_DE_TIPO = {"duplicada": "duplicadas", "corta": "cortas", "punta": "puntas", "tramo": "tramos",
                  "suelta": "sueltas"}
TEXTOS_LIMPIEZA = {
    "copiar": N_("Preparando la revisión…"),
    "duplicadas": N_("Buscando utilidades repetidas: {i} de {n}"),
    "cortas": N_("Buscando utilidades muy cortas…"),
    "puntas": N_("Revisando las puntas: {i} de {n}"),
    "tramos": N_("Revisando tramos diminutos: {i} de {n}"),
    "sueltas": N_("Buscando utilidades sueltas: {i} de {n}"),
}


def limpieza(host, n_utilidades, tipos, copiar):
    """Barra para revisar (`copiar`: sobre una copia) o arreglar el dibujo con esos `tipos`."""
    etapas = {_ETAPA_DE_TIPO[t] for t in tipos if t in _ETAPA_DE_TIPO} | ({"copiar"} if copiar else set())
    partes = {e: n_utilidades * MS_LIMPIEZA[e] for e in MS_LIMPIEZA if e in etapas}   # en el orden en que se hacen
    return AvancePesado(host, partes, TEXTOS_LIMPIEZA)


# ── Tabla de datos y su Excel ──
MS_TABLA = {"tabla_utilidades": 0.092, "tabla_vertices": 0.06}      # por utilidad
MS_POR_CELDA_TABLA = 0.016             # crear cada celda de la ventana
MS_POR_FILA_ORDENAR = 0.014            # ordenar (compara números como números)
MS_POR_FILA_COLUMNAS = 0.007           # ajustar el ancho de las columnas
MS_EXCEL_FILA = 0.026
MS_EXCEL_CELDA_VERDE = 0.047
MS_EXCEL_CELDA_GUARDAR = 0.0138
TEXTOS_TABLA = {
    "tabla_utilidades": N_("Juntando los datos: {i} de {n} utilidades"),
    "tabla_vertices": N_("Juntando las cotas por vértice: {i} de {n} utilidades"),
    "celdas": N_("Armando la tabla: {i} de {n} filas"),
    "ordenar": N_("Ordenando la tabla: {i} de {n} filas"),
    "columnas": N_("Ajustando las columnas: {i} de {n} filas"),
    "excel_filas": N_("Escribiendo el Excel: {i} de {n} filas"),
    "excel_formato": N_("Marcando las columnas editables: {i} de {n} celdas"),
    "excel_guardar": N_("Guardando el Excel: {i} de {n} filas"),
}


def tabla(host, n_utilidades):
    """Barra de la Tabla de datos: datos (en otro hilo) y la ventana; `celdas_tabla` corrige con lo real."""
    filas = n_utilidades * 2.6                                # estimado (utilidades + avisos + vértices)
    partes = {k: n_utilidades * ms for k, ms in MS_TABLA.items()}
    partes.update(celdas=filas * 16 * MS_POR_CELDA_TABLA, ordenar=filas * MS_POR_FILA_ORDENAR,
                  columnas=filas * MS_POR_FILA_COLUMNAS)
    return AvancePesado(host, partes, TEXTOS_TABLA)


def celdas_tabla(tablas):
    filas = sum(len(tb.filas) for tb in tablas)
    celdas = sum(len(tb.filas) * len(tb.columnas) for tb in tablas)
    return {"celdas": celdas * MS_POR_CELDA_TABLA, "ordenar": filas * MS_POR_FILA_ORDENAR,
            "columnas": filas * MS_POR_FILA_COLUMNAS}


def excel(host, tablas, editables):
    """Barra del Excel de la Tabla de datos (`editables` = `tabla_excel.EDITABLES`)."""
    filas = sum(len(tb.filas) for tb in tablas)
    verdes = sum(len(tb.filas) * len(editables.get(tb.clave, {})) for tb in tablas)
    celdas = sum(len(tb.filas) * len(tb.columnas) for tb in tablas)
    partes = {"excel_filas": filas * MS_EXCEL_FILA, "excel_formato": verdes * MS_EXCEL_CELDA_VERDE,
              "excel_guardar": celdas * MS_EXCEL_CELDA_GUARDAR}
    return AvancePesado(host, partes, TEXTOS_TABLA)


def _mpx_png(png_head):
    try:
        w, h = struct.unpack(">II", png_head[16:24])
        return w * h / 1e6
    except struct.error:
        return 0.0


def abrir_proyecto(host, ruta):
    """Barra para abrir el .digproj `ruta` (estimada con lo que dice el zip, sin leerlo entero)."""
    mb, mpx, n = 0.0, 0.0, 0
    try:
        with zipfile.ZipFile(ruta) as z:
            mb = sum(i.file_size for i in z.infolist()) / MB
            with z.open("page.png") as f:
                mpx = _mpx_png(f.read(24))
            n = max(1, z.getinfo("model.json").file_size // 550)     # ~550 bytes de JSON por utilidad
    except (OSError, KeyError, zipfile.BadZipFile):
        pass
    partes = {"leer": mb * MS_POR_MB_LEER, "hoja": mpx * MS_POR_MPX_HOJA, "gris": mpx * MS_POR_MPX_GRIS,
              "modelo": n * MS_POR_UTIL_MODELO, "listas": n * MS_POR_UTIL_LISTAS,
              "dibujo": MS_BASE_DIBUJO + n * MS_POR_UTIL_DIBUJO}
    return AvancePesado(host, partes, TEXTOS_ARCHIVO)


def guardar_proyecto(host, n_utilidades, mpx_hoja, png_nuevo, mb_pdf, mb_otros):
    """Barra para guardar: datos, imagen (solo si cambió), PDF y comprimir."""
    partes = {"datos": n_utilidades * MS_POR_UTIL_MODELO * 2,
              "imagen": mpx_hoja * MS_POR_MPX_PNG if png_nuevo else 0.0,
              "pdf": mb_pdf * MS_POR_MB_PDF,
              "comprimir": (mb_pdf + mb_otros + n_utilidades * 550 / MB) * MS_POR_MB_ZIP}
    return AvancePesado(host, partes, TEXTOS_ARCHIVO)


def tam_mb(ruta):
    try:
        return os.path.getsize(ruta) / MB if ruta and os.path.isfile(ruta) else 0.0
    except OSError:
        return 0.0

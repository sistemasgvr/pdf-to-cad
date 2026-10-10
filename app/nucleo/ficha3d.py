"""Ficha de atributos del objeto elegido en la Vista 3D (PURO: sin Qt).

Una lista corta de (campo, valor) para mostrar en la tabla de la ventana 3D. Las
utilidades y los buzones salen de las MISMAS tablas que «Tabla de datos»
(`tabla_datos.armar`), así los valores coinciden; se omiten las coordenadas y lo
vacío, y se suman la pendiente y los avisos. Los accesorios salen del modelo 3D.
Los campos son claves en español (N_) que la interfaz traduce al mostrar.
"""
from __future__ import annotations

from nucleo import accesorios as acc
from nucleo import model_ops
from nucleo.normas_validar import NOMBRE_ACC
from traduccion.i18n_core import N_, t

OMITIR = {N_("N°"), N_("Inicio X"), N_("Inicio Y"), N_("Fin X"), N_("Fin Y"), N_("Vértices"), N_("X"), N_("Y"),
          N_("Nombre"), N_("Código")}


def _fila(tabla, objeto, indice):
    for fila, lugar in zip(tabla.filas, tabla.lugares):
        if lugar and lugar[2] == objeto and lugar[3] == indice:
            return dict(zip(tabla.columnas, fila))
    return None


def _valor(v):
    if isinstance(v, float):
        return f"{v:,.3f}".rstrip("0").rstrip(".")
    return str(v)


def _limpias(d):
    return [(c, _valor(v)) for c, v in d.items() if c not in OMITIR and v not in (None, "")]


def _avisos(avisos, pipes_idx, x=None, y=None, tol=None):
    """Mensajes de los avisos (no informativos) de esas utilidades (o de ese punto)."""
    out = []
    for a in avisos or []:
        if a.get("info") or a.get("pipe") not in pipes_idx:
            continue
        if tol is not None and ((a["x"] - x) ** 2 + (a["y"] - y) ** 2) > tol * tol:
            continue
        out.append(a.get("mensaje", ""))
    return out


def de_utilidad(tablas, pipes, avisos, i):
    """(título, [(campo, valor)]) de la utilidad i."""
    d = _fila(tablas[0], "pipe", i)
    if d is None or not (0 <= i < len(pipes)):
        return "", []
    p = pipes[i]
    titulo = f"#{i + 1} {d.get(N_('Nombre')) or ''}".strip()
    filas = _limpias(d)
    largo = d.get(N_("Largo (ft)"))
    zs, ze = p.get("inv_start"), p.get("inv_end")
    if largo and zs is not None and ze is not None:
        filas.append((N_("Pendiente (%)"), _valor(round((float(ze) - float(zs)) / float(largo) * 100.0, 3))))
    filas = [(c, v) for c, v in filas if c != N_("Avisos")]
    for m in _avisos(avisos, {i}):
        filas.append((N_("Aviso"), m))
    return titulo, filas


def de_estructura(tablas, s_idx, z0=None, z1=None):
    """(título, [(campo, valor)]) del buzón, caja o sólido."""
    d = _fila(tablas[1], "struct", s_idx)
    if d is None:
        return "", []
    filas = _limpias(d)
    if z0 is not None and not d.get(N_("Fondo (ft)")):
        filas.append((N_("Fondo en 3D (ft)"), _valor(round(z0, 3))))
    if z1 is not None and not d.get(N_("Tapa (ft)")):
        filas.append((N_("Tapa en 3D (ft)"), _valor(round(z1, 3))))
    return str(d.get(N_("Código")) or ""), filas


def de_accesorio(obj, pipes, avisos, nombre_utilidad=lambda c: c, tol_px=None):
    """(título, [(campo, valor)]) de un accesorio del modelo 3D (`modelo3d.objetos`)."""
    nombre = t(NOMBRE_ACC.get(obj.get("acc_tipo"), N_("Accesorio")))
    ang = obj.get("angulo")
    titulo = f"{nombre} {acc.texto_angulo(ang)}" if ang is not None else nombre
    une = [i for i in obj.get("pipes") or [] if 0 <= i < len(pipes)]
    filas = [(N_("Accesorio"), nombre)]
    if ang is not None:
        filas.append((N_("Ángulo"), acc.texto_angulo(ang)))
    filas.append((N_("Utilidad"), nombre_utilidad(obj.get("capa") or "")))
    if une:
        filas.append((N_("Une las utilidades"), ", ".join(f"#{i + 1}" for i in une)))
        filas.append((N_("Diámetros"), " × ".join(f'{model_ops.diametro(pipes[i])[0]:g}"' for i in une)))
    if obj.get("eje_z") is not None:
        filas.append((N_("Cota del eje (ft)"), _valor(round(obj["eje_z"], 3))))
    for m in _avisos(avisos, set(une), obj.get("x"), obj.get("y"), tol_px):
        filas.append((N_("Aviso"), m))
    return titulo, filas

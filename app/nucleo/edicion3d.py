"""Cambios de cota y diámetro de UNA utilidad, como los hace el panel del plano (PURO: sin Qt).

Los usa la edición desde la Vista 3D (`ui/ventana/ventana_edicion3d`) sobre la utilidad del proyecto y,
para la vista previa inmediata, sobre una COPIA (`ui/dialogos/vista3d_editor`): mismo cambio en los dos.
"""
from __future__ import annotations

from nucleo import model_ops
from nucleo.edicion_bloque import diam_de_tamano


def aplicar_cota(p, tramo, lado, valor):
    """Cota del `lado` («inicio»/«fin») del `tramo` de `p` (en sitio). Rasantes = `inv_start`/`inv_end`;
    una intermedia = salida/llegada de su vértice, con las demás congeladas antes (`snapshot_seg_values`) y la
    edición por tramo activada, como el botón del plano. Devuelve True si cambió."""
    n = len(p.get("pts") or [])
    if not 0 <= tramo < n - 1:
        return False
    actual = (model_ops.cotas_tramo(p, tramo) or (0.0, 0.0))[0 if lado == "inicio" else 1]
    if abs(float(actual) - float(valor)) < 1e-9:
        return False
    if lado == "inicio" and tramo == 0:
        p["inv_start"] = float(valor)
    elif lado == "fin" and tramo == n - 2:
        p["inv_end"] = float(valor)
    else:
        model_ops.snapshot_seg_values(p)
        p["seg_edit_enabled"] = True
        clave, vi = ("vertex_inv_out", tramo) if lado == "inicio" else ("vertex_inv_in", tramo + 1)
        p.setdefault(clave, {})[vi] = float(valor)
    return True


def aplicar_diametro(p, dato):
    """El diámetro elegido en el desplegable (`dato` = tamaño del catálogo, «diam:N» sin familia o "" = por
    defecto), como `_prop_changed` del panel (en sitio)."""
    dato = str(dato or "")
    if dato.startswith("diam:"):
        p["pipe_size"] = ""
        p["diam"] = float(dato[5:])
        p["diam_elegido"] = True
    else:
        p["pipe_size"] = dato
        p["diam"] = diam_de_tamano(dato) if dato else model_ops.DIAM_DEFECTO_IN
        p.pop("diam_elegido", None)

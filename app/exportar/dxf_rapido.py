"""Guardar el DXF más rápido, con el MISMO archivo (pedido del usuario 2026-10-19: con el mapa de 16 761
utilidades y ~600 mil entidades del plano, `doc.saveas` tardaba ~30 s).

Casi todo ese tiempo era `DXFNamespace._export_dxf_attribute_optional` de ezdxf: por cada atributo de cada
entidad (~13 millones) busca su definición, arma un `DXFTag` y lo convierte a texto, y por cada atributo sin
valor arma el mensaje de `logger.debug` aunque el registro esté apagado. `escritura_rapida()` lo cambia,
solo mientras dura el bloque, por `_exportar_atributo`: la MISMA lógica y el mismo texto (`"%3d\\n%s\\n"`,
vértices como `float` de hasta 3 componentes, igual que `DXFVertex`) sin los objetos intermedios. Solo con
el escritor de texto de ezdxf (`TagWriter`); con cualquier otro (binario, colector de pruebas) sigue el de
ezdxf. Verificado: el archivo sale idéntico byte a byte (salvo la hora de guardado de la cabecera).
"""
from __future__ import annotations

import contextlib
import logging
import threading

from ezdxf.entities import dxfns as _dxfns
from ezdxf.lldxf.attributes import XType
from ezdxf.lldxf.tagwriter import TagWriter
from ezdxf.lldxf.types import BINARY_DATA, POINT_CODES, TAG_STRING_FORMAT, cast_tag_value

_original = _dxfns.DXFNamespace._export_dxf_attribute_optional
_original_lista = _dxfns.DXFNamespace.export_dxf_attribs
_POINT2D = XType.point2d
_CALLBACK = XType.callback
_logger = logging.getLogger("ezdxf")
_cerrojo = threading.Lock()
_activos = 0


def _exportar_atributo(self, tagwriter, name):
    """= `DXFNamespace._export_dxf_attribute_optional` + `_export_group_codes` para un `TagWriter`."""
    if type(tagwriter) is not TagWriter:
        return _original(self, tagwriter, name)
    attrib = self._entity.DXFATTRIBS.get(name)
    if attrib is None:
        return _original(self, tagwriter, name)          # (el error de siempre)
    return _escribir(self, tagwriter, name, attrib)


_NADA = object()
_PLANES = {}                                              # (definiciones, nombres) → [(nombre, definición)]


def _exportar_atributos(self, tagwriter, attribs):
    """= `DXFNamespace.export_dxf_attribs`: las definiciones de cada lista de nombres se buscan una vez."""
    if type(tagwriter) is not TagWriter or isinstance(attribs, str):
        return _original_lista(self, tagwriter, attribs)
    defs = self._entity.DXFATTRIBS
    clave = (id(defs), attribs if isinstance(attribs, tuple) else tuple(attribs))
    plan = _PLANES.get(clave)
    if plan is None:
        plan = [(n, defs.get(n)) for n in clave[1]]
        if any(a is None for _n, a in plan):
            return _original_lista(self, tagwriter, clave[1])   # (el error de siempre)
        plan = _PLANES[clave] = [(n, a, a.optional, a.default, a.xtype == _CALLBACK) for n, a in plan]
    # = `_escribir` por cada nombre, en línea (12 millones de llamadas con el mapa de 16 761 utilidades)
    d = self.__dict__
    force = tagwriter.force_optional
    for name, attrib, optional, default, callback in plan:
        value = d.get(name, _NADA)
        if value is _NADA:                                # = DXFNamespace.get(name, None) sin el atributo
            value = attrib.get_callback_value(self._entity) if callback else None
        if value is None and not optional:
            value = default
        if value is None:
            if _logger.isEnabledFor(logging.DEBUG):
                _logger.debug(f"DXF attribute '{name}' not written because its a None value.")
            continue
        if optional and (not force) and default is not None and default == value:
            continue
        _grupo(self, tagwriter, name, attrib, value)


def _escribir(self, tagwriter, name, attrib):
    value = self.__dict__.get(name, _NADA)
    if value is _NADA:                                    # = DXFNamespace.get(name, None) sin el atributo
        value = attrib.get_callback_value(self._entity) if attrib.xtype == _CALLBACK else None
    optional = attrib.optional
    default = attrib.default
    if value is None and not optional:
        value = default
    if value is None:
        if _logger.isEnabledFor(logging.DEBUG):
            _logger.debug(f"DXF attribute '{name}' not written because its a None value.")
        return
    if optional and (not tagwriter.force_optional) and default is not None and default == value:
        return
    _grupo(self, tagwriter, name, attrib, value)


def _grupo(self, tagwriter, name, attrib, value):
    """= `dxfns._export_group_codes` + `TagWriter.write_tag(dxftag(...))`."""
    if tagwriter.dxfversion < attrib.dxfversion:
        return
    if attrib.xtype == _POINT2D and len(value) > 2:
        try:  # Vec3, Vec2
            value = (value.x, value.y)
        except AttributeError:
            value = value[:2]
    if isinstance(value, str):
        assert "\n" not in value, "line break '\\n' not allowed"
        assert "\r" not in value, "line break '\\r' not allowed"
    code = attrib.code
    if code in BINARY_DATA:
        return _original(self, tagwriter, name)           # (poco común: el camino de ezdxf)
    write = tagwriter._stream.write
    if code in POINT_CODES:                               # = DXFVertex: array("d", value), hasta 3 componentes
        partes = [float(v) for v in value]
        write("".join([TAG_STRING_FORMAT % (c, v) for c, v in zip((code, code + 10, code + 20), partes)]))
    else:
        write(TAG_STRING_FORMAT % (code, cast_tag_value(code, value)))


@contextlib.contextmanager
def escritura_rapida():
    """Dentro del bloque, ezdxf escribe los atributos con `_exportar_atributo` (mismo texto)."""
    global _activos
    with _cerrojo:
        _activos += 1
        _dxfns.DXFNamespace._export_dxf_attribute_optional = _exportar_atributo
        _dxfns.DXFNamespace.export_dxf_attribs = _exportar_atributos
    try:
        yield
    finally:
        with _cerrojo:
            _activos -= 1
            if _activos == 0:
                _dxfns.DXFNamespace._export_dxf_attribute_optional = _original
                _dxfns.DXFNamespace.export_dxf_attribs = _original_lista


@contextlib.contextmanager
def _contando(doc):
    """Si alguien escucha el avance (`nucleo.avance`, la barra de la exportación), avisa «guardar» con
    cuántas entidades van de las del documento. Solo cuenta: el archivo es el mismo."""
    from ezdxf.entities.dxfentity import DXFEntity
    from nucleo import avance
    if not avance.activo():
        yield
        return
    original = DXFEntity.export_dxf
    total = max(1, len(doc.entitydb))
    cuenta = [0]

    def export_dxf(self, tagwriter):
        cuenta[0] += 1
        if not cuenta[0] & 511:                           # cada 512: avisar en cada una costaba tiempo
            avance.avisar("guardar", min(cuenta[0], total), total)
        return original(self, tagwriter)
    DXFEntity.export_dxf = export_dxf
    avance.avisar("guardar", 0, total)                    # empieza (aunque sean pocas)
    try:
        yield
        avance.avisar("guardar", total, total)            # el final (también con menos de 512)
    finally:
        DXFEntity.export_dxf = original


def guardar(doc, ruta):
    """`doc.saveas(ruta)` con la escritura rápida (mismo archivo)."""
    with escritura_rapida(), _contando(doc):
        doc.saveas(ruta)

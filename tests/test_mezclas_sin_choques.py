"""`Main` hereda de muchas clases mezcla (`ventana_*.py`). Si dos definen un método con el MISMO nombre,
gana la primera del MRO sin ningún aviso y la otra deja de funcionar. Pasó (auditoría 2026-11-09):
`PerfilMixin._ft()` tapaba `TrazoMixin._ft(a, b)` y la línea elástica del dibujo no se veía (el TypeError
quedaba tragado en un try)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))


def test_ningun_metodo_definido_en_dos_mezclas():
    from ui.ventana.app_window import Main
    duenos = {}
    for cls in Main.__mro__:
        if cls is Main or cls is object or cls.__module__.startswith(("PySide6", "shiboken")):
            continue
        for nombre, valor in vars(cls).items():
            if nombre.startswith("__"):
                continue
            if callable(valor) or isinstance(valor, (property, staticmethod, classmethod)):
                duenos.setdefault(nombre, []).append(cls.__name__)
    choques = {n: c for n, c in duenos.items() if len(c) > 1}
    assert not choques, f"métodos con el mismo nombre en varias mezclas de Main: {choques}"

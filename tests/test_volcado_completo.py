"""2026-11-21: un fallo nativo deja `sesion-<pid>.dmp` con toda la memoria (para ver quién dañó la memoria)."""
import os
import struct
import subprocess
import sys
import tempfile

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.mark.skipif(sys.platform != "win32", reason="volcados de Windows")
def test_un_fallo_nativo_deja_un_volcado_completo_con_la_excepcion():
    with tempfile.TemporaryDirectory() as carpeta:
        codigo = ("import sys, faulthandler; sys.path.insert(0, 'app'); from nucleo import diagnostico as D; "
                  "D.activar(); faulthandler._read_null()")
        env = dict(os.environ, PDFCAD_DIAGNOSTICOS=carpeta)
        subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ, env=env, capture_output=True, timeout=120)
        dmps = [f for f in os.listdir(carpeta) if f.endswith(".dmp")]
        assert dmps
        datos = open(os.path.join(carpeta, dmps[0]), "rb").read()
        assert len(datos) > 5_000_000 and datos[:4] == b"MDMP"
        n, rva = struct.unpack_from("<II", datos, 8)
        tipos = {struct.unpack_from("<I", datos, rva + 12 * i)[0] for i in range(n)}
        assert 6 in tipos                                     # trae el flujo de la excepción

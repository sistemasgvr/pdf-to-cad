"""Genera el sitio público y lo sube a Cloudflare Pages (wrangler). La vista de administrador NUNCA se publica:
solo se sube `gestion/_salida/publico`.

Primera vez (una sola, en esta PC):   npx wrangler login
"""
from __future__ import annotations

import os
import shutil
import subprocess

import datos as D
import sitio

SALIDA = lambda: D.ruta("_salida")                     # noqa: E731
PUBLICO = lambda: D.ruta("_salida", "publico")         # noqa: E731


def construir(pr=None):
    pr = pr or D.leer()
    errores = D.validar(pr)
    if errores:
        raise ValueError("Datos con problemas:\n  " + "\n  ".join(errores))
    return sitio.generar(pr, PUBLICO())


def _npx():
    return shutil.which("npx.cmd") or shutil.which("npx")


def publicar(pr=None, al_texto=print):
    """Construye y sube. Devuelve (ok, salida)."""
    pr = pr or D.leer()
    construir(pr)
    npx = _npx()
    if not npx:
        return False, "No se encontró npx (instala Node.js)."
    base = [npx, "--yes", "wrangler@4"]
    crear = subprocess.run(base + ["pages", "project", "create", pr.cloudflare, "--production-branch", "main"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
    salida = crear.stdout + crear.stderr
    if crear.returncode != 0 and "already exists" not in salida and "8000002" not in salida:
        if "login" in salida.lower() or "authentic" in salida.lower():
            return False, "Falta iniciar sesión en Cloudflare: corre una vez  npx wrangler login\n\n" + salida
    p = subprocess.run(base + ["pages", "deploy", PUBLICO(), "--project-name", pr.cloudflare, "--branch", "main",
                               "--commit-dirty=true"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    salida = p.stdout + p.stderr
    al_texto(salida)
    return p.returncode == 0, salida

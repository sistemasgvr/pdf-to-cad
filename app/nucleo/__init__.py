"""Núcleo: lógica PURA del dominio (sin Qt ni fitz).

Modelo de datos y sus operaciones (utilidades, buzones, cotas, curvas, bancoductos,
datos extendidos) y el motor de normativas. La interfaz (Qt) usa este paquete;
este paquete NUNCA importa la interfaz. Se importa como `from nucleo import model_ops`.
"""

# Válvulas de compuerta — pendientes

Estado al 2026-11-05. Lo hecho está descrito en `CLAUDE.md` (sección «Válvulas en agua y gas») y en el changelog
2.0.0. Esto es lo que falta, en orden de urgencia.

## 1. Probarlo dentro de Civil 3D (lo más urgente)

El plugin compila y la receta en C# da lo mismo que la de la app (`PerfilPruebas`: `Valvulas()`), pero
**nunca se corrió en Civil 3D**: en este equipo solo hay AutoCAD, y su consola no carga DLL fuera de las rutas de
confianza (no se cambió esa seguridad). Hay que comprobar, con un DXF de la app que tenga válvulas:

- `IMPORTAR_RED` paso 5f-bis (`ImportarRedValvulas.cs`): que encuentre la tubería, la parta en las dos caras y
  vuelva a conectar las piezas de sus puntas (`ConnectToPipe`).
- Que los sólidos salgan bien: uniones y restas (paso interior, agujeros de pernos, toro del volante).
- Que la orientación coincida con la Vista 3D de la app (X = eje con pendiente, Z = vertical, volante hacia +Y).
- `CREAR_PERFIL_RED`: que el recorrido pase de un trozo al otro a través de la válvula (XDATA `PDFCAD_FITTING`
  con `TIPO=VALVE`) y que salga el rótulo «8" FLG GATE VALVE».

## 2. Válvulas roscadas NPT (1"–2")

Están en `Valvulas_AWWA_3D.dwg` (`VALV_1_NPT`, `VALV_1.5_NPT`, `VALV_2_NPT`, capa `V-PRES-VALV-LATON`, ACI 42), pero
el plugin del equipo no las usaba. Forma: cuerpo de latón con extremos roscados y hexagonales, bonete de cilindros
apilados, vástago y volante HORIZONTAL arriba (aro con 4 rayos). Medidas leídas hasta ahora (pulgadas):

| | 1" | 1.5" | 2" | fórmula probable |
|---|---|---|---|---|
| largo total | 5.5 | 7.1 | 8.7 | 3.2·N + 2.3 |
| tope (volante) | 8.0 | 9.725 | 11.45 | 3.45·N + 4.55 |
| radio del volante (en Y) | 2.4 | 3.039 | 3.679 | 1.279·N + 1.121 |
| fondo (z mín.) | −1.344 | −1.764 | −2.184 | −(0.84·N + 0.504) |

Falta medir el resto de las piezas (exportar los bloques con `STLOUT` desde la consola de AutoCAD, como se hizo
con los demás) y sumarlas a `valvula_receta.py` / `ValvulaReceta.cs`. Para usarlas también hay que bajar
`N_MIN` (hoy 3") y decidir hasta qué diámetro es roscada.

## 3. Ficha de datos en Civil 3D (Property Set)

Los codos y las Tee llevan el Property Set `PDFCAD_Accesorio`. La válvula ya trae el XDATA de accesorio
(`PDFCAD_FITTING`, `TIPO=VALVE`), así que bastaría llamar `AccesorioPropertySet.AplicarDesdeXData` sobre su cuerpo y
sumar `VALVE` → «Válvula de compuerta» en `NombreTipo`.

## 4. Tabla de datos, Excel, informe y normativas

Las válvulas no salen en la Tabla de datos ni en su Excel, ni en el informe Word, y no hay reglas de normativa para
ellas (p. ej. distancia máxima entre válvulas, válvula en cada ramal).

## 5. Válvula con reductores

Hoy la válvula va dentro de UNA tubería, con el mismo diámetro a los dos lados. El plugin del equipo también
ponía válvula + reductores entre dos tuberías de distinto diámetro (configuraciones A/B/C y reductor excéntrico).

## 6. Choques con otras cosas

El plugin del equipo avisaba si la válvula (con su volante) tocaba otras entidades del dibujo. La app solo
revisa codos, T, cruces y otras válvulas del mismo tramo.

## 7. Detalles menores

- La compuerta interna (capa INT, dentro del cuerpo) no está en la receta: no se ve desde afuera.
- Perfil del plugin: la válvula sale solo con su rótulo, como los codos y las Tee (el perfil es 100 % nativo de
  Civil 3D, `PERFIL_DISENO.md`); en la app se dibuja además el símbolo.
- Si la tubería se edita y la válvula ya no cabe, queda en rojo y no se exporta (no se corre sola).

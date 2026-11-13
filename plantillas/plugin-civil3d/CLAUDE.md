# Plugin de Civil 3D — reglas del repo

Este plugin se INTEGRA en el plugin principal de Deyvy (repo `pdf-to-cad`, `API-CIVIL/proyecto1/proyecto1`).
Todo lo de aquí debe compilar allá sin tocar nada. Español en código, comentarios, mensajes y commits.

## Versiones: fijadas, no se cambian

- `Directory.Build.props` es copia de la configuración del plugin principal: AutoCAD 2025 → 2026 → 2027
  (`AcadDir`), .NET 8 (2025/2026) o .NET 10 (2027) (`AcadTfm`), `LangVersion` 12, `Nullable` y
  `ImplicitUsings` apagados, x64, WPF, referencias de AutoCAD/Civil 3D con `Private=false`.
- **NO editar `Directory.Build.props`** ni poner `TargetFramework`, `LangVersion`, `Platform`, `UseWindowsForms`
  o referencias de Autodesk en un `.csproj`. Si algo no compila así, se avisa a Deyvy.
- No usar APIs de .NET 9/10 ni sintaxis de C# 13/14 (aunque tu AutoCAD sea 2027).
- Paquetes NuGet: solo `ClosedXML` 0.104.2 y `Microsoft.Data.Sqlite` 8.0.11 (las versiones del principal).
  Otro paquete u otra versión: preguntar antes.
- Ventanas en WPF (sin XAML externo si se puede, como `Ventanas/VentanaBrida.cs`). WinForms no.

## Estructura: la lógica PURA va aparte

```
<Plugin>/Logica/    PURA: sin «using Autodesk». Entradas (números, textos) → resultado (medidas, puntos,
                    listas). Nada de Document, Transaction, Solid3d, Point3d… Aquí van las fórmulas y tablas.
<Plugin>/Civil3D/   Comandos [CommandMethod]: piden datos, llaman a Logica y dibujan. Sin fórmulas.
<Plugin>/Ventanas/  Ventanas WPF de entrada: piden y validan con Logica. No dibujan.
<Plugin>.Pruebas/   Consola que compila SOLO Logica/ (Compile Include). Sin AutoCAD.
```

- Namespace: `Civil3DBasico.<Area>` (p. ej. `Civil3DBasico.Hidrantes`). El principal usa `Civil3DBasico`.
- Nombres de comando con prefijo del área (`HIDRANTE_CREAR`, `LAMINADO_…`): no pueden repetirse en el principal.
- Unidades: el dibujo va en PIES; si la lógica trabaja en pulgadas, convertir en un solo lugar.
- Errores de entrada: la lógica devuelve un resultado con `Valido`/`Error` legible, no lanza excepciones.
- Archivos < 500 líneas, una responsabilidad por archivo.

## Pruebas: obligatorias

- Antes de entregar: `dotnet run -c Release --project <Plugin>.Pruebas` → debe terminar con todo PASA
  (código de salida 0). También `dotnet build <Plugin>.sln -c Release` sin errores.
- **Toda corrección de bug lleva una prueba nueva que FALLABA antes del arreglo.** Primero escribir la
  prueba, ver que falla, arreglar, ver que pasa.
- Toda función nueva de `Logica/` lleva al menos un caso normal y uno de entrada inválida.
- Si algo solo se puede probar dentro de Civil 3D, decirlo en el commit («sin probar en Civil 3D: …»).

## Catálogo de elementos

Cada elemento (válvula, hidrante, pieza…) tiene una ficha EN ESTE REPO: `catalogo/<tipo>/<id>/ficha.toml` +
capturas `.png` en la misma carpeta (la primera es la portada). Al integrar, Deyvy la copia a
`gestion/catalogo/<area>/<tipo>/<id>/` del repo principal (mismo formato), desde donde sale al catálogo del cliente.

```toml
nombre = "Hidrante de barril seco 6 in"
tipo = "hidrantes"
area = "piezas-3d"          # Jean: piezas-3d · Elvis: laminado
responsable = "Jean"
descripcion = "Sólido 3D del hidrante con base, barril y bocas, desde una ventana de entrada."
entradas = ["diametro_in", "altura_ft", "numero_bocas"]
tamanos = "4, 6, 8 in"
version = "0.3.0"
propuesto = "falta_probar"
estado = ""                 # NO TOCAR: lo pone Deyvy
aprobado = ""               # NO TOCAR: lo pone Deyvy
issues = []                 # números de issue de GitHub relacionados
```

- Tú SOLO llenas/cambias `propuesto`: `planificado`, `en_desarrollo`, `falta_probar`, `optimizar` o `probado`.
- **NUNCA** escribir `estado` ni `aprobado`.
- Capturas: `vista_3d.png`, `ventana.png`… del resultado en Civil 3D, junto a la ficha.

## Entrega

- Se entrega con **commit + push en tu repo de GitHub** (tu Claude Code hace git). Nunca carpetas ni .zip por
  WhatsApp.
- Antes del commit: compilar la solución, correr las pruebas, actualizar la ficha (`propuesto`, `version`).
- Mensaje de commit en español: qué hace, qué pruebas se sumaron y qué falta probar en Civil 3D.
- Para Deyvy importan las clases de `Logica/`: documentar en su comentario `///` qué entra (unidades) y qué
  sale. Ver «Contrato de entrega» en `README.md`.

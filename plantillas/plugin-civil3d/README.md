# Plantilla de plugin de Civil 3D

Plantilla para los plugins que se integran en el plugin principal (`pdf-to-cad`,
`API-CIVIL/proyecto1/proyecto1`). Trae las MISMAS versiones que el principal (`Directory.Build.props`), la lógica
pura separada de AutoCAD y un arnés de pruebas que corre sin AutoCAD (como `PerfilPruebas` del principal).

Ejemplo incluido: `EJEMPLO_BRIDA` — ventana para elegir el diámetro → `CalculoBrida` (puro) calcula exterior,
espesor, círculo y agujeros de pernos → el comando dibuja el `Solid3d` con los agujeros restados.

```
Directory.Build.props        versiones fijadas (NO cambiar)
PluginEjemplo.sln
PluginEjemplo/
  Logica/CalculoBrida.cs     PURA (sin Autodesk)
  Civil3D/ComandosBrida.cs   comando EJEMPLO_BRIDA
  Ventanas/VentanaBrida.cs   ventana WPF de entrada
PluginEjemplo.Pruebas/
  Program.cs                 casos PASA/FALLA, código de salida 0/1
CLAUDE.md                    reglas para Claude Code en el repo del ingeniero
```

## Crear un repo nuevo desde la plantilla

1. Crear el repo vacío en GitHub (p. ej. `plugin-hidrantes`) y clonarlo.
2. Copiar dentro TODO el contenido de `plantillas/plugin-civil3d/` (incluido `.gitignore`).
3. Renombrar (o pedírselo a Claude Code): `PluginEjemplo` → `PluginHidrantes` en carpetas, `.csproj`, `.sln`,
   `PluginEjemplo.Pruebas` → `PluginHidrantes.Pruebas` (el nombre DEBE terminar en `.Pruebas`: así
   `Directory.Build.props` no le pone AutoCAD), `RootNamespace` → `Civil3DBasico.Hidrantes`.
4. Borrar el ejemplo de la brida cuando ya haya código propio (o dejarlo como referencia hasta entonces).
5. Commit inicial y push.

## Compilar

```
dotnet build PluginEjemplo.sln -c Release
```

- Usa la PRIMERA AutoCAD instalada entre 2025, 2026 y 2027 (forzar otra: `-p:AcadDir="C:\Program Files\Autodesk\AutoCAD 2026"`).
- El DLL queda en `PluginEjemplo\bin\x64\Release\PluginEjemplo.dll` y sirve SOLO para esa versión de AutoCAD
  (2025/2026 = .NET 8, 2027 = .NET 10). Cargar en Civil 3D con `NETLOAD`.
- Es normal un aviso MSB3277 (conflicto de versiones entre DLL de Autodesk); el principal también lo tiene.
- Sin AutoCAD instalado el plugin no compila, pero las pruebas sí.

## Correr las pruebas

```
dotnet run -c Release --project PluginEjemplo.Pruebas
```

Imprime `PASA`/`FALLA` por caso y termina con código 0 si todo pasa (1 si algo falla). No necesita AutoCAD.
Incluye solo `Logica/**/*.cs`: si alguien pone `using Autodesk` en la lógica, las pruebas dejan de compilar.

## Contrato de entrega a Deyvy

Lo que se integra en el principal es, sobre todo, `Logica/`. Los comandos y ventanas se adaptan al flujo del
principal (por ejemplo, `IMPORTAR_RED` llama a la lógica con datos del DXF en vez de una ventana).

Por cada elemento entregado:

1. **Clases puras** (`Logica/`): una clase estática de cálculo por elemento (p. ej. `CalculoHidrante`) con:
   - **Entradas**: parámetros simples (`double`, `int`, `string`, enums propios), con unidad en el nombre
     o en el `///` (`diametroIn`, `alturaFt`).
   - **Salida**: una clase de resultado (`ResultadoHidrante`) con `Valido`, `Error` legible y las medidas/
     geometría en tipos propios (`Punto2D`, listas de puntos, perfiles, radios). Nunca tipos de Autodesk.
   - Sin estado global, sin archivos, sin excepciones por entradas inválidas.
   - Constantes y tablas de la norma con su fuente en un comentario.
2. **Pruebas**: casos en `*.Pruebas` que cubran los tamaños de la tabla, bordes e inválidos; todas pasan.
3. **Comando** (`Civil3D/`): cómo se usa la lógica para dibujar (capa, unidades en pies, orientación
   del sólido). Indicar qué se probó en Civil 3D y qué no.
4. **Ficha** del catálogo en este repo (`catalogo/<tipo>/<id>/ficha.toml` + `.png`; Deyvy la copia a `gestion/catalogo/<area>/…` del principal)
   con `propuesto` actualizado. `estado` y `aprobado` los pone Deyvy.
5. **Commit y push** en el repo del ingeniero; avisar a Deyvy el commit (no carpetas por WhatsApp).

Al integrar, Deyvy copia `Logica/` (y lo que corresponda) dentro de `API-CIVIL/proyecto1/proyecto1/<Area>/` y suma
los casos de prueba a un arnés del principal con `Compile Include`, igual que aquí.

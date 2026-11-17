"""Shaders GLSL 1.20 de la vista 3D (movidos tal cual de `visor3d` el 2026-10-16).

`VERT` + `FRAG`: los triángulos de siempre (15 floats por vértice, `mallas3d`).
`VERT_INST`: las INSTANCIAS (`instancias3d` / `visor3d_instancias`): la misma cuenta que
`barrido_camino` hecha en la GPU, y el mismo `FRAG`.

Superficie importada (`mallas3d.tin`, 2026-11-14): el vértice trae `aRadio` = −1 y sus baricéntricas en `aEje`.
`FRAG` la pinta según `uEstiloSup` (ESTILOS_SUPERFICIE): 0 relieve (color por cota de `mallas3d.color_por_cota` con
la sombra de un sol FIJO, no la de la cámara), 1 cotas en franjas de arcoíris (como el análisis de elevaciones de
Civil 3D), 2 malla (solo los bordes de los triángulos). `uCurvas` suma curvas de nivel cada `uIntervalo` ft (cota
real = `vZ` + `uZBase`), con una más marcada cada `CURVA_MAYOR_CADA`.
"""

ESTILOS_SUPERFICIE = ("relieve", "cotas", "malla")
BANDAS_COTA = 12                     # franjas del estilo «cotas»
CURVA_MAYOR_CADA = 5                 # curva maestra cada 5 curvas
SOL = (-0.5, 0.5, 0.7071)            # sol fijo del noroeste a 45° (la sombra de relieve de los mapas)
SOMBRA_MIN = 0.45                    # lo que queda iluminada la ladera de espaldas al sol
FACTOR_RELIEVE = 3.0                 # solo para la SOMBRA (como el «factor z» de los SIG): la geometría no cambia


def arcoiris(t):
    """(r, g, b) 0–1 del estilo «cotas» (morado en lo más bajo → rojo en lo más alto): la MISMA cuenta que el
    shader, para la leyenda."""
    import colorsys
    return colorsys.hsv_to_rgb(0.75 * (1.0 - max(0.0, min(1.0, t))), 0.85, 0.95)

VERT = """
#version 120
attribute vec3 aPos; attribute vec3 aNor; attribute vec4 aCol; attribute float aId;
attribute vec3 aEje; attribute float aRadio;
uniform mat4 uMvp; uniform float uSel; uniform float uHov;
uniform vec3 uOjo; uniform float uPxMundo; uniform float uMinPx;
varying vec4 vCol; varying vec3 vNor; varying float vEstado; varying vec3 vBar; varying float vZ;
void main() {
    vec3 p = aPos;
    vZ = aPos.z;
    if (aRadio > 0.0) {    // tubería: nunca más fina que uMinPx de radio en pantalla
        float minimo = uMinPx * uPxMundo * distance(uOjo, aEje);
        p = aEje + (aPos - aEje) * max(1.0, minimo / aRadio);
    }
    gl_Position = uMvp * vec4(p, 1.0);
    vNor = aNor;
    vCol = aCol;
    vEstado = 0.0;
    vBar = vec3(1.0);
    if (aRadio < -0.5) {   // superficie (mallas3d.tin): color por cota; aEje = baricéntricas
        vEstado = -1.0;
        vBar = aEje;
    }
    if (aId > 0.5 && abs(aId - uHov) < 0.5) vEstado = 1.0;
    if (aId > 0.5 && abs(aId - uSel) < 0.5) vEstado = 2.0;
}
"""
FRAG = """
#version 120
uniform vec3 uLuz; uniform vec4 uResalte; uniform float uAlfa; uniform float uBordes;
uniform float uEstiloSup; uniform float uCurvas; uniform float uIntervalo; uniform float uZBase; uniform vec2 uRangoZ;
varying vec4 vCol; varying vec3 vNor; varying float vEstado; varying vec3 vBar; varying float vZ;
vec3 hsv(float h, float s, float v) {
    vec3 k = clamp(abs(mod(h * 6.0 + vec3(0.0, 4.0, 2.0), 6.0) - 3.0) - 1.0, 0.0, 1.0);
    return v * mix(vec3(1.0), k, s);
}
void main() {
    if (vEstado < -0.5) {  // superficie (ver el docstring del módulo)
        vec3 n = normalize(vNor * vec3(@FACTOR@, @FACTOR@, 1.0));
        float sombra = @SOMBRA@ + (1.0 - @SOMBRA@) * clamp(dot(n, normalize(vec3(@SOL@))), 0.0, 1.0);
        vec3 c = vCol.rgb * sombra;
        float alfa = vCol.a * uAlfa;
        if (uEstiloSup > 0.5 && uEstiloSup < 1.5) {
            float t = clamp((vZ - uRangoZ.x) / max(uRangoZ.y - uRangoZ.x, 1e-6), 0.0, 0.9999);
            float b = (floor(t * @BANDAS@.0) + 0.5) / @BANDAS@.0;
            c = hsv(0.75 * (1.0 - b), 0.85, 0.95) * (0.78 + 0.22 * sombra);
        }
        vec3 d = fwidth(vBar);
        vec3 a = smoothstep(vec3(0.0), d * 1.2, vBar);
        float borde = 1.0 - min(min(a.x, a.y), a.z);
        float curva = 0.0;
        float mayor = 0.0;
        if (uCurvas > 0.5 && uIntervalo > 0.0) {
            float f = (vZ + uZBase) / uIntervalo;
            float df = max(fwidth(f), 1e-6);
            mayor = abs(mod(floor(f + 0.5), @MAYOR@.0)) < 0.5 ? 1.0 : 0.0;
            float ancho = mayor > 0.5 ? 1.3 : 0.6;
            curva = 1.0 - smoothstep(ancho - 0.5, ancho + 0.5, abs(fract(f + 0.5) - 0.5) / df);
            curva *= 1.0 - smoothstep(0.25, 0.5, df);      // más juntas que ~3 px: se desvanecen
        }
        if (uEstiloSup > 1.5) {                            // malla: solo las líneas
            float linea = max(borde, curva);
            if (linea < 0.05) discard;
            vec3 tinta = curva > borde ? vec3(1.0, 0.78, 0.32) : min(vCol.rgb * 1.2, vec3(1.0));   // curvas en ámbar
            gl_FragColor = vec4(tinta, linea * alfa);
            return;
        }
        if (uBordes > 0.5) {
            // de lejos (triángulos de pocos píxeles) los bordes se desvanecen: si no, todo sería línea
            float lejos = smoothstep(1.0 / 14.0, 1.0 / 5.0, max(max(d.x, d.y), d.z));
            c = mix(c, c * 0.62, borde * (1.0 - lejos));
        }
        c = mix(c, c * 0.3, curva * (mayor > 0.5 ? 0.9 : 0.65));
        gl_FragColor = vec4(c, alfa);
        return;
    }
    vec3 n = normalize(vNor);
    float l = 0.38 + 0.62 * abs(dot(n, normalize(uLuz)));
    vec3 c = vCol.rgb * l;
    if (vEstado > 1.5) c = mix(c, uResalte.rgb, 0.6);
    else if (vEstado > 0.5) c = mix(c, vec3(1.0), 0.35);
    gl_FragColor = vec4(c, vCol.a * uAlfa);
}
"""

VERT_INST = """
#version 120
attribute vec3 aBase;
attribute vec3 iP0; attribute vec3 iL0; attribute vec3 iA0; attribute vec4 iB0;
attribute vec3 iP1; attribute vec3 iL1; attribute vec3 iA1; attribute vec4 iB1;
attribute vec4 iCol; attribute vec4 iMisc;
uniform mat4 uMvp; uniform float uSel; uniform float uHov; uniform float uModo;
uniform vec3 uOjo; uniform float uPxMundo; uniform float uMinPx;
varying vec4 vCol; varying vec3 vNor; varying float vEstado; varying vec3 vBar; varying float vZ;
vec3 anillo(vec3 P, vec3 L, vec3 A, vec4 B, vec2 c, float r) {
    vec3 off = (c.x * r) * L + (c.y * r) * A;
    off += (dot(off, B.xyz) * B.w) * B.xyz;      // inglete en los vértices interiores
    return P + off;
}
void main() {
    float r = iMisc.y;
    float rmin = iMisc.z;
    vec3 p; vec3 n; vec3 eje;
    if (uModo < 0.5) {                              // tramo: anillo del extremo 0 o 1
        bool fin = aBase.z > 0.5;
        vec3 P = fin ? iP1 : iP0;
        vec3 L = fin ? iL1 : iL0;
        vec3 A = fin ? iA1 : iA0;
        vec4 B = fin ? iB1 : iB0;
        p = anillo(P, L, A, B, aBase.xy, r);
        n = aBase.x * L + aBase.y * A;
        eje = P;
    } else if (uModo < 1.5) {                       // tapa: centro o anillo del extremo
        p = aBase.z > 0.5 ? iP0 : anillo(iP0, iL0, iA0, vec4(0.0), aBase.xy, r);
        n = iB0.xyz;
        eje = iP0;
    } else {                                        // esfera
        p = iP0 + aBase * r;
        n = aBase;
        eje = p;
        rmin = 0.0;
    }
    if (rmin > 0.0) {      // tubería: nunca más fina que uMinPx de radio en pantalla
        float minimo = uMinPx * uPxMundo * distance(uOjo, eje);
        p = eje + (p - eje) * max(1.0, minimo / rmin);
    }
    gl_Position = uMvp * vec4(p, 1.0);
    vNor = n;
    vCol = iCol;
    vEstado = 0.0;
    vBar = vec3(1.0);
    vZ = 0.0;
    float id = iMisc.x;
    if (id > 0.5 && abs(id - uHov) < 0.5) vEstado = 1.0;
    if (id > 0.5 && abs(id - uSel) < 0.5) vEstado = 2.0;
}
"""


FRAG = (FRAG.replace("@FACTOR@", repr(float(FACTOR_RELIEVE))).replace("@SOMBRA@", repr(float(SOMBRA_MIN)))
        .replace("@SOL@", ", ".join(repr(float(v)) for v in SOL)).replace("@BANDAS@", str(BANDAS_COTA))
        .replace("@MAYOR@", str(CURVA_MAYOR_CADA)))

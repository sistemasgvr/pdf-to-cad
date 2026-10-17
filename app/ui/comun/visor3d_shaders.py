"""Shaders GLSL 1.20 de la vista 3D (movidos tal cual de `visor3d` el 2026-10-16).

`VERT` + `FRAG`: los triángulos de siempre (15 floats por vértice, `mallas3d`).
`VERT_INST`: las INSTANCIAS (`instancias3d` / `visor3d_instancias`): la misma cuenta que
`barrido_camino` hecha en la GPU, y el mismo `FRAG`.
"""

VERT = """
#version 120
attribute vec3 aPos; attribute vec3 aNor; attribute vec4 aCol; attribute float aId;
attribute vec3 aEje; attribute float aRadio;
uniform mat4 uMvp; uniform float uSel; uniform float uHov;
uniform vec3 uOjo; uniform float uPxMundo; uniform float uMinPx;
varying vec4 vCol; varying vec3 vNor; varying float vEstado;
void main() {
    vec3 p = aPos;
    if (aRadio > 0.0) {    // tubería: nunca más fina que uMinPx de radio en pantalla
        float minimo = uMinPx * uPxMundo * distance(uOjo, aEje);
        p = aEje + (aPos - aEje) * max(1.0, minimo / aRadio);
    }
    gl_Position = uMvp * vec4(p, 1.0);
    vNor = aNor;
    vCol = aCol;
    vEstado = 0.0;
    if (aId > 0.5 && abs(aId - uHov) < 0.5) vEstado = 1.0;
    if (aId > 0.5 && abs(aId - uSel) < 0.5) vEstado = 2.0;
}
"""
FRAG = """
#version 120
uniform vec3 uLuz; uniform vec4 uResalte; uniform float uAlfa;
varying vec4 vCol; varying vec3 vNor; varying float vEstado;
void main() {
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
varying vec4 vCol; varying vec3 vNor; varying float vEstado;
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
    float id = iMisc.x;
    if (id > 0.5 && abs(id - uHov) < 0.5) vEstado = 1.0;
    if (id > 0.5 && abs(id - uSel) < 0.5) vEstado = 2.0;
}
"""

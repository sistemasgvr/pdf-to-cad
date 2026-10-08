"""quiebres_curvas.py — los QUIEBRES del plano entran como CURVAS (PURO, sin Qt).

Regla de los ingenieros (pedido del usuario 2026-10-06, captura de una línea eléctrica
con dos quiebres): en las redes que NO van a presión —eléctrico y telecomunicaciones
(conduit), drenaje y alcantarillado (gravedad)— un quiebre del plano está mal
dibujado: en obra es una curva. Agua y gas no entran (en presión el quiebre es un
accesorio, el codo).

Quiebre = vértice «bend»/«corner» que dejó el reconocimiento (la línea cambia de rumbo
sin bóveda, sin ramal y sin curva en la tinta) con giro > `GIRO_MIN_DEG`, y también un
vértice «curve» que quedó SIN codo (2.º reporte, 2026-10-07, DU06 h.5 eléctrico: una
línea dibujada como UN trazo de tres rectas —el núcleo la toma por curva— o una curva
que no entró en ningún arco y quedó como polilínea): en el editor es una esquina igual
que un «bend». Los vértices de un codo ya reconocido (`fillet`, con su CV) no. Pasa a
esquina de elemento curvo (CV, el mismo modelo que el codo manual) con el radio
AUTOMÁTICO —6 × el ancho interior de la tubería (`model_ops.radio_auto_ft`, igual que
el editor y el plugin)—: es el radio mínimo de la regla, así la curva es la más chica
posible y no agranda el error del dibujo. Queda en automático (`radius_ft` = 0) para
que siga al diámetro si el usuario lo cambia; la marca `quiebre` dice de dónde salió.

La curva se pone SOLO si entra tal cual la dibujan el editor y el plugin, sin tocar
nada más; si no, el quiebre queda como estaba y se devuelve en `sin_lugar`:
  - la tangencia T = r·tan(Δ/2) cabe en los dos tramos con los topes de siempre
    (`FILLET_CAP_RECTA`, o `FILLET_CAP_CURVA` si el vértice vecino también es curva);
  - una curva vecina (codo leído de la tinta u otro quiebre) no cambia: con la nueva
    al lado su tope en ese tramo baja a 0.48 y debe seguir entrando entera;
  - entre dos curvas seguidas queda el tramo recto mínimo del plugin (1 × el ancho
    interior, «tramo recto mínimo» de ImportarRed.cs); si no, el plugin achica las dos.
No se toca un vértice compartido (otro vértice de otra tubería a ≤ tol px —la CV es de
UN vértice, `curve_vertex_indices`—; en gravedad tampoco de la misma, porque su buzón
se reconcilia por coordenada), con una estructura visible cerca o dentro del contorno
de una bóveda (es la llegada a la bóveda, no un quiebre).
"""
import math

from nucleo import model_ops
from nucleo.model import network_kind

GIRO_MIN_DEG = 2.0            # menos = «prácticamente recto»: el plugin no hace arco y lo endereza
KINDS_QUIEBRE = ("bend", "corner", "curve")   # «curve» sin codo = esquina en el editor
REDES_CON_CURVAS = ("gravity", "conduit")
# El ancho interior del catálogo puede ser algo mayor que el nominal: margen en el
# tramo recto mínimo entre dos curvas (si no alcanza, el plugin achicaría las dos).
HOLGURA_RECTO = 1.1


def _giro_deg(a, b, c):
    """Cuánto gira la línea en `b` (0 = sigue recta)."""
    d1x, d1y = b[0] - a[0], b[1] - a[1]
    d2x, d2y = c[0] - b[0], c[1] - b[1]
    l1, l2 = math.hypot(d1x, d1y), math.hypot(d2x, d2y)
    if l1 < 1e-9 or l2 < 1e-9:
        return 0.0
    cs = max(-1.0, min(1.0, (d1x * d2x + d1y * d2y) / (l1 * l2)))
    return math.degrees(math.acos(cs))


def _dentro(poly, x, y):
    """¿(x, y) dentro del polígono `poly`? (par/impar)."""
    dentro = False
    n = len(poly)
    for k in range(n):
        (ax, ay), (bx, by) = poly[k], poly[(k + 1) % n]
        if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
            dentro = not dentro
    return dentro


def _vertice_libre(pipes, ip, vi, tol, gravedad):
    """Ningún otro vértice a ≤ tol px: de otra tubería (la CV sería de las dos) y, en
    gravedad, tampoco de la misma (su buzón se reconcilia por coordenada)."""
    x, y = pipes[ip]["pts"][vi]
    for jp, p in enumerate(pipes):
        if p.get("world"):
            continue
        for vj, (qx, qy) in enumerate(p.get("pts") or ()):
            if jp == ip and (vj == vi or not gravedad):
                continue
            if math.hypot(qx - x, qy - y) <= tol:
                return False
    return True


def _estructura_cerca(structures, x, y, tol, ft_per_px):
    """Una estructura visible a ≤ tol px, o el punto dentro del contorno de una
    bóveda/sólido (o del círculo de un buzón redondo): el quiebre es parte de la
    llegada a esa estructura, no un quiebre del trazado."""
    for s in structures:
        if s.get("world") or s.get("curve") or s.get("x") is None:
            continue
        out = s.get("outline")
        if out and len(out) >= 3 and _dentro(out, x, y):
            return True
        if s.get("hidden"):
            continue
        d = math.hypot(float(s["x"]) - x, float(s["y"]) - y)
        alcance = tol
        if s.get("shape") == "circle" and s.get("width_ft"):
            # la estructura puede estar en el anillo (punta que llega): todo el
            # diámetro del buzón desde ella
            alcance += float(s["width_ft"]) / ft_per_px
        if d <= alcance:
            return True
    return False


def _radio_px(s, p, ft_per_px):
    """Radio con el que el editor dibuja la CV `s` de la tubería `p` (explícito o auto)."""
    r_ft = float(s.get("radius_ft") or 0.0)
    if r_ft <= 0.01:
        r_ft = model_ops.radio_auto_ft(p)
    return r_ft / ft_per_px


def _geo(pts, vi, r_px, curvas, ft_per_px):
    """Arco de la CV del vértice `vi` como lo dibuja el editor (`_curve_arc_info`) y lo
    genera el plugin: tope 0.48 del tramo si el vecino también es curva."""
    cap_p = model_ops.FILLET_CAP_CURVA if (vi - 1) in curvas else model_ops.FILLET_CAP_RECTA
    cap_n = model_ops.FILLET_CAP_CURVA if (vi + 1) in curvas else model_ops.FILLET_CAP_RECTA
    return model_ops.fillet_geo(pts[vi - 1], pts[vi], pts[vi + 1], r_px, max_frac=cap_p,
                                max_frac_next=cap_n,
                                tol_r=model_ops.FILLET_TOL_RADIO_FT / ft_per_px)


def _igual(a, b, tol=1e-6):
    return (a["clamped"] == b["clamped"] and abs(a["r"] - b["r"]) <= tol
            and math.dist(a["t1"], b["t1"]) <= tol and math.dist(a["t2"], b["t2"]) <= tol)


def _entra(p, vi, curvas, ft_per_px):
    """¿La curva mínima entra en el vértice `vi` sin recorte y sin cambiar ninguna curva
    vecina? `curvas` = {vértice: CV} de la tubería (incluye las ya aceptadas)."""
    pts = p["pts"]
    luego = set(curvas) | {vi}
    g = _geo(pts, vi, model_ops.radio_auto_ft(p) / ft_per_px, luego, ft_per_px)
    if g is None or g["clamped"]:
        return False
    ancho = max(model_ops.radio_auto_ft(p) / model_ops.RADIO_AUTO_FACTOR,
                model_ops.alto_interior_ft(p)) * HOLGURA_RECTO / ft_per_px
    for vj in (vi - 1, vi + 1):
        s = curvas.get(vj)
        if s is None or not (0 < vj < len(pts) - 1):
            continue
        rj = _radio_px(s, p, ft_per_px)
        g_antes, g_luego = _geo(pts, vj, rj, set(curvas), ft_per_px), _geo(pts, vj, rj, luego, ft_per_px)
        if (g_antes is None) != (g_luego is None):
            return False
        if g_antes is None:
            continue                           # el vecino no tiene arco (casi recto): no se toca
        if not _igual(g_antes, g_luego):
            return False                       # la curva vecina se recortaría
        if g["T"] + g_luego["T"] > math.dist(pts[vi], pts[vj]) - ancho + 1e-9:
            return False                       # sin el tramo recto mínimo entre las dos
    return True


def _marcar_cv(structures, x, y, net):
    """La estructura del vértice (en gravedad, el buzón oculto del quiebre) pasa a CV con
    radio automático; en conduit no hay ninguna y se crea la marca, como en
    `model_ops.attach_fillets`."""
    cerca = [(math.hypot(float(o["x"]) - x, float(o["y"]) - y), k) for k, o in enumerate(structures)
             if not o.get("world") and not o.get("curve") and o.get("x") is not None]
    d, k = min(cerca, default=(math.inf, -1))
    s = structures[k] if d <= 1.0 else None      # nunca la curva de otro vértice
    if s is None:
        s = {"cod": "", "x": float(x), "y": float(y), "rim": None, "sump": None,
             "part": "", "part_size": "", "net": net, "covered": True,
             "world": False, "hidden": False}
        structures.append(s)
    s.update(curve=True, radius_ft=0.0, hidden=False, part="", part_size="", quiebre=True)
    if not str(s.get("cod") or "").startswith("CV-"):
        s["cod"] = ""                          # rebuild_structures le asigna CV-N
    return s


def curvas_en_quiebres(pipes, structures, ft_per_px, indices=None, tol=None):
    """Convierte en CV de radio automático los quiebres de las tuberías RECONOCIDAS
    (`vertex_kinds`) de gravedad y conduit. `indices` = tuberías a revisar (None =
    todas); `ft_per_px` = pies por px del lienzo (escala / zoom). Primero los quiebres
    que más giran. Devuelve (nuevas, sin_lugar): las CV puestas (en gravedad, el buzón
    oculto del quiebre convertido) y [(x, y)] de los quiebres donde la curva mínima no
    entra, que quedan como estaban. Muta `structures`."""
    tol = model_ops._TOL if tol is None else tol
    if not ft_per_px or ft_per_px <= 0:
        return [], []
    nuevas, sin_lugar = [], []
    for ip in (range(len(pipes)) if indices is None else indices):
        p = pipes[ip]
        net = network_kind(p.get("layer") or "")
        pts = p.get("pts") or []
        kinds = p.get("vertex_kinds") or []
        if p.get("world") or net not in REDES_CON_CURVAS or len(pts) < 3 or len(kinds) != len(pts):
            continue
        curvas = model_ops.curve_vertex_indices(p, structures, pipes, tol)
        cand = []
        for i in range(1, len(pts) - 1):
            if kinds[i] in KINDS_QUIEBRE and i not in curvas:
                g = _giro_deg(pts[i - 1], pts[i], pts[i + 1])
                if g > GIRO_MIN_DEG:
                    cand.append((-g, i))
        for _g, i in sorted(cand):
            x, y = pts[i]
            if (not _vertice_libre(pipes, ip, i, tol, net == "gravity")
                    or _estructura_cerca(structures, x, y, tol, ft_per_px)):
                continue
            if not _entra(p, i, curvas, ft_per_px):
                sin_lugar.append((float(x), float(y)))
                continue
            curvas[i] = _marcar_cv(structures, x, y, net)
            nuevas.append(curvas[i])
    return nuevas, sin_lugar

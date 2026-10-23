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

Vértices PRÁCTICAMENTE RECTOS que estorban (reporte del usuario 2026-10-19, DU06 UD-205:
la diagonal «—SC—» llega a su quiebre con dos vértices de 0.75° a 1.3 ft de él y la curva
no entraba): un vértice blando que gira ≤ `GIRO_MIN_DEG`, a ≤ 0.25 ft de la recta, sin
otra utilidad, sin buzón/caja visible y sin curva, se QUITA si es lo único que deja sin
lugar la curva del quiebre vecino (y, en gravedad, si está a ≤ tol px del quiebre). Es lo
mismo que hace el plugin al importar (`EnderezarQuiebres`: esos vértices no llegan a Civil
3D) y lo que hace la limpieza de tramos (`limpieza_tramos.quitar_vertice`). Solo si con
eso la curva entra y ninguna otra curva cambia de radio, se recorta o se corre más de
0.25 ft; si no, nada se quita.

CHAFLÁN = dos quiebres SEGUIDOS del mismo giro donde no entran dos curvas mínimas (reporte del
usuario 2026-10-23, DU06 UD-202 telecom `C-TELE-UNGD-D`: la línea gira 90° con un chaflán de
5 ft —quiebres de 48° y 42°—; entraba la curva del primero y el segundo quedaba de esquina):
UNA curva mínima en el cruce de las dos rectas de fuera (`_unir_chaflan`), si entra como
cualquier otra y su dibujo no se aparta del plano más de lo que se aparta la curva mínima de
cada quiebre (+ 0.25 ft). Los dos vértices pasan a uno, en ese cruce.
"""
import copy
import math

from nucleo import avance, limpieza_tramos, model_ops, vecindario
from nucleo.model import network_kind
from traduccion.i18n_core import t as _tr

GIRO_MIN_DEG = 2.0            # menos = «prácticamente recto»: el plugin no hace arco y lo endereza
KINDS_QUIEBRE = ("bend", "corner", "curve")   # «curve» sin codo = esquina en el editor
REDES_CON_CURVAS = ("gravity", "conduit")
# El ancho interior del catálogo puede ser algo mayor que el nominal: margen en el
# tramo recto mínimo entre dos curvas (si no alcanza, el plugin achicaría las dos).
HOLGURA_RECTO = 1.1
# Vértices prácticamente rectos que se pueden quitar a cada lado de un quiebre para que
# entre su curva (el plugin los endereza igual: giro ≤ GIRO_MIN_DEG y ≤ 0.25 ft).
RECTOS_MAX = 4
DESVIO_RECTO_FT = limpieza_tramos.DESVIO_MAX_FT
# lo que mira un quiebre está junto a su tubería: tuberías y estructuras a ≤ esto (+ el radio) de su caja
MARGEN_VECINOS_PX = 400.0


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


def _propios_cerca(pipes, ip, vi, tol):
    """Vértices de la MISMA tubería a ≤ tol px del vértice vi."""
    pts = pipes[ip]["pts"]
    return [vj for vj, q in enumerate(pts) if vj != vi and math.dist(q, pts[vi]) <= tol]


def _recto_quitable(pipes, structures, ip, j, curvas, ft_per_px, tol):
    """¿El vértice j es prácticamente recto y no lleva nada (se puede quitar)?"""
    p = pipes[ip]
    pts, kinds = p["pts"], p.get("vertex_kinds") or []
    if not (0 < j < len(pts) - 1) or len(kinds) != len(pts) or kinds[j] not in KINDS_QUIEBRE or j in curvas:
        return False
    if _giro_deg(pts[j - 1], pts[j], pts[j + 1]) > GIRO_MIN_DEG:
        return False
    if limpieza_tramos.compartido(pipes, ip, pts[j], limpieza_tramos.COMPARTIDO_FT / ft_per_px):
        return False                           # otra utilidad pasa por ahí: es una unión
    if any(not s.get("hidden") and not s.get("curve")
           for s in model_ops.structures_at_vertex(pipes, structures, ip, j)):
        return False
    return not _estructura_cerca(structures, pts[j][0], pts[j][1], tol, ft_per_px)


def _curvas_quietas(antes, despues, desvio_px):
    """Ninguna curva de la tubería desaparece, cambia de radio, se recorta ni su arco se
    corre más de `desvio_px` (tangencias y punto medio; geos de `limpieza_tramos.curvas`,
    por estructura)."""
    for clave, g in antes.items():
        h = despues.get(clave)
        if h is None or (h["clamped"] and not g["clamped"]) or abs(h["r"] - g["r"]) > 1e-6 * max(1.0, g["r"]):
            return False
        medio_g, medio_h = g["arc"][len(g["arc"]) // 2], h["arc"][len(h["arc"]) // 2]
        if max(math.dist(g["t1"], h["t1"]), math.dist(g["t2"], h["t2"]), math.dist(medio_g, medio_h)) > desvio_px:
            return False
    return True


def _por_estructura(pipes, structures, ip, ft_per_px):
    cv, geos = limpieza_tramos.curvas(pipes, structures, ip, ft_per_px)
    return {id(cv[k]): g for k, g in geos.items()}


def _enderezar(pipes, structures, ip, i, ft_per_px, tol, obligados=()):
    """Quita los vértices prácticamente rectos junto al quiebre i (los menos posibles; los
    `obligados` siempre) para que entre su curva. Devuelve el índice nuevo del quiebre, o
    None si así tampoco entra (entonces no se quita nada). Muta la tubería y, en gravedad,
    quita el buzón oculto de cada vértice quitado."""
    p = pipes[ip]
    pts = p["pts"]
    curvas = model_ops.curve_vertex_indices(p, structures, pipes, tol)
    lados = []
    for paso in (-1, 1):
        lado, j = [], i + paso
        while len(lado) < RECTOS_MAX and _recto_quitable(pipes, structures, ip, j, curvas, ft_per_px, tol):
            lado.append(j)
            j += paso
        lados.append(lado)
    antes_, despues_ = lados
    min_a = max((i - j for j in obligados if j < i), default=0)
    min_b = max((j - i for j in obligados if j > i), default=0)
    if min_a > len(antes_) or min_b > len(despues_):
        return None
    desvio_px = DESVIO_RECTO_FT / ft_per_px
    firma = _por_estructura(pipes, structures, ip, ft_per_px)
    for total in range(max(1, min_a + min_b), len(antes_) + len(despues_) + 1):
        for a in range(min_a, len(antes_) + 1):
            b = total - a
            if not (min_b <= b <= len(despues_)):
                continue
            quitar = sorted(antes_[:a] + despues_[:b], reverse=True)
            # el dibujo no se aparta: cada vértice quitado queda sobre la recta nueva
            ini, fin = pts[i - a - 1], pts[i]
            ini2, fin2 = pts[i], pts[i + b + 1]
            if any(math.dist(pts[v], limpieza_tramos.proyeccion(pts[v], *((ini, fin) if v < i else (ini2, fin2)))[0])
                   > desvio_px for v in quitar):
                continue
            copia = copy.deepcopy(p)
            for v in quitar:
                limpieza_tramos.quitar_vertice(copia, v)
            prueba = [copia if k == ip else o for k, o in enumerate(pipes)]
            i2 = i - a
            cv2 = model_ops.curve_vertex_indices(copia, structures, prueba, tol)
            if (i2 in cv2 or not _curvas_quietas(firma, _por_estructura(prueba, structures, ip, ft_per_px), desvio_px)
                    or not _entra(copia, i2, cv2, ft_per_px)):
                continue
            ocultas = [s for v in quitar for s in model_ops.structures_at_vertex(pipes, structures, ip, v)
                       if s.get("hidden") and not s.get("curve")]
            for v in quitar:
                limpieza_tramos.quitar_vertice(p, v)
            for s in ocultas:                  # el buzón oculto de un vértice que ya no existe
                k = next((k for k, o in enumerate(structures) if o is s), None)
                if k is not None:
                    del structures[k]
            return i2
    return None


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


def _lado(pts, k):
    """Hacia qué lado gira la línea en el vértice k (+1 / −1; 0 = recta)."""
    (ax, ay), (bx, by), (cx, cy) = pts[k - 1], pts[k], pts[k + 1]
    z = (bx - ax) * (cy - by) - (by - ay) * (cx - bx)
    return (z > 0) - (z < 0)


def _cruce(a, b, c, d):
    """Cruce de la recta a→b con la recta c→d (None si son paralelas)."""
    rx, ry, sx, sy = b[0] - a[0], b[1] - a[1], d[0] - c[0], d[1] - c[1]
    den = rx * sy - ry * sx
    if abs(den) < 1e-12 * max(1.0, math.hypot(rx, ry) * math.hypot(sx, sy)):
        return None
    t = ((c[0] - a[0]) * sy - (c[1] - a[1]) * sx) / den
    return (a[0] + rx * t, a[1] + ry * t)


def _a_polilinea(q, pts):
    return min(math.dist(q, limpieza_tramos.proyeccion(q, a, b)[0]) for a, b in zip(pts, pts[1:]))


def _unir_chaflan(pipes, structures, ip, i, nuevas, ft_per_px, tol):
    """El quiebre i no tuvo lugar: con el quiebre vecino del mismo giro (sin curva, o con la
    que este paso le acaba de poner) pasa a UNA curva mínima en el cruce de las rectas de
    fuera (ver CHAFLÁN arriba). Devuelve la CV o None (entonces nada cambia)."""
    p = pipes[ip]
    pts, kinds = p["pts"], p["vertex_kinds"]
    net = network_kind(p.get("layer") or "")
    r_ft = model_ops.radio_auto_ft(p)
    nuevas_ids = {id(s) for s in nuevas}
    curvas = model_ops.curve_vertex_indices(p, structures, pipes, tol)
    for j in (i - 1, i + 1):
        a, b = min(i, j), max(i, j)
        if a < 1 or b > len(pts) - 2 or kinds[j] not in KINDS_QUIEBRE or i in curvas:
            continue
        cv_j = curvas.get(j)
        if cv_j is not None and (id(cv_j) not in nuevas_ids or not cv_j.get("quiebre")):
            continue                           # un codo de la tinta (u otra curva) no se toca
        giros = [_giro_deg(pts[k - 1], pts[k], pts[k + 1]) for k in (a, b)]
        if min(giros) <= GIRO_MIN_DEG or _lado(pts, a) != _lado(pts, b):
            continue
        if not _vertice_libre(pipes, ip, j, tol, False) or _estructura_cerca(structures, *pts[j], tol, ft_per_px):
            continue
        P = _cruce(pts[a - 1], pts[a], pts[b], pts[b + 1])
        if P is None:
            continue
        d1, d2 = limpieza_tramos.unit(pts[a - 1], pts[a]), limpieza_tramos.unit(pts[b], pts[b + 1])
        if (d1 is None or d2 is None
                or (P[0] - pts[a][0]) * d1[0] + (P[1] - pts[a][1]) * d1[1] <= 0
                or (pts[b][0] - P[0]) * d2[0] + (pts[b][1] - P[1]) * d2[1] <= 0):
            continue                           # el cruce no queda entre los dos quiebres
        if _estructura_cerca(structures, P[0], P[1], tol, ft_per_px) or any(
                math.hypot(qx - P[0], qy - P[1]) <= tol for jp, o in enumerate(pipes)
                if jp != ip and not o.get("world") for qx, qy in o.get("pts") or ()):
            continue
        copia = copy.deepcopy(p)
        limpieza_tramos.quitar_vertice(copia, b)
        copia["pts"][a] = type(pts[a])((P[0], P[1]))
        resto = [s for s in structures if s is not cv_j]
        prueba = [copia if k == ip else o for k, o in enumerate(pipes)]
        cv2 = model_ops.curve_vertex_indices(copia, resto, prueba, tol)
        if a in cv2 or not _entra(copia, a, cv2, ft_per_px):
            continue
        g = _geo(copia["pts"], a, r_ft / ft_per_px, set(cv2) | {a}, ft_per_px)
        # el dibujo no se aparta del plano más que la curva mínima de cada quiebre
        tol_d = (max(r_ft * (1.0 / math.cos(math.radians(gk) / 2.0) - 1.0) for gk in giros)
                 + DESVIO_RECTO_FT) / ft_per_px
        viejo = [pts[a - 1], pts[a], pts[b], pts[b + 1]]
        nuevo = [pts[a - 1]] + list(g["arc"]) + [pts[b + 1]]
        if (any(_a_polilinea(q, nuevo) > tol_d for q in (pts[a], pts[b]))
                or any(_a_polilinea(q, viejo) > tol_d for q in g["arc"])):
            continue
        # aplicar: los buzones ocultos de los dos vértices se van (gravedad); la CV va al cruce
        ocultas = [s for k in (a, b) for s in model_ops.structures_at_vertex(pipes, structures, ip, k)
                   if s is not cv_j and s.get("hidden") and not s.get("curve")]
        structures[:] = [s for s in structures if not any(s is o for o in ocultas)]
        limpieza_tramos.quitar_vertice(p, b)
        p["pts"][a] = type(pts[a])((P[0], P[1]))
        if cv_j is not None:
            model_ops.translate_structure(cv_j, P[0] - float(cv_j["x"]), P[1] - float(cv_j["y"]))
            return cv_j
        return _marcar_cv(structures, P[0], P[1], net)
    return None


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
    # cada tubería con lo que tiene ALREDEDOR (`vecindario`): todo lo que se mira está junto a sus
    # vértices. Mismo resultado y mismo orden; con 36 mapas de alcantarillado, cada quiebre se
    # comparaba con las 12 000 tuberías y 20 000 estructuras de la hoja (2026-10-23).
    vec = vecindario.Vecindario(pipes, structures, ft_per_px)
    lista = list(range(len(pipes)) if indices is None else indices)
    for k_av, ip in enumerate(lista):
        avance.avisar(_tr("Buscando los quiebres que entran como curva…"), k_av + 1, len(lista))
        p = pipes[ip]
        net = network_kind(p.get("layer") or "")
        pts = p.get("pts") or []
        kinds = p.get("vertex_kinds") or []
        if p.get("world") or net not in REDES_CON_CURVAS or len(pts) < 3 or len(kinds) != len(pts):
            continue
        if not any(kinds[i] in KINDS_QUIEBRE and _giro_deg(pts[i - 1], pts[i], pts[i + 1]) > GIRO_MIN_DEG
                   for i in range(1, len(pts) - 1)):
            continue                           # sin quiebres: nada que hacer (lo mismo que abajo)
        margen = MARGEN_VECINOS_PX + 4 * tol + 4 * (model_ops.radio_auto_ft(p) + DESVIO_RECTO_FT) / ft_per_px
        sub_p, k, sub_s = vec.de(ip, margen)
        antes = list(sub_s)
        _quiebres_de(sub_p, sub_s, k, ft_per_px, tol, nuevas, sin_lugar)
        vec.aplicar(ip, antes, sub_s)
    return nuevas, sin_lugar


def _quiebres_de(pipes, structures, ip, ft_per_px, tol, nuevas, sin_lugar):
    """Los quiebres de la tubería `ip` (el cuerpo de siempre de `curvas_en_quiebres`)."""
    p = pipes[ip]
    net = network_kind(p.get("layer") or "")
    pts = p.get("pts") or []
    kinds = p.get("vertex_kinds") or []
    curvas = model_ops.curve_vertex_indices(p, structures, pipes, tol)
    cand, fallidos = [], []
    for i in range(1, len(pts) - 1):
        if kinds[i] in KINDS_QUIEBRE and i not in curvas:
            g = _giro_deg(pts[i - 1], pts[i], pts[i + 1])
            if g > GIRO_MIN_DEG:
                cand.append((-g, i, tuple(pts[i])))
    for _g, _i, q in sorted(cand):
        # (si se quitó un vértice recto, los índices se corren: el quiebre, por su lugar)
        pts = p["pts"]
        i = next((k for k, w in enumerate(pts) if w[0] == q[0] and w[1] == q[1]), None)
        if i is None or not (0 < i < len(pts) - 1) or i in curvas:
            continue
        x, y = pts[i]
        if (not _vertice_libre(pipes, ip, i, tol, False)
                or _estructura_cerca(structures, x, y, tol, ft_per_px)):
            continue
        # en gravedad, un vértice propio pegado al quiebre se lleva su buzón: solo si se quita
        propios = _propios_cerca(pipes, ip, i, tol) if net == "gravity" else []
        if propios or not _entra(p, i, curvas, ft_per_px):
            i2 = _enderezar(pipes, structures, ip, i, ft_per_px, tol, propios)
            if i2 is None:
                if not propios:
                    fallidos.append((float(x), float(y)))
                continue
            i = i2
            curvas = model_ops.curve_vertex_indices(p, structures, pipes, tol)
        curvas[i] = _marcar_cv(structures, x, y, net)
        nuevas.append(curvas[i])
    # sin lugar: con el quiebre de al lado puede ser UN chaflán → una curva (CHAFLÁN arriba)
    for q in fallidos:
        i = next((k for k, w in enumerate(p["pts"]) if w[0] == q[0] and w[1] == q[1]), None)
        if i is None:
            continue                       # ya entró en el chaflán de su vecino
        s = _unir_chaflan(pipes, structures, ip, i, nuevas, ft_per_px, tol)
        if s is None:
            sin_lugar.append(q)
        elif not any(s is o for o in nuevas):
            nuevas.append(s)

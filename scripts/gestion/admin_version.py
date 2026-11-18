"""Editor de una versión en el administrador (pedido del usuario 2026-11-18: «que no me sugiera funciones… ver el
lienzo final y agregar una fila más o un elemento más, más directo y visual»).

La página se ve como la del cliente (mismas tarjetas por Novedades / Mejoras / Correcciones) y todo se escribe
encima: título, detalle y observación de cada cambio, «+ Agregar cambio» al final de cada sección, ↑ ↓ ✕ por
tarjeta, y las funciones del diagrama como fichas que se buscan y asocian a mano (o se crean ahí mismo). Nada se
sugiere solo. Cada cambio se guarda solo (POST JSON a /api/version) y cada tarjeta dice qué le falta para publicar.
"""
from __future__ import annotations

import html
import json
import os

import datos as D
import sitio

E = html.escape

CSS = """
.barra-ed{position:sticky;top:0;z-index:5;background:var(--bg);display:flex;gap:10px;align-items:center;
flex-wrap:wrap;padding:10px 0;border-bottom:1px solid var(--line)}
.barra-ed .estado{margin-left:auto;color:var(--muted);font-size:13px}.barra-ed .estado.err{color:#c0392b}
.btn{display:inline-block;border:1px solid var(--line);background:var(--card);color:var(--text);border-radius:9px;
padding:6px 12px;font:inherit;font-weight:600;cursor:pointer;text-decoration:none}
.btn.p{background:var(--accent);border-color:var(--accent);color:#fff}.btn.r{color:#c0392b}
.btn.mini{padding:2px 8px;font-size:13px}
.ed{width:100%;border:1px dashed transparent;border-radius:8px;background:transparent;color:inherit;font:inherit;
padding:3px 6px;margin:0 -6px;resize:none;overflow:hidden}
.ed:hover{border-color:var(--line)}.ed:focus{outline:none;border-style:solid;border-color:var(--accent);
background:var(--card)}.ed::placeholder{color:var(--muted);opacity:.7}
h1 .ed{font-size:26px;font-weight:700}.tit{font-weight:700}.det-ed{color:var(--muted)}
.obs-ed{font-size:12px;color:var(--accent)}
.nov.e{position:relative}.nov .cab{display:flex;gap:6px;align-items:center}
.nov .cab .acc{display:flex;gap:4px;opacity:.35}.nov:hover .cab .acc,.nov:focus-within .cab .acc{opacity:1}
select.tipo{padding:3px 6px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--text);
font:inherit;font-size:13px}
.chips{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-top:8px}
.chip{display:inline-flex;align-items:center;gap:4px;border-radius:999px;padding:2px 4px 2px 10px;font-size:13px;
font-weight:600;border:1px solid transparent}.chip button{border:0;background:none;color:inherit;cursor:pointer;
font:inherit;padding:0 5px;opacity:.7}.chip button:hover{opacity:1}
.chip.pend{border:1px dashed #c0392b}.chip.falta{background:#fde8e8;color:#8a1c1c}
.buscar-f{position:relative}.buscar-f input{border:1px dashed var(--line);border-radius:999px;padding:3px 12px;
background:transparent;color:var(--text);font:inherit;font-size:13px;width:210px}
.buscar-f input:focus{outline:none;border-style:solid;border-color:var(--accent);background:var(--card)}
.menu{position:absolute;z-index:9;top:calc(100% + 4px);left:0;width:440px;max-width:80vw;max-height:440px;
overflow:auto;background:var(--card);border:1px solid var(--line);border-radius:10px;
box-shadow:0 8px 24px rgba(0,0,0,.14);padding:4px}
.menu .op{display:flex;gap:8px;align-items:center;padding:6px 8px;border-radius:7px;cursor:pointer;font-size:13px}
.menu .op.on,.menu .op:hover{background:var(--soft)}.menu .op .ruta{color:var(--muted);font-size:12px}
.menu .op .dot{flex:0 0 10px;height:10px;border-radius:50%}.menu .vacio{padding:8px;color:var(--muted);font-size:13px}
.menu .crear{border-top:1px solid var(--line);margin-top:4px;padding:8px;display:grid;gap:6px;font-size:13px}
.menu .crear select{width:100%;padding:5px;border:1px solid var(--line);border-radius:7px;background:var(--card);
color:var(--text);font:inherit;font-size:13px}
.falta-txt{font-size:12px;color:#c0392b;margin-top:6px}
.agregar{display:block;width:100%;border:1px dashed var(--line);border-radius:12px;background:transparent;
color:var(--muted);padding:10px;font:inherit;font-weight:600;cursor:pointer;margin:8px 0}
.agregar:hover{border-color:var(--accent);color:var(--accent)}
.listo{border-radius:10px;padding:8px 12px;margin:12px 0;font-size:14px}
.listo.ok{background:#e4f5ea;color:#1d6b37}.listo.no{background:#fff3e0;color:#8a4b00}
.bloqueada .ed,.bloqueada select,.bloqueada .acc,.bloqueada .buscar-f,.bloqueada .agregar,.bloqueada .chip button
{pointer-events:none}.bloqueada .agregar,.bloqueada .acc,.bloqueada .buscar-f,.bloqueada .chip button{display:none}
"""

JS = r"""
const D = JSON.parse(document.getElementById('datos').textContent);
const V = D.version, FUN = new Map(D.funciones.map(f => [f.id, f]));
const $ = (s, r = document) => r.querySelector(s);
const el = (tag, props = {}, ...hijos) => { const n = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) { if (k === 'class') n.className = v; else if (k === 'style') n.style.cssText = v;
    else if (k.startsWith('on')) n.addEventListener(k.slice(2), v); else n.setAttribute(k, v); }
  for (const h of hijos) if (h != null) n.append(h); return n; };
let reloj = null;
function estado(t, err) { const s = $('#estado'); s.textContent = t; s.classList.toggle('err', !!err); }
function guardar() { clearTimeout(reloj); estado('Sin guardar…'); reloj = setTimeout(enviar, 500); }
async function enviar() {
  estado('Guardando…');
  try {
    const r = await fetch('/api/version', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(V)});
    const j = await r.json();
    if (!j.ok) return estado('No se guardó: ' + j.error, true);
    estado('Guardado ✓'); listo(j.pendientes);
  } catch (e) { estado('No se guardó: ' + e, true); }
}
function listo(p) {
  const b = $('#listo'); if (!b) return;
  b.className = 'listo ' + (p.length ? 'no' : 'ok');
  b.textContent = !V.novedades.length ? 'Aún no tiene cambios: agrégalos con «+ Agregar».'
    : p.length ? `Falta para publicar: ${p.length} punto(s). Lo ves en rojo en cada cambio.`
                           : 'Lista para publicar: cada cambio tiene sus funciones aprobadas.';
}
function autoalto(t) { t.style.height = 'auto'; t.style.height = t.scrollHeight + 'px'; }
function campo(obj, k, cls, ph, multi) {
  const n = el(multi ? 'textarea' : 'input', {class: 'ed ' + cls, placeholder: ph, rows: 1});
  n.value = obj[k] || '';
  n.addEventListener('input', () => { obj[k] = n.value; if (multi) autoalto(n); guardar(); revisar(); });
  if (multi) requestAnimationFrame(() => autoalto(n));
  return n;
}
function falta(n) {
  const out = [];
  if (!(n.titulo || '').trim()) out.push('Ponle un título.');
  if (!(n.funciones || []).length) out.push('Asocia al menos una función del diagrama.');
  for (const id of n.funciones || []) { const f = FUN.get(id);
    if (!f) out.push(`La función «${id}» ya no existe.`);
    else if (!f.estado) out.push(`«${f.nombre}» aún no tiene estado aprobado.`); }
  return out;
}
function revisar() { document.querySelectorAll('.nov.e[data-i]').forEach(c => {
  const n = V.novedades[+c.dataset.i]; const t = falta(n); const w = $('.falta-txt', c);
  w.textContent = t.join(' '); w.style.display = t.length ? '' : 'none'; }); }
function chip(n, id) {
  const f = FUN.get(id);
  const c = el('span', {class: 'chip' + (!f ? ' falta' : (!f.estado ? ' pend' : '')),
    style: f ? `background:${f.fondo};color:${f.texto}` : '', title: f ? `${f.ruta}\n${f.est_nombre}` : 'No existe'},
    f ? f.nombre + (f.estado ? '' : ' · sin aprobar') : id,
    el('button', {title: 'Quitar del cambio', onclick: () => { n.funciones = n.funciones.filter(x => x !== id);
      pintar(); guardar(); }}, '✕'));
  return c;
}
function normal(s) { return s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase(); }
function buscador(n) {
  const caja = el('span', {class: 'buscar-f'});
  const inp = el('input', {placeholder: '+ Asociar función…'});
  let menu = null, ops = [], sel = 0;
  const cerrar = () => { if (menu) menu.remove(); menu = null; };
  const elegir = id => { if (!n.funciones) n.funciones = []; if (!n.funciones.includes(id)) n.funciones.push(id);
    pintar(); guardar(); setTimeout(() => { const b = document.querySelector(`.nov.e[data-i="${V.novedades.indexOf(n)}"] .buscar-f input`); if (b) b.focus(); }); };
  const abrir = () => {
    cerrar(); const q = normal(inp.value.trim()); const palabras = q.split(/\s+/).filter(Boolean);
    ops = D.funciones.filter(f => !(n.funciones || []).includes(f.id) &&
      palabras.every(p => normal(f.nombre + ' ' + f.ruta).includes(p))).slice(0, 40);
    sel = 0; menu = el('div', {class: 'menu'});
    ops.forEach((f, i) => menu.append(el('div', {class: 'op' + (i === sel ? ' on' : ''),
      onmousedown: e => { e.preventDefault(); elegir(f.id); }},
      el('span', {class: 'dot', style: `background:${f.fondo}`}),
      el('span', {}, f.nombre, el('div', {class: 'ruta'}, f.ruta + ' · ' + f.est_nombre)))));
    if (!ops.length) menu.append(el('div', {class: 'vacio'}, 'Ninguna función coincide.'));
    if (inp.value.trim()) {
      const grupo = el('select', {}, ...D.grupos.map(([id, r]) => el('option', {value: id}, r)));
      const est = el('select', {}, ...D.estados.map(([id, nom]) => { const o = el('option', {value: id}, nom);
        if (id === 'probado') o.selected = true; return o; }));
      const crear = async () => {
        const r = await fetch('/api/funcion', {method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({grupo: grupo.value, nombre: inp.value.trim(), estado: est.value})});
        const j = await r.json(); if (!j.ok) return estado('No se creó: ' + j.error, true);
        D.funciones.push(j.funcion); FUN.set(j.funcion.id, j.funcion); elegir(j.funcion.id);
        estado('Función creada: ' + j.funcion.nombre);
      };
      menu.append(el('div', {class: 'crear', onmousedown: e => { if (e.target.tagName !== 'SELECT') e.preventDefault(); }},
        el('b', {}, `Crear la función «${inp.value.trim()}» en el diagrama`), el('label', {}, 'Grupo'), grupo,
        el('label', {}, 'Estado'), est, el('button', {class: 'btn p mini', onclick: crear}, 'Crear y asociar')));
    }
    caja.append(menu);
  };
  inp.addEventListener('focus', abrir); inp.addEventListener('input', abrir);
  inp.addEventListener('blur', () => setTimeout(() => { if (!caja.contains(document.activeElement)) cerrar(); }, 150));
  inp.addEventListener('keydown', e => {
    if (!menu) return;
    const items = menu.querySelectorAll('.op');
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); if (!items.length) return;
      items[sel].classList.remove('on'); sel = (sel + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
      items[sel].classList.add('on'); items[sel].scrollIntoView({block: 'nearest'}); }
    else if (e.key === 'Enter') { e.preventDefault(); if (ops[sel]) elegir(ops[sel].id); }
    else if (e.key === 'Escape') { cerrar(); inp.blur(); }
  });
  caja.append(inp); return caja;
}
function mover(n, paso) {
  const misma = V.novedades.filter(x => x.tipo === n.tipo); const k = misma.indexOf(n) + paso;
  if (k < 0 || k >= misma.length) return;
  const a = V.novedades.indexOf(n), b = V.novedades.indexOf(misma[k]);
  [V.novedades[a], V.novedades[b]] = [V.novedades[b], V.novedades[a]]; pintar(); guardar();
}
function tarjeta(n) {
  const i = V.novedades.indexOf(n);
  const tipo = el('select', {class: 'tipo', title: 'Mover a otra sección'},
    ...Object.entries(D.tipos).map(([t, nom]) => { const o = el('option', {value: t}, nom); if (t === n.tipo) o.selected = true; return o; }));
  tipo.addEventListener('change', () => { n.tipo = tipo.value; V.novedades.splice(V.novedades.indexOf(n), 1);
    V.novedades.push(n); pintar(); guardar(); });
  const quitar = () => { if ((n.titulo || n.detalle || (n.funciones || []).length) &&
      !confirm(`¿Quitar el cambio «${n.titulo || 'sin título'}»?`)) return;
    V.novedades.splice(V.novedades.indexOf(n), 1); pintar(); guardar(); };
  const chips = el('div', {class: 'chips'}, ...(n.funciones || []).map(id => chip(n, id)), buscador(n));
  return el('div', {class: 'nov e', 'data-i': i},
    el('div', {class: 'cab'}, campo(n, 'titulo', 'tit', 'Título corto del cambio'),
      el('span', {class: 'acc'}, tipo, el('button', {class: 'btn mini', title: 'Subir', onclick: () => mover(n, -1)}, '↑'),
        el('button', {class: 'btn mini', title: 'Bajar', onclick: () => mover(n, 1)}, '↓'),
        el('button', {class: 'btn mini r', title: 'Quitar', onclick: quitar}, '✕'))),
    campo(n, 'detalle', 'det-ed', 'Detalle en una línea, para el cliente (opcional)', true),
    campo(n, 'observacion', 'obs-ed', 'Atiende la observación… (opcional)'),
    chips, el('div', {class: 'falta-txt'}));
}
function pendiente(p) {
  return el('div', {class: 'nov e'}, el('div', {class: 'cab'}, campo(p, 'titulo', 'tit', 'Qué viene en la próxima entrega'),
    el('span', {class: 'acc'}, el('button', {class: 'btn mini r', title: 'Quitar', onclick: () => {
      V.pendientes.splice(V.pendientes.indexOf(p), 1); pintar(); guardar(); }}, '✕'))),
    campo(p, 'detalle', 'det-ed', 'Detalle (opcional)', true));
}
function pintar() {
  const raiz = $('#cambios'); raiz.replaceChildren();
  for (const [t, nombre] of Object.entries(D.tipos)) {
    raiz.append(el('h2', {}, nombre));
    V.novedades.filter(n => n.tipo === t).forEach(n => raiz.append(tarjeta(n)));
    raiz.append(el('button', {class: 'agregar', onclick: () => {
      const n = {tipo: t, titulo: '', detalle: '', funciones: [], observacion: ''}; V.novedades.push(n); pintar(); guardar();
      const c = document.querySelector(`.nov.e[data-i="${V.novedades.indexOf(n)}"] .tit`); if (c) c.focus(); }},
      `+ Agregar a ${nombre}`));
  }
  raiz.append(el('h2', {}, 'Para la próxima entrega'));
  (V.pendientes = V.pendientes || []).forEach(p => raiz.append(pendiente(p)));
  raiz.append(el('button', {class: 'agregar', onclick: () => { const p = {titulo: '', detalle: ''}; V.pendientes.push(p);
    pintar(); const cs = document.querySelectorAll('#cambios .nov.e:not([data-i]) .tit'); if (cs.length) cs[cs.length - 1].focus(); }},
    '+ Agregar a la próxima entrega'));
  revisar();
}
const cab = $('#cabecera');
cab.append(el('h1', {}, 'Versión ' + V.numero),
  el('div', {class: 'sub'}, el('input', {type: 'date', class: 'ed', style: 'width:auto', value: V.fecha || '',
    onchange: e => { V.fecha = e.target.value; guardar(); }})),
  campo(V, 'titulo', 'tit', 'Título de la entrega (lo ve el cliente)'),
  campo(V, 'resumen', '', 'Resumen en una o dos líneas (opcional)', true));
pintar(); listo(D.pendientes);
"""


# ───────────────────────── editor de versiones (pedido 2026-11-18) ─────────────────────────
# El administrador arma cada versión a mano sobre la vista del cliente: nada se sugiere solo.

def nueva_version(pr: D.Proyecto, numero, titulo="", hoy=None):
    numero = (numero or "").strip()
    if not numero or not all(p.isdigit() for p in numero.split(".")):
        raise ValueError("El número de versión va así: 2.2.0")
    if any(v.numero == numero for v in pr.versiones):
        raise ValueError(f"La versión {numero} ya existe")
    v = D.Version(archivo=D.ruta("versiones", f"{numero}.toml"), numero=numero,
                  fecha=(hoy or D._dt.date.today()).isoformat(), titulo=(titulo or "").strip())
    os.makedirs(os.path.dirname(v.archivo), exist_ok=True)
    D.guardar_version(v)
    pr.versiones.append(v)
    pr.versiones.sort(key=lambda x: D._clave_version(x.numero), reverse=True)
    return v


def _texto(d, k):
    v = d.get(k, "")
    return v.strip() if isinstance(v, str) else ""


def actualizar_version(pr: D.Proyecto, numero, datos_v):
    """Escribe lo que armó el editor: encabezado, cambios (en su orden) y lo de la próxima entrega. Solo una versión
    sin publicar (una publicada se pasa antes a borrador). Las claves que el editor no conoce se conservan.
    Devuelve lo que aún impide publicarla."""
    v = next((x for x in pr.versiones if x.numero == numero), None)
    if v is None:
        raise ValueError(f"No existe la versión {numero}")
    if v.publicada:
        raise ValueError(f"La versión {numero} está publicada: pásala a borrador para editarla")
    novedades = []
    for n in datos_v.get("novedades", []):
        if n.get("tipo") not in D.TIPOS_NOVEDAD:
            raise ValueError(f"Tipo de cambio inválido: {n.get('tipo')}")
        fun = []
        for fid in n.get("funciones", []) or []:
            if isinstance(fid, str) and fid and fid not in fun:
                fun.append(fid)
        d = {k: x for k, x in n.items() if k not in ("tipo", "titulo", "detalle", "funciones", "observacion")}
        novedades.append(dict(tipo=n["tipo"], titulo=_texto(n, "titulo"), detalle=_texto(n, "detalle"),
                              funciones=fun, observacion=_texto(n, "observacion"), **d))
    pendientes = [dict(titulo=_texto(p, "titulo"), detalle=_texto(p, "detalle"))
                  for p in datos_v.get("pendientes", []) if _texto(p, "titulo") or _texto(p, "detalle")]
    v.fecha, v.titulo, v.resumen = _texto(datos_v, "fecha"), _texto(datos_v, "titulo"), _texto(datos_v, "resumen")
    v.novedades, v.pendientes = novedades, pendientes
    D.guardar_version(v)
    return D.pendientes_version(pr, v)


def _datos(pr, v):
    fun = _datos_funciones(pr)
    version = dict(numero=v.numero, fecha=v.fecha, titulo=v.titulo, resumen=v.resumen,
                   novedades=v.novedades, pendientes=v.pendientes)
    return dict(version=version, funciones=fun, grupos=_rutas(pr), tipos=D.TIPOS_NOVEDAD,
                estados=[(e, D.ESTADOS[e][0] or "Sin clasificar") for e in D.ORDEN_ESTADOS],
                pendientes=D.pendientes_version(pr, v))


def _rutas(pr):
    out = []

    def bajar(g, pref):
        nombre = f"{pref} › {g.nombre}" if pref else g.nombre
        out.append((g.id, nombre))
        for h in pr.hijos(g.id):
            bajar(h, nombre)
    for r in pr.raices():
        bajar(r, "")
    return out


def funcion_json(pr, f):
    return next(x for x in _datos_funciones(pr) if x["id"] == f.id)


def _datos_funciones(pr):
    rutas = dict(_rutas(pr))
    return [dict(id=f.id, nombre=f.nombre, ruta=rutas.get(f.grupo, f.grupo), estado=f.estado,
                 est_nombre=D.ESTADOS.get(f.estado, D.ESTADOS[""])[0] or "Sin clasificar",
                 fondo=D.ESTADOS.get(f.estado, D.ESTADOS[""])[2], texto=D.ESTADOS.get(f.estado, D.ESTADOS[""])[3])
            for f in pr.funciones]


def pagina(pr, v):
    datos = json.dumps(_datos(pr, v), ensure_ascii=False).replace("</", "<\\/")
    if v.publicada:
        aviso = ('<div class="listo no">Esta versión está publicada: el cliente ya la ve. Para cambiarla, pásala a '
                 'borrador (deja de verse hasta que la vuelvas a publicar).'
                 f'<form method="post" action="/version" style="display:inline;margin-left:8px">'
                 f'<input type="hidden" name="numero" value="{E(v.numero)}"><input type="hidden" name="publicada" '
                 f'value="0"><input type="hidden" name="volver" value="1"><button class="btn mini">Pasar a borrador'
                 '</button></form></div>')
        listo = ""
    else:
        aviso, listo = "", '<div id="listo" class="listo"></div>'
    cuerpo = (f'<style>{CSS}</style><div class="barra-ed"><a class="btn" href="/panel#versiones">← Versiones</a>'
              f'<a class="btn" href="/version/{E(v.numero)}" target="_blank">Ver como el cliente</a>'
              f'<span id="estado" class="estado">{"Solo lectura" if v.publicada else "Todo se guarda solo."}</span></div>'
              f'{aviso}<div class="{"bloqueada" if v.publicada else ""}"><div id="cabecera"></div>{listo}'
              '<div id="cambios"></div></div>'
              f'<script type="application/json" id="datos">{datos}</script>'
              + f"<script>{JS}</script>")
    if v.publicada:                                       # vista sin guardar: el editor no envía nada
        cuerpo = cuerpo.replace("function guardar() {", "function guardar() { return;", 1).replace(
            "pintar(); listo(D.pendientes);", "pintar();", 1)
    return sitio.pagina(pr, f"Editar versión {v.numero}", cuerpo, "", admin=True)


def api(ruta, datos_post):
    """POST JSON del editor. Devuelve el dict de respuesta."""
    pr = D.leer()
    if ruta == "api/version":
        pend = actualizar_version(pr, datos_post.get("numero", ""), datos_post)
        return dict(ok=True, pendientes=pend)
    if ruta == "api/funcion":
        f = D.agregar_funcion(pr, datos_post.get("grupo", ""), datos_post.get("nombre", ""),
                              datos_post.get("estado", "probado"))
        D.guardar_funciones(pr)
        return dict(ok=True, funcion=funcion_json(pr, f))
    raise ValueError(f"Acción desconocida: {ruta}")

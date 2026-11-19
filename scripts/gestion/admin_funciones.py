"""Editor de las funciones del diagrama sobre la MISMA vista que ve el cliente (pedido del usuario 2026-11-18: «que
sea igual a la vista del cliente y que yo desde ahí inserte o edite filas o nuevas tarjetas con módulos de manera
fácil y simple»).

Se escribe encima de todo: el nombre de cada función, el título y subtítulo de cada tarjeta y de cada área. Clic en
el estado de una fila = elegir otro. «+ Agregar función» al pie de cada tarjeta (Enter crea y deja escribir la
siguiente), «+ Nueva tarjeta» al final de cada área y «+ Nueva área» al final. Las filas se arrastran por su asa
(⋮⋮) a otro lugar u otra tarjeta. Cada cambio se guarda al momento (POST JSON a /api/f/… y /api/g/…).
"""
from __future__ import annotations

import html
import json

import datos as D
import sitio

E = html.escape

CSS = """
.barra-ed{position:sticky;top:0;z-index:5;background:var(--bg);display:flex;gap:10px;align-items:center;
flex-wrap:wrap;padding:10px 0;border-bottom:1px solid var(--line)}
.barra-ed .estado{margin-left:auto;color:var(--muted);font-size:13px}.barra-ed .estado.err{color:#c0392b}
.btn{display:inline-block;border:1px solid var(--line);background:var(--card);color:var(--text);border-radius:9px;
padding:6px 12px;font:inherit;font-weight:600;cursor:pointer;text-decoration:none}
[contenteditable]{border-radius:6px;outline:none;padding:0 3px;margin:0 -3px;cursor:text}
[contenteditable]:hover{box-shadow:inset 0 0 0 1px var(--line)}
[contenteditable]:focus{box-shadow:inset 0 0 0 1px var(--accent);background:var(--card)}
[contenteditable]:empty:before{content:attr(data-ph);color:transparent}
.grupo:hover [contenteditable]:empty:before,.area>.sub:hover [contenteditable]:empty:before,
[contenteditable]:empty:focus:before{color:var(--muted);opacity:.7}
.grupo{position:relative}.grupo .quitar-g{position:absolute;top:8px;right:8px;opacity:0;border:0;background:none;
color:#c0392b;cursor:pointer;font:inherit;font-size:13px}.grupo:hover .quitar-g{opacity:.8}
.grupo li{position:relative;border-radius:6px}.grupo li.arr{opacity:.4}
.grupo li.antes{box-shadow:0 -2px 0 var(--accent)}.grupo ul.al-final{box-shadow:0 2px 0 var(--accent)}
.asa{cursor:grab;color:var(--muted);opacity:0;font-size:12px;margin-left:-14px;width:12px;user-select:none}
.grupo li:hover .asa{opacity:.8}
.grupo li .est{cursor:pointer;border-radius:999px;padding:0 6px;border:1px solid transparent}
.grupo li .est:hover{border-color:var(--line)}
.grupo li .x{opacity:0;border:0;background:none;color:#c0392b;cursor:pointer;font:inherit;font-size:12px;padding:0 2px}
.grupo li:hover .x{opacity:.8}
.nueva-f{color:var(--muted);font-size:14px;padding:4px 0;cursor:pointer;border:0;background:none;font:inherit;
text-align:left}.nueva-f:hover{color:var(--accent)}
.nueva-t{border:1px dashed var(--line);border-radius:12px;display:grid;place-items:center;min-height:90px;
color:var(--muted);font-weight:600;cursor:pointer;background:transparent;font:inherit}
.nueva-t:hover{border-color:var(--accent);color:var(--accent)}
.campo-nuevo{width:100%;border:1px solid var(--accent);border-radius:8px;padding:5px 8px;background:var(--card);
color:var(--text);font:inherit;font-size:14px}
.menu-est{position:absolute;z-index:20;background:var(--card);border:1px solid var(--line);border-radius:10px;
box-shadow:0 8px 24px rgba(0,0,0,.18);padding:4px;min-width:220px}
.menu-est div{display:flex;gap:8px;align-items:center;padding:6px 8px;border-radius:7px;cursor:pointer;font-size:13px}
.menu-est div:hover{background:var(--soft)}.menu-est .int{color:var(--muted);font-size:12px;margin-left:auto}
.priv{opacity:.5}.priv:hover{opacity:.85}
.candado{border:0;background:none;cursor:pointer;font-size:12px;padding:0 2px;opacity:0;filter:grayscale(1)}
.grupo li:hover .candado,.grupo:hover>.cab-g .candado,.area>h2:hover .candado{opacity:.7}
.candado.on{opacity:1!important;filter:none}
.tag-priv{font-size:11px;font-weight:700;color:#8a4b00;background:#fff3e0;border-radius:999px;padding:1px 7px;
margin-left:6px;vertical-align:middle}
.grupo .cab-g{position:absolute;top:8px;right:8px;display:flex;gap:2px;align-items:center}
.grupo .cab-g .quitar-g{position:static}
.grupo>h3{padding-right:42px}
.barra-ed .p{background:var(--accent);border-color:var(--accent);color:#fff}
.faltan{background:#fde8e8;color:#8a1c1c;border-radius:10px;padding:10px 14px;margin:12px 0;font-size:14px}
.faltan b{display:block;margin-bottom:4px}.faltan a{color:inherit;cursor:pointer;text-decoration:underline}
.faltan ul{margin:4px 0 0;padding-left:18px}
.grupo li.bloquea{box-shadow:0 0 0 2px #e05252;background:rgba(224,82,82,.08)}
.grupo li.destello{animation:destello 1.6s ease-out 2}
@keyframes destello{0%{background:rgba(224,82,82,.45)}100%{background:transparent}}
.area .quitar-a{float:right;border:0;background:none;color:#c0392b;cursor:pointer;font:inherit;font-size:13px;
opacity:.6}
"""

JS = r"""
const D = JSON.parse(document.getElementById('datos').textContent);
const EST = new Map(D.estados.map(e => [e.id, e]));
const $ = (s, r = document) => r.querySelector(s);
const el = (tag, props = {}, ...hijos) => { const n = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) { if (k === 'class') n.className = v; else if (k === 'style') n.style.cssText = v;
    else if (k.startsWith('on')) n.addEventListener(k.slice(2), v); else n.setAttribute(k, v); }
  for (const h of hijos) if (h != null) n.append(h); return n; };
let ultimoEstado = 'probado';
function aviso(t, err) { const s = $('#estado'); s.textContent = t; s.classList.toggle('err', !!err); }
async function api(ruta, datos) {
  aviso('Guardando…');
  try { const r = await fetch('/api/' + ruta, {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(datos)}); const j = await r.json();
    if (!j.ok) { aviso('No se guardó: ' + j.error, true); return null; } aviso('Guardado ✓'); return j;
  } catch (e) { aviso('No se guardó: ' + e, true); return null; }
}
function privG(gid) { const vistos = new Set(); while (gid && !vistos.has(gid)) { vistos.add(gid);
  const g = D.priv[gid]; if (!g) return false; if (g.privado) return true; gid = g.padre; } return false; }
const oculta = (g, f) => f.privado || privG(g.id);
const todasF = () => D.areas.flatMap(a => a.grupos.flatMap(g => g.funciones.filter(f => !oculta(g, f))));
function faltan() {
  const out = [];
  for (const a of D.areas) for (const g of a.grupos) for (const f of g.funciones) {
    const motivos = D.bloquean[f.id]; if (!motivos) continue;
    if (!f.estado) out.push({f, txt: `«${f.nombre}» no tiene estado`, motivos});
    else if (oculta(g, f)) out.push({f, txt: `«${f.nombre}» es privada`, motivos});
  }
  return out;
}
function irA(fid) { const li = document.querySelector(`li[data-id="${CSS.escape(fid)}"]`); if (!li) return;
  li.scrollIntoView({block: 'center', behavior: 'smooth'}); li.classList.remove('destello'); void li.offsetWidth;
  li.classList.add('destello'); }
function pintarFaltan() {
  const caja = $('#faltan'); const fs = faltan();
  if (!fs.length && !D.otros.length) { caja.style.display = 'none'; return; }
  caja.style.display = '';
  caja.replaceChildren(el('b', {}, 'Para publicar en Cloudflare falta:'), el('ul', {},
    ...fs.map(x => el('li', {}, el('a', {onclick: () => irA(x.f.id)}, x.txt),
      ` — la usa ${x.motivos.join('; ')}. Haz clic en su estado y elige uno` + (x.txt.endsWith('privada') ? ', o quítale el 🔒.' : '.'))),
    ...D.otros.map(o => el('li', {}, o.texto + ' ', el('a', {href: '/editar/' + encodeURIComponent(o.version)}, 'Abrir la versión')))));
}
function candado(privado, alCambiar, que) {
  return el('button', {class: 'candado' + (privado ? ' on' : ''), onclick: alCambiar,
    title: privado ? `Privado: el cliente no ve ${que}. Clic para mostrarlo` : `Clic para que el cliente no vea ${que}`},
    privado ? '🔒' : '🔓');
}
async function ponerPrivG(g, valor) { if (await api('g/editar', {id: g.id, privado: valor})) { D.priv[g.id].privado = valor;
  g.privado = valor; pintar(); } }
function conteo(fs) { const c = {}; for (const e of D.estados) c[e.id] = 0;
  for (const f of fs) c[EST.has(f.estado) ? f.estado : ''] = (c[EST.has(f.estado) ? f.estado : ''] || 0) + 1; return c; }
function barra(c) { const t = Object.values(c).reduce((a, b) => a + b, 0) || 1;
  return el('div', {class: 'barra'}, ...D.estados.filter(e => c[e.id]).map(e =>
    el('span', {style: `width:${100 * c[e.id] / t}%;background:${e.fondo}`}))); }
function editable(texto, ph, guardar, unaLinea = true) {
  const n = el('span', {contenteditable: 'plaintext-only', 'data-ph': ph, spellcheck: 'false'}); n.textContent = texto;
  let antes = texto;
  n.addEventListener('focus', () => antes = n.textContent);
  n.addEventListener('keydown', e => { if (e.key === 'Enter' && unaLinea) { e.preventDefault(); n.blur(); }
    if (e.key === 'Escape') { n.textContent = antes; n.blur(); } });
  n.addEventListener('blur', async () => { const t = n.textContent.trim(); n.textContent = t;
    if (t === antes) return; if (!t && unaLinea) { n.textContent = antes; return; }
    if (!(await guardar(t))) n.textContent = antes; else antes = t; });
  return n;
}
function cerrarMenus() { document.querySelectorAll('.menu-est').forEach(m => m.remove()); }
document.addEventListener('mousedown', e => { if (!e.target.closest('.menu-est')) cerrarMenus(); });
function menuEstado(f, ancla) {
  cerrarMenus(); const r = ancla.getBoundingClientRect();
  const m = el('div', {class: 'menu-est', style: `top:${r.bottom + scrollY + 4}px;left:${Math.max(8, r.right + scrollX - 230)}px`},
    ...D.estados.map(e => el('div', {onclick: async () => { cerrarMenus(); const j = await api('f/editar', {id: f.id, estado: e.id});
        if (j) { f.estado = e.id; ultimoEstado = e.id; pintar(); } }},
      el('span', {class: 'dot', style: `background:${e.fondo}`}), e.cliente || 'Sin clasificar',
      el('span', {class: 'int'}, e.cliente === e.nombre ? '' : e.nombre))));
  document.body.append(m);
}
let arrastrada = null;
function fila(g, f) {
  const e = EST.get(f.estado) || EST.get('');
  const bloquea = D.bloquean[f.id] && (!f.estado || oculta(g, f));
  const li = el('li', {'data-id': f.id, 'data-texto': f.nombre.toLowerCase(),
    class: (oculta(g, f) ? 'priv' : '') + (bloquea ? ' bloquea' : ''),
    title: bloquea ? 'Impide publicar: la usa ' + D.bloquean[f.id].join('; ') : ''},
    el('span', {class: 'asa', title: 'Arrastrar a otro lugar'}, '⋮⋮'),
    el('span', {class: 'dot', style: `background:${e.fondo}`}),
    el('span', {}, editable(f.nombre, 'Nombre de la función', async t => { const j = await api('f/editar', {id: f.id, nombre: t});
      if (j) f.nombre = t; return !!j; })),
    el('span', {class: 'est', title: 'Cambiar el estado', onclick: ev => menuEstado(f, ev.currentTarget)},
      e.cliente || 'Sin clasificar'),
    candado(f.privado, async () => { if (await api('f/editar', {id: f.id, privado: !f.privado})) { f.privado = !f.privado; pintar(); } },
      'esta función'),
    el('button', {class: 'x', title: 'Quitar la función', onclick: async () => {
      if (!confirm(`¿Quitar «${f.nombre}» del diagrama?`)) return;
      if (await api('f/quitar', {id: f.id})) { g.funciones.splice(g.funciones.indexOf(f), 1); pintar(); } }}, '✕'));
  const asa = $('.asa', li);
  asa.addEventListener('mousedown', () => li.draggable = true);
  li.addEventListener('dragstart', ev => { arrastrada = {g, f}; li.classList.add('arr'); ev.dataTransfer.effectAllowed = 'move'; });
  li.addEventListener('dragend', () => { li.draggable = false; li.classList.remove('arr'); arrastrada = null; limpiarMarcas(); });
  li.addEventListener('dragover', ev => { if (!arrastrada) return; ev.preventDefault(); limpiarMarcas(); li.classList.add('antes'); });
  li.addEventListener('drop', ev => { ev.preventDefault(); ev.stopPropagation(); soltar(g, f); });
  return li;
}
function limpiarMarcas() { document.querySelectorAll('.antes,.al-final').forEach(x => x.classList.remove('antes', 'al-final')); }
async function soltar(g, antes) {
  limpiarMarcas(); if (!arrastrada) return; const {g: g0, f} = arrastrada; arrastrada = null;
  if (antes === f) return;
  const j = await api('f/mover', {id: f.id, grupo: g.id, antes: antes ? antes.id : null}); if (!j) return;
  g0.funciones.splice(g0.funciones.indexOf(f), 1);
  if (antes) g.funciones.splice(g.funciones.indexOf(antes), 0, f); else g.funciones.push(f);
  pintar();
}
function campoNuevo(ph, alCrear, alSalir) {
  const i = el('input', {class: 'campo-nuevo', placeholder: ph});
  let ocupado = false;
  i.addEventListener('keydown', async e => {
    if (e.key === 'Escape') return alSalir();
    if (e.key !== 'Enter') return; e.preventDefault();
    const t = i.value.trim(); if (!t || ocupado) return; ocupado = true; await alCrear(t); ocupado = false; });
  i.addEventListener('blur', () => setTimeout(() => { if (!i.value.trim() && document.activeElement !== i) alSalir(); }, 120));
  setTimeout(() => i.focus()); return i;
}
let abierto = null;   // {tipo: 'f'|'t'|'a', id} = el campo nuevo que queda abierto tras pintar
function tarjeta(a, g) {
  const ul = el('ul', {}, ...g.funciones.map(f => fila(g, f)));
  if (g.catalogo) ul.append(el('li', {}, el('span', {class: 'dot', style: 'background:var(--accent)'}),
    el('span', {}, `${g.piezas} pieza(s) en el catálogo`)));
  ul.addEventListener('dragover', ev => { if (!arrastrada) return; ev.preventDefault();
    if (ev.target === ul) { limpiarMarcas(); ul.classList.add('al-final'); } });
  ul.addEventListener('drop', ev => { ev.preventDefault(); soltar(g, null); });
  const pie = el('div');
  const abrirNueva = () => { abierto = {tipo: 'f', id: g.id};
    pie.replaceChildren(campoNuevo('Nombre de la función y Enter', async t => {
      const j = await api('f/nueva', {grupo: g.id, nombre: t, estado: ultimoEstado});
      if (j) { g.funciones.push(j.funcion); pintar(); } }, () => { abierto = null; pintar(); })); };
  pie.append(el('button', {class: 'nueva-f', onclick: abrirNueva}, '+ Agregar función'));
  const vacia = !g.funciones.length && !g.catalogo;
  const card = el('div', {class: 'grupo' + (privG(g.id) ? ' priv' : ''), 'data-g': g.id},
    el('span', {class: 'cab-g'}, candado(g.privado, () => ponerPrivG(g, !g.privado), 'esta tarjeta'),
    el('button', {class: 'quitar-g', title: 'Quitar la tarjeta', onclick: async () => {
      if (!confirm(vacia ? `¿Quitar la tarjeta «${g.nombre}»?`
        : `¿Quitar la tarjeta «${g.nombre}» y sus ${g.funciones.length} funciones?`)) return;
      if (await api('g/quitar', {id: g.id})) { a.grupos.splice(a.grupos.indexOf(g), 1); pintar(); } }}, '✕')),
    el('h3', {}, editable(g.nombre, 'Título de la tarjeta', async t => { const j = await api('g/editar', {id: g.id, nombre: t});
      if (j) g.nombre = t; return !!j; }), g.privado ? el('span', {class: 'tag-priv'}, 'Privado') : null),
    el('div', {class: 'det'}, editable(g.detalle || '', 'Subtítulo (opcional)', async t => {
      const j = await api('g/editar', {id: g.id, detalle: t}); if (j) g.detalle = t; return !!j; }, true)),
    ul, pie);
  if (abierto && abierto.tipo === 'f' && abierto.id === g.id) abrirNueva();
  return card;
}
function nuevaTarjeta(a) {
  const caja = el('div');
  const abrir = () => { abierto = {tipo: 't', id: a.id};
    caja.className = 'grupo'; caja.replaceChildren(campoNuevo('Título de la tarjeta y Enter', async t => {
      const j = await api('g/nuevo', {padre: a.id, nombre: t});
      if (j) { D.priv[j.grupo.id] = {padre: a.id, privado: false}; a.grupos.push(Object.assign(j.grupo, {funciones: []})); abierto = {tipo: 'f', id: j.grupo.id}; pintar(); } },
      () => { abierto = null; pintar(); })); };
  caja.append(el('button', {class: 'nueva-t', onclick: abrir}, '+ Nueva tarjeta'));
  caja.style.display = 'grid';
  if (abierto && abierto.tipo === 't' && abierto.id === a.id) abrir();
  return caja;
}
function area(a) {
  const fs = a.grupos.flatMap(g => g.funciones.filter(f => !oculta(g, f)));
  const s = el('section', {class: 'area' + (a.privado ? ' priv' : '')},
    a.grupos.length ? null : el('button', {class: 'quitar-a', onclick: async () => {
      if (await api('g/quitar', {id: a.id})) { D.areas.splice(D.areas.indexOf(a), 1); pintar(); } }}, 'Quitar área'),
    el('h2', {}, editable(a.nombre, 'Nombre del área', async t => { const j = await api('g/editar', {id: a.id, nombre: t});
      if (j) a.nombre = t; return !!j; }), ' ', candado(a.privado, () => ponerPrivG(a, !a.privado), 'esta área'),
      a.privado ? el('span', {class: 'tag-priv'}, 'Privado') : null),
    el('p', {class: 'sub'}, editable(a.detalle || '', 'Subtítulo (opcional)', async t => {
      const j = await api('g/editar', {id: a.id, detalle: t}); if (j) a.detalle = t; return !!j; }),
      ` · ${fs.length} funciones`),
    barra(conteo(fs)), el('div', {class: 'grid'}, ...a.grupos.map(g => tarjeta(a, g)), nuevaTarjeta(a)));
  return s;
}
function pintar() {
  const fs = todasF(); const c = conteo(fs);
  $('#total').textContent = fs.length;
  $('#barra').replaceChildren(barra(c));
  $('#leyenda').replaceChildren(...D.estados.filter(e => c[e.id]).map(e =>
    el('span', {class: 'pill', style: `background:${e.fondo};color:${e.texto}`}, `${e.cliente || 'Sin clasificar'} · ${c[e.id]}`)));
  const raiz = $('#areas'); raiz.replaceChildren(...D.areas.map(area));
  const pie = el('div');
  const abrir = () => { abierto = {tipo: 'a'}; pie.replaceChildren(el('section', {class: 'area'},
    campoNuevo('Nombre del área nueva y Enter (p. ej. «Plugin de válvulas»)', async t => {
      const j = await api('g/nuevo', {padre: '', nombre: t});
      if (j) { D.priv[j.grupo.id] = {padre: '', privado: false}; D.areas.push(Object.assign(j.grupo, {grupos: []})); abierto = {tipo: 't', id: j.grupo.id}; pintar(); } },
      () => { abierto = null; pintar(); }))); };
  pie.append(el('button', {class: 'nueva-t', style: 'width:100%;margin:18px 0', onclick: abrir}, '+ Nueva área'));
  raiz.append(pie);
  if (abierto && abierto.tipo === 'a') abrir();
  pintarFaltan();
  filtrar();
}
function filtrar() { const t = ($('#q').value || '').toLowerCase();
  document.querySelectorAll('li[data-id]').forEach(li => li.classList.toggle('oculto', !!t && !li.dataset.texto.includes(t))); }
$('#q').addEventListener('input', filtrar);
pintar();
{ const q = new URLSearchParams(location.search); if (q.get('e')) aviso(q.get('e'), true); else if (q.get('m')) aviso(q.get('m'));
  if (q.get('m') || q.get('e')) history.replaceState(null, '', location.pathname); }
"""


def _datos(pr):
    def grupo(g):
        return dict(id=g.id, nombre=g.nombre, detalle=g.detalle, catalogo=g.catalogo, privado=g.privado,
                    piezas=len(pr.fichas_de(g.catalogo)) if g.catalogo else 0,
                    funciones=[dict(id=f.id, nombre=f.nombre, estado=f.estado, privado=f.privado)
                               for f in pr.funciones_de(g.id)])

    def debajo(gid):
        out = []
        for h in pr.hijos(gid):
            out.append(h)
            out += debajo(h.id)
        return out
    areas = [dict(id=a.id, nombre=a.nombre, detalle=a.detalle, privado=a.privado,
                  grupos=([grupo(a)] if pr.funciones_de(a.id) else []) + [grupo(g) for g in debajo(a.id)])
             for a in pr.raices()]
    estados = [dict(id=e, nombre=D.ESTADOS[e][0] or "Sin clasificar", cliente=D.ESTADOS[e][1],
                    fondo=D.ESTADOS[e][2], texto=D.ESTADOS[e][3]) for e in D.ORDEN_ESTADOS]
    priv = {g.id: dict(padre=g.padre, privado=g.privado) for g in pr.grupos}
    bloquean, otros = _impide_publicar(pr)
    return dict(areas=areas, estados=estados, priv=priv, bloquean=bloquean, otros=otros)


def _impide_publicar(pr):
    """Lo que hoy impide publicar, para marcarlo en el editor: {función: [«versión X: cambio»]} de las funciones que
    usa una versión PUBLICADA y no tienen estado o son privadas, y los demás problemas de esas versiones."""
    funciones = {f.id: f for f in pr.funciones}
    bloquean, otros = {}, []
    for v in pr.versiones:
        if not v.publicada:
            continue
        for n in v.novedades:
            for fid in n.get("funciones", []):
                f = funciones.get(fid)
                if f is not None and (not f.estado or D.es_privada(pr, f)):
                    bloquean.setdefault(fid, []).append(f"la versión {v.numero} en «{n.get('titulo', '')}»")
        for txt in D.pendientes_version(pr, v):
            if "aún no tiene estado aprobado" not in txt and "es privada" not in txt:
                otros.append(dict(version=v.numero, texto=f"Versión {v.numero}: {txt}"))
    return bloquean, otros


BOTON_PUBLICAR = ("<form method='post' action='/publicar' style='display:inline' "
                  "onsubmit=\"return confirm('¿Publicar el sitio del cliente en Cloudflare?')\">"
                  "<input type='hidden' name='volver_a' value='/'>"
                  "<button class='btn p'>Publicar en Cloudflare</button></form>")


def pagina(pr):
    datos = json.dumps(_datos(pr), ensure_ascii=False).replace("</", "<\\/")
    cuerpo = (f'<style>{CSS}</style><div class="barra-ed">'
              '<a class="btn" href="/panel#versiones">Versiones</a>'
              '<a class="btn" href="/vista/index.html" target="_blank">Vista previa del cliente</a>'
              + BOTON_PUBLICAR + '<a class="btn" href="/panel">Más opciones</a>'
              '<span id="estado" class="estado">Escribe encima de cualquier texto. Todo se guarda solo. 🔒 = privado'
              '</span></div>'
              f"<h1>Funciones del proyecto</h1><p class='sub'>Vista general · versión {E(pr.version_actual)} · "
              '<span id="total"></span> funciones</p><div id="barra"></div><div id="leyenda" class="leyenda"></div>'
              '<input id="q" class="buscar" placeholder="Buscar una función…" aria-label="Buscar una función">'
              '<div id="faltan" class="faltan" style="display:none"></div><div id="areas"></div>'
              f'<script type="application/json" id="datos">{datos}</script><script>{JS}</script>')
    return sitio.pagina(pr, "Editar funciones", cuerpo, "", admin=True)


# ───────────────────────── operaciones (las llama el editor) ─────────────────────────

def mover_funcion(pr, f, grupo, antes=None):
    """Lleva la función a `grupo` (otra tarjeta o la misma), justo antes de `antes` o al final de esa tarjeta."""
    if not pr.grupo(grupo):
        raise ValueError(f"No existe la tarjeta «{grupo}»")
    pr.funciones.remove(f)
    f.grupo = grupo
    if antes:
        destino = next((i for i, x in enumerate(pr.funciones) if x.id == antes), None)
        if destino is None:
            raise ValueError(f"No existe la función «{antes}»")
    else:
        destino = max((i for i, x in enumerate(pr.funciones) if x.grupo == grupo), default=len(pr.funciones) - 1) + 1
    pr.funciones.insert(destino, f)


def quitar_tarjeta(pr, gid):
    """Quita una tarjeta con sus funciones (no si alguna está en una versión, ni si tiene tarjetas dentro)."""
    g = pr.grupo(gid)
    if g is None:
        raise ValueError(f"No existe la tarjeta «{gid}»")
    if pr.hijos(gid):
        raise ValueError(f"«{g.nombre}» tiene tarjetas dentro: quítalas primero")
    for f in pr.funciones_de(gid):
        usos = D.usos_de_funcion(pr, f.id)
        if usos:
            raise ValueError(f"«{f.nombre}» está en la versión {', '.join(usos)}: quítala de ahí primero")
    pr.funciones[:] = [f for f in pr.funciones if f.grupo != gid]
    D.quitar_grupo(pr, gid)


def _funcion(pr, fid):
    f = next((x for x in pr.funciones if x.id == fid), None)
    if f is None:
        raise ValueError(f"No existe la función «{fid}»")
    return f


def api(ruta, d):
    pr = D.leer()
    if ruta == "api/f/editar":
        f = _funcion(pr, d.get("id", ""))
        if "nombre" in d:
            D.editar_funcion(pr, f, nombre=d["nombre"])
        if "estado" in d:
            D.aprobar(pr, f, d["estado"])
        if "privado" in d:
            f.privado = bool(d["privado"])
        D.guardar_funciones(pr)
        return dict(ok=True)
    if ruta == "api/f/nueva":
        f = D.agregar_funcion(pr, d.get("grupo", ""), d.get("nombre", ""), d.get("estado", "probado"))
        D.guardar_funciones(pr)
        return dict(ok=True, funcion=dict(id=f.id, nombre=f.nombre, estado=f.estado, privado=False))
    if ruta == "api/f/quitar":
        D.quitar_funcion(pr, _funcion(pr, d.get("id", "")))
        D.guardar_funciones(pr)
        return dict(ok=True)
    if ruta == "api/f/mover":
        mover_funcion(pr, _funcion(pr, d.get("id", "")), d.get("grupo", ""), d.get("antes"))
        D.guardar_funciones(pr)
        return dict(ok=True)
    if ruta == "api/g/nuevo":
        g = D.agregar_grupo(pr, d.get("nombre", ""), d.get("padre", ""), d.get("detalle", ""))
        D.guardar_funciones(pr)
        return dict(ok=True, grupo=dict(id=g.id, nombre=g.nombre, detalle=g.detalle, catalogo="", piezas=0,
                                        privado=False))
    if ruta == "api/g/editar":
        g = pr.grupo(d.get("id", ""))
        if g is None:
            raise ValueError("No existe esa tarjeta")
        if "nombre" in d:
            if not d["nombre"].strip():
                raise ValueError("El título no puede quedar vacío")
            g.nombre = d["nombre"].strip()
        if "detalle" in d:
            g.detalle = d["detalle"].strip()
        if "privado" in d:
            g.privado = bool(d["privado"])
        D.guardar_funciones(pr)
        return dict(ok=True)
    if ruta == "api/g/quitar":
        quitar_tarjeta(pr, d.get("id", ""))
        D.guardar_funciones(pr)
        return dict(ok=True)
    raise ValueError(f"Acción desconocida: {ruta}")

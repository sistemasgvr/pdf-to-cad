"""Vista de ADMINISTRADOR: servidor local (solo 127.0.0.1, nunca se publica). Aquí se aprueba o rechaza lo que
propone cada persona, se cambia el estado oficial, se marcan versiones como publicadas, se ve el sitio del cliente
antes de subirlo, se genera el reporte y se publica en Cloudflare.

    python scripts/gestion admin        (abre el navegador en http://127.0.0.1:8765)
"""
from __future__ import annotations

import html
import json
import mimetypes
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse

import admin_funciones
import admin_version
import datos as D
import publicar
import reporte
import sitio

E = html.escape
PUERTO = 8765
_CERROJO = threading.Lock()

CSS_ADMIN = """
.aviso{background:var(--soft);border-radius:10px;padding:10px 14px;margin:14px 0}
.error{background:#fde8e8;color:#8a1c1c;border-radius:10px;padding:10px 14px;margin:14px 0;white-space:pre-wrap}
.acciones{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0}
.btn{display:inline-block;border:1px solid var(--line);background:var(--card);color:var(--text);border-radius:9px;
padding:7px 14px;font:inherit;font-weight:600;cursor:pointer;text-decoration:none}
.btn.p{background:var(--accent);border-color:var(--accent);color:#fff}.btn.r{color:#c0392b}
.rev{background:var(--card);border:1px solid var(--line);border-left:4px solid #f39237;border-radius:12px;
padding:12px 14px;margin:10px 0}.rev .det{color:var(--muted);font-size:13px}
.rev form{display:inline-flex;gap:6px;align-items:center;margin:8px 8px 0 0;flex-wrap:wrap}
.edit td{vertical-align:middle}.edit input[type=text]{width:100%;box-sizing:border-box}
.alta{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin:10px 0}
.alta form{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.alta label{font-size:13px;color:var(--muted)}
input[type=color]{width:42px;height:32px;border:1px solid var(--line);border-radius:8px;padding:2px;background:none}
select,input[type=text]{padding:6px 8px;border:1px solid var(--line);border-radius:8px;background:var(--card);
color:var(--text);font:inherit}.mini img{height:90px;border-radius:8px;border:1px solid var(--line);margin:6px 6px 0 0}
td form,.acciones form{display:inline-flex}
table{width:100%;border-collapse:collapse;background:var(--card)}td,th{padding:6px 8px;border-bottom:1px solid var(--line);
text-align:left;font-size:14px}th{color:var(--muted);font-weight:600}details{margin:8px 0}
summary{cursor:pointer;font-weight:700;padding:6px 0}pre{white-space:pre-wrap;background:var(--card);
border:1px solid var(--line);border-radius:10px;padding:10px;max-height:420px;overflow:auto}
"""


def _select(nombre, actual):
    ops = "".join(f'<option value="{e}" {"selected" if e == actual else ""}>{E(D.ESTADOS[e][0])}</option>'
                  for e in D.ORDEN_ESTADOS)
    return f'<select name="{nombre}">{ops}</select>'


def _form(accion, campos, contenido, auto=False, extra=""):
    ocultos = "".join(f'<input type="hidden" name="{k}" value="{E(str(v))}">' for k, v in campos.items())
    extra += ' onchange="this.submit()"' if auto else ""
    return f'<form method="post" action="/{accion}"{extra}>{ocultos}{contenido}</form>'


def _tarjeta_revision(tipo, it, grupo=""):
    caps = ""
    if tipo == "ficha" and it.capturas:
        caps = '<div class="mini">' + "".join(
            f'<img src="/cap/{quote(it.id)}/{quote(a)}" alt="">' for a in it.capturas) + "</div>"
    quien = f" · propone {E(it.propuesto_por)}" if it.propuesto_por else ""
    nota = f'<div>{E(it.propuesto_nota)}</div>' if it.propuesto_nota else ""
    desc = f'<div class="det">{E(it.descripcion)}</div>' if tipo == "ficha" and it.descripcion else ""
    return (f'<div class="rev"><b>{E(it.nombre)}</b> <span class="det">{E(grupo)}{quien}</span>{desc}<div>'
            f'{sitio.pill(it.estado, cliente=False)} → {sitio.pill(it.propuesto, cliente=False)}</div>{nota}{caps}'
            + _form("aprobar", dict(tipo=tipo, id=it.id), _select("estado", it.propuesto)
                    + '<button class="btn p">Aprobar</button>')
            + _form("rechazar", dict(tipo=tipo, id=it.id), '<input type="text" name="motivo" '
                    'placeholder="Motivo (opcional)"><button class="btn r">Rechazar</button>') + "</div>")


def pagina_principal(pr, mensaje="", error=""):
    partes = ['<div class="acciones"><a class="btn" href="/">← Funciones</a></div>'
              "<h1>Más opciones</h1><p class='sub'>Solo en esta PC. Versiones, propuestas por revisar, estados y "
              "piezas. Las funciones se editan en la página de entrada.</p>"]
    if mensaje:
        partes.append(f'<div class="aviso">{E(mensaje)}</div>')
    errores = D.validar(pr)
    if error or errores:
        partes.append(f'<div class="error">{E(error or "")}{E(chr(10).join(errores))}</div>')
    link = f' · <a href="{E(pr.sitio)}" target="_blank">{E(pr.sitio)}</a>' if pr.sitio else ""
    partes.append('<div class="acciones"><a class="btn p" href="/funciones">Editar funciones (vista del cliente)</a>'
                  '<a class="btn" href="/vista/index.html" target="_blank">Vista previa del '
                  'sitio del cliente</a>' + _form("publicar", {}, '<button class="btn p">Publicar en Cloudflare'
                                                  '</button>') + f"</div><p class='sub'>Link del cliente{link or ': aún no publicado'}</p>")
    # pendientes de revisión
    pend_f = [f for f in pr.funciones if f.por_revisar]
    pend_c = [fi for fi in pr.fichas if fi.por_revisar]
    partes.append(f"<h2>Por revisar ({len(pend_f) + len(pend_c)})</h2>")
    if not (pend_f or pend_c):
        partes.append("<p class='sub'>Nada pendiente.</p>")
    nombres = {g.id: g.nombre for g in pr.grupos}
    partes += [_tarjeta_revision("funcion", f, nombres.get(f.grupo, "")) for f in pend_f]
    partes += [_tarjeta_revision("ficha", fi, fi.area) for fi in pend_c]
    # versiones
    partes.append("<h2 id='versiones'>Versiones</h2><table><tr><th>Versión</th><th>Título</th><th>Novedades</th>"
                  "<th>Publicada</th><th></th></tr>")
    for v in pr.versiones:
        chk = _form("version", dict(numero=v.numero),
                    f'<select name="publicada"><option value="0" {"selected" if not v.publicada else ""}>No</option>'
                    f'<option value="1" {"selected" if v.publicada else ""}>Sí</option></select>', auto=True)
        partes.append(f"<tr><td>{E(v.numero)}</td><td>{E(v.titulo)}</td><td>{len(v.novedades)}</td><td>{chk}</td>"
                      f'<td><a class="btn p" href="/editar/{quote(v.numero)}">Editar</a> '
                      f'<a class="btn" href="/version/{quote(v.numero)}" target="_blank">Ver</a> '
                      + _form("reporte", dict(numero=v.numero), '<button class="btn">Reporte PDF</button>')
                      + "</td></tr>")
    partes.append("</table>")
    partes.append('<div class="alta">' + _form("nueva_version", {}, (
        '<input type="text" name="numero" placeholder="Número, p. ej. 2.2.0" required size="16">'
        '<input type="text" name="titulo" placeholder="Título de la entrega (opcional)" size="34">'
        '<button class="btn p">Nueva versión</button>')) + "</div>")
    for v in pr.versiones:
        faltan = D.pendientes_version(pr, v)
        if faltan:
            partes.append(f'<details class="aviso"><summary>Versión {E(v.numero)}: {len(faltan)} cambio(s) sin función '
                          f'aprobada (no se puede publicar)</summary><ul>'
                          + "".join(f"<li>{E(x)}</li>" for x in faltan) + "</ul></details>")
    partes.append(_seccion_estados(pr))
    # catálogo
    partes.append(f"<h2>Catálogo de piezas ({len(pr.fichas)})</h2>")
    if pr.fichas:
        partes.append(sitio.catalogo(pr, publico=False,
                                     ruta_img=lambda fi, a: f"/cap/{quote(fi.id)}/{quote(a)}").split("</p>", 1)[1])
    return sitio.pagina(pr, "Administrador", "<style>" + CSS_ADMIN + "</style>" + "".join(partes), "", admin=True)


def _seccion_estados(pr):
    propios = {e.get("id") for e in pr.estados}
    filas = []
    for e in D.ORDEN_ESTADOS:
        if not e:
            continue
        n_int, n_cli, fondo, texto = D.ESTADOS[e]
        base = e in D.ESTADOS_BASE
        boton = "" if e not in propios else _form(
            "quitar_estado", dict(id=e), f'<button class="btn r">{"Color original" if base else "Quitar"}</button>')
        filas.append("<tr><td>" + sitio.pill(e, cliente=False) + "</td><td>" + _form("estado_color", dict(id=e), (
            f'<input type="text" name="nombre" value="{E(n_int)}" size="16">'
            f'<input type="text" name="cliente" value="{E(n_cli)}" size="14" title="Lo que ve el cliente">'
            f'<input type="color" name="fondo" value="{E(fondo)}" title="Fondo">'
            f'<input type="color" name="texto" value="{E(texto)}" title="Texto">'
            '<button class="btn">Guardar</button>')) + f"</td><td>{boton}</td></tr>")
    alta = _form("nuevo_estado", {}, (
        '<input type="text" name="nombre" placeholder="Nombre interno" required size="16">'
        '<input type="text" name="cliente" placeholder="Lo que ve el cliente" size="16">'
        '<label>Fondo</label><input type="color" name="fondo" value="#7b61ff">'
        '<label>Texto</label><input type="color" name="texto" value="#ffffff">'
        '<button class="btn p">Agregar estado</button>'))
    return ("<h2>Estados y colores</h2><p class='sub'>Cada función toma el color de su estado (sitio, reporte y "
            "draw.io). Puedes cambiar el color de cualquiera o crear estados propios.</p>"
            "<table class='edit'><tr><th>Vista</th><th>Nombre · cliente · fondo · texto</th><th></th></tr>"
            + "".join(filas) + f"</table><div class='alta'>{alta}</div>")


def _buscar(pr, tipo, iid):
    items = pr.funciones if tipo == "funcion" else pr.fichas
    it = next((x for x in items if x.id == iid), None)
    if it is None:
        raise ValueError(f"No existe {tipo} «{iid}»")
    return it


def _guardar(pr, tipo, it):
    if tipo == "funcion":
        D.guardar_funciones(pr)
    else:
        D.guardar_ficha(it)


def accion(ruta_post, campos):
    """Aplica un POST. Devuelve (mensaje, error)."""
    g = lambda k: campos.get(k, [""])[0]          # noqa: E731
    with _CERROJO:
        pr = D.leer()
        if ruta_post in ("aprobar", "estado"):
            it = _buscar(pr, g("tipo"), g("id"))
            D.aprobar(pr, it, g("estado"))
            _guardar(pr, g("tipo"), it)
            return f"«{it.nombre}»: {D.ESTADOS[it.estado][0]}", ""
        if ruta_post == "nueva_funcion":
            f = D.agregar_funcion(pr, g("grupo"), g("nombre"), g("estado"), nota=g("nota"))
            D.guardar_funciones(pr)
            return f"Función agregada: «{f.nombre}»", ""
        if ruta_post == "nuevo_grupo":
            gr = D.agregar_grupo(pr, g("nombre"), g("padre"), g("detalle"))
            D.guardar_funciones(pr)
            return f"Grupo agregado: «{gr.nombre}» (agrégale funciones)", ""
        if ruta_post == "editar_funcion":
            f = _buscar(pr, "funcion", g("id"))
            D.editar_funcion(pr, f, nombre=campos["nombre"][0] if "nombre" in campos else None,
                             grupo=g("grupo") or None, nota=campos["nota"][0] if "nota" in campos else None)
            D.guardar_funciones(pr)
            return f"«{f.nombre}» guardada", ""
        if ruta_post == "quitar_funcion":
            f = _buscar(pr, "funcion", g("id"))
            D.quitar_funcion(pr, f)
            D.guardar_funciones(pr)
            return f"Quitada: «{f.nombre}»", ""
        if ruta_post == "quitar_grupo":
            D.quitar_grupo(pr, g("id"))
            D.guardar_funciones(pr)
            return "Grupo quitado", ""
        if ruta_post in ("nuevo_estado", "estado_color"):
            eid = D.poner_estado(pr, g("nombre"), g("fondo"), g("texto") or "#ffffff", g("cliente"),
                                 eid=g("id") or None)
            D.guardar_funciones(pr)
            return f"Estado «{D.ESTADOS[eid][0]}» guardado", ""
        if ruta_post == "quitar_estado":
            D.quitar_estado(pr, g("id"))
            D.guardar_funciones(pr)
            return "Estado actualizado", ""
        if ruta_post == "rechazar":
            it = _buscar(pr, g("tipo"), g("id"))
            D.rechazar(it, g("motivo"))
            _guardar(pr, g("tipo"), it)
            return f"«{it.nombre}»: propuesta rechazada", ""
        if ruta_post == "nueva_version":
            v = admin_version.nueva_version(pr, g("numero"), g("titulo"))
            return f"Versión {v.numero} creada", "", f"/editar/{quote(v.numero)}"
        if ruta_post == "version":
            v = next(x for x in pr.versiones if x.numero == g("numero"))
            faltan = D.pendientes_version(pr, v)
            if g("publicada") == "1" and faltan:
                return "", (f"La versión {v.numero} no se puede publicar: cada cambio debe ir asociado a una función "
                            "aprobada del diagrama.\n  " + "\n  ".join(faltan))
            v.publicada = g("publicada") == "1"
            D.guardar_version(v)
            m = f"Versión {v.numero}: {'publicada' if v.publicada else 'no publicada'} (falta subir el sitio)"
            return (m, "", f"/editar/{quote(v.numero)}") if g("volver") else (m, "")
        if ruta_post == "reporte":
            pdf, txt = reporte.generar(g("numero"), pr)
            os.startfile(os.path.dirname(pdf)) if hasattr(os, "startfile") else None
            return f"Reporte listo: {pdf} (y el texto para WhatsApp: {os.path.basename(txt)})", ""
        if ruta_post == "publicar":
            ok, salida = publicar.publicar(pr, al_texto=lambda *_: None)
            return ("Sitio publicado." if ok else ""), ("" if ok else "No se pudo publicar:\n" + salida[-3000:])
    return "", f"Acción desconocida: {ruta_post}"


class _Manejador(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _local(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost")

    def _enviar(self, codigo, cuerpo, tipo="text/html; charset=utf-8", extra=None):
        datos = cuerpo.encode("utf-8") if isinstance(cuerpo, str) else cuerpo
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(datos)

    def _archivo(self, base, rel):
        destino = os.path.realpath(os.path.join(base, *[p for p in rel.split("/") if p not in ("", "..")]))
        if not destino.startswith(os.path.realpath(base)) or not os.path.isfile(destino):
            return self._enviar(404, "No existe")
        with open(destino, "rb") as f:
            self._enviar(200, f.read(), mimetypes.guess_type(destino)[0] or "application/octet-stream")

    def do_GET(self):
        if not self._local():
            return self._enviar(403, "Solo local")
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            if u.path == "/":                      # entrada: el diagrama editable, igual al del cliente
                return self._enviar(200, admin_funciones.pagina(D.leer()))
            if u.path == "/panel":
                return self._enviar(200, pagina_principal(D.leer(), q.get("m", [""])[0], q.get("e", [""])[0]))
            if u.path.startswith("/vista/"):
                if u.path == "/vista/index.html":
                    publicar.construir(estricto=False)   # la vista previa se ve aunque falte aprobar algo
                return self._archivo(publicar.PUBLICO(), unquote(u.path[len("/vista/"):]))
            if u.path == "/funciones":
                return self._enviar(200, admin_funciones.pagina(D.leer()))
            if u.path.startswith("/editar/"):
                pr = D.leer()
                num = unquote(u.path[len("/editar/"):])
                v = next((x for x in pr.versiones if x.numero == num), None)
                if v is None:
                    return self._enviar(404, "No existe esa versión")
                return self._enviar(200, admin_version.pagina(pr, v))
            if u.path.startswith("/version/"):
                pr = D.leer()
                v = next(x for x in pr.versiones if x.numero == unquote(u.path[len("/version/"):]))
                return self._enviar(200, sitio.pagina_version(D.publico(pr), v))
            if u.path.startswith("/cap/"):
                return self._archivo(D.ruta("catalogo"), unquote(u.path[len("/cap/"):]))
        except Exception as e:                        # noqa: BLE001
            return self._enviar(500, f"<pre>{E(repr(e))}</pre>")
        self._enviar(404, "No existe")

    def do_POST(self):
        largo = int(self.headers.get("Content-Length") or 0)
        cuerpo = self.rfile.read(largo)              # leerlo siempre: si no, Windows corta la conexión
        origen = urlparse(self.headers.get("Origin") or "").hostname
        if not self._local() or origen not in ("127.0.0.1", "localhost"):
            return self._enviar(403, "Solo local")
        ruta_post = urlparse(self.path).path.strip("/")
        if ruta_post.startswith("api/"):               # editor de versiones: JSON de ida y vuelta
            try:
                with _CERROJO:
                    modulo = admin_funciones if ruta_post.startswith(("api/f/", "api/g/")) else admin_version
                    res = modulo.api(ruta_post, json.loads(cuerpo.decode("utf-8") or "{}"))
            except Exception as ex:                    # noqa: BLE001
                res = dict(ok=False, error=str(ex))
            return self._enviar(200, json.dumps(res, ensure_ascii=False), "application/json; charset=utf-8")
        campos = parse_qs(cuerpo.decode("utf-8"))
        destino = campos.get("volver_a", ["/panel"])[0]
        if not destino.startswith("/") or destino.startswith("//"):
            destino = "/panel"
        try:
            res = accion(ruta_post, campos)
            m, e = res[0], res[1]
            destino = res[2] if len(res) > 2 else destino
        except Exception as ex:                        # noqa: BLE001
            m, e = "", f"Error: {ex}"
        self._enviar(303, "", extra={"Location": f"{destino}?m={quote(m)}&e={quote(e)}"})


class _Servidor(ThreadingHTTPServer):
    """Puerto EXCLUSIVO (reporte 2026-11-18): con SO_REUSEADDR, en Windows un segundo administrador se abría en el
    MISMO puerto de uno viejo que seguía corriendo y el navegador seguía viendo el viejo, sin ningún aviso."""
    allow_reuse_address = False

    def server_bind(self):
        import socket
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def abrir_servidor(puerto=PUERTO, intentos=20):
    """El primer puerto libre desde `puerto` (si hay otro administrador abierto, este usa el siguiente)."""
    for p in range(puerto, puerto + intentos):
        try:
            return _Servidor(("127.0.0.1", p), _Manejador)
        except OSError:
            if p == puerto:
                print(f"El puerto {p} está ocupado (¿otro administrador abierto?): uso el siguiente libre.")
    raise SystemExit(f"No hay puertos libres entre {puerto} y {puerto + intentos - 1}")


def servir(puerto=PUERTO, abrir=True):
    srv = abrir_servidor(puerto)
    puerto = srv.server_address[1]
    url = f"http://127.0.0.1:{puerto}/"
    print(f"Administrador en {url}  (Ctrl+C para cerrar)")
    if abrir:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()

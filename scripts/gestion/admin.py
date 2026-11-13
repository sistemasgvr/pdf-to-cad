"""Vista de ADMINISTRADOR: servidor local (solo 127.0.0.1, nunca se publica). Aquí se aprueba o rechaza lo que
propone cada persona, se cambia el estado oficial, se marcan versiones como publicadas, se ve el sitio del cliente
antes de subirlo, se genera el reporte y se publica en Cloudflare.

    python scripts/gestion admin        (abre el navegador en http://127.0.0.1:8765)
"""
from __future__ import annotations

import html
import mimetypes
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse

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


def _form(accion, campos, contenido, auto=False):
    ocultos = "".join(f'<input type="hidden" name="{k}" value="{E(str(v))}">' for k, v in campos.items())
    extra = ' onchange="this.submit()"' if auto else ""
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
    partes = ["<h1>Administrador</h1><p class='sub'>Solo en esta PC. Lo que apruebas aquí es lo único que ve el "
              "cliente.</p>"]
    if mensaje:
        partes.append(f'<div class="aviso">{E(mensaje)}</div>')
    errores = D.validar(pr)
    if error or errores:
        partes.append(f'<div class="error">{E(error or "")}{E(chr(10).join(errores))}</div>')
    link = f' · <a href="{E(pr.sitio)}" target="_blank">{E(pr.sitio)}</a>' if pr.sitio else ""
    partes.append('<div class="acciones"><a class="btn" href="/vista/index.html" target="_blank">Vista previa del '
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
    partes.append("<h2>Versiones</h2><table><tr><th>Versión</th><th>Título</th><th>Novedades</th>"
                  "<th>Publicada</th><th></th></tr>")
    for v in pr.versiones:
        chk = _form("version", dict(numero=v.numero),
                    f'<select name="publicada"><option value="0" {"selected" if not v.publicada else ""}>No</option>'
                    f'<option value="1" {"selected" if v.publicada else ""}>Sí</option></select>', auto=True)
        partes.append(f"<tr><td>{E(v.numero)}</td><td>{E(v.titulo)}</td><td>{len(v.novedades)}</td><td>{chk}</td>"
                      f'<td><a class="btn" href="/version/{quote(v.numero)}" target="_blank">Ver</a> '
                      + _form("reporte", dict(numero=v.numero), '<button class="btn">Reporte PDF</button>')
                      + "</td></tr>")
    partes.append("</table>")
    for v in pr.versiones:
        faltan = D.pendientes_version(pr, v)
        if faltan:
            partes.append(f'<details class="aviso"><summary>Versión {E(v.numero)}: {len(faltan)} cambio(s) sin función '
                          f'aprobada (no se puede publicar)</summary><ul>'
                          + "".join(f"<li>{E(x)}</li>" for x in faltan) + "</ul></details>")
    # todas las funciones
    partes.append(f"<h2>Todas las funciones ({len(pr.funciones)})</h2>{sitio.barra(D.conteo(pr.funciones))}")
    for area in pr.raices():
        for g in sitio._grupos_con_algo(pr, area.id):
            fs = pr.funciones_de(g.id)
            if not fs:
                continue
            filas = "".join(
                f"<tr><td>{E(f.nombre)}</td><td>"
                + _form("estado", dict(tipo="funcion", id=f.id), _select("estado", f.estado), auto=True)
                + f"</td><td class='det'>{E(f.aprobado)}</td><td class='det'>{E(f.nota)}</td></tr>" for f in fs)
            c = D.conteo(fs)
            partes.append(f"<details><summary>{E(area.nombre)} › {E(g.nombre)} · {c['probado']}/{len(fs)} probadas"
                          f"</summary><table><tr><th>Función</th><th>Estado oficial</th><th>Aprobado</th>"
                          f"<th>Nota interna</th></tr>{filas}</table></details>")
    # catálogo
    partes.append(f"<h2>Catálogo de piezas ({len(pr.fichas)})</h2>")
    if pr.fichas:
        partes.append(sitio.catalogo(pr, publico=False,
                                     ruta_img=lambda fi, a: f"/cap/{quote(fi.id)}/{quote(a)}").split("</p>", 1)[1])
    return sitio.pagina(pr, "Administrador", "<style>" + CSS_ADMIN + "</style>" + "".join(partes), "", admin=True)


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
        if ruta_post == "rechazar":
            it = _buscar(pr, g("tipo"), g("id"))
            D.rechazar(it, g("motivo"))
            _guardar(pr, g("tipo"), it)
            return f"«{it.nombre}»: propuesta rechazada", ""
        if ruta_post == "version":
            v = next(x for x in pr.versiones if x.numero == g("numero"))
            faltan = D.pendientes_version(pr, v)
            if g("publicada") == "1" and faltan:
                return "", (f"La versión {v.numero} no se puede publicar: cada cambio debe ir asociado a una función "
                            "aprobada del diagrama.\n  " + "\n  ".join(faltan))
            v.publicada = g("publicada") == "1"
            D.guardar_version(v)
            return f"Versión {v.numero}: {'publicada' if v.publicada else 'no publicada'} (falta subir el sitio)", ""
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
            if u.path == "/":
                return self._enviar(200, pagina_principal(D.leer(), q.get("m", [""])[0], q.get("e", [""])[0]))
            if u.path.startswith("/vista/"):
                if u.path == "/vista/index.html":
                    publicar.construir()
                return self._archivo(publicar.PUBLICO(), unquote(u.path[len("/vista/"):]))
            if u.path.startswith("/version/"):
                pr = D.leer()
                v = next(x for x in pr.versiones if x.numero == unquote(u.path[len("/version/"):]))
                return self._enviar(200, sitio.pagina_version(pr, v))
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
        campos = parse_qs(cuerpo.decode("utf-8"))
        try:
            m, e = accion(urlparse(self.path).path.strip("/"), campos)
        except Exception as ex:                        # noqa: BLE001
            m, e = "", f"Error: {ex}"
        self._enviar(303, "", extra={"Location": f"/?m={quote(m)}&e={quote(e)}"})


def servir(puerto=PUERTO, abrir=True):
    srv = ThreadingHTTPServer(("127.0.0.1", puerto), _Manejador)
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

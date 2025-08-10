from dataclasses import dataclass
from typing import Callable, Dict, Tuple
from html import escape as html_escape
from app.responses import build_response
from pathlib import Path
from app.staticserve import serve_static, STATIC_ROOT
from app.templating import render_page

@dataclass
class Request:
    """Representa uma requisição já parseada para as views/handlers"""
    method: str # "GET", "POST", ...
    path: str #ex.: "/sobre" (sem query)
    query: dict # dict[strm list[str]] de parse_qs
    version: str #http/1.1
    headers: dict # headers em minusculo
    remote_addr: str # ip do cliente (string)
    body: bytes # corpo bruto
    form: dict # dict[str, list[str]] quandp form-ur lencoded; caso contrario {}

RouteKey = Tuple[str, str] # (METHOD, PATH)
_routes: Dict[RouteKey, Callable[[Request], bytes]] = {}

def add_route(method: str, path: str, handler: Callable[[Request], bytes]) -> None:
    method = method.upper()
    _routes[(method, path)] = handler

def _allowed_methods_for_path(path: str):
    return sorted({m for (m, p) in _routes.keys() if p == path})

def dispatch(req: Request) -> bytes:
    """Encontra o handler para (method, path). 404/405 conforme o caso."""
    # Estáticos por prefixo
    if req.path.startswith("/static/"):
        return serve_static(req)

    handler = _routes.get((req.method, req.path))
    if handler is not None:
        return handler(req)

    methods = _allowed_methods_for_path(req.path)
    if methods:
        return build_response(
            405,
            b"<h1>405 Method Not Allowed</h1>",
            {"Allow": ", ".join(methods)},
        )
    return render_404()

# ---------- Handlers (views) de exemplo ----------

def home(req: Request) -> bytes:
    nome = req.query.get("nome", ["mundo"])[0]
    return render_page("home.html", title="BrasaHTTP", nome=nome)


def sobre(req: Request) -> bytes:
    ua = req.headers.get("user-agent", "desconhecido")
    return render_page("sobre.html", title="Sobre • BrasaHTTP", ua=ua)

def saudacao(req: Request) -> bytes:
    nome = req.query.get("nome", ["mundo"])[0]
    return render_page("saudacao.html", title="Saudação • BrasaHTTP", nome=nome)

def init_routes() -> None:
    """Registra as rotas iniciais do projeto."""
    add_route("GET", "/", home)
    add_route("GET", "/sobre", sobre)
    add_route("GET", "/saudacao", saudacao)
    add_route("GET", "/eco", eco_get)
    add_route("POST", "/eco", eco_post)

def eco_get(req: Request) -> bytes:
    # Formulário simples (GET)
    html = """<h1>Echo (formulário)</h1>
<p>Envie dados por POST (application/x-www-form-urlencoded).</p>
<form method="POST" action="/eco">
  <label>Nome: <input type="text" name="nome"></label><br><br>
  <label>Mensagem:<br>
    <textarea name="mensagem" rows="4" cols="40"></textarea>
  </label><br><br>
  <button type="submit">Enviar</button>
</form>
<p><a href="/">voltar</a></p>
"""
    return render_page("home.html", title="Echo • BrasaHTTP", nome="mundo").replace(
        b"</main></body></html>",
        f"{html}".encode("utf-8") + b"</main></body></html>"
    )

def eco_post(req: Request) -> bytes:
    # Aceita somente application/x-www-form-urlencoded
    ctype = req.headers.get("content-type", "")
    if not ctype.lower().startswith("application/x-www-form-urlencoded"):
        return build_response(
            415,
            b"<!doctype html><meta charset='utf-8'><h1>415 Unsupported Media Type</h1>"
            b"<p>Use Content-Type: application/x-www-form-urlencoded</p>",
            extra_headers={"Accept": "application/x-www-form-urlencoded"},
        )

    nome = req.form.get("nome", ["(sem nome)"])[0]
    msg  = req.form.get("mensagem", ["(sem mensagem)"])[0]

    body = f"""<!doctype html>
<html lang="pt-BR"><meta charset="utf-8">
<title>Echo</title>
<link rel="stylesheet" href="/static/style.css">
<main class="container">
  <h1>Eco do POST</h1>
  <p><strong>Nome:</strong> {html_escape(nome)}</p>
  <p><strong>Mensagem:</strong> {html_escape(msg)}</p>
  <p><a href="/eco">voltar ao formulário</a> — <a href="/">home</a></p>
</main>
""".encode("utf-8")
    return build_response(200, body, content_type="text/html; charset=utf-8")

def render_404() -> bytes:
    """Tenta servir o app/static/404.html; se não existir, usa fallback."""
    custom = STATIC_ROOT / "404.html"
    if custom.exists() and custom.is_file():
        body = custom.read_bytes()
        return build_response(404, body, content_type="text/html; charset=utf-8")
    # fallback simples
    return build_response(404, b"<!doctype html><meta charset='utf-8'><h1>404 Not Found</h1>")
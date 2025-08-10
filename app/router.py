from dataclasses import dataclass
from typing import Callable, Dict, Tuple
from html import escape as html_escape
from app.responses import build_response, redirect
from pathlib import Path
from app.staticserve import serve_static, STATIC_ROOT
from app.templating import render_page
from app.sessions import verify_token, build_session_cookie, build_clear_session_cookie, COOKIE_NAME
from app.db import insert_eco, fetch_recent

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
    cookies: dict

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
    add_route("GET", "/favicon.ico", favicon)
    add_route("GET",  "/login", login_get)
    add_route("POST", "/login", login_post)
    add_route("GET",  "/area", area)
    add_route("GET",  "/logout", logout)   
    add_route("GET", "/eco/list", eco_list)

def favicon(req: Request) -> bytes:
    # 204 sem corpo, só para silenciar o pedido do browser
    return build_response(204, b"", content_type="image/x-icon")

def eco_get(req: Request) -> bytes:
    return render_page("eco.html", title="Echo • BrasaHTTP")

def eco_post(req: Request) -> bytes:
    ctype = req.headers.get("content-type", "")
    if not ctype.lower().startswith("application/x-www-form-urlencoded"):
        return build_response(
            415,
            (b"<!doctype html><meta charset='utf-8'>"
             b"<h1>415 Unsupported Media Type</h1>"
             b"<p>Use Content-Type: application/x-www-form-urlencoded</p>"),
            extra_headers={"Accept": "application/x-www-form-urlencoded"},
        )

    nome = req.form.get("nome", ["(sem nome)"])[0]
    msg  = req.form.get("mensagem", ["(sem mensagem)"])[0]

    ua = req.headers.get("user-agent", "")
    try:
        insert_eco(req.remote_addr, nome, msg, ua)
    except Exception:
        # falha no DB -> 500 simples (poderia logar)
        return build_response(500, b"<!doctype html><meta charset='utf-8'><h1>500</h1><p>DB error</p>")

    return render_page("eco_result.html", title="Echo • BrasaHTTP", nome=nome, mensagem=msg)

def eco_list(req: Request) -> bytes:
    # pega limite via query (?n=50), default 20
    n = 20
    try:
        if "n" in req.query:
            n = int(req.query["n"][0])
    except Exception:
        n = 20

    rows = fetch_recent(n)

    # monte as linhas (autoescape acontece no motor se passarmos como texto)
    linhas = []
    for r in rows:
        # cada campo será escapado quando injetado no template base (usamos Safe só quando for HTML já pronto; aqui não)
        linha = (
            f"<tr>"
            f"<td>{r['id']}</td>"
            f"<td>{r['created_at']}</td>"
            f"<td>{r['ip']}</td>"
            f"<td>{r['nome']}</td>"
            f"<td>{r['mensagem']}</td>"
            f"<td>{r['ua']}</td>"
            f"</tr>"
        )
        linhas.append(linha)

    # junte e injete como string “segura”?
    # preferimos deixar o motor escapar por padrão; porém aqui queremos injetar HTML de linhas.
    # então importamos Safe e marcamos as TRs.
    from app.templating import Safe, render_page
    html_linhas = Safe("\n".join(linhas))

    return render_page("eco_list.html", title="Mensagens • BrasaHTTP", qtd=len(rows), linhas=html_linhas)

def render_404() -> bytes:
    """Tenta servir o app/static/404.html; se não existir, usa fallback."""
    custom = STATIC_ROOT / "404.html"
    if custom.exists() and custom.is_file():
        body = custom.read_bytes()
        return build_response(404, body, content_type="text/html; charset=utf-8")
    # fallback simples
    return build_response(404, b"<!doctype html><meta charset='utf-8'><h1>404 Not Found</h1>")

def login_get(req: Request) -> bytes:
    # Se já tiver sessão válida, redireciona direto
    tok = req.cookies.get(COOKIE_NAME)
    if tok and verify_token(tok):
        return redirect("/area")
    return render_page("login.html", title="Login • BrasaHTTP")

def login_post(req: Request) -> bytes:
    nome = req.form.get("nome", [""])[0].strip()
    if not nome:
        return build_response(
            400,
            "<!doctype html><meta charset='utf-8'><h1>400</h1><p>Nome obrigatório</p>".encode("utf-8")
        )
    cookie = build_session_cookie({"nome": nome}, max_age=7200, secure=False)
    return redirect("/area", extra_headers={"Set-Cookie": cookie})

def area(req: Request) -> bytes:
    tok = req.cookies.get(COOKIE_NAME)
    data = verify_token(tok) if tok else None
    if not data:
        return redirect("/login")
    nome = data.get("nome", "visitante")
    return render_page("area.html", title="Área • BrasaHTTP", nome=nome)

def logout(req: Request) -> bytes:
    clear = build_clear_session_cookie()
    return redirect("/", extra_headers={"Set-Cookie": clear})
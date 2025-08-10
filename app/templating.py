from pathlib import Path
from string import Template
from html import escape as html_escape
from typing import Any, Mapping
import gzip
from app.responses import build_response

TEMPLATES_ROOT = Path(__file__).resolve().parent / "templates"

class Safe(str):
    """Marca conteudo como 'já seguro' (não escapar de novo)"""
    pass

def _escape_value(v: Any) -> str:
    if isinstance(v, Safe):
        return str(v)
    #padrão: escapar para evitar XSS
    return html_escape(str(v), quote=True)

def _prepare_context(ctx: Mapping[str, Any]) -> dict[str, str]:
    # Converte para strings já escapadas (ou mantidas se Safe)
    return {k: _escape_value(v) for k, v in ctx.items()}

def load_template(name: str) -> Template:
    path = TEMPLATES_ROOT / name
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Template não encontrado: {name}")
    text = path.read_text(encoding="utf-8")
    return Template(text)

def render_template_to_str(name: str, **context: Any) -> str:
    tpl = load_template(name)
    ctx = _prepare_context(context)
    # safe_substitute: se faltar variável, não explode (mais didático no início)
    return tpl.safe_substitute(ctx)

def render_layout(content_template: str, **context: Any) -> str:
    """
    Renderiza 'content_template' com autoescape, depois injeta
    o HTML resultante como ${content} em base.html (marcado como Safe).
    Espera-se que 'title' esteja no context.
    """
    inner_html = render_template_to_str(content_template, **context)
    return render_template_to_str("base.html", content=Safe(inner_html), **context)

def render_page(content_template: str, status: int = 200, accept_encoding: str | None = None, **context: Any) -> bytes:
    html = render_layout(content_template, **context)
    body = html.encode("utf-8")
    # Negociação simples de gzip
    wants_gzip = False
    if accept_encoding and "gzip" in accept_encoding.lower():
        # limiar p/ não gastar CPU com corpos muito pequenos
        wants_gzip = len(body) >= 512
    if wants_gzip and status not in (204, 304):
        gz = gzip.compress(body, mtime=0)  # mtime=0 -> output estável (bom p/ testes)
        return build_response(
            status,
            gz,
            extra_headers={
                "Content-Encoding": "gzip",
                "Vary": "Accept-Encoding",
            },
            content_type="text/html; charset=utf-8",
        )
    return build_response(status, body, content_type="text/html; charset=utf-8")
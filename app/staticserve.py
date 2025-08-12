from pathlib import Path
from urllib.parse import unquote
import mimetypes
from email.utils import formatdate, parsedate_to_datetime
from app.responses import build_response
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.router import Request
import gzip

# Raiz dos estáticos: app/static
STATIC_ROOT = Path(__file__).resolve().parent / "static"

def _safe_path(url_path: str) -> Path | None:
    """
    Converte a parte da URL após /static/ em um caminho seguro dentro de STATIC_ROOT.
    Retorna Path absoluto seguro ou None se inválido/fora da raiz.
    """
    # remove o prefixo '/static/' (já garantido pelo caller) e decodifica %xx
    rel = url_path[len("/static/"):]
    rel = unquote(rel)

    # Não permitir caminhos absolutos ou voltando diretórios
    # resolve() normaliza .. e .
    candidate = (STATIC_ROOT / rel).resolve()

    try:
        # Garante que candidate está DENTRO de STATIC_ROOT
        candidate.relative_to(STATIC_ROOT)
    except ValueError:
        return None
    return candidate

def _guess_content_type(path: Path) -> str:
    ctype, enc = mimetypes.guess_type(path.name)
    if not ctype:
        ctype = "application/octet-stream"
    # charset só para tipos textuais
    if ctype.startswith("text/"):
        ctype += "; charset=utf-8"
    return ctype

def _http_date_from_timestamp(ts: float) -> str:
    return formatdate(ts, usegmt=True)

def serve_static(req: 'Request') -> bytes:
    """
    Atende URLs /static/... com GET e HEAD.
    Segurança: path traversal bloqueado. Sem listagem de diretório.
    Cache simples: Last-Modified / If-Modified-Since.
    Suporta gzip quando o cliente envia Accept-Encoding: gzip.
    """
    if req.method not in ("GET", "HEAD"):
        return build_response(405, b"<h1>405 Method Not Allowed</h1>", {"Allow": "GET, HEAD"})

    # Segurança de caminho
    target = _safe_path(req.path)
    if target is None:
        return build_response(403, b"<h1>403 Forbidden</h1>")

    # Não listamos diretórios
    if not target.exists() or not target.is_file():
        return build_response(404, b"<h1>404 Not Found</h1>")

    # Metadados do arquivo
    st = target.stat()
    last_mod = _http_date_from_timestamp(st.st_mtime)
    size = st.st_size
    ctype = _guess_content_type(target)

    # Cache condicional (If-Modified-Since)
    ims = req.headers.get("if-modified-since")
    if ims:
        try:
            ims_dt = parsedate_to_datetime(ims)
            if int(st.st_mtime) <= int(ims_dt.timestamp()):
                # 304 sem corpo
                return build_response(
                    304,
                    b"",
                    extra_headers={
                        "Last-Modified": last_mod,
                        "Cache-Control": "public, max-age=3600",
                        "X-Content-Type-Options": "nosniff",
                        "Vary": "Accept-Encoding",
                    },
                )
        except Exception:
            # header malformado -> ignora e envia normalmente
            pass

    # Negociação de gzip
    ae = (req.headers.get("accept-encoding") or "").lower()
    can_gzip = "gzip" in ae
    compressible = ctype.startswith("text/") or ctype in {
        "application/javascript",
        "application/json",
        "application/xml",
        "image/svg+xml",
    }

    if req.method == "HEAD":
        if can_gzip and compressible:
            # precisamos do tamanho comprimido, então comprimimos mas não enviamos corpo
            src = target.read_bytes()
            gz = gzip.compress(src, mtime=0)
            return build_response(
                200,
                b"",
                extra_headers={
                    "Content-Length": str(len(gz)),
                    "Last-Modified": last_mod,
                    "Cache-Control": "public, max-age=3600",
                    "X-Content-Type-Options": "nosniff",
                    "Content-Encoding": "gzip",
                    "Vary": "Accept-Encoding",
                },
                content_type=ctype,
            )
        else:
            return build_response(
                200,
                b"",
                extra_headers={
                    "Content-Length": str(size),
                    "Last-Modified": last_mod,
                    "Cache-Control": "public, max-age=3600",
                    "X-Content-Type-Options": "nosniff",
                },
                content_type=ctype,
            )

    # GET
    data = target.read_bytes()
    if can_gzip and compressible:
        gz = gzip.compress(data, mtime=0)
        return build_response(
            200,
            gz,
            extra_headers={
                "Last-Modified": last_mod,
                "Cache-Control": "public, max-age=3600",
                "X-Content-Type-Options": "nosniff",
                "Content-Encoding": "gzip",
                "Vary": "Accept-Encoding",
            },
            content_type=ctype,
        )

    # GET sem gzip
    return build_response(
        200,
        data,
        extra_headers={
            "Last-Modified": last_mod,
            "Cache-Control": "public, max-age=3600",
            "X-Content-Type-Options": "nosniff",
        },
        content_type=ctype,
    )
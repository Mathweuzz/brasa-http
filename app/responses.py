from email.utils import formatdate

# Mapa de códigos HTTP -> razão (texto curto)
STATUS_REASONS = {
    200: "OK",
    204: "No content",
    302: "Found",
    304: "Not Modified",
    400: "Bad Request",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    415: "Unsupported Media Type",
}

def http_date() -> str:
    """Data no padrão HTTP (GMT), ex.: Sun, 10 Aug 2025 17:12:00 GMT"""
    return formatdate(usegmt=True)

def build_response(
    status: int,
    body: bytes,
    extra_headers: dict | None = None,
    content_type: str = "text/html; charset=utf-8",
) -> bytes:
    """Monta uma resposta HTTP/1.1 completa em bytes."""
    reason = STATUS_REASONS.get(status, "OK")
    headers = {
        "Date": http_date(),
        "Server": "BrasaHTTP/0.4",
        "Content-Type": content_type,
        "Content-Length": str(len(body)),
        "Connection": "close",
    }
    if extra_headers:
        headers.update(extra_headers)

    status_line = f"HTTP/1.1 {status} {reason}\r\n"
    headers_blob = "".join(f"{k}: {v}\r\n" for k, v in headers.items())
    # Headers: ISO-8859-1 (regra do HTTP/1.1). Corpo: livre (usaremos UTF-8).
    return (status_line + headers_blob + "\r\n").encode("iso-8859-1") + body

def redirect(location: str, status: int = 302, extra_headers: dict | None = None) -> bytes:
    hdrs = {"Location": location}
    if extra_headers:
        hdrs.update(extra_headers)
    #corpo vazio é ok em 302
    return build_response(status, b"", extra_headers=hdrs, content_type="text/plain; charset=utf-8")
import socket # comunicação tcp 
from urllib.parse import urlsplit, parse_qs
from app.responses import build_response
from app.router import Request, dispatch, init_routes
import traceback
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from app.db import init_db
from app.config import load_settings
from app.logging_setup import setup_logging
import ssl

HOST = '0.0.0.0' # escuta em todas as interfaces locais
PORT = 8080 # porta do nosso servidor
BACKLOG = 50 # fila de conexões pendentes
BUF_SIZE = 4096 # leitura de bloco de 4 kib
MAX_HEADER = 16 * 1024 # limite de 16kib para cabeçalhos (defesa básica)
MAX_BODY = 1 * 1024 * 1024 # 1MiB: limita para corpo
MAX_WORKERS = min(32, (os.cpu_count() or 2) * 5)

def read_request(conn: socket.socket):
    """
    Lê headers até \\r\\n\\r\\n, parseia Content-Length e lê o corpo (se houver).
    Retorna (method, target, version, headers, body_bytes).
    """
    conn.settimeout(5.0)
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = conn.recv(BUF_SIZE)
        if not chunk:
            break
        data += chunk
        if len(data) > MAX_HEADER:
            raise ValueError("request headers too large")

    if b"\r\n\r\n" not in data:
        raise ValueError("incomplete headers")

    head, rest = data.split(b"\r\n\r\n", 1)

    # Parse da linha e headers (igual ao seu parse_request, só que com 'head')
    text = head.decode("iso-8859-1", errors="replace")
    lines = text.split("\r\n")
    if not lines:
        raise ValueError("empty request")

    try:
        method, target, version = lines[0].split(" ", 2)
    except ValueError:
        raise ValueError("malformed request line")

    headers = {}
    for line in lines[1:]:
        if not line:
            continue
        if ":" not in line:
            raise ValueError("malformed header")
        name, value = line.split(":", 1)
        headers[name.strip().lower()] = value.strip()

    # Corpo conforme Content-Length
    clen = int(headers.get("content-length", "0") or "0")
    if clen < 0 or clen > MAX_BODY:
        raise ValueError("invalid content-length")

    # rest = bytes depois de \r\n\r\n
    body = b""
    if clen == 0:
        # ignore qualquer byte extra (pode ser outra req iniciando)
        body = b""
    else:
        body = rest
        if len(body) < clen:
            to_read = clen - len(body)
            while to_read > 0:
                chunk = conn.recv(min(BUF_SIZE, to_read))
                if not chunk:
                    raise ValueError("incomplete body")
                body += chunk
                to_read -= len(chunk)
        else:
            # veio além do necessário (pode ser início de outra req); ficamos só com o corpo
            body = body[:clen]

    return method, target, version, headers, body

def to_request(method: str, target: str, version: str, headers: dict, body: bytes, remote_addr: str, is_secure: bool) -> Request:
    parts = urlsplit(target)
    path = parts.path or "/"
    query = parse_qs(parts.query, keep_blank_values=True)

    # Parse de form-urlencoded se aplicável
    form = {}
    if method.upper() in ("POST", "PUT", "PATCH"):
        mt, params = parse_content_type(headers.get("content-type", ""))
        if mt == "application/x-www-form-urlencoded":
            charset = params.get("charset", "utf-8") or "utf-8"
            try:
                text = body.decode(charset, errors="strict")
                form = parse_qs(text, keep_blank_values=True)
            except UnicodeDecodeError:
                # charset inválido -> mantém form vazio (handler pode reagir com 415)
                form = {}
        
    cookies = parse_cookies(headers.get("cookie", ""))

    return Request(
        method=method.upper(),
        path=path,
        query=query,
        version=version,
        headers=headers,
        remote_addr=remote_addr,
        body=body,
        form=form,
        cookies=cookies,
        is_secure=is_secure,
    )

def parse_content_type(value: str) -> tuple[str, dict]:
    media = value or ""
    parts = [p.strip() for p in media.split(";")]
    mt = parts[0].lower() if parts else ""
    params = {}
    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            params[k.strip().lower()] = v.strip().strip('"')
    return mt, params

def parse_cookies(header_value: str) -> dict:
    cookies = {}
    if not header_value:
        return cookies
    for pair in header_value.split(";"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            cookies[k.strip()] = v.strip()
    return cookies

def _parse_status_and_cl(resp: bytes) -> tuple[int, int]:
    try:
        head_end = resp.find(b"\r\n\r\n")
        head = resp[:head_end if head_end != -1 else len(resp)]
        first_line_end = head.find(b"\r\n")
        status_line = head[:first_line_end if first_line_end != -1 else len(head)].decode("iso-8859-1", "replace")
        parts = status_line.split(" ", 2)
        status = int(parts[1]) if len(parts) >= 2 else 200
        cl = None
        for line in head.split(b"\r\n")[1:]:
            if line.lower().startswith(b"content-length:"):
                try:
                    cl = int(line.split(b":", 1)[1].strip())
                    break
                except Exception:
                    pass
        if cl is None and head_end != -1:
            cl = len(resp) - (head_end + 4)  # fallback
        return status, int(cl or 0)
    except Exception:
        return 200, 0



APP_LOG = None
ACC_LOG = None

def serve_connection(conn: socket.socket, addr: tuple[str, int], is_secure: bool) -> None:
    global APP_LOG, ACC_LOG
    try:
        method, target, version, headers, body = read_request(conn)
        req = to_request(method, target, version, headers, body, addr[0], is_secure)
        resp = dispatch(req)
    except (TimeoutError, socket.timeout):
        # cliente conectou mas não enviou request completo a tempo
        if APP_LOG: APP_LOG.info("408 Request Timeout de %s", addr[0])
        resp = build_response(408, b"<!doctype html><meta charset='utf-8'><h1>408 Request Timeout</h1>")        
    except ValueError as e:
        if APP_LOG: APP_LOG.info("400 Bad Request de %s: %s", addr[0], e)
        resp = build_response(400, f"<h1>400 Bad Request</h1><p>{e}</p>".encode("utf-8"))
    except Exception as e:
        if APP_LOG: APP_LOG.exception("Erro inesperado atendendo %s", addr[0])
        resp = build_response(400, b"<h1>400 Bad Request</h1>")
    try:
        conn.sendall(resp)
    except Exception:
        pass
    finally:
        try:
            conn.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        conn.close()
        # Access log (só depois de enviar)
        try:
            status, clen = _parse_status_and_cl(resp)
            ua = (req.headers.get("user-agent") if 'req' in locals() else "-") or "-"
            if ACC_LOG:
                # Formato: IP "METHOD PATH VERSION" status bytes UA
                ACC_LOG.info('%s "%s %s %s" %d %d "%s"',
                             addr[0],
                             req.method if 'req' in locals() else "-",
                             req.path if 'req' in locals() else "-",
                             req.version if 'req' in locals() else "-",
                             status, clen, ua)
        except Exception:
            pass

def serve_forever():
    from app.db import init_db
    cfg = load_settings()
    app_log, acc_log = setup_logging(cfg.logging)
    global APP_LOG, ACC_LOG
    APP_LOG, ACC_LOG = app_log, acc_log

    init_db()
    init_routes()

    use_tls = cfg.tls.enabled
    host = cfg.server.host
    port = (cfg.tls.port if use_tls else cfg.server.port)
    backlog = cfg.server.backlog

    tls_ctx = None
    if use_tls:
        tls_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls_ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        tls_ctx.load_cert_chain(certfile=cfg.tls.cert_file, keyfile=cfg.tls.key_file)
        # ciphers e opções adicionais poderiam ser ajustados aqui

    if APP_LOG:
        APP_LOG.info("Iniciando BrasaHTTP em %s://%s:%d (workers=%d)",
                     "https" if use_tls else "http", host, port, MAX_WORKERS)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((host, port))
        srv.listen(backlog)
        print(f"BrasaHTTP escutando em {'https' if use_tls else 'http'}://{host}:{port} (CTRL+C para sair)")
        if APP_LOG: APP_LOG.info("Servidor iniciado e escutando")

        with ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="brasa") as pool:
            try:
                while True:
                    conn, addr = srv.accept()
                    if use_tls:
                        try:
                            conn = tls_ctx.wrap_socket(conn, server_side=True)
                        except ssl.SSLError as e:
                            if APP_LOG: APP_LOG.info("Falha no handshake TLS de %s: %s", addr[0], e)
                            try: conn.close()
                            except Exception: pass
                            continue
                    pool.submit(serve_connection, conn, addr, use_tls)
            except KeyboardInterrupt:
                print("\nEncerrando BrasaHTTP...")
                if APP_LOG: APP_LOG.info("Encerrando por KeyboardInterrupt")


if __name__ == "__main__":
    serve_forever()

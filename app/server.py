import socket # comunicação tcp 
from urllib.parse import urlsplit, parse_qs
from app.responses import build_response
from app.router import Request, dispatch, init_routes
import traceback
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from app.db import init_db

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

def to_request(method: str, target: str, version: str, headers: dict, body: bytes, remote_addr: str) -> Request:
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
    )

def serve_forever():
    init_db()
    init_routes()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((HOST, PORT))
        srv.listen(BACKLOG)
        print(f"BrasaHTTP escutando em http://{HOST}:{PORT} (CTRL+C para sair)")

        # Pool de threads para atender conexões
        with ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="brasa") as pool:
            try:
                while True:
                    conn, addr = srv.accept()   # NÃO use 'with conn' aqui
                    pool.submit(serve_connection, conn, addr)
            except KeyboardInterrupt:
                print("\nEncerrando BrasaHTTP...")
                # saindo do 'with' da pool -> espera workers terminarem

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


def serve_connection(conn: socket.socket, addr: tuple[str, int]) -> None:
    """Atende UMA conexão: lê requisição, despacha, responde e fecha."""
    try:
        method, target, version, headers, body = read_request(conn)
        req = to_request(method, target, version, headers, body, addr[0])
        tname = threading.current_thread().name
        print(f"[{tname}] {addr[0]} {req.method} {req.path} q={req.query} body={len(req.body)}")
        resp = dispatch(req)
    except ValueError as e:
        resp = build_response(400, f"<h1>400 Bad Request</h1><p>{e}</p>".encode("utf-8"))
    except Exception:
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

if __name__ == "__main__":
    serve_forever()

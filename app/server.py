import socket # comunicação tcp 
from urllib.parse import urlsplit, parse_qs
from app.responses import build_response
from app.router import Request, dispatch, init_routes

HOST = '0.0.0.0' # escuta em todas as interfaces locais
PORT = 8080 # porta do nosso servidor
BACKLOG = 50 # fila de conexões pendentes
BUF_SIZE = 4096 # leitura de bloco de 4 kib
MAX_HEADER = 16 * 1024 # limite de 16kib para cabeçalhos (defesa básica)


def read_http_request(conn: socket.socket) -> bytes:
    conn.settimeout(5.0) # não ficar esperando para sempre
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = conn.recv(BUF_SIZE)
        if not chunk:
            break
        data += chunk
        if len(data) > MAX_HEADER:
            raise ValueError("request headers too large")
    return data

def parse_request(raw: bytes):
    # Headers HTTP: ISO-8859-1
    text = raw.decode("iso-8859-1", errors="replace")

    head = text.split("\r\n\r\n", 1)[0]
    lines = head.split("\r\n")
    if not lines:
        raise ValueError("empty request")

    request_line = lines[0]
    try:
        method, target, version = request_line.split(" ", 2)  # <= maxsplit=2
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

    return method, target, version, headers

def to_request(method: str, target:str, version: str, headers: dict, remote_addr: str) -> Request:
    """Converte method/target/headers em um objeto Request pronto para o router."""
    parts = urlsplit(target)
    path = parts.path or "/"
    query = parse_qs(parts.query, keep_blank_values=True) # dict[str, list[str]]
    return Request(
        method=method.upper(),
        path=path,
        query=query,
        version=version,
        headers=headers,
        remote_addr=remote_addr
    )

def serve_forever():
    #inicializa as rotas registradas no router
    init_routes()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((HOST, PORT))
        srv.listen(BACKLOG)
        print(f"BrasaHTTP escutando em http://{HOST}:{PORT} (CTRL+C para sair)")

        try:
            while True:
                conn, addr = srv.accept()
                with conn:
                    try:
                        raw = read_http_request(conn)
                        if not raw:
                            continue # conxão fechada sem dados
                        method, target, version, headers = parse_request(raw)
                        req = to_request(method, target, version, headers, addr[0])
                        print(f"{addr[0]} {req.method} {req.path} {req.query}") # log
                        resp = dispatch(req)
                    except ValueError as e:
                        resp = build_response(400, f"<h1>400 Bad Request</h1><p>{e}</p>".encode("utf-8"))
                    except Exception:
                        # em produção, logue a exceção; aqui, apenas responde 400
                        resp = build_response(400, b"<h1>400 Bad Request</h1>")
                    conn.sendall(resp)
        except KeyboardInterrupt:
            print("\nEncerrando BrasaHTTP...")

if __name__ == "__main__":
    serve_forever()

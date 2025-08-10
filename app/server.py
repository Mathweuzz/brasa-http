import socket # comunicação tcp 
from email.utils import formatdate  # gera data no formato http (rfc 7231)

HOST = '0.0.0.0' # escuta em todas as interfaces locais
PORT = 8080 # porta do nosso servidor
BACKLOG = 50 # fila de conexões pendentes
BUF_SIZE = 4096 # leitura de bloco de 4 kib
MAX_HEADER = 16 * 1024 # limite de 16kib para cabeçalhos (defesa básica)

STATUS_REASONS = {
    200: "OK",
    400: "Bad Request",
    404: "Not Found",
    405: "Method Not Allowed"
}

def http_date():
    # Data no padrão gmt exigido pelo http
    return formatdate(usegmt=True)

def build_response(
        status: int,
        body: bytes,
        extra_headers: dict | None = None,
        content_type: str = "text/html; charset=utf-8",
) -> bytes:
    reason = STATUS_REASONS.get(status, "OK")
    headers = {
        "Date": http_date(),
        "Server": "BrasaHTTP/0.1",
        "Content-Type": content_type,
        "Content-Length": str(len(body)),
        "Connection": "close" # simples, fecha a cada resposta
    }
    if extra_headers:
        headers.update(extra_headers)

    status_line = f"HTTP/1.1 {status} {reason}\r\n"
    headers_blob = "".join(f"{k}: {v}\r\n" for k, v in headers.items())
    # Importante: \r\n\r\n separa headers do corpo e usamos ISO-8859-1
    return (status_line + headers_blob + "\r\n").encode("iso-8859-1") + body

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
    # headers http são iso-8858-1; se algo vier fora, trocamos por caractere de substituição
    text = raw.decode("iso-8859-1", errors="replace")

    # separa cabeçalho do corpo (que vamos ignorar nessa passo)
    parts = text.split("\r\n\r\n", 1)
    head = parts[0]
    lines = head.split("\r\n")
    if not lines:
        raise ValueError("empty request")
    
    # primeira linha: METHOD PARH VERSION
    request_line = lines[0]
    try:
        method, path, version = request_line.split(" ", 3)
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

    return method, path, version, headers


def handle_request(method: str, path: str) -> bytes:
    if method != "GET":
        return build_response(405, b"<h1>405 Method Not Allowed</h1>", {"Allow": "GET"})

    if path == "/":
        body = """<!doctype html>
    <html lang="pt-BR"><meta charset="utf-8">
    <title>BrasaHTTP</title>
    <h1>BrasaHTTP 🔥</h1>
    <p>Parabéns! Seu servidor HTTP está respondendo.</p>
    <p>Rotas: <a href="/">/</a> &middot; <a href="/sobre">/sobre</a></p>
    </html>""".encode("utf-8")
        return build_response(200, body)

    if path == "/sobre":
        body = """<!doctype html>
    <html lang="pt-BR"><meta charset="utf-8">
    <title>Sobre</title>
    <h1>Sobre</h1>
    <p>Servidor minimalista em Python stdlib para estudo.</p>
    <p>Em breve: roteador, estáticos, templates, POST, cookies, TLS...</p>
    <p><a href="/">voltar</a></p>
    </html>""".encode("utf-8")
        return build_response(200, body)


    return build_response(404, b"<h1>404 Not Found</h1>")


def serve_forever():
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
                        method, path, version, headers = parse_request(raw)
                        print(f"{addr[0]} {method} {path}") # log simples
                        resp = handle_request(method, path)
                    except ValueError as e:
                        resp = build_response(400, f"<h1>400 Bad Request</h1><p>{e}</p>".encode("utf-8"))
                    except Exception:
                        # em produção, logue a exceção; aqui, apenas responde 400
                        resp = build_response(400, b"<h1>400 Bad Request</h>")
                    conn.sendall(resp)
        except KeyboardInterrupt:
            print("\nEncerrando BrasaHTTP...")

if __name__ == "__main__":
    serve_forever()

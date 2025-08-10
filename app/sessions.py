import os, hmac, hashlib, time, json, secrets, base64
from pathlib import Path
from email.utils import formatdate

SECRET_PATH = Path(__file__).resolve().parent.parent / "config" / "secret.key"
COOKIE_NAME = "brasa_sess"

def _ensure_secret() -> bytes:
    """Lê (ou cria) um segredo persistente para assinar tokens"""
    SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)
    if SECRET_PATH.exists():
        return SECRET_PATH.read_bytes()
    key = secrets.token_bytes(32)
    SECRET_PATH.write_bytes(key)
    try:
        os.chmod(SECRET_PATH, 0o600)
    except Exception:
        pass
    return key 

_SECRET = None
def get_secret() -> bytes:
    global _SECRET
    if _SECRET is None:
        _SECRET = _ensure_secret()
    return _SECRET

def _b64u_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")

def _b64u_decode(s: str) -> bytes:
    pad = "=" * ((4 - len(s) % 4) % 4)
    return base64.urlsafe_b64decode((s + pad).encode("ascii"))

def issue_token(payload: dict, max_age: int = 7200) -> str:
    """Cria token: base64url(data) . base64url(exp) . base64url(hmac)."""
    now = int(time.time())
    exp = now + max_age
    data = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    head = _b64u_encode(data) + "." + _b64u_encode(str(exp).encode("ascii"))
    mac = hmac.new(get_secret(), head.encode("ascii"), hashlib.sha256).digest()
    return head + "." + _b64u_encode(mac)

def verify_token(token: str) -> dict | None:
    """Valida assinatura e expiração. Retorna payload (dict) ou None."""
    try:
        part_data, part_exp, part_mac = token.split(".", 3)
        head = part_data + "." + part_exp
        mac = _b64u_decode(part_mac)
        good = hmac.compare_digest(mac, hmac.new(get_secret(), head.encode("ascii"), hashlib.sha256).digest())
        if not good:
            return None
        exp = int(_b64u_decode(part_exp).decode("ascii"))
        if time.time() > exp:
            return None
        data = json.loads(_b64u_decode(part_data).decode("utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None
    
def build_set_cookie(name: str, value: str, *, path="/", http_only=True, secure=False, same_site="Lax", max_age: int | None = None, expires_ts: int | None = None) -> str:
    """Monta um header Set-Cookie canônico."""
    parts = [f"{name}={value}", f"Path={path}", f"SameSite={same_site}"]
    if http_only:
        parts.append("HttpOnly")
    if secure:
        parts.append("Secure")     # só use em HTTPS
    if max_age is not None:
        parts.append(f"Max-Age={max_age}")
    if expires_ts is not None:
        parts.append(f"Expires={formatdate(expires_ts, usegmt=True)}")
    return "; ".join(parts)

def build_session_cookie(payload: dict, *, max_age=7200, secure=False) -> str:
    token = issue_token(payload, max_age=max_age)
    return build_set_cookie(COOKIE_NAME, token, http_only=True, secure=secure, same_site="Lax", max_age=max_age, path="/")

def build_clear_session_cookie() -> str:
    past = int(time.time()) - 3600
    return build_set_cookie(COOKIE_NAME, "expired", http_only=True, same_site="Lax", max_age=0, expires_ts=past, path="/")


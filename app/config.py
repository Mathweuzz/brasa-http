from __future__ import annotations
import json, os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CFG_PATH = PROJECT_ROOT / "config" / "config.json"

@dataclass
class ServerCfg:
    host: str = "0.0.0.0"
    port: int = 8080
    backlog: int = 50

@dataclass
class LoggingCfg:
    level: str = "INFO"
    dir: str = "logs"
    app_file: str = "app.log"
    access_file: str = "access.log"
    max_bytes: int = 1_048_576
    backup_count: int = 5

@dataclass
class TLSCfg:
    enabled: bool = False
    port: int = 8443
    cert_file: str = "config/tls/server.crt"
    key_file: str = "config/tls/server.key"

@dataclass
class Settings:
    server: ServerCfg
    logging: LoggingCfg
    tls: TLSCfg

def _merge_env(s: Settings) -> Settings:
    host = os.getenv("BRASA_HOST") or s.server.host
    port = int(os.getenv("BRASA_PORT") or s.server.port)
    level = (os.getenv("BRASA_LOG_LEVEL") or s.logging.level).upper()

    tls_enabled = os.getenv("BRASA_TLS_ENABLED")
    tls_port = os.getenv("BRASA_TLS_PORT")
    tls_cert = os.getenv("BRASA_TLS_CERT")
    tls_key  = os.getenv("BRASA_TLS_KEY")

    return Settings(
        server=ServerCfg(host=host, port=port, backlog=s.server.backlog),
        logging=LoggingCfg(
            level=level, dir=s.logging.dir, app_file=s.logging.app_file,
            access_file=s.logging.access_file, max_bytes=s.logging.max_bytes,
            backup_count=s.logging.backup_count
        ),
        tls=TLSCfg(
            enabled= (s.tls.enabled if tls_enabled is None else (tls_enabled not in ("0","false","False"))),
            port= int(tls_port or s.tls.port),
            cert_file= tls_cert or s.tls.cert_file,
            key_file= tls_key  or s.tls.key_file,
        )
    )


def load_settings(path: Path | None = None) -> Settings:
    cfg_path = Path(path) if path else DEFAULT_CFG_PATH
    data = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
    srv = data.get("server", {})
    log = data.get("logging", {})
    tls = data.get("tls", {})
    settings = Settings(
        server=ServerCfg(
            host=srv.get("host", "0.0.0.0"),
            port=int(srv.get("port", 8080)),
            backlog=int(srv.get("backlog", 50)),
        ),
        logging=LoggingCfg(
            level=(log.get("level", "INFO")).upper(),
            dir=log.get("dir", "logs"),
            app_file=log.get("app_file", "app.log"),
            access_file=log.get("access_file", "access.log"),
            max_bytes=int(log.get("max_bytes", 1_048_576)),
            backup_count=int(log.get("backup_count", 5)),
        ),
        tls=TLSCfg(
            enabled=bool(tls.get("enabled", False)),
            port=int(tls.get("port", 8443)),
            cert_file=tls.get("cert_file", "config/tls/server.crt"),
            key_file=tls.get("key_file",  "config/tls/server.key"),
        ),
    )
    return _merge_env(settings)
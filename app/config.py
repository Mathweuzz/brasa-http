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
class Settings:
    server: ServerCfg
    logging: LoggingCfg

def _merge_env(s: Settings) -> Settings:
    host = os.getenv("BRASA_HOST") or s.server.host
    port = int(os.getenv("BRASA_PORT") or s.server.port)
    level = (os.getenv("BRASA_LOG_LEVEL") or s.logging.level).upper()
    return Settings(
        server=ServerCfg(host=host, port=port, backlog=s.server.backlog),
        logging=LoggingCfg(
            level=level, dir=s.logging.dir, app_file=s.logging.app_file,
            access_file=s.logging.access_file, max_bytes=s.logging.max_bytes,
            backup_count=s.logging.backup_count
        )
    )

def load_settings(path: Path | None = None) -> Settings:
    cfg_path = Path(path) if path else DEFAULT_CFG_PATH
    if cfg_path.exists():
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
    else:
        data = {}
    srv = data.get("server", {})
    log = data.get("logging", {})
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
    )
    return _merge_env(settings)
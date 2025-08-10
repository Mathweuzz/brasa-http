import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Tuple
from app.config import PROJECT_ROOT, LoggingCfg

_APP_LOG_NAME = "brasa.app"
_ACC_LOG_NAME = "brasa.access"

def setup_logging(cfg: LoggingCfg) -> Tuple[logging.Logger, logging.Logger]:
    log_dir = (PROJECT_ROOT / cfg.dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s [%(threadName)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # App logger (erro/infos do servidor)
    app_logger = logging.getLogger(_APP_LOG_NAME)
    app_logger.setLevel(getattr(logging, cfg.level, logging.INFO))
    app_logger.handlers.clear()
    fh_app = RotatingFileHandler(log_dir / cfg.app_file, maxBytes=cfg.max_bytes, backupCount=cfg.backup_count, encoding="utf-8")
    fh_app.setFormatter(fmt)
    app_logger.addHandler(fh_app)
    # Console também (útil no dev)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    app_logger.addHandler(sh)
    app_logger.propagate = False

    # Access logger (um por request)
    acc_logger = logging.getLogger(_ACC_LOG_NAME)
    acc_logger.setLevel(logging.INFO)  # access log fica em INFO
    acc_logger.handlers.clear()
    fh_acc = RotatingFileHandler(log_dir / cfg.access_file, maxBytes=cfg.max_bytes, backupCount=cfg.backup_count, encoding="utf-8")
    fh_acc.setFormatter(logging.Formatter("%(message)s"))
    acc_logger.addHandler(fh_acc)
    acc_logger.propagate = False

    return app_logger, acc_logger
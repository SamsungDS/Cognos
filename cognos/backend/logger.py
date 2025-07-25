import os
import logging
from logging.handlers import RotatingFileHandler


def create_logger(
        name: str,
        log_dir: str = "/var/log/svk/",
        log_file: str = "svkapp-cal.log",
        max_bytes: int = 10 * 1024 * 1024,
        backup_count: int = 5,
        level: int = logging.INFO,
) -> logging.Logger:
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        file_path = os.path.join(log_dir, log_file)

        handler = RotatingFileHandler(
            filename=file_path,
            maxBytes=max_bytes,
            backupCount=backup_count
        )

        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        console = logging.StreamHandler()
        console.setFormatter(formatter)
        logger.addHandler(console)
    return logger

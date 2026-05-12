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
    # Ensure the log directory exists; fallback to a writable local directory on permission errors
    if not os.path.exists(log_dir):
        try:
            os.makedirs(log_dir, exist_ok=True)
        except PermissionError:
            fallback_dir = os.path.join(os.getcwd(), "logs")
            os.makedirs(fallback_dir, exist_ok=True)
            log_dir = fallback_dir

    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        # Ensure no stale handlers remain (important for isolated tests)
        logger.handlers.clear()

        # Determine log file path
        file_path = os.path.join(log_dir, log_file)

        try:
            handler = RotatingFileHandler(
                filename=file_path,
                maxBytes=max_bytes,
                backupCount=backup_count
            )
        except PermissionError:
            # Fallback to a temporary writable directory
            fallback_dir = os.path.join(os.getcwd(), "logs")
            os.makedirs(fallback_dir, exist_ok=True)
            fallback_path = os.path.join(fallback_dir, log_file)
            # Ensure the fallback log file exists
            open(fallback_path, 'a').close()
            handler = RotatingFileHandler(
                filename=fallback_path,
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

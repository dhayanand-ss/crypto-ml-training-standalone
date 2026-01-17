"""
Logger utility for producer-consumer processes.
"""

import logging
import os
from pathlib import Path

# Default log directory
LOG_DIR = os.getenv("LOG_DIR", "/opt/airflow/custom_persistent_shared/logs")
LOG_FILE = os.path.join(LOG_DIR, "consumer.log")


def setup_logger(name: str, log_file: str = None, level: int = logging.INFO) -> logging.Logger:
    """
    Set up a logger with both file and console handlers.
    
    Args:
        name: Logger name
        log_file: Path to log file (default: consumer.log)
        level: Logging level
        
    Returns:
        Configured logger
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler (add first so warnings are visible even if file handler fails)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler
    if log_file is None:
        log_file = LOG_FILE

    # Ensure log directory exists with fallback handling
    log_path = Path(log_file)
    file_handler = None
    
    try:
        # Try to create the log directory
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Set permissions (for Airflow compatibility)
        try:
            os.chmod(log_path.parent, 0o777)
        except Exception:
            pass  # Ignore permission errors on Windows or if already set
        
        # Try to create the file handler
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except (PermissionError, OSError) as e:
        # If we can't write to the intended location, try fallback directories
        fallback_dirs = [
            Path("/tmp/logs"),
            Path("/opt/airflow/logs"),
            Path("./logs")
        ]
        
        file_handler = None
        for fallback_dir in fallback_dirs:
            try:
                fallback_dir.mkdir(parents=True, exist_ok=True)
                fallback_log_file = fallback_dir / f"{log_path.name}"
                file_handler = logging.FileHandler(fallback_log_file)
                file_handler.setLevel(level)
                file_handler.setFormatter(formatter)
                logger.addHandler(file_handler)
                logger.warning(f"Could not write to {log_file}, using fallback: {fallback_log_file}")
                break
            except (PermissionError, OSError):
                continue
        
        # If all fallbacks fail, just log a warning and continue with console-only logging
        if file_handler is None:
            logger.warning(f"Could not create file handler for {log_file}. Using console logging only.")
    
    return logger

















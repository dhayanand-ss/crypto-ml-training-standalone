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
    
    # File handler
    if log_file is None:
        log_file = LOG_FILE
    
    # Ensure log directory exists
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Set permissions (for Airflow compatibility)
    try:
        os.chmod(log_path.parent, 0o777)
    except Exception:
        pass  # Ignore permission errors on Windows
    
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    return logger








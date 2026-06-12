import os
import sys
import logging
from logging.handlers import RotatingFileHandler

LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

class LoggerManager:
    def __init__(self, name="JARVIS", log_file="jarvis.log", level=logging.INFO):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        self.logger.propagate = False  # Prevent duplicates
        
        if not self.logger.handlers:
            formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
            
            # Console Handler
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            console_handler.setLevel(level)
            self.logger.addHandler(console_handler)
            
            # File Handler
            try:
                # Find project root (3 levels up from backend/utils/logger.py)
                root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                log_path = os.path.join(root_dir, log_file)
                
                # Keep logs under 5MB, saving max 3 backup files
                file_handler = RotatingFileHandler(
                    log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
                )
                file_handler.setFormatter(formatter)
                file_handler.setLevel(level)
                self.logger.addHandler(file_handler)
            except Exception as e:
                print(f"  ⚠️  Failed to setup file logging: {e}", file=sys.stderr)

    def get_logger(self):
        return self.logger

# Global logger instance
logger = LoggerManager().get_logger()

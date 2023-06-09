import logging
import time
from os import path, system
from termcolor import cprint

from logging.handlers import RotatingFileHandler

class Logging():
        
    def __init__(self):
        self.log_file_name = "nodectl.log"
        self.log_path = "/var/tessellation/nodectl/"
        self.full_log_path = f"{self.log_path}{self.log_file_name}"
        
        self.check_for_log_file()
        self.log_setup()
                        
                
    def log_setup(self):
        logger = logging.getLogger("nodectl_logging")
        if not len(logger.handlers):
            logger.setLevel(logging.INFO)

            formatter = logging.Formatter(
                '%(asctime)s [%(process)d]: %(levelname)s : %(message)s',
                '%b %d %H:%M:%S')
            formatter.converter = time.gmtime  # if you want UTC time

            log_handler = RotatingFileHandler(self.full_log_path, maxBytes=2097152, backupCount=3)        
            log_handler.setFormatter(formatter)

            logger.addHandler(log_handler)
        self.logger = logger

    def check_for_log_file(self):
        log_dir_exists = path.exists(self.log_path)
        log_file_exists = path.exists(self.full_log_path)

        if not log_dir_exists:
            cprint("No installation found","red")
            cprint("Creating log directory for nodectl","yellow")
            system(f"mkdir -p {self.log_path} > /dev/null 2>&1")
        if not log_file_exists:
            system(f"touch {self.full_log_path} > /dev/null 2>&1")
            
            
if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")
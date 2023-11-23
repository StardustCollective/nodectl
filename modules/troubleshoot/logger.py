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
        self.level = "INFO"
        self.logger = logging.getLogger("nodectl_logging")     
           
        self.check_for_log_file()
        self.get_log_level()
        self.log_setup()
                
    
    def log_setup(self):
        try:
            if len(self.logger.handlers): return
                
            if self.level == "NOTSET": self.logger.setLevel(logging.NOTSET)
            elif self.level == "DEBUG": self.logger.setLevel(logging.DEBUG)
            elif self.level == "INFO": self.logger.setLevel(logging.INFO)
            elif self.level == "WARN": self.logger.setLevel(logging.WARN)
            elif self.level == "ERROR": self.logger.setLevel(logging.ERROR)
            elif self.level == "CRITICAL": self.logger.setLevel(logging.CRITICAL)

            formatter = logging.Formatter(
                '%(asctime)s [%(process)d]: %(levelname)s : %(message)s',
                '%b %d %H:%M:%S')
            formatter.converter = time.gmtime  # if you want UTC time

            log_handler = RotatingFileHandler(self.full_log_path, maxBytes=2097152, backupCount=3)        
            log_handler.setFormatter(formatter)
            self.logger.addHandler(log_handler)
            self.logger.info(f"Logger module initialized with level [{self.level}]")
        except PermissionError as e:
            try:
                cprint("Permission Error encountered, are you using sudo?","red")
            except:
                print("Permission Error encountered, are you using sudo?")
            exit(1)
        except Exception as e:
            try:
                cprint("Unknown Error encountered?","red")
            except:
                print("Unknown Error encountered?")
            exit(1)


    def check_for_log_file(self):
        log_dir_exists = path.exists(self.log_path)
        log_file_exists = path.exists(self.full_log_path)

        if not log_dir_exists:
            cprint("No installation found","red")
            cprint("Creating log directory for nodectl","yellow")
            system(f"mkdir -p {self.log_path} > /dev/null 2>&1")
        if not log_file_exists:
            system(f"touch {self.full_log_path} > /dev/null 2>&1")
            
            
    def get_log_level(self):
        if len(self.logger.handlers): return
        
        try:
            with open(f"{self.log_path}cn-config.yaml","r") as find_level:
                for line in find_level:
                    if "log_level" in line:
                        self.level = line.split(":")[-1].upper()
                        self.level = self.level.strip()
                        break
        except: pass
        
        levels = ["NOTSET","DEBUG","INFO","WARN","ERROR","CRITICAL"]
        if self.level not in levels: self.level = "INFO"

                
if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")
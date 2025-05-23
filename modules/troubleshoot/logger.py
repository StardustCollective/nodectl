import logging
import time
import subprocess

from shlex import split as shlexsplit
from os import path, system, makedirs
from termcolor import cprint
from sys import exit

from logging.handlers import RotatingFileHandler

class Logging():
        
    def __init__(self,caller,process=None):
        self.log_file_name = "nodectl.log"
        self.auto_file_name = "nodectl_auto_restart.log"
        self.version_file_name = "nodectl_versioning.log"
        self.node_cache_file_name = "nodectl_cache.log"
        self.process = process
        self.caller = caller

        self.log_path = "/var/tessellation/nodectl/logs/"

        self.full_log_paths = {
            "main": f"{self.log_path}{self.log_file_name}",
            "auto": f"{self.log_path}{self.auto_file_name}",
            "version": f"{self.log_path}{self.version_file_name}",
            "cache": f"{self.log_path}{self.node_cache_file_name}",
        }
        self.level = "INFO"
        self.logger = {
            "main": logging.getLogger("nodectl_logging"),
            "version": logging.getLogger("nodectl_versioning"),
            "auto": logging.getLogger("nodectl_autorestart"),
            "cache": logging.getLogger("nodectl_cache"),
        } 
           
        try:
            self.check_for_log_file()
            self.get_log_level()
            self.log_setup()
        except PermissionError:
            print("  There was an permission error found")
            print("  Does the process have proper elevated permissions?")
            print("  Please verify and try again.")
            exit("permissions error")
        except Exception as e:
            print("  Unknown logging error was found.")
            print("  Please try again.")
            print("  If error persists you may need to reinstall nodectl?")
            print("  Please seek help on Constellation Network's Discord channels.")
            print(f"  Error: {e}")
            exit(1)
                
    
    def log_setup(self):
        if self.test_for_handler(): return
            
        level_mapping = {
            "NOTSET": logging.NOTSET,
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARN": logging.WARN,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL
        }


        for key, log_path in self.full_log_paths.items():
            if self.level in level_mapping:
                self.logger[key].setLevel(level_mapping[self.level])

            formatter = logging.Formatter(
                '%(asctime)s [%(process)d]: %(levelname)s : %(message)s',
                '%b %d %H:%M:%S')
            formatter.converter = time.gmtime  # if you want UTC time

            log_handler = RotatingFileHandler(log_path, maxBytes=8*1024*1024, backupCount=8)
        
            log_handler.setFormatter(formatter)
            self.logger[key].addHandler(log_handler)
        
        if self.caller != "init":
            self.logger[self.caller].info(f"Logger module initialized with level [{self.level}]")


    def check_for_log_file(self):
        log_dir_exists = path.isdir(self.log_path)

        if not log_dir_exists and self.process not in ["install","installer"]:
            cprint("  No installation found ~OR~ log path not found.","red")
            cprint("  Creating log directory for nodectl","yellow")
            makedirs(self.log_path)
        for value in self.full_log_paths.values():
            if not path.isfile(value):
                cmd = f"touch {value}"
                try:
                    _ = subprocess.run(shlexsplit(cmd), stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, check=True)
                except subprocess.CalledProcessError as e:
                    pass
            

    def test_for_handler(self):
        found = True
        for logger in self.logger.values():
            if not len(logger.handlers):
                found = False
        return found
    

    def get_log_level(self):
        if self.test_for_handler(): return

        try:
            with open(f"/var/tessellation/nodectl/cn-config.yaml","r") as find_level:
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
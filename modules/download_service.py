import json

from re import search
from time import sleep, perf_counter
from sys import exit
from os import system, path, get_terminal_size, makedirs, chmod
from termcolor import colored
from re import sub
from copy import deepcopy 
from types import SimpleNamespace
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from itertools import cycle
import time


from .troubleshoot.errors import Error_codes

class Download():
    
    def __init__(self,command_obj):

        self.parent = command_obj["parent"]
        self.caller = command_obj.get("caller","node_services")
        self.auto_restart = self.parent.auto_restart

        self.functions = self.parent.functions
        self.config_obj = self.parent.config_obj
        self.error_messages = Error_codes(self.config_obj) 
        
        self.log = self.parent.log
        self.log.logger.info("Download services module initiated")

        command_obj = command_obj["command_obj"]
        self.action = command_obj.get("action","normal")
        self.requested_profile = command_obj.get("profile",False)
        self.download_version = command_obj.get("download_version","default")
        self.environment = command_obj.get("environment",False)
        self.argv_list = command_obj.get("argv_list",[])
        self.backup = command_obj.get("backup", True)

        self.retries = 3

        if "-v" in self.argv_list: self.download_version = self.argv_list(self.argv_list.index("-v")+1)
        
        if self.auto_restart: self.profile_names = [self.requested_profile]
        else: self.profile_names = self.functions.profile_names

        if not self.environment:
            self.error_messages.error_code_messages({
                "error_code": "ns-95",
                "line_code": "environment_error",
                "extra": "binary downloads",
            })


    def execute_downloads(self):
        self.set_file_objects()
        self.file_backup_handler()
        self.initialize_output_handler()
        self.threaded_download_handler()
        self.file_backup_handler(False)
        

    # Setters
        
    def set_file_objects(self):
        file_pos = 3
        file_obj = {}

        download_version = self.download_version
        if self.action == "upgrade":
                download_version = download_version[self.profile_names[0]]["download_version"]

        # default the wallet and key tools
        for n, tool in enumerate(["cl-keytool.jar","cl-wallet.jar"]):
            uri, download_version = self.set_download_options(
                self.config_obj[self.profile_names[0]]["jar_repository"], download_version, self.profile_names[0]
            )
            file_obj = {
                **file_obj,
                f"{tool}": { "state": "fetching", "pos": n+1, "uri": f"{uri}/{tool}", "version": download_version } 
            }

        if self.auto_restart:
            # avoid race condition if same file is downloaded at the same time only
            # download tool jars if root profile.
            root_profile = self.functions.test_for_root_ml_type(self.environment)
            if self.requested_profile != root_profile: 
                 file_obj, file_pos = {}, 0  # initialize only

        for n, profile in enumerate(self.profile_names):
            if self.config_obj[profile]["is_jar_static"]: 
                download_version = self.config_obj[profile]["jar_version"]
            if "-v" in self.argv_list: 
                download_version = self.argv_list(self.argv_list.index("-v")+1)
            if self.config_obj[profile]["environment"] == self.environment:
                uri, download_version = self.set_download_options(
                    self.config_obj[profile]["jar_repository"], download_version, profile
                )
                file_obj[self.config_obj[profile]["jar_file"]] = {
                    "state": "fetching",
                    "pos": n+file_pos,
                    "uri": f'{uri}/{self.config_obj[profile]["jar_file"]}',
                    "version": download_version,
                    "profile": profile
                }

        # reorder cursor positions
        for n, file in enumerate(file_obj):
            file_obj[file]["pos"] = len(file_obj)-n

        self.file_list = list(file_obj.keys())
        self.file_obj = file_obj
   
        # debugging purposes
        # self.file_obj = {
        #     "cl-keytool.jar": {'state': 'fetching', 'pos': 4, 'uri': 'https://github.com/Constellation-Labs/tessellation/releases/download/v2.3.0/cl-keytool.jar', 'version': 'v2.3.0'}
        # }

        # self.handle_backups()

        
    def set_file_path(self,file_name):
        tess_dir = self.functions.default_tessellation_dir
        if not path.exists(tess_dir): makedirs(tess_dir)
        return f"{tess_dir}{file_name}"


    def set_download_options(self,uri,download_version,profile):
        if download_version == "default":
            # retrieved from the edge point
            if self.config_obj["global_elements"]["metagraph_name"] == "hypergraph":
                download_version = self.parent.version_obj[self.environment][profile]["cluster_tess_version"]
            elif isinstance(self.config_obj["global_elements"]["metagraph_name"],list):
                # future glean version off of a multi metagraph configuration
                pass
            else:
                # future glean version off of edge_point api for the configured metagraph
                # download_version = self.functions.get_metagraph_version()
                pass

        uri = self.functions.cleaner(uri,"trailing_backslash")
        if uri[0:3] != "http" and uri != "default": # default to https://
            uri = f"https://{uri}"

        uri = self.parent.set_download_repository({
            "repo": uri,
            "profile": profile,
            "download_version": download_version,
        })

        return uri, download_version
    

    # Getters

    def get_download_looper(self,file_name):
        self.get_file_size(file_name)
        for _ in range(0,self.retries):
            self.get_download(file_name)
            if self.test_file_size(file_name):
                return file_name
        return False


    def get_file_size(self,file_name):
        # get size of the file from remote
        # https://api.github.com/repos/Constellation-Labs/tessellation/releases/tags/v2.3.1
        uri = f"{self.file_obj[file_name]['uri']}"
        uri = uri.split("github.com")[1]
        uri = uri.split("download")[0]
        artifact_uri = f"https://api.github.com/repos{uri}tags/{self.file_obj[file_name]['version']}"
        
        response = requests.get(artifact_uri)
        if response.status_code == 200:
            response = response.json()
            if "assets" in response.keys():
                assets = response["assets"]
                for asset in assets:
                    if asset["name"] == file_name:
                        self.file_obj[file_name]["remote_size"] = asset["size"]
                        return

        self.file_obj[file_name]["remote_size"] = False
        return
        

    def get_download(self,file_name):
        self.log.logger.info(f"downloading binary jar files: {file_name} uri [{self.file_obj[file_name]['uri']}] remote size [{self.file_obj[file_name]['remote_size']}]")
        file_path = self.set_file_path(file_name)

        try:
            bashCommand = f'sudo wget {self.file_obj[file_name]["uri"]} -O {file_path} -o /dev/null'
            self.functions.process_command({
                "bashCommand": bashCommand,
                "proc_action": "timeout"
            })
            chmod(file_path, 0o755)

            # using requests.get is 80% slower than wget?
            # response = requests.get(self.file_obj[file_name]["uri"], stream=True)
            # with open(file_path, "wb") as f:
            #     for chunk in response.iter_content(chunk_size=8192):
            #         if chunk:
            #             f.write(chunk)

        except Exception as e:
            self.log.logger.error(f"download_service -> error streaming down binary requirement | [{e}]")

        return file_name # return to the futures executor to print results.
                

    # Tests

    def test_file_size(self,file_name):
        file_path = self.set_file_path(file_name)
        if path.exists(file_path):
            return path.getsize(file_path) == self.file_obj[file_name]["remote_size"]
        return False


    # Handlers

    def auto_restart_handler(self):
        # do not thread
        pass


    def threaded_download_handler(self):
        if not self.auto_restart:
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {executor.submit(self.get_download_looper, file_name): file_name for file_name in list(self.file_obj.keys())}
                for future in as_completed(futures):
                    file_name = futures[future]
                    try:
                        future.result()
                    except Exception as e:
                        self.log.logger.error(f"download_service -> threaded download attempt failed for [{file_name} with [{e}]]")
                        self.file_obj[file_name]["state"] = "failed"
                        self.print_status_handler(file_name) 
                    else:
                        self.file_obj[file_name]["state"] = "completed"
                        self.print_status_handler(file_name)
        else: 
            for file_name in list(self.file_obj.keys()):
                self.get_download_looper(file_name)


    def print_status_handler(self, file_name, init=False):
        escape = "\033[F"
        position = self.file_obj[file_name]["pos"]+1
        if init:
            escape = ""
            position = 1

        status = self.file_obj[file_name]["state"]
        status_color = "green"
        if status == "fetching":
            status_color = "yellow"
        elif status == "failed":
            status_color = "red"

        print(f"{escape}" * position)
        self.functions.print_clear_line()
        self.functions.print_cmd_status({
            "text_start": "Fetch Tessellation binary",
            "brackets": file_name,
            "status": status,
            "status_color": status_color,
            "newline": False
        })
        if not init:
            print(f"\033[{position}B", end="", flush=True)


    def initialize_output_handler(self):
        self.functions.print_header_title({
            "line1": "DOWNLOADING BINARIES",
            "newline": "top",
            "single_line": True,
        })
        for file in list(self.file_obj.keys()):
            self.print_status_handler(file, True)
        print("")


    def file_backup_handler(self,backup=True):
        if not self.backup: 
            self.log.logger.warn(f"download_service -> file_backup_handler -> backup feature disabled")
            return
        
        file_list = []

        if backup:
            self.log.logger.info(f"download_service -> file_backup_handler -> nodectl backing up the following files | [{self.file_list}]")
            action = "backup" 
            file_list = self.file_list
        else:
            action = "restore"
            for file in self.file_obj.keys():
                if self.file_obj[file]["state"] == "failed":
                    file_list.append[file]

        if len(file_list) > 0:
            if action == "restore":
                self.log.logger.warn(f"download_service -> file_backup_handler -> nodectl had to restore the following files | [{file_list}]")
                self.functions.print_paragraphs([
                    [" NOTE ",0,"yellow,on_red"], ["nodectl will only restore failed files",1,"red"],
                ])
            self.functions.backup_restore_files({
                "file_list": self.file_list,
                "location": "/var/tessellation",
                "action": action
            })        


if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation") 
from os import path, makedirs, chmod
from concurrent.futures import ThreadPoolExecutor, as_completed
from termcolor import colored
from copy import deepcopy
import requests

from .troubleshoot.errors import Error_codes

class Download():
    
    def __init__(self,command_obj):

        self.parent = command_obj["parent"]
        self.auto_restart = self.parent.auto_restart

        self.functions = self.parent.functions
        self.config_obj = self.parent.config_obj
        self.error_messages = Error_codes(self.config_obj) 
        self.log = self.parent.log
        command_obj = command_obj["command_obj"]
        action = command_obj.get("action",False)

        self.log_prefix = "download_service ->"
        if self.auto_restart:
            self.log_prefix = f"auto_restart -> {self.log_prefix}"
        if action == "quiet_install":
            self.log_prefix = f"download_service -> quiet installation ->"
            self.auto_restart = True # utilize the auto_restart flag to disable threading and printouts
            self.functions.auto_restart = True
            
        self.caller = command_obj.get("caller","node_service")
        self.action = command_obj.get("action","normal")
        self.requested_profile = command_obj.get("profile",False)
        self.download_version = command_obj.get("download_version","default")
        self.tools_version = command_obj.get("tools_version",self.download_version)
        self.install_upgrade = command_obj.get("install_upgrade",False)
        self.environment = command_obj.get("environment",False)
        self.argv_list = command_obj.get("argv_list",[])
        self.backup = command_obj.get("backup", True)
        self.version_obj = command_obj.get("version_obj",False)

        self.successful = True
        self.skip_asset_check = False
        self.fallback = False
        self.retries = 3
        self.file_pos = 1
        self.file_count = 0
        self.cursor_setup = {
            "up": 6,
            "clear": 7,
            "reset": -1,
            "down": -1,
            "success": True,
        }

        self.log.logger.info(f"{self.log_prefix} module initiated")
        if self.caller == "refresh_binaries" or self.caller == "_rtb":
            self.caller = "refresh_binaries"
            self.log.logger.debug(f"{self.log_prefix} - refresh node binaries.")
        elif self.caller == "update_seedlist" or self.caller == "_usl":
            self.caller = "update_seedlist"
            self.log.logger.debug(f"{self.log_prefix} - download seed lists.")
        elif self.action == "upgrade":
            self.log.logger.debug(f"{self.log_prefix} - upgrade module called.")
        elif "install" in self.action:
            self.log.logger.debug(f"{self.log_prefix} - {self.action} module called.")

        if "-v" in self.argv_list: self.download_version = self.argv_list(self.argv_list.index("-v")+1)
        
        self.profile_names = [self.requested_profile]
        if not self.requested_profile: 
            self.profile_names = self.functions.profile_names
            self.profile_names = self.functions.clear_global_profiles(self.profile_names)

        if not self.environment:
            self.error_messages.error_code_messages({
                "error_code": "ds-95",
                "line_code": "environment_error",
                "extra": "binary downloads",
            })


    def execute_downloads(self):
        self.set_default_version()
        self.set_file_objects()
        self.set_seedfile_object()
        self.set_file_obj_order()
        self.file_backup_handler("backup")
        self.initialize_output_handler()
        self.threaded_download_handler()
        self.file_fallback_handler()
        self.file_backup_handler("restore")

        if self.fallback:
            self.cursor_setup["up"] = self.cursor_setup["up"]+7
            self.cursor_setup["clear"] = self.cursor_setup["clear"]+7
            self.cursor_setup["reset"] = self.cursor_setup["reset"]+7

        return self.cursor_setup

    # Setters
        
    def set_file_objects(self,fallback=False):
        if self.caller == "update_seedlist": return
        if self.fallback:
            self.file_obj = deepcopy(self.file_obj_fallback)
            return
        
        repo_location_key = "jar_repository"
        if fallback:
            repo_location_key = "jar_fallback_repository" 
        
        file_pos = 3
        file_obj = {}

        download_version = self.download_version

        # default the wallet and key tools
        if self.auto_restart and self.action != "quiet_install":
            # auto_restart avoid race condition if same file is downloaded at the same time only
            # download tool jars if root profile.
            root_profile = self.functions.test_for_root_ml_type(self.environment)
            if self.requested_profile != root_profile: 
                 file_obj, file_pos = {}, 0  # initialize only
        if not self.requested_profile:
            for n, tool in enumerate(["cl-keytool.jar","cl-wallet.jar"]):
                if self.config_obj["global_elements"]["metagraph_name"] == "hypergraph":
                    pre_uri = self.config_obj[self.profile_names[0]][repo_location_key]
                else:
                    pre_uri = self.functions.default_tessellation_repo

                uri = self.set_download_options(
                    pre_uri, self.tools_version, self.profile_names[0], fallback,
                )

                file_obj = {
                    **file_obj,
                    f"{tool}-cnngglobal": { 
                        "state": "fetching", "pos": n+1, "uri": f"{uri}/{tool}", "version": self.tools_version, 
                        "type": "binary", "profile": "global", 
                        "dest_path": f"{self.functions.default_tessellation_dir}{tool}",
                    } 
                }

        for n, profile in enumerate(self.profile_names):
            file_pos += n

            if self.config_obj[profile]["is_jar_static"]: 
                try:
                    download_version = self.config_obj[profile]["jar_version"]
                    uri = self.config_obj[profile][repo_location_key]
                except:
                    self.error_messages.error_code_messages({
                        "error_code": "ds-134",
                        "line_code": "config_error",
                        "extra": "format",
                        "extra2": "static jar value issue."
                    })

            elif "-v" in self.argv_list: 
                download_version = self.argv_list(self.argv_list.index("-v")+1)
                
            elif self.config_obj[profile]["environment"] == self.environment:
                uri = self.set_download_options(
                    self.config_obj[profile][repo_location_key], download_version, profile, fallback,
                )

            file_obj[f'{self.config_obj[profile]["jar_file"]}-cnng{profile}'] = {
                "state": "fetching",
                "pos": file_pos,
                "uri": f'{uri}/{self.config_obj[profile]["jar_file"]}',
                "version": download_version,
                "profile": profile,
                "dest_path": self.config_obj[profile]["jar_path"], 
                "type": "binary"
            }
            
        if fallback:
            self.file_obj_fallback = file_obj
            self.file_pos_fallback = file_pos
        else:
            self.file_obj = file_obj
            self.file_pos = file_pos

        if self.config_obj["global_elements"]["jar_fallback"] and not fallback:
            # recursive
            self.set_file_objects(True)

        # debugging purposes
        # self.file_obj = {
        #     "cl-keytool.jar-cnngglobal": {
        #         'state': 'fetching', 'pos': 4, 'uri': 'https://github.com/Constellation-Labs/tessellation/releases/download/v2.3.0/cl-keytool.jar', 
        #         'version': 'v2.3.0', 'profile': 'global', 'dest_path': '/var/tessellation/cl-keytool.jar', 'type': 'binary',
        #     }
        # }


    def set_seedfile_object(self):
        self.log.logger.debug(f"{self.log_prefix} -> set_seedfile_object -> initiated.")
        if self.fallback: return

        if self.caller == "update_seedlist": self.file_obj = {}

        if self.requested_profile: profiles = [self.requested_profile]
        else: profiles = self.functions.profile_names

        for n, profile in enumerate(profiles):
            self.file_pos += n+1
            seed_path = self.config_obj[profile]["seed_path"]    
            seed_repo = self.config_obj[profile]['seed_repository']
            seed_file = self.config_obj[profile]["seed_file"]
                
            state = "fetching"
            if "disable" in seed_path:
                state = "disabled"
                seed_file = "seed-disabled"

            if self.download_version == "default":
                self.log.logger.info(f"{self.log_prefix} [{self.environment}] seedlist")   
                self.download_version = self.parent.version_obj[self.environment][profile]['cluster_tess_version']

            if self.config_obj["global_elements"]["metagraph_name"] == "hypergraph" and self.environment != "mainnet":
                # does not matter if the global_elements -> metagraph_name is set, if not mainnet
                if self.environment == "testnet" or self.environment == "integrationnet":
                    self.skip_asset_check = True
                    seed_repo = f"https://constellationlabs-dag.s3.us-west-1.amazonaws.com/{self.environment}-seedlist"
            elif seed_repo == "disable":
                pass
            else:
                seed_repo = self.set_download_options(
                    seed_repo, self.download_version, profile, False, "seed"
                )
                seed_repo = f"{seed_repo}/{seed_file}"

            self.file_obj = {
                **self.file_obj,
                f"{seed_file}-cnng{profile}": {
                    "file_name": seed_file, 
                    "state": state, 
                    "pos": self.file_pos, 
                    "uri": seed_repo, 
                    "version": self.download_version,
                    "profile": profile,
                    "dest_path": self.functions.cleaner(seed_path,"double_slash"), 
                    "type": "seedlist",
                }
            }

            # debugging purposes
            # self.file_obj = {
            #     "testnet-seedlist-cnngdag-l0": {'state': 'fetching', 'pos': 5, 'uri': 'https://constellationlabs-dag.s3.us-west-1.amazonaws.com/testnet-seedlist', 'version': 'v2.3.0', 'profile': 'dag-l0', 'type': 'seedlist'}
            # }
            if not path.exists(self.config_obj[profile]['seed_location']):
                if self.config_obj[profile]['seed_location'] != "disable": 
                    makedirs(self.config_obj[profile]['seed_location'])


    def set_file_path(self,file_name,file_path=False):
        if not file_path:
            file_path = self.functions.default_tessellation_dir
        else:
            file_path = self.functions.cleaner(file_path,"double_slash")  

        if not path.exists(file_path) and file_path != "disable":
            makedirs(file_path)

        return self.functions.cleaner(f"{file_path}{file_name}","double_slash")  


    def set_default_version(self):
        if self.fallback: return

        error_str = "The Download Service module may have conflicted with a parallel running versioning service at the time of the Node Operator's request."
        for tries in range(0,5):
            try:
                # readability
                env = self.functions.environment_name

                if self.requested_profile: profile = self.requested_profile
                else: profile = self.functions.profile_names[0]

                if self.tools_version == "default":
                    self.tools_version = self.functions.version_obj[env][profile]["cluster_tess_version"]

                if self.download_version == "default":
                    if self.config_obj["global_elements"]["metagraph_name"] == "hypergraph":
                        self.download_version = self.functions.version_obj[env][profile]["cluster_tess_version"]
                    else:
                        self.download_version = self.functions.version_obj[env][profile]["cluster_metagraph_version"]
            except Exception as e:
                if tries < 1:
                    self.functions.version_obj = self.functions.handle_missing_version(self.parent.version_class_obj)
                    continue
                if tries < 2:
                    if not self.auto_restart:
                        self.functions.print_paragraphs([
                            ["",1],[" STAND BY ",0,"red,on_yellow"],[error_str,1,"yellow"],
                        ])
                if tries < 4:
                    phrase_str = colored("Attempt ","cyan")+colored(tries,"red")+colored(" of ","cyan")+colored("3","red")
                    self.functions.print_timer({
                        "p_type": "cmd",
                        "seconds": 20 if tries < 3 else 60,
                        "step": -1,
                        "end_phrase": "...",
                        "phrase": phrase_str,
                        "status": "Pausing"
                    })
                    self.functions.version_obj = self.functions.handle_missing_version(self.parent.version_class_obj)
                else:
                    self.log.logger.error(f"{self.log_prefix} -> set_default_version -> unknown error occurred, retry command to continue | error [{e}]")
                    self.error_messages.error_code_messages({
                        "error_code": "ds-265",
                        "line_code": "unknown_error",
                        "extra": e,
                        "extra2": error_str,
                    })

        return
    

    def set_download_options(self, uri, download_version, profile, fallback, dtype="repo"):
        github, s3 = False, False
        if isinstance(self.config_obj["global_elements"]["metagraph_name"],list):
            # future glean version off of a multi metagraph configuration
            pass
        else:
            # future glean version off of edge_point api for the configured metagraph
            # download_version = self.functions.get_metagraph_version()
            pass

        if dtype == "seed":
            if self.config_obj[profile]["seed_github"]: github = True
            uri = self.config_obj[profile]["seed_repository"]
        else:
            if fallback:
                if "github.com" in self.config_obj[profile]["jar_fallback_repository"]: github = True
                elif "s3" in self.config_obj[profile]["jar_fallback_repository"] and "amazonaws" in self.config_obj[profile]["jar_fallback_repository"]:
                    s3 = True
            else:
                if self.config_obj[profile]["jar_github"]: github = True
                elif self.config_obj[profile]["jar_s3"]: s3 = True

        uri = self.functions.cleaner(uri,"trailing_backslash")
        if not uri.startswith("http"): # default to https://
            uri = f"https://{uri}"

        if github:
            return f'{uri}/releases/download/{download_version}'
        elif s3:
            if download_version.startswith('v') and self.config_obj[profile]["environment"] == "testnet":
                # exception for TestNet 
                download_version = download_version[1:]
            return f'{uri}/{download_version}'
        return uri


    def set_file_obj_order(self):
        # reorder cursor positions
        self.cursor_setup["clear"] += len(self.file_obj)
        self.cursor_setup["down"] = len(self.file_obj)+1
        for n, file in enumerate(self.file_obj):
            self.file_obj[file]["pos"] = n

        if self.config_obj["global_elements"]["jar_fallback"] and self.caller != "update_seedlist":
            for n, file in enumerate(self.file_obj_fallback):
                self.file_obj_fallback[file]["pos"] = n


    # Getters

    def get_download_looper(self,file_key):
        file_name = self.get_file_from_fileobj(file_key)
        self.get_remote_file_size(file_key, file_name)
        for _ in range(0,self.retries):
            self.get_download(file_key, file_name)
            if self.test_file_size(file_key, file_name):
                return file_key
        raise Exception("file did not download properly")


    def get_download(self,file_key, file_name, fallback=False):
        self.log.logger.info(f"{self.log_prefix} -> get_download -> downloading [{self.file_obj[file_key]['type']}] file: {file_name} uri [{self.file_obj[file_key]['uri']}] remote size [{self.file_obj[file_key]['remote_size']}]")
        file_path = self.file_obj[file_key]["dest_path"]

        file_path_only = path.split(file_path)[0]
        if not path.exists(file_path_only):
            makedirs(file_path_only)
        
        if self.file_obj[file_key]["state"] == "disabled":
            self.log.logger.warning(f"{self.log_prefix} get_download -> downloading [{self.file_obj[file_key]['type']}] disabled, skipping.")
            return

        try:
            bashCommand = f'sudo wget {self.file_obj[file_key]["uri"]} -O {file_path} -o /dev/null'
            self.functions.process_command({
                "bashCommand": bashCommand,
                "proc_action": "timeout"
            })
            if self.file_obj[file_key]["type"] == "binary":
                chmod(file_path, 0o755)

        except Exception as e:
            self.log.logger.error(f"{self.log_prefix} get_download -> error streaming down [{self.file_obj[file_key]['type']}] requirement | [{e}]")

        return file_key # return to the futures executor to print results.
    

    def get_remote_file_size(self,file_key,file_name):
        # get size of the file from remote
        # https://api.github.com/repos/Constellation-Labs/tessellation/releases/tags/{version}

        uri = f"{self.file_obj[file_key]['uri']}"

        if "https://github.com" in uri or "http://github.com" in uri:
            uri = uri.split("github.com")[1]
            uri = uri.split("download")[0]
            artifact_uri = f"https://api.github.com/repos{uri}tags/{self.file_obj[file_key]['version']}"
            
            response = requests.get(artifact_uri)
            if response.status_code == 200:
                response = response.json()
                if "assets" in response.keys():
                    assets = response["assets"]
                    for asset in assets:
                        if asset["name"] == file_name:
                            self.file_obj[file_key]["remote_size"] = asset["size"]
                            return
                self.log.logger.error(f"{self.log_prefix} -> get_remote_file_size -> failed to retrieve the file size. Status code: {response.status_code}")
                self.file_obj[file_key]["remote_size"] = -1
                return 
            
        elif "s3" in uri or "amazonaws" in uri:
            response = requests.head(uri)
            if response.status_code == 200:
                    self.file_obj[file_key]["remote_size"] = int(response.headers.get('Content-Length', 0))
                    return
            else:
                self.log.logger.error(f"{self.log_prefix} -> get_remote_file_size -> failed to retrieve the file size. Status code: {response.status_code}")
                self.file_obj[file_key]["remote_size"] = -1
                        
        self.file_obj[file_key]["remote_size"] = -1
        return           

    # Tests

    def test_file_size(self,file_key,file_name):
        if self.skip_asset_check: return True

        if self.file_obj[file_key]["remote_size"] < 0:
            self.log.logger.error(f"download_service -> test_file_size -> {file_name} remote size did not return a | remote value: {self.file_obj[file_key]['remote_size']}")
            raise Exception("file size")
        
        file_path = self.file_obj[file_key]["dest_path"]
        if self.file_obj[file_key]["state"] == "disabled": 
            self.log.logger.warning(f"download_service -> test_file_size -> {file_name} -> was determined to be [disabled] -> skipping")
            return True # skip test
        
        if path.exists(file_path):
            self.log.logger.info(f"download_service -> test_file_size -> {file_name} ->  local size: [{path.getsize(file_path)}] remote size [{self.file_obj[file_key]['remote_size']}]")
            return path.getsize(file_path) == self.file_obj[file_key]["remote_size"]
        raise Exception("file size")

    # Handlers

    def auto_restart_handler(self):
        # do not thread
        pass


    def threaded_download_handler(self):
        if self.auto_restart:
            for file_name in list(self.file_obj.keys()):
                if self.file_obj[file_name]["state"] != "disabled":
                    self.get_download_looper(file_name)
                    self.redundant_check()
                    test = 1
        else:
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {executor.submit(self.get_download_looper, file_name): file_name for file_name in list(self.file_obj.keys())}
                for future in as_completed(futures):
                    file_name = futures[future]
                    try:
                        future.result()
                    except Exception as e:
                        self.log.logger.error(f"{self.log_prefix} threaded download attempt failed for [{file_name} with [{e}]]")
                        if self.file_obj[file_name]["state"] != "disabled":
                            self.file_obj[file_name]["state"] = "failed"
                            self.successful = False
                        self.print_status_handler(file_name) 
                    else:
                        if self.file_obj[file_name]["state"] != "disabled":
                            self.file_obj[file_name]["state"] = "completed"
                            if not self.functions.get_size(self.file_obj[file_name]["dest_path"],True):
                                self.file_obj[file_name]["state"] = "failed"
                        self.print_status_handler(file_name)

        self.cursor_setup["reset"] = self.cursor_setup["clear"]-1


    def get_file_from_fileobj(self,file_name):
        s_file = file_name.replace("-cnngglobal","")
        
        try:
            s_file = file_name.replace(f"-cnng{self.file_obj[file_name]['profile']}","")
        except:
            pass
        
        return s_file


    def print_status_handler(self, file_name, init=False):
        if self.auto_restart: return

        s_file = self.get_file_from_fileobj(file_name)

        position = self.file_obj[file_name]["pos"]
        end_position = position+1
        if init:
            position -= 1

        status = self.file_obj[file_name]["state"]
        status_color = "green"
        if status == "fetching":
            status_color = "yellow"
        elif status == "failed":
            status_color = "red"
        elif status == "disabled":
            status_color = "magenta"

        text_start = "Fetch"
        brackets = f'{s_file} -> {self.file_obj[file_name]["profile"]}'
        if status == "disabled": 
            brackets = brackets.replace(s_file,"seedlist for")

        print("\033[B" * position)
        self.functions.print_clear_line()
        self.functions.print_cmd_status({
            "text_start": text_start,
            "brackets": brackets,
            "status": status,
            "status_color": status_color,
            "newline": False
        })
        print(f"\033[{end_position}A", end="", flush=True)


    def initialize_output_handler(self):
        if self.auto_restart: return

        title = "DOWNLOADING BINARIES"
        if self.caller == "update_seedlist":
            title = "UPDATING SEEDLISTS"
            
        self.functions.print_header_title({
            "line1": title,
            "newline": "both",
            "single_line": True,
        })

        # display the download version ( may be different versions per file )
        download_version = "-1"
        for n, file in enumerate(self.file_obj.keys()):
            if download_version != self.file_obj[file]["version"]:
                if n > 0: 
                    self.cursor_setup = {key: value + 1 for key, value in self.cursor_setup.items() if key != "success"}
                    self.cursor_setup["success"] = True
                download_version = self.file_obj[file]["version"]
                self.functions.print_cmd_status({
                    "text_start": "Downloading version",
                    "status": download_version,
                    "status_color": "green",
                    "newline": True,
                })

        for file in list(self.file_obj.keys()):
            self.print_status_handler(file, True if file == list(self.file_obj.keys())[0] else False)


    def file_fallback_handler(self):
        if not self.config_obj["global_elements"]["jar_fallback"]: return
        self.config_obj["global_elements"]["jar_fallback"] = False  # do not allow multiple executions
        file_list = [file for file in list(self.file_obj.keys()) if self.file_obj[file]["state"] == "failed"]
        if len(file_list) > 0:
            nl = 2
            if "install" in self.action: nl = 1
            if not self.auto_restart:
                print(f"\033[{self.cursor_setup['down']}B", end="", flush=True)
                self.functions.print_paragraphs([
                    ["",nl],[" FALLBACK ",0,"yellow,on_red"], ["nodectl identified a fallback for this cluster.",0,"yellow"],
                    ["Attempting secondary download mechanism",1,"yellow"],
                ])
            self.fallback = True
            self.execute_downloads()


    def file_backup_handler(self,action):
        if not self.backup: 
            self.log.logger.warning(f"{self.log_prefix} file_backup_handler -> backup feature disabled")
            return
        if self.fallback and action == "backup": 
            self.log.logger.debug(f"{self.log_prefix} file_backup_handler -> skipping redundant backup.")
            return

        if action == "restore": 
            self.redundant_check()

        file_list = [file for file in list(self.file_obj.keys()) if self.file_obj[file]["state"] == "failed"]
        if action == "backup":
            file_list = [file for file in list(self.file_obj.keys()) if self.file_obj[file]["state"] != "disabled"]
        
        self.log.logger.info(f"{self.log_prefix} file_backup_handler -> nodectl executing action [{action}] on the following files | [{file_list}]")
        
        if len(file_list) > 0:
            if action == "restore":
                self.log.logger.warning(f"{self.log_prefix} file_backup_handler -> nodectl had to restore the following files | [{file_list}]")
                if not self.auto_restart:
                    print(f"\033[8B", end="", flush=True)
                    self.cursor_setup = {key: value + 2 for key, value in self.cursor_setup.items() if key != "success"}
                    self.cursor_setup["success"] = False
                    self.cursor_setup["down"] = 0
                    self.functions.print_paragraphs([
                        [" NOTE ",0,"yellow,on_red"], ["nodectl will only restore failed files",1,"red"],
                    ])

            for file in file_list:
                print_start, print_complete = False, False
                if file == file_list[0]: print_start = True
                if file == file_list[-1]: print_complete = True
            
                location, file_list_single = path.split(self.file_obj[file]["dest_path"])
                file_list_single = [file_list_single]

                self.functions.backup_restore_files({
                    "file_list": file_list_single,
                    "location": location,
                    "action": action,
                    "remove": True if action == "backup" else False,
                    "print_start": print_start,
                    "print_complete": print_complete,
                })    


    def redundant_check(self):
        check_action = "auto_restart file size" if self.auto_restart else "extra redundant"
        self.log.logger.debug(f"{self.log_prefix} {check_action} check initiated")
        for file in self.file_obj.keys():
            if self.file_obj[file]["state"] == "disabled": continue
            if "seedlist" in str(self.file_obj[file]): continue
            file_size = self.functions.get_size(self.file_obj[file]["dest_path"],True)
            if file_size < 1 and file_size != self.file_obj[file]['remote_size']:
                file_name = file.replace(f'-cnng{self.file_obj[file]["profile"]}',"")
                self.log.logger.error(f"{self.log_prefix} redundant check method found possible file size issue [{file_name}] file size [{file_size}] remote size [{self.file_obj[file]['remote_size']}]")
                self.file_obj[file]['state'] = "failed"



if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation") 
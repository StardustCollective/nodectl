import json

from time import sleep
from os import path, mkdir
from requests import get
from sys import exit
from concurrent.futures import ThreadPoolExecutor
from copy import copy, deepcopy

from ..functions import Functions
from ..troubleshoot.logger import Logging
from ..troubleshoot.errors import Error_codes

class Versioning():

    def __init__(self,command_obj):
        self.log = Logging()
        
        # important
        # migration -> verify_config_type -> simple verification value counters
        #                                    may need to be adjusted if new key/pair 
        #                                    was introduced.  The value should remain
        #                                    at the last required migration upgrade_path
        
        nodectl_version = "v2.13.0"
        nodectl_yaml_version = "v2.2.0"
                
        node_upgrade_path_yaml_version = "v2.1.0" # if previous is 'current_less'; upgrade path needed (for migration module)

        self.upgrade_path_path = f'https://raw.githubusercontent.com/stardustCollective/nodectl/nodectl_{nodectl_version.replace(".","")}/admin/upgrade_path.json'
        # self.upgrade_path_path = f'https://raw.githubusercontent.com/StardustCollective/nodectl/main/admin/upgrade_path.json'
                
        self.print_messages = command_obj.get("print_messages",True)
        self.show_spinner = command_obj.get("show_spinner",True)
        self.called_cmd = command_obj["called_cmd"]
        self.request = command_obj.get("request","runtime")  # runtime, install 
        self.force = command_obj.get("force",False)
        self.verify_only = command_obj.get("verify_only",False)
        self.print_object = command_obj.get("print_object",False)
        self.seconds = command_obj.get("seconds",60*5)
        self.static_seconds = 60*5
        
        self.config_obj = command_obj.get("config_obj",False)
    
        self.auto_restart = False

        exception_cmds = ["auto_restart","uvos","service_restart","quick_install"]
        if self.called_cmd in exception_cmds:
            if self.called_cmd != "quick_install": self.auto_restart = True
            self.print_messages = False 
            self.show_spinner = False 
        
        self.service_uvos = False
        self.logging_name = self.called_cmd
        if self.called_cmd == "uvos":
            self.logging_name = "versioning service"
            self.service_uvos = True
        
        self.update_required = False
        self.new_creation = False
        self.update_file_only = False
        self.version_valid_cache = False
        self.date_time = None
        self.session_timeout = 2

        self.nodectl_static_versions = {
            "node_nodectl_version": nodectl_version,
            "node_nodectl_yaml_version": nodectl_yaml_version,  
            "node_upgrade_path_yaml_version": node_upgrade_path_yaml_version,          
        }
        self.version_obj = copy(self.nodectl_static_versions)
        self.version_obj["nodectl_github_version"] = f'nodectl_{self.version_obj["node_nodectl_version"].replace(".","")}'
        self.version_obj_path = "/var/tessellation/nodectl/"
        self.version_obj_file = f"{self.version_obj_path}version_obj.json"

        init_only = ["verify_nodectl","_vn","-vn","uninstall"]
        if self.called_cmd in init_only: return
        
        self.execute_versioning()
        
        
    def execute_versioning(self):
        self.log.logger.debug(f"versioning - called [{self.logging_name}] - executing versioning update request.")
        if self.called_cmd == "show_version": return # nodectl only
        if self.called_cmd in ["upgrade","install","quick_install"]: self.force = True

        self.functions = Functions(self.config_obj)
        self.error_messages = Error_codes(self.functions) 
        self.functions.log = self.log # avoid embedded circular reference errors

        if self.auto_restart and not self.service_uvos: 
            return  # relies on service updater
                        
        self.get_cached_version_obj()
        
        if self.update_required:
            self.log.logger.info(f"versioning - called by [{self.logging_name}] - updating versioning object")
        else:
            msg = f"localhost versioning object under {str(int(self.seconds/60))} minutes old."
            self.log.logger.info(f"versioning - called by [{self.logging_name}] - {msg}")
            
            
    def get_version_obj(self):
        self.log.logger.debug(f"versioning - called by [{self.logging_name}] - request for version_obj made.")
        return self.version_obj
    
    
    def get_cached_version_obj(self):
        self.log.logger.debug(f"versioning - called by [{self.logging_name}] - initiating cached version object check and request.")
                
        self.date_time = self.functions.get_date_time({"action": "datetime"})
        self.next_time = self.functions.get_date_time({
            "action": "future_datetime", 
            "elapsed": self.static_seconds,
        })
        
        try:
            with open(self.version_obj_file, 'r') as file:
                version_obj = json.load(file)
                self.old_version_obj = deepcopy(version_obj)
        except FileNotFoundError:
            self.log.logger.info(f"Versioning - File [{self.version_obj_file}] not found, creating...")
            self.new_creation = True
        except json.JSONDecodeError:
            self.log.logger.error(f"Versioning Failed to decode JSON in [{self.version_obj_file}].")
            if self.called_cmd != "uvos":
                self.print_error("ver-126","invalid_file_format")
        
        self.verify_version_object()
        if self.new_creation:
            self.log.logger.debug(f"versioning - called by [{self.logging_name}] - new versioning json object file creation.")
            self.write_version_obj_file()
        else:
            elapsed = self.functions.get_date_time({
                "action": "get_elapsed",
                "old_time": version_obj["last_updated"],
            })
            if (self.force or elapsed.seconds > self.seconds) and (not self.auto_restart or self.service_uvos):
                self.log.logger.debug(f"versioning - called by [{self.logging_name}] - out of date - updating.")
                self.write_version_obj_file()
            else:
                self.log.logger.debug(f"versioning - called by [{self.logging_name}] - up to date - no action taken.")

        if self.auto_restart: return version_obj            
        if not self.new_creation and not self.force: 
            version_obj = {
                **version_obj,
                **self.nodectl_static_versions, # pick up new nodectl static variables
            }
            if self.version_obj["node_nodectl_version"] != self.old_version_obj["node_nodectl_version"] or self.version_obj["node_nodectl_yaml_version"] != self.old_version_obj["node_nodectl_yaml_version"]:
                self.update_file_only = True
                self.write_version_obj_file()
            self.version_obj = version_obj
        self.force = False # do not leave forced on
        
        
    def pull_from_jar(self,jar):
        self.log.logger.debug(f"versioning - called by [{self.logging_name}] - pulling tessellation version for jar file.")
        bashCommand = f"/usr/bin/java -jar /var/tessellation/{jar} --version"
        node_tess_version = self.functions.process_command({
            "bashCommand": bashCommand,
            "proc_action": "wait"
        })
        try: node_tess_version = node_tess_version.strip("\n")
        except: node_tess_version = "v0.0.0"
        if node_tess_version == "v" or node_tess_version == "" or node_tess_version == None:
            node_tess_version = "v0.0.0"
        return node_tess_version
    
    
    def write_version_obj_file(self):
        self.log.logger.debug(f"versioning - called by [{self.logging_name}] - write_version_obj_file initiated.")
        self.update_required = True

        if self.update_file_only:
            self.write_file()
            return 
                   
        with ThreadPoolExecutor() as executor:
            # set default variables
            self.functions.version_obj = self.version_obj
            self.functions.set_statics()
            self.functions.set_default_variables({})
            if self.auto_restart: self.functions.auto_restart = True
            self.pull_upgrade_path()

            test_obj = {
                "threaded": False,
                "caller": "versioning",
                "spinner": False,
                "print_output": False,
                "profile": self.functions.default_profile,
                "simple": True                
            }
            self.log.logger.debug(f"versioning - version test obj | [{test_obj}]")
            state = self.functions.test_peer_state(test_obj)
            
            if (state == "ApiNotReady" or state == "ApiNotResponding") and self.called_cmd == "uvos": 
                # after installation there should be a version obj already created
                # no need to update file while Node is not online.
                self.log.logger.warn(f"versioning - versioning service found [{self.functions.default_profile}] in state [{state}] exiting module.")
                exit(0)
                    
            if self.show_spinner:  
                self.functions.event = True
                _ = executor.submit(self.functions.print_spinner,{
                    "msg": "Gathering Tessellation version info",
                    "color": "magenta",
                }) 
          
            # get cluster Tessellation
            self.log.logger.debug(f"versioning - called by [{self.logging_name}] - building new version object.")
           
            version_obj, env_version_obj = {}, {}
            last_environment = False
            info_list = ["version"]
            metagraph = False

            for environment in self.functions.environment_names:
                for profile in self.functions.profile_names:
                    upgrade_path = deepcopy(self.upgrade_path)
                    if self.config_obj[profile]["environment"] != environment: continue
                    api_endpoint = "/node/info"
                    api_host = self.config_obj[profile]["edge_point"]
                    api_port = self.config_obj[profile]["edge_point_tcp_port"]

                    # migration only version by-pass
                    if self.config_obj["global_elements"]["nodectl_yaml"] == self.nodectl_static_versions["node_nodectl_yaml_version"]: # migration only version by-pass
                        if self.config_obj["global_elements"]["metagraph_name"] != "hypergraph":
                            info_list = ["metagraphVersion"]
                            api_endpoint = "/metagraph/info"
                            metagraph = True

                        
                    if not last_environment or last_environment != self.config_obj[profile]["environment"]:
                        version_obj = {
                            **version_obj,
                            f"{environment}": {
                                "nodectl": {}
                            },
                        }
                    if last_environment != self.config_obj[profile]["environment"]:
                        env_version_obj = {f"{profile}": {}}        
                        
                        try:
                            version = self.functions.get_api_node_info({
                                "api_host": api_host,
                                "api_port": api_port,
                                "api_endpoint": api_endpoint,
                                "info_list": info_list,
                                "tolerance": 2,
                            })
                        except:
                            version = "v0.0.0"
                            metagraph_version = "v0.0.0"
                        else:
                            if metagraph:
                                metagraph_version = version[0]
                                if not metagraph_version.startswith("v"): metagraph_version = f"v{metagraph_version}"
                                try:
                                    test = self.functions.lb_urls[self.config_obj[profile]["environment"]][0]
                                    version = self.functions.get_api_node_info({
                                        "api_host": self.functions.lb_urls[self.config_obj[profile]["environment"]][0],
                                        "api_port": self.functions.lb_urls[self.config_obj[profile]["environment"]][1],
                                        "api_endpoint": "/node/info",
                                        "info_list": ["version"],
                                        "tolerance": 2,
                                    })
                                except:
                                    version = "v0.0.0"
                                else:
                                    version = version[0]
                            else:
                                metagraph_version = None
                                version = version[0]
                    
                    if profile not in env_version_obj.keys():
                        env_version_obj = {
                            **env_version_obj,
                            f"{profile}": {},
                        }
                    
                    jar = self.config_obj[profile]["jar_file"]
                    try:
                        node_tess_version = self.pull_from_jar(jar)            
                    except Exception as e:
                        self.log.logger.error(f"attempting to pull node version from jar failed with [{e}]")
                        node_tess_version = "v0.0.0"

                    if not "v" in version.lower():
                        version = f"v{version}"
                    if not "v" in node_tess_version.lower():
                        node_tess_version = f"v{node_tess_version}"
                                                
                    env_version_obj[profile]["cluster_tess_version"] = version
                    env_version_obj[profile]["cluster_metagraph_version"] = metagraph_version
                    env_version_obj[profile]["node_tess_version"] = node_tess_version
                    env_version_obj[profile]["node_tess_jar"] = jar
                    
                    if not last_environment or last_environment != self.config_obj[profile]["environment"]:
                        try:
                            version_obj["upgrade_path"] = upgrade_path["path"]
                            version_obj[environment]["nodectl"]["latest_nodectl_version"] = upgrade_path[environment]["version"]
                            version_obj[environment]["nodectl"]["current_stable"] = upgrade_path[environment]["current_stable"]
                            version_obj[environment]["nodectl"]["nodectl_prerelease"] = upgrade_path["nodectl_pre_release"]
                            version_obj[environment]["nodectl"]["nodectl_remote_config"] = upgrade_path["nodectl_config"]
                            version_obj[environment]["nodectl"]["upgrade"] = upgrade_path[environment]["upgrade"]
                            version_obj[environment]["remote_yaml_version"] = upgrade_path["nodectl_config"]
                        except Exception as e:
                            self.log.logger.error(f"versioning --> building object issue encountered | [{e}]")
                            self.functions.event = False
                            if self.called_cmd != "uvos":
                                self.print_error("ver-278","invalid_file_format","sudo nodectl update_version_object")
                            return

                        
                        try: del version_obj[environment]["nodectl"]["version"]
                        except: pass

                    up_to_date = [
                        ["nodectl_uptodate", self.version_obj["node_nodectl_version"], self.upgrade_path[environment]["current_stable"],"nodectl version"],
                        ["nodectl_yaml_uptodate", self.version_obj["node_nodectl_yaml_version"],upgrade_path["nodectl_config"],"nodectl yaml version"],
                        ["tess_uptodate", node_tess_version, version,"tessellation version"],
                    ]
                    for versions in up_to_date:
                        test = self.functions.is_new_version(versions[1],versions[2],"versioning module",versions[3])
                        if not test: test = True
                        if versions[0] == "nodectl_uptodate": version_obj[environment]["nodectl"]["nodectl_uptodate"] = test
                        else: env_version_obj[profile][f"{versions[0]}"] = test

                    version_obj[environment] = {
                        **version_obj[environment],
                        **env_version_obj,
                    }
                    
                    last_environment = environment
                    
                if "install" in self.request: break

            self.version_obj = {**self.version_obj, **version_obj}
            self.version_obj["last_updated"] = self.date_time
            self.version_obj["next_updated"] = self.next_time
            self.version_obj["upgrade_path"] = self.upgrade_path["path"]
            
            self.write_file()
            
            sleep(.8) # allow system time to catch up              
            self.functions.event = False
            

    def pull_upgrade_path(self):
        do_update = False
        if self.new_creation or self.force: do_update = True
        else: 
            do_update = self.functions.get_date_time({
                "action": "difference",
                "time_part": "day",
                "old_time": self.old_version_obj["last_updated"],
                "new_time": self.old_version_obj["next_updated"]
            })
    
        if do_update or self.force:
            try:
                session = self.functions.set_request_session()
                upgrade_path = session.get(self.upgrade_path_path, timeout=self.session_timeout)
            except:
                # only trying once (not that important)
                
                self.log.logger.error("unable to pull upgrade path from nodectl repo, if the upgrade path is incorrect, nodectl may upgrade incorrectly.")
                if self.print_messages:
                    self.functions.print_paragraphs([
                        ["",1], ["Unable to determine upgrade path.  Please make sure you adhere to the proper upgrade path before",0,"red"],
                        ["continuing this upgrade; otherwise, you may experience unexpected results.",2,"red"],
                    ])
                self.upgrade_path = False
                return
            finally:
                session.close()

            upgrade_path =  upgrade_path.content.decode("utf-8").replace("\n","").replace(" ","")
            try:
                self.upgrade_path = eval(upgrade_path)
            except Exception as e:
                self.log.logger.critical(f"versioning --> upgrade_path uri returned invalid data [{e}]")
                self.error_messages.error_code_messages({
                    "error_code": "ver_327",
                    "line_code": "possible404",
                    "extra": e,
                    "extra2": self.upgrade_path_path,
                })
            self.upgrade_path["nodectl_pre_release"] = self.is_nodectl_pre_release()
        else:
            self.upgrade_path = {
                "path": self.old_version_obj["upgrade_path"],
            }
            for environment in self.functions.environment_names:
                self.upgrade_path = {
                    **self.upgrade_path,
                    "nodectl_config": self.old_version_obj[environment]["nodectl"]["nodectl_remote_config"],
                    "nodectl_pre_release": self.old_version_obj[environment]["nodectl"]["nodectl_prerelease"],
                    "remote_yaml_version": self.old_version_obj[environment]["nodectl"]["nodectl_remote_config"],
                    f"{environment}": {
                        "version": self.old_version_obj[environment]["nodectl"]["latest_nodectl_version"],
                        "current_stable": self.old_version_obj[environment]["nodectl"]["current_stable"],
                        "upgrade": self.old_version_obj[environment]["nodectl"]["upgrade"]
                    }
                }

                        
    def is_nodectl_pre_release(self):
        p_version = self.upgrade_path[self.functions.environment_names[0]]["version"]
        pre_release_uri = f"https://api.github.com/repos/stardustCollective/nodectl/releases/tags/{p_version}"
        pre_release = {"prerelease":"Unknown"}

        try:
            session = self.functions.set_request_session()
            pre_release = session.get(pre_release_uri, timeout=self.session_timeout).json()
        except Exception as e:
            self.log.logger.warn(f"unable to reach api to check for pre-release uri [{pre_release_uri}] | exception [{e}]")
        else:
            try:
                if "API rate limit" in pre_release["message"]:
                    self.log.logger.warn(f"function - pull_upgrade_path - unable to determine if pre-release | [{pre_release['message']}]")
                    pre_release["prerelease"] = "Unknown"
            except: pass
        finally:
            session.close()
            
        try:
            return pre_release["prerelease"] # this will be true or false
        except:
            return "Unknown"  

    def write_file(self):
        if not path.exists(self.version_obj_path):
            mkdir(self.version_obj_path)
        with open(self.version_obj_file, 'w') as file:
            json.dump(self.version_obj,file,indent=4)
            
    
    def print_error(self,ver,code,hint=None):
        self.error_messages.error_code_messages({
            "error_code": ver,
            "line_code": code,
            "extra": self.version_obj_file,
            "hint": hint,
        })
        
         
    def verify_version_object(self):
        error_found = False
        if self.new_creation: return # nothing to verify
        
        root_keys = [
            "node_nodectl_version","node_nodectl_yaml_version","nodectl_github_version",
            "upgrade_path","last_updated","next_updated",
            "node_upgrade_path_yaml_version","remote_yaml_version",
        ]    
        nodectl_keys = [
            "latest_nodectl_version","nodectl_prerelease","nodectl_remote_config",
            "upgrade","nodectl_uptodate"
        ]
        tess_keys = [
            "cluster_tess_version","cluster_metagraph_version","node_tess_version","node_tess_jar","tess_uptodate"           
        ]    
            
        self.functions.version_obj = self.old_version_obj
        self.functions.set_statics()
        
        for environment in self.functions.environment_names:
            for key_name in nodectl_keys:
                root_keys.append(f"{environment}.nodectl.{key_name}")
                    
            for profile in self.functions.profile_names:
                for key_name in tess_keys:
                    root_keys.append(f"{environment}.{profile}.{key_name}")
        
        def recursive_verification(version_obj_verify,verify_keys):
            missing_keys = []

            for key in verify_keys:
                keys = key.split('.')
                current_dict = version_obj_verify

                # Traverse the dictionary hierarchy
                for sub_key in keys:
                    if sub_key in current_dict:
                        current_dict = current_dict[sub_key]
                    else:
                        missing_keys.append(key)
                        break

            return missing_keys

        missing_keys = recursive_verification(self.old_version_obj,root_keys)
        
        if len(missing_keys) > 0:
            error_msg = "versioning --> verification obj (json) failed"
            if not self.verify_only: error_msg += ", forcing rebuild of version object file."
            self.log.logger.error(error_msg)
            error_found = True
            self.force = True
            self.new_creation = True

        if (self.verify_only or self.print_object) and self.print_messages:
            if self.verify_only:
                result, color = "verified OK", "green"
                if error_found: 
                    self.log.logger.error(f"versioning -> found missing | [{missing_keys}]")
                    self.log.logger.error("versioning -> note: if there were [cn-config.yaml] changes, missing keys may be inaccurate, please force or update with the [-f] flag and then rerun the version updater.")
                    result, color = "verified INVALID (check logs)","red"
                
                self.functions.print_paragraphs([
                    ["",1],[" VERSION OBJECT ",1,"green,on_grey"],
                    ["verification status:",0], [result,1,color,"bold"]
                ])
            if self.print_object:
                self.functions.print_paragraphs([
                    ["",1],[" Node Version Object Elements ",2,"green,on_grey"],
                ])
                print(json.dumps(self.functions.version_obj,indent=4))
                print("")
            exit(0)
            



        
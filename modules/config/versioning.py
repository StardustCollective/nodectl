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
        
        nodectl_version = "v2.12.4"
        nodectl_yaml_version = "v2.1.0"
        self.upgrade_path_path = f"https://raw.githubusercontent.com/stardustCollective/nodectl/{nodectl_version}/admin/upgrade_path.json"
        
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
        if self.called_cmd == "auto_restart" or self.called_cmd == "service_restart":
            self.auto_restart = True
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
        
        self.nodectl_static_versions = {
            "node_nodectl_version": nodectl_version,
            "node_nodectl_yaml_version": nodectl_yaml_version,            
        }
        self.version_obj = copy(self.nodectl_static_versions)
        self.version_obj["nodectl_github_version"] = f'nodectl_{self.version_obj["node_nodectl_version"].replace(".","")}'
        self.version_obj_path = "/var/tessellation/nodectl/"
        self.version_obj_file = f"{self.version_obj_path}version_obj.json"

        init_only = ["verify_nodectl","_vn","-vn"]
        if self.called_cmd in init_only: return
        
        self.execute_versioning()
        
        
    def execute_versioning(self):
        self.log.logger.debug(f"versioning - called [{self.logging_name}] - executing versioning update request.")
        if self.called_cmd == "show_version": return # nodectl only
        if self.called_cmd == "upgrade": self.force = True

        self.functions = Functions(self.config_obj)
        self.error_messages = Error_codes(self.functions) 
        self.functions.log = self.log # avoid embedded circular reference errors

        if self.auto_restart: return  # relies on service updater
                        
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
            self.print_error()
        
        self.verify_version_object()
        if self.new_creation:
            self.log.logger.debug(f"versioning - called by [{self.logging_name}] - new versioning json object file creation.")
            self.write_version_obj_file()
        else:
            elapsed = self.functions.get_date_time({
                "action": "get_elapsed",
                "old_time": version_obj["last_updated"],
            })
            if (self.force or elapsed.seconds > self.seconds) and not self.auto_restart:
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
                "spinner": False,
                "print_output": False,
                "profile": self.functions.default_profile,
                "simple": True                
            }
            self.log.logger.debug(f"versioning - version test obj | [{test_obj}]")
            state = self.functions.test_peer_state(test_obj)
            
            if state == "ApiNotReady" and self.called_cmd == "uvos": 
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
           
            for environment in self.functions.environment_names:
                for profile in self.functions.profile_names:
                    upgrade_path = deepcopy(self.upgrade_path)
                    if self.config_obj[profile]["environment"] != environment: continue
                    if self.request == "runtime":
                        api_host = self.config_obj[profile]["edge_point"]
                        api_port = self.config_obj[profile]["edge_point_tcp_port"]
                    else:
                        api_host = self.functions.lb_urls[self.functions.environment_name][0]
                        api_port = self.functions.lb_urls[self.functions.environment_name][1]
                        
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
                                "info_list": ["version"],
                                "tolerance": 2,
                            })[0]
                        except:
                            version = "v0.0.0"
                    
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
                    env_version_obj[profile]["node_tess_version"] = node_tess_version
                    env_version_obj[profile]["node_tess_jar"] = jar
                    
                    if not last_environment or last_environment != self.config_obj[profile]["environment"]:
                        version_obj["upgrade_path"] = upgrade_path["path"]
                        version_obj[environment]["nodectl"]["latest_nodectl_version"] = upgrade_path[environment]["version"]
                        version_obj[environment]["nodectl"]["nodectl_prerelease"] = upgrade_path["nodectl_pre_release"]
                        version_obj[environment]["nodectl"]["nodectl_remote_config"] = upgrade_path["nodectl_config"]
                        version_obj[environment]["nodectl"]["upgrade"] = upgrade_path[environment]["upgrade"]
                        
                        try: del version_obj[environment]["nodectl"]["version"]
                        except: pass

                    up_to_date = [
                        ["nodectl_uptodate", self.version_obj["node_nodectl_version"], self.upgrade_path[environment]["version"]],
                        ["tess_uptodate", node_tess_version, version]
                    ]
                    for versions in up_to_date:
                        test = self.functions.is_new_version(versions[1],versions[2])
                        if not test: test = True
                        if versions[0] == "nodectl_uptodate": version_obj[environment]["nodectl"]["nodectl_uptodate"] = test
                        else: env_version_obj[profile][f"{versions[0]}"] = test

                    version_obj[environment] = {
                        **version_obj[environment],
                        **env_version_obj,
                    }
                    
                    last_environment = environment
                    
                if self.request == "install": break

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
                upgrade_path = session.get(self.upgrade_path_path)
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
            self.upgrade_path = eval(upgrade_path)
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
                    f"{environment}": {
                        "version": self.old_version_obj[environment]["nodectl"]["latest_nodectl_version"],
                        "upgrade": self.old_version_obj[environment]["nodectl"]["upgrade"]
                    }
                }

                        
    def is_nodectl_pre_release(self):
        p_version = self.upgrade_path[self.functions.environment_names[0]]["version"]
        pre_release_uri = f"https://api.github.com/repos/stardustCollective/nodectl/releases/tags/{p_version}"
        pre_success = True

        try:
            session = self.functions.set_request_session()
            pre_release = session.get(pre_release_uri).json()
            # pre_release = {"prerelease": True} # debug
        except Exception as e:
            self.log.logger.warn(f"unable to reach api to check for pre-release uri [{pre_release_uri}] | exception [{e}]")
            pre_success = False
        else:
            try:
                if "API rate limit" in pre_release["message"]:
                    self.log.logger.warn(f"function - pull_upgrade_path - unable to determine if pre-release | [{pre_release['message']}]")
                    pre_release["prerelease"] = "Unknown"
            except: pass
        finally:
            session.close()
            
        if not pre_success: pre_release["prerelease"] = "Unknown"
        return pre_release["prerelease"]  # this will be true or false

    
    def write_file(self):
        if not path.exists(self.version_obj_path):
            mkdir(self.version_obj_path)
        with open(self.version_obj_file, 'w') as file:
            json.dump(self.version_obj,file,indent=4)
            
    
    def print_error(self):
        self.error_messages.error_code_messages({
            "error_code": "ver-83",
            "line_code": "invalid_file_format",
            "extra": self.version_obj_file,
        })         
        
         
    def verify_version_object(self):
        error_found = False
        if self.new_creation: return # nothing to verify
        
        root_keys = [
            "node_nodectl_version","node_nodectl_yaml_version","nodectl_github_version",
            "upgrade_path","last_updated","next_updated",
        ]    
        nodectl_keys = [
            "latest_nodectl_version","nodectl_prerelease","nodectl_remote_config",
            "upgrade","nodectl_uptodate"
        ]
        tess_keys = [
            "cluster_tess_version","node_tess_version","node_tess_jar","tess_uptodate"           
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
            



        
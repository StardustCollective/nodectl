import json

from time import sleep
from os import path, mkdir, chmod

from sys import exit
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

from ..functions import Functions
from ..troubleshoot.logger import Logging
from ..troubleshoot.errors import Error_codes
from ..submodules.version_service import VersionService

class Versioning():

    def __init__(self,command_obj):
        
        self.command_obj = command_obj
        self.parent_setter = command_obj["setter"]
        self.parent_getter = command_obj["getter"]
        
        self.configurator = False # special case
        
            
    def _set_nodectl_versioning(self):
        # important
        # migration -> verify_config_type -> simple verification value counters
        #                                    may need to be adjusted if new key/pair 
        #                                    was introduced.  The value should remain
        #                                    at the last required migration upgrade_path
        
        self.nodectl_version = "v2.19.0"
        # self.nodectl_version = self.functions.nodectl_version
        self.nodectl_yaml_version = "v2.1.1"
        self.nodectl_github_version = self.nodectl_version.replace(".","")

        # self.version_obj["nodectl_github_version"] = f'nodectl_{self.version_obj["node_nodectl_version"].replace(".","")}'
        self.version_obj_path = "/var/tessellation/nodectl/"
        self.version_obj_file = f"{self.version_obj_path}version_obj.json"
        self.node_upgrade_path_yaml_version = "v2.1.0" # if previous is 'current_less'; upgrade path needed (for migration module)

        self.upgrade_path_path = f'https://raw.githubusercontent.com/stardustCollective/nodectl/nodectl_{self.nodectl_version.replace(".","")}/admin/upgrade_path.json'
        self.spec_path = f'https://raw.githubusercontent.com/stardustCollective/nodectl/main/admin/specs.json'
        # self.upgrade_path_path = f'https://raw.githubusercontent.com/StardustCollective/nodectl/main/admin/upgrade_path.json'
        
                
    def set_parameters(self):
        self._set_log_obj()
        
        self.called_cmd = self.command_obj.get("called_cmd","default")
        self.auto_restart = False

        self._set_nodectl_versioning()
        self.set_init_version_obj()
        
        self.print_messages = self.command_obj.get("print_messages",True)
        self.primary_command = self.command_obj.get("primary_command",False)
        self.show_spinner = self.command_obj.get("show_spinner",True)
        self.request = self.command_obj.get("request","runtime")  # runtime, install 
        self.force = self.command_obj.get("force",False)
        self.verify_only = self.command_obj.get("verify_only",False)
        self.print_object = self.command_obj.get("print_object",False)
        self.skip_p12_details = self.command_obj.get("skip_p12_details",False)
        self.seconds = self.command_obj.get("seconds",60*10)
        self.service_uvos = False
    
        self.profile_states = {}
        
        self.functions = self.parent_getter("functions")
        if self.configurator:
            # configurator
            self.functions = self.parent_getter("c")
            self.functions = self.functions.functions
            
        self._set_version_service()        
        self.set_version_timers()


    def set_self_value(self, name, value):
        setattr(self, name, value)
        
        
    def _set_version_service(self):
        self.command_obj["setter"] = self.set_self_value
        self.command_obj["getter"] = self.get_self_value
        
        self.version_service = VersionService(self.command_obj)        
        self.version_service.set_parameters()
    
    
    def set_init_version_obj(self):
        self.version_obj = {
            "node_nodectl_version": self.nodectl_version,
            "node_nodectl_yaml_version": self.nodectl_yaml_version,  
            "node_upgrade_path_yaml_version": self.node_upgrade_path_yaml_version, 
            "nodectl_github_version": self.nodectl_github_version,   
        }
        
    
    def _set_log_obj(self):
        self.log = Logging("version",None)    
        self.log_key = "version"
        self.log = self.log.logger[self.log_key]
    
    
    def build_full_version_obj(self):
        # called from cn_requests
        self.version_service.write_distro_details()
        self.version_service.get_cached_version()    
    
        self.new_creation = self.version_service.get_self_value("new_creation")
        self.new_version_obj = self.version_service.get_self_value("version_obj") # new because upaded with this nodectl version
        self.version_obj = {
            **self.new_version_obj,
            **self.version_obj, # write new static versions over
        }
        
    
    def get_self_value(self, name, default=False):
        return getattr(self, name, default)
    
    
    def pull_version_from_jar(self,jar_path):
        self._print_log_msg("debug",f"called by [{self.called_cmd}] - pulling tessellation version for jar file [{jar_path}].")
        bashCommand = f"/usr/bin/java -jar {jar_path} --version"
        node_tess_version = self.functions.process_command({
            "bashCommand": bashCommand,
            "proc_action": "wait"
        })
        try: node_tess_version = node_tess_version.strip("\n")
        except: node_tess_version = "v0.0.0"
        if node_tess_version == "v" or node_tess_version == "" or node_tess_version == None:
            node_tess_version = "v0.0.0"
        return node_tess_version    

            
    def build_objs(self):
        self.functions = Functions()
        self.functions.set_parameters()
        
        try:
            self.functions.set_self_value("config_obj",self.functions.config_obj)
        except:
            self.functions.set_self_value("config_obj",self.cn_requests["config_obj"])
            
        self.functions.set_self_value("logs",self.log)
        self.error_messages = Error_codes(self.functions) 
        return


    def execute_versioning(self):
        print("This is not used anymore")
        exit(0)
    #     self._print_log_msg("debug",f"called [{self.called_cmd}] - executing versioning update request.")
    #     if self.called_cmd == "show_version": return # nodectl only
    #     if self.called_cmd in ["upgrade","install","quick_install"]: self.force = True

    #     self.build_objs()
    #     self.functions.log = self.log # avoid embedded circular reference errors

    #     if self.auto_restart and not self.service_uvos: 
    #         return  # relies on service updater
                        
    #     self.get_cached_version_obj()
        
    #     if self.update_required:
    #         self._print_log_msg("info",f"called by [{self.called_cmd}] - updating versioning object")
    #     else:
    #         msg = f"localhost versioning object under {str(int(self.seconds/60))} minutes old."
    #         self._print_log_msg("info",f"called by [{self.called_cmd}] - {msg}")
            

    def get_version_obj(self):
        self._print_log_msg("debug",f"called by [{self.called_cmd}] - request for version_obj made.")
        return self.version_obj
    
    
    def set_version_timers(self):
        self.date_time = self.functions.get_date_time({"action": "datetime"})
        self.next_time = self.functions.get_date_time({
            "action": "future_datetime", 
            "elapsed": self.version_service.static_seconds,
        })
        
                
    def get_cached_version_obj(self):
        self._print_log_msg("debug",f"called by [{self.called_cmd}] - initiating cached version object check and request.")
                
        self.date_time = self.functions.get_date_time({"action": "datetime"})
        self.next_time = self.functions.get_date_time({
            "action": "future_datetime", 
            "elapsed": self.version_service.static_seconds,
        })
        
        try:
            with open(self.version_obj_file, 'r') as file:
                version_obj = json.load(file)
                self.old_version_obj = deepcopy(version_obj)
        except FileNotFoundError:
            self._print_log_msg("info",f"File [{self.version_obj_file}] not found, creating...")
            self.new_creation = True
        except json.JSONDecodeError:
            self._print_log_msg("error",f"Versioning Failed to decode JSON in [{self.version_obj_file}].")
            if self.called_cmd != "uvos":
                self.print_error("ver-126","invalid_file_format")
        
        if self.new_creation:
            self._print_log_msg("debug",f"called by [{self.called_cmd}] - new versioning json object file creation.")
            self.write_version_obj_file()
        else:
            try:
                elapsed = self.functions.get_date_time({
                    "action": "get_elapsed",
                    "old_time": version_obj["last_updated"],
                })
            except:
                elapsed = {"seconds": -1}
                elapsed = SimpleNamespace(**elapsed)
            if (self.force or elapsed.seconds > self.seconds) and (not self.auto_restart or self.service_uvos) and self.called_cmd != "migrator":
                self._print_log_msg("debug",f"called by [{self.called_cmd}] - out of date - updating.")
                self.write_version_obj_file()
            else:
                self._print_log_msg("debug",f"called by [{self.called_cmd}] - up to date - no action taken.")

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

        if self.force: # if forced verify object after new write
            self.verify_version_object()
        self.force = False # do not leave forced on


    def pull_p12_details(self):
        if self.skip_p12_details:
            return
        
        try:
            from ..command_line import CLI

            self._print_log_msg("debug",f"called by [{self.called_cmd}] - pulling nodeid from p12 file.")
            nodeids = {}

            p12_command_obj = {
                "auto_restart": True,
                "command": "versioning",
                "ip_address": "127.0.0.1",
                "skip_services": True,
                "auto_restart": True, # avoid threading
                "functions": self.functions
            }   
            self.cli = CLI(self.log)
            self.cli.set_parameters(p12_command_obj)
            self.cli.functions.set_default_directories()
            self.functions.set_default_variables({
                "profiles_only": True,
            })
            for profile in self.functions.profile_names:
                self.cli.cli_grab_id({
                    "command": "versioning",
                    "dag_addr_only": True,
                    "threading": False,
                    "profile": profile,
                })
                nodeids[profile] = self.cli.nodeid.strip("\n")

            with open(f"{self.functions.nodectl_path}/cn-nodeid.json","w") as dfile:
                json.dump(nodeids, dfile, indent=4)
            chmod(f"{self.functions.nodectl_path}/cn-nodeid.json",0o600)
        except Exception as e:
            self._print_log_msg("error",f"attempting to pull node id from p12 failed with [{e}]")

        self._print_log_msg("debug",f"called by [{self.called_cmd}] - found nodeids [{nodeids}]")


    def pull_version_from_jar(self,jar_path):
        self._print_log_msg("debug",f"versioning - called by [{self.called_cmd}] - pulling tessellation version for jar file [{jar_path}].")
        bashCommand = f"/usr/bin/java -jar {jar_path} --version"
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
        # replaced with _set_version_obj_for_write (version service)
        self._print_log_msg("debug",f"called by [{self.called_cmd}] - write_version_obj_file initiated.")
        self.update_required = True
        self.pull_p12_details()            
        
        try:
            with ThreadPoolExecutor() as executor:
                # set default variables
                self.functions.version_obj = self.version_obj
                self.functions.set_statics()
                self.functions.set_default_variables({})
                if self.auto_restart: self.functions.auto_restart = True

                self._print_log_msg("debug",f"version test obj | [requesting state update]")
                state = self.profile_states[self.functions.profile_names[0]]
                if state == "ApiNotResponding" and self.called_cmd == "uvos": 
                    # after installation there should be a version obj already created
                    # no need to update file while node is not online.
                    self._print_log_msg("info",f"versioning service found [{self.functions.default_profile}] in state [{state}] exiting module.")
                    exit(0)                    
                        
                if self.show_spinner:  
                    self.functions.event = True
                    _ = executor.submit(self.functions.print_spinner,{
                        "msg": "Gathering Tessellation version info",
                        "color": "magenta",
                        "timeout": 15,
                    }) 

                # get cluster Tessellation
                self._print_log_msg("debug",f"called by [{self.called_cmd}] - building new version object.")
            
                metagraph = False

                for environment in self.functions.environment_names:
                    for profile in self.functions.profile_names:

                        jar_dir = f"{self.functions.config_obj[profile]['jar_location']}{self.functions.config_obj[profile]['jar_file']}"
                        jar_dir = path.normpath(jar_dir)
                        self.new_version_obj[environment][profile]["node_tess_version"] = self.pull_version_from_jar(jar_dir) 
                                        
                        upgrade_path = deepcopy(self.upgrade_path)

                        if self.functions.config_obj[profile]["environment"] != environment: continue
                        if not self.functions.config_obj[profile]["profile_enable"]: continue

                        # migration only version by-pass
                        if self.functions.config_obj["global_elements"]["nodectl_yaml"] == self.nodectl_yaml_version: # migration only version by-pass
                            if self.functions.config_obj["global_elements"]["metagraph_name"] != "hypergraph":
                                metagraph = True
                            
                        if metagraph:
                            metagraph_version = version[0]
                            if not metagraph_version.startswith("v"): 
                                metagraph_version = f"v{metagraph_version}"
                            try:
                                test = self.functions.lb_urls[self.functions.config_obj[profile]["environment"]][0]
                                get_node_info_from_cluster = self.parent_getter("get_node_info_from_cluster")
                                version = get_node_info_from_cluster({
                                    "ip": self.functions.lb_urls[self.functions.config_obj[profile]["environment"]][0],
                                    "publicPort": self.functions.lb_urls[self.functions.config_obj[profile]["environment"]][1],
                                    "end_point": "node/info",
                                    "profile": profile,
                                    "info_list": ["version"],
                                })
                            except:
                                version = "v0.0.0"
                            else:
                                metagraph_version = version[0]
                        else:
                            metagraph_version = None
                        
                        self.new_version_obj[environment][profile]["cluster_metagraph_version"] = metagraph_version
                        
                        version_type = "versioning_module"
                        if environment == "testnet": 
                            version_type = "versioning_module_testnet" # exception
                        up_to_date = [
                            ["nodectl_uptodate", self.new_version_obj["node_nodectl_version"], self.upgrade_path[environment]["current_stable"],"nodectl version"],
                            ["nodectl_yaml_uptodate", self.new_version_obj["node_nodectl_yaml_version"],upgrade_path["nodectl_config"],"nodectl yaml version"],
                            ["tess_uptodate", self.new_version_obj[environment][profile]['node_tess_version'], self.new_version_obj[environment][profile]['cluster_tess_version'], version_type],
                            
                        ]
                        for versions in up_to_date:
                            if versions[0] == "tess_uptodate":
                                pass
                            test = self.functions.is_new_version(versions[1],versions[2],"tessellation/nodectl versioning",versions[3])
                            if not test: 
                                test = True
                            if versions[0] == "nodectl_uptodate":
                                self.new_version_obj[environment]["nodectl"]["nodectl_uptodate"] = test
                            if test == "error":
                                if self.service_uvos: 
                                    self._print_log_msg("error","uvos -> unable to determine versioning, stopping service updater, versioning object not updated.")
                                    exit(1)
                                self._print_log_msg("error","unable to determine versioning, skipping service updater.")
                                return 
                            else: 
                                self.new_version_obj[environment][profile][f"{versions[0]}"] = test

                    if "install" in self.request: break

                self.new_version_obj["last_updated"] = self.date_time
                self.new_version_obj["next_updated"] = self.next_time
                self.new_version_obj["upgrade_path"] = self.upgrade_path["path"]

                self.write_file()
                
                sleep(.8) # allow system time to catch up  
                self.functions.cancel_event = True            
                self.functions.event = False
        except Exception as e:
            self.version_service.print_error("ver-391","api_error","N/A","Please verify the cluster is up and try again later.","None")


    def is_nodectl_pre_release(self):
        p_version = self.upgrade_path[self.functions.environment_names[0]]["version"]
        pre_release_uri = f"https://api.github.com/repos/stardustCollective/nodectl/releases/tags/{p_version}"
        pre_release = {"prerelease":"Unknown"}


        self._print_log_msg("debug",f"is_nodectl_pre_release --> get request --> posting to [{pre_release_uri}].")
        try:
            session = self.functions.set_request_session()
            s_timeout = (5, 3)
            pre_release = session.get(pre_release_uri, timeout=s_timeout).json()
        except Exception as e:
            self._print_log_msg("info",f"unable to reach api to check for pre-release uri [{pre_release_uri}] | exception [{e}]")
        else:
            try:
                if "API rate limit" in pre_release["message"]:
                    self._print_log_msg("info",f"is_nodectl_pre_release - pull_upgrade_path - unable to determine if pre-release | [{pre_release['message']}]")
                    pre_release["prerelease"] = "Unknown"
            except: pass
            self._print_log_msg("debug",f"is_nodectl_pre_release - pull_upgrade_path - url | [{pre_release_uri}]")
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
            json.dump(self.new_version_obj,file,indent=4)
        chmod(self.version_obj_file,0o600)
            
    

        
         



    def _print_log_msg(self, log_type, msg):
            log_method = getattr(self.log, log_type, None)
            log_method(f"{self.__class__.__name__} --> node_service -> {msg}")    
            
            
if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")   
        
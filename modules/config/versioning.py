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

    def __init__(self, command_obj):
        
        self.command_obj = command_obj
        self.parent_setter = command_obj["setter"]
        self.parent_getter = command_obj["getter"]
        
        self.configurator = False # special case
        
    # ==== SETTERS ====
                
    def _set_nodectl_versioning(self):
        # important
        # migration -> verify_config_type -> simple verification value counters
        #                                    may need to be adjusted if new key/pair 
        #                                    was introduced.  The value should remain
        #                                    at the last required migration upgrade_path
        
        self.nodectl_version = "v2.19.0"
        self.nodectl_yaml_version = "v2.1.1"
        self.nodectl_github_version = f'nodectl_{self.nodectl_version.replace(".","")}'

        self.version_obj_path = "/var/tessellation/nodectl/"
        self.version_obj_file = f"{self.version_obj_path}version_obj.json"
        self.node_upgrade_path_yaml_version = "v2.1.0" # if previous is 'current_less'; upgrade path needed (for migration module)

        self.upgrade_path_path = f'https://raw.githubusercontent.com/stardustCollective/nodectl/nodectl_{self.nodectl_version.replace(".","")}/admin/upgrade_path.json'
        self.spec_path = f'https://raw.githubusercontent.com/stardustCollective/nodectl/main/admin/specs.json'


    def set_parameters(self):
        self._set_log_obj()
        
        self.called_cmd = self.command_obj.get("called_cmd","default")
        self.auto_restart = False

        self._set_nodectl_versioning()
        # self._set_force(argv_list)
        self.set_init_version_obj()

        self.print_messages = self.command_obj.get("print_messages",True)
        self.primary_command = self.command_obj.get("primary_command",False)
        self.show_spinner = self.command_obj.get("show_spinner",True)
        self.request = self.command_obj.get("request","runtime")  # runtime, install 
        self.verify_only = self.command_obj.get("verify_only",False)
        self.print_object = self.command_obj.get("print_object",False)
        self.skip_p12_details = self.command_obj.get("skip_p12_details",False)
        self.seconds = self.command_obj.get("seconds",60*10)
        
        self.version_file_exists = True
        self.cn_requests =False
        self.service_uvos = False
    
        self.profile_states = {}
        
        self.functions = self.parent_getter("functions")
        if self.configurator:
            # configurator
            self.functions = self.parent_getter("c")
            self.functions = self.functions.functions
            
        self._set_version_service()        
        self.version_service.set_version_timers()


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
    
    
    def set_full_version_obj(self):
        # called from cn_requests
        self.version_service.get_cached_version()    
    
        self.new_version_obj_needed = self.version_service.get_self_value("new_version_obj_needed")
        self.new_version_obj = self.version_service.get_self_value("version_obj") # new because upaded with this nodectl version
        if not self.new_version_obj:
            self.new_version_obj = {} # create
        if not self.version_obj:
            self.version_obj = {} # create
        self.version_obj = {
            **self.new_version_obj,
            **self.version_obj, # write new static versions over
        } 
        

    def set_objs(self):
        # not used - placeholder clean up later
        self.functions = Functions()
        self.functions.set_parameters()
        
        try:
            self.functions.set_self_value("config_obj",self.functions.config_obj)
        except:
            self.functions.set_self_value("config_obj",self.cn_requests["config_obj"])
            
        self.functions.set_self_value("logs",self.log)
        self.error_messages = Error_codes(self.functions) 
        return      
    
         
    # ==== GETTERS ====
    
    def get_self_value(self, name, default=False):
        return getattr(self, name, default)
    
    
    def get_version_obj(self):
        self._print_log_msg("debug",f"called by [{self.called_cmd}] - request for version_obj made.")
        return self.version_obj


    def get_pre_release_status(self, environment):
        p_version = self.upgrade_path[environment]["version"]
        pre_release_uri = f"https://api.github.com/repos/stardustCollective/nodectl/releases/tags/{p_version}"
        pre_release = {"prerelease":"Unknown"}

        self._print_log_msg("debug",f"get_pre_release_status --> get request --> posting to [{pre_release_uri}].")
        try:
            pre_release = self.cn_requests.get_from_api(pre_release_uri,"json")
        except Exception as e:
            self._print_log_msg("error",f"unable to reach api to check for pre-release uri [{pre_release_uri}] | exception [{e}]")
            pre_release["prerelease"] = "Unknown"
            
        try:
            return pre_release["prerelease"] # this will be true or false
        except:
            return "Unknown"  
        
               
    # ==== INTERNALS ====
    
    def execute_versioning(self):
        print("This is not used anymore")
        exit(0)
        
    # ==== HANDLERS ====    

    
    # ==== PRINTERS ====    

    
    def print_version_obj_to_file(self):
        # replaced with _set_version_obj_for_write (version service)
        self._print_log_msg("debug",f"called by [{self.called_cmd}] - print_version_obj_to_file initiated.")
        self.update_required = True
        self.version_service.set_self_value("cn_requests",self.cn_requests)
        self.version_service.get_p12_details() 

        self.version_service.set_version_timers()           
        
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
                        
                        if not self.version_file_exists:
                            self.new_version_obj = self.cn_requests.config_obj['global_elements']['version_obj']
                        
                        self.new_version_obj[environment][profile]["node_tess_version"] = self.version_service.get_version_from_jar(jar_dir) 
                                        
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
                        self.new_version_obj[environment][profile]["node_tess_jar"] = self.functions.config_obj[profile]['jar_file']
                        
                        self.new_version_obj[environment]["remote_yaml_version"] = upgrade_path['nodectl_config']

                        self.new_version_obj[environment]["nodectl"]["upgrade"] = upgrade_path[environment]["upgrade"]
                        self.new_version_obj[environment]["nodectl"]["current_stable"] = upgrade_path[environment]['current_stable']
                        self.new_version_obj[environment]["nodectl"]["nodectl_remote_config"] = upgrade_path['nodectl_config']
                        self.new_version_obj[environment]["nodectl"]["nodectl_prerelease"] = f"{self.get_pre_release_status(environment)}"
                        
                        version_type = "versioning_module"
                        if environment == "testnet": 
                            version_type = "versioning_module_testnet" # exception
                        up_to_date = [
                            ["nodectl_uptodate", self.new_version_obj["node_nodectl_version"], upgrade_path[environment]["current_stable"],"nodectl version"],
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

                self.new_version_obj["last_updated"] = self.version_service.date_time
                self.new_version_obj["next_updated"] = self.version_service.next_time
                self.new_version_obj["upgrade_path"] = self.upgrade_path["path"]

                self._print_log_msg("debug",self.new_version_obj)
                self.version_service.set_self_value("new_version_obj",self.new_version_obj)

                self.version_service.print_to_file()
                
                sleep(.8) # allow system time to catch up  
                self.functions.cancel_event = True            
                self.functions.event = False
        except Exception as e:
            self._print_log_msg("error",f"something went wrong during the attempt to write out the new versioning object [{e}]")
            self.version_service.print_error("ver-391","api_error","N/A","Please verify the cluster is up and try again later.","None")


    def _print_log_msg(self, log_type, msg):
            log_method = getattr(self.log, log_type, None)
            log_method(f"{self.__class__.__name__} --> node_service -> {msg}")    
            
            
if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")   
        
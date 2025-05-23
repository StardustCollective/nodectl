import random
import psutil

from time import sleep, time
from datetime import datetime, timedelta
from os import path

from .node_service import Node
from .functions import Functions
from .command_line import CLI
from .config.versioning import Versioning

from .troubleshoot.errors import Error_codes
from .troubleshoot.logger import Logging
from .alerting import prepare_alert, prepare_report

class AutoRestart():

    def __init__(self,thread_profile,config_obj,first_thread):
        # THIS SERVICE IS THREADED TO RUN ALL PROFILES SEPARATELY
        self.log = Logging()
        self.log_key = "auto"
        
        self.config_obj = {
            **config_obj,
            "global_elements": {
                **config_obj["global_elements"],
                "caller":"auto_restart",
            },
        }

        self.debug = False # full debug - disable restart and join actions
        self.first_thread = first_thread # only want one thread to attempt auto_upgrade
        self.retry_tolerance = 50
        self.thread_profile = thread_profile  # initialize
        self.rapid_restart = self.config_obj["global_auto_restart"]["rapid_restart"] 
        self.thread_layer = self.config_obj[self.thread_profile]["layer"]
        self.cluster = self.config_obj[self.thread_profile]["environment"]
        self.alerting = {}
        
        self.alert_on_up = True
        
        self.link_types = ["ml0","gl0"]
        self.independent_profile = False
        self.on_boot_handler_check = True
        
        self.stuck_timers = {
            "Observing_tolerance": 5*60, 
            "Observing_enabled": False,
            "Observing_state_enabled": False,

            "SessionStarted_tolerance": 5*60, 
            "SessionStarted_enabled": False,
            "SessionStarted_state_enabled": False,

            "WaitingForDownload_tolerance": 5*60,
            "WaitingForDownload_state_enabled": False,
            "WaitingForDownload_enabled": False,    

            "WaitingForReady_tolerance": 5*60,
            "WaitingForReady_state_enabled": False,
            "WaitingForReady_enabled": False,    
        }

        self.persist_alert_file = f"/var/tessellation/nodectl/{self.thread_profile}_alert_report"

        self.fork_check_time = {
            "minority_fork": -1,
            "consensus_fork": -1,
        }
        self.fork_timer = 60*5 # 5 minutes
        

        
        self.log.logger[self.log_key].info(f"\n==================\nAUTO RESTART - {self.thread_profile} Thread - Initiated\n==================")
        
        self.build_class_objs()   
        self.set_timers()
        self.setup_profile_states()
        self.setup_alerting()
        self.restart_handler()
        
    
    def on_boot_handler(self):
        if not self.on_boot_handler_check: return
        if not self.first_thread: return
        
        while True:
            uptime_seconds = psutil.boot_time()
            uptime_seconds = datetime.now().timestamp() - uptime_seconds
            uptime_seconds = timedelta(seconds=uptime_seconds)
            uptime_seconds = int(uptime_seconds.total_seconds())
            if 60 <= uptime_seconds <= 70:
                self.log.logger[self.log_key].warning(f"auto_restart - on_boot_handler - thread [{self.thread_profile}] - restarting auto_restart service after 60 seconds to ensure stability")
                raise Exception("auto_restart forced stability restart")
            elif uptime_seconds < 60: 
                for n in range(0,10):
                    self.log.logger[self.log_key].debug(f"auto_restart - on_boot_handler - thread [{self.thread_profile}] - sleeping [{n}] of 10 seconds before next on_boot check")
                    sleep(1)  
            else: 
                self.on_boot_handler_check = False
                break

        self.log.logger[self.log_key].debug(f"auto_restart - on_boot_handler - thread [{self.thread_profile}] - uptime in seconds [{uptime_seconds}]")
        
                      
    # SETUP  
    def build_class_objs(self):
        self.log.logger[self.log_key].info(f"auto_restart - thread [{self.thread_profile}] -> build node services class obj")

        self.functions = Functions(self.config_obj) 
        self.functions.auto_restart = True
        
        # versioning update is handled by nodectl's versioning service
        # which checks for updates every 2 minutes
        self.log.logger[self.log_key].info("auto_restart -> build version class obj")  
        # first run make sure the full version is pulled in order
        # for other setup procedures to 
        self.versioning = Versioning({
            "config_obj": self.config_obj,
            "called_cmd": "auto_restart",
        })
        self.version_obj = self.versioning.execute_versioning()
        self.version_obj = self.versioning.get_cached_version_obj()

        self.functions.version_obj = self.version_obj
        self.functions.set_statics()
        self.error_messages = Error_codes(self.functions)        
        
        self.functions.set_default_variables({
            "profile": self.thread_profile,
        })
        
        self.stuck_in_state_list = self.functions.get_node_states("stuck_in_states",True) 
        self.pre_consensus_state_list = self.functions.get_node_states("pre_consensus",True)
        self.environment = self.functions.config_obj[self.thread_profile]["environment"]
        
        self.log.logger[self.log_key].info(f"auto_restart - thread [{self.thread_profile}] - starting node services...")
        command_obj = {
            "caller": "cli",
            "auto_restart": True,
            "functions": self.functions,
            "profile": self.thread_profile,
        }
        self.node_service = Node(command_obj)   
        self.node_service.profile_names = [self.thread_profile]
        self.log.logger[self.log_key].debug("auto_restart -> start_node_service completed successfully.") 
        self.ip_address = self.functions.get_ext_ip()
        
        self.seed_file_version = self.functions.config_obj[self.thread_profile]["seed_version"]
        
        self.clean_up_thread_profiles()
        
        self.log.logger[self.log_key].info("auto_restart -> build command_line class obj")
        command_obj = {
            "auto_restart": True,
            "command": "None",
            "profile": self.thread_profile,  
            "command_list": [],
            "ip_address": self.ip_address,
            "skip_services": True,
            "profile_names": self.profile_names,
            "functions": self.functions
        }   
        self.cli = CLI(command_obj)
        self.cli.functions.set_default_directories()
        
        if not self.functions.config_obj["global_auto_restart"]["on_boot"]: 
            self.on_boot_handler_check = False
                
                            
    def set_ep(self):  
         # ep: def: edge_point
         self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] - setup ep - pulling ep details | profile [{self.node_service.profile}]")
         self.edge_device = self.functions.pull_edge_point(self.node_service.profile)
         self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] - setup ep - pulling ep details | remote [{self.edge_device}]")
        

    def set_timers(self):
        self.sleep_on_critical = 600
        self.silent_restart_timer = 30  
        self.join_pause_timer = 30
        
        if self.rapid_restart: 
            self.random_times = [120]
            self.timer = 120
            self.sleep_on_critical = 160
            
        else:
            self.random_times = []
            for n in range(210,340,10):
                self.random_times.append(n)
            
            self.sleep_times = []
            for n in range(240,360,10):
                self.sleep_times.append(n)
                
            random.seed(self.functions.get_uuid)
            self.timer = random.choice(self.sleep_times)     
              
               
    # PROFILE MANIPULATE
    def clean_up_thread_profiles(self):
        # This method will clean up all unnecessary profiles that are not
        # related to this service / thread
        self.profile_names = []
        profile_pairings = self.functions.pull_profile({
            "req": "pairing",
        })

        # merge pairing lists if first element is the same
        # indication that gl0 and ml0 are needed
        merge_list = []
        profile = None  # skip the first merge pair
        for merge_pairing in profile_pairings:
            if merge_pairing[0]["profile"] == "external": 
                continue
            if merge_pairing[0]["profile"] == profile:
                merge_list.append(merge_pairing[1])
            profile = merge_pairing[0]["profile"]


        complete = False
        for single_pairing in profile_pairings:
            for profile in single_pairing:
                self.profile_pairing = single_pairing
                if profile["profile"] == self.thread_profile:
                    self.profile_names = [single_pairing[-1]["profile"]]
                    self.profile_names.append(self.thread_profile)
                    complete = True
                    break
            if complete:
                break
            
        for merge_profile in merge_list: 
            self.profile_pairing.append(merge_profile)
            self.profile_names.append(merge_profile["profile"])

        if len(self.profile_names) < 1:
            # duplicate independent link
            self.profile_names = [self.thread_profile,self.thread_profile]


    def setup_profile_states(self):
        self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] -  setup profiles - initializing known profile sessions and state | all profile [{self.profile_names}]")
        self.profile_states = {}

        self.auto_upgrade, self.passphrase_warning = False, False
        if self.functions.config_obj["global_auto_restart"]["auto_upgrade"]: 
            if not self.functions.config_obj[self.thread_profile]["is_jar_static"]:
                self.auto_upgrade = True
            else:
                self.log.logger[self.log_key].warning(f"auto_restart - thread [{self.thread_profile}] - update profile states - [auto_upgrade] is [enabled] however, the jar repository is statically defined.  auto_upgrade will not be able to determine if an upgrade is needed, disabling feature [False].")
        if self.functions.config_obj["global_p12"]["passphrase"] == "None":
            self.passphrase_warning = True
            
        for profile in self.profile_names:
            if self.functions.config_obj[profile]["global_p12_cli_pass"]:
                self.passphrase_warning = True
            self.profile_states[profile] = {}
            self.profile_states[profile]["remote_session"] = None
            self.profile_states[profile]["local_session"] = None
            self.profile_states[profile]["node_state"] = None
            self.profile_states[profile]["match"] = None
            self.profile_states[profile]["ep_ready"] = None
            self.profile_states[profile]["action"] = None
            self.profile_states[profile]["gl0_link_profile"] = False
            self.profile_states[profile]["ml0_link_profile"] = False
            self.profile_states[profile]["gl0_link_ehost"] = False
            self.profile_states[profile]["gl0_link_eport"] = False
            self.profile_states[profile]["ml0_link_ehost"] = False
            self.profile_states[profile]["ml0_link_eport"] = False
            self.profile_states[profile]["minority_fork"] = False
            self.profile_states[profile]["consensus_fork"] = False
            self.profile_states[profile]["layer"] = int(self.functions.config_obj[profile]["layer"])
            
            for link_type in self.link_types:
                if self.functions.config_obj[profile][f"{link_type}_link_enable"]:
                    self.profile_states[profile][f"{link_type}_link_profile"] = 'external'
                    if self.functions.config_obj[profile][f"{link_type}_link_profile"] == "None":
                        self.profile_states[profile][f"{link_type}_link_ehost"] = self.functions.config_obj[profile][f"{link_type}_link_host"]
                        self.profile_states[profile][f"{link_type}_link_eport"] = self.functions.config_obj[profile][f"{link_type}_link_port"]
                    else:
                        self.profile_states[profile][f"{link_type}_link_profile"] =  self.functions.config_obj[profile][f"{link_type}_link_profile"]
                        
        if len(self.profile_states) < 2: self.independent_profile = True
    

    def setup_alerting(self):
        try: self.alerting = {**self.config_obj["global_elements"]["alerting"]}
        except: 
            self.alerting = {"enable": False}
        self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] - alerting module [{self.alerting['enable']}]")

        if not self.alerting["enable"]: return

        #validate alerting
        necessary_items = [
            "enable","gmail","token","send_method","recipients",
            "begin_alert_utc","end_alert_utc","report_hour_utc",
            "local_time_zone","report_currency","label"
        ]
        found_items = list(self.config_obj["global_elements"]["alerting"].keys())
        if set(necessary_items) != set(found_items):
            self.log.logger[self.log_key].error(f"auto_restart - thread [{self.thread_profile}] - invalid alerting configuration found alerting is [disabled]")
            self.alerting = {"enable": False}
            return

        try:
            if self.alerting["report_hour_utc"] == "disable":
                self.alerting["report_hour_utc"] = -1
            if self.alerting["begin_alert_utc"] == "disable" or self.alerting["end_alert_utc"] == "disable":
                self.alerting["begin_alert_utc"] = -1
                self.alerting["end_alert_utc"] = -1
        except:
            self.alerting = {"enable": False}
            self.log.logger[self.log_key].error(f"auto_restart - thread [{self.thread_profile}] - alerting module error in configuration - disabling alerting.")

        try:
            self.local_time_zone = self.alerting["local_time_zone"]
        except:
            self.local_time_zone = 'disable'
        

    def update_profile_states(self):
        self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] - update profile states | all profile [{self.profile_names}]")
        
        for profile in self.profile_states:
           self.node_service.set_profile(profile)
           self.set_ep()
           self.set_session_and_state()
           self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] -  update profile states | profile details [{self.profile_states[profile]}]")
                        
           # debugging
           self.log.logger[self.log_key].debug("=====================================================================================")
           self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] -  update profile states | requested by [{self.thread_profile}]")
           self.log.logger[self.log_key].debug("=====================================================================================")
           for key,value in self.profile_states[profile].items():
               self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] -  update profile states | profile [{profile}] {key} [{value}]")
           self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] -  update profile states | profile [{profile}] cluster version [{self.version_obj[self.environment][self.thread_profile]['cluster_tess_version']}]")
           self.log.logger[self.log_key].debug("=====================================================================================")
           
        self.node_service.set_profile(self.thread_profile)  ## return the node_service profile to the appropriate profile
                        

    def set_test_external_state(self,link_type):
        if link_type == "ep":
            attempts = 1
            while True:
                ep_status = self.functions.get_api_node_info({
                    "api_host": self.config_obj[self.thread_profile]["edge_point"],
                    "api_port": self.config_obj[self.thread_profile]["edge_point_tcp_port"],
                })
                if ep_status == "LB_Not_Ready":
                    attempts = self.wait_for_ep_looper("ep_wait_ext",attempts)
                else: 
                    return
                
        return self.functions.test_peer_state({
                    "test_address": self.profile_states[self.node_service.profile][f"{link_type}_link_ehost"],
                    "profile": self.node_service.profile,
                    "caller": "auto_restart",
                    "simple": True,
                    "print_output": False,
                    "skip_thread": True,
                    "threaded": False,
                    "spinner": False,
                })  


    def set_session_and_state(self):
        self.log.logger[self.log_key].info(f"auto restart - get session and state - updating profile [{self.node_service.profile}] state and session object with edge device [{self.edge_device}]") 
        
        self.functions.get_service_status()
        continue_checking = True
        # reset the stop_start monitor
        self.stop_or_start_failed = {
            "failed": False,
            "action": None
        }  

        attempts = 0
        # session fetch
        while True: # utilize looper until success
            try:
                self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] edge [{self.edge_device}]")
                self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] profile [{self.node_service.profile}]")
                session_list = self.functions.pull_node_sessions({
                    "edge_device": self.edge_device,
                    "profile": self.node_service.profile,
                    "caller": "auto_restart",
                    "key": "clusterSession"
                })
                if not session_list:
                    raise Exception("pull node sessions failed? Is Load Balancer up?")
            except Exception as e:
                self.log.logger[self.log_key].error(f"auto_restart - set_session_and_state - thread [{self.thread_profile}] error [{e}]")
                attempts = self.attempts_looper(attempts,"session retrieval",20,3,False)
            else:
                break
            
        self.log.logger[self.log_key].debug(f"auto_restart - set sessions - profile [{self.thread_profile}] | session_list | {session_list}")
        
        # default everything
        self.profile_states[self.node_service.profile]["match"] = True
        self.profile_states[self.node_service.profile]["ep_ready"] = True
        self.profile_states[self.node_service.profile]["action"] = None
        self.profile_states[self.node_service.profile]["remote_session"] = session_list["session0"]
        self.profile_states[self.node_service.profile]["local_session"] = session_list["session1"]
        self.profile_states[self.node_service.profile]["remote_node"] = session_list["node0"]
        self.profile_states[self.node_service.profile]["local_node"] = session_list["node1"]
        self.profile_states[self.node_service.profile]["node_state"] = session_list["state1"]
        self.profile_states[self.node_service.profile]["action"] = "NoActionNeeded"
        
        gl0_dependent_link = self.profile_states[self.node_service.profile]["gl0_link_profile"]
        ml0_dependent_link = self.profile_states[self.node_service.profile]["ml0_link_profile"]
    
        # check if LB is up first
        if session_list["session0"] == 0:
            self.profile_states[self.node_service.profile]["match"] = False
            self.profile_states[self.node_service.profile]["ep_ready"] = False
            self.profile_states[self.node_service.profile]["action"] = "ep_wait"
            self.profile_states[self.node_service.profile]["node_state"] = session_list["state1"]
            continue_checking = False
            
        if continue_checking:
            if gl0_dependent_link == "external":
                ext_state = self.set_test_external_state("gl0")
                if ext_state != "Ready":
                    self.log.logger[self.log_key].debug(f'auto_restart - set sessions - profile [{self.thread_profile}] | gl0 link not ready | state [{ext_state}] - Detected external link not local to node - setting layer0_wait flag')
                    self.profile_states[self.node_service.profile]["match"] = False
                    self.profile_states[self.node_service.profile]["ep_ready"] = True
                    self.profile_states[self.node_service.profile]["action"] = "layer0_wait"
                    self.profile_states[self.node_service.profile]["node_state"] = session_list["state1"]
                    continue_checking = False
            elif gl0_dependent_link and self.profile_states[gl0_dependent_link]["node_state"] != "Ready":
                self.log.logger[self.log_key].debug(f'auto_restart - set sessions - profile [{self.thread_profile}] | gl0 link not ready | state [{self.profile_states[gl0_dependent_link]["node_state"]}] - setting layer0_wait flag')
                self.profile_states[self.node_service.profile]["match"] = False
                self.profile_states[self.node_service.profile]["ep_ready"] = True
                self.profile_states[self.node_service.profile]["action"] = "layer0_wait"
                self.profile_states[self.node_service.profile]["node_state"] = session_list["state1"]
                continue_checking = False

            if self.profile_states[self.node_service.profile]["layer"] > 0:
                if ml0_dependent_link == "external":
                    ext_state = self.set_test_external_state("ml0")
                    if ext_state != "Ready":
                        self.log.logger[self.log_key].debug(f'auto_restart - set sessions - profile [{self.thread_profile}] | gl0 link not ready | state [{ext_state}] - Detected external link not local to node - setting layer0_wait flag')
                        self.profile_states[self.node_service.profile]["match"] = False
                        self.profile_states[self.node_service.profile]["ep_ready"] = True
                        self.profile_states[self.node_service.profile]["action"] = "layer1_wait"
                        self.profile_states[self.node_service.profile]["node_state"] = session_list["state1"]
                        continue_checking = False
                elif ml0_dependent_link and self.profile_states[ml0_dependent_link]["node_state"] != "Ready":
                    self.log.logger[self.log_key].debug(f'auto_restart - set sessions - profile [{self.thread_profile}] | ml0 link not ready | state [{self.profile_states[ml0_dependent_link]["node_state"]}] - setting layer1_wait flag')
                    self.profile_states[self.node_service.profile]["match"] = False
                    self.profile_states[self.node_service.profile]["ep_ready"] = True
                    self.profile_states[self.node_service.profile]["action"] = "layer1_wait"
                    self.profile_states[self.node_service.profile]["node_state"] = session_list["state1"]
                    continue_checking = False
        
        if continue_checking: # and min_fork_check: # check every 5 minutes
            for fork_type in ["minority_fork","consensus_fork"]:
                if self.fork_handler(fork_type):
                    self.profile_states[self.node_service.profile]["action"] = "restart_full"
                    continue_checking = False
                    break
            
        if continue_checking:                                        
            if session_list["session0"] > session_list["session1"] and session_list['session1'] > 0:
                self.profile_states[self.node_service.profile]["match"] = False
                self.profile_states[self.node_service.profile]["action"] = "restart_full"  
                
            elif session_list["state1"] in self.stuck_in_state_list:
                # Check for stuck Session
                state = session_list["state1"]
                self.profile_states[self.node_service.profile]["match"] = True
                self.profile_states[self.node_service.profile]["action"] = "NoActionNeeded"  
                if self.stuck_in_state_handler(state):
                    self.log.logger[self.log_key].warning(f"auto_restart - thread [{self.thread_profile}] -  set session detected profile [{self.node_service.profile}] - stuck in [{session_list['state1']}] - forcing restart.")
                    self.profile_states[self.node_service.profile]["action"] = "restart_full"  
                    self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] -  set session detected profile [{self.node_service.profile}] - resetting tolerance counter.")
                    self.profile_states[self.node_service.profile][f"{session_list['state1']}_enabled"] = False                
            elif session_list["state1"] == "ReadyToJoin":
                # local service is ready to join doesn't need a restart
                self.profile_states[self.node_service.profile]["match"] = True
                self.profile_states[self.node_service.profile]["action"] = "join_only"   
                                    
            elif session_list["session1"] == 0 or session_list["state1"] == "ApiNotReady" or session_list["state1"] == "Offline":
                # local service is not started 
                if session_list["session1"] == 0:
                    self.profile_states[self.node_service.profile]["match"] = False
                self.profile_states[self.node_service.profile]["action"] = "restart_full" 

        if self.profile_states[self.node_service.profile]["node_state"] == "Ready":
            self.clear_timers_flags("timers")
        elif self.profile_states[self.node_service.profile]["node_state"] in self.pre_consensus_state_list:
            self.clear_timers_flags("flags")
    

    def set_persistent_alert(self,alert,report):
        with open(self.persist_alert_file,"w") as file:
            file.write(f"alert: {str(alert)}\n")       
            file.write(f"report: {str(report)}\n")       


    def clear_timers_flags(self, tf_type):
        if tf_type == "timers":
            for clear_state_time in self.stuck_in_state_list:
                self.profile_states[self.node_service.profile][f"{clear_state_time}_time"] = 0  
        elif tf_type == "flags":
            for fork_type in ["minority_fork","consensus_fork"]:
                self.profile_states[self.node_service.profile][fork_type] = False


    # LOOPERS
    def attempts_looper(self,attempts,action,sec,max_attempts,critical_sleep):
        # attempts       : attempt so far
        # action         : for debug message
        # sec            : how long
        # max_attempts   : before critical sleep
        # critical_sleep : True sleep False skip

        if attempts > max_attempts:
            self.log.logger[self.log_key].critical(f"auto_restart - thread [{self.thread_profile}] - attempts looper - service has attempted [{max_attempts}] times | profile [{self.node_service.profile}] | action [{action}]")
            self.log.logger[self.log_key].warning(f"auto_restart - thread [{self.thread_profile}] -  attempts looper...  profile [{self.node_service.profile}] - LOOPER will wait 10 minutes before continuing.")
            if critical_sleep:
                sleep(self.sleep_on_critical)
            self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] - attempts looper - profile [{self.node_service.profile}] has completed a 10 minute wait and will continue...")
            self.stop_or_start_failed = {
                "failed": True,
                "action": None,
            }
            return 1
            
        self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] -  attempts looper - profile [{self.node_service.profile}] - [{action}] attempt [{attempts}] of [{max_attempts}] - pausing {sec}")
        sleep(sec)
        return attempts+1
           
                         
    def wait_for_ep_looper(self,action=None,attempts=1):
        self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] -  wait for ep looper - timer invoked thread [{self.node_service.profile}]")
        while True:
            if action == None:
                action = self.profile_states[self.node_service.profile]["action"]
            remote_session = self.profile_states[self.node_service.profile]["remote_session"]
            if "ep_wait" in action:
                self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] -  check and wait for LB - found [{action}]  | error or maintenance [{remote_session}] - entering attempts looper")
                attempts = self.attempts_looper(attempts,"waiting for LB to return valid token",30,30,True)  # infinite sleep - throws critical error at 30
                if action == "ep_wait": self.update_profile_states()
                if action == "ep_wait_ext": return attempts
            else:
                self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] -  check and wait for LB - found [{action}]  | returning from looper")
                return
               

    def observing_looper(self):
        # Observing looper includes WaitingForReady State (>1.9.0)
        attempts = 1
        max_attempts = 10

        while True:
            self.update_profile_states()
            state = self.profile_states[self.profile_pairing[1]['profile']]['node_state']  # layer0 state

            self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] -  Observing/WaitingForReady looper - action [{self.node_service.profile}] initiated | current found state [{state}]")
            if state == "Observing" or state == "WaitingForReady":
                attempts = self.attempts_looper(attempts,f"waiting: {state} --> Ready",16,max_attempts,False)  # 4 minutes of testing
                if attempts > max_attempts:
                    self.log.logger[self.log_key].error(f"auto_restart - thread [{self.thread_profile}] -  Observing/WaitingForReady looper - action [{self.node_service.profile}] initiated | could not achieve \"Ready\" | current found state [{state}]")
                    return False
            else:
                self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] -  Observing/WaitingForReady looper - action [{self.node_service.profile}] exiting | current found state [{state}]")  
                return True


    # CORE SERVICE MANIPULATION
    def check_service_state(self):
        self.node_service.get_service_status()
        self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] -  check service state - found service [{self.node_service.profile}] state [{self.node_service.node_service_status[self.node_service.profile]}]")
        if self.node_service.node_service_status[self.node_service.profile] == "active (running)":
            return True
        return False


    def silent_restart(self,action):
        self.on_boot_handler()
        
        # make sure we don't need to auto_upgrade before we do the restart
        self.version_check_handler()
        self.v2v3_migration_handler()

        if action != "join_only":
            if not self.profile_states[self.node_service.profile]["minority_fork"] and not self.profile_states[self.node_service.profile]["consensus_fork"]:
                # double check in case network issue caused a false positive
                # fork detection already has a 5 minute verification process
                self.update_profile_states() 
            if self.profile_states[self.node_service.profile]["action"] == "NoActionNeeded":
                self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] -  possible cluster restart false positive detected - skipping restart | profile [{self.node_service.profile}]")
                return
            
            self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] -  cluster restart false positive detection test cleared - continuing with restart | profile [{self.node_service.profile}]")        
            self.log.logger[self.log_key].warning(f"auto_restart - thread [{self.thread_profile}] -  silent restart [stop] initiating | profile [{self.node_service.profile}]")
            self.stop_start_handler("stop")
            self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] -  silent restart - updating [seed_list]")
            if self.config_obj[self.thread_profile]["seed_repository"] != "disable":
                _ = self.node_service.download_constellation_binaries({
                    "caller": "update_seedlist",
                    "profile": self.thread_profile,
                    "environment": self.environment,
                })
            # self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] -  silent restart - sleeping [{self.silent_restart_timer}]")
            # sleep(self.silent_restart_timer)   # not truly necessary but adding more delay
            self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] -  silent restart [start] initiating | profile [{self.node_service.profile}]")
            self.stop_start_handler("start")
            
        self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] -  silent restart [join] initiating | profile [{self.node_service.profile}]")
        if self.stop_or_start_failed["failed"] == False:
            self.join_handler()
        else:
           self.log.logger[self.log_key].debug(f"auto_restart - silent restart - action [{self.stop_or_start_failed['action']}] failed, dropping back to - restart handler")
            
        self.log.logger[self.log_key].info(f"auto_restart - silent restart method completed | [{self.node_service.profile}]")
            
                
    # HANDLERS
    def stuck_in_state_handler(self,state):
        self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] - stuck_in_state_handler - testing timing for state [{state}]")
        current_time = time()
        
        if state == "SessionStarted":
            self.version_check_handler(True)

        if not self.stuck_timers[f"{state}_state_enabled"]:
            self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] - stuck_in_state_handler - enabling timer for state [{state}]")
            self.stuck_timers[f"{state}_state_enabled"] = True
            self.profile_states[self.node_service.profile][f"{state}_time"] = time()

        elapsed_seconds = int(current_time - self.profile_states[self.node_service.profile][f"{state}_time"])
        self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] - stuck_in_state_handler - timer for state [{state}] reached [{elapsed_seconds}] (will be negative for first run)")
        if elapsed_seconds > self.stuck_timers[f"{state}_tolerance"]:
            return True
        self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] - stuck_in_state_handler - does not meet tolerance level for state [{state}] continuing... tolerance [{elapsed_seconds}] of [{self.stuck_timers[f'{state}_tolerance']}]")
        return False
    
    
    def fork_handler(self,fork_type):
        # on the first run only the timers will be set
        # check for minority fork or consensus fork
        # after first run
        #   if minority fork was detected wait 5 minutes
        #   otherwise check for minority fork
        #   if longer than 5 minutes then check again and if still 
        #   present, execute restart

        if self.fork_check_time[fork_type] > -1: 
            if self.profile_states[self.node_service.profile][fork_type] == "disabled":
                self.log.logger[self.log_key].debug(f"auto_restart - {fork_type}_handler - thread [{self.thread_profile}] fork detection disabled, skipping...")
                return
        
        self.log.logger[self.log_key].info(f"auto_restart - {fork_type}_handler - thread [{self.thread_profile}]")
        if self.thread_layer > 0:
            self.log.logger[self.log_key].debug(f"auto_restart - {fork_type}_handler - thread [{self.thread_profile}] - layer [{self.thread_layer}] - skipping minority fork detection")
            return
        
        if self.profile_states[self.thread_profile]["node_state"] != "Ready": 
            self.log.logger[self.log_key].warning(f"auto_restart - {fork_type}_handler - thread [{self.thread_profile}] | node state: [{self.profile_states[self.thread_profile]['node_state']}] will not check for fork, skipping.")
            return

        if self.fork_check_time[fork_type] > -1: 
            if self.profile_states[self.node_service.profile][fork_type]:
                if self.fork_check_time[fork_type] >= time() - self.fork_timer:
                    self.log.logger[self.log_key].debug(f"auto_restart - {fork_type}_handler - thread [{self.thread_profile}] - minority check timer not met, skipping.")
                    return False
                else:
                    self.fork_check_time[fork_type] = -1 # force reinitialization after restart
                    return True
        else:
            # initialize on first run
            self.log.logger[self.log_key].debug(f"auto_restart - {fork_type}_handler - thread [{self.thread_profile}] fork detection initializing...")
            self.profile_states[self.node_service.profile][fork_type] = False if self.first_thread else "disabled"
            if self.profile_states[self.node_service.profile][fork_type] == "disabled":
                return False

        # reset timer   
        self.fork_check_time[fork_type] = time()
        self.log.logger[self.log_key].debug(f"auto_restart - {fork_type}_handler - thread [{self.thread_profile}] checking for {fork_type} fork.")
        
        skip = False
        try:
            if fork_type == "minority_fork":
                global_ordinals = self.cli.cli_minority_fork_detection({
                    "caller": "auto_restart",
                    "profile": self.thread_profile,
                })
            elif fork_type == "consensus_fork":
                # if false there is a consensus_fork
                consensus_match = self.cli.cli_check_consensus({
                    "profile": self.thread_profile,
                    "caller": "auto_restart",
                })
        except Exception as e:
            if fork_type == "minority_fork":
                self.log.logger[self.log_key].error(f"auto_restart - {fork_type}_handler - thread [{self.thread_profile}] - error while obtaining global ordinals [{e}] skipping check. | nodectl error_code [as-578]")
            elif fork_type == "consensus_fork":    
                self.log.logger[self.log_key].error(f"auto_restart - {fork_type}_handler - thread [{self.thread_profile}] - error while checking for consensus fork [{e}] skipping check. | nodectl error_code [as-580]")
            skip = True
        
        if fork_type == "minority_fork":
            for key, value in global_ordinals.items():
                if value == None:  
                    skip = True
                    self.log.logger[self.log_key].warning(f'auto_restart - minority_fork_handler - thread [{self.thread_profile}] -requesting ordinal resulted in no results - ordinal key/value [{key}/{value}]')
            if skip: return False # skipping restart
            
            self.log.logger[self.log_key].debug(f'auto_restart - minority_fork_handler - thread [{self.thread_profile}] - localhost ordinal [{global_ordinals["local"]["ordinal"]}]')
            self.log.logger[self.log_key].debug(f'auto_restart - minority_fork_handler - thread [{self.thread_profile}] -   Backend ordinal [{global_ordinals["backend"]["ordinal"]}]')
            self.log.logger[self.log_key].debug(f'auto_restart - minority_fork_handler - thread [{self.thread_profile}] - localhost hash [{global_ordinals["local"]["lastSnapshotHash"]}]')
            self.log.logger[self.log_key].debug(f'auto_restart - minority_fork_handler - thread [{self.thread_profile}] -   Backend hash [{global_ordinals["backend"]["lastSnapshotHash"]}]')
            
            if global_ordinals["local"]["lastSnapshotHash"] == global_ordinals["backend"]["lastSnapshotHash"]: 
                self.log.logger[self.log_key].debug(f'auto_restart - minority_fork_handler - thread [{self.thread_profile}] - fork not detected - valid match found')
                self.profile_states[self.node_service.profile][fork_type] = False
                return False
            
        elif fork_type == "consensus_fork":
            if skip: return False # skipping restart
            if consensus_match:
                self.log.logger[self.log_key].debug(f'auto_restart - consensus_fork_handler - thread [{self.thread_profile}] - fork not detected - valid participation detected')
                self.profile_states[self.node_service.profile][fork_type] = False
                return False
        
        # restart needed
        self.log.logger[self.log_key].warning(f'auto_restart - {fork_type}_handler - thread [{self.thread_profile}] - fork detected.')
        self.profile_states[self.node_service.profile][fork_type] = True
        return False # wait five minutes first
    
    
    def v2v3_migration_handler(self):
        if not self.auto_upgrade: 
            return
        self.version_obj = self.versioning.get_cached_version_obj()
        self.log.logger[self.log_key].info(f"auto_restart - thread [{self.thread_profile}] - v2 to v3 migration handler - initialized.")
        for n in range(0,4):
            migration_success = self.cli.cli_execute_directory_restructure(
                self.thread_profile,
                self.version_obj[self.environment][self.thread_profile]["node_tess_version"],
            )
            if migration_success == "not_needed":
                self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] - v2 to v3 migration handler - not needed, skipping.")
                return                
            if migration_success: 
                self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] - v2 to v3 migration handler - successfully updated.")
                return
            if n > 2:
                self.log.logger[self.log_key].critical(f"auto_restart - thread [{self.thread_profile}] - v2 to v3 migration handler - unable to properly migrate this node - skipping.")
                return
            

    def version_check_handler(self,sessionStartedState=False):
        # do not do anything until the versions match
        self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] -  version check handler - initiated - profile [{self.node_service.profile}] ")
        attempts = 1
        notice_warning = ""
        warning = False
        auto_upgrade_success = True
    
        # update version_obj
        def update_version_cache():
            for n in range(1,5):
                self.version_obj = self.versioning.get_cached_version_obj()
                try:
                    if isinstance(self.version_obj[self.environment][self.thread_profile]["tess_uptodate"],bool):
                        self.version_obj[self.environment][self.thread_profile]["tess_uptodate"] = "false"
                        self.profile_states[self.node_service.profile]["version_uptodate"] = False
                        if self.version_obj[self.environment][self.thread_profile]["tess_uptodate"]:
                            self.version_obj[self.environment][self.thread_profile]["tess_uptodate"] = "true"
                            self.profile_states[self.node_service.profile]["version_uptodate"] = True
                except Exception as e:
                    self.log.logger[self.log_key].critical(f"auto_restart -> version_check_handler -> update_version -> failed with [{e}]")
                    if n > 3:
                        self.attempts_looper(0,"versioning_update",125,1,True)
                    self.log.logger[self.log_key].debug(f"attempting to update version object | attempt [{n}] or [3]")
                    self.attempts_looper(0,"versioning_update",125,1,False)
                else:
                    break
                    
            versions = [
                self.version_obj[self.environment][self.thread_profile]["cluster_tess_version"],
                self.version_obj[self.environment][self.thread_profile]["node_tess_version"]
            ]
            
            return versions
        
        while True:
            versions = update_version_cache()
            self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] -  version check handler - version check")
            try:
                if self.version_obj[self.environment][self.thread_profile]["tess_uptodate"] == "true": 
                    self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] -  version check handler - profile [{self.thread_profile}] - versions matched | Hypergraph/metagraph/cluster [{versions[0]}] node [{versions[1]}]")
                    if not self.auto_upgrade or auto_upgrade_success:
                        return True
                    elif self.auto_upgrade and not auto_upgrade_success:
                        self.log.logger[self.log_key].error("auto_restart - auto_upgrade - was unsuccessful in attempt to download new version.")
                    warning = True
            except Exception as e:
                self.log.logger[self.log_key].critical(f"auto_restart - thread [{self.thread_profile}] -  version check handler - profile [{self.node_service.profile}] - versions do not match - and we received an error [{e}] - sleeping 10m")
                sleep(self.sleep_on_critical) # ten minutes
            self.log.logger[self.log_key].warning(f"auto_restart - thread [{self.thread_profile}] -  version check handler - profile [{self.node_service.profile}] - versions do not match - versions found | Hypergraph/metagraph/cluster [{versions[0]}] node [{versions[1]}] - auto_upgrade setting [{str(self.auto_upgrade)}]")

            if self.auto_upgrade:
                notice_warning = "auto_upgrade to obtain "
                if sessionStartedState:
                    self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] -  version check handler - version changed while in [SessionStarted] updating to [restart_full]")
                    self.profile_states[self.thread_profile]["action"] = "restart_full"
                auto_upgrade_success = self.node_service.download_constellation_binaries({
                    "caller": "refresh_binaries",
                    "profile": self.thread_profile,
                    "environment": self.environment,
                })["success"]
                if auto_upgrade_success: 
                    self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] -  version check handler - versions upgrade successful")
                    update_version_cache()
                    break
                else: warning = True
            else:
                self.log.logger[self.log_key].warning(f"auto_restart - thread [{self.thread_profile}] - auto_upgrade disabled.")
                notice_warning = "node operator to obtain "
                warning = True
            if warning:
                attempts = self.attempts_looper(attempts,f"pausing for {notice_warning}new version",30,10,True)
            warning = False
           
           
    def stop_start_handler(self,action):
        self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] -  stop start  - profile: [{self.node_service.profile}] api_port [{self.node_service.api_ports['public']}] -- ready to [{action}]")
        if not self.debug:
            self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] -  stop start  - profile: [{self.node_service.profile}] [{action}] action commencing...")
            self.node_service.change_service_state({
                "profile": self.thread_profile,
                "action": action,
                "service_name": f"cnng-{self.node_service.node_service_name}",
                "caller": "auto_restart"
            })
                    
        attempts = 1
        max_attempts = 10
        while True:
            self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] -  stop start - profile [{self.node_service.profile}] testing or retesting state")
            self.update_profile_states()
            state = self.profile_states[self.node_service.profile]['node_state'] # readability
            
            self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] -  stop start - profile [{self.node_service.profile}] found state [{state}]")
            
            if action == "stop":
                self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] -  stop start - state [{state}] waiting for [stop] to reach [ApiNotReady] or [Offline]")
                if state == "ApiNotReady" or state == "Offline":
                    self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] - stop start - profile [{self.node_service.profile}] stop start exiting [stop] found state [{state}]")
                    break
                self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] -  stop start - profile [{state}] did not reach desired state [ApiNotReady] or [Offline]")
                
            elif action == "start":
                self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] -  stop start - waiting for [start] to complete with desired state [ReadyToJoin]")
                # note: DownloadInProgress may take a long time to complete.
                if "Ready" in state or "Observing" in state: # Ready, Observing, WaitingForReady, WaitingForObserving
                    self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] -  stop start - profile [{self.node_service.profile}] stop start exiting [start] found state [{state}]")
                    break
                self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] -  stop start - profile [{self.node_service.profile}] did not reach desired state [ReadyToJoin]")
            
            attempts = self.attempts_looper(attempts,action,10,max_attempts+1,False)
            if self.stop_or_start_failed["failed"]:
                self.log.logger[self.log_key].warning(f"auto_restart - thread [{self.thread_profile}] -  stop start - profile [{self.node_service.profile}] failed [{state}]")
                self.stop_or_start_failed = {
                    "failed": True,
                    "action": action
                }
                break
                
        self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] -  stop start - action [{action}] [{self.node_service.profile}] api_port [{self.node_service.api_ports['public']}] completed")
        
   
    def join_handler(self):
        state = self.profile_states[self.node_service.profile]['node_state']  # code readability  -- self.profile_states is set in the handler method
        self.log.logger[self.log_key].info(f"auto_restart - thread [{self.thread_profile}] -  join handler - [join] action [{self.node_service.profile}] initiated | current found state [{state}]")
        
        # The stop and start procedures would not allow us to get here without being "ReadyToJoin"
        self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] -  join handler - starting action [join] | state is [{state}]")
        
        if not self.independent_profile: # we do not need to test other layers before joining
            try:
                self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] -  join handler - action [join] | detected layer1 [{self.node_service.profile}] - waiting for layer0 to become ready entering Observing/WaitingForReady state looper")
                observing_to_ready = self.observing_looper()
                if not observing_to_ready:
                    self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] -  join handler - action [join] | detected layer1 [{self.node_service.profile}] - failed to see L0 set to [Ready] returning to restart handler")
                    return
            except:
                # single profile no dependencies
                pass
        
        if not self.debug:
            self.node_service.join_cluster({
                "caller": "auto_restart",
                "action": "auto_join",
                "interactive": False,
            })

        attempts = 1
        while True:
            self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] -  join handler | profile: [{self.node_service.profile}] [127.0.0.1] port [{self.node_service.api_ports['public']}] - testing or retesting state...")
            self.update_profile_states()
            state = self.profile_states[self.node_service.profile]['node_state'] # readability

            self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] -  join handler - profile [{self.node_service.profile}] found | state [{state}]")
            
            if "Ready" in state or "Observing" in state: # Ready, Observing, WaitingForReady, WaitingForObserving  
                self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] -  join handler - success achieved | state [{state}]")
                break
            
            self.log.logger[self.log_key].warning(f"auto_restart join handler - profile [{self.node_service.profile}] state in [{state}] entering retry looper")
            attempts = self.attempts_looper(attempts,"silent_restart",5,5,False)
            if attempts > 4:
                if "download" in state.lower() or "waiting" in state.lower() or "observing" in state.lower():
                    self.log.logger[self.log_key].warning(f"auto_restart join handler - profile [{self.node_service.profile}] not ready to continue state [{state}] dropping back into restart handler.")
                else:
                    self.log.logger[self.log_key].warning(f"auto_restart join handler - profile [{self.node_service.profile}] failed, dropping back to restart handler")
                break
        
        
        self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] -  join handler - completed join attempt | state [{state}] | sleeping [{self.join_pause_timer}] seconds before continuing")
        sleep(self.join_pause_timer)
        self.update_profile_states()
        state = self.profile_states[self.node_service.profile]['node_state'] # readability
        self.log.logger[self.log_key].info(f"auto_restart - thread [{self.thread_profile}] -  join handler - check for ready state | final state: [{state}] [127.0.0.1] port [{self.node_service.api_ports['public']}] - exiting join_handler")  
    

    def alert_handler(self):
        if not self.alerting["enable"]: 
            self.log.logger[self.log_key].debug(f"auto_restart -> thread [{self.thread_profile}] --> alerting is disabled")
            return

        report_hour = datetime.now().hour
        l_msg = f'auto_restart -> thread [{self.thread_profile}] --> alerting is disabled because outside of specified alerting hours. '
        l_msg += f'begin hour [{self.alerting["begin_alert_utc"]}] emd hour [{self.alerting["end_alert_utc"]}] current_hour [{report_hour}]'   

        if self.alerting["begin_alert_utc"] == self.alerting["end_alert_utc"]:
            self.log.logger[self.log_key].debug(f"auto_restart -> thread [{self.thread_profile}] -> alerting set to always on.")
        elif self.alerting["begin_alert_utc"] <= self.alerting["end_alert_utc"]:
            if not (self.alerting["begin_alert_utc"] <= report_hour < self.alerting["end_alert_utc"]):
                self.log.logger[self.log_key].debug(l_msg)
                return  
        else: # Wraparound case
            if not (report_hour >= self.alerting["begin_alert_utc"] or report_hour < self.alerting["end_alert_utc"]):
                msg += f' wrap around case'
                self.log.logger[self.log_key].debug(l_msg)
                return   
               
        send_alert, send_report = True, True        

        if not path.isfile(self.persist_alert_file):
            self.set_persistent_alert(True,True)
        else:
            with open(self.persist_alert_file,"r") as file:
                lines = file.readlines()
                for line in lines:
                    if "alert" in line and "False" in line:
                        send_alert = False
                    if f"report" in line and "False" in line:
                        send_report = False

        if self.profile_states[self.thread_profile]["action"] == "NoActionNeeded":
            try:
                if int(self.alerting['report_hour_utc']) == report_hour:
                    if send_report:
                        self.set_persistent_alert(send_alert,False)
                        if self.thread_layer < 1:
                            prepare_report(
                                self.cli, self.node_service, self.functions, 
                                self.profile_states[self.thread_profile], 
                                self.alerting, self.thread_profile, 
                                self.cluster, self.log
                            )
                    return
                else:
                    if self.profile_states[self.thread_profile]['node_state'] == "Ready":
                        if not send_alert:
                            prepare_alert(
                                "clear", self.alerting, self.thread_profile, 
                                self.cluster, self.functions, self.log
                            )
                        self.set_persistent_alert(True,True)
            except: 
                self.log.logger[self.log_key].error(f"auto_restart - thread [{self.thread_profile}] - alert handler - unable to send report - issue with configuration settings")
            return
        
        if send_alert:
            self.set_persistent_alert(False,send_report)
            result = prepare_alert(
                self.profile_states, self.alerting, self.thread_profile, 
                self.cluster, self.functions, self.log
            )
            if result == "skip":
                self.set_persistent_alert(True,send_report)    


    def restart_handler(self):
        self.node_service.set_profile(self.thread_profile)
        
        self.log.logger[self.log_key].info(f"auto_restart - thread [{self.thread_profile}] -  restart handler - invoked | profile [{self.thread_profile}]")

        while True:
            if self.passphrase_warning:
                self.log.logger[self.log_key].error(f"auto_restart - restart handler -  thread [{self.thread_profile}] found possible manual passphrase requirement - auto_restart will not be able to proper authenticate on restart requirement, sleeping [20 minutes].")
                sleep(1200)
                self.log.logger[self.log_key].info(f"auto_restart - restart handler -  thread [{self.thread_profile}] re-checking if configuration has been updated...")
                self.setup_profile_states()
            else:
                self.log.logger[self.log_key].info(f"auto_restart - thread [{self.thread_profile}] -  restart handler - timer invoked thread [{self.thread_profile}] - sleeping [{self.timer}] seconds")
                sleep(self.timer)
                self.log.logger[self.log_key].info(f">>>> auto_restart - thread [{self.thread_profile}] -  restart handler - thread [{self.thread_profile}] timer expired [{self.timer}] seconds elapsed, checking sessions.") 
            
                self.set_test_external_state("ep") # is the cluster up?
                self.update_profile_states()   
                action = self.profile_states[self.node_service.profile]["action"]
                match = self.profile_states[self.node_service.profile]["match"]
                state = self.profile_states[self.node_service.profile]["node_state"]
                minority_fork = self.profile_states[self.node_service.profile]["minority_fork"]
                consensus_fork = self.profile_states[self.node_service.profile]["consensus_fork"]

                self.alert_handler()
                # extra_wait_time = random.choice(self.random_times)

                if action == "ep_wait":
                    warn_msg = "\n==========================================================================\n"
                    warn_msg += f"auto_restart - thread [{self.thread_profile}] -  restart handler - LOAD BALANCER NOT REACHABLE | profile [{self.thread_profile}] state [{state}] sessions matched [{match}]\n"
                    warn_msg += "=========================================================================="
                    self.log.logger[self.log_key].warning(warn_msg)
                    self.wait_for_ep_looper()
                elif match and action == "NoActionNeeded":
                    warn_msg = "\n==========================================================================\n"
                    warn_msg += f"auto_restart - thread [{self.thread_profile}] -  restart handler - SESSION MATCHED | profile [{self.thread_profile}] state [{state}] sessions matched [{match}]\n"
                    warn_msg += "=========================================================================="
                    self.log.logger[self.log_key].info(warn_msg)
                elif action == "layer0_wait" or action == "layer1_wait":
                    cause = "Global layer0 link (GL0)" if action == "layer0_wait" else "Cluster/metagraph Layer0 (ML0)"
                    warn_msg = "\n==========================================================================\n"
                    warn_msg += f"auto_restart - thread [{self.thread_profile}] -  restart handler - {cause} link state not ready | profile [{self.thread_profile}] action [{action}]\n"
                    warn_msg += f"auto_restart - take no action at this time | thread [{self.thread_profile}] state [{state}]\n"
                    warn_msg += "=========================================================================="
                    self.log.logger[self.log_key].warning(warn_msg)
                else:
                    self.log.logger[self.log_key].debug(f"auto_restart - thread [{self.thread_profile}] -  restart handler - random sleep before executing restart request | sleep [{extra_wait_time}s]")
                    sleep(extra_wait_time)
                    if not match:
                        warn_msg = "\n==========================================================================\n"
                        warn_msg += f"auto_restart - thread [{self.thread_profile}] -  restart handler - SESSION DID NOT MATCHED - MAJORITY FORK detected | profile [{self.thread_profile}] state [{state}] sessions matched [{match}]\n"
                        warn_msg += "=========================================================================="                        
                        self.log.logger[self.log_key].warning(warn_msg)
                    elif consensus_fork:
                        warn_msg = "\n==========================================================================\n"
                        warn_msg += f"auto_restart - thread [{self.thread_profile}] -  restart handler - RESTART NEEDED CONSENSUS FORK detected | profile [{self.thread_profile}] state [{state}]\n"
                        warn_msg += "=========================================================================="      
                        self.log.logger[self.log_key].warning(warn_msg)
                    elif minority_fork:
                        warn_msg = "\n==========================================================================\n"
                        warn_msg += f"auto_restart - thread [{self.thread_profile}] -  restart handler - RESTART NEEDED MINORITY FORK detected | profile [{self.thread_profile}] state [{state}]\n"
                        warn_msg += "=========================================================================="      
                        self.log.logger[self.log_key].warning(warn_msg)
                    elif action == "restart_full":
                        warn_msg = "\n==========================================================================\n"
                        warn_msg += f"auto_restart - thread [{self.thread_profile}] -  restart handler - RESTART NEEDED but SESSION MATCH | profile [{self.thread_profile}] state [{state}] sessions matched [{match}]\n"
                        warn_msg += "=========================================================================="      
                        self.log.logger[self.log_key].warning(warn_msg)
                    elif action == "join_only":
                        warn_msg = "\n==========================================================================\n"
                        warn_msg += f"auto_restart - thread [{self.thread_profile}] -  restart handler - JOIN ONLY ACTION NEEDED | profile [{self.thread_profile}] state [{state}] sessions matched [{match}]\n"
                        warn_msg += "=========================================================================="      
                        self.log.logger[self.log_key].warning(warn_msg)
                    self.silent_restart(action)


if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")
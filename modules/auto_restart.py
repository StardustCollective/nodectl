
from time import sleep
from sys import exit
import random

from .node_service import Node
from .functions import Functions
from .troubleshoot.errors import Error_codes
from .troubleshoot.logger import Logging
from .node_service import Node

class AutoRestart():

    def __init__(self,thread_profile,config_obj,allow_upgrade):
        # THIS SERVICE IS THREADED TO RUN ALL PROFILES SEPARATELY
        self.error_messages = Error_codes() 
        self.log = Logging()

        config_obj = {
            **config_obj,
            "global_elements": {"caller":"auto_restart"},
        }
        
        self.functions = Functions(config_obj)        
        self.functions.auto_restart = True
        self.functions.set_default_variables({
            "profile": thread_profile
        })

        self.debug = False # full debug - disable restart and join actions
        self.allow_upgrade = allow_upgrade # only want one thread to attempt auto_upgrade
        self.retry_tolerance = 50
        self.observing_tolerance = 5        
        self.thread_profile = thread_profile  # initialize
        self.rapid_restart = config_obj["global_auto_restart"]["rapid_restart"]    
        self.sleep_on_critical = 600 if not self.rapid_restart else 15
        self.link_types = ["ml0","gl0"]
        
        if self.rapid_restart: self.random_times = [5]; self.timer = 5; self.sleep_on_critical = 15
        else:
            self.random_times = []
            for n in range(40,220,10):
                self.random_times.append(n)
            
            self.sleep_times = []
            for n in range(95,125,5):
                self.sleep_times.append(n)
                
            self.timer = random.choice(self.sleep_times)
        
        self.log.logger.info(f"\n==================\nAUTO RESTART - {self.thread_profile} Thread - Initiated\n==================")
        
        self.clean_up_thread_profiles()
        self.start_node_service()   
        self.setup_profile_states()
        self.restart_handler()
        
      
    # SETUP  
    def start_node_service(self):
        self.log.logger.info(f"auto_restart - thread [{self.thread_profile}] - starting node services...")
        command_obj = {
            "caller": "cli",
            "config_obj": self.functions.config_obj,
            "profile": self.profile_names[0],
            "command": "auto_restart",
        }
        self.node_service = Node(command_obj,False)   
        self.node_service.auto_restart = True 
        self.log.logger.debug("auto_restart -> start_node_service completed successfully.") 
        
        self.ip_address = self.functions.get_ext_ip()
        
        
    def set_ep(self):  
         # ep: def: edge_point
         self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] -  setup ep - pulling ep details | profile [{self.node_service.profile}]")
         self.edge_device = self.functions.pull_edge_point(self.node_service.profile)
         self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] -  setup ep - pulling ep details | remote [{self.edge_device}]")
        

    # PROFILE MANIPULATE
    def clean_up_thread_profiles(self):
        # This method will clean up all unnecessary profiles that are not
        # related to this service / thread
        self.profile_names = []
        profile_pairings = self.functions.pull_profile({
            "req": "pairings",
        })

        complete = False
        for single_pairing in profile_pairings:
            for profile in single_pairing:
                if profile["profile"] == self.thread_profile:
                    self.profile_names = [single_pairing[-1]["profile"]]
                    self.profile_names.append(self.thread_profile)
                    complete = True
                    break
            if complete:
                break

        remove_profile_list = []
        
        self.gl0_link_profile = self.functions.config_obj[self.thread_profile]["gl0_link_profile"]
        self.ml0_link_profile = self.functions.config_obj[self.thread_profile]["ml0_link_profile"]
            
        for link_type in self.link_types:            
            for profile in self.profile_names:
                if profile != self.thread_profile and profile != eval(f"self.{link_type}_link_profile"):
                    remove_profile_list.append(profile)
                    
        for remove in remove_profile_list:
            self.profile_names.pop(self.profile_names.index(remove))


    def setup_profile_states(self):
        self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] -  setup profiles - initializing known profile sessions and state | all profile [{self.profile_names}]")
        self.profile_states = {}
        
        self.auto_upgrade = self.passphrase_warning = False
        if self.functions.config_obj["global_auto_restart"]["auto_upgrade"] and self.allow_upgrade:
            self.auto_upgrade = True
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
            self.profile_states[profile]["layer"] = int(self.functions.config_obj[profile]["layer"])
            
            for link_type in self.link_types:
                if self.functions.config_obj[self.thread_profile][f"{link_type}_link_enable"] == True:
                    if self.gl0_link_profile != "None": self.profile_states[profile]["gl0_link_profile"] = self.gl0_link_profile
                    if self.gl0_link_profile != "None": self.profile_states[profile]["gl0_link_profile"] = self.gl0_link_profile

    
    def update_profile_states(self):
        self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] -  update profile states | all profile [{self.profile_names}]")
        
        profile_states = self.profile_states
        if self.profile_states[self.thread_profile]["layer"] == 0:  # layer0 doesn't care about layer1
            profile_states = [self.thread_profile]
        
        for profile in profile_states:
           self.node_service.set_profile(profile)
           self.set_ep()
           self.set_session_and_state()
           self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] -  update profile states | profile details [{self.profile_states[profile]}]")
                        
           # debugging
           self.log.logger.debug("=====================================================================================")
           self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] -  update profile states | requested by [{self.thread_profile}]")
           self.log.logger.debug("=====================================================================================")
           for key,value in self.profile_states[profile].items():
               self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] -  update profile states | profile [{profile}] {key} [{value}]")
           self.log.logger.debug("=====================================================================================")
           
        self.node_service.set_profile(self.thread_profile)  ## return the node_service profile to the appropriate profile
        
        
    def set_session_and_state(self):
        self.log.logger.info(f"auto restart - get session and state - updating profile [{self.node_service.profile}] state and session object with edge device [{self.edge_device}]") 
        
        self.functions.get_service_status()
        continue_checking = True
        # reset the stop_start monitor
        self.stop_or_start_failed = {
            "failed": False,
            "action": None
        }  

        attempts = 0
        while True: # utilize looper until success
            try:
                self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] edge [{self.edge_device}]")
                self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] profile [{self.node_service.profile}]")
                session_list = self.functions.pull_node_sessions({
                    "edge_device": self.edge_device,
                    "profile": self.node_service.profile,
                    "key": "clusterSession"
                })
            except Exception as e:
                self.log.logger.error(f"auto_restart - set_session_and_state - thread [{self.thread_profile}] error [{e}]")
                attempts = self.attempts_looper(attempts,"session retrieval",20,3,False)
            else:
                break
        
        self.log.logger.debug(f"auto_restart - set sessions - profile [{self.thread_profile}] | session_list | {session_list}")
        
        self.profile_states[self.node_service.profile]["match"] = True
        self.profile_states[self.node_service.profile]["ep_ready"] = True
        self.profile_states[self.node_service.profile]["action"] = None
        self.profile_states[self.node_service.profile]["remote_session"] = session_list["session0"]
        self.profile_states[self.node_service.profile]["local_session"] = session_list["session1"]
        self.profile_states[self.node_service.profile]["remote_node"] = session_list["node0"]
        self.profile_states[self.node_service.profile]["local_node"] = session_list["node1"]
        self.profile_states[self.node_service.profile]["node_state"] = session_list["state1"]
        self.profile_states[self.node_service.profile]["action"] = "NoActionNeeded"
        
        dependent_link = self.profile_states[self.node_service.profile]["link_profile"]
        
        # check if LB is up first
        if session_list["session0"] == 0:
            self.profile_states[self.node_service.profile]["match"] = False
            self.profile_states[self.node_service.profile]["ep_ready"] = False
            self.profile_states[self.node_service.profile]["action"] = "ep_wait"
            self.profile_states[self.node_service.profile]["node_state"] = session_list["state1"]
            
        # force layer1 to wait until layer0 is Ready
        elif self.profile_states[self.node_service.profile]["layer"] > 0:
            if dependent_link and self.profile_states[dependent_link]["node_state"] != "Ready":
                self.profile_states[self.node_service.profile]["match"] = False
                self.profile_states[self.node_service.profile]["ep_ready"] = True
                self.profile_states[self.node_service.profile]["action"] = "layer1_wait"
                self.profile_states[self.node_service.profile]["node_state"] = session_list["state1"]
                continue_checking = False
        
        if continue_checking:    
            if session_list["session0"] > session_list["session1"] and session_list['session1'] > 0:
                self.profile_states[self.node_service.profile]["match"] = False
                self.profile_states[self.node_service.profile]["action"] = "restart_full"  
                
            elif session_list["state1"] == "Observing" or session_list["state1"] == "WaitingForReady":
                # local service is Observing -- Check for stuck Observing Session
                self.profile_states[self.node_service.profile]["match"] = True
                self.profile_states[self.node_service.profile]["observing_timer"] = self.profile_states[self.node_service.profile]["observing_timer"]+1
                self.profile_states[self.node_service.profile]["action"] = "NoActionNeeded"   
                if self.observing_tolerance < self.profile_states[self.node_service.profile]["observing_timer"]:
                    self.log.logger.warn(f"auto_restart - thread [{self.thread_profile}] -  set session detected profile [{self.node_service.profile}] - stuck in [{session_list['state1']}] - forcing restart.")
                    self.profile_states[self.node_service.profile]["action"] = "restart_full"  
                                    
            elif session_list["state1"] == "ReadyToJoin":
                # local service is ready to join doesn't need a restart
                self.profile_states[self.node_service.profile]["match"] = True
                self.profile_states[self.node_service.profile]["action"] = "join_only"   
                                    
            elif session_list["session1"] == 0 or session_list["state1"] == "ApiNotReady" or session_list["state1"] == "SessionStarted" or session_list["state1"] == "Offline":
                # local service is not started 
                if session_list["session1"] == 0:
                    self.profile_states[self.node_service.profile]["match"] = False
                self.profile_states[self.node_service.profile]["action"] = "restart_full"
            
        if self.profile_states[self.thread_profile]["layer"] == 0 and self.node_service.profile == self.thread_profile and self.profile_states[self.node_service.profile]["action"] == "restart_full":
            self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] -  set session detected profile [{self.node_service.profile}] - resetting observing timer.")
            self.profile_states[self.node_service.profile]["observing_timer"] = 0
    
    
    # LOOPERS
    def attempts_looper(self,attempts,action,sec,max_attempts,critical_sleep):
        # attempts       : attempt so far
        # action         : for debug message
        # sec            : how long
        # max_attempts   : before critical sleep
        # critical_sleep : True sleep False skip
        
        attempts = attempts+1
        if attempts > max_attempts:
            self.log.logger.critical(f"auto_restart - thread [{self.thread_profile}] - attempts looper - service has attempted [{max_attempts}] times | profile [{self.node_service.profile}] | action [{action}]")
            self.log.logger.warn(f"auto_restart - thread [{self.thread_profile}] -  attempts looper...  profile [{self.node_service.profile}] - LOOPER will wait 10 minutes before continuing.")
            if critical_sleep:
                sleep(self.sleep_on_critical)
            self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] - attempts looper - profile [{self.node_service.profile}] has completed a 10 minute wait and will continue...")
            self.stop_or_start_failed = {
                "failed": True,
                "action": None,
            }
            return 1
            
        self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] -  attempts looper - profile [{self.node_service.profile}] - [{action}] attempt [{attempts}] of [{max_attempts}] - pausing {sec}")
        sleep(sec)
        return attempts
           
                         
    def wait_for_ep_looper(self):
        self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] -  wait for ep looper - timer invoked thread [{self.node_service.profile}]")
        attempts = 1
        while True:
            action = self.profile_states[self.node_service.profile]["action"]
            remote_session = self.profile_states[self.node_service.profile]["remote_session"]
            if action == "ep_wait":
                self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] -  check and wait for LB - found [{action}]  | error or maintenance [{remote_session}] - entering attempts looper")
                attempts = self.attempts_looper(attempts,"waiting for LB to return valid token",30,30,True)  # infinite sleep - throws critical error at 30
                self.update_profile_states()
            else:
                self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] -  check and wait for LB - found [{action}]  | returning from looper")
                return
               

    def observing_looper(self):
        # Observing looper includes WaitingForReady State (>1.9.0)
        attempts = 1
        max_attempts = 10
        while True:
            self.update_profile_states()
            state = self.profile_states[self.profile_names[0]]['node_state']  # layer0 state
            self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] -  Observing/WaitingForReady looper - action [{self.node_service.profile}] initiated | current found state [{state}]")
            if state == "Observing" or state == "WaitingForReady":
                attempts = self.attempts_looper(attempts,f"waiting: {state} --> Ready",16,max_attempts,False)  # 4 minutes of testing
                if attempts > max_attempts:
                    self.log.logger.error(f"auto_restart - thread [{self.thread_profile}] -  Observing/WaitingForReady looper - action [{self.node_service.profile}] initiated | could not achieve \"Ready\" | current found state [{state}]")
                    return False
            else:
                self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] -  Observing/WaitingForReady looper - action [{self.node_service.profile}] exiting | current found state [{state}]")  
                return True


    # CORE SERVICE MANIPULATION
    def check_service_state(self):
        self.node_service.get_service_status()
        self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] -  check service state - found service [{self.node_service.profile}] state [{self.node_service.node_service_status[self.node_service.profile]}]")
        if self.node_service.node_service_status[self.node_service.profile] == "active (running)":
            return True
        return False


    def silent_restart(self,action):
        if action != "join_only":
            self.update_profile_states()  # double check in case network issue caused a false positive
            if self.profile_states[self.node_service.profile]["action"] == "NoActionNeeded":
                self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] -  possible cluster restart false positive detected - skipping restart | profile [{self.node_service.profile}]")
                return
            
            self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] -  cluster restart false positive detection cleared - continuing with restart | profile [{self.node_service.profile}]")        
            self.log.logger.warn(f"auto_restart - thread [{self.thread_profile}] -  silent restart [stop] initiating | profile [{self.node_service.profile}]")
            self.stop_start_handler("stop")
            self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] -  silent restart - updating [seed_list]")
            self.node_service.download_update_seedlist({
                "profile": self.thread_profile,
                "install_upgrade": False,
            })
            self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] -  silent restart - sleeping [30]")
            sleep(30)   # not truly necessary but adding more delay
            self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] -  silent restart [start] initiating | profile [{self.node_service.profile}]")
            self.stop_start_handler("start")
            
        self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] -  silent restart [join] initiating | profile [{self.node_service.profile}]")
        if self.stop_or_start_failed["failed"] == False:
            self.join_handler()
        else:
           self.log.logger.debug(f"auto_restart - silent restart - action [{self.stop_or_start_failed['action']}] failed, dropping back to - restart handler")
            
        self.log.logger.info(f"auto_restart - silent restart method completed | [{self.node_service.profile}]")
            
                
    # HANDLERS
    def version_check_handler(self):
        # do not do anything until the versions match
        self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] -  version check handler - initiated - profile [{self.node_service.profile}] ")
        attempts = 1
        notice_warning = ""
        warning = False
        auto_upgrade_success = True
        
        while True:
            versions = self.functions.test_n_check_version("get")
            self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] -  version check handler - version checked | [{versions}]")
            try:
                # 0 == on node  1 == on cluster
                if versions[0][self.thread_profile] == versions[1][self.thread_profile]["node_tess_version"]:
                    self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] -  version check handler - profile [{self.node_service.profile}] - versions matched | Hypergraph [{versions[0]}] Node [{versions[1]}]")
                    if not self.auto_upgrade or auto_upgrade_success:
                        return True
                    elif self.auto_upgrade and not auto_upgrade_success:
                        self.log.logger.error("auto_restart - auto_upgrade - was unsuccessful downloading new version.")
                    warning = True
            except Exception as e:
                self.log.logger.critical(f"auto_restart - thread [{self.thread_profile}] -  version check handler - profile [{self.node_service.profile}] - versions do not match - and we received an error [{e}] - sleeping 10m")
                sleep(self.sleep_on_critical) # ten minutes
            self.log.logger.warn(f"auto_restart - thread [{self.thread_profile}] -  version check handler - profile [{self.node_service.profile}] - versions do not match - versions matched | Hypergraph [{versions[0]}] Node [{versions[1]}] - entering attempts looper [180] delay")
            if self.auto_upgrade:
                notice_warning = "auto_upgrade to obtain "
                auto_upgrade_success = self.node_service.download_constellation_binaries({
                    "print_version": False,
                    "action": "auto_restart",
                    "download_version": versions[0],
                })
                if not auto_upgrade_success:
                    warning = True
            else:
                self.log.logger.warn(f"auto_restart - thread [{self.thread_profile}] - auto_upgrade disabled.")
                notice_warning = "node operator to obtain "
            if warning:
                attempts = self.attempts_looper(attempts,f"pausing for {notice_warning}new version",30,10,True)
            warning = False
           
           
    def stop_start_handler(self,action):
        self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] -  stop start  - profile: [{self.node_service.profile}] api_port [{self.node_service.api_ports['public']}] -- ready to [{action}]")
        if not self.debug:
            self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] -  stop start  - profile: [{self.node_service.profile}] [{action}] action commencing...")
            self.node_service.change_service_state({
                "profile": self.thread_profile,
                "action": action,
                "service_name": f"cnng-{self.node_service.node_service_name}",
                "caller": "auto_restart"
            })
                    
        attempts = 1
        max_attempts = 10
        while True:
            self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] -  stop start - profile [{self.node_service.profile}] testing or retesting state")
            self.update_profile_states()
            state = self.profile_states[self.node_service.profile]['node_state'] # readability
            
            self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] -  stop start - profile [{self.node_service.profile}] found state [{state}]")
            
            if action == "stop":
                self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] -  stop start - state [{state}] waiting for [stop] to reach [ApiNotReady] or [Offline]")
                if state == "ApiNotReady" or state == "Offline":
                    self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] - stop start - profile [{self.node_service.profile}] stop start exiting [stop] found state [{state}]")
                    break
                self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] -  stop start - profile [{state}] did not reach desired state [ApiNotReady] or [Offline]")
                
            elif action == "start":
                self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] -  stop start - waiting for [start] to complete with desired state [ReadyToJoin]")
                if "Ready" in state or "Observing" in state: # Ready, Observing, WaitingForReady, WaitingForObserving
                    self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] -  stop start - profile [{self.node_service.profile}] stop start exiting [start] found state [{state}]")
                    break
                self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] -  stop start - profile [{self.node_service.profile}] did not reach desired state [ReadyToJoin]")
            
            attempts = self.attempts_looper(attempts,action,10,max_attempts+1,False)
            if self.stop_or_start_failed["failed"]:
                self.log.logger.warn(f"auto_restart - thread [{self.thread_profile}] -  stop start - profile [{self.node_service.profile}] failed [{state}]")
                self.stop_or_start_failed = {
                    "failed": True,
                    "action": action
                }
                break
                
        self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] -  stop start - action [{action}] [{self.node_service.profile}] api_port [{self.node_service.api_ports['public']}] completed")
        
   
    def join_handler(self):
        state = self.profile_states[self.node_service.profile]['node_state']  # code readability  -- self.profile_states is set in the handler method
        self.log.logger.info(f"auto_restart - thread [{self.thread_profile}] -  join handler - [join] action [{self.node_service.profile}] initiated | current found state [{state}]")
        
        # The stop and start procedures would not allow us to get here without being "ReadyToJoin"
        self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] -  join handler - starting action [join] | state is [{state}]")
        
        try:
            if self.node_service.profile == self.profile_names[1]:
                self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] -  join handler - action [join] | detected layer1 [{self.node_service.profile}] - waiting for layer0 to become ready entering Observing/WaitingForReady state looper")
                observing_to_ready = self.observing_looper()
                if not observing_to_ready:
                    self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] -  join handler - action [join] | detected layer1 [{self.node_service.profile}] - failed to see L0 set to [Ready] returning to restart handler")
                    return
        except:
            # single profile no dependencies
            pass
        
        if not self.debug:
            self.node_service.join_cluster({
                "action": "auto_join",
                "interactive": False,
            })

        attempts = 1
        session_start_attempts = 1
        while True:
            self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] -  join handler | profile: [{self.node_service.profile}] [127.0.0.1] port [{self.node_service.api_ports['public']}] - testing or retesting state...")
            self.update_profile_states()
            state = self.profile_states[self.node_service.profile]['node_state'] # readability

            self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] -  join handler - profile [{self.node_service.profile}] found | state [{state}]")
            
            if "Ready" in state or "Observing" in state: # Ready, Observing, WaitingForReady, WaitingForObserving  
                self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] -  join handler - success achieved | state [{state}]")
                break
            
            self.log.logger.warn(f"auto_restart join handler - profile [{self.node_service.profile}] state in [{state}] entering retry looper")
            if state == "SessionStarted": 
                session_start_attempts = self.attempts_looper(session_start_attempts,"joining",30,3,False)
                if session_start_attempts > 2:
                    self.log.logger.warn(f"auto_restart join handler - profile [{self.node_service.profile}] state in [{state}]")                    
                    break
            else: # if any other state retry
                attempts = self.attempts_looper(attempts,"silent_restart",5,5,False)
                if attempts > 4:
                    self.log.logger.warn(f"auto_restart join handler - profile [{self.node_service.profile}] failed, dropping back to restart handler")
                    break
        
        
        self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] -  join handler - completed join attempt | state [{state}] | sleeping [180] seconds before continuing")
        sleep(180)
        self.update_profile_states()
        state = self.profile_states[self.node_service.profile]['node_state'] # readability
        self.log.logger.info(f"auto_restart - thread [{self.thread_profile}] -  join handler - check for ready state | final state: [{state}] [127.0.0.1] port [{self.node_service.api_ports['public']}] - exiting join_handler")  
    

    def restart_handler(self):
        self.node_service.set_profile(self.thread_profile)
        
        self.log.logger.info(f"auto_restart - thread [{self.thread_profile}] -  restart handler - invoked | profile [{self.thread_profile}]")

        while True:
            if self.passphrase_warning:
                self.log.logger.error("auto_restart - restart handler - found possible manual passphrase requirement - auto_restart will not be able to proper authenticate on restart requirement, sleeping [20 minutes].")
                sleep(1200)
                self.log.logger.info("auto_restart - restart handler - re-checking if configuration has been updated...")
                self.setup_profile_states()
            else:
                self.log.logger.info(f"auto_restart - thread [{self.thread_profile}] -  restart handler - timer invoked thread [{self.thread_profile}] - sleeping [{self.timer}] seconds")
                sleep(self.timer)
                self.log.logger.info(f">>>> auto_restart - thread [{self.thread_profile}] -  restart handler - thread [{self.thread_profile}] timer expired [{self.timer}] seconds elapsed, checking sessions.") 
            
                self.version_check_handler()
                
                self.update_profile_states()   
                action = self.profile_states[self.node_service.profile]["action"]
                match = self.profile_states[self.node_service.profile]["match"]
                state = self.profile_states[self.node_service.profile]["node_state"]
                extra_wait_time = random.choice(self.random_times)
                
                if action == "ep_wait":
                    self.log.logger.warn(f"\n==========================================================================\nauto_restart - thread [{self.thread_profile}] -  restart handler - LOAD BALANCER NOT REACHABLE | profile [{self.thread_profile}] state [{state}] sessions matched [{match}]\n==========================================================================")
                    self.wait_for_ep_looper()
                elif match and action == "NoActionNeeded":
                    self.log.logger.info(f"\n==========================================================================\nauto_restart - thread [{self.thread_profile}] -  restart handler - SESSION MATCHED | profile [{self.thread_profile}] state [{state}] sessions matched [{match}]\n==========================================================================")
                else:
                    self.log.logger.debug(f"auto_restart - thread [{self.thread_profile}] -  restart handler - random sleep before executing restart request | sleep [{extra_wait_time}s]")
                    sleep(extra_wait_time)
                    if not match:
                        self.log.logger.warn(f"\n==========================================================================\nauto_restart - thread [{self.thread_profile}] -  restart handler - SESSION DID NOT MATCHED | profile [{self.thread_profile}] state [{state}] sessions matched [{match}]\n==========================================================================")
                    elif action == "restart_full":
                        self.log.logger.warn(f"\n==========================================================================\nauto_restart - thread [{self.thread_profile}] -  restart handler - RESTART NEEDED but SESSION MATCH | profile [{self.thread_profile}] state [{state}] sessions matched [{match}]\n==========================================================================")
                    elif action == "join_only":
                        self.log.logger.warn(f"\n==========================================================================\nauto_restart - thread [{self.thread_profile}] -  restart handler - JOIN ONLY ACTION NEEDED | profile [{self.thread_profile}] state [{state}] sessions matched [{match}]\n==========================================================================")
                    self.silent_restart(action)


if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")        
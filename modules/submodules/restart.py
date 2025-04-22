from termcolor import colored
from time import sleep, perf_counter
from concurrent.futures import ThreadPoolExecutor, wait as thread_wait

from modules.troubleshoot.ts import Troubleshooter

class RestartNode():
    
    def __init__(self,parent,command_obj):
        self.parent = parent
        self.command_obj = command_obj
        self.restart_type = command_obj["restart_type"]
        self.argv_list = command_obj["argv_list"]
        
        self.log = self.parent.log.logger[self.parent.log_key]
        self.functions = self.parent.functions


    # ==== SETTERS ====
    
    def _set_leave_obj(self,delay,profile):
        self.leave_obj = {
            "secs": self.secs,
            "delay": delay,
            "profile": profile,
            "reboot_flag": False,
            "threaded": True,
        }
        
        
    def _set_stop_obj(self,delay,profile):
        self.stop_obj = {
            "show_timer": False,
            "profile": profile,
            "delay": delay,
            "argv_list": []
        }
        
        
    def _set_start_obj(self, profile, service_name):
        self.start_obj = {
            "spinner": False,
            "profile": profile,
            "service_name": service_name,
            "skip_seedlist_title": True,
        }         
        
        
    def set_parameters(self):
        self.called_profile = self.argv_list[self.argv_list.index("-p")+1]

        self.watch = True if "-w" in self.argv_list else False
        self.interactive = True if "-i" in self.argv_list else False
        self.non_interactive = True if "-ni" in self.argv_list or "--ni" in self.argv_list else False
        self.dip = True if "--dip" in self.argv_list else False
        self.input_error = False
        self.valid_request = False
        self.single_profile = True
                
        self.link_types = ["gl0","ml0"] 
        self.failure_retries = 3
        self.pos = 0
        
        self.performance_start = None
        
        self.restart_type = "restart_only" if "--restart-only" in self.argv_list else False
        self.secs = 30
        
        self.slow_flag = False
        if "--slow_restart" in self.argv_list:
            self.secs = 600 
            self.slow_flag = True
        
        if "-r" in self.argv_list:
            try: self.failure_retries = int(self.argv_list[self.argv_list.index("-r")+1])
            except: 
                self.input_error = True
                self.option = "r"
                self.extra2 = f'-r {self.argv_list[self.argv_list.index("-r")+1]}'
               
                
    def set_performance_start(self):
        self.performance_start = perf_counter()
        
        
    def set_default_variables(self):
        self.functions.set_default_variables({
            "profile": self.called_profile,
        })
        
        
    # ==== GETTERS ====
    
    def _get_profile_state(self, profile):
        return self.functions.test_peer_state({
            "profile": profile,
            "test_address": "127.0.0.1",
            "simple": True,
        })


    def get_profiles(self):
        self.profile_pairing_list = self.functions.pull_profile({
            "req": "order_pairing",
        })
        self.profile_order = self.profile_pairing_list.pop()
        
    # ==== PARSERS / PROCESSORS ====
    
    def _process_restart_full(self, profile):
        if self.restart_type == "restart_only": return
            
        environment = self.parent.config_obj[profile]["environment"]
        self.parent.print_title(f"JOINING [{environment.upper()}] [{profile.upper()}]")   

        if profile not in self.start_failed_list:
            self._print_log_msg("info",f'sending to join process. | profile [{profile}]')
            self.parent.cli_join({
                "skip_msg": False,
                "caller": "cli_restart",
                "skip_title": True,
                "wait": False,
                "watch": self.watch,
                "dip": self.dip,
                "interactive": self.interactive,
                "non_interactive": self.non_interactive,
                "single_profile": self.single_profile,
                "argv_list": ["-p",profile]
            })
        else:
            self._print_join_error(profile)
                    
                    
    def _process_restart_only(self, profile):
        self._print_log_msg("debug",f"'restart_only' option found")
        
        link_profiles = self.functions.pull_profile({
            "profile": profile,
            "req": "all_link_profiles",
        })
        for link_type in self.link_types:
            if link_profiles[f"{link_type}_link_enable"]:
                state = self.functions.test_peer_state({
                    "profile": link_profiles[f"{link_type}_profile"],
                    "skip_thread": False,
                    "simple": True
                })    
                
                if state != "Ready":
                    link_profile = link_profiles[f"{link_type}_profile"]
                    self._print_log_msg("warning",f"restart_only with join requested for a profile that is dependent on other profiles | [{profile}] link profile [{link_profile}]")
                    self._print_ready_warning(link_profile,state,profile)
                            
                            
    def process_ep_state(self):
        if self.restart_type == "restart_only": return
        
        while True:
            if self.functions.check_edge_point_health():
                break
        
            
    def process_leave_stop(self):
        with ThreadPoolExecutor() as executor:
            leave_list = []
            stop_list = []
            delay = .8
            
            for n, profile in enumerate(self.profile_order):
                self._print_log_msg("debug",f"preparing to leave and stop | profile [{profile}]")
                self._set_leave_obj(delay, profile)
                leave_list.append(self.leave_obj)
                self._set_stop_obj(delay, profile)
                delay += 1
                stop_list.append(self.stop_obj)  
                         
            # leave
            self.parent.print_title("LEAVING CLUSTERS") 
            leave_list[-1]["skip_msg"] = False     
            self._print_log_msg("info",f"executing leave process against profiles found")               
            futures = [executor.submit(self.parent.cli_leave, obj) for obj in leave_list]
            thread_wait(futures)

            self._print_stage_complete("Leave network operations")
        
            # stop
            self._print_log_msg("debug",f"executing stop process against profiles found")
            self.parent.print_title(f"STOPPING PROFILE {'SERVICES' if self.called_profile == 'all' else 'SERVICE'}","top")    
            stop_list[-1]["spinner"] = True
            futures = [executor.submit(self.parent.cli_stop, obj) for obj in stop_list]
            thread_wait(futures)  
            
            self._print_stage_complete("Stop network services")    
    
        
    def process_start_join(self):
        for profile in self.profile_order:
            self.parent.set_profile(profile)
                
            if self.restart_type == "restart_only":
                self._process_restart_only()
                        
            service_name = self.parent.config_obj[profile]["service"] 
            self.start_failed_list = []
            if not service_name.startswith("cnng-"): service_name = f"cnng-{service_name}"
                
            for n in range(1,self.failure_retries+1):
                self._print_log_msg("debug",f"service[s] associated with [{self.called_profile}]")
                self.parent.print_title(f"RESTARTING PROFILE {'SERVICES' if self.called_profile == 'all' else 'SERVICE'}")
                self._set_start_obj(profile, service_name)
                self.parent.cli_start(self.start_obj)
                
                peer_test_results = self._get_profile_state(profile)
                ready_states = self.functions.get_node_states("ready_states",True)
                
                if peer_test_results in ready_states:  # ReadyToJoin and Ready
                    self._print_log_msg("debug",f"found state [{peer_test_results}] profile [{profile}]")
                    break
                else:
                    if n > self.failure_retries-1:
                        self._handle_start_errors(profile, service_name)
                        
                    self._print_start_error(profile, n)
                    sleep(1)
                    self.cli_stop = {
                        "show_timer": False,
                        "profile": profile,
                        "argv_list": []
                    }
                    self.parent.cli_stop(self.cli_stop)
            
            self._process_restart_full(profile)
                    
                    
    def process_seedlist_updates(self):
        for n, profile in enumerate(self.profile_order):
            self._print_log_msg("debug",f"handling seed list updates against profile [{profile}]")
            self.parent.node_service.set_profile(profile)

            self.pos = self.parent.node_service.download_constellation_binaries({
                "caller": "update_seedlist",
                "profile": profile,
                "environment": self.parent.config_obj[profile]["environment"],
                "action": self.parent.caller,

            })  
            sleep(.5)      
            
    # ==== INTERNALS ====


    # ==== HANDLERS ====

    def handle_help_request(self):
        self.functions.check_for_help(self.argv_list,"restart")


    def handle_input_error(self):
        if not self.input_error: return
        
        self.parent.error_messages.error_code_messages({
            "error_code": "rn-85",
            "line_code": "input_error",
            "extra": self.option,
            "extra2": f"invalid value found -> {self.extra2}"
        })


    def handle_request_error(self):
        if self.valid_request: return
        
        self.parent.error_messages.error_code_messages({
            "error_code": "rn-96",
            "line_code": "profile_error",
            "extra": self.called_profile,
            "extra2": None
        })
        
        
    def _handle_start_errors(self, profile, service_name):
        self._print_log_msg("error",f"service failed to start [{service_name}] profile [{profile}]")
        self.functions.print_paragraphs([
            [profile,0,"red","bold"], ["service failed to start...",1]
        ])
        ts = Troubleshooter({"config_obj": self.parent.config_obj})
        self.parent.show_profile_issues(["-p",profile],ts)
        self.functions.print_auto_restart_warning()
        self.start_failed_list.append(profile)
                        
                        
    def handle_all_parameter(self):
        if self.called_profile != "all": return
        
        if "external" in self.profile_order: 
            self.profile_order.remove("external")
        self.single_profile = False
        self.valid_request = True
        
        
    def handle_empty_profile(self):
        if self.called_profile != "empty" and self.called_profile != None:
            for profile_list in self.profile_pairing_list:
                for profile_dict in profile_list:
                    if self.called_profile == profile_dict["profile"]:
                        self.profile_pairing_list = [[profile_dict]]  # double list due to "all" parameter
                        self.profile_order = [self.called_profile]
                        self.valid_request = True
                        break
                    
    # ==== PRINTERS ====
    
    def _print_stage_complete(self,msg):
        self.functions.print_cmd_status({
            "text_start": msg,
            "status": "complete",
            "status_color": "green",
            "newline": True,
        })
            
            
    def _print_start_error(self, profile,n):
        self.functions.print_paragraphs([
            [" Issue Found: ",0,"yellow,on_red","bold"],
            [f"{profile}'s service was unable to start properly.",1,"yellow"], 
            ["Attempting stop/start again",0], 
            [str(n),0,"yellow","bold"],
            ["of",0], [str(self.failure_retries),1,"yellow","bold"]
        ])


    def _print_join_error(self, profile):
            self._print_log_msg("error",f'restart process failed due to improper join, skipping join process. | profile [{profile}]')
            self.functions.print_paragraphs([
                [profile,0,"red","bold"], ["did not start properly; therefore,",0,"red"],
                ["the join process cannot begin",0,"red"], ["skipping",1, "yellow"],
            ])
            
            
    def _print_ready_warning(self, link_profile, state, profile):
        self.functions.print_paragraphs([
            ["",1], 
            [" WARNING ",2,"white,on_red"], 
            
            ["nodectl",0,"cyan","bold"], ["has detected a [",0], ["restart_only",-1,"yellow","bold"], 
            ["] request.  However, the configuration is showing that this node is (",-1],
            ["properly",0,"green","bold"], [") linking to a layer0 profile [",0],
            [link_profile,-1,"yellow","bold"], ["].",-1], ["",2],
            
            ["Due to this",0], ["recommended",0,"cyan","bold"], ["configurational setup, the layer1 [",0],
            [profile,-1,"yellow","bold"], ["]'s associated service will",-1], ["not",0,"red","bold"], 
            ["be able to start until after",0],
            [f"the {link_profile} profile is joined successfully to the network. A restart_only will not join the network.",2],
            
            ["      link profile: ",0,"yellow"], [link_profile,1,"magenta"],
            ["link profile state: ",0,"yellow"], [state,2,"red","bold"],
            
            ["This",0], ["restart_only",0,"magenta"], ["request will be",0], ["skipped",0,"red","bold"],
            [f"for {profile}.",-1]
        ])
                    
                    
    def _print_log_msg(self,log_type,msg):
        log_method = getattr(self.log, log_type, None)
        log_method(f"restart request --> {msg}")
        
                            
    def print_restart_init(self):
        self.functions.print_clear_line()
        ip_address = self.functions.get_ext_ip()

        self._print_log_msg("debug",f"request commencing on [{ip_address}] for [{self.called_profile}]")
        self.functions.print_cmd_status({
            "text_start": "Restart request initiated",
            "status": "running",
            "status_color": "yellow",
            "newline": True,
        })
        self.functions.print_cmd_status({
            "text_start": "Node IP address",
            "status": ip_address,
            "status_color": "green",
            "newline": True,
        })
    
    
    def print_performance(self):
        print("")        
        self.functions.print_perftime(self.performance_start,"restart")
        
        
    def print_cursor_position(self):
        print(f"\033[{self.pos['down']}B", end="", flush=True)
        print("")        

if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")  

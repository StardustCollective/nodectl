from termcolor import colored
from time import sleep
from sys import exit

from modules.cn_requests import CnRequests

class Join():
    
    def __init__(self,parent,command_obj):
        self.parent = parent
        self.command_obj = command_obj
        self.skip_msg = command_obj.get("skip_msg",False)
        self.skip_title = command_obj.get("skip_title",False)
        self.watch_peer_counts = command_obj.get("watch",False)
        self.single_profile = command_obj.get("single_profile",True)
        self.upgrade = command_obj.get("upgrade",False)
        self.interactive = command_obj.get("interactive",False)
        self.non_interactive = command_obj.get("non_interactive",False)
        self.dip_status = command_obj.get("dip",False)
        self.caller = command_obj.get("caller",False)
        self.argv_list = command_obj.get("argv_list")
        
        self.log = self.parent.log
        self.functions = self.parent.functions
        
        
    # ==== SETTERS ====

    def set_parameters(self):
        
        self.called_profile = self.argv_list[self.argv_list.index("-p")+1]
        self.parent.set_profile(self.called_profile)
        
        self.cn_requests = CnRequests(self.set_self_value, self.get_self_value, self.log)
        self.cn_requests.set_self_value("called_command","join")
        self.cn_requests.set_self_value("config_obj",self.parent.config_obj)
        self.cn_requests.set_self_value("profile_names",[self.called_profile])
        self.cn_requests.set_parameters()
        self.parent.node_service.set_self_value('cn_requests',self.cn_requests)
        
        self.result = False
        self.snapshot_issues = False 
        self.tolerance_result = False
        self.found_dependency = False
        self.offline_msg = False
        
        self.join_result = None
        self.state = None
        
        self.first_attempt = True
        
        # every 4 seconds updated
        self.wfd_count, self.wfd_max = 0, 5  # WaitingForDownload
        self.dip_count, self.dip_max = 0, 8 # DownloadInProgress
        self.ss_count, self.ss_max = 0, 35 # SessionStarted 
        
        self.attempt = ""
        self.color = "green"
        
        
        self.defined_connection_threshold = .8
        self.max_timer = 300
        self.peer_count, self.old_peer_count = 0, 0 
        self.src_peer_count, self.increase_check = 0, 0
        
        self.gl0_link = self.functions.config_obj[self.called_profile]["gl0_link_enable"]
        self.ml0_link = self.functions.config_obj[self.called_profile]["ml0_link_enable"]

        self.states = self.functions.get_node_states("on_network",True)
        self.break_states = self.functions.get_node_states("past_observing",True)
                    
                    
    def set_state_n_profile(self,profile):
        self.cn_requests.set_self_value("use_profile_cache",True)
        self.state = self.cn_requests.get_profile_state(profile)
        self.profile = profile
        # self.state = self.functions.test_peer_state({
        #     "profile": profile,
        #     "simple": simple,
        #     "skip_thread": skip_thread,
        # })

        
    def set_self_value(self, name, value):
        setattr(self, name, value)
        

    # ==== GETTERS ====
    
    def _get_peer_count(self):
        self.peer_count = self.functions.get_peer_count({
            "peer_obj": {"ip": "127.0.0.1"},
            "profile": self.parent.profile,
            "count_only": True,
        })
        
        
    def get_self_value(self, name, default=False):
        return getattr(self, name, default)
    
            
    # ==== PARSERS / PROCESSORS ====

    def process_join_cluster(self):
        self._print_log_msg("info",f"joining cluster profile [{self.profile}]")
        
        from modules.submodules.join_service import JoinService
        join_service = JoinService(self,self.command_obj)
        join_service.set_self_value("cn_requests",self.cn_requests)
        join_service.set_self_value("profile",self.profile)
        
        join_service.set_parameters()
        join_service.set_profile_api_ports()
        join_service.set_link_obj()
        join_service.print_caller_log()
        join_service.get_link_types()
        join_service.handle_static_peer()
        join_service.set_join_data_obj()
        join_service.set_clear_to_join()
        join_service.process_prepare_to_join()
        join_service.print_join_status()            
        join_service.process_join()        
        join_service.handle_exceptions()
        join_service.handle_not_clear_to_join()
                
        if join_service.action == "cli":
            return join_service.result   
            
        # self.join_result = self.parent.node_service.join_cluster({
        #     "caller": "cli_join",
        #     "action":"cli",
        #     "interactive": True if self.watch_peer_counts or self.interactive else False, 
        # }).strip()

        
    def process_post_join(self):
        if self.color != "green": return
        
        for allocated_time in range(0,self.max_timer):
            self.allocated_time = allocated_time
            sleep(1)
            
            self._print_log_msg("debug",f" watching join process | profile [{self.parent.profile}]")
            if allocated_time % 5 == 0 or allocated_time < 1:  # 5 second mark or first attempt
                self._process_allocated_time(allocated_time)
                self._get_peer_count()

            
                self._process_peer_increment()
                
                if self._process_wfd(): 
                    break
                if self._process_offline(): 
                    break
                if self._process_sessionstarted(): 
                    break
                
                if self._process_dip(): 
                    break

                self.increase_check = 0
                self.set_state(self.called_profile,True,True)

                if self._process_watch_peers(): 
                    break

                        
            self._parse_connection_threshold()
            self._print_update(True)
                    
            if self._parse_tolerance(): 
                break
                
                
    def _process_allocated_time(self,allocated_time):
        if allocated_time % 10 == 0 or allocated_time < 1:
            # re-check source every 10 seconds
            self.src_peer_count = self.functions.get_peer_count({
                "profile": self.parent.profile,
                "count_only": True,
            })
            
            
    def _process_peer_increment(self):
        if self.peer_count != self.old_peer_count or self.allocated_time < 2:
            return
        
        # did not increase
        if self.peer_count == False:
            self.print_connection_error()
        self.increase_check += 1
        
        
    def _process_wfd(self):
        if self.state != "WaitingForDownload": return False
        
        if self.wfd_count > self.wfd_max:
            self.snapshot_issues = "wfd_break"
            self.result = False
            self.tolerance_result = False # force last error to print
            return True
        
        self.wfd_count += 1
        return True
    
            
    def _process_offline(self):
        if self.state != "Offline": return False
        
        self.offline_msg = True
        self.result = False
        self.tolerance_result = False
        
        return True
        
        
    def _process_sessionstarted(self):
        if self.state != "SessionStarted": return False
        
        if self.ss_count > self.ss_max:
            self.result = False
            self.tolerance_result = False # force last error to print
            return True
        
        self.ss_count += 1        
        return False
        
        
    def _process_dip(self):
        if self.state != "DownloadInProgress": return False
        
        if self.dip_status:
            self._print_dip_msg()
            if self.non_interactive: 
                continue_dip = True
            else:  
                continue_dip = self.functions.confirm_action({
                "yes_no_default": "n",
                "return_on": "y",
                "prompt_color": "magenta",
                "prompt": "Watch DownloadInProgress status?",
                "exit_if": True
                })
            if continue_dip:
                self.parent.show_download_status({
                    "caller": self.caller,
                    "command_list": ["-p", self.called_profile],
                })
                return True
            
        elif self.dip_count > self.dip_max:
            self.snapshot_issues = "dip_break"
            self.result = False
            self.tolerance_result = False # force last error to print
            return True
        
        self.dip_count += 1
        return False
            
    
    def _process_watch_peers(self):
        if self.watch_peer_counts: return False
        
        if self.state in self.break_states or (self.single_profile and self.state in self.states):
            self._print_update()
            self.result = True
            return True
                 

    def process_incomplete_peer_connections(self):
        if self.peer_count < self.src_peer_count and not self.watch_peer_counts:
            call_type = "upgrade" if self.upgrade else "default"
            self.functions.print_paragraphs([
                ["",1],[" IMPORTANT ",0,"grey,on_green"], ["It is ok that the peer count < cluster peer count",1,"yellow"],
                ["because watch mode was",0,"yellow"], ["not",0,"red"], [f"chosen by {call_type}.",1,"yellow"],
            ])
            if not self.upgrade:
                self.functions.print_paragraphs([
                    ["add",0,"yellow"], ["-w",0,"cyan","bold"], ["to wait and show full peer count display.",1,"yellow"],
                ])                    
    
    
    def _parse_connection_threshold(self):
        try:
            self.connect_threshold = self.peer_count/self.src_peer_count
            if self.peer_count >= self.src_peer_count and self.state != "SessionStarted": 
                self.result = True
            else:
                if self.connect_threshold >= self.defined_connection_threshold and self.increase_check > 1:
                    if self.state in self.break_states:
                        self.tolerance_result = True
                else:
                    self.old_peer_count = self.peer_count
        except Exception as e:
            self._print_log_msg("error",f"cli-join - {e}")
            
                
    def _parse_tolerance(self):
        if self.result or self.tolerance_result or self.allocated_time > self.max_timer or self.increase_check > 8: # 8*5=40
            self.no_new_status = "error" if self.state not in self.break_states else self.state

            if self.increase_check > 3:
                self.functions.print_cmd_status({
                    "text_start": "No new nodes discovered for ~40 seconds",
                    "status": self.no_new_status,
                    "status_color": "red",
                    "newLine": True
                })
            return True
        return False


    def parse_snapshot_issues(self):
        if not self.snapshot_issues: return

        if self.snapshot_issues == "wfd_break":
            self._print_wfd_issue()                
        if self.snapshot_issues == "dip_break":
            self._print_dip_issue()


    def parse_tolerance_issues(self):
        if not self.result and self.tolerance_result:
            self._print_tolerance_warning()
        elif not self.result and not self.tolerance_result:
            self._print_tolerance_error()


    # ==== INTERNALS ====


    # ==== HANDLERS ====

    def handle_layer0_links(self):
        if self.single_profile or (not self.gl0_link and not self.ml0_link):
            return
            
        found_dependency = False
        if not self.watch_peer_counts: # check to see if we can skip waiting for Ready
            for link_profile in self.parent.profile_names:
                for link_type in ["gl0","ml0"]:
                    if getattr(self, f"{link_type}_link", True):
                        if self.functions.config_obj[self.called_profile][f"{link_type}_link_profile"] == link_profile:
                            self._print_log_msg("info",f"found [{link_type}] dependency | profile [{self.called_profile}]")
                            found_dependency = True
                        elif self.functions.config_obj[self.called_profile][f"{link_type}_link_profile"] == "None" and not found_dependency:
                            self._print_log_msg("debug",f"found [{link_type}] dependency | profile [{self.called_profile}] external [{self.functions.config_obj[link_profile][f'{link_type}_link_host']}] external port [{self.functions.config_obj[link_profile][f'{link_type}_link_port']}]")
                            found_dependency = True

        if not found_dependency:
            self._print_log_msg("debug",f"no dependency found | profile [{self.called_profile}]")
            self.single_profile = True
            
        self.found_dependency = found_dependency    
            
    
    def handle_ready_state(self):
        if self.state != "Ready": 
            return False
        
        self._print_log_msg("warning",f"profile already in proper state, nothing to do | profile [{self.parent.profile}] state [{self.state}]")
        self.functions.print_paragraphs([
            [" WARNING ",0,"blue,on_green"],
            ["Profile already in",0,"green"],
            ["Ready",0,"green","bold"],
            ["state, the join process is not necessary.",1,"green"]
        ])
        
        return True


    def handle_apinotready(self):
        if self.state != "ApiNotReady": return
        
        self._print_log_msg("warning",f" service does not seem to be running | profile [{self.parent.profile}] service [{self.parent.service_name}]")
        self.functions.print_paragraphs([
            ["Profile state in",0,"red"], [self.state,0,"red","bold"],
            ["state, cannot join",1,"red"], ["Attempting to start service [",0],
            [self.parent.service_name.replace('cnng-',''),-1,"yellow","bold"],
            ["] again.",-1], ["",1]
        ])

        self._print_log_msg("debug",f"attempting to start service | profile [{self.parent.profile}] service [{self.parent.service_name}]")
        self.parent.cli_start({
            "spinner": True,
            "profile": self.parent.profile,
            "service_name": self.parent.service_name,
        })
        
        
    def handle_static_peer(self):
        if self.parent.config_obj[self.parent.profile]["static_peer"]:
            self._print_log_msg("info",f"sending to node services to start join process | profile [{self.parent.profile}] static peer [{self.parent.config_obj[self.parent.profile]['edge_point']}]")

        
    def handle_link_color(self):
        if self.gl0_link or self.ml0_link:
            if "not Ready" in str(self.join_result):
                self.color = "red"
                self.attempt = " attempt"
            

    def handle_offline_state(self):
        if not self.offline_msg: return

        self.functions.print_paragraphs([
            ["",1],[" Please start the node first. ",1,"yellow,on_red"],
        ])
        
        
    def handle_join_complete(self):
        print("")
        self._print_log_msg("info",f"join process has completed | profile [{self.parent.profile}] result [{self.join_result}]")
        self.functions.print_cmd_status({
            "text_start": f"Join process{self.attempt} complete",
            "status": self.join_result,
            "status_color": self.color,
            "newline": True
        })
        
        
    def handle_bad_join(self):
        if self.color != "red": return
        
        self.functions.print_paragraphs([
            ["'sudo nodectl check-connection -p <profile_name>'",2,self.color]
        ])  
        
        
    def handle_help_arg(self):
        self.functions.check_for_help(self.argv_list,"join")
        
        
    # ==== PRINTERS ====
    
    def _print_dip_msg(self):
        self.functions.print_paragraphs([
            ["",2],[" IMPORTANT ",0,"red,on_yellow"], ["the",0], ["--dip",0,"yellow"],
            ["option has been identified.  This will prompt nodectl to execute the",0],
            ["download_status",0,"magenta"], ["command.",2],
            ["The",0,],["DownloadInProgress",0,"magenta"], ["stage of the",0],["join cluster",0,"magenta"],
            ["process can be time consuming. If there's a desire to cancel watching the",0], 
            ["DownloadInProgress",0,"magenta"],
            ["stage, pressing the",0],["ctrl",0,"blue","bold"],["and",0],["c",0,"blue","bold"],
            ["will exit this process.",2], 
            
            ["Cancelling an issued",0,"green"], ["--dip",0,"yellow"], ["option will",0,"green"], ["NOT",0,"green","bold"], 
            ["harm or halt the join or restart process;",0,"green"],
            ["instead, it will just exit the visual aspects of this command and allow the node process to continue in the",0,"green"],
            ["background.",2,"green"],
            
            ["Issue:",0,],["sudo nodectl download_status help",1,"yellow"],
            ["to learn about the dedicated standalone command.",2],
        ])


    def _print_dip_issue(self):
        self._print_log_msg("warning",f"leaving watch process due to expired waiting time tolerance | profile [{self.parent.profile}] state [DownloadInProgress]")
        self.functions.print_paragraphs([
            ["",2],["nodectl has detected",0],["DownloadInProgress",0,"yellow","bold"],["state.",2],
            ["This is",0], ["not",0,"green","bold"], ["an issue; however, nodes may take",0],
            ["longer than expected time to complete this process.  nodectl will terminate the",0],
            ["watching for peers process during this join in order to avoid undesirable wait times.",1],
        ])  
            
            
    def _print_wfd_issue(self):
        self._print_log_msg("error",f"possible issue found | profile [{self.parent.profile}] issue [WaitingForDownload]")
        self.functions.print_paragraphs([
            ["",2],["nodectl has detected",0],["WaitingForDownload",0,"red","bold"],["state.",2],
            ["This is an indication that your node may be stuck in an improper state.",0],
            ["Please contact technical support in the Discord Channels for more help.",1],
        ])    
        
        
    def _print_tolerance_warning(self):
        self._print_log_msg("warning",f"cleaving watch process due to expired waiting time tolerance | profile [{self.parent.profile}]")
        self.functions.print_clear_line()
        self.functions.print_paragraphs([
            ["",1],["nodectl tolerance connection status of [",0,],
            [f"{self.defined_connection_threshold*100}%",-1,"yellow","bold"], ["] met or exceeded successfully,",-1],
            ["continuing join request.",1]
        ])
            
    
    def _print_tolerance_error(self):
        self._print_log_msg("error",f"may have found an issue during join process; however, this may not be of concern if the node is in proper state | profile [{self.parent.profile}]")
        self.functions.print_clear_line()
        self.functions.print_paragraphs([
            ["",1], [" WARNING ",0,"yellow,on_red","bold"], ["Issue may be present?",0,"red"],
            ["Please issue the following command to review the node's details.",1,"red"], 
            ["sudo nodectl check-connection -p <profile_name>",1],
            ["Follow instructions if error persists",2,"red"],
            
            [" NOTE ",0,"grey,on_green"], ["Missing a few nodes on the Hypergraph independent of the network, is",0,"green"],
            ["not an issue.  There will be other nodes leaving and joining the network; possibly, at all times.",1,"green"],
        ])
        
        
    def _print_log_msg(self,log_type,msg):
        log_method = getattr(self.log, log_type, None)
        log_method(f"{self.__class__.__name__} request --> {msg}")


    def _print_update(self,check_allocation=False):
        if check_allocation:
            if self.allocated_time % 1 > 0:
                return
            
        if self.first_attempt:
            self.first_attempt = False
            self.functions.print_paragraphs([
                ["",1],["State:",0,"magenta"], ["SessionStarted",0,"yellow"], ["may take up to",0,"magenta"],
                ["120+",0,"yellow"],["seconds to properly synchronize with peers to enhance join accuracy.",1,"magenta"],
                [" Max Timer ",0,"yellow,on_blue"],["300",0,"yellow"], ["seconds",1],
                ["-","half","blue","bold"],
            ])
            
        self.functions.print_clear_line()
        print(colored("  Peers:","cyan"),colored(f"{self.src_peer_count}","yellow"),
            colored("Connected:","cyan"),colored(f"{self.peer_count}","yellow"), 
            colored("State:","cyan"),colored(f"{self.state}","yellow"), 
            colored("Timer:","cyan"),colored(f"{self.allocated_time}","yellow"),
            end='\r')        


    def print_title(self):
        if self.skip_title: return
        self.parent.print_title(f"JOINING {self.called_profile.upper()}")
        
    
    def print_connection_error(self):
        self.parent.troubleshooter.setup_logs({"profile": self.called_profile})
        error_msg = self.troubleshooter.test_for_connect_error("all")
        if error_msg:
            self.functions.print_paragraphs([
                ["",1], ["Possible Error",1,"red","bold"],
                [f"{error_msg[1][0]['find']}",1,"magenta"],
                [f"{error_msg[1][0]['user_msg']}",1,"magenta"],
            ])
        self.functions.print_auto_restart_warning()
        print("")
        exit(1)
        
            
    def print_joining(self):
        if self.skip_msg: return
        
        self._print_log_msg("info",f"cli_join -> join starting| profile [{self.parent.profile}]")
        self.functions.print_cmd_status({
            "text_start": "Joining",
            "brackets": self.parent.profile,
            "status": "please wait",
            "status_color": "magenta",
            "newLine": True
        })
    
    
    def print_review(self):
        self._print_log_msg("debug",f"reviewing node state | profile [{self.parent.profile}] state [{self.state}]")
        self.functions.print_cmd_status({
            "text_start": "Reviewing",
            "brackets": self.parent.profile,
            "status": self.state,
            "color": "magenta",
            "newline": True,
        })    


    def print_completed_join(self,start_timer):
        self.functions.print_clear_line()
        print("")
        
        self.functions.print_cmd_status({
            "text_start": "Checking status",
            "brackets": self.parent.profile,
            "newline": True,
        })

        self.functions.cancel_event = False
        self.parent.show_system_status({
            "rebuild": True,
            "wait": False,
            "-p": self.parent.profile
        })
        
        print("")
        self.functions.print_perftime(start_timer,"join process")




if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")  

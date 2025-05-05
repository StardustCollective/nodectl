import psutil

from termcolor import colored
from concurrent.futures import ThreadPoolExecutor
from sys import exit
from datetime import datetime, timedelta

from modules.cn_requests import CnRequests

class ShowStatus():
    
    def __init__(self,parent,command_obj):
        self.parent = parent
        self.command_obj = command_obj
        self.rebuild = command_obj.get("rebuild",False)
        self.do_wait = command_obj.get("wait",True)
        self.spinner = command_obj.get("spinner",True)
        self.threaded = command_obj.get("threaded",False)
        self.static_nodeid = command_obj.get("static_nodeid",False)
        self.argv = command_obj.get("argv",[])
        self.log = self.parent.log
        self.functions = self.parent.functions
        self.auto_restart_handler = command_obj.get("auto_restart_handler",False)

    # ==== SETTERS ====

    def set_parameter(self):
        self.all_profile_request = False
        self.called_profile = self.parent.profile
        self.current_profile = False
        self.config_obj = self.parent.config_obj
        self.auto_restart_setup = False
        
        called_command = self.command_obj.get("called_command","default")
        if called_command == "_s": called_command = "status"
        if called_command == "_qs": called_command = "quick_status"
        if called_command == "stop": called_command = "quick_status"
        self.called_command = called_command
        
        self.profile_names = self.parent.profile_names
        self.ordinal_dict = {}        

        self.watch_enabled = True if "-w" in self.argv else False
        self.print_title = True if "--legend" in self.argv else False
        
        self.cn_requests = CnRequests(self,self.log)
        self.cn_requests.set_parameters()
        self.cn_requests.get_cache_needed()
                
        self.latest_ordinal = False  
        self.range_error = False
        self.node_id = False
        self.restart_time = False
        self.uptime = False
        self.sessions = False
        self.consensus_match = False
        
        self.watch_seconds = 15
        self.watch_passes = 0

    
    def set_profile(self):
        profile = self.functions.set_argv(self.argv,"-p","all")
        self.profile_names = self.parent.profile_names
          
        if profile == "all":
            self.all_profile_request = True
            return
 
        self.called_profile = profile
        self.profile_names = [profile]
        self.functions.check_valid_profile(profile)   
            
            
    def _set_service_status(self):
        self.functions.get_service_status()
            

    def _set_status_output(self):
        sessions = self.sessions
        
        on_network = colored("False","red")
        cluster_session = sessions["cluster_session"]
        node_session = sessions["node_session"]
        join_state = sessions['node_state']
        
        consensus_match = colored(f"False","red",attrs=["bold"])
        if self.consensus_match:
            consensus_match = colored(f"True","green",attrs=["bold"])      
                      
        if sessions["cluster_session"] == 0:
            on_network = colored("EdgePointDown","red")
            cluster_session = colored("SessionNotFound".ljust(20," "),"red")
            join_state = colored(f"{sessions['node_state']}".ljust(20),"yellow")
        else:
            if sessions["node_state"] == "ReadyToJoin":
                join_state = colored(f"{sessions['node_state']}".ljust(20),"yellow")
                on_network = colored("ReadyToJoin","yellow")
                
            if sessions["cluster_session"] == sessions["node_cluster_session"]:
                if sessions["node_state"] in ["DownloadInProgress"]:
                    join_state = colored(f"{sessions['node_state']}".ljust(20),"yellow")
                    consensus_match = colored(f"Preparing","yellow")
                elif sessions["node_state"] == "ApiNotResponding":
                    on_network = colored("TryAgainLater","magenta")
                    join_state = colored(f"ApiNotResponding".ljust(20),"magenta")
                elif sessions["node_state"] in ["WaitingForDownload","SessionStarted"]:
                    join_state = colored(f"{sessions['node_state']}".ljust(20),"yellow")
                    on_network = colored("True","magenta",attrs=["bold"])
                elif sessions["node_state"] != "ApiNotReady" and sessions["node_state"] != "Offline" and sessions["node_state"] != "Initial":
                    # there are other states other than Ready and Observing when on_network
                    on_network = colored("True","green",attrs=["bold"])
                    join_state = colored(f"{sessions['node_state']}".ljust(20),"green")
                    if sessions["node_state"] == "Observing" or sessions["node_state"] == "WaitingForReady":
                        join_state = colored(f"{sessions['node_state']}".ljust(20),"yellow")
                        consensus_match = colored(f"Preparing","yellow")
                else:
                    node_session = colored("SessionIgnored".ljust(20," "),"red")
                    join_state = colored(f"{sessions['node_state']}".ljust(20),"red")
                    
            if sessions["cluster_session"] != sessions["node_cluster_session"] and sessions["node_state"] == "Ready":
                    on_network = colored("False","red")
                    join_state = colored(f"{sessions['node_state']} (forked)".ljust(20),"yellow")
                            
        if sessions["node_session"] == 0:
            node_session = colored("SessionNotFound".ljust(20," "),"red")
        
        if join_state == "ApiNotReady":
            join_state = colored("ApiNotReady","red",attrs=["bold"])
    
        service_state = self.parent.config_obj["global_elements"]["node_service_status"][self.called_profile]
        if service_state == "inactive":
            service_state = colored(f"{service_state}".ljust(20),"magenta")
        elif service_state == "active":
            service_state = colored(f"{service_state}".ljust(20),"light_green")
            
        self.main_output = {
            "on_network": on_network,
            "cluster_session": cluster_session,
            "node_session": node_session,
            "join_state": join_state,
            "consensus_match": consensus_match,
            "service_state": service_state,
        }
                        
            
    def _set_ordinal_dict(self):
        self.ordinal_dict = self.cn_requests.get_cached_ordinal_details()

        
    def _set_node_cluster_times(self):
        restart_time, uptime = self._handle_time_node_id(self.sessions)  # localhost
        cluster_restart_time, cluster_uptime = self._handle_time_node_id(self.sessions,True)  # remote
                                
        system_boot = psutil.boot_time()
        system_uptime = datetime.now().timestamp() - system_boot
        system_uptime = timedelta(seconds=system_uptime)
        system_uptime = self.functions.get_date_time({
            "action":"estimate_elapsed",
            "elapsed": system_uptime,
        })
        system_boot = datetime.fromtimestamp(system_boot)
        system_boot = system_boot.strftime("%Y-%m-%d %H:%M:%S")
                        
        self.node_cluster_times = {
            "system_boot": system_boot,
            "system_uptime": system_uptime,
            "restart_time": restart_time,
            "uptime": uptime,
            "cluster_restart_time": cluster_restart_time,
            "cluster_uptime": cluster_uptime,
        }
        
                                                    
    def set_watch_parameters(self):
        if not self.watch_enabled: return
        
        self.watch_status = {}
        for profile in self.profile_names:
            self.watch_status[profile] = False
            
        try: 
            watch_seconds = self.argv[self.argv.index("-w")+1]
            watch_seconds = int(watch_seconds)
        except: 
            if watch_seconds != "--skip-warning-messages" and watch_seconds != "-p": 
                self._print_log_msg("error","invalid value for [-w] option, needs to be an integer. Using default of [6].")
                self.range_error = True
            watch_seconds = 15
        self.watch_enabled = True
        if watch_seconds < 6:
            self.range_error = True
            watch_seconds = 6
            
        self.watch_seconds = watch_seconds
        

    # ==== PARSERS / PROCESSORS ====

    def process_status(self):
        with ThreadPoolExecutor() as executor:
            self._handle_watch_request(executor)
            
            while True:
                if self.functions.cancel_event: 
                    exit("  Event Canceled")
                    
                if self.watch_enabled:
                    self.watch_passes += 1
                    self._print_watch_enabled()
                
                self._get_latest_ordinal_details()
                
                for n, current_profile in enumerate(self.profile_names):
                    self.current_profile = current_profile
                    self._print_log_msg("info",f"show system status requested | {self.current_profile}")
                    
                    self.parent.set_profile(self.current_profile)
                    self.called_profile = self.current_profile
                            
                    self._set_ordinal_dict()            

                    if self.called_command == "quick_status" or self.called_command == "_qs":
                        self._process_quick_status(n)
                        continue

                    if n > 0: 
                        self.print_title = False 
                        if self.all_profile_request:
                            self.spinner = False
                        print("")

                    self._set_service_status()
                    self._get_cluster_sessions()
                    
                    if self.parent.config_obj[self.called_profile]["layer"] < 1:
                        self._get_cluster_consensus()
                        
                    self._set_status_output()
                                    
                    if not self.parent.skip_build:
                        self._handle_rebuild()
                        self._set_node_cluster_times()

                        if self.called_command == "alerting":
                            raise Exception(self.node_cluster_times)
                        
                        self._print_title()
                        
                        # if self.config_obj[self.current_profile]["environment"] not in ["mainnet","integrationnet","testnet"]:
                        #      self.ordinal_dict["backend"] = "N/A"
                                        
                        self._print_status_output(self.current_profile)
                            
                if self._handle_watch_request(None,False):            
                    break
                self.cn_requests.handle_edge_point_cache()

    
    def _process_quick_status(self,n):
        if n == 0:
            self.functions.print_paragraphs([
                ["",1],[" NODE STATUS QUICK RESULTS ",2,"yellow,on_blue","bold"],
            ])                    
        self.quick_state = self.cn_requests.get_profile_state(self.called_profile)
        sessions = self.cn_requests.get_cached_sessions(self.called_profile)
        self.restart_time, self.uptime = self._handle_time_node_id(sessions)
            
        self._print_quickstatus_output()

        
    # ==== GETTERS ====
            
    def _get_nodeid(self):
        try:
            node_id = self.parent.cli_grab_id({
                "command": "nodeid",
                "argv_list": ["-p",self.called_profile],
                "dag_addr_only": True,
                "ready_state": True if self._get_profile_state(self.called_profile) == "Ready" else False
            })
            node_id = self.functions.cleaner(node_id,"new_line")
            node_id = f"{node_id[:8]}...{node_id[-8:]}"
        except Exception as e:
            self._print_log_msg("error",f"attempting to pull nodeid [{e}]")
            node_id = "unknown"
            
        return node_id
    
    
    def _get_latest_ordinal_details(self):
        if self.config_obj[self.called_profile]["layer"] > 0:
            return
        
        try:
            self.latest_ordinal = self.config_obj["global_elements"]["snapshot_cache"][self.called_profile]["latest"]
        except Exception as e:
            self._print_log_msg("error",f"_get_latest_ordinal_details --> error [{e}]")
                
                
    def _get_cluster_sessions(self):
        self.sessions = self.cn_requests.get_cached_sessions(self.called_profile)
    
    
    def _get_cluster_consensus(self):   
        self.consensus_match = self.cn_requests.get_cached_consensus(self.called_profile)
                        
                        
    # ==== INTERNALS ====


    # ==== HANDLERS ====

    def _handle_watch_request(self, executor, start=True):
        if not self.watch_enabled: return True
        
        if start:
            try:
                executor.submit(self.functions.get_user_keypress,{
                    "prompt": None,
                    "prompt_color": "magenta",
                    "options": ["Q"],
                    "quit_option": "Q",
                    "quit_with_exception": True,
                })
            except self.functions.exception:
                self.functions.cancel_event = True
                self.functions.print_paragraphs([
                    ["Action cancelled by user",1,"green"]
                ])
                exit(0)
                
            return False       

        if self.functions.cancel_event: 
            exit("  Event Canceled")
        self.functions.print_paragraphs([
            ["",1],["Press",0],["'q'",0,"yellow,on_red"], ['to quit',1],
            ["Watch passes:",0,"magenta"], [f"{self.watch_passes}",0,"yellow"],
            ["Intervals:",0,"magenta"], [f"{self.watch_seconds}s",1,"yellow"],
        ])
        self.functions.print_timer({
            "p_type": "cmd",
            "seconds": self.watch_seconds,
            "step": -1,
            "phrase": "Waiting",
            "end_phrase": "before updating",
        })
        
        return False
         

    def _handle_time_node_id(self,sessions,remote=False):
        get_nodid = False
        try:
            restart_time = self.functions.get_date_time({
                "action":"session_to_date",
                "elapsed": sessions["cluster_session"] if remote else sessions["node_session"],
            })
            
            uptime = self.functions.get_date_time({
                "action": "get_elapsed",
                "old_time": restart_time
            })
            uptime = self.functions.get_date_time({
                "action": "estimate_elapsed",
                "elapsed": uptime,
            })
        except:
            restart_time = "n/a"
            uptime = "n/a"
        
        if self.static_nodeid:
            node_id = f"{self.static_nodeid[:8]}...{self.static_nodeid[-8:]}"
        elif self.parent.node_id_obj:
            try:
                node_id = self.parent.node_id_obj[f"{self.current_profile}_short"]
            except:
                get_nodid = True
        else:
            get_nodid = True

        if get_nodid:
            try:
                node_id = f"{elements[1][:8]}...{elements[1][-8:]}"
            except:
                node_id = self._get_nodeid()
        
        self.node_id = node_id
        return restart_time, uptime
    
    
    def _get_profile_state(self,profile):
        state = self.functions.test_peer_state({
            "threaded": self.threaded,
            "spinner": self.spinner,
            "profile": profile,
            "simple": True
        })
        
        return state
        
        
    def _handle_rebuild(self):
        if not self.rebuild: return
        
        if self.do_wait:
            self.functions.print_timer({
                "seconds":20
            })
                                            
        self.sessions["node_state"] = self._get_profile_state(self.called_profile)
    
        return self._set_status_output()
            
            
    # ==== PRINTERS ====
    
    def print_auto_restart_options(self):
        self.auto_restart_handler("current_pid")
        
            
    def _print_log_msg(self,log_type,msg):
        log_method = getattr(self.log, log_type, None)
        log_method(f"{self.__class__.__name__} --> {msg}")


    def _print_watch_enabled(self):
        _ = self.functions.process_command({
            "proc_action": "clear",
        })

        self.functions.print_paragraphs([
            ["Press",0],["'q'",0,"yellow,on_red"], ['to quit',1],
            ["Do not use",0],["ctrl",0,"yellow"],["and",0],["c",2,"yellow"],
        ])
        if self.range_error:
            self.functions.print_paragraphs([
                [" RANGE ERROR ",0,"red,on_yellow"],["using [",0], 
                ["15",0,"yellow"], ["] second default.",2]
            ]) 


    def _print_title(self):
        if not self.print_title: return
        
        self.functions.print_states()
        self.functions.print_paragraphs([
            ["Current Session:",0,"magenta"], ["The metagraph cluster session",1],
            ["   Node Session:",0,"magenta"], ["Node's current session",1],
            [" Latest Ordinal:",0,"magenta"], ["Cluster latest known ordinal",1],
            ["  Epoc Progress:",0,"magenta"], ["Blockchain time cycle/round",1],
            ["  Snapshot Hash:",0,"magenta"], ["Latest ordinal hash value (truncated)",1],
            ["      Consensus:",0,"magenta"], ["Is this node participating in consensus rounds",1],
            ["  Cluster Start:",0,"magenta"], ["When the cluster started (or restarted)",1],
            ["    Node Uptime:",0,"magenta"], ["Amount of time node has been on the cluster",2],
        ])   
        
            
    def _print_status_output(self,profile):
        print_out_list = [
            {
                "PROFILE": self.called_profile,
                "SERVICE": self.main_output["service_state"],
                "JOIN STATE": self.main_output["join_state"],
            },
            {
                "PUBLIC API TCP":self.functions.config_obj[self.called_profile]["public_port"],
                "P2P API TCP": self.functions.config_obj[self.called_profile]["p2p_port"],
                "CLI API TCP": self.functions.config_obj[self.called_profile]["cli_port"]
            },
            {
                "LATEST ORDINAL": self.ordinal_dict.get(profile, {}).get("ordinal", False),
                "EPOC PROGRESS": self.ordinal_dict.get(profile, {}).get("epocProgress", False),
                "SNAPSHOT HASH": self.ordinal_dict.get(profile, {}).get("hash", False),
            },
            {
                "CURRENT SESSION": str(self.main_output["cluster_session"]),
                "NODE SESSION": str(self.main_output["node_session"]),
                "ON NETWORK": self.main_output["on_network"],
            },
        ]
        
        print_out_list2 = [
            {
                "CLUSTER START": self.node_cluster_times["cluster_restart_time"],
                "NODE START":  self.node_cluster_times["restart_time"],
                "SYSTEM START":  self.node_cluster_times["system_boot"],
            },
            {
                "CLUSTER UPTIME":  self.node_cluster_times["cluster_uptime"],
                "NODE UPTIME":  self.node_cluster_times["uptime"],
                "SYSTEM UPTIME:":  self.node_cluster_times["system_uptime"],
            },
        ]
        
        print_out_list3 = [
            {
                "NODE ID": self.node_id,
                "IN CONSENSUS": self.main_output["consensus_match"],
            }
        ]
        
        if self.called_command == "uptime":
            print_out_list = print_out_list2
        else:
            if self.config_obj[profile]["layer"] > 0:
                print_out_list3[0].pop("IN CONSENSUS", None)
            print_out_list = print_out_list + print_out_list2 + print_out_list3
            if self.config_obj[profile]["layer"] > 0:
                print_out_list.pop(2)
            
            self.functions.event = False  # if spinner was called stop it first.
            
        for header_elements in print_out_list:
            self.functions.print_show_output({
                "header_elements" : header_elements
            })

    
    def _print_quickstatus_output(self):
        self.functions.print_paragraphs([
            [f"{self.called_profile} State:",0,"yellow","bold"],[self.quick_state,1,"blue","bold"],
            ["nodeid:",0,"yellow"],[self.node_id,1],
            ["Last Restart:",0,"yellow"],[self.restart_time,1],
            ["Estimated Uptime:",0,"yellow"],[self.uptime,2],
        ])
        
        
if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")  
import psutil

from termcolor import colored
from concurrent.futures import ThreadPoolExecutor
from sys import exit
from datetime import datetime, timedelta
from types import SimpleNamespace


class ShowStatus():
    
    def __init__(self,parent,command_obj):
        self.parent = parent
        self.command_obj = command_obj
        self.rebuild = command_obj.get("rebuild",False)
        self.do_wait = command_obj.get("wait",True)
        self.spinner = command_obj.get("spinner",True)
        self.threaded = command_obj.get("threaded",False)
        self.static_nodeid = command_obj.get("static_nodeid",False)
        self.command_list = command_obj.get("command_list",[])
        self.log = self.parent.log.logger[self.parent.log_key]
        self.functions = self.parent.functions

    # ==== SETTERS ====

    def set_parameter(self):
        self.all_profile_request = False
        self.called_profile = self.parent.profile
        self.current_profile = False
        
        called_command = self.command_obj.get("called","default")
        if called_command == "_s": called_command = "status"
        if called_command == "_qs": called_command = "quick_status"
        if called_command == "stop": called_command = "quick_status"
        self.called_command = called_command
        
        self.profile_list = self.parent.profile_names
        self.ordinal_dict = {}        

        self.watch_enabled = True if "-w" in self.command_list else False
        self.print_title = True if "--legend" in self.command_list else False
        
        self.latest_ordinal = False  
        self.watch_enabled = False
        self.range_error = False
        self.node_id = False
        self.restart_time = False
        self.uptime = False
        self.sessions = False
        self.quick_results = False
        self.consensus_match = False
        
        self.watch_seconds = 15
        self.watch_passes = 0

    
    def set_profile(self):
        for key,value in self.command_obj.items():
            if key == "-p" and (value == "all" or value == "empty"):
                self.all_profile_request = True
                break
            if key == "-p" and value != "empty":
                self.profile_list = [value]
                self.called_profile = value
                self.functions.check_valid_profile(self.called_profile)
            
            
    def _set_service_status(self):
        self.functions.get_service_status()
            

    def _set_status_output(self):
        sessions = self.sessions
        
        on_network = colored("False","red")
        cluster_session = sessions["session0"]
        node_session = sessions["session1"]
        join_state = sessions['state1']
                        
        if sessions["session0"] == 0:
            # on_network = colored("NetworkUnreachable","red")
            on_network = colored("EdgePointDown","red")
            cluster_session = colored("SessionNotFound".ljust(20," "),"red")
            join_state = colored(f"{sessions['state1']}".ljust(20),"yellow")
        else:
            if sessions["state1"] == "ReadyToJoin":
                join_state = colored(f"{sessions['state1']}".ljust(20),"yellow")
                on_network = colored("ReadyToJoin","yellow")
            if sessions["session0"] == sessions["session1"]:
                if sessions["state1"] == "ApiNotResponding":
                    on_network = colored("TryAgainLater","magenta")
                    join_state = colored(f"ApiNotResponding".ljust(20),"magenta")
                elif sessions["state1"] == "WaitingForDownload" or sessions["state1"] == "SessionStarted":
                    join_state = colored(f"{sessions['state1']}".ljust(20),"yellow")
                    on_network = colored("True","magenta",attrs=["bold"])
                elif sessions["state1"] != "ApiNotReady" and sessions["state1"] != "Offline" and sessions["state1"] != "Initial":
                    # there are other states other than Ready and Observing when on_network
                    on_network = colored("True","green",attrs=["bold"])
                    join_state = colored(f"{sessions['state1']}".ljust(20),"green")
                    if sessions["state1"] == "Observing" or sessions["state1"] == "WaitingForReady":
                        join_state = colored(f"{sessions['state1']}".ljust(20),"yellow")
                else:
                    node_session = colored("SessionIgnored".ljust(20," "),"red")
                    join_state = colored(f"{sessions['state1']}".ljust(20),"red")
            if sessions["session0"] != sessions["session1"] and sessions["state1"] == "Ready":
                    on_network = colored("False","red")
                    join_state = colored(f"{sessions['state1']} (forked)".ljust(20),"yellow")
                            
        if sessions["session1"] == 0:
            node_session = colored("SessionNotFound".ljust(20," "),"red")
        
        if join_state == "ApiNotReady":
            join_state = colored("ApiNotReady","red",attrs=["bold"])

        return {
            "on_network": on_network,
            "cluster_session": cluster_session,
            "node_session": node_session,
            "join_state": join_state
        }
                        
                        
    def _set_ordinal_dict(self):
        self.ordinal_dict = {
            **self.ordinal_dict,
            **self.parent.show_download_status({
                "command_list": ["-p",self.current_profile],
                "caller": "status",
                "metrics": self.ordinal_dict,
            })
        }
        
        for key, value in self.ordinal_dict.items():
            if isinstance(value, int): 
                self.ordinal_dict[key] = str(value)
                    
        
    def _set_node_cluster_times(self,output):
        restart_time, uptime = self._handle_time_node_id(self.quick_results)  # localhost
        cluster_results = [None, None, output["cluster_session"]]  # cluster
        cluster_restart_time, cluster_uptime = self._handle_time_node_id(cluster_results)
                                
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
        if not "-w" in self.command_list: return
        
        try: 
            watch_seconds = self.command_list[self.command_list.index("-w")+1]
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
                
                for n, current_profile in enumerate(self.profile_list):
                    self.current_profile = current_profile
                    self._print_log_msg("info",f"show system status requested | {self.current_profile}")
                    
                    self.parent.set_profile(self.current_profile)
                    self.called_profile = self.current_profile
                            
                    # self._set_ordinal_dict()            

                    if self.called_command == "quick_status" or self.called_command == "_qs":
                        self._process_quick_status(n)
                        continue
                    
                    self.quick_results = self._get_quick_status(self.functions.config_obj[self.current_profile]["public_port"])
                    
                    if n > 0: 
                        self.print_title = False 
                        if self.all_profile_request:
                            self.spinner = False
                        print("")

                    self._set_service_status()
                    self._get_cluster_sessions()
                    self._get_cluster_consensus()
                    
                    output = self._set_status_output()
                                    
                    if not self.parent.skip_build:
                        self._handle_rebuild()
                        self._set_node_cluster_times(output)

                        if self.called_command == "alerting":
                            raise Exception(self.node_cluster_times)
                        
                        self._print_title()
                        
                        if self.parent.config_obj[self.current_profile]["environment"] not in ["mainnet","integrationnet","testnet"]:
                             self.ordinal_dict["backend"] = "N/A"
                                        
                        self._print_status_output(self.current_profile, output)
                            
                if self._handle_watch_request(None,False):            
                    break

    
    def _process_quick_status(self,n):
        if n == 0:
            self.functions.print_paragraphs([
                ["",1],[" NODE STATUS QUICK RESULTS ",2,"yellow,on_blue","bold"],
            ])                    
        quick_results = self._get_quick_status(
            self.functions.config_obj[self.called_profile]["public_port"]
        )
        self.restart_time, self.uptime = self._handle_time_node_id(quick_results)
            
        self.functions.print_paragraphs([
            [f"{self.called_profile} State:",0,"yellow","bold"],[quick_results[0],1,"blue","bold"],
            ["nodeid:",0,"yellow"],[self.node_id,1],
            ["Last Restart:",0,"yellow"],[self.restart_time,1],
            ["Estimated Uptime:",0,"yellow"],[self.uptime,2],
        ])
        
        
    # ==== GETTERS ====

    def _get_quick_status(self,port):
        quick_results = self.functions.get_api_node_info({
            "api_host": self.functions.get_ext_ip(),
            "api_port": port,
            "info_list": ["state","id","session"]
        })
        if quick_results == None:
            quick_results = ["ApiNotReady"]

        try_known_id = quick_results[1] == "unknown" if len(quick_results) > 1 else True
        if try_known_id:
            quick_results.append(self._get_nodeid())
            
        return quick_results
            
            
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
        if self.parent.config_obj[self.called_profile]["layer"] > 0:
            return
        
        try:
            self.latest_ordinal = self.parent.config_obj["global_elements"]["snapshot_cache"][self.called_profile]["latest"]
        except Exception as e:
            self._print_log_msg("error",f"_get_latest_ordinal_details --> error [{e}]")
          
        # try:
        #     ordinal_list = ["height","subHeight","ordinal"]
        #     results = self.functions.get_snapshot({
        #         "environment": self.parent.config_obj[self.called_profile]["environment"],
        #         "profile": self.called_profile,
        #         "return_values": ordinal_list,
        #         "return_type": "list",
        #     })
        #     for i,item in enumerate(ordinal_list):
        #         self.ordinal_dict[item] = str(results[i])
        #     self.ordinal_dict["backend"] = results[2]
        # except Exception as e:
        #     if isinstance(self.ordinal_dict,dict):
        #         self.ordinal_dict = {
        #             **self.ordinal_dict,
        #             "backend": "n/a"
        #         }
        #     else:
        #         self.parent.error_messages.error_code({
        #             "error_code": "cmd-261",
        #             "line_code": "api_error",
        #             "extra2": e,
        #         })
        # return
                
                
    def _get_cluster_sessions(self):
        
        # edge_point = self.functions.pull_edge_point(self.current_profile)
        # self.functions.config_obj["global_elements"]["cluster_info_lists"] = self.parent.config_obj["global_elements"]["cluster_info_lists"]
        
        # self._print_log_msg("debug","ready to pull node sessions")
        # self.sessions = self.functions.pull_node_sessions({
        #     "edge_device": edge_point,
        #     "caller": self.called_command,
        #     "spinner": self.spinner,
        #     "profile": self.called_profile, 
        #     "key": "clusterSession"
        # })
        # self.parent.config_obj["global_elements"]["cluster_info_lists"] = self.functions.config_obj["global_elements"]["cluster_info_lists"]
        # return
    
    
    def _get_cluster_consensus(self):                    
        consensus_match = self.parent.cli_check_consensus({
            "profile": self.current_profile,
            "caller": "status",
            "state": self.sessions["state1"]
        })
        if consensus_match == 0: consensus_match = 1
        
        self.consensus_match = consensus_match
                        
                        
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
                
            return        

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
         

    def _handle_time_node_id(self,elements):
        get_nodid = False
        try:
            restart_time = self.functions.get_date_time({
                "action":"session_to_date",
                "elapsed": elements[2],
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
                                            
        self.sessions["state1"] = self._get_profile_state(self.called_profile)
    
        return self._set_status_output()
            
            
    # ==== PRINTERS ====
    
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
            ["  Found Session:",0,"magenta"], ["Node's current cluster session",1],
            [" Latest Ordinal:",0,"magenta"], ["Node consensus ordinal",1],
            ["      Last DLed:",0,"magenta"], ["Last found ordinal downloaded by node",1],
            ["Blk Exp Ordinal:",0,"magenta"], ["Latest found block explorer ordinal",1],
            ["      Consensus:",0,"magenta"], ["Is this node participating in consensus rounds",1],
            ["          Start:",0,"magenta"], ["When the cluster started (or restarted)",1],
            ["         Uptime:",0,"magenta"], ["Amount of time node or Cluster has been online",2],
        ])   
        
            
    def _print_status_output(self,profile,output):
        print_out_list = [
            {
                "PROFILE": self.called_profile,
                "SERVICE": self.functions.config_obj["global_elements"]["node_service_status"][self.called_profile],
                "JOIN STATE": output["join_state"],
            },
            {
                "PUBLIC API TCP":self.functions.config_obj[self.called_profile]["public_port"],
                "P2P API TCP": self.functions.config_obj[self.called_profile]["p2p_port"],
                "CLI API TCP": self.functions.config_obj[self.called_profile]["cli_port"]
            },
            {
                "LATEST ORDINAL":self.ordinal_dict["latest"],
                "LAST DLed": self.ordinal_dict["current"],
                "BLK EXP ORDINAL": self.ordinal_dict["backend"],
            },
            {
                "CURRENT SESSION": output["cluster_session"],
                "FOUND SESSION": output["node_session"],
                "ON NETWORK": output["on_network"],
            },
        ]
        
        timers = SimpleNamespace(**self.node_cluster_times)
        print_out_list2 = [
            {
                "CLUSTER START": timers.cluster_restart_time,
                "NODE START":  timers.restart_time,
                "SYSTEM START":  timers.system_boot,
            },
            {
                "CLUSTER UPTIME":  timers.cluster_uptime,
                "NODE UPTIME":  timers.uptime,
                "SYSTEM UPTIME:":  timers.system_uptime,
            },
        ]
        
        print_out_list3 = [
            {
                "NODE ID": self.node_id,
                "IN CONSENSUS": self.consensus_match,
            }
        ]
        
        if self.called_command == "uptime":
            print_out_list = print_out_list2
        else:
            if self.parent.config_obj[profile]["layer"] > 0:
                print_out_list3[0].pop("IN CONSENSUS", None)
            print_out_list = print_out_list + print_out_list2 + print_out_list3
            if self.parent.config_obj[profile]["layer"] > 0:
                print_out_list.pop(2)
            
            self.functions.event = False  # if spinner was called stop it first.
            
        for header_elements in print_out_list:
            self.functions.print_show_output({
                "header_elements" : header_elements
            })
            
        
if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")  
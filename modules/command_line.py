import re
import base58
import psutil
import socket

from hashlib import sha256

from time import sleep, perf_counter
from datetime import datetime, timedelta
from os import system, path, get_terminal_size, popen, remove, chmod, makedirs, walk, listdir, SEEK_END, SEEK_CUR
from shutil import copy2, move
from sys import exit
from types import SimpleNamespace
from getpass import getpass
from termcolor import colored, cprint
from secrets import compare_digest
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, wait as thread_wait

from modules.p12 import P12Class
from modules.troubleshoot.snapshot import * # discover_snapshots, merge_snap_results, ordhash_to_ordhash, process_snap_files, remove_elements, clean_info, set_count_dict, custom_input, print_report
from .download_status import DownloadStatus
from .status import Status
from .node_service import Node
from .troubleshoot.errors import Error_codes
from .troubleshoot.logger import Logging
from .cleaner import Cleaner
from .troubleshoot.send_logs import Send
from .troubleshoot.ts import Troubleshooter
from .find_newest_standalone import find_newest
from .config.ipv6 import handle_ipv6
from .console import Menu

class TerminateCLIException(Exception): pass

class CLI():
    
    def __init__(self,command_obj):
        
        self.log = Logging()
        self.command_obj = command_obj

        self.profile = command_obj.get("profile",None)
        self.command_list = command_obj.get("command_list",[])
        self.profile_names = command_obj.get("profile_names",None)
        self.skip_services = command_obj.get("skip_services",False)
        self.auto_restart =  command_obj.get("auto_restart",False)
        self.caller = command_obj.get("caller","default")
        self.functions = command_obj["functions"]
        self.ip_address = command_obj["ip_address"]
        self.primary_command = self.command_obj["command"]

        self.set_variables()


    # ==========================================
    # set commands
    # ==========================================

    def set_variables(self):
        self.config_obj = self.functions.config_obj
        self.log_key = self.config_obj["global_elements"]["log_key"]
        self.version_obj = self.functions.version_obj

        self.slow_flag = False
        self.skip_version_check = False
        self.skip_build = False
        self.check_versions_called = False
        self.node_id_obj = False
        self.invalid_version = False
        self.mobile = False
        self.caller = "cli"
        self.version_class_obj = None
        self.current_try = 0
        self.max_try = 2
        
        self.error_messages = Error_codes(self.functions)  
        self.troubleshooter = Troubleshooter({
            "config_obj": self.config_obj,
        })

        if self.profile_names != None:
            self.profile_names = self.functions.clear_global_profiles(self.profile_names)

        self.skip_warning_messages = False
        if not self.auto_restart:
            try:
                if "--skip_warning_messages" in self.command_list or self.config_obj["global_elements"]["developer_mode"]:
                    self.skip_warning_messages = True 
            except:
                # install command will not have a config_obj
                self.skip_warning_messages = False
        
        if not self.skip_services:
            # try:
            # review and change to spread operator if able
            self.build_node_class()
            
        elif not self.auto_restart:
            self.functions.print_clear_line()
            self.functions.print_cmd_status({
                "text_start": "Preparing Node details",
                "text_color": "green",
                "delay": .3
            })
            self.functions.print_clear_line()
            
        self.arch = self.functions.get_distro_details()["arch"]

        if self.caller == "installer":
            return


    def build_node_class(self):
        command_obj = {
            "caller": "cli",
            "profile": self.profile,
            "command": self.primary_command,
            "argv": self.command_list,
            "ip_address": self.ip_address,
            "profile_names": self.profile_names,
            "functions": self.functions
        }
        # self.log.logger[self.log_key].debug(f"cli - calling node Obj - [{command_obj}]")
        if self.primary_command != "quiet_install":
            self.functions.print_cmd_status({
                "text_start": "Acquiring Node details"
            })
        self.node_service = Node(command_obj)
        self.node_service.log = self.functions.log
        self.node_service.functions.set_statics()


    def set_default_profile(self,node_service):
        profiles = self.functions.pull_profile({
            "req": "list",
        })
        
        if node_service:
            self.set_profile(profiles[0])
        else:
            self.profile = profiles[0]
            self.set_profile_api_ports()
            
            
    def set_profile_api_ports(self):
        self.log.logger[self.log_key].debug(f"cli - setting profile parameters | profile [{self.profile}]")
        self.service_name = self.functions.get_service_name(self.profile)
        self.api_ports = self.functions.pull_profile({
            "req": "ports",
            "profile": self.profile,
        })
                
   
    def set_data_dir(self,profile=False):
        if not profile:
            profile = self.profile
        return f"{self.functions.default_tessellation_dir}{self.profile}/data/incremental_snapshot"
    

    def set_profile(self,profile):
        self.functions.pull_profile({  # test if profile is valid
            "profile": profile,
            "req": "exists"
        })
        self.profile = profile
        self.node_service.set_profile(profile)
        self.set_profile_api_ports() 
        

    def raise_exception(self):
        self.functions.set_exception()
        raise self.functions.exception
    
    
    # ==========================================
    # show commands
    # ==========================================
    
    def show_system_status(self,command_obj):
        rebuild = command_obj.get("rebuild",False)
        do_wait = command_obj.get("wait",True)
        print_title = command_obj.get("print_title",True)
        spinner = command_obj.get("spinner",True)
        threaded = command_obj.get("threaded",False)
        static_nodeid = command_obj.get("static_nodeid",False)
        command_list = command_obj.get("command_list",[])
        
        all_profile_request = False
        called_profile = self.profile
        called_command = command_obj.get("called","default")
        
        if called_command == "uptime": print_title = False
        if called_command == "_s": called_command = "status"
        if called_command == "_qs": called_command = "quick_status"
        if called_command == "stop": called_command = "quick_status"

        self.functions.check_for_help(command_list,called_command)
        
        profile_list = self.profile_names
        ordinal_dict = {}
        
        def quick_status_pull(port):
            quick_results = self.functions.get_api_node_info({
                "api_host": self.functions.get_ext_ip(),
                "api_port": port,
                "tolerance": 1,
                "info_list": ["state","id","session"]
            })
            if quick_results == None:
                quick_results = ["ApiNotReady"]
            
            return quick_results
                
        for key,value in command_obj.items():
            if key == "-p" and (value == "all" or value == "empty"):
                all_profile_request = True
                break
            if key == "-p" and value != "empty":
                profile_list = [value]
                called_profile = value
                self.functions.check_valid_profile(called_profile)
                
        
        watch_enabled = True if "-w" in command_list else False
        watch_seconds = 15
        watch_passes = 0
        watch_enabled, range_error = False, False
        
        if "-w" in command_list:
            try: 
                watch_seconds = command_list[command_list.index("-w")+1]
                watch_seconds = int(watch_seconds)
            except: 
                if watch_seconds != "--skip_warning_messages" and watch_seconds != "-p": 
                    # watch requested with valid next option, skipping error message and using default
                    self.log.logger[self.log_key].error("invalid value for [-w] option, needs to be an integer. Using default of [6].")
                    range_error = True
                watch_seconds = 15
            watch_enabled = True
            if watch_seconds < 6:
                range_error = True
                watch_seconds = 6
                
        with ThreadPoolExecutor() as executor:
            if watch_enabled:
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
                            
            def convert_time_node_id(elements):
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
                
                if static_nodeid:
                    node_id = f"{static_nodeid[:8]}...{static_nodeid[-8:]}"
                elif self.node_id_obj:
                    node_id = self.node_id_obj[f"{profile}_short"]
                else:
                    try:
                        node_id = f"{elements[1][:8]}...{elements[1][-8:]}"
                    except:
                        try:
                            node_id = self.cli_grab_id({
                                "command": "nodeid",
                                "argv_list": ["-p",called_profile],
                                "dag_addr_only": True,
                                "ready_state": True if self.config_obj["global_elements"]["node_profile_states"][profile] == "Ready" else False
                            })
                            node_id = self.functions.cleaner(node_id,"new_line")
                            node_id = f"{node_id[:8]}...{node_id[-8:]}"
                        except:
                            node_id = "unknown"
                
                return restart_time, uptime, node_id
                        
            while True:
                if self.functions.cancel_event: exit(0)
                if watch_enabled:
                    watch_passes += 1

                    _ = self.functions.process_command({
                        "proc_action": "clear",
                    })

                    self.functions.print_paragraphs([
                        ["Press",0],["'q'",0,"yellow,on_red"], ['to quit',1],
                        ["Do not use",0],["ctrl",0,"yellow"],["and",0],["c",2,"yellow"],
                    ])
                    if range_error:
                        self.functions.print_paragraphs([
                            [" RANGE ERROR ",0,"red,on_yellow"],["using [15] second default.",2]
                        ]) 
                
                try:
                    ordinal_dict["backend"] = str(self.functions.get_snapshot({
                        "history": 1, 
                        "environment": self.config_obj[called_profile]["environment"],
                        "profile": called_profile
                    })[1])
                except Exception as e:
                    if isinstance(ordinal_dict,dict):
                        ordinal_dict = {
                            **ordinal_dict,
                            "backend": "n/a"
                        }
                    else:
                        self.error_messages.error_code({
                            "error_code": "cmd-261",
                            "line_code": "api_error",
                            "extra2": e,
                        })
                
                for n,profile in enumerate(profile_list):
                    self.log.logger[self.log_key].info(f"show system status requested | {profile}")      
                    self.set_profile(profile)
                    called_profile = profile
                                        
                    ordinal_dict = {
                        **ordinal_dict,
                        **self.show_download_status({
                            "command_list": ["-p",profile],
                            "caller": "status",
                        })
                    }
                    for key, value in ordinal_dict.items():
                        if isinstance(value, int): ordinal_dict[key] = str(value)
                    
                    if called_command == "quick_status" or called_command == "_qs":
                        if n == 0:
                            self.functions.print_paragraphs([
                                ["",1],[" NODE STATUS QUICK RESULTS ",2,"yellow,on_blue","bold"],
                            ])                    
                        quick_results = quick_status_pull(self.functions.config_obj[called_profile]["public_port"])
                        restart_time, uptime, node_id = convert_time_node_id(quick_results)
                            
                        self.functions.print_paragraphs([
                            [f"{called_profile} State:",0,"yellow","bold"],[quick_results[0],1,"blue","bold"],
                            ["nodeid:",0,"yellow"],[node_id,1],
                            ["Last Restart:",0,"yellow"],[restart_time,1],
                            ["Estimated Uptime:",0,"yellow"],[uptime,2],
                        ])
                        continue
                    
                    quick_results = quick_status_pull(self.functions.config_obj[profile]["public_port"])
                    
                    try_known_id = False
                    try:
                        if quick_results[1] == "unknown": try_known_id = True
                    except: 
                        try_known_id = True
                    
                    if try_known_id:
                        try: quick_results[1] = self.nodeid
                        except: pass
                        
                    if n > 0: 
                        print_title = False 
                        if all_profile_request:
                            spinner = False
                        print("")

                    self.functions.get_service_status()
                    edge_point = self.functions.pull_edge_point(profile)

                    self.log.logger[self.log_key].debug("show system status - ready to pull node sessions")
                    
                    sessions = self.functions.pull_node_sessions({
                        "edge_device": edge_point,
                        "caller": called_command,
                        "spinner": spinner,
                        "profile": called_profile, 
                        "key": "clusterSession"
                    })

                    consensus_match = self.cli_check_consensus({
                        "profile": self.profile,
                        "caller": "status",
                        "state": sessions["state1"]
                    })
                    if consensus_match == 0:
                        consensus_match = 1

                    def setup_output():
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
                                    on_network = colored("True","green")
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
                        
                        return {
                            "on_network": on_network,
                            "cluster_session": cluster_session,
                            "node_session": node_session,
                            "join_state": join_state
                        }
                        
                    output = setup_output()
                    clean_state = self.functions.cleaner(output["join_state"],"ansi_escape_colors")
                    self.config_obj["global_elements"]["node_profile_states"][called_profile] = clean_state  # to speed up restarts and upgrades
                    
                    if not self.skip_build:
                        if rebuild:
                            if do_wait:
                                self.functions.print_timer({
                                    "seconds":20
                                })
                                                               
                            sessions["state1"] = self.functions.test_peer_state({
                                "threaded": threaded,
                                "spinner": spinner,
                                "profile": called_profile,
                                "simple": True
                            })
                        
                            output = setup_output()
        
                        restart_time, uptime, node_id = convert_time_node_id(quick_results)  # localhost
                        cluster_results = [None, None, output["cluster_session"]]  # cluster
                        cluster_restart_time, cluster_uptime, _ = convert_time_node_id(cluster_results)
                                                
                        system_boot = psutil.boot_time()
                        system_uptime = datetime.now().timestamp() - system_boot
                        system_uptime = timedelta(seconds=system_uptime)
                        system_uptime = self.functions.get_date_time({
                            "action":"estimate_elapsed",
                            "elapsed": system_uptime,
                        })
                        system_boot = datetime.fromtimestamp(system_boot)
                        system_boot = system_boot.strftime("%Y-%m-%d %H:%M:%S")
                        
                        if called_command == "alerting":
                            return {
                                "system_boot": system_boot,
                                "system_uptime": system_uptime,
                                "restart_time": restart_time,
                                "uptime": uptime,
                                "cluster_restart_time": cluster_restart_time,
                                "cluster_uptime": cluster_uptime,
                            }
                        
                        if print_title:
                            self.functions.print_states()
                            self.functions.print_paragraphs([
                                ["Current Session:",0,"magenta"], ["The metagraph cluster session",1],
                                ["  Found Session:",0,"magenta"], ["Node's current cluster session",1],
                                [" Latest Ordinal:",0,"magenta"], ["Node consensus ordinal",1],
                                ["      Last DLed:",0,"magenta"], ["Last found ordinal downloaded by Node",1],
                                ["Blk Exp Ordinal:",0,"magenta"], ["Latest found block explorer ordinal",1],
                                ["      Consensus:",0,"magenta"], ["Is this Node participating in consensus rounds",1],
                                ["          Start:",0,"magenta"], ["When the cluster started (or restarted)",1],
                                ["         Uptime:",0,"magenta"], ["About of time Node or Cluster has been online",2],
                            ])
                        
                        if self.config_obj[profile]["environment"] not in ["mainnet","integrationnet","testnet"]:
                             ordinal_dict["backend"] = "N/A"
                                        
                        print_out_list = [
                            {
                                "PROFILE": called_profile,
                                "SERVICE": self.functions.config_obj["global_elements"]["node_service_status"][called_profile],
                                "JOIN STATE": output["join_state"],
                            },
                            {
                                "PUBLIC API TCP":self.functions.config_obj[called_profile]["public_port"],
                                "P2P API TCP": self.functions.config_obj[called_profile]["p2p_port"],
                                "CLI API TCP": self.functions.config_obj[called_profile]["cli_port"]
                            },
                            {
                                "LATEST ORDINAL":ordinal_dict["latest"],
                                "LAST DLed": ordinal_dict["current"],
                                "BLK EXP ORDINAL": ordinal_dict["backend"],
                            },
                            {
                                "CURRENT SESSION": output["cluster_session"],
                                "FOUND SESSION": output["node_session"],
                                "ON NETWORK": output["on_network"],
                            },
                        ]
                        
                        print_out_list2 = [
                            {
                                "CLUSTER START": cluster_restart_time,
                                "NODE START": restart_time,
                                "SYSTEM START": system_boot,
                            },
                            {
                                "CLUSTER UPTIME": cluster_uptime,
                                "NODE UPTIME": uptime,
                                "SYSTEM UPTIME:": system_uptime,
                            },
                        ]
                        
                        print_out_list3 = [
                            {
                                "NODE ID": node_id,
                                "IN CONSENSUS": consensus_match,
                            }
                        ]
                        
                        if called_command == "uptime":
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
                            
                if watch_enabled:
                    if self.functions.cancel_event: exit(0)
                    self.functions.print_paragraphs([
                        ["",1],["Press",0],["'q'",0,"yellow,on_red"], ['to quit',1],
                        ["Watch passes:",0,"magenta"], [f"{watch_passes}",0,"yellow"],
                        ["Intervals:",0,"magenta"], [f"{watch_seconds}s",1,"yellow"],
                    ])
                    self.functions.print_timer({
                        "p_type": "cmd",
                        "seconds": watch_seconds,
                        "step": -1,
                        "phrase": "Waiting",
                        "end_phrase": "before updating",
                    })
                else: break    
                

    def show_service_status(self,command_list):
        self.functions.check_for_help(command_list, "show_service_status")
        print_out_list = []
        service_elements = self.config_obj["global_elements"]["node_service_status"]
        for service in service_elements["service_list"]:
            service_status = service_elements[service]
            service_code = service_elements[f"{service}_service_return_code"]
            service_pid = service_elements[f"{service}_service_pid"]

            if service in self.functions.profile_names:
                title_name = service
                service_name = self.config_obj[service]["service"]
            else:
                if "node_restart" in service: 
                    title_name = "auto_restart"
                    continue # disable showing service due to false negatives
                elif "version_updater" in service: 
                    title_name = "version_service"
                    #service_name = service.replace("@","")
                    continue # disable showing service due to false negatives

            if service_code < 1:
                service_status = colored(service_status,"green",attrs=["bold"])
            elif service_code == 768:
                service_status = colored(service_status,"red")
            else:
                service_status = colored(service_status,"yellow")

            single_list = [
                {
                    "-BLANK-":None,
                    "OWNER": title_name,
                    "SERVICE": service_name,
                    "PID": service_pid,
                },
                {
                    "STATUS CODE": service_code,
                    "STATUS": service_status,
                },
            ]
            print_out_list += single_list

        for header_elements in print_out_list:
            self.functions.print_show_output({
                "header_elements" : header_elements,
            })


    def show_service_log(self,command_list):
        self.functions.check_for_help(command_list, "show_service_log")
        profile = command_list[command_list.index("-p")+1]
        service = self.functions.pull_profile({
            "req":"service",
            "profile": profile,
        })
        bash_command = f"journalctl -b -u cnng-{service} --no-pager"
        
        self.functions.print_paragraphs([
            ["",1],["SERVICE JOURNAL LOGS",1,"blue","bold"],
            ["=","half","blue","bold"],
            ["press",0], ["q",0,"yellow"],["to quit",1],
            ["press",0], ["the space bar",0,"yellow"],["to advance screens",1],
        ])
        self.functions.print_any_key({
            "prompt": "Press any key to begin",
            "color": "cyan",
        })
        _ = self.functions.process_command({
            "bashCommand": bash_command,
            "proc_action": "subprocess_run",
        })
        cprint("  Service log review complete","blue")

            
    def show_prices(self,command_list):
        self.functions.check_for_help(command_list,"price")
            
        self.log.logger[self.log_key].info(f"show prices requested")
        crypto_prices = self.functions.get_crypto_price()
        
        crypto_setup, crypto_setup2 = {}, {}
        for n, coin in enumerate(crypto_prices.keys()):
            if n < 4:
                crypto_setup = {
                    **crypto_setup,
                    f"${crypto_prices[coin]['symbol'].upper()}": crypto_prices[coin]['formatted'],
                }
            else:
                crypto_setup2 = {
                    **crypto_setup2,
                    f"${crypto_prices[coin]['symbol'].upper()}": crypto_prices[coin]['formatted'],
                }                

        print_out_list = [
            crypto_setup,
            crypto_setup2,
        ]
        
        for header_elements in print_out_list:
            self.functions.print_show_output({
                "header_elements" : header_elements
        })
            
        self.functions.print_paragraphs([
            ["",1], ["Information obtained from CoinGecko and does not represent any opinions or financial advise of or from Constellation Network.",1,"red"],
        ])


    def show_markets(self, command_list):
        self.functions.check_for_help(command_list,"markets")
        self.log.logger[self.log_key].info("show market requested")
                
        self.functions.print_cmd_status({
            "text_start": "Preparing Report, this may take a few seconds",
            "status": "running"
        })
        
        markets = self.functions.get_crypto_markets()
        if markets == 1:  # error returned
            return 1
        
        print_out_list = [
            {
                "header_elements": {
                    "Rank": markets[0]['market_cap_rank'],
                    "Name": markets[0]["name"],
                    "Symbol": markets[0]["symbol"],
                    "Price": ' ${:,.2f}'.format(markets[0]['current_price']),
                    "Market Cap": '${:,.2f}'.format(markets[0]['market_cap']),
                    "Total Supply": '{:,.2f}'.format(markets[0]['total_supply']),
                    "ATH": '${:,.2f}'.format(markets[0]['ath']),
                },
                "spacing": 5,
                "1": 15,
                "3": 10,
                "4": 20,
                "5": 20,
                
            },
        ]
        for header_elements in print_out_list:
            self.functions.print_show_output({
                "header_elements" : header_elements
        })
            
        markets.pop(0)
   
        for market in markets:
            color = "white"
            # for remove in removers:
            #     del market[remove] 
            for k,v in market.items():
                if v == "Constellation":
                    color = "green"
                if v == None:
                    market[k] = 0 
            print(colored(f"  {market['market_cap_rank']: <{5}}",color),end="")
            print(colored(f"  {market['name']: <{15}}",color),end="")
            print(colored(f"  {market['symbol']: <{5}}",color),end="")
            print(colored(f"  {' ${:,.2f}'.format(market['current_price']): <{10}}",color),end="")
            print(colored(f"  {' ${:,.2f}'.format(market['market_cap']): <{20}}",color),end="")
            print(colored(f"   {'{:,}'.format(market['total_supply']): <{20}}",color),end="")
            print(colored(f"  {'${:,.2f}'.format(market['ath']): <{5}}",color))
        
        self.functions.print_paragraphs([
            ["",1], 
            ["Information obtained from CoinGecko and does not represent any opinions or financial advise of or from Constellation Network",2,"red"],
        ])    
        
        
    def show_health(self, command_list):
        self.functions.check_for_help(command_list,"health")
        self.log.logger[self.log_key].info(f"show health requested")

        status = Status(self.functions)
        status.called_command = self.command_obj["command"]
        status.non_interactive = True if "--ni" in command_list else False
        status.execute_status()

        self.functions.print_header_title({
            "line1": "NODE BASIC HEALTH",
            "single_line": True,
            "newline": "both",
        })
        
        print_out_list = [
            {
                "header_elements" : {
                    "DISK USAGE": status.hd_space.strip("\n"),
                    "CPU USAGE": status.usage,
                    "UPTIME_DAYS": status.system_up_time,
                },
                "spacing": 15,
            },
            {
                "header_elements" : {
                    "MEMORY": status.memory,
                    "MEMORY %": f"{status.memory_percent}%",
                    "SWAP": status.swap,
                },
                "spacing": 15,
            },
        ]
        
        for n, profile in enumerate(status.profile_sizes.keys()):
            dyn_dict = {}
            section_dict = {}

            size_list = status.profile_sizes[profile]

            profile_title = "PROFILE" if n == 0 else "\n  PROFILE"
            print_out_list.append({
                "header_elements": {profile_title: colored(profile,'green',attrs=['bold'])},
                "spacing": 15
            })
            
            while True:
                if len(size_list) > 0:
                    for _ in range(0,4):
                        if len(size_list) == 0:
                            break
                        tup = size_list.pop()
                        section_dict[tup[0].upper().replace("DIRECTORY_","")] = tup[1]
                    dyn_dict["header_elements"] = section_dict
                    dyn_dict["spacing"] = 15
                    print_out_list.append(dyn_dict)
                    section_dict = {}; dyn_dict = {}
                else:
                    break

            for key, value in status.process_memory.items():
                if key == profile:
                    if "-1" in value["RSS"]: value["RSS"] = "not running"
                    if "-1" in value["VMS"]: value["VMS"] = "not running"
                    dyn_dict["header_elements"] = {
                        "JAR PROCESS": value["jar_file"],
                        "RSS": value["RSS"],
                        "VMS": value["VMS"],
                    }
                    dyn_dict["spacing"] = 15
                    print_out_list.append(dyn_dict)
            
        for header_elements in print_out_list:
            self.functions.print_show_output({
                "header_elements" : header_elements
        })
    

    def show_cpu_memory(self, command_list):
        self.functions.check_for_help(command_list,"show_cpu_memory")
        
        ave_cpu_list = []
        ave_mem_list = []

        self.log.logger[self.log_key].info(f"show cpu and memory stats")

        def remove_highest_lowest(value_list):
            lowest = min(value_list)
            highest = max(value_list)
            lowest_index = value_list.index(lowest)
            highest_index = value_list.index(highest)

            # Remove one occurrence of the lowest and highest values
            if lowest_index < highest_index:
                value_list.pop(highest_index)
                value_list.pop(lowest_index)
            else:
                value_list.pop(lowest_index)
                value_list.pop(highest_index)

            return value_list

        status_obj = {
            "text_start": f"Calculating cpu/memory stats",
            "status": "running",
            "status_color": "yellow",
            "newline": True,
        }
        self.functions.print_cmd_status(status_obj)
        for n in range(1,11):
            self.functions.print_cmd_status({
                "text_start": "Gathering stats over",
                "brackets": f"0{n} of 10" if n < 10 else f"{n} of 10",
                "text_end": "iterations",
                "newline": False,
                "status": "calculating",
                "status_color": "yellow",
            })
            cpu_ok, memory_ok, details = self.functions.check_cpu_memory_thresholds()
            details = SimpleNamespace(**details)
            ave_cpu_list.append(details.thresholds['cpu_percent'])
            ave_mem_list.append(details.thresholds['mem_percent'])
            sleep(.5)

        print(f"\033[1A", end="", flush=True)
        self.functions.print_cmd_status({
            **status_obj,
            "status": "completed",
            "status_color": "green",
            "newline": True,
        })
        self.functions.print_clear_line()

        cpu_thresholds = deepcopy(ave_cpu_list)
        ave_cpu_set = set(ave_cpu_list)
        if len(ave_cpu_set) > 3:
            cpu_thresholds = remove_highest_lowest(cpu_thresholds)

        mem_thresholds = deepcopy(ave_mem_list)
        ave_mem_set = set(ave_mem_list)
        if len(ave_mem_set) > 3:
            mem_thresholds = remove_highest_lowest(mem_thresholds)

        details.thresholds['cpu_percent'] = round(sum(cpu_thresholds) / len(cpu_thresholds),2)
        details.thresholds['mem_percent'] = round(sum(mem_thresholds) / len(mem_thresholds),2)
        cpu_ok = True if details.thresholds['cpu_percent'] < details.thresholds['cpu_threshold'] else False
        memory_ok = True if details.thresholds['mem_percent'] < details.thresholds['mem_threshold'] else False

        cpu_status = colored("PROBLEM","red")
        cpu_percent = colored(f"{details.thresholds['cpu_percent']}%","red")
        if cpu_ok:
            cpu_status = colored("OK","green")
            cpu_percent = colored(f"{details.thresholds['cpu_percent']}%","green")

        memory_status = colored("PROBLEM","red")
        memory_percent = colored(f"{details.thresholds['mem_percent']}%","red")  
        if memory_ok:
            memory_status = colored("OK","green")
            memory_percent = colored(f"{details.thresholds['mem_percent']}%","green")

        self.functions.print_header_title({
            "line1": "NODE MEMORY AND CPU",
            "single_line": True,
            "newline": "both",
        })

        print_out_list = [
            {
                "header_elements": {
                    "CURRENT CPU": f"{cpu_percent: <25}",
                    "THRESHOLD": f"{details.thresholds['cpu_threshold']}%",
                    "CPU": cpu_status,
                },
                "spacing": 16,
            },
            {
                "header_elements": {
                    "CURRENT MEMORY":f"{memory_percent: <25}",
                    "THRESHOLD": f"{details.thresholds['mem_threshold']}%",
                    "MEMORY": memory_status,
                },
                "spacing": 16,
            },
        ]

        for header_elements in print_out_list:
            self.functions.print_show_output({
                "header_elements" : header_elements
            })

        self.functions.print_paragraphs([
            ["",1],["Individual Iterations Results:",1,"blue","bold"],
        ])
        for n, value in enumerate(ave_mem_list):
            self.functions.print_cmd_status({
                "text_start": "Pass",
                "brackets": f"0{n+1}" if n < 9 else str(n+1),
                "text_end": "cpu / mem",
                "status": f"{str(ave_cpu_list[n])}% / {str(value)}%",
                "status_color": "yellow",
                "newline": True,
            })


    def show_peers(self,command_list):
        self.functions.check_for_help(command_list,"peers")
        self.log.logger[self.log_key].info(f"show peers requested")
        profile = command_list[command_list.index("-p")+1]
        count_args = ["-p", profile]
        sip = {}
        nodeid = csv_file_name = ""
        is_basic = create_csv = False
        state, i_state = False, False
        
        if "--csv" in command_list:
            if not "--output" in command_list:
                self.functions.print_paragraphs([
                    [" NOTE ",0,"blue,on_yellow"], 
                    ["The",0],["--csv",0,"yellow","bold"],
                    ["option will default to include:",0],["--extended",2,"yellow","bold"],
                ])
            create_csv = True 
            if "--output" in command_list:
                csv_file_name = command_list[command_list.index("--output")+1]
                if "/" in csv_file_name:
                    self.error_messages.error_code_messages({
                        "error_code": "cmd-442",
                        "line_code": "invalid_output_file",
                        "extra": csv_file_name
                    })
            else:
                prefix = self.functions.get_date_time({"action": "datetime"})
                csv_file_name = f"{prefix}-peers-data.csv"
                
            if "--basic" in command_list: 
                command_list.remove("--basic")
            command_list.extend(["--extended","-np"])
            csv_path = f"{self.config_obj[profile]['directory_uploads']}{csv_file_name}"
            
        do_more = False if "-np" in command_list else True
        if do_more:
            console_size = get_terminal_size()
            more_break = round(console_size.lines)-20 
            if "--extended" in command_list:
                more_break = round(more_break/3) 
        
        if "-t" in command_list:
            sip = self.functions.get_info_from_edge_point({
                "profile": self.profile,
                "caller": "show_peers",
                "specific_ip": command_list[command_list.index("-t")+1],
            })
            count_args.extend(["-t",sip])
        else:
            sip = self.functions.get_info_from_edge_point({
                "profile": profile,
                "caller": "show_peers",
            })
                    
        if "-c" in command_list:
            self.cli_find(count_args)
            return
        
        if "--state" in command_list:
            i_state = command_list[command_list.index("--state")+1]
            states = self.functions.get_node_states("on_network_and_stuck")
            state = next((s[0] for s in states if i_state == s[1].replace("*", "")), False)

            if not state:
                self.error_messages.error_code_messages({
                    "error_code": "cli-1008",
                    "line_code": "invalid_option",
                    "extra": i_state,
                    "extra2": "supported states: dip, ob, wfd, wfr, wfo, and wfd",
                })
        
        try:
            if sip["ip"] == "self": sip["ip"] = self.functions.get_ext_ip()
        except: 
            try:
                sip["ip"] = self.functions.get_ext_ip()
            except:
                self.error_messages.error_code_messages({
                    "error_code": "cli-996",
                    "line_code": "off_network",
                    "extra": f'{self.config_obj[profile]["edge_point"]}:{self.config_obj[profile]["edge_point_tcp_port"]}',
                    "extra2": self.config_obj[profile]["layer"],
                })
    
        peer_results = self.node_service.functions.get_peer_count({
            "peer_obj": sip, 
            "profile": profile, 
            "compare": True
        })

        if peer_results == "error":
            self.log.logger[self.log_key].error(f"show peers | attempt to access peer count with ip [{sip}] failed")
            self.error_messages.error_code_messages({
                "error_code": "cmd-179",
                "line_code": "ip_not_found",
                "extra": sip,
                "extra2": None
            })     

        lookup = "peer_list"
        search_title = "all peers"
        if i_state:
            search_title = state
            lookup = f"{state.lower()}"
            
        self.functions.print_header_title({
            "line1": f"SHOW PEERS - {search_title}",
            "single_line": True,
            "newline": "both"  
        })     

        print_out_list = [
            {
                "PROFILE": profile,
                "SEARCH NODE IP": sip["ip"],
                "SN PUBLIC PORT": sip['publicPort']
            },
        ]
        
        for header_elements in print_out_list:
            self.functions.print_show_output({
                "header_elements" : header_elements
            })  

        if sip["ip"] == "127.0.0.1":
            sip["ip"] = self.ip_address

        print_header = True
        peer_title1 = colored("NETWORK PEER IP","blue",attrs=["bold"])
        peer_title2 = colored("NODE ID","blue",attrs=["bold"])
        peer_title3 = colored("WALLET","blue",attrs=["bold"])
        status_header = f"  {peer_title1: <36}"
        if "--basic" in command_list:
            is_basic = True
        else:
            status_header += f"{peer_title2: <36}"
            status_header += f"{peer_title3: <36}"

        for item, peer in enumerate(peer_results[lookup]):
            public_port = peer_results["peers_publicport"][item]
            
            if not is_basic:
                nodeid = self.cli_grab_id({
                    "dag_addr_only": True,
                    "command": "peers",
                    "argv_list": ["-p",profile,"-t",peer,"--port",public_port,"-l"]
                })
                if isinstance(nodeid,list):
                    nodeid = "UnableToReach"
                    wallet = "UnableToReach"
                else:
                    wallet = self.cli_nodeid2dag([nodeid, "return_only"])
                
            if do_more and item % more_break == 0 and item > 0:
                more = self.functions.print_any_key({
                    "quit_option": "q",
                    "newline": "both",
                })
                if more: break
                print_header = True
                
            print_peer = f"{peer}:{public_port}" 
            if "--extended" in command_list:
                status_results  = f"  {colored('PEER IP:','blue',attrs=['bold'])} {print_peer}\n"                      
                status_results += f"  {colored(' WALLET:','blue',attrs=['bold'])} {wallet}\n"                      
                status_results += f"  {colored('NODE ID:','blue',attrs=['bold'])} {nodeid}\n" 
                if create_csv:
                    csv_header = ["Peer Ip","Wallet","Node Id"]
                    csv_row = [print_peer,wallet,nodeid]
                    if item == 0:
                        self.functions.create_n_write_csv({
                        "file": csv_path,
                        "row": csv_header
                        })
                    self.functions.create_n_write_csv({
                        "file": csv_path,
                        "row": csv_row
                    })
                        
            elif is_basic:
                spacing = 23
                status_results = f"  {print_peer: <{spacing}}"                        
            else:
                spacing = 23
                if nodeid != "UnableToReach": nodeid = f"{nodeid[0:8]}....{nodeid[-8:]}"
                if nodeid != "UnableToReach": wallet = f"{wallet[0:8]}....{wallet[-8:]}"
                status_results = f"  {print_peer: <{spacing}}"                      
                status_results += f"{nodeid: <{spacing}}"                      
                status_results += f"{wallet: <{spacing}}"        
  
            if create_csv and item == 0:
                print("")
                self.functions.print_cmd_status({
                    "text_start": "Creating",
                    "brackets": csv_file_name,
                    "text_end": "file",
                    "status": "running",
                    "newline": True,
                })
            elif not create_csv:
                if print_header:    
                    print(status_header)
                    print_header = False
                print(status_results)
        
        if create_csv: 
            self.log.logger[self.log_key].info(f"csv file created: location: [{csv_file_name}]") 
            self.functions.print_paragraphs([
                ["CSV created successfully",1,"green","bold"],
                ["filename:",0,], [csv_file_name,1,"yellow","bold"],
                ["location:",0,], [self.config_obj[profile]['directory_uploads'],1,"yellow","bold"]
            ])  


    def show_ip(self,argv_list):
        self.log.logger[self.log_key].info(f"whoami request for password initiated.")
        ip_address = self.ip_address
        
        if "-id" in argv_list:
            if "-p" in argv_list: # only required for "-id"
                profile = argv_list[argv_list.index("-p")+1]
                id = argv_list[argv_list.index("-id")+1]
                try:
                    list = self.functions.get_cluster_info_list({
                        "ip_address": self.config_obj[profile]["edge_point"],
                        "port": self.config_obj[profile]["edge_point_tcp_port"],
                        "api_endpoint": "/cluster/info",
                        "error_secs": 3,
                        "attempt_range": 3,
                    })   
                except Exception as e:
                    self.log.logger[self.log_key].error(f"request to find node id request failed | error [{e}]")
                    argv_list.append("help")
                                
                try:
                    for item in list:
                        if item["id"] == id:
                            ip_address = colored(item["ip"],"yellow")
                            break
                except:
                    ip_address = colored("nodeid not found","red")    
            else: 
                argv_list.append("help")    
        
        self.functions.check_for_help(argv_list,"whoami")
            
        print_out_list = [
            {
                "IP ADDRESS".ljust(30): str(ip_address),
            },
        ]
    
        for header_elements in print_out_list:
            self.functions.print_show_output({
                "header_elements" : header_elements
            })  
            
            
    def show_security(self, command_list):
        self.functions.check_for_help(command_list,"sec")
        self.log.logger[self.log_key].info(f"Show security request made.")
        
        with ThreadPoolExecutor() as executor:
            self.functions.event = True
            _ = executor.submit(self.functions.print_spinner,{
                "msg": f"Reviewing [VPS security], please wait ",
                "color": "magenta",
            })              
            status = Status(self.functions)
            status.called_command = self.command_obj["command"]
            status.execute_status()
            self.functions.event = False

        print_out_list = [
            {
                "header_elements" : {
                    "LOG ERRORS": status.error_auths_count,
                    "ACCESS ACCEPTED": status.accepted_logins,
                    "ACCESS DENIED": status.invalid_logins,
                    "MAX EXCEEDED": status.max_auth_attempt_count,
                    "PORT RANGE": status.port_range,
                },
                "spacing": 18
            },
        ]
        
        for header_elements in print_out_list:
            self.functions.print_show_output({
                "header_elements" : header_elements
        })                        
        
        self.functions.print_paragraphs([
            ["AUTHORIZATION LOG DETAILS",1,"blue","bold"],
            ["=","full","blue","bold"],["",1],
            [f"Since: {status.creation_time}",2,"magenta","bold"],
        ])    
        for line in status.accepted_list:
            cprint(f"  {line}","cyan")           
            
            
    def show_logs(self,command_list):  
        self.log.logger[self.log_key].debug("show logs invoked")
        self.functions.check_for_help(command_list,"logs")

        profile = self.functions.default_profile
        possible_logs = [
            "nodectl","auto_restart","versioning",
            "app", "http", "gossip", "transactions"
        ]

        name = command_list[command_list.index("-l")+1] if "-l" in command_list else "empty"
        self.log.logger[self.log_key].info("show log invoked")

        if name != "empty":
            if name not in possible_logs:
                self.functions.print_help({
                    "usage_only": True,
                    "hint": "Did you include the '-l' switch?"
                })
            file_path = f"/var/tessellation/{profile}/logs/{name}.log"
            if name in ["nodectl","auto_restart","versioning"]:
                if name == "nodectl":
                    file_path = f"{self.functions.nodectl_path}logs/nodectl.log"
                else:
                    file_path = f"{self.functions.nodectl_path}logs/nodectl_{name}.log"
        else:
            self.log.logger[self.log_key].info(f"show log invoked")
            
            self.functions.print_header_title({
                "line1": "SHOW LOGS",
                "clear": True,
            })
            
            t_options = [
                "nodectl log","auto_restart log","versioning log",
                "Tessellation app log","Tessellation http log",
                "Tessellation gossip log","Tessellation transaction log"
            ]
            option = self.functions.print_option_menu({
                "options": t_options,
                "let_or_num": "number",
                "return_value": False,
            })
                
            option_match = {
                "1": f"{self.functions.nodectl_path}logs/nodectl.log",
                "2": f"{self.functions.nodectl_path}logs/nodectl_auto_restart.log",
                "3": f"{self.functions.nodectl_path}logs/nodectl_versioning.log",
                "4": f"/var/tessellation/{profile}/logs/app.log",
                "5": f"/var/tessellation/{profile}/logs/http.log",
                "6": f"/var/tessellation/{profile}/logs/gossip.log",
                "7": f"/var/tessellation/{profile}/logs/transactions.log",
            }    
            file_path = option_match.get(option) 

        self.functions.print_paragraphs([
            ["",1],["shift + g",0,"yellow"],["Move to the end of the file and follow.",1],
            ["        q",0,"yellow"],["quit out of the log viewer",2],
        ])
        _ = self.functions.print_any_key({})
        system(f"lnav {file_path}")     

        
    def show_list(self,command_list):
        self.log.logger[self.log_key].info(f"Request for list of known profiles requested")
        self.functions.check_for_help(command_list,"list")
        
        profile_only = True if "-p" in command_list else False
        
        coins = self.functions.get_local_coin_db()

        self.functions.print_clear_line()
        self.functions.print_header_title({
            "line1": "CURRENT LOADED CLUSTERS",
            "line2": "Based on local Node's config",
            "newline": "top",
            "upper": False,
        })
        
        profile_details = self.functions.pull_profile({
            "req": "list_details",
            "profile": None,
        })
        
        profile_names = profile_details["profile_names"]
        profile_descr = profile_details["profile_descr"]
        profile_services = profile_details["profile_services"]
        metagraph_name = profile_details["metagraph_name"]
        profile_layers = profile_details["layer_list"]
        
        if profile_only:
            cprint("  PROFILE NAMES ON NODE","blue",attrs=["bold"])
            for profile in profile_names:
                cprint(f"  {profile}","cyan")
            return           
                
        for n,profile in enumerate(profile_names):
            self.profile = profile
            self.set_profile_api_ports()

            try:
                for coin in coins:
                    if coin["id"] == self.functions.config_obj[profile]['token_coin_id']:
                        ticker = coin["symbol"]
            except:
                ticker = " --"

            if n > 0:
                self.functions.print_paragraphs([
                    ["-","half","blue","bold"],["",1],
                ])
                
            mc_key = "CLUSTER" if metagraph_name == "hypergraph" else "METAGRAPH"

            print_out_list = [
                {
                    f"{mc_key}": metagraph_name,
                    "ENVIRONMENT": self.functions.config_obj[profile]["environment"],
                    "PROFILE NAME": profile,
                },
                {
                    "SERVICE NAME": profile_services[n],
                    "BLOCKCHAIN LAYER": profile_layers[n],
                    "TOKEN": f"${ticker.upper()}",
                },
                {
                    "PROFILE DESCRIPTION": profile_descr[n],
                },
                {
                    "PUBLIC API TCP":self.functions.config_obj[profile]["public_port"],
                    "P2P API TCP": self.functions.config_obj[profile]["p2p_port"],
                    "CLI API TCP": self.functions.config_obj[profile]["cli_port"]
                },
            ]
            
            for header_elements in print_out_list:
                self.functions.print_show_output({
                    "header_elements" : header_elements
                })
                        
            seed_path = self.config_obj[profile]["seed_path"]
            if self.config_obj[profile]["seed_path"] == "disable":
                seed_path = "disabled"
                
            pro_rating_path = self.config_obj[profile]["pro_rating_path"]    
            if self.config_obj[profile]["pro_rating_path"] == "disable":
                pro_rating_path = "disabled"
                
            priority_path = self.config_obj[profile]["priority_source_path"]
            if self.config_obj[profile]["priority_source_path"] == "disable":
                priority_path = "disabled"
                
            self.functions.print_paragraphs([
                ["",1],
                ["SEED LIST DETAILS",1,"blue","bold"],
                [seed_path,1,"yellow"],
                ["PRIORITY SOURCE LIST DETAILS",1,"blue","bold"],
                [priority_path,1,"yellow"],
                ["RATINGS LIST DETAILS",1,"blue","bold"],
                [pro_rating_path,2,"yellow"],
                ["METAGRAPH CUSTOM VALUES",1,"blue","bold"],
            ])

            self.functions.print_paragraphs([
                ["developer mode:",0,"cyan","bold"], ["enabled:",0], [str(self.config_obj['global_elements']['developer_mode']),1,"yellow"],
            ])

            for n, args_envs in enumerate(["custom_args","custom_env_vars"]):
                    print_enabled = True
                    a_type = "arguments" if n < 1 else "environment variables"
                    for custom in profile_details["custom_values"][args_envs]:
                        if profile == custom[0]:
                            if print_enabled:
                                print_enabled = False
                                self.functions.print_paragraphs([
                                    [f"{a_type}:",0,"cyan","bold"],
                                    ["enabled:",0],
                                    [str(custom[2]).strip("/n"),1,"yellow"]
                                ])
                            else:
                                self.functions.print_paragraphs([
                                    [str(custom[1]),0,"yellow"],["=",0],
                                    [str(custom[2]).strip("/n"),1],
                                ])       
            
            print(" ") # spacer

        self.functions.print_paragraphs([
            ["Note:",0,"yellow"], ["port configurations are for the local Node only.",0,"magenta"],
            ["API ports are per Node customizable.",1,"magenta"],
            ["sudo nodectl configure",2,"cyan","bold"],
        ])

        self.show_distro_elements(["list"])


    def show_distro_elements(self,command_list):
        self.functions.check_for_help(command_list,"show_distro")
        distro_items = self.functions.get_distro_details()
        print_out_list = [
            {
                "header_elements": {
                    "DISTRIBUTION": distro_items["description"],
                    "ARCHITECTURE": distro_items['arch'],
                    "CODE NAME": distro_items["codename"],
                    
                },
                "spacing": 19,
            },
        ]
        if not "list" in command_list: 
            print_out_list.append({
                "header_elements": {
                    "BRAND": distro_items["info"]["brand_raw"],
                },
                "spacing": 19,
            })
            print_out_list.append({
                "header_elements": {
                    "CPU COUNT": distro_items["info"]["count"],
                    "ARCH BITS": distro_items["info"]["bits"],
                    "VENDOR ID": distro_items["info"]["vendor_id_raw"],
                },
                "spacing": 19,
            })
            print_out_list.append({
                "header_elements": {
                    "CPU MODEL": distro_items["info"]["model"],
                    "CPU FAMILY": distro_items["info"]["family"],
                },
                "spacing": 19,
            })
            print_out_list.append({
                "header_elements": {
                    "L1 DATA CACHE": self.functions.set_byte_size(distro_items["info"]["l1_data_cache_size"]),
                    "L1 INST CACHE": self.functions.set_byte_size(distro_items["info"]["l1_instruction_cache_size"]),
                    "WSL": f'{distro_items["info"]["wsl"]}'
                },
                "spacing": 19,
            })
            print_out_list.append({
                "header_elements": {
                    "L3 CACHE": self.functions.set_byte_size(distro_items["info"]["l3_cache_size"]),
                    "L2 CACHE": self.functions.set_byte_size(distro_items["info"]["l2_cache_size"]),
                },
                "spacing": 19,
            })

        for header_elements in print_out_list:
            self.functions.print_show_output({
                "header_elements" : header_elements
            })


    def show_node_states(self,command_list):
        self.log.logger[self.log_key].info(f"Request to view known Node states by nodectl")
        self.functions.check_for_help(command_list,"show_node_states")
        states = self.functions.get_node_states()
        
        print(f'  {colored("*","white",attrs=["bold"])} {colored("nodectl only state".ljust(30),"cyan")}')
        
        # doesn't use the 'print_show_output' because of unique nature
        # of the command
        header_elements = {
            "NODE STATES".ljust(18): states[0][0],
            "NODECTL ABBREVIATION".ljust(18): states[0][1][:-1],
        }
     
        status_header, status_results = "",""
        for header, value in header_elements.items():
            status_header += colored(f"  {header: <22}","blue",attrs=["bold"])
            status_results += f"  {str(value): <22.15}"
                            
        print(status_header.rjust(28))
        print(status_results)

        nodectl_only = self.functions.get_node_states("nodectl_only",True)
        states.pop(0)
        for value in states:
            print_value = value[1]
            if value[0] in nodectl_only:
                print_value = f"{value[1]}*"
            
            print(f"  {str(value[0]): <22}  {str(print_value[:-1]): <22}") 
        print("")            
            

    def show_seedlist_participation(self,command_list):
        self.functions.check_for_help(command_list,"check_seedlist_participation")
        
        for profile in self.profile_names:
            if path.exists(self.config_obj[profile]["seed_path"]):
                found_list = list(); not_found_list = list()
                for n in range(0,2):
                    cluster_ips = self.functions.get_cluster_info_list({
                        "ip_address": self.config_obj[profile]["edge_point"],
                        "port": self.config_obj[profile]["edge_point_tcp_port"],
                        "api_endpoint": "/cluster/info",
                        "error_secs": 3,
                        "attempt_range": 3,
                    })   
                    try:
                        count = cluster_ips.pop()   
                    except Exception as e:
                        if n > 0:
                            self.error_messages.error_code_messages({
                                "error_code": "cli-1497",
                                "line_code": "lb_not_up",
                                "extra": f'{self.config_obj[profile]["edge_point"]}:{self.config_obj[profile]["edge_point_tcp_port"]}',
                                "extra2": self.config_obj[profile]["layer"],
                            })
                        self.log.logger[self.log_key].warning("cli -> show_seedlist_participation -> LB may not be accessible, trying local.")
                        self.config_obj[profile]["edge_point"] = self.functions.get_ext_ip()
                        self.config_obj[profile]["edge_point_tcp_port"] = self.config_obj[profile]["public_port"]
                        self.config_obj[profile]["static_peer"] = True 
                                            
                count["seedlist_count"] = 0
                with open(self.config_obj[profile]["seed_path"],"r") as seed_file:
                    for line in seed_file:
                        found = False
                        line = line.strip("\n")
                        count["seedlist_count"] += 1
                        for cluster_ip in cluster_ips:
                            if line == cluster_ip["id"]:
                                id = f"{cluster_ip['id'][0:12]}...{cluster_ip['id'][-12:]}"
                                found_list.append(f"{cluster_ip['ip']} -> {id}")
                                found = True
                        if not found:
                            id = f"{line[0:12]}...{line[-12:]}"
                            not_found_list.append(id)
                        
                try:
                    first = not_found_list.pop()
                except:
                    first = colored(f"perfect attendance","green",attrs=["bold"])

        
                print_out_list = [
                    {
                        "header_elements": {
                        "PROFILE NAME": profile,
                        "ON_LINE": count["nodectl_found_peer_count"],
                        "SEED COUNT": count["seedlist_count"],
                        "MISSING NODEIDs": len(not_found_list)+1,                            
                        },
                        "spacing": 14,
                    },
                    {
                        "MISSING LIST": first
                    },
                ]
                
                for header_elements in print_out_list:
                    self.functions.print_show_output({
                        "header_elements" : header_elements,
                    })   
                    
                for line in not_found_list:
                    print(f"  {line}")
                
                print(" ") # spacer        
                    
        
    def show_current_snapshot_proofs(self,command_list):
        self.log.logger[self.log_key].info("show current snapshot proofs called")
        if "-p" in command_list:
            self.profile = command_list[command_list.index("-p")+1]
            self.log.logger[self.log_key].debug(f"show current snapshot proofs using profile [{self.profile}]")
        else: command_list.append("help")
        if not self.auto_restart: self.functions.check_for_help(command_list,"current_global_snapshot")
        
        more_break = 1
        print_title = False
        do_more = True

        if "-np" in command_list or "--np" in command_list:
            do_more = False
        if do_more:
            console_size = get_terminal_size()
            more_break = round((console_size.lines-20)/6)
                    
        snap_obj = {
            "lookup_uri": f'http://127.0.0.1:{self.config_obj[self.profile]["public_port"]}',
            "header": "json",
            "get_results": "proofs", 
            "return_type": "raw",
            "profile": self.profile,     
        }
        
        # get state here first
        state = self.functions.test_peer_state({
            "profile": self.profile,
            "simple": True
        })
        if state != "Ready":
            self.functions.print_paragraphs([
                [f" {self.profile} ",0,"yellow,on_red"], ["not in Ready state.",1,"red"],
                ["state found:",0], [state,1,"yellow"],
                ["Please join the cluster first...",1],
            ])
            exit(0)
                
        results = self.functions.get_snapshot(snap_obj)
        try:
            for n, result in enumerate(results):
                if do_more and n % more_break == 0 and n > 0:
                    more = self.functions.print_any_key({
                        "quit_option": "q",
                        "newline": "both",
                    })
                    print_title = True
                    if more:
                        break     
                if result == results[0] or print_title:           
                    self.functions.print_paragraphs([
                        ["SNAPSHOT SIGNATURES IN CURRENT GLOBAL SNAPSHOT BEING PROCESSED ON NODE",2,"green"]
                    ])
                    print_title = False
                self.functions.print_paragraphs([
                    ["SnapShot Transaction Id:",1,"blue","bold"], [result["id"],1,"yellow"],
                    ["SnapShot Transaction Sig:",1,"blue","bold"], [result["signature"],2,"yellow"],
                ])
        except Exception as e:
            self.log.logger[self.log_key].error(f"show_current_snapshot_proofs -> unable to process results [{e}]")
            self.functions.print_paragraphs([
                ["Unable to parse any transactions",1,"red"],
            ])
            results = []

        self.functions.print_paragraphs([
            ["Transactions Found:",0],[str(len(results)),1,"green","bold"],
        ])
        
        
    def show_download_status(self,command_obj):
        self.functions.check_for_help(self.command_list,"download_status")

        download_status = DownloadStatus({
            "parent": self,
            "command_obj": command_obj,
        })
        
        if command_obj["caller"] == "status":
            ds = download_status.download_status_process()
            return ds
        download_status.download_status()
            
                       
    def show_current_rewards(self,command_list):
        self.functions.check_for_help(command_list,"show_current_rewards") 
        reward_amount = dict()
        color = "red"
        found = "FALSE"
        title = "NODE P12"
        profile = self.functions.default_profile
        snapshot_size = command_list[command_list.index("-s")+1] if "-s" in command_list else 50
        target_dag_addr, create_csv = False, False

        def send_error(code, line="input_error", extra=None, extra2=None):
            self.error_messages.error_code_messages({
                "error_code": code,
                "line_code": line,
                "extra": extra,
                "extra2": extra2,
            })   

        try:
            if int(snapshot_size) > 375 or int(snapshot_size) < 1:
                self.functions.print_paragraphs([
                    [" INPUT ERROR ",0,"white,on_red"], ["the",0,"red"],
                    ["-s",0], ["option in the command",0,"red"], ["show_current_rewards",0], 
                    ["must be in the range between [",0,"red"], ["10",-1,"yellow","bold"], ["] and [",-1,"red"],
                    ["375",-1,"yellow","bold"], ["], please try again.",-1,"red"],["",2],
                ])
                cprint("  show_current_reward -s option must be in range between [10] and [375]","red",attrs=["bold"])
                return
        except:
            send_error("cmd-825")
        
        data = self.get_and_verify_snapshots(snapshot_size, self.config_obj[profile]["environment"],profile)        
            
        if "-p" in command_list:
            profile = command_list[command_list.index("-p")+1]
            self.functions.check_valid_profile(profile)
            
        if "-w" in command_list:
            search_dag_addr = command_list[command_list.index("-w")+1]
            self.functions.is_valid_address("dag",False,search_dag_addr)
            title = "REQ WALLET"
        elif self.node_id_obj:
            search_dag_addr = self.node_id_obj[f"{profile}_wallet"]
        else:
            self.cli_grab_id({
                "dag_addr_only": True,
                "command": "dag",
                "argv_list": ["-p",profile]
            })
            search_dag_addr = self.nodeid.strip("\n")
            search_dag_addr = self.cli_nodeid2dag([search_dag_addr,"return_only"])

        if "--target" in command_list or "-t" in command_list:
            try:
                target_dag_addr = command_list[command_list.index("-t")+1]
            except:
                try:
                    target_dag_addr = command_list[command_list.index("--target")+1]
                except:
                    send_error("cmd-1741","input_error","target","must be a valid DAG wallet address")

        if "--csv" in command_list:
            self.functions.print_cmd_status({
                "text_start": "Create csv for",
                "brackets": "show current rewards",
                "status": "running"
            })
            create_csv = True 
            if "-np" not in command_list:
                command_list.append("-np")
            if "--output" in command_list:
                csv_file_name = command_list[command_list.index("--output")+1]
                if "/" in csv_file_name:
                    send_error("cmd-442","invalid_output_file",csv_file_name)

            else:
                prefix = self.functions.get_date_time({"action": "datetime"})
                csv_file_name = f"{prefix}-{search_dag_addr[0:8]}-{search_dag_addr[-8:]}-rewards-data.csv"
            csv_path = f"{self.config_obj[profile]['directory_uploads']}{csv_file_name}"


        for rewards in data["data"]:
            for reward in rewards["rewards"]:
                if reward["destination"] in reward_amount:
                    reward_amount[reward["destination"]] += reward["amount"]
                    color = "green"; found = "TRUE"
                else:
                    reward_amount[reward["destination"]] = reward["amount"]

        if target_dag_addr:
            for target in reward_amount.keys():
                if target == target_dag_addr:
                    first = [target, reward_amount[target]]
                    break
        else:
            try:
                first = reward_amount.popitem()  
            except:
                first = [0,0]

        title = f"{title} ADDRESS FOUND ({colored(found,color)}{colored(')','blue',attrs=['bold'])}"   
        
        elapsed = self.functions.get_date_time({
            "action": "estimate_elapsed",
            "elapsed": data["elapsed_time"]
        })
                           
        print_out_list = [
            {
                "header_elements": {
                "START SNAPSHOT": data["data"][-1]["timestamp"],
                "STOP SNAPSHOT": data["data"][0]["timestamp"],
                },
                "spacing": 25,
            },
            {
                "header_elements": {
                "START ORDINAL": data["start_ordinal"],
                "END ORDINAL": data["end_ordinal"],
                },
                "spacing": 25,
            },
            {
                "header_elements": {
                "ELAPSED TIME": elapsed,
                "SNAPSHOTS": snapshot_size,
                "REWARDED COUNT": len(reward_amount),
                },
                "spacing": 14,
            },
            {
                "header_elements": {
                "-BLANK-":None,
                f"{title}": colored(search_dag_addr,color),
                },
            },
            {
                "header_elements": {
                "REWARDED DAG ADDRESSES": first[0],
                "AMOUNT REWARDED": "{:,.3f}".format(first[1]/1e8)
                },
                "spacing": 40,
            },
        ]
        
        if create_csv:
            self.log.logger[self.log_key].info(f"current rewards command is creating csv file [{csv_file_name}] and adding headers")
            csv_headers = [
                
                ["General"],
                
                ["start ordinal","end ordinal","snapshot count","start snapshot",
                 "end snapshot","dag address count"],
                
                [data["start_ordinal"],data["end_ordinal"],snapshot_size,data["data"][-1]["timestamp"],
                 data["data"][0]["timestamp"],len(reward_amount)],
                 
                ["rewards"],
                
                ["DAG address","amount rewards"],
                [first[0],"{:,.3f}".format(first[1]/1e8)],

            ]
                
            self.functions.create_n_write_csv({
                "file": csv_path,
                "rows": csv_headers
            })
        else:
            for header_elements in print_out_list:
                self.functions.print_show_output({
                    "header_elements" : header_elements,
                })   

        if target_dag_addr:
            return
        
        do_more = False if "-np" in command_list else True
        if do_more:
            console_size = get_terminal_size()
            more_break = round(console_size.lines)-20   
            
        for n, (address, amount) in enumerate(reward_amount.items()):
            if do_more and n % more_break == 0 and n > 0:
                more = self.functions.print_any_key({
                    "quit_option": "q",
                    "newline": "both",
                })
                if more:
                    break
                
            amount = "{:,.3f}".format(amount/1e8)
            if create_csv:
                self.functions.create_n_write_csv({
                    "file": csv_path,
                    "row": [address,amount]
                })
            else:
                if address == search_dag_addr:
                    print(f"  {colored(address,color)}  {colored(amount,color)}{colored('**','yellow',attrs=['bold'])}")
                else:
                    print(f"  {address}  {amount}")        
    
        if create_csv:
            self.log.logger[self.log_key].info(f"csv file created: location: [{csv_path}]") 
            self.functions.print_cmd_status({
                "text_start": "Create csv for",
                "brackets": "show current rewards",
                "newline": True,
                "status": "complete"
            })
            self.functions.print_paragraphs([
                ["CSV created successfully",1,"green","bold"],
                ["filename:",0,], [csv_file_name,1,"yellow","bold"],
                ["location:",0,], [self.config_obj[profile]['directory_uploads'],1,"yellow","bold"]
            ])  
        

    def show_dip_error(self,command_list):
        self.functions.check_for_help(command_list,"show_dip_error")
        profile = command_list[command_list.index("-p")+1]
        self.log.logger[self.log_key].info(f"show_dip_error -> initiated - profile [{profile}]")
        
        bashCommand = f"grep -a -B 50 -A 5 'Unexpected failure during download' /var/tessellation/{profile}/logs/app.log | tail -n 50"
    
        results = self.functions.process_command({
            "bashCommand": bashCommand,
            "proc_action": "subprocess_co",
        })
        
        if not results or results == "":
            self.functions.print_paragraphs([
                ["nodectl was not able to locate any",0], ["DownloadInProgress",0,"yellow"],
                ["errors.",1],                           
            ])
        else:
            results = results.split("\n")
            self.functions.print_paragraphs([
                [" RESULTS ",1,"red,on_yellow"],
            ])

            for line in results:
                color = "cyan"
                if "Unexpected failure" in line: color = "red"
                if "CannotFetchSnapshot" in line: color = "yellow"
                self.functions.print_paragraphs([
                    ["=","half","blue","bold"],
                    [str(line),1,color],
                ])
        

    def show_p12_details(self,command_list):
        self.functions.check_for_help(command_list,"show_p12_details")
        p12 = P12Class({"functions": self.functions})   
        p12.solo = True   
        p12.show_p12_details(command_list)  


    def show_profile_issues(self,command_list,ts=False):
        self.functions.check_for_help(command_list,"show_profile_issues")
        solo = False
        lines = command_list[command_list.index("--lines")+1] if "--lines" in command_list else 149
        if not ts:
            ts = self.troubleshooter
            self.print_title("POSSIBLE PROFILE ISSUES")
            solo = True

        try:
            profile = command_list[command_list.index("-p")+1]
        except Exception as e:
            self.functions.print_paragraphs([
                ["Error:",0,"red","bold"], ["Unable to determine profile issue",1,"red"],
            ])
            self.log.logger[self.log_key].warning(f"command_line -> show_profile_issues -> unable to obtain profile, skipping [{e}]")
            return
        
        ts.setup_logs({
            "profile": profile,
        })
        results = ts.test_for_connect_error(lines) 

        def sort_errors(err):
            return err["rank"], err["timestamp"].timestamp()
        
        if results:
            f_profile = results[0] 
            for result in results[1]:
                try:
                    result["timestamp"] = datetime.fromisoformat(result["timestamp"].replace("Z","+00:00"))
                except: 
                    # list references same dict, so it can be skipped
                    pass

            try:
                results = sorted(results[1],key=sort_errors)
            except:
                self.log.logger[self.log_key].error("cli -> show_profile_error -> unable to sort timestamps, skipping")

            for result in results:
                try:
                    result["timestamp"] = result["timestamp"].isoformat() + 'Z'
                except: 
                    pass

            self.functions.print_paragraphs([
                ["",1], ["The following was identified in the logs",2,"red"],
            ])
            try:
                results = self.functions.remove_duplicates("list_of_dicts",results)
            except Exception as e:
                self.log.logger[self.log_key].critical(f"show_profile_issues -> attempted to remove duplicate error messages which resulted in [{e}]")
                self.error_messages.error_code_messages({
                    "error_code": "cli-1973",
                    "line_code": "unknown_error",
                    "extra": e,
                })

            for result in results:
                error_msg = str(result['error_msg'])
                find_msg = str(result['find'])
                user_msg = str(result['user_msg'])
                timestamp_msg = str(result['timestamp'])
                self.log.logger[self.log_key].error(f"cli_restart -> profile [{f_profile}] error [{result['error_msg']}] error found [{result['find']}] user message [{result['user_msg']}]")
                self.functions.print_paragraphs([
                    ["       Profile:",0],[f_profile,1,"yellow"],
                    ["         Error:",0],[error_msg,1,"yellow"],
                    ["Possible Cause:",0],[user_msg,1,"yellow"],
                    ["        Result:",0],[find_msg,1,"yellow"],
                    ["          Time:",0],[timestamp_msg,2,"yellow"],
                ])
        elif solo:
            self.functions.print_paragraphs([
                ["Profile:",0],[profile,1,"yellow"],
                ["No issues found...",1,"green","bold"],
            ])


    # ==========================================
    # update commands
    # ==========================================

    def tess_downloads(self,command_obj):
        caller = command_obj.get("caller",False)
        argv_list = command_obj["argv_list"]

        if "-e" not in argv_list and "-p" not in argv_list:
            argv_list.append("help")
        self.functions.check_for_help(argv_list,caller)

        title = "TESSELLATION BINARIES"
        print_status = "Refresh of Tessellation binaries"
        confirm_text = "binaries"
        if caller == "update_seedlist" or caller == "_usl":
            title = "UPDATE SEEDLISTS"
            print_status = "Refresh of Tessellation seedlist(s)"
            confirm_text = "seedlist"
        self.functions.print_header_title({
          "line1": title,
          "line2": "refresh request",
          "clear": False,
          "upper": False,
        })

        if caller == "refresh_binaries" or caller == "_rtb":
            self.functions.print_paragraphs([
                [" WARNING ",0,"yellow,on_red","bold"], ["You will need to restart all services after completing this download.",2]
            ])
        
        if not "-y" in argv_list:
            confirm = self.functions.confirm_action({
                "yes_no_default": "n",
                "return_on": "y",
                "prompt": f"Are you sure you want to overwrite Tessellation {confirm_text}?",
                "exit_if": False,
            })
            if not confirm:
                if self.mobile: return
                exit(0)
        
        download_obj = {"caller": caller, "action": caller}
        if "-p" in argv_list:  
            download_obj["profile"] = argv_list[argv_list.index("-p")+1]
            download_obj["environment"] = self.config_obj[download_obj["profile"]]["environment"]
        else:
            download_obj["environment"] = argv_list[argv_list.index("-e")+1]
        if "-v" in argv_list:
            download_obj["download_version"] = argv_list[argv_list.index("-v")+1]

        pos = self.node_service.download_constellation_binaries(download_obj)

        print("\n"*(pos["down"]-1))
        self.functions.print_cmd_status({
            "text_start": print_status,
            "status": "complete",
            "newline": True,
        })
        print("")

    # ==========================================
    # check commands
    # ==========================================
            
    def check_versions(self, command_obj):
        command_list = command_obj["command_list"]
        self.functions.check_for_help(command_list,"check_version")

        self.check_versions_called = True
        self.skip_build = False
        self.skip_services = True
        self.version_check_needed = True
                
        profile = None
        profile_names = self.profile_names
        if "-p" in command_list:
            profile = command_list[command_list.index("-p")+1]
            profile_names = [profile]
                
        if self.skip_warning_messages:
            self.functions.print_paragraphs([
                [" WARNING ",1,"yellow,on_red"], ["Developer Mode",0,"yellow"],["or",0,"red"],
                ["--skip_warning_messages",0,"yellow"], ["was enabled.",1,"red"],
                ["This command will",0,"red"],
                ["automatically disable this option in order to function properly.",1,"red"],
            ])
            self.skip_warning_messages = False
            self.functions.print_cmd_status({
                "text_start": "disabling --skip_warning_messages",
                "status": "complete",
                "status_color": "green",
                "newline": True,
            })
            print("")

        spacing = 25
        match_true= colored("True","green",attrs=["bold"])
        match_false = colored("False","red",attrs=["bold"])
                
        for n, profile in enumerate(profile_names):
            try:
                environment = self.config_obj[profile]["environment"]
            except:
                self.error_messages.error_code_messages({
                    "error_code": "cmd-848",
                    "line_code": "profile_error",
                    "extra": profile
                })   

            for n in range(0,2):
                try:
                    _ = self.version_obj[environment]["nodectl"]
                    break
                except:
                    if n > 0:
                        self.error_messages.error_code_messages({
                            "error_code": "cmd-1962",
                            "line_code": "version_fetch",
                        })                           
                    self.version_obj = self.functions.handle_missing_version(command_obj["version_class_obj"])

                
            nodectl_match = True       
            if not isinstance(self.version_obj[environment]["nodectl"]["nodectl_uptodate"],bool):
                if "current" in self.version_obj[environment]["nodectl"]["nodectl_uptodate"]:
                    nodectl_match = False   
            tess_match = True       
            if not isinstance(self.version_obj[environment][profile]["tess_uptodate"],bool):
                if "current" in self.version_obj[environment][profile]["tess_uptodate"]:
                    tess_match = False   
            yaml_match = True       
            if not isinstance(self.version_obj[environment][profile]["nodectl_yaml_uptodate"],bool):
                if "current" in self.version_obj[environment][profile]["nodectl_yaml_uptodate"]:
                    yaml_match = False   
                     
            prerelease = colored("False","green")
            if self.version_obj[environment]["nodectl"]["nodectl_prerelease"]:
                prerelease = colored("True","yellow")
            if self.version_obj[environment]["nodectl"]["nodectl_prerelease"] == "Unknown":
                prerelease = "Unknown"
            
            if n < 1:
                self.functions.print_header_title({
                    "line1": "CHECK VERSIONS",
                    "show_titles": False,
                    "newline": "bottom",
                })
            else:
                self.functions.print_paragraphs([
                    ["-","half","cyan"]
                ])

            mc_key = "METAGRAPH"
            tess_installed = self.version_obj[environment][profile]["node_tess_version"]
            if len(tess_installed) > spacing:
                spacing = len(tess_installed)+1
                
            metagraph = f'{self.config_obj["global_elements"]["metagraph_name"]}/{self.config_obj[profile]["environment"]}'
            if self.config_obj["global_elements"]["metagraph_name"] == "hypergraph":
                metagraph = self.config_obj[profile]["environment"]
                mc_key = "CLUSTER"
                
            print_out_list = [
                {
                    "header_elements" : {
                    "PROFILE": profile,
                    f"{mc_key}": metagraph,
                    "JAR FILE": self.version_obj[environment][profile]["node_tess_jar"],
                    },
                    "spacing": spacing
                },
                {
                    "header_elements" : {
                    "TESS INSTALLED": self.version_obj[environment][profile]["node_tess_version"],
                    "NODECTL INSTALLED": self.version_obj["node_nodectl_version"],
                    "NODECTL CONFIG": self.version_obj["node_nodectl_yaml_version"],
                    },
                    "spacing": spacing
                },
                {
                    "header_elements" : {
                    "TESS LATEST": self.version_obj[environment][profile]["cluster_tess_version"],
                    "NODECTL LATEST STABLE": self.version_obj[environment]["nodectl"]["current_stable"],
                    "CONFIG LATEST": self.version_obj[environment]["nodectl"]["nodectl_remote_config"],
                    },
                    "spacing": spacing
                },
                {
                    "header_elements" : {
                        # 38
                        "TESS VERSION MATCH": f"{match_true: <38}" if tess_match else f"{match_false: <38}",
                        "NODECTL VERSION MATCH": f"{match_true: <38}" if nodectl_match else f"{match_false: <38}",
                        "NODECTL CONFIG MATCH": f"{match_true}" if yaml_match else match_false
                    },
                    "spacing": 25
                },
                {
                    "header_elements" : {
                    "NODECTL CODE NAME": self.functions.nodectl_code_name,
                    "NODECTL PRERELEASE": prerelease,
                    },
                    "spacing": spacing
                },
            ]
            
            if self.config_obj["global_elements"]["metagraph_name"] != "hypergraph":
                meta_list = [{
                    "header_elements" : {
                    "METAGRAPH VERSION": self.version_obj[environment][self.profile_names[0]]["cluster_metagraph_version"],
                    },
                    "spacing": spacing                    
                }]
                print_out_list += meta_list

            for header_elements in print_out_list:
                self.functions.print_show_output({
                    "header_elements" : header_elements
                })  

            self.functions.print_paragraphs([
                ["",1],
                ["nodectl installed:",0,"blue","bold"], ["Running on Node.",1],
                ["nodectl latest stable:",0,"blue","bold"], ["Recommended version.",1],
                ["nodectl latest:",0,"blue","bold"], ["Newest, may be experimental and not stable.",1],
                ["nodectl config:",0,"blue","bold"], ["nodectl's configuration version.",2],
            ])
       
 
    def check_source_connection(self,command_list):
        self.functions.check_for_help(command_list,"check_source_connection")
        self.log.logger[self.log_key].info(f"Check source connection request made.")
        self.set_profile(command_list[command_list.index("-p")+1])
        self.functions.test_ready_observing(self.profile)
        
        self.functions.print_states()
        
        self.functions.print_paragraphs([
            ["Source:",0,"magenta"], ["Server this Node is joined to",1],
            ["  Edge:",0,"magenta"], ["This Node",2],
            ["Note:",0,"yellow"], ["If the SOURCE is on a different network it will show",0], ["ApiNotReady",2,"cyan","underline"],
        ])

        if not self.functions.check_health_endpoint(self.api_ports["public"]):
            self.functions.print_paragraphs([
                ["API endpoint for [",0,"red"], [self.profile,-1,"yellow","bold"], ["] is in state [",-1,"red"],
                ["ApiNotReady",-1,"yellow","bold"], ["].",-1,"red"],
                ["",1], ["Unable to process request.",2,"red"],
            ])
            return 1
            

        peer_test_results = self.functions.test_peer_state({"profile": self.profile})
        peer_test_results = SimpleNamespace(**peer_test_results)   

        source_result = f"{peer_test_results.node_on_src} | {peer_test_results.node_state_src}"
        edge_result = f"{peer_test_results.node_on_edge} | {peer_test_results.node_state_edge}"
        
        spacing = 27
        print_out_list = [
            {
                "header_elements" : {
            "FULL CONNECTION": colored(f"{peer_test_results.full_connection}".ljust(27),peer_test_results.full_connection_color),
            "PROFILE": self.profile.ljust(27),
                },
                "spacing": spacing
            },
            {
                "header_elements" : {
            "SOURCE -> STATE": colored(f"{source_result.ljust(27)}",peer_test_results.src_node_color),
            "EDGE -> STATE": colored(f"{edge_result.ljust(27)}",peer_test_results.edge_node_color),
                },
                "spacing": spacing
            },
        ]
        
        for header_elements in print_out_list:
            self.functions.print_show_output({
                "header_elements" : header_elements
            })    
    

    def check_connection(self,command_list):
        # -s source=(str), -e edge=(str)
        print_error_flag = False  
        issues_found = False
        defined_connection_threshold = .08
        sn_obj = {}
        en_obj = {}
        node_obj_list = [sn_obj,en_obj]
        source = False
        edge = False
        
        # dictionary > sn_obj and en_obj
            # "ip": "",
            # "peer_count"
            # "node_online"
            # "peer_set"
            
            # "peer_label_set"
            # "missed_ips": "None",
            # "missed_ip_count": 0,
            # "full_connection": True,
            # "full_connection_color": "green"


        def print_results(node_obj_list,secondFlag):
            for n in range(0,5):
                if n == 0:
                    header_elements = {
                        "SN: SOURCE NODE": node_obj_list[0]["ip"],
                        "EN: EDGE NODE": node_obj_list[1]["ip"],
                        "PROFILE": self.profile
                    }
                elif n == 1:
                    header_elements = {
                        "SN PEER COUNT": str(node_obj_list[0]["peer_count"]),
                        "EN PEER COUNT": str(node_obj_list[1]["peer_count"]),
                    }
                elif n == 2:
                    header_elements = {
                        "SN MISSING COUNT": node_obj_list[0]["missed_ip_count"],
                        "EN MISSING COUNT": node_obj_list[1]["missed_ip_count"],
                    }
                elif n == 3:
                    connection_status = "False"
                    connection_status_color = "red"
                    if node_obj_list[1]["peer_count"] == 0:
                        pass 
                    elif node_obj_list[0]["peer_count"] == 0:
                        connection_status = "Source Issue?"
                        connection_status_color = "yellow"
                    elif node_obj_list[1]["connection_status"] == "Observing":
                        connection_status = "Currently Observing"
                        connection_status_color = "yellow"
                    elif node_obj_list[1]["connection_status"] == "WaitingForReady":
                        connection_status = "Currently WaitingForReady"
                        connection_status_color = "yellow"
                    elif len(node_obj_list[0]["missed_ips"]) == 0 and len(node_obj_list[1]["missed_ips"]) == 0:
                        connection_status = "True"
                        connection_status_color = "green"
                    elif node_obj_list[0]["connection_status"] == True and node_obj_list[1]["connection_status"] == True:
                        found = [True,True]
                        for ip in node_obj_list[0]["missed_ips"]:
                            if node_obj_list[1]["ip"] == ip:
                                found[0] = False
                        for ip in node_obj_list[1]["missed_ips"]:
                            if node_obj_list[0]["ip"] == ip:
                                found[1] = False
                        if found[0] == True and found[1] == True:
                            connection_status = "True"
                            connection_status_color = "green"
                        if found[0] == True and found[1] == False:
                            connection_status = "One Way"
                            connection_status_color = "yellow"
                        if found[1] == True and found[0] == False:
                            connection_status = "One Way"

                    full_connection = node_obj_list[1]["full_connection"]
                    
                    header_elements = {
                        "SN/EN CONNECTED": colored(f"{connection_status}".ljust(20),connection_status_color),
                        "CONNECTION STATUS": colored(f"{str(full_connection).ljust(20)}",node_obj_list[1]["color"])
                    }
                else:
                    try:
                        sn_missing = node_obj_list[0]["missed_ips"].pop().strip("\n")
                    except:
                        if secondFlag:
                            sn_missing = "See Above"
                        else:
                            sn_missing = "None"
                    try:
                        en_missing = node_obj_list[1]["missed_ips"].pop().strip("\n")
                    except:
                        if secondFlag:
                            en_missing = "See Above"
                        else:
                            en_missing = "None"
                        
                    header_elements = {
                        "SN MISSING PEERS": str(sn_missing),
                        "EN MISSING PEERS": str(en_missing),
                    }
                
                self.functions.print_show_output({
                    "header_elements" : header_elements
                })
                         
            if not secondFlag:
                if node_obj_list[0]["missed_ip_count"] > node_obj_list[1]["missed_ip_count"]:
                    dash_needed_list = 1
                    no_dash_list = 0
                    size = node_obj_list[0]["missed_ip_count"]
                else:
                    dash_needed_list = 0
                    no_dash_list = 1
                    size = node_obj_list[1]["missed_ip_count"]
                    
                missed_ip_list = []
                while len(missed_ip_list) < size:
                    missed_ip_list.append("-")
                
                try:
                    for x,ip in enumerate(node_obj_list[no_dash_list]["missed_ips"]):
                        ip1 = ip.strip("\n")
                        ip2 = missed_ip_list[x].strip("\n")
                        if dash_needed_list:
                            print(f"  {ip1.ljust(22)}{ip2}")
                        else:
                            print(f"  {ip2.ljust(22)}{ip1}")
                except:
                    pass


        self.functions.check_for_help(command_list,"check_connection")
        self.set_profile(command_list[command_list.index("-p")+1])
        
        if "-s" in command_list:
            source = command_list[command_list.index("-s")+1]
        if "-e" in command_list:
            edge = command_list[command_list.index("-e")+1]
           
        edge = "127.0.0.1" if not edge else edge
        self.log.logger[self.log_key].info(f"Check connection request made. | {edge}")

        node_list = [source,edge]
        flip_flop = []

        self.functions.test_ready_observing(self.profile)
        
        for n, node in enumerate(node_list):
            # "peer_count": [], # peer_count, node_online, peer_set
            self.log.logger[self.log_key].debug(f"checking count and testing peer on {node}")
            node_obj = self.functions.get_info_from_edge_point({
                "profile": self.profile,
                "caller": "check_connection",
                "specific_ip": node
            })
            flip_flop.append(node_obj)
        
        if True in flip_flop or False in flip_flop:
            self.error_messages.error_code_messages({
                "error_code": "cli-2392",
                "line_code": "invalid_peer_address",
                "extra": node_list[1],
            })

        try:
            for node_obj in flip_flop:
                valid = node_obj["specific_ip_found"]
                if valid:
                    if valid[0] != valid[1]:
                        self.functions.print_paragraphs([
                            [" warning ",0,"yellow,on_red"],["requested",0,"red"],[valid[0],0,"yellow"],
                            ["ip was not found, using",0,"red"],[valid[1],0,"yellow"],
                            ["instead...",2,"red"],
                        ])
        except:
            pass
                
        for n, node_obj in enumerate(flip_flop):    
            peer_count = self.functions.get_peer_count({
                "peer_obj": node_obj,
                "profile": self.profile,
                "compare": True
            })
            
            # check two-way connection
            if n == 1:
                flip_flop.reverse()
            conn_test = self.functions.test_peer_state({
                "test_address": flip_flop[0]["ip"],
                "current_source_node": flip_flop[1]["ip"],
                "profile": self.profile
            }) 
            
            node_obj_list[n]["connection_status"] = conn_test["full_connection"]
            
            try: 
                if peer_count is None or peer_count["peer_count"] is None or peer_count["node_online"] is None or peer_count["peer_count"] == "e":
                    node_obj_list[n]["peer_count"] = 0
                else:
                    node_obj_list[n]["peer_count"] = peer_count["peer_count"]
            except:
                node_obj_list[n]["peer_count"] = 0
            
            if peer_count == None or peer_count == "error" or peer_count == 0:
                node_obj_list[n]["node_online"] = conn_test["full_connection"]
                node_obj_list[n]["peer_set"] = set([node_obj])
                node_obj_list[n]["peer_label_set"] = set([node_obj])
                node_obj_list[n]["peer_label_set"] = set([node_obj])
                node_obj_list[n]["ip"] = node_obj["ip"]
            else:
                node_obj_list[n]["node_online"] = peer_count["node_online"]
                node_obj_list[n]["peer_set"] = set(peer_count["peer_list"])
                node_obj_list[n]["peer_label_set"] = set(peer_count["state_list"])
                node_obj_list[n]["ip"] = node_obj["ip"]

        # update missed_ip_counts
        try:
            # edge node missing                        source                  -              edge
            node_obj_list[1]["missed_ips"] = node_obj_list[0]["peer_set"] - node_obj_list[1]["peer_set"]
        except Exception as e:
            self.log.logger[self.log_key].error(f"check_connection - source - edge - threw error [{e}]")
        else:
            node_obj_list[1]["missed_ip_count"] = len(node_obj_list[1]["missed_ips"])
  

        # source node missing                          edge                    -              source
        try:
            node_obj_list[0]["missed_ips"] = node_obj_list[1]["peer_set"] - node_obj_list[0]["peer_set"]
        except Exception as e:
            self.log.logger[self.log_key].error(f"check_connection - edge - source - threw error [{e}]")
        else:
            node_obj_list[0]["missed_ip_count"] = len(node_obj_list[0]["missed_ips"])
    
        # add state labels (*,i*,rtj*,ss*,l*,s*,o*)
        for s in range(0,2):
            missed_set = set()    
            ss = 1 if s == 0 else 0
            for missed in node_obj_list[ss]["missed_ips"]:
                try:
                    index = node_obj_list[s]["peer_set"].index(missed)
                    if node_obj_list[s]["peer_label_set"][index] != "":
                        missed_set.add(f'{missed}{node_obj_list[s]["peer_label_set"][index]}')
                    else:
                        missed_set.add(f'{missed}{node_obj_list[s]["peer_label_set"][index]}')
                except:
                    missed_set = node_obj_list[s]["peer_set"]
            node_obj_list[ss]["missed_ips"] = missed_set
                
        if node_obj_list[0]["missed_ip_count"] == node_obj_list[1]["missed_ip_count"]:
            node_obj_list[1]["full_connection"] = "Fully Connected"
            node_obj_list[1]["color"] = "green"
            node_obj_list[0]["missed_count"] = 0
            node_obj_list[1]["missed_count"] = 0
        else:
            try:
                threshold_check = node_obj_list[1]["missed_ip_count"] / node_obj_list[0]["peer_count"]
            except:
                threshold_check = 100
                
            if threshold_check < defined_connection_threshold:
                issues_found = True
                node_obj_list[1]["full_connection"] = f"Threshold Met < 8% ({node_obj_list[1]['missed_ip_count']})"
                node_obj_list[1]["color"] = "yellow"   
            else:
                print_error_flag = True  
                node_obj_list[1]["full_connection"] = "Unstable Connection"
                node_obj_list[1]["color"] = "red"   
    
        print_results(node_obj_list,False)
            
        if issues_found:
            self.log.logger[self.log_key].error(f"Check  connection request returned threshold or other error.")
            self.functions.print_paragraphs([
                ["This Node is",0,"yellow"], ["not 100%",0,"red","underline"], ["connected",2,"yellow"],
                
                ["However, it meets a 8% the threshold",2,"green"],
                
                ["You can safely allow your Node to function.",0,"green","bold"], ["Note:",0,"green","underline"],
                ["You may be missing Nodes because",0,"green"], ["other",0,"red"], 
                ["Nodes are always coming and going on the network, or other Nodes may be the source of the",0,"green"],
                ["issue(s)",2,"red"]
            ])
            
        if print_error_flag:
            self.functions.print_paragraphs([
                ["Issues were found.",0,"red","bold"], ["See help for details",1,"red"],
                ["sudo nodectl check_connection help",2],
                ["Although you do not have a full connection, the issue may",0,"red","bold"], 
                ["not",0,"red","underline"], ["be directly correlated with your Node.",2,"red","bold"]
            ])            

        if print_error_flag or issues_found:
            self.functions.print_paragraphs([
                ["If you feel it necessary, please contact an Admin for assistance.",1,"magenta"],
                ["You can save and send your log files to a support developer.",1,"magenta"],
                ["sudo nodectl send_logs",2],
                ["This may supply you with further analysis.",2,"red"],
            ])
            if node_obj_list[0]["missed_ip_count"] > 10 or node_obj_list[1]["missed_ip_count"] > 10:
                for n in range(2):
                    node_obj_list[n]["missed_ips"] = "see above"
                print_results(node_obj_list,True)
        else:
            self.functions.print_paragraphs([
                ["",1], [" CONGRATULATIONS ",0,"grey,on_green"], ["No issues were found!",1,"green"],
                ["This Node looks",0,"green"], ["healthy!",2,"green","bold"],
            ])
            
    
    def check_seed_list(self,command_list):
        self.functions.check_for_help(command_list,"check_seedlist")
        found = colored("False","red",attrs=["bold"])
        profile = command_list[command_list.index("-p")+1]
        skip = True if "skip_warnings" in command_list else False
        nodeid, nodeid_short = None, None
        skip_full_nodeid = False

        if not "skip_seedlist_title" in command_list: self.print_title("CHECK SEED LIST REQUEST")
        
        argv_list = []
        if "-t" in command_list:
            target = command_list[command_list.index("-t")+1]
            if not self.functions.is_valid_address("ip_address",True,target):
                self.error_messages.error_code_messages({
                    "error_code": "cli-2086",
                    "line_code": "input_error",
                    "extra": "invalid ip address",
                    "extra2": "An invalid ip address was entered; use -id for node id",
                })
            argv_list = ["-t",target,"-l"]
        nodeid = command_list[command_list.index("-id")+1] if "-id" in command_list else False

        if "-p" in command_list:
            argv_list += ["-p",profile]

        if self.functions.config_obj[profile]["seed_location"] == "disable":
            if skip:
                return True
            self.functions.print_paragraphs([
                ["Seed list is disabled for profile [",0], [profile,-1,"yellow","bold"],
                ["] unable to do a proper nodeid lookup",0], ["exiting.",2,"red"]
            ])
            return 0

        if nodeid:
            skip_full_nodeid = True
            self.functions.print_paragraphs([
                ["NODE ID",1,"blue","bold"],
                [nodeid,1,"white"],
            ])
        elif self.node_id_obj and "-t" not in argv_list:
            nodeid = self.node_id_obj[profile]
            nodeid_short = self.node_id_obj[f"{profile}_short"]
        else:
            self.cli_grab_id({
                "command":"nodeid",
                "argv_list": argv_list,
                "skip_display": skip,
                "return_success": "set_value",
            })
            nodeid = self.nodeid
            nodeid_short = f"{nodeid[:8]}...{nodeid[-8:]}"
               
        if nodeid:
            if not self.functions.is_valid_address("nodeid",True,nodeid):
                if self.primary_command == "install":
                    return False
                self.error_messages.error_code_messages({
                    "error_code": "cli-2121",
                    "line_code": "input_error",
                    "extra": "invalid nodeid entered with -t",
                    "extra2": "invalid nodeid; use -t for node ip address",
                })
            nodeid = self.functions.cleaner(nodeid,"new_line")
            seed_path = self.functions.cleaner(self.functions.config_obj[profile]["seed_path"],"double_slash")
            test = self.functions.test_or_replace_line_in_file({
              "file_path": seed_path,
              "search_line": nodeid
            })

            if test == "file_not_found":
                self.error_messages.error_code_messages({
                    "error_code": "cmd-1229",
                    "line_code": "file_not_found",
                    "extra": seed_path,
                    "extra2": None
                })
            elif test:
                found = colored("True","green",attrs=["bold"]) 

        if skip:
            if "True" in found:
                return True
            return False
        
        print_out_list = [
            {
                "PROFILE": profile,
                "NODE ID": nodeid_short,
            },
            {
                "NODE ID FOUND ON SEED LIST": found,
            }
        ]
    
        if skip_full_nodeid:
            print_out_list.pop(0)
            
        for header_elements in print_out_list:
            self.functions.print_show_output({
                "header_elements" : header_elements
            }) 
            

    def check_nodectl_upgrade_path(self,command_obj):
        called_command = command_obj["called_command"]
        argv_list = command_obj["argv_list"]
        version_class_obj = command_obj.get("version_class_obj",False)

        try: env = argv_list[argv_list.index('-e')+1]
        except: argv_list.append("help")
            
        self.functions.check_for_help(argv_list,"upgrade_path")
        called_command = "upgrade_path" if called_command == "_up" else called_command
        
        self.log.logger[self.log_key].debug("testing for upgrade path requirements")

        try:
            nodectl_uptodate = getattr(versions,env)
        except:
            try:
                versions = self.functions.handle_missing_version(version_class_obj)
                versions = SimpleNamespace(**versions)
                nodectl_uptodate = getattr(versions,env)
            except:
                self.error_messages.error_code_messages({
                    "error_code": "cli-2671",
                    "line_code": "version_fetch",
                })

        nodectl_uptodate = nodectl_uptodate["nodectl"]["nodectl_uptodate"]
        
        upgrade_path = versions.upgrade_path
        try:
            test_next_version = upgrade_path[upgrade_path.index(versions.node_nodectl_version)-1]
        except:
            test_next_version = upgrade_path[0]
        finally:
            if versions.node_nodectl_version in upgrade_path and versions.node_nodectl_version != upgrade_path[0] and test_next_version != upgrade_path[0]:
                upgrade_path_this_version = upgrade_path[upgrade_path.index(versions.node_nodectl_version)-1:]    
                next_upgrade_path = upgrade_path_this_version[0] 
            else: next_upgrade_path = upgrade_path[0]   
        
        for test_version in reversed(upgrade_path):
            test = self.functions.is_new_version(versions.node_nodectl_version,test_version,called_command,"nodectl version")
            if test == "current_less":
                next_upgrade_path = test_version
                break
        
        def print_version_path():
            self.functions.print_header_title({
                "line1": "UPGRADE PATH",
                "single_line": True,
                "show_titles": False,
                "newline": "both"
            })

            upgrade_path_str_list = [["=","half",2,"green","bold"]]
            for version in reversed(upgrade_path):
                upgrade_path_str_list.append([version,0,'yellow'])
                if version != upgrade_path[0]:
                    upgrade_path_str_list.append(["-->",0,"cyan"])
            upgrade_path_str_list.append(["",1])
            upgrade_path_str_list.append(["=","half",2,"green","bold"])
            self.functions.print_paragraphs(upgrade_path_str_list)
                          
                                
        if versions.node_nodectl_version != next_upgrade_path:
            if next_upgrade_path != upgrade_path[0]:
                self.functions.print_clear_line()
                self.functions.print_paragraphs([
                    ["",1], [" WARNING !! ",2,"yellow,on_red","bold"],
                    ["nodectl",0,"blue","bold"], ["may",0,"red"], ["not",0,"red","underline,bold"], ["be at the correct version.",2,"red"],
                    ["Version [",0,"red"], [versions.node_nodectl_version,-1,"yellow"], 
                    ["] was detected. The next required upgrade is to",-1,"red"],
                    ["Version [",0,"red"], [next_upgrade_path,-1,"yellow"], 
                    ["] which should then be followed by the path presented above, if not already the latest.",-1,"red"],["",2],
                    ["Download the latest version via a",0,"red"],["wget",0,"yellow","bold"],
                    ["command, then:",1,"red"],
                    [f"sudo nodectl upgrade",1],
                    [f"sudo nodectl {called_command}",2],
                    ["See:",0,"red"], ["Github release notes",2,"magenta"]
                ])
            elif called_command == "upgrade_path" and not nodectl_uptodate:
                self.functions.print_clear_line()
                self.functions.print_paragraphs([
                    ["",1], [" WARNING !! ",2,"yellow,on_red","bold"],
                    ["nodectl",0,"blue","bold"], ["may",0,"red"], ["not",0,"red","underline,bold"],
                    ["be running on the latest stable version.",2,"red"],
                ])   
                
        if next_upgrade_path != upgrade_path[0]:
            if called_command == "upgrade_path":
                self.functions.print_clear_line()
            
            if called_command == "upgrade":
                self.functions.print_paragraphs([
                    ["",1], ["Upgrade cannot continue. Exiting...",1,"red","bold"],
                ])
                self.functions.print_auto_restart_warning()
                exit("  auto restart enablement error")

        if called_command == "upgrade_path":
            self.functions.print_cmd_status({
                "text_start": "Version found on system",
                "status": versions.node_nodectl_version,
                "status_color": "yellow",
                "newline": True,
            })
            if nodectl_uptodate == "current_greater":  
                self.functions.print_paragraphs([
                    ["",1],["Use this version of nodectl with caution because it may produce undesired affects.",0,"yellow"],
                    ["If the",0,"yellow"], ["sudo nodectl upgrade",0], ["command was used against this version, you may run",0,"yellow"],
                    ["into undesired results if you attempt to downgrade to a previous version.  A new installation of nodectl would be",0,"yellow"],
                    ["a better option to resume on a stable release.",2,"yellow"],
                ])   
            elif nodectl_uptodate and nodectl_uptodate != "current_less":
                self.functions.print_paragraphs([
                    ["You are",0,"green"], ["up-to-date",0,"green","bold"], ["nothing to do",1,"green"], 
                ])
            else:
                self.functions.print_cmd_status({
                    "text_start": "nodectl can be",
                    "brackets": "directly",
                    "text_end": "upgraded to",
                    "status": next_upgrade_path,
                    "status_color": "yellow",
                    "newline": True,
                })
                    
            print_version_path()
            print("")
        

    def check_for_new_versions(self,command_obj):
        profile = command_obj.get("profile","default")
        nodectl_version_shown, nodectl_version_check = False, False
        caller = command_obj.get("caller",None)
        
        if caller in ["_sl","send_logs"]: return # send_logs command exception
        self.functions.get_service_status()
        if caller in ["upgrade_nodectl","main_error","uninstall"]: return
        
        environments = self.functions.pull_profile({"req": "environments"})
        profile_names = self.profile_names

        if profile != "default":
            profile_names = [profile]

        for i_profile in profile_names:
            if not self.config_obj[i_profile]["profile_enable"]: continue

            env = self.config_obj[i_profile]["environment"]

            try:
                nodectl_version_check = self.version_obj[env]["nodectl"]["nodectl_uptodate"]
            except:
                self.log.logger[self.log_key].warning("check_for_new_version -> unable to determine if [nodectl] version is up to date... skipping")
                nodectl_version_check = "unknown"

            if nodectl_version_check == "current_greater" and not self.check_versions_called:
                if nodectl_version_check == "current_greater" and not self.skip_warning_messages:
                    self.functions.print_paragraphs([
                        [" WARNING ",0,"red,on_yellow"],
                        ["You are running a version of nodectl that is claiming to be newer than what was found on the",0],
                        ["official Constellation Network StardustCollective repository, please proceed",0],
                        ["carefully, as this version may either be:",2],
                        ["- experimental (pre-release)",1,"magenta"],
                        ["- malware",1,"magenta"],
                        ["- not an official supported version",2,"magenta"],
                        ["   environment checked:",0],[env,1,"yellow","bold"],
                        [" version found running:",0],[self.version_obj['node_nodectl_version'],1,"yellow","bold"],
                        [" required upgrade path:",0],[self.version_obj['upgrade_path'][0],1,"yellow","bold"],
                        ["current stable version:",0],[self.version_obj[env]["nodectl"]["current_stable"],2,"yellow","bold"],
                        ["Suggestion:",0],["sudo nodectl verify_nodectl",2,"yellow"],
                    ])
                    self.invalid_version = True
                    return
            if nodectl_version_check == "current_less" and not self.check_versions_called:
                if not nodectl_version_shown:
                    self.functions.print_cmd_status({
                        "text_start": "A new version of",
                        "brackets": "nodectl",
                        "text_end": "was detected",
                        "status": self.version_obj[env]['nodectl']['current_stable'],
                        "status_color": "yellow",
                        "newline": True,
                    })
                    self.functions.print_paragraphs([
                        ["To upgrade issue:",0], [f"sudo nodectl upgrade_nodectl",2,"green"]
                    ])
                nodectl_version_shown = True
            try:
                tess_version_check = self.version_obj[env][i_profile]["tess_uptodate"]
            except:
                self.log.logger[self.log_key].warning("check_for_new_version -> unable to determine if [Tessellation] version is up to date... skipping")
                tess_version_check = "unknown"
            if tess_version_check == "current_less" and not self.check_versions_called:
                    self.functions.print_clear_line()
                    self.functions.print_paragraphs([
                        [f" {i_profile} ",0,"green,on_blue"],["A",0], ["new",0,"green"], ["version of",0], 
                        ["Tessellation",0,"cyan"], ["was detected:",0],
                        [f"{self.version_obj[env][i_profile]['cluster_tess_version']}",1,"yellow","bold"],
                    ])
                    if i_profile == profile_names[-1]:
                        self.functions.print_paragraphs([
                            ["To upgrade issue:",0], [f"sudo nodectl upgrade",2,"green"]
                        ])
    
            
    # ==========================================
    # cli main functional commands
    # ==========================================
                       
    def cli_start(self,command_obj):
        profile = command_obj.get("profile",self.profile)        
        argv_list = command_obj.get("argv_list",[])
        spinner = command_obj.get("spinner",False)
        service_name = command_obj.get("service_name",self.service_name)
        threaded = command_obj.get("threaded", False)
        static_nodeid = command_obj.get("static_nodeid",False)
        skip_seedlist_title = command_obj.get("skip_seedlist_title",False)
        existing_node_id = command_obj.get("node_id",False)
        self.functions.check_for_help(argv_list,"start")

        self.log.logger[self.log_key].info(f"Start service request initiated.")
        progress = {
            "text_start": "Start request initiated",
            "brackets": self.functions.cleaner(service_name,'service_prefix'),
            "status": "running",
            "newline": True,
        }
        self.functions.print_cmd_status(progress)

        if self.config_obj[profile]["seed_path"] != "disable/disable":
            check_seed_list_options = ["-p",profile,"skip_warnings","-id",existing_node_id]
            if skip_seedlist_title: check_seed_list_options.append("skip_seedlist_title")
            found = self.check_seed_list(check_seed_list_options)
            self.functions.print_cmd_status({
                "text_start": "Node found on Seed List",
                "status": found,
                "status_color": "green" if found == True else "red",
                "newline": True,
            })
            if not found:
                self.functions.print_paragraphs([
                    [" WARNING ",0,"red,on_yellow"], ["nodeid was not found on the seed list.",1,"red"]
                ])
                if not self.functions.confirm_action({
                    "prompt": "Continue with start action?",
                    "yes_no_default": "n",
                    "return_on": "y",
                    "exit_if": False
                }):
                    self.functions.print_paragraphs([
                        ["Action canceled by Operator",1,"green"]
                    ])
                    exit(0)
            
        self.node_service.change_service_state({
            "profile": profile,
            "action": "start",
            "service_name": service_name,
            "caller": "cli_start"
        })
        
        self.functions.print_cmd_status({
            **progress,
            "status": "complete",
        }) 
        
        self.functions.print_timer({
            "p_type": "cmd",
            "seconds": 6,
            "step": -1,
            "phrase": "Waiting",
            "end_phrase": "before starting",
        })

        with ThreadPoolExecutor() as executor:
            if spinner:
                self.functions.event = True
                _ = executor.submit(self.functions.print_spinner,{
                    "msg": f"Fetching status [{profile}], please wait ",
                    "color": "cyan",
                })      
            else:  
                self.functions.print_cmd_status({
                    "text_start": "Fetching Status",
                    "brackets": profile,
                    "newline": True,
                })
        
            self.functions.event = False
            sleep(.8)
            
            show_status_obj = {
                "called": "status",
                "spinner": False,
                "rebuild": True,
                "wait": False,
                "print_title": False,
                "threaded": threaded,
                "static_nodeid": static_nodeid if static_nodeid else False,
                "-p": profile                
            }
            
            try:
                if self.command_obj["command"] == "start":
                    show_status_obj["called"] = "start"
            except: pass
        
            self.show_system_status(show_status_obj)
        

    def cli_stop(self,command_obj):
        show_timer = command_obj.get("show_timer",True)
        spinner = command_obj.get("spinner",False)
        argv_list = command_obj.get("argv_list",[])
        profile = command_obj.get("profile",self.profile)
        static_nodeid = command_obj.get("static_nodeid",False)
        check_for_leave = command_obj.get("check_for_leave",False)
        leave_first, rebuild, result = False, True, False
    
        sleep(command_obj.get("delay",0))
        
        self.functions.check_for_help(argv_list,"stop")
        self.set_profile(profile)

        self.log.logger[self.log_key].info(f"cli_stop -> stop process commencing | profile [{profile}]")
        self.functions.print_cmd_status({
            "status": "stop",
            "status_color": "magenta",
            "text_start": "Issuing system service",
            "brackets": profile,
            "newline": False,
        })

        if check_for_leave:
            state = self.functions.test_peer_state({
                "profile": profile,
                "skip_thread": True,
                "spinner": spinner,
                "simple": True,
                "current_source_node": "127.0.0.1",
                "caller": "cli_stop",
            })     
            self.log.logger[self.log_key].info(f"cli_stop -> found state | profile [{profile}] | state [{state}]")
            states = self.functions.get_node_states("on_network",True)

            if state in states:
                self.functions.print_paragraphs([
                    ["",1],[" WARNING ",0,"white,on_red"], ["This profile",0],
                    [profile,0,"yellow","bold"], ["is in state:",0], [state,2,"yellow","bold"],
                ]) 
                if "-l" in argv_list or "--leave" in argv_list:
                    leave_first = True
                else:
                    leave_first = self.functions.confirm_action({
                        "yes_no_default": "y",
                        "return_on": "y",
                        "prompt": "Do you want to leave first?",
                        "exit_if": False,
                    })
                if leave_first:
                    self.cli_leave({
                        "secs": 30,
                        "reboot_flag": False,
                        "skip_msg": False,
                        "argv_list": ["-p",profile],
                    })
                
        progress = {
            "status": "running",
            "status_color": "yellow",
            "text_start": "stop request initiated",
            "brackets": self.functions.cleaner(self.service_name,'service_prefix'),
            "newline": True,
        }
        print("")
        self.functions.print_cmd_status(progress)
        self.log.logger[self.log_key].info(f"Stop service request initiated. [{self.service_name}]")
        
        with ThreadPoolExecutor() as executor:
            if spinner:
                self.functions.event = True
                show_timer = False
                _ = executor.submit(self.functions.print_spinner,{
                    "msg": "This could take some time, please wait",
                    "color": "red",
                })      
            else:  
                self.functions.print_cmd_status({
                    "text_start": "This could take some time, please wait",
                    "text_color": "red",
                    "bold": True,
                    "newline": False,
                })

            try:
                result = self.node_service.change_service_state({
                    "profile": profile,
                    "action": "stop",
                    "service_name": self.service_name,
                    "caller": "cli_stop"
                })
                self.functions.event = False
            except Exception as e:
                self.log.logger[self.log_key].error(f"cli_stop -> found issue with stop request [{e}]")

        if result == "skip_timer":
            show_timer = False
        if spinner:
            show_timer = False
        if self.functions.config_obj["global_elements"]["node_service_status"][profile] == "inactive (dead)":
            rebuild = False
        
        self.log.logger[self.log_key].debug(f"cli_stop -> stop process completed | profile [{profile}]")
        self.functions.print_cmd_status({
            **progress,
            "status": "complete",
            "status_color": "green",
            "newline": True
        }) 

        self.show_system_status({
            "rebuild": rebuild,
            "called": "stop",
            "wait": show_timer,
            "spinner": spinner,
            "print_title": False,
            "static_nodeid": static_nodeid if static_nodeid else False,
            "-p": profile
        })

        
    def cli_restart(self,command_obj):
        argv_list = command_obj["argv_list"]
        self.functions.check_for_help(argv_list,"restart")

        restart_type = command_obj["restart_type"]
        secs = command_obj["secs"]
        slow_flag = command_obj["slow_flag"]
        cli_leave_cmd = command_obj["cli_leave_cmd"]
        cli_join_cmd = command_obj["cli_join_cmd"]
        called_profile = argv_list[argv_list.index("-p")+1]
        watch = True if "-w" in argv_list else False
        interactive = True if "-i" in argv_list else False
        non_interactive = True if "-ni" in argv_list or "--ni" in argv_list else False
        dip = True if "--dip" in argv_list else False
        link_types = ["gl0","ml0"] 
        failure_retries = 3
        input_error = False

        if "-r" in argv_list:
            try: failure_retries = int(argv_list[argv_list.index("-r")+1])
            except: 
                input_error = True
                option = "r"
                extra2 = f'-r {argv_list[argv_list.index("-r")+1]}'

        if input_error:
            self.error_messages.error_code_messages({
                "error_code": "cmd-2138",
                "line_code": "input_error",
                "extra": option,
                "extra2": f"invalid value found -> {extra2}"
            })
                
        self.functions.print_clear_line()
        performance_start = perf_counter()  # keep track of how long
        self.log.logger[self.log_key].debug(f"cli_restart -> request commencing")
        self.functions.print_cmd_status({
            "text_start": "Restart request initiated",
            "status": "running",
            "status_color": "yellow",
            "newline": True,
        })

        self.functions.print_cmd_status({
            "text_start": "Node IP address",
            "status": self.functions.get_ext_ip(),
            "status_color": "green",
            "newline": True,
        }) 
        
        self.functions.set_default_variables({
            "profile": called_profile,
        })
        
        if restart_type != "restart_only":
            while True:
                if self.functions.check_edge_point_health():
                    break

        self.slow_flag = slow_flag
        valid_request, single_profile = False, True
   
        profile_pairing_list = self.functions.pull_profile({
            "req": "order_pairing",
        })
        profile_order = profile_pairing_list.pop()

        
        if called_profile == "all":
            if "external" in profile_order: 
                profile_order.remove("external")
            single_profile = False
            valid_request = True
        elif called_profile != "empty" and called_profile != None:
            for profile_list in profile_pairing_list:
                for profile_dict in profile_list:
                    if called_profile == profile_dict["profile"]:
                        profile_pairing_list = [[profile_dict]]  # double list due to "all" parameter
                        profile_order = [called_profile]
                        valid_request = True
                        break
                    
        if not valid_request:
            self.error_messages.error_code_messages({
                "error_code": "cmd-744",
                "line_code": "profile_error",
                "extra": called_profile,
                "extra2": None
            })
        
        with ThreadPoolExecutor() as executor:
            leave_list = []; stop_list = []; delay = 0
            for n, profile in enumerate(profile_order):
                self.log.logger[self.log_key].debug(f"cli_restart -> preparing to leave and stop | profile [{profile}]")
                leave_obj = {
                    "secs": secs,
                    "delay": delay,
                    "profile": profile,
                    "reboot_flag": False,
                    "threaded": True,
                }
                leave_list.append(leave_obj)
                delay = delay+.3
                stop_obj = {
                    "show_timer": False,
                    "profile": profile,
                    "delay": delay,
                    "argv_list": []
                }
                stop_list.append(stop_obj)  
                         
            # leave
            self.print_title("LEAVING CLUSTERS") 
            leave_list[-1]["skip_msg"] = False     
            self.log.logger[self.log_key].info(f"cli_restart -> executing leave process against profiles found")               
            futures = [executor.submit(self.cli_leave, obj) for obj in leave_list]
            thread_wait(futures)

            self.functions.print_cmd_status({
                "text_start": "Leave network operations",
                "status": "complete",
                "status_color": "green",
                "newline": True,
            })
        
            # stop
            self.log.logger[self.log_key].debug(f"cli_restart -> executing stop process against profiles found")
            self.print_title(f"STOPPING PROFILE {'SERVICES' if called_profile == 'all' else 'SERVICE'}")    
            stop_list[-1]["spinner"] = True
            futures = [executor.submit(self.cli_stop, obj) for obj in stop_list]
            thread_wait(futures)  
            
            self.functions.print_cmd_status({
                "text_start": "Stop network services",
                "status": "complete",
                "status_color": "green",
                "newline": True,
            })        
        
        # seed list title printed in download_service class
        for n, profile in enumerate(profile_order):
            self.log.logger[self.log_key].debug(f"cli_restart -> handling seed list updates against profile [{profile}]")
            self.node_service.set_profile(profile)

            pos = self.node_service.download_constellation_binaries({
                "caller": "update_seedlist",
                "profile": profile,
                "environment": self.config_obj[profile]["environment"],
                "action": self.caller,

            })
            sleep(.5)    
        print(f"\033[{pos['down']}B", end="", flush=True)
        print("")
            
            
        # ====================
        # CONTROLLED START & JOIN OPERATIONS
        # ====================

        if not cli_leave_cmd:
            for profile in profile_order:
                self.set_profile(profile)
                    
                if restart_type == "restart_only":
                    self.log.logger[self.log_key].debug(f"cli_restart -> 'restart_only' option found")
                    link_profiles = self.functions.pull_profile({
                        "profile": profile,
                        "req": "all_link_profiles",
                    })
                    for link_type in link_types:
                        if link_profiles[f"{link_type}_link_enable"]:
                            state = self.functions.test_peer_state({
                                "profile": link_profiles[f"{link_type}_profile"],
                                "skip_thread": False,
                                "simple": True
                            })    
                            
                            if state != "Ready":
                                link_profile = link_profiles[f"{link_type}_profile"]
                                self.log.logger[self.log_key].warning(f"cli_restart -> restart_only with join requested for a profile that is dependent on other profiles | [{profile}] link profile [{link_profile}]")
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
                            
                service_name = self.config_obj[profile]["service"] 
                start_failed_list = []
                if not service_name.startswith("cnng-"): service_name = f"cnng-{service_name}"
                    
                for n in range(1,failure_retries+1):
                    self.log.logger[self.log_key].debug(f"cli_restart -> service[s] associated with [{called_profile}]")
                    self.print_title(f"RESTARTING PROFILE {'SERVICES' if called_profile == 'all' else 'SERVICE'}")
                    self.cli_start({
                        "spinner": False,
                        "profile": profile,
                        "service_name": service_name,
                        "skip_seedlist_title": True,
                    })
                    
                    peer_test_results = self.functions.test_peer_state({
                        "profile": profile,
                        "test_address": "127.0.0.1",
                        "simple": True,
                    })

                    ready_states = self.functions.get_node_states("ready_states",True)
                    if peer_test_results in ready_states:  # ReadyToJoin and Ready
                        self.log.logger[self.log_key].debug(f"cli_restart -> found state [{peer_test_results}] profile [{profile}]")
                        break
                    else:
                        if n == failure_retries:
                            self.log.logger[self.log_key].error(f"cli_restart -> service failed to start [{service_name}] profile [{profile}]")
                            self.functions.print_paragraphs([
                                [profile,0,"red","bold"], ["service failed to start...",1]
                            ])
                            ts = Troubleshooter({"config_obj": self.config_obj})
                            self.show_profile_issues(["-p",profile],ts)
                            self.functions.print_auto_restart_warning()
                            start_failed_list.append(profile)
                            
                        self.functions.print_paragraphs([
                            [" Issue Found: ",0,"yellow,on_red","bold"],
                            [f"{profile}'s service was unable to start properly.",1,"yellow"], 
                            ["Attempting stop/start again",0], 
                            [str(n),0,"yellow","bold"],
                            ["of",0], [str(failure_retries),1,"yellow","bold"]
                        ])
                        sleep(1)
                        self.cli_stop = {
                            "show_timer": False,
                            "profile": profile,
                            "argv_list": []
                        }
                
                if cli_join_cmd or restart_type != "restart_only":
                    environment = self.config_obj[profile]["environment"]
                    self.print_title(f"JOINING [{environment.upper()}] [{profile.upper()}]")   

                    if profile not in start_failed_list:
                        self.log.logger[self.log_key].info(f'cli_restart -> sending to join process. | profile [{profile}]')
                        self.cli_join({
                            "skip_msg": False,
                            "caller": "cli_restart",
                            "skip_title": True,
                            "wait": False,
                            "watch": watch,
                            "dip": dip,
                            "interactive": interactive,
                            "non_interactive": non_interactive,
                            "single_profile": single_profile,
                            "argv_list": ["-p",profile]
                        })
                    else:
                        self.log.logger[self.log_key].error(f'cli_restart -> restart process failed due to improper join, skipping join process. | profile [{profile}]')
                        self.functions.print_paragraphs([
                            [profile,0,"red","bold"], ["did not start properly; therefore,",0,"red"],
                            ["the join process cannot begin",0,"red"], ["skipping",1, "yellow"],
                        ])
                        
        print("")        
        self.functions.print_perftime(performance_start,"restart")
                

    def cli_reboot(self,command_list):

        def do_reboot():
            _ = self.functions.process_command({
                "bashCommand": "sudo reboot",
                "proc_action": "subprocess_devnull",
            })

        self.log.logger[self.log_key].info("user initiated system warm reboot.")
        self.functions.check_for_help(command_list,"reboot")
        
        on_boot = self.config_obj["global_auto_restart"]["on_boot"]
        
        interactive = False if "--ni" in command_list else True

        self.functions.print_header_title({
            "line1": "REBOOT REQUEST",
            "line2": "nodectl",
            "newline": "top",
            "upper": False,
        })
        
        self.functions.print_paragraphs([
            [" WARNING ",0,"yellow,on_red","bold"],
            ["This will reboot your Node!",2,"yellow","bold"],
            
            ["This feature will allow your Node to properly leave the Tessellation network prior to soft booting (rebooting).",0],
            ["This reboot will cause the Node Operator to lose access to the VPS or bare metal system that this Node is running on.",2],
        ])
        
        if on_boot:
            self.functions.print_paragraphs([
                ["nodectl has detected that you have",0],["on_boot",0,"yellow"], ["enabled!",0],
                ["Once your VPS completes it startup, the Node should automatically rejoin the network clusters configured.",2],
            ])
        else:
            self.functions.print_paragraphs([
                ["Once your VPS or bare metal host returns from the soft boot, you will need to manually join the network clusters configured",0],
                ["by issuing the necessary commands.",2],
                ["command:",0,"white","bold"], ["sudo nodectl restart -p all",2,"yellow"]
            ])
        
        confirm = True
        if interactive:
            confirm = self.functions.confirm_action({
                "yes_no_default": "n",
                "return_on": "y",
                "prompt": "Are you SURE you want to leave and reboot?",
                "exit_if": True
            })
        if confirm:
            for profile in reversed(self.profile_names):
                self.set_profile(profile)
                self.cli_leave({
                    "secs": 45,
                    "reboot_flag": True,
                    "skip_msg": True
                })

            self.functions.print_timer({
                "p_type": "cmd",
                "seconds": 15,
                "step": -1,
                "phrase": "Waiting",
                "end_phrase": "gracefully leave",
            })

            self.functions.print_paragraphs([
                ["Leave complete",1,"green","bold"],
                ["Preparing to reboot.  You will lose access after this message appears.  Please reconnect to your Node after a few moments of patience, to allow your server to reboot, initialize, and restart the SSH daemon.",2]
            ])
            sleep(2)
            do_reboot() 
 
                    
        confirm ="y"
        if interactive:
            confirm = input(f"\n  Are you SURE you want to leave and reboot? [n] : ")

        if confirm.lower() == "y" or confirm.lower() == "yes":
            for profile in reversed(self.profile_names):
                self.set_profile(profile)
                self.cli_leave({
                    "secs": 30,
                    "reboot_flag": True,
                    "skip_msg": True
                })
            cprint("  Leave complete","green")
            cprint("  Preparing to reboot...","magenta")
            sleep(2)
            do_reboot()
            
      
    def cli_console(self,command_list) -> tuple:
        self.functions.check_for_help(command_list,self.primary_command)
        console = Menu({
            "config_obj": self.config_obj,
            "profile_names": self.profile_names,
            "functions": self.functions,
        })

        choice = console.build_root_menu(self.primary_command)
        if choice == "q": exit(0)
        return choice
    

    def cli_join(self,command_obj):
        argv_list = command_obj.get("argv_list")
        self.functions.check_for_help(argv_list,"join")

        start_timer = perf_counter()
                
        skip_msg = command_obj.get("skip_msg",False)
        skip_title = command_obj.get("skip_title",False)
        watch_peer_counts = command_obj.get("watch",False)
        single_profile = command_obj.get("single_profile",True)
        upgrade = command_obj.get("upgrade",False)
        interactive = command_obj.get("interactive",False)
        non_interactive = command_obj.get("non_interactive",False)
        dip_status = command_obj.get("dip",False)
        caller = command_obj.get("caller",False)
        
        called_profile = argv_list[argv_list.index("-p")+1]
        self.set_profile(called_profile)
            
        result, snapshot_issues, tolerance_result = False, False, False
        first_attempt = True

        # every 4 seconds updated
        wfd_count, wfd_max = 0, 5  # WaitingForDownload
        dip_count, dip_max = 0, 8 # DownloadInProgress
        ss_count, ss_max = 0, 35 # SessionStarted 
        
        attempt = ""
        
        defined_connection_threshold = .8
        max_timer = 300
        offline_msg = False
        peer_count, old_peer_count, src_peer_count, increase_check = 0, 0, 0, 0
        
        gl0_link = self.functions.config_obj[called_profile]["gl0_link_enable"]
        ml0_link = self.functions.config_obj[called_profile]["ml0_link_enable"]

        states = self.functions.get_node_states("on_network",True)
        break_states = self.functions.get_node_states("past_observing",True)
                
        def print_update():
            nonlocal first_attempt
            if first_attempt:
                first_attempt = False
                self.functions.print_paragraphs([
                    ["",1],["State:",0,"magenta"], ["SessionStarted",0,"yellow"], ["may take up to",0,"magenta"],
                    ["120+",0,"yellow"],["seconds to properly synchronize with peers to enhance join accuracy.",1,"magenta"],
                    [" Max Timer ",0,"yellow,on_blue"],["300",0,"yellow"], ["seconds",1],
                    ["-","half","blue","bold"],
                ])
                
            self.functions.print_clear_line()
            print(colored("  Peers:","cyan"),colored(f"{src_peer_count}","yellow"),
                colored("Connected:","cyan"),colored(f"{peer_count}","yellow"), 
                colored("State:","cyan"),colored(f"{state}","yellow"), 
                colored("Timer:","cyan"),colored(f"{allocated_time}","yellow"),
                end='\r')
                    
        if not skip_title:
            self.print_title(f"JOINING {called_profile.upper()}")  
        
        if not skip_msg:
            self.log.logger[self.log_key].info(f"cli_join -> join starting| profile [{self.profile}]")
            self.functions.print_cmd_status({
                "text_start": "Joining",
                "brackets": self.profile,
                "status": "please wait",
                "status_color": "magenta",
                "newLine": True
            })

        if (gl0_link or ml0_link) and not single_profile:
            found_dependency = False
            if not watch_peer_counts: # check to see if we can skip waiting for Ready
                for link_profile in self.profile_names:
                    for link_type in ["gl0","ml0"]:
                        if eval(f"{link_type}_link"):
                            if self.functions.config_obj[called_profile][f"{link_type}_link_profile"] == link_profile:
                                self.log.logger[self.log_key].debug(f"cli_join -> found [{link_type}] dependency | profile [{called_profile}]")
                                found_dependency = True
                            elif self.functions.config_obj[called_profile][f"{link_type}_link_profile"] == "None" and not found_dependency:
                                self.log.logger[self.log_key].debug(f"cli_join -> found [{link_type}] dependency | profile [{called_profile}] external [{self.functions.config_obj[link_profile][f'{link_type}_link_host']}] external port [{self.functions.config_obj[link_profile][f'{link_type}_link_port']}]")
                                found_dependency = True

            if not found_dependency:
                self.log.logger[self.log_key].debug(f"cli_join -> no dependency found | profile [{called_profile}]")
                single_profile = True

            
        state = self.functions.test_peer_state({
            "profile": self.profile,
            "simple": True
        })
        
        self.log.logger[self.log_key].debug(f"cli_join -> reviewing node state | profile [{self.profile}] state [{state}]")
        self.functions.print_cmd_status({
            "text_start": "Reviewing",
            "brackets": self.profile,
            "status": state,
            "color": "magenta",
            "newline": True,
        })

        if state == "Ready":
            self.log.logger[self.log_key].warning(f"cli_join -> profile already in proper state, nothing to do | profile [{self.profile}] state [{state}]")
            self.functions.print_paragraphs([
                ["Profile already in",0,"green"],
                [" Ready ",0,"grey,on_green","bold"],
                ["state, nothing to do",1,"green"]
            ])
            return
        
        if state == "ApiNotReady":
            self.log.logger[self.log_key].warning(f"cli_join -> service does not seem to be running | profile [{self.profile}] service [{self.service_name}]")
            self.functions.print_paragraphs([
                ["Profile state in",0,"red"], [state,0,"red","bold"],
                ["state, cannot join",1,"red"], ["Attempting to start service [",0],
                [self.service_name.replace('cnng-',''),-1,"yellow","bold"], ["] again.",-1], ["",1]
            ])
            
            self.log.logger[self.log_key].debug(f"cli_join -> attempting to start service | profile [{self.profile}] service [{self.service_name}]")
            self.cli_start({
                "spinner": True,
                "profile": self.profile,
                "service_name": self.service_name,
            })
        
        if self.config_obj[self.profile]["static_peer"]:
            self.log.logger[self.log_key].info(f"cli_join -> sending to node services to start join process | profile [{self.profile}] static peer [{self.config_obj[self.profile]['edge_point']}]")
        join_result = self.node_service.join_cluster({
            "caller": "cli_join",
            "action":"cli",
            "interactive": True if watch_peer_counts or interactive else False, 
        })
      
        if gl0_link or ml0_link:
            if "not Ready" in str(join_result):
                color = "red"
                attempt = " attempt"
            else:
                color = "green"
        else:
            color = "green"
        
        if color == "green":
            for allocated_time in range(0,max_timer):
                sleep(1)
                self.log.logger[self.log_key].debug(f"cli_join -> watching join process | profile [{self.profile}]")
                if allocated_time % 5 == 0 or allocated_time < 1:  # 5 second mark or first attempt
                    if allocated_time % 10 == 0 or allocated_time < 1:
                        # re-check source every 10 seconds
                        src_peer_count = self.functions.get_peer_count({
                            "profile": self.profile,
                            "count_only": True,
                        })

                    peer_count = self.functions.get_peer_count({
                        "peer_obj": {"ip": "127.0.0.1"},
                        "profile": self.profile,
                        "count_only": True,
                    })
                
                    if peer_count == old_peer_count and allocated_time > 1:
                        # did not increase
                        if peer_count == False:
                            self.troubleshooter.setup_logs({"profile": called_profile})
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
                        increase_check += 1
                    if state == "WaitingForDownload":
                        if wfd_count > wfd_max:
                            snapshot_issues = "wfd_break"
                            result = False
                            tolerance_result = False # force last error to print
                            break
                        wfd_count += 1
                    if state == "Offline":
                        offline_msg = True
                        result = False
                        tolerance_result = False
                        break
                    if state == "SessionStarted":
                        if ss_count > ss_max:
                            result = False
                            tolerance_result = False # force last error to print
                            break
                        ss_count += 1
                    if state == "DownloadInProgress":
                        if dip_status:
                            self.functions.print_paragraphs([
                                ["",2],[" IMPORTANT ",0,"red,on_yellow"], ["the",0], ["--dip",0,"yellow"],
                                ["option has been identified.  This will prompt nodectl to execute the",0],
                                ["download_status",0,"magenta"], ["command.",2],
                                ["The",0,],["DownloadInProgress",0,"magenta"], ["stage of the",0],["join cluster",0,"magenta"],
                                ["process can be time consuming. If there's a desire to cancel watching the",0], ["DownloadInProgress",0,"magenta"],
                                ["stage, pressing the",0],["ctrl",0,"blue","bold"],["and",0],["c",0,"blue","bold"],
                                ["will exit this process.",2], 
                                
                                ["Cancelling an issued",0,"green"], ["--dip",0,"yellow"], ["option will",0,"green"], ["NOT",0,"green","bold"], ["harm or halt the join or restart process;",0,"green"],
                                ["instead, it will just exit the visual aspects of this command and allow the Node process to continue in the",0,"green"],
                                ["background.",2,"green"],
                                
                                ["Issue:",0,],["sudo nodectl download_status help",1,"yellow"],
                                ["to learn about the dedicated standalone command.",2],
                            ])
                            if non_interactive: continue_dip = True
                            else:  
                                continue_dip = self.functions.confirm_action({
                                "yes_no_default": "n",
                                "return_on": "y",
                                "prompt_color": "magenta",
                                "prompt": "Watch DownloadInProgress status?",
                                "exit_if": True
                                })
                            if continue_dip:
                                self.show_download_status({
                                    "caller": caller,
                                    "command_list": ["-p", called_profile],
                                })
                                break
                        elif dip_count > dip_max:
                            snapshot_issues = "dip_break"
                            result = False
                            tolerance_result = False # force last error to print
                            break
                        dip_count += 1
                    else:
                        increase_check = 0
                        state = self.functions.test_peer_state({
                            "profile": called_profile,
                            "skip_thread": True,
                            "simple": True,
                        })
                        if not watch_peer_counts:
                            if state in break_states or (single_profile and state in states):
                                print_update()
                                result = True
                                break
                            
                try:
                    connect_threshold = peer_count/src_peer_count
                    if peer_count >= src_peer_count and state != "SessionStarted": 
                        result = True
                    else:
                        if connect_threshold >= defined_connection_threshold and increase_check > 1:
                            if state in break_states:
                                tolerance_result = True
                        else:
                            old_peer_count = peer_count
                except Exception as e:
                    self.log.logger[self.log_key].error(f"cli-join - {e}")
                

                if allocated_time % 1 == 0:  
                    print_update()
                        
                if result or tolerance_result or allocated_time > max_timer or increase_check > 8: # 8*5=40
                    no_new_status = "error" if state not in break_states else state
                    if increase_check > 3:
                        self.functions.print_cmd_status({
                            "text_start": "No new nodes discovered for ~40 seconds",
                            "status": no_new_status,
                            "status_color": "red",
                            "newLine": True
                        })
                    break
            
            # ========================
                
            if snapshot_issues:
                if snapshot_issues == "wfd_break":
                    self.log.logger[self.log_key].error(f"cli_join -> possible issue found | profile [{self.profile}] issue [WaitingForDownload]")
                    self.functions.print_paragraphs([
                        ["",2],["nodectl has detected",0],["WaitingForDownload",0,"red","bold"],["state.",2],
                        ["This is an indication that your Node may be stuck in an improper state.",0],
                        ["Please contact technical support in the Discord Channels for more help.",1],
                    ])                    
                if snapshot_issues == "dip_break":
                    self.log.logger[self.log_key].warning(f"cli_join -> leaving watch process due to expired waiting time tolerance | profile [{self.profile}] state [DownloadInProgress]")
                    self.functions.print_paragraphs([
                        ["",2],["nodectl has detected",0],["DownloadInProgress",0,"yellow","bold"],["state.",2],
                        ["This is",0], ["not",0,"green","bold"], ["an issue; however, Nodes may take",0],
                        ["longer than expected time to complete this process.  nodectl will terminate the",0],
                        ["watching for peers process during this join in order to avoid undesirable wait times.",1],
                    ])       
            elif not result and tolerance_result:
                self.log.logger[self.log_key].warning(f"cli_join -> leaving watch process due to expired waiting time tolerance | profile [{self.profile}]")
                self.functions.print_clear_line()
                self.functions.print_paragraphs([
                    ["",1],["nodectl tolerance connection status of [",0,],
                    [f"{defined_connection_threshold*100}%",-1,"yellow","bold"], ["] met or exceeded successfully,",-1],
                    ["continuing join request.",1]
                ])
            elif not result and not tolerance_result:
                self.log.logger[self.log_key].error(f"cli_join -> may have found an issue during join process; however, this may not be of concern if the Node is in proper state | profile [{self.profile}]")
                self.functions.print_clear_line()
                self.functions.print_paragraphs([
                    ["",1], [" WARNING ",0,"yellow,on_red","bold"], ["Issue may be present?",0,"red"],
                    ["Please issue the following command to review the Node's details.",1,"red"], 
                    ["sudo nodectl check-connection -p <profile_name>",1],
                    ["Follow instructions if error persists",2,"red"],
                    
                    [" NOTE ",0,"grey,on_green"], ["Missing a few Nodes on the Hypergraph independent of the network, is",0,"green"],
                    ["not an issue.  There will be other Nodes leaving and joining the network; possibly, at all times.",1,"green"],
                ])
            if offline_msg:
                self.functions.print_paragraphs([
                    ["",1],[" Please start the node first. ",1,"yellow,on_red"],
                ])
                
        print("")
        self.log.logger[self.log_key].info(f"cli_join -> join process has completed | profile [{self.profile}] result [{join_result}]")
        self.functions.print_cmd_status({
            "text_start": f"Join process{attempt} complete",
            "status": join_result,
            "status_color": color,
            "newline": True
        })
        if peer_count < src_peer_count and not watch_peer_counts:
            call_type = "upgrade" if upgrade else "default"
            self.functions.print_paragraphs([
                [" IMPORTANT ",0,"grey,on_green"], ["It is ok that the peer count < cluster peer count",1,"yellow"],
                ["because watch mode was",0,"yellow"], ["not",0,"red"], [f"chosen by {call_type}.",1,"yellow"],
            ])
            if not upgrade:
                self.functions.print_paragraphs([
                    ["add",0,"yellow"], ["-w",0,"cyan","bold"], ["to wait and show full peer count display.",1,"yellow"],
                ])

        if color == "red":
            self.functions.print_paragraphs([
                ["'sudo nodectl check-connection -p <profile_name>'",2,color]
            ])
            
        stop_timer = perf_counter()
        self.log.logger[self.log_key].debug(f"join process completed in: [{stop_timer - start_timer}s]")
        self.functions.print_clear_line()
        print("")
        
        self.functions.print_cmd_status({
            "text_start": "Checking status",
            "brackets": self.profile,
            "newline": True,
        })

        self.show_system_status({
            "rebuild": True,
            "wait": False,
            "print_title": False,
            "-p": self.profile
        })
                
                
    def cli_leave(self,command_obj):
        profile = command_obj.get("profile", self.profile)
        print_timer = command_obj.get("print_timer", True)
        secs = command_obj.get("secs", 30)
        reboot_flag = command_obj.get("reboot_flag", False)
        skip_msg = command_obj.get("skip_msg", False)
        threaded = command_obj.get("threaded", False)
        leave_obj, backup_line = False, False
        max_retries = 5
                
        sleep(command_obj.get("delay",0))

        api_port = self.functions.config_obj[profile]["public_port"]
        slow = ""
        
        if self.slow_flag:
            slow = "Slow Reset "
            
        self.functions.print_cmd_status({
            "status": profile,
            "text_start": f"{slow}Leaving the cluster for profile",
            "newline": True
        })
        
        if reboot_flag:
             secs = 15 # reboot don't need to wait
                       
        self.node_service.set_profile(profile)
        
        def call_leave_cluster():
            state = self.node_service.leave_cluster({
                "skip_thread": True,
                "threaded": threaded,
                "profile": profile,
                "secs": secs,
                "cli_flag": True,
                "current_source_node": "127.0.0.1",   
            })
            return state

        call_leave_cluster()

        if not skip_msg:
            start = 1
            skip_log_lookup = False
            while True:
                self.log.logger[self.log_key].info(f"cli_leave -> leave in progress | profile [{profile}] port [{api_port}] | ip [127.0.0.1]")
                if start > max_retries+1:
                    self.log.logger[self.log_key].warning(f"Node did not seem to leave the cluster properly, executing leave command again. | profile [{profile}]")
                    call_leave_cluster()

                self.functions.print_cmd_status({
                    "text_start": "Node going",
                    "brackets": "Offline",
                    "text_end": "please be patient",
                    "status": profile,
                    "newline": True,
                })
                progress = {
                    "status": "testing",
                    "text_start": "Retrieving Node Service State",
                    "brackets": profile,
                    "newline": False,
                }
                self.functions.print_cmd_status(progress)
                    
                get_state_obj = {
                    "profile": profile,
                    "caller": "leave",
                    "skip_thread": True,
                    "simple": True,
                    "treaded": threaded,
                }
                state = self.functions.test_peer_state(get_state_obj)
                
                self.functions.print_cmd_status({
                    **progress,
                    "status": state,
                })
                
                if state in self.functions.not_on_network_list:
                    self.log.logger[self.log_key].debug(f"cli_leave -> leave process complete | profile [{profile}] state [{state}] | ip [127.0.0.1]")
                    self.functions.print_cmd_status({
                        "status": "OutOfCluster",
                        "status_color": "green",
                        "text_start": "Service with profile",
                        "text_start": "cluster status",
                        "brackets": profile,
                        "newline": True
                    })
                    break
                elif leave_obj: break
                elif start > 1:
                    if backup_line: print(f'\x1b[1A', end='')
                    self.log.logger[self.log_key].warning(f"cli_leave -> leave process not out of cluster | profile [{profile}] state [{state}] | ip [127.0.0.1]")
                    self.functions.print_cmd_status({
                        "text_start": f"{profile} not out of cluster",
                        "text_color": "red",
                        "status": state,
                        "status_color": "yellow",
                        "newline": True
                    })  
                
                if start > 4:
                    self.log.logger[self.log_key].warning(f"command line leave request reached [{start}] secs without properly leaving the cluster, aborting attempts | profile [{profile}]")
                    if print_timer:
                        self.functions.print_cmd_status({
                            "text_start": "Unable to gracefully leave",
                            "brackets": profile,
                            "status": "skipping",
                            "newline": True,
                            "status_color": "red"
                        })
                    break
                if print_timer:
                    self.prepare_and_send_logs(["-p",profile,"scrap"])
                    try:
                        self.log.logger[self.log_key].debug(f"cli_leave -> leave process waiting for | profile [{profile}] state to be [leaving] | ip [127.0.0.1]")
                        leave_obj = self.send.scrap_log({
                            "profile": profile,
                            "msg": "Wait for Node to transition to leaving",
                            "value": "Node state changed to=Leaving",
                            "key": "message",
                            "thread": False,
                            "timeout": 40,
                            "parent": self,
                        })
                    except Exception as e:
                        self.log.logger[self.log_key].error(f"leave object exception raised [{e}]")
                        
                    try: 
                        timestamp = leave_obj["@timestamp"]
                    except:
                        self.log.logger[self.log_key].warning(f"cli_leave -> leave process unable to verify| profile [{profile}] leave progress | ip [127.0.0.1] - switching to new method")
                        leave_str = "to allow Node to gracefully leave"
                        skip_log_lookup = True
                        sleep(.5)

                    state = self.functions.test_peer_state(get_state_obj)
                    if state in self.functions.not_on_network_list: 
                        self.log.logger[self.log_key].debug(f"cli_leave -> found out of cluster | profile [{profile}] state [{state}] | ip [127.0.0.1] - continuing")
                        break
                    elif start > 2:
                        skip_log_lookup = True
                        
                    if skip_log_lookup:
                        self.log.logger[self.log_key].debug(f"cli_leave -> pausing to allow leave process to complete | profile [{profile}] | ip [127.0.0.1]")
                        self.functions.print_timer({
                            "seconds": secs,
                            "phrase": leave_str,
                            "start": start,
                        })
                    else:
                        leave_obj = False
                        sleep(1)
                        try:
                            self.log.logger[self.log_key].debug(f"cli_leave -> checking for Offline status | profile [{profile}] | ip [127.0.0.1]")
                            leave_obj = self.send.scrap_log({
                                "profile": profile,
                                "msg": "Wait for Node to go offline",
                                "value": "Node state changed to=Offline",
                                "key": "message",
                                "timeout": 20,
                                "timestamp": timestamp if timestamp else False,
                                "parent": self,
                            })
                        except Exception as e:
                            self.log.logger[self.log_key].error(f"leave object exception raised [{e}]")
                            skip_log_lookup = True
                                
                        state = self.functions.test_peer_state(get_state_obj)
                        if state not in self.functions.not_on_network_list and start > 2: 
                            self.log.logger[self.log_key].warning(f"cli_leave -> leave process not out of cluster | profile [{profile}] state [{state}] | ip [127.0.0.1]")
                            sleep(.1) 
                            skip_log_lookup = True      
                            backup_line = True  
                        else: 
                            break         
                else:
                    sleep(5) # silent sleep 
                    
                self.functions.print_clear_line()
                start += 1      
                    
        
    def cli_grab_id(self,command_obj):
        # method is secondary method to obtain node id
        argv_list = command_obj.get("argv_list",[None])
        command = command_obj["command"]
        return_success = command_obj.get("return_success",False)
        skip_display = command_obj.get("skip_display",False)
        outside_node_request = command_obj.get("outside_node_request",False)
        dag_addr_only = command_obj.get("dag_addr_only",False)
        ready_state = command_obj.get("ready_state",False)
        threading = command_obj.get("threading",True)
        profile = command_obj.get("profile",self.profile)
        is_global = command_obj.get("is_global",True)

        nodeid = ""
        ip_address = "127.0.0.1" # default

        balance_only = False
        api_port, nodeid_to_ip, target, is_self, cmd, print_out_list = False, False, False, False, False, False
        wallet_only = True if "-w" in argv_list or "--wallet" in argv_list else False

        if command == "nodeid": 
            title = "NODE ID"
        else:
            title = "DAG ADDRESS"
            if "--balance" in argv_list: 
                balance_only = True
        file, create_csv = False, False
        false_lookups = []

        self.functions.check_for_help(argv_list,command)

        # --file check must be checked first
        if "--file" in argv_list:
            file = argv_list[argv_list.index("--file")+1]
        elif "-p" in argv_list:  # profile
            profile = argv_list[argv_list.index("-p")+1] 
            is_global = False

        if not wallet_only:
            if "-t" in argv_list:
                try:
                    ip_address = argv_list[argv_list.index("-t")+1]
                except:
                    argv_list.append("help")
                target = True
                outside_node_request = True

            if "--port" in argv_list:
                api_port = argv_list[argv_list.index("--port")+1] 
        else:
            outside_node_request = True
            nodeid = argv_list[argv_list.index("-w")+1] 
                                         
        self.log.logger[self.log_key].info(f"Request to display nodeid | type {command}")

        if not outside_node_request and not target:
            self.functions.config_obj["global_elements"]["caller"] = "command_line"
            action_obj = {
                "action": command,
                "functions": self.functions,
            }
            p12 = P12Class(action_obj)
            extract_obj = {
                "global": is_global,
                "profile": profile,
                "return_success": True if self.primary_command == "install" else False
            }  
            if file:
                extract_obj["ext_p12"] = file          

            success = p12.extract_export_config_env(extract_obj) 
            if not success and return_success: 
                return False
        
        if ip_address != "127.0.0.1" or ready_state:
            if target or ready_state:
                t_ip = self.functions.get_info_from_edge_point({
                    "profile": self.profile,
                    "caller": "cli_grab_id",
                    "specific_ip": ip_address,
                })
                api_port = t_ip["publicPort"]
                nodeid = t_ip["id"]
                
            if not api_port:
                try: 
                    api_port = self.functions.config_obj[profile]["public_port"]
                except:
                    self.error_messages.error_code_messages({
                        "error_code": "cmd_1953",
                        "line_code": "profile_error",
                        "extra": profile
                    })

            with ThreadPoolExecutor() as executor:
                self.functions.event = True
                if threading:
                    _ = executor.submit(self.functions.print_spinner,{
                        "msg": f"Pulling Node ID, please wait",
                        "color": "magenta",
                    })                     
                if outside_node_request:
                    for n in range(0,1):
                        cluster_ips = self.functions.get_cluster_info_list({
                            "ip_address": ip_address,
                            "port": api_port,
                            "api_endpoint": "/cluster/info",
                            "error_secs": 3,
                            "attempt_range": 3,
                        })  
                        
                        try:
                            cluster_ips.pop()   
                        except:
                            if ip_address not in false_lookups:
                                false_lookups.append(ip_address)
                            if n > 2 and command != "peers":
                                self.error_messages.error_code_messages({
                                    "error_code": "cmd-2484",
                                    "line_code": "node_id_issue",
                                    "extra": "external" if outside_node_request else None,
                                })
                            sleep(1)
                        else:
                            if ip_address in false_lookups:
                                false_lookups.remove(ip_address)
                            break

                    if command == "peers" and len(false_lookups) > 0:
                        return false_lookups
                            
                    if cluster_ips:
                        for desired_ip in cluster_ips:
                            if desired_ip["id"] == nodeid:     
                                ip_address = desired_ip["ip"]
                                nodeid_to_ip = True
                                break
                    else:
                        nodeid = colored("not found?","red")
                        
                    if not nodeid_to_ip:
                        ip_address = colored("not found?","red")
                    elif command == "dag":
                        pass
                    elif "-l" not in argv_list: nodeid = f"{nodeid[0:8]}....{nodeid[-8:]}"

                elif not nodeid:
                    nodeid = self.functions.get_api_node_info({
                        "api_host": ip_address,
                        "api_port": api_port,
                        "info_list": ["id","host"]
                    })
                    try:
                        ip_address = nodeid[1]
                        nodeid = nodeid[0]
                    except:
                        self.log.logger[self.log_key].warning(f"attempt to access api returned no response | command [{command}] ip [{ip_address}]")
                        nodeid = colored("Unable To Retrieve","red")
                self.functions.event = False           
        else:
            if "-wr" in argv_list:
                cmd = "java -jar /var/tessellation/cl-wallet.jar show-public-key"
            else:
                cmd = "java -jar /var/tessellation/cl-wallet.jar show-id"
        
        if (ip_address == "127.0.0.1" and not wallet_only) or command == "dag":
            with ThreadPoolExecutor() as executor:
                if not nodeid:
                    self.functions.event = True
                    if threading:
                        _ = executor.submit(self.functions.print_spinner,{
                            "msg": f"Pulling {title}, please wait",
                            "color": "magenta",
                        })                     
                    nodeid = self.functions.process_command({
                        "bashCommand": cmd,
                        "proc_action": "poll"
                    })
                    
                self.nodeid = nodeid
                if command == "dag" and not wallet_only:
                    nodeid = self.cli_nodeid2dag([nodeid.strip(),"return_only"]) # convert to dag address
                    
                if ip_address == "127.0.0.1":
                    ip_address = self.ip_address
                    is_self = True
                    
                self.functions.event = False  

        if dag_addr_only:
            return nodeid
        
        if command == "dag":
            if "--csv" in argv_list:
                self.functions.print_cmd_status({
                    "text_start": "Create csv for",
                    "brackets": "show dag rewards",
                    "status": "running"
                })
                create_csv = True 
                if "-np" not in argv_list:
                    argv_list.append("-np")
                if "--output" in argv_list:
                    csv_file_name = argv_list[argv_list.index("--output")+1]
                    if "/" in csv_file_name:
                        self.error_messages.error_code_messages({
                            "error_code": "cmd-442",
                            "line_code": "invalid_output_file",
                            "extra": csv_file_name
                        })
                else:
                    prefix = self.functions.get_date_time({"action": "datetime"})
                    csv_file_name = f"{prefix}-{nodeid[0:8]}-{nodeid[-8:]}-show-dag-data.csv"
                csv_path = f"{self.config_obj[profile]['directory_uploads']}{csv_file_name}"

            # this creates a print /r status during retrieval so placed here to not affect output
            if wallet_only:
                self.functions.is_valid_address("dag",False,nodeid)
                
            consensus = self.cli_check_consensus({
                "caller": "dag",
                "ip_address": ip_address,
                "profile": profile,
            })
                    
            for n in range(0,3):
                wallet_balance = self.functions.pull_node_balance({
                    "ip_address": ip_address,
                    "wallet": nodeid.strip(),
                    "environment": self.config_obj[profile]["environment"]
                })

                if n < 2 and int(float(wallet_balance["balance_dag"].replace(',', ''))) < 1:    
                    self.log.logger[self.log_key].warning("cli_grab_id --> wallet balance came back as 0, trying again before reporting 0 balance.")
                    if n < 1:
                        sleep(.8) # avoid asking too fast
                    else:
                        self.functions.print_paragraphs([
                            ["Balance has come back a",0,"red"], ["0",0,"yellow"], ["after",0,"red"], ["2",0,"yellow"], ["attempts. Making",0,"red"],
                            ["final attempt to find a balance before continuing, after pause to avoid perceived API violations.",1,"red"],
                        ])
                        self.functions.print_timer({
                            "p_type": "cmd",
                            "seconds": 45,
                            "status": "pausing",
                            "step": -1,
                            "phrase": "Waiting",
                            "end_phrase": "before trying again",
                        })
                    continue
                break    
            wallet_balance = SimpleNamespace(**wallet_balance)

        # clear anything off the top of screen
        if "quiet_install" in list(self.command_obj.values()):
            pass
        elif not create_csv:
            self.functions.print_clear_line()

        if not is_self and not wallet_only and not balance_only:
            print_out_list = [
                {
                    "header_elements" : {
                        "IP ADDRESS REQUESTED": ip_address,
                    },
                },
            ]
        if not skip_display:
            if not outside_node_request and not create_csv:
                if not balance_only:            
                    if not file: self.show_ip([None])
                    print_out_list = [
                        {
                            "header_elements" : {
                                "P12 FILENAME": p12.p12_filename,
                                "P12 LOCATION": p12.path_to_p12,
                            },
                            "spacing": 30
                        },
                    ]

            if print_out_list:
                for header_elements in print_out_list:
                    self.functions.print_show_output({
                        "header_elements" : header_elements
                    })   
            
            if "-wr" in argv_list:
                nodeidwr = []
                nodeid = nodeid.split("\n")
                for part in nodeid:
                    part = re.sub('[^A-Za-z0-9]+', '', part)
                    nodeidwr.append(part)
                try:
                    nodeid = f"{nodeidwr[1][1::]}{nodeidwr[2][1::]}"
                except:
                    self.log.logger[self.log_key].error(f"Unable to access nodeid from p12 file.")
                    nodeid = "unable to derive"
            else:
                nodeid = nodeid.strip()
                if nodeid == "":
                    self.log.logger[self.log_key].error(f"Unable to access nodeid from p12 file.")
                    nodeid = "unable to derive"
            header_elements = {
                title: nodeid,
            }

            print_out_list = [
                {
                    "header_elements" : header_elements,
                },
            ]
            
            if create_csv:
                self.functions.create_n_write_csv({
                    "file": csv_path,
                    "rows": [
                            ["ip address","dag address"],
                            [ip_address,nodeid],
                            ["balance","usd value","dag price"],
                            [
                                wallet_balance.balance_dag,
                                wallet_balance.balance_usd,
                                wallet_balance.token_price
                            ]
                        ]
                })
            elif not balance_only:
                for header_elements in print_out_list:
                    self.functions.print_show_output({
                        "header_elements" : header_elements
                    })
                        
            if command == "dag":
                if not create_csv:
                    print_out_list = [
                        {
                            f"{wallet_balance.token_symbol} BALANCE": f"{wallet_balance.balance_dag: <20}",
                            "$USD VALUE": f"{wallet_balance.balance_usd}",
                            f"{wallet_balance.token_symbol} PRICE": f"{wallet_balance.token_price}",
                            "IN CONSENSUS": consensus,
                        }
                    ]
                    if self.config_obj[profile]["layer"] > 0 or balance_only:
                        print_out_list[0].pop("IN CONSENSUS", None)
                
                    for header_elements in print_out_list:
                        self.functions.print_show_output({
                            "header_elements" : header_elements
                        })  
                                    
                if not "-b" in argv_list and not balance_only:
                    total_rewards = 0
                    data = self.get_and_verify_snapshots(375,self.config_obj[profile]["environment"],profile)
                    elapsed = data["elapsed_time"]
                    data = data["data"]
                    show_title = True
                    found = False
                    data_point = 0
                    
                    do_more = False if "-np" in argv_list else True
                    if do_more:
                        console_size = get_terminal_size()
                        more_break = round(console_size.lines)-20  

                    for n, rewards in enumerate(data):
                        for reward in rewards["rewards"]:
                            if reward["destination"] == nodeid:
                                found = True
                                total_rewards += reward["amount"]
                                if show_title:
                                    show_title = False
                                    if create_csv:
                                        self.functions.create_n_write_csv({
                                            "file": csv_path,
                                            "rows": [
                                                    ["timestamp","ordinal","reward","cumulative"],
                                                    [
                                                        data[n]["timestamp"],
                                                        data[n]["ordinal"],
                                                        reward["amount"]/1e8,
                                                        total_rewards/1e8
                                                    ]
                                                ]
                                        })
                                    else:
                                        print_out_list = [
                                            {
                                                "header_elements": {
                                                    "TIMESTAMP": data[n]["timestamp"],
                                                    "ORDINAL": data[n]["ordinal"],
                                                    "REWARD": reward["amount"]/1e8,
                                                    "TOTAL REWARDS": total_rewards/1e8
                                                },
                                                "spacing": 25,
                                                "1": 10,
                                                "2": 13,
                                            },
                                        ]
                                        
                                        for header_elements in print_out_list:
                                            self.functions.print_show_output({
                                                "header_elements" : header_elements
                                            })
                                else: 
                                    if reward["amount"] > 999999:
                                        if create_csv:
                                            self.functions.create_n_write_csv({
                                                "file": csv_path,
                                                "row": [
                                                            data[n]["timestamp"],
                                                            data[n]["ordinal"],
                                                            reward["amount"]/1e8,
                                                            total_rewards/1e8
                                                    ]
                                            })
                                        else:
                                            self.functions.print_paragraphs([
                                                [f'{data[n]["timestamp"]}  ',0,"white"],
                                                [f'{data[n]["ordinal"]: <11}',0,"white"],
                                                [f'{reward["amount"]/1e8: <14}',0,"white"],
                                                [f'{total_rewards/1e8}',1,"white"],
                                            ])                                    
                                            if do_more and data_point % more_break == 0 and data_point > 0:
                                                more = self.functions.print_any_key({
                                                    "quit_option": "q",
                                                    "newline": "both",
                                                })
                                                if more:
                                                    cprint("  Terminated by Node Operator","red")
                                                    return
                                                show_title = True  
                                data_point += 1 
                                
                    if found:
                        elapsed = self.functions.get_date_time({
                            "action": "estimate_elapsed",
                            "elapsed": elapsed
                        })
                        
                    if create_csv:
                        self.functions.print_cmd_status({
                            "text_start": "Create csv for",
                            "brackets": "show dag rewards",
                            "status": "complete",
                            "newline": True,
                        })
                        
                    if found:
                        self.functions.print_paragraphs([
                            ["",1],["Elapsed Time:",0], [elapsed,1,"green"]
                        ])  
            
            
            if create_csv:
                self.functions.print_paragraphs([
                    ["CSV created successfully",1,"green","bold"],
                    ["filename:",0,], [csv_file_name,1,"yellow","bold"],
                    ["location:",0,], [self.config_obj[profile]['directory_uploads'],1,"yellow","bold"]
                ])  
                                                   
        if return_success:    
            if return_success == "set_value":
                self.nodeid = nodeid
            elif nodeid == "unable to derive":
                return False 
            return True
            

    def cli_find(self,argv_list): # ip="empty",dest=None
        self.log.logger[self.log_key].debug("find request initiated...")
        self.functions.check_for_help(argv_list,"find")
        ordhash_lookup = False
        list_file = False
        
        self.profile = argv_list[argv_list.index("-p")+1]
        source_obj = "empty"

        if "--file" in argv_list:
            list_file = argv_list[argv_list.index("--file")+1]
            if not path.isfile(list_file):
                self.error_messages.error_code_messages({
                    "error_code": "cli-4414",
                    "line_code": "file_not_found",
                    "extra": list_file,
                })
            
        if "-s"  in argv_list:
            source_obj = {"ip": "127.0.0.1"} if argv_list[argv_list.index("-s")+1] == "self" else {"ip": argv_list[argv_list.index("-s")+1]}

        target_obj = {"ip":"127.0.0.1"}
        if "-t" in argv_list:
            target_obj = argv_list[argv_list.index("-t")+1]

            if target_obj == "ordinal" or target_obj == "hash":
                ordhash = argv_list[argv_list.index(target_obj)+1]
                ordhash_lookup = True
                try:
                    if target_obj == "ordinal":
                        ordhash = int(ordhash)
                    else:
                        if len(ordhash) < 64 or len(ordhash) > 64: 
                            raise Exception()
                except:
                    self.functions.check_for_help(["help"],"find")

            if ordhash_lookup:
                self.print_title(f"{target_obj} LOOKUP")
                inode = process_snap_files([ordhash], self.set_data_dir(), self.log, False)
                ordhash_inode = list(inode.keys())[0]
                results = discover_snapshots(self.set_data_dir(),self.functions,self.log,ordhash_inode)
                ordhash_lookup, stamp = ordhash_to_ordhash(results, target_obj)
                if target_obj == "ordinal":
                    ordinal = ordhash
                    hash = ordhash_lookup
                else:
                    ordinal = ordhash_lookup
                    hash = ordhash
                
                print_single_ordhash(self.profile,ordinal,hash,ordhash_inode,stamp,self.functions)
                return

            if not isinstance(target_obj,dict):
                target_obj =  {"ip": "127.0.0.1"} if argv_list[argv_list.index("-t")+1] == "self" else {"ip": argv_list[argv_list.index("-t")+1]}
        
        target_ip = target_obj["ip"]
            
        if source_obj == "empty":
            source_obj = self.functions.get_info_from_edge_point({
                "caller": "cli_find",
                "profile": self.profile,
            })

        def pull_peer_results(target_ip, target_obj,source_obj):
            peer_results = self.node_service.functions.get_peer_count({
                "peer_obj": target_obj,
                "edge_obj": source_obj,
                "profile": self.profile,
                "count_consensus": True,
            })

            if peer_results == "error" or peer_results == None:
                self.log.logger[self.log_key].error(f"show count | attempt to access peer count function failed")
                self.error_messages.error_code_messages({
                    "error_code": "cmd-217",
                    "line_code": "service",
                    "extra": None,
                    "extra2": None
                })

            node_found_color = "green" if peer_results["node_online"] == True else "red"
            if target_obj["ip"] == "127.0.0.1" or target_obj["ip"] == "self":
                target_ip = self.ip_address
            if source_obj["ip"] == "127.0.0.1" or source_obj["ip"] == "self":
                source_obj["ip"] = self.ip_address

            id_ip = "ID"
            if len(target_ip) > 127:
                id_ip = "IP"
                target_ip_id = self.functions.get_info_from_edge_point({
                    "profile": self.profile,
                    "caller": "cli_find",
                    "desired_key": "ip",
                    "specific_ip": target_ip,
                })            
                target_ip = f"{target_ip[:8]}...{target_ip[-8:]}"
            else:
                try:
                    target_ip_id = self.functions.get_info_from_edge_point({
                        "profile": self.profile,
                        "caller": "cli_find",
                        "desired_key": "id",
                        "specific_ip": target_ip,
                    })
                except:
                    target_ip_id = "unknown"
            return peer_results, id_ip, target_ip_id, target_ip, node_found_color

        if list_file:
            list_results = []
            with open(list_file,"r") as find_file:
                results = find_file.readlines()
                for n, list_node in enumerate(results):
                    list_node = list_node.strip("\n")
                    if len(list_node) != 128:
                        self.error_messages.error_code_messages({
                            "error_code": "cli_4520",
                            "line_code": "invalid_nodeid",
                            "extra": list_node,
                        })
                    list_node_obj = {"ip": list_node}
                    if n > 0:
                        peer_results_f, _, _, target_ip_f, node_found_color = pull_peer_results(list_node, list_node_obj, source_obj)
                        list_results.append(
                            ( peer_results_f['node_online'], 
                              target_ip_f, 
                              source_obj['ip'],
                              node_found_color
                            )
                        )
                    else:
                        peer_results, id_ip, target_ip_id, target_ip, node_found_color = pull_peer_results(list_node, list_node_obj, source_obj) 
                    
        else:
            peer_results, id_ip, target_ip_id, target_ip, node_found_color = pull_peer_results(target_ip, target_obj, source_obj) 

        if "return_only" in argv_list:
            return target_ip_id
        
        spacing = 21            
        print_out_list = [
            {
                "header_elements" : {
                    "CLUSTER PEERS": peer_results["peer_count"],
                    "READY": peer_results["ready_count"],
                    "PROFILE": self.profile,
                },
                "spacing": spacing
            },
            {
                "header_elements" : {
                    "Observing": peer_results["observing_count"],
                    "WaitingForObserving": peer_results["waitingforobserving_count"],
                    "WaitingForReady": peer_results["waitingforready_count"],
                },
                "spacing": spacing
            },
            {
                "header_elements" : {
                    "DownloadInProgress": peer_results["downloadinprogress_count"],
                    "WaitingForDownload": peer_results["waitingfordownload_count"],
                    "In Consensus": peer_results["consensus_count"],
                },
                "spacing": spacing
            },
            {
                "header_elements" : {
                    "TARGET NODE": target_ip,
                    "SOURCE NODE": source_obj["ip"],
                    "NODE FOUND": colored(f"{str(peer_results['node_online']).ljust(spacing)}",node_found_color),
                },
                "spacing": spacing
            },
        ]

        if list_file:
            for multi_result in list_results:
                print_out_list = print_out_list + [
                    {
                        "header_elements" : {
                            "-SKIP_HEADER1-": multi_result[1],
                            "-SKIP_HEADER2-": source_obj["ip"],
                            "-SKIP_HEADER3-": colored(f"{str(multi_result[0]).ljust(spacing)}",multi_result[3]),
                        },
                        "spacing": spacing
                    }
                ]

        print_out_list = print_out_list+[
            {
                "header_elements" : {
                    f"TARGET {id_ip}": target_ip_id,
                },
                "spacing": spacing
            },
        ]
        
        for header_elements in print_out_list:
            self.functions.print_show_output({
                "header_elements" : header_elements
            })  

        return
            
        
    def cli_nodeid2dag(self,argv_list):
        self.functions.check_for_help(argv_list,"nodeid2dag")
        pkcs_prefix = "3056301006072a8648ce3d020106052b8104000a03420004"  # PKCS prefix + 04 required byte
        
        try:
            nodeid = argv_list[0]
        except:
            nodeid = 0  # force error
        else:
            output_nodeid = f"{nodeid[0:8]}...{nodeid[-8:]}"
        
        if len(nodeid) == 128:
            nodeid = f"{pkcs_prefix}{nodeid}"
        else:
            self.error_messages.error_code_messages({
                "error_code": "cmd-2735",
                "line_code": "node_id_issue",
                "extra": "invalid",
                "extra2": "nodeid2dag"
            })

        nodeid = sha256( bytes.fromhex(nodeid)).hexdigest()
        nodeid = base58.b58encode(bytes.fromhex(nodeid)).decode()
        nodeid = nodeid[len(nodeid)-36:]  

        check_digits = re.sub('[^0-9]+','',nodeid)
        check_digit = 0
        for n in check_digits:
            check_digit += int(n)
            
        if check_digit > 8:
            check_digit = check_digit % 9
            
        dag_address = f"DAG{check_digit}{nodeid}"

        if "return_only" in argv_list:
            return dag_address
        
        print_out_list = [
            {
                "header_elements" : {
                "NODEID": output_nodeid,
                "DAG ADDRESS": dag_address
                },
            },
        ]
        
        for header_elements in print_out_list:
            self.functions.print_show_output({
                "header_elements" : header_elements
            })  
        
        return
                     

    def cli_handle_ipv6(self,argv_list):
        self.functions.check_for_help(argv_list, "ipv6")
        self.log.logger[self.log_key].info("command_line -> request to handle ipv6 issued")

        if "status" in argv_list:
            action = "status"
        elif "enable" in argv_list:
            action = "enable"
        elif "disable" in argv_list:
            action = "disable"
        else:
            self.error_messages.error_code_messages({
                "error_code": "cli-4723",
                "line_code": "invalid_option",
                "extra": "'status', 'enable' or 'disable' not found",
                "extra2": "valid options include 'status', 'enable' and 'disable'",
            })
        
        if "--ni" in argv_list and not "--grub" in argv_list and not "--sysctl" in argv_list and not "--all" in argv_list:
            self.error_messages.error_code_messages({
                "error_code": "cli-4723",
                "line_code": "invalid_option",
                "extra": "--grub, --sysctl, --all",
                "extra2": "non-interactive requires valid options '--grub', '--sysctl', or '--all'",
            })

        handle_ipv6(action,self.log,self.functions,argv_list)
        return


    def cli_upgrade_vps(self,argv_list):
        self.functions.check_for_help(argv_list, "upgrade_vps")
        self.log.logger[self.log_key].info("command_line -> request to upgrade VPS issued")

        interactive = True if not "--ni" in argv_list else False
        do_reboot = True if "--reboot" in argv_list else False

        self.functions.print_header_title({
            "line1": "UPGRADE VPS or SERVER",
            "clear": True,
        })

        self.functions.print_paragraphs([
            [" IMPORTANT ",0,"red,on_yellow"],
            ["Throughout this process, you may need to engage with the command line interface. If the server (VPS) necessitates",0], 
            ["upgrading certain system core functionalities, including:",1],
            ["- core services",1,"yellow"], 
            ["- core kernel upgrades",2,"yellow"], 

            ["If you encounter a",0], ["purple",0,"magenta"], ["or",0], ["pink",0,"magenta"],
            ["full-screen prompt requesting necessary options to be chosen, follow these steps:",1],
            ["- Press the tab key repeatedly until the CONFIRM or OK option is highlighted.",1,"yellow"], 
            ["- Once highlighted, press the ENTER key to allow the upgrade process to complete.",2,"yellow"],

            ["Any necessary modifications to core system elements required for the Node to operate successfully",0],
            ["will be automated through the standard nodectl upgrade process. Therefore, we can accept the",0],
            ["defaults during this process.",2],

            ["Advanced users have the flexibility to select any options required for customized or non-Node operations being completed simultaneously on this VPS.",2,"red"],
        ])

        if interactive:
            self.functions.confirm_action({
                "prompt": "Start VPS update and upgrade?",
                "yes_no_default": "n",
                "return_on": "y",
                "exit_if": True,
            })
        print("")

        self.functions.print_cmd_status({
            "text_start": "Updating VPS/Server Package listings",
            "status": "running",
            "status_color": "yellow",
            "newline": True,
        })
        self.functions.print_paragraphs([
            ["",1],["UPDATE OUTPUT BOX",1,"blue","bold"],["-","half","bold"],
        ])
        _ = self.functions.process_command({
            "bashCommand": "sudo apt -y update",
            "proc_action": "subprocess_run_check_only",
        })
        self.functions.print_paragraphs([
            ["-","half","cyan","bold"],["",1],
        ])

        self.functions.print_cmd_status({
            "text_start": "Upgrading VPS/Server",
            "status": "running",
            "status_color": "yellow",
            "newline": True,
        })
        self.functions.print_paragraphs([
            ["",1],["UPGRADE OUTPUT BOX",1,"blue","bold"],["-","half","bold"],
        ])
        _ = self.functions.process_command({
            "bashCommand": "sudo apt -y upgrade",
            "proc_action": "subprocess_run_check_only",
        })
        self.functions.print_paragraphs([
            ["-","half","cyan","bold"],["",1],
        ])

        self.functions.print_cmd_status({
            "text_start": "VPS/Server updates and upgrades",
            "status": "complete",
            "status_color": "green",
            "newline": True,
        })

        reboot_status = "NO"
        if path.exists('/var/run/reboot-required'):
            reboot_status = "YES"

        self.functions.print_cmd_status({
            "text_start": "Does this server need to rebooted?",
            "status": reboot_status,
            "status_color": "green" if reboot_status == "NO" else "red",
            "newline": True,
        })            

        if do_reboot: reboot_status = "YES"
        if reboot_status == "YES":
            self.functions.print_paragraphs([
                ["",1],["If a message has been presented requesting a system reboot, please gracefully",0,"yellow"],
                ["exit any clusters that this Node is currently participating in before proceeding with the reboot.",0,"yellow"],
                ["The following command will accomplish this for you.",2,"yellow"],
            ])
            self.build_node_class()
            print("")

            if interactive:
                if not do_reboot:
                    self.functions.confirm_action({
                        "prompt": "Reboot the VPS now?",
                        "yes_no_default": "n",
                        "return_on": "y",
                        "exit_if": True,
                    }) 

            self.functions.print_clear_line()
            self.cli_reboot(argv_list)
        else:
            self.functions.print_paragraphs([
                ["",1],["nodectl did not detect that the VPS needs to be restart/rebooted.",2,"green"],
            ])           


    def cli_minority_fork_detection(self,command_obj):
        caller = command_obj.get("caller","cli")
        argv_list = command_obj.get("argv_list",[])
        profile = command_obj.get("profile",False)
        
        self.functions.check_for_help(argv_list,"check_minority_fork")
        environment = False
        
        if "-e" in argv_list:
            environment = argv_list[argv_list.index("-e")+1]
            profile = self.functions.pull_profile({"req":"one_profile_per_env"})
            profile = profile[0]

        if not profile:
            profile = argv_list[argv_list.index("-p")+1]
        if not environment:
            environment = self.config_obj[profile]["environment"]
            
        global_ordinals ={}
        fork_obj = {
            "history": 1,
            "environment": environment,
            "return_values": ["ordinal","lastSnapshotHash"],
            "return_type": "dict",
            "profile": profile,
        }
        
        if caller != "auto_restart":
            adj = "STATE"
            print_error = False
            if self.config_obj[profile]["layer"] > 0:
                adj = "BLOCKCHAIN LAYER"
                print_error = True
            else:
                state = self.functions.test_peer_state({
                    "profile": profile,
                    "simple": True,
                })
                if state != "Ready": 
                    print_error = True    
            
            if print_error:
                self.functions.print_paragraphs([
                    [f" INVALID PROFILE {adj} ",1,"red,on_yellow"],
                    ["Unable to process minority fork detection request",1,"red"],
                ])
                if adj == "STATE":
                    self.functions.print_paragraphs([
                        ["    Profile:",0], [profile,1,"yellow"],
                        ["Environment:",0], [environment,1,"yellow"],
                        ["      State:",0], [state,1,"yellow"]
                    ])
                exit(0)
                
        for n in range(0,2):
            if n == 0: 
                self.log.logger[self.log_key].debug(f"command_line - cli_minority_fork_detection - [{caller}] - profile [{profile}] | fork_obj remote: [{self.functions.be_urls[environment]}].")
                global_ordinals["backend"] = self.functions.get_snapshot(fork_obj)
                if global_ordinals["backend"] is None:
                    self.log.logger[self.log_key].error("check_minority_fork -> backend api endpoint did not return any results.") 
                    global_ordinals["backend"] = {
                        "ordinal": "unknown",
                        "lastSnapshotHash": "unknown",
                    }
            else:
                fork_obj = {
                    **fork_obj,
                    "lookup_uri": f'http://{self.ip_address}:{self.functions.config_obj[profile]["public_port"]}',
                    "header": "json",
                    "get_results": "value",
                    "ordinal": global_ordinals["backend"]["ordinal"],
                    "action": "ordinal",
                    "profile": profile,
                }
                self.log.logger[self.log_key].debug(f"command_line - cli_minority_fork_detection - [{caller}] - profile [{profile}] | retrieving localhost: [{fork_obj['lookup_uri']}].")
                global_ordinals["local"] = self.functions.get_snapshot(fork_obj)
                if global_ordinals["local"] is None: 
                    self.log.logger[self.log_key].error("check_minority_fork -> local api endpoint did not return any results.") 
                    global_ordinals["local"] = {
                        "ordinal": "unknown",
                        "lastSnapshotHash": "unknown",
                    }


        if caller != "cli": return global_ordinals
        
        fork_result = colored("True","red",attrs=["bold"])
        if global_ordinals["local"]["lastSnapshotHash"] == global_ordinals["backend"]["lastSnapshotHash"]:
            fork_result = colored("False","green",attrs=["bold"])
            
        self.functions.print_paragraphs([
            ["",1],[" MINORITY FORK DETECTION ",2,"green,on_blue","bold"],
        ])
        
        print_out_list = [
            {
                "PROFILE": profile,
                "ENVIRONMENT": environment,
                "IP ADDRESS": self.ip_address,
            },
            {
                "LOCAL ORDINAL": global_ordinals["local"]["ordinal"],
                "LOCAL HASH": global_ordinals["local"]["lastSnapshotHash"],
            },
            {
                "REMOTE ORDINAL": global_ordinals["backend"]["ordinal"],
                "REMOTE HASH": global_ordinals["backend"]["lastSnapshotHash"],
            },
            {
                "MINORITY FORK": fork_result,
            },
        ] 
        for header_elements in print_out_list:
            self.functions.print_show_output({
                "header_elements" : header_elements
            })          
        
    
    def cli_check_consensus(self,command_obj):
        profile = command_obj.get("profile",False) 
        caller = command_obj.get("caller","check_consensus")
        argv_list = command_obj.get("argv_list",[])   
        ip_address = command_obj.get("ip_address",self.ip_address)   
        state = command_obj.get("state",False)

        base_indent = 38
        watch_passes = 0
        self.functions.check_for_help(argv_list,"check_consensus")
        nodeid, file, seconds, get_help, range_error = False, False, False, False, False
        check_node_list = []
        
        if "-p" in argv_list:
            profile = argv_list[argv_list.index("-p")+1]
        if "-s" in argv_list:
            ip_address = argv_list[argv_list.index("-s")+1]

        if "-w" in argv_list:
            try: seconds = int(argv_list[argv_list.index("-w")+1])
            except: seconds = 16
            if not isinstance(seconds,int): seconds = 16
            if seconds < 15: 
                seconds = 15
                range_error = True

        if "-id" in argv_list:
            nodeid = argv_list[argv_list.index("-id")+1]
        elif "--id" in argv_list:
            nodeid = argv_list[argv_list.index("--id")+1]
        elif "--file" in argv_list:
            file = argv_list[argv_list.index("--file")+1]
            if not path.exists(file):
                self.error_messages.error_code_messages({
                    "error_code": "cli-4099",
                    "line_code": "file_not_found",
                    "extra": file,
                    "extra2": "requires full path to file, or change directory to file location before executing command."
                })        
        brief = True if "--brief" in argv_list else False
        
        if get_help:
            self.check_for_help("help","check_consensus")

        if self.config_obj[profile]["layer"] > 0 and caller == "check_consensus" and not self.auto_restart:
            self.functions.print_paragraphs([
                ["Currently, Nodes participating in layer1 clusters do not participate in consensus rounds.",2,"red"],
            ])
            exit(0)

        if nodeid and not self.functions.is_valid_address("nodeid",True,nodeid):
            if caller != "check_consensus": 
                return False
            self.error_messages.error_code_messages({
                "error_code": "cli-4079",
                "line_code": "input_error",
                "extra": "invalid nodeid format",
                "extra2": "Is the nodeid format correct?",
            })
            
        with ThreadPoolExecutor() as executor:
            if seconds:
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

            while True:
                if self.functions.cancel_event: exit(0)
                if seconds:
                    watch_passes += 1
                    _ = self.functions.process_command({"proc_action": "clear"})
                    if not brief:
                        self.functions.print_paragraphs([
                            ["Press",0],["'q'",0,"yellow,on_red"], ['to quit',1],
                            ["Do not use",0],["ctrl",0,"yellow"],["and",0],["c",2,"yellow"],
                        ])
                        if range_error:
                            self.functions.print_paragraphs([
                                [" RANGE ERROR ",0,"red,on_yellow"],["using [15] second default.",2]
                            ])              
                if not state:
                    state = self.functions.test_peer_state({
                        "profile": profile,
                        "spinner": True if not self.auto_restart else False,
                        "simple": True,
                    })   
                            
                if nodeid or file:
                    ip_address = self.functions.get_info_from_edge_point({
                        "profile": profile,
                        "caller": "status",
                        "api_endpoint_type": "consensus",
                    })   
                    node_list = self.functions.get_cluster_info_list({
                        "ip_address": ip_address["ip"],
                        "port": ip_address["publicPort"],
                        "attempt_range": 3,
                        "api_endpoint": "/consensus/latest/peers",
                    })  
                    _ = node_list.pop() # clean off counter
                    if file:
                        with open(file,"r") as f:
                            for line in f.readlines():
                                if self.functions.is_valid_address("nodeid",True,line):
                                    check_node_list.append(line.strip("\n"))
                    else:
                        check_node_list = [nodeid]
                else:
                    check_node_list = ["localhost"]
                        
                exists = True
                for n, check_nodeid in enumerate(check_node_list):
                    if check_nodeid != "localhost":
                        exists = any(check_nodeid == node["id"] for node in node_list)
                        ip_address = "unable to derive" # invalid in case doesn't exist to force a False
                        if exists:
                            ip_address = next((node for node in node_list if node.get("id") == check_nodeid), False)["ip"]
                                                
                    consensus = self.functions.get_info_from_edge_point({
                        "profile": profile,
                        "caller": caller,
                        "api_endpoint_type": "consensus",
                        "threaded": True if not self.auto_restart else False,
                        "specific_ip": ip_address,
                    })

                    consensus_match = colored("False","red")
                    try:
                        if consensus['specific_ip_found'][0] == consensus['specific_ip_found'][1]:
                            consensus_match = colored("True","green") if not self.auto_restart else True
                        if state in self.functions.pre_consensus_list:
                            consensus_match = colored("Preparing","yellow") if not self.auto_restart else False
                    except:
                        consensus_match = colored("UnableToDetermine","magenta")
                        
                    self.log.logger[self.log_key].debug(f"cli_check_consensus -> caller [{caller}] -> participating in consensus rounds [{consensus_match}]")
                    if caller != "check_consensus": 
                        return consensus_match
                    
                    c_node_id = f'{consensus["id"][:7]}...{consensus["id"][-7::]}'
                    
                    if n < 1 and not brief:
                        print_out_list = [
                            {
                                "PROFILE": profile,
                                "ENVIRONMENT": self.config_obj[profile]["environment"],
                            },
                            {
                                "IP ADDRESS": ip_address,
                                "NODE ID": c_node_id,
                                "IN CONSENSUS": consensus_match,
                            },
                        ] 
                        for header_elements in print_out_list:
                            self.functions.print_show_output({
                                "header_elements" : header_elements
                            })     
                    else:  
                        indent = base_indent-len(ip_address)  
                        indent2 = 17 if "True" in consensus_match else 18
                        print(f"  {ip_address} {f'{c_node_id}': >{indent}} {f'{consensus_match}': >{indent2}}")

                if seconds:
                    if self.functions.cancel_event: exit(0)
                    if not brief: 
                        self.functions.print_paragraphs([
                            ["",1],["Press",0],["'q'",0,"yellow,on_red"], ['to quit',1],
                            ["Watch passes:",0,"magenta"], [f"{watch_passes}",0,"yellow"],
                            ["Intervals:",0,"magenta"], [f"{seconds}s",1,"yellow"],
                        ])
                    self.functions.print_timer({
                        "p_type": "cmd",
                        "seconds": seconds,
                        "status": "Q)uit" if brief else "waiting",
                        "step": -1,
                        "phrase": "Waiting",
                        "end_phrase": "before updating",
                    })
                else: 
                    break
                  

    def cli_check_tcp_ports(self,command_obj):
        caller = command_obj.get("caller","check_tcp_ports")
        argv_list = command_obj.get("argv_list",[])   
        self.functions.check_for_help(argv_list,"check_tcp_ports")
        profile = "all"
        profile_names = self.profile_names

        if "-p" in argv_list:
            profile = argv_list[argv_list.index("-p")+1]
            if profile not in self.profile_names:
                self.error_messages.error_code_messages({
                    "error_code": "profile_error",
                    "extra": profile,
                })
            profile_names = [profile]

        self.print_title("TCP PORT TESTING")

        timeout = 10
        if "-t" in argv_list:
             timeout = argv_list[argv_list.index("-t")+1]           
        elif "--timeout" in argv_list:
            timeout = argv_list[argv_list.index("--timeout")+1]
        timeout = 10 if not "-t" in argv_list else argv_list[argv_list.index("-t")+1]
        try: timeout = int(timeout)
        except: 
            self.functions.print_paragraphs([
                [" WARNING ",0,"yellow,on_red"], 
                ["Invalid timeout detected, reverting to default 10 seconds",1,"red"]
            ])
            timeout = 10

        tcp_test_results = {
            "data_found": True,
            "recv_data_found": False,
            "send_data_found": False,
            "ext_int": False,
        }

        self.functions.print_cmd_status({
            "text_start": "External Interface IP",
            "status": self.ip_address,
            "status_color": "yellow",
            "newline": True,
        })

        with ThreadPoolExecutor() as executor:
            self.functions.event = False
            _ = executor.submit(self.functions.print_spinner,{
                "msg": f"Identifying network interfaces",
                "color": "magenta",
            }) 
            interface = False
            for interface, addrs in psutil.net_if_addrs().items():
                for addr in addrs:
                    if addr.family == socket.AF_INET:
                        if addr.address == self.ip_address:
                            tcp_test_results["ext_int"] = interface 
            self.functions.event = False
            if not interface:
                self.error_messages.error_code_messages({
                    "error_code": "cli-5038",
                    "line_code": "network_error",
                    "extra": caller
                })
            self.functions.print_cmd_status({
                "text_start": "Identifying network interface",
                "status": interface,
                "status_color": "green",
                "newline": True,
            })

        with ThreadPoolExecutor() as executor:
            self.functions.event = True
            _ = executor.submit(self.functions.print_spinner,{
                "msg": f"Sniffing interface: [{interface}] ...",
                "color": "magenta",
            }) 

            initial_stats = psutil.net_io_counters(pernic=True).get(interface)
            self.functions.event = False

        self.functions.print_cmd_status({
            "text_start": f"Sniffing full interface",
            "brackets": interface,
            "status": "complete",
            "status_color": "green",
            "newline": True,
        })

        if initial_stats is None:
                tcp_test_results["data_found"] = False
        else:
            with ThreadPoolExecutor() as executor:
                self.functions.event = True

                self.functions.print_paragraphs([
                    ["",1],["TCP PORT CHECK ON",0],[f" {profile.upper()} ",0,"white,on_blue"],["TCP PORT ASSIGNMENTS.",1]
                ])

                int_str = colored(interface,"yellow",attrs=["bold"])
                int_str_end = colored("]","magenta")

                _ = executor.submit(self.functions.print_timer,{
                    "p_type": "cmd",
                    "seconds": timeout,
                    "step": -1,
                    "status": "sniffing",
                    "phrase": f"Interface send/receive:",
                    "end_phrase": f"[{int_str}{int_str_end} ... ",
                }) 

                initial_bytes_sent = initial_stats.bytes_sent
                initial_bytes_recv = initial_stats.bytes_recv
                
                sleep(1.5)
                
                current_stats = psutil.net_io_counters(pernic=True).get(interface)
                if current_stats is None:
                    tcp_test_results["data_found"] = False
                else:
                    if current_stats.bytes_sent > initial_bytes_sent:
                        tcp_test_results["send_data_found"] = True
                    if current_stats.bytes_recv > initial_bytes_recv:
                        tcp_test_results["recv_data_found"] = True
                self.functions.event = False

            self.functions.print_cmd_status({
                "text_start": f"Please wait",
                "brackets": str(timeout),
                "text_end": "seconds per interface",
                "newline": True,
            })
            for self.profile in profile_names:
                self.set_profile_api_ports()
                del self.api_ports["cli"]
                for port_int in self.api_ports.values():
                    with ThreadPoolExecutor() as executor:
                        self.functions.event = True
                        port_int_str = colored(port_int,"yellow",attrs=["bold"])
                        port_close_str = colored("]","magenta")
                        port_int_str_end = colored("I/O on [","magenta")+colored(interface,"yellow",attrs=["bold"])+colored("]","magenta")

                        _ = executor.submit(self.functions.print_timer,{
                            "p_type": "cmd",
                            "seconds": timeout,
                            "step": -1,
                            "status": "sniffing",
                            "phrase": f"Port: [{port_int_str}{port_close_str} {port_int_str_end} ... ",
                            
                        }) 
                        tcp_test_results[port_int] = {}
                        tcp_test_results = self.functions.test_for_tcp_packet({
                            "tcp_test_results": tcp_test_results,
                            "timeout": timeout,
                            "interface": interface,
                            "port_int": port_int
                        })
                        sleep(.5)
                        self.functions.event = False
                        self.functions.print_cmd_status({
                            "text_start": f"Sniffing tcp packets",
                            "brackets": str(port_int),
                            "status": "complete",
                            "status_color": "green",
                            "newline": True,
                        })
        print("")

        print_out_list = [
            {
                "EXTERNAL IP": self.ip_address,
                "EXTERNAL INTERFACE": interface,
                "INTERFACE TRAFFIC": colored(str(tcp_test_results["data_found"]),"green" if tcp_test_results["data_found"] else "red"),
            },
        ]
        for port, values in tcp_test_results.items():
            try: int(port)
            except: continue
            inbound = colored(str(values["found_destination"]),"green" if values["found_destination"] else "red")
            outbound = colored(str(values["found_source"]),"green" if values["found_source"] else "red")
            print_obj = {
                "header_elements": {
                    f"TCP {port} INBOUND": inbound, 
                    f"TCP {port} OUTBOUND": outbound,
                },
                "value_spacing_only": True,
                "spacing": 29,
            }
            print_out_list.append(print_obj)

        for header_elements in print_out_list:
            self.functions.print_show_output({
                "header_elements" : header_elements
            })
        print("")

                            
    def passwd12(self,command_list):
        self.log.logger[self.log_key].info("passwd12 command called by user")
        self.functions.check_for_help(command_list,"passwd12")
        profile = self.functions.pull_profile({
            "req": "default_profile"
        })
            
        self.functions.print_header_title({
            "line1": "P12 PASSPHRASE CHANGE",
            "line2": "request initiated",
            "newline": "top",
            "clear": True,
            "upper": False,
        })
        
        self.functions.print_paragraphs([
            [" WARNING !!",2,"yellow,on_red","bold"],
            ["This is a",0,"white","bold"], ["dangerous",0,"red","bold,underline"], ["command.",2,"white","bold"],
            ["A",0], ["backup",0,"cyan","underline"], ["of your old",0], ["p12",0, "yellow"], 
            ["file will be placed in the following Node VPS location.",1],
            ["directory:",0], [self.functions.config_obj[profile]["directory_backups"],2,"yellow","bold"]
        ])

        if self.functions.confirm_action({
            "yes_no_default": "n",
            "return_on": "n",
            "prompt": "Are you sure you want to change the p12 passphrase?",
            "exit_if": False
        }):
            self.log.logger[self.log_key].info(f"request to change p12 cancelled.")
            print(colored("  Action cancelled","cyan"))
            return 0          
        
        # request new passphrase
        
        self.functions.print_paragraphs([
            ["  NOTE  ",0,"yellow,on_red","bold"], ["Your passphrase will",0,"yellow"], 
            ["not",0,"red","bold"], ["show on the screen.",2,"yellow"]
        ])

        while True:
            validated = True
            
            p12_key_name = f'{colored("  Enter your","green")} {colored("p12","cyan",attrs=["bold"])} {colored("file name","green")}: '
            p12_key_name = input(p12_key_name)
            
            p12_location = f'{colored("  Enter your","green")} {colored("p12","cyan",attrs=["bold"])} {colored("path location","green")}: '
            p12_location = input(p12_location)
                
            if p12_location[-1] != "/":
                p12_location = f"{p12_location}/"
            
            if not path.exists(f"{p12_location}{p12_key_name}"):
                validated = False
                
            if validated:
                p12_list = [p12_key_name]
                p12_list.append(p12_location)
                break
            
            self.log.logger[self.log_key].error(f"User entered invalid p12 [name] or [location] options")
            
            self.functions.print_paragraphs([
                ["",1],
                ["p12 file identified was",0,"red"], ["not",0,"yellow","bold"], 
                ["found in Node Operator entered location; otherwise, the path or file name may be wrong.",1,"red"],
                ["p12 full path:",0], [f"{p12_location}{p12_key_name}",2,"yellow"]
            ])
        
        passphrases = []
        for n in range(0,2):
            while True:
                verb = "original" if n == 0 else "new"
                
                pass_request = f'{colored("  Enter your","green")} {colored(verb,"cyan",attrs=["bold"])} {colored("passphrase","green")}: '
                pass1 = getpass(pass_request)
                pass_request = f'{colored("  Confirm your","green")} {colored(verb,"cyan",attrs=["bold"])} {colored("passphrase","green")}: '
                pass2 = getpass(pass_request)
            
                if compare_digest(pass1,pass2):
                    if "'" not in pass1 and '"' not in pass2:
                        if len(pass1) > 9:
                            passphrases.append(pass1)
                            break
                        
                self.log.logger[self.log_key].error(f"{verb} entered passphrase did not match, had a length issue, or did not have proper restrictions.")
                
                self.functions.print_paragraphs([
                    ["",1], ["Passphrase did not",0,"red"], ["match",0,"yellow","bold"], ["or",1,"red","underline"],
                    ["Passphrase did not meet character minimum length of",0,"red"], ["10",0,"yellow","bold"], ["or",1,"red","underline"],
                    ["Passphrase contained a",0,"red"], ['"',0,"yellow","bold"], ["or",1,"red","underline"],
                    ["Passphrase contained a",0,"red"], ["'",0,"yellow","bold"], ["or",2,"red","underline"],
                ])

        print("")
        self.functions.print_cmd_status({
            "text_start": "Passphrase change in progress",
            "newline": True
        })
        self.functions.print_cmd_status({
            "text_start": "Backing up p12 file",
            "status": "running",
            "status_color": "yellow"
        })

        self.functions.print_paragraphs([
            ["",2], [" IMPORTANT ",0,"yellow,on_red","bold"],
            ["Remove this file after verification of passphrase change is completed.",0,"red","bold"],
            ["The backed up file contains ability to access the blockchain using the original passphrase.",2,"red","bold"],
        ])
        
        p12 = P12Class({
            "action": "passwd12",
            "functions": self.functions,
        })
        
        result = p12.change_passphrase({
            "original": passphrases[0],
            "new": passphrases[1],
            "p12_key_name": p12_key_name,
            "p12_location": p12_location
        })

        if result == "success":
            self.log.logger[self.log_key].info(f"Successfully changed p12 passphrase.")
            status = "successful"
            color = "green"
            self.functions.print_paragraphs([
                ["",1], [f"The passphrase for",0,"green"], [p12_key_name,0,"white","bold"],
                ["was successfully changed.  Please update your configuration.",1,"green"],
                ["command:",0], ["sudo nodectl configure",2,"blue","bold"]
            ])
        else:
            self.log.logger[self.log_key].error(f"P12 Passphrase change failed | {result}.")
            status = "failed"
            color = "red"
            self.functions.print_paragraphs([
                ["",1], [f"The passphrase for",0,"red"], [p12_key_name,0,"white","bold"],
                ["was not changed.  Please review your settings and try again.",2,"red"],
                ["error:",0,"red"], [result,1,"yellow"]
            ])

        self.functions.print_cmd_status({
            "text_start": "Passphrase change",
            "status": status,
            "status_color": color,
            "newline": True,
        })      
      

    def cli_create_p12(self,command_list):
        self.functions.check_for_help(command_list,"cli_create_p12")
        p12 = P12Class({"functions": self.functions})  
        p12.solo = True    
        p12.create_individual_p12(self)  


    def cli_node_last_snapshot(self,command_list):
        self.functions.check_for_help(command_list,"node_last_snapshot")
        value_only = True if "value_only" in command_list else False

        profile = command_list[command_list.index("-p")+1]
        snapshot_dir = self.set_data_dir(profile)+"/hash"
        
        if self.config_obj[profile]["layer"] > 0:
            self.error_messages.error_code_messages({
                "error_code": "cli-4977",
                "line_code": "invalid_layer",
                "extra": "1",
            })

        snapshot_subdirs = [path.join(snapshot_dir, name) for name in listdir(snapshot_dir) if path.isdir(path.join(snapshot_dir, name))]

        self.functions.print_paragraphs([
            [" WARNING ",0,"red,on_yellow"], ["This may take some time to complete depending on the size of the snapshot state.",1,"light_yellow"],
            ["The process may take up to 3 minutes.",2,"magenta"],
        ])

        with ThreadPoolExecutor() as executor:
            self.functions.status_dots = True
            status_obj = {
                "text_start": f"Reviewing snapshots",
                "status": "please wait",
                "status_color": "yellow",
                "timeout": False,
                "dotted_animation": True,
                "newline": False,
            }
            _ = executor.submit(self.functions.print_cmd_status,status_obj)

            cpu_count = self.functions.get_distro_details()["info"]["count"]-1

            with ProcessPoolExecutor(max_workers=cpu_count) as executor0:
                results = executor0.map(find_newest, snapshot_subdirs)
            
            newest_time, newest_snapshot = 0, None
            for creation_time, file_path, is_error in results:
                if is_error:
                    self.log.logger[self.log_key].error(is_error)
                elif creation_time > newest_time:
                    newest_time, newest_snapshot = creation_time, file_path

            self.functions.status_dots = False
            self.functions.print_cmd_status({
                **status_obj,
                "status": "completed",
                "status_color": "green",
                "dotted_animation": False,
                "newline": True,
            })

        if value_only: return snapshot_dir, path.basename(newest_snapshot)
        elif not newest_snapshot:
            newest_snapshot = "NotFound"

        print("")
        print_out_list = [
            {
                "PROFILE": profile,
                "TIME STAMP": self.functions.get_date_time({
                                  "action": "convert_to_datetime",
                                  "new_time": newest_time,
                              }),
            },
            {
                "LAST FOUND LOCAL SNAPSHOT": path.basename(newest_snapshot),
            },
        ]
    
        for header_elements in print_out_list:
            self.functions.print_show_output({
                "header_elements" : header_elements
            }) 
        print("")


    def cli_snapshot_chain(self,command_list):
        debug = False
        self.functions.check_for_help(command_list,"display_snapshot_chain")
        self.log.logger[self.log_key].info("cli -> display_snapshot_chain initiated.")

        fix = True if "--fix" in command_list else False
        if fix and not self.config_obj["global_elements"]["developer_mode"]:
            self.functions.check_for_help(["help"],"")

        self.functions.print_header_title({
            "line1": "DISPLAY SNAPSHOT CHAIN REPORT",
            "single_line": True,
            "newline": "both",
        })

        profile = command_list[command_list.index("-p")+1]
        snapshot_dir = self.set_data_dir(profile)

        if fix:
            self.functions.print_paragraphs([
                [" WARNING ",0,"red,on_yellow"], ["This is an advanced feature and should not",0,"red"],
                ["be used unless",0,"red"], ["ABSOLUTELY",0,"yellow"],
                ["necessary.",1,"red"],
                ["This feature can lead to unpredictable and undesired affects on your existing Node.",2,"red"],
                ["nodectl will take your Node offline first.",2],
            ])

        self.functions.print_paragraphs([
            ["To prevent",0,"blue","bold"], ["false-negatives",0,"red"], 
            ["nodectl will take your Node offline first.",2,"blue","bold"],
        ])

        if "-y" not in command_list:
            self.functions.confirm_action({
                "yes_no_default": "n",
                "return_on": "y",
                "prompt_color": "magenta",
                "prompt": f"Continue?",
                "exit_if": True,
            })  
            print("")

        self.log.logger[self.log_key].info("cli -> display_snapshot_chain --fix option detected.")

        old_days = -1
        if fix and "--days" in command_list:
            old_days = command_list[command_list.index("--days")+1]
            self.log.logger[self.log_key].info(f"cli -> display_snapshot_chain remove old snapshots requested [{old_days} days].")
            try:
                old_days = int(old_days)
            except:
                self.error_messages.error_code_messages({
                    "error_code": "cli-5137",
                    "line_code": "invalid_input",
                    "extra": f"--days {old_days}",
                    "extra2": "--days must be a positive integer",
                })
            else:
                if old_days < 1: old_days = -1

            if old_days > 0:
                self.functions.print_paragraphs([
                    ["Removing old snapshot data requested by Node Operator >",0],[str(old_days),0,"yellow"],
                    ["days old",2],
                ])
            if old_days < 30:
                self.functions.print_paragraphs([
                    [" WARNING ",0,"red,on_yellow"],
                    ["Removing snapshot data younger than",0,"red"],
                    ["30",0,"yellow"], ["days can lead to undesirable results.",2,"red"],
                ])

        self.build_node_class()
        self.set_profile(profile)
        self.cli_leave({
            "secs": 30,
            "reboot_flag": False,
            "skip_msg": False,
            "print_timer": True,
            "threaded": False,
        })
        self.cli_stop({
            "show_timer": False,
            "static_nodeid": False,
            "argv_list": []
        })

        self.functions.print_paragraphs([
            [" PATIENCE ",0,"yellow,on_red"],["This could take up to",0],
            ["fifteen",0,"yellow"], ["minutes to complete the entire process.",2],
            ["In the event the process takes longer than the allotted timers (for slower nodes), the",0,"magenta"],
            ["screen may go blank, please do not interrupt the process and allow it to continue",0,"magenta"],
            ["until complete:",0,"magenta"], ["A reasonable extra time frame should be allotted before manually cancelling",0,"yellow"],
            ["this snapshot state analysis.",2,"yellow"],
        ])

        self.functions.print_cmd_status({
            "text_start": "Beginning discovery",
            "newline": True,
        })
        results = discover_snapshots(snapshot_dir, self.functions, self.log)

        if not results["valid"]:
            count_results = set_count_dict()
            merged_dict = {}
        else:
            count_results = results
        #   merged_dict, count_results = merge_snap_results(results,self.functions,self.log,debug)

        snapshot_info_dir = snapshot_dir.replace("incremental_snapshot","snapshot_info")
        count_results["old_days"] = old_days

        start = count_results["lowest_no_inode"]
        if start is None: count_results["lowest_no_inode"] = "n/a"

        # if results["max_ordinal"] > count_results["ord_highest"]:
        #     count_results["ord_highest"] = results["max_ordinal"]
        end = count_results["ord_highest"]
        if end < 0: count_results["ord_highest"] = "n/a"

        self.print_title("ANALYSIS RESULTS")
        print_report(count_results, fix, snapshot_dir, self.functions)

        exit(0)
        # do not go any further - until removal process is refactored

        p_status = colored("True","green")
        if count_results["solo_count"] > 0 or count_results["day_0_old"] < 1: 
            p_status = colored("False","red")

        self.functions.print_paragraphs([
            ["",1], [" WARNING ",0,"red,on_yellow"], ["nodectl is not integrated directly with",0],
            ["Tessellation, which is the",0], ["definitive authority",0,"green","bold"], ["for verifying a Node's",0],
            ["validity. Therefore, this feature uses the term",0],
            ["'in order'",0,"green"], ["instead of",0], ["'valid'.",0,"green"], ["According to the organization, based",0],
            ["on the pairing of ordinals to hashes and the last known snapshot age, nodectl considers whether or not",0],
            ["the Node to be in proper order.",2],

            ["If your Node reaches",0], ["WaitingForDownload",0,"red"], ["and this command indicates that",0],
            ["the chain on this Node is",0], ["'in order',",0,"green"], ["it only means that the chain elements",0],
            ["appear to be correctly aligned.",2],
            
            ["For a definitive assessment of the Node's snapshot DAG chain, nodectl would need to replicate",0],
            ["Tessellation's functionality; instead, it can only direct you to the use of Tessellation's",0],
            ["protocol [HGTP] to further analysis.",2],
        ])

        print_out_list = [
            {
                "-BLANK-": None,
                "PROFILE": profile,
                "IN ORDER": p_status,
            },
        ]

        for header_elements in print_out_list:
            self.functions.print_show_output({
                "header_elements" : header_elements,
            })

        if "--full_report" in command_list:
            np = True if "--np" in command_list else False
            print_full_snapshot_report(
                merged_dict, count_results["length_of_files"],
                get_terminal_size(), self.functions, np, self.log
            )
        if "--json_output" in command_list:
            output_to_file(merged_dict,command_list, self.functions, self.log)

        if not fix:
            print("")
            return

        if count_results["length_of_files"] < 1:
            self.functions.print_paragraphs([
                ["",1],[" WARNING ",0,"yellow,on_red"], 
                ["nodectl was unable to find any ordinal, snapshot, or hash history on this Node?",2,"red"],
                ["In most cases, this indicates that the Node is either new or has never participated",0],
                ["on the configured cluster.",2],
                ["nodectl will now exit.",2,"blue","bold"],
            ])
            return
        
        if count_results["solo_count"] < 1:
            self.functions.print_paragraphs([
                ["",1],[" IN ORDER ",0,"blue,on_green"], 
                ["This Node's snapshot inventory is in order and does not need any further action.",0,"green"],
                ["nodectl will quit with no action.",2,"green"],

                ["If your Node is reaching the",0], ["WaitingForDownload",0,"red"], ["state, the Node may have an",0],
                ["invalid ordinal/hash match, or something is wrong that is out of the scope of nodectl's' abilities.",0],
                ["It is recommended to reach out to Constellation Network support for further troubleshooting.",2],

                ["If you believe you reached this message in error, you will now be offered the option to enter a",0,"magenta"], 
                ["user defined",0,"yellow"], ["starting ordinal below.",2,"magenta"],
            ])
            
            if old_days > -1:
                self.functions.print_paragraphs([
                    ["Remove snapshots request identified and will ignore the start ordinal",0,"red"],
                    ["and remove all ordinals older than",0,"red"], [str(old_days),0,"yellow"], ["days.",1,"red"],
                    ["Regular removal from the identified start ordinal will also be handled.",2],
                ])

            if count_results["ord_lowest"] == "n/a": 
                find_start = Send({
                    "config_obj": self.config_obj,
                    "command_list": command_list,
                    "ip_address": self.ip_address,
                })
                start = find_start.handle_wdf_last_valid()
                if start == "not_found": 
                    start = 0
                elif start > 100:
                    start -= 100

            if self.config_obj[profile]["environment"] == "testnet":
                start = 1933590 # static defined on protocol update waypoint
            self.functions.print_paragraphs([
                ["Please enter a",0], ["start",0,"yellow"], ["ordinal to begin removal process.",1],
                ["Alternatively, you can please",0],["q",0,"yellow"], ["to exit the removal process.",2],
            ])

            start, end = custom_input(start, end, self.functions)
        
        self.functions.print_paragraphs([
            ["",1],["The removal clean up process will take some time to complete.",1],
        ])
        if "-y" not in command_list:
            self.functions.confirm_action({
                "yes_no_default": "n",
                "return_on": "y",
                "prompt_color": "magenta",
                "prompt": f"Start removal process?",
                "exit_if": True,
            })  

        self.functions.print_cmd_status({
            "text_start": "Removing info bookmarks",
            "newline": True,
        })
        sleep(1) # give Node Operator time to read messages
        clean_info(snapshot_info_dir, self.functions, self.log, merged_dict, start, end, old_days, debug)

        print("")
        self.functions.print_cmd_status({
            "text_start": "Removing chain elements",
            "status": "running",
            "status_color": "yellow",
            "newline": True,
        })
        remove_elements(merged_dict,snapshot_dir,self.functions,self.log,start,old_days,debug)
           
        self.functions.print_paragraphs([
            [f"Removal operations complete, please restart profile [{profile}]",0],
            ["to return your Node to operational status.",2],
        ])


    def cli_execute_starchiver(self,command_list):
        self.log.logger[self.log_key].info("cli -> execute_starchiver initiated.")
        self.functions.check_for_help(command_list,"execute_starchiver")

        def set_key_pairs():
            local_path = self.config_obj["global_elements"]["starchiver"]["local_dir"]+"starchiver"
            repo = self.config_obj["global_elements"]["starchiver"]["remote_uri"]
            return local_path, repo

        def send_error(extra2):
            self.error_messages.error_code_messages({
                "error_code": "cli-4814",
                "line_code": "input_error",
                "extra": "unknown values",
                "extra2": extra2
            })

        self.functions.print_cmd_status({
            "text_start": "Preparing starchiver",
            "status": "running",
            "status_color": "yellow",
            "newline": False,
        })

        profile = command_list[command_list.index("-p")+1]
        if profile not in self.functions.profile_names:
            send_error(f"is this a valid profile? [{profile}]")

        self.functions.print_paragraphs([
            [" WARNING ",0,"red,on_yellow"], ["This will execute the starchiver external community",0],
            ["supported script.",2],
            ["USE AT YOUR OWN RISK!",1,"red","bold"], 
            ["The",0], ["starchiver",0,"yellow"], 
            ["script is not supported by Constellation Network; however,",0],
            ["it is a useful script included in nodectl's tool set to help expedite a Node's ability to",0],
            ["join the Constellation cluster of choice.",1],
            ["This will be executed on:",0,"blue","bold"],[self.config_obj[profile]['environment'],1,"yellow"],
            [f"{self.config_obj[profile]['environment']} cluster profile:",0,"blue","bold"],[profile,2,"yellow"],
        ])

        try:
            local_path, repo = set_key_pairs()
        except:
            self.functions.get_includes("remote_only")
            try:
                local_path, repo = set_key_pairs()
            except:
                send_error("make sure you have the proper include file in the includes directory [/var/tessellation/nodectl/includes/].")

        local_path = self.functions.cleaner(local_path,"double_slash")
        data_path = f"/var/tessellation/{profile}/data"
        cluster = self.config_obj[profile]["environment"]
        bashCommand = f"{local_path} --data-path '{data_path}' --cluster '{cluster}'"

        if "--datetime" in command_list:  
            sc_date = command_list[command_list.index("--datetime")+1]
            if self.functions.get_date_time({
                "action": "valid_datetime",
                "new_time": sc_date,
            }):
                try:
                    int(sc_date)
                except:
                    if (sc_date[0] != "'" and sc_date[-1] != "'") and (sc_date[0] != '"' and sc_date[-1] != '"'):
                        sc_date = f"'{sc_date}'"
                bashCommand += f" --datetime {sc_date}"
            else:
                bashCommand += f" --datetime"

        elif "-d" in command_list: bashCommand += " -d"
        elif "-o" in command_list: bashCommand += " -o"

        self.log.logger[self.log_key].debug(f"cli -> execute_starchiver -> executing starchiver | profile [{profile}] | cluster [{cluster}] | command referenced [{bashCommand}]")


        self.functions.print_paragraphs([
            ["The following command will be executed at the terminal.",1],
            ["=","half","blue","bold"],
            [bashCommand,1,"yellow"],
            ["=","half","blue","bold"],["",1]
        ])

        self.functions.confirm_action({
            "yes_no_default": "n",
            "return_on": "y",
            "prompt_color": "magenta",
            "prompt": f"Execute the starchiver script?",
            "exit_if": True,
        })

        if "-d" in command_list and "-o" in command_list:
            send_error("invalid options requested together")

        self.functions.print_header_title({
            "line1": "COMMUNITY STARCHIVER",
            "single_line": True,
            "newline": "both",
        })

        self.functions.print_cmd_status({
            "text_start": "Remove existing starchiver scripts",
            "status": "running",
            "status_color": "yellow",
            "newline": False,
        })
        sleep(.5)
        self.log.logger[self.log_key].debug("cli -> execute_starchiver -> removing existing starchiver if exists.")
        try:
            remove(local_path)
        except:
            self.log.logger[self.log_key].debug("cli -> execute_starchiver -> did not find an existing starchiver script.")
        self.functions.print_cmd_status({
            "text_start": "Remove existing starchiver scripts",
            "status": "complete",
            "status_color": "green",
            "newline": True,
        })    

        self.functions.print_cmd_status({
            "text_start": "Fetching starchiver",
            "status": "running",
            "status_color": "yellow",
            "newline": False,
        })
        sleep(.5)
        self.log.logger[self.log_key].debug(f"cli -> execute_starchiver -> fetching starchiver -> [{repo}] -> [{local_path}]")
        self.functions.download_file({
            "url": repo,
            "local": local_path,
        })
        self.functions.print_cmd_status({
            "text_start": "Fetching starchiver",
            "status": "complete",
            "status_color": "green",
            "newline": True,
        })

        self.functions.print_cmd_status({
            "text_start": "Setting starchiver permissions",
            "status": "running",
            "status_color": "yellow",
            "newline": False,
        })
        sleep(.5)
        self.log.logger[self.log_key].debug(f"cli -> execute_starchiver -> changing starchiver permissions to +x -> [/var/tmp/starchiver]")
        chmod(local_path, 0o755)
        self.functions.print_cmd_status({
            "text_start": "Setting starchiver permissions",
            "status": "complete",
            "status_color": "green",
            "newline": True,
        })

        self.build_node_class()
        self.set_profile(profile)
        self.cli_leave({
            "secs": 30,
            "reboot_flag": False,
            "skip_msg": False,
            "print_timer": True,
            "threaded": False,
        })
        self.cli_stop({
            "show_timer": False,
            "static_nodeid": False,
            "argv_list": []
        })

        self.functions.print_cmd_status({
            "text_start": "Executing starchiver",
            "status": "running",
            "status_color": "yellow",
            "newline": True,
        })

        _ = self.functions.process_command({
            "bashCommand": bashCommand,
            "proc_action": "subprocess_run_check_only",
        })
        
        self.functions.print_cmd_status({
            "text_start": "Executing starchiver",
            "status": "complete",
            "status_color": "green",
            "newline": True,
        })
        if "--restart" in self.command_list:
            self.cli_start({})
            self.cli_join({
                "skip_msg": False,
                "wait": True,
                "argv_list": ["-p",profile],
            })
        else:
            self.functions.print_paragraphs([
                ["",1], ["The",0],["starchiver",0,"yellow"],["script has completed!",2],

                ["Please execute a restart; as soon as possible, to make sure you",0],
                ["are able to join the cluster with as little delay as possible.",2],

                ["The longer you delay, the more snapshots may be produced on the cluster,",0,"magenta"],
                ["the longer it will take for your Node to download the additional snapshots, complete acquisition of the",0,"magenta"],
                ["full chain, and join consensus.",2,"magenta"],
                
                ["If",0,"green"],["auto_restart",0,"yellow","bold"], ["is enabled on this Node, if will restart the",0,"green"],
                ["service automatically for you.",1,"green"],
            ])


    def cli_execute_tests(self,command_list):
        self.log.logger[self.log_key].info("cli -> execute_tests initiated.")
        self.functions.check_for_help(command_list,"execute_tests")

        self.functions.print_header_title({
            "line1": "NODECTL OPERATOR TESTS",
            "single_line": True,
            "newline": "both",
        })

        self.functions.print_paragraphs([
            ["nodectl's",0], ["Node Operator tests",0,"yellow"], ["are designed to execute most of the available commands",0],
            ["associated with nodectl.  It is designed to help test the utility during development.",2],
            ["You may also utilize this script to become acquainted with a comprehensive set of all the commands",0,"yellow"], 
            ["associated with nodectl.",2,"yellow"],
        ])

        self.functions.confirm_action({
            "yes_no_default": "n",
            "return_on": "y",
            "prompt_color": "magenta",
            "prompt": f"Execute the test script?",
            "exit_if": True,
        })

        self.functions.print_cmd_status({
            "text_start": "Remove existing test script",
            "status": "running",
            "status_color": "yellow",
            "newline": False,
        })
        sleep(.5)
        self.log.logger[self.log_key].debug("cli -> execute_tests -> removing existing test script if exists.")
        try:
            remove("/usr/local/bin/nodectl_tests_x86_64")
        except:
            self.log.logger[self.log_key].debug("cli -> execute_tests -> did not find an existing user tests script.")
        self.functions.print_cmd_status({
            "text_start": "Remove existing user tests",
            "status": "complete",
            "status_color": "green",
            "newline": True,
        })    

        self.functions.print_cmd_status({
            "text_start": "Fetching user tests",
            "status": "running",
            "status_color": "yellow",
            "newline": False,
        })
        sleep(.5)
        repo = f"{self.functions.nodectl_download_url}/nodectl_tests_x86_64"
        local_path = "/usr/local/bin/nodectl_tests"
        self.log.logger[self.log_key].debug(f"cli -> execute_tests -> fetching Node Operator tests -> [{repo}] to [{local_path}]")
        self.functions.download_file({
            "url": repo,
            "local": local_path,
        })
        self.functions.print_cmd_status({
            "text_start": "Fetching tests",
            "status": "complete",
            "status_color": "green",
            "newline": True,
        })

        self.functions.print_cmd_status({
            "text_start": "Setting test permissions",
            "status": "running",
            "status_color": "yellow",
            "newline": False,
        })
        sleep(.5)
        self.log.logger[self.log_key].debug(f"cli -> execute_tests -> changing Node Operator tests permissions to +x -> [{local_path}]")
        chmod(local_path, 0o755)
        self.functions.print_cmd_status({
            "text_start": "Setting test permissions",
            "status": "complete",
            "status_color": "green",
            "newline": True,
        })

        self.functions.print_cmd_status({
            "text_start": "Executing tests",
            "status": "running",
            "status_color": "yellow",
            "newline": False,
        })
        sleep(.5)

        bashCommand = f"{local_path}"
        if path.getsize(local_path) < 1:
            self.log.logger[self.log_key].error(f"cli -> execute_tests -> binary file size too small, may not exist [{path.getsize(local_path)}]")
            self.functions.print_paragraphs([
                ["Unable to properly download the necessary binary containing the",0,"red"],
                ["unit tests",0,"yellow"], ["script. It may not have been released for this",0,"red"],
                ["version of",0,"red"], ["nodectl?",0,"yellow"], ["Please refer to the repository to make sure",0,"red"],
                ["the binary is present.",2,"red"]
            ])
            exit(0)
        self.log.logger[self.log_key].debug(f"cli -> execute_tests -> executing Node Operator tests | command referenced [{bashCommand}]")
        _ = self.functions.process_command({
            "bashCommand": bashCommand,
            "proc_action": "subprocess_run",
        })        


    def cli_execute_directory_restructure(self, profile_argv,version=False,non_interactive=False):
        profile_error = False
        profile = None
        executor0, executor1, executor2, executor3, executor4 = False, False, False, False, False

        if not self.auto_restart:
            self.functions.print_header_title({
                "line1": "Handle Data Restructure",
                "newline": "both",
                "single_line": True,
            })

        if isinstance(profile_argv,str):
            profile = profile_argv
        else:
            try:
                profile = profile_argv[profile_argv.index("-p")+1]
            except:
                profile_error = True

        if profile not in self.profile_names:
            profile_error = "profile_error"
        elif self.config_obj[profile]["layer"] > 0:
            profile_error = "invalid_layer"
        elif not self.auto_restart:
            self.functions.print_cmd_status({
                "text_start": "Data directory profile",
                "status": profile,
                "status_color": "yellow",
                "newline": True,
            })
        
        if profile_error and not self.auto_restart:
            self.error_messages.error_code_messages({
                "error_code": "cli-6067",
                "line_code": profile_error,
                "extra": profile,
            })
        elif profile_error:
            return False

        self.functions.set_default_directories()

        run_v = version
        env = self.config_obj[profile]["environment"]

        if not version:
            try:
                self.version_obj = self.functions.handle_missing_version(self.version_class_obj)
                run_v = self.version_obj[env][profile]["node_tess_version"]
            except Exception as e:
                self.log.logger[self.log_key].error(f"cli_execute_directory_restructure -> unable to determine versioning -> error [{e}]")
                self.error_messages.error_code_messages({
                    "error_code": "cli-6109",
                    "line_code": "version_fetch",
                })

        if not self.auto_restart:
            self.functions.print_cmd_status({
                "text_start": "Data migration",
                "brackets": run_v,
                "status": env,
                "status_color": "green",
                "newline": True,
            })

        if not version:
            with ThreadPoolExecutor() as executor0:
                self.functions.status_dots = True
                test_exe = {
                    "text_start": "Validating profile",
                    "brackets": profile,
                    "status": "running",
                    "dotted_animation": True,
                    "status_color": "yellow",
                    "newline": False,
                }
                _ = executor0.submit(self.functions.print_cmd_status,test_exe)

                profile_state = self.functions.test_peer_state({
                    "profile": profile,
                    "simple": True,
                    "current_source_node": "127.0.0.1",
                    "caller": "cli_stop",
                })    

                self.functions.status_dots = False
                if profile_state != "ApiNotReady":
                    self.error_messages.error_code_messages({
                        "error_code": "cli-6134",
                        "line_code": "node_not_offline",
                        "extra": profile,
                    })
                self.functions.print_cmd_status({
                    **test_exe,
                    "status": profile_state,
                    "dotted_animation": False,
                    "newline": True,
                    "status_color": "green",
                })

            self.functions.print_paragraphs([
                ["",1], [" WARNING ",0,"red,on_yellow",'bold'],
                ["A standalone migration request was possibly detected.",2,"magenta"],

                ["This process can",0,"yellow"], ["potentially break",0,"red"], ["the node",0,"yellow"],
                ["if the Node Operator runs this process on a node that does not support",0,"yellow"],
                ["the data structure of a node with a version lower than",0,"yellow"],
                ["v3.x.x.",2,"green"],
                
                ["Please use caution before proceeding.",1,"magenta"],
            ])
            if not non_interactive:
                self.functions.confirm_action({
                    "yes_no_default": "n",
                    "return_on": "y",
                    "prompt": "Migrate data structures?",
                    "prompt_color": "magenta",
                    "exit_if": True,
                })
        elif env != "testnet" and "v3" != version[:2]:
            if not self.auto_restart:
                cprint("  Migrate not needed","red")
            return "not_needed"
        
        bits64, amd = False, False
        data_dir = self.config_obj[profile]["directory_inc_snapshot"]

        if not self.auto_restart:
            self.functions.print_paragraphs([
                ["",1],["Preparing node for snapshot data restructuring.",1,"yellow"],
                ["This may take a few minutes, and the screen may not display",0,"red"],
                ["any output during this time.",0,"red"],["Please be patient.",2,"red","bold"],
            ])

        if not path.isdir(data_dir):
            if self.auto_restart: return False
            self.error_messages.error_code_messages({
                "error_code": "cli-6069",
                "line_code": "config_error",
                "extra": "format",
                "extra2": "Please join Discord and report this error.",
            })

        with ThreadPoolExecutor() as executor1:
            if not self.auto_restart:
                self.functions.status_dots = True
                test_first = {
                    "text_start": "Verifying requirements",
                    "status": "running",
                    "status_color": "yellow",
                    "timeout": False,
                    "dotted_animation": True,
                    "newline": False,
                }
                _ = executor1.submit(self.functions.print_cmd_status,test_first)

            r_color = "magenta"
            r_status = "executing"
            r_brackets = "required"

            self.log.logger[self.log_key].info(f"cli -> execute_directory_restructure -> testing for migration requirement")
            if path.isdir(f"{data_dir}/hash") and path.isdir(f"{data_dir}/ordinal"):
                r_color = "green"
                r_brackets = "passed"
                r_status = "skipping"                

            if not self.auto_restart:
                self.functions.status_dots = False
                self.functions.print_cmd_status({
                    "text_start": "Verifying",
                    "newline": True,
                    "brackets": r_brackets,
                    "status": r_status,
                    "status_color": r_color,
                    "dotted_animation": False,
                })

        if r_status == "skipping": 
            self.log.logger[self.log_key].info("cli -> execute_directory_restructure -> found this process is not needed -> skipping")
            return "not_needed"

        with ThreadPoolExecutor() as executor2:
            if not self.auto_restart:
                self.functions.status_dots = True
                prep = {
                    "text_start": "Preparing",
                    "status": "running",
                    "status_color": "yellow",
                    "dotted_animation": True,
                    "timeout": False,
                    "newline": False,
                }
                _ = executor2.submit(self.functions.print_cmd_status,prep)

            info = self.functions.get_distro_details()
            bits = info["info"].get('bits')
            brand = info["info"].get('vendor_id_raw')
            arch = info["arch"]
            if "AMD" in brand: amd = True
            if bits == 64: bits64 = True

            if not self.auto_restart:
                self.functions.status_dots = False
                self.functions.print_cmd_status({
                    **prep,
                    "newline": True,
                    "status": "complete",
                    "status_color": "green",
                    "dotted_animation": False,
                })

        if not self.auto_restart:
            for item in [("Architecture",arch),("Brand",brand),("Bits",bits)]:
                self.log.logger[self.log_key].info(f"cli -> execute_directory_restructure -> {item[0]}: [{item[1]}]")
                self.functions.print_cmd_status({
                    "text_start": "Found",
                    "brackets": item[0],
                    "status": item[1],
                    "status_color": "grey",
                    "newline": True,
                })

        if (brand == "AuthenticIntel" or brand == "GenuineIntel") and arch.upper() == "X86_64":
            amd = True

        self.log.logger[self.log_key].info(f"cli -> execute_directory_restructure -> migration requirement detected, starting migration.")
        with ThreadPoolExecutor() as executor3:
            if not self.auto_restart:
                self.functions.status_dots = True
                do_fetch = {
                    "text_start": "Fetching migration tool",
                    "status": "running",
                    "status_color": "yellow",
                    "dotted_animation": True,
                    "newline": False,
                }
                _ = executor3.submit(self.functions.print_cmd_status,do_fetch)

            repo = "https://github.com/Constellation-Labs/snapshot-migration/releases/download/v1.0.0/"
            if amd: file = "snapshot-migration-tool_linux_amd"
            else: file = "snapshot-migration-tool_linux_arm"
            if bits64: file = file+"64"
            local_path = f"/var/tmp/{file}"
            repo = f"{repo}{file}"

            self.log.logger[self.log_key].info(f"cli -> execute_directory_restructure -> fetching migration tool -> [{repo}] -> [{local_path}]")
            for n in range(0,4):
                try:
                    self.functions.download_file({
                        "url": repo,
                        "local": local_path,
                    })
                except Exception as e:
                    if n > 2: 
                        self.log.logger[self.log_key].critical(f"cli -> execute_directory_restructure -> fetching migration tool FAILED 3x -> [{repo}] -> [{local_path}]")
                        return False
                    self.log.logger[self.log_key].error(f"cli -> execute_directory_restructure -> fetching migration tool FAILED -> [{repo}] -> [{local_path}]")
                else:
                    self.log.logger[self.log_key].info(f"cli -> execute_directory_restructure -> fetching migration tool SUCCESS -> [{repo}] -> [{local_path}]")
                    break

            sleep(.5)
            self.log.logger[self.log_key].debug(f"cli -> execute_directory_restructure -> changing permissions to +x -> [{local_path}]")
            chmod(local_path, 0o755)

            if not self.auto_restart:
                self.functions.status_dots = False
                self.functions.print_cmd_status({
                    "text_start": "Fetching migration tool",
                    "dotted_animation": False,
                    "status": "complete",
                    "status_color": "green",
                    "newline": True,
                })

        if not self.auto_restart:
            self.functions.print_paragraphs([
                ["",1], [" WARNING ",0,"red,on_yellow"], ["The migration of the data for v3.x.x",0,"yellow"],
                ["may take a few minutes to complete. Please exercise patience while this",0,"yellow"],
                ["process completes.",2,"yellow"],
            ])

        with ThreadPoolExecutor() as executor4:
            if not self.auto_restart:
                self.functions.status_dots = True
                do_exe = {
                    "text_start": "Executing migration tool",
                    "status": "running",
                    "dotted_animation": True,
                    "timeout": False,
                    "status_color": "yellow",
                    "newline": False,
                }
                _ = executor4.submit(self.functions.print_cmd_status,do_exe)

            # https://github.com/Constellation-Labs/snapshot-migration
            # $ ./snapshot-migration-tool -src ./data/incremental_snapshots
            bashCommand = f"{local_path} -src {data_dir}"
            self.log.logger[self.log_key].info(f"cli -> execute_directory_restructure -> executing migration tool -> [{bashCommand}]")
            result = 1

            for n in range(1,4):
                try:
                    result = self.functions.process_command({
                        "bashCommand": bashCommand,
                        "proc_action": "subprocess_run_check_only",
                    })
                    result = result.returncode
                except Exception as e:
                    self.log.logger[self.log_key].error(f"cli -> execute_directory_restructure -> executing migration tool | attempt [{n}] of [3] | error [{e}]")
                else:
                    if result < 1: break
                    self.log.logger[self.log_key].error(f"cli -> execute_directory_restructure -> executing migration tool did not return successful completion. | attempt [{n}] of [3] | error [{result}]")

            status_result = "complete"
            status_color = "green"
            if result < 1:
                self.log.logger[self.log_key].info(f"cli -> execute_directory_restructure -> executing migration tool -> completed [success]")
            else:
                self.log.logger[self.log_key].error(f"cli -> execute_directory_restructure -> executing migration tool -> [failed] with error code [{result}]")
                status_color = "red"
                status_result = "failed"

            if not self.auto_restart:
                self.functions.status_dots = False
                self.functions.print_cmd_status({
                    "text_start": "Executing migration tool",
                    "status": status_result,
                    "status_color": status_color,
                    "newline": True,
                })

        if not self.auto_restart:
            self.functions.print_cmd_status({
                "text_start": "Clean up migration tool",
                "status": "running",
                "status_color": "yellow",
                "newline": False,
                "delay": 0.8,
            })

        c_result = self.functions.remove_files(local_path,"cli_execute_directory_restructure",False,False)
        if not self.auto_restart:
            self.functions.print_cmd_status({
                "text_start": "Clean up migration tool",
                "status": "complete" if c_result else "failed",
                "status_color": "green" if c_result else "red",
                "newline": True,
            })
        
        if result > 0: return False
        return True


    def cli_enable_remote_access(self,command_list):
        if "help" in command_list:
            pass
        elif "disable" in command_list:
            pass
        elif "enable" in command_list:
            self.print_paragraphs([
                [" WARNING ",0,"red,on_yellow"], 
                ["This will allow temporary access to your VPS and Node by an external entity",0,"red","bold"],
                ["In order to administer your Node this remote access will have",0,"red"],
                ["sudo",0,"yellow"], ["rights to your VPS which will offer unfettered access to your Node",0,"red","bold"],
                ["including:",1,"red","bold"],
                ["  - access to root",1],
                ["  - access to your p12 hot wallet",1],
                ["  - access to your key files",1],
                ["  - access to your encryption keys",1],
                ["  - access to everything",2],
                ["Make sure to disable access when the external entity has completed their working session with you.",0,"yellow","bold"],
                ["command:",0,"yellow"], ["sudo nodectl remote_access disable",2],
            ])
        else:
            command_list.append("help")
        self.functions.check_for_help(command_list,"remote_access")        
            

    def cli_prepare_file_download(self, command_list):

        if "--type" not in command_list:
            command_list.append("help")
        elif command_list[command_list.index("--type")+1] not in ["file","p12"]:
            command_list.append("help")
        cleanup = True if "--cleanup" in command_list else False
        title = "PREPARE P12 FOR BACKUP"
        if "--caller" in command_list:
            caller = command_list[command_list.index("--caller")+1]
            if caller == "cli":
                 if not cleanup: 
                    title = "CLEAN UP P12 FILES"
            elif caller == "send_logs":
                title = "PREPARE LOGS FOR DOWNLOAD"
        self.functions.check_for_help(command_list,"prepare_file_download")


        def display_file_results(action, root_path, file):
            file_list = ["*.p12"] if action == "p12" else [path.basename(file)]
            files = self.functions.get_list_of_files({
                "paths": [root_path],
                "files": file_list,
                "exclude_paths": [f"{root_path}/tessellation"],
                "exclude_files": ["*"],
            })
            if len(files) > 0:
                self.functions.print_paragraphs([
                    ["",1], ["Found Files:",1,"yellow"],
                ])
                for _, file in files.items():
                    cprint(f"  - {path.basename(file)}","blue",attrs=["bold"])
            else:
                cprint("  no files found","red")
            print("")

        requirements = ["global_p12"]
        files = []

        root_path = f'/home/{self.config_obj["global_p12"]["nodeadmin"]}'
        root_path = path.normpath(root_path)

        user = self.config_obj["global_p12"]["nodeadmin"]
        action = command_list[command_list.index("--type")+1]

        self.print_title(title)

        status = {
            "text_start": "Preparing",
            "status": "copying",
            "status_color": "yellow",
            "delay": 0.8,
            "newline": False,
        }

        if "-p" in command_list:
            profile = command_list[command_list.index("-p")+1]
            if profile not in self.profile_names:
                self.log.logger[self.log_key].error(f"cli -> prepare_file_download -> profile [{profile}] not found.")
                self.error_messages.error_code_messages({
                    "error_code": "cli-5859",
                    "line_code": "profile_error",
                    "extra": profile,
                })
            requirements = [profile]
        else:
            for profile in self.profile_names:
                if not self.config_obj[profile]["global_p12_key_location"]:
                    requirements.append(profile)

        for profile in requirements:
            key_name = "key_store" if profile == "global_p12" else "p12_key_name"
            key_name = self.config_obj[profile][key_name]
            files.append(key_name)

        if action == "file":
            file = command_list[command_list.index("--type")+2]
            if not path.exists(file):
                self.log.logger[self.log_key].error(f"cli -> prepare_file_download -> unable to find requested file [{file}]")
                self.error_messages.error_code_messages({
                    "error_code": "cli-5837",
                    "line_code": "file_not_found",
                    "extra": file,
                })   
                
            if cleanup:
                self.functions.print_paragraphs([
                    [" WARNING ",1,"red,on_yellow"], 
                    ["The following file will be removed!!",1,"red","bold"],
                ])                
                if not path.exists(f"{root_path}/{path.basename(file)}"):
                    cprint("  File not found, request cancelled, nothing done!","red")
                    exit(0)

                display_file_results(action, root_path, path.basename(file))
                self.functions.confirm_action({
                    "yes_no_default": "n",
                    "return_on": "y",
                    "prompt": f"clean up file?",
                    "exit_if": True,
                })
                remove(f"{root_path}/{path.basename(file)}")
                cprint("  File Removed","green",attrs=["bold"])
                exit(0)
                                                 
            self.functions.print_paragraphs([
                [" WARNING ",1,"red,on_yellow"], ["The following operation should be considered temporary and",0],
                ["has the possibility",0,"red"],["of causing a",0],["a minor security risk,",0,"red"],["on your Node.",2],

                [f"This command will create a copy of the requested file",0,"magenta"],
                [file,0,"yellow"], ["in the root of a non-root user's home directory,",0,"magenta"],
                ["and set the permissions for access via a",0,"magenta"], ["non-root",0,"red","bold"], ["user until removed.",2,"magenta"],

                [f"Once you have completed the backup of your file",0,"green"],
                [file,0,"yellow"],["it is",0,"green"],
                ["recommended",0,"green","bold"], ["that you return to your Node and re-run",0,"green"],
                ["this command with the",0,"green"], ["--cleanup",0,"yellow"], ["option, to remove and",0,"green"],
                ["secure your Node's nodeadmin user from accessing root files.",2,"green"],
            ])
            exists = self.functions.test_file_exists(root_path,path.basename(file))
            if exists and exists != "override":
                cprint("  Skipping request and exiting.","red")
                exit(0)
            status["brackets"] = path.basename(file)
            self.functions.print_cmd_status(status)
            copy2(file,root_path)
            self.functions.print_cmd_status({
                **status,
                "delay": 0,
                "newline": True,
                "status": "complete",
                "status_color": "green"
            })
            self.functions.set_chown(f"{root_path}/{path.basename(file)}", user, user)
        else:
            if cleanup:
                self.functions.print_paragraphs([
                    [" WARNING ",1,"red,on_yellow"], 
                    ["The following file will be removed!!",2,"red","bold"],
                    ["If you want to remove individual files only, use the",0],
                    ["--file",0,"yellow"], ["option instead",1],
                ])                

                found = False
                for file in files:
                    if path.exists(f"{root_path}/{path.basename(file)}"):
                        display_file_results(action, root_path, path.basename(file))
                        found = True
                if not found:
                    cprint("  Unable to find p12 files to remove, nothing to do!!","red")
                    exit(0)

                self.functions.print_paragraphs([
                    ["Please ensure you have your p12 files backed up and in a secure",0,"red"],
                    ["location. This process will only remove the files located in the",0,"red"],
                    ["root",0,"yellow"],["of the nodeadmin user's directory.",0,"red"],
                    ["If you have a custom setup, exercise",0,"red"],["CAUTION",0,"yellow","bold"],
                    ["before continuing!",1,"red"],
                ])
                self.functions.confirm_action({
                    "yes_no_default": "n",
                    "return_on": "y",
                    "prompt": f"clean up p12 files?",
                    "exit_if": True,
                })
                for file in files:
                    remove(f"{root_path}/{path.basename(file)}")

                cprint("  File(s) Removed","green",attrs=["bold"])
                exit(0)

            self.functions.print_paragraphs([
                [" WARNING ",1,"red,on_yellow"], ["The following operation will temporarily",0],
                ["create a minor security risk,",0,"red"],["on your Node.",2],

                ["This command will create copies of your known p12 files, place them into a non-root",0,"magenta"],
                ["user's home directory, and change the",0,"magenta"],
                ["permissions for access via a",0,"magenta"], ["non-root",0,"red","bold"], ["user until removed.",2,"magenta"],

                ["Once you have completed the backup of your p12 keystore files, it is",0,"green"],
                ["very",0,"green","bold"], ["important that you return to your Node and re-run",0,"green"],
                ["this command with the",0,"green"], ["--cleanup",0,"yellow"], ["option, to remove and",0,"green"],
                ["secure your Node's p12 access to proper status.",2,"green"],
            ])
            self.functions.confirm_action({
                "yes_no_default": "n",
                "return_on": "y",
                "prompt": f"Prepare p12 for backup?",
                "exit_if": True,
            })

            for file in files:
                try:
                    exists = self.functions.test_file_exists(root_path,path.basename(file))
                    if exists and exists != "override":
                        continue
                    status["brackets"] = path.basename(file)
                    self.functions.print_cmd_status(status)
                    copy2(file,root_path)
                    self.functions.set_chown(f"{root_path}/{path.basename(file)}", user, user)
                except Exception as e:
                    self.log.logger[self.log_key].error(f"cli -> prepare_file_download -> file copy error [{e}]")
                    self.error_messages.error_code_messages({
                        "error_code": "cli-5870",
                        "line_code": "file_not_found",
                        "extra": file,
                    })
                self.functions.print_cmd_status({
                    **status,
                    "delay": 0,
                    "newline": True,
                    "status": "complete",
                    "status_color": "green"
                })
            
        if not cleanup:
            display_file_results(action, root_path, file)

        verb = "p12"
        if action == "file": verb = "file"
        if caller == "send_logs": verb = "log"
        self.functions.print_cmd_status({
            "text_start": f"{verb} preparation" if not cleanup else f"{verb} cleanup",
            "status": "complete",
            "newline": True,
        })


    def cli_sync_time(self,command_list):
        self.functions.check_for_help(command_list,"sync_node_time")

        if "-v" not in command_list:
            cprint("  option: -v to see details","magenta")
        status = {
            "text_start": "Syncing clock with network",
            "status": "running",
            "status_color": "yellow",
            "newline": False,
            "delay": 0.8,
        }
        self.functions.print_cmd_status(status)
        results, track, source = self.functions.set_time_sync()
        status["newline"] = True
        status["delay"] = 0
        status["status"] = "complete" if "OK" in results else "failed"
        status["status_color"] = "green" if "OK" in results else "red"
        self.functions.print_cmd_status(status)

        if "-v" in command_list:
            self.functions.print_paragraphs([
                ["",1],[" TRACKING OUTPUT ",1,"white,on_blue","bold"],
            ])
            for line in track.split("\n"):
                self.functions.print_paragraphs([
                    [line,1,"green"],
                ])            
            self.functions.print_paragraphs([
                ["",1],[" SOURCE OUTPUT ",1,"white,on_blue","bold"],
            ])
            for line in source.split("\n"):
                self.functions.print_paragraphs([
                    [line,1,"green"],
                ]) 
            print("")


    def clean_files(self,command_obj):
        what = "clear_snapshots" if command_obj["action"] == "snapshots" else "clean_files"
        self.log.logger[self.log_key].info(f"request to {what} inventory by Operator...")
        self.functions.check_for_help(command_obj["argv_list"],what)
        command_obj["functions"] = self.functions
        Cleaner(command_obj)
            

    def export_private_key(self,command_list):
        self.functions.check_for_help(command_list,"export_private_key")
        profile =  command_list[command_list.index("-p")+1]
        
        action_obj = {
            "profile": profile,
            "caller": "command_line",
            "action": "private_key",
            "functions": self.functions,
        }
        p12 = P12Class(action_obj)
        p12.export_private_key_from_p12()
        
    
    def ssh_configure(self,command_obj):
        #,action="enable",port_no=22,install=False):
        command = command_obj["command"]
        argv_list = command_obj["argv_list"]
        user = command_obj.get("user","root")
        do_confirm = command_obj.get("do_confirm",True)
        skip_reload_status = command_obj.get("skip_reload_status",False)

        self.log.logger[self.log_key].info(f"SSH port configuration change initiated | command [{command}]")
        action_print = command
        show_help = False
        action = "disable" if "disable" in command else "enable"
        action = "port" if command == "change_ssh_port" else action
        if command == "disable_user_auth": action = command

        port_no = None
        install = True if "install" in argv_list else False
        uninstall = True if "uninstall" in argv_list else False
        one_off = False
        found_errors = False
        
        if "help" in argv_list:
            show_help = True
        else:
            if "--port" not in argv_list and command == "change_ssh_port":
                show_help = True
            elif "--port" in argv_list:
                port_no = argv_list[argv_list.index("--port")+1]
            else:
                port_no = 22
                
            try:
                port_no = int(port_no)
            except:
                self.log.logger[self.log_key].error(f"SSH Configuration terminated due to invalid or missing port [{port_no}]")
                show_help = True
            else:
                if port_no != 22 and not install:
                    invalid_ports = []
                    for profile in self.functions.config_obj.keys():
                        for used_port in self.functions.config_obj[profile].keys():
                            if "port" in used_port:
                                invalid_ports.append(self.functions.config_obj[profile][used_port])
                            
                    for inv in invalid_ports:
                            if port_no < 1024 or port_no > 65535 or port_no == inv:
                                show_help = True
        if show_help:
            self.functions.print_help({
                "usage_only": True,
                "extended": command
            })
         
        if "quick_install" in argv_list or not do_confirm:
            confirm = True
        else:
            self.functions.print_paragraphs([
                ["",2], [" WARNING ",0,"yellow,on_red","bold"], 
                ["This is an administrative feature!",2,"red","bold"]
            ])
            if action != "port":
                self.functions.print_paragraphs([
                    ["This feature will",0], [action,0,"cyan","underline"], 
                    [user,0], [" SSH ",0,"grey,on_yellow","bold"], ["access for this server (VPS, Bare Metal). It is independent of",0], 
                    ["nodectl",0,"cyan","underline"], [".",-1], ["",2]
                ])
                if action == "disable":
                    self.functions.print_paragraphs([
                        ["Make sure your",0,"red","bold"], ["non-root",0,"red","bold,underline"], ["user access is available",0,"red","bold"],
                        ["before you exit the current terminal shell!",0,"red","bold"], [" (keep open and connected until fully tested and verified.)",2,"red"]
                    ])
            else:
                self.functions.print_paragraphs([
                    ["This feature will change the port number used to access this Node via the Secure Shell Protocol!",1],
                    ["Make sure to update your VPS firewall to match!",1,"red","bold"]
                ])

            confirm = self.functions.confirm_action({
                "prompt": "Are you SURE you want to continue?",
                "return_on": "y",
                "exit_if": True,
                "yes_no_default": "n",
            })
            
        if confirm:
            backup_dir = "/var/tmp/"
            if not install and not uninstall:
                profile = self.functions.pull_profile({"req":"default_profile"})
                backup_dir = self.functions.config_obj[profile]["directory_backups"]
            
            if not path.exists(backup_dir) and not uninstall:
                self.log.logger[self.log_key].warning(f"backup dir did not exist, attempting to create [{backup_dir}]")
                makedirs(backup_dir)

            self.log.logger[self.log_key].info(f"creating a backup of the sshd.config file to [{backup_dir}]")
            date = self.functions.get_date_time({"action":"datetime"})
            copy2("/etc/ssh/sshd_config",f"{backup_dir}sshd_config{date}.bak")
            
            config_file = open("/etc/ssh/sshd_config")
            f = config_file.readlines()
            
            upath = f"/home/{user}/"
            if user == "root": upath = "/root/"
            verb = "not completed"

            with open("/tmp/sshd_config-new","w") as newfile:
                for line in f:
                    if action == "enable" or action == "disable":
                        if line.startswith("PermitRootLogin") or line.startswith("#PermitRootLogin"):
                            if action == "enable":
                                verb = "yes"
                                if path.isfile(f"{upath}.ssh/backup_authorized_keys"):
                                    move(f"{upath}.ssh/backup_authorized_keys",f"{upath}.ssh/authorized_keys")
                                    self.log.logger[self.log_key].info(f"cli -> found and recovered {user} authorized_keys file")
                                else:
                                    found_errors = f"auth_not_found {user}"
                                    self.log.logger[self.log_key].critical(f"cli -> could not find a backup authorized_key file to recover | user {user}")
                            elif action == "disable":
                                verb = "no"
                                if path.isfile(f"{upath}.ssh/authorized_keys"):
                                    move(f"{upath}.ssh/authorized_keys",f"{upath}.ssh/backup_authorized_keys")
                                    self.log.logger[self.log_key].warning(f"cli -> found and renamed authorized_keys file | user {user}")
                                else:
                                    self.log.logger[self.log_key].critical(f"cli -> could not find an authorized_key file to update | {user}")
                            if user == "root":
                                self.log.logger[self.log_key].warning(f"cli -> setting PermitRootLogin to [{verb}] | user [{user}]")
                                newfile.write(f"PermitRootLogin {verb}\n")
                            else:
                                newfile.write(f"{line}")
                        else:
                            newfile.write(f"{line}")
                        action_print = f"{action} {user} user"
                        
                    elif action == "disable_user_auth":
                        if line.startswith("PubkeyAuthentication") or line.startswith("#PubkeyAuthentication"):
                            self.log.logger[self.log_key].warning(f"cli -> found and enabled PubkeyAuthentication for SSH protocol daemon | sshd_config")
                            newfile.write(f"PubkeyAuthentication yes\n")
                        elif line.startswith("PasswordAuthentication") or line.startswith("#PasswordAuthentication"):
                            self.log.logger[self.log_key].warning(f"cli -> found and disabled PasswordAuthentication for SSH protocol daemon | sshd_config")
                            newfile.write(f"PasswordAuthentication no\n")
                        elif line.startswith("KbdInteractiveAuthentication") or line.startswith("#KbdInteractiveAuthentication"):
                            self.log.logger[self.log_key].warning(f"cli -> found and disabled KbdInteractiveAuthentication for SSH protocol daemon | sshd_config")
                            newfile.write(f"KbdInteractiveAuthentication no\n")
                        elif line.startswith("ChallengeResponseAuthentication") or line.startswith("#ChallengeResponseAuthentication"):
                            self.log.logger[self.log_key].warning(f"cli -> found and disabled ChallengeResponseAuthentication for SSH protocol daemon | sshd_config")
                            newfile.write(f"ChallengeResponseAuthentication no\n")
                        else:
                            newfile.write(f"{line}")
                        
                    elif action == "port":
                        action_print = action
                        if not "GatewayPorts" in line and (line.startswith("Port") or line.startswith("#Port")):
                            self.log.logger[self.log_key].warning(f"cli -> found and updated the Port settings for SSH protocol daemon | sshd_config")
                            newfile.write(f"Port {port_no}\n")
                        else:
                            newfile.write(f"{line}")
            
            newfile.close()
            config_file.close()

            # one off check
            if action == "disable_user_auth":
                if path.exists("/etc/ssh/sshd_config.d/50-cloud-init.conf"):
                    copy2("/etc/ssh/sshd_config.d/50-cloud-init.conf",f"{backup_dir}50-cloud-init.conf{date}.bak")
                    one_off = True
                    config_file = open("/etc/ssh/sshd_config.d/50-cloud-init.conf")
                    f = config_file.readlines()
                    with open("/tmp/sshd_config-new2","w") as newfile:
                        for line in f:
                            if line.startswith("PasswordAuthentication") or line.startswith("#PasswordAuthentication"):
                                self.log.logger[self.log_key].warning(f"cli -> found and disabled PasswordAuthentication for SSH protocol daemon | 50-cloud-init.conf")
                                newfile.write(f"PasswordAuthentication no\n")
                            else:
                                newfile.write(f"{line}")
                    newfile.close()
                    config_file.close()
            
            if not skip_reload_status and "quick_install" not in argv_list:
                progress = {
                    "text_start": "Reloading",
                    "text_end": "daemon",
                    "brackets": "SSH",
                    "status": "running"
                }
                self.functions.print_cmd_status(progress)

            if path.isfile("/tmp/sshd_config-new"):
                move("/tmp/sshd_config-new","/etc/ssh/sshd_config")
            self.log.logger[self.log_key].info(f"cli -> moving modified sshd_config into place.")
            if one_off:
                self.log.logger[self.log_key].info(f"cli -> found one-off [50-cloud-init-config] moving modified sshd config file into place.")
                if path.isfile("/tmp/sshd_config-new2"):
                    move("/tmp/sshd_config-new2","/etc/ssh/sshd_config.d/50-cloud-init.conf")
                
            sleep(1)
            self.log.logger[self.log_key].info(f"cli -> restarted sshd service.")
            _ = self.functions.process_command({
                "bashCommand": "service sshd restart",
                "proc_action": "subprocess_devnull",
            })

            self.log.logger[self.log_key].info(f"SSH port configuration change successfully implemented [{action_print}]")
            if one_off:
                self.log.logger[self.log_key].info(f"SSH configuration for an include file [one off] has been updated with password authentication [{verb}]")
                
            if not skip_reload_status and "quick_install" not in argv_list:
                self.functions.print_cmd_status({
                    **progress,
                    "status": "complete",
                    "status_color": "green",
                    "newline": True
                })
            
            if uninstall: return found_errors


    def prepare_and_send_logs(self, command_list):
        result = False
        self.functions.check_for_help(command_list,"send_logs")    
        send = Send({
            "config_obj": self.functions.config_obj,
            "command_list": command_list,
            "ip_address": self.ip_address,
        })             
        if "scrap" in command_list: self.send = send
        else:
            result = send.prepare_and_send_logs()
        
        if result:
            command_list = [
                "--type","file",
                result,
                "--caller", "send_logs",
            ]
            self.cli_prepare_file_download(command_list)


    def backup_config(self,command_list):
        self.log.logger[self.log_key].info("command_line --> backup configuration")
        self.functions.check_for_help(command_list,"backup_config")

        progress = {
            "text_start": "Backing up configuration",
            "status": "running",
            "status_color": "yellow",
            "newline": False,
        }
        self.functions.print_cmd_status({
            **progress
        })

        backup_dir = self.config_obj[self.functions.default_profile]["directory_backups"]
        config_file_path = "/var/tessellation/nodectl/cn-config.yaml"

        c_time = self.functions.get_date_time({"action":"datetime"})
        if not path.isdir(backup_dir):
            makedirs(backup_dir)
        
        dest = f"{backup_dir}backup_cn-config_{c_time}"
        copy2(config_file_path,dest)

        self.functions.print_cmd_status({
            **progress,
            "status": "complete",
            "status_color": "green",
            "newline": True,
        })        

        title1 = "     Backup Date:"
        title2 = " Backup Location:"
        if self.caller == "upgrader":
            title1 = "Backup Date:"
            title2 = "Backup Location:"
        else:
            print()

        self.functions.print_paragraphs([
            [title1,0], [c_time,1,"yellow"],
            [title2,0], [backup_dir,1,"yellow"],
            ["Backup File Name:",0], [f"backup_cn-config_{c_time}",1,"yellow"],
        ])


    # ==========================================
    # upgrade command
    # ==========================================

    def upgrade_nodectl(self,command_obj):
        argv_list = command_obj["argv_list"]
        custom_version, upgrade_chosen = False, False

        self.functions.print_header_title({
            "line1": "UPGRADE NODECTL",
            "show_titles": False,
            "newline": "bottom",
        })
        
        env_set = set()
        
        if command_obj["help"] == "help" or "help" in argv_list:
            self.functions.print_help({
                "extended": self.primary_command
            })

        try:
            for i_profile in self.profile_names:
                environment_name = self.config_obj[i_profile]["environment"]
                env_set.add(self.config_obj[i_profile]["environment"])
        except Exception as e:
            try:
                self.log.logger[self.log_key].critical(f"unable to determine environment type [{environment_name}]")
            except:
                self.log.logger[self.log_key].critical(f"unable to determine environment type [unknown]")
            finally:
                self.error_messages.error_code_messages({
                    "error_code": "cmd-3435",
                    "line_code": "input_error",
                    "extra": e,
                }) 

        try:
            version_obj = self.version_obj[environment_name] # readability
        except:
            version_obj = self.functions.handle_missing_version(command_obj["version_class_obj"])
            version_obj = version_obj[environment_name]

        if self.primary_command == "revision":
            custom_version = self.version_obj["node_nodectl_version"]
            self.functions.print_paragraphs([
                ["Upgrading nodectl over itself!",2,"yellow"],
            ])
        elif "-v" in argv_list: 
            custom_version = argv_list[argv_list.index("-v")+1]
            custom_version = custom_version.lower()
            if custom_version[0] != "v":
                custom_version = f"v{custom_version}"
            self.functions.print_paragraphs([
                [" WARNING ",0,"red,on_yellow"], ["This will skip verification checks and",0],
                ["attempt",0,"red","bold"], ["to upgrade/downgrade your Node's nodectl version to:",0], [custom_version,2,"yellow","bold"],
                ["If you decide to downgrade to a version that meets or falls below the upgrade path requirements",0,"red"],
                ["for nodectl, you might encounter unexpected consequences that could make your Node unmanageable. In these",0,"red"],
                ["situations, it is advisable to re-create the Node and perform a clean installation.",2,"red"],
                ["hint:",0],["sudo nodectl upgrade_path",2,"yellow"],
                ["Are you sure you want to continue?",1,"magenta"],
            ])

        if len(env_set) > 1:
            environment_name = self.functions.print_option_menu({
                "options": list(env_set),
                "let_or_num": "number",
                "return_value": True,
            })

        for i_profile in self.profile_names:
            if self.config_obj[i_profile]["environment"] == environment_name:
                profile = i_profile
                backup_location = self.config_obj[profile]["directory_backups"]
                break

        self.log.logger[self.log_key].info(f"Upgrade request for nodectl for [{environment_name}] using first profile [{profile}].")

        self.functions.print_clear_line()

        def print_prerelease():
            if version_obj["nodectl"]["nodectl_prerelease"] == 'Unknown':
                self.functions.print_paragraphs([
                    [" WARNING ",0,"yellow,on_red"], ["This version may not be valid, or could not be found, cancelling update.",1,"red","bold"],
                ])   
                exit(0)             
            elif version_obj["nodectl"]["nodectl_prerelease"]:
                self.functions.print_paragraphs([
                    [" WARNING ",0,"yellow,on_red"], ["This is a pre-release version and may have developer experimental features, adds or bugs.",1,"red","bold"],
                ])
                
        for n in range(0,2):
            try:
                nodectl_uptodate = self.version_obj[environment_name]["nodectl"]["nodectl_uptodate"]
                break
            except:
                if n > 0:
                    self.error_messages.error_code_messages({
                        "error_code": "cli-5903",
                        "line_code": "version_fetch",
                    })
                self.version_obj = self.functions.handle_missing_version(self.version_class_obj)

        latest_nodectl = version_obj["nodectl"]["current_stable"]
        node_nodectl_version = self.version_obj['node_nodectl_version']

        if nodectl_uptodate and nodectl_uptodate != "current_less" and not custom_version:
            self.log.logger[self.log_key].error(f"Upgrade nodectl to new version request not needed {node_nodectl_version}.")
            up_to_date = "is already up to date..."
            if nodectl_uptodate == "current_greater": up_to_date = "is a version higher than the official release"
            self.functions.print_paragraphs([
                ["Current version of nodectl:",0], [node_nodectl_version,0,"yellow"],
                [up_to_date,1], ["nothing to do",2,"red"]
            ])
            return

        print_prerelease()       

        if custom_version:
            upgrade_chosen = custom_version
        else:
            self.functions.print_paragraphs([
                [" WARNING ",0,"yellow,on_red"], ["You are about to upgrade nodectl.",1,"green","bold"],
                ["You are currently on:",0], [environment_name.upper(),1,"yellow"],
                ["      current version:",0], [node_nodectl_version,1,"yellow"],
                ["latest stable version:",0], [latest_nodectl,1,"yellow"],
                ["    last upgrade path:",0], [self.version_obj["upgrade_path"][0],2,"yellow"],

                ["This node should be",0,"blue","bold"], ["equal to or greater than the last upgrade path",0,"yellow"], 
                ["before attempting to update to the latest stable version.",1,"blue","bold"],
            ])

            if latest_nodectl != self.version_obj["node_nodectl_version"]:
                upgrade_chosen = False
                if node_nodectl_version == self.version_obj["upgrade_path"][0]:
                    upgrade_chosen = latest_nodectl
                    print("")
                    
                if not upgrade_chosen:
                    self.functions.print_header_title({
                        "line1": "MULTIPLE OPTIONS FOUND",
                        "line2": "please choose a version",
                        "show_titles": False,
                        "newline": "both",
                        "upper": False,
                    })
                    self.functions.print_paragraphs([
                        [" WARNING ",0,"red,on_yellow"], ["downgrading to a previous version of nodectl may cause",0,"red"],
                        ["undesirable effects.",0,"red"], ["It is recommended to upgrade to a newer stable version or to",0],
                        ["reinstall a fresh copy of nodectl, at a lower version that suits your needs.",2]
                    ])
                    
                    option_one = self.version_obj["upgrade_path"][0]
                    for v in self.version_obj["upgrade_path"]:
                        if latest_nodectl != v:
                            option_one = v
                            break

                    option = self.functions.print_option_menu({
                        "options": [
                            option_one,
                            latest_nodectl
                        ],
                        "r_and_q": "q",
                        "color": "magenta",
                    })
                    upgrade_chosen = self.version_obj["upgrade_path"][0] # default 
                    if option == "q": 
                        self.functions.print_paragraphs([
                            ["Aborting nodectl upgrade procedure at user's request.",1,"magenta"],
                        ])
                        return 0
                    elif int(option) == 2:
                        upgrade_chosen = latest_nodectl
            elif not upgrade_chosen:
                upgrade_chosen = latest_nodectl
                
        confirm = self.functions.confirm_action({
            "yes_no_default": "n",
            "return_on": "y",
            "prompt": f"Upgrade to {colored(upgrade_chosen,'yellow')} {colored('?','cyan')}",
            "exit_if": False,
        })
        if not confirm:
            if self.mobile: return
            cprint("  Action cancelled by Node Operator.","red")
            exit(0)
        
        self.functions.print_paragraphs([
            ["Upgrading nodectl version from",0], [f"{node_nodectl_version}",0,"yellow"], ["to",0],
            [f"{upgrade_chosen}",2,"yellow"],
            
            ["Detected architecture:",0], [self.arch,1,"yellow"],
            ["WARNING",0,"yellow,on_red"], ["nodectl will exit to upgrade.",1],
            ["Please be",0], ["patient",0,"white,on_red","bold"], ["and allow the upgrade to",0], ["complete",0,"green"],
            ["before continuing to work.",2],
        ])

        upgrade_file = self.node_service.create_files({
            "file": "upgrade",
            "environment_name": environment_name,
            "upgrade_required": True if version_obj["nodectl"]["upgrade"] != "False" else False,
            "pre_release": version_obj["nodectl"]["nodectl_prerelease"],
        })

        try:
            upgrade_file = upgrade_file.replace("NODECTL_VERSION",upgrade_chosen)
            upgrade_file = upgrade_file.replace("NODECTL_OLD",node_nodectl_version)
            upgrade_file = upgrade_file.replace("NODECTL_BACKUP",backup_location)
            upgrade_file = upgrade_file.replace("ARCH",self.arch)
            if version_obj["nodectl"]["upgrade"] == "full":
                upgrade_file = upgrade_file.replace("sudo nodectl upgrade --nodectl_only","sudo nodectl upgrade")
                upgrade_file = upgrade_file.replace("requires a nodectl_only","requires a full upgrade")
        except Exception as e:
            self.log.logger[self.log_key].debug(f"nodectl binary updater was unable to build the upgrade file path | upgrade chosen [{upgrade_chosen}] old [{node_nodectl_version}] backup location [{backup_location}] arch [{self.arch}] | error [{e}]")
            self.error_messages.error_code_messages({
                "error_code": "cli-4718",
                "line_code": "",
                "extra": ""
            })
        upgrade_bash_script = "/var/tmp/upgrade-nodectl"
        with open(upgrade_bash_script,'w') as file:
            file.write(upgrade_file)
        file.close
        sleep(1)  
        chmod("/var/tmp/upgrade-nodectl",0o755)
        
        _ = self.functions.process_command({
            "bashCommand": "sudo /var/tmp/upgrade-nodectl",
            "proc_action": "subprocess_run_check_only",
        })
        
        if self.functions.get_size("/usr/local/bin/nodectl",True) < 1:
            self.functions.print_paragraphs([
                ["The original backed up version of nodectl will be restored",1,"yellow"],
                ["file version:",0],[node_nodectl_version,2,"blue","bold"],
            ])

            self.log.logger[self.log_key].warning(f"nodectl upgrader is restoring [{backup_location}nodectl_{node_nodectl_version}] to [/usr/local/bin/nodectl]")
            if path.isfile(f"{backup_location}nodectl_{node_nodectl_version}"):
                move(f"{backup_location}nodectl_{node_nodectl_version}","/usr/local/bin/nodectl")

            if self.functions.get_size("/usr/local/bin/nodectl",True) < 1:
                self.log.logger[self.log_key].critical(f"nodectl upgrader unable to restore [{backup_location}nodectl_{node_nodectl_version}] to [/usr/local/bin/nodectl]")
                self.functions.print_paragraphs([
                    [" WARNING ",0,"red,on_yellow"], ["unable to restore original nodectl, please manually download via",0,"red"],
                    ["the known",0,"red"], ["wget",0,"yellow"], ["command. See Constellation Network documentation hub for further details.",1,"red"]
                ])
        else:
            self.log.logger[self.log_key].info(f"Upgrade of nodectl to new version successfully completed")
        
        return_value = False
        if path.isfile("/var/tessellation/nodectl/cnng_upgrade_results.txt"):
            with open("/var/tessellation/nodectl/cnng_upgrade_results.txt","r") as f:
                return_value = f.read().strip()
            remove("/var/tessellation/nodectl/cnng_upgrade_results.txt")

        try: 
            remove("/var/tmp/upgrade-nodectl")
            self.log.logger[self.log_key].info("upgrade_nodectl files cleaned up successfully.")
        except Exception as e:
            self.log.logger[self.log_key].error(f"upgrade_nodectl nodectl method unable to clean up files : error [{e}]")
            
        if "return_caller" in argv_list: 
            if "mobile" in argv_list: return ["mobile","return_caller"]
            return "return_caller"
        return return_value if return_value else 0

    # ==========================================
    # reusable methods
    # ==========================================

    def get_and_verify_snapshots(self,snapshot_size, environment, profile, reward_only=False):
        error = True
        return_data = {}
        action = "history" if not reward_only else "rewards_per_id"
        for _ in range(0,5): # 5 attempts
            data = self.functions.get_snapshot({
                "action": action,
                "history": snapshot_size,
                "environment": environment,
                "profile": profile,
            })   
            
            try:
                start_time = datetime.strptime(data[-1]["timestamp"],"%Y-%m-%dT%H:%M:%S.%fZ")
                end_time = datetime.strptime(data[0]["timestamp"],"%Y-%m-%dT%H:%M:%S.%fZ")
                return_data["start_ordinal"] = data[-1]["ordinal"]
                return_data["end_ordinal"] = data[0]["ordinal"]
                return_data["elapsed_time"] = end_time - start_time
            except Exception as e:
                self.log.logger[self.log_key].error(f"received data from backend that wasn't parsable, trying again | [{e}]")
                sleep(2)
            else:
                error = False
                return_data["start_time"] = start_time
                return_data["end_time"] = end_time
                return_data["data"] = data
                break
            
        if error:
            self.error_messages.error_code_messages({
                "error_code": "cmd-3151",
                "line_code": "api_error",
                "extra": None,
            })
        
        return return_data
                    
    # ==========================================
    # print commands
    # ==========================================

    def print_title(self,line):
        self.functions.print_header_title({
            "line1": line,
            "single_line": True,
            "newline": "both"
        })
        

    def print_removed(self,command_obj):
        # command=(str), version={str), new_command=(str), done_exit=(bool), is_new_command=(bool)
        var = SimpleNamespace(**command_obj)
        is_new = command_obj.get("is_new_command",True) # is there a new command to replace?
        done_exit = command_obj.get("done_exit",True) # exit after statement?
        new_command = command_obj["new_command"] if is_new else "n/a" 
        help_hint = "sudo nodectl help" if new_command == "n/a" else f"sudo nodectl {new_command} help"
        
        if var.command[0] == "_":
            var.command = var.command.replace("_","-",1)
        self.log.logger[self.log_key].error(f"[{var.command}] requested --> removed for [{new_command}]")
        self.functions.print_paragraphs([
            [f" WARNING ",0,"white,on_red","bold"], ["requested feature has been",0,"red"], ["removed",0,"red","bold"],["!",1,"red"],
            ["      Feature:",0,"cyan","bold"], [var.command,1,"blue","bold"],
            ["As of version:",0,"cyan","bold"], [var.version,1,"yellow"]
        ])
        if is_new:
            self.functions.print_paragraphs([
                ["  Replacement:",0,"cyan","bold"], [new_command,1,"green","bold"],
                [help_hint,1,"magenta"]
            ])
        if done_exit:
            return 0

                  
if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")      
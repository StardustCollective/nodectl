import re
import base58
import psutil
from hashlib import sha256

from time import sleep, perf_counter
from datetime import datetime, timedelta
from os import system, path, get_terminal_size, remove, SEEK_END, SEEK_CUR
from pathlib import Path
from sys import exit, stdout, stdin
from types import SimpleNamespace
from getpass import getpass
from termcolor import colored, cprint
from secrets import compare_digest

from modules.p12 import P12Class
from concurrent.futures import ThreadPoolExecutor, wait as thread_wait
from .download_status import DownloadStatus
from .status import Status
from .node_service import Node
from .troubleshoot.errors import Error_codes
from .troubleshoot.logger import Logging
from .cleaner import Cleaner
from .troubleshoot.send_logs import Send
from .troubleshoot.ts import Troubleshooter


class CLI():
    
    def __init__(self,command_obj):
        
        self.log = Logging()
        self.command_obj = command_obj

        self.profile = command_obj.get("profile",None)
        self.command_list = command_obj.get("command_list",[])
        self.profile_names = command_obj.get("profile_names",None)
        self.skip_services = command_obj.get("skip_services",False)
        self.auto_restart =  command_obj.get("auto_restart",False)
        self.functions = command_obj["functions"]
        self.ip_address = command_obj["ip_address"]
        self.primary_command = self.command_obj["command"]

        self.config_obj = self.functions.config_obj
        self.version_obj = self.functions.version_obj
                
        self.slow_flag = False
        self.skip_version_check = False
        self.skip_build = False
        self.check_versions_called = False
        self.invalid_version = False
                
        self.current_try = 0
        self.max_try = 2
        
        self.error_messages = Error_codes(self.functions)  
        self.troubleshooter = Troubleshooter({
            "config_obj": self.config_obj,
        })

        if self.profile_names != None:
            self.profile_names = self.functions.clear_global_profiles(self.profile_names)
            
        self.skip_warning_messages = True if "--skip_warning_messages" in self.command_list else False
        
        if not self.skip_services:
            # try:
            # review and change to spread operator if able
            command_obj = {
                "caller": "cli",
                "profile": self.profile,
                "command": self.primary_command,
                "argv": self.command_list,
                "ip_address": self.ip_address,
                "profile_names": self.profile_names,
                "functions": self.functions
            }
            # self.log.logger.debug(f"cli - calling node Obj - [{command_obj}]")
            self.functions.print_cmd_status({
                "text_start": "Acquiring Node details"
            })
            self.node_service = Node(command_obj)
            self.node_service.log = self.functions.log
            self.node_service.functions.set_statics()
            
        elif not self.auto_restart:
            self.functions.print_clear_line()
            self.functions.print_cmd_status({
                "text_start": "Preparing Node details",
                "text_color": "green",
                "delay": .3
            })
            self.functions.print_clear_line()
            
        self.arch = self.functions.get_arch()
            
            
    # ==========================================
    # set commands
    # ==========================================
    
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
        self.log.logger.debug(f"cli - setting profile parameters | profile [{self.profile}]")
        self.service_name = self.functions.get_service_name(self.profile)
        self.api_ports = self.functions.pull_profile({
            "req": "ports",
            "profile": self.profile,
        })
                
   
    def set_profile(self,profile):
        self.functions.pull_profile({  # test if profile is valid
            "profile": profile,
            "req": "exists"
        })
        self.profile = profile
        self.node_service.set_profile(profile)
        self.set_profile_api_ports() 
        

    # ==========================================
    # show commands
    # ==========================================
    
    def show_system_status(self,command_obj):
        rebuild = command_obj.get("rebuild",False)
        do_wait = command_obj.get("wait",True)
        print_title = command_obj.get("print_title",True)
        spinner = command_obj.get("spinner",True)
        threaded = command_obj.get("threaded",False)
        command_list = command_obj.get("command_list",[])
        
        all_profile_request = False
        called_profile = self.profile
        called_command = command_obj.get("called","default")
        
        if called_command == "uptime": print_title = False
        if called_command == "_s": called_command = "status"
        if called_command == "_qs": called_command = "quick_status"
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
                    self.log.logger.error("invalid value for [-w] option, needs to be an integer. Using default of [6].")
                    range_error = True
                watch_seconds = 15
            watch_enabled = True
            if watch_seconds < 6:
                range_error = True
                watch_seconds = 6
                
        with ThreadPoolExecutor() as executor:
            if watch_enabled:
                quit_loop = executor.submit(self.functions.get_user_keypress,{
                    "prompt": None,
                    "prompt_color": "magenta",
                    "options": ["Q"],
                    "quit_option": "Q",
                })
        
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
                
                try:
                    node_id = f"{elements[1][:8]}...{elements[1][-8:]}"
                except:
                    node_id = "unknown"
                
                return restart_time, uptime, node_id
                        
            while True:
                if watch_enabled:
                    watch_passes += 1
                    system("clear")
                    self.functions.print_paragraphs([
                        ["Press",0],["'q'",0,"yellow,on_red"], ['to quit',1],
                        ["Once",0], ["'q'",0,"yellow"], 
                        ["is pressed and the last timer is completed, the program will exit.",1],
                        ["Do not use",0],["Ctrl-c",2,"yellow"],
                    ])
                    if range_error:
                        self.functions.print_paragraphs([
                            [" RANGE ERROR ",0,"red,on_yellow"],["using [15] second default.",2]
                        ]) 
                    if quit_loop._state == "FINISHED":
                        system("clear")
                        exit(0)
                
                try:
                    ordinal_dict["backend"] = str(self.functions.get_snapshot({
                        "history": 1, 
                        "environment": self.config_obj[called_profile]["environment"],
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
                    self.log.logger.info(f"show system status requested | {profile}")      
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
                                ["Node Status Quick Results",1,"green","bold"],
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

                    self.log.logger.debug("show system status - ready to pull node sessions")
                    
                    sessions = self.functions.pull_node_sessions({
                        "edge_device": edge_point,
                        "spinner": spinner,
                        "profile": called_profile, 
                        "key": "clusterSession"
                    })

                    consensus_match = self.cli_check_consensus({
                        "profile": self.profile,
                        "caller": "status",
                    })
                    # consensus = self.functions.get_info_from_edge_point({
                    #     "profile": self.profile,
                    #     "caller": "status",
                    #     "api_endpoint_type": "consensus",
                    #     "specific_ip": self.ip_address,
                    # })
                    # consensus_match = colored("False","red")
                    # if consensus['specific_ip_found'][0] == consensus['specific_ip_found'][1]:
                    #     consensus_match = colored("True","green")
                    
                    def setup_output():
                        on_network = colored("False","red")
                        cluster_session = sessions["session0"]
                        node_session = sessions["session1"]
                        join_state = sessions['state1']
                                        
                        if sessions["session0"] == 0:
                            on_network = colored("LbNotReady","red")
                            cluster_session = colored("SessionNotFound".ljust(20," "),"red")
                            join_state = colored(f"{sessions['state1']}".ljust(20),"yellow")
                        else:
                            if sessions["state1"] == "ReadyToJoin":
                                join_state = colored(f"{sessions['state1']}".ljust(20),"yellow")
                                on_network = colored("ReadyToJoin","yellow")
                            if sessions["session0"] == sessions["session1"]:
                                if sessions["state1"] != "ApiNotReady" and sessions["state1"] != "Offline" and sessions["state1"] != "SessionStarted" and sessions["state1"] != "Initial":
                                    # there are other states other than Ready and Observing when on_network
                                    on_network = colored("True","green")
                                    join_state = colored(f"{sessions['state1']}".ljust(20),"green")
                                    if sessions["state1"] == "Observing" or sessions["state1"] == "WaitingForReady":
                                        join_state = colored(f"{sessions['state1']}".ljust(20),"yellow")
                                elif sessions["state1"] == "Ready":
                                    join_state = colored(f"{sessions['state1']}".ljust(20),"green",attrs=['bold'])
                                    on_network = colored("True","green",attrs=["bold"])
                                else:
                                    node_session = colored("SessionIgnored".ljust(20," "),"red")
                                    join_state = colored(f"{sessions['state1']}".ljust(20),"red")
                            if sessions["session0"] != sessions["session1"] and sessions["state1"] == "Ready":
                                    on_network = colored("False","red")
                                    join_state = colored(f"{sessions['state1']} (off-cluster)".ljust(20),"yellow")
                                            
                        if sessions["session1"] == 0:
                            node_session = colored("SessionNotFound".ljust(20," "),"red")
                        
                        return {
                            "on_network": on_network,
                            "cluster_session": cluster_session,
                            "node_session": node_session,
                            "join_state": join_state
                        }
                        
                    output = setup_output()
                    self.config_obj["global_elements"]["node_profile_states"][called_profile] = output["join_state"].strip()  # to speed up restarts and upgrades
                    
                    if not self.skip_build:
                        if rebuild:
                            if do_wait:
                                self.functions.print_timer(20)
                                
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
                        
                        if print_title:
                            self.functions.print_states()
                            self.functions.print_paragraphs([
                                ["Current Session:",0,"magenta"], ["  The Hypergraph cluster session",1],
                                ["  Found Session:",0,"magenta"], ["  The Cluster session Node is currently connected",1],
                                ["  Latest Ordinal:",0,"magenta"], [" Node consensus ordinal",1],
                                ["  Last DLed:",0,"magenta"], ["      Last found ordinal downloaded by Node",1],
                                ["  Blk Exp Ordinal:",0,"magenta"], ["Latest found block explorer ordinal",1],
                                ["  Consensus:",0,"magenta"], ["Is this Node participating in consensus rounds",1],
                                ["  Start:",0,"magenta"], ["When the cluster started (or restarted)",1],
                                ["  Uptime:",0,"magenta"], ["About of time Node or Cluster has been online",2],
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
                                "CONSENSUS": consensus_match,
                            }
                        ]
                        
                        if called_command == "uptime":
                            print_out_list = print_out_list2
                        else:
                            print_out_list = print_out_list + print_out_list2 + print_out_list3
                            if self.config_obj[profile]["layer"] > 0:
                                print_out_list.pop(2)
                            
                            self.functions.event = False  # if spinner was called stop it first.
                            
                        for header_elements in print_out_list:
                            self.functions.print_show_output({
                                "header_elements" : header_elements
                            })
                            
                if watch_enabled:
                    if quit_loop._state == "FINISHED":
                        exit(0) 
                    self.functions.print_paragraphs([
                        ["",1],["Press",0],["'q'",0,"yellow,on_red"], ['to quit',1],
                        ["Watch passes:",0,"magenta"], [f"{watch_passes}",0,"yellow"],
                        ["Intervals:",0,"magenta"], [f"{watch_seconds}s",1,"yellow"],
                    ])
                    self.functions.print_timer(watch_seconds,"before updating status")
                else: break    
                

    def show_service_log(self,command_list):
        self.functions.check_for_help(command_list, "show_service_log")
        profile = command_list[command_list.index("-p")+1]
        service = self.functions.pull_profile({
            "req":"service",
            "profile": profile,
        })
        bash_command = f"journalctl -b -u cnng-{service}"
        
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
        system(bash_command)
        cprint("  Service log review complete","blue")

            
    def show_prices(self,command_list):
        self.functions.check_for_help(command_list,"price")
            
        self.log.logger.info(f"show prices requested")
        crypto_prices = self.functions.get_crypto_price()
        
        print_out_list = [
            {
                "header_elements" : {
                    "$DAG": crypto_prices[0],
                    "$LTX": crypto_prices[1],
                    "$BTC": crypto_prices[2],
                    "$ETH": crypto_prices[3],
                    "$QNT": crypto_prices[4],
                },
                "spacing": 13
            },
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
        self.log.logger.info("show market requested")
                
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
        self.log.logger.info(f"show health requested")
        status = Status(self.functions)
        
        self.functions.print_header_title({
            "line1": "Node Basic Health",
            "single_line": True,
            "newline": "both"
        })
        
        print_out_list = [
            {
                "header_elements" : {
                    "DISK USAGE": status.hd_space.strip("\n"),
                    "15M CPU": status.usage,
                    "UPTIME_DAYS": status.system_up_time,
                    "MEMORY": status.memory,
                    "SWAP": status.swap,
                },
                "spacing": 15
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
                        section_dict[tup[0].upper()] = tup[1]
                    dyn_dict["header_elements"] = section_dict
                    dyn_dict["spacing"] = 15
                    print_out_list.append(dyn_dict)
                    section_dict = {}; dyn_dict = {}
                else:
                    break
            
        for header_elements in print_out_list:
            self.functions.print_show_output({
                "header_elements" : header_elements
        })
        

    def show_peers(self,command_list):
        self.functions.check_for_help(command_list,"peers")
        self.log.logger.info(f"show peers requested")
        profile = command_list[command_list.index("-p")+1]
        count_args = ["-p", profile]
        sip = {}
        nodeid = csv_file_name = ""
        is_basic = create_csv = False
        
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
        
        try:
            if sip["ip"] == "self": sip["ip"] = self.functions.get_ext_ip()
        except: sip["ip"] = self.functions.get_ext_ip()
    
        peer_results = self.node_service.functions.get_peer_count({
            "peer_obj": sip, 
            "profile": profile, 
            "compare": True
        })

        if peer_results == "error":
            self.log.logger.error(f"show peers | attempt to access peer count with ip [{sip}] failed")
            self.error_messages.error_code_messages({
                "error_code": "cmd-179",
                "line_code": "ip_not_found",
                "extra": sip,
                "extra2": None
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
        
        for item, peer in enumerate(peer_results["peer_list"]):
            public_port = peer_results["peers_publicport"][item]
            
            if not is_basic:
                nodeid = self.cli_grab_id({
                    "dag_addr_only": True,
                    "argv_list": ["-p",profile,"-t",peer,"--port",public_port,"-l"]
                })
                wallet = self.cli_nodeid2dag([nodeid, "return_only"])
                
            if do_more and item % more_break == 0 and item > 0:
                more = self.functions.print_any_key({
                    "quit_option": "q",
                    "newline": "both",
                })
                if more:
                    break
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
                nodeid = f"{nodeid[0:8]}....{nodeid[-8:]}"
                wallet = f"{wallet[0:8]}....{wallet[-8:]}"
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
            self.log.logger.info(f"csv file created: location: [{csv_file_name}]") 
            self.functions.print_paragraphs([
                ["CSV created successfully",1,"green","bold"],
                ["filename:",0,], [csv_file_name,1,"yellow","bold"],
                ["location:",0,], [self.config_obj[profile]['directory_uploads'],1,"yellow","bold"]
            ])  


    def show_ip(self,argv_list):
        self.log.logger.info(f"whoami request for password initiated.")
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
                    self.log.logger.error(f"request to find node id request failed | error [{e}]")
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
        self.log.logger.info(f"Show security request made.")
        status = Status(self.functions)
        
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
        # name,-p,profile,grep,follow
        self.log.logger.debug("show logs invoked")
        self.functions.check_for_help(command_list,"logs")

        l_flag = False
        profile = self.functions.default_profile
        possible_logs = [
            "app", "http", "nodectl", "gossip", "transactions"
        ]

        follow = "-f" if "-f" in command_list else "empty"
        grep = command_list[command_list.index("-g")+1] if "-g" in command_list else "empty"
        name = command_list[command_list.index("-l")+1] if "-l" in command_list else "empty"
        
        # update log file
        if grep != "empty" and follow != "-f":
            self.log.logger.info(f"show log with grep [{grep}] invoked | [{name}]")
        elif grep != "empty" and follow == "-f":
            self.log.logger.info(f"show log with grep [{grep}] invoked with follow | [{name}]")
        elif follow == "-f":
            self.log.logger.info(f"show log with follow invoked | [{name}]")
        else:
            self.log.logger.info("show log invoked")

        if name != "empty":
            if name not in possible_logs:
                self.functions.print_help({
                    "usage_only": True,
                    "hint": "Did you include the '-l' switch?"
                })
            file_path = f"/var/tessellation/{profile}/logs/{name}.log"
            if name == "nodectl":
                file_path = f"{self.functions.nodectl_path}nodectl.log"
        else:
            self.log.logger.info(f"show log invoked")
            
            self.functions.print_header_title({
                "line1": "SHOW LOGS",
                "clear": True,
            })
            
            self.functions.print_paragraphs([
                ["1",0,"magenta","bold"], [") nodectl logs",-1,"magenta"],["",1],
                ["2",0,"magenta","bold"], [") Tessellation app log",-1,"magenta"],["",1],
                ["3",0,"magenta","bold"], [") Tessellation http log",-1,"magenta"],["",1],
                ["4",0,"magenta","bold"], [") Tessellation gossip log",-1,"magenta"],["",1],
                ["5",0,"magenta","bold"], [") Tessellation transactions log",-1,"magenta"],["",2],
                ["Q",0,"magenta","bold"], [")uit",-1,"magenta"],["",2],
            ])
            
            option = self.functions.get_user_keypress({
                "prompt": "KEY PRESS an option",
                "prompt_color": "magenta",
                "options": ["1","2","3","4","5","Q"],
                "quit_option": "Q",
            })

            option_match = {
                "1": f"{self.functions.nodectl_path}nodectl.log",
                "2": f"/var/tessellation/{profile}/logs/app.log",
                "3": f"/var/tessellation/{profile}/logs/http.log",
                "4": f"/var/tessellation/{profile}/logs/gossip.log",
                "5": f"/var/tessellation/{profile}/logs/transactions.log",
            }    
            file_path = option_match.get(option)      

        try:
            f = open(f"{file_path}","r")
        except:
            self.log.logger.error(f"unable to open log file for reading [{file_path}]")
            self.functions.print_paragraphs([
                ["Error opening file:",0,"red"], [file_path,1,"yellow"],
            ])
            return 1
            
        self.functions.print_header_title({
            "line1": "SHOW LOGS",
            "line2": f"{profile} -> {name}",
            "clear": True,
        })

        for line in f.readlines():
            line = line.strip()
            if grep != "empty":
                if grep in str(line):
                    line = line.replace(grep,colored(grep,"red"))
                    print(line)
            else:
                print(line)
                
        if follow == "-f":
            has_line_changed = None
            print(colored("ctrl-c","cyan"),"to exit follow")
            while True:
                try:
                    with open(f'{file_path}', 'rb') as f:
                        try:  # catch OSError in case of a one line file 
                            f.seek(-2, SEEK_END)
                            while f.read(1) != b'\n':
                                f.seek(-2, SEEK_CUR)
                        except OSError:
                            f.seek(0)
                        except KeyboardInterrupt:
                            break
                        line = f.readline().decode()
                        if grep in str(line):
                            line = line.replace(grep,colored(grep,"red"))
                        if has_line_changed != line and grep == "empty" or (has_line_changed != line and grep in str(line)):
                            print(line.strip())
                            has_line_changed = line
                        sleep(.8)
                except KeyboardInterrupt:
                    break

        
    def show_list(self,command_list):
        self.log.logger.info(f"Request for list of known profiles requested")
        self.functions.check_for_help(command_list,"list")
        
        profile_only = True if "-p" in command_list else False
        
        self.functions.print_clear_line()
        self.functions.print_header_title({
            "line1": "CURRENT LOADED METAGRAPHS",
            "line2": "Based on local Node's config",
            "newline": "top",
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

            print_out_list = [
                {
                    "METAGRAPH NAME": metagraph_name,
                    "PROFILE NAME": profile,
                },
                {
                    "SERVICE NAME": profile_services[n],
                    "BLOCKCHAIN LAYER": profile_layers[n],
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
                        
            print("")
            cprint("  METAGRAPH CUSTOM VALUES","blue",attrs=["bold"])
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


    def show_node_states(self,command_list):
        self.log.logger.info(f"Request to view known Node states by nodectl")
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

        nodectl_only = ["ApiNotReady","SessionIgnored","SessionNotFound"]
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
                cluster_ips = self.functions.get_cluster_info_list({
                    "ip_address": self.config_obj[profile]["edge_point"],
                    "port": self.config_obj[profile]["edge_point_tcp_port"],
                    "api_endpoint": "/cluster/info",
                    "error_secs": 3,
                    "attempt_range": 3,
                })   
                count = cluster_ips.pop()   
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
        self.log.logger.info("show current snapshot proofs called")
        if "-p" in command_list:
            self.profile = command_list[command_list.index("-p")+1]
            self.log.logger.debug(f"show current snapshot proofs using profile [{self.profile}]")
        else: command_list.append("help")
        if not self.auto_restart: self.functions.check_for_help(command_list,"current_global_snapshot")
        
        more_break = 1
        print_title = False
        do_more = False if "-np" in command_list else True
        if do_more:
            console_size = get_terminal_size()
            more_break = round((console_size.lines-20)/6)
                    
        snap_obj = {
            "lookup_uri": f'http://127.0.0.1:{self.config_obj[self.profile]["public_port"]}/',
            "header": {'Accept': 'application/json' },
            "get_results": "proofs", 
            "return_type": "raw"      
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
        
        self.functions.print_paragraphs([
            ["Transactions Found:",0],[str(len(results)),1,"green","bold"],
        ])
        
        
    def show_download_status(self,command_obj):
        download_status = DownloadStatus({
            "parent": self,
            "command_obj": command_obj,
        })
        if command_obj["caller"] == "status":
            return download_status.download_status()
        download_status.download_status()
            
                       
    def show_current_rewards(self,command_list):
        self.functions.check_for_help(command_list,"show_current_rewards") 
        reward_amount = dict()
        color = "red"
        found = "FALSE"
        title = "NODE P12"
        profile = self.functions.default_profile
        snapshot_size = command_list[command_list.index("-s")+1] if "-s" in command_list else 50
        create_csv = False
        
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
            self.error_messages.error_code_messages({
                "error_code": "cmd-826",
                "line_code": "input_error",
                "extra": None,
            })            
        
        data = self.get_and_verify_snapshots(snapshot_size, self.config_obj[profile]["environment"])        
            
        if "-p" in command_list:
            profile = command_list[command_list.index("-p")+1]
            self.functions.check_valid_profile(profile)
            
        if "-w" in command_list:
            search_dag_addr = command_list[command_list.index("-w")+1]
            self.functions.is_valid_address("dag",False,search_dag_addr)
            title = "REQ WALLET"
        else:
            self.cli_grab_id({
                "dag_addr_only": True,
                "command": "dag",
                "argv_list": ["-p",profile]
            })
            search_dag_addr = self.nodeid.strip("\n")

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
                    self.error_messages.error_code_messages({
                        "error_code": "cmd-442",
                        "line_code": "invalid_output_file",
                        "extra": csv_file_name
                    })
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
        
        first = reward_amount.popitem()  
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
            self.log.logger.info(f"current rewards command is creating csv file [{csv_file_name}] and adding headers")
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
            self.log.logger.info(f"csv file created: location: [{csv_path}]") 
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
        self.log.logger.info(f"show_dip_error -> initiated - profile [{profile}]")
        
        bashCommand = f"grep -B 15 -A 5 'Unexpected failure during download' /var/tessellation/{profile}/logs/app.log | tail -n 21"
    
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
                    ["=","half","bold","blue"],
                    [str(line),1,color],
                ])
                
    # ==========================================
    # update commands
    # ==========================================

    def update_seedlist(self,command_list):
        self.functions.check_for_help(command_list,"update_seedlist")
        self.log.logger.info("updating seed list...")
        profiles = []
        
        try: # can be either env or profile (prefer -p over -e)
            profile = command_list[command_list.index("-p")+1]
        except:
            environment = command_list[command_list.index("-e")+1]
            profiles = self.functions.pull_profile({
                "req":"profiles_by_environment",
                "environment": environment
            })      
        else:
            profiles.append(profile)
              
        self.functions.print_clear_line()
        self.print_title("Update Seed list")
        
        for i_profile in reversed(list(profiles)):
            if "disable" in self.functions.config_obj[i_profile]["seed_path"]:
                self.functions.print_paragraphs([
                    ["Seed list is disabled for profile [",0,"red"],
                    [i_profile,-1,"yellow","bold"],
                    ["]",-1,"red"], ["nothing to do",1,"red"], 
                ])
            else:
                download_version = "default" if self.functions.config_obj[i_profile]["seed_repository"] == "default" else None
                self.node_service.download_update_seedlist({
                    "profile": i_profile,
                    "action": "normal",
                    "install_upgrade": False,
                    "download_version": download_version
                })


    # ==========================================
    # check commands
    # ==========================================
            
    def check_versions(self, command_list):
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
            self.error_messages.error_code_messages({
                "error_code": "cmd-1325",
                "line_code": "input_error",
                "extra": "skip_warning_messages is invalid for this command."
            })

        spacing = 25
        match_true= colored("True","green",attrs=["bold"])
        match_false = colored("False","red",attrs=["bold"])
                
        for profile in profile_names:
            try:
                environment = self.config_obj[profile]["environment"]
            except:
                self.error_messages.error_code_messages({
                    "error_code": "cmd-848",
                    "line_code": "profile_error",
                    "extra": profile
                })   
                
            nodectl_match = True       
            if not isinstance(self.version_obj[environment]["nodectl"]["nodectl_uptodate"],bool):
                if "current" in self.version_obj[environment]["nodectl"]["nodectl_uptodate"]:
                    nodectl_match = False   
            tess_match = True       
            if not isinstance(self.version_obj[environment][profile]["tess_uptodate"],bool):
                if "current" in self.version_obj[environment][profile]["tess_uptodate"]:
                    tess_match = False   
                     
            prerelease = "False"
            if self.version_obj[environment]["nodectl"]["nodectl_prerelease"]:
                prerelease = "True"
            if self.version_obj[environment]["nodectl"]["nodectl_prerelease"] == "Unknown":
                prerelease = "Unknown"
            
            print_out_list = [
                {
                    "header_elements" : {
                    "PROFILE": profile,
                    "METAGRAPH": self.config_obj["global_elements"]["metagraph_name"],
                    "JAR FILE": self.version_obj[environment][profile]["node_tess_jar"],
                    },
                    "spacing": spacing
                },
                {
                    "header_elements" : {
                    "TESS INSTALLED": self.version_obj[environment][profile]["node_tess_version"],
                    "NODECTL INSTALLED": self.version_obj["node_nodectl_version"],
                    },
                    "spacing": spacing
                },
                {
                    "header_elements" : {
                    "TESS LATEST": self.version_obj[environment][profile]["cluster_tess_version"],
                    "NODECTL LATEST": self.version_obj[environment]["nodectl"]["latest_nodectl_version"],
                    "NODECTL PRE_RELEASE": prerelease,
                    },
                    "spacing": spacing
                },
                {
                    "header_elements" : {
                        # 38
                        "TESS VERSION MATCH": f"{match_true: <38}" if tess_match else f"{match_false: <38}",
                        "NODECTL VERSION MATCH": f"{match_true}" if nodectl_match else match_false
                    },
                    "spacing": 25
                },
            ]
            
            for header_elements in print_out_list:
                self.functions.print_show_output({
                    "header_elements" : header_elements
                })  
            print("")
       
 
    def check_source_connection(self,command_list):
        self.functions.check_for_help(command_list,"check_source_connection")
        self.log.logger.info(f"Check source connection request made.")
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
            
        self.log.logger.info(f"Check connection request made. | {edge}")
              
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
        node_list = [source,edge]
        flip_flop = []

        self.functions.test_ready_observing(self.profile)
        
        for n, node in enumerate(node_list):
            # "peer_count": [], # peer_count, node_online, peer_set
            self.log.logger.debug(f"checking count and testing peer on {node}")
            node_obj = self.functions.get_info_from_edge_point({
                "profile": self.profile,
                "caller": "check_connection",
                "specific_ip": node
            })
            flip_flop.append(node_obj)
        
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
            self.log.logger.error(f"check_connection - source - edge - threw error [{e}]")
        else:
            node_obj_list[1]["missed_ip_count"] = len(node_obj_list[1]["missed_ips"])
  

        # source node missing                          edge                    -              source
        try:
            node_obj_list[0]["missed_ips"] = node_obj_list[1]["peer_set"] - node_obj_list[0]["peer_set"]
        except Exception as e:
            self.log.logger.error(f"check_connection - edge - source - threw error [{e}]")
        else:
            node_obj_list[0]["missed_ip_count"] = len(node_obj_list[0]["missed_ips"])
    
        # add state labels (*,i*,rj*,ss*,l*,s*,o*)
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
            self.log.logger.error(f"Check  connection request returned threshold or other error.")
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
        
        if not "skip_seedlist_title" in command_list: self.print_title("Check Seed List Request")

        is_target = command_list[command_list.index("-p")+1] if "-t" in command_list else False
        target = ["-t",target] if is_target else []
        nodeid = command_list[command_list.index("-id")+1] if "-id" in command_list else False

        if self.functions.config_obj[profile]["seed_location"] == "disable":
            if skip:
                return True
            self.functions.print_paragraphs([
                ["Seed list is disabled for profile [",0], [profile,-1,"yellow","bold"],
                ["] unable to do a proper nodeid lookup",0], ["exiting.",2,"red"]
            ])
            return 0

        if nodeid:
            self.functions.print_paragraphs([
                ["NODE ID",1,"blue","bold"],
                [nodeid,1,"white"],
            ])
        else:
            self.cli_grab_id({
                "command":"nodeid",
                "is_global": False,
                "profile": profile,
                "argv_list": target,
                "skip_display": skip
            })
            nodeid = self.nodeid
               
        if nodeid:
            nodeid = self.functions.cleaner(nodeid,"new_line")
            test = self.functions.test_or_replace_line_in_file({
              "file_path": self.functions.config_obj[profile]["seed_path"],
              "search_line": nodeid
            })

            if test == "file_not_found":
                self.error_messages.error_code_messages({
                    "error_code": "cmd-1229",
                    "line_code": "file_not_found",
                    "extra": "seed-list",
                    "extra2": None
                })
            elif test:
                found = colored("True","green",attrs=["bold"]) 

        if skip:
            if "True" in found:
                return True
            return False
        
        print_out_list = [{
            "NODE ID FOUND ON SEED LIST": found,
        }]
    
        for header_elements in print_out_list:
            self.functions.print_show_output({
                "header_elements" : header_elements
            }) 
            

    def check_nodectl_upgrade_path(self,command_obj):
        called_command = command_obj["called_command"]
        argv_list = command_obj["argv_list"]
        
        try: env = argv_list[argv_list.index('-e')+1]
        except: argv_list.append("help")
            
        self.functions.check_for_help(argv_list,"upgrade_path")
        called_command = "upgrade_path" if called_command == "_up" else called_command
        
        self.log.logger.debug("testing for upgrade path requirements")
        versions = SimpleNamespace(**self.version_obj)
        
        nodectl_uptodate = getattr(versions,env)
        nodectl_uptodate = nodectl_uptodate["nodectl"]["nodectl_uptodate"]
        
        upgrade_path = versions.upgrade_path
        if versions.node_nodectl_version in upgrade_path:
            upgrade_path_this_version = upgrade_path[upgrade_path.index(versions.node_nodectl_version)-1:]      
            next_upgrade_path = upgrade_path_this_version[0] 
        else: next_upgrade_path = upgrade_path[0]   
        
        for test_version in reversed(upgrade_path):
            test = self.functions.is_new_version(versions.node_nodectl_version,test_version)
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
            self.functions.print_paragraphs([
                ["=","full",2,"green","bold"],
            ])
            for n, version in enumerate(reversed(upgrade_path)):
                if n < 1:
                    print(" ",end=" ")
                print(f"{colored(version,'yellow')}",end=" ")
                if version != upgrade_path[0]:
                    print(colored("-->","cyan"),end=" ")
            self.functions.print_paragraphs([
                ["",1],["=","full",1,"green","bold"],
            ])                                
                                
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
            elif called_command == "upgrade_path":
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
                exit("  auto restart enabled error")

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
        nodectl_version_check = False
        caller = command_obj.get("caller",None)
        
        if self.skip_warning_messages: return
        
        self.functions.get_service_status()
        if caller == "upgrade_nodectl":
            return
        
        profile_names = self.profile_names
        if profile != "default":
            profile_names = [profile]
            
        environments = self.functions.pull_profile({"req": "environments"})

        # pull_profiles now has environments added as option
        # switch this check to by environment not profile!
        for env in environments["environment_names"]:
            nodectl_version_check = self.version_obj[env]["nodectl"]["nodectl_uptodate"]
            if nodectl_version_check == "current_greater" and not self.check_versions_called:
                if nodectl_version_check == "current_greater":
                    self.functions.print_paragraphs([
                        [" WARNING ",0,"red,on_yellow"],
                        ["You are running a version of nodectl that is claiming to be newer than what was found on the",0],
                        ["official Constellation Network StardustCollective repository, please proceed",0],
                        ["carefully, as this version may either be:",2],
                        ["- experimental (pre-release)",1,"magenta"],
                        ["- malware",1,"magenta"],
                        ["- not an official supported version",2,"magenta"],
                        ["   environment checked:",0],[env,1,"yellow","bold"],
                        ["current stable version:",0],[self.version_obj['upgrade_path'][0],1,"yellow","bold"],
                        [" version found running:",0],[self.version_obj['node_nodectl_version'],2,"yellow","bold"],
                        ["Suggestion:",0],["sudo nodectl verify_nodectl",2,"yellow"],
                    ])
                    self.invalid_version = True
                    return
            if nodectl_version_check == "current_less" and not self.check_versions_called:
                self.functions.print_cmd_status({
                    "text_start": "A new version of",
                    "brackets": "nodectl",
                    "text_end": "was detected",
                    "status": self.version_obj[env]['nodectl']['latest_nodectl_version'],
                    "status_color": "yellow",
                    "newline": True,
                })
                self.functions.print_paragraphs([
                    ["To upgrade issue:",0], [f"sudo nodectl upgrade_nodectl",2,"green"]
                ])

        for i_profile in profile_names:
            tess_version_check = self.version_obj[env][profile_names[0]]["tess_uptodate"]
            if tess_version_check == "current_less" and not self.check_versions_called:
                    self.functions.print_clear_line()
                    self.functions.print_paragraphs([
                        [f" {i_profile} ",0,"green,on_blue"],["A",0], ["new",0,"green"], ["version of",0], ["Tessellation",0,"cyan"], ["was detected:",0],
                        [self.version_obj[env][i_profile]['cluster_tess_version'],1,"yellow","bold"],
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
        skip_seedlist_title = command_obj.get("skip_seedlist_title",False)
        existing_node_id = command_obj.get("node_id",False)
        self.functions.check_for_help(argv_list,"start")

        self.log.logger.info(f"Start service request initiated.")
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
        
        self.functions.print_timer(6,"wait for start",1)
        
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
                "spinner": False,
                "rebuild": True,
                "wait": False,
                "print_title": False,
                "threaded": threaded,
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
        check_for_leave = command_obj.get("check_for_leave",False)
        rebuild = True
    
        sleep(command_obj.get("delay",0))
        
        self.functions.check_for_help(argv_list,"stop")
        self.set_profile(profile)

        self.functions.print_cmd_status({
            "status": "stop",
            "text_start": "Issuing system service manipulation",
            "brackets": profile,
            "newline": False,
        })

        if check_for_leave:
            state = self.functions.test_peer_state({
                "profile": profile,
                "skip_thread": True,
                "spinner": spinner,
                "simple": True
            })     
            if state == "Ready" or state == "DownloadInProgress":
                self.functions.print_paragraphs([
                    [" WARNING ",0,"white,on_red"], ["This profile [",0],
                    [profile,-1,"yellow","bold"], ["] is in [",-1], [state,-1,"yellow","bold"],
                    ["] state.",-1], ["",2]
                ]) 
                if self.functions.confirm_action({
                    "yes_no_default": "y",
                    "return_on": "y",
                    "prompt": "Do you want to leave first?",
                    "exit_if": False,
                }):
                    self.cli_leave({
                        "secs": 30,
                        "reboot_flag": False,
                        "skip_msg": False,
                        "argv_list": ["-p",profile],
                    })
                
        progress = {
            "status": "running",
            "text_start": "Stop request initiated",
            "brackets": self.functions.cleaner(self.service_name,'service_prefix'),
            "newline": True,
        }
        self.functions.print_cmd_status(progress)
        self.log.logger.info(f"Stop service request initiated. [{self.service_name}]")
        
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

            result = self.node_service.change_service_state({
                "profile": profile,
                "action": "stop",
                "service_name": self.service_name,
                "caller": "cli_stop"
            })
            self.functions.event = False

        if result == "skip_timer":
            show_timer = False
        if spinner:
            show_timer = False
        if self.functions.config_obj["global_elements"]["node_service_status"][profile] == "inactive (dead)":
            rebuild = False
        
        self.functions.print_cmd_status({
            **progress,
            "status": "complete",
            "newline": True
        }) 

        self.show_system_status({
            "rebuild": rebuild,
            "wait": show_timer,
            "spinner": spinner,
            "print_title": False,
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
        if "-r" in argv_list:
            try: failure_retries = int(argv_list[argv_list.index("-r")+1])
            except:
                self.error_messages.error_code_messages({
                    "error_code": "cmd-2138",
                    "line_code": "input_error",
                    "extra": f'-r {argv_list[argv_list.index("-r")+1]}'
                })
                
        self.functions.print_clear_line()
        performance_start = perf_counter()  # keep track of how long
        self.functions.print_cmd_status({
            "text_start": "Restart request initiated",
            "status": "running",
            "status_color": "yellow",
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
            "req": "order_pairings",
        })
        profile_order = profile_pairing_list.pop()
        
        if called_profile == "all":
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
            self.print_title("Leaving Metagraphs") 
            leave_list[-1]["skip_msg"] = False                    
            futures = [executor.submit(self.cli_leave, obj) for obj in leave_list]
            thread_wait(futures)

            self.functions.print_cmd_status({
                "text_start": "Leave network operations",
                "status": "complete",
                "status_color": "green",
                "newline": True,
            })
        
            # stop
            self.print_title(f"Stopping profile {'services' if called_profile == 'all' else 'service'}")    
            stop_list[-1]["spinner"] = True
            futures = [executor.submit(self.cli_stop, obj) for obj in stop_list]
            thread_wait(futures)  
            
            self.functions.print_cmd_status({
                "text_start": "Stop network services",
                "status": "complete",
                "status_color": "green",
                "newline": True,
            })        

        self.print_title("Updating seed list")
        
        for n, profile in enumerate(profile_order):
            self.node_service.set_profile(profile)
            self.node_service.download_update_seedlist({
                "action": "normal",
                "install_upgrade": False,
            })
            sleep(.5)    
            
        # ====================
        # CONTROLLED START & JOIN OPERATIONS
        # ====================

        if not cli_leave_cmd:
            for profile in profile_order:
                self.set_profile(profile)
                    
                if restart_type == "restart_only":
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
                                self.functions.print_paragraphs([
                                    ["",1], 
                                    [" WARNING ",2,"white,on_red"], 
                                    
                                    ["nodectl",0,"cyan","bold"], ["has detected a [",0], ["restart_only",-1,"yellow","bold"], 
                                    ["] request.  However, the configuration is showing that this node is (",-1],
                                    ["properly",0,"green","underline"], [") linking to a layer0 profile [",0],
                                    [link_profile,-1,"yellow","bold"], ["].",-1], ["",2],
                                    
                                    ["Due to this",0], ["recommended",0,"cyan","underline"], ["configurational setup, the layer1 [",0],
                                    [profile,-1,"yellow","bold"], ["]'s associated service will",-1], ["not",0,"red","bold"], 
                                    ["be able to start until after",0],
                                    [f"the {link_profile} profile is joined successfully to the network. A restart_only will not join the network.",2],
                                    
                                    ["      link profile: ",0,"yellow"], [link_profile,1,"magenta"],
                                    ["link profile state: ",0,"yellow"], [state,2,"red","bold"],
                                    
                                    ["This",0], ["restart_only",0,"magenta"], ["request will be",0], ["skipped",0,"red","underline"],
                                    [f"for {profile}.",-1]
                                ])
                            
                service_name = self.config_obj[profile]["service"] 
                start_failed_list = []
                if not service_name.startswith("cnng-"): service_name = f"cnng-{service_name}"
                    
                for n in range(1,failure_retries+1):
                    self.print_title(f"Restarting profile {'services' if called_profile == 'all' else 'service'}")
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

                    ready_states = list(zip(*self.functions.get_node_states("ready_states")))[0]
                    if peer_test_results in ready_states:  # ReadyToJoin and Ready
                        break
                    else:
                        if n == failure_retries:
                            self.functions.print_paragraphs([
                                [profile,0,"red","bold"], ["service failed to start...",1]
                            ])
                            ts = Troubleshooter({"config_obj": self.config_obj})
                            ts.setup_logs({
                                "profile": profile,
                            })
                            results = ts.test_for_connect_error() 
                            if results:
                                self.functions.print_paragraphs([
                                    ["",1], ["The following was identified in the logs",1],
                                    ["       Profile:",0],[results[0],1,"yellow"],
                                    ["Possible Cause:",0],[results[1],1,"yellow"],
                                    ["        Result:",0],[results[2],2,"yellow"],
                                ])
                            self.functions.print_auto_restart_warning()
                            start_failed_list.append(profile)
                            
                        self.functions.print_paragraphs([
                            [" Issue Found: ",0,"yellow,on_red","bold"],
                            [f"{profile}'s service was unable to start properly. Attempting stop/start again",0], 
                            [str(n),0,"yellow","bold"],
                            ["of",0], [str(failure_retries),1,"yellow","bold"]
                        ])
                        sleep(1)
                        self.cli_stop = {
                            "show_timer": False,
                            "profile": profile,
                            "argv_list": []
                        }
                
                static_peer = False
                if "all" in argv_list and "--peer" in argv_list:
                    self.functions.print_paragraphs([
                        [" WARNING ",0,"red,on_yellow"], ["an attempt to join with a static",0,"red"],
                        ["--peer",0,"yellow"], ["option was identified with the special option variable",0,"red"],
                        ["all",0,"yellow"], ["and will be ignored",1,"red"],
                    ])
                elif "--peer" in argv_list:
                    # validation takes place on join
                    static_peer = argv_list[argv_list.index("--peer")+1]
                    self.functions.is_valid_address("ip_address",False,static_peer)
                    
                if cli_join_cmd or restart_type != "restart_only":
                    environment = self.config_obj[profile]["environment"]
                    self.print_title(f"Joining [{environment}] [{profile}]")   

                    if profile not in start_failed_list:
                        self.cli_join({
                            "skip_msg": False,
                            "caller": "cli_restart",
                            "skip_title": True,
                            "wait": False,
                            "watch": watch,
                            "dip": dip,
                            "interactive": interactive,
                            "static_peer": static_peer,
                            "non_interactive": non_interactive,
                            "single_profile": single_profile,
                            "argv_list": ["-p",profile]
                        })
                    else:
                        self.functions.print_paragraphs([
                            [profile,0,"red","bold"], ["did not start properly; therefore,",0,"red"],
                            ["the join process cannot begin",0,"red"], ["skipping",1, "yellow"],
                        ])
                        
        print("")        
        self.functions.print_perftime(performance_start,"restart")
                

    def cli_reboot(self,command_list):
        self.log.logger.info("user initiated system warm reboot.")
        self.functions.check_for_help(command_list,"reboot")
        
        on_boot = self.config_obj["global_auto_restart"]["on_boot"]
        
        self.functions.print_header_title({
            "line1": "REBOOT REQUEST",
            "line2": "nodectl",
            "newline": "top"
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
                ["Once your VPS completes it startup, the Node should automatically rejoin the Metagraphs configured.",2],
            ])
        else:
            self.functions.print_paragraphs([
                ["Once your VPS or bare metal host returns from the soft boot, you will need to manually join the Metagraphs configured",0],
                ["by issuing the necessary commands.",2],
                ["command:",0,"white","bold"], ["sudo nodectl restart -p all",2,"yellow"]
            ])
        
        if self.functions.confirm_action({
            "yes_no_default": "n",
            "return_on": "y",
            "prompt": "Are you SURE you want to leave and reboot?",
            "exit_if": True
        }):
            for profile in reversed(self.profile_names):
                self.set_profile(profile)
                self.cli_leave({
                    "secs": 45,
                    "reboot_flag": True,
                    "skip_msg": True
                })
            self.functions.print_paragraphs([
                ["Leave complete",1,"green","bold"],
                ["Preparing to reboot.  You will lose access after this message appears.  Please reconnect to your Node after a few moments of patience, to allow your server to reboot, initialize, and restart the SSH daemon.",2]
            ])
            sleep(2)
            system(f"sudo reboot > /dev/null 2>&1")  
                    
        confirm = input(f"\n  Are you SURE you want to leave and reboot? [n] : ")
        if confirm.lower() == "y" or confirm.lower() == "yes":
            for profile in reversed(self.profile_names):
                self.set_profile(profile)
                self.cli_leave({
                    "secs": 0,
                    "reboot_flag": True,
                    "skip_msg": True
                })
            cprint("  Leave complete","green")
            cprint("  Preparing to reboot...","magenta")
            sleep(2)
            system(f"sudo reboot > /dev/null 2>&1")
            
      
    def cli_join(self,command_obj):
        argv_list = command_obj.get("argv_list")
        self.functions.check_for_help(argv_list,"join")

        start_timer = perf_counter()
                
        skip_msg = command_obj.get("skip_msg",False)
        skip_title = command_obj.get("skip_title",False)
        watch_peer_counts = command_obj.get("watch",False)
        static_peer = command_obj.get("static_peer",False)
        single_profile = command_obj.get("single_profile",True)
        upgrade = command_obj.get("upgrade",False)
        interactive = command_obj.get("interactive",False)
        non_interactive = command_obj.get("non_interactive",False)
        dip_status = command_obj.get("dip",False)
        caller = command_obj.get("caller",False)
        
        called_profile = argv_list[argv_list.index("-p")+1]
        self.set_profile(called_profile)
        
        if "--peer" in argv_list:
            static_peer = argv_list[argv_list.index("--peer")+1]
        if static_peer:
            self.functions.is_valid_address("ip_address",False,static_peer)
            
        result, snapshot_issues, tolerance_result = False, False, False
        first_attempt = True
        wfd_count, wfd_max = 0, 3  # WaitingForDownload
        dip_count, dip_max = 0, 8 # DownloadInProgress
        ss_count, ss_max = 0, 5 # SessionStarted
        
        attempt = ""
        
        defined_connection_threshold = .8
        max_timer = 300
        peer_count, old_peer_count, src_peer_count, increase_check = 0, 0, 0, 0
        
        gl0_link = self.functions.config_obj[called_profile]["gl0_link_enable"]
        ml0_link = self.functions.config_obj[called_profile]["ml0_link_enable"]

        states = list(zip(*self.functions.get_node_states("on_network")))[0]
        break_states = list(zip(*self.functions.get_node_states("past_observing")))[0]
                
        def print_update():
            nonlocal first_attempt
            if first_attempt:
                first_attempt = False
                self.functions.print_paragraphs([
                    [" Max Timer ",0,"yellow,on_blue"],["300",0,"yellow"], ["seconds",1]
                ])
                
            self.functions.print_clear_line()
            print(colored("  Peers:","cyan"),colored(f"{src_peer_count}","yellow"),
                colored("Connected:","cyan"),colored(f"{peer_count}","yellow"), 
                colored("State:","cyan"),colored(f"{state}","yellow"), 
                colored("Timer:","cyan"),colored(f"{allocated_time}","yellow"),
                end='\r')
            
                    
        if not skip_title:
            self.print_title(f"Joining {called_profile}")  
        
        if not skip_msg:
            self.functions.print_cmd_status({
                "text_start": "Joining",
                "brackets": self.profile,
                "status": "please wait",
                "status_color": "magenta",
                "newLine": True
            })

        if gl0_link and ml0_link and not single_profile:
            found_dependency = False
            if not watch_peer_counts: # check to see if we can skip waiting for Ready
                for link_profile in self.profile_names:
                    if self.functions.config_obj[link_profile]["gl0_link_profile"] == called_profile:
                        found_dependency = True
                        break
                    elif self.functions.config_obj[link_profile]["ml0_link_profile"] == called_profile:
                        found_dependency = True
                        break
            if not found_dependency:
                single_profile = True

            
        state = self.functions.test_peer_state({
            "profile": self.profile,
            "simple": True
        })
        
        self.functions.print_cmd_status({
            "text_start": "Reviewing",
            "brackets": self.profile,
            "status": state,
            "color": "magenta",
            "newline": True,
        })

        if state == "Ready":
            self.functions.print_paragraphs([
                ["Profile already in",0,"green"],
                [" Ready ",0,"grey,on_green","bold"],
                ["state, nothing to do",1,"green"]
            ])
            return
        
        if state == "ApiNotReady":
            self.functions.print_paragraphs([
                ["Profile state in",0,"red"], [state,0,"red","bold,underline"],
                ["state, cannot join",1,"red"], ["Attempting to start service [",0],
                [self.service_name.replace('cnng-',''),-1,"yellow","bold"], ["] again.",-1], ["",1]
            ])
            
            self.cli_start({
                "spinner": True,
                "profile": self.profile,
                "service_name": self.service_name,
            })
        
        join_result = self.node_service.join_cluster({
            "caller": "cli_join",
            "action":"cli",
            "static_peer": static_peer,
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
                            error_msg = self.troubleshooter.test_for_connect_error()
                            if error_msg:
                                self.functions.print_paragraphs([
                                    ["",1], ["Possible Error",1,"red","bold"],
                                    [f"{error_msg[1]}",1],
                                ])
                            self.functions.print_auto_restart_warning()
                            exit("  possible error during join")
                        increase_check += 1
                    if state == "WaitingForDownload":
                        if wfd_count > wfd_max:
                            snapshot_issues = "wfd_break"
                            result = False
                            tolerance_result = False # force last error to print
                            break
                        wfd_count += 1
                    if state == "SessionStarted":
                        if ss_count > ss_max:
                            result = False
                            tolerance_result = False # force last error to print
                            break
                        ss_max += 1
                    if state == "DownloadInProgress":
                        if dip_status:
                            self.functions.print_paragraphs([
                                ["",2],[" IMPORTANT ",0,"red,on_yellow"], ["the",0], ["--dip",0,"yellow"],
                                ["option was identified.  This will cause nodectl to execute the",0],
                                ["download_status",0,"yellow"], ["command.",2],
                                ["In order to cancel this potentially long process, you will need to issue a",0],
                                ["ctrl-c",0,"blue","bold"],
                                ["which will exit the entire upgrade or restart processes.",0], 
                                ["This will not harm the process, just exit the visual aspects of it",0,"green"],
                                ["Another option is to skip this option and issue:",0], ["sudo nodectl download_status",0,"yellow"],
                                ["when the upgrade or restart process completes.",2],
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
                    if peer_count >= src_peer_count: 
                        result = True
                    else:
                        if connect_threshold >= defined_connection_threshold and increase_check > 1:
                            if state in break_states:
                                tolerance_result = True
                        else:
                            old_peer_count = peer_count
                except Exception as e:
                    self.log.logger.error(f"cli-join - {e}")
                

                if allocated_time % 1 == 0:  
                    print_update()
                        
                if result or tolerance_result or allocated_time > max_timer or increase_check > 8: # 8*5=40
                    if increase_check > 3:
                        self.functions.print_cmd_status({
                            "text_start": "No new nodes discovered for ~40 seconds",
                            "status": "error",
                            "status_color": "red",
                            "newLine": True
                        })
                    break
            
            # ========================
                
            if snapshot_issues:
                if snapshot_issues == "wfd_break":
                    self.functions.print_paragraphs([
                        ["",2],["nodectl has detected",0],["WaitingForDownload",0,"red","bold"],["state.",2],
                        ["This is an indication that your Node may be stuck in an improper state.",0],
                        ["Please contact technical support in the Discord Channels for more help.",1],
                    ])                    
                if snapshot_issues == "dip_break":
                    self.functions.print_paragraphs([
                        ["",2],["nodectl has detected",0],["DownloadInProgress",0,"yellow","bold"],["state.",2],
                        ["This is",0], ["not",0,"green","bold"], ["an issue; however, Nodes may take",0],
                        ["longer than expected time to complete this process.  nodectl will terminate the",0],
                        ["watching for peers process during this join in order to avoid undesirable wait times.",1],
                    ])       
            elif not result and tolerance_result:
                self.functions.print_clear_line()
                self.functions.print_paragraphs([
                    ["",1],["nodectl tolerance connection status of [",0,],
                    [f"{defined_connection_threshold*100}%",-1,"yellow","bold"], ["] met or exceeded successfully,",-1],
                    ["continuing join request.",1]
                ])
            elif not result and not tolerance_result:
                self.functions.print_clear_line()
                self.functions.print_paragraphs([
                    ["",1], [" WARNING ",0,"yellow,on_red","bold"], ["Issue may be present?",0,"red"],
                    ["Please issue the following command to review the Node's details.",1,"red"], 
                    ["sudo nodectl check-connection -p <profile_name>",1],
                    ["Follow instructions if error persists",2,"red"],
                    
                    [" NOTE ",0,"grey,on_green"], ["Missing a few Nodes on the Hypergraph independent of the network, is",0,"green"],
                    ["not an issue.  There will be other Nodes leaving and joining the network; possibly, at all times.",1,"green"],
                ])
                
        print("")
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
        self.log.logger.debug(f"join process completed in: [{stop_timer - start_timer}s]")
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
            for _ in range(0,4):
                state = self.node_service.leave_cluster({
                    "skip_thread": True,
                    "threaded": threaded,
                    "profile": profile,
                    "secs": secs,
                    "cli_flag": True    
                })
                if state == "Ready": continue
                return state

        call_leave_cluster()

        if not skip_msg:
            start = 1
            while True:
                self.log.logger.info(f"leave in progress | profile [{profile}] port [{api_port}] | ip [127.0.0.1]")
                if start > secs*3:
                    self.log.logger.warn(f"Node did not seem to leave the cluster properly, executing leave command again. | profile [{profile}]")
                    call_leave_cluster()

                progress = {
                    "status": "testing",
                    "text_start": "Retrieving Node Service State",
                    "brackets": profile,
                    "newline": False,
                }
                self.functions.print_cmd_status(progress)
                    
                state = self.functions.test_peer_state({
                    "profile": profile,
                    "skip_thread": True,
                    "simple": True,
                    "treaded": threaded,
                })
                
                self.functions.print_cmd_status({
                    **progress,
                    "status": state,
                })
                
                if state in self.functions.not_on_network_list:
                    self.functions.print_cmd_status({
                        "status": "out of cluster",
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
                    self.functions.print_cmd_status({
                        "text_start": f"{profile} not out of cluster",
                        "text_color": "red",
                        "status": state,
                        "status_color": "yellow",
                        "newline": True
                    })  
                if start > secs*4:
                    self.log.logger.warn(f"command line leave request reached [{start}] secs without properly leaving the cluster, aborting attempts | profile [{profile}]")
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
                    skip_log_lookup = False
                    self.prepare_and_send_logs(["-p",profile,"scrap"])
                    for _ in range(0,3): # 3 tries
                        leave_obj = self.send.scrap_log({
                            "profile": profile,
                            "msg": "Wait for Node to go offline",
                            "value": "Node state changed to=Leaving",
                            "key": "message",
                            "thread": False,
                            "timeout": 60,
                        })
                        try: timestamp = leave_obj["@timestamp"]
                        except:
                            leave_str = "to allow Node to gracefully leave"
                            skip_log_lookup = True
                            sleep(.5)
                        else: 
                            skip_log_lookup = False
                            break
                    if skip_log_lookup:
                        self.functions.print_timer(secs,leave_str,start)
                    else:
                        leave_obj = False
                        sleep(2) # wait 2 seconds
                        for _ in range(0,3): # 3 minutes
                            leave_obj = self.send.scrap_log({
                                "profile": profile,
                                "msg": "Wait for Node to go offline",
                                "value": "Node state changed to=Offline",
                                "key": "message",
                                "timeout": 60,
                                "timestamp": timestamp,
                            })   
                            if leave_obj: 
                                skip_log_lookup = False 
                                break   
                            sleep(.1) 
                            skip_log_lookup = True      
                            backup_line = True           
                else:
                    sleep(secs) # silent sleep 
                    
                self.functions.print_clear_line()
                start = start - 1 if secs > 1 else start
                start = start+secs      
                    
        
    def cli_grab_id(self,command_obj):
        # method is secondary method to obtain node id
        argv_list = command_obj.get("argv_list",[None])
        command = command_obj.get("command")
        return_success = command_obj.get("return_success",False)
        skip_display = command_obj.get("skip_display",False)
        outside_node_request = command_obj.get("outside_node_request",False)
        dag_address_only = command_obj.get("dag_addr_only",False)
        
        profile = self.profile # default
        nodeid = ""
        ip_address = "127.0.0.1" # default
        is_global = True
        api_port = nodeid_to_ip = target = is_self = cmd = print_out_list = False
        wallet_only = True if "-w" in argv_list else False
        title = "NODE ID" if command == "nodeid" else "DAG ADDRESS"
        create_csv = False
        
        self.functions.check_for_help(argv_list,command)
                
        if "-p" in argv_list:  # profile
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
                                         
        self.log.logger.info(f"Request to display nodeid | type {command}")

        if not outside_node_request and not target:
            self.functions.config_obj["global_elements"]["caller"] = "command_line"
            action_obj = {
                "action": command,
                "functions": self.functions,
            }
            p12 = P12Class(action_obj,False)
            p12.extract_export_config_env({
                "is_global": is_global,
                "profile": profile,
            }) 
        
        if ip_address != "127.0.0.1":
            if target:
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
                _ = executor.submit(self.functions.print_spinner,{
                    "msg": f"Pulling Node ID, please wait",
                    "color": "magenta",
                })                     
                if outside_node_request:
                    for n in range(0,4):
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
                            if n > 2:
                                self.error_messages.error_code_messages({
                                    "error_code": "cmd-2484",
                                    "line_code": "node_id_issue",
                                    "extra": "external" if outside_node_request else None,
                                })
                            sleep(1)
                        else:
                            break
                            
                    for desired_ip in cluster_ips:
                        if desired_ip["id"] == nodeid:     
                            ip_address = desired_ip["ip"]
                            nodeid_to_ip = True
                            break
                        
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
                        self.log.logger.warn(f"attempt to access api returned no response | command [{command}] ip [{ip_address}]")
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

        if dag_address_only:
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
                    
            wallet_balance = self.functions.pull_node_balance({
                "ip_address": ip_address,
                "wallet": nodeid.strip(),
                "environment": self.config_obj[profile]["environment"]
            })
            wallet_balance = SimpleNamespace(**wallet_balance)


        # clear anything off the top of screen
        if not create_csv:
            self.functions.print_clear_line()

        if not is_self and not wallet_only:
            print_out_list = [
                {
                    "header_elements" : {
                        "IP ADDRESS REQUESTED": ip_address,
                    },
                },
            ]
        if not skip_display:
            if not outside_node_request and not create_csv:            
                self.show_ip([None])
                print_out_list = [
                    {
                        "header_elements" : {
                            "P12 FILENAME": p12.p12_file,
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
                    self.log.logger.error(f"Unable to access nodeid from p12 file.")
                    nodeid = "unable to derive"
            else:
                nodeid = nodeid.strip()
                if nodeid == "":
                    self.log.logger.error(f"Unable to access nodeid from p12 file.")
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
                                wallet_balance.dag_price
                            ]
                        ]
                })
            else:
                for header_elements in print_out_list:
                    self.functions.print_show_output({
                        "header_elements" : header_elements
                    })
                        
            if command == "dag":
                if not create_csv:
                    print_out_list = [
                        {
                            "$DAG BALANCE": f"{wallet_balance.balance_dag: <20}",
                            "$USD VALUE": f"{wallet_balance.balance_usd}",
                            "$DAG PRICE": f"{wallet_balance.dag_price}",
                            "IN CONSENSUS": consensus,
                        }
                    ]
                
                    for header_elements in print_out_list:
                        self.functions.print_show_output({
                            "header_elements" : header_elements
                        })  
                                    
                if not "-b" in argv_list:
                    total_rewards = 0
                    data = self.get_and_verify_snapshots(375,self.config_obj[profile]["environment"])
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
            if nodeid == "unable to derive":
                return False 
            return True
            

    def cli_find(self,argv_list): # ip="empty",dest=None
        self.log.logger.debug("find request initiated...")

        if "help" in argv_list:
            self.functions.print_help({
                "usage_only": True,
                "extended": "find"
            })
                    
        self.profile = argv_list[argv_list.index("-p")+1]
        source_obj = "empty"
        if "-s"  in argv_list:
            source_obj = {"ip": "127.0.0.1"} if argv_list[argv_list.index("-s")+1] == "self" else {"ip": argv_list[argv_list.index("-s")+1]}

        target_obj = {"ip":"127.0.0.1"}
        if "-t" in argv_list:
            target_obj = argv_list[argv_list.index("-t")+1]
            if not isinstance(target_obj,dict):
                target_obj =  {"ip": "127.0.0.1"} if argv_list[argv_list.index("-t")+1] == "self" else {"ip": argv_list[argv_list.index("-t")+1]}
        target_ip = target_obj["ip"]
            
        if source_obj == "empty":
            source_obj = self.functions.get_info_from_edge_point({
                "caller": "cli_find",
                "profile": self.profile,
            })

        peer_results = self.node_service.functions.get_peer_count({
            "peer_obj": target_obj,
            "edge_obj": source_obj,
            "profile": self.profile,
        })

        if peer_results == "error" or peer_results == None:
            self.log.logger.error(f"show count | attempt to access peer count function failed")
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

        if len(target_ip) > 127:
            target_ip = f"{target_ip[:8]}...{target_ip[-8:]}"

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
        
        for header_elements in print_out_list:
            self.functions.print_show_output({
                "header_elements" : header_elements
            })  
            
        
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


    def cli_digital_signature(self,command_list):
        self.log.logger.info("Attempting to verify nodectl binary against code signed signature.")
        self.functions.check_for_help(command_list,"verify_nodectl")
        self.functions.print_header_title({
            "line1": "VERIFY NODECTL",
            "line2": "warning verify keys",
            "newline": "top",
        })   
        
        nodectl_version_github = self.functions.node_nodectl_version_github
        nodectl_version_full = self.functions.node_nodectl_version
        outputs, urls = [], []
        cmds = [  # must be in this order
            [ "nodectl_public","fetching public key","PUBLIC KEY","-----BEGINPUBLICKEY----"],
            [ f'{nodectl_version_github}_{self.arch}.sha256',"fetching digital signature hash","BINARY HASH","SHA256"],
            [ f"{nodectl_version_github}_{self.arch}.sig","fetching digital signature","none","none"],
        ]
                
        def send_error(extra):
            self.error_messages.error_code_messages({
                "error_code": "cmd-3432",
                "line_code": "verification_failure",
                "extra": extra,
            })     
    
        progress = {
            "status": "running",
            "status_color": "red",
            "delay": 0.3
        }
        for n, cmd in enumerate(cmds): 
            self.functions.print_cmd_status({
                **progress,
                "text_start": cmd[1],
            })
            
            url = f"https://raw.githubusercontent.com/StardustCollective/nodectl/{nodectl_version_github}/admin/{cmd[0]}"
            urls.append(url)
            if cmd[2] == "none":
                url = f"https://github.com/StardustCollective/nodectl/releases/download/{nodectl_version_full}/{cmd[0]}"
                verify_cmd = f"openssl dgst -sha256 -verify {self.functions.nodectl_path}nodectl_public -signature {self.functions.nodectl_path}{cmd[0]} {self.functions.nodectl_path}{cmds[1][0]}"

            wget_cmd = 'sudo wget -H "Cache-Control: no-cache, no-store, must-revalidate" -H "Pragma: no-cache" -H "Expires: 0" '
            wget_cmd += f'{url} -O {self.functions.nodectl_path}{cmd[0]} -o /dev/null'
            system(wget_cmd)
            full_file_path = f"{self.functions.nodectl_path}{cmd[0]}"
            
            if cmd[2] == "none":
                self.functions.print_cmd_status({
                    "text_start": cmd[1],
                    "status": "complete",
                    "status_color": "green",
                    "newline": True
                })  
            else:
                text_output = Path(full_file_path).read_text().lstrip()
                if n != 1: text_output = text_output.replace(" ","")
                if cmd[3] not in text_output:
                    send_error(f"invalid {cmd[2]} downloaded or unable to download")
                outputs.append(text_output.replace("-----BEGINPUBLICKEY-----","").replace("-----ENDPUBLICKEY-----","").replace("\n",""))

                self.functions.print_cmd_status({
                    "text_start": cmd[1],
                    "status": "complete",
                    "status_color": "green",
                    "newline": True
                })   
        
        for n, cmd in enumerate(cmds[:-1]):   
            if cmd[2] == "PUBLIC KEY": 
                extra1, extra2 = "-----BEGIN PUBLIC KEY-----", "-----END PUBLIC KEY-----" 
                extra1s, main = 1,1
            else:
                extra1, extra2 = "", "" 
                extra1s, main = 0,-1   
                            
            self.functions.print_paragraphs([
                ["",1],[cmd[2],1,"blue","bold"],
                ["=","half","blue","bold"],
                [extra1,extra1s,"yellow"],
                [outputs[n],main,"yellow"],
                [extra2,2,"yellow"],
                ["To further secure that you have the correct binary that was authenticated with a matching",0,"magenta"],
                [f"{cmd[2]} found in yellow [above].",0,"yellow"],["Please open the following",0,"magenta"],["url",0,"yellow"], 
                ["in our local browser to compare to the authentic repository via",0,"magenta"], ["https",0,"green","bold"],
                ["secure hypertext transport protocol.",2,"magenta"],
                [urls[n],2,"blue","bold"],
            ])

        self.functions.print_cmd_status({
            "text_start": "verifying signature match",
            "newline": True
        })   
        
        self.log.logger.info("copy binary nodectl to nodectl dir for verification via rename")
        system(f"cp /usr/local/bin/nodectl /var/tessellation/nodectl/nodectl_{self.arch}")    
        result_sig = self.functions.process_command({
            "bashCommand": verify_cmd,
            "proc_action": "timeout"
        })
        result_nodectl_current_hash = self.functions.process_command({
            "bashCommand": f"openssl dgst -sha256 -hex nodectl_{self.arch}",
            "proc_action": "timeout",
            "working_directory": "/var/tessellation/nodectl/"
        }).strip("\n")
        
        bg, verb, error_line = "on_red","INVALID SIGNATURE - WARNING", ""
        
        # handle openssl version incompatibilities
        output_mod =  outputs[1].split('(', 1)[-1]
        result_nodectl_current_hash_mod = result_nodectl_current_hash.split('(', 1)[-1]
        
        self.log.logger.info("nodectl digital signature verification requested")
        if "OK" in result_sig and result_nodectl_current_hash_mod == output_mod:
            self.log.logger.info(f"digital signature verified successfully | {result_sig}")
            bg, verb = "on_green","SUCCESS - AUTHENTIC NODECTL"
        else: 
            error_line = "Review logs for details."
            self.log.logger.critical(f"digital signature did NOT verified successfully | {result_sig}")
        self.log.logger.info(f"digital signature - local file hash | {result_nodectl_current_hash}")
        self.log.logger.info(f"digital signature - remote file hash | {outputs[1]}")
        
        self.functions.print_paragraphs([
            ["",1],["VERIFICATION RESULT",1,"blue","bold"],
            [f" {verb} ",1,f"blue,{bg}","bold"],
            [error_line,1,"red"]
        ])
                 
        #clean up
        self.log.logger.info("cleaning up digital signature check files.")
        for cmd in cmds[1:]:
            remove(f'/var/tessellation/nodectl/{cmd[0]}')
        remove(f'/var/tessellation/nodectl/nodectl_{self.arch}')
                         

    def cli_minority_fork_detection(self,command_obj):
        caller = command_obj.get("caller","cli")
        argv_list = command_obj.get("argv_list",[])
        profile = command_obj.get("profile",False)
        
        if "-e" in argv_list:
            environment = argv_list[argv_list.index("-e")+1]
            profile = self.functions.pull_profile({"req":"one_profile_per_env"})
            profile = profile[0]

        if not profile:
            profile = argv_list[argv_list.index("-p")+1]
            environment = self.config_obj[profile]["environment"]
            
        global_ordinals ={}
        fork_obj = {
            "history": 1,
            "environment": environment,
            "return_values": ["ordinal","lastSnapshotHash"],
            "header": self.functions.get_headers,
            "return_type": "dict"
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
                self.log.logger.debug(f"command_line - cli_minority_fork_detection - [{caller}] - profile [{profile}] | fork_obj remote: [{self.functions.be_urls[environment]}].")
                global_ordinals["backend"] = self.functions.get_snapshot(fork_obj)
            else:
                fork_obj = {
                    **fork_obj,
                    "lookup_uri": f'http://{self.ip_address}:{self.functions.config_obj[profile]["public_port"]}/',
                    "header": {**fork_obj["header"], 'Accept': 'application/json'},
                    "get_results": "value",
                    "ordinal": global_ordinals["backend"]["ordinal"],
                    "action": "ordinal",
                }
                self.log.logger.debug(f"command_line - cli_minority_fork_detection - [{caller}] - profile [{profile}] | retrieving localhost: [{fork_obj['lookup_uri']}].")
                global_ordinals["local"] = self.functions.get_snapshot(fork_obj)

        if caller != "cli": return global_ordinals
        
        fork_result = colored("True","red",attrs=["bold"])
        if global_ordinals["local"]["lastSnapshotHash"] == global_ordinals["backend"]["lastSnapshotHash"]:
            fork_result = colored("False","green",attrs=["bold"])
            
        self.functions.print_paragraphs([
            [" MINORITY FORK DETECTION ",2,"green,on_blue","bold"],
        ])
        
        self.functions.print_cmd_status({
            "text_start": "Environment",
            "status": environment,
            "status_color": "cyan",
            "newline": True,
        })
        
        print_out_list = [
            {
                "PROFILE": profile,
                "IP ADDRESS": self.ip_address,
                "ENVIRONMENT": environment,
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
        
        if "-s" in argv_list:
            ip_address = argv_list[argv_list.index("-s")+1]
        if "-p" in argv_list:
            profile = argv_list[argv_list.index("-p")+1]
        
        consensus = self.functions.get_info_from_edge_point({
            "profile": profile,
            "caller": "status",
            "api_endpoint_type": "consensus",
            "specific_ip": ip_address,
        })
        consensus_match = colored("False","red")
        if consensus['specific_ip_found'][0] == consensus['specific_ip_found'][1]:
            consensus_match = colored("True","green")    
            
        if caller != "check_consensus": 
            return consensus_match
        
        print_out_list = [
            {
                "PROFILE": profile,
                "IP ADDRESS": ip_address,
                "CONSENSUS": consensus_match,
            },
        ] 
        for header_elements in print_out_list:
            self.functions.print_show_output({
                "header_elements" : header_elements
            })         
                  
                             
    def passwd12(self,command_list):
        self.log.logger.info("passwd12 command called by user")
        self.functions.check_for_help(command_list,"passwd12")
        profile = self.functions.pull_profile({
            "req": "default_profile"
        })
            
        self.functions.print_header_title({
            "line1": "P12 PASSPHRASE CHANGE",
            "line2": "request initiated",
            "newline": "top",
            "clear": True,
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
            self.log.logger.info(f"request to change p12 cancelled.")
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
            
            self.log.logger.error(f"User entered invalid p12 [name] or [location] options")
            
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
                        
                self.log.logger.error(f"{verb} entered passphrase did not match, had a length issue, or did not have proper restrictions.")
                
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
            ["Remove this file after verification of passphrase change is completed.  The backed up file contains ability to access the blockchain using the original passphrase.",2],
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
            self.log.logger.info(f"Successfully changed p12 passphrase.")
            status = "successful"
            color = "green"
            self.functions.print_paragraphs([
                ["",1], [f"The passphrase for",0,"green"], [p12_key_name,0,"white","bold"],
                ["was successfully changed.  Please update your configuration.",1,"green"],
                ["command:",0], ["sudo nodectl configure",2,"blue","bold"]
            ])
        else:
            self.log.logger.error(f"P12 Passphrase change failed | {result}.")
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
      
      
    def clean_files(self,command_obj):
        what = "clear_snapshots" if command_obj["action"] == "snapshots" else "clean_files"
        self.log.logger.info(f"request to {what} inventory by Operator...")
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
        p12 = P12Class(action_obj,False)
        p12.export_private_key_from_p12()
        
    
    def ssh_configure(self,command_obj):
        #,action="enable",port_no=22,install=False):
        var = SimpleNamespace(**command_obj)
        self.log.logger.info(f"SSH port configuration change initiated | command [{var.command}]")
        action_print = var.command
        show_help = False
        action = "disable" if "disable" in var.command else "enable"
        action = "port" if var.command == "change_ssh_port" else action
        port_no = None
        install = True if "install" in var.argv_list else False
        one_off = False
        
        if "help" in var.argv_list:
            show_help = True
        else:
            if "--port" not in var.argv_list and var.command == "change_ssh_port":
                show_help = True
            elif "--port" in var.argv_list:
                port_no = var.argv_list[var.argv_list.index("--port")+1]
            else:
                port_no = 22
                
            try:
                port_no = int(port_no)
            except:
                self.log.logger.error(f"SSH Configuration terminated due to invalid or missing port [{port_no}]")
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
                "extended": var.command
            })
         
        if "install" not in var.argv_list:
            confirm = True
        else:
            self.functions.print_paragraphs([
                ["",2], [" WARNING ",0,"yellow,on_red","bold"], 
                ["This is an administrative feature!",2,"red","bold"]
            ])
            if action != "port":
                self.functions.print_paragraphs([
                    ["This feature will",0], [action,0,"cyan","underline"], 
                    ["root",0], [" SSH ",0,"grey,on_yellow","bold"], ["access for this server (VPS, Bare Metal). It is independent of",0], 
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
            backup_dir = "/var/tmp"
            if not install:
                profile = self.functions.pull_profile({"req":"default_profile"})
                backup_dir = self.functions.config_obj[profile]["directory_backups"]
            
            if not path.exists(backup_dir):
                self.log.logger.warn(f"backup dir did not exist, attempting to create [{backup_dir}]")
                system(f"mkdir {backup_dir} > /dev/null 2>&1")
            
            self.log.logger.info(f"creating a backup of the sshd.config file to [{backup_dir}]")
            date = self.functions.get_date_time({"action":"datetime"})
            system(f"cp /etc/ssh/sshd_config {backup_dir}sshd_config{date}.bak > /dev/null 2>&1")
            
            config_file = open("/etc/ssh/sshd_config")
            f = config_file.readlines()
            with open("/tmp/sshd_config-new","w") as newfile:
                for line in f:
                    if action == "enable" or action == "disable":
                        if "PermitRootLogin" in line:
                            if action == "enable":
                                verb = "yes"
                                if path.isfile("/root/.ssh/backup_authorized_keys"):
                                    system(f"sudo mv /root/.ssh/backup_authorized_keys /root/.ssh/authorized_keys > /dev/null 2>&1")
                                    self.log.logger.info("found and recovered root authorized_keys file")
                                else:
                                    self.log.logger.critical("could not find a backup authorized_key file to recover")
                            if action == "disable":
                                verb = "no"
                                if path.isfile("/root/.ssh/authorized_keys"):
                                    system(f"sudo mv /root/.ssh/authorized_keys /root/.ssh/backup_authorized_keys > /dev/null 2>&1")
                                    self.log.logger.warn("found and renamed authorized_keys file")
                                else:
                                    self.log.logger.critical("could not find an authorized_key file to update")
                            newfile.write(f"PermitRootLogin {verb}\n")
                        else:
                            newfile.write(f"{line}")
                        action_print = f"{action} root user"
                        
                    elif action == "disable_user_auth":
                        if "PasswordAuthentication" in line:
                            verb = "yes"
                            if action == "disable_user_auth":
                                verb = "no"
                            newfile.write(f"PasswordAuthentication {verb}\n")
                        else:
                            newfile.write(f"{line}")
                        action_print = f"password authentication set to {verb}"
                        
                    elif action == "port":
                        action_print = action
                        if not "GatewayPorts" in line and "Port" in line:
                            newfile.write(f"Port {port_no}\n")
                        else:
                            newfile.write(f"{line}")
            
            newfile.close()
            config_file.close()

            # one off check
            if action == "disable_user_auth":
                if path.exists("/etc/ssh/sshd_config.d/50-cloud-init.conf"):
                    one_off = True
                    config_file = open("/etc/ssh/sshd_config.d/50-cloud-init.conf")
                    f = config_file.readlines()
                    with open("/tmp/sshd_config-new2","w") as newfile:
                        for line in f:
                            if "PasswordAuthentication" in line:
                                verb = "yes"
                                if action == "disable_user_auth":
                                    verb = "no"
                                newfile.write(f"PasswordAuthentication {verb}\n")
                            else:
                                newfile.write(f"{line}")
                    newfile.close()
                    config_file.close()
            
            progress = {
                "text_start": "Reloading",
                "text_end": "daemon",
                "brackets": "SSH",
                "status": "running"
            }
            self.functions.print_cmd_status(progress)

            system("mv /tmp/sshd_config-new /etc/ssh/sshd_config > /dev/null 2>&1")
            if one_off:
                system("mv /tmp/sshd_config-new2 /etc/ssh/sshd_config.d/50-cloud-init.conf > /dev/null 2>&1")
                
            sleep(1)
            system("service sshd restart > /dev/null 2>&1")
            
            self.log.logger.info(f"SSH port configuration change successfully implemented [{action_print}]")
            if one_off:
                self.log.logger.info(f"SSH configuration for an include file [one off] has been updated with password authentication [{verb}]")
                
            self.functions.print_cmd_status({
                **progress,
                "status": "complete",
                "status_color": "green",
                "newline": True
            })


    def prepare_and_send_logs(self, command_list):
        self.functions.check_for_help(command_list,"send_logs")    
        send = Send({
            "config_obj": self.functions.config_obj,
            "command_list": command_list,
            "ip_address": self.ip_address,
        })             
        if "scrap" in command_list: self.send = send
        else:
            send.prepare_and_send_logs()
            
        
    def download_tess_binaries(self,command_list):
        if "-e" not in command_list:
            command_list.append("help")
        self.functions.check_for_help(command_list,"refresh_binaries")

        self.functions.print_header_title({
          "line1": "TESSELLATION BINARIES",
          "line2": "refresh request",
          "clear": False,
        })
        
        self.functions.print_paragraphs([
            [" WARNING ",0,"yellow,on_red","bold"], ["You will need to restart all services after completing this download.",2]
        ])
        
        self.functions.confirm_action({
            "yes_no_default": "n",
            "return_on": "y",
            "prompt": "Are you sure you want to overwrite Tessellation binaries?",
            "exit_if": True,
        })
        
        download_obj = {
            "environment": command_list[command_list.index("-e")+1]
        }
        if "-v" in command_list:
            download_obj["download_version"] = command_list[command_list.index("-v")+1]
            
        self.node_service.download_constellation_binaries(download_obj)

    # ==========================================
    # upgrade command
    # ==========================================

    def upgrade_nodectl(self,command_obj):
        argv_list = command_obj["argv_list"]
        custom_version, upgrade_chosen = False, False
        
        if command_obj["help"] == "help" or "help" in argv_list:
            self.functions.print_help({
                "extended": "upgrade_nodectl"
            })
         

        env_set = set()
        if "-v" in argv_list: 
            custom_version = argv_list[argv_list.index("-v")+1]
            self.functions.print_paragraphs([
                [" WARNING ",0,"red,on_yellow"], ["This will skip verification checks and",0],
                ["attempt",0,"red","bold"], ["to upgrade/downgrade your Node's nodectl version to:",0], [custom_version,2,"yellow","bold"],
                ["If you decide to downgrade to a version that meets or falls below the upgrade path requirements",0,"red"],
                ["for nodectl, you might encounter unexpected consequences that could make your Node unmanageable. In these",0,"red"],
                ["situations, it is advisable to re-create the Node and perform a clean installation.",2,"red"],
                ["hint:",0],["sudo nodectl upgrade_path",2,"yellow"],
                ["Are you sure you want to continue?",1,"magenta"],
            ])

        try:
            for i_profile in self.profile_names:
                environment_name = self.config_obj[i_profile]["environment"]
                env_set.add(self.config_obj[i_profile]["environment"])
        except Exception as e:
            try:
                self.log.logger.critical(f"unable to determine environment type [{environment_name}]")
            except:
                self.log.logger.critical(f"unable to determine environment type [unknown]")
            finally:
                self.error_messages.error_code_messages({
                    "error_code": "cmd-3435",
                    "line_code": "input_error",
                    "extra": e,
                })   
        
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

        self.log.logger.info(f"Upgrade request for nodectl for [{environment_name}] using first profile [{profile}].")

        version_obj = self.version_obj[environment_name] # readability
        self.functions.print_clear_line()

        def print_prerelease():
            if version_obj["nodectl"]["nodectl_prerelease"]:
                self.functions.print_paragraphs([
                    [" WARNING ",0,"yellow,on_red"], ["This is a pre-release version and may have developer experimental features, adds or bugs.",1,"red","bold"],
                ])
                
        nodectl_uptodate = self.version_obj[environment_name]["nodectl"]["nodectl_uptodate"]
        latest_nodectl = version_obj["nodectl"]["latest_nodectl_version"]
        node_nodectl_version = self.version_obj['node_nodectl_version']
        
        if nodectl_uptodate and nodectl_uptodate != "current_less" and not custom_version:
            self.log.logger.error(f"Upgrade nodectl to new version request not needed {node_nodectl_version}.")
            up_to_date = "is already up to date..."
            if nodectl_uptodate == "current_greater": up_to_date = "is a version higher than the official release"
            self.functions.print_paragraphs([
                ["Current version of nodectl:",0], [node_nodectl_version,0,"yellow"],
                [up_to_date,1], ["nothing to do",2,"red"]
            ])
            print_prerelease()
            return
        
        if custom_version:
            upgrade_chosen = custom_version
        else:
            self.functions.print_paragraphs([
                [" WARNING ",0,"yellow,on_red"], ["You are about to upgrade nodectl.",1,"green","bold"],
                ["You are currently on:",0], [environment_name.upper(),1,"yellow"],
                ["  current version:",0], [node_nodectl_version,1,"yellow"],
                ["available version:",0], [latest_nodectl,1,"yellow"],
                ["   latest release:",0], [self.version_obj["upgrade_path"][0],1,"yellow"],
            ])
            if latest_nodectl != self.version_obj["upgrade_path"][0]:
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
                    })
                    self.functions.print_paragraphs([
                        [" WARNING ",0,"red,on_yellow"], ["downgrading to a previous version of nodectl may cause",0,"red"],
                        ["undesirable effects.",0,"red"], ["It is recommended to upgrade to a newer known version or to",0],
                        ["reinstall a fresh copy at a lower version that suits your needs.",2]
                    ])
                    
                    option = self.functions.print_option_menu({
                        "options": [
                            self.version_obj["upgrade_path"][0],
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
                
        self.functions.confirm_action({
            "yes_no_default": "n",
            "return_on": "y",
            "prompt": f"Upgrade to {colored(upgrade_chosen,'yellow')}?"
        })
        
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
            "upgrade_required": True if version_obj["nodectl"]["upgrade"] == "True" else False,
            "pre_release": version_obj["nodectl"]["nodectl_prerelease"],
        })

        upgrade_file = upgrade_file.replace("NODECTL_VERSION",upgrade_chosen)
        upgrade_file = upgrade_file.replace("NODECTL_OLD",node_nodectl_version)
        upgrade_file = upgrade_file.replace("NODECTL_BACKUP",backup_location)
        upgrade_file = upgrade_file.replace("ARCH",self.arch)
        
        upgrade_bash_script = "/var/tmp/upgrade-nodectl"
        with open(upgrade_bash_script,'w') as file:
            file.write(upgrade_file)
        file.close
        sleep(1)  
        self.functions.process_command({
            "bashCommand": "chmod +x /var/tmp/upgrade-nodectl",
            "proc_action": "wait"
        })  
        
        system("sudo /var/tmp/upgrade-nodectl")
        
        if self.functions.get_size("/usr/local/bin/nodectl",True) < 1:
            self.functions.print_paragraphs([
                ["The original backed up version of nodectl will be restored",1,"yellow"],
                ["file version:",0],[node_nodectl_version,2,"blue","bold"],
            ])
            self.log.logger.warn(f"nodectl upgrader is restoring [{backup_location}nodectl_{node_nodectl_version}] to [/usr/local/bin/nodectl]")
            try:
                system(f"mv {backup_location}nodectl_{node_nodectl_version} /usr/local/bin/nodectl > /dev/null 2>&1")
            except: pass
            if self.functions.get_size("/usr/local/bin/nodectl",True) < 1:
                self.log.logger.critical(f"nodectl upgrader unable to restore [{backup_location}nodectl_{node_nodectl_version}] to [/usr/local/bin/nodectl]")
                self.functions.print_paragraphs([
                    [" WARNING ",0,"red,on_yellow"], ["unable to restore original nodectl, please manually download via",0,"red"],
                    ["the known",0,"red"], ["wget",0,"yellow"], ["command. See Constellation Network documentation hub for further details.",1,"red"]
                ])
        else:
            self.log.logger.info(f"Upgrade of nodectl to new version successfully completed")
        
        try: 
            remove("/var/tmp/upgrade-nodectl")
            self.log.logger.info("upgrade_nodectl files cleaned up successfully.")
        except OSError as e:
            self.log.logger.error(f"upgrade_nodectl nodectl method unable to clean up files : error [{e}]")
            
        return 0 

    # ==========================================
    # reusable methods
    # ==========================================

    def get_and_verify_snapshots(self,snapshot_size, environment):
        error = True
        return_data = {}
        for _ in range(0,5): # 5 attempts
            data = self.functions.get_snapshot({
                "action": "history",
                "history": snapshot_size,
                "environment": environment,
            })   
            
            try:
                start_time = datetime.strptime(data[-1]["timestamp"],"%Y-%m-%dT%H:%M:%S.%fZ")
                end_time = datetime.strptime(data[0]["timestamp"],"%Y-%m-%dT%H:%M:%S.%fZ")
                return_data["start_ordinal"] = data[-1]["ordinal"]
                return_data["end_ordinal"] = data[0]["ordinal"]
                return_data["elapsed_time"] = end_time - start_time
            except Exception as e:
                self.log.logger.error(f"received data from backend that wasn't parsable, trying again | [{e}]")
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
        self.log.logger.error(f"[{var.command}] requested --> removed for [{new_command}]")
        self.functions.print_paragraphs([
            [var.command,0,"white","bold"], ["command has been",0,"red"], ["removed",1,"red","bold"],
            ["As of version:",0,"white","bold"], [var.version,1,"yellow"]
        ])
        if is_new:
            self.functions.print_paragraphs([
                ["Please use",0,"white","bold"], [new_command,0,"yellow","bold"], ["instead",1,"white","bold"], 
                [help_hint,1,"magenta"]
            ])
        if done_exit:
            return 0

                  
        
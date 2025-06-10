import re
import base58
import psutil
import socket

from hashlib import sha256
from time import sleep, perf_counter
from datetime import datetime
from os import system, path, get_terminal_size, remove, chmod, makedirs, listdir
from shutil import copy2, move
from sys import exit
from types import SimpleNamespace
from getpass import getpass
from termcolor import colored, cprint
from secrets import compare_digest
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor

from modules.p12 import P12Class
from modules.troubleshoot.snapshot import * # discover_snapshots, merge_snap_results, ordhash_to_ordhash, process_snap_files, remove_elements, clean_info, set_count_dict, custom_input, print_report
from modules.download_status import DownloadStatus
from modules.status import Status
from modules.node_service import Node
from modules.troubleshoot.errors import Error_codes
from modules.troubleshoot.logger import Logging
from modules.cleaner import Cleaner
from modules.troubleshoot.send_logs import Send
from modules.troubleshoot.ts import Troubleshooter
from modules.find_newest_standalone import find_newest
from modules.config.ipv6 import handle_ipv6
from modules.console import Menu
from modules.delegate import DelegatedStaking
from modules.crypto.crypto_class import NodeCtlCryptoClass

class TerminateCLIException(Exception): pass
class FullReturn(Exception): pass

class CLI():
    
    def __init__(self, log):
        self.log = log


    # ==== SETTERS ====
    
    def set_parameters(self,command_obj):
        self.profile = command_obj.get("profile",None)
        self.command_list = command_obj.get("command_list",[])
        self.profile_names = command_obj.get("profile_names",None)
        self.skip_services = command_obj.get("skip_services",False)
        self.auto_restart =  command_obj.get("auto_restart",False)
        self.caller = command_obj.get("caller","default")
        self.functions = command_obj["functions"]
        self.ip_address = command_obj["ip_address"]
        self.primary_command = command_obj["command"]

        self.set_variables()
    
    
    def set_self_value(self, name, value):
        setattr(self, name, value)
        
        
    def set_variables(self):
        self.config_obj = self.functions.config_obj
        # try:
        #     self.log_key = self.config_obj["global_elements"]["log_key"]
        # except:
        #     self.config_obj["global_elements"]["log_key"] = "main"
        #     self.log_key = "main"

        config_global_elements = self.config_obj.setdefault("global_elements", {})
        self.log_key = config_global_elements.setdefault("log_key", "main")
        

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
                if "--skip-warning-messages" in self.command_list or self.config_obj["global_elements"]["developer_mode"]:
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
                "text_start": "Preparing node details",
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
        self._print_log_msg("debug",f"build_node_class --> calling node Obj - [{command_obj}]")
        if self.primary_command != "quiet_install":
            self.functions.print_cmd_status({
                "text_start": "Acquiring node details"
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
        self._print_log_msg("debug",f"build_node_class --> setting profile parameters | profile [{self.profile}]")
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
    
    
    # ==== GETTERS ====

    def get_self_value(self, name, default=False):
        return getattr(self, name, default)
    
    
    def get_and_verify_snapshots(self,command_obj):
        snapshot_size = command_obj["snapshot_size"]
        environment = command_obj["environment"]
        profile = command_obj["profile"]
        ordinal = command_obj.get("ordinal",False)
        return_on_error = command_obj.get("return_on_error",False)
        return_type = command_obj.get("return_type","list")

        error = True
        return_data = {}
        action = "history"

        if ordinal:
            action = "rewards"
        
        data = self.functions.get_snapshot({
            "action": action,
            "history": snapshot_size,
            "environment": environment,
            "profile": profile,
            "ordinal": ordinal,
            "return_type": return_type,
        })   
        
        try:
            start_time = datetime.strptime(data[-1]["timestamp"],"%Y-%m-%dT%H:%M:%S.%fZ")
            end_time = datetime.strptime(data[0]["timestamp"],"%Y-%m-%dT%H:%M:%S.%fZ")
            return_data["start_ordinal"] = data[-1]["ordinal"]
            return_data["end_ordinal"] = data[0]["ordinal"]
            return_data["elapsed_time"] = end_time - start_time
        except Exception as e:
            self._print_log_msg("error",f"received data from backend that wasn't parsable, trying again | [{e}]")
            sleep(2)
        else:
            error = False
            return_data["start_time"] = start_time
            return_data["end_time"] = end_time
            return_data["data"] = data
            
        if error:
            if return_on_error: 
                return False
            self.error_messages.error_code_messages({
                "error_code": "cmd-3151",
                "line_code": "api_error",
                "extra": None,
            })
        
        return return_data    
    
    
    # ==========================================
    # show commands
    # ==========================================
    
    def show_system_status(self,command_obj):
        from modules.submodules.show_status import ShowStatus
        
        command_obj["getter"] = self.get_self_value
        command_obj["setter"] = self.set_self_value
        status = ShowStatus(command_obj)
        status.set_parameter()

        self.functions.check_for_help(status.argv,status.called_command)

        if command_obj.get("config_obj"): # if there an updated config?
            status.set_self_value("config_obj",command_obj["config_obj"])   
                 
        status.set_profile()
        status.set_watch_parameters()
        status.process_status()    
        status.print_auto_restart_options()    
                

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
            
        self._print_log_msg("info",f"show prices requested")
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
        self._print_log_msg("info","show market requested")
                
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
        self._print_log_msg("info",f"show health requested")

        status = Status(self.functions)
        status.called_command = self.command_obj["command"]
        status.non_interactive = True if "--ni" in command_list else False
        if self.config_obj["global_elements"]["d240412"]:
            status.new_method = True
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

        self._print_log_msg("info",f"show cpu and memory stats")

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
        
        from modules.submodules.peers import Peers 
        
        peers = Peers(self.set_self_value, self.get_self_value)
        
        peers.set_parameters()
        peers.handle_state_specific_request()
        peers.set_title()
        peers.handle_csv_file()
        peers.handle_source_node()
        
        if "-c" in command_list:
            self.cli_find(peers.count_args)
            return
        
        peers.handle_info_type_request()

        # peers.get_ext_ip()
        
        # peers.peer_results = self.node_service.functions.get_peer_count({
        #     "peer_obj": peers.sip, 
        #     "profile": peers.profile, 
        #     "compare": True
        # })

        # peers.handle_peer_error()
        peers.handle_wallets()
        peers.set_main_print_out()
        peers.set_pagination()
        peers.print_submenu()
        peers.print_results()
        peers.print_csv_success()


    def show_ip(self,argv_list):
        self._print_log_msg("info",f"whoami request initiated.")
        ip_address = self.ip_address
        
        if "-id" in argv_list:
            if "-p" in argv_list: # only required for "-id"
                profile = argv_list[argv_list.index("-p")+1]
                id = argv_list[argv_list.index("-id")+1]
                try:
                    list = self.functions.get_cluster_info_list({
                        "profile": profile,
                        "ip_address": self.config_obj[profile]["edge_point"],
                        "port": self.config_obj[profile]["edge_point_tcp_port"],
                        "api_endpoint": "/cluster/info",
                        "error_secs": 3,
                        "attempt_range": 3,
                    })   
                except Exception as e:
                    self._print_log_msg("error",f"request to find node id request failed | error [{e}]")
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
        self._print_log_msg("info",f"Show security request made.")
        
        with ThreadPoolExecutor() as executor:
            self.functions.event = True
            _ = executor.submit(self.functions.print_spinner,{
                "msg": f"Reviewing [VPS security], please wait ",
                "color": "magenta",
            })              
            status = Status(self.functions)
            status.called_command = self.command_obj["command"]
            if self.config_obj["global_elements"]["d240412"]:
                status.new_method = True
            result = status.execute_status()
            self.functions.event = False
            if not result:
                exit("  Linux distribution file access error")

        print_out_list = [
            {
                "header_elements" : {
                    "LOG ERRORS": status.error_auths_count,
                    "ACCESS ACCEPTED": status.accepted_logins,
                    "ACCESS DENIED": status.invalid_logins,
                },
                "spacing": 18,
            },
            {
                "header_elements" : {
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
            ["",1],["AUTHORIZATION LOG DETAILS",1,"blue","bold"],
            ["=","full","blue","bold"],
            [f"Since: {status.creation_time}",2,"magenta","bold"],
        ])    
        for line in status.accepted_list:
            cprint(f"  {line}","cyan")           
            
            
    def show_logs(self,command_list):  
        self._print_log_msg("debug","show logs invoked")
        self.functions.check_for_help(command_list,"logs")

        profile = self.functions.default_profile
        possible_logs = [
            "nodectl","auto_restart","versioning",
            "app", "http", "gossip", "transactions"
        ]

        name = command_list[command_list.index("-l")+1] if "-l" in command_list else "empty"
        self._print_log_msg("info","show log invoked")

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
            self._print_log_msg("info",f"show log invoked")
            
            self.functions.print_header_title({
                "line1": "SHOW LOGS",
                "clear": True,
            })
            
            t_options = [
                "nodectl log","auto_restart log","versioning log",
                "Tessellation app log","Tessellation http log",
                "Tessellation gossip log","Tessellation transaction log","Quit",
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
                "8": "Quit",
            }    
            if option == "8":
                return
            
            file_path = option_match.get(option) 


        self.functions.print_paragraphs([
            ["",1],["shift + g",0,"yellow"],["Move to the end of the file and follow.",1],
            ["        q",0,"yellow"],["quit out of the log viewer",2],
        ])
        _ = self.functions.print_any_key({})
        system(f"lnav {file_path}")     

        
    def show_list(self,command_list):
        self._print_log_msg("info",f"Request for list of known profiles requested")
        self.functions.check_for_help(command_list,"list")
        
        profile_only = True if "-p" in command_list else False
        
        coins = self.functions.get_local_coin_db()

        self.functions.print_clear_line()
        self.functions.print_header_title({
            "line1": "CURRENT LOADED CLUSTERS",
            "line2": "Based on local node's config",
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
            ["Note:",0,"yellow"], ["port configurations are for the local node only.",0,"magenta"],
            ["API ports are per node customizable.",1,"magenta"],
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
        self._print_log_msg("info",f"Request to view known node states by nodectl")
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
                        "profile": profile,
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
                        self._print_log_msg("warning","show_seedlist_participation -> LB may not be accessible, trying local.")
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
        self._print_log_msg("info","show current snapshot proofs called")
        if "-p" in command_list:
            self.profile = command_list[command_list.index("-p")+1]
            self._print_log_msg("debug",f"show current snapshot proofs using profile [{self.profile}]")
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
            self._print_log_msg("error",f"show_current_snapshot_proofs -> unable to process results [{e}]")
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

        from modules.submodules.current_rewards import CurrentRewards
        current_rewards = CurrentRewards(self,command_list)

        current_rewards.set_parameters()
        current_rewards.handle_snapshot_size()
        current_rewards.get_data()
        current_rewards.set_search_n_target_addr()
        current_rewards.handle_target_addr()
        current_rewards.set_csv()
        current_rewards.parse_rewards()
        current_rewards.set_elapsed_time()
        current_rewards.process_csv()
        current_rewards.set_print_out_list()
        current_rewards.print_initial_output()

        if current_rewards.target_dag_addr:
            return

        current_rewards.print_list_results()        
        current_rewards.handle_csv_instructions()
        

    def show_dip_error(self,command_list):
        self.functions.check_for_help(command_list,"show_dip_error")
        profile = command_list[command_list.index("-p")+1]
        self._print_log_msg("info",f"show_dip_error -> initiated - profile [{profile}]")
        
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
            self._print_log_msg("warning",f"command_line -> show_profile_issues -> unable to obtain profile, skipping [{e}]")
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
                self._print_log_msg("error","show_profile_error -> unable to sort timestamps, skipping")

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
                self._print_log_msg("critical",f"show_profile_issues -> attempted to remove duplicate error messages which resulted in [{e}]")
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
                self._print_log_msg("error",f"cli_restart -> profile [{f_profile}] error [{result['error_msg']}] error found [{result['find']}] user message [{result['user_msg']}]")
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
                ["--skip-warning-messages",0,"yellow"], ["was enabled.",1,"red"],
                ["This command will",0,"red"],
                ["automatically disable this option in order to function properly.",1,"red"],
            ])
            self.skip_warning_messages = False
            self.functions.print_cmd_status({
                "text_start": "disabling --skip-warning-messages",
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
                ["nodectl installed:",0,"blue","bold"], ["Running on node.",1],
                ["nodectl latest stable:",0,"blue","bold"], ["Recommended version.",1],
                ["nodectl latest:",0,"blue","bold"], ["Newest, may be experimental and not stable.",1],
                ["nodectl config:",0,"blue","bold"], ["nodectl's configuration version.",2],
            ])
       
 
    def check_source_connection(self,command_list):
        self.functions.check_for_help(command_list,"check_source_connection")
        self._print_log_msg("info",f"Check source connection request made.")
        self.set_profile(command_list[command_list.index("-p")+1])
        self.functions.test_ready_observing(self.profile)
        
        self.functions.print_states()
        
        self.functions.print_paragraphs([
            ["Source:",0,"magenta"], ["Server this node is joined to",1],
            ["  Edge:",0,"magenta"], ["This node",2],
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
        self._print_log_msg("info",f"Check connection request made. | {edge}")

        node_list = [source,edge]
        flip_flop = []

        self.functions.test_ready_observing(self.profile)
        
        for n, node in enumerate(node_list):
            # "peer_count": [], # peer_count, node_online, peer_set
            self._print_log_msg("debug",f"checking count and testing peer on {node}")
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
            self._print_log_msg("error",f"check_connection - source - edge - threw error [{e}]")
        else:
            node_obj_list[1]["missed_ip_count"] = len(node_obj_list[1]["missed_ips"])
  

        # source node missing                          edge                    -              source
        try:
            node_obj_list[0]["missed_ips"] = node_obj_list[1]["peer_set"] - node_obj_list[0]["peer_set"]
        except Exception as e:
            self._print_log_msg("error",f"check_connection - edge - source - threw error [{e}]")
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
            self._print_log_msg("error",f"Check  connection request returned threshold or other error.")
            self.functions.print_paragraphs([
                ["This node is",0,"yellow"], ["not 100%",0,"red","underline"], ["connected",2,"yellow"],
                
                ["However, it meets a 8% the threshold",2,"green"],
                
                ["You can safely allow your node to function.",0,"green","bold"], ["Note:",0,"green","underline"],
                ["You may be missing nodes because",0,"green"], ["other",0,"red"], 
                ["Nodes are always coming and going on the network, or other nodes may be the source of the",0,"green"],
                ["issue(s)",2,"red"]
            ])
            
        if print_error_flag:
            self.functions.print_paragraphs([
                ["Issues were found.",0,"red","bold"], ["See help for details",1,"red"],
                ["sudo nodectl check_connection help",2],
                ["Although you do not have a full connection, the issue may",0,"red","bold"], 
                ["not",0,"red","underline"], ["be directly correlated with your node.",2,"red","bold"]
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
                ["This node looks",0,"green"], ["healthy!",2,"green","bold"],
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
        
        self._print_log_msg("debug","testing for upgrade path requirements")

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
                    ["",1],[" POSSIBLE PRE-RELEASE ",0,"red,on_yellow"],
                    ["Use this version of nodectl with caution because it may produce undesired affects.",0,"yellow"],
                    ["If the",0,"yellow"], ["sudo nodectl upgrade",0], ["command was used against this version, you may run",0,"yellow"],
                    ["into undesired results if you attempt to downgrade to a previous version.  A new installation of nodectl would be",0,"yellow"],
                    ["a better option to resume on a stable release.",2,"yellow"],

                    ["Proceed with caution.",2,"magenta"],
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
        
        self.functions.set_self_value("log",self.log)
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
                self._print_log_msg("warning","check_for_new_version -> unable to determine if [nodectl] version is up to date... skipping")
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
                self._print_log_msg("warning","check_for_new_version -> unable to determine if [Tessellation] version is up to date... skipping")
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
        from modules.submodules.start import StartNode
        
        command_obj["get_self_value"] = self.get_self_value
        command_obj["set_self_value"] = self.set_self_value
        cli_start = StartNode(command_obj)
        
        cli_start.set_parameters()
        cli_start.handle_check_for_help()
        cli_start.set_progress_obj()
        cli_start.print_start_init()
        cli_start.handle_seedlist()
        cli_start.set_service_state()
        cli_start.print_start_complete()        
        cli_start.print_timer()        
        cli_start.process_start_results()
        cli_start.print_final_status()
        
        
    def cli_stop(self,command_obj):
        from modules.submodules.stop import StopNode
        
        command_obj["getter"] = self.get_self_value
        command_obj["setter"] = self.set_self_value
        
        cli_stop = StopNode(command_obj)

        cli_stop.set_parameters()
        cli_stop.process_delay()
        cli_stop.handle_help()
        cli_stop.handle_check_for_leave()
        cli_stop.set_progress_obj()                
        cli_stop.print_init_process()
        cli_stop.process_stop_request()

        if cli_stop.result == "skip_timer":
            cli_stop.set_show_timer(False)

        if cli_stop.spinner:
            cli_stop.set_show_timer(False)
            
        cli_stop.set_rebuild()
        cli_stop.print_progress_complete()
        cli_stop.print_final_status()

        
    def cli_restart(self,command_obj):
        from modules.submodules.restart import RestartNode
        
        cli_restart = RestartNode(self.set_self_value, self.get_self_value, command_obj)
        
        cli_restart.set_parameters()
        cli_restart.handle_help_request()
        
        cli_restart.set_performance_start()
        cli_restart.handle_input_error()
        cli_restart.print_restart_init() 

        cli_restart.set_function_obj_variables()
        cli_restart.process_ep_state()    
        
        cli_restart.get_profiles()
        cli_restart.handle_all_parameter()
        
        self.slow_flag = cli_restart.slow_flag
   
        cli_restart.handle_empty_profile()
        cli_restart.handle_request_error()            
        cli_restart.process_leave_stop()
        cli_restart.process_seedlist_updates()
        cli_restart.print_cursor_position()

        cli_restart.process_start_join()
        cli_restart.print_performance()                        
                

    def cli_reboot(self,command_list):

        def do_reboot():
            _ = self.functions.process_command({
                "bashCommand": "sudo reboot",
                "proc_action": "subprocess_devnull",
            })

        self._print_log_msg("info","user initiated system warm reboot.")
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
            ["This will reboot your node!",2,"yellow","bold"],
            
            ["This feature will allow your node to properly leave the Tessellation network prior to soft booting (rebooting).",0],
            ["This reboot will cause the node Operator to lose access to the VPS or bare metal system that this node is running on.",2],
        ])
        
        if on_boot:
            self.functions.print_paragraphs([
                ["nodectl has detected that you have",0],["on_boot",0,"yellow"], ["enabled!",0],
                ["Once your VPS completes it startup, the node should automatically rejoin the network clusters configured.",2],
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
                ["Preparing to reboot.  You will lose access after this message appears.  Please reconnect to your node after a few moments of patience, to allow your server to reboot, initialize, and restart the SSH daemon.",2]
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
        from modules.submodules.join import Join
        
        command_obj["setter"] = self.set_self_value
        command_obj["getter"] = self.get_self_value
        cli_join = Join(command_obj)
        
        start_timer = perf_counter()
        
        cli_join.set_parameters()
        cli_join.handle_help_arg()
        
        cli_join.print_title()        
        cli_join.print_joining()

        cli_join.handle_layer0_links()
        cli_join.set_state_from_profile()    
        
        cli_join.print_review()

        if cli_join.handle_ready_state():
            return
        
        cli_join.handle_apinotready()
        cli_join.handle_static_peer()
        
        cli_join.process_join_cluster()
        cli_join.handle_link_color()
        cli_join.process_post_join()
            
        cli_join.parse_snapshot_issues()
        cli_join.parse_tolerance_issues()
        
        cli_join.handle_offline_state()
        cli_join.handle_join_complete()

        cli_join.process_incomplete_peer_connections()

        cli_join.handle_bad_join()
        cli_join.print_completed_join(start_timer)
                
                
    def cli_leave(self,command_obj):
        from modules.submodules.leave import LeaveNode
        
        cli_leave = LeaveNode(self,command_obj)
    
        cli_leave.set_parameters()
        cli_leave.set_progress_obj()
        cli_leave.handle_pause()
        cli_leave.print_leave_init()
        cli_leave.get_profile_state(False)
        cli_leave.process_leave_cluster()

        if cli_leave.skip_msg:
            return
            
        while True:
            cli_leave.parse_leave_status()
            cli_leave.print_leaving_msg()
            cli_leave.print_leave_progress()
            cli_leave.set_state_obj()    
            cli_leave.get_profile_state(True)
                
            cli_leave.print_leave_progress(True)    

            if cli_leave.process_leave_status(): 
                cli_leave.print_outofcluster_msg()
                break

            if cli_leave.leave_obj: 
                break    
            
            cli_leave.handle_not_outofcluster()
            if cli_leave.handle_max_retries(): 
                break

            cli_leave.parse_log_wait_for_leave()
            cli_leave.get_profile_state(False)

            if cli_leave.process_leave_status(): 
                break
            if cli_leave.start > 2:
                cli_leave.set_skip_lookup(True)
    
            if cli_leave.skip_log_lookup:
                cli_leave.print_leave_timer()
                    
            cli_leave.handle_wait_for_offline()
            cli_leave.set_start_increment() 
        
        if self.primary_command == "leave":
            self.show_system_status(command_obj)     
                    
        
    def cli_grab_id(self,command_obj):
        from modules.submodules.node_id import NodeDAGid
        nodeid_dag_obj = NodeDAGid(self,command_obj)

        nodeid_dag_obj.set_parameters()
        nodeid_dag_obj.handle_file_request()
        nodeid_dag_obj.set_profile()
        nodeid_dag_obj.set_static_target_ip()

        if not nodeid_dag_obj.handle_local_request():
            return False
        
        try:
            nodeid_dag_obj.handle_ext_or_ready_state()
        except Exception as e:
            false_lookups = e.args[0] # readability
            return false_lookups

        nodeid_dag_obj.set_command()        
        nodeid_dag_obj.process_node_id()

        if nodeid_dag_obj.dag_addr_only:
            return nodeid_dag_obj.nodeid 

        nodeid_dag_obj.handle_dag_command()
        nodeid_dag_obj.set_print_out_ip()
        nodeid_dag_obj.print_display()
                                                   
        if nodeid_dag_obj.return_success:    
            if nodeid_dag_obj.return_success == "set_value":
                self.nodeid = nodeid_dag_obj.nodeid
            elif nodeid_dag_obj.nodeid == "unable to derive":
                return False 
            return True
            

    def cli_find(self,argv_list):
        self.functions.check_for_help(argv_list,"find")
        
        from modules.submodules.find import Find
        
        command_obj = {
            "setter": self.set_self_value,
            "getter": self.get_self_value,
            "argv_list": argv_list,
        }
        
        cli_find = Find(command_obj)
        
        try:
            cli_find.set_parameters()
        except FullReturn:
            return
            

        cli_find.handle_ordhash_lookup()
        cli_find.set_empty_source_obj()
        cli_find.handle_list_file_build()
        cli_find.get_peer_results()
        
        if "return_only" in argv_list:
            return cli_find.target_obj[cli_find.lookup_type]
        
        cli_find.print_final_results()
        
        return
            
        
    def cli_nodeid2dag(self,command_obj):
        if isinstance(command_obj,list):
            argv_list = command_obj
            nodeid = argv_list[0]
            return_only = False
            caller = "default"
        else:
            nodeid = command_obj.get("nodeid",False)
            profile = command_obj.get("profile",False)
            caller = command_obj.get("caller","default")
            if not profile:
                profile =self.profile_names[0]
            return_only = command_obj.get("return_only",True)
            argv_list = []

        self.functions.check_for_help(argv_list,"nodeid2dag")
        pkcs_prefix = "3056301006072a8648ce3d020106052b8104000a03420004"  # PKCS prefix + 04 required byte
        self._print_log_msg("debug",f"cli_nodeid2dag: preparing to convert nodeid to dag [{nodeid}]")

        try:
            if nodeid != self.config_obj["global_elements"]["nodeid_obj"][profile]:
                raise 
            dag_address = self.config_obj["global_elements"]["nodeid_obj"][f"{profile}_wallet"]
        except:
            if not nodeid:
                nodeid = 0  # force error
            else:
                output_nodeid = f"{nodeid[0:8]}...{nodeid[-8:]}"
            
            try:
                if len(nodeid) == 128:
                    nodeid = f"{pkcs_prefix}{nodeid}"
                else:
                    if caller == "show_peers":
                        return "UnableToRetrieve"
                    raise
            except:
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

        if return_only:
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
        self._print_log_msg("info","command_line -> request to handle ipv6 issued")

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
        self._print_log_msg("info","command_line -> request to upgrade VPS issued")

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

            ["Any necessary modifications to core system elements required for the node to operate successfully",0],
            ["will be automated through the standard nodectl upgrade process. Therefore, we can accept the",0],
            ["defaults during this process.",2],

            ["Advanced users have the flexibility to select any options required for customized or non-node operations being completed simultaneously on this VPS.",2,"red"],
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
                ["exit any clusters that this node is currently participating in before proceeding with the reboot.",0,"yellow"],
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
                self._print_log_msg("debug",f"command_line - cli_minority_fork_detection - [{caller}] - profile [{profile}] | fork_obj remote: [{self.functions.be_urls[environment]}].")
                global_ordinals["backend"] = self.functions.get_snapshot(fork_obj)
                if global_ordinals["backend"] is None:
                    self._print_log_msg("error","check_minority_fork -> backend api endpoint did not return any results.") 
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
                self._print_log_msg("debug",f"command_line - cli_minority_fork_detection - [{caller}] - profile [{profile}] | retrieving localhost: [{fork_obj['lookup_uri']}].")
                global_ordinals["local"] = self.functions.get_snapshot(fork_obj)
                if global_ordinals["local"] is None: 
                    self._print_log_msg("error","check_minority_fork -> local api endpoint did not return any results.") 
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
                ["Currently, nodes participating in layer1 clusters do not participate in consensus rounds.",2,"red"],
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
                if self.functions.cancel_event: 
                    exit("  Event Canceled")
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
                        "profile": profile,
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
                        
                    self._print_log_msg("debug",f"cli_check_consensus -> caller [{caller}] -> participating in consensus rounds [{consensus_match}]")
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
                    if self.functions.cancel_event: 
                        exit("  Event Canceled")
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
        try:
            _ = socket.has_ipv6 and path.exists("/proc/net/if_inet6")
        except Exception:
            self.functions.print_paragraphs([
                ["You must have the Debian",0,"red"], ["IPv6",0,"yellow"], ["module installed",0,"red"],
                ["to utilize this feature",2,"red"]
            ])
            exit(colored("  No IPv6 module found","red"))

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
        self.functions.print_paragraphs([
            ["See",0],["help",0,"yellow"],["for more information on this command.",1]
        ])

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
        self._print_log_msg("info","passwd12 command called by user")
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
            ["file will be placed in the following node VPS location.",1],
            ["directory:",0], [self.functions.config_obj[profile]["directory_backups"],2,"yellow","bold"]
        ])

        if self.functions.confirm_action({
            "yes_no_default": "n",
            "return_on": "n",
            "prompt": "Are you sure you want to change the p12 passphrase?",
            "exit_if": False
        }):
            self._print_log_msg("info",f"request to change p12 cancelled.")
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
            
            self._print_log_msg("error",f"User entered invalid p12 [name] or [location] options")
            
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
                        
                self._print_log_msg("error",f"{verb} entered passphrase did not match, had a length issue, or did not have proper restrictions.")
                
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
            self._print_log_msg("info",f"Successfully changed p12 passphrase.")
            status = "successful"
            color = "green"
            self.functions.print_paragraphs([
                ["",1], [f"The passphrase for",0,"green"], [p12_key_name,0,"white","bold"],
                ["was successfully changed.  Please update your configuration.",1,"green"],
                ["command:",0], ["sudo nodectl configure",2,"blue","bold"]
            ])
        else:
            self._print_log_msg("error",f"P12 Passphrase change failed | {result}.")
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

        status, status_color = "complete", "green"
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
                    self._print_log_msg("error",is_error)
                    status, status_color = "error", "red"
                elif creation_time > newest_time:
                    newest_time, newest_snapshot = creation_time, file_path

            self.functions.status_dots = False
            self.functions.print_cmd_status({
                **status_obj,
                "status": status,
                "status_color": status_color,
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
        self._print_log_msg("info","display_snapshot_chain initiated.")

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
                ["This feature can lead to unpredictable and undesired affects on your existing node.",2,"red"],
                ["nodectl will take your node offline first.",2],
            ])

        self.functions.print_paragraphs([
            ["To prevent",0,"blue","bold"], ["false-negatives",0,"red"], 
            ["nodectl will take your node offline first.",2,"blue","bold"],
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

        self._print_log_msg("info","display_snapshot_chain --fix option detected.")

        old_days = -1
        if fix and "--days" in command_list:
            old_days = command_list[command_list.index("--days")+1]
            self._print_log_msg("info",f"display_snapshot_chain remove old snapshots requested [{old_days} days].")
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
            ["Tessellation, which is the",0], ["definitive authority",0,"green","bold"], ["for verifying a node's",0],
            ["validity. Therefore, this feature uses the term",0],
            ["'in order'",0,"green"], ["instead of",0], ["'valid'.",0,"green"], ["According to the organization, based",0],
            ["on the pairing of ordinals to hashes and the last known snapshot age, nodectl considers whether or not",0],
            ["the node to be in proper order.",2],

            ["If your node reaches",0], ["WaitingForDownload",0,"red"], ["and this command indicates that",0],
            ["the chain on this node is",0], ["'in order',",0,"green"], ["it only means that the chain elements",0],
            ["appear to be correctly aligned.",2],
            
            ["For a definitive assessment of the node's snapshot DAG chain, nodectl would need to replicate",0],
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

        if "--full-report" in command_list:
            np = True if "--np" in command_list else False
            print_full_snapshot_report(
                merged_dict, count_results["length_of_files"],
                get_terminal_size(), self.functions, np, self.log
            )
        if "--json-output" in command_list:
            output_to_file(merged_dict,command_list, self.functions, self.log)

        if not fix:
            print("")
            return

        if count_results["length_of_files"] < 1:
            self.functions.print_paragraphs([
                ["",1],[" WARNING ",0,"yellow,on_red"], 
                ["nodectl was unable to find any ordinal, snapshot, or hash history on this node?",2,"red"],
                ["In most cases, this indicates that the node is either new or has never participated",0],
                ["on the configured cluster.",2],
                ["nodectl will now exit.",2,"blue","bold"],
            ])
            return
        
        if count_results["solo_count"] < 1:
            self.functions.print_paragraphs([
                ["",1],[" IN ORDER ",0,"blue,on_green"], 
                ["This node's snapshot inventory is in order and does not need any further action.",0,"green"],
                ["nodectl will quit with no action.",2,"green"],

                ["If your node is reaching the",0], ["WaitingForDownload",0,"red"], ["state, the node may have an",0],
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
            ["to return your node to operational status.",2],
        ])


    def cli_execute_starchiver(self,command_list):
        self._print_log_msg("info","execute_starchiver initiated.")
        self.functions.check_for_help(command_list,"execute_starchiver")

        empty_params = False
        
        def set_key_pairs():
            executable = self.config_obj["global_elements"]["starchiver"]["executable"]
            local_path = self.config_obj["global_elements"]["starchiver"]["local_dir"]+executable
            repo = self.config_obj["global_elements"]["starchiver"]["remote_uri"]+executable
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

        try:
            local_path, repo = set_key_pairs()
        except:
            self.functions.get_includes("remote_only")
            try:
                local_path, repo = set_key_pairs()
            except:
                send_error("make sure you have the proper include file in the includes directory [/var/tessellation/nodectl/includes/].")

        print("")
        self.functions.print_header_title({
            "line1": "COMMUNITY STARCHIVER",
            "single_line": True,
            "newline": "both",
        })
        
        local_path = self.functions.cleaner(local_path,"double_slash")

        if all(v == "empty" for v in command_list):
            bashCommand = local_path
            profile = "missing"
            cluster = "missing"
            
            self.functions.print_clear_line()
            self.functions.print_paragraphs([
                [" WARNING ",0,"red,on_yellow"], ["No parameters were detected",1,"yellow"],
            ])

            self.functions.confirm_action({
                "yes_no_default": "n",
                "return_on": "y",
                "prompt_color": "magenta",
                "prompt": f"Execute the starchiver script with empty paraemters?",
                "exit_if": True,
            }) 
            
            empty_params = True
             
        if not empty_params:  
            if "--default" in command_list:
                profile = self.profile_names[0]
            else:
                profile = command_list[command_list.index("-p")+1]
                
            if profile not in self.functions.profile_names:
                send_error(f"is this a valid profile? [{profile}]")
                
            data_path = f"/var/tessellation/{profile}/data"
            cluster = self.config_obj[profile]["environment"]
        
            self.functions.print_paragraphs([
                [" WARNING ",0,"red,on_yellow"], ["This will execute the starchiver external community",0],
                ["supported script.",2],
                ["USE AT YOUR OWN RISK!",1,"red","bold"], 
                ["The",0], ["starchiver",0,"yellow"], 
                ["script is not supported by Constellation Network; however,",0],
                ["it is a useful script included in nodectl's tool set to help expedite a node's ability to",0],
                ["join the Constellation Network cluster of choice.",1],
                ["This will be executed on:",0,"blue","bold"],[self.config_obj[profile]['environment'],1,"yellow"],
                [f"{self.config_obj[profile]['environment']} cluster profile:",0,"blue","bold"],[profile,2,"yellow"],
            ])
            
            bashCommand = f"{local_path} --data-path '{data_path}' --cluster '{cluster}'"

            if "--default" in command_list:
                bashCommand += " --datetime -d --cleanup"
            elif "--upload" in command_list:
                if path.isfile(command_list[command_list.index("--datetime")+1]):
                    bashCommand += f' --upload {command_list[command_list.index("--datetime")+1]}'
                else:
                    send_error(f"invalid path or file")
            else: 
                if "--datetime" in command_list:  
                    sc_date = command_list[command_list.index("--datetime")+1]
                    
                    if sc_date.isdigit() and len(sc_date) == 10:
                        bashCommand += f" --datetime {sc_date}"
                    else:
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

                if "-d" in command_list: bashCommand += " -d"
                elif "-o" in command_list: bashCommand += " -o"
                
                if "--cleanup" in command_list: bashCommand += " --cleanup"
                elif "--nocleanup" in command_list: bashCommand += " --nocleanup"
                elif "--onlycleanup" in command_list: bashCommand += " --onlycleanup"

        self._print_log_msg("debug",f"execute_starchiver -> executing starchiver | profile [{profile}] | cluster [{cluster}] | command referenced [{bashCommand}]")

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

        self.functions.print_cmd_status({
            "text_start": "Remove existing starchiver scripts",
            "status": "running",
            "status_color": "yellow",
            "newline": False,
        })
        sleep(.5)
        self._print_log_msg("debug","execute_starchiver -> removing existing starchiver if exists.")
        try:
            remove(local_path)
        except:
            self._print_log_msg("debug","execute_starchiver -> did not find an existing starchiver script.")
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
        self._print_log_msg("debug",f"execute_starchiver -> fetching starchiver -> [{repo}] -> [{local_path}]")
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
        self._print_log_msg("debug",f"execute_starchiver -> changing starchiver permissions to +x -> [/var/tmp/starchiver]")
        chmod(local_path, 0o755)
        self.functions.print_cmd_status({
            "text_start": "Setting starchiver permissions",
            "status": "complete",
            "status_color": "green",
            "newline": True,
        })

        if empty_params:
            self.functions.print_paragraphs([
                ["Skipping nodectl cluster removal commands because no parameters were set by the Node Operator so",0,"yellow"],
                ["nodectl",0], ["is unable to determine profile or environment to shutdown",0,"yellow"],                            
            ])
            sleep(1.5)
        else:
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
        if ("--restart" in self.command_list or "--default" in self.command_list) and not empty_params:
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
                ["the longer it will take for your node to download the additional snapshots, complete acquisition of the",0,"magenta"],
                ["full chain, and join consensus.",2,"magenta"],
                
                ["If",0,"green"],["auto_restart",0,"yellow","bold"], ["is enabled on this node, if will restart the",0,"green"],
                ["service automatically for you.",1,"green"],
            ])


    def cli_execute_tests(self,command_list):
        self._print_log_msg("info","execute_tests initiated.")
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
        self._print_log_msg("debug","execute_tests -> removing existing test script if exists.")
        try:
            remove("/usr/local/bin/nodectl_tests_x86_64")
        except:
            self._print_log_msg("debug","execute_tests -> did not find an existing user tests script.")
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
        self._print_log_msg("debug",f"execute_tests -> fetching Node Operator tests -> [{repo}] to [{local_path}]")
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
        self._print_log_msg("debug",f"execute_tests -> changing Node Operator tests permissions to +x -> [{local_path}]")
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
            self._print_log_msg("error",f"execute_tests -> binary file size too small, may not exist [{path.getsize(local_path)}]")
            self.functions.print_paragraphs([
                ["Unable to properly download the necessary binary containing the",0,"red"],
                ["unit tests",0,"yellow"], ["script. It may not have been released for this",0,"red"],
                ["version of",0,"red"], ["nodectl?",0,"yellow"], ["Please refer to the repository to make sure",0,"red"],
                ["the binary is present.",2,"red"]
            ])
            exit(0)
        self._print_log_msg("debug",f"execute_tests -> executing Node Operator tests | command referenced [{bashCommand}]")
        _ = self.functions.process_command({
            "bashCommand": bashCommand,
            "proc_action": "subprocess_run",
        })        


    def cli_execute_directory_restructure(self, profile_argv,version=False,non_interactive=False,new_install=False):
        profile_error = False
        profile = None
        executor0, executor1, executor2, executor3, executor4 = False, False, False, False, False
        already_started_migration = False

        forced = False
        if "--force" in profile_argv:
            self._print_log_msg("warning","execute_directory_restructure -> data migration request with [--force] detected and will ignore fail safes.")
            forced = True

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
                self._print_log_msg("error",f"cli_execute_directory_restructure -> unable to determine versioning -> error [{e}]")
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
        elif not forced and env != "testnet" and "v3" != version[:2]:
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
            dir_error_show = False
            if self.auto_restart: return False
            if not new_install:
                self.functions.print_paragraphs([
                    ["*","half","blue","bold"],
                    [" WARNING ",0,"red,on_yellow"], ["The nodectl utility was",0,"yellow"], 
                    ["unable to determine the proper directory structure",0,"red"],
                    ["required to complete a possibly needed data migration.",2,"yellow"],

                    ["It is also",0,"magenta"], ["unable to verify",0,"red"], ["if this is a",0,"magenta"],
                    ["new installation?",2,"magenta"],

                    ["If this is not a brand-new installation it is not recommended to proceed.",0,"red"],
                    ["Continuing the upgrade may corrupt the node's snapshot chain",0,"red"],
                    ["and render it",0,"red"], ["invalid,",0,"red","bold"], ["requiring a full",0,"red"],
                    ["reinitialization from genesis.",2,"red"],

                    ["Please confirm your node’s status before proceeding. If unsure, seek guidance",0,"yellow"],
                    ["to avoid data loss or extended downtime.",2,"yellow"],
                ])
                if non_interactive:
                    dir_error_show = True
                if not self.functions.confirm_action({
                        "yes_no_default": "n",
                        "return_on": "y",
                        "prompt": "Is this a NEW installation?",
                        "prompt_color": "green",
                        "exit_if": False,
                    }):
                    dir_error_show = True

                if dir_error_show:
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

            self._print_log_msg("info",f"execute_directory_restructure -> testing for migration requirement")

            if path.isdir(f"{data_dir}/hash") and path.isdir(f"{data_dir}/ordinal") and not forced:
                already_started_migration = True
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

        if forced:
            self.functions.print_paragraphs([
                ["",1],[" FORCED ",0,"red,on_yellow"], ["A new data directory structure has already",0,"yellow"],
                ["been detected on this node, but",0,"yellow"], ["--force",0,"red"],
                ["was detected. If you have previously attempted the migration and the process",0,"yellow"],
                ["did not fully complete,",0,"magenta"], ["it should be safe to continue from this point.",1,"yellow"],
            ])
            _ = self.functions.confirm_action({
                "yes_no_default": "n",
                "return_on": "y",
                "prompt": "Continue with Migration?",
                "prompt_color": "cyan",
                "exit_if": True,
            })
        elif r_status == "skipping": 
            self._print_log_msg("info","execute_directory_restructure -> found this process is not needed -> skipping")
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
                self._print_log_msg("info",f"execute_directory_restructure -> {item[0]}: [{item[1]}]")
                self.functions.print_cmd_status({
                    "text_start": "Found",
                    "brackets": item[0],
                    "status": item[1],
                    "status_color": "grey",
                    "newline": True,
                })

        if (brand == "AuthenticIntel" or brand == "GenuineIntel") and arch.upper() == "X86_64":
            amd = True

        self._print_log_msg("info",f"execute_directory_restructure -> migration requirement detected, starting migration.")
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

            self._print_log_msg("info",f"execute_directory_restructure -> fetching migration tool -> [{repo}] -> [{local_path}]")
            for n in range(0,4):
                try:
                    self.functions.download_file({
                        "url": repo,
                        "local": local_path,
                    })
                except Exception as e:
                    if n > 2: 
                        self._print_log_msg("critical",f"execute_directory_restructure -> fetching migration tool FAILED 3x -> [{repo}] -> [{local_path}]")
                        return False
                    self._print_log_msg("error",f"execute_directory_restructure -> fetching migration tool FAILED -> [{repo}] -> [{local_path}]")
                else:
                    self._print_log_msg("info",f"execute_directory_restructure -> fetching migration tool SUCCESS -> [{repo}] -> [{local_path}]")
                    break

            sleep(.5)
            self._print_log_msg("debug",f"execute_directory_restructure -> changing permissions to +x -> [{local_path}]")
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
                ["may take more than few minutes to complete. Please exercise patience while this",0,"yellow"],
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
            self._print_log_msg("info",f"execute_directory_restructure -> executing migration tool -> [{bashCommand}]")
            result = 1

            for n in range(1,4):
                try:
                    result = self.functions.process_command({
                        "bashCommand": bashCommand,
                        "proc_action": "subprocess_run_check_only",
                    })
                    result = result.returncode
                except Exception as e:
                    self._print_log_msg("error",f"execute_directory_restructure -> executing migration tool | attempt [{n}] of [3] | error [{e}]")
                else:
                    if result < 1: break
                    self._print_log_msg("error",f"execute_directory_restructure -> executing migration tool did not return successful completion. | attempt [{n}] of [3] | error [{result}]")

            status_result = "complete"
            status_color = "green"
            if result < 1:
                self._print_log_msg("info",f"execute_directory_restructure -> executing migration tool -> completed [success]")
            else:
                self._print_log_msg("error",f"execute_directory_restructure -> executing migration tool -> [failed] with error code [{result}]")
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

        c_result = self.functions.remove_files({
            "file_or_list": local_path,
            "caller": "cli_execute_directory_restructure"
        })
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
                ["This will allow temporary access to your VPS and node by an external entity",0,"red","bold"],
                ["In order to administer your node this remote access will have",0,"red"],
                ["sudo",0,"yellow"], ["rights to your VPS which will offer unfettered access to your node",0,"red","bold"],
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
                self._print_log_msg("error",f"prepare_file_download -> profile [{profile}] not found.")
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
                self._print_log_msg("error",f"prepare_file_download -> unable to find requested file [{file}]")
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
                ["has the possibility",0,"red"],["of causing a",0],["a minor security risk,",0,"red"],["on your node.",2],

                [f"This command will create a copy of the requested file",0,"magenta"],
                [file,0,"yellow"], ["in the root of a non-root user's home directory,",0,"magenta"],
                ["and set the permissions for access via a",0,"magenta"], ["non-root",0,"red","bold"], ["user until removed.",2,"magenta"],

                [f"Once you have completed the backup of your file",0,"green"],
                [file,0,"yellow"],["it is",0,"green"],
                ["recommended",0,"green","bold"], ["that you return to your node and re-run",0,"green"],
                ["this command with the",0,"green"], ["--cleanup",0,"yellow"], ["option, to remove and",0,"green"],
                ["secure your node's nodeadmin user from accessing root files.",2,"green"],
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
                ["create a minor security risk,",0,"red"],["on your node.",2],

                ["This command will create copies of your known p12 files, place them into a non-root",0,"magenta"],
                ["user's home directory, and change the",0,"magenta"],
                ["permissions for access via a",0,"magenta"], ["non-root",0,"red","bold"], ["user until removed.",2,"magenta"],

                ["Once you have completed the backup of your p12 keystore files, it is",0,"green"],
                ["very",0,"green","bold"], ["important that you return to your node and re-run",0,"green"],
                ["this command with the",0,"green"], ["--cleanup",0,"yellow"], ["option, to remove and",0,"green"],
                ["secure your node's p12 access to proper status.",2,"green"],
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
                    self._print_log_msg("error",f"prepare_file_download -> file copy error [{e}]")
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


    def cli_rotate_keys(self,command_list):
        self.functions.check_for_help(command_list,"rotate_keys")
        config_encryption_enabled, alert_encryption_enabled = False, False
        rotate_profiles, rotate_profiles_errors = [],[]

        from .config.configurator import Configurator
        configurator = Configurator(["--upgrader"])
        configurator.detailed = True
        configurator.action = "rotation"
        configurator.metagraph_list = self.functions.profile_names
        configurator.c.config_obj = deepcopy(self.config_obj)
        configurator.c.functions.config_obj = deepcopy(self.config_obj)
        _, _, effp = configurator.build_encryption_path()

        try:
            alert_encryption_enabled = self.config_obj["global_elements"]["alerting"]["enable"]       
        except:
            alert_encryption_enabled = False 

        if self.config_obj["global_p12"]["encryption"]:
            config_encryption_enabled = True

            
        if not config_encryption_enabled and not alert_encryption_enabled:
            cprint("  Encryption is not enabled, terminating","red")
            exit(0)

        self.functions.print_header_title({
            "line1": "NODECTL SECURITY KEY ROTATAION",
            "single_line": True,
            "newline": "both",
        })

        self.functions.print_paragraphs([
            [" WARNING ",0,"yellow,on_red"], ["This is a security feature that will attempt to",0,"magenta"],
            ["rotate your security keys for all detected profiles on this node.",2,"magenta"],
            
            ["Once completed, it is advised to:",1],
            ["  - Issue a command that may require your passphrase to continue.",1],
            ["    Example:",0,"blue","bold"], ["sudo nodectl status",1,"yellow"],
            ["  - If alerting is enabled, send an alert test.",1],
            ["    Example:",0,"blue","bold"], ["sudo nodectl auto_restart alert_test",1,"yellow"],
            ["  - If any of the above tests fail, please use the configurator to reset your passphrases",1],
            ["    Command:",0,"blue","bold"], ["sudo nodectl configure -e",2,"yellow"],

            [" IMPORTANT ",0,"yellow,on_red"], ["If a profile or alerting is disabled, the associated",0,"red"],
            ["key will not be rotated.",2,"red"],
        ])

        self.functions.confirm_action({
            "yes_no_default": "n",
            "return_on": "y",
            "prompt_color": "magenta",
            "prompt": f"Begin key rotation?",
            "exit_if": True,
        })

        if config_encryption_enabled:
            rotate_profiles.append(("global_p12",self.config_obj["global_p12"]["passphrase"]))
            for profile in self.profile_names:
                if not self.config_obj[profile]["global_p12_passphrase"]:
                    rotate_profiles.append((profile,self.config_obj[profile]["p12_passphrase"]))

        if alert_encryption_enabled:
            rotate_profiles.append(("alerting",self.config_obj["global_elements"]["alerting"]["token"]))


        for profile, pass_hash in rotate_profiles:
            replace_line, cn_config_path = " "," "

            with ThreadPoolExecutor() as executor:
                self.functions.status_dots = True
                status_obj = {
                    "text_start": "Rotating key",
                    "brackets": profile if profile != "global_p12" else "global",
                    "status": "running",
                    "status_color": "yellow",
                    "dotted_animation": True,
                    "newline": False,
                }
                _ = executor.submit(self.functions.print_cmd_status,status_obj)
                
                error = False
                for atp in range(0,3):
                    pass1 = self.functions.get_persist_hash({
                        "pass1": pass_hash,
                        "profile": profile,
                        "enc_data": True,
                        "test_only": True,
                    })
                    sleep(1)
                    new_hash, pass2 = configurator.perform_encryption(profile,{},effp,pass1,"rotation")
                    if pass1 == str(pass2):
                        break
                    if atp > 1:
                        error = True
                        break
                    sleep(1.5)
                
                if error:
                    self._print_log_msg("error","rotate_key error was encountered during key rotation, advised to manually reset passphrase encryption and alerting if enabled.")
                    rotate_profiles_errors.append(profile)
                    self.functions.status_dots = False
                    continue
                    
                cn_config_path = path.normpath(f"{self.functions.nodectl_path}cn-config.yaml")
                replace_line = f'    p12_passphrase: "{new_hash}"\n'
                if profile == "global_p12":
                    replace_line = replace_line.replace("p12_passphrase","passphrase")
                elif profile == "alerting":
                    cn_config_path = path.normpath(f"{self.functions.default_includes_path}alerting.yaml")
                    replace_line = f"  token: '{new_hash}'\n"

                self.functions.test_or_replace_line_in_file({
                    "file_path": cn_config_path,
                    "search_line": pass_hash,
                    "replace_line": replace_line,
                    "start_after_string": profile,
                    "allow_dups": False,
                })
            
                sleep(1.5)
                self.functions.status_dots = False
                self.functions.print_cmd_status({
                    **status_obj,
                    "dotted_animation": False,
                    "status": "complete",
                    "status_color": "green",
                    "newline": True,
                })

        rot_status, rot_color = "complete", "green"
        if len(rotate_profiles_errors) > 0:
            self.functions.print_paragraphs([
                [" ERROR ",0,"yellow,on_red"],
                ["The rotation process has failed, please update your configuration as explained above.",1,"magenta"],
            ])
            for profile in rotate_profiles_errors:
                self.functions.print_paragraphs([
                    ["Profile:",0,"red","bold"], [profile,0,"yellow"],["failed key rotation attempt.",1,"red"]
                ])
            rot_status, rot_color = "incomplete", "red"
            if len(rotate_profiles_errors) == len(rotate_profiles):
                rot_status = "failed"
            print(" ")

        self.functions.print_cmd_status({
            "text_start": "Key rotating request",
            "status": rot_status,
            "status_color": rot_color,
            "newline": True,
        })


    def clean_files(self,command_obj):
        what = "clear_snapshots" if command_obj["action"] == "snapshots" else "clean_files"
        self._print_log_msg("info",f"request to {what} inventory by Operator...")
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

        self._print_log_msg("info",f"SSH port configuration change initiated | command [{command}]")
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
                self._print_log_msg("error",f"SSH Configuration terminated due to invalid or missing port [{port_no}]")
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
                    ["This feature will change the port number used to access this node via the Secure Shell Protocol!",1],
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
                self._print_log_msg("warning",f"backup dir did not exist, attempting to create [{backup_dir}]")
                makedirs(backup_dir)

            self._print_log_msg("info",f"creating a backup of the sshd.config file to [{backup_dir}]")
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
                                    self._print_log_msg("info",f"found and recovered {user} authorized_keys file")
                                else:
                                    found_errors = f"auth_not_found {user}"
                                    self._print_log_msg("critical",f"could not find a backup authorized_key file to recover | user {user}")
                            elif action == "disable":
                                verb = "no"
                                if path.isfile(f"{upath}.ssh/authorized_keys"):
                                    move(f"{upath}.ssh/authorized_keys",f"{upath}.ssh/backup_authorized_keys")
                                    self._print_log_msg("warning",f"found and renamed authorized_keys file | user {user}")
                                else:
                                    self._print_log_msg("critical",f"could not find an authorized_key file to update | {user}")
                            if user == "root":
                                self._print_log_msg("warning",f"setting PermitRootLogin to [{verb}] | user [{user}]")
                                newfile.write(f"PermitRootLogin {verb}\n")
                            else:
                                newfile.write(f"{line}")
                        else:
                            newfile.write(f"{line}")
                        action_print = f"{action} {user} user"
                        
                    elif action == "disable_user_auth":
                        if line.startswith("PubkeyAuthentication") or line.startswith("#PubkeyAuthentication"):
                            self._print_log_msg("warning",f"found and enabled PubkeyAuthentication for SSH protocol daemon | sshd_config")
                            newfile.write(f"PubkeyAuthentication yes\n")
                        elif line.startswith("PasswordAuthentication") or line.startswith("#PasswordAuthentication"):
                            self._print_log_msg("warning",f"found and disabled PasswordAuthentication for SSH protocol daemon | sshd_config")
                            newfile.write(f"PasswordAuthentication no\n")
                        elif line.startswith("KbdInteractiveAuthentication") or line.startswith("#KbdInteractiveAuthentication"):
                            self._print_log_msg("warning",f"found and disabled KbdInteractiveAuthentication for SSH protocol daemon | sshd_config")
                            newfile.write(f"KbdInteractiveAuthentication no\n")
                        elif line.startswith("ChallengeResponseAuthentication") or line.startswith("#ChallengeResponseAuthentication"):
                            self._print_log_msg("warning",f"found and disabled ChallengeResponseAuthentication for SSH protocol daemon | sshd_config")
                            newfile.write(f"ChallengeResponseAuthentication no\n")
                        else:
                            newfile.write(f"{line}")
                        
                    elif action == "port":
                        action_print = action
                        if not "GatewayPorts" in line and (line.startswith("Port") or line.startswith("#Port")):
                            self._print_log_msg("warning",f"found and updated the Port settings for SSH protocol daemon | sshd_config")
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
                                self._print_log_msg("warning",f"found and disabled PasswordAuthentication for SSH protocol daemon | 50-cloud-init.conf")
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
            self._print_log_msg("info",f"moving modified sshd_config into place.")
            if one_off:
                self._print_log_msg("info",f"found one-off [50-cloud-init-config] moving modified sshd config file into place.")
                if path.isfile("/tmp/sshd_config-new2"):
                    move("/tmp/sshd_config-new2","/etc/ssh/sshd_config.d/50-cloud-init.conf")
                
            sleep(1)
            self._print_log_msg("info",f"restarted sshd service.")
            _ = self.functions.process_command({
                "bashCommand": "service sshd restart",
                "proc_action": "subprocess_devnull",
            })

            self._print_log_msg("info",f"SSH port configuration change successfully implemented [{action_print}]")
            if one_off:
                self._print_log_msg("info",f"SSH configuration for an include file [one off] has been updated with password authentication [{verb}]")
                
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
        if "scrap" in command_list: 
            self.send = send
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
        self._print_log_msg("info","command_line --> backup configuration")
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


    def delegated_staking(self,command_list):
        self.functions.check_for_help(command_list,self.command_obj["command"])
        self.functions.print_header_title({
            "line1": "DELEGATED STAKING",
            "newline": False
        })

        try: 
            _ = self.config_obj["global_elements"]["delegated_staking"]
        except:
            self.error_messages.error_code_messages({
                "line_code": "config_error",
                "error_code": "cli-7519",
                "extra": "includes",
                "extra2": "You must create a delegated staking configuaration first."
            })        

        profiles = self.functions.pull_profile({
            "req": "layer0",
        })

        if len(profiles) < 1:
            self.error_messages.error_code_messages({
                "line_code": "layer_zero_missing",
                "error_code": "cli-7529",
                "extra": ', '.join(self.profile_names)
            })

        profile = profiles[0] # default
        if len(profiles) > 1:
            self.functions.print_paragraphs([
                ["Please chooose a layer0 profile associated with your delegated staking configuration:",2]
            ])
            profile = self.functions.print_option_menu({
                    "options": profiles,
                    "return_value": True,
                    "color": "blue",
                    "r_and_q": "both",
                })

        if "update" in command_list:
            action = "update"
        elif "remove" in command_list:
            action = "remove"
        elif "status" in command_list:
            action = "status"
        else:
            action = self.functions.print_option_menu({
                    "options": ["status","update","remove"],
                    "return_value": True,
                    "color": "blue",
                    "r_and_q": "q",
                })  
            print("")          

        delegated = DelegatedStaking({
            "profile": profile,
            "action": action,
            "config_obj": self.config_obj,
            "functions": self.functions,
            "log": self.log,
            "error_messages": self.error_messages
        })

        if "--verbose" in command_list or "-v" in command_list:
            delegated.verbose = True
        if "--vv" in command_list:
            delegated.verbose = True
            delegated.dbl_verbose = True

        if action == "update":
            delegated.update()
        elif action == "remove":
            delegated.remove()
        elif action == "status":
            delegated.status()
            

    def sign(self,command_list):
        self.functions.check_for_help(command_list,self.command_obj["command"])
        signed_input_path, signed_output_path = False, False
        error = False

        sign_parms = {
            "input_json": False,
            "output_json": False,
            "private_key": False,
            "public_key": False,
            "output_json": "stdout",
            "package": False,
        }

        if "--input-json" in command_list:
            signed_input_path = command_list[command_list.index("--input-json")+1]
            signed_input_path = path.normpath(signed_input_path)
            try:
                check_path = path.basename(signed_input_path)
            except: pass
            self.functions.check_file_dir_exits({
                "check_path": check_path,
                "return_on": "n",
                "negative": True,
                "always_exit": True,
            })
            sign_parms["input_json"] = signed_input_path

        if "--output-json" in command_list:
            signed_output_file = command_list[command_list.index("--output-json")+1]
            signed_output_path = path.normpath(f"{self.functions.default_upload_location}/{signed_output_file}")
            self.functions.check_file_dir_exists({
                "check_path": signed_output_path,
            })
            sign_parms["output_json"] = signed_output_file

        for key_option in ["private-key","public-key"]:
            if key_option in command_list:
                key_file = command_list[command_list.index(f"--{key_option}-path")+1]
                self.functions.check_file_dir_exists({
                    "check_path": key_file,
                    "always_exit": True,
                    "negative": True,
                })
                sign_parms[f"{key_option}"] = key_file

        if "--stdin" in command_list:
            ingest_data = command_list[command_list.index("--stdin")+1]
            try:
                ingest_data = json.loads(ingest_data)
            except Exception as e:
                self.log.logger["log_key"].error(f"sign feature was Unable to validate the JSON object from stdin [{e}]")
                error = True
        else:
            if not sign_parms["input_json"]:
                error = True

        if error:
            self.error_messages.error_code_messages({
                "line_code": "invalid_data",
                "error_code": "cli-7618",
            }) 

        sign_obj = {
            "log": self.log,
            "config_obj": self.config_obj,
            "error_mesages": self.error_messages
        }
        if sign_parms["input_json"]: sign_obj["data"] = sign_parms["input_json"]
        if sign_parms["private_key"]: sign_obj["private_path"] = sign_parms["private_key"]
        if sign_parms["public_key"]: sign_obj["public_path"] = sign_parms["public_key"]
        signer = NodeCtlCryptoClass(sign_obj)

        p_type = "node p12 key store"
        if sign_parms["private_key"]:
            p_type = "private key"
        sign_obj["p12p"] = getpass(colored(f"  Please enter your {p_type} passphrase: ","magenta"))


        if sign_parms["output_json"] == "stdout":
            self.functions.print_paragraphs([
                ["",1],
                ["*","half","green","bold"],
                ["** SIGNED JSON START **",1,"white"],
                ["*","half","green","bold"],
            ])
            print(colored(json.dumps(signer.data,indent=4),"light_yellow"),end="\n")
            self.functions.print_paragraphs([
                ["*","half","green","bold"],
                ["** SIGNED JSON END **",1,"white"],
                ["*","half","green","bold"],
            ]) 
            exit(0)                   

        with open(sign_parms["output_json"],"w") as f:
            f.write(json.dumps(signer.data))
            self.functions.print_paragraphs([
                ["JSON data has been signed and placed in requested output file."],
                ["Output File",0,"blue","bold"], [sign_parms["output_json"],2,"yellow"],
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
        plus_twenty_four = False
        try:
            if float(self.functions.get_distro_details()["release"]) > 24:
                plus_twenty_four = True
        except:
            pass
        
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
                self._print_log_msg("critical",f"unable to determine environment type [{environment_name}]")
            except:
                self._print_log_msg("critical",f"unable to determine environment type [unknown]")
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
                ["attempt",0,"red","bold"], ["to upgrade/downgrade your node's nodectl version to:",0], [custom_version,2,"yellow","bold"],
                ["If you decide to downgrade to a version that meets or falls below the upgrade path requirements",0,"red"],
                ["for nodectl, you might encounter unexpected consequences that could make your node unmanageable. In these",0,"red"],
                ["situations, it is advisable to re-create the node and perform a clean installation.",2,"red"],
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

        self._print_log_msg("info",f"Upgrade request for nodectl for [{environment_name}] using first profile [{profile}].")

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
            self._print_log_msg("error",f"Upgrade nodectl to new version request not needed {node_nodectl_version}.")
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

        arch = self.arch
        if plus_twenty_four:
            arch = f"{self.arch}_2404"
        try:
            upgrade_file = upgrade_file.replace("NODECTL_VERSION",upgrade_chosen)
            upgrade_file = upgrade_file.replace("NODECTL_OLD",node_nodectl_version)
            upgrade_file = upgrade_file.replace("NODECTL_BACKUP",backup_location)
            upgrade_file = upgrade_file.replace("ARCH",arch)
            if version_obj["nodectl"]["upgrade"] == "full":
                upgrade_file = upgrade_file.replace("sudo nodectl upgrade --nodectl_only","sudo nodectl upgrade")
                upgrade_file = upgrade_file.replace("requires a nodectl_only","requires a full upgrade")
        except Exception as e:
            self._print_log_msg("debug",f"nodectl binary updater was unable to build the upgrade file path | upgrade chosen [{upgrade_chosen}] old [{node_nodectl_version}] backup location [{backup_location}] arch [{self.arch}] | error [{e}]")
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

            self._print_log_msg("warning",f"nodectl upgrader is restoring [{backup_location}nodectl_{node_nodectl_version}] to [/usr/local/bin/nodectl]")
            if path.isfile(f"{backup_location}nodectl_{node_nodectl_version}"):
                move(f"{backup_location}nodectl_{node_nodectl_version}","/usr/local/bin/nodectl")

            if self.functions.get_size("/usr/local/bin/nodectl",True) < 1:
                self._print_log_msg("critical",f"nodectl upgrader unable to restore [{backup_location}nodectl_{node_nodectl_version}] to [/usr/local/bin/nodectl]")
                self.functions.print_paragraphs([
                    [" WARNING ",0,"red,on_yellow"], ["unable to restore original nodectl, please manually download via",0,"red"],
                    ["the known",0,"red"], ["wget",0,"yellow"], ["command. See Constellation Network documentation hub for further details.",1,"red"]
                ])
        else:
            self._print_log_msg("info",f"Upgrade of nodectl to new version successfully completed")
        
        return_value = False
        if path.isfile("/var/tessellation/nodectl/cnng_upgrade_results.txt"):
            with open("/var/tessellation/nodectl/cnng_upgrade_results.txt","r") as f:
                return_value = f.read().strip()
            remove("/var/tessellation/nodectl/cnng_upgrade_results.txt")

        try: 
            remove("/var/tmp/upgrade-nodectl")
            self._print_log_msg("info","upgrade_nodectl files cleaned up successfully.")
        except Exception as e:
            self._print_log_msg("error",f"upgrade_nodectl nodectl method unable to clean up files : error [{e}]")
            
        if "return_caller" in argv_list: 
            if "mobile" in argv_list: return ["mobile","return_caller"]
            return "return_caller"
        return return_value if return_value else 0

                    
    # ==========================================
    # print commands
    # ==========================================

    def print_title(self,line,newline="both"):
        self.functions.print_header_title({
            "line1": line,
            "single_line": True,
            "newline": newline,
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
        self._print_log_msg("error",f"[{var.command}] requested --> removed for [{new_command}]")
        self.functions.print_paragraphs([
            ["",],[f" WARNING ",0,"white,on_red","bold"], ["requested feature has been",0,"red"], ["removed",0,"red","bold"],["!",1,"red"],
            ["      Feature:",0,"cyan","bold"], [var.command,1,"blue","bold"],
            ["As of version:",0,"cyan","bold"], [var.version,1,"yellow"]
        ])
        if is_new:
            self.functions.print_paragraphs([
                ["  Replacement:",0,"cyan","bold"], [new_command,2,"green","bold"],
                [help_hint,1,"magenta"]
            ])
        if done_exit:
            return 0


    def _print_log_msg(self,log_type,msg):
            log_method = getattr(self.log, log_type, None)
            log_method(f"{self.__class__.__name__} --> {msg}")
                          
if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")      
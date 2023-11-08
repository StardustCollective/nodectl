import math
import random
import json
import urllib3
import csv
import yaml
import select
import subprocess
import socket
import validators

from getpass import getuser
from re import match, sub, compile
from textwrap import TextWrapper
from requests import get
from subprocess import Popen, PIPE, call, run, check_output
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from termcolor import colored, cprint, RESET
from copy import copy, deepcopy
from time import sleep, perf_counter
from shlex import split as shlexsplit
from sshkeyboard import listen_keyboard, stop_listening
from threading import Timer
from platform import platform

from os import system, getenv, path, walk, environ, get_terminal_size, scandir
from sys import exit, stdout, stdin
from pathlib import Path
from types import SimpleNamespace
from packaging import version
from datetime import datetime
from .troubleshoot.help import build_help
from pycoingecko import CoinGeckoAPI

from .troubleshoot.errors import Error_codes
from .troubleshoot.logger import Logging

class Functions():

    def __init__(self,config_obj):
        self.sudo_rights = config_obj.get("sudo_rights", True)
        if self.sudo_rights:
            self.log = Logging()
        # set self.version_obj before calling set_statics
        self.config_obj = config_obj
        self.nodectl_path = "/var/tessellation/nodectl/"  # required here for configurator first run
        self.version_obj = False
        self.valid_commands = []
        
        
    def set_statics(self):
        self.error_messages = Error_codes(self.config_obj)         
        # versioning
        self.node_nodectl_version = self.version_obj["node_nodectl_version"]
        self.node_nodectl_version_github = self.version_obj["nodectl_github_version"]
        self.node_nodectl_yaml_version = self.version_obj["node_nodectl_yaml_version"]

        # stop requests from caching results
        self.get_headers = {
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
        urllib3.disable_warnings()

        # used for installation 
        self.lb_urls = {
            "testnet": ["l0-lb-testnet.constellationnetwork.io",443],
            "mainnet": ["l0-lb-mainnet.constellationnetwork.io",443],
            "integrationnet": ["l0-lb-integrationnet.constellationnetwork.io",443],
        }
        
        # constellation specific statics
        self.be_urls = {
            "testnet": "be-testnet.constellationnetwork.io",
            "mainnet": "be-mainnet.constellationnetwork.io",
            "integrationnet": "be-integrationnet.constellationnetwork.io",
        }
        
        # constellation nodectl statics
        self.nodectl_profiles_url = f'https://github.com/StardustCollective/nodectl/tree/{self.node_nodectl_version_github}/predefined_configs'
        self.nodectl_profiles_url_raw = f"https://raw.githubusercontent.com/StardustCollective/nodectl/{self.node_nodectl_version_github}/predefined_configs"
        
        # Tessellation reusable lists
        self.not_on_network_list = ["ReadyToJoin","Offline","Initial","ApiNotReady","SessionStarted","Initial"]
        self.our_node_id = ""
        self.join_timeout = 300 # 5 minutes

        
        try:
            self.environment_name = self.config_obj["global_elements"]["metagraph_name"]
        except:
            self.environment_name = False
            
        self.default_profile = None
        self.default_edge_point = {}
        self.link_types = ["ml0","gl0"]   
        self.environment_names = []
             
        self.event = False # used for different threading events
        self.status_dots = False # used for different threading events
        
        self.auto_restart = True if self.config_obj["global_elements"]["caller"] == "auto_restart" else False
        ignore_defaults = ["config","install","auto_restart","ts","debug"]
        if self.config_obj["global_elements"]["caller"] not in ignore_defaults: self.set_default_variables({})


    # =============================
    # getter functions
    # =============================
    def get_crypto_price(self):
        pricing_list = ["N/A","N/A","N/A","N/A","N/A","N/A"]  
        # The last element is used for balance calculations
        # It is not used by the show prices command
        
        def test_for_api_outage(coin_prices):
            try:
                coin_prices['constellation-labs']['usd']
            except:
                coin_prices['constellation-labs']['usd'] = 0.00
            
            try:
                coin_prices['lattice-token']['usd'] 
            except:
                coin_prices['lattice-token']['usd'] = 0.00
            
            try:
                coin_prices['bitcoin']['usd']
            except:
                coin_prices['bitcoin']['usd'] = 0.00
                
            try:
                coin_prices['quant-network']['usd']
            except:
                coin_prices['quant-network']['usd'] = 0.00
                
            try:
                coin_prices['quant-network']['usd']
            except:
                coin_prices['quant-network']['usd'] = 0.00
                
            return coin_prices
        
        # In the circumstance that CoinGecko is down *rare but happens*
        # This is a quick timeout check before attempting to download pricing
        
        self.create_coingecko_obj()
        
        try:
            coin_prices = self.cg.get_price(ids='constellation-labs,lattice-token,bitcoin,ethereum,quant-network', vs_currencies='usd')
        except Exception as e:
            self.log.logger.error(f"coingecko response error | {e}")
            cprint("  Unable to process CoinGecko results...","red")
        else:
            # replace pricing list properly
            coin_prices = test_for_api_outage(coin_prices)
            
            pricing_list_temp = [
            "${:,.3f}".format(coin_prices['constellation-labs']['usd']),
            "${:,.3f}".format(coin_prices['lattice-token']['usd']),
            "${:,.2f}".format(coin_prices['bitcoin']['usd']),
            "${:,.2f}".format(coin_prices['ethereum']['usd']),
            "${:,.2f}".format(coin_prices['quant-network']['usd']),
            coin_prices['constellation-labs']['usd']  # unformatted 
            ]
            
            for n, price in enumerate(pricing_list_temp):
                try:
                    price = price
                except:
                    pass
                else:
                    pricing_list[n] = price
                
        return (pricing_list)


    def get_crypto_markets(self):
        market_results = []
        market_results_cn = []
        final_results = []
        dag_top_ten = False


        with ThreadPoolExecutor() as executor:
            self.event = True
            _ = executor.submit(self.print_spinner,{
                "msg": f"Pulling Market Information, please wait",
                "color": "magenta",
            })           
                      
            self.create_coingecko_obj()

            try:
                market_results = self.cg.get_coins_markets(per_page=10, order='market_cap_desc', vs_currency='usd')
                sleep(1)
                market_results_cn = self.cg.get_coins_markets(ids="constellation-labs", order='market_cap_desc', vs_currency='usd')
            except Exception as e:
                self.log.logger.error(f"coingecko response error | {e}")
                self.event = False  
                self.print_clear_line()
                cprint("  Unable to process CoinGecko results...","red")
                return 1         
 
            self.event = False   
        
        try:
            if market_results_cn[0]["market_cap_rank"] < 11:
                dag_top_ten = True
        except:
            pass
        
        for n in range(0,2):
            if n == 1: 
                if not dag_top_ten:
                    market_results = market_results_cn
                else:
                    break
            
            for market in market_results:
                final_results.append(market)
            
        return final_results

            
    def get_peer_count(self,command_obj):
        peer_obj = command_obj.get("peer_obj",False)
        edge_obj = command_obj.get("edge_obj",False)
        profile = command_obj.get("profile",None)
        compare = command_obj.get("compare",False)
        count_only = command_obj.get("count_only",False)
        pull_node_id = command_obj.get("pull_node_id",False)
            
        if not peer_obj:
            ip_address = self.default_edge_point["host"]
            api_port = self.default_edge_point["host_port"]
        else:
            ip_address = peer_obj["ip"]  
            localhost_ports = self.pull_profile({
                "req": "ports",
                "profile": profile,
            })
            
            if peer_obj["ip"] == "127.0.0.1":
                api_port = localhost_ports["public"]
            else:
                try:
                    api_port = peer_obj["publicPort"]
                except:
                    api_port = self.get_info_from_edge_point({
                        "caller": "get_peer_count",
                        "profile": profile,
                        "desired_key": "publicPort",
                        "specific_ip": ip_address,
                    })
        
        if count_only:
            count = self.get_cluster_info_list({
                "ip_address": ip_address,
                "port": api_port,
                "api_endpoint": "/cluster/info",
                "spinner": False,
                "attempt_range": 4,
                "error_secs": 3
            })
            try:
                count = count.pop()
            except:
                pass  # skip to avoid unnecessary crash if the cluster info comes back bad during iteration
            if count:
                return(count["nodectl_found_peer_count"])
            else:
                return count
        
        peer_list = list()
        state_list = list()
        peers_publicport = list()

        peers_ready = list()        
        peers_observing = list()
        peers_waitingforready = list()
        peers_waitingforobserving = list()
        peers_downloadinprogress = list()
        peers_waitingfordownload = list()
        
        node_online = False
        node_states = self.get_node_states()
        
        def pull_states(line):
            if line["state"] == "Observing":
                peers_observing.append(line['ip'])  # count observing nodes
            elif line["state"] == "Ready":
                peers_ready.append(line['ip'])  # count ready nodes
            elif line["state"] == "WaitingForReady":
                peers_waitingforready.append(line['ip'])
            elif line["state"] == "WaitingForObserving":
                peers_waitingforobserving.append(line['ip'])
            elif line["state"] == "DownloadInProgress":
                peers_downloadinprogress.append(line['ip'])
            elif line["state"] == "WaitingForDownload":
                peers_waitingfordownload.append(line['ip'])            
                
        if compare:
            cluster_ip = ip_address
        elif not edge_obj:
            cluster_ip = edge_obj["ip"]
            api_port = edge_obj["publicPort"]
        elif edge_obj["ip"] == "127.0.0.1" or ip_address == "self":
            cluster_ip = "127.0.0.1"
            api_port = localhost_ports["public"]
        else:
            cluster_ip = edge_obj["ip"]
            try:
                api_port = edge_obj["publicPort"]
            except:
                api_port = self.get_info_from_edge_point({
                    "caller": "get_peer_count",
                    "profile": profile,
                    "desired_key": "publicPort",
                    "specific_ip": edge_obj["ip"],
                })
            
        attempts = 1
        while True:
            try:
                peers = get(f"http://{cluster_ip}:{api_port}/cluster/info",verify=False,timeout=2,headers=self.get_headers)
            except:
                if attempts > 3:
                    return "error"
                attempts = attempts+1
            else:
                break

        try:
            peers = peers.json()
        except:
            pass
        else:
            ip_address = self.ip_address if ip_address == "127.0.0.1" or ip_address == "self" else ip_address
            try:
                for line in peers:
                    if ip_address in line["ip"]:
                        if pull_node_id:
                            self.our_node_id = line['id']
                            return
                        node_online = True
                        peer_list.append(line['ip'])
                        peers_publicport.append(line['publicPort'])
                        pull_states(line)
                        state_list.append("*")
                    else:
                        # append state abbreviations
                        for state in node_states:
                            if state[0] in line["state"]:
                                pull_states(line)
                                peer_list.append(line['ip'])
                                peers_publicport.append(line['publicPort'])
                                state_list.append(state[1])
            except Exception as e:
                self.log.logger.error(f"get peer count - an error occurred attempting to review the line items on a /cluster/info api request | error [{e}]")
                pass
            
            return {
                "peer_list": peer_list,
                "peers_publicport": peers_publicport,
                "state_list": state_list,
                "observing": peers_observing,
                "waitingforready": peers_waitingforready,
                "waitingforobserving": peers_waitingforobserving,
                "waitingfordownload": peers_waitingfordownload,
                "downloadinprogress": peers_downloadinprogress,
                "ready": peers_ready,
                "peer_count": len(peer_list),
                "observing_count": len(peers_observing),
                "waitingforready_count": len(peers_waitingforready),
                "waitingforobserving_count": len(peers_waitingforobserving),
                "waitingfordownload_count": len(peers_waitingfordownload),
                "downloadinprogress_count": len(peers_downloadinprogress),
                "ready_count": len(peers_ready),
                "node_online": node_online
            }


    def get_node_states(self,types="all"):
        if types == "all":
            node_states = [
                ('Initial','i*'),
                ('ReadyToJoin','rj*'),
                ('StartingSession','ss*'),
                ('SessionStarted','s*'),
                ('ReadyToDownload','rd*'),
                ('WaitingForDownload','wd*'),
                ('DownloadInProgress','dp*'),
                ('Observing','ob*'),
                ('WaitingForReady','wr*'),
                ('WaitingForObserving','wo*'),
                ('Ready',''),
                ('Leaving','l*'),
                ('Offline','o*'),
                ('ApiNotReady','a*'),
                ('SessionIgnored','si*'),
                ('SessionNotFound','snf*'),
            ]
        elif types == "on_network":
            node_states = [
                ('Observing','ob*'),
                ('WaitingForReady','wr*'),
                ('WaitingForObserving','wo*'),
                ('Ready',''),
            ]
        elif types == "past_observing":
            node_states = [
                ('WaitingForReady','wr*'),
                ('Ready',''),
            ]            
        elif types == "ready_states":
            node_states = [
                ('ReadyToJoin','rj*'),
                ('Ready',''),
            ]            
        
                        
        return node_states
    
    
    def get_ext_ip(self):
        bashCommand = "curl -s https://ipv4.icanhazip.com/"
        
        try:
            ip = self.process_command({
                    "bashCommand": bashCommand,
                    "proc_action": "timeout"
            })
        except Exception as e:
            self.error_messages.error_code_messages({
                "error_code": "fnt-522",
                "line_code": "dependency",
                "extra": "curl",
                "extra2": e,
            })
            
        if isinstance(ip, bytes):
            ip = ip.decode('utf-8')
        try:
            ip = ip.replace("\n", "")
        except:
            ip = "unable to find"
            
        return ip
            

    def get_service_name(self,profile):
        try:
            return f"cnng-{self.config_obj[profile]['service']}"
        except:
            self.error_messages.error_code_messages({
                "error_code": "fnt-645",
                "line_code": "profile_error",
                "extra": profile,
                "extra2": None
            })            
    

    def get_service_status(self):
        # =========================
        # this needs to be migrated to node_services
        # move this to node.service
        # =========================
        self.log.logger.debug("functions [get_service_status]")
        self.config_obj["global_elements"]["node_service_status"] = {}
        
        try: _ = self.profile_names
        except: self.set_default_variables({"skip_error":True})
        
        for profile in self.profile_names:
            service_name = f"cnng-{self.config_obj[profile]['service']}"
            service_status = system(f'systemctl is-active --quiet {service_name}')
            if service_status == 0:
                self.config_obj["global_elements"]["node_service_status"][profile] = "active (running)"
            elif service_status == 768:
                self.config_obj["global_elements"]["node_service_status"][profile] = "inactive (dead)"
            else:
                self.config_obj["global_elements"]["node_service_status"][profile] = "error (exit code)"
            self.config_obj["global_elements"]["node_service_status"]["service_return_code"] = service_status   
            self.log.logger.debug(f'get_service_status -> [{profile}] -> [{service_status}] [{self.config_obj["global_elements"]["node_service_status"][profile]}]')
            
    
    def get_date_time(self,command_obj):
        action = command_obj.get("action",False)
        backward = command_obj.get("backward",True) 
        r_days = command_obj.get("days",False) # requested days
        elapsed = command_obj.get("elapsed",False)
        old_time = command_obj.get("old_time",False)
        new_time = command_obj.get("new_time",False)
        time_part = command_obj.get("time_part",False)
        format = command_obj.get("format", "%Y-%m-%d-%H:%M:%SZ")
        return_format = command_obj.get("return_format","string")
        
        if not new_time: new_time = datetime.now()
        if not old_time: old_time = datetime.now()

        if action == "date":
            return new_time.strftime("%Y-%m-%d")
        elif action == "datetime":
            return new_time.strftime("%Y-%m-%d-%H:%M:%SZ")
        elif action == "get_elapsed":
            try: old_time = datetime.strptime(old_time, "%Y-%m-%d-%H:%M:%SZ")
            except: pass # already in proper format
            return new_time - old_time
        elif action == "future_datetime":
            new_time += timedelta(seconds=elapsed)
            if return_format == "string":
                return new_time.strftime(format)
            return new_time
        elif action == "estimate_elapsed":
            total_seconds = int(elapsed.total_seconds())
            days, seconds = divmod(total_seconds, 86400) 
            hours, seconds = divmod(seconds, 3600)  
            minutes, seconds = divmod(seconds, 60)
            result = "~"
            if days > 0:
                result += f"{days}D "
            if hours > 0:
                result += f"{hours}H "
            if minutes > 0:
                result += f"{minutes}M "
            result += f"{seconds}S"
            return result
        elif action == "session_to_date":
            elapsed = elapsed/1000
            elapsed = datetime.fromtimestamp(elapsed)
            return elapsed.strftime("%Y-%m-%d-%H:%M:%SZ")
        elif action == "uptime_seconds":
            uptime_output = check_output(["uptime"]).decode("utf-8")
            uptime_parts = uptime_output.split()
            uptime_string = uptime_parts[3]
            uptime = uptime_parts[2]

            if "min" in uptime_string:
                uptime_minutes = int(uptime.split()[0])
                uptime_seconds = uptime_minutes * 60
            elif "sec" in uptime_string:
                uptime_seconds = int(uptime.split()[0])
            else:
                uptime_hours, uptime_minutes = map(int, uptime.split(":"))
                uptime_seconds = (uptime_hours * 60 + uptime_minutes) * 60
            return uptime_seconds
        elif action == "difference":
            test1 = datetime.strptime(old_time, "%Y-%m-%d-%H:%M:%SZ")
            test2 = datetime.strptime(new_time, "%Y-%m-%d-%H:%M:%SZ")
            if getattr(test1, time_part) != getattr(test2, time_part):
                return True  # There is a difference            
            return False
        else:
            # if the action is default 
            return_val = new_time+timedelta(days=r_days)
            if backward:
                return_val = new_time-timedelta(days=r_days)
        
        return return_val.strftime("%Y-%m-%d")
        
                
    def get_arch(self):
        arch = platform()
        if "x86_64" in arch:
            arch = "x86_64"
        else:
            arch = "arm64"
        return arch       
    

    def get_percentage_complete(self, command_obj):
        start = command_obj["start"]
        end = command_obj["end"]
        current = command_obj["current"]
        invert = command_obj.get("invert",False)
        absolute = command_obj.get("absolute",False)
        
        if not absolute: 
            if current < start:
                return 0
        
        elif current >= end:
            return 100
        
        total_range = end - start
        current_range = abs(current - start)
        percentage = (current_range / total_range) * 100
        if invert: percentage = 100 - percentage
        return int(percentage) 
    

    def get_info_from_edge_point(self,command_obj):
        # api_endpoint_type=(str) [consensus, info]
        # specific_ip=(ip_address) # will set range to 0 and not do a random
        profile = command_obj.get("profile")
        caller = command_obj.get("caller",False) # for logging and troubleshooting
        api_endpoint_type = command_obj.get("api_endpoint_type","info")
        desired_key = command_obj.get("desired_key","all")
        desired_value = command_obj.get("desired_value","cnng_current")
        return_value = command_obj.get("return_value", desired_value)
        specific_ip = command_obj.get("specific_ip",False)
        spinner = command_obj.get("spinner",False)
        max_range = command_obj.get("max_range",10)
        threaded = command_obj.get("threaded", False)
        cluster_info = []
        
        if caller: self.log.logger.debug(f"get_info_from_edge_point called from [{caller}]")
            
        api_str = "/cluster/info"
        if api_endpoint_type == "consensus":
            if self.config_obj[profile]["layer"] == 0:
                api_str = "/consensus/latest/peers"

        local_only = ["self","localhost","127.0.0.1"]
        if specific_ip in local_only:
            return {
                "ip": self.get_ext_ip(),
                "publicPort": self.config_obj[profile]["public_port"],
                "p2pPort": self.config_obj[profile]["p2p_port"],
                "cli": self.config_obj[profile]["cli_port"],
            }
            
        while True:
            try:
                cluster_info = self.get_cluster_info_list({
                    "ip_address": self.config_obj[profile]["edge_point"],
                    "port": self.config_obj[profile]["edge_point_tcp_port"],
                    "api_endpoint": api_str,
                    "spinner": spinner,
                    "error_secs": 3,
                    "attempt_range": 7,
                })
            except Exception as e:
                self.log.logger.error(f"get_info_from_edge_point -> get_cluster_info_list | error: {e}")
                pass
            
            cluster_info_tmp = deepcopy(cluster_info)
            self.log.logger.debug(f"get_info_from_edge_point --> edge_point info request result size: [{cluster_info[-1]['nodectl_found_peer_count']}]")
            
            try:
                cluster_info_tmp.pop()
            except:
                if threaded: 
                    self.log.logger.error("get_info_from_edge_point reached error while threaded, error skipped")
                    cprint("  error attempting to reach edge point","red")
                else:
                    self.error_messages.error_code_messages({
                        "error_code": "fun-648",
                        "line_code": "off-network",
                    })
            
            for n in range(0,max_range):
                node = random.choice(cluster_info_tmp)
                if specific_ip:
                    specific_ip = self.ip_address if specific_ip == "127.0.0.1" else specific_ip
                    for i_node in cluster_info_tmp:
                        if specific_ip == i_node["ip"]:
                            node = i_node
                            break
                
                self.log.logger.debug(f"get_info_from_edge_point --> api_endpoint: [{api_str}] node picked: [{node}]")
                
                node["specific_ip_found"] = False
                if specific_ip:
                    node["specific_ip_found"] = (specific_ip,node["ip"])
                        
                try:
                    if desired_value == "cnng_current" or desired_value == node[desired_key]:
                        if desired_key == "all" or return_value == "all":
                            return node
                        return node[desired_key]
                    
                except Exception as e:
                    self.log.logger.warn(f"unable to find a Node with a State object, trying again | error {e}")
                    sleep(1)
                if n > 9:
                    self.log.logger.error(f"unable to find a Node on the current cluster with [{desired_key}] == [{desired_value}]") 
                    if not self.auto_restart:
                        print(colored("  WARNING:","yellow",attrs=['bold']),colored(f"unable to find node in [{desired_value}]","red"))
                        self.print_timer(10,"Pausing 10 seconds",1)

        
    def get_api_node_info(self,command_obj):
        # api_host=(str), api_port=(int), info_list=(list)
        api_host = command_obj.get("api_host")
        api_port = command_obj.get("api_port")
        api_endpoint = command_obj.get("api_endpoint","/node/info")
        info_list = command_obj.get("info_list","all")
        tolerance = command_obj.get("tolerance",2)
        
        # dictionary
        #  api_host: to do api call against
        #  api_port: for the L0 or metagraph channel
        #  info_list:  list of details to return from the call
        #       if info_list is string "all" will return everything
        #  
        #  a list of values will be returned based on the list_info
        # example_return = {
        #         "state":"Ready",
        #         "session":1663963276934,  # is a peer session (changes with every restart)
        #         "clusterSession":1663959458366, # cluster session (changes with every network restart)
        #         "version":"0.27.0",
        #         "host":"198.199.77.205",  # ip address or hostname
        #         "publicPort":9000,
        #         "p2pPort":9001,
        #         "id":"70e149abe4cc8eee53ba53d393152751496289f541452bd6d2b1d312dd37bb3c57692bad33069f5e7f521617992b87e1b388873c9672c01f71a0a16483fc27e5" #PeerId
        #     }
        
        api_url = self.set_api_url(api_host, api_port, api_endpoint)
        
        if info_list[0] == "all":
            info_list = ["state","session","clusterSession","host","version","publicPort","p2pPort","id"]
        
        result_list = []
        for n in range(0,tolerance):
            try:
                session = get(api_url,verify=False,timeout=(2,2),headers=self.get_headers).json()
            except:
                self.log.logger.error(f"get_api_node_info - unable to pull request | test address [{api_host}] public_api_port [{api_port}] attempt [{n}]")
                if n == tolerance-1:
                    self.log.logger.warn(f"get_api_node_info - trying again attempt [{n} of [{tolerance}]")
                    return None
                sleep(1.5)
            else:
                break

        if len(session) < 2 and "data" in session.keys():
            session = session["data"]
            
        self.log.logger.debug(f"get_api_node_info --> session [{session}] returned from node address [{api_host}] public_api_port [{api_port}]")
        try:
            for info in info_list:
                result_list.append(session[info])
        except:
            self.log.logger.warn(f"Node was not able to retrieve [{info}] of [{info_list}] returning None")
            return "LB_Not_Ready"
        else:
            return result_list


    def get_from_api(self,url,utype,tolerance=5):
        
        for n in range(1,tolerance):
            try:
                if utype == "json":
                    response = get(url,timeout=2,headers=self.get_headers).json()
                else:
                    response = get(url,timeout=2,headers=self.get_headers)
            except Exception as e:
                self.log.logger.error(f"unable to reach profiles repo list with error [{e}] attempt [{n}] of [3]")
                if n > tolerance-1:
                    self.error_messages.error_code_messages({
                        "error_code": "fnt-876",
                        "line_code": "api_error",
                        "extra2": url,
                        "extra": None
                    })
            else:
                if utype == "yaml_raw":
                    return response.content.decode("utf-8").replace("\n","").replace(" ","")
                elif utype == "yaml":
                    return yaml.safe_load(response.content)
                return response
                        
                    
    def get_cluster_info_list(self,command_obj):
        # ip_address, port, api_endpoint, error_secs, attempt_range
        var = SimpleNamespace(**command_obj)
        spinner = command_obj.get("spinner",True)
        results = False
        
        uri = f"http://{var.ip_address}:{var.port}{var.api_endpoint}"
        if var.port == 443:
            uri = f"https://{var.ip_address}{var.api_endpoint}"
            
        with ThreadPoolExecutor() as executor:
            do_thread = False # avoid race conditions
            # self.log.logger.debug(f"auto_restart set to [{self.auto_restart}]")
            if not self.auto_restart:
                if not self.event and spinner:
                    self.event, do_thread = True, True
                    self.print_clear_line()
                    _ = executor.submit(self.print_spinner,{
                        "msg": f"API making call outbound, please wait",
                        "color": "magenta",
                    })   
                
            for n in range(var.attempt_range+1):
                try:
                    results = get(uri,verify=False,timeout=2,headers=self.get_headers).json()
                except:
                    if n > var.attempt_range:
                        if not self.auto_restart:
                            self.network_unreachable_looper()
                        else:
                            self.event = False
                            return
                    self.log.logger.warn(f"attempt to pull details for LB failed, trying again - attempt [{n+1}] of [10] - sleeping [{var.error_secs}s]")
                    sleep(var.error_secs)
                else:
                    if "consensus" in var.api_endpoint:
                        results = results["peers"]
                    try:
                        results.append({
                            "nodectl_found_peer_count": len(results)
                        })
                    except:
                        self.log.logger.warn("network may have become unavailable during cluster_info_list verification checking.")
                        results = [{"nodectl_found_peer_count": 0}]
                self.event = False
                return results 
            
            if do_thread:
                self.event = False  
            
        
    def get_dirs_by_profile(self,command_obj):
        profile = command_obj["profile"]
        specific = command_obj.get("specific",False)

        self.set_default_directories()
        
        return_obj = {}
        for i_profile in self.profile_names: 
            if i_profile == profile and profile != "all":
                if specific:
                    return self.config_obj[i_profile][specific]
                for directory in self.config_obj[i_profile].keys():
                    if "directory" in directory:
                        return_obj[directory] =  self.config_obj[i_profile][directory]
            elif profile == "all":
                return_obj[i_profile] = {}
                for directory in self.config_obj[i_profile].keys():
                    if "directory" in directory and "userset" not in directory:
                        return_obj[i_profile][directory] =  self.config_obj[i_profile][directory]
        return return_obj
    
        
    def get_user_keypress(self,command_obj):
        # prompt=(str)
        # prompt_color=(str)
        # options=(list) list of valid keys
        # debug=(bool) if want to test output of key for dev purposes
        
        options = command_obj.get("options",["any_key"])
        prompt = command_obj.get("prompt","")
        prompt_color = command_obj.get("prompt_color","magenta")
        debug = command_obj.get("debug",False)
        quit_option = command_obj.get("quit_option",False)
        self.key_pressed = None
        
        invalid_str = f"  {colored(' Invalid ','yellow','on_red',attrs=['bold'])}: {colored('only','red')} "
        for option in options:
            invalid_str += f"{colored(option,'white',attrs=['bold'])}, " if option != options[-1] else f"{colored(option,'white',attrs=['bold'])}"
        invalid_str = colored(invalid_str,"red")
                
        cprint(f"  {prompt}",prompt_color,end="\r")
        print("\033[F")
        
        def press(key):
            if debug:
                print(key)
                return
            if options[0] == "any_key" or key.upper() in options:
                stop_listening()
                self.key_pressed = key
                return
            if key != "enter":
                print(f"{invalid_str} {colored('options','red')}")
                cprint("  are accepted, please try again","red")

        listen_keyboard(
            on_press=press,
            delay_second_char=0.75,
        )

        print("")
        if quit_option and (self.key_pressed.upper() == quit_option.upper()):
            cprint("  Action cancelled by User","yellow")
            exit(0)
            
        try: _ = self.key_pressed.lower()  # avoid NoneType error
        except: return
        return self.key_pressed.lower()


    def get_size(self,start_path = '.',single=False):
        if single:
            return path.getsize(start_path)
        total_size = 0
        for dirpath, dirnames, filenames in walk(start_path):
            for f in filenames:
                fp = path.join(dirpath, f)
                # skip if it is symbolic link
                if not path.islink(fp):
                    total_size += path.getsize(fp)
        
        return total_size  
    
    
    def get_dir_size(self, r_path="."):
        total = 0
        if path.exists(r_path):
            with scandir(r_path) as it:
                for entry in it:
                    if entry.is_file():
                        total += entry.stat().st_size
                    elif entry.is_dir():
                        total += self.get_dir_size(entry.path)
        return total

 
    def get_snapshot(self,command_obj):
        action = command_obj.get("action","latest")
        ordinal = command_obj.get("ordinal",False)
        history = command_obj.get("history",50)
        environment = command_obj.get("environment","mainnet")
        return_values = command_obj.get("return_values",False)
        lookup_uri = command_obj.get("lookup_uri",f"https://{self.be_urls[environment]}/")
        header = command_obj.get("header",self.get_headers)
        get_results = command_obj.get("get_results","data")
        return_type =  command_obj.get("return_type","list")
        
        return_data = []
        error_secs = 2
        
        if action == "latest":
            uri = f"{lookup_uri}global-snapshots/latest"
            if not return_values: return_values = ["timestamp","ordinal"]
        elif action == "history":
            uri = f"{lookup_uri}global-snapshots?limit={history}"
            return_type = "raw"
        elif action == "ordinal":
            uri = f"{lookup_uri}global-snapshots/{ordinal}"
        elif action == "rewards":
            uri = f"{lookup_uri}global-snapshots/{ordinal}/rewards"
            if not return_values: return_values = ["destination"]
            return_type = "dict"
        
        try:
            results = get(uri,verify=False,timeout=2,headers=header).json()
            results = results[get_results]
        except Exception as e:
            self.log.logger.warn(f"get_snapshot -> attempt to access backend explorer or localhost ap failed with | [{e}] | url [{uri}]")
            sleep(error_secs)
        else:
            if return_type == "raw":
                return_data = results
            else:
                for value in return_values:
                    if return_type == "list":
                        return_data.append(results[value])
                    elif return_type == "dict":
                        return_data = {}
                        for v in results:
                            if not return_values or v in return_values:
                                return_data[v] = results[v]
            return return_data


    def get_list_of_files(self,command_obj):
        paths = command_obj.get("paths") # list
        files = command_obj.get("files") # list - *.extention or full file name
        
        excludes = [command_obj.get("exclude_paths",False)] # list
        excludes.append(command_obj.get("exclude_files",False)) # list
        
        possible_found = {}
        
        for i_path in paths:
            try:
                for file in files:
                    for n,f_path in enumerate(Path(f'/{i_path}').rglob(file)):
                        possible_found[f"{n+1}"] = f"{f_path}"
            except:
                self.log.logger.warn(f"unable to process path search | [/{i_path}/]")
            
        clean_up = copy(possible_found) 
        for n,exclude in enumerate(excludes):  
            if exclude:
                for item in exclude:
                    for key, found in clean_up.items():
                        if n < 1:
                            if item == found[1:]:
                                possible_found.pop(key)
                        else:
                            if item in found:
                                possible_found.pop(key)
                
        return possible_found
    
    
    # =============================
    # setter functions
    # =============================
    
      
    def set_env_variable(self,variable,value):
        # self.log.logger.debug(f"setting up environment [{variable}]")
        environ[variable] = f"{value}"

    
    def set_api_url(self,api_host,api_port,post_fix):        
        api_url = f"http://{api_host}:{api_port}{post_fix}"
        if api_port == 443:
            api_url = f"https://{api_host}{post_fix}"
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
        return api_url
    
    
    def set_default_variables(self,command_obj):
        # set default profile
        # set default edge point
        profile = command_obj.get("profile",None)
        skip_error = command_obj.get("skip_error",False)
        self.default_profile = False

        if profile != "skip":
            try:
                for layer in range(0,3):
                    if self.default_profile:
                        break
                    for i_profile in self.config_obj.keys():
                        if "global" not in i_profile: 
                            if profile != None and profile != "all":
                                i_profile = profile
                            profile_layer = self.config_obj[i_profile]["layer"]
                            profile_enable = self.config_obj[i_profile]["profile_enable"]
                            if profile_layer == layer and profile_enable:
                                self.default_profile = i_profile
                                
                                uri = self.set_api_url(
                                    self.config_obj[self.default_profile]["edge_point"],
                                    self.config_obj[self.default_profile]["edge_point_tcp_port"],
                                    "" # no post_fix
                                )
                                self.default_edge_point = {
                                    "host": self.config_obj[self.default_profile]["edge_point"],
                                    "host_port":self.config_obj[self.default_profile]["edge_point_tcp_port"],
                                    "uri": uri
                                } 
                                break # on 1st and lowest layer   
            except:
                self.log.logger.error("functions unable to process profile while setting up default values")
                if not skip_error:
                    self.error_messages.error_code_messages({
                        "error_code": "fnt-924",
                        "line_code": "profile_error",
                        "extra": profile,
                    })
            
        self.config_obj["global_elements"]["node_profile_states"] = {}  # initialize 
        self.profile_names = self.clear_global_profiles(self.config_obj)
        
        try: self.profile_names.pop(self.profile_names.index("upgrader"))
        except ValueError: pass
        
        for profile in self.profile_names:
            self.environment_names.append(self.config_obj[profile]["environment"])
        self.environment_names = list(set(self.environment_names))
        
        self.ip_address = self.get_ext_ip()
        if not self.auto_restart: self.check_config_environment()
                

    def set_default_directories(self):
        # only to be set if "default" value is found

        for profile in self.config_obj.keys():
            if "global" not in profile:
                self.config_obj[profile]["directory_snapshots_userset"] = False
                self.config_obj[profile]["directory_inc_snapshot_userset"] = False
                self.config_obj[profile]["directory_inc_snapshot_tmp_userset"] = False
                
                snap_dict = {
                    "custom_env_vars_CL_SNAPSHOT_STORED_PATH": {
                        "config_key": "directory_snapshots", 
                        "path": f"/var/tessellation/{profile}/data/snapshot"
                    },
                    "custom_env_vars_CL_INCREMENTAL_SNAPSHOT_STORED_PATH": {
                        "config_key": "directory_inc_snapshot", 
                        "path": f"/var/tessellation/{profile}/data/incremental_snapshot"
                    },
                    "custom_env_vars_CL_INCREMENTAL_SNAPSHOT_TMP_STORED_PATH": {
                        "config_key": "directory_inc_snapshot_tmp", 
                        "path": f"/var/tessellation/{profile}/data/incremental_snapshot_tmp",
                    },
                }   
        
                for env_arg, values in snap_dict.items():
                    default_setting = values["path"] if self.config_obj[profile]["layer"] < 1 else "disabled"
                    if not self.config_obj[profile]["custom_env_vars_enable"]:
                        self.config_obj[profile][values["config_key"]] = default_setting
                    else:
                        try:
                            value = self.config_obj[profile][env_arg]
                        except: # disabled exception
                            self.config_obj[profile][values["config_key"]] = default_setting
                        else:
                            self.config_obj[profile][values["config_key"]] = value
                            self.config_obj[profile][f"{values['config_key']}_userset"] = True
                         
                if self.config_obj[profile]["directory_backups"] == "default": # otherwise already set
                    self.config_obj[profile]["directory_backups"] = "/var/tessellation/backups/"
                if self.config_obj[profile]["directory_uploads"] == "default": # otherwise already set
                    self.config_obj[profile]["directory_uploads"] = "/var/tessellation/uploads/"
                if self.config_obj[profile]["seed_location"] == "default": # otherwise already set
                    self.config_obj[profile]["seed_location"] = "/var/tessellation/"
                if self.config_obj[profile]["seed_file"] == "default": # otherwise already set
                    self.config_obj[profile]["seed_file"] = "seed-list"
                 
            # currently not configurable
            self.config_obj[profile]["directory_logs"] = f"/var/tessellation/{profile}/logs/"   
            self.config_obj[profile]["directory_archived"] = f"/var/tessellation/{profile}/logs/archived"  
            self.config_obj[profile]["directory_json_logs"] = f"/var/tessellation/{profile}/logs/json_logs"  
            
            
    def set_system_prompt(self,username):
        prompt_update = r"'\[\e[1;34m\]\u@Constellation-Node:\w\$\[\e[0m\] '"
        prompt_update = f"PS1={prompt_update}"
        cmd = f'echo "{prompt_update}" | tee -a /home/{username}/.bashrc > /dev/null 2>&1'  
        
        is_prompt_there = self.test_or_replace_line_in_file({
            "file_path": f"/home/{username}/.bashrc",
            "search_line": "Constellation-Node",
        })
        if is_prompt_there and is_prompt_there != "file_not_found":
            self.test_or_replace_line_in_file({
                "file_path": f"/home/{username}/.bashrc",
                "search_line": "Constellation-Node",
                "replace_line": prompt_update,
            })
        elif is_prompt_there != "file_not_found":
            system(cmd)   
        
        system(f". /home/{username}/.bashrc > /dev/null 2>&1")   
        
                 
    # =============================
    # pull functions
    # ============================= 
      
      
    def pull_node_sessions(self,command_obj):
        key = command_obj['key']
        port = command_obj['edge_device']['remote_port']
        profile = command_obj['profile']
        spinner = command_obj.get("spinner",True)
        
        local_port = self.config_obj[profile]["public_port"]
        nodes = command_obj['edge_device']['remote'], self.ip_address
        session = {}

        # node0 = edge (remote) device (for dynamic purposes)
        session_obj = {
            "node0": nodes[0],
            "node1": nodes[1],
            "session0": 0,
            "session1": 0,
            "state0": "ApiNotReady",
            "state1": "ApiNotReady"
        }
        
        self.log.logger.debug(f"pull_node_session: session_obj [{session_obj}]")
        
        for i,node in enumerate(nodes):
            state = None
                
            if i > 0: # remote session first
                if self.config_obj["global_elements"]["node_service_status"][profile] == "inactive (dead)":
                    break # state defaulted to ApiNotReady
                port = local_port    

            try:
                state = self.test_peer_state({
                    "profile": profile,
                    "spinner": spinner,
                    "simple": True,
                })
            except Exception as e:
                self.log.logger.error(f"pull_node_session -> exception | {e}")
        
            self.log.logger.debug(f"pull_node_sessions -> profile [{profile}] node [{node}] state found [{state}] assign to [{i}]")
            session_obj[f"state{i}"] = state
            url = self.set_api_url(node,port,"/node/info")
            self.log.logger.debug(f"pull_node_session -> url: {url}")
            
            try:
                session = get(url,verify=False,headers=self.get_headers).json()
            except:
                self.log.logger.error(f"pull_node_sessions - unable to pull request [functions->pull_node_sessions] test address [{node}] public_api_port [{port}] url [{url}]")

            self.log.logger.info(f"pull_node_sessions found session [{session}] returned from test address [{node}] url [{url}] public_api_port [{port}]")
            try:
                token = session[key]
            except Exception as e:
                try:
                    self.log.logger.warn(f"Load Balancer did not return a token | reason [{session['reason']} error [{e}]]")
                    session_obj[f"session{i}"] = f"LB_NotReady{i}"
                except:
                    self.error_messages.error_code_messages({
                        "error_code": "fnt-958",
                        "line_code": "lb_not_up",
                        "extra": command_obj['edge_device']['remote'],
                    })
            else:
                session_obj[f"session{i}"] = token
                
        # double-check session is int
        try:
            if session_obj["session0"] == None:
                session_obj["session0"] = 0
            if session_obj["session1"] == None:
                session_obj["session1"] = 0
        except Exception as e:
            self.log.logger.debug(f"pull_node_session - error applying session0 and session1 | [{e}]")
        
        self.log.logger.debug(f"pull_node_session - session being returned [{session_obj}]")    
        return session_obj    
    
    
    def pull_edge_point(self,i_profile):
        self.log.logger.debug(f"function - pull edge point device [{i_profile}]")
        while True:
            try:
                self.log.logger.debug(f"function - pull edge point device i_profile [{i_profile}]")
                return {
                    "remote": self.config_obj[i_profile]["edge_point"],
                    "remote_port": self.config_obj[i_profile]["edge_point_tcp_port"],
                    "port_list": self.pull_profile({
                        "req": "localhost",
                        "profile": i_profile,
                    })
                }
            except:
                self.log.logger.error(f"function - pull edge point device - error during [{i_profile}] profile retrieval")
                self.error_messages.error_code_messages({
                    "error_code": "fnt-616",
                    "line_code": "profile_error",
                    "extra": i_profile,
                    "extra2": None
                })       
    
    
    def pull_node_balance(self, command_obj):
        ip_address = command_obj["ip_address"]
        wallet = command_obj["wallet"]
        environment = command_obj["environment"]
        
        balance = 0
        return_obj = {
            "balance_dag": "unavailable",
            "balance_usd": "unavailable",
            "dag_price": "unavailable"
        }
        
        self.print_cmd_status({
            "text_start": "Pulling DAG details from APIs",
            "brackets": environment,
            "status": "running",
            "newline": True,
        })

        if environment != "mainnet":
            self.print_paragraphs([
                [" NOTICE ",0,"red,on_yellow"], 
                [f"Wallet balances on {environment} are fictitious",0],["$DAG",0,"green"], 
                ["and will not be redeemable or spendable.",2],
            ])
            
        with ThreadPoolExecutor() as executor:
            self.event = True
            _ = executor.submit(self.print_spinner,{
                "msg": f"Pulling Node balances, please wait",
                "color": "magenta",
            })                     

            for n in range(5):
                try:
                    url =f"https://{self.be_urls[environment]}/addresses/{wallet}/balance"
                    balance = get(url,verify=True,timeout=2,headers=self.get_headers).json()
                    balance = balance["data"]
                    balance = balance["balance"]
                except:
                    self.log.logger.error(f"pull_node_balance - unable to pull request [{ip_address}] DAG address [{wallet}] attempt [{n}]")
                    if n == 9:
                        self.log.logger(f"pull_node_balance session - returning [{balance}] because could not reach requested address")
                        break
                    sleep(1.5)
                break   
            self.event = False              
        
        try:  
            balance = balance/1e8 
        except:
            balance = 0

        usd = []
        usd = self.get_crypto_price()  # position 5 in list

        try:
            return_obj["dag_price"] = "${:,.3f}".format(usd[5])
        except:
            pass
        try:
            return_obj["balance_dag"] = "{:,.5f}".format(balance)
        except:
            pass
        try:
            return_obj["balance_usd"] = "${:,.2f}".format(balance*usd[5])
        except:
            pass
        
        return return_obj
    
   
    def pull_custom_variables(self):
        return_obj = {
            "custom_args": [],
            "custom_env_vars": [],
        }
        for profile in self.profile_names:
            for item,value in self.config_obj[profile].items():
                if "custom_args" in item:
                    return_obj["custom_args"].append((profile,item.replace("custom_args_",""),value))
                if "custom_env_vars" in item:
                    return_obj["custom_env_vars"].append((profile, item.replace("custom_env_vars_",""),value))
                    
        return return_obj
            
        
    def pull_profile(self,command_obj):
        # profile=(str)
        # req=(str) # what do you want to do?
    
        var = SimpleNamespace(**command_obj)
        self.log.logger.debug(f"function pull_profile [{var.req}]")
        var.profile = command_obj.get("profile",None)
            
        profile = "empty"
        if var.profile:
            profile = var.profile # profile in question (will default if not specified)
        
        
        global metagraph_name
        global service_list
        global description_list
        global metagraph_layer_list
        global metagraph_env_set 
        global custom_values_dict 
        
        metagraph_name = None
        service_list = []
        description_list = []
        metagraph_layer_list = []
        metagraph_env_set = set()
        custom_values_dict = {}
        
        def pull_all():
            global metagraph_name
            global service_list
            global description_list
            global metagraph_layer_list
            global metagraph_env_set 
            global custom_values_dict 
            
            custom_values_dict = self.pull_custom_variables()
            metagraph_name = self.config_obj["global_elements"]["metagraph_name"]
            for i_profile in self.profile_names:
                service_list.append(self.config_obj[i_profile]["service"]) 
                description_list.append(self.config_obj[i_profile]["description"]) 
                metagraph_layer_list.append(self.config_obj[i_profile]["layer"]) 
                metagraph_env_set.add(self.config_obj[i_profile]["environment"]) 

        def test_replace_last_elements(list1,list2):
            if list1[-1] == list2[-1]:
                list1.append(list2[0])
                list1[-2], list1[-1] = list1[-1], list1[-2]
                return list1
            return False

        if var.req == "service":
            if profile != "empty":
                return self.config_obj[profile]["service"]
            else:
                pull_all()
                return service_list
            
        elif "pairings" in var.req:
            # return list of profile objects that are paired via layer0_link
            pairing_list = []
                       
            for profile in self.profile_names:
                link_found = False
                for link_type in self.link_types:
                    if self.config_obj[profile][f"{link_type}_link_enable"]:
                        link_found = True
                        # list of lists of matching profile to linked profile
                        link_profile = self.config_obj[profile][f"{link_type}_link_profile"]
                        if link_profile != "None":
                            pairing_list.append([profile, self.config_obj[profile][f"{link_type}_link_profile"]])
                        else: pairing_list.append([profile])
                if not link_found: pairing_list.append([profile])
            
            n = 0
            while True:
                list1 = pairing_list[n]
                try: list2 = pairing_list[n+1]
                except IndexError: break
                else:
                    list1 = test_replace_last_elements(list1,list2)
                    if list1:
                        pairing_list[n] = list1
                        pairing_list.remove(list2)
                    else:
                        n += 1
            
            # add services to the pairing list
            for n, s_list in enumerate(pairing_list):
                for i, profile in enumerate(s_list):
                    pair_dict = {
                        "profile": profile,
                        "service": self.config_obj[profile]["service"],
                        "layer": self.config_obj[profile]["layer"]
                    }
                    s_list[i] = pair_dict
                pairing_list[n] = s_list

            if "order_pairing" in var.req:
                # put profiles in order of leave, stop, start, join
                # order_pairing option should have the last element with the
                # pairing dict popped before the returned list is used.
                pre_profile_order = []; profile_order = []
                for profile_group in pairing_list:
                    for profile_obj in reversed(profile_group):
                        pre_profile_order.append(profile_obj["profile"])
                [profile_order.append(element) for element in pre_profile_order if element not in profile_order]         
                pairing_list.append(profile_order)
                
            return pairing_list

        elif "environments" in var.req:
            pull_all()
            return {
                "environment_names": metagraph_env_set,
                "multiple_environments": True if len(metagraph_env_set) > 1 else False
            }
        
        elif "one_profile_per_env" in var.req:
            pull_all()
            last_env = set(); profiles = []
            for env in metagraph_env_set:
                for profile in self.profile_names:
                    if not self.config_obj[profile]["environment"] in last_env:
                        profiles.append(profile)
                    last_env.add(env)
            return profiles

        elif var.req == "profiles_by_environment":
            pull_all()
            profiles = set()
            for i_profile in self.profile_names:
                if self.config_obj[i_profile]["environment"] == var.environment:
                    profiles.add(i_profile)
            return profiles   
                
        elif "list" in var.req:
            if var.req == "list":
                return list(self.config_obj.keys())
            elif var.req == "list_details":
                pull_all()
                return {
                    "profile_names": self.profile_names,
                    "profile_services": service_list,
                    "profile_descr": description_list,
                    "metagraph_name": metagraph_name,
                    "environment_names": metagraph_env_set,
                    "layer_list": metagraph_layer_list,
                    "custom_values": custom_values_dict,
                }
        if var.req == "default_profile":
            return list(self.config_obj.keys())[0]
            
        elif "link_profile" in var.req:
            gl0_link_obj = {
                "gl0_link_enable": self.config_obj[profile]["gl0_link_enable"],
                "gl0_profile": self.config_obj[profile]["gl0_link_profile"],
                "gl0_port": self.config_obj[profile]["gl0_link_port"],
                "gl0_host": self.config_obj[profile]["gl0_link_host"],
                "gl0_key": self.config_obj[profile]["gl0_link_key"],                
            }
            ml0_link_obj = {
                    "ml0_link_enable": self.config_obj[profile]["ml0_link_enable"],
                    "ml0_profile": self.config_obj[profile]["ml0_link_profile"],
                    "ml0_port": self.config_obj[profile]["ml0_link_port"],
                    "ml0_host": self.config_obj[profile]["ml0_link_host"],
                    "ml0_key": self.config_obj[profile]["ml0_link_key"],                
            }
            all_link_obj = gl0_link_obj | ml0_link_obj
            if var.req == "gl0_link_profile": return gl0_link_obj
            if var.req == "ml0_link_profile": return ml0_link_obj
            if var.req == "all_link_profiles": return all_link_obj
            return False 
                        
        elif var.req == "ports":
            return {
                "public": self.config_obj[profile]["public_port"],
                "p2p": self.config_obj[profile]["p2p_port"],
                "cli": self.config_obj[profile]["cli_port"],
            }
        
        elif var.req == "exists" or var.req == "enabled":
            try: test = self.config_obj[profile]["profile_enable"]
            except: test = False
                
            if test:
                if var.req == "enabled" and test: return True
                elif var.req == "enabled" and not test: return False
                else: return test
                
            self.error_messages.error_code_messages({
                "error_code": "fnt-998",
                "line_code": "profile_error",
                "extra": profile
            })
    
    
    def pull_remote_profiles(self,command_obj):
        r_and_q = command_obj.get("r_and_q","both")
        retrieve = command_obj.get("retrieve","profile_names")
        return_where = command_obj.get("return_where","Main")
        set_in_functions = command_obj.get("set_in_functions",False)
        predefined_envs = []
        
        repo_profiles = self.get_from_api(self.nodectl_profiles_url,"json")
        repo_profiles = repo_profiles["payload"]["tree"]["items"]
        metagraph_name, chosen_profile = None, None
        
        predefined_configs = {}
        for repo_profile in repo_profiles:
            if "predefined_configs" in repo_profile["path"] and "yaml" in repo_profile["name"]:
                f_url = f"{self.nodectl_profiles_url_raw}/{repo_profile['name']}" 
                details = self.get_from_api(f_url,"yaml")
                metagraph_name = details["nodectl"]["global_elements"]["metagraph_name"] # readability
                predefined_envs.append(metagraph_name)
                predefined_configs = {
                    **predefined_configs,
                    f"{metagraph_name}": {
                        "json": details,
                        "yaml_url": f_url,
                    }
                }
                    
        if retrieve == "profile_names" or retrieve == "chosen_profile":    
            chosen_profile = self.print_option_menu({
                "options": predefined_envs,
                "return_where": return_where,
                "r_and_q": r_and_q,
                "color": "green",
                "return_value": True,
            })

        if set_in_functions: 
            self.environment_names = list(predefined_configs.keys())
            return
        
        if chosen_profile == "r" or chosen_profile == "q": return chosen_profile
        elif retrieve == "profile_names": return chosen_profile
        elif retrieve == "config_file": return predefined_configs
        elif retrieve == "chosen_profile": return [chosen_profile, predefined_configs[chosen_profile]]


    # =============================
    # check functions
    # =============================    
    
    def check_edge_point_health(self,command_obj=False):
        # check_edge_point_health should be wrapped in a 
        # while loop from where it is called...
        uri = f"{self.default_edge_point['uri']}/node/health"
        
        if command_obj:    
            profile = command_obj.get("profile",False)
            
            if profile:
                uri = self.set_api_url(
                    self.config_obj[profile]["edge_point"],
                    self.config_obj[profile]["edge_point_tcp_port"],
                    "/node/health",               
                    )

        for n in range(0,4):
            try:
                health = get(uri,verify=True,timeout=2,headers=self.get_headers)
            except:
                self.log.logger.warn(f"unable to reach edge point [{uri}] attempt [{n+1}] of [3]")
                if n > 2:
                    if not self.auto_restart:
                        self.network_unreachable_looper()
                        return False
                pass
            else:  
                if health.status_code != 200:
                    self.log.logger.warn(f"unable to reach edge point [{uri}] returned code [{health.status_code}]")
                    if n > 2:
                        if not self.auto_restart:
                            self.network_unreachable_looper()
                            return False
                    else:
                        pass
                else:
                    return True
            if not self.auto_restart:
                sleep(1)
            
            
    def check_health_endpoint(self,api_port): 
        try:
            r = get(f'http://127.0.0.1:{api_port}/node/health',verify=False,timeout=2,headers=self.get_headers)
        except:
            pass
        else:
            if r.status_code == 200:
                self.log.logger.error(f"check health failed on endpoint [localhost] port [{api_port}]")
                return True
        self.log.logger.debug(f"check health successful on endpoint [localhost] port [{api_port}]")
        return False   
            
        
    def check_sudo(self):
        e = "sudo"

        if getuser() == "root":
            return
        
        try:
            test_sudo = getenv("SUDO_USER")
        except Exception as e:
            pass
        
        if test_sudo is None:
            try:
                self.error_messages.error_code_messages({
                    "error_code": "fnt-1057",
                    "line_code": "sudo_error",
                    "extra": e,
                    "extra2": None
                })   
            except:
                self.print_paragraphs([
                    ["WARNING",0,"white,on_red"], ["Permissions issue detected.",1,"red","bold"],
                    ["nodectl",0, "blue","bold"], ["is unable to continue.",1,"red"],
                    ["Are you sure your have sudo permissions?",2,"red"]
                ])
                exit("  sudo permissions error") # auto_restart not affected  
            

    def check_config_environment(self):
        # if there is not a configuration (during installation)
        # check what the primary network is
        # this method will need to be refactored as new Metagraphs
        # register with Node Garage or Constellation (depending)
        try:
            self.environment_name = self.config_obj[self.default_profile]["environment"]             
        except:
            if not self.environment_name:
                self.environment_name = self.pull_remote_profiles({"r_and_q": None})

            
    def check_for_help(self,argv_list,extended):
        if "help" in argv_list:
            self.print_help({
                "extended": extended
            })  
    
    
    def check_valid_profile(self,profile):
        if profile == "all":
            return
        
        if profile not in self.config_obj.keys():
            self.error_messages.error_code_messages({
                "error_code": "fnt-603",
                "line_code": "profile_error",
                "extra": profile,
            })
            
            
    # =============================
    # is functions
    # =============================      
    
    def is_new_version(self,current,remote):
        if version.parse(current) == version.parse(remote):
            self.log.logger.warn(f"versions match")
            return False            
        elif version.parse(current) > version.parse(remote):
            return "current_greater"
        else:
            return "current_less"
    
    
    def is_version_valid(self,check_version):
        try:
            version.Version(check_version)
        except Exception as e:
            self.log.logger.warn(f"is_version_valid returned False [{check_version}] e [{e}]")
            return False
        else:
            check_version = check_version.split(".")
            if len(check_version) == 3:
                return True
            return False    

    
    def is_valid_address(self,v_type,return_on,address):
        valid = False
        reg_expression = "^[D][A][G][a-zA-Z0-9]{37}$"
        if v_type == "nodeid":
            reg_expression = "^[a-f0-9]{128}$"
            
        if match(reg_expression,address):
            valid = True
        if return_on:
            return valid
        
        if not valid:
            self.error_messages.error_code_messages({
                "error_code": "fnt-1524",
                "line_code": "invalid_address",
                "extra": v_type,
                "extra2": address,
            })
        
    # =============================
    # test functions
    # =============================  

    def test_ready_observing(self,profile):
        self.get_service_status()
        state = self.test_peer_state({
            "profile": profile,
            "simple": True,
        })
        continue_states = ["Observing","Ready","WaitingForReady","WaitingForObserving","DownloadInProgress"] 
        if state not in continue_states or "active" not in self.config_obj["global_elements"]["node_service_status"][profile]:
            self.print_paragraphs([
                [" PROBLEM FOUND ",0,"grey,on_red","bold"], ["",1],
            ])
            self.print_cmd_status({
                "text_start": "Cannot continue",
                "brackets": profile,
                "text_end": "in state",
                "status": state,
                "status_color": "red",
                "newline": True,
            })
            self.print_auto_restart_warning()
            exit("  Tessellation Validator Node State Error")
            
            
    def test_peer_state(self,command_obj):
        # test_address=(str), current_source_node=(str), public_port=(int), simple=(bool)
        test_address = command_obj.get("test_address","127.0.0.1")
        profile = command_obj.get("profile")
        simple = command_obj.get("simple",False)
        print_output = command_obj.get("print_output",True)
        current_source_node = command_obj.get("current_source_node",False)
        skip_thread = command_obj.get("skip_thread",False)
        threaded = command_obj.get("threaded", False)
        spinner = command_obj.get("spinner", False)
        spinner = False if self.auto_restart else spinner
        api_not_ready_flag = False
        
        results = {
            "node_on_src": False,
            "node_on_edge": False,
            "src_node_color": "red",
            "edge_node_color": "red",
            "node_state_src": "ApiNotReady",
            "node_state_edge": "ApiNotReady",
            "full_connection": False,
            "full_connection_color": "red",
        }

        attempt = 0
        break_while = False
        
        if not current_source_node:
            try:
                current_source_node = self.get_info_from_edge_point({
                    "caller": "test_peer_state",
                    "threaded": threaded,
                    "profile": profile,
                    "spinner": spinner,
                })
            except Exception as e:
                self.log.logger.error(f"test_peer_state -> error retrieving get_info_from_edge_point | current_source_node: {current_source_node} | e: {e}")
            
        ip_addresses = prepare_ip_objs = [test_address,current_source_node]
        for n,ip in enumerate(prepare_ip_objs):
            if not isinstance(ip,dict):
                try:
                    ip_addresses[n] = self.get_info_from_edge_point({
                        "caller": "test_peer_state",
                        "threaded": threaded,
                        "profile": profile,
                        "specific_ip": ip,
                        "spinner": spinner,
                    })
                except Exception as e:
                    self.log.logger.error(f"test_peer_state -> unable to get_info_from_edge_point | ip_address {ip_addresses[n]} | e: [{e}]")

        with ThreadPoolExecutor() as executor:
            do_thread = False
            if not self.auto_restart:
                if not self.event and not skip_thread:
                    if print_output: self.print_clear_line()
                    self.event, do_thread = True, True
                    _ = executor.submit(self.print_spinner,{
                        "msg": f"API making call outbound, please wait",
                        "color": "magenta",
                    })           
                      
            while True:
                for n,ip_address in enumerate(ip_addresses):
                    if api_not_ready_flag: 
                        ip_address["ip"] = "127.0.0.1"
                        ip_address["publicPort"] = self.config_obj[profile]["public_port"]
                        
                    uri = self.set_api_url(ip_address["ip"], ip_address["publicPort"],"/node/state")
                        
                    if ip_address["ip"] is not None:
                        try: 
                            state = get(uri,verify=False,timeout=2,headers=self.get_headers).json()
                            color = self.change_connection_color(state)
                            self.log.logger.debug(f"test_peer_state -> uri [{uri}]")

                            if n == 1:
                                results['node_state_src'] = state
                                if state != "ReadyToJoin":
                                    results['node_on_src'] = True
                                results['src_node_color'] = color
                            else:
                                results['node_state_edge'] = state
                                if state != "ReadyToJoin":
                                    results['node_on_edge'] = True
                                results['edge_node_color'] = color
                                
                        except:
                            if api_not_ready_flag: break_while = True
                            # try 2 times before passing with ApiNotReady
                            attempt = attempt+1
                            if attempt > 1:
                                api_not_ready_flag = True
                            sleep(.5)
                            break
                        else:
                            break_while = True
                            if simple: # do not check/update source node
                                break
                
                if break_while:
                    break
                
            if do_thread:
                self.event = False   

        if simple:
            self.log.logger.debug(f"test peer state - simple - returning [{test_address}] [{ip_addresses[0]['publicPort']}] [{results['node_state_edge']}]")
            results = results["node_state_edge"]
        else:
            if results["node_on_edge"] and results["node_on_src"]:
                results["full_connection"] = True
                results["full_connection_color"] = "green"
        
        self.log.logger.debug(f"function test_peer_state returning [{results}]")
        return results


    def test_term_type(self):
        term_type = getenv('TERM')
        if "vt" in term_type or term_type == "ansi":
            self.error_messages.error_code_messages({
                "error_code": "fnt-346",
                "line_code": "term",
                "extra": term_type,
                "extra2": None
            })


    def test_hostname_or_ip(self, hostname):
        try:
            socket.gethostbyaddr(hostname)
        except:
            try:
                socket.gethostbyname(hostname)
            except:
                try:
                    validators.url(hostname)
                except:
                    return False
        return True    
    
    
    def test_or_replace_line_in_file(self,command_obj):
        # single line without dups only
        file_path = command_obj["file_path"]
        search_line = command_obj["search_line"]
        replace_line = command_obj.get("replace_line",False)
        skip_backup = command_obj.get("skip_backup",False)
        all_first_last = command_obj.get("all_first_last","all")
        skip_line_list = command_obj.get("skip_line_list",[])
        allow_dups = command_obj.get("allow_dups",True)
        return_value = command_obj.get("return_value", False)
        
        file = file_path.split("/")
        file = file[-1]
        i_replace_line = False
        
        global search_only_found
        search_only_found = False
        
        def search_replace(done,replace_line,line_position):
            global search_only_found
            if search_line in line and not done:
                search_only_found = True
                line_position = line_number
                if return_value: line_position = line
                if all_first_last != "all" and line_position not in skip_line_list:
                    done = True
                if replace_line:
                    temp_file.write(replace_line)
                    return done, line_position
            temp_file.write(line)  
            return done, line_position
                    
        if replace_line and not skip_backup:
            date = self.get_date_time({"action":"datetime"})
            try:
                backup_dir = self.get_dirs_by_profile({
                    "profile": self.default_profile,
                    "specific": "backups"
                })
            except:
                backup_dir = self.nodectl_path
        
        if not path.exists(file_path):
            return "file_not_found"
        try:
            f = open(file_path)
        except:
            return "file_not_found"
        
        result = False
        done = False
        temp = "/var/tmp/cnng_temp_file"
        
        # makes sure no left over file from esc'ed method
        def remove_temps():
            if path.isfile(temp):
                system(f"sudo rm {temp} > /dev/null 2>&1") 
            if path.isfile(f"{temp}_reverse"):
                system(f"sudo rm {temp}_reverse > /dev/null 2>&1")
        
        remove_temps()
                
        line_number, line_position = 0, 0       
        with open(temp,"w") as temp_file:
            if replace_line and not skip_backup:
                system(f"cp {file_path} {backup_dir}{file}_{date} > /dev/null 2>&1")
            if all_first_last == "last":
                for line in reversed(list(f)):
                    search_returns = search_replace(done,i_replace_line,line_position)
                    done, line_position = search_returns
            else:
                for line in list(f):
                    line_number += 1
                    i_replace_line = replace_line
                    if line_number in skip_line_list:
                        i_replace_line = False
                    search_returns = search_replace(done,i_replace_line,line_position)
                    done, line_position = search_returns

            f.close()
        
        if not replace_line:
            result = search_only_found
                
        if all_first_last == "last":
            f = open(temp)
            temp = f"{temp}_reverse"
            with open(temp, "w") as temp_file:
                search_line = ""
                all_first_last = "all"
                done = True            
                for line in reversed(list(f)):
                    search_returns = search_replace(done,i_replace_line,line_position)
                    try: done, line_position = search_returns
                    except: done = search_returns
                    
        f.close() # make sure closed properly                
                
        if replace_line:
            system(f"cp {temp} {file_path} > /dev/null 2>&1")
        # use statics to avoid accidental file removal
        remove_temps()
        
        if replace_line and not allow_dups:
            return [result, line_position]
        elif not allow_dups:
            return [result, line_position] 
        return result


    def test_for_premature_enter_press(self):
        return select.select([stdin], [], [], 0) == ([stdin], [], [])
    
    
    def test_for_root_ml_type(self,metagraph):
        # Review the configuration and return the lowest Metagraph
        try: profile_names = self.profile_names
        except:
            profile_names = self.clear_global_profiles(self.config_obj)
            
        root_profile = profile_names[0]
        layer_0_profiles = []
        
        if len(profile_names) == 1: return root_profile   # handle single metagraph profile
        
        for profile in profile_names:
            if self.config_obj[profile]["layer"] < 1 and metagraph == self.config_obj[profile]["environment"]:
                layer_0_profiles.append([
                    profile,
                    self.config_obj[profile]["environment"],
                    self.config_obj[profile]["meta_type"],
                    self.config_obj[profile]["gl0_link_enable"],
                ])
            
        if len(layer_0_profiles) == 1: return layer_0_profiles[0][0]    
        
        for profile in layer_0_profiles:
            # [3] == gl0_link_enable
            root_profile = profile
            if "gl" in profile: break
            elif "ml" in profile and not profile[3]: break

        return root_profile
                    
    
    def test_valid_functions_obj(self):
        # simple method that just returns True
        # to test if this method is available
        return True         
    
    # =============================
    # create functions
    # =============================  
       
    def create_coingecko_obj(self):
        self.log.logger.info(f"creating CoinGeckoAPI Object")
        self.cg = CoinGeckoAPI()   
            
    
    def create_n_write_csv(self, command_obj):
        full_path = command_obj.get("file",False)
        row = command_obj.get("row",False)
        rows = command_obj.get("rows",False)

        if row and rows or not full_path:
            self.log.logger("csv error detected, cannot write or row and rows in the same call.")
            self.error_messages.error_code({
                "line_code": "fnt-1795",
                "error_code": "internal_error"
            })
        
        rows = [row] if row else rows
            
        write_append = "w"
        if path.isfile(full_path):
            write_append = "a"
            
        with open(full_path, write_append, newline='') as file:
            writer = csv.writer(file, dialect='excel')
            writer.writerows(rows)
            
                        
    # =============================
    # print functions
    # =============================  

    def print_clear_line(self,lines=1):
        console_size = get_terminal_size()
        for _ in range(1,lines-1):
            print(f"{' ': >{console_size.columns-2}}")
        print(f"{' ': >{console_size.columns-2}}",end="\r")
        
        
    def print_timer(self,seconds,phrase="none",start=1):
        end_range = start+seconds
        if start == 1:
            end_range = end_range-1
            
        if phrase == "none":
            phrase = "to allow services to take effect"
        for n in range(start,end_range+1):
            if not self.auto_restart:
                self.print_clear_line()
                print(colored(f"  Pausing:","magenta"),
                        colored(f"{n}","yellow"),
                        colored("of","magenta"),
                        colored(f"{end_range}","yellow"),
                        colored(f"seconds {phrase}","magenta"), end='\r')
            sleep(1) 
            
        self.print_clear_line()  
            
            
    def print_states(self):
        states = self.get_node_states()
        
        state_strs = []
        
        n=0 
        not_done=True
        while not_done:
            state_str = ""
            for _ in range(4):
                try:
                    state_str += states[n][0]+", "
                except:
                    not_done = False
                n=n+1
            state_strs.append(state_str)
                
        print(colored("  States:","magenta"),colored(state_strs[0],"cyan"))
        state_strs.pop(0)
        for state_str in state_strs:
            print("         ",colored(state_str,"cyan"))


    def print_header_title(self,command_obj):
        #line1=(str), line2=(str)None, clear=(bool)True, newline=(str) Top, Bottom, Both
        #show_titles=(bool)
        #single_line=(bool) default: False
        #single_color=(str) default: yellow
        #single_bg=(str) default: on_blue
        
        line1 = command_obj["line1"] 
        line2 = command_obj.get("line2", None)
        clear = command_obj.get("clear", False)
        show_titles = command_obj.get("show_titles", True)
        newline = command_obj.get("newline", False)
        
        single_line = command_obj.get("single_line", False)
        single_color = command_obj.get("single_color", "yellow")
        single_bg = command_obj.get("single_bg", "on_blue")
        
        if "on_" not in single_bg:
            single_bg = f"on_{single_bg}" 

        if clear:
            system("clear")
        if newline == "top" or newline == "both":
            print("")
                                    
        if single_line:
            line1 = f" * {line1} * "  
            print("  ",end="")  
            cprint(f'{line1:-^40}',single_color,single_bg,attrs=["bold"])
        else:
            header0 = "  ========================================"
            header1 = "  =   CONSTELLATION NETWORK HYPERGRAPH   ="
            header2 = "  @netmet72\n"
            
            header_length = len(header0)-2
            header_middle = math.ceil(header_length/2)
            
            lines = [line1,line2]
            for n,line in enumerate(lines):
                if line != None:
                    line_length = len(line)
                    line_middle = math.ceil(line_length/2)
                    reduce = 1
                    if line_length % 2 == 0:
                        reduce = 2
                    line_rjust = int((header_middle-line_middle))
                    lines[n] = "".rjust(line_rjust)+line+"".rjust(line_rjust-reduce)
                
            print(colored(header0,"white",attrs=['bold']))
            if show_titles:
                print(colored(header1,"white",attrs=['bold']))
            
            for line in lines:
                if line != None:
                    print(colored("  =","white",attrs=["bold"]),end="")
                    print(colored(line,"green",attrs=["bold"]),end="")
                    print(colored("=","white",attrs=["bold"]))
            
            print(colored(header0,"white",attrs=['bold']))
            if show_titles:
                print(colored(header2,"white"))
        
        if newline == "bottom" or newline == "both":
            print("")
        
        
    def print_show_output(self,function_obj):
        # -BLANK- is reserved word for this function
        status_header, status_results = "",""
        header_elements = function_obj["header_elements"]
        cols = {}  # custom spacing per column

        # defaults
        header_color = "blue"
        header_attr = "bold" 
        d_spacing = 20
               
        for key,value in header_elements.items():
            if key != "spacing" and key != "header_color" and key != "header_attr" and key != "header_elements":
                try:
                    int(key)
                except:       
                    break   
                else:
                    # custom col spacing
                    for n in range(0,10):
                        try:
                            if int(key) == n:
                                cols[key] = value
                        except:
                            pass
            else:
                if key == "header_elements":
                    header_elements = value
                if key == "header_color":
                    header_color = value
                if key == "header_attr":
                    header_attr = value
                if key == "spacing":
                    d_spacing = int(value)
        
        #for header, value in header_elements.items():
        for i, (header, value) in enumerate(header_elements.items()):
            spacing = d_spacing
            if header == "-BLANK-":
                print("")
            else:
                if str(i) in cols:
                        spacing = cols[str(i)]
                status_header += colored(f"  {header: <{spacing}}",header_color,attrs=[header_attr])
                try:
                    status_results += f"  {value: <{spacing}}"
                except:
                    value = "unavailable".ljust(spacing," ")
                    status_results += f"  {value: <{spacing}}"
                
        print(status_header)
        print(status_results)
                

    def print_at_position(self,print_obj):
        x = print_obj["x"]            
        y = print_obj["y"]            
        text = print_obj["text"] 
        
        stdout.write("\x1b7\x1b[%d;%df%s\x1b8" % (x, y, text))
        stdout.flush()      
        
            
    def print_cmd_status(self,command_obj):
        # status=(str) "running", "successful", "complete"
        # text_start=(str) wording before brackets
        # text_end=(str) working after brackets  # default ""
        # brackets=(str) string to be in yellow and brackets # default False
        # newline={bool} # default False
        # delay={float} # how long to pause to allow user to see 

        text_start = command_obj["text_start"]
        text_end = command_obj.get('text_end',"")
        text_color = command_obj.get('text_color',"cyan")
        status = command_obj.get("status","")
        brackets = command_obj.get('brackets',False)
        delay = command_obj.get('delay',0)
        dotted_animation = command_obj.get('dotted_animation',False)
        
        newline = command_obj.get('newline',False)  # because of use of spread operator this should be declared consistently 
        status_color = command_obj.get('status_color',"default")
        bold = command_obj.get('bold',False)
        
        if status_color == "default":
            status_color = "yellow" if status == "running" else "green"
            status_color = "red" if status == "failed" else status_color

        padding = 50 - (len(text_start)+(len(brackets)-2)) if brackets else 55 - len(text_start)
        if padding < 0:
            padding = 0
            
        status = colored(status,status_color,attrs=['bold'])
                
        text_start = colored(text_start,text_color,attrs=['bold']) if bold else colored(text_start,text_color)
        text_end = colored(text_end,text_color,attrs=['bold']) if bold else colored(text_end,text_color)
        
        if brackets:
            l_bracket = colored("[",text_color,attrs=['bold']) if bold else colored("[",text_color) 
            r_bracket = colored("]",text_color,attrs=['bold']) if bold else colored("]",text_color) 
            brackets = colored(brackets,"yellow",attrs=["bold"])
            text_start = f"{text_start} {l_bracket}{brackets}{r_bracket} {text_end:.<{padding}} {status}"    
        else:
            text_start = f"{text_start} {text_end:.<{padding}} {status}"
                
        self.print_clear_line()
        
        def print_dots(text_start):
            dots = ["",".","..","..."]
            while True:
                for dot in dots: 
                    yield f"  {text_start} {dot}"
                                           
        if dotted_animation:
            dotted = print_dots(text_start)
            while self.status_dots:
                text_start = next(dotted)
                print(text_start, end="\r")
                sleep(.4)
                self.print_clear_line()
            self.print_clear_line()
        else:
            print(" ",text_start,end="\r")

        if newline:
            print("")       
            
        sleep(delay)
        
    
    def print_option_menu(self,command_obj):
        options_org = command_obj.get("options")
        options = copy(options_org) # options relative to self.profile_names
        let_or_num = command_obj.get("let_or_num","num")
        return_value = command_obj.get("return_value",False)
        return_where = command_obj.get("return_where","Main")
        color = command_obj.get("color","cyan")
        # If r_and_q is set ("r","q" or "both")
        # make sure if using "let" option, "r" and "q" do not conflict
        r_and_q = command_obj.get("r_and_q",False)
        
        prefix_list = []
        spacing = 0
        for n, option in enumerate(options):
            prefix_list.append(str(n+1))
            if let_or_num == "let":
                prefix_list[n] = option[0].upper()
                option = option[1::]
                spacing = -1
            self.print_paragraphs([
                [prefix_list[n],-1,color,"bold"],[")",-1,color],
                [option,spacing,color], ["",1],
            ])

        if r_and_q:
            if r_and_q == "both" or r_and_q == "r":
                self.print_paragraphs([
                    ["R",0,color,"bold"], [")",-1,color], [f"eturn to {return_where} Menu",-1,color], ["",1],
                ])
                prefix_list.append("R")
                options.append("r")
            if r_and_q == "both" or r_and_q == "q":
                self.print_paragraphs([
                    ["Q",-1,color,"bold"], [")",-1,color], ["uit",-1,color], ["",2],                
                ])
                prefix_list.append("Q")
                options.append("q")
        else:
            print("")
            
        option = self.get_user_keypress({
            "prompt": "KEY PRESS an option",
            "prompt_color": "cyan",
            "options": prefix_list,
        })
        
        if not return_value:
            return option
        for return_option in options:
            if let_or_num == "let":
                if option.lower() == return_option[0].lower():
                    return return_option
        try:
            return options[int(option)-1]
        except:
            return option # r_and_q exception
        

    def print_profile_env_menu(self,command_obj):
        print_header = command_obj.get("print_header", True)
        color = command_obj.get("color","magenta")
        p_type = command_obj.get("p_type","profile")
        title = command_obj.get("title",False)
        
        p_type_list = self.profile_names if p_type == "profile" else self.environment_names
        if not title:
            title = f"Press choose required {p_type}"

        print("")
        if print_header:
            self.print_header_title({
            "line1": title,
            "single_line": True,
            "newline": True,  
            })
        
        print("")
        return_value = self.print_option_menu({
            "options": p_type_list,
            "return_value": True,
            "color": color,
            "r_and_q": "q"
        })
        
        if return_value == "q":
            self.print_paragraphs([
                ["Command operation canceled by Node Operator",2,"green"],
            ])
            exit(0)
            
        self.print_paragraphs([
            ["",1], [f" {return_value} ",2,"yellow,on_blue","bold"],
        ])
        
        return return_value
        
                
    def print_any_key(self,command_obj):
        quit_option = command_obj.get("quit_option",False)
        newline = command_obj.get("newline",False)
        prompt = command_obj.get("prompt",False)
        color = command_obj.get("color", "yellow")
        
        key_pressed = None
        
        if newline == "top" or newline == "both":
            print("")
            
        if not prompt: prompt = "Press any key to continue"
        options = ["any_key"]
        if quit_option == "quit_only":
            prompt = f"press 'q' to quit"
            options = ["q"]
        elif quit_option:
            prompt = f"{prompt} or 'q' to quit"
            options = ["any_key","q"]
            
        key_pressed = self.get_user_keypress({
            "prompt": prompt,
            "prompt_color": color,
            "options": options,
        })
        
        if newline == "bottom" or newline == "both":
            print("")
            
        try: key_pressed = key_pressed.lower()
        except: key_pressed = "None"
        if quit_option and quit_option == key_pressed:
            return True
        return
        
        
    def print_paragraphs(self,paragraphs,wrapper_obj=None):
        # paragraph=(list)
        # [0] = line
        # [1] = newlines (optional default = 1)
            # -1 = no space
            # 0 = same line with white space
            # 2 - X = number of newlines
        # [2] = color (optional default = cyan)

        console_size = get_terminal_size()  # columns, lines

        initial_indent = subsequent_indent = "  "
        if wrapper_obj is not None:
                initial_indent = wrapper_obj.get("indent","  ")
                subsequent_indent = wrapper_obj.get("sub_indent","  ")
                
        console_setup = TextWrapper()
        console_setup.initial_indent = initial_indent
        console_setup.subsequent_indent = subsequent_indent
        console_setup.width=(console_size.columns - 2)
        attribute = []
        
        try:
            if paragraphs == "wrapper_only":
                return console_setup
        except:
            pass
        
        last_line = ""
        
        for current in paragraphs:
            line = current[0]

            try:
                newlines = current[1]
            except:
                newlines = 1

            ljust_parm = (console_size.columns - (len(line)+16))
            
            if newlines == "full":
                line = line.ljust(ljust_parm,line[0])
                newlines = 1
            elif newlines == "half":
                line = line.ljust((int(ljust_parm/2)),line[0])
                newlines = 1
            
            try:
                if "," in current[3]:
                    attribute = current[3].split(",")
                    line = colored(line,current[2],attrs=[f'{attribute[0]}',f'{attribute[1]}'])
                else:
                    line = colored(line,current[2],attrs=[current[3]])
            except:
                try:
                    if "," in current[2]:
                        c_attrs = current[2].split(",")
                        line = colored(line,c_attrs[0],c_attrs[1])
                    else:
                        line = colored(line,current[2])
                except:
                    line = colored(line,"cyan")

            do_print = True
            if newlines == 0 and last_line == "":
                last_line = line
                do_print = False
            elif newlines == -1:
                last_line = last_line+line
                do_print = False
            elif newlines == 0:
                last_line = last_line+" "+line
                do_print = False
            elif last_line != "":
                line = last_line+" "+line
                last_line = ""
                
            if do_print:
                print(console_setup.fill(line))
                for _ in range(1,newlines):
                    print("") # newlines 
                    
            
    def print_spinner(self,command_obj):
        msg = command_obj.get("msg")
        color = command_obj.get("color","cyan")
        newline = command_obj.get("newline",False)
        clearline = command_obj.get("clearline",True)
        spinner_type = command_obj.get("spinner_type","spinner")
        
        if clearline: self.print_clear_line()
        
        if newline == "top" or newline == "both":
            print("")
        
        def spinning_cursor(stype):
            if stype == "dotted":
                dots = ["   ",".  ",".. ","..."]
                while True:
                    for dot in dots: 
                        yield dot
            else:
                while True:
                    for cursor in '|/-\\':
                        yield cursor

        spinner = spinning_cursor(spinner_type)
        while self.event:
            cursor = next(spinner)
            print(f"  {colored(msg,color)} {colored(cursor,color)}",end="\r")
            sleep(0.3)
            if not self.event:
                self.print_clear_line()

        if newline == "bottom" or newline == "both":
            print("")
            
    
    def print_json_debug(self,obj,exit_on):
        print(json.dumps(obj,indent=3))
        if exit_on:
            exit(1) # auto_restart not affected
            
            
    def print_perftime(self,performance_start, action):
        performance_stop = perf_counter()
        total_time = performance_stop - performance_start
        
        unit = "seconds"
        if total_time > 60:
            total_time = total_time/60
            unit = "minutes"
        
        self.print_paragraphs([
            ["Total",0], [action,0,"yellow","underline"], ["time:",0],
            [f" {round(total_time,3)} ",0,"grey,on_green","bold"],
            [f"{unit}",2],
        ])


    def print_help(self,command_obj):
        nodectl_version_only = command_obj.get("nodectl_version_only",False)
        hint = command_obj.get("hint","None")
        title = command_obj.get("title",False)
        
        command_obj = {
            **command_obj,
            "valid_commands": self.valid_commands
        }
        self.print_clear_line()
        self.log.logger.info(f"Help file print out")
        self.help_text = "" 
        if title:
            self.print_header_title({
                "line1": "NODE GARAGE",
                "line2": "welcome to the help section",
                "newline": "top",
                "clear": True
            })
            
        self.help_text = f"  NODECTL INSTALLED: [{colored(self.version_obj['node_nodectl_version'],'yellow')}]"

        if not nodectl_version_only:
            install_profiles = self.pull_profile({"req":"one_profile_per_env"})
            old_env = None
            for profile in install_profiles:
                env = self.config_obj[profile]["environment"]
                node_tess_version = self.version_obj[env][profile]['node_tess_version']
                if old_env != env:
                    self.help_text += f"\n  {env.upper()} TESSELLATION INSTALLED: [{colored(node_tess_version,'yellow')}]"
                old_env = env

        self.help_text += build_help(self,command_obj)
        
        print(self.help_text)
                
        if "profile" in hint:
            self.print_paragraphs([
                ["HINT:",0,"yellow","bold"],
                ["Did you include the",0,"white"],["-p <profile>",0,"yellow"],
                ["in your command request?",1,"white"],
            ])
        if "env" in hint:
            self.print_paragraphs([
                ["HINT:",0,"yellow","bold"],
                ["Did you include the",0,"white"],["-e <environment_name>",0,"yellow"],
                ["in your command request?",1,"white"],
            ])
            
        elif hint == "unknown":
            print(colored('  Unknown command entered','red'),"\n")
        elif isinstance(hint,str) and hint != "None":
            cprint(f"{  hint}","cyan")
            
        exit(0) # auto_restart not affected
        
    
    def print_auto_restart_warning(self):
        try:
            if self.config_obj["global_auto_restart"]["auto_restart"]:
                self.print_paragraphs([
                    ["",1], ["If",0,"red"], ["global_auto_restart",0,"yellow","bold"], ["is enabled, this is an",0,"red"], ["exception",0,"red","bold"],
                    ["and auto_restart will not reengage. You will have to do this manually.",2,"red"],
                ])      
                if not self.config_obj["global_auto_restart"]["auto_upgrade"]:
                    self.print_paragraphs([
                        [" NOTE ",0, "grey,on_yellow"], ["auto_restart will continue to fail",0],
                        ["if Tessellation versions do not properly match.",2]
                    ]) 
        except:
            return                       
    
    
    # =============================
    # miscellaneous
    # =============================  
                
    def change_connection_color(self,state):
        if state == "ReadyToJoin":
            return "red"
        if state == "Ready":
            return "green"
        else:
            return "yellow"


    def backup_restore_files(self, file_obj):
        files = file_obj["file_list"]
        location = file_obj["location"]
        action = file_obj["action"]
        
        if not self.auto_restart:
            self.print_cmd_status({
                "text_start": f"{action} files",
                "status": "running",
                "newline": False,
                "status_color": "yellow"
            })
        
        for file in files:
            org_path =  f"{location}/{file}"
            backup_path = f"/var/tmp/cnng-{file}"
            bashCommand = False
            if action == "backup":
                if path.exists(org_path):
                    bashCommand = f"sudo cp {org_path} {backup_path}"
            elif action == "restore":
                if path.exists(backup_path):
                    bashCommand = f"sudo mv {backup_path} {org_path}"
            
            if bashCommand:
                self.process_command({
                    "bashCommand": bashCommand,
                    "proc_action": "run"
                }) 
                
        if not self.auto_restart:           
            self.print_cmd_status({
                "text_start": f"{action} files",
                "status": "complete",
                "newline": True,
                "status_color": "green"
            })        
        
        
    def clear_global_profiles(self,profile_list_or_obj):
        if isinstance(profile_list_or_obj,list):
            return [x for x in profile_list_or_obj if "global" not in x]
        return [ x for x in profile_list_or_obj.keys() if "global" not in x]

    
    def cleaner(self, line, action, char=None):
        if action == "dag_count":
            cleaned_line = sub('\D', '', line)
            return cleaned_line[6:]
        elif action == "ansi_escape":
            ansi_escape = compile(r'(\x9B|\x1B\[)[0-?]*[ -\/]*[@-~]')
            return ansi_escape.sub('', line)  
        elif action == "spaces":
            return sub(' ', '', line)                 
        elif action == "commas":
            return sub(',', '', line) 
        elif action == "float_only":
            return sub('[^0-9,.]', '', line)      
        elif action == "new_line":
            return sub('\n', '', line) 
        elif action == "remove_char":
            return sub(char, '', line)  
        elif action == "service_prefix":
            return sub("cnng-","", line)   
        elif action == "trailing_backslash":
            if line[-1] == "/":
                return line[0:-1]
            return line


    def confirm_action(self,command_obj):
        self.log.logger.debug("confirm action request")
        
        yes_no_default = command_obj.get("yes_no_default")
        return_on = command_obj.get("return_on")
        
        prompt = command_obj.get("prompt")
        prompt_color = command_obj.get("prompt_color","cyan")
        exit_if = command_obj.get("exit_if",True)
        strict = command_obj.get("strict",False)

        prompt = f"  {colored(f'{prompt}',prompt_color)} {colored('[',prompt_color)}{colored(yes_no_default,'yellow')}{colored(']: ',prompt_color)}"
        
        valid_options = ["y","n",return_on,yes_no_default]
        
        for _ in range(0,2):
            # double check if there was information waiting in stdin, clearing
            sleep(.2)
            if self.test_for_premature_enter_press():
                input()
        
        if strict:
            valid_options = valid_options[2::]
            
        while True:
            confirm = input(prompt)
            if confirm == "":
                break
            confirm = confirm.lower() if not strict else confirm
            if confirm not in valid_options:
                print(colored("  incorrect input","red"))
            else:
                break
            
        if strict:
            if confirm == return_on:
                return True
        else:
            if yes_no_default == return_on:
                if confirm == "":
                    return True
            if confirm.lower() == str(return_on).lower():
                return True
                
        if exit_if:
            print(colored("  Action has been cancelled","green"))
            exit(0)
        
        return False


    def modify_pass_line(self,line,check_line):
        # pull out password only
        new_line = line[0:-2].replace(check_line,"")
        # replace all " with \"
        new_line = new_line.replace('"','\\"')
        # replace all ! with \!"
        # new_line = new_line.replace('"','\\!')
        # replace all $ with \$"
        new_line = new_line.replace('$','\\$')
        # add the export CL... back in with " surrounding 
        new_line = f'{check_line[:-1]}"{new_line}"\n'
        line = new_line      
        return line
    
           
    def network_unreachable_looper(self):
            seconds = 30
            self.log.logger.warn("network has become unreachable, starting retry loop to avoid error")
            if not self.auto_restart:
                progress = {
                    "text_start": "Network unreachable pausing until reachable",
                    "text_color": "red",
                    "status": f"{seconds}s",
                    "status_color": "yellow",
                    "newline": True,
                }
                self.print_cmd_status(progress)
                self.print_timer(seconds,"to allow network to recover",start=1)
                print(f'\x1b[1A', end='')
                self.print_clear_line()
                self.print_cmd_status({
                    **progress,
                    "status": "retry",
                    "status_color": "green",
                    "delay": .6,
                }) 
                print(f'\x1b[1A', end='')
                self.print_clear_line()
                

    def process_command(self,command_obj):
        # bashCommand, proc_action, autoSplit=True,timeout=180,skip=False,log_error=False,return_error=False
        bashCommand = command_obj.get("bashCommand")
        proc_action = command_obj.get("proc_action")
        
        autoSplit = command_obj.get("autoSplit",True)
        timeout = command_obj.get("timeout",180)
        skip = command_obj.get("skip",False)
        log_error = command_obj.get("log_error",False)
        return_error = command_obj.get("return_error",False)
        working_directory = command_obj.get("working_directory",None)
        
        if proc_action == "timeout":
            if working_directory == None:
                p = Popen(shlexsplit(bashCommand), stdout=PIPE, stderr=PIPE)
            else:
                p = Popen(shlexsplit(bashCommand), cwd=working_directory, stdout=PIPE, stderr=PIPE)
                
            timer = Timer(timeout, p.kill)
            try:
                timer.start()
                # stdout, stderr = p.communicate()
            except Exception as e:
                self.log.logger.error(f"function process command errored out with [{e}]")
            finally:
                timer.cancel()
        
        if proc_action == "pipeline":
            # bashCommand for this should be a list of lists
            # example)
            #     grep_cmd = ["grep","some_string","/var/log/some_file"]
            #     tail_cmd = ["tail","-n","1"]
            #     awk_cmd = ["awk","...","..."]
            
            results = []
            for n, cmd in enumerate(bashCommand):
                if n == 0:
                    results.append(subprocess.Popen(cmd, stdout=subprocess.PIPE))
                    continue
                results.append(subprocess.Popen(bashCommand[n],stdin=results[n-1].stdout, stdout=subprocess.PIPE))
                
            output, _ = results[-1].communicate()
            return output.decode()
    
            
        if proc_action == "subprocess_co":
            output = subprocess.check_output(bashCommand, shell=True, text=True)
            return output
        
        if proc_action == "subprocess_run":
            output = subprocess.run(shlexsplit(bashCommand), shell=True, text=True)
            return output
            
        if autoSplit:
            bashCommand = bashCommand.split()
            
        if proc_action == "call":
            call(bashCommand,
                            stdout=PIPE,
                            stderr=PIPE)
            skip = True
        elif proc_action == "run":
            run(bashCommand,
                            stdout=PIPE,
                            stderr=PIPE)
            skip = True 
        elif proc_action == "no_wait":
            Popen(bashCommand).pid
            skip = True
        elif proc_action == "poll" or proc_action == "wait":
            try:
                p = Popen(bashCommand,            
                                    stdout=PIPE,
                                    stderr=PIPE)
            except Exception as e:
                self.log.logger.error(f"function process command errored out with [{e}]")
                skip = True
           
        if not skip:     
            if proc_action == "wait":
                p.wait()
            elif proc_action == "poll":
                poll = None
                while poll is None:
                    poll = p.poll()
                    
            result, err = p.communicate()

            if err and log_error:
                self.log.logger.error(f"process command [Bash Command] err: [{err}].")
                
            if return_error:
                return err.decode('utf-8')

            if isinstance(result,bytes):
                result = result.decode('utf-8')
                
            return result
        else:
            return    
    

if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")
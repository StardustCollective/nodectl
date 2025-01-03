import math
import random
import json
import urllib3
import csv
import yaml
import select
import socket
import validators
import uuid
import glob
import distro
import cpuinfo

import pytz
from tzlocal import get_localzone

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.fernet import Fernet
import base64

from scapy.all import TCP
from psutil import Process, cpu_percent, virtual_memory, process_iter, disk_usage, AccessDenied, NoSuchProcess
from getpass import getuser
from re import match, sub, compile
from textwrap import TextWrapper
from requests import get, Session
from requests.exceptions import HTTPError, RequestException
from subprocess import Popen, PIPE, call, run, check_output, CalledProcessError, DEVNULL, STDOUT
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from datetime import datetime, timedelta
from termcolor import colored, cprint, RESET
from copy import copy, deepcopy
from time import sleep, perf_counter, time
from shlex import split as shlexsplit
from sshkeyboard import listen_keyboard, stop_listening
from threading import Timer
from urllib.parse import urlparse, urlunparse

from os import system, getenv, path, walk, environ, get_terminal_size, scandir, popen, listdir, remove, chmod, chown
from pwd import getpwnam
from grp import getgrnam
from shutil import copy2, move
from sys import exit, stdout, stdin
from pathlib import Path
from types import SimpleNamespace
from packaging import version
from .troubleshoot.help import build_help
from pycoingecko import CoinGeckoAPI

from .troubleshoot.errors import Error_codes
from .troubleshoot.logger import Logging

class TerminateFunctionsException(Exception): pass

class Functions():

    def __init__(self,config_obj):
        self.sudo_rights = config_obj.get("sudo_rights", True)
        if self.sudo_rights:
            self.log = Logging()
        # set self.version_obj before calling set_statics
        self.config_obj = config_obj
        self.nodectl_path = "/var/tessellation/nodectl/"  # required here for configurator first run
        self.nodectl_code_name = "Princess Warrior"
        self.version_obj = False
        self.cancel_event = False
        self.valid_commands = []


    def set_statics(self):
        self.set_install_statics()
        self.set_error_obj()      
        # versioning
        self.node_nodectl_version = self.version_obj["node_nodectl_version"]
        self.node_nodectl_version_github = self.version_obj["nodectl_github_version"]
        self.node_nodectl_yaml_version = self.version_obj["node_nodectl_yaml_version"]

        urllib3.disable_warnings()

        # constellation nodectl statics
        self.nodectl_profiles_url = f'https://github.com/StardustCollective/nodectl/tree/{self.node_nodectl_version_github}/predefined_configs'
        # https://github.com/StardustCollective/nodectl/tree/nodectl_v2130/predefined_configs
        self.nodectl_profiles_url_raw = f"https://raw.githubusercontent.com/StardustCollective/nodectl/{self.node_nodectl_version_github}/predefined_configs"
        
        # nodectl metagraph custom statics (main branch only) 
        self.nodectl_includes_url = f'https://github.com/StardustCollective/nodectl/tree/main/predefined_configs/includes'
        self.nodectl_includes_url_raw = f"https://raw.githubusercontent.com/StardustCollective/nodectl/main/predefined_configs/includes"
        self.nodectl_download_url = f"https://github.com/stardustCollective/nodectl/releases/download/{self.node_nodectl_version}"
        # Tessellation reusable lists
        self.not_on_network_list = self.get_node_states("not_on_network",True)
        self.pre_consensus_list = self.get_node_states("pre_consensus",True)
        self.our_node_id = ""
        self.join_timeout = 300 # 5 minutes
        self.session_timeout = 2 # seconds
        
        try:
            for profile in self.config_obj.keys():
                if "global" not in profile:
                    self.environment_name = self.config_obj[profile]["environment"]
                    break
        except:
            self.environment_name = False
            
        self.default_profile = None
        self.default_edge_point = {}
        self.link_types = ["ml0","gl0"]   
        self.environment_names = []
             
        self.event = False # used for different threading events
        self.status_dots = False # used for different threading events
        
        self.auto_restart = True if self.config_obj["global_elements"]["caller"] == "auto_restart" else False
        ignore_defaults = ["config","install","installer","auto_restart","ts","debug"]
        if self.config_obj["global_elements"]["caller"] not in ignore_defaults: self.set_default_variables({})


    def set_error_obj(self):
        self.error_messages = Error_codes(self.config_obj) 
        return
    

    def set_install_statics(self):
        self.lb_urls = {
            "testnet": ["l0-lb-testnet.constellationnetwork.io",443],
            "mainnet": ["l0-lb-mainnet.constellationnetwork.io",443],
            "integrationnet": ["l0-lb-integrationnet.constellationnetwork.io",443],
            "dor-metagraph": ["54.191.143.191",9000] 
        }
        
        self.default_tessellation_dir = "/var/tessellation/"
        self.default_backup_location = "/var/tessellation/backups/"
        self.default_upload_location = "/var/tessellation/uploads/"
        
        self.default_seed_location = "/var/tessellation/"
        self.default_seed_file = "seedlist"
        
        self.default_priority_source_location = "/var/tessellation/"
        self.default_priority_source_file = "priority-source-list"
        
        self.default_pro_rating_file = "ratings.csv"
        self.default_pro_rating_location = "/var/tessellation"
        self.default_includes_path = '/var/tessellation/nodectl/includes/'
        self.default_tessellation_repo = "https://github.com/Constellation-Labs/tessellation"
        
        # constellation specific statics
        self.be_urls = {
            "testnet": "be-testnet.constellationnetwork.io",
            "mainnet": "be-mainnet.constellationnetwork.io",
            "dor-metagraph": "be-mainnet.constellationnetwork.io",
            "integrationnet": "be-integrationnet.constellationnetwork.io",
        }
        self.snapshot_type = "global-snapshots"


    # =============================
    # getter functions
    # =============================
        
    def get_local_coin_db(self):
        # https://www.coingecko.com/api/documentation
        # curl -X 'GET' \ 'https://api.coingecko.com/api/v3/coins/list?include_platform=false' \ -H 'accept: application/json'
        # https://api.coingecko.com/api/v3/coins/list?include_platform=false
        try:
            from .data.coingecko_coin_list import coin_gecko_db
            return coin_gecko_db
        except Exception as e:
            self.log.logger.error(f"functions -> get_local_coin_db -> error occurerd, skipping with error [{e}]")
            cprint("  An unknown error occured, please try again","red")
        

    def get_crypto_price(self):
        # The last element is used for balance calculations
        # It is not used by the show prices command

        def test_for_api_outage(coin_prices):

            for ticker_id in coin_prices.keys():
                try:
                    coin_prices[ticker_id]['usd']
                except:
                    coin_prices[ticker_id]['usd'] = 0.00

            return coin_prices
            
        updated_coin_prices = {}
        # In the circumstance that CoinGecko is down *rare but happens*
        # This is a quick timeout check before attempting to download pricing
        self.create_coingecko_obj()
        check_ids = 'constellation-labs,lattice-token,Dor,bitcoin,ethereum,quant-network'

        if self.config_obj[self.default_profile]["token_coin_id"] != "Dor" and self.config_obj[self.default_profile]["token_coin_id"] != "constellation-labs":
            check_ids += f',{self.config_obj[self.default_profile]["token_coin_id"]}'

        try:
            coin_prices = self.cg.get_price(ids=check_ids, vs_currencies='usd')
            # used for debugging to avoid api hitting attempts peridium 
            # coin_prices = {'bitcoin': {'usd': 43097}, 'constellation-labs': {'usd': 0.051318}, 'dor': {'usd': 0.04198262}, 'ethereum': {'usd': 2305.3}, 'lattice-token': {'usd': 0.119092}, 'quant-network': {'usd': 103.24}, 'solana': {'usd': 97.75}}
        except Exception as e:
            self.log.logger.error(f"coingecko response error | {e}")
            if not self.auto_restart:
                cprint("  Unable to process CoinGecko results...","red")
        else:
            # replace pricing list properly
            coin_prices = test_for_api_outage(coin_prices)
            coins = self.get_local_coin_db()
            if coins:
                updated_coin_prices = deepcopy(coin_prices)
                for coin in coins:
                    for cid in coin_prices.keys():
                        if coin['id'] == cid:
                            updated_coin_prices[cid] = {
                                **updated_coin_prices[cid],
                                "symbol": coin["symbol"],
                                "formatted": "${:,.3f}".format(updated_coin_prices[coin['id']]['usd'])
                            }

        return updated_coin_prices


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
        count_consensus = command_obj.get("count_consensus",False)

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
        
        if count_consensus:
            consensus_count = self.get_cluster_info_list({
                "ip_address": ip_address,
                "port": api_port,
                "api_endpoint": "/consensus/latest/peers",
                "spinner": False,
                "attempt_range": 4,
                "error_secs": 3
            })
            try:
                consensus_count = consensus_count.pop()
            except:
                consensus_count = {'nodectl_found_peer_count': "UnableToDerive"}
        else:
            consensus_count = {'nodectl_found_peer_count': "UnableToDerive"}
        
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
                session = self.set_request_session()
                session.verify = False
                session.timeout = 2
                url = f"http://{cluster_ip}:{api_port}/cluster/info"
                peers = session.get(url,timeout=self.session_timeout)
            except:
                if attempts > 3:
                    return "error"
                attempts = attempts+1
            else:
                break
            finally:
                session.close()

        try:
            peers = peers.json()
        except:
            pass
        else:
            ip_address = self.ip_address if ip_address == "127.0.0.1" or ip_address == "self" else ip_address
            id_ip = ("ip","id") if len(ip_address) < 128 else ("id","ip")
            try:
                for line in peers:
                    if ip_address in line[id_ip[0]]:
                        if pull_node_id:
                            self.our_node_id = line[id_ip[1]]
                            return
                        node_online = True
                        peer_list.append(line[id_ip[0]])
                        peers_publicport.append(line['publicPort'])
                        pull_states(line)
                        state_list.append("*")
                    else:
                        # append state abbreviations
                        for state in node_states:
                            if state[0] in line["state"]:
                                pull_states(line)
                                peer_list.append(line[id_ip[0]])
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
                "consensus_count": consensus_count["nodectl_found_peer_count"],
                "ready_count": len(peers_ready),
                "node_online": node_online
            }


    def get_node_states(self,types="all",state_list=False):
        if types == "all":
            node_states = [
                ('Initial','i*'),
                ('ReadyToJoin','rtj*'),
                ('StartingSession','ss*'),
                ('SessionStarted','s*'),
                ('ReadyToDownload','rtd*'),
                ('WaitingForDownload','wfd*'),
                ('DownloadInProgress','dip*'),
                ('Observing','ob*'),
                ('WaitingForReady','wr*'),
                ('WaitingForObserving','wo*'),
                ('Ready',''),
                ('Leaving','l*'),
                ('Offline','o*'),
                ('ApiNotReady','ar*'),
                ('ApiNotResponding','anr*'),
                ('SessionIgnored','si*'),
                ('SessionNotFound','snf*'),
            ]
        elif types == "on_network" or types == "pre_consensus" or types == "on_network_and_stuck":
            node_states = [
                ('Observing','ob*'),
                ('WaitingForReady','wfr*'),
                ('WaitingForObserving','wfo*'),
                ('DownloadInProgress','dip*'),
                ('Ready',''),
            ]
            if types == "pre_consensus":
                node_states.pop()
            elif types == "on_network_and_stuck":
                node_states.append(("WaitingForDownload",'wfd*'))
        elif types == "not_on_network":
            node_states = [
                ('Initial','i*'),
                ('ReadyToJoin','rtj*'),
                ('StartingSession','ss*'),
                ('SessionStarted','s*'),
                ('ApiNotResponding','anr*'),
                ('Offline','o*'),
                ('ApiNotReady','ar*'),
            ]
        elif types == "stuck_in_states":
            node_states = [
                ('Observing','ob*'),
                ('WaitingForDownload','wfd*'),
                ('WaitingForReady','wfr*'),
                ('SessionStarted','s*'),
            ]
        elif types == "past_dip":
            node_states = [
                ('WaitingForObserving','wfo*'),
                ('Observing','ob*'),
                ('WaitingForReady','wfr*'),
                ('Ready',''),
            ]            
        elif types == "past_observing":
            node_states = [
                ('WaitingForReady','wfr*'),
                ('Ready',''),
            ]            
        elif types == "ready_states":
            node_states = [
                ('ReadyToJoin','rtj*'),
                ('Ready',''),
            ]            
        elif types == "nodectl_only":
            node_states = [
                ('ApiNotReady','ar*'),
                ('ApiNotResponding','anr*'),
                ('SessionIgnored','si*'),
                ('SessionNotFound','snf*'),
            ]            
        
        if state_list:
            return list(list(zip(*node_states))[0])
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
        
        service_names = self.profile_names + ["node_restart@","node_version_updater"]
        service_names = self.clear_global_profiles(service_names)
        self.config_obj["global_elements"]["node_service_status"]["service_list"] = service_names

        for service in service_names:
            service_name = service+".service"
            if service in self.profile_names:
                service_name = f"cnng-{self.config_obj[service]['service']}"

            service_status = self.process_command({
                "bashCommand": f"systemctl is-active --quiet {service_name}",
                "proc_action": "subprocess_return_code",
            })

            if service_status == 0:
                self.config_obj["global_elements"]["node_service_status"][service] = "active"
            elif service_status == 768 or service_status == 3:
                self.config_obj["global_elements"]["node_service_status"][service] = "inactive"
            else:

                self.config_obj["global_elements"]["node_service_status"][service] = f"exit code"
            self.config_obj["global_elements"]["node_service_status"][f"{service}_service_return_code"] = service_status  

            for process in process_iter():
                if service in self.profile_names:
                    find_string = self.config_obj[service]["jar_file"]
                elif "node_version_updater" in service:
                    find_string = "uvos"
                elif "restart" in service:
                    find_string = "service_restart"
                try:
                    cmdline = process.cmdline()[1:]
                except IndexError:
                    continue
                except AccessDenied:
                    continue
                except NoSuchProcess:
                    continue
                for item in cmdline:
                    if find_string in item:
                        self.config_obj["global_elements"]["node_service_status"][f"{service}_service_pid"] = process.pid

            try:
                _ = self.config_obj["global_elements"]["node_service_status"][f"{service}_service_pid"]
            except KeyError:
                self.config_obj["global_elements"]["node_service_status"][f"{service}_service_pid"] = "??"
            if self.config_obj["global_elements"]["node_service_status"][f"{service}_service_return_code"] > 0:
                self.config_obj["global_elements"]["node_service_status"][f"{service}_service_pid"] = "n/a"

        self.log.logger.debug(f'get_service_status -> [{service}] -> [{service_status}] [{self.config_obj["global_elements"]["node_service_status"][service]}]')


    def get_date_time(self,command_obj):
        action = command_obj.get("action",False)
        backward = command_obj.get("backward",True) 
        r_days = command_obj.get("days",False) # requested days
        elapsed = command_obj.get("elapsed",False)
        old_time = command_obj.get("old_time",False)
        new_time = command_obj.get("new_time",False)
        time_part = command_obj.get("time_part",False)
        time_zone = command_obj.get("time_zone",False)
        format = command_obj.get("format",False)

        if not format: 
            format = command_obj.get("format", "%Y-%m-%d-%H:%M:%SZ")

        return_format = command_obj.get("return_format","string")
        
        if not new_time: new_time = datetime.now()
        if not old_time: old_time = datetime.now()

        if action == "date":
            return new_time.strftime("%Y-%m-%d")
        elif action == "convert_to_datetime":
            new_time = datetime.fromtimestamp(new_time)
            return new_time.strftime(format)
        elif action == "datetime":
            utc_now = datetime.now(pytz.utc)
            if time_zone == "self":
                local_now = utc_now.astimezone(get_localzone())
                return local_now.strftime(format)
            elif time_zone:
                return utc_now.astimezone(pytz.timezone(time_zone)).strftime(format)
            return new_time.strftime(format)
        elif action == "get_elapsed":
            try: old_time = datetime.strptime(old_time, format)
            except: pass # already in proper format
            if isinstance(new_time,str):
                new_time = datetime.strptime(new_time, format)
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
            return elapsed.strftime(format)
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
            test1 = datetime.strptime(old_time, format)
            test2 = datetime.strptime(new_time, format)
            if getattr(test1, time_part) != getattr(test2, time_part):
                return True  # There is a difference            
            return False
        elif action == "valid_datetime":
            unix = False
            try: 
                new_time = int(new_time)
                unix = True
            except: pass

            date_formats = [
                "%Y-%m-%d",
                "%d-%m-%Y",
                "%m/%d/%Y",
                "%d/%m/%Y",
                "%Y-%m-%d %H:%M:%S",
                "%d-%m-%Y %H:%M:%S",
                "%m/%d/%Y %H:%M:%S",
                "%d/%m/%Y %H:%M:%S",
                "%H:%M:%S",
                "%H:%M",
                "%Y-%m-%d.%H",
                '%Y-%m-%d z%H%M', 
                '%Y-%m-%d Z%H%M'
            ]
            for fmt in date_formats:
                try:
                    if unix:
                        datetime.fromtimestamp(new_time)
                    else:
                        datetime.strptime(new_time, fmt)
                    return True
                except ValueError:
                    continue
            return False
        else:
            # if the action is default 
            return_val = new_time+timedelta(days=r_days)
            if backward:
                return_val = new_time-timedelta(days=r_days)
        
        return return_val.strftime("%Y-%m-%d")
        

    def get_distro_details(self):
        info = cpuinfo.get_cpu_info()
        return {
            "arch": info.get('arch'),
            **distro.lsb_release_info(),
            "info": info,
        }


    def get_percentage_complete(self, command_obj):
        start = command_obj["start"]
        end = command_obj["end"]
        current = command_obj["current"]
        absolute = command_obj.get("absolute", False)
        backwards = command_obj.get("backwards", False)
        set_current = command_obj.get("set_current","end")
        
        if set_current == "end":
            set_current = end
        else:
            set_current = start
        
        if not absolute: 
            if current < start:
                return 0
        
        elif current >= end:
            return 100
        
        if backwards:
            total_range = end - start
            current_range = abs(total_range)
            percentage = 100 - (1 - current_range / start) * 100
        else:
            percentage = (current / end) * 100

        return round(percentage,2) 
    

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
        random_node = True

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
            for n in range(0,3):
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
                    
                if not cluster_info and n > 2:
                    if self.auto_restart:
                        return False
                    if random_node and self.config_obj["global_elements"]["use_offline"]:
                        self.log.logger.warning("functions -> get_info_from_edge_point -> LB may not be accessible, trying local.")
                        random_node = False
                        self.config_obj[profile]["edge_point"] = self.get_ext_ip()
                        self.config_obj[profile]["edge_point_tcp_port"] = self.config_obj[profile]["public_port"]
                        self.config_obj[profile]["static_peer"] = True 
                    else:               
                        self.error_messages.error_code_messages({
                            "error_code": "fnt-725",
                            "line_code": "lb_not_up",
                            "extra": f'{self.config_obj[profile]["edge_point"]}:{self.config_obj[profile]["edge_point_tcp_port"]}',
                            "extra2": self.config_obj[profile]["layer"],
                        })
                if not cluster_info and n > 0:
                    sleep(.8)
                else:
                    break
                
            cluster_info_tmp = deepcopy(cluster_info)
            try:
                self.log.logger.debug(f"get_info_from_edge_point --> edge_point info request result size: [{cluster_info[-1]['nodectl_found_peer_count']}]")
            except:
                self.log.logger.debug(f"get_info_from_edge_point --> edge_point info request no results")
            
            try:
                cluster_info_tmp.pop()
            except:
                if threaded: 
                    self.log.logger.error("get_info_from_edge_point reached error while threaded, error skipped")
                    cprint("  error attempting to reach edge point","red")
                else:
                    if self.config_obj["global_elements"]["use_offline"]:
                        return False
                    else:
                        self.error_messages.error_code_messages({
                            "error_code": "fnt-648",
                            "line_code": "off_network",
                            "extra": f'{self.config_obj[profile]["edge_point"]}:{self.config_obj[profile]["edge_point_tcp_port"]}',
                            "extra2": self.config_obj[profile]["layer"],
                        })
            
            for n in range(0,max_range):
                try:
                    node = random.choice(cluster_info_tmp)
                except:
                    self.error_messages.error_code_messages({
                        "error_code": "fnt-745",
                        "line_code": "api_error",
                        "extra": profile,
                        "extra2": self.config_obj[profile]["edge_point"],
                    })

                if specific_ip:
                    id_ip = "id" if len(specific_ip) > 127 else "ip"
                    specific_ip = self.ip_address if specific_ip == "127.0.0.1" else specific_ip
                    for i_node in cluster_info_tmp:
                        if specific_ip == i_node[id_ip]:
                            node = i_node
                            break

                if node == self.ip_address:
                    self.log.logger.debug(f"get_info_from_edge_point --> api_endpoint: [{api_str}] node picked was self, trying again: attempt [{n}] of [{max_range}]")
                    continue # avoid picking "ourself"
                
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
                    self.log.logger.warning(f"unable to find a Node with a State object, trying again | error {e}")
                    sleep(1)
                if n > 9:
                    self.log.logger.error(f"unable to find a Node on the current cluster with [{desired_key}] == [{desired_value}]") 
                    if not self.auto_restart:
                        print(colored("  WARNING:","yellow",attrs=['bold']),colored(f"unable to find node in [{desired_value}]","red"))
                        self.print_timer({
                            "seconds": 10,
                            "phrase": ""
                        })

        
    def get_api_node_info(self,command_obj):
        # api_host=(str), api_port=(int), info_list=(list)
        api_host = command_obj.get("api_host")
        api_port = command_obj.get("api_port")
        api_endpoint = command_obj.get("api_endpoint","/node/info")
        info_list = command_obj.get("info_list",["all"])
        tolerance = command_obj.get("tolerance",2)
        
        # dictionary
        #  api_host: to do api call against
        #  api_port: for the L0 or cluster/metagraph channel
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
                r_session = self.set_request_session()
                r_session.timeout = (2,2)
                r_session.verify = False
                session = r_session.get(api_url, timeout=self.session_timeout).json()
            except:
                self.log.logger.error(f"get_api_node_info - unable to pull request | test address [{api_host}] public_api_port [{api_port}] attempt [{n}]")
                if n == tolerance-1:
                    self.log.logger.warning(f"get_api_node_info - trying again attempt [{n} of [{tolerance}]")
                    return None
                sleep(1.5)
            else:
                break
            finally:
                r_session.close()

        if len(session) < 2 and "data" in session.keys():
            session = session["data"]
        
        self.log.logger.debug(f"get_api_node_info --> session [{session}] returned from node address [{api_host}] public_api_port [{api_port}]")
        try:
            for info in info_list:
                result_list.append(session[info])
        except:
            self.log.logger.warning(f"Node was not able to retrieve [{info}] of [{info_list}] returning None")
            return "LB_Not_Ready"
        else:
            if "reason" in session.keys():
                if session["reason"] == "Load balancer is currently under a maintenance mode due to cluster upgrade.":
                    return "LB_Not_Ready" 
            return result_list


    def get_from_api(self,url,utype,tolerance=5):
        
        is_json = True if utype == "json" else False
        for n in range(1,tolerance+2):
            try:
                session = self.set_request_session(False,is_json)
                session.timeout = 2
                if utype == "json":
                    response = session.get(url, timeout=self.session_timeout).json()
                else:
                    response = session.get(url, timeout=self.session_timeout)
            except Exception as e:
                print(response.text)
                self.log.logger.error(f"unable to reach profiles repo list with error [{e}] attempt [{n}] of [3]")
                if n > tolerance:
                    self.error_messages.error_code_messages({
                        "error_code": "fnt-876",
                        "line_code": "api_error",
                        "extra2": url,
                        "extra": None
                    })
                sleep(.5)
            else:
                if utype == "yaml_raw":
                    return response.content.decode("utf-8").replace("\n","").replace(" ","")
                elif utype == "yaml":
                    return yaml.safe_load(response.content)
                return response
            finally:
                session.close()
                        
                    
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
                    session = self.set_request_session()
                    session.verify = False
                    session.timeout=2
                    results = session.get(uri, timeout=self.session_timeout).json()
                except:
                    if n > var.attempt_range:
                        if not self.auto_restart:
                            self.network_unreachable_looper()
                        else:
                            self.event = False
                            return
                    self.log.logger.warning(f"attempt to pull details for LB failed, trying again - attempt [{n+1}] of [10] - sleeping [{var.error_secs}s]")
                    sleep(var.error_secs)
                else:
                    if "consensus" in var.api_endpoint:
                        results = results["peers"]
                    try:
                        results.append({
                            "nodectl_found_peer_count": len(results)
                        })
                    except:
                        self.log.logger.warning("network may have become unavailable during cluster_info_list verification checking.")
                        results = [{"nodectl_found_peer_count": 0}]
                finally:
                    session.close()
                    
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
        options = command_obj.get("options",["any_key"])
        prompt = command_obj.get("prompt","")
        prompt_color = command_obj.get("prompt_color","magenta")
        debug = command_obj.get("debug",False)
        quit_option = command_obj.get("quit_option",False)
        quit_with_exception = command_obj.get("quit_with_exception",False)
        parent = command_obj.get("parent",False)
        display = command_obj.get("display",True)
        mobile = command_obj.get("mobile",False)

        self.key_pressed = None
        if prompt == None: prompt = ""
        
        invalid_str = f"  {colored(' Invalid ','yellow','on_red',attrs=['bold'])}: {colored('only','red')} "
        for option in options:
            invalid_str += f"{colored(option,'white',attrs=['bold'])}, " if option != options[-1] else f"{colored(option,'white',attrs=['bold'])}"
        invalid_str = colored(invalid_str,"red")
                
        if display:
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
                if display:
                    print(f"{invalid_str} {colored('options','red')}")
                    cprint("  are accepted, please try again","red")

        try:
            listen_keyboard(
                on_press=press,
                delay_second_char=0.75,
            )
        except Exception as e:
            self.log.logger.warning(f"functions -> spinner exited with [{e}]")
            
        if options[0] == "any_key" and quit_with_exception:
            if parent:
                parent.terminate_program = True

        if display: print("")
        if quit_option and (self.key_pressed.upper() == quit_option.upper()):
            if display:
                self.print_clear_line()
                cprint("  Action cancelled by User","yellow")
            if quit_with_exception:
                self.cancel_event = True
                if parent:
                    parent.terminate_program = True
                    parent.clear_and_exit(False)
                raise TerminateFunctionsException("spinner cancel")
            if mobile: return "q"
            exit(0)
            
        try: _ = self.key_pressed.lower()  # avoid NoneType error
        except: return
        return self.key_pressed.lower()


    def get_size(self,start_path = '.',single=False):
        try:
            single = self.status_single_file
        except:
            # this is an exception for health command
            pass

        if single:
            try:
                return path.getsize(start_path)
            except:
                return False
        total_size = 0
        for dirpath, dirnames, filenames in walk(start_path):
            for f in filenames:
                fp = path.join(dirpath, f)
                # skip if it is symbolic link
                if not path.islink(fp):
                    total_size += path.getsize(fp)
        
        return total_size  
    

    def get_paths(self, r_dir):
        for dirpath, _, filenames in walk(r_dir):
            for filename in filenames:
                yield path.join(dirpath, filename)


    def get_dir_size(self, r_path=".",workers=False):
        total = 0
        if not workers:
            if path.exists(r_path):
                with scandir(r_path) as it:
                    for entry in it:
                        if entry.is_file():
                            total += entry.stat().st_size
                        elif entry.is_dir():
                            total += self.get_dir_size(entry.path)
            return total
        
        total = 0
        file_paths = list(self.get_paths(r_path))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            sizes = list(executor.map(self.get_size, file_paths))

        sizes = [0 if x is False else x for x in sizes]
        return sum(sizes)
    

    def check_dev_device(self):
        cmd = 'df -h | awk \'$NF=="/"{print $5 " of " $2}\''
        device = popen(cmd)
        device = device.read()
        if device: return device
        return "unknown"
    
    
    def get_snapshot(self,command_obj):
        action = command_obj.get("action","latest")
        ordinal = command_obj.get("ordinal",False)
        history = command_obj.get("history",50)
        environment = command_obj.get("environment","mainnet")
        profile = command_obj.get("profile",self.default_profile)
        return_values = command_obj.get("return_values",False) # list
        lookup_uri = command_obj.get("lookup_uri",self.set_proof_uri({"environment":environment, "profile": profile}))
        header = command_obj.get("header","normal")
        get_results = command_obj.get("get_results","data")
        return_type =  command_obj.get("return_type","list")
        
        json = True if header == "json" else False
        return_data = []
        error_secs = 2
        
        self.set_proof_uri({"environment":environment, "profile": profile},True)
        
        if action == "latest":
            uri = f"{lookup_uri}/{self.snapshot_type}/latest"
            if not return_values: return_values = ["timestamp","ordinal"]
        elif action == "history":
            uri = f"{lookup_uri}/{self.snapshot_type}?limit={history}"
            return_type = "raw"
        elif action == "ordinal":
            uri = f"{lookup_uri}/{self.snapshot_type}/{ordinal}"
        elif action == "rewards":
            uri = f"{lookup_uri}/{self.snapshot_type}/{ordinal}/rewards"
            if not return_values: return_values = ["destination"]
            return_type = "dict"
        
        try:
            session = self.set_request_session(False,json)
            session.verify = False
            session.timeout = 2
            results = session.get(uri, timeout=self.session_timeout).json()
            results = results[get_results]
        except Exception as e:
            self.log.logger.warning(f"get_snapshot -> attempt to access backend explorer or localhost ap failed with | [{e}] | url [{uri}]")
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
        finally:
            session.close()


    def get_list_of_files(self,command_obj):
        paths = command_obj.get("paths") # list
        files = command_obj.get("files") # list - *.extension or full file name
        
        excludes = [command_obj.get("exclude_paths",False)] # list
        excludes.append(command_obj.get("exclude_files",False)) # list
        
        possible_found = {}
        clean_up = {}

        for i_path in paths:
            try:
                for file in files:
                    for n,f_path in enumerate(Path(f'/{i_path}').rglob(file)):
                        possible_found[f"{n+1}"] = f"{f_path}"
            except:
                self.log.logger.warning(f"unable to process path search | [/{i_path}/]")
            
        for i, file in possible_found.items():
            file = file.replace("//","/")
            clean_up[i] = file
        possible_found = deepcopy(clean_up)

        for n,exclude in enumerate(excludes):  
            if exclude:
                for item in exclude:
                    for key, found in clean_up.items():
                        if item in found:
                            try:
                                possible_found.pop(key)
                            except:
                                pass
                
        return possible_found
    

    def get_uuid(self):
        return str(uuid.uuid4())
    

    def get_persist_hash(self, command_obj):
        pass1 = command_obj["pass1"]
        enc_data = command_obj.get("enc_data",False)
        salt2 = command_obj.get("salt2",False)
        profile = command_obj.get("profile",False)
        test_only = command_obj.get("test_only",False)

        ekf = "/etc/security/cnngsenc.conf"

        if not enc_data:
            salt = self.get_uuid()
            salt = f"{salt2[:6]}{salt}"
            salt += "0" * (32 - len(salt))
            salt = salt[:32]
            try:
                salt = base64.urlsafe_b64decode(salt)
            # except binascii.Error as e:
            except Exception as e:
                self.log.logger.critical(f"Invalid salt base64 encoding: {e}")
                self.error_messages.error_code_messages({
                    "error_code": "fnt-1079",
                    "line_code": "system_error",
                    "extra": "encryption generation issue.",
                })

            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA3_512(),
                iterations=1311313,
                salt=salt,
                length=32,
                backend=default_backend(),
            )
            key = kdf.derive(pass1.encode())
            fernet_key = base64.urlsafe_b64encode(key)
            enc_key = Fernet(fernet_key)
            fernet_key = fernet_key.decode()
            enc_data = enc_key.encrypt(pass1.encode()).decode()
            return (enc_data,fernet_key)

        if not path.exists(ekf):
            self.error_messages.error_code_messages({
                "error_code": "fnt-1100",
                "line_code": "system_error",
                "extra": "encryption issue found, unable to decrypt",
            })

        with open(ekf,"r") as f:
            for line in f.readlines():
                if profile in line:
                    key = line
                    break
        try:
            key = key.split(":")
            kdf = key[2].encode()
            dec = key[-1].strip("\n")
            enc_key = Fernet(kdf)
            de = [(int(dec[i], 16), int(dec[i + 1], 16)) for i in range(0, len(dec), 2)]
            de_list = [""]*len(de)
            index = 0
            for i, length in de:
                de_list[i] = pass1[index:index + length]
                index += length        
            pass1 = ''.join(de_list).encode()
        except:
            self.log.logger.critical("unable to decrypt passphrase, please verify settings.")
            return None

        try:
            decrypt_data = enc_key.decrypt(pass1)
            return decrypt_data.decode()
        except Exception as e:  # Catch any exceptions during decryption
            self.log.logger.critical(f"Decryption failed: [{e}]")
            if test_only: return False
            self.error_messages.error_code_messages({
                "error_code": "fnt-1108",
                "line_code": "system_error",
                "extra": "encryption generation issue.",
            })
            exit(0)


    def get_includes(self,remote=False):

        if remote:
            include_params = self.get_from_api(
                self.nodectl_includes_url,
                "json",
            )["payload"]["tree"]["items"]

            # this code can be reused via pull_remote_profiles
            for file in include_params:
                if "includes" in file["path"] and "yaml" in file["name"]:
                    f_url = f"{self.nodectl_includes_url_raw}/{file['name']}" 
                    details = self.get_from_api(f_url,"yaml")
                    main_key = list(details.keys())
                    if len(main_key) > 1:
                        self.log.logger.warning(f"config --> while handling includes, an invalid include file was loaded and ignored. [{main_key}]")
                    else:
                        self.config_obj["global_elements"][main_key[0]] = {}
                        for key, value in details[main_key[0]].items():
                            self.config_obj["global_elements"][main_key[0]][key] = value                       

        if remote == "remote_only": return

        if not path.exists(self.default_includes_path):
            self.log.logger.info(f'configuration -> no includes directory found; however, includes has been found as [{self.config_obj["global_elements"]["includes"]}] skipping local includes.')     
            return

        self.log.logger.warning("config -> includes directory found, all found local configuration information will overwrite any remote details, if they both exist.")
        yaml_data = {}
        try:
            for filename in listdir(self.default_includes_path):
                if filename.endswith('.yaml'):
                    filepath = path.join(self.default_includes_path, filename)
                    self.log.logger.info(f"functions -> get_includes -> loading local [{filepath}] data into configuration.")
                    with open(filepath, 'r') as file:
                        try:
                            yaml_data = yaml.safe_load(file)
                            self.config_obj["global_elements"] = {
                                **self.config_obj["global_elements"],
                                **yaml_data,
                            }
                        except Exception as e:
                            self.log.logger.warning(f"functions -> get_includes -> found an invalid yaml include file [{file}] -> ignoring with [{e}]")
                            continue
        except Exception as e:
            self.log.logger.warning("functions -> get_includes -> found possible empty includes, nothing to do")

        return
    

    def get_version(self):
        pass
        # versioning = Versioning({
        #     "config_obj": self.config_obj,
        #     "show_spinner": False,
        #     "print_messages": False,
        #     "called_cmd": "functions",
        # })     
        # return versioning.get_version_obj()


    def get_memory(self):
        return virtual_memory()


    def get_disk(self):
        return disk_usage('/')
    

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
    

    def set_proof_uri(self,command_obj,snap_type_only=False):   
        profile = command_obj.get("profile",self.default_profile) 
        environment = command_obj.get("environment",self.environment_name)  
        ti = False
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        if self.config_obj[profile]["token_identifier"] != "disable":
            ti = self.config_obj[profile]["token_identifier"] 
            self.snapshot_type = "snapshots"
        else:
            self.snapshot_type = "global-snapshots"

        if snap_type_only: return
        
        if ti:
            api_uri = f"https://{self.be_urls[environment]}/currency/{ti}"
        else:
            api_uri = f"https://{self.be_urls[environment]}"

        return api_uri


    def set_default_variables(self,command_obj):
        # set default profile
        # set default edge point
        profile = command_obj.get("profile",None)
        skip_error = command_obj.get("skip_error",False)
        profiles_only = command_obj.get("profiles_only",False)
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
            except Exception as e:
                self.log.logger.error(f"functions unable to process profile while setting up default values | error [{e}]")
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
        
        if profiles_only: return

        self.set_environment_names()
        self.ip_address = self.get_ext_ip()

        if not self.auto_restart: self.check_config_environment()
                

    def set_environment_names(self):
        try:
            _ = self.environment_names
        except:
            self.environment_names = list()

        for i_profile in self.profile_names:
            if self.config_obj[i_profile]["profile_enable"]:
                self.environment_names.append(self.config_obj[i_profile]["environment"])
        self.environment_names = list(set(self.environment_names))


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
                    self.config_obj[profile]["directory_backups"] = self.default_backup_location 
                if self.config_obj[profile]["directory_uploads"] == "default": # otherwise already set
                    self.config_obj[profile]["directory_uploads"] = self.default_upload_location 
                if self.config_obj[profile]["seed_location"] == "default": # otherwise already set
                    self.config_obj[profile]["seed_location"] = self.default_seed_location 
                if self.config_obj[profile]["priority_source_location"] == "default": # otherwise already set
                    self.config_obj[profile]["priority_source_location"] = self.default_priority_source_location
                if self.config_obj[profile]["pro_rating_location"] == "default": # otherwise already set
                    self.config_obj[profile]["pro_rating_location"] = self.default_pro_rating_location
                 
            # currently not configurable
            self.config_obj[profile]["directory_logs"] = f"/var/tessellation/{profile}/logs/"   
            self.config_obj[profile]["directory_archived"] = f"/var/tessellation/{profile}/logs/archived"  
            self.config_obj[profile]["directory_json_logs"] = f"/var/tessellation/{profile}/logs/json_logs"  
            
            
    def set_system_prompt(self,username):
        prompt_update = r"'\[\e[1;34m\]\u@Constellation-Node:\w\$\[\e[0m\] '"
        prompt_update = f"PS1={prompt_update}"
        bashrc_file = f"/home/{username}/.bashrc"

        is_prompt_there = self.test_or_replace_line_in_file({
            "file_path": bashrc_file,
            "search_line": "Constellation-Node",
        })
        if is_prompt_there and is_prompt_there != "file_not_found":
            self.test_or_replace_line_in_file({
                "file_path": bashrc_file,
                "search_line": "Constellation-Node",
                "replace_line": prompt_update,
            })
        elif is_prompt_there != "file_not_found":
            if not path.exists(bashrc_file):
                _ = self.process_command({
                    "bashCommand": f"sudo touch {bashrc_file}",
                    "proc_action": "subprocess_devnull",
                }) 
            with open(bashrc_file,"a") as file:
                file.write(f"{prompt_update}\n")
        
        _ = self.process_command({
            "bashCommand": f"sudo -u {username} -i bash -c source /home/{username}/.bashrc",
            "proc_action": "subprocess_return_code",
        })
        

    def set_request_session(self,local_file=False,json=False):
        get_headers = {
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }

        # if local_file and path.isfile(f"{local_file}.etag"):
        #     with open(f"{local_file}.etag",'r') as etag_f:
        #         get_headers['If-None-Match'] = etag_f.read().strip()

        if json:
            get_headers.update({
                'Accept': 'application/json',
            })
            
        session = Session()            
        session.headers.update(get_headers)   
        session.params = {'random': random.randint(10000,20000)}
        return session


    def set_console_setup(self,wrapper_obj):
        console_size = get_terminal_size()  # columns, lines

        initial_indent = subsequent_indent = "  "
        if wrapper_obj is not None:
                initial_indent = wrapper_obj.get("indent","  ")
                subsequent_indent = wrapper_obj.get("sub_indent","  ")
                
        console_setup = TextWrapper()
        console_setup.initial_indent = initial_indent
        console_setup.subsequent_indent = subsequent_indent
        console_setup.width=(console_size.columns - 2)

        return console_size, console_setup


    def set_chown(self,file_path,user,group):
        chown(file_path, getpwnam(user).pw_uid, getgrnam(group).gr_gid)
        return
    

    def set_time_sync(self):
        self.log.logger.info("functions -> syncing system clock")
        try:
            result = self.process_command({
                "bashCommand": "chronyc makestep",
                "proc_action": "subprocess_run_pipe",
            })
        except:
            self.log.logger.warning("functions -> unable to sync the clock with the network, skipping")
            return False
        else:
            result = result.stdout.decode().strip()
            self.log.logger.info(f"functions -> time sync'ed with network [{result}]")
            if "OK" not in result:
                return result
            
        try:
            track_output = self.process_command({
                "bashCommand": "chronyc tracking",
                "proc_action": "subprocess_run_pipe",
            })
        except:
            self.log.logger.warning("functions -> unable to sync the clock with the network, skipping")
            return False
        else:
            track_output = track_output.stdout.decode().strip()
            self.log.logger.info(f"functions -> track the time sync'ed with network [{track_output}]")
        
        try:
            source_output = self.process_command({
                "bashCommand": "chronyc sources -v",
                "proc_action": "subprocess_run_pipe",
            })
        except:
            self.log.logger.warning("functions -> unable to view sources of the clock with the network, skipping")
            return False
        else:
            source_output = source_output.stdout.decode().strip()
            self.log.logger.info(f"functions -> time source output sync'ed with network [{source_output}]")

        return result, track_output, source_output
        
    # =============================
    # pull functions
    # ============================= 
      
      
    def pull_node_sessions(self,command_obj):
        key = command_obj['key']
        port = command_obj['edge_device']['remote_port']
        profile = command_obj['profile']
        spinner = command_obj.get("spinner",True)
        caller = command_obj.get("caller","default")

        local_port = self.config_obj[profile]["public_port"]
        nodes = command_obj['edge_device']['remote'], self.ip_address
        session = {}

        # node0 = edge (remote) device (for dynamic purposes)
        session_obj = {
            "node0": nodes[0],
            "node1": nodes[1],
            "session0": 0,
            "session1": 0,
            "state0": "ApiNotReady", #remote
            "state1": "ApiNotReady" #local
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
                    "caller": caller,
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
                r_session = self.set_request_session()
                r_session.verify = False
                session = r_session.get(url, timeout=self.session_timeout).json()
            except:
                self.log.logger.error(f"pull_node_sessions - unable to pull request [functions->pull_node_sessions] test address [{node}] public_api_port [{port}] url [{url}]")
            finally:
                r_session.close()

            self.log.logger.info(f"pull_node_sessions found session [{session}] returned from test address [{node}] url [{url}] public_api_port [{port}]")
            try:
                token = session[key]
            except Exception as e:
                try:
                    self.log.logger.warning(f"Peer did not return a token | reason [{session['reason']} error [{e}]]")
                    session_obj[f"session{i}"] = f"{i}"
                except:
                    if self.auto_restart:
                        return False
                    try:
                        return {
                            "node0": nodes[0],
                            "node1": nodes[1],
                            "session0": 0,
                            "session1": 0,
                            "state0": "EdgePointDown", #remote
                            "state1": "EdgePointDown" #local                        
                        }
                        # return {
                        #     "node0": nodes[0],
                        #     "node1": nodes[1],
                        #     "session0": 0,
                        #     "session1": 0,
                        #     "state0": "NetworkUnreachable", #remote
                        #     "state1": "NetworkUnreachable" #local                        
                        # }
                    except:
                        self.error_messages.error_code_messages({
                            "error_code": "fnt-958",
                            "line_code": "lb_not_up",
                            "extra": command_obj['edge_device']['remote'],
                            "extra2": "0",
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

        cpu, memory, _ = self.check_cpu_memory_thresholds()
        if not cpu or not memory:
            if session_obj["state0"] == "ApiNotReady":
                session_obj["state0"] = "ApiNotResponding"
            if session_obj["state1"] == "ApiNotReady":
                session_obj["state1"] = "ApiNotResponding"
                
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
            "token_price": "unavailable",
            "token_symbol": "unknown"
        }
        
        if not self.auto_restart:
            self.print_cmd_status({
                "text_start": "Pulling DAG details from APIs",
                "brackets": environment,
                "status": "running",
                "newline": True,
            })

            if environment != "mainnet":
                self.print_paragraphs([
                    [" NOTICE ",0,"red,on_yellow"], 
                    [f"Wallet balances on {environment} are fictitious",0],["$TOKENS",0,"green"], 
                    ["and will not be redeemable, transferable, or spendable.",2],
                ])
            
        with ThreadPoolExecutor() as executor:
            self.event = True
            if not self.auto_restart:
                _ = executor.submit(self.print_spinner,{
                    "msg": f"Pulling Node balances, please wait",
                    "color": "magenta",
                })                     

            for n in range(5):
                try:
                    session = self.set_request_session()
                    session.verify = True
                    session.timeout = 2
                    uri = self.set_proof_uri({})
                    # url =f"https://{self.be_urls[environment]}/addresses/{wallet}/balance"
                    uri = f"{uri}/addresses/{wallet}/balance"
                    balance = session.get(uri, timeout=self.session_timeout).json()
                    balance = balance["data"]
                    balance = balance["balance"]
                except:
                    self.log.logger.error(f"pull_node_balance - unable to pull request [{ip_address}] DAG address [{wallet}] attempt [{n}]")
                    if n == 9:
                        self.log.logger.warning(f"pull_node_balance session - returning [{balance}] because could not reach requested address")
                        break
                    sleep(1.5)
                finally:
                    session.close()
                break   
            self.event = False              
        
        try:  
            balance = balance/1e8 
        except:
            balance = 0

        usd = []
        usd = self.get_crypto_price()  # position 5 in list

        token = self.config_obj[self.default_profile]["token_coin_id"].lower()
        try:
            return_obj["token_price"] = usd[token]["formatted"]
        except:
            pass
        try:
            return_obj["balance_dag"] = "{:,.5f}".format(balance)
        except:
            pass
        try:
            return_obj["balance_usd"] = "${:,.2f}".format(balance*usd[token]["usd"])
        except:
            pass
        try:
            return_obj["token_symbol"] = f'${usd[token]["symbol"].upper()}'
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
            
        elif "pairing" in var.req:
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
                        else: pairing_list.append([{
                            "profile": "external",
                            "host": self.config_obj[profile][f"{link_type}_link_host"],
                            "port": self.config_obj[profile][f"{link_type}_link_port"]
                        }])
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
                    if isinstance(profile,dict) or profile == "external": continue  # external connection not profile
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
                if len(profile_order) < 2 and profile_order[0] == "external":
                    pairing_list = []
                    for profile in self.profile_names:
                        pairing_list.append(
                            [{
                            "profile": profile,
                            "service" : self.config_obj[profile]["service"],
                            "layer": self.config_obj[profile]["layer"],
                            }]
                        )
                    pairing_list.append(["external"])
                    pairing_list[-1] += self.profile_names
                else:
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
            exit(0) # force exit on service changes.
    
    
    def pull_remote_profiles(self,command_obj):
        r_and_q = command_obj.get("r_and_q","both")
        retrieve = command_obj.get("retrieve","profile_names")
        return_where = command_obj.get("return_where","Main")
        set_in_functions = command_obj.get("set_in_functions",False)
        add_postfix = command_obj.get("add_postfix",False)
        options_color = command_obj.get("option_color","green")
        required = command_obj.get("required",False)

        predefined_envs = []
        try:
            repo_profiles = self.get_from_api(self.nodectl_profiles_url,"json")
        except:
            self.log.logger.error("functions --> pull_remote_profiles --> unable to access network.")
            self.error_messages.error_code_messages({
                "error_code": "fnt-1993",
                "line_code": "off_network",
                "extra": path.split(self.nodectl_profiles_url)[0],
                "extra2": "n/a",
            })

        repo_profiles = repo_profiles["payload"]["tree"]["items"]
        metagraph_name, chosen_profile = None, None
        ordered_predefined_envs = ["mainnet","integrationnet","testnet"]

        predefined_configs = {}
        for repo_profile in repo_profiles:
            if "predefined_configs" in repo_profile["path"] and "yaml" in repo_profile["name"]:
                f_url = f"{self.nodectl_profiles_url_raw}/{repo_profile['name']}" 
                details = self.get_from_api(f_url,"yaml")
                if details["nodectl"]["global_elements"]["nodectl_yaml"] != self.version_obj["node_nodectl_yaml_version"]:
                    continue # do not use old configuration that may not have been updated
                metagraph_name = details["nodectl"]["global_elements"]["yaml_config_name"] # readability
                predefined_envs.append(metagraph_name)
                predefined_configs = {
                    **predefined_configs,
                    f"{metagraph_name}": {
                        "json": details,
                        "yaml_url": f_url,
                    }
                }

        if required:
            for value in predefined_configs.values():
                _, file = path.split(value["yaml_url"])
                if file == required:
                    return value
            self.error_messages.error_code_messages({
                "error_code": "fnt-1865",
                "line_code": "invalid_configuration_request",
                "extra": required.replace(".yaml","")
            })

        # reorder
        for env in predefined_envs:    
            if env in ordered_predefined_envs and add_postfix:
                ordered_predefined_envs[ordered_predefined_envs.index(env)] = f"{env} [HyperGraph]"
            elif env not in ordered_predefined_envs:
                if add_postfix:
                    env = f"{env} [metagraph]"
                ordered_predefined_envs.append(env)

        if retrieve == "profile_names" or retrieve == "chosen_profile":    
            chosen_profile = self.print_option_menu({
                "options": ordered_predefined_envs,
                "return_where": return_where,
                "r_and_q": r_and_q,
                "color": options_color,
                "newline": True,
                "return_value": True,
            })

        if add_postfix:
            chosen_profile = chosen_profile.replace(" [HyperGraph]","").replace(" [metagraph]","")

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
                session = self.set_request_session()
                session.verify = True
                session.timeout = 2
                health = session.get(uri, timeout=self.session_timeout)
            except:
                self.log.logger.warning(f"unable to reach edge point [{uri}] attempt [{n+1}] of [3]")
                if n > 2:
                    if not self.auto_restart:
                        self.network_unreachable_looper()
                        return False
                pass
            else:  
                if health.status_code != 200:
                    self.log.logger.warning(f"unable to reach edge point [{uri}] returned code [{health.status_code}]")
                    if n > 2:
                        if not self.auto_restart:
                            self.network_unreachable_looper()
                            return False
                    else:
                        pass
                else:
                    return True
            finally:
                session.close()
                
            if not self.auto_restart:
                sleep(1)
            
            
    def check_health_endpoint(self,api_port): 
        try:
            session = self.set_request_session()
            session.verify = False
            session.timeout = 2
            r = session.get(f'http://127.0.0.1:{api_port}/node/health', timeout=self.session_timeout)
        except:
            pass
        else:
            if r.status_code == 200:
                self.log.logger.error(f"check health failed on endpoint [localhost] port [{api_port}]")
                return True
        finally:
            session.close()
            
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
        # this method will need to be refactored as new network clusters
        # register with Node Garage or Constellation (depending)
        try:
            self.environment_name = self.config_obj[self.default_profile]["environment"]             
        except:
            if not self.environment_name:
                self.environment_name = self.pull_remote_profiles({"r_and_q": None})

            
    def check_for_help(self,argv_list,extended):
        nodectl_version_only = False
        if extended == "configure": nodectl_version_only = True
        
        if "help" in argv_list:
            self.print_help({
                "extended": extended,
                "nodectl_version_only": nodectl_version_only,
                "special_case": True if "special_case" in argv_list else False
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
            
            
    def check_cpu_memory_thresholds(self):
        memory_threshold = 95
        cpu_threshold = 98
        cpu_ok, memory_ok = True, True

        cpu_found_percent = cpu_percent(interval=1)
        memory_found_percent = virtual_memory().percent

        # important note
        # memory utilization of the entire box (as found above) does not properly represent 
        # the metric of whether or not there is a memory issue on the box unless a serious issue
        # is present.  Future modifications should include the results of the pid process
        # as calculated below [future feature updates]
        # =====================================================
        cpu_mem_details = {}
        self.profile_names = self.clear_global_profiles(self.profile_names)
        for profile in self.profile_names:
            find_pid_for = self.config_obj[profile]["jar_file"]
            cpu_mem_details = {
                **cpu_mem_details,
                f"{profile}": {
                    "jar_file": find_pid_for,
                    "RSS": -1,
                    "VMS": -1,
                }
            }
            for process in process_iter(['pid', 'cmdline']):
                if process.info['cmdline']:
                    for value in process.info['cmdline']:
                        if find_pid_for in value:
                            found_pid = process.pid
                            process = Process(found_pid)
                            pid_memory = process.memory_info()
                            cpu_mem_details[profile]["RSS"] = pid_memory.rss
                            cpu_mem_details[profile]["VMS"] = pid_memory.vms
                            break

            cpu_mem_details["thresholds"] = {
                "mem_threshold": memory_threshold,
                "cpu_threshold": cpu_threshold,
                "mem_percent": memory_found_percent,
                "cpu_percent": cpu_found_percent
            }

        self.log.logger.info(f"functions -> cpu_memory_thresholds -> checked memory and cpu pid values [{cpu_mem_details}]")
        # ======================================================

        if cpu_found_percent > cpu_threshold:
            self.log.logger.warning(f"functions -> cpu_memory_thresholds -> cpu exceeding max | cpu % [{cpu_found_percent}] | memory % [{memory_found_percent}]")
            cpu_ok = False

        if memory_found_percent > memory_threshold:
            self.log.logger.warning(f"functions -> cpu_memory_thresholds -> memory exceeding max | memory % [{memory_found_percent}] cpu % [{cpu_found_percent}]")
            memory_ok = False

        if not cpu_ok and not memory_ok:
            self.log.logger.error(f"functions -> cpu_memory_thresholds -> system may be unresponsive or intermittently unresponsive")
        elif cpu_ok and memory_ok:
            self.log.logger.info(f"functions -> cpu_memory_thresholds -> checked memory and cpu found [OK] | memory % [{memory_found_percent}] cpu % [{cpu_found_percent}]")

        return cpu_ok, memory_ok, cpu_mem_details
    

    # =============================
    # is functions
    # =============================      
    
    def is_new_version(self,current,remote,caller,version_type):
        try:
            if version.parse(current) == version.parse(remote):
                self.log.logger.info(f"functions -> is_new_version -> versions match | current [{current}] remote [{remote}] version type [{version_type}] caller [{caller}]")
                return False            
            elif version.parse(current) > version.parse(remote):
                self.log.logger.warning(f"functions -> is_new_version -> versions do NOT match | current [{current}] remote [{remote}] version type [{version_type}] caller [{caller}]")
                return "current_greater"
            else:
                self.log.logger.warning(f"functions -> is_new_version -> versions do NOT match | current [{current}] remote [{remote}] version type [{version_type}] caller [{caller}]")
                return "current_less"
        except:
            if version_type == "versioning_module_testnet":
                return "current_greater"
            return "error"
    
    
    def is_version_valid(self,check_version):
        try:
            version.Version(check_version)
        except Exception as e:
            self.log.logger.warning(f"is_version_valid returned False [{check_version}] e [{e}]")
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
        if v_type == "ip_address":
            reg_expression = "^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"
            
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
            "caller": "test_ready_observing",
            "profile": profile,
            "simple": True,
        })
        continue_states = self.get_node_states("on_network",True) 
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
        test_address = command_obj.get("test_address","127.0.0.1")
        caller = command_obj.get("caller","default")
        profile = command_obj.get("profile")
        simple = command_obj.get("simple",False)
        print_output = command_obj.get("print_output",True)
        current_source_node = command_obj.get("current_source_node",False)
        skip_thread = command_obj.get("skip_thread",False)
        threaded = command_obj.get("threaded", False)
        spinner = command_obj.get("spinner", False)
        spinner = False if self.auto_restart else spinner
        api_not_ready_flag = False
        send_error = False

        def print_test_error(errors):
            self.set_error_obj()
            self.error_messages.error_code_messages({
                "line_code": "api_error",
                "error_code": f"fnt-{errors[0]}",
                "extra": None,
                "extra2": str(errors[1]),
            })

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
                    "caller": caller,
                    "threaded": threaded,
                    "profile": profile,
                    "spinner": spinner,
                })
            except IndexError as e:
                self.log.logger.error(f"test_peer_state -> IndexError retrieving get_info_from_edge_point | caller: [{caller}] current_source_node: [{current_source_node}] | e: {e}")
            except Exception as e:
                self.log.logger.error(f"test_peer_state -> error retrieving get_info_from_edge_point | caller: [{caller}] | current_source_node: [{current_source_node}] | e: {e}")
                send_error = (2160,e) # fnt-2160
        
        ip_addresses = [test_address,current_source_node]
        ip_addresses = [x for x in ip_addresses if x]
        prepare_ip_objs = deepcopy(ip_addresses)

        for n,ip in enumerate(prepare_ip_objs):
            if not isinstance(ip,dict):
                try:
                    ip_addresses[n] = self.get_info_from_edge_point({
                        "caller": caller,
                        "threaded": threaded,
                        "profile": profile,
                        "specific_ip": ip,
                        "spinner": spinner,
                    })
                except IndexError as e:
                    self.log.logger.error(f"test_peer_state -> IndexError retrieving get_info_from_edge_point | ip_address {ip_addresses[n]} | e: {e}")
                    send_error = (2184,e) # fnt-2184
                except Exception as e:
                    self.log.logger.error(f"test_peer_state -> unable to get_info_from_edge_point | ip_address {ip_addresses[n]} | e: [{e}]")
                    send_error = (2187,e) # fnt-2187

        if send_error and not self.auto_restart:
            if caller not in ["versioning","status","quick_status","skip_error"]:
                print_test_error(send_error)

        if send_error and not self.auto_restart and caller != "skip_error":
            if caller in ["upgrade","install","quick_install","versioning"]:
                if caller == "versioning":
                    return send_error
                else:
                    print_test_error(send_error)
            
        with ThreadPoolExecutor() as executor:
            do_thread = False
            if not self.auto_restart and threaded:
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
                            session = self.set_request_session()
                            session.verify = False
                            session.timeout = 2 
                            state = session.get(uri, timeout=self.session_timeout).json()
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
                            if api_not_ready_flag: 
                                cpu, mem, _ = self.check_cpu_memory_thresholds()
                                if not cpu or not mem: 
                                    self.log.logger.warning("functions -> test peer state -> setting status to [ApiNotReponding]")
                                    results['node_state_src'] = "ApiNotResponding"
                                    results['node_state_edge'] = "ApiNotResponding"
                                break_while = True
                            # try 2 times before passing with ApiNotReady or ApiNotResponding
                            attempt = attempt+1
                            if attempt > 1:
                                api_not_ready_flag = True
                            sleep(.5)
                            break
                        else:
                            break_while = True
                            if simple: # do not check/update source node
                                break
                        finally:
                            session.close()
                
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


    def test_hostname_or_ip(self, hostname, http=True):
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
                
        if not http:
            if hostname.startswith("http:") or hostname.startswith("https:"):
                return False
        return True    
    
    
    def test_or_replace_line_in_file(self,command_obj):
        # single line without dups only
        file_path = command_obj["file_path"]
        search_line = command_obj["search_line"]
        replace_line = command_obj.get("replace_line",False)
        remove_line = command_obj.get("remove_line",False)
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
                if remove_line:
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
                remove(temp) 
            if path.isfile(f"{temp}_reverse"):
                remove(f"{temp}_reverse")
        
        remove_temps()
                
        line_number, line_position = 0, 0       
        with open(temp,"w") as temp_file:
            if replace_line and not skip_backup:
                copy2(file_path,f"{backup_dir}{file}_{date}")
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
            copy2(temp,file_path)
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
        # Review the configuration and return the lowest Cluster or metagraph
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
    

    def test_file_exists(self,root_path,file,ask=True):
        if path.exists(f"{root_path}/{file}"):
            cprint(f"  {root_path}/{file} already found","red")
            if ask:
                confirm = self.confirm_action({
                    "yes_no_default": "y",
                    "return_on": "y",
                    "prompt": f"Overwrite existing?",
                    "exit_if": False,
                })
                if confirm: return "override"
            return True
        return False
     

    def test_for_tcp_packet(self, packet):
        # set self.parent before calling test_for_tcp_packets
        try: _ = self.parent.tcp_test_results[self.port_int]
        except:
            self.parent.tcp_test_results[self.port_int] = {
                "found_destination": False,
                "found_source": False
            }

        if TCP in packet:
            if packet[TCP].dport in [self.port_int]:
                self.log.logger.debug(f"functions -> test_for_tcp_packet -> TCP destination packet found: {packet.summary()}")
                self.parent.tcp_test_results[self.port_int]["found_destination"] = True
            if packet[TCP].sport in [self.port_int]:
                self.log.logger.debug(f"functions -> test_for_tcp_packet -> TCP source packet found: {packet.summary()}")
                self.parent.tcp_test_results[self.port_int]["found_source"] = True
        
        return
            

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
            self.log.logger.error("csv error detected, cannot write or row and rows in the same call.")
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

    def print_clear_line(self,lines=1,command_obj=False):
        backwards, fl, bl = False, False, False
        if command_obj:
            backwards = command_obj.get("backwards",False)
            fl = command_obj.get("fl",False) # extra forward lines
            bl = command_obj.get("bl",False) # extra backward lines
            if lines < 2 and not bl: bl = -1

        console_size = get_terminal_size()
        print(f"{' ': >{console_size.columns-2}}",end="\r")
        if backwards:
            print(f'\x1b[{lines}A', end='')
            print(f"{' ': >{console_size.columns-2}}",end="\r")
        if lines < 2: lines -= 1
        for _ in range(1,lines):
            print(f"{' ': >{console_size.columns-2}}")
        print(f"{' ': >{console_size.columns-2}}",end="\r")
        if backwards:
            if lines > 1: print("\n"*fl) 
            elif fl: print("")
            if bl: lines += bl
            print(f'\x1b[{lines}A', end='')        
        

    def print_timer(self,command_obj):
        seconds = command_obj["seconds"]
        start = command_obj.get("start",1)
        phrase = command_obj.get("phrase",None)
        end_phrase = command_obj.get("end_phrase",None)
        p_type = command_obj.get("p_type","trad")
        step = command_obj.get("step",1)
        status = command_obj.get("status","preparing")
        use_minutes = command_obj.get("use_minutes",False)

        if step > 0: 
            end_range = start+seconds
            end_range_print = end_range
            if start == 1: end_range = end_range-1
        else: 
            start = seconds
            end_range_print = start
            end_range = 0

        if phrase == None:
            phrase = "to allow services to take effect"     
        if end_phrase == None:
            end_phrase = " "

        for s in range(start,end_range+1,step):
            if self.cancel_event: break
            ss = s
            count_verb = "seconds"
            if use_minutes:
                if s > 59:
                    count_verb = "minutes"
                    minutes = ss // 60
                    seconds = ss % 60
                    ss = f"{minutes:02d}:{seconds:02d}"

                
            if not self.auto_restart:
                if p_type == "trad":
                    self.print_clear_line()
                    print(colored(f"  Pausing:","magenta"),
                            colored(f"{s}","yellow"),
                            colored("of","magenta"),
                            colored(f"{end_range_print}","yellow"),
                            colored(f"{count_verb} {phrase}","magenta"), end='\r')
                elif p_type == "cmd":
                    self.print_cmd_status({
                        "text_start": phrase,
                        "brackets": str(ss),
                        "text_end": end_phrase,
                        "status": status,
                    })
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
        line1 = command_obj["line1"] 
        line2 = command_obj.get("line2", None)
        clear = command_obj.get("clear", False)
        show_titles = command_obj.get("show_titles", True)
        newline = command_obj.get("newline", False)
        upper = command_obj.get("uppercase",True)

        single_line = command_obj.get("single_line", False)
        single_color = command_obj.get("single_color", "yellow")
        single_bg = command_obj.get("single_bg", "on_blue")

        if upper:
            if line1 is not None: line1 = line1.upper()
            if line2 is not None: line2 = line2.upper()

        if "on_" not in single_bg:
            single_bg = f"on_{single_bg}" 

        if clear:
            _ = self.process_command({"proc_action": "clear"})
        if newline == "top" or newline == "both":
            print("")
                                    
        if single_line:
            line1 = f" * {line1} * "  
            print("  ",end="")  
            cprint(f' {line1:-^40} ',single_color,single_bg,attrs=["bold"])
        else:
            header0 = "  ========================================"
            header1 = "  =   CONSTELLATION NETWORK HYPERGRAPH   ="
            header2 = f"  Code Name: {colored(self.nodectl_code_name,'yellow')}\n"
            
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
        value_spacing_only = False
        d_spacing = 20
               
        for key,value in header_elements.items():
            if key != "spacing" and key != "header_color" and key != "header_attr" and key != "header_elements" and key != "value_spacing_only":
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
                if key == "value_spacing_only":
                    value_spacing_only = True
        
        #for header, value in header_elements.items():
        for i, (header, value) in enumerate(header_elements.items()):
            spacing = d_spacing if not value_spacing_only else 20
            v_spacing = d_spacing

            if header == "-BLANK-":
                print("")
            else:
                if str(i) in cols:
                        spacing = cols[str(i)]
                status_header += colored(f"  {header: <{spacing}}",header_color,attrs=[header_attr])
                try:
                    status_results += f"  {value: <{v_spacing}}"
                except:
                    value = "unavailable".ljust(v_spacing," ")
                    status_results += f"  {value: <{v_spacing}}"
                
        if "SKIP_HEADER" not in status_header:
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
        timeout = command_obj.get('timeout',True)
        dotted_animation = command_obj.get('dotted_animation',False)
        
        newline = command_obj.get('newline',False)  # because of use of spread operator this should be declared consistently 
        status_color = command_obj.get('status_color',"default")
        bold = command_obj.get('bold',False)

        error_out_timer = time()
        error_out_threshold = 20
        
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
                if time() - error_out_timer > error_out_threshold and timeout:
                    raise Exception
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
        options = deepcopy(options_org) # options relative to self.profile_names
        let_or_num = command_obj.get("let_or_num","num")
        prepend_let = command_obj.get("prepend_let", False)
        return_value = command_obj.get("return_value",False)
        return_where = command_obj.get("return_where","Main")
        color = command_obj.get("color","cyan")
        newline = command_obj.get("newline",False) # top, bottom, both
        press_type = command_obj.get("press_type","key_press") # manual, key_press

        # If r_and_q is set ("r","q" or "both")
        # make sure if using "let" option, "r" and "q" do not conflict
        r_and_q = command_obj.get("r_and_q",False)
        
        prefix_list = []
        spacing = 0
        blank = 0

        if prepend_let:
            i = 0
            for n in range(len(options)):
                if options[n] == "blank_spacer": continue
                while chr(97 + i) in ["q","r"]:
                    i +=1
                letter = chr(97 + i)  # 97 is 'a'
                options[n] = f"{letter} {options[n]}"  
                i += 1

        for n, option in enumerate(options):
            if "blank_spacer" in option: 
                print("")
                blank += 1
                continue
            if blank > 0: n -= blank
            prefix_list.append(str(n+1))
            if let_or_num == "let":
                prefix_list[n] = option[0].upper()
                option = option[1::]
                spacing = -1
        
            menu_item = [
                [prefix_list[n],-1,color,"bold"],[")",-1,color],
                [option,spacing,color], ["",1],
            ]
            if color == "blue": menu_item[2] = [option,spacing,color,"bold"]
            self.print_paragraphs(menu_item)

        if r_and_q:
            if r_and_q == "both" or r_and_q == "r":
                menu_item = [
                    ["",1],["R",0,color,"bold"], [")",-1,color], [f"eturn to {return_where} Menu",-1,color], ["",1],
                ]
                if color == "blue": menu_item[3] = [f"eturn to {return_where} Menu",-1,color,"bold"]
                self.print_paragraphs(menu_item)
                prefix_list.append("R")
                options.append("r")
                newline = False
            if r_and_q == "both" or r_and_q == "q":
                if newline: print("")
                menu_item = [
                    ["Q",-1,color,"bold"], [")",-1,color], ["uit",-1,color], ["",2],                
                ]
                if color == "blue": menu_item[2] = ["uit",-1,color,"bold"]
                self.print_paragraphs(menu_item)
                prefix_list.append("Q")
                options.append("q")
        else:
            print("")
            
        if press_type == "manual":
            cprint("  Enter an option and hit the <enter> key",color)
            option = input("  : ")
            return option
        
        option = self.get_user_keypress({
            "prompt": "KEY PRESS an option",
            "prompt_color": "cyan",
            "options": prefix_list,
        })
        
        if not return_value:
            return option
        for return_option in options:
            if return_option == "blank_spacer": continue
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
        
        try:
            p_type_list = self.environment_names
        except:
            self.set_environment_names()
            p_type_list = self.environment_names

        if p_type == "profile" or p_type == "send_logs":
            p_type_list = self.profile_names
            if p_type == "send_logs": 
                for p in p_type_list:
                    p_type_list[p_type_list.index(p)] = f"{p} app logs"
                p_type_list.append("nodectl logs")
            
        if not title:
            title = f"Press choose required {p_type}"

        if len(p_type_list) < 1 and p_type == "environment":
            self.pull_remote_profiles({
                "set_in_functions": True,
                "retrieve": None,
            })
            p_type_list = self.environment_names
        

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

        if p_type == "send_logs": 
            return_value = return_value.replace(" app logs","")
            return_value = return_value.replace(" logs","")

        self.print_paragraphs([
            ["",1], [f" {return_value} ",2,"yellow,on_blue","bold"],
        ])
        
        return return_value
        
                
    def print_any_key(self,command_obj):
        quit_option = command_obj.get("quit_option",False)
        newline = command_obj.get("newline",False)
        prompt = command_obj.get("prompt",False)
        color = command_obj.get("color", "yellow")
        return_key_pressed = command_obj.get("return_key",False)
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
    
        if return_key_pressed: return key_pressed
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

        console_size, console_setup = self.set_console_setup(wrapper_obj)
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
        try:
            msg = command_obj.get("msg")
            color = command_obj.get("color","cyan")
            newline = command_obj.get("newline",False)
            clearline = command_obj.get("clearline",True)
            spinner_type = command_obj.get("spinner_type","spinner")
            timeout = command_obj.get("timeout",False)
            
            timer = -1
            if timeout:
                timer = perf_counter()
                
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
            while self.event and not self.cancel_event:
                cursor = next(spinner)
                print(f"  {colored(msg,color)} {colored(cursor,color)}",end="\r")
                sleep(0.3)
                if not self.event:
                    self.print_clear_line()
                    break
                
                current = perf_counter() - timer
                if timeout and (current > timeout):
                    exit(0)

            if newline == "bottom" or newline == "both":
                print("")
        except Exception as e:
            self.log.logger.warning(f"functions -> spinner -> errored with [{e}]")
            return
            
    
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
        
        self.log.logger.info(f"{action} completed in [{total_time}]")
        self.print_paragraphs([
            ["Total",0], [action,0,"yellow","underline"], ["time:",0],
            [f" {round(total_time,3)} ",0,"grey,on_green","bold"],
            [f"{unit}",2],
        ])


    def print_help(self,command_obj):
        nodectl_version_only = command_obj.get("nodectl_version_only",False)
        hint = command_obj.get("hint","None")
        title = command_obj.get("title",False)
        usage_only = command_obj.get("usage_only",False)
        special_case = command_obj.get("special_case",False)
        extended = command_obj.get("extended",False)

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
                "clear": True,
                "upper": False,
            })
            
        if special_case:
            command_obj["valid_commands"] = [extended]
        else:
            if not self.version_obj:
                self.print_paragraphs([
                    [" WARNING/ERROR ",0,"red,on_yellow"],
                    ["nodectl was initialized without a command request, or something went wrong?",2,"red"],
                    ["command:",0],["sudo nodectl help",2,"yellow","bold"],
                ])
                exit(0)
                
            self.help_text = f"  NODECTL INSTALLED: [{colored(self.version_obj['node_nodectl_version'],'yellow')}]"

            if not nodectl_version_only:
                install_profiles = self.pull_profile({"req":"one_profile_per_env"})
                old_env = None
                for profile in install_profiles:
                    env = self.config_obj[profile]["environment"]
                    try:
                        node_tess_version = self.version_obj[env][profile]['node_tess_version']
                    except:
                        node_tess_version = "not_found"

                    if old_env != env and node_tess_version != "not_found":
                        self.help_text += f"\n  {env.upper()} TESSELLATION INSTALLED: [{colored(node_tess_version,'yellow')}]"
                    old_env = env

        self.help_text += build_help(self,command_obj)
        print(self.help_text)

        if usage_only: exit(0)

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
    # handlers
    # =============================  

    def handle_spinner_kill(self):
        raise TerminateFunctionsException("spinner cancel")
    

    def handle_missing_version(self,version_class_obj):
        version_class_obj.functions = self
        version_class_obj.config_obj = self.config_obj
        version_class_obj.get_cached_version_obj()
        
        return version_class_obj.get_version_obj()   
    

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
        f_remove = file_obj.get("remove",False)
        print_start = file_obj.get("print_start",True)
        print_complete = file_obj.get("print_complete",True)

        if self.auto_restart:
            print_start, print_complete = False, False

        if print_start:
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

        if f_remove:
            for file in files:
                if path.exists(f"{location}/{file}"):
                    remove(f"{location}/{file}")

        if print_complete:           
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
        
        
    def clear_external_profiles(self,profile_list_or_obj):
        if isinstance(profile_list_or_obj,list):
            return [x for x in profile_list_or_obj if "external" not in x]
        return [ x for x in profile_list_or_obj.keys() if "external" not in x]

    
    def remove_duplicates(self, r_type, dicts_list):
        if r_type == "list_of_dicts":
            seen = set()
            unique_dicts = []

            for d in dicts_list:
                dict_as_tuple = frozenset(d.items())
                if dict_as_tuple not in seen:
                    seen.add(dict_as_tuple)
                    unique_dicts.append(d)
        
            return unique_dicts


    def cleaner(self, line, action, char=None):
        if action == "dag_count":
            cleaned_line = sub('\D', '', line)
            return cleaned_line[6:]
        elif action == "ansi_escape":
            ansi_escape = compile(r'(\x9B|\x1B\[)[0-?]*[ -\/]*[@-~]')
            return ansi_escape.sub('', line)  
        elif action == "ansi_escape_colors":
            ansi_escape = compile(r'\x1b\[[0-9;]+m')
            ansi_escape = ansi_escape.sub('', line)  
            return ansi_escape.strip()
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
        elif action == "double_spaces":
            return sub(r'\s+', ' ', line) 
        elif action == "double_slash":
            return sub('//', '/', line) 
        elif action == "trailing_backslash":
            if line[-1] == "/":
                return line[0:-1]
            return line
        elif action == "url":
            parsed_url = urlparse(line)
            cleaned_path = parsed_url.path.replace('//', '/')
            cleaned_url = urlunparse((parsed_url.scheme, parsed_url.netloc, cleaned_path,
                          parsed_url.params, parsed_url.query, parsed_url.fragment))
            return cleaned_url
        elif action == "remove_surrounding": # removing first and last - used for single and doubleq quotes mostly
            return line[1:-1]


    def escape_strings(self, input_string):
        special_chars = r'\\|\'|"|\$|&|\||>|<|;|\(|\)|\[|\]|\*|\?|~|!|#| '
        escaped_string = sub(f"([{special_chars}])", r'\\\1', input_string)

        return escaped_string
    

    def confirm_action(self,command_obj):
        self.log.logger.debug("confirm action request")
        
        yes_no_default = command_obj.get("yes_no_default")
        return_on = command_obj.get("return_on")
        incorrect_input = command_obj.get("incorrect_input","incorrect input")
        
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
                print(colored(f"  {incorrect_input}","red"))
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
            self.log.logger.warning("network has become unreachable, starting retry loop to avoid error")
            if not self.auto_restart:
                progress = {
                    "text_start": "Network unreachable pausing until reachable",
                    "text_color": "red",
                    "status": f"{seconds}s",
                    "status_color": "yellow",
                    "newline": True,
                }
                self.print_cmd_status(progress)
                self.print_timer({
                    "seconds": seconds,
                    "phrase": "to allow network to recover",
                })
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
                

    def remove_files(self, file_or_list, caller, is_glob=False, etag=False):
        # is_glob:  False is not in use; directory location if to be used
        # etag: if etags are associated with the file to remove
        self.log.logger.info(f"functions -> remove_files -> cleaning up files | caller [{caller}].")
        files = file_or_list
        result = True

        if is_glob:
            files = glob.glob(is_glob)
        elif not isinstance(file_or_list,list):
            files = [file_or_list]

        if etag:
            e_files = deepcopy(files)
            for file in e_files:
                files.append(f"{file}.etag")

        for file in files:
            try:
                if is_glob:
                    self.process_command({
                        "bashCommand": f"sudo rm -f {file}",
                        "proc_action": "subprocess_devnull",
                    })
                else:
                    remove(file)
            except OSError as e:
                result = False
                self.log.logger.error(f"functions --> remove_files --> caller [{caller}] -> error: unable to remove temp file [{file}] error [{e}]")

        return result
    

    def download_file(self,command_obj):
        url = command_obj["url"]
        local = command_obj.get("local",path.split(url)[1])
        do_raise = False
        etag = None
        try:
            session = self.set_request_session(local)
            session.verify = True
            params = {'random': random.randint(10000, 20000)}
            with session.get(url,params=params, stream=True) as response:
                if response.status_code == 304: # file did not change
                    self.log.logger.warning(f"functions --> download_file [{url}] response status code [{response.status_code}] - file fetched has not changed since last download attempt.")
                else:
                    response.raise_for_status()
                    etag = response.headers.get("ETag")
                    with open(local,'wb') as output_file:
                        for chunk in response.iter_content(chunk_size=8192):
                            output_file.write(chunk)
                    if etag:
                        with open(f'{local}.etag','w') as output_file_etag:
                            output_file_etag.write(etag)
            self.log.logger.info(f"functions --> download_file [{url}] successful output file [{local}]")
        except HTTPError as e:
            self.log.logger.error(f"functions --> download_file [{url}] was not successfully downloaded to output file [{local}] error [{e}]")
            do_raise = True
        except RequestException as e:
            self.log.logger.error(f"functions --> download_file [{url}] was not successfully downloaded to output file [{local}] error [{e}]")
            do_raise = True
        finally:
            session.close()

        if do_raise:
            raise


    def process_command(self,command_obj):
        # bashCommand, proc_action, autoSplit=True,timeout=180,skip=False,log_error=False,return_error=False
        bashCommand = command_obj.get("bashCommand",False)
        proc_action = command_obj.get("proc_action")
        
        autoSplit = command_obj.get("autoSplit",True)
        timeout = command_obj.get("timeout",180)
        skip = command_obj.get("skip",False)
        check = command_obj.get("check",False)
        log_error = command_obj.get("log_error",False)
        return_error = command_obj.get("return_error",False)
        working_directory = command_obj.get("working_directory",None)
        
        if proc_action == "clear":
            run('clear', shell=True)
            return
        
        if "timeout" in proc_action:
            if working_directory == None:
                p = Popen(shlexsplit(bashCommand), stdout=PIPE, stderr=PIPE)
            else:
                p = Popen(shlexsplit(bashCommand), cwd=working_directory, stdout=PIPE, stderr=PIPE)
                
            timer = Timer(timeout, p.kill)
            try:
                timer.start()
                # stdout, stderr = p.communicate()
            except Exception as e:
                self.log.logger.warning(f"function process command errored out with [{e}]")
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
                    results.append(Popen(cmd, stdout=PIPE))
                    continue
                results.append(Popen(bashCommand[n],stdin=results[n-1].stdout, stdout=PIPE))
                
            output, _ = results[-1].communicate()
            return output.decode()

        if proc_action == "subprocess_co":
            try:
                output = check_output(bashCommand, shell=True, text=True)
            except CalledProcessError as e:
                self.log.logger.warning(f"functions -> subprocess error -> error [{e}]")
            return output
        
        if proc_action == "subprocess_run":
            output = run(shlexsplit(bashCommand), shell=True, text=True)
            return output
        
        if proc_action == "subprocess_run_check_only":
            try:
                output = run(shlexsplit(bashCommand), check=True)
            except CalledProcessError as e:
                self.log.logger.warning(f"functions -> subprocess error -> error [{e}]")
                output = False
            return output
                
        if proc_action == "subprocess_run_pipe":
            try:
                output = run(shlexsplit(bashCommand), check=True, stdout=PIPE, stderr=PIPE)
            except CalledProcessError as e:
                self.log.logger.warning(f"functions -> subprocess error -> error [{e}]")
                output = False
            return output
                
        if proc_action == "subprocess_run_only":
            try:
                output = run(shlexsplit(bashCommand))
            except CalledProcessError as e:
                self.log.logger.warning(f"functions -> subprocess error -> error [{e}]")
                output = False
            return output
        
        if proc_action == "subprocess_return_code":
            try:
                output = run(shlexsplit(bashCommand), stdout=DEVNULL, stderr=DEVNULL, check=True)
            except CalledProcessError as e:
                self.log.logger.warning(f"functions -> subprocess error -> error [{e}]")
                output = e
            return output.returncode
        
        if proc_action == "subprocess_devnull":
            try:
                output = run(shlexsplit(bashCommand), stdout=DEVNULL, stderr=STDOUT, check=True)
            except CalledProcessError as e:
                self.log.logger.warning(f"functions -> subprocess error -> error [{e}]")
                output = False
            return output  
              
        if proc_action == "subprocess_run_check_text":
            try:
                output = run(shlexsplit(bashCommand), check=True, text=True)
            except CalledProcessError as e:
                self.log.logger.warning(f"functions -> subprocess error -> error [{e}]")
                output = False
            return output
        

        if proc_action == "subprocess_capture" or proc_action == "subprocess_rsync":
            verb = "capture" if "capture" in proc_action else "rsync"
            try:
                result = run(shlexsplit(bashCommand), check=True, text=True, capture_output=True)
                self.log.logger.info(f"{verb} completed successfully.")
            except CalledProcessError as e:
                self.log.logger.warning(f"{verb} failed. Error: {e.stderr}")
            except Exception as e:
                self.log.logger.warning(f"An error occurred: {str(e)}")
            return result

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
                self.log.logger.warning(f"function process command errored out with [{e}]")
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
                self.log.logger.warning(f"process command [Bash Command] err: [{err}].")
                
            if return_error:
                return err.decode('utf-8')

            if isinstance(result,bytes):
                result = result.decode('utf-8')
                
            return result
        else:
            return    


if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")
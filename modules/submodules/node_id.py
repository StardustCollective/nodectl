import re
from termcolor import colored, cprint
from copy import deepcopy
from os import path, get_terminal_size
from concurrent.futures import ThreadPoolExecutor
from time import sleep
from types import SimpleNamespace

from modules.p12 import P12Class


class NodeDAGid():
    
    def __init__(self,parent,command_obj):
        self.parent = parent
        self.argv_list = command_obj.get("argv_list",[None])
        self.command = command_obj["command"]
        self.return_success = command_obj.get("return_success",False)
        self.skip_display = command_obj.get("skip_display",False)
        self.outside_node_request = command_obj.get("outside_node_request",False)
        self.dag_addr_only = command_obj.get("dag_addr_only",False)
        self.ready_state = command_obj.get("ready_state",False)
        self.threading = command_obj.get("threading",True)
        self.profile = command_obj.get("profile",self.parent.profile)
        self.is_global = command_obj.get("is_global",True)
        self.functions = self.parent.functions
        self.log = self.parent.log.logger[self.parent.log_key]

        self.functions.check_for_help(self.argv_list,self.command)
        self._print_log_msg("info",f"Request to display nodeid | type {self.command}")

        self.quiet_install = True if list(command_obj.values()) else False


    # ==== SETTERS ====

    def set_parameters(self):
        self.nodeid = ""
        self.ip_address = "127.0.0.1"

        self.total_rewards = 0
        self.snap_size = 100
        
        self.balance_only = False
        self.api_port = False
        self.nodeid_to_ip = False 
        self.target = False
        self.is_self= False
        self.cmd = False
        self.print_out_list = False
        self.file = False
        self.create_csv = False
        self.consensus = False
        self.dag_address = False

        self.wallet_only = True if "-w" in self.argv_list or "--wallet" in self.argv_list else False
         
        if self.command == "nodeid": 
            self.title = "NODE ID"
        else:
            self.title = "DAG ADDRESS"
            if "--balance" in self.argv_list: 
                self.balance_only = True


    def set_profile(self):
        if self.file: return

        if "-p" in self.argv_list:  # profile
            self.profile = self.argv_list[self.argv_list.index("-p")+1] 
            self.is_global = False

            
    def set_static_target_ip(self):
        if self.wallet_only: return

        if "-t" in self.argv_list:
            try:
                self.ip_address = self.argv_list[self.argv_list.index("-t")+1]
            except:
                self.argv_list.append("help")
            self.target = True
            self.outside_node_request = True

        if "--port" in self.argv_list:
            self.api_port = self.argv_list[self.argv_list.index("--port")+1]


    def set_outside_request(self):
        if not self.wallet_only: return

        self.outside_node_request = True
        self.nodeid = self.argv_list[self.argv_list.index("-w")+1]


    def set_command(self):
        if self.ip_address != "127.0.0.1" or self.ready_state: return

        self.cmd = "/usr/bin/java -jar /var/tessellation/cl-wallet.jar show-id"
        if "-wr" in self.argv_list:
            self.cmd = "/usr/bin/java -jar /var/tessellation/cl-wallet.jar show-public-key"


    def set_print_out_ip(self):
        if not self.is_self and not self.wallet_only and not self.balance_only:
            self.print_out_list = [
                {
                    "header_elements" : {
                        "IP ADDRESS REQUESTED": self.ip_address,
                    },
                },
            ]


    def _set_csv_file(self):
            if "--csv" not in self.argv_list: return

            self.functions.print_cmd_status({
                "text_start": "Create csv for",
                "brackets": "show dag rewards",
                "status": "running"
            })
            self.create_csv = True

            if "-np" not in self.argv_list:
                self.argv_list.append("-np"
                                    )
            if "--output" in self.argv_list:
                csv_file_name = self.argv_list[self.argv_list.index("--output")+1]
                try:
                    self.csv_file_name = path.normalize(csv_file_name)
                except:
                    self.parent.error_messages.error_code_messages({
                        "error_code": "cmd-442",
                        "line_code": "invalid_file_or_path",
                        "extra": csv_file_name
                    })
            else:
                prefix = self.functions.get_date_time({"action": "datetime"})
                self.csv_file_name = f"{prefix}-{self.nodeid[0:8]}-{self.nodeid[-8:]}-show-dag-data.csv"
            
            self.csv_path = f"{self.parent.config_obj[self.profile]['directory_uploads']}{csv_file_name}"


    def _set_dyn_target_ip(self):
        if self.target or self.ready_state: 
            target_ip = self.functions.get_info_from_edge_point({
                "profile": self.profile,
                "caller": "cli_grab_id",
                "specific_ip": self.ip_address,
            })
            self.api_port = target_ip["publicPort"]
            self.nodeid = target_ip["id"]
            self.target_ip = target_ip


    def _set_api_port(self):
        if self.api_port: return

        try: 
            self.api_port = self.functions.config_obj[self.profile]["public_port"]
        except:
            self.parent.error_messages.error_code_messages({
                "error_code": "cmd_1953",
                "line_code": "profile_error",
                "extra": self.profile
            })


    def _set_wr_nodeid(self):
        nodeidwr = []
        nodeid = self.nodeid.split("\n")

        for part in nodeid:
            part = re.sub('[^A-Za-z0-9]+', '', part)
            nodeidwr.append(part)

        try:
            nodeid = f"{nodeidwr[1][1::]}{nodeidwr[2][1::]}"
        except:
            self._print_log_msg("error",f"Unable to access nodeid from p12 file.")
            nodeid = "unable to derive"

        self.nodeid = nodeid


    def _set_normal_nodeid(self):
        nodeid = self.nodeid.strip()

        if nodeid == "":
            self._print_log_msg("error",f"Unable to access nodeid from p12 file.")
            nodeid = "unable to derive"

        self.nodeid = nodeid


    def _set_do_more(self):
            do_more = False if "-np" in self.argv_list else True
            if do_more:
                console_size = get_terminal_size()
                self.more_break = round(console_size.lines)-20

            self.do_more = do_more


    # ==== PARSERS / PROCESSORS ====

    def process_node_id(self):
        if (self.ip_address == "127.0.0.1" and not self.wallet_only) or self.command == "dag":
            with ThreadPoolExecutor() as executor:
                if not self.nodeid:
                    try:
                        nodeid = self.parent.config_obj["global_elements"]["nodeid_obj"][self.profile]
                    except:
                        self.functions.event = True
                        if self.threading:
                            _ = executor.submit(self.functions.print_spinner,{
                                "msg": f"Pulling {self.title}, please wait",
                                "color": "magenta",
                            })                     
                        nodeid = self.functions.process_command({
                            "bashCommand": self.cmd,
                            "proc_action": "poll"
                        })
                    
                self.nodeid = nodeid
                self._print_log_msg(
                    "debug",
                    f"The requested the node's nodeid and found | nodeid [{self.nodeid}] | profile [{self.profile}]"
                )
                if self.command == "dag" and not self.wallet_only:
                    try:
                        self.dag_address = self.parent.config_obj["global_elements"]["nodeid_obj"][f"{self.profile}_wallet"]
                    except:
                        self.dag_address = self.parent.cli_nodeid2dag({
                            "nodeid": nodeid.strip(),
                            "profile": self.profile,
                        })
                    self._print_log_msg(
                        "debug",
                        f"The requested the node's DAG address and found | nodeid [{self.nodeid}] | profile [{self.profile}]"
                    )
                if self.ip_address == "127.0.0.1":
                    self.ip_address = self.parent.ip_address
                    self.is_self = True
                    
                self.functions.event = False 


    def _process_nodeid_request(self):
        with ThreadPoolExecutor() as executor:
            self.functions.event = True
            if self.threading:
                _ = executor.submit(self.functions.print_spinner,{
                    "msg": f"Pulling node ID, please wait",
                    "color": "magenta",
                })                     
            if self.outside_node_request:
                self._process_outside_nodeid_request()
            elif not self.nodeid:
                self._process_internal_nodeid_request()

            self.functions.event = False  


    def _process_outside_nodeid_request(self):
        false_lookups = []
        cluster_ips = self.functions.get_cluster_info_list({
            "profile": self.profile,
            "ip_address": self.ip_address,
            "port": self.api_port,
            "api_endpoint": "/cluster/info",
            "error_secs": 3,
            "attempt_range": 3,
        })  
        
        try:
            cluster_ips.pop()   
        except:
            if self.ip_address not in false_lookups:
                false_lookups.append(self.ip_address)
            if self.command != "peers":
                self.parent.error_messages.error_code_messages({
                    "error_code": "cmd-2484",
                    "line_code": "node_id_issue",
                    "extra": "external" if self.outside_node_request else None,
                })
            sleep(1)
        else:
            if self.ip_address in false_lookups:
                false_lookups.remove(self.ip_address)

        if self.command == "peers" and len(false_lookups) > 0:
            self.functions.event = False
            raise Exception(false_lookups)
                
        if cluster_ips:
            for desired_ip in cluster_ips:
                if desired_ip["id"] == self.nodeid:     
                    self.ip_address = desired_ip["ip"]
                    self.nodeid_to_ip = True
        else:
            self.nodeid = colored("not found?","red")
            
        if not self.nodeid_to_ip:
            self.ip_address = colored("not found?","red")
        elif self.command == "dag":
            pass
        elif "-l" not in self.argv_list: 
            self.nodeid = f"{self.nodeid[0:8]}....{self.nodeid[-8:]}"


    def _process_internal_nodeid_request(self):
        nodeid = self.functions.get_api_node_info({
            "api_host": self.ip_address,
            "api_port": self.api_port,
            "info_list": ["id","host"]
        })
        try:
            self.ip_address = nodeid[1]
            self.nodeid = nodeid[0]
        except:
            self._print_log_msg(
                "warning",
                f"cli_grab_id: attempt to access api returned no response | command [{self.command}] ip [{self.ip_address}]"
            )
            self.nodeid = colored("Unable To Retrieve","red")


    def _parse_csv_file(self):
        if not self.create_csv: return

        self.functions.create_n_write_csv({
            "file": self.csv_path,
            "rows": 
                [
                    [
                        "ip address",
                        "dag address"
                    ],
                    [
                        self.ip_address,
                        self.nodeid
                    ],
                    [
                        "balance",
                        "usd value",
                        "dag price"
                    ],
                    [
                        self.wallet_balance.balance_dag,
                        self.wallet_balance.balance_usd,
                        self.wallet_balance.token_price
                    ]
                ]
        })

        self.functions.print_paragraphs([
            ["CSV created successfully",1,"green","bold"],
            ["filename:",0,], [self.csv_file_name,1,"yellow","bold"],
            ["location:",0,], [self.parent.config_obj[self.profile]['directory_uploads'],1,"yellow","bold"]
        ]) 

    # ==== GETTERS ====

    def get_node_balance(self, command_obj):
        ip_address = command_obj["ip_address"]
        wallet = command_obj["wallet"]
        environment = command_obj["environment"]
        silent = command_obj.get("silent",False)

        balance = 0
        return_obj = {
            "balance_dag": "unavailable",
            "balance_usd": "unavailable",
            "token_price": "unavailable",
            "token_symbol": "unknown"
        }
        
        if not silent:
            self.functions.print_cmd_status({
                "text_start": "Pulling DAG details from APIs",
                "brackets": environment,
                "status": "running",
                "newline": True,
            })

            if environment != "mainnet":
                self.functions.print_paragraphs([
                    [" NOTICE ",0,"red,on_yellow"], 
                    [f"Wallet balances on {environment} are fictitious",0],["$TOKENS",0,"green"], 
                    ["and will not be redeemable, transferable, or spendable.",2],
                ])
            
        with ThreadPoolExecutor() as executor:
            self.functions.event = True
            
            session, s_timeout = self.functions.set_request_session(True)
            session.verify = True
                        
            _ = executor.submit(self.functions.print_spinner,{
                "msg": f"Pulling node balances, please wait",
                "color": "magenta",
            })                     

            for _ in range(0,4):
                try:
                    uri = self.functions.set_proof_uri({})
                    uri = f"{uri}/addresses/{wallet}/balance"
                    balance = session.get(uri, timeout=s_timeout).json()
                    balance = balance["data"]
                    balance = balance["balance"]
                except:
                    self._print_log_msg("error",f"node_id --> get_node_balance --> unable to pull request [{ip_address}] DAG address [{wallet}]")
                    self._print_log_msg("warning",f"get_node_balance session - returning [{balance}] because could not reach requested address")
                    sleep(1)
                else:
                    self._print_log_msg("debug",f"node_id --> get_node_balance --> url [{uri}]")
                    break
                finally:
                    session.close()

            self.functions.event = False      
              
        try:  
            balance = balance/1e8 
        except:
            balance = 0

        usd = []
        usd = self.functions.get_crypto_price()  # position 5 in list

        token = self.parent.config_obj[self.profile]["token_coin_id"].lower()
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
    
    
    # ==== INTERNALS ====


    # ==== HANDLERS ====

    def handle_file_request(self):
        if not "--file" in self.argv_list: return

        self.file = self.argv_list[self.argv_list.index("--file")+1]


    def handle_outside_request(self):
        if not self.wallet_only: return

        self.outside_node_request = True
        self.nodeid = self.argv_list[self.argv_list.index("-w")+1]


    def handle_local_request(self):
        if not self.outside_node_request and not self.target:
            self.functions.config_obj["global_elements"]["caller"] = "command_line"
            action_obj = {
                "action": self.command,
                "functions": self.functions,
            }
            p12 = P12Class(action_obj)
            p12.config_obj = deepcopy(self.parent.config_obj)
            extract_obj = {
                "global": self.is_global,
                "profile": self.profile,
                "return_success": True if self.parent.primary_command == "install" else False
            }  
            if self.file:
                extract_obj["ext_p12"] = self.file          

            success = p12.extract_export_config_env(extract_obj) 
            if not success and self.return_success: 
                return False
            
            self.p12 = p12
            
        return True


    def handle_ext_or_ready_state(self):
        if self.ip_address != "127.0.0.1" or self.ready_state: 
            self._set_dyn_target_ip()
            self._set_api_port()
            self._process_nodeid_request()


    def handle_dag_command(self):
        if self.command != "dag": return

        self._set_csv_file()

        # this creates a print /r status during retrieval so placed here 
        # to not affect output
        if self.wallet_only:
            self.functions.is_valid_address("DAG",False,self.nodeid)
            
        self.consensus = self.parent.cli_check_consensus({
            "caller": "dag",
            "ip_address": self.ip_address,
            "profile": self.profile,
        })
                
        for n in range(0,3):
            wallet_balance = self.get_node_balance({
                "ip_address": self.ip_address,
                "wallet": self.dag_address,
                "environment": self.parent.config_obj[self.profile]["environment"],
                "silent": False if n < 1 else True,
            })

            if n < 2 and int(float(wallet_balance["balance_dag"].replace(',', ''))) < 1:    
                self._print_log_msg(
                    "warning",
                    "The wallet balance request came back as 0, trying again before reporting 0 balance."
                )
                if n < 1:
                    sleep(1.5) # avoid asking too fast
                else:
                    self.functions.print_paragraphs([
                        ["Balance has come back a",0,"red"], ["0",0,"yellow"], ["after",0,"red"], ["2",0,"yellow"], ["attempts. Making",0,"red"],
                        ["final attempt to find a balance before continuing, after pause to avoid perceived API violations.",1,"red"],
                    ])
                    self.functions.print_timer({
                        "p_type": "cmd",
                        "seconds": 2,
                        "status": "pausing",
                        "step": -1,
                        "phrase": "Waiting",
                        "end_phrase": "before trying again",
                    })
                continue
            break    

        self.wallet_balance = SimpleNamespace(**wallet_balance)


    # ==== PRINTERS ====

    def print_display(self):
        if self.skip_display: return

        if not self.outside_node_request and not self.create_csv:
            if not self.balance_only:            
                if not self.file: self.parent.show_ip([None])
                print_out_list = [
                    {
                        "header_elements" : {
                            "P12 FILENAME": self.p12.p12_filename,
                            "P12 LOCATION": self.p12.path_to_p12,
                        },
                        "spacing": 30
                    },
                ]

            if print_out_list:
                for header_elements in print_out_list:
                    self.functions.print_show_output({
                        "header_elements" : header_elements
                    })   
            
            if "-wr" in self.argv_list:  # work around
                self._set_wr_nodeid()
            else:
                self._set_normal_nodeid()

            header_elements = {
                self.title: self.nodeid,
            }

            print_out_list = [
                {
                    "header_elements" : header_elements,
                },
            ]
            
            self._parse_csv_file()

            if not self.balance_only:
                for header_elements in print_out_list:
                    self.functions.print_show_output({
                        "header_elements" : header_elements
                    })
                        
            if self.command == "dag": 
                if not self.create_csv:
                    self._print_balances_and_consensus()
                                    
                self.snap_size = self.argv_list[self.argv_list.index("--snapshot-size")+1] if "--snapshot-size" in self.argv_list else self.snap_size
                                    
                if not "-b" in self.argv_list and not self.balance_only:
                    data = self.parent.get_and_verify_snapshots({
                        "snapshot_size": self.snap_size,
                        "environment": self.parent.config_obj[self.profile]["environment"],
                        "profile": self.profile,
                        "return_type": "raw",
                    })

                    found, elapsed = self._print_data_output(data)
                                
                    if found:
                        elapsed = self.functions.get_date_time({
                            "action": "estimate_elapsed",
                            "elapsed": elapsed
                        })
                        
                    if self.create_csv:
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
                    else:
                        self.functions.print_clear_line()
                        cprint("  No rewards found for this node.","magenta")


    def print_clear_or_pass(self):
        if self.quiet_install: return
        if not self.create_csv:
            self.functions.print_clear_line()


    def _print_balances_and_consensus(self):
        print_out_list = [
            {
                f"{self.wallet_balance.token_symbol} BALANCE": f"{self.wallet_balance.balance_dag: <18}",
                "$USD VALUE": f"{self.wallet_balance.balance_usd}",
                f"{self.wallet_balance.token_symbol} PRICE": f"{self.wallet_balance.token_price}",
                "IN CONSENSUS": self.consensus,
            }
        ]
        if self.parent.config_obj[self.profile]["layer"] > 0 or self.balance_only:
            print_out_list[0].pop("IN CONSENSUS", None)
    
        for header_elements in print_out_list:
            self.functions.print_show_output({
                "header_elements" : header_elements
            })  


    def _print_append_to_csv(self,reward,init=False):
        rows = []
        if init:
            rows.append(["timestamp","ordinal","reward","cumulative"])
        rows.append(
            [
                reward["timestamp"],
                reward["ordinal"],
                reward["amount"]/1e8,
                self.total_rewards/1e8
            ]
        )
        self.functions.create_n_write_csv({
            "file": self.csv_path,
            "rows": rows,
        })


    def _print_append_output(self,reward, first=True):
        if first:
            print("")
            print_out_list = [
                {
                    "header_elements": {
                        "TIMESTAMP": "",
                        "ORDINAL": "",
                        "REWARD": "",
                        "TOTAL REWARDS": "",
                    },
                    "spacing": 25,
                    "1": 10,
                    "2": 15,
                },
            ]
            
            for header_elements in print_out_list:
                self.functions.print_show_output({
                    "header_elements" : header_elements
                })
            print("\033[F", end="")
        
        p_reward = str(reward["amount"]/1e8)
        spacing = 17
        
        print(f'  {reward["timestamp"]}',end="   ")
        print(f'{reward["ordinal"]}',end="     ")
        print(f"{p_reward:<{spacing}}",end="")
        print(f'{self.total_rewards/1e8}')


    def _print_data_output(self,data):
        elapsed = data["elapsed_time"]
        data = data["data"]
        self.rewards = []

        found = False        
        self._set_do_more()

        print("")
        self.functions.print_cmd_status({
            "text_start": "Reviewing",
            "brackets": "snapshot rewards",
            "text_end": "history size",
            "status": str(self.snap_size),
            "status_color": "yellow",
            "newline": True,
        })
        self.functions.print_cmd_status({
            "text_start": "Searching ordinals for rewards",
            "newline": True,
        })
        
        end_ordinal = max(data, key=lambda ordinal: ordinal['ordinal'])['ordinal']
        for n, hash in enumerate(data):
            remaining = len(data)-(n+1)
            remaining = f"0{remaining}" if remaining < 10 else str(remaining)
            self.functions.print_cmd_status({
                "text_start": "Ordinal",
                "brackets":  f"[{hash['ordinal']}] [{remaining}]",
                "text_end": "from start ordinal",
                "status": end_ordinal,
                "newline": False,
            })
            reward_snaps = self.functions.get_snapshot({
                "action": "rewards",
                "history": 1,
                "environment": self.parent.config_obj[self.profile]["environment"],
                "profile": self.profile,
                "ordinal": hash["ordinal"],
                "return_on_error": True,
                "return_type": "raw",
            })   
            if len(reward_snaps) > 0: 
                for reward_snap in reward_snaps:
                    reward_snap["timestamp"] = data[n]["timestamp"]
                    reward_snap["ordinal"] = data[n]["ordinal"]
                    
                self.rewards.append(reward_snap)

        found = self._print_individual_reward()
        return found, elapsed


    def _print_log_msg(self,log_type,msg):
        log_method = getattr(self.log, log_type, None)
        log_method(f"{self.__class__.__name__} --> {msg}")


    def _print_individual_reward(self):
        if len(self.rewards) < 1: return

        found = False
        show_title = True
        data_point = 0

        print("")
        for reward in self.rewards:
            if reward["destination"] == self.dag_address:
                found = True
                self.total_rewards += reward["amount"]
                if show_title:
                    show_title = False
                    if self.create_csv:
                        self._print_append_to_csv(reward,True)
                    else:
                        self._print_append_output(reward,True)
                else: 
                    if reward["amount"] > 999999: # 1e8
                        if self.create_csv:
                            self._print_append_to_csv(reward,False)
                        else:
                            self._print_append_output(reward,False)
                            if self.do_more and data_point % self.more_break == 0 and data_point > 0:
                                self.more = self.functions.print_any_key({
                                    "quit_option": "q",
                                    "newline": "both",
                                })
                                if self.more:
                                    cprint("  Terminated by Node Operator","red")
                                    return
                                show_title = True  
                data_point += 1 
                
        return found
                    
                    
if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")  

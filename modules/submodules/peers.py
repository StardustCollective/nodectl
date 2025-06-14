import re
import multiprocessing

from os import get_terminal_size        
from termcolor import colored, cprint
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor

class Peers():
    
    def __init__(self, setter, getter):
        self.parent_setter = setter
        self.parent_getter = getter


    # setters 
    # ==============

    def set_parameters(self):
        self.config_obj = self.parent_getter("config_obj")
        self.command_list =self.parent_getter("command_list")
        self.functions = self.parent_getter("functions")
        
        self.cli_grab_id = self.parent_getter("cli_grab_id")
        self.cli_nodeid2dag = self.parent_getter("cli_nodeid2dag")
        
        self.error_messages = self.parent_getter("error_messages")
        self.profile = self.command_list[self.command_list.index("-p")+1] 
        self.cluster_info = self.config_obj["global_elements"]["cluster_info_lists"][self.profile]    
                
        self.log = self.parent_getter("log")
        self._print_log_msg("info",f"show peers requested")

        self.console_size = get_terminal_size()
        self.count_args = ["-p", self.profile]
        self.sip = {}
        self.nodeid, self.csv_file_name = "", ""
 
        self.is_basic = False
        self.is_extended = False
        self.csv_info_type_dict = False
        self.states = False
        self.peer_results = False
        self.requested_states = False
        
        self.do_more = False
        self.create_csv = True if "-csv" in self.command_list or "--csv" in self.command_list else False
        
        self.info_type_list = False
        self.print_header = False
        self.found_results = False

        self.first_item = True

        self.more_break = 0
        self.more_subtrahend = 0

        self.lookups = ["peer_list"]
        self.retry_list = []
        self.search_title = "all peers"
        self.command_list = ["--state" if item == "--states" else item for item in self.command_list]
        
        self._set_do_print()


    def set_pagination(self):
        if "-np" in self.command_list: return

        self.do_more = True

        self.more_break = round(self.console_size.lines)-20 
        if "--extended" in self.command_list:
            self.more_subtrahend = 4
            if self.info_type_list:
                self.more_subtrahend += len(set(self.info_type_list))


    def set_title(self):
        title = "SHOW PEERS"
        
        if self.requested_states: 
            lookups = []
            search_title = self.states[0] if len(self.requested_states) < 2 else "filtered states"
            for s in self.states:
                lookups.append(f"{s.lower()}")
            title = f"SHOW PEERS - {search_title}"
            
        self.functions.print_header_title({
            "line1": title,
            "single_line": True,
            "newline": "both"  
        })    


    def set_main_print_out(self):
        print_out_obj = {
            "PROFILE": self.profile,
            "SOURCE NODE IP": self.sip["ip"],
            "SN PUBLIC PORT": self.sip['publicPort']
        }
        print_out_list = [print_out_obj]
        
        for header_elements in print_out_list:
            self.functions.print_show_output({
                "header_elements" : header_elements
            })  
            
    
    def _set_do_print(self):
        self.do_print = True
        if self.create_csv:
            self.do_print = True if "--print" in self.command_list else False    
            
            
    # getters
    # ==============

    def _get_peer_status(self):
        for key, value in self.peer_results.items():
            if key == "peer_list":
                continue
            if isinstance(value,list):
                if self.current_peer in value:
                    return key
        return "unknown"


    # parsers and processors
    # ==============
    
    def _process_dag_address(self, node):
        return [node['ip'], node['publicPort'], node['id'], node["state"], self._parse_nodeid2dag(node['id'])]


    def _parse_nodeid2dag(self, nodeid):
        wallet = self.cli_nodeid2dag({
            "nodeid": nodeid,
            "caller": "show_peers",
            "profile": self.profile,
        })
        return wallet        
            
    # handlers 
    # ==============
    
    def handle_csv_file(self):
        if not self.create_csv: return

        if not "--output" in self.command_list:
            self.functions.print_paragraphs([
                [" NOTE ",0,"blue,on_yellow"], 
                ["The",0],["--csv",0,"yellow","bold"],
                ["option will default to include:",0],["--extended",2,"yellow","bold"],
            ])
        if "--output" in self.command_list:
            self.csv_file_name = self.command_list[self.command_list.index("--output")+1]
            if "/" in self.csv_file_name:
                self.error_messages.error_code_messages({
                    "error_code": "per-442",
                    "line_code": "invalid_file_or_path",
                    "extra": self.csv_file_name
                })
        else:
            prefix = self.functions.get_date_time({"action": "datetime"})
            self.csv_file_name = f"{prefix}-peers-data.csv"
            
        if "--basic" in self.command_list: 
            self.command_list.remove("--basic")

        self.command_list.extend(["--extended","-np"])
        self.csv_path = f"{self.config_obj[self.profile]['directory_uploads']}{self.csv_file_name}"


    def handle_source_node(self):
        if "-t" in self.command_list:
            self.functions.print_paragraphs([ 
                [" ERROR ",0,"yellow,on_red"], ["The",0],["-t",0,"yellow"],
                ["target option has been removed.",2],
                ["Please use",0],
                ["--source",0,"yellow"],["or",0],["-s",0,"yellow"], ["to request",0],
                ["a source node to obtain other peer parameters from.",2],
                
                ["You may also included the",0], ["--port",0,"yellow"],
                ["option.",2],
            ])
            exit(colored("  Please try again.","red"))
            
        if "-s" in self.command_list:
            self.sip["ip"] = self.command_list[self.command_list.index("-s")]
        elif "--source" in self.command_list:
            self.sip["ip"] = self.command_list[self.command_list.index("--source")]
            
        if self.sip.get("ip"):
            self.functions.test_hostname_or_ip(self.sip["ip"], True, False)
            for node in self.config_obj["global_elements"]["cluster_info_list"][self.profile].items():
                if node["ip"] == self.sip["ip"]:
                    self.sip["publicPort"] = node["publicPort"]
        else:
            self.sip["ip"] = self.config_obj["global_elements"]["api_peers"][self.profile]["ip"]
            self.sip['publicPort'] = self.config_obj["global_elements"]["api_peers"][self.profile]["publicPort"]


    def handle_state_specific_request(self):
        if "--state" not in self.command_list: return
        error = False
        state = []

        try:
            requested_states = self.command_list[self.command_list.index("--state")+1]
            requested_states = requested_states.strip("[]").split(",")
        except:
            error = True

        if not error:
            if not isinstance(requested_states, list):
                requested_states = [requested_states]

            states = self.functions.get_node_states("on_network_and_stuck")
            for requested_state in requested_states:
                state.append(next((s[0] for s in states if requested_state == s[1].replace("*", "")), False))
                if "ready" in requested_states or "Ready" in requested_states:
                    state.append("Ready")

            if not any(state) or len(state) < 1:
                error = True

        if error:
            self.error_messages.error_code_messages({
                "error_code": "per-1008",
                "line_code": "invalid_option",
                "extra": requested_state,
                "extra2": "supported states: dip, ob, wfd, wfr, wfo, and wfd (or list of [dip,ob])",
            })

        self.states = [x for x in state if x is not False]
        self.requested_states = requested_states
        self.cluster_info = [node for node in self.cluster_info if node["state"] in self.states]


    def handle_info_type_request(self):
        if "--info-type" not in self.command_list: return

        try:
            info_type =  self.command_list[self.command_list.index("--info-type")+1]
            info_type_list = info_type.strip("[]").split(",")
        except Exception as e:
            self._print_log_msg("error",f"unable to create info_list per request, skipping [{e}]")
        
        if info_type_list:
            for item in ["ip_address","ip-address","nodeid","node-id","node_id"]:
                if item in info_type_list:
                    info_type_list.remove(item)
            self.info_type_list = set(info_type_list) # remove dups

        self.command_list.append("--extended")
        if "--basic" in self.command_list: self.command_list.remove("--basic")


    def handle_wallets(self):
        if "--basic" in self.command_list: return
        
        length = len(self.cluster_info)
        self.functions.print_cmd_status({
            "text_start": "Calculating",
            "brackets": str(length),
            "text_end": "$DAG addresses",
            "status": "running",
            "newline": True,
        })
        cprint("  This will take a moment...","red")

        with ThreadPoolExecutor() as t_exectutor:
            self.functions.event = True
            _ = t_exectutor.submit(self.functions.print_spinner,{
                "msg": f"Calculating $DAG addresses",
                "color": "yellow",
            })          
                     
            with ProcessPoolExecutor(max_workers=multiprocessing.cpu_count()) as executor:
                self.peer_results = list(executor.map(self._process_dag_address, self.cluster_info))
            
            self.functions.event = False   
        
        self.functions.print_clear_line(3, {"backwards": True})
        

    def _handle_is_extended(self,node):
        ip, port, id, state, wallet = node
        
        status_results  = f"  {colored('PEER IP:','blue',attrs=['bold'])} {ip}\n"  
        status_results  += f"  {colored('PEER STATE:','blue',attrs=['bold'])} {state}\n"                      
        csv_info_type_dict = False

        cn_requests = self.parent_getter("node_service").get_self_value("cn_requests")

        # pull info_list from cn_requests and then make sure the CSV is working
        # correctly
        # =====================================================================
                
        if self.info_type_list:
            csv_info_type_dict = {}
            for item in self.info_type_list:
                info_type_results = cn_requests.get_node_info_from_cluster({
                    "end_point": "metrics",
                    "ip": ip,
                    "publicPort": port,
                    "profile": self.profile,
                    "return_type": "text",
                })
                if info_type_results is None or not info_type_results:
                    self._print_log_msg("error",f"info_type requested but not found: [{self.info_type_list}]")
                    status_results += f"  {colored('WALLET:','blue',attrs=['bold'])} {self.wallet}\n" 
                else:
                    info_type_results = info_type_results.split("\n")
                    distro = False
                    title = item
                    if item == "distro":
                        distro = True
                        item = "jvm_info"
                        title = "distro"
                    for line_item in info_type_results:
                        info_value = "N/A"
                        if line_item.startswith(item):
                            info_value = line_item
                            if distro:
                                # distro = False
                                # distro_match = re.search(r'vendor="(\w+)"', info_value)
                                # distro_name = distro_match.group(1) if distro_match else "N/A"
                                # ubuntu_match = re.search(r'Ubuntu-0ubuntu\d{2}\.(\d{2})', info_value, re.IGNORECASE)
                                # debian_match = re.search(r'1deb(\d{1,2})', info_value, re.IGNORECASE)
                                # if distro_name.lower() == "ubuntu" and ubuntu_match:
                                #     version = ubuntu_match.group(1)
                                # elif distro_name.lower() == "debian" and debian_match:
                                #     version = debian_match.group(1)
                                # else:
                                #     version = "N/A"
                                # info_value = f"{distro_name} | version: {version}"
                                distro = False
                                # distro_match = re.search(r'vendor="([^"]+)"', info_value)
                                # distro_name = distro_match.group(1) if distro_match else "N/A"

                                # # Match Ubuntu version like "0ubuntu122.04", "0ubuntu2204", etc.
                                # ubuntu_match = re.search(r'0ubuntu(\d{2,3})\.(\d{2})', info_value, re.IGNORECASE)
                                # debian_match = re.search(r'1deb(\d{1,2})', info_value, re.IGNORECASE)

                                # if distro_name.lower() == "ubuntu" and ubuntu_match:
                                #     version = f"{ubuntu_match.group(1)}.{ubuntu_match.group(2)}"
                                # elif distro_name.lower() == "debian" and debian_match:
                                #     version = f"{debian_match.group(1)}"
                                # else:
                                #     version = "N/A"

                                # info_value = f"{distro_name} | version: {version}"
                                distro_match = re.search(r'vendor="([^"]+)"', info_value)
                                distro_name = distro_match.group(1) if distro_match else "N/A"

                                # Match Ubuntu version like "0ubuntu122.04" or "0ubuntu22.04"
                                ubuntu_match = re.search(r'0ubuntu(\d{2,3})\.(\d{2})', info_value, re.IGNORECASE)
                                debian_match = re.search(r'1deb(\d{1,2})', info_value, re.IGNORECASE)

                                if distro_name.lower() == "ubuntu" and ubuntu_match:
                                    major = ubuntu_match.group(1)
                                    minor = ubuntu_match.group(2)
                                    # Normalize to last two digits of the major version
                                    if len(major) > 2:
                                        major = major[-2:]
                                    version = f"{major}.{minor}"
                                elif distro_name.lower() == "debian" and debian_match:
                                    version = f"{debian_match.group(1)}"
                                else:
                                    version = "N/A"

                                info_value = f"{distro_name} | version: {version}"
                                pass
                            break
                    status_results += f"  {colored(f'{title.upper()}:','blue',attrs=['bold'])} {info_value}\n" 
                    csv_info_type_dict[title] = info_value

        status_results += f"  {colored('WALLET:','blue',attrs=['bold'])} {wallet}\n"                      
        status_results += f"  {colored('NODE ID:','blue',attrs=['bold'])} {id}\n" 

        if self.create_csv:
            csv_header = ["Peer Ip","Wallet","Node Id","State"]
            if csv_info_type_dict:
                csv_header.extend(self.info_type_list)

            csv_row = [ip, wallet, id, state]
            if csv_info_type_dict:
                for v in csv_info_type_dict.values():
                    csv_row.append(v)

            if self.first_item:
                self.functions.create_n_write_csv({
                "file": self.csv_path,
                "row": csv_header
                })
            self.functions.create_n_write_csv({
                "file": self.csv_path,
                "row": csv_row
            })

        self.status_results = status_results


    # printers
    # ==============

    def print_submenu(self):
        self.print_header = True
        self.peer_title1 = colored("NETWORK PEER IP","blue",attrs=["bold"])
        self.peer_title2 = colored("NODE ID","blue",attrs=["bold"])
        self.peer_title3 = colored("WALLET","blue",attrs=["bold"])
        self.peer_title4 = False
        if self.lookups[0] != "peer_list" or self.requested_states:
            self.peer_title4 = colored("STATE","blue",attrs=["bold"])
        status_header = f"  {self.peer_title1: <36}"

        if "--basic" in self.command_list:
            self.is_basic = True
            
        elif "--extended" in self.command_list:
            self.is_extended = True
            self.print_header = False
        else:
            status_header += f"{self.peer_title2: <36}"
            status_header += f"{self.peer_title3: <36}"
            
        if not self.is_basic: 
            print("")
            
        if self.peer_title4:
            status_header += f"{self.peer_title4: <36}"

        self.status_header = status_header
        
        if not self.create_csv or self.do_print:
            print(self.status_header)


    def print_results(self):
        break_counter = self.more_break
        
        try:
            for item, node in enumerate(self.peer_results):
                if self.is_basic:
                    pass
                else:
                    ip, port, id, state, wallet = node
                    ip = f"{ip}:{port}"
                
                if self.requested_states and not self.is_extended:
                    wallet = f"{wallet[0:8]}....{wallet[-8:]}"
                    
                if self.do_more and break_counter < 1 and item > 0:
                    more = self.functions.print_any_key({
                        "quit_option": "q",
                        "newline": "both",
                    })
                    if more: break
                    self.print_header = True
                    break_counter = self.more_break
                    
                if self.is_extended:
                    self._handle_is_extended(node)
                    self.first_item = False
                    status_results = self.status_results    
                                
                elif self.is_basic:
                    spacing = 23
                    self.status_results = f"  {ip: <{spacing}}"                        
                else:                
                    spacing = 23
                    id = f"{id[0:8]}....{id[-8:]}"
                    status_results = f"  {ip: <{spacing}}"                      
                    status_results += f"{id: <{spacing}}"                      
                    status_results += f"{wallet: <{spacing}}"
                    if self.requested_states:
                        status_results += f"{state: <{spacing}}"
                    status_results = status_results 
                
                break_counter -= self.more_subtrahend+1

                if not self.create_csv or self.do_print:
                    print(status_results)  
        except Exception as e:
            self.error_messages.error_code_messages({
                "error_code": "per-442",
                "line_code": "profile_error",
                "extra": self.profile
            })     

        if self.create_csv and item < 1:
            self.functions.print_cmd_status({
                "text_start": "Creating",
                "brackets": self.csv_file_name,
                "text_end": "file",
                "status": "running",
                "newline": True,
            })
            
        print_end = "no results"
        print_color = "red"
        if len(self.peer_results) > 0:
            print_end = "complete"
            print_color = "green"

        print("")
        self.functions.print_cmd_status({
            "text_start": "Peer search",
            "brackets": "completed",
            "status": print_end,
            "status_color": print_color,
            "newline": True,
        })

        if len(self.peer_results) > 0:
            self.functions.print_cmd_status({
                "text_start": "Results found",
                "status": str(len(self.peer_results)),
                "status_color": "yellow",
                "newline": True,
            })


    def print_csv_success(self):
        if not self.create_csv: return

        self._print_log_msg("info",f"csv file created: location: [{self.csv_file_name}]") 
        self.functions.print_paragraphs([
            ["",1],["CSV created successfully",1,"green","bold"],
            ["filename:",0,], [self.csv_file_name,1,"yellow","bold"],
            ["location:",0,], [self.config_obj[self.profile]['directory_uploads'],1,"yellow","bold"]
        ])
            
        
    def _print_log_msg(self,log_type,msg):
            log_method = getattr(self.log, log_type, None)
            log_method(f"{self.__class__.__name__} --> {msg}")
            

if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")  
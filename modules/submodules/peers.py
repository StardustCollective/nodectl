import ast
import re
from os import get_terminal_size        
from termcolor import colored

from modules.troubleshoot.errors import Error_codes

class Peers():
    
    def __init__(self,parent):
        self.config_obj = parent.config_obj
        self.command_list =parent.command_list
        self.functions = parent.functions
        self.error_messages = Error_codes(self.functions)
        self.profile = self.command_list[self.command_list.index("-p")+1] 
        self.parent = parent       


    # handlers 
    # ==============

    def handle_params(self):
        self.parent.log.logger[self.parent.log_key].info(f"show peers requested")

        self.console_size = get_terminal_size()
        self.count_args = ["-p", self.profile]
        self.sip = {}
        self.nodeid, self.csv_file_name = "", ""
        
        self.is_basic = False
        self.create_csv = False
        self.csv_info_type_dict = False
        self.states = False
        self.requested_state = False
        self.requested_states = False
        self.do_more = False
        self.info_type_list = False
        self.peer_results = False
        self.print_header = False
        self.first_item = True

        self.more_break = 0
        self.more_subtrahend = 0

        self.lookups = ["peer_list"]
        self.search_title = "all peers"


    def handle_csv_file(self):
        if "-csv" not in self.command_list and "--csv" not in self.command_list: return

        self.create_csv = True 

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
                    "error_code": "cmd-442",
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
        source = False
        if "-t" in self.command_list:
            self.print_paragraphs([ 
                [" WARNING ",0,"red,on_yellow"], ["The",0],["-t",0,"yellow"],
                ["target option has been deprecated.  Please use",0],
                ["--source",0,"yellow"],["or",0],["-s",0,"yellow"], ["to request",0],
                ["a source node to obtain peer parameters from...",2],
            ])
            source = self.command_list[self.command_list.index("-t")+1]
        elif "-s" in self.command_list or "--source" in self.command_list:
            if "-s" in self.command_list:
                source = self.command_list[self.command_list.index("-s")+1]
            if "--source" in self.command_list:
                source = self.command_list[self.command_list.index("--source")+1]

        if source:
            self.sip = self.functions.get_info_from_edge_point({
                "profile": self.profile,
                "caller": "show_peers",
                "specific_ip": source,
            })
            self.count_args.extend(["-s",self.sip])
        else:
            self.sip = self.functions.get_info_from_edge_point({
                "profile": self.profile,
                "caller": "show_peers",
            })


    def handle_state_specific_request(self):
        if "--state" not in self.command_list: return

        state = []
        requested_states = self.command_list[self.command_list.index("--state")+1]

        try:
            requested_states = ast.literal_eval(requested_states)
        except:
            pass

        if not isinstance(requested_states, list):
            requested_states = [requested_states]

        states = self.functions.get_node_states("on_network_and_stuck")
        for requested_state in requested_states:
            state.append(next((s[0] for s in states if requested_state == s[1].replace("*", "")), False))

        if not any(state) or len(state) < 1:
            self.error_messages.error_code_messages({
                "error_code": "cli-1008",
                "line_code": "invalid_option",
                "extra": requested_state,
                "extra2": "supported states: dip, ob, wfd, wfr, wfo, and wfd (or list of [\"dip\",\"ob\"])",
            })
        self.states = [x for x in state if x is not False]
        self.requested_states = requested_states


    def handle_info_type_request(self):
        if "--info_type" not in self.command_list: return

        info_type =  self.command_list[self.command_list.index("--info_type")+1]
        if info_type.startswith("[") and info_type.endswith("]"):
            try:
                info_type_list = ast.literal_eval(info_type)
                if not isinstance(info_type_list, list):
                    raise
            except Exception as e:
                self.parent.log.logger[self.parent.log_key].error(f"unable to create info_list per request, skipping [{e}]")
        else:
            try:
                info_type_list = [info_type]
            except:
                self.parent.log.logger[self.parent.log_key].warning(f"info_type request does not look like a list, skipping [{info_type_list}].")
        
        if info_type_list:
            for item in ["ip_address","ip-address","nodeid","node-id","node_id"]:
                if item in info_type_list:
                    info_type_list.remove(item)
            self.info_type_list = set(info_type_list) # remove dups

        self.command_list.append("--extended")
        if "--basic" in self.command_list: self.command_list.remove("--basic")

    
    def handle_peer_error(self):
        if self.peer_results == "error": 
            self.parent.log.logger[self.parent.log_key].error(f"show peers | attempt to access peer count with ip [{self.sip}] failed")
            self.error_messages.error_code_messages({
                "error_code": "cmd-179",
                "line_code": "ip_not_found",
                "extra": self.sip,
                "extra2": None
            }) 


    def handle_local_host(self):
        if self.sip["ip"] == "127.0.0.1":
            self.sip["ip"] = self.parent.ip_address


    def _handle_is_basic(self,peer,public_port):
        nodeid = self.parent.cli_grab_id({
            "dag_addr_only": True,
            "command": "peers",
            "argv_list": ["-p",self.profile,"-t",peer,"--port",public_port,"-l"]
        })
        if isinstance(nodeid,list):
            nodeid = "UnableToRetrieve"
            wallet = "UnableToRetrieve"
        else:
            wallet = self.parent.cli_nodeid2dag({
                "nodeid": nodeid,
                "caller": "show_peers",
                "profile": self.profile,
            })

        self.nodeid = nodeid
        self.wallet = wallet


    def _handle_is_extended(self,peer,public_port):
        status_results  = f"  {colored('PEER IP:','blue',attrs=['bold'])} {self.print_peer}\n"  
        peer_state = self._get_peer_status()              
        status_results  += f"  {colored('PEER STATE:','blue',attrs=['bold'])} {peer_state}\n"                      
        csv_info_type_dict = False
        
        if self.info_type_list:
            csv_info_type_dict = {}
            for item in self.info_type_list:
                info_type_results = self.functions.get_api_node_info({
                        "api_host": peer,
                        "api_port": public_port,
                        "api_endpoint": "/metrics",
                        "result_type": "text",
                    })
                if info_type_results is None:
                    self.parent.log.logger[self.parent.log_key].warning(f"info_type requested but not found: [{self.info_type_list}]")
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
                                distro = False
                                distro_match = re.search(r'vendor="(\w+)"', info_value)
                                distro_name = distro_match.group(1) if distro_match else "N/A"
                                ubuntu_match = re.search(r'1ubuntu\d*(\d{2}\.\d{2})', info_value, re.IGNORECASE)
                                debian_match = re.search(r'1deb(\d{1,2})', info_value, re.IGNORECASE)
                                if distro_name.lower() == "ubuntu" and ubuntu_match:
                                    version = ubuntu_match.group(1)
                                elif distro_name.lower() == "debian" and debian_match:
                                    version = debian_match.group(1)
                                else:
                                    version = "N/A"
                                info_value = f"{distro_name} | version: {version}"
                            break
                    status_results += f"  {colored(f'{title.upper()}:','blue',attrs=['bold'])} {info_value}\n" 
                    csv_info_type_dict[title] = info_value

        status_results += f"  {colored('WALLET:','blue',attrs=['bold'])} {self.wallet}\n"                      
        status_results += f"  {colored('NODE ID:','blue',attrs=['bold'])} {self.nodeid}\n" 

        if self.create_csv:
            csv_header = ["Peer Ip","Wallet","Node Id"]
            if csv_info_type_dict:
                csv_header.extend(self.info_type_list)

            csv_row = [self.print_peer,self.wallet,self.nodeid]
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


    # getters
    # ==============

    def get_ext_ip(self):
        try:
            if self.sip["ip"] == "self": 
                self.sip["ip"] = self.functions.get_ext_ip()
        except: 
            try:
                self.sip["ip"] = self.functions.get_ext_ip()
            except:
                self.error_messages.error_code_messages({
                    "error_code": "cli-996",
                    "line_code": "off_network",
                    "extra": f'{self.config_obj[self.profile]["edge_point"]}:{self.config_obj[self.profile]["edge_point_tcp_port"]}',
                    "extra2": self.config_obj[self.profile]["layer"],
                })


    def _get_peer_status(self):
        for key, value in self.peer_results.items():
            if key == "peer_list":
                continue
            if isinstance(value,list):
                if self.current_peer in value:
                    return key
        return "unknown"

    # setters 
    # ==============

    def set_pagination(self):
        if "-np" in self.command_list: return

        self.do_more = True

        self.more_break = round(self.console_size.lines)-20 
        if "--extended" in self.command_list:
            self.more_subtrahend = 4
            if self.info_type_list:
                self.more_subtrahend += len(set(self.info_type_list))


    def set_title(self):
        if not self.requested_states: return

        lookups = []
        search_title = self.states[0] if len(self.requested_states) < 2 else "filtered states"
        for s in self.states:
            lookups.append(f"{s.lower()}")
            
        self.functions.print_header_title({
            "line1": f"SHOW PEERS - {search_title}",
            "single_line": True,
            "newline": "both"  
        })    


    def set_main_print_out(self):
        print_out_obj = {
            "PROFILE": self.profile,
            "SEARCH NODE IP": self.sip["ip"],
            "SN PUBLIC PORT": self.sip['publicPort']
        }
        print_out_list = [print_out_obj]
        
        for header_elements in print_out_list:
            self.functions.print_show_output({
                "header_elements" : header_elements
            })  


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
        else:
            status_header += f"{self.peer_title2: <36}"
            status_header += f"{self.peer_title3: <36}"
        if self.peer_title4:
            status_header += f"{self.peer_title4: <36}"

        self.status_header = status_header


    def print_results(self):
        for lookup in self.lookups:
            break_counter = self.more_break
            for item, peer in enumerate(self.peer_results[lookup]):
                do_print = True
                public_port = self.peer_results["peers_publicport"][item]
                
                if not self.is_basic: # will do this later otherwise
                    self._handle_is_basic(peer,public_port)
                    
                if self.do_more and break_counter < 1 and item > 0:
                    more = self.functions.print_any_key({
                        "quit_option": "q",
                        "newline": "both",
                    })
                    if more: break
                    self.print_header = True
                    break_counter = self.more_break
                else:
                    break_counter -= self.more_subtrahend+1
                    
                self.current_peer = peer
                self.print_peer = f"{peer}:{public_port}" 

                if "--extended" in self.command_list:
                    self._handle_is_extended(peer,public_port)
                    self.first_item = False
                elif self.is_basic:
                    spacing = 23
                    status_results = f"  {self.print_peer: <{spacing}}"                        
                else:
                    if self.requested_states:
                        do_print = False
                        self.status_results = False
                        for state in self.states:
                            if peer in self.peer_results[state.lower()]:
                                do_print = True
                                break
                    if do_print:
                        spacing = 23
                        if self.nodeid != "UnableToReach": self.nodeid = f"{self.nodeid[0:8]}....{self.nodeid[-8:]}"
                        if self.nodeid != "UnableToReach": self.wallet = f"{self.wallet[0:8]}....{self.wallet[-8:]}"
                        status_results = f"  {self.print_peer: <{spacing}}"                      
                        status_results += f"{self.nodeid: <{spacing}}"                      
                        status_results += f"{self.wallet: <{spacing}}"   
                        if self.requested_states:
                            status_results += f"{state: <{spacing}}"
                        elif self.peer_title4:
                            status_results += f"{lookup: <{spacing}}"  
                        self.status_results = status_results 
    
                if self.create_csv and item == 0:
                    print("")
                    self.functions.print_cmd_status({
                        "text_start": "Creating",
                        "brackets": self.csv_file_name,
                        "text_end": "file",
                        "status": "running",
                        "newline": True,
                    })
                elif not self.create_csv and self.status_results:
                    if self.print_header:    
                        print(self.status_header)
                        self.print_header = False
                    print(self.status_results)


    def print_csv_success(self):
        if not self.create_csv: return

        self.parent.log.logger[self.parent.log_key].info(f"csv file created: location: [{self.csv_file_name}]") 
        self.functions.print_paragraphs([
            ["CSV created successfully",1,"green","bold"],
            ["filename:",0,], [self.csv_file_name,1,"yellow","bold"],
            ["location:",0,], [self.config_obj[self.profile]['directory_uploads'],1,"yellow","bold"]
        ])


if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")  

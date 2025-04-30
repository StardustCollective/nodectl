from termcolor import colored
from os import get_terminal_size

class CurrentRewards():
    
    def __init__(self,parent,command_list):
        self.parent = parent   
        self.profile = self.parent.functions.default_profile
        self.command_list = command_list
        self.error_messages = self.parent.error_messages
        self.functions = self.parent.functions
        self.config_obj = self.parent.config_obj
        self.node_id_obj = self.parent.node_id_obj
        self.log = self.parent.log.logger[self.parent.log_key]

        self._print_log_msg("info","CurrentRewards class initialized")


    # ==== SETTERS ====

    def set_parameters(self):
        self.reward_amount = dict()

        self.color = "red"
        self.found = "FALSE"
        self.title = "NODE P12"
        self.api_max_history = 100 # current limit before API error

        self.argv_list = False
        self.search_dag_addr = False
        self.target_dag_addr = False
        self.current_ordinal = False
        self.create_csv = False
        self.data = False

        self.print_out_list = []
        self.first = [0,0]
        
        self.csv_path = None
        self.csv_file_name = None
        self.elapsed = None

        self.snapshot_size = self.command_list[self.command_list.index("-s")+1] if "-s" in self.command_list else 50
        
        if "-p" in self.command_list:
            self.profile = self.command_list[self.command_list.index("-p")+1]
            self.functions.check_valid_profile(self.profile)


    def set_search_n_target_addr(self):
        if "-w" in self.command_list:
            self.search_dag_addr = self.command_list[self.command_list.index("-w")+1]
            self.functions.is_valid_address("DAG",False,search_dag_addr)
            self.title = "REQ WALLET"
            return

        if self.node_id_obj:
            self.search_dag_addr = self.node_id_obj[f"{self.profile}_wallet"]
            return

        if "--peer" in self.command_list:
            try:
                target_ip_address = self.command_list[self.command_list.index("--peer")+1]
            except:
                self._send_error("cmd-1741","input_error","target","must be a valid IP address")
            
            if not self.functions.is_valid_address("ip_address",True,target_ip_address):
                self._send_error("cmd-1802","input_error","target","must be a valid IP address or not found on cluster")
            public_port = self.parent.get_info_from_edge_point({
                "caller": "get_peer_count",
                "profile": self.profile,
                "desired_key": "publicPort",
                "specific_ip": target_ip_address,
            })
            argv_list = ["-p",self.profile,"-t",target_ip_address,"--port", public_port,"-l"]
            self.target_dag_addr = target_ip_address
            return

        self.parent.cli_grab_id({
            "dag_addr_only": True,
            "command": "dag",
            "argv_list": argv_list if argv_list else ["-p",self.profile]
        })
        search_dag_addr = self.parent.nodeid.strip("\n")
        self.search_dag_addr = self.parent.cli_nodeid2dag({
            "nodeid": search_dag_addr,
            "profile": self.profile,
        })


    def set_csv(self):
        if not "--csv" in self.command_list: return

        self.functions.print_cmd_status({
            "text_start": "Create csv for",
            "brackets": "show current rewards",
            "status": "running"
        })

        self.create_csv = True 

        if "-np" not in self.command_list:
            self.command_list.append("-np")

        if "--output" in self.command_list:
            csv_file_name = self.command_list[self.command_list.index("--output")+1]
            if "/" in csv_file_name:
                self._send_error("cmd-442","invalid_file_or_path",csv_file_name)
        else:
            prefix = self.functions.get_date_time({"action": "datetime"})
            csv_file_name = f"{prefix}-{self.search_dag_addr[0:8]}-{self.search_dag_addr[-8:]}-rewards-data.csv"

        self.csv_path = f"{self.config_obj[self.profile]['directory_uploads']}{csv_file_name}"
        self.csv_file_name = csv_file_name


    def set_elapsed_time(self):
        self.elapsed = self.functions.get_date_time({
            "action": "estimate_elapsed",
            "elapsed": self.data["elapsed_time"]
        })


    def set_print_out_list(self):
        self.title = f"{self.title} ADDRESS FOUND ({colored(self.found,self.color)}{colored(')','blue',attrs=['bold'])}"
        
        first_reward_addr = self.first[0]
        if len(self.first[0]) > 40:
            first_reward_addr = f"{self.first[0][:18]}....{self.first[0][-18:]}"

        self.functions.print_paragraphs([
            ["All reward amounts are in",0],["$DAG",0,"green","bold"], ["tokens.",2]
        ])

        self.print_out_list = [
            {
                "header_elements": {
                "START SNAPSHOT": self.data["data"][-1]["timestamp"],
                "STOP SNAPSHOT": self.data["data"][0]["timestamp"],
                },
                "spacing": 25,
            },
            {
                "header_elements": {
                "START ORDINAL": self.data["start_ordinal"],
                "END ORDINAL": self.data["end_ordinal"],
                },
                "spacing": 25,
            },
            {
                "header_elements": {
                "ELAPSED TIME": self.elapsed,
                "SNAPSHOTS": self.snapshot_size,
                "REWARDED COUNT": len(self.reward_amount),
                },
                "spacing": 14,
            },
            {
                "header_elements": {
                "-BLANK-":None,
                f"{self.title}": colored(self.search_dag_addr,self.color),
                },
            },
            {
                "header_elements": {
                "REWARDED DAG ADDRESSES": first_reward_addr,
                "REWARDED": "{:,.3f}".format(self.first[1]/1e8)
                },
                "spacing": 40,
            },
        ]
    
    
    # ==== PARSERS / PROCESSORS ====

    def parse_rewards(self):
        end_ordinal = "init"
        for snapshot in self.data["data"]:
            self.current_ordinal = str(snapshot["ordinal"])
            
            if end_ordinal != "init" and int(self.current_ordinal) < end_ordinal:
                continue

            self.get_rewards()
            if not self.reward_data:
                continue
            end_ordinal = self.data["end_ordinal"]

            try:
                for rewards in self.reward_data:
                    if self.search_dag_addr in rewards["destination"]:
                        self.reward_amount[rewards["destination"]] = self.reward_amount.get(rewards["destination"], 0) + rewards["amount"]
                        self.color = "green"
                        self.found = "TRUE"
                    else:
                        self.reward_amount[rewards["destination"]] = rewards["amount"]
            except Exception as e:
                print(e)
                self._send_error("cmd-1677","api_error")

        if self.target_dag_addr:
            for target in self.reward_amount.keys():
                if target == self.target_dag_addr:
                    self.first = [target, self.reward_amount[target]]
                    break
        else:
            try:
                self.first = self.reward_amount.popitem()  
            except:
                self.first = [0,0]


    def process_csv(self):
        if not self.create_csv: return

        self._print_log_msg("info",f"process_csv --> creating csv file [{self.csv_file_name}].")
                
        csv_headers = [
            
            ["General"],
            
            [
                "start ordinal","end ordinal","snapshot count",
                "start snapshot","end snapshot","dag address count"
            ],
            
            [
                self.data["start_ordinal"], self.data["end_ordinal"],
                self.snapshot_size,self.data["data"][-1]["timestamp"],
                self.data["data"][0]["timestamp"],len(self.reward_amount)
            ],
                
            ["rewards"],
            
            ["DAG address","amount rewards"],

            [self.first[0],"{:,.3f}".format(self.first[1]/1e8)],

        ]
            
        self.functions.create_n_write_csv({
            "file": self.csv_path,
            "rows": csv_headers
        })


    # ==== GETTERS ====

    def get_data(self):
        self.data = self.parent.get_and_verify_snapshots({
            "snapshot_size": self.snapshot_size,
            "environment": self.config_obj[self.profile]["environment"], 
            "profile": self.profile,
        })


    def get_rewards(self):
        self.reward_data = self.functions.get_snapshot({
            "action": "rewards",
            "history": self.snapshot_size,
            "environment": self.config_obj[self.profile]["environment"],
            "profile": self.profile,
            "ordinal": self.current_ordinal if self.current_ordinal else False,
            "return_on_error": True if self.current_ordinal else False,
            "return_type": "raw",
        })   


    # ==== INTERNALS ====

    def _send_error(self, code, line="input_error", extra=None, extra2=None):
        self.error_messages.error_code_messages({
            "error_code": code,
            "line_code": line,
            "extra": extra,
            "extra2": extra2,
        })  


    # ==== HANDLERS ====

    def handle_snapshot_size(self):
        try:
            if int(self.snapshot_size) > self.api_max_history or int(self.snapshot_size) < 1:
                self.functions.print_paragraphs([
                    [" INPUT ERROR ",0,"white,on_red"], ["the",0,"red"],
                    ["-s",0], ["option in the command",0,"red"], ["show_current_rewards",0], 
                    ["must be in the range between [",0,"red"], ["10",-1,"yellow","bold"], ["] and [",-1,"red"],
                    ["375",-1,"yellow","bold"], ["], please try again.",-1,"red"],["",2],

                    ["show_current_rewards",0,"red"], ["-s",0,"yellow"], ["option must be in the range between",0,"red"],
                    ["10",0,"yellow"], ["and",0,"red"], ["375",2,"yellow"], 
                ])
                return
        except Exception as e:
            self._print_log_msg("error",f"handle_snapshot_size --> error [{e}]")
            self._send_error("cmd-825")


    def handle_target_addr(self):
        if ("--target" in self.command_list or "-t" in self.command_list) and not self.argv_list:
            try:
                target_dag_addr = self.command_list[self.command_list.index("-t")+1]
            except:
                try:
                    self.target_dag_addr = self.command_list[self.command_list.index("--target")+1]
                except:
                    self._send_error("cmd-1741","input_error","target","must be a valid DAG wallet address")
            
            self.functions.is_valid_address("DAG",False,target_dag_addr)


    def handle_csv_instructions(self):
        if not self.create_csv: return

        self._print_log_msg("info",f"handle_csv_instructions -> csv file created: location: [{self.csv_path}]")
        self.functions.print_cmd_status({
            "text_start": "Create csv for",
            "brackets": "show current rewards",
            "newline": True,
            "status": "complete"
        })
        self.functions.print_paragraphs([
            ["CSV created successfully",1,"green","bold"],
            ["filename:",0,], [self.csv_file_name,1,"yellow","bold"],
            ["location:",0,], [self.config_obj[self.profile]['directory_uploads'],1,"yellow","bold"]
        ])  


    # ==== PRINTERS ====

    def _print_log_msg(self,log_type,msg):
        log_method = getattr(self.log, log_type, None)
        log_method(f"{self.__class__.__name__} --> {msg}")


    def print_initial_output(self):
        if self.create_csv: return

        for header_elements in self.print_out_list:
            self.functions.print_show_output({
                "header_elements" : header_elements,
            }) 


    def print_list_results(self):
        do_more = False if "-np" in self.command_list else True
        if do_more:
            console_size = get_terminal_size()
            more_break = round(console_size.lines)-20   
            
        for n, (address, amount) in enumerate(self.reward_amount.items()):
            if do_more and n % more_break == 0 and n > 0:
                more = self.functions.print_any_key({
                    "quit_option": "q",
                    "newline": "both",
                })
                if more:
                    break
                
            amount = "{:,.3f}".format(amount/1e8)
            if self.create_csv:
                self.functions.create_n_write_csv({
                    "file": self.csv_path,
                    "row": [address,amount]
                })
            else:
                if address == self.search_dag_addr:
                    print(f"  {colored(address,self.color)}  {colored(amount,self.color)}{colored('**','yellow',attrs=['bold'])}")
                else:
                    print(f"  {address}  {amount}") 

        print("\n")  


if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")  

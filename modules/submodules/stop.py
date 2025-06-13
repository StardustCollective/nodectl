from time import sleep
from concurrent.futures import ThreadPoolExecutor


class StopNode():
    
    def __init__(self,command_obj):
        self.command_obj = command_obj
        
        self.parent_getter = command_obj.get("getter")
        self.parent_setter = command_obj.get("setter")


    # ==== SETTERS ====
    
    def set_parameters(self):
        self.log = self.parent_getter("log")
        self.functions = self.parent_getter("functions")
        self.node_service = self.parent_getter("node_service")

        self.profile = self.parent_getter("profile")
        
        self.service_name_clean = self.node_service.config_obj[self.profile]["service"]
        self.service_name = f"cnng-{self.service_name_clean}"

        self.cn_requests = self.node_service.get_self_value("cn_requests")
        self.config_obj = self.cn_requests.get_self_value("config_obj")
        self.parent_cli_leave = self.parent_getter("cli_leave")
        self.parent_show_system_status = self.parent_getter("show_system_status")

        self.show_timer = self.command_obj.get("show_timer",True)
        self.spinner = self.command_obj.get("spinner",False)
        self.argv_list = self.command_obj.get("argv_list",[])
        self.caller = self.command_obj.get("caller","stop")
        
        self.static_nodeid = self.command_obj.get("static_nodeid",False)
        self.check_for_leave = self.command_obj.get("check_for_leave",False)
                
        self.leave_first = False
        self.rebuild = False
        self.result = False
        self.state = None


    def set_progress_obj(self):
        self.progress = {
            "status": "running",
            "status_color": "yellow",
            "text_start": "stop request initiated",
            "brackets": self.service_name_clean,
            "newline": True,
        }
        
        
    def set_show_timer(self,enable):
        self.show_timer = False
        if enable:
            self.show_timer = True
            
    
    def set_rebuild(self):
        self.rebuild = True
        if self.functions.config_obj["global_elements"]["node_service_status"][self.profile] == "inactive":
            self.rebuild = False
            
    
    def _set_service_state(self):
        self.functions.set_self_value("config_obj",self.config_obj)
        self.functions.get_service_status()
        self.config_obj = self.functions.get_self_value("config_obj")
        
        pass
    
    
    def set_self_value(self, name, value):
        setattr(self, name, value)
        
        
    # ==== GETTERS ====
    
    def _get_profile_state(self):
        self.state = self.cn_requests.get_current_local_state(self.profile, True)

             
    # ==== PARSERS / PROCESSORS ====

    def process_delay(self):
        sleep(self.command_obj.get("delay",0))
        
        
    def process_stop_request(self):
        with ThreadPoolExecutor() as executor:
            if self.spinner:
                self.functions.event = True
                self.show_timer = False
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
                self.result = self.node_service.change_service_state({
                    "profile": self.profile,
                    "action": "stop",
                    "service_name": self.service_name,
                    "caller": "cli_stop",
                    "cn_requests": self.cn_requests,
                })
                self.functions.event = False
            except Exception as e:
                self._print_log_msg("error",f"found issue with stop request profile [{self.profile}] [{e}]")


    # ==== INTERNALS ====


    # ==== HANDLERS ====

    def handle_help(self):
        self.functions.check_for_help(self.argv_list,"stop")
        
        
    def handle_check_for_leave(self):
        if not self.check_for_leave: return
        
        self._get_profile_state()
        self._print_current_state()
        
        self._print_log_msg("info",f"found state | profile [{self.profile}] | state [{self.state}]")
        states = self.functions.get_node_states("on_network",True)

        if self.state in states:
            self.functions.print_paragraphs([
                ["",1],[" WARNING ",0,"white,on_red"], ["This profile",0],
                [self.profile,0,"yellow","bold"], ["is in state:",0], 
                [self.state,2,"yellow","bold"],
            ]) 
            if "-l" in self.argv_list or "--leave" in self.argv_list:
                leave_first = True
            else:
                leave_first = self.functions.confirm_action({
                    "yes_no_default": "y",
                    "return_on": "y",
                    "prompt": "Do you want to leave first?",
                    "exit_if": False,
                })
            if leave_first:
                self.parent_cli_leave({
                    "secs": 30,
                    "reboot_flag": False,
                    "skip_msg": False,
                    "argv_list": ["-p",self.profile],
                })
                
        
    # ==== PRINTERS ====

    def print_starting(self):
        self._print_log_msg("info",f"stop process commencing | profile [{self.profile}]")
        self.functions.print_cmd_status({
            "status": "stop",
            "status_color": "magenta",
            "text_start": "Issuing system service",
            "brackets": self.profile,
            "newline": False,
        })
        
    
    def print_init_process(self):
        self._print_log_msg("info",f"Stop service request initiated. [{self.service_name}]")
        
        print("")
        self.functions.print_cmd_status(self.progress)
                

    def print_progress_complete(self):
        self._print_log_msg("debug",f"stop process completed | profile [{self.profile}]")
        self.functions.print_cmd_status({
            **self.progress,
            "status": "complete",
            "status_color": "green",
            "newline": True
        }) 
                

    def _print_current_state(self):
        self.functions.print_cmd_status({
            "text_start": "Node found in state",
            "status": self.state,
            "status_color": "cyan",
            "newline": True
        }) 
        
    
    def print_final_status(self):
        self.functions.cancel_event = False
        self._get_profile_state()
        self._set_service_state()
        
        self.parent_show_system_status({
            "rebuild": self.rebuild,
            "called_command": "stop",
            "wait": self.show_timer,
            "spinner": self.spinner,
            "cn_requests": self.cn_requests,
            "argv": ["-p",self.profile],
        })
        
        
    def print_caller(self):
        caller = "direct stop requested" if self.caller == "stop" else f"{self.caller} requested stop"
        self._print_log_msg("debug",caller)
        
        
    def _print_log_msg(self,log_type,msg):
        log_method = getattr(self.log, log_type, None)
        log_method(f"{self.__class__.__name__} request --> {msg}")
        
if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")  

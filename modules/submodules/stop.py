from time import sleep
from concurrent.futures import ThreadPoolExecutor


class StopNode():
    
    def __init__(self,parent,command_obj):
        self.parent = parent
        self.command_obj = command_obj
        
        self.show_timer = command_obj.get("show_timer",True)
        self.spinner = command_obj.get("spinner",False)
        self.argv_list = command_obj.get("argv_list",[])
        self.profile = command_obj.get("profile",self.parent.profile)
        self.static_nodeid = command_obj.get("static_nodeid",False)
        self.check_for_leave = command_obj.get("check_for_leave",False)
        
        self.log = self.parent.log.logger[self.parent.log_key]
        self.functions = self.parent.functions


    # ==== SETTERS ====
    
    def set_parameters(self):
        self.leave_first = False
        self.rebuild = False
        self.result = False
        
        self.state = None
        
        self.parent.set_profile(self.profile)


    def set_progress_obj(self):
        self.progress = {
            "status": "running",
            "status_color": "yellow",
            "text_start": "stop request initiated",
            "brackets": self.functions.cleaner(self.parent.service_name,'service_prefix'),
            "newline": True,
        }
        
        
    def set_show_timer(self,enable):
        self.show_timer = False
        if enable:
            self.show_timer = True
            
    
    def set_rebuild(self):
        if self.functions.config_obj["global_elements"]["node_service_status"][self.profile] == "inactive (dead)":
            self.rebuild = False
            
            
    # ==== GETTERS ====
    
    def _get_profile_state(self):
        self.state = self.functions.test_peer_state({
            "profile": self.profile,
            "skip_thread": True,
            "spinner": self.spinner,
            "simple": True,
            "current_source_node": "127.0.0.1",
            "caller": "cli_stop",
        }) 
             
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
                self.result = self.parent.node_service.change_service_state({
                    "profile": self.profile,
                    "action": "stop",
                    "service_name": self.parent.service_name,
                    "caller": "cli_stop"
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
                self.parent.cli_leave({
                    "secs": 30,
                    "reboot_flag": False,
                    "skip_msg": False,
                    "argv_list": ["-p",self.profile],
                })
                
        
    # ==== PRINTERS ====
    
    def _print_log_msg(self,log_type,msg):
        log_method = getattr(self.log, log_type, None)
        log_method(f"stop request --> {msg}")


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
        self._print_log_msg("info",f"Stop service request initiated. [{self.parent.service_name}]")
        
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
        
        
    def print_final_status(self):
        self.functions.cancel_event = False
        self.parent.show_system_status({
            "rebuild": self.rebuild,
            "called": "stop",
            "wait": self.show_timer,
            "spinner": self.spinner,
            "static_nodeid": self.static_nodeid if self.static_nodeid else False,
            "-p": self.profile
        })
        

if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")  

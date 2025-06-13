from sys import exit
from concurrent.futures import ThreadPoolExecutor

class StartNode():
    
    def __init__(self,command_obj):
        self.command_obj = command_obj
        
        self.parent_getter = command_obj["getter"]
        self.parent_setter = command_obj["setter"]


    # ==== SETTERS ====
    
    def set_parameters(self):
        self.cn_requests = self.command_obj["cn_requests"]
        self.argv_list = self.command_obj.get("argv_list",[])

        self.profile = self.command_obj.get("profile",self.parent_getter("profile"))    
        self.skip_seedlist_title = self.command_obj.get("skip_title", True)
        self.caller = self.command_obj.get("caller","start")
        
        self.service_name = self.command_obj.get("service_name",self.parent_getter("service_name"))
        self.node_service = self.parent_getter("node_service")
        
        self.log = self.parent_getter("log")
        self.functions = self.parent_getter("functions")
        self.check_seed_list = self.parent_getter("check_seed_list")
        self.show_system_status = self.parent_getter("show_system_status")

        self.spinner = self.command_obj.get("spinner", False)
        
    
    def set_progress_obj(self):
        self.progress = {
            "text_start": "Start request initiated",
            "brackets": self.functions.cleaner(self.service_name,'service_prefix'),
            "status": "running",
            "newline": True,
        }
        
    
    def set_service_state(self):
        self.node_service.change_service_state({
            "profile": self.profile,
            "action": "start",
            "service_name": self.service_name,
            "caller": "cli_start",
            "cn_requests": self.cn_requests,
        })
        

    def _set_status_obj(self):
        self.show_status_obj = {
            "called_command": "start",
            "argv": ["-p",self.profile],                
            "cn_requests": self.cn_requests,
            "print_auto_restart_status": False,
        }
        
              
    # ==== GETTERS ====
    
    def get_self_value(self, name, default=False):
        return getattr(self, name, default)
    
    # ==== PARSERS / PROCESSORS ====

    def process_start_results(self):
        self.cn_requests.config_obj = self.functions.get_service_status(self.cn_requests.config_obj,True) # update service states
        
        with ThreadPoolExecutor() as executor:
            if self.spinner:
                self.functions.event = True
                _ = executor.submit(self.functions.print_spinner,{
                    "msg": f"Fetching status [{self.profile}], please wait ",
                    "color": "cyan",
                })      
            else:  
                self.functions.print_cmd_status({
                    "text_start": "Fetching status",
                    "brackets": self.profile,
                    "newline": True,
                })
        
            self.functions.event = False
            self._set_status_obj()
            
            try:
                if self.command_obj["command"] == "start":
                    self.show_status_obj["called"] = "start"
            except: pass
        
            self.functions.cancel_event = False

    # ==== INTERNALS ====


    # ==== HANDLERS ====

    def handle_check_for_help(self):
        self.functions.check_for_help(self.argv_list,"start")    


    def handle_seedlist(self):
        if self.cn_requests.config_obj[self.profile]["seed_path"] != "disable/disable":
            node_id = self.cn_requests.get_node_id(self.profile)
            check_seed_list_options = ["-p",self.profile,"skip_warnings","-id",node_id]
            
            if self.skip_seedlist_title:
                check_seed_list_options.extend(["skip_seedlist_title","return_only"])
                
            found = self.check_seed_list({
                "command_list": check_seed_list_options,
                "cn_requests": self.cn_requests,
            })
            
            self._print_seedlist_progress(found)
            
            if not found:
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
                    
                    
    # ==== PRINTERS ====
    
    def _print_seedlist_progress(self,found):
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
            

    def print_start_init(self):
        self._print_log_msg("info",f"service request initiated.")
        self.functions.print_cmd_status(self.progress)


    def print_start_complete(self):
        self._print_log_msg("info",f"service request completed.")
        self.functions.print_cmd_status({
            **self.progress,
            "status": "complete",
        })
        
        
    def print_timer(self):
        self.functions.print_timer({
            "p_type": "cmd",
            "seconds": 6,
            "step": -1,
            "phrase": "Waiting",
            "end_phrase": "before starting",
        })
        
        
    def print_final_status(self, rebuild=False):
        self.show_status_obj["rebuild"] = rebuild
        self.show_status_obj["print_auto_restart_status"] = False

        self.node_service.cn_requests.get_current_local_state(self.profile)
        self.show_status_obj["config_obj"] = self.node_service.cn_requests.config_obj
        self.show_system_status(self.show_status_obj)
        
        
    def print_caller(self):
        caller = "direct start requested" if self.caller == "start" else f"{self.caller} requested start"
        self._print_log_msg("debug",caller)
        
        
    def _print_log_msg(self,log_type,msg):
            log_method = getattr(self.log, log_type, None)
            log_method(f"{self.__class__.__name__} --> {msg}")
            
            
if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")  

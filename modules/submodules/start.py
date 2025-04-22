from sys import exit
from concurrent.futures import ThreadPoolExecutor

class StartNode():
    
    def __init__(self,parent,command_obj):
        self.parent = parent
        self.command_obj = command_obj
        
        self.profile = command_obj.get("profile",self.parent.profile)        
        self.argv_list = command_obj.get("argv_list",[])
        self.spinner = command_obj.get("spinner",False)
        self.service_name = command_obj.get("service_name",self.parent.service_name)
        self.threaded = command_obj.get("threaded", False)
        self.static_nodeid = command_obj.get("static_nodeid",False)
        self.skip_seedlist_title = command_obj.get("skip_seedlist_title",False)
        self.existing_node_id = command_obj.get("node_id",False)
    

    # ==== SETTERS ====
    def set_parameters(self):
        self.node_service = self.parent.node_service
        
        self.log = self.parent.log.logger[self.parent.log_key]
        self.functions = self.parent.functions
        self.config_obj = self.parent.config_obj
    
    
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
            "caller": "cli_start"
        })
        

    def _set_status_obj(self):
        self.show_status_obj = {
            "called": "status",
            "spinner": False,
            "rebuild": True,
            "wait": False,
            "threaded": self.threaded,
            "static_nodeid": self.static_nodeid if self.static_nodeid else False,
            "-p": self.profile                
        }  
        
              
    # ==== GETTERS ====
    
    
    # ==== PARSERS / PROCESSORS ====

    def process_start_results(self):
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
        if self.config_obj[self.profile]["seed_path"] != "disable/disable":
            check_seed_list_options = ["-p",self.profile,"skip_warnings","-id",self.existing_node_id]
            if self.skip_seedlist_title: check_seed_list_options.append("skip_seedlist_title")
            found = self.parent.check_seed_list(check_seed_list_options)
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
            
            
    def _print_log_msg(self,log_type,msg):
        log_method = getattr(self.log, log_type, None)
        log_method(f"start request --> {msg}")


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
        
        
    def print_final_status(self):
        self.parent.show_system_status(self.show_status_obj)


if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")  

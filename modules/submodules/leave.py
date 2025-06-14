from time import sleep
from modules.troubleshoot.send_logs import Send

class LeaveNode():
    
    def __init__(self,command_obj):
        self.command_obj = command_obj
        self.parent_getter = command_obj["getter"]
        self.parent_setter = command_obj["setter"]


    # ==== SETTERS ====

    def set_parameters(self):
        self.cn_requests = self.command_obj["cn_requests"]
        
        self.profile = self.command_obj.get("profile", self.parent_getter("profile"))
        self.print_timer = self.command_obj.get("print_timer", True)
        self.secs = self.command_obj.get("secs", 30)
        self.reboot_flag = self.command_obj.get("reboot_flag", False)
        self.argv_list = self.command_obj.get("argv_list",[])
        self.thread = self.command_obj.get("thread", False)
        self.caller = self.command_obj.get("caller", "leave")
        
        self.log = self.parent_getter("log") 
        self.functions = self.parent_getter("functions")
        self.node_service = self.parent_getter("node_service")
                
        self.leave_obj = False 
        self.backup_line = False
        self.skip_log_lookup = False
        self.timestamp = False
        self.skip_msg = False
        self.max_retries = 3
        self.start = 1
        
        self.state_obj = None
        self.state = None
        self.leave_str = None
                
        self.slow = "Slow Reset " if self.parent_getter("slow_flag") else ""
        
        if self.reboot_flag:
             self.secs = 15 # reboot don't need to wait
             
        self.send = Send({
            "command_list": [],
            "config_obj": self.cn_requests.config_obj,
            "ip_address": self.functions.get_ext_ip()
        })
        self.send.set_self_value("log",self.log)
        self.send.set_self_value("functions",self.functions)
        self.send.set_self_value("profile",self.profile)
        self.send.set_parameters()
            
        
    def set_skip_lookup(self,enable=True):
        self.skip_log_lookup = False
        if enable:
            self.skip_log_lookup = True
            
                
    def set_progress_obj(self):
        self.progress = {
            "status": "testing",
            "text_start": "Retrieving Node Service State",
            "brackets": self.profile,
            "newline": False,
        }
        
        
    def set_state_obj(self):
        self.state_obj = {
            "profile": self.profile,
            "caller": "leave",
            "skip_thread": True,
            "simple": True,
            "treaded": self.thread,
        }
        

    def set_node_service_profile(self):
        self.node_service.set_profile(self.profile)
        
        
    def set_start_increment(self):
        self.functions.print_clear_line()
        self.start += 1 
             
    
    def set_self_value(self, name, value):
        setattr(self, name, value)


    def _set_timestamp(self):
        try: 
            self.timestamp = self.leave_obj["@timestamp"]
        except:
            self._print_log_msg("warning",f"leave process unable to verify| profile [{self.profile}] leave progress | ip [127.0.0.1] - switching to new method")
            self.leave_str = "to allow node to gracefully leave"
            # self.skip_log_lookup = True
            sleep(.5)      
              
              
    # ==== GETTERS ====
    
    def get_profile_state(self):
        # self.cn_requests.set_session()
        self.cn_requests.set_self_value("get_state",True)
        self.cn_requests.set_self_value("profile",self.profile)
        self.cn_requests.set_self_value("profile_names",self.parent_getter("profile_names"))
        self.cn_requests.get_current_local_state(self.profile)
        self.state = self.cn_requests.get_current_cached_state(self.profile)

    
    # ==== PARSERS / PROCESSORS ====

    def process_leave_cluster(self):
        if self.state in self.functions.not_on_network_list:
            self.functions.print_cmd_status({
                "text_start": "Profile",
                "brackets": self.profile,
                "text_end": "already",
                "status": self.state,
                "status_color": "red",
                "newline": True,
            })
            self.skip_msg = True
            return
        
        self.cn_requests.handle_leave_cluster(self.profile)


    def process_leave_status(self):
        self.cn_requests.set_self_value("use_profile_cache",True)
        state = self.cn_requests.get_profile_state(self.profile)

        if state not in self.functions.not_on_network_list: 
            return False
        
        self._print_log_msg("debug",f"found out of cluster | profile [{self.profile}] state [{state}] | ip [127.0.0.1]")
        return True
    
    
    def parse_leave_status(self):
        if self.start > self.max_retries-1:
            self._print_log_msg("warning",f"node did not seem to leave the cluster properly, executing leave command again. | profile [{self.profile}]")
            self.process_leave_cluster()
            
    
    def parse_skip_log_lookup(self):
        if not self. skip_log_lookup: return
        self.print_leave_timer()


    def parse_log_wait_for_leave(self):
        if not self.print_timer:
            sleep(5)
            return
        
        for attempt in range(0,4):
            state = self.cn_requests.get_current_local_state(self.profile, True)
            if state == "Offline" or state == "ApiNotReady":
                break
            sleep(5)
            
        self._set_timestamp()   
             
    # ==== INTERNALS ====


    # ==== HANDLERS ====
    def handle_pause(self):
        sleep(self.command_obj.get("delay",0))


    def handle_not_outofcluster(self):
        if self.start < 2: return
        
        if self.backup_line: 
            print(f'\x1b[1A', end='')

        self.print_outofcluster_msg(False)
        
         
    def handle_max_retries(self):
        if self.start < 5: return False
        
        self._print_log_msg("warning",f"requests reached [{self.start}] secs without properly leaving the cluster, aborting attempts | profile [{self.profile}]")
        if self.print_timer:
            self._print_leave_unsuccessful()
        
        return True


    def handle_wait_for_offline(self):
        # if not self.skip_log_lookup: 
        #     return False
        
        self.leave_obj = False
        sleep(1)
        try:
            self._print_log_msg("debug",f"checking for Offline status | profile [{self.profile}] | ip [127.0.0.1]")
            self.leave_obj = self.send.scrap_log({
                "profile": self.profile,
                "msg": "Wait for node to go offline",
                "value": "Node state changed to=Offline",
                "key": "message",
                "timeout": 20,
                "timestamp": self.timestamp if self.timestamp else False,
                "parent": self.parent,
            })
        except Exception as e:
            self._print_log_msg("error",f"leave object exception raised [{e}]")
            self.skip_log_lookup = True
    
    
    def handle_check_for_help(self):
        self.functions.check_for_help(self.argv_list,"start") 
               
    # ==== PRINTERS ====
    
    def _print_log_msg(self,log_type,msg):
        log_method = getattr(self.log, log_type, None)
        log_method(f"{self.__class__.__name__} request --> {msg}")


    def print_leave_timer(self):
        self._print_log_msg("debug",f"pausing to allow leave process to complete | profile [{self.profile}] | ip [127.0.0.1]")
        self.functions.print_timer({
            "seconds": 12,
            "phrase": self.leave_str,
            "start": self.start,
        })    
        
        
    def print_outofcluster_msg(self,complete=True):
        action = "complete" if complete else "not out of cluster"
        self._print_log_msg("debug",f"leave process {action} | profile [{self.profile}] state [{self.state}] | ip [127.0.0.1]")
        
        self.functions.print_cmd_status({
            "status": "OutOfCluster" if complete else self.state,
            "status_color": "green" if complete else "yellow",
            "text_color": "cyan" if complete else "red",
            "text_start": f"Service for",
            "brackets": self.profile,
            "newline": True
        })
        

    def _print_leave_unsuccessful(self):
        self.functions.print_cmd_status({
            "text_start": "Unable to gracefully leave",
            "brackets": self.profile,
            "status": "skipping",
            "newline": True,
            "status_color": "red"
        })
            
                    
    def print_leave_init(self, first=False):
        self.functions.print_cmd_status({
            "status": self.profile,
            "text_start": f"{self.slow}Leaving the cluster for profile",
            "newline": True
        })

        text_start = "Please wait patiently"
        if not first:
            text_start = "Please continue to wait patiently"
        self.functions.print_cmd_status({
            "status": "",
            "text_color": "red",
            "text_start": text_start,
            "newline": True
        })

        
    def print_caller(self):
        caller = "direct leave requested" if self.caller == "leave" else f"{self.caller} requested leave"
        self._print_log_msg("debug",caller)
                
        
    def print_leaving_msg(self):
        self.functions.print_cmd_status({
            "text_start": "Node going",
            "brackets": "Offline",
            "text_end": "please be patient",
            "status": self.profile,
            "newline": True,
        })
        
        
    def print_leave_progress(self,state=False):
        if not state:
            self.progress["state"] = self.state
            self.progress["status"] = self.state
        
        self.functions.print_cmd_status(self.progress)


if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")  

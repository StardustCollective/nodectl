from time import sleep

class LeaveNode():
    
    def __init__(self,parent,command_obj):
        self.parent = parent
        self.command_obj = command_obj
        self.profile = command_obj.get("profile", self.parent.profile)
        self.print_timer = command_obj.get("print_timer", True)
        self.secs = command_obj.get("secs", 30)
        self.reboot_flag = command_obj.get("reboot_flag", False)
        self.skip_msg = command_obj.get("skip_msg", False)
        self.threaded = command_obj.get("threaded", False)
                
        self.log = self.parent.log.logger[self.parent.log_key]
        self.functions = self.parent.functions


    # ==== SETTERS ====

    def _set_timestamp(self):
        try: 
            self.timestamp = self.leave_obj["@timestamp"]
        except:
            self._print_log_msg("warning",f"leave process unable to verify| profile [{self.profile}] leave progress | ip [127.0.0.1] - switching to new method")
            self.leave_str = "to allow node to gracefully leave"
            self.skip_log_lookup = True
            sleep(.5)
            

    def set_parameters(self):
        self.leave_obj = False 
        self.backup_line = False
        self.skip_log_lookup = False
        self.timestamp = False
        
        self.max_retries = 5
        self.start = 1
        
        self.state_obj = None
        self.state = None
        self.leave_str = None
                
        self.node_service = self.parent.node_service
        self.api_port = self.functions.config_obj[self.profile]["public_port"]
        
        self.slow = "Slow Reset " if self.parent.slow_flag else ""
        
        if self.reboot_flag:
             self.secs = 15 # reboot don't need to wait
            
        
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
            "treaded": self.threaded,
        }
        

    def set_node_service_profile(self):
        self.node_service.set_profile(self.profile)
        
        
    def set_start_increment(self):
        self.functions.print_clear_line()
        self.start += 1 
             
    # ==== GETTERS ====
    
    def get_profile_state(self):
        self.state = self.functions.test_peer_state(self.state_obj)
    
    # ==== PARSERS / PROCESSORS ====

    def process_leave_cluster(self):
        self.state = self.node_service.leave_cluster({
            "skip_thread": True,
            "threaded": self.threaded,
            "profile": self.profile,
            "secs": self.secs,
            "cli_flag": True,
            "current_source_node": "127.0.0.1",   
        })


    def process_leave_status(self):
        if not self.state in self.functions.not_on_network_list: 
            return False
        
        self._print_log_msg("debug",f"found out of cluster | profile [{self.profile}] state [{self.state}] | ip [127.0.0.1]")
        return True
    
    
    def parse_leave_status(self):
        self._print_log_msg("info",f"leave in progress | profile [{self.profile}] port [{self.api_port}] | ip [127.0.0.1]")
        if self.start > self.max_retries+1:
            self._print_log_msg("warning",f"node did not seem to leave the cluster properly, executing leave command again. | profile [{self.profile}]")
            self.process_leave_cluster()
            
    
    def parse_skip_log_lookup(self):
        if not self. skip_log_lookup: return
        self.print_leave_timer()


    def parse_log_wait_for_leave(self):
        if not self.print_timer:
            sleep(5)
            return
        
        self.parent.prepare_and_send_logs(["-p",self.profile,"scrap"])
        try:
            self._print_log_msg("debug",f"leave process waiting for | profile [{self.profile}] state to be [leaving] | ip [127.0.0.1]")
            self.leave_obj = self.parent.send.scrap_log({
                "profile": self.profile,
                "msg": "Wait for node to transition to leaving",
                "value": "Node state changed to=Leaving",
                "key": "message",
                "thread": False,
                "timeout": 40,
                "parent": self.parent,
            })
        except Exception as e:
            self._print_log_msg("error",f"leave object exception raised [{e}]")
            
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
        if not self.skip_log_lookup: return False
        
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
                
        self.get_profile_state()
        if self.state not in self.functions.not_on_network_list and self.start > 2: 

            self._print_log_msg("warining",f"leave process not out of cluster | profile [{self.profile}] state [{self.state}] | ip [127.0.0.1]")
            sleep(.3) 
            self.skip_log_lookup = True      
            self.backup_line = True  
            return False
        
        return True  
    
    # ==== PRINTERS ====
    
    def _print_log_msg(self,log_type,msg):
        log_method = getattr(self.log, log_type, None)
        log_method(f"{self.__class__.__name__} request --> {msg}")


    def print_leave_timer(self):
        self._print_log_msg("debug",f"pausing to allow leave process to complete | profile [{self.profile}] | ip [127.0.0.1]")
        self.functions.print_timer({
            "seconds": self.secs,
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
            
                    
    def print_leave_init(self):
        self.functions.print_cmd_status({
            "status": self.profile,
            "text_start": f"{self.slow}Leaving the cluster for profile",
            "newline": True
        })
        
        
    def print_leaving_msg(self):
        self.functions.print_cmd_status({
            "text_start": "Node going",
            "brackets": "Offline",
            "text_end": "please be patient",
            "status": self.profile,
            "newline": True,
        })
        
        
    def print_leave_progress(self,state=False):
        if state:
            self.progress["state"] = self.state
            self.progress["status"] = self.state
        
        self.functions.print_cmd_status(self.progress)

if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")  

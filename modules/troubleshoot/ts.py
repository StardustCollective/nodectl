
import json
from copy import deepcopy

class Troubleshooter():
    
    def __init__(self,command_obj):
        self.command_obj = command_obj    
        self.parent_getter = command_obj["getter"]
        self.parent_setter = command_obj["setter"]
        self.cn_requests = deepcopy(command_obj["cn_requests"])
        
        self.log = command_obj.get("log")
        
        
    def setup_logs(self,command_obj):
        profile_names = list(self.cn_requests.config_obj.keys())
        self.log_dict = {}
        single_profile = command_obj.get("profile",False)
        if single_profile:
            profile_names = [single_profile]
            
        for profile in profile_names:
            if "global" not in profile:
                self.log_dict[profile] = {}
                self.log_dict[profile]["app"] = f"/var/tessellation/{profile}/logs/json_logs/app.json.log"
                self.log_dict[profile]["http"] = f"/var/tessellation/{profile}/logs/json_logs/http.json.log"


    def test_for_connect_error(self,lines):
        self._print_log_msg("info","checking logs for simple error messages")
        no_of_errors, found = 4, 0
        end_results, ERROR_list = [], []

        for profile, log in self.log_dict.items():
            ERROR_list = [] # reset
            try:
                with open(log["app"],"r") as file:

                    test_messages = [
                        {
                            "find":"CollateralNotSatisfied",
                            "user_msg": "Collateral Not Satisfied",
                            "error_msg": "join_error",
                            "rank": 1,
                        },
                        {
                            "find":"SeedlistDoesNotMatch",
                            "user_msg": "Seed List Issue",
                            "error_msg": "join_error",
                            "rank": 1,
                        },
                        {
                            "find":"VersionMismatch",
                            "user_msg": "Incorrect Tessellation Version",
                            "error_msg": "upgrade_needed",
                            "rank": 1,
                        },
                        {
                            "find":"not in seedlist",
                            "user_msg": "This node is not authorized to join the cluster. Seed list issue.",
                            "error_msg": "join_error",
                            "rank": 1,
                        },
                        {
                            "find":"Address already in use",
                            "user_msg": "Connection Issue - Server reboot may be required.",
                            "error_msg": "Unhandled Exception during runtime",
                            "rank": 2,
                        },
                        {
                            "find":"Unauthorized for request",
                            "user_msg": "Not joined properly to the cluster and received: Access Permission - Unauthorized",
                            "error_msg": "join_error",
                            "rank": 1,
                        },
                        {
                            "find":"Joining to peer P2PContext",
                            "user_msg": "Peer to Peer port issue",
                            "error_msg": "join_error",
                            "rank": 3,
                        },
                        {
                            "find":"Join request rejected",
                            "user_msg": "Join was rejected",
                            "error_msg": "join_error",
                            "rank": 1,
                        },
                        {
                            "find":"Failed to join",
                            "user_msg": "Unable to join to selected Peer",
                            "error_msg": "join_error",
                            "rank": 2,
                        }
                    ]
                    for n, line in enumerate(reversed(list(file))):
                        if "ERROR" in line or "WARN" in line:
                            try:
                                ERROR_list.append(json.loads(line))
                            except json.JSONDecodeError as e:
                                self._print_log_msg("warning",f"troubleshooter -> Unable to parse JSON from log -> decoding error: [{e}]") 
                            if lines != "all" and n > lines-1: 
                                break
                                                   
                    # search for more significant errors first verses
                    # last found error.
                    no_of_errors, found = 4, 0 # reset
                    end_results = [] # reset
                    for message_test in test_messages:
                        for line in ERROR_list:            
                            # only going to search in reverse
                            # because a service start error will be at
                            # the end of the current app file
                            message_test["timestamp"] = line["@timestamp"]
                            if "stack_trace" in line.keys():
                                if message_test["find"] in line["stack_trace"]:
                                    found += 1
                                    end_results.append(message_test)
                            if message_test["find"].lower() in line["message"].lower():
                                found += 1 
                                end_results.append(message_test)
                            if found > no_of_errors-1:
                                break
                        if found > no_of_errors-1:
                            break

            except Exception as e:
                try:
                    self._print_log_msg("error",f"error attempting to open log file | file [{file}] | error [{e}]")
                except:
                    self._print_log_msg("error",f"error attempting to open log file... file not present on system?")

        if found > 0:
            return (profile,end_results)
        return False
    
    
    def _print_log_msg(self,log_type,msg):
        log_method = getattr(self.log, log_type, None)
        log_method(f"{self.__class__.__name__} request --> {msg}")
            

if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")
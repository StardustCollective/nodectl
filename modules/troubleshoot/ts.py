
import json
from copy import deepcopy
from .logger import Logging

class Troubleshooter():
    
    def __init__(self,command_obj):    
        self.config_obj = deepcopy(command_obj["config_obj"])
        self.log = Logging()
        
    def setup_logs(self,command_obj):
        profile_names = list(self.config_obj.keys())
        self.log_dict = {}
        single_profile = command_obj.get("profile",False)
        if single_profile:
            profile_names = [single_profile]
            
        for profile in profile_names:
            if "global" not in profile:
                self.log_dict[profile] = {}
                self.log_dict[profile]["app"] = f"/var/tessellation/{profile}/logs/json_logs/app.json.log"
                self.log_dict[profile]["http"] = f"/var/tessellation/{profile}/logs/json_logs/http.json.log"


    def test_for_connect_error(self):
        self.log.logger.info("checking logs for simple error messages")

        for profile, log in self.log_dict.items():
            ERROR_list = []; two_lines = False
            
            try:
                with open(log["app"]) as file:

                    test_messages = [
                        {
                            "find":"CollateralNotSatisfied",
                            "user_msg": "Collateral Not Satisfied",
                            "error_msg": "join_error",
                        },
                        {
                            "find":"SeedlistDoesNotMatch",
                            "user_msg": "Seed List Issue",
                            "error_msg": "join_error",
                        },
                        {
                            "find":"VersionMismatch",
                            "user_msg": "Incorrect Tessellation Version",
                            "error_msg": "upgrade_needed",
                        },
                        {
                            "find":"Address already in use",
                            "user_msg": "Connection Issue - Server reboot may be required.",
                            "error_msg": "Unhandled Exception during runtime",
                        },
                        {
                            "find":"Unauthorized for request",
                            "user_msg": "Access Permission - Unauthorized",
                            "error_msg": "join_error",
                        },
                        {
                            "find":"Joining to peer P2PContext",
                            "user_msg": "Peer to Peer port issue",
                            "error_msg": "join_error",
                        }
                    ]
                    for n, line in enumerate(reversed(list(file))):
                        if "ERROR" in line:
                            try:
                                ERROR_list.append(json.loads(line))
                            except json.JSONDecodeError as e:
                                self.log.logger.warn(f"troubleshooter -> Unable to parse JSON from log -> decoding error: [{e}]") 
                            if n > 49: break
                                                   
                    # search for more significant errors first verses
                    # last found error.
                    for message_test in test_messages:
                        for line in ERROR_list:            
                            # only going to search the last lines
                            # because a service start error will be at
                            # the end of the current app file
                            if "stack_trace" in line.keys():
                                if message_test["find"] in line["stack_trace"]:
                                    return (profile,message_test["user_msg"],message_test["error_msg"])
                            if message_test["find"] in line["message"]: 
                                return (profile,message_test["user_msg"],message_test["error_msg"])

            except Exception as e:
                try:
                    self.log.logger.error(f"error attempting to open log file | file [{file}] | error [{e}]")
                except:
                    self.log.logger.error(f"error attempting to open log file... file not present on system?")
        return False
    

if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")
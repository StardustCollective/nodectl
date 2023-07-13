
from copy import deepcopy
from .logger import Logging

class Troubleshooter():
    
    def __init__(self,command_obj):    
        self.config_obj = deepcopy(command_obj["config_obj"])
        self.log = Logging()
        
    def setup_logs(self,command_obj):
        profile_names = list(self.config_obj["profiles"].keys())
        self.log_dict = {}
        single_profile = command_obj.get("profile",False)
        if single_profile:
            profile_names = [single_profile]
            
        for profile in profile_names:
            self.log_dict[profile] = {}
            self.log_dict[profile]["app"] = f"/var/tessellation/{profile}/logs/app.log"
            self.log_dict[profile]["http"] = f"/var/tessellation/{profile}/logs/http.log"


    def test_for_connect_error(self):
        self.log.logger.info("checking logs for simple error messages")

        for profile, log in self.log_dict.items():
            ERROR_list = []; two_lines = False
            
            try:
                with open(log["app"]) as file:
                    # pull all errors and the next line in the file
                    for line in reversed(list(file)):
                        if two_lines:
                            if not line.startswith("20"):
                                ERROR_list.append(line)
                            two_lines = False
                        elif "ERROR" in line:
                            two_lines = True
                            ERROR_list.append(line)

                    for line in (ERROR_list):            
                        # only going to search the last lines
                        # because a service start error will be at
                        # the end of the current app file
                        if "CollateralNotSatisfied" in line:
                            return (profile,"Collateral Not Satisfied","join_error")
                        if "VersionMismatch" in line:
                            return (profile,"Version Issue","upgrade_needed")
                        if "Unauthorized for request" in line:
                            return (profile,"Access Permission - Unauthorized","join_error")
                        if "Joining to peer P2PContext" in line:
                            return (profile,"Peer to Peer port issue","join_error")
            except Exception as e:
                try:
                    self.log.logger.error(f"error attempting to open log file | file [{file}] | error [{e}]")
                except:
                    self.log.logger.error(f"error attempting to open log file... file not present on system?")
        return False
    

if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")
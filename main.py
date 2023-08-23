#!/bin/env python
from sys import argv, exit
from modules.shell_handler import ShellHandler
from termcolor import colored
from modules.troubleshoot.logger import Logging
from modules.config.config import Configuration
from modules.config.configurator import Configurator

import pdb

global debug
debug = False


def cli_commands(argv_list):
    current_shell = False
    try:
        _ = argv_list[1]
    except:
        argv_list = ["main_error","main_error"]
        
    while True:
        try:
            config_list = [
                "configure","install",
                "validate_config","validate-config","-val",
                "view_config","view-config","-vc"
            ]
            exclude_config = ["-v","_v","version"]
            
            if argv_list[1] in config_list:
                if argv_list[1] == "configure":
                    Configurator(argv_list)
                elif argv_list[1] == "install":
                    current_shell = ShellHandler({"global_elements":{"caller":"install"}},False)
                else:  
                    config_needed = Configuration({
                        "action": argv_list[1],
                        "implement": True,
                        "argv_list": argv_list
                    }) 
                    if config_needed.requested_configuration:
                        Configurator(["-e"])
            else:
                if "main_error" not in argv_list and argv_list[1] not in exclude_config:
                    config = Configuration({
                        "action": "normal",
                        "global_elements": {"caller":"normal"},
                        "implement": True,
                        "argv_list": argv_list
                    })
                    if config.action == "edit_on_error":
                        Configurator(config.edit_on_error_args)
                    else:
                        current_shell = ShellHandler(config.config_obj,False)               
                else:
                    caller = argv_list[1] if argv_list[1] in exclude_config else "config"
                    current_shell = ShellHandler({"caller": caller},False)
            if current_shell:        
                current_shell.start_cli(argv_list)
                
        except KeyboardInterrupt:
            log = Logging()
            log.logger.critical(f"user terminated nodectl prematurely with keyboard interrupt")
            print("")
            print(colored("  user terminating nodectl prematurely","red"))
            break
    
if __name__ == "__main__":
    cli_commands(argv)        
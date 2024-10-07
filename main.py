from sys import argv, exit
from modules.shell_handler import ShellHandler
from termcolor import colored
from modules.troubleshoot.logger import Logging
from modules.config.config import Configuration
from modules.config.configurator import Configurator
# import pdb

global debug
debug = False

def cli_commands(argv_list):
    current_shell, return_caller = False, False

    try:
        _ = argv_list[1]
    except:
        argv_list = ["main_error","main_error"]
        
    while True:
        if return_caller:
            poss_cmds = ["revision","configure"]
            found_mobile = True if "mobile" in argv_list else False
            for cmd in poss_cmds:
                if cmd in return_caller:
                    if "revision" in return_caller:
                        argv_list = ["main.py","revision","return_caller"]
                    elif "configure" in return_caller:
                        argv_list = return_caller+["return_caller"]
                    if "mobile" in return_caller: 
                        argv_list.append("mobile")
                        found_mobile = False
            if found_mobile or "mobile" in argv_list: 
                argv_list = return_caller+["mobile"]
                return_caller = ["main.py","mobile"]
        try:
            skip_config_list = ["install","verify_nodectl","-vn","restore_config"]
            exception_list = [
                "configure",
                "validate_config","validate-config","-val",
                "view_config","view-config","-vc",
            ]
            exception_list += skip_config_list
            exclude_config = ["-v","_v","version","verify_specs"]
            
            if argv_list[1] in exception_list:
                if argv_list[1] == "configure":
                    argv_list = Configurator(argv_list)
                    if argv_list.mobile: argv_list = ["main.py","mobile"]
                elif argv_list[1] in skip_config_list:
                    current_shell = ShellHandler({
                        "config_obj": {"global_elements":{"caller": argv_list[1]}},
                        },False)
                else:  
                    config_needed = Configuration({
                        "action": argv_list[1],
                        "implement": True,
                        "argv_list": argv_list
                    }) 
                    if config_needed.requested_configuration:
                        Configurator(["-e"])
                    elif return_caller:
                        argv_list = return_caller
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
                        current_shell = ShellHandler(config,False)               
                else:
                    caller = argv_list[1] if argv_list[1] in exclude_config else "config"
                    if "main_error" in argv_list: caller = "main_error" 
                    current_shell = ShellHandler({
                        "config_obj": {"global_elements":{"caller":caller}}
                    },False)
            if current_shell:        
                return_caller = current_shell.start_cli(argv_list)
                
        except KeyboardInterrupt:
            log = Logging()
            log.logger.critical(f"user terminated nodectl prematurely with keyboard interrupt")
            print("")
            print(colored("  user terminating nodectl prematurely","red"))
            break
    
if __name__ == "__main__":
    cli_commands(argv)        
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
    found_mobile, found_console = False, False
    handle_main = True

    try:
        _ = argv_list[1]
    except:
        argv_list = ["main_error","main_error"]

    log_key = logging_setup(argv_list)
            
    while True:
        if return_caller:
            poss_cmds = ["revision","configure"]
            found_mobile = True if "mobile" in argv_list else False
            found_console = True if "console" in argv_list else False
            for cmd in poss_cmds:
                if cmd in return_caller:
                    if "revision" in return_caller:
                        argv_list = ["main.py","revision","return_caller"]
                        handle_main = True
                    elif "configure" in return_caller:
                        argv_list = return_caller+["return_caller"]
                    if "mobile" in return_caller: 
                        argv_list.append("mobile")
                        found_mobile = False
            if found_mobile or "mobile" in argv_list: 
                argv_list = return_caller+["mobile"]
                return_caller = ["main.py","mobile"]
            elif "console" in argv_list or "verify_nodectl" in return_caller:
                argv_list = return_caller
        try:
            skip_config_list = ["install","verify_nodectl","-vn","restore_config"]
            exception_list = [
                "configure","export_private_key",
                "validate_config","validate-config","-val",
                "view_config","view-config","-vc",
            ]
            exception_list += skip_config_list
            exclude_config = ["-v","_v","version","verify_specs"]
            
            if argv_list[0] == "mobile_success":
                handle_main = True
            elif argv_list[1] in exception_list:
                handle_main = False
                if argv_list[1] == "export_private_key": 
                    handle_main = True
                elif argv_list[1] == "configure":
                    try:
                        argv_list = Configurator(argv_list)
                    except KeyboardInterrupt:
                        keyboardInterrupt()
                    if argv_list.mobile: 
                        argv_list = ["main.py","mobile"]
                elif argv_list[1] in skip_config_list:
                    try:
                        current_shell = ShellHandler({
                            "config_obj": {
                                "global_elements": {
                                    "caller": argv_list[1],
                                },
                            },
                        },False)
                    except KeyboardInterrupt:
                        keyboardInterrupt()
                else:  
                    try:
                        config_needed = Configuration({
                            "action": argv_list[1],
                            "implement": True,
                            "argv_list": argv_list,
                        }) 
                    except KeyboardInterrupt:
                        keyboardInterrupt()

                    if config_needed.requested_configuration:
                        try:
                            Configurator(["-e"])
                        except KeyboardInterrupt:
                            keyboardInterrupt()
                    elif config_needed.p12.pass_quit_request:
                        exit(0)
                    elif return_caller:
                        argv_list = return_caller

            if handle_main:
                if "main_error" not in argv_list and argv_list[1] not in exclude_config:
                    caller = "normal"
                    if "service_restart" in argv_list: 
                        caller = "service_restart"
                    if "export_private_key" in argv_list: 
                        caller = "export_private_key"

                    try:
                        config = Configuration({
                            "action": "normal",
                            "global_elements": {"caller":"normal"},
                            "implement": True,
                            "argv_list": argv_list,
                            "log_key": log_key,
                        })
                    except KeyboardInterrupt:
                        keyboardInterrupt()

                    try:
                        if config.p12.pass_quit_request:
                            if not return_caller:
                                raise
                            if caller == "export_private_key" and found_console:
                                return_caller = False
                                raise
                            argv_list = return_caller
                    except:
                        if not return_caller:
                            exit(0)

                    if config.action == "edit_on_error":
                        try:
                            Configurator(config.edit_on_error_args)
                        except KeyboardInterrupt:
                            keyboardInterrupt()
                    else:
                        try:
                            current_shell = ShellHandler(config,False)               
                        except KeyboardInterrupt:
                            keyboardInterrupt()
                else:
                    caller = argv_list[1] if argv_list[1] in exclude_config else "config"
                    if "main_error" in argv_list: 
                        caller = "main_error" 
                    try:
                        current_shell = ShellHandler({
                            "config_obj": {
                                "global_elements":{
                                    "caller":caller,
                                }
                            }
                        },False)
                    except KeyboardInterrupt:
                        keyboardInterrupt()

            if current_shell: 
                try: 
                    return_caller = current_shell.start_cli(argv_list)
                except KeyboardInterrupt:
                    keyboardInterrupt()

                
        except KeyboardInterrupt:
            keyboardInterrupt()     


def keyboardInterrupt():
    log = Logging()
    log.logger["main"].critical(f"user terminated nodectl prematurely with keyboard interrupt")
    print("")
    print(colored("  user terminating nodectl prematurely","red"))
    exit(1)


def logging_setup(argv_list):
    if "service_restart" in argv_list:
        return "auto"
    if "uvos" in argv_list:
        return "version" 
    return "main"
  

if __name__ == "__main__":
    try:
        cli_commands(argv)        
    except KeyboardInterrupt:
        keyboardInterrupt()
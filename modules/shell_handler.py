import concurrent.futures
from sys import exit
import time
from datetime import datetime
from termcolor import colored, cprint
from concurrent.futures import ThreadPoolExecutor, wait as thread_wait
from os import geteuid, getgid, environ, system, walk, remove
from types import SimpleNamespace
from pathlib import Path

from .auto_restart import AutoRestart
from .functions import Functions
from .upgrade import Upgrader
from .install import Installer
from .command_line import CLI
from .troubleshoot.errors import Error_codes
from .troubleshoot.logger import Logging
from .config.versioning import Versioning
from .config.valid_commands import pull_valid_command

class ShellHandler:

    def __init__(self, config_obj, debug):

        try:
            self.log = Logging() # install exception
        except Exception as e:
            print(colored("Are you sure your are running with 'sudo'","red",attrs=["bold"]))
            print(colored("nodectl unrecoverable error","red",attrs=["bold"]))
            print(colored("nodectl may not be installed?","red"),colored("hint:","cyan"),"use sudo")
            exit("  sudo rights error")

        self.functions = Functions(config_obj)
        self.error_messages = Error_codes(self.functions)
        self.error_messages.functions = self.functions

        self.config_obj = config_obj
        
        self.install_flag = False
        self.restart_flag = False
        self.has_existing_p12 = False
        self.debug = debug
        self.correct_permissions = True
        self.auto_restart_enabled = False
        self.environment_requested = None
        
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        self.node_service = "" #empty
        self.packages = {}
        
        self.get_auto_restart_pid()
        self.userid = geteuid()
        self.groupid = getgid()

        self.ip_address = self.functions.get_ext_ip()
        

    def build_cli_obj(self,skip_check=False):
        build_cli = self.check_non_cli_command() if skip_check == False else True
        self.invalid_version = False
        cli = None
        if build_cli:
            command_obj = {
                "caller": "shell_handler",
                "command": self.called_command,
                "profile": self.profile,  
                "command_list": self.argv,
                "ip_address": self.ip_address,
                "skip_services": self.skip_services,
                "profile_names": self.profile_names,
                "functions": self.functions,
                "valid_commands": self.valid_commands
            }   
            cli = CLI(command_obj)
            cli.check_for_new_versions({
                "caller": self.called_command
            })
            if cli.skip_warning_messages:
                cli.invalid_version = False
            return cli 

        if self.called_command != "install":
            if self.config_obj["global_elements"]["developer_mode"] or "--skip_warning_messages" in self.argv:
                cli = {
                    "skip_warning_messages": True,
                    "invalid_version": False,
                }
                cli = SimpleNamespace(**cli)
                
        return cli
    
         
    def start_cli(self,argv):
        self.argv = argv
        self.check_error_argv(argv)
        
        self.skip_services = True
        return_value = 0

        self.log.logger.info(f"obtain ip address: {self.ip_address}")
                
        # commands that do not need all resources
        if "main_error" in argv:
            self.functions.auto_restart = False
            self.log.logger.error(f"invalid command called [{self.called_command}] sending to help file.")
            self.functions.print_help({
                "usage_only": True,
                "nodectl_version_only": True,
                "hint": "unknown",
            })

        version_cmd = ["-v","_v","version"]
        if argv[1] in version_cmd:
            self.functions.auto_restart = False
            self.show_version()
            exit(0)
        verify_command = ["verify_nodectl","_vn","-vn"]
        if argv[1] in verify_command:
            self.functions.auto_restart = False
            self.digital_signature(argv)
            exit(0)

        self.handle_versioning()
        self.check_valid_command()

        self.setup_profiles()
        self.check_auto_restart()
        self.check_skip_services()
        self.check_for_profile_requirements()

        if "all" in self.argv:
            self.check_all_profile()     

        self.cli = self.build_cli_obj()
        
        if self.cli != None and self.cli.invalid_version:
            self.functions.confirm_action({
                "yes_no_default": "NO",
                "return_on": "YES",
                "strict": True,
                "prompt_color": "red",
                "prompt": "Are you sure you want to continue?",
                "exit_if": True
            })
            
        restart_commands = ["restart","slow_restart","restart_only","_sr","join"]
        service_change_commands = ["start","stop","leave"]
        status_commands = ["status","_s","quick_status","_qs","uptime"]
        node_id_commands = ["id","dag","nodeid"]
        cv_commands = ["check_versions","_cv"]
        removed_clear_file_cmds = [
            "clear_uploads","_cul","_cls","clear_logs",
            "clear_snapshots","clear_backups",
            "reset_cache","_rc","clean_snapshots","_cs",
        ]
        ssh_commands = ["disable_root_ssh","enable_root_ssh","change_ssh_port"]
        config_list = ["view_config","validate_config","_vc", "_val"]
        clean_files_list = ["clean_files","_cf"]
        
        if self.called_command != "service_restart":
            self.functions.print_clear_line()
        
        if self.called_command in status_commands:
            try: profile = self.argv[self.argv.index("-p")+1]
            except: profile = "empty"
            self.cli.show_system_status({
                "rebuild": False,
                "wait": False,
                "print_title": True,
                "-p": profile,
                "called": self.called_command,
                "command_list": self.argv
            })
            
        elif self.called_command in service_change_commands:
            if not self.help_requested:
                try: self.cli.set_profile(self.argv[self.argv.index("-p")+1])
                except: 
                    self.error_messages.error_code_messages({
                        "error_code": "sh-161",
                        "line_code": "profile_error",
                    })
            if not self.help_requested:            
                if self.called_command == "start":
                    self.cli.cli_start({
                        "argv_list": self.argv,
                    })
                elif self.called_command == "stop":
                    self.cli.cli_stop({
                        "show_timer": False,
                        "spinner": True,
                        "upgrade_install": False,
                        "argv_list": self.argv,
                        "check_for_leave": True,
                    })
                elif self.called_command == "leave":
                    self.cli.cli_leave({
                        "secs": 30,
                        "reboot_flag": False,
                        "skip_msg": False,
                        "argv_list": self.argv,
                        "threaded": True,
                    })
            else:  
                self.functions.print_help({
                    "extended": self.called_command,
                })     
          
        elif self.called_command in restart_commands:
            restart = True
            slow_flag = False
            cli_join_cmd = False
            secs = 30
            if self.called_command == "slow_restart" or self.called_command == "_sr":
                slow_flag = True
                secs = 600
            if self.called_command == "join":
                if "all" in self.argv:
                    return_value = self.cli.print_removed({
                        "command": "-p all on join",
                        "is_new_command": False,
                        "version": "v2.0.0",
                        "done_exit": False
                    })
                    self.functions.print_help({
                        "nodectl_version_only": True,
                        "extended": "join_all",
                    })
                else:
                    self.cli.cli_join({
                        "skip_msg": False,
                        "wait": True,
                        "argv_list": self.argv
                    })
                    restart = False

            if restart:
                self.cli.cli_restart({
                    "secs": secs,
                    "restart_type": self.called_command,
                    "slow_flag": slow_flag,
                    "cli_join_cmd": cli_join_cmd,
                    "cli_leave_cmd": False,
                    "argv_list": self.argv
                })

        elif self.called_command == "list":
            self.cli.show_list(self.argv)  
        elif self.called_command == "show_current_rewards" or self.called_command == "_scr":
            self.cli.show_current_rewards(self.argv)  
        elif self.called_command == "find":
            self.cli.cli_find(self.argv)
        elif self.called_command == "peers":
            self.cli.show_peers(self.argv)
        elif self.called_command == "whoami":
            self.cli.show_ip(self.argv)
        elif self.called_command == "nodeid2dag":
            self.cli.cli_nodeid2dag(self.argv)
        elif self.called_command == "show_node_states" or self.called_command == "_sns":
            self.cli.show_node_states(self.argv)
        elif self.called_command == "passwd12":
            return_value = self.cli.passwd12(self.argv)
        elif self.called_command == "reboot":
            self.cli.cli_reboot(self.argv)
        elif self.called_command in node_id_commands:
            command = "dag" if self.called_command == "dag" else "nodeid"
            self.cli.cli_grab_id({
                "command": command,
                "argv_list": self.argv
            })
        elif self.called_command == "upgrade_nodectl_testnet":
            self.cli.print_removed({
                "command": self.called_command,
                "version": "v2.8.0",
                "new_command": "upgrade_nodectl"
            })
        elif self.called_command == "upgrade_nodectl":
            return_value = self.cli.upgrade_nodectl({
                "argv_list": self.argv,
                "help": self.argv[0]
            })
        elif self.called_command in ssh_commands:
            self.cli.ssh_configure({
                "command": self.called_command,
                "argv_list": self.argv   
            })
        elif self.called_command in clean_files_list:
            command_obj = {"argv_list": self.argv, "action": "normal"}
            self.cli.clean_files(command_obj)
            
        elif self.called_command in removed_clear_file_cmds:
            return_value = self.cli.print_removed({
                "command": self.called_command,
                "version": "v2.0.0",
                "new_command": "n/a"
            })
            
        elif self.called_command == "check_seedlist" or self.called_command == "_csl":
            return_value = self.cli.check_seed_list(self.argv)
        elif self.called_command == "check_consensus" or self.called_command == "_con":
            self.cli.cli_check_consensus({"argv_list":self.argv})
        elif self.called_command == "check_minority_fork" or self.called_command == "_cmf":
            self.cli.cli_minority_fork_detection({"argv_list":self.argv})
        elif self.called_command == "create_p12":
            self.cli.cli_create_p12(self.argv)
        elif self.called_command == "update_seedlist" or self.called_command == "_usl":
            return_value = self.cli.update_seedlist(self.argv)
        elif self.called_command == "export_private_key": 
            self.cli.export_private_key(self.argv)
        elif self.called_command == "check_source_connection" or self.called_command == "_csc":
            return_value = self.cli.check_source_connection(self.argv)
        elif self.called_command == "show_node_proofs" or self.called_command == "_snp":
            return_value = self.cli.show_current_snapshot_proofs(self.argv)
        elif self.called_command == "check_connection" or self.called_command == "_cc":
            self.cli.check_connection(self.argv)
        elif self.called_command == "send_logs" or self.called_command == "_sl":
            self.cli.prepare_and_send_logs(self.argv)
        elif self.called_command == "check_seedlist_participation" or self.called_command == "_cslp":
            self.cli.show_seedlist_participation(self.argv)
        elif self.called_command == "download_status" or self.called_command == "_ds":
            self.cli.show_download_status({
                "caller": "download_status",
                "command_list": self.argv
            })
        elif self.called_command in cv_commands:
            self.cli.check_versions(self.argv)
        elif "auto_" in self.called_command:
            if self.called_command == "auto_upgrade":
                if "help" not in self.argv:
                    self.argv.append("help")
                self.called_command = "auto_restart"
            if "help" in self.argv:
                self.functions.print_help({
                    "usage_only": True,
                    "nodectl_version_only": True,
                    "extended": "auto_restart",
                })
            else:
                self.auto_restart_handler(self.argv[0],True,True)
        elif self.called_command == "service_restart":
            if self.argv[0] == "--variable1=enable": self.argv[0] = "enable" # on-boot 
            if self.argv[0] != "enable":
               self.log.logger.error(f"start cli --> invalid request [{self.argv[0]}]")
               exit(0)
            self.auto_restart_handler("service_start",True)
        elif self.called_command == "log" or self.called_command == "logs":
            return_value = self.cli.show_logs(self.argv)
        elif self.called_command == "install":
            self.install(self.argv)
        elif self.called_command == "upgrade":
            self.upgrade_node(self.argv)
        elif self.called_command == "upgrade_path" or self.called_command == "_up":
            self.cli.check_nodectl_upgrade_path({
                "called_command": self.called_command,
                "argv_list": self.argv,
            })
        elif self.called_command == "refresh_binaries" or self.called_command == "_rtb":
            self.cli.download_tess_binaries(self.argv)
        elif self.called_command == "health":
            self.cli.show_health(self.argv)
        elif self.called_command == "show_service_log" or self.called_command == "_ssl":
            self.cli.show_service_log(self.argv)
        elif self.called_command == "sec":
            self.cli.show_security(self.argv)
        elif self.called_command == "price" or self.called_command == "prices":
            self.cli.show_prices(self.argv)
        elif "market" in self.called_command:
            return_value = self.cli.show_markets(self.argv)
        elif self.called_command == "show_dip_error" or self.called_command == "_sde":
            self.cli.show_dip_error(self.argv)
        elif self.called_command == "show_p12_details" or self.called_command == "_spd":
            self.cli.show_p12_details(self.argv)

        elif self.called_command == "help" or self.called_command == "_h":
                self.functions.print_help({
                    "usage_only": False,
                })
        elif self.called_command == "help_only": 
            self.functions.print_help({
                "usage_only": True,
                "hint": False,
            })
        elif self.called_command in config_list:
            self.functions.print_help({
                "usage_only": True,
                "nodectl_version_only": True,
                "extended": self.called_command,
            })
            
        self.handle_exit(return_value)
        
        
    # CHECK METHODS
    # =============  
          
    def check_error_argv(self, argv):
        # error check first
        self.called_cmds = []
        self.help_requested = False
        invalid = False
        
        if "main_error" in self.argv: 
            try:
                subdirectories = next(walk("/var/tessellation"))[1]
                if len(subdirectories) < 2 and "nodectl" in subdirectories:
                    invalid = True
            except StopIteration:
                invalid = True
            
            if invalid:
                self.functions.print_paragraphs([
                    [" NODECTL ERROR ",0,"grey,on_red"], ["unable to find valid installation",0,"red"],
                    ["on this server.",1,"red"],
                    ["install command:",0], ["sudo nodectl install",1,"yellow","bold"]
                ])
                exit("  invalid nodectl installation")
                
            self.called_command = "help_only"
            return
                    
        if "uvos" in argv: 
            # do not log if versioning service initialized Configuration
            for handler in self.log.logger.handlers[:]:
                self.log.logger.removeHandler(handler)
            self.argv[1] = "uvos"
            
        try:
            self.called_command = self.argv[1]
        except:
            self.called_command = "help_only"
            return
                    
        if "help" in self.argv: self.help_requested = True  
              
        max = len(self.argv) if len(self.argv) > 7 else 8
        for n in range(2,max):  # make sure at least 8 entries
            try:
                self.argv[n]
            except:
                self.called_cmds.append("empty") 
            else:
                self.called_cmds.append(self.argv[n])
                
        self.argv = self.called_cmds
        self.called_command = self.called_command.replace("-","_")
            

    def check_auto_restart(self,action="start"):
        # do we need to make sure auto_restart is turned off?
        if action == "end":
            if self.auto_restart_enabled and self.called_command != "auto_restart":
                self.auto_restart_handler("enable",True)
                exit(0)
                
        kill_auto_restart_commands = [
            "restart_only","slow_restart","-sr",
            "leave","start","stop","restart","join", 
            "nodectl_upgrade","upgrade_nodectl_testnet",
        ]
            
        if self.called_command not in ["help","install"]:    
            if self.functions.config_obj["global_auto_restart"]["auto_restart"]:
                self.auto_restart_enabled = True
            
        if self.called_command in kill_auto_restart_commands:
            self.log.logger.warn(f"cli request {self.called_command} received. DISABLING auto_restart if enabled")
            self.auto_restart_handler("disable",True)
                

    def check_skip_services(self):
        # do we want to skip loading the node service obj?
        dont_skip_service_list = [
            "status","_s","quick_status","_qs","reboot","uptime",
            "start","stop","restart","slow_restart","_sr",
            "restart_only","auto_restart","service_restart", # not meant to be started from cli
            "join","id", "nodeid", "dag", "passwd12","export_private_key",
            "find","leave","peers","check_source_connection","_csc",
            "check_connection","_cc","refresh_binaries","_rtb",
            "update_seedlist","_usl","upgrade_nodectl","upgrade_nodectl_testnet",
        ]
        
        if self.called_command in dont_skip_service_list:
            self.skip_services = False
                

    def check_all_profile(self):
        # do we want to skip loading the node service obj?
        all_profile_allow_list = [
            "restart","restart_only","slow_restart","-sr","join","status"
        ]
        if self.called_command in all_profile_allow_list:
            return
        self.called_command = "help"  # otherwise force help screen
                

    def check_non_cli_command(self):
        non_cli_commands = [
            "upgrade","install","auto_restart",
            "service_restart","uvos","help",
        ]
        if self.called_command in non_cli_commands:
            return False
        return True
    

    def check_valid_command(self):
        cmds = pull_valid_command()
        self.valid_commands = cmds[0]
        valid_short_cuts = cmds[1]
        service_cmds = cmds[2]
        removed_cmds = cmds[3]

        self.log.logger.debug(f"nodectl feature count [{len(self.valid_commands)}]")
        self.functions.valid_commands = self.valid_commands 
        
        all_command_check = self.valid_commands+valid_short_cuts+service_cmds+removed_cmds

        if self.called_command not in all_command_check:
            self.called_command = "help_only"
        
        
    def verify_env_and_versioning(self,command_obj):
        force = command_obj.get("force",False)
        show_list = command_obj.get("show_list",False)
        env_provided = command_obj.get("env_provided",False)
        action = command_obj.get("action","normal")
        self.log.logger.info("testing permissions")
        
        progress = {
            "status": "running",
            "text_start": "Check permissions & versioning",
        }
        self.functions.print_cmd_status(progress) 
        time.sleep(.8)

        if action == "normal":
            environments = self.functions.pull_profile({"req": "environments"})
            if not show_list:
                show_list = True if environments["multiple_environments"] else show_list
            
            if env_provided:
                print("")
                if env_provided not in list(environments["environment_names"]):
                    self.error_messages.error_code_messages({
                        "error_code": "sh-441",
                        "line_code": "environment_error",
                        "extra": "upgrade",
                        "extra2": env_provided
                    })
        
            if show_list:
                print("")
                self.functions.print_header_title({
                    "line1": "Upgrade Environment Menu",
                    "newline": "both",
                    "single_line": True,
                })

                msg_start = "Multiple Metagraph environments were found on this system."
                if show_list and not environments["multiple_environments"]:
                    msg_start = "Show list of Metagraphs was requested."
                    self.log.logger.debug("Upgrade show list of environments requested")
                if env_provided:
                    msg_start = "Choose environment from list requested but environment request was entered at the command line."
                    self.functions.print_cmd_status({
                        "text_start": "Environment requested by argument",
                        "brackets": "-e",
                        "status": env_provided,
                        "status_color": "blue",
                        "newline": True,
                    })
                    print("")

                if environments["multiple_environments"] and not env_provided:
                    self.log.logger.debug(f"Upgrade found multiple metagraph environments on the same Node that may are supported by different versions of nodectl")
                    self.functions.print_paragraphs([
                        [f"{msg_start} nodectl can only upgrade one environment at a time.",0],
                        ["Please select an environment by",0], ["key pressing",0,"yellow"], 
                        ["the number correlating to the environment you wish to upgrade.",2],  
                        ["PLEASE CHOOSE AN ENVIRONMENT TO UPGRADE",2,"magenta","bold"]                      
                    ])
                environment = self.functions.print_option_menu({
                    "options": list(environments["environment_names"]),
                    "return_value": True,
                    "color": "magenta"
                })
                
                verb = "Using" if env_provided == environment else "Selected"
                print("")
                self.functions.print_cmd_status({
                    "text_start": f"{verb} environment",
                    "status": environment,
                    "status_color": "blue",
                    "newline": True,
                })
            else:
                if env_provided:
                    environment = env_provided
                else:
                    environment = list(environments["environment_names"])[0]
                                
            current = self.functions.version_obj["node_nodectl_version"]
            
            show_warning = False
            if self.functions.version_obj[environment]["nodectl"]["nodectl_uptodate"]:
                if not isinstance(self.functions.version_obj[environment]["nodectl"]["nodectl_uptodate"],bool):
                    show_warning = True
                    
            if show_warning:
                err_warn = "warning"
                err_warn_color = "yellow"
                if self.install_upgrade == "installation":
                    err_warn = "error"
                    err_warn_color = "red"
                
                self.functions.print_cmd_status({
                    "text_start": "Check permissions & versioning",
                    "status": err_warn,
                    "status_color": err_warn_color,
                    "newline": True,
                })
                
                self.functions.print_paragraphs([
                    ["This is not a current stable version of nodectl.",1,"red","bold"],
                    ["Recommended to:",1],
                    ["  - Cancel this upgrade of Tessellation.",1,"magenta"],
                    ["  - Issue:",0,"magenta"], ["sudo nodectl upgrade_nodectl",1,"green"],
                    ["  - Restart this upgrade of Tessellation.",1,"magenta"],
                ])
                
                try: 
                    skip_warning_messages = self.cli.skip_warning_messages
                except:
                    skip_warning_messages = False
                    
                if force or skip_warning_messages:
                    self.log.logger.warn(f"an attempt to {self.install_upgrade} with an non-interactive mode detected {current}")  
                    self.functions.print_paragraphs([
                        [" WARNING ",0,"red,on_yellow"], [f"non-interactive mode was detected, or extra parameters were supplied to",0],
                        [f"this {self.install_upgrade}",1],
                        ["It will continue at the Node Operator's",0,"yellow"],
                        ["own risk and decision.",2,"yellow","bold"]
                    ])
                else:
                    self.log.logger.warn(f"an attempt to {self.install_upgrade} with an older nodectl detected {current}")  
                    prompt_str = f"Are you sure you want to continue this {self.install_upgrade}?"
                    self.functions.confirm_action({
                        "yes_no_default": "n",
                        "return_on": "y",
                        "prompt": prompt_str,
                    })
                self.log.logger.warn(f"{self.install_upgrade} was continued with an older version of nodectl [{current}]") 
        else:
            request_environment = False
            try:
                environment = self.functions.environment_name
            except AttributeError:
                request_environment = True
            if not self.functions.environment_name: request_environment = True
            
            if action == "install": 
                print("") # create newline
                title = "PLEASE CHOOSE METAGRAPH TO INSTALL"
                
            if request_environment:
                environment = self.functions.print_profile_env_menu({
                    "p_type": "environment",
                    "title": title,
                })
                
            self.functions.print_cmd_status({
                "text_start": "Using environment",
                "status": environment,
                "newline": True,
            })
                 
        self.functions.check_sudo()
        self.functions.print_cmd_status({
            **progress,
            "status": "complete",
            "newline": True
        })

        self.environment_requested = environment
        
        
    def check_deps(self,package):
        bashCommand = f"dpkg -s {package}"
        result = self.functions.process_command({
            "bashCommand": bashCommand,
            "proc_action": "timeout"
        })
        if "install ok installed" in result:
            self.packages[f'{package}'] = True 


    def check_for_profile_requirements(self):
        # check if default profile needs to be set
        self.log.logger.debug(f"checking profile requirements | command [{self.called_command}]") 
        need_profile, need_environment = False, False
        called_profile, called_environment = False, False
        profile_hint, env_hint, either_or_hint = False, False, False
        
        def send_to_help_method(hint):
            self.functions.print_help({
                "usage_only": True,
                "hint": hint,
            }) 
                               
        if self.help_requested:
            return

        need_environment_list = [
            "refresh_binaries","_rtb",
            "update_seedlist", "_usl",
            "upgrade_path","_up","install",
            "check_minority_fork","_cmf",
        ]

        need_profile_list = [
            "find","quick_check","logs",
            "start","stop","restart",
            "slow_restart","_sr","restart_only",
            "peers","check_source_connection","_csc",
            "check_connection","_cc",
            "send_logs","_sl","show_node_proofs","_snp",
            "nodeid","id","dag","export_private_key",
            "check_seedlist","_csl","update_seedlist","_usl",
            "show_service_log","_ssl","download_status","_ds",
            "show_dip_error","_sde","check_consensus","_con",
            "check_minority_fork","_cmf",
        ]                

        if "-p" in self.argv:
            called_profile = self.argv[self.argv.index("-p")+1]
            if self.called_command not in need_profile_list: return
            self.functions.check_valid_profile(called_profile)
        
        if self.called_command in need_profile_list and self.called_command in need_environment_list:
            either_or_hint = True
            
        if self.called_command in need_profile_list:
            need_profile = True
            if "help" in self.argv:
                pass
            elif self.called_command == "logs" and "nodectl" in self.argv:
                # logs command exception
                pass
            elif len(self.argv) == 0 or ("-p" not in self.argv or called_profile == "empty"):
                profile_hint = True
                
        if self.called_command in need_environment_list:
            # need_environment = True
            if "help" in self.argv:
                pass
            elif self.called_command == "logs" and "nodectl" in self.argv:
                # logs command exception
                pass
            elif len(self.argv) == 0 or ("-e" not in self.argv or called_profile == "empty"):
                env_hint = True
        
        if env_hint and profile_hint and either_or_hint:
            send_to_help_method("profile_env")
        elif profile_hint and not either_or_hint:
            self.profile = self.functions.profile_names[0]
            if len(self.functions.profile_names) > 1:
                self.profile = self.functions.print_profile_env_menu({"p_type": "profile"})
            self.argv.extend(["-p",self.profile])
            need_profile = False
        elif env_hint and not either_or_hint:
            try:
                self.environment_requested = self.functions.environment_names[0]
            except:
                if self.called_command == "install":
                    self.functions.pull_remote_profiles({
                        "retrieve": "config_file",
                        "set_in_functions": True,
                    })
                    return
                else: self.environment_requested = []
                
            if len(self.functions.environment_names) > 1 or len(self.functions.environment_names) < 1:
                self.environment_requested = self.functions.print_profile_env_menu({"p_type": "environment"})
            self.argv.extend(["-e",self.environment_requested])
            need_profile = False  
                      
        if need_profile and self.called_command != "empty":
           if "-p" in self.argv: self.profile = called_profile
     
    # =============  

    def handle_versioning(self):
        if self.called_command == "install": called_cmd = "show_version"
        elif self.called_command in ["version","_v"]: return
        else: called_cmd = self.called_command
        
        need_forced_update = [
            "check_versions","_cv",
            "uvos","update_version_object",
            "nodectl_upgrade", "upgrade",
            "upgrade_path","_up"
        ]
        
        print_messages, show_spinner, verify_only, force, print_object = True, True, False, False, False   
        if called_cmd in need_forced_update: force = True
        if "--force" in self.argv: force = True

        if called_cmd == "update_version_object":
            if "-v" in self.argv: verify_only = True
            if "--print" in self.argv: print_object = True

        if called_cmd == "uvos":
            print_messages, show_spinner = False, False
            
        versioning = Versioning({
            "config_obj": self.config_obj,
            "show_spinner": show_spinner,
            "print_messages": print_messages,
            "called_cmd": called_cmd,
            "verify_only": verify_only,
            "print_object": print_object,
            "force": force
        })

        if called_cmd == "update_version_object" or called_cmd == "uvos":
            if "help" not in self.argv:
                exit(0)
            
        self.version_obj = versioning.get_version_obj()  
        self.functions.version_obj = self.version_obj
        self.functions.set_statics()

        if called_cmd == "update_version_object": # needs to be checked after version_obj is created
            self.functions.check_for_help(self.argv,"update_version_object")          
          
          
    def print_ext_ip(self):
        self.functions.print_cmd_status({
            "text_start": "Obtaining External IP",
            "status": "running",
            "delay": .8,

        })
        self.functions.print_cmd_status({
            "text_start": "Obtaining External IP",
            "status": self.ip_address,
            "status_color": "magenta",
            "newline": True
        })
        
                                                
    def update_os(self):
        with ThreadPoolExecutor() as executor:
            self.functions.status_dots = True
            self.log.logger.info(f"updating the Debian operating system.")
            environ['DEBIAN_FRONTEND'] = 'noninteractive'
            
            _ = executor.submit(self.functions.print_cmd_status,{
                "text_start": "Updating the Debian OS system",
                "dotted_animation": True,
                "status": "running",
            })
                    
            if self.debug:
                pass
            else:
                bashCommand = "apt-get -o Dpkg::Options::=--force-confold -y update"
                self.functions.process_command({
                    "bashCommand": bashCommand,
                    "proc_action": "timeout",
                })        

            self.functions.status_dots = False
            self.functions.print_cmd_status({
                "text_start": "Updating the Debian OS system",
                "status": "complete",
                "newline": True
            })
        

    def setup_profiles(self):
        self.log.logger.debug(f"setup profiles [{self.called_command}]")

        skip_list = [
            "main_error","validate_config","install",
            "view_config","_vc","_val","help",
        ]
        if self.called_command in skip_list:
            self.profile = None
            self.profile_names = None
            return
        
        self.profile_names = self.functions.profile_names 
        self.profile = self.functions.default_profile  # default to first layer0 found
                

    def show_version(self):
        self.log.logger.info(f"show version check requested")
        versioning = Versioning({
            "config_obj": self.config_obj,
            "print_messages": False,
            "called_cmd": "show_version",
        })
        version_obj = versioning.version_obj
        self.functions.print_clear_line()
        parts = self.functions.cleaner(version_obj["node_nodectl_version"],"remove_char","v")
        parts = parts.split(".")
        
        print_out_list = [
            {
                "header_elements" : {
                    "VERSION": version_obj["node_nodectl_version"],
                    "MAJOR": parts[0],
                    "MINOR": parts[1],
                    "PATCH": parts[2],
                },
                "spacing": 13
            },
        ]
        
        for header_elements in print_out_list:
            self.functions.print_show_output({
                "header_elements" : header_elements
            })  
            

    def digital_signature(self,command_list):
        self.log.logger.info("Attempting to verify nodectl binary against code signed signature.")
        self.functions.check_for_help(command_list,"verify_nodectl")
        self.functions.print_header_title({
            "line1": "VERIFY NODECTL",
            "line2": "warning verify keys",
            "newline": "top",
        })   
        
        version_obj = Versioning({"called_cmd": self.called_command})
        node_arch = self.functions.get_arch()
        nodectl_version_github = version_obj.version_obj["nodectl_github_version"]
        nodectl_version_full = version_obj.version_obj["node_nodectl_version"]
        
        outputs, urls = [], []
        cmds = [  # must be in this order
            [ "nodectl_public","fetching public key","PUBLIC KEY","-----BEGINPUBLICKEY----"],
            [ f'{nodectl_version_github}_{node_arch}.sha256',"fetching digital signature hash","BINARY HASH","SHA256"],
            [ f"{nodectl_version_github}_{node_arch}.sig","fetching digital signature","none","none"],
        ]
                
        def send_error(extra):
            self.error_messages.error_code_messages({
                "error_code": "cmd-3432",
                "line_code": "verification_failure",
                "extra": extra,
            })     
    
        progress = {
            "status": "running",
            "status_color": "red",
            "delay": 0.3
        }
        for n, cmd in enumerate(cmds): 
            self.functions.print_cmd_status({
                **progress,
                "text_start": cmd[1],
            })
            
            url = f"https://raw.githubusercontent.com/StardustCollective/nodectl/{nodectl_version_github}/admin/{cmd[0]}"
            urls.append(url)
            if cmd[2] == "none":
                url = f"https://github.com/StardustCollective/nodectl/releases/download/{nodectl_version_full}/{cmd[0]}"
                verify_cmd = f"openssl dgst -sha256 -verify /var/tmp/nodectl_public -signature /var/tmp/{cmd[0]} /var/tmp/{cmds[1][0]}"

            wget_cmd = 'sudo wget -H "Cache-Control: no-cache, no-store, must-revalidate" -H "Pragma: no-cache" -H "Expires: 0" '
            wget_cmd += f'{url} -O /var/tmp/{cmd[0]} -o /dev/null'
            system(wget_cmd)
            full_file_path = f"/var/tmp/{cmd[0]}"
            
            if cmd[2] == "none":
                self.functions.print_cmd_status({
                    "text_start": cmd[1],
                    "status": "complete",
                    "status_color": "green",
                    "newline": True
                })  
            else:
                text_output = Path(full_file_path).read_text().lstrip()
                if n != 1: text_output = text_output.replace(" ","")
                if cmd[3] not in text_output:
                    send_error(f"invalid {cmd[2]} downloaded or unable to download")
                outputs.append(text_output.replace("-----BEGINPUBLICKEY-----","").replace("-----ENDPUBLICKEY-----","").replace("\n",""))

                self.functions.print_cmd_status({
                    "text_start": cmd[1],
                    "status": "complete",
                    "status_color": "green",
                    "newline": True
                })   
        
        for n, cmd in enumerate(cmds[:-1]):   
            if cmd[2] == "PUBLIC KEY": 
                extra1, extra2 = "-----BEGIN PUBLIC KEY-----", "-----END PUBLIC KEY-----" 
                extra1s, main = 1,1
            else:
                extra1, extra2 = "", "" 
                extra1s, main = 0,-1   
                            
            self.functions.print_paragraphs([
                ["",1],[cmd[2],1,"blue","bold"],
                ["=","half","blue","bold"],
                [extra1,extra1s,"yellow"],
                [outputs[n],main,"yellow"],
                [extra2,2,"yellow"],
                ["To further secure that you have the correct binary that was authenticated with a matching",0,"magenta"],
                [f"{cmd[2]} found in yellow [above].",0,"yellow"],["Please open the following",0,"magenta"],["url",0,"yellow"], 
                ["in our local browser to compare to the authentic repository via",0,"magenta"], ["https",0,"green","bold"],
                ["secure hypertext transport protocol.",2,"magenta"],
                [urls[n],2,"blue","bold"],
            ])

        self.functions.print_cmd_status({
            "text_start": "verifying signature match",
            "newline": True
        })   
        
        self.log.logger.info("copy binary nodectl to nodectl dir for verification via rename")
        
        system(f"cp /usr/local/bin/nodectl /var/tmp/nodectl_{node_arch} > /dev/null 2>&1")    
        result_sig = self.functions.process_command({
            "bashCommand": verify_cmd,
            "proc_action": "timeout"
        })
        result_nodectl_current_hash = self.functions.process_command({
            "bashCommand": f"openssl dgst -sha256 -hex nodectl_{node_arch}",
            "proc_action": "timeout",
            "working_directory": "/var/tmp/"
        }).strip("\n")
        
        bg, verb, error_line = "on_red","INVALID SIGNATURE - WARNING", ""
        
        # handle openssl version incompatibilities
        output_mod =  outputs[1].split('(', 1)[-1]
        result_nodectl_current_hash_mod = result_nodectl_current_hash.split('(', 1)[-1]
        
        self.log.logger.info("nodectl digital signature verification requested")
        if "OK" in result_sig and result_nodectl_current_hash_mod == output_mod:
            self.log.logger.info(f"digital signature verified successfully | {result_sig}")
            bg, verb = "on_green","SUCCESS - AUTHENTIC NODECTL"
        else: 
            error_line = "Review logs for details."
            self.log.logger.critical(f"digital signature did NOT verified successfully | {result_sig}")
        self.log.logger.info(f"digital signature - local file hash | {result_nodectl_current_hash}")
        self.log.logger.info(f"digital signature - remote file hash | {outputs[1]}")
        
        self.functions.print_paragraphs([
            ["",1],["VERIFICATION RESULT",1,"blue","bold"],
            [f" {verb} ",1,f"blue,{bg}","bold"],
            [error_line,1,"red"]
        ])
                 
        #clean up
        self.log.logger.info("cleaning up digital signature check files.")
        for cmd in cmds[1:]:
            remove(f'/var/tmp/{cmd[0]}')
        remove(f'/var/tmp/nodectl_{node_arch}')                    
    
    
    def install_upgrade_common(self,command_obj):
        self.functions.print_clear_line()
        self.verify_env_and_versioning(command_obj)
        self.print_ext_ip()        
            
            
    def confirm_int_upg(self):
        
        self.log.logger.info(f"{self.install_upgrade} for Tessellation and nodectl started")       
        
        if self.install_upgrade == "installation":
            print(f'  {colored("WARNING","red",attrs=["bold"])} {colored("You about to turn this VPS or Server into a","red")}')
            cprint("  Constellation Network Validator Node","green",attrs=['bold'])
        else:
            if self.auto_restart_pid:
                self.log.logger.info("terminating auto_restart in order to upgrade")  
                progress = {
                    "text_start": "Terminating auto_restart",
                    "status": "running",
                    "color": "yellow",
                }
                self.functions.print_cmd_status(progress)          
                self.auto_restart_handler("disable",True)
                self.functions.print_cmd_status({
                    **progress,
                    "status": "complete",
                    "status_color": "green",
                    "newline": True,
                })   
                
        prompt_str = f"Are you sure you want to continue this {self.install_upgrade}?"
        self.functions.confirm_action({
            "yes_no_default": "n",
            "return_on": "y",
            "prompt": prompt_str,
        })


    def get_auto_restart_pid(self):
        cmd = "ps -ef"
        results = self.functions.process_command({
            "bashCommand": cmd,
            "proc_action": "poll"
        })
        
        results = results.split("\n")
        self.auto_restart_pid = False
        for line in results:
            if "service_restart" in line:
                line = " ".join(line.split()).split(" ")
                self.auto_restart_pid = int(line[1])

       
    def auto_restart_handler(self,action,cli=False,manual=False):
        restart_request = warning = False  
        pid_color = "green"
        end_status = "enabled"
        
        if not self.auto_restart_pid:
            self.auto_restart_pid = "disabled"
            end_status = "not running"
            pid_color = "blue"  
              
        if action == "restart":
            action = "disable"
            restart_request = True
                            
        if action == "service_start":
            self.log.logger.info("auto_restart - restart session threader - invoked.")

            with ThreadPoolExecutor(max_workers=4) as executor:
                thread_list = []
                # self.profile_names = ["dag-l0"]  # used for debugging purposes
                for n, profile in enumerate(self.profile_names):
                    self.log.logger.info(f"auto_restart - restart threader -  invoked session threads for [{profile}]")
                    first_thread = True if n < 1 else False
                    time.sleep(2)
                    future = executor.submit(
                        AutoRestart,
                        profile,
                        self.functions.config_obj,
                        first_thread,
                    )
                    thread_list.append(future)

                # thread_wait is an alias to wait, and will only execute the next line of this
                # code before the exception kills the entire process therefor it is not logged
                thread_wait(thread_list,return_when=concurrent.futures.FIRST_EXCEPTION)
                system(f'sudo systemctl restart node_restart@"enable" > /dev/null 2>&1')  

            
        if action == "disable":
            if cli:
                end_status = "not running"
                end_color = "blue"
                if self.auto_restart_pid != "disabled":
                    end_status = "disabled" # because disabling
                    end_color = "green"
                    self.functions.print_clear_line()
                    self.functions.print_paragraphs([
                        [" FOUND ",0, "yellow,on_red"], ["auto_restart instance.",1,"red"],
                    ])
                    
                progress = {
                    "text_start": "AutoRestart service with pid",
                    "text_color": "red",
                    "brackets": str(self.auto_restart_pid),
                    "status": "terminating",
                    "color": "yellow",
                }
                self.functions.print_cmd_status(progress)
                system('sudo systemctl stop node_restart@"enable" > /dev/null 2>&1')
                # test pid removal
                self.get_auto_restart_pid()
                
                
                self.functions.print_cmd_status({
                    **progress,
                    "status": end_status,
                    "status_color": end_color,
                    "newline": True,
                })
                
                if self.auto_restart_pid != "disabled" and not restart_request:
                    verb = "of next" if manual else "of"
                    if self.auto_restart_enabled:
                        cprint(f"  Auto Restart will reengage at completion {verb} requested task","green")
                    else:
                        cprint("  This will need to restarted manually...","red")
                    self.log.logger.debug(f"auto_restart process pid: [{self.auto_restart_pid}] killed") 
                    self.auto_restart_pid = False # reset 

                if restart_request:
                    system('sudo systemctl start node_restart@"enable" > /dev/null 2>&1')
                    cprint("  auto_restart restart request completed.","green",attrs=["bold"])
                    time.sleep(.5)
                    self.get_auto_restart_pid()
                    action = "check_pid"
                else:
                    return
        
        if action == "check_pid" or action == "current_pid" or action =="status":
            config_restart = self.functions.config_obj["global_auto_restart"]["auto_restart"]
            config_restart = "True" if config_restart else "False"
            config_restart_color = "green" if config_restart == "True" else "red"
            
            config_upgrade = self.functions.config_obj["global_auto_restart"]["auto_upgrade"]
            config_upgrade = "True" if config_upgrade else "False"
            config_upgrade_color = "green" if config_upgrade == "True" else "red"
            
            config_boot = self.functions.config_obj["global_auto_restart"]["on_boot"]
            config_boot = "True" if config_boot else "False"
            config_boot_color = "green" if config_boot  == "True" else "red"
            
            self.functions.print_clear_line()
            self.functions.print_paragraphs([
                ["AUTO RESTART STATUS CHECK",1,"yellow","bold"]
            ])
            
            print_out_list = [
                {
                    "-BLANK-" :None,
                    "SERVICE PROCESS FOUND (PID)": f"{colored(self.auto_restart_pid,pid_color)}"
                }
            ]
            
            for header_elements in print_out_list:
                self.functions.print_show_output({
                    "header_elements" : header_elements
            })          
            print_out_list = [
                {
                    "header_elements" : {
                        "AUTO RESTART": colored(f'{config_restart: <{14}}',config_restart_color),
                        "AUTO UPGRADE": colored(f'{config_upgrade: <{14}}',config_upgrade_color),
                        "ON BOOT": colored(config_boot,config_boot_color),
                    },
                    "spacing": 14
                }
            ]
            self.functions.print_paragraphs([
                ["",1],["CONFIGURATION SETTINGS",1,"blue","bold"]
            ])            
            for header_elements in print_out_list:
                self.functions.print_show_output({
                    "header_elements" : header_elements,
            })          
            
            return
        
        if action != "enable":  # change back to action != "empty" when enabled in prod
            cprint("  unknown auto_restart parameter detected, exiting","red")
            return

        keys = list(self.functions.config_obj.keys())
        keys.append("global_p12")
        
        for profile in keys:
            if profile == "global_p12":
                if self.functions.config_obj[profile]["passphrase"] == "None":
                    warning = True
                    break
            elif profile in self.profile_names:
                if self.functions.config_obj[profile]["p12_passphrase"] == "None":
                    warning = True
                    break
            
        if warning:
            self.functions.print_paragraphs([
                [" ERROR ",0,"yellow,on_red"], ["Auto Restart",0,"red","underline"], 
                ["cannot be manually enabled if the Node's passphrases are not set in the configuration.",0,"red"],
                ["nodectl",0,"blue","bold"],["will not have the ability to authenticate to the HyperGraph in an automated fashion.",2,"red"],
                ["Action cancelled",1,"yellow"],
            ])
            exit("  auto restart passphrase error")
                        
        if self.auto_restart_pid != "disabled":
            if self.auto_restart_enabled:
                self.functions.print_paragraphs([
                    ["",1], ["Node restart service",0,"green"], 
                    ["does not",0,"green","underline"], ["need to be restarted because pid [",0,"green"],
                    [str(self.auto_restart_pid),-1,"yellow","bold"],
                    ["] was found already.",-1,"green"],["",1]
                ])
            else:
                self.functions.print_paragraphs([
                    ["",1], ["Node restart service not started because pid [",0,"yellow"],
                    [str(self.auto_restart_pid),-1,"green","bold"],
                    ["] found already.",-1,"yellow"],["",1]
                ])
            self.log.logger.warn(f"auto_restart start request initiated; however process exists: pid [{self.auto_restart_pid}]")
            return
        
        system(f'sudo systemctl start node_restart@"{action}" > /dev/null 2>&1')
        if cli:
            print("")
            cprint("  node restart service started... ","green")
            
    
    def upgrade_node(self,argv_list):
        if "help" in argv_list:
            self.functions.print_help({
                "extended": self.called_command,
            })

        self.log.logger.debug(f"{self.called_command} request started") 
        performance_start = time.perf_counter()  # keep track of how long
           
        self.functions.print_header_title({
          "line1": f"{self.called_command.upper()} REQUEST",
          "line2": "TESSELLATION VALIDATOR NODE",
          "clear": True,
        })
        
        self.install_upgrade = "upgrade"
        if "-ni" not in argv_list and not "--ni" in argv_list:
            self.confirm_int_upg()

        self.functions.print_header_title({
            "line1": "Handle OS System Upgrades",
            "single_line": True,
            "newline": "both",
        })
        
        command_obj = {
            "force": True if "-f" in argv_list else False,
            "show_list": True if "-l" in argv_list else False,
            "env_provided": argv_list[argv_list.index("-e")+1] if "-e" in argv_list else False,
            "action": "normal"
        }
        
        # -e gets converted into self.environment_requested
        self.install_upgrade_common(command_obj)
        self.upgrader = Upgrader({
            "ip_address": self.ip_address,
            "functions": self.functions,
            "called_command": self.called_command,
            "environment": self.environment_requested,
            "argv_list": argv_list,
        }) 
        self.update_os()
        self.upgrader.upgrade_process()

        self.functions.print_perftime(performance_start,self.install_upgrade)
        
    
    def install(self,argv_list):
        if "help" in argv_list:
            self.functions.print_help({
                "nodectl_version_only": True,
                "extended": "install",
            })
        self.log.logger.debug("installation request started")
        
        performance_start = time.perf_counter()  # keep track of how long

        environment = argv_list[argv_list.index("-e")+1] if "-e" in argv_list else False
        
        self.functions.print_header_title({
          "line1":  "INSTALLATION REQUEST",
          "line2": "TESSELLATION VALIDATOR NODE",
          "clear": True,
        })
        self.install_upgrade = "installation"
        self.functions.print_paragraphs([
            [" NOTE ",2,"yellow,on_magenta"],
            ["Default options will be enclosed in",0,"magenta"], ["[] (brackets).",0,"yellow,bold"],
            ["If you want to use the value defined in the brackets, simply hit the",0,"magenta"], ["<enter>",0,"yellow","bold"],
            ["key to accept said value.",2,"magenta"],
            
            ["n",0,"yellow","bold"], ["stands for",0], [" no  ",0,"yellow,on_red"], ["",1],
            ["y",0,"yellow","bold"], ["stands for",0], [" yes ",0,"blue,on_green"], ["",2],
            
            ["IMPORTANT",0,"red","bold"],
            ["nodectl",0,"blue","bold"], ["was designed to run on a terminal session with a",0], ["black",0,"cyan","bold"],
            ["background setting. Default terminal emulators with a",0], ["white",0,"cyan","bold"], ["background may experience some 'hard to see' contrasts.",0],
            ["It is recommended to change the preferences on your terminal [of choice] to run with a",0], ["black",0,"cyan","bold"],
            ["background.",2],
        ])

        self.confirm_int_upg()
        
        # self.functions.print_clear_line()
        self.functions.print_header_title({
            "line1": "Installation Starting",
            "single_line": True,
            "show_titles": False,
            "newline": "both",
        })
        
        self.functions.print_paragraphs([
            ["For a new installation, the Node Operator can choose to build this Node based",0,"green"],
            ["on various Metagraph pre-defined configurations.",2,"green"],
            
            ["If the Metagraph this Node is being built to participate on is not part of this list, it is advised to",0],
            ["choose",0], ["mainnet",0,"red,on_yellow"], ["as the default to complete the installation.",2], 
            ["The MainNet configuration template will only be a placeholder to allow this Node to install all",0],
            ["required components, to ensure successful implementation of this utility.",0],
            
            ["If a pre-defined Metagraph listed above is not the ultimate role of this future Node,",0],
            ["following a successful installation, the next steps should be for you to refer to the Metagraph",0],
            ["Administrators of the Metagraph you are expected to finally connect with. The Administrator",0,],
            ["will offer instructions on how to obtain the required configuration file for said Metagraph.",2],
            ["Please key press number of a Metagraph configuration below:",2,"blue","bold"],
        ])
        
        self.install_upgrade_common({
            "env_provided": environment,
            "action": "install"
        })
        
        self.functions.print_header_title({
            "line1": "P12 Migration Check",
            "single_line": True,
            "show_titles": False,
            "newline": "both",
        })
        
        self.has_existing_p12 = self.functions.confirm_action({
            "yes_no_default": "n",
            "return_on": "y",
            "prompt": "Are you migrating an existing p12 private key to this Node?",
            "exit_if": False,
        })
        
        if self.has_existing_p12:        
            self.functions.print_paragraphs([
                ["",1], [" BEFORE WE BEGIN ",2,"grey,on_yellow"], 
                ["If",0,"cyan","bold,underline"], ["this Node will be using",0],
                ["an existing",0], ["p12 private key",0,"yellow","bold"], [", the installation should be exited and the",-1],
                ["existing",0,"yellow","bold"], ["p12 private key uploaded to a known secure local directory on this server.",0],
                ["Alternatively, you can simply pause here and upload the p12 private key file, and then continue.",2],
                
                ["Please see the Constellation Doc Hub Validator section for instructions on how to do this.",2,"magenta"],
                
                ["Later in the installation, the Node Operator will be given the opportunity to migrate over the existing p12 private key.",0],
                ["At the necessary time, a request for the",0], ["p12 name",0,"yellow","bold"], ["and",0], ["directory location",0,"yellow","bold"],
                ["will be given.",0], ["Once nodectl understands where the p12 file is located and necessary credentials, it will then be migrated by the installation to the proper location.",2]
            ])
            
            prompt_str = f"Exit now to upload existing p12?"
            self.functions.confirm_action({
                "yes_no_default": "n",
                "prompt_color": "red",
                "return_on": "n",
                "prompt": prompt_str,
                "exit_if": True,
            })

        print("")
        self.functions.print_header_title({
            "line1": "Update Distribution",
            "single_line": True,
            "show_titles": False,
            "newline": "both",
        })
        self.update_os()
        
        # self.functions.pull_remote_profiles()
        # self.functions.check_config_environment()
        
        self.installer = Installer({
            "ip_address": self.ip_address,
            "existing_p12": self.has_existing_p12,
            "environment_name": self.environment_requested,
            "functions": self.functions,
        })
        
        self.installer.install_process()
        self.functions.print_perftime(performance_start,"installation")


    def handle_exit(self,value):
        self.check_auto_restart("end")
        exit(value)
        
        
if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")            
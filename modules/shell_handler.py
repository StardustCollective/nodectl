import concurrent.futures
from sys import exit
import time

from datetime import datetime
from termcolor import colored, cprint
from concurrent.futures import ThreadPoolExecutor, wait as thread_wait
from os import geteuid, getgid, environ, system

from .auto_restart import AutoRestart
from .functions import Functions
from .upgrade import Upgrader
from .install import Installer
from .command_line import CLI
from .troubleshoot.errors import Error_codes
from .troubleshoot.logger import Logging

class ShellHandler:

    def __init__(self, config_obj, debug):

        try:
            self.log = Logging() # install exception
        except Exception as e:
            print(colored("Are you sure your are running with 'sudo'","red",attrs=["bold"]))
            print(colored("nodectl unrecoverable error","red",attrs=["bold"]))
            print(colored("nodectl may not be installed?","red"),colored("hint:","cyan"),"use sudo")
            exit(1)

        self.error_messages = Error_codes()
        self.functions = Functions(config_obj)
        
        self.install_flag = False
        self.restart_flag = False
        self.has_existing_p12 = False
        self.debug = debug
        self.correct_permissions = True
        self.auto_restart_enabled = False
        
        self.current_date = datetime.now().strftime("%Y-%m-%d")
        self.node_service = "" #empty
        self.packages = {}
        self.version_obj = {}
        
        self.get_auto_restart_pid()
        self.userid = geteuid()
        self.groupid = getgid()

        self.ip_address = self.functions.get_ext_ip()
        self.log.logger.info(f"obtain ip address: {self.ip_address}")
        

    def build_cli_obj(self,skip_check=False):
        build_cli = self.check_non_cli_command() if skip_check == False else True
        if build_cli:
            command_obj = {
                "caller": "shell_handler",
                "command": self.called_command,
                "profile": self.profile,  
                "command_list": self.argv,
                "ip_address": self.ip_address,
                "skip_services": self.skip_services,
                "version_obj": self.version_obj,
                "profile_names": self.profile_names,
                "config_obj": self.functions.config_obj
            }   
            cli = CLI(command_obj)
            cli.check_for_new_versions()
            return cli 
        return None
    
         
    def start_cli(self,argv):
        self.argv = argv
        self.check_error_argv()
        
        self.skip_services = True
        show_help = False
        return_value = 0
        
        version_cmd = ["-v","_v","version"]
        if argv[1] in version_cmd:
            self.functions.auto_restart = False
            self.show_version()
            exit(0)
            
        self.setup_profiles()
        self.check_auto_restart()
        self.check_skip_services()
        self.check_for_profile_requirements()

        if "all" in self.argv:
            self.check_all_profile()     

        cli = self.build_cli_obj()
        
        restart_commands = ["restart","slow_restart","restart_only","_sr","join"]
        service_change_commands = ["start","stop","leave"]
        status_commands = ["status","_s","quick_status","_qs"]
        node_id_commands = ["id","dag","nodeid"]
        upgrade_commands = ["upgrade_nodectl","upgrade_nodectl_testnet"]
        cv_commands = ["check_versions","_cv"]
        deprecated_clear_file_cmds = [
            "clear_uploads","_cul","_cls","clear_logs",
            "clear_snapshots","clear_backups",
            "reset_cache","_rc"
        ]
        ssh_commands = ["disable_root_ssh","enable_root_ssh","change_ssh_port"]
        config_list = ["view_config","validate_config","_vc", "_val"]
        clean_files_list = ["clean_snapshots","_cs","clean_files","_cf"]
        
        if self.called_command != "service_restart":
            self.functions.print_clear_line()
        
        if self.called_command in status_commands:
            cli.show_system_status({
                "rebuild": False,
                "wait": False,
                "print_title": True,
                "-p": self.argv[1],
                "called": self.called_command
            })
            
        elif self.called_command in service_change_commands:
            cli.set_profile(self.argv[1])
            if not show_help:            
                if self.called_command == "start":
                    cli.cli_start({
                        "argv_list": self.argv,
                    })
                elif self.called_command == "stop":
                    cli.cli_stop({
                        "show_timer": False,
                        "upgrade_install": False,
                        "argv_list": self.argv,
                        "check_for_leave": True,
                    })
                elif self.called_command == "leave":
                    cli.cli_leave({
                        "secs": 30,
                        "reboot_flag": False,
                        "skip_msg": False,
                        "argv_list": self.argv
                    })
            else:  
                self.functions.print_help({
                    "usage_only": True,
                    "hint": "profile"
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
                    return_value = cli.print_deprecated({
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
                    cli.cli_join({
                        "skip_msg": False,
                        "wait": True,
                        "argv_list": self.argv
                    })
                    restart = False

            if restart:
                cli.cli_restart({
                    "secs": secs,
                    "restart_type": self.called_command,
                    "slow_flag": slow_flag,
                    "cli_join_cmd": cli_join_cmd,
                    "cli_leave_cmd": False,
                    "argv_list": self.argv
                })

        elif self.called_command == "list":
            cli.show_list(self.argv)  
        elif self.called_command == "show_current_rewards" or self.called_command == "_scr":
            cli.show_current_rewards(self.argv)  
        elif self.called_command == "find":
            cli.cli_find(self.argv)
        elif self.called_command == "peers":
            cli.show_peers(self.argv)
        elif self.called_command == "whoami":
            cli.show_ip(self.argv)
        elif self.called_command == "nodeid2dag":
            cli.cli_nodeid2dag(self.argv)
        elif self.called_command == "show_node_states" or self.called_command == "_sns":
            cli.show_node_states(self.argv)
        elif self.called_command == "passwd12":
            return_value = cli.passwd12(self.argv)
        elif self.called_command == "reboot":
            cli.cli_reboot(self.argv)
        elif self.called_command in node_id_commands:
            command = "dag" if self.called_command == "dag" else "nodeid"
            cli.cli_grab_id({
                "command": command,
                "argv_list": self.argv
            })
        elif self.called_command in upgrade_commands:
            command = "mainnet"
            if "testnet" in self.called_command:
                command = "testnet"
            return_value = cli.upgrade_nodectl({
                "command": command,
                "help": self.argv[0]
            })
        elif self.called_command in ssh_commands:
            cli.ssh_configure({
                "command": self.called_command,
                "argv_list": self.argv   
            })
        elif self.called_command == "help" or self.called_command == "_h":
                self.functions.print_help({
                    "usage_only": False,
                })
        elif self.called_command in clean_files_list:
            command_obj = {"argv_list": self.argv, "action": "normal"}
            if self.called_command == "clean_snapshots" or self.called_command == "_cs":
                command_obj["action"] = "snapshots"
            cli.clean_files(command_obj)
            
        elif self.called_command in deprecated_clear_file_cmds:
            new_cmd = "clean_snapshots" if self.called_command == "reset_cache" or self.called_command == "_rc" else "clean_files"
            return_value = cli.print_deprecated({
                "command": self.called_command,
                "version": self.functions.node_nodectl_version,
                "new_command": new_cmd
            })
            
        elif self.called_command == "check_seedlist" or self.called_command == "_csl":
            return_value = cli.check_seed_list(self.argv)
        elif self.called_command == "update_seedlist" or self.called_command == "_usl":
            return_value = cli.update_seedlist(self.argv)
        elif self.called_command == "export_private_key": 
            cli.export_private_key(self.argv)
        elif self.called_command == "check_source_connection" or self.called_command == "_csc":
            return_value = cli.check_source_connection(self.argv)
        elif self.called_command == "check_connection" or self.called_command == "_cc":
            cli.check_connection(self.argv)
        elif self.called_command == "send_logs" or self.called_command == "_sl":
            cli.prepare_and_send_logs(self.argv)
        elif self.called_command == "check_seedlist_participation" or self.called_command == "_cslp":
            cli.show_seedlist_participation(self.argv)
        elif self.called_command in cv_commands:
            cli.check_versions(self.argv)
        elif "auto_" in self.called_command:
            if self.called_command == "auto_upgrade":
                if "help" not in self.argv:
                    self.argv.append("help")
                self.called_command = "auto_restart"
            if "help" in self.argv:
                self.functions.print_help({
                    "usage_only": True,
                    "extended": "auto_restart"
                })
            else:
                self.auto_restart_handler(self.argv[0],True,True)
        elif self.called_command == "service_restart":
           if self.argv[0] != "enable":
               self.log.logger.error(f"start cli --> invalid request [{self.argv[0]}]")
               exit(0)
           self.auto_restart_handler("service_start",True)
        elif self.called_command == "log" or self.called_command == "logs":
            return_value = cli.show_logs(self.argv)
        elif self.called_command == "install":
            self.install(self.argv)
        elif self.called_command == "upgrade":
            self.upgrade_node(self.argv)
        elif self.called_command == "upgrade_path" or self.called_command == "_up":
            cli.check_nodectl_upgrade_path({
                "called_command": self.called_command,
                "argv_list": self.argv
            })
        elif self.called_command == "refresh_binaries" or self.called_command == "_rtb":
            cli.download_tess_binaries(self.argv)
        elif self.called_command == "health":
            cli.show_health(self.argv)
        elif self.called_command == "sec":
            cli.show_security(self.argv)
        elif self.called_command == "price" or self.called_command == "prices":
            cli.show_prices(self.argv)
        elif self.called_command == "market" or self.called_command == "markets":
            return_value = cli.show_markets(self.argv)
        elif self.called_command in config_list:
            self.functions.print_help({
                "usage_only": True,
                "nodectl_version_only": True,
                "extended": self.called_command,
            })
        else:
            skip = True if self.called_command == "main_error" else False
            self.functions.print_help({
                "usage_only": True,
                "nodectl_version_only": skip,
                "hint": "unknown"
            })
        if show_help:
            self.functions.print_help({
                "usage_only": True,
                "hint": False
            })
            
        self.handle_exit(return_value)
        
        
    # CHECK METHODS
    # =============        
    def check_error_argv(self):
        # error check first
        self.called_cmds = []
        self.help_requested = False
                
        try:
            self.called_command = self.argv[1]
        except:
            self.called_command = "help"
            return

        if "help" in self.argv:
            self.help_requested = True
        
        max = len(self.argv) if len(self.argv) > 7 else 8    
        for n in range(2,max):  # allow argv[2] - argv[7]
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
            
        if self.called_command != "install":    
            if self.functions.config_obj["auto_restart"]["enable"]:
                self.auto_restart_enabled = True
            
        if self.called_command in kill_auto_restart_commands:
            self.log.logger.warn(f"cli request {self.called_command} received. DISABLING auto_restart if enabled")
            self.auto_restart_handler("disable",True)
                

    def check_skip_services(self):
        # do we want to skip loading the node service obj?
        dont_skip_service_list = [
            "status","_s","quick_status","_qs","reboot",
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
            "upgrade","install","auto_restart","service_restart"
        ]
        if self.called_command in non_cli_commands:
            return False
        return True
    

    def check_system_permissions(self,force=False):
        # grab execution user
        self.log.logger.info("testing permissions")
        progress = {
            "status": "running",
            "text_start": "Check permissions & versioning",
        }
        self.functions.print_cmd_status(progress) 
        time.sleep(.8)
        
        current = self.version_obj["node_nodectl_version"]
        remote = self.version_obj["latest_nodectl_version"]
        
        if self.functions.is_new_version(current,remote):
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
                ["This is not a current version of",0,"red","bold"], ["nodectl",0,"blue","bold"], [".",-1,"red","bold"],["",1],
                ["Issue:",0,"magenta"], ["sudo nodectl upgrade_nodectl",1,"green"],
            ])
                
            if force:
                self.log.logger.warn(f"an attempt to {self.install_upgrade} with an non-interactive mode detected {current}")  
                self.functions.print_paragraphs([
                    [" WARNING ",0,"red,on_yellow"], [f"non-interactive mode was detected, this {self.install_upgrade} will continue at the Node Operator's",0,"yellow"],
                    ["own risk and decision.",1,"yellow"]
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
             
        self.functions.check_sudo()
        self.functions.print_cmd_status({
            **progress,
            "status": "complete",
            "newline": True
        })
        
        
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
        need_profile = False
        called_profile = False
        
        if self.help_requested:
            return

        if "-p" in self.argv:
            called_profile = self.argv[self.argv.index("-p")+1]
            self.functions.check_valid_profile(called_profile)
                    
        need_profile_list = [
            "find","quick_check","logs",
            "start","stop","restart",
            "slow_restart","_sr","restart_only",
            "peers","check_source_connection","_csc",
            "check_connection","_cc",
            "send_logs","_sl",
            "nodeid","id","dag","export_private_key",
            "check_seedlist","_csl","update_seedlist","_usl",
        ]                
        
        if self.called_command in need_profile_list:
            need_profile = True
            if "help" in self.argv:
                pass
            elif len(self.argv) == 0 or ("-p" not in self.argv or called_profile == "empty"):
                self.functions.print_help({
                    "usage_only": True,
                    "hint": "profile"
                })
                
        if need_profile and self.called_command != "empty":
            if "-p" in self.argv:
                self.profile = called_profile
     
    # =============  
    
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

        help_only_list = [
            "main_error","validate_config","install",
            "view_config","_vc","_val"
        ]
        if self.called_command in help_only_list:
            self.profile = None
            self.profile_names = None
            return
        
        self.profile_names = self.functions.pull_profile({
            "req": "list",
            "profile": "empty",
        })  
        self.profile = self.functions.default_profile  # default to first layer0 found
        

    def show_version(self):
        self.log.logger.info(f"show version check requested")
        nodectl_version = self.functions.get_version({"which":"nodectl"})
        self.functions.print_clear_line()
        parts = self.functions.cleaner(nodectl_version["node_nodectl_version"],"remove_char","v")
        parts = parts.split(".")
        
        print_out_list = [
            {
                "header_elements" : {
                    "VERSION": nodectl_version["node_nodectl_version"],
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
            
                    
    def install_upgrade_common(self,action,force=False):
        self.version_obj = self.functions.get_version({
            "which": "all",
            "action": action,
        })
        self.functions.print_clear_line()
        self.check_system_permissions(force)
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
        warning = False  
        if action == "service_start":
            self.log.logger.info("auto_restart - restart session threader - invoked.")

            with ThreadPoolExecutor() as executor:
                thread_list = []
                # self.profile_names = ["dag-l0"]  # used for debugging purposes
                for n, profile in enumerate(self.profile_names):
                    self.log.logger.info(f"auto_restart - restart threader -  invoked session threads for [{profile}]")
                    allow_upgrade = True if n < 1 else False
                    time.sleep(2)
                    thread_list.append(
                        executor.submit(
                            AutoRestart,
                            profile,
                            self.functions.config_obj,
                            allow_upgrade,
                        )
                    )
                thread_wait(thread_list,timeout=None,return_when=concurrent.futures.FIRST_EXCEPTION)
                self.log.logger.critical("shell auto restart handler --> thread creation returned with exception - service will be restarted immediately")
                # system(f'sudo systemctl restart node_restart@"enable" > /dev/null 2>&1')
                
        if action == "disable":
            if not self.auto_restart_pid:
                self.auto_restart_pid = "disabled"
            if cli:
                end_status = "not running"
                end_color = "blue"
                if self.auto_restart_pid != "disabled":
                    end_status = "complete"
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
                system(f'sudo systemctl stop node_restart@"enable" > /dev/null 2>&1')
                self.functions.print_cmd_status({
                    **progress,
                    "status": end_status,
                    "status_color": end_color,
                    "newline": True,
                })
                
                if self.auto_restart_pid != "disabled":
                    verb = "of next" if manual else "of"
                    if self.auto_restart_enabled:
                        cprint(f"  Auto Restart will reengage at completion {verb} requested task","green")
                    else:
                        cprint("  This will need to restarted manually...","red")
                    self.log.logger.debug(f"auto_restart process pid: [{self.auto_restart_pid}] killed") 
                    self.auto_restart_pid = False # reset 

                return
        
        if action == "check_pid" or action == "current_pid" or action =="status":
            self.functions.print_clear_line()
            self.functions.print_cmd_status({
                "text_start": "node",
                "brackets": "auto_restart",
                "text_end": "service found pid",
                "status": self.auto_restart_pid,
                "status_color": "magenta",
                "newline": True,
            })
            return
        
        if action != "enable":  # change back to action != "empty" when enabled in prod
            cprint("  unknown auto_restart parameter detected, exiting","red")
            return

        keys = list(self.functions.config_obj["profiles"].keys())
        keys.append("global_p12")
        for profile in keys:
            if profile == "global_p12":
                if self.functions.config_obj[profile]["passphrase"] == "None":
                    warning = True
                    break
            elif self.functions.config_obj["profiles"][profile]["p12"]["passphrase"] == "None":
                warning = True
                break
            
        if warning:
            self.functions.print_paragraphs([
                [" ERROR ",0,"yellow,on_red"], ["Auto Restart",0,"red","underline"], 
                ["cannot be manually enabled if the Node's passphrases are not set in the configuration.",0,"red"],
                ["nodectl",0,"blue","bold"],["will not have the ability to authenticate to the HyperGraph in an automated fashion.",2,"red"],
                ["Action cancelled",1,"yellow"],
            ])
            exit(1)
                        
        if self.auto_restart_pid and self.auto_restart_pid != "disabled":
            if self.auto_restart_enabled:
                self.functions.print_paragraphs([
                    ["",1], ["Node restart service does not need to be restarted because pid [",0,"green"],
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
                "extended": self.called_command
            })

        self.log.logger.debug(f"{self.called_command} request started") 
        performance_start = time.perf_counter()  # keep track of how long
           
        self.functions.print_header_title({
          "line1": f"{self.called_command.upper()} REQUEST",
          "line2": "TESSELLATION VALIDATOR NODE",
          "clear": True,
        })
        
        self.install_upgrade = "upgrade"
        if "-ni" not in argv_list:
            self.confirm_int_upg()

        self.functions.print_header_title({
            "line1": "Handle OS System Upgrades",
            "single_line": True,
            "newline": "both",
        })
        
        force = True if "-f" in argv_list else False
        self.install_upgrade_common("normal",force)
        self.upgrader = Upgrader({
            "ip_address": self.ip_address,
            "config_obj": self.functions.config_obj,
            "version_obj": self.version_obj,
            "called_command": self.called_command,
            "argv_list": argv_list
        }) 
        self.update_os()
        self.upgrader.upgrade_process()

        self.functions.print_perftime(performance_start,self.install_upgrade)
        
    
    def install(self,argv_list):
        if "help" in argv_list:
            self.functions.print_help({
                "extended": "install"
            })
            
        self.log.logger.debug("installation request started")
        
        performance_start = time.perf_counter()  # keep track of how long
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
            
            ["n",0,"yellow","bold"], ["stands for",0], [" no ",0,"yellow,on_red"], ["",1],
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
        
        self.install_upgrade_common("install")
        
        self.has_existing_p12 = self.functions.confirm_action({
            "yes_no_default": "n",
            "return_on": "y",
            "prompt": "Are you migrating over an existing p12 private key?",
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
            
        self.update_os()
        
        self.functions.check_config_testnet_mainnet()
        self.installer = Installer({
            "ip_address": self.ip_address,
            "existing_p12": self.has_existing_p12,
            "network_name": self.functions.network_name,
            "version_obj": self.version_obj
        },self.debug)
        
        self.installer.install_process()
        self.functions.print_perftime(performance_start,"installation")


    def handle_exit(self,value):
        self.check_auto_restart("end")
        exit(value)
        
        
if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")            
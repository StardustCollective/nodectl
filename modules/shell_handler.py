import time
import json
import math
from sys import exit
from datetime import datetime
from termcolor import colored, cprint
from concurrent.futures import ThreadPoolExecutor
from os import geteuid, getgid, environ, system, walk, path
from shutil import copy2
from types import SimpleNamespace
from pathlib import Path
from copy import deepcopy

from modules.functions import Functions
from modules.upgrade import Upgrader
from modules.install import Installer
from modules.command_line import CLI
from modules.troubleshoot.errors import Error_codes
from modules.troubleshoot.logger import Logging
from modules.config.versioning import Versioning
from modules.config.valid_commands import pull_valid_command
from modules.cn_requests import CnRequests

class ShellHandler:

    def __init__(self, command_obj, debug):
        try:
            self.log = Logging("init") # install exception
        except:
            print(colored("Are you sure your are running with 'sudo'","red",attrs=["bold"]))
            print(colored("nodectl unrecoverable error","red",attrs=["bold"]))
            print(colored("nodectl may not be installed?","red"),colored("hint:","cyan"),"use sudo")
            exit("  sudo rights error")

        self._setup_logging_key(command_obj)

        self.functions = Functions()
        self.functions.set_parameters()
        self.functions.set_self_value("config_obj",self.config_obj)
        self.functions.set_self_value("log",self.log)
        
        self.error_messages = Error_codes(self.functions)
        self.error_messages.functions = self.functions
        self.functions.error_messages = self.error_messages
        
        self._set_versioning_obj(command_obj)
        # try:
        #     self.version_class_obj = command_obj.versioning
        # except:
        #     self.version_class_obj = command_obj.get("versioning",False)

        self.restart_flag = False
        self.has_existing_p12 = False
        self.debug = debug
        self.correct_permissions = True
        self.auto_restart_enabled = False
        self.auto_restart_quiet = False
        self.environment_requested = None
        self.called_command = None
        self.node_file_cache_obj = None

        self.non_cli_commands = [
            "install",
            "auto_restart","service_restart",
            "uvos","help",
        ]

        self.service_commands = [
            "auto_restart","service_restart",
            "uvos"
        ]
        
        try: # install exception
            self.mobile = True if "mobile" in command_obj.argv_list else False
        except:
            self.mobile = False

        self.current_date = datetime.now().strftime("%Y-%m-%d")
        self.node_service = "" #empty
        self.packages = {}
        
        if self.called_command is not None:
            self.auto_restart_handler("get_pid")
            
        self.userid = geteuid()
        self.groupid = getgid()

        self.ip_address = self.functions.get_ext_ip()
        

    def _setup_logging_key(self,command_obj):
        try:
            self.config_obj = command_obj.config_obj
        except:
            self.config_obj = command_obj["config_obj"]

        try:
            self.log_key = self.config_obj["global_elements"]["log_key"]
        except:
            try:
                self.log_key = command_obj["log_key"]
            except:
                self.log_key = "main"
                
        self.log = self.log.logger[self.log_key]


    def _set_versioning_obj(self, command_obj):
        if hasattr(command_obj, "versioning"):
            self.version_class_obj = command_obj.versioning
        else:
            self.version_class_obj = command_obj.get("versioning", False)
            

    def _set_cn_requests(self):
        self.set_function_value("called_command",self.called_command)
        
        self.cn_requests = CnRequests(self.set_self_value,self.get_self_value)
        self.cn_requests.set_parameters()
        
        # router.handle_direct_node_cache_request()
        if self.cn_requests.get_is_cache_needed():
            try:
                if self.cli.node_service:
                    self.cli.node_service.set_self_value("cn_requests",self.cn_requests)
            except: 
                pass
            self.cn_requests.set_self_value("node_file_cache_obj",self.node_file_cache_obj)
            self.cn_requests.handle_edge_point_cache()
            
           
    def _set_cli_obj(self, skip_check=False):
        build_cli = self.check_non_cli_command() if skip_check == False else True
        self.invalid_version = False
        cli = False
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
                "valid_commands": self.valid_commands,
            } 

            cli = CLI(self.log)
            cli.set_parameters(command_obj)
            cli.version_class_obj = self.version_class_obj

            try:
                cli.node_service.version_class_obj = self.version_class_obj
            except:
                self._print_log_msg("debug","shell --> skipped node service versioning, not needed.")

            # cli.check_for_new_versions({
            #     "caller": self.called_command
            # })
            if cli.skip_warning_messages:
                cli.invalid_version = False
            return cli 

        if self.called_command != "install":
            if self.config_obj["global_elements"]["developer_mode"] or "--skip-warning-messages" in self.argv:
                cli = {
                    "skip_warning_messages": True,
                    "invalid_version": False,
                }
                cli = SimpleNamespace(**cli)
                
        return cli
    
    
    def get_self_value(self, name, default=False):
        return getattr(self, name, default)
    
    
    def set_self_value(self, name, value):
        setattr(self, name, value)
        
        
    def set_function_value(self, name, value):
        setattr(self.functions, name, value)
                     
                     
    def start_cli(self,argv,cli_iterative=False):
        from modules.nodectl_router import NodeCtlRouter

        self.argv = argv
        self.check_error_argv(argv)
        
        self.skip_services = True
        return_value = 0

        self._print_log_msg("info",f"shell_handler -> start_cli -> obtain ip address: {self.ip_address}")
                
        router = NodeCtlRouter(
            self, self.get_self_value, self.set_self_value,
            self.set_function_value,
        )
        
        router.set_parameters()
        self.check_valid_command()
        router.set_self_value("called_command",self.called_command)
        
        while True:
            if router.process_main_error(): exit(0)
            if router.handle_version(): exit(0)
            if router.handle_verify_specs(): exit(0)
            
            return_caller = router.handle_verify_nodectl() 
            if isinstance(return_caller,bool) and return_caller: exit(0)
            if return_caller: return return_caller

            if router.handle_restore_config(): exit(0)

            # self.set_version_obj_class()
            self.check_can_use_offline()
            self.setup_profiles()
            self.check_auto_restart()
            self.check_skip_services()
            # self.check_for_static_peer()
            # self.handle_versioning()
            self.check_fernet_rotation()
            self.check_diskspace()
            self.check_for_profile_requirements()

            if not hasattr(self, "cli"):
                self.cli = self._set_cli_obj()
                if self.called_command in self.service_commands:
                    self.cli.set_self_value("auto_restart", True)
                router.set_self_value("cli",self.cli)
                
            router.process_all_profiles()

            router.handle_invalid_version()

            self._set_node_obj() # needs cli object
            
            self._set_cn_requests()

            router.set_cli_cn_requests()
            router.print_ux_clear_line()
            
            router.handle_console_mobile()
            router.handle_status_command()
            router.handle_start_stop_leave()
            router.handle_restart_command()
            
            router.handle_download_commands()
            router.handle_peers_command()
            router.handle_find_command()
            router.handle_list_command()
            router.handle_delegated_staking()
            router.handle_delegated_sign()
            router.handle_show_current_rewards()
            router.handle_whoami()
            router.handle_remote_access()
            router.handle_nodeid2dag()
            router.handle_show_node_states()
            router.handle_reboot()
            router.handle_dag()
            router.handle_ssh_configure()
            router.handle_clear_files()
            router.handle_check_consensus()
            router.handle_minority_fork()
            router.handle_check_tcp_ports()
            router.handle_config_backup()
            router.handle_create_p12()
            router.handle_show_distro()
            router.handle_send_logs()
            router.handle_display_snaphost_chain()
            router.handle_last_snapshot()
            router.handle_seedlist_participation()
            router.handle_download_status()
            router.handle_check_versions()
            router.handle_auto_commands()
            router.handle_service_commands()
            router.handle_api_service()
            router.handle_installer()
            router.handle_upgrader()
            router.handle_upgrade_path()
            router.handle_upgrade_vps()
            router.handle_health()
            router.handle_show_profile_issues()
            router.handle_starchiver()
            router.hanle_user_tests()
            router.handle_rotate_keys()
            router.handle_prepare_file_download()
            router.handle_show_service_logs()
            router.handle_show_service_status()
            router.handle_prepare_file_download()

            router.handle_show_cpu_memory()
            router.handle_sync_time()
            router.handle_update_version_obj()
            router.handle_security()
            router.handle_price()
            router.handle_show_dip_error()
            router.handle_show_p12_details()
            router.handle_ipv6()
            router.handle_data_migration()
            router.handle_getting_started()
            router.handle_test_only()
            
            cli_iterative = router.handle_p12_export(cli_iterative)
            return_value, cli_iterative = router.handle_nodectl_upgrade(return_value, cli_iterative)
            
            return_value = router.handle_show_node_proofs(return_value)
            return_value = router.handle_check_seedlist(return_value)
            return_value = router.handle_passwd(return_value)
            return_value = router.handle_source_connection(return_value)
            return_value = router.handle_show_node_proofs(return_value)
            return_value = router.handle_logs(return_value)    
            return_value = router.handle_markets(return_value)

            # must be at end
            router.handle_help()
            router.handle_help_only()
            router.handle_config_list()
        
            self.handle_exit(return_value)
            
            if self.mobile: 
                if cli_iterative in ["mobile_revision", "mobile_success"]:
                    self.called_command = "mobile"
                else:
                    self.called_command = cli_iterative

                if cli_iterative != "mobile_revision":
                    self.functions.print_any_key({"newline": "top"})
                    system("clear")
            else:
                break
        
        
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
                self.called_cmds.append(self.argv[n].replace("_","-"))
                
        self.argv = self.called_cmds
        self.called_command = self.called_command.replace("-","_")
            

    def check_auto_restart(self,action="start"):
        # do we need to make sure auto_restart is turned off?

        skip_enable_restart_commands = ["leave","stop","uninstall"]
        if action == "end" or action == "mobile":
            if self.auto_restart_enabled and self.called_command != "auto_restart":
                if self.called_command in skip_enable_restart_commands:
                    if self.called_command != "uninstall":
                        self.functions.print_paragraphs([
                            [" WARNING ",0,"yellow,on_red"], ["The",0,"red"],
                            [self.called_command,0,"yellow"], 
                            ["command will not re-engage the auto_restart feature of nodectl.",1,"red"],
                        ])
                else:
                    self.auto_restart_handler("enable",True)
                if self.mobile: return
                exit(0) 
                
        kill_auto_restart_commands = [
            "restart_only","slow_restart","-sr","_sr",
            "leave","start","stop","restart","join", 
            "upgrade_nodectl","upgrade","execute_starchiver",
            "display_snapshot_chain","uninstall",
        ]
            
        print_quiet_auto_restart = [
            "check_consensus","check_tcp_ports","logs",
        ]

        if self.called_command in print_quiet_auto_restart:
            self.auto_restart_quiet = True

        if self.called_command not in ["help","install","revision"]:
            try:    
                if self.functions.config_obj["global_auto_restart"]["auto_restart"]:
                    self.auto_restart_enabled = True
            except:
                pass # skip
            
        if self.called_command in kill_auto_restart_commands:
            self._print_log_msg("warning",f"cli request {self.called_command} received. DISABLING auto_restart if enabled")
            self.auto_restart_handler("disable",True)
                

    def check_skip_services(self):
        # do we want to skip loading the node service obj?
        dont_skip_service_list = [
            "status","_s","quick_status","_qs","reboot","uptime","revision",
            "start","stop","restart","slow_restart","_sr","mobile","console",
            "restart_only","auto_restart","service_restart",
            "join","id", "nodeid", "dag", "passwd12","export_private_key",
            "find","leave","peers","check_source_connection","_csc",
            "check_connection","_cc","refresh_binaries","_rtb","upgrade",
            "update_seedlist","_usl","upgrade_nodectl","upgrade_nodectl_testnet",
            "_cache_update_request",
        ]
        
        if self.called_command in dont_skip_service_list:
            self.skip_services = False
                

    def check_diskspace(self):
        verbose = True
        warning_threshold = 84
        main_threshold = 94
        size_str = self.functions.check_dev_device().strip()
        size = int(size_str.split(" ")[0].replace("%",""))

        if "_restart" in self.called_command:
            verbose = False        
        if size > main_threshold:
            self._print_log_msg("critical",f"shell_handler -> disk check -> {size_str}")
            if verbose:
                self.functions.print_paragraphs([
                    [" CRITICAL ",0,"yellow,on_red"], ["Disk Space:",0,"magenta"],
                    [size_str,1,"red"]
                ])
        elif size > warning_threshold:
            self._print_log_msg("warning",f"shell_handler -> disk check -> {size_str}")
            if verbose:
                self.functions.print_paragraphs([
                    [" WARNING ",0,"red,on_yellow"], ["Disk Space:",0,"yellow"],
                    [size_str,1,"magenta"]
                ])
                

    def check_fernet_rotation(self):
        verbose = True
        if self.called_command == "install" or not self.config_obj.get("global_p12",False):
            return
        if not self.config_obj["global_p12"]["encryption"]: 
            return
        if "_restart" in self.called_command:
            verbose = False
        
        warning_threshold = 45
        main_threshold = 90

        mod_time = path.getmtime(self.config_obj["global_p12"]["ekf_path"])
        age = self.functions.get_date_time({
            "action": "get_elapsed",
            "old_time": datetime.fromtimestamp(mod_time)
        })

        if age.days > main_threshold:
            self._print_log_msg("critical",f"shell_handler -> p12 encryption key rotation check -> age [{age}]")
            if verbose:
                self.functions.print_paragraphs([
                    [" IMPORTANT ",0,"yellow,on_red"], 
                    ["P12 encryption key rotation suggested.",1,"magenta"],
            ])
        elif age.days > warning_threshold:
            self._print_log_msg("warning",f"shell_handler -> p12 encryption key rotation check -> age [{age}]")
            if verbose:
                self.functions.print_paragraphs([
                    [" WARNING ",0,"red,on_yellow"], 
                    ["Consider P12 passphrase encryption key rotation soon.",1,"magenta"],
                ])


    def check_all_profile(self):
        # do we want to skip loading the node service obj?
        all_profile_allow_list = [
            "restart","restart_only","slow_restart","-sr","join","status",
            "show_profile_issues","console","mobile",
        ]
        if self.called_command in all_profile_allow_list:
            return
        self.called_command = "help"  # otherwise force help screen
                

    def check_non_cli_command(self):
        # if self.called_command in non_cli_commands:
        #     return False
        return True
    

    def check_developer_only_commands(self):
        if self.config_obj.get("global_elements",False).get("developer_mode",False): return   

        develop_commands = ["test_only"]
        if self.called_command in develop_commands:
            self.called_command = "help_only"


    def check_valid_command(self):
        cmds = pull_valid_command()
        self.valid_commands = cmds[0]
        valid_short_cuts = cmds[1]
        service_cmds = cmds[2]
        removed_cmds = cmds[3]
        temp_disabled = cmds[4]
        special_disabled = cmds[5]
        duplicate_count = cmds[6]

        do_exit = False
        print_temp_disable = False
        
        command_count = len(self.valid_commands)-duplicate_count
        self._print_log_msg("debug",f"nodectl feature count [{command_count}]")
        self.functions.valid_commands = self.valid_commands 
        
        all_command_check = self.valid_commands+valid_short_cuts+service_cmds+removed_cmds

        if self.called_command in temp_disabled or self.called_command in special_disabled:
            print_temp_disable = True
        if self.called_command == "whoami" and "-id" in self.argv:
            print_temp_disable = True
            
        if print_temp_disable:
            self.functions.print_paragraphs([
                [" IMPORTANT ",1,"yellow,on_red"], 
                [f"nodectl:",0], [self.called_command,2,"yellow"],
                [f"The {self.called_command} command is temporarily disabled due to recent refactoring.",0,"magenta"],
                ["We plan to re-enable this feature in an upcoming release. We apologize for any inconvenience and appreciate your patience.",2,"magenta"],
            ])
            do_exit = True
        
        if self.called_command in special_disabled:
            self.functions.print_paragraphs([
                ["Team Leads and/or Administrators will provide specific instructions on how to implement this command when the need",0,"magenta"],
                ["to utilize it arises, given its important nature.",2,"magenta"],
            ])
            do_exit = True
        
        if do_exit:
            exit(0)    
                    
        if self.called_command not in all_command_check:
            self.called_command = "help_only"
        

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
        self._print_log_msg("debug",f"checking profile requirements | command [{self.called_command}]") 
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
            "update_seedlist","_usl",
            "upgrade_path","_up","install",
            "check_minority_fork","_cmf",
        ]

        need_profile_list = [
            "find","quick_check","logs",
            "start","stop","restart","leave",
            "slow_restart","_sr","restart_only",
            "peers","check_source_connection","_csc",
            "check_connection","_cc",
            "send_logs","_sl","show_node_proofs","_snp",
            "nodeid","id","dag","export_private_key",
            "check_seedlist","_csl","show_profile_issues",
            "show_service_log","_ssl","download_status","_ds",
            "show_dip_error","_sde","check_consensus","_con",
            "check_minority_fork","_cmf","node_last_snapshot",
            "display_snapshot_chain", "show_p12_details",
        ]  

        option_exceptions = [
            ("nodeid","--file"),
        ]              

        if "-p" in self.argv:
            called_profile = self.argv[self.argv.index("-p")+1]
            self.functions.check_valid_profile(called_profile)
            if self.called_command not in need_profile_list: return
        
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
        
        for t in option_exceptions:
            if t[0] == self.called_command:
                if t[1] in self.argv:
                    need_profile, profile_hint = False, False

        if env_hint and profile_hint and either_or_hint:
            send_to_help_method("profile_env")
        elif profile_hint and not either_or_hint:
            self.profile = self.functions.profile_names[0]
            if len(self.functions.profile_names) > 1:
                menu_action = "profile"
                if self.called_command in ["_sl","send_logs"]:
                    menu_action = "send_logs"
                self.profile = self.functions.print_profile_env_menu({"p_type": menu_action})
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
                
            for n in range(0,2):
                try:
                    _ = self.functions.environment_names # network offline issue
                except:
                    if n > 0:
                        self.error_messages.error_code_messages({
                            "error_code": "sh-688",
                            "line_code": "system_error",
                            "extra": self.called_command,
                        })
                    self._print_log_msg("error",f"shell handler -> check_for_profile_requirements -> unable to obtain environment names.")
                    self.functions.set_environment_names()

            if len(self.functions.environment_names) > 1 or len(self.functions.environment_names) < 1:
                self.environment_requested = self.functions.print_profile_env_menu({"p_type": "environment"})
            else:
                self.environment_requested = self.functions.environment_names[0] # only one env found
                
            self.argv.extend(["-e",self.environment_requested])
            need_profile = False  
                      
        if need_profile and self.called_command != "empty":
           if "-p" in self.argv: self.profile = called_profile

        self.check_developer_only_commands()
     

    def check_can_use_offline(self):
        cannot_use_offline = [
            "upgrade","restart","join",
        ]
        if self.called_command in cannot_use_offline:
            if self.called_command == "upgrade" and "--nodectl-only" in self.argv: 
                return # exception
            self.config_obj["global_elements"]["use_offline"] = False


    def check_for_static_peer(self):
        # are we avoiding the load balancer?
        error_found = False
        # static_peer = False if not "--peer" in self.argv else self.argv[self.argv.index("--peer")+1]
        static_peer = self.functions.set_argv(self.argv, "--peer", False)
        # static_peer_port = False if not "--port" in self.argv else int(self.argv[self.argv.index("--port")+1])
        static_peer_port = self.functions.set_argv(self.argv,"--port", False)

        if not static_peer: 
            return
        
        if static_peer == "self":
            if self.called_command == "join" or self.called_command == "restart":
                error_found = True
                error_code = "sh-692"
                extra = self.called_command
                verb = "to" if self.called_command == "join" else "via"
                extra2 = f"You will not be able to {self.called_command} your node {verb} itself."
            static_peer = self.functions.get_ext_ip()
            static_peer_port = self.config_obj[self.profile]["public_port"]
        else:
            self.functions.is_valid_address("ip_address",False,static_peer)

        if self.profile == "all":
            error_found = True
            error_code = "sh-704"
            extra = "-p all"
            extra2 = "You must specify valid profile(s) individually on the command line. "
            extra2 += f"Please see the help file: 'sudo nodectl {self.called_command} help'"

        if error_found:
            self.error_messages.error_code_messages({
                "error_code": error_code,
                "line_code": "invalid_option",
                "extra": extra,
                "extra2": extra2,
            })

        if not static_peer_port:
            try:
                static_peer_port = self.functions.get_info_from_edge_point({
                    "profile": self.profile,
                    "caller": "shell",
                    "specific_ip": static_peer,
                })
                static_peer_port = static_peer_port["publicPort"]
            except:
                while True:
                    self.functions.print_paragraphs([
                        ["",1],["Static peer request detected:",1],
                        ["Unable to determine the public port to access API for the peer.",1,"red"],
                        ["peer:",0],[f"{static_peer}",1,"yellow"],
                    ])
                    static_peer_port = input(colored(f"  Please enter public API port [{colored('9000','yellow')}{colored(']: ','magenta')}","magenta"))
                    if static_peer_port == "" or static_peer_port == None:
                        static_peer_port = 9000
                    try:
                        static_peer_port = int(static_peer_port)
                    except:
                        pass
                    else:
                        if static_peer_port > 1023 and static_peer_port < 65536:
                            break
                    self._print_log_msg("error",f"shell handler -> invalid static peer port entered [{static_peer_port}]")

        self.config_obj[self.profile]["edge_point"] = static_peer
        self.config_obj[self.profile]["edge_point_tcp_port"] = static_peer_port
        self.config_obj[self.profile]["static_peer"] = True

        self.functions.auto_restart = False
        self.functions.event = False
        self.functions.ip_address = self.functions.get_ext_ip()
        self.functions.session_timeout = 2
        state = self.functions.test_peer_state({
            "profile": self.profile,
            "current_source_node": "127.0.0.1",
            "test_address": static_peer,
            "simple": True
        })
        if state != "Ready":
            self.error_messages.error_code_messages({
                "error_code": "sh-830",
                "line_code": "invalid_peer_address",
                "extra": f"{static_peer}:{static_peer_port}",
            })
        
    # =============  

    # def handle_invalid_version(self):
    #     if self.cli != None and self.cli.invalid_version:
    #         self.functions.confirm_action({
    #             "yes_no_default": "NO",
    #             "return_on": "YES",
    #             "strict": True,
    #             "prompt_color": "red",
    #             "prompt": "Are you sure you want to continue?",
    #             "exit_if": True
    #         })

            
    def handle_versioning(self):
        if self.called_command == "install": called_cmd = "show_version"
        elif self.called_command in ["version", "_v", "upgrade"]: return
        else: called_cmd = self.called_command
        
        if self.called_command in ["check_versions","_cv"]:
            self.node_service = False
            self._set_cn_requests()
        
        need_forced_update = [
            "check_versions","_cv",
            "uvos","update_version_object",
            "nodectl_upgrade", "upgrade",
            "upgrade_path","_up",
        ]
        
        print_messages, show_spinner, verify_only, force, print_object = True, True, False, False, False   
        if called_cmd in need_forced_update: force = True
        if "--force" in self.argv: force = True

        if called_cmd == "update_version_object":
            if "-v" in self.argv: verify_only = True
            if "--print" in self.argv: print_object = True

        if called_cmd == "uvos":
            print_messages, show_spinner = False, False

        if not force and self.version_class_obj:
            versioning = self.version_class_obj
        else:
            try:   
                versioning = Versioning({
                    "cn_requests": self.cn_requests,
                    "show_spinner": show_spinner,
                    "print_messages": print_messages,
                    "called_cmd": called_cmd,
                    "verify_only": verify_only,
                    "print_object": print_object,
                    "logging_key": self.log_key,
                    "force": force
                })
                versioning.set_parameters()
            except Exception as e:
                self._print_log_msg("error",f"shell_handler -> unable to process versioning | [{e}]")
                self.functions.event = False
                exit(1)


        if called_cmd == "update_version_object" or called_cmd == "uvos":
            if "help" not in self.argv:
                exit(0)

        self.version_obj = versioning.get_version_obj()  
        self.functions.version_obj = self.version_obj

        self.functions.set_statics()

        if called_cmd == "update_version_object": # needs to be checked after version_obj is created
            self.functions.check_for_help(self.argv,"update_version_object")  


    def _set_node_obj(self):
        invalid = False
        if not self.cli or self.called_command in ["help_only"]: 
            return
        if isinstance(self.cli,SimpleNamespace):
            return
        for _ in range(0,2):
            add_forced = False
            node_id_obj_org = self.functions.get_nodeid_from_file()
            if node_id_obj_org:
                self.cli.node_id_obj = deepcopy(node_id_obj_org)
                for key, value in node_id_obj_org.items():
                    if "short" not in key:
                        self.cli.node_id_obj[f"{key}_wallet"] = self.cli.cli_nodeid2dag({
                            "nodeid": value,
                            "profile": self.profile,
                        })
                self.config_obj["global_elements"]["nodeid_obj"] = self.cli.node_id_obj
                for value in node_id_obj_org.values():
                    if value == None or value == "":
                        invalid = True
                if not invalid:
                    return
            if "--force" not in self.argv:
                add_forced = True
                self.argv.append("--force")
            self.handle_versioning()
            self.cli.node_id_obj = False    
            if add_forced:      
                self.argv.remove("--force")
        
          
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

        pass
        
                                                
    def update_os(self,threading=True,display=True):
        with ThreadPoolExecutor() as executor:
            self._print_log_msg("info",f"updating the Debian operating system.")
            environ['DEBIAN_FRONTEND'] = 'noninteractive'
            
            if threading:
                self.functions.status_dots = True
                _ = executor.submit(self.functions.print_cmd_status,{
                    "text_start": "Updating the Debian OS system",
                    "dotted_animation": True,
                    "status": "running",
                })

            bashCommand = "apt-get -o Dpkg::Options::=--force-confold -y update"
            self.functions.process_command({
                "bashCommand": bashCommand,
                "proc_action": "timeout",
            })        

            if threading: self.functions.status_dots = False
            if display:
                self.functions.print_cmd_status({
                    "text_start": "Updating the Debian OS system",
                    "status": "complete",
                    "newline": True
                })
        

    def setup_profiles(self):
        self._print_log_msg("debug",f"setup profiles [{self.called_command}]")

        skip_list = [
            "main_error","validate_config","install",
            "view_config","_vc","_val","help",
        ]
        if self.called_command in skip_list:
            self.profile = None
            self.profile_names = None
            return

        self.functions.set_default_variables({"profiles_only": True})        
        self.profile_names = self.functions.profile_names
        self.profile = self.functions.default_profile  # default to first layer0 found


    def _set_version_obj(self):
        return Versioning({
            "config_obj": self.config_obj,
            "print_messages": False,
            "called_cmd": "show_version",
        })
    

    def show_version(self):
        self._print_log_msg("info",f"show version check requested")
        # versioning = self._set_version_obj()
        # version_obj = versioning.version_obj
        # self.functions.print_clear_line()
        parts = self.functions.cleaner(self.functions.nodectl_version,"remove_char","v")
        parts = parts.split(".")
        
        print_out_list = [
            {
                "header_elements" : {
                    "VERSION": self.functions.nodectl_version,
                    "MAJOR": parts[0],
                    "MINOR": parts[1],
                    "PATCH": parts[2],
                    "CONFIG": self.functions.nodectl_version,
                },
                "spacing": 10
            },
        ]
        
        for header_elements in print_out_list:
            self.functions.print_show_output({
                "header_elements" : header_elements
            })
        exit(0)
            

    def verify_specs(self,command_list):
        self.functions.check_for_help(command_list+["special_case"],"verify_specs")
        specs = self.functions.get_distro_details()
        info = specs["info"]
        memory = self.functions.get_memory().total
        disk = self.functions.get_disk().total
        specs["cpu_count"] = specs["info"]["count"]
        
        version_obj = self._set_version_obj()
        
        if not hasattr(self.cn_requests,"session"):
            self.cn_requests.get_json = True
            self.cn_requests.set_session()
        requirements = self.cn_requests.get_raw_request(version_obj.spec_path)
        if not requirements:
            self.error_messages.error_code_messages({
                "error_code": "sh-1257",
                "line_code": "api_error",
                "extra": None,
                "extra2": "unable to reach nodectl repo to pull specs, try again later."
            })
        
        requirements = json.loads(requirements.content.decode())
        
        possible_issues = {
            "release": False,
            "debian": False,
            "layer0_disk": False,
            "layer1_disk": False,
            "layer0_memory": False,
            "layer1_memory": False,
            "layer0_cpu_count": False, 
            "layer1_cpu_count": False, 
        }

        self.functions.print_header_title({
            "line1": "VERIFY NODECTL SPECS",
            "line2": "Pre-installation Tool",
            "newline": "top",
            "upper": False,
        })  
        cprint("  Please choose node type to test:","blue",attrs=["bold"])
        option = self.functions.print_option_menu({
            "options": [
                "Hybrid Dual Layer",
                "Dor Validator",
            ],
            "let_or_num": "let",
            "r_and_q": "q",
            "color": "cyan",
        }).lower()

        node_type = "Hybrid"
        if option == "q":
            exit(0)
        if option == "d":
            node_type = "Dor"

        def round_down(val):
            if val <= 0:
                return 0
            magnitude = 10 ** int(math.log10(val))
            return (val // magnitude) * magnitude
        
        def test_ubuntu_debian(specs):
            try:
                spec_key = specs["distributor_id"]
            except:
                spec_key = specs["id"]

            if spec_key == "Ubuntu":
                specs["debian"] = spec_key
                if specs["release"] not in ["22.04","24.04"]:
                    possible_issues["release"] = specs["release"]
            elif spec_key == "Debian":
                specs["debian"] = spec_key
                if specs["release"] not in ["12"]:
                    possible_issues["release"] = specs["release"]
            else:
                return False
            return True
        
        debian = test_ubuntu_debian(specs)

        if not debian:
            possible_issues["debian"] = "Not a Debian release"

        if info["bits"] != 64:
            possible_issues["bits"] = info["bits"]

        specs["layer1_cpu_count"] = info["count"]
        if info["count"] < requirements["layer1"]["cpu"]:
            possible_issues["layer1_cpu_count"] =info["count"]
        specs["layer0_cpu_count"] = info["count"]
        if info["count"] < requirements["hybrid"]["cpu"]:
            possible_issues["layer0_cpu_count"] =info["count"]

        specs["layer1_memory"] = memory
        if memory < round_down(requirements["layer1"]["memory"]):
            possible_issues["layer1_memory"] = memory
        specs["layer0_memory"] = memory
        if memory < round_down(requirements["hybrid"]["memory"]):
            possible_issues["layer0_memory"] = memory

        specs["layer0_disk"] = disk
        if disk < round_down(requirements["hybrid"]["disk"]): # 320G = 343597383680
            possible_issues["layer0_disk"]
        specs["layer1_disk"] = disk
        if disk < round_down(requirements["layer1"]["disk"]): # 80G = 85899345920
            possible_issues["layer1_disk"]

        requirements = {
            "release": "11" if specs["distributor_id"] == "Debian" else "22.04",
            "debian": "Debian",
            "layer0_disk": requirements["hybrid"]["disk"],
            "layer1_disk": requirements["layer1"]["disk"],
            "layer0_memory": requirements["hybrid"]["memory"],
            "layer1_memory": requirements["layer1"]["memory"],
            "layer0_cpu_count": requirements["hybrid"]["cpu"], 
            "layer1_cpu_count": requirements["layer1"]["cpu"],             
        }

        if option == "h":
            possible_issues = {key: value for key, value in possible_issues.items() if 'layer1' not in key}
            specs = {key: value for key, value in specs.items() if 'layer1' not in key}
        else:
            possible_issues = {key: value for key, value in possible_issues.items() if 'layer0' not in key}
            specs = {key: value for key, value in specs.items() if 'layer0' not in key}

        passed = True
        self.functions.print_paragraphs([
            ["Node type:",0], [node_type,1,"yellow"],
        ])
        for item, value in possible_issues.items():
            p_item = item
            if "layer0" in item: p_item = item.replace("layer0_","")
            if "layer1" in item: p_item = item.replace("layer1_","")
            if not value:
                self.functions.print_cmd_status({
                    "text_start": p_item,
                    "brackets": str(specs[item]),
                    "status": "passed",
                    "status_color": "green",
                    "newline": True,
                    "delay": 0.8,
                })
            else:
                passed = False
                self.functions.print_cmd_status({
                    "text_start": p_item,
                    "brackets": str(specs[item]),
                    "status": "failed",
                    "status_color": "red",
                    "newline": True,
                })                
                self.functions.print_cmd_status({
                    "text_start": p_item,
                    "brackets": str(requirements[item]),
                    "status": "required",
                    "status_color": "yellow",
                    "newline": True,
                    "delay": 0.8,
                })                
        
        if passed:
            self.functions.print_paragraphs([
                ["",1],[" SUCCESS ",0,"yellow,on_green","bold"],
                ["This node meets all necessary specifications to run as a node.",2,"green"],
            ])
            return True
        else:
            self.functions.print_paragraphs([
                ["",1],[" FAILURE ",0,"yellow,on_red"],
                ["This node",0,"red"], ["does not",0,"red","bold"],
                ["meet the necessary specifications to run as a node.",2,"red"],
            ])
            return False


    def digital_signature(self,command_list):
        if "--skip-validation" in command_list:
            self.functions.print_paragraphs([
                ["  WARNING ",0,"white,on_yellow"],
                ["Digital signature verification skipped by user request",1,"red"],
            ])
            return
        found_error = False

        self._print_log_msg("info","Attempting to verify nodectl binary against code signed signature.")
        self.functions.check_for_help(command_list,"verify_nodectl")
        self.functions.print_header_title({
            "line1": "VERIFY NODECTL",
            "line2": "warning verify keys",
            "newline": "top",
            "upper": False,
        })   
        
        short = True if "-s" in command_list else False
        version_obj = Versioning({"called_cmd": self.called_command})
        distro = self.functions.get_distro_details()
        node_arch = distro["arch"]
        arch_release = distro["release"].replace(".","")
        if arch_release == "2204": arch_release = "12"
        if "X86" in node_arch: node_arch = node_arch.lower()
        nodectl_version_github = version_obj.version_obj["nodectl_github_version"]
        nodectl_version_full = version_obj.version_obj["node_nodectl_version"]
        file_name = f'{nodectl_version_github}_{node_arch}_{arch_release}'
        outputs, urls = [], []
        cmds = [  # must be in this order
            [ "nodectl_public","fetching public key","PUBLIC KEY","-----BEGINPUBLICKEY----"],
            [ f'{file_name}.sha256',"fetching digital signature hash","BINARY HASH",("SHA2-256","SHA256")],
            [ f"{file_name}.sig","fetching digital signature","none","none"],
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

        files = [f"/var/tmp/{file[0]}" for file in cmds]

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

            try:
                self.functions.download_file({
                    "url": url,
                    "local": f"/var/tmp/{cmd[0]}",
                })
                full_file_path = f"/var/tmp/{cmd[0]}"
            except Exception as e:
                self._print_log_msg("error",f"shell handler -> digital signature failed to download from [{url}] with error [{e}]")
                self.error_messages.error_code_messages({
                    "error_code": "sh-1019",
                    "line_code": "download_invalid",
                    "extra": url,
                })

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
                if isinstance(cmd[3],tuple):
                    found_error = True
                    for s in cmd[3]:
                        if s in text_output: 
                            found_error = False
                            break
                elif cmd[3] not in text_output:
                    found_error = True
                if found_error:
                    self.functions.remove_files({
                        "file_or_list": files,
                        "caller": "digital_signature",
                        "is_glob": False,
                        "etag": True
                    })
                    send_error(f"invalid {cmd[2]} downloaded or unable to download")
                outputs.append(text_output.replace("-----BEGINPUBLICKEY-----","").replace("-----ENDPUBLICKEY-----","").replace("\n",""))

                self.functions.print_cmd_status({
                    "text_start": cmd[1],
                    "status": "complete",
                    "status_color": "green",
                    "newline": True
                })   
        
        if not short:
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
            "newline": False,
            "status": "verifying",
            "status_color": "yellow",
        })   
        
        self._print_log_msg("info","copy binary nodectl to nodectl dir for verification via rename")
        copy2("/usr/local/bin/nodectl",f"/var/tmp/nodectl_{node_arch}")  
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
        
        self._print_log_msg("info","nodectl digital signature verification requested")
        if "OK" in result_sig and result_nodectl_current_hash_mod == output_mod:
            self._print_log_msg("info",f"digital signature verified successfully | {result_sig}")
            bg, verb = "on_green","SUCCESS - AUTHENTIC NODECTL"
        else: 
            error_line = "Review logs for details."
            self._print_log_msg("critical",f"digital signature did NOT verified successfully | {result_sig}")
        self._print_log_msg("info",f"digital signature - local file hash | {result_nodectl_current_hash}")
        self._print_log_msg("info",f"digital signature - remote file hash | {outputs[1]}")

        self.functions.print_cmd_status({
            "text_start": "verifying signature match",
            "newline": True,
            "status": "complete",
            "status_color": "green" if bg == "on_green" else "red",
        })   

        self.functions.print_paragraphs([
            ["",1],["VERIFICATION RESULT",1,"blue","bold"],
            [f" {verb} ",1,f"blue,{bg}","bold"],
            [error_line,1,"red"]
        ])

        if bg == "on_red" and "--skip-override" not in command_list:
            self.functions.print_paragraphs([
                ["Would you like to attempt to update the binary hash by downloading this version of nodectl over itself?",1],
            ])
            if self.functions.confirm_action({
                "yes_no_default": "n",
                "return_on": "y",
                "prompt_color": "magenta",
                "prompt": "Overwrite nodectl?",
                "exit_if": False,
            }):  
                if "mobile" in command_list: return ["mobile","revision"]
                return ["revision"]  
            elif "mobile" in command_list: return ["mobile"]
            else: 
                cprint("  Terminated by user","green")
                exit(0)
        
        if "mobile" in command_list: 
            self.functions.print_any_key({})
            return ["mobile_success"]
        return False      
    
            
    def confirm_int_upg(self):
        self._print_log_msg("info",f"{self.install_upgrade} for Tessellation and nodectl started")       
        
        if self.install_upgrade == "installation":
            print(f'  {colored("WARNING","red",attrs=["bold"])} {colored("You about to turn this VPS or Server into a","red")}')
            cprint("  Constellation Network validator node","green",attrs=['bold'])
        else:
            if self.auto_restart_enabled:
                self._print_log_msg("info","terminating auto_restart in order to upgrade")  
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
                
        if "-y" not in self.argv:
            prompt_str = f"Are you sure you want to continue this {self.install_upgrade}?"
            self.functions.confirm_action({
                "yes_no_default": "y",
                "return_on": "y",
                "prompt": prompt_str,
            })


    def restore_config(self):
        from modules.submodules.restore_config import RestoreConfig

        restore_config = RestoreConfig(self)

        restore_config.set_parameters()
        restore_config.get_files()
        restore_config.set_display()
        restore_config.print_headers()
        restore_config.get_operator_option()
        restore_config.handle_backup_location()
        restore_config.execute_restore()    
        restore_config.print_complete("restored")


    def api_service_handler(self):
        # future development placeholder
        action = self.argv[0]
        # if action != "enable":
        self.error_messages.error_code_messages({
            "error_code": "sh-967",
            "line_code": "api_server_error",
        })
        # api_server = API(self.functions)
        # api_server.run()
       

    def auto_restart_handler(self, action, cli=False, manual=False):
        from modules.submodules.auto_restart_handler import AutoRestartHandler
        ar_handler = AutoRestartHandler(self, action, cli, manual)
        ar_handler.set_parameters()
        
        if ar_handler.process_invalid_action():
            return        

        ar_handler.set_auto_restart_pid()
        ar_handler.handle_service_restart()
            
        if ar_handler.handle_cli_service_disable():
            return
                
        ar_handler.get_service_times()
            
        return_value = ar_handler.set_print_output()
        if return_value:
            return return_value
        
        if ar_handler.handle_clear_alerts():
            return

        if ar_handler.handle_alert_tests():
            return
        
        if ar_handler.process_p12_keys():
            exit("  auto restart passphrase error")

        if ar_handler.handle_service_disable():
            return

        ar_handler.print_final_cli_message()        

    
    def upgrade_node(self,argv_list):
        if "help" in argv_list:
            self.functions.print_help({
                "extended": self.called_command,
            })

        self._print_log_msg("debug",f"{self.called_command} request started") 
        performance_start = time.perf_counter()  # keep track of how long

        self.upgrader = Upgrader({
            "argv_list": argv_list,
            "setter": self.set_self_value,
            "getter": self.get_self_value,
        }) 
        self.upgrader.upgrade_process()
        
        self.functions.print_perftime(performance_start,"upgrade")
        
    
    def install(self,argv_list):
        if "help" in argv_list:
            self.functions.print_help({
                "nodectl_version_only": True,
                "extended": "install",
            })

        performance_start = time.perf_counter()  # keep track of how long
        self.installer = Installer(self,argv_list)
        v_result = False

        if self.called_command == "uninstall":
            self.installer.action = "uninstall"
            self.installer.uninstall()
            return

        self.installer.handle_options()
        if not self.installer.options.quiet and not self.installer.options.skip_system_validation:
            self.functions.print_paragraphs([
                ["",1],["Before we begin the",0,"green"],
                ["installation",0,"yellow"],["process, let's verify our",0,"green"],
                ["VPS",0,"yellow"],["meets the necessary requirements.",1,"green"],
            ])
            v_result = self.verify_specs([])
            if not v_result:
                self.functions.print_paragraphs([
                    ["You may proceed with this installation; however, it is not advised.",1,"magenta","bold"],
                ])
                do_install = self.functions.print_any_key({
                    "prompt": "Press any key to continue installation",
                    "quit_option": True,
                    "return_key": True,
                })
                if do_install == "q": 
                    cprint("  Installation exited on Node Operator request","green",attrs=["bold"])
                    exit(0)
                self.installer.options.confirm_install = True
            else:
                time.sleep(2)

        self.installer.install_process()
        if not self.installer.options.quiet:
            self.functions.print_perftime(performance_start,"installation")


    def set_version_obj_class(self):
        self.version_class_obj = Versioning({"called_cmd": "setup_only"})
        self.version_class_obj.set_parameters()

    def handle_exit(self,return_value):
        if return_value == "skip_auto_restart_restart":
            return_value = 0
        else:
            self.check_auto_restart("end")
        if self.mobile: return
        if return_value == "return_caller": exit(0) # don't display
        if self.called_command in ["upgrade_nodectl","revision"]:
            exit(0)
        exit(return_value)
        
        
    def _print_log_msg(self,log_type,msg):
        log_method = getattr(self.log, log_type, None)
        log_method(f"{self.__class__.__name__} --> {msg}")
                
if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")            
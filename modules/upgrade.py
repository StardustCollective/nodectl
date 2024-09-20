from concurrent.futures import ThreadPoolExecutor, as_completed
from os import path, makedirs, remove, listdir
from shutil import copy2, rmtree
from time import sleep
from termcolor import colored
from re import match
from copy import deepcopy

from .troubleshoot.errors import Error_codes
from .p12 import P12Class
from .troubleshoot.logger import Logging
from .config.configurator import Configurator
from .config.auto_complete import ac_validate_path, ac_build_script, ac_write_file
from .config.time_setup import remove_ntp_services, handle_time_setup


class Upgrader():

    def __init__(self,command_obj):
        self.log = Logging()
        self.log.logger.info("System Upgrade called, initializing upgrade.")
        
        self.parent = command_obj["parent"]
        self.functions = self.parent.functions
        self.config_obj = self.parent.config_obj
        self.version_obj = self.parent.version_obj
        self.argv_list = command_obj["argv_list"]
        self.environment = command_obj.get("environment",False)
        
        self.debug = command_obj.get("debug",False)
        self.cli_global_pass = False
        self.step = 1
        self.status = "" #empty
        self.node_id = ""
        
        self.link_types = ["gl0","ml0"]
        self.final_upgrade_status_list = []
        self.api_ready_list = {}
        self.profile_progress = {}     
        
        self.error_messages = Error_codes(self.functions) 
    

    def build_p12_obj(self):
        p12_obj = {
            "caller": "upgrader",
            "action": "upgrade",
            "operation": "upgrade",
            "functions": self.functions,
            "cli_obj": self.cli,
        }
        self.p12 = P12Class(p12_obj)   
        
        
    def build_cli_obj(self):
        self.cli = self.parent.cli
        self.cli.caller = "upgrader"
        self.cli.command = "upgrade"
        self.cli.profile_name = self.functions.profile_names
        self.cli.backup_config([])
                
                
    def upgrade_process(self):

        self.setup_upgrader()
        self.setup_argv_list()

        self.environments_verification_handler()
        self.build_cli_obj()

        self.versioning_handler()
        self.profile_handler()

        self.build_p12_obj()
        self.get_node_id()    
        self.get_ip_address()
        self.request_version()
        
        self.leave_cluster() 
        self.stop_service() 

        self.print_section("Node Internal Configuration")
        self.verify_directories()
        self.modify_dynamic_elements()
        self.upgrade_log_archive()  # must be done after modify to accept new config dir
                
        self.update_dependencies()      
        self.p12_encrypt_passphrase()
        self.reload_node_service()
  
        if not self.nodectl_only:
            self.print_section("Bring Node Back Online")
            for profile in self.profile_order:
                self.start_node_service(profile)
                self.check_for_api_readytojoin(profile)
                self.re_join_tessellation(profile)
        
        self.complete_process()
    
    
    def setup_upgrader(self):
        self.functions.print_header_title({
          "line1": f"UPGRADE REQUEST",
          "line2": "TESSELLATION VALIDATOR NODE",
          "clear": True,
        })
        
        self.install_upgrade = "upgrade"
        if "-ni" not in self.argv_list and not "--ni" in self.argv_list:
            self.parent.install_upgrade = "upgrade"
            self.parent.confirm_int_upg()


    def profile_handler(self):
        profile_items = self.functions.pull_profile({"req": "order_pairing"})
        self.profile_order = profile_items.pop()
        self.profile_order = self.functions.clear_external_profiles(self.profile_order)
        self.profiles_by_env = list(self.functions.pull_profile({
            "req": "profiles_by_environment",
            "environment": self.environment
        }))
        
        # removes any profiles that don't belong to this environment
        for n, profile_list in enumerate(profile_items):
            for profile in profile_list:
                if profile["profile"] == "external": continue
                elif profile["profile"] not in self.profiles_by_env: profile_items.pop(n)
                else:
                    self.profile_progress = {
                        **self.profile_progress,
                        f'{profile["profile"]}': {
                            f"leave_complete": False,
                            f"stop_complete": False,
                            f"start_complete": False,
                            f"join_complete": False,
                            f"ready_to_join": False,
                            f"complete_status": False,
                            f"download_version": False,
                        }
                    }
        
        # clean up external entries
        clean_profile_list = []
        for n, profile_list in enumerate(profile_items):
            if profile_list[0]["profile"] != "external":
                clean_profile_list.append(profile_list)
        self.profile_items = clean_profile_list


    def environments_verification_handler(self):
        self.functions.print_clear_line(1,{
            "backwards": True,
            "bl": 1,
        })
        print("")

        progress = {
            "text_start": "Handling environment setup",
            "status": "running",
            "newline": False,
        }
        self.functions.print_cmd_status(progress)

        verb = "Using" 
        environments = self.functions.pull_profile({"req": "environments"})
        if not self.show_list:
            self.show_list = True if environments["multiple_environments"] else self.show_list
        
        if self.environment:
            print("")
            if self.environment not in list(environments["environment_names"]):
                self.error_messages.error_code_messages({
                    "error_code": "upg-178",
                    "line_code": "environment_error",
                    "extra": "upgrade",
                    "extra2": self.environment
                })
    
        if self.show_list:
            verb = "Selected"
            print("")
            self.functions.print_header_title({
                "line1": "ENVIRONMENT UPGRADE MENU",
                "newline": "both",
                "single_line": True,
            })

            msg_start = "Multiple network cluster environments were found on this system."
            if self.show_list and not environments["multiple_environments"]:
                msg_start = "Show list of network clusters was requested."
                self.log.logger.debug("Upgrade show list of environments requested")
            if self.environment:
                msg_start = "Choose environment from list requested but environment request was entered at the command line."
                self.functions.print_cmd_status({
                    "text_start": "Environment requested by argument",
                    "brackets": "-e",
                    "status": self.environment,
                    "status_color": "blue",
                    "newline": True,
                })
                print("")

            if environments["multiple_environments"] and not self.environment:
                self.log.logger.debug(f"Upgrade found multiple network cluster environments on the same Node that may are supported by different versions of nodectl")
                self.functions.print_paragraphs([
                    [f"{msg_start} nodectl can only upgrade one environment at a time.",0],
                    ["Please select an environment by",0], ["key pressing",0,"yellow"], 
                    ["the number correlating to the environment you wish to upgrade.",2],  
                    ["PLEASE CHOOSE AN ENVIRONMENT TO UPGRADE",2,"magenta","bold"]                      
                ])
            self.environment = self.functions.print_option_menu({
                "options": list(environments["environment_names"]),
                "return_value": True,
                "color": "magenta"
            })
        else:
            if not self.environment:
                self.environment = list(environments["environment_names"])[0]

        self.functions.print_cmd_status({
            "text_start": f"{verb} environment",
            "status": self.environment,
            "status_color": "blue",
            "newline": True,
        })       


    def versioning_handler(self):
        self.print_section("Verify Node Upgrade")
        
        progress = {
            "text_start": "Verify upgrade paths",
            "status": "running",
            "status_color": "yellow"
        }
        self.functions.print_cmd_status(progress)
        self.cli.check_nodectl_upgrade_path({
            "called_command": "upgrade",
            "argv_list": ["-e",self.environment],
            "version_class_obj": self.parent.version_class_obj
        })
        self.functions.print_cmd_status({
            **progress,
            "status": "complete",
            "status_color": "green",
            "newline": True,
        })
        
        current = self.functions.version_obj["node_nodectl_version"]
        
        show_warning = False
        for _ in range(0,2):
            try:
                if self.functions.version_obj[self.environment]["nodectl"]["nodectl_uptodate"]:
                    if not isinstance(self.functions.version_obj[self.environment]["nodectl"]["nodectl_uptodate"],bool):
                        show_warning = True
                break
            except:
                # in the event the version object is corrupt
                self.functions.version_obj = self.functions.handle_missing_version(self.parent.version_class_obj)
                
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
                
            if self.forced or skip_warning_messages:
                self.log.logger.warning(f"an attempt to {self.install_upgrade} with an non-interactive mode detected {current}")  
                self.functions.print_paragraphs([
                    [" WARNING ",0,"red,on_yellow"], [f"non-interactive mode was detected, developer mode, or extra parameters were supplied to",0],
                    [f"this {self.install_upgrade}.",1],
                    ["It will continue at the Node Operator's",0,"yellow"],
                    ["own risk and decision.",2,"yellow","bold"]
                ])
            else:
                self.log.logger.warning(f"an attempt to upgrade with an older nodectl detected {current}")  
                prompt_str = f"Are you sure you want to continue this upgrade?"
                self.functions.confirm_action({
                    "yes_no_default": "n",
                    "return_on": "y",
                    "prompt": prompt_str,
                })
            self.log.logger.warning(f"upgrade executed with an older version of nodectl [{current}]") 

        self.functions.print_cmd_status({
            **progress,
            "status": "complete",
            "newline": True
        })

            
    def print_section(self,line):
        self.functions.print_header_title({
            "line1": line,
            "newline": "both",
            "single_line": True,
        })

   
    def get_ip_address(self):
        self.functions.print_cmd_status({
            "text_start": "Node IP address",
            "status": self.functions.get_ext_ip(),
            "status_color": "green",
            "newline": True,
        })  


    def get_node_id(self):

        def pull_node_id(profile):
            with ThreadPoolExecutor() as executor:
                self.functions.status_dots = True
                progress ={
                    "status": "running",
                    "brackets": profile,
                    "dotted_animation": True,
                    "text_start": "Obtaining Node ID from p12",
                }
                _ = executor.submit(self.functions.print_cmd_status,progress)

                self.p12.extract_export_config_env({
                    "global": True if profile == "global" else False,
                    "profile": profile,
                })
                result = 1

                core_file_error = False
                if not path.isfile("/var/tessellation/cl-wallet.jar"):
                    core_file_error = True
                if self.functions.get_size("/var/tessellation/cl-wallet.jar","single") < 1:
                    core_file_error = True
                if core_file_error:
                    self.error_messages.error_code_messages({
                        "error_code": "upg-345",
                        "line_code": "file_not_found",
                        "extra": "/var/tessellation/cl-wallet.jar",
                    })

                while True:
                    cmd = "java -jar /var/tessellation/cl-wallet.jar show-id"
                    self.node_id = self.functions.process_command({
                        "bashCommand": cmd,
                        "proc_action": "poll"
                    })
                    self.node_id = self.node_id.strip()

                    if self.validate_node_id(self.node_id):
                        break
                    result = self.node_id_error_handler(result)
                    
                brief_node_id = f"{self.node_id[0:5]}....{self.node_id[-5:]}"
                
                self.functions.status_dots = False
                self.functions.print_cmd_status({
                    **progress,
                    "dotted_animation": False,
                    "result_color": "yellow",
                    "status": brief_node_id,
                    "newline": True
                })
        
        p_color = "cyan"
        for profile in self.profiles_by_env:
            if self.functions.config_obj[profile]["global_p12_passphrase"]:
                p_status = "using global"
                p_color = "cyan"
            else:
                p_status = self.functions.config_obj[profile]["p12_validated"]
                p_color = "green" if p_status else "red"
            self.functions.print_cmd_status({
                "text_start": "p12 validated",
                "brackets": profile,
                "status": p_status,
                "status_color": p_color,
                "newline": True,
            })

        self.functions.print_cmd_status({
            "text_start": "Global p12 validated",
            "status": self.functions.config_obj["global_p12"]["p12_validated"],
            "status_color": "green" if self.functions.config_obj["global_p12"]["p12_validated"] else "red",
            "newline": True,
        })

        self.all_global = True
        if self.functions.config_obj["global_elements"]["all_global"]:
            self.all_global = True
            pull_node_id("global")
            return
        
        global_complete = False
        for profile_list in self.profile_items:
            for profile in profile_list:
                c_profile = profile["profile"]

                if self.functions.config_obj[c_profile]["global_p12_passphrase"] and not global_complete:
                    global_complete, c_profile = True, "global"
                pull_node_id(c_profile)
                
        if not global_complete:
            pull_node_id("global")


    def validate_node_id(self,node_id):
        if match("[0-9a-fA-F]{128}$",node_id):
            return True
        return False
        
                
    def request_version(self):
        if self.nodectl_only: return
        
        self.print_section("Handle Node Versioning")
        ml_version_found = False

        meta_type = self.config_obj["global_elements"]["metagraph_name"]
        meta_title = "metagraph: "
        is_meta = True

        if meta_type == "hypergraph:":
            meta_title = "   cluster:"
            is_meta = False

        # all profiles with the ml type should be the same version
        for profile in self.profile_order:
            do_continue, dynamic_uri = False, True
            env = self.config_obj[profile]["environment"]
            
            if self.profile_progress[profile]["download_version"]:
                download_version = self.profile_progress[profile]["download_version"]
            elif ml_version_found and self.config_obj[profile]["meta_type"] == "ml": 
                self.profile_progress[profile]["download_version"] = ml_download_version
                self.profile_progress[profile]["tools_version"] = ml_tools_version
                do_continue = True
            
            self.functions.print_paragraphs([
                ["PROFILE:     ",0], [profile,1,"yellow","bold"], 
                ["ENVIRONMENT: ",0],[self.environment,1,"yellow","bold"],
                [f"{meta_title.upper()}  ",0],[meta_type,2,"yellow","bold"],
            ])
            
            if do_continue:
                self.functions.print_paragraphs([
                    [f"Cluster {self.environment} for profile {profile} using {ml_download_version}",1]
                ])
                continue
            
            if self.config_obj[profile]["is_jar_static"]:
                self.functions.print_cmd_status({
                    "text_start": "Statically defined versioning found",
                    "status": "continuing",
                    "status_color": "green",
                    "newline": True,
                })
                do_continue = True
                dynamic_uri = False
                download_version = False

            for n in range(1,4):
                try:
                    found_tess_version = self.version_obj[env][profile]['cluster_tess_version']
                    running_tess_version = self.version_obj[env][profile]["node_tess_version"]
                    metagraph_version = self.version_obj[env][profile]["cluster_metagraph_version"]
                except:
                    if n == 1:
                        self.version_obj = self.parent.version_class_obj.version_obj
                    elif n < 3:
                        self.parent.version_class_obj.called_cmd = "upgrader"
                        self.parent.version_class_obj.execute_versioning()
                        self.version_obj = self.parent.version_class_obj.version_obj
                    else:
                        self.error_messages.error_code_messages({
                            "error_code": "upg-298",
                            "line_code": "version_fetch"
                        })
                else:
                    break
                
            self.log.logger.info(f"upgrade handling versioning: profile [{profile}] tessellation latest [{found_tess_version}] current: [{running_tess_version}]")
            if is_meta:
                self.log.logger.info(f"upgrade handling versioning: profile [{profile}] {meta_type} latest [{metagraph_version}]")
            
            self.functions.print_paragraphs([
                ["Tess",0,"yellow"],["short hand for",0], 
                ["Tessellation",0,"yellow"],[".",-1],["",1],
            ])
        
            if dynamic_uri:
                self.functions.print_cmd_status({
                    "status": found_tess_version,
                    "text_start": "The latest",
                    "brackets": "Tess", 
                    "text_end": "version",
                    "result_color": "green",
                    "newline": True
                })
                if is_meta:
                    self.functions.print_cmd_status({
                        "status": metagraph_version,
                        "text_start": "The latest",
                        "brackets": meta_type, 
                        "text_end": "version",
                        "result_color": "green",
                        "newline": True
                    })
            
            if running_tess_version.lower() == "v":
                self.version_obj[env][profile]['node_tess_version'] = "unavailable" 
                
            self.functions.print_cmd_status({
                "status": running_tess_version,
                "text_start": f"Current {meta_title.replace(':','').rstrip()}",
                "brackets": "Tess",
                "text_end": f"version",
                "status_color": "red",
                "newline": True
            }) 
            
            if found_tess_version == running_tess_version:
                self.functions.print_paragraphs([
                    ["",1],[" WARNING ",0,"yellow,on_red","bold"], ["Tessellation is already on the latest known version.",1,"red"],
                    ["If you are only upgrading the Node's internal components because your Node is exhibiting undesirable or",0,"yellow"],
                    ["unexpected behavior, you should accept the default and upgrade your Node's version to the same",0,"yellow"],
                    ["version level by simply hitting",0,"yellow"],["<enter>",0,"white"],["here.",2,"yellow"],
                ])
                
            if dynamic_uri:
                self.functions.print_paragraphs([
                    ["Press enter to accept the default value between",0], ["[]",0,"white"], ["brackets.",1]
                ])
                
            new_version = metagraph_version
            if meta_type == "hypergraph":
                new_version = found_tess_version

            while True:
                if not self.profile_progress[profile]["download_version"] and dynamic_uri:
                    self.functions.print_cmd_status({
                        "text_start": "Please enter", 
                        "brackets": meta_type, 
                        "text_end": "version to upgrade to:",
                        "newline": False,
                    })
                    if "-ni" in self.argv_list or "--ni" in self.argv_list: # cannot use self.non_interactive because of developer mode
                        download_version = False 
                    else:
                        version_str = colored("  Please enter version to upgrade to".ljust(45,"."),"cyan")+"["+colored(new_version,"yellow",attrs=['bold'])+"] : "
                        download_version = input(version_str) # cannot use self.non_interactive because of developer mode

                if not download_version:
                    download_version = new_version
                    break
                else:
                    if not self.forced:
                        if download_version[0] == "V":
                            download_version = download_version.replace("V","v")
                        elif download_version[0] != "v": 
                            download_version = f"v{download_version}"
                        
                    if self.functions.is_version_valid(download_version) or self.forced:
                        confirm = True
                        if self.forced:
                            self.functions.print_paragraphs([
                                [" WARNING ",0,"red,on_yellow"], ["forcing to version [",0,"yellow"],
                                [download_version,-1,"cyan","bold"], ["]",-1,"yellow"],["",1],
                            ])
                        else:
                            if found_tess_version != download_version and not self.cli.skip_warning_messages:
                                self.functions.print_paragraphs([
                                    ["This does not seem to be the latest version?",1,"red","bold"]
                                ])
                                confirm = self.functions.confirm_action({
                                    "yes_no_default": "n",
                                    "return_on": "y",
                                    "prompt": "Continue with selected version?",
                                    "exit_if": False
                                })
                        if confirm:                        
                            break
                        
                    elif self.forced:
                        self.functions.print_paragraphs([
                            [" WARNING ",0,"red,on_yellow"], ["A forced version was found that did not pass",0],
                            ["the version verification test; moreover, this version will be used",0],
                            ["and may result in an invalid version download.",1],
                            ["version:",0,"yellow"], [download_version,1,"magenta"],
                        ])
                        self.functions.confirm_action({
                            "yes_no_default": "y",
                            "return_on": "y",
                            "prompt": "Continue with selected version?",
                            "exit_if": True
                        })
                        break
                    
                self.functions.print_paragraphs([
                    ["Invalid version [",0,"red"], [download_version,-1,"yellow","bold"], ["] inputted, try again",-1,"red"],["",1],
                ])
                download_version = False
                
            self.functions.print_cmd_status({
                "status": download_version,
                "text_start": "Using",
                "brackets": meta_type,
                "text_end": "version",
                "result_color": "green",
                "newline": True
            })  

            self.profile_progress[profile]["download_version"] = download_version
            self.profile_progress[profile]["tools_version"] = download_version
            if meta_type != "hypergraph":
                self.profile_progress[profile]["tools_version"] = found_tess_version
            
            if self.config_obj[profile]["meta_type"] == "ml": 
                ml_version_found = True # only need once
                ml_download_version = download_version
                ml_tools_version = self.profile_progress[profile]["tools_version"]
                
            self.functions.print_paragraphs([
                ["",1], ["=","full","blue","bold"],["",1],
            ])

            
    def leave_cluster(self):
        if self.nodectl_only: return
        
        self.print_section("Take Node Offline")
        
        # < 2.0.0  shutdown legacy
        with ThreadPoolExecutor() as executor:
            futures = {}
            for profile_list in self.profile_items:
                for item in profile_list:
                    if not self.get_update_core_statuses("get","leave_complete",item["profile"]):
                        self.get_update_core_statuses("update","leave_complete",item["profile"],True)
                        self.cli.set_profile(item["profile"])
                        print_timer = True if item["profile"] == profile_list[-1]["profile"] else False
                        leave_obj = {
                            "secs": 30,
                            "reboot_flag": False,
                            "skip_msg": False,
                            "print_timer": print_timer,
                            "threaded": True,
                        }
                        futures = {
                            **futures,
                            executor.submit(self.cli.cli_leave, leave_obj): item,
                        }
                        sleep(1.5)
            self.futures_error_checking(futures,"upg-594","leave")

    
    def stop_service(self):
        if self.nodectl_only: return
        
        with ThreadPoolExecutor() as executor:
            futures = {}
            for profile_list in self.profile_items:
                for item in profile_list:
                    if not self.get_update_core_statuses("get","stop_complete",item["profile"]):
                        self.get_update_core_statuses("update","stop_complete",item["profile"],True)
                        if path.exists(f"/etc/systemd/system/cnng-{item['service']}.service") or path.exists(f"/etc/systemd/system/{item['service']}.service"): # includes legacy < v2.0.0
                            self.cli.set_profile(item["profile"])
                            stop_obj = {
                                "show_timer": False,
                                "static_nodeid": self.node_id if self.all_global else False,
                                "argv_list": []
                            }
                            futures = {
                                **futures,
                                executor.submit(self.cli.cli_stop,stop_obj): item,
                            }
                            sleep(3.3)
                        else:
                            self.functions.print_paragraphs([
                                ["unable to find [",0,"red"], [item['service'],-1,"yellow","bold"],
                                ["] on this Node.",-1,"red"],["",1],
                            ])
            self.futures_error_checking(futures,"upg-622","stop")    
            self.functions.print_clear_line()
            
 
    def futures_error_checking(self, futures, error_code, what):
        for future in as_completed(futures):
            try:
                _ = future.result()
            except Exception as e:
                self.functions.event = False
                self.functions.status_dots = False
                self.log.logger.error(f"upgrader -> threaded leave request failed with [{e}]")
                self.error_messages.error_code_messages({
                    "error_code": error_code,
                    "line_code": "upgrade_failure",
                    "extra": e,
                    "extra2": what,
                })


    def upgrade_log_archive(self):
        self.log.logger.info(f"logging and archiving prior to update.")

        to_clear = ["backups","uploads","logs"]
        action = "upgrade"
        days = 30
        for item in to_clear:
            self.functions.print_header_title({
                "line1": f"CLEAN UP {item.upper()}",
                "single_line": True,
                "newline": "both",
            })

            progress = {
                "status": "running",
                "text_start": "Cleaning logs from",
                "brackets": item,
                "text_end": f"> {days} days ",
            }
            self.functions.print_cmd_status(progress)

            argv_list = ["--ni","-t", item, "-d", days] if self.non_interactive else ["-t", item, "-d", days]
                
            # in the event Node Op attempts to upgrade over existing
            # v2.0.0 need to verify clean_files dirs
            self.cli.clean_files({
                "action": action,
                "argv_list": argv_list
            })
            
            self.functions.print_cmd_status({
                **progress,
                "status": "complete",
                "newline": True
            })


    def verify_directories(self):
        self.functions.set_default_directories() # put directories into place if default
        overall_status = "complete"
        overall_status_color = "green"
        print_warning = False
        
        file_paths = ["directory_backups","directory_uploads"]
        for file_path in file_paths:
            for profile in self.profiles_by_env:
                build_profile_dirs = False
                f_dir = self.functions.cleaner(self.functions.config_obj[profile][file_path],"trailing_backslash")
                if not path.exists(f_dir):
                    progress = {
                        "text_start": "Directory not found",
                        "brackets": f_dir,
                        "text_end": "creating",
                        "status": "creating"
                    }
                    self.functions.print_cmd_status(progress)
                    self.functions.print_clear_line()                    
                    bu_status = "complete"
                    bu_color = "green"
                    try:
                        makedirs(f_dir)
                    except Exception as e:
                        self.log.logger.error(f"during the upgrade process nodectl could not find or create [{file_path}] due to [{e}]")
                        bu_status = "failed"
                        bu_color = "red"
                        overall_status = "incomplete"
                        overall_status_color = "magenta"
                    else:
                        print_warning = True

                    self.functions.print_cmd_status({
                        **progress,
                        "status": bu_status,
                        "status_color": bu_color,
                        "newline": True,
                    })  
                # verify that data dirs are in place in event full configuration file is replaced
                if not path.exists(f"/var/tessellation/{profile}"):
                    build_profile_dirs = True
                elif not path.exists(f"/var/tessellation/{profile}/data") and  self.functions.config_obj[profile]["layer"] > 0: 
                    build_profile_dirs = True
                if build_profile_dirs:
                    self.log.logger.info(f"upgrader creating non-existent directories for core profile files | profile [{profile}]")
                    makedirs(f"/var/tessellation/{profile}/data")

                    
        self.functions.print_cmd_status({
            "status": overall_status,
            "status_color": overall_status_color,
            "text_start": "Verifying Node directory setup",
            "newline": True
        })
        
        if print_warning:
            self.functions.print_paragraphs([
                ["",1], ["IMPORTANT",0,"yellow,on_red"], ["This upgrade will not migrate data to new directories.",0,"yellow"],
                ["Updating the cn-config.yaml manually may result in old directories artifacts remaining present",0,"yellow"],
                ["on this Node.",0,"yellow"],
                ["This should be completed by the configurator.",2,"yellow"],
                ["sudo nodectl configure",2,"blue","bold"],
                ["continuing upgrade...",2]
            ])    
        

    def modify_dynamic_elements(self):
        
        self.fix_swap_issues()
        self.update_system_prompt()

        # keep in place for future refactoring for future upgrades
        backup = False
        confirm = True if self.non_interactive else False

        progress = {
            "text_start": "Removing old default seed files",
            "status": "running",
            "status_color": "yellow",
            "newline": True,
        }
        progress2 = {
            "text_start": "Removing old default jar files",
            "status": "running",
            "status_color": "yellow",
            "newline": False,
        }
        self.functions.print_cmd_status(progress)
        self.functions.print_cmd_status(progress2)
        
        if path.exists("/var/tessellation/seed-list"):
            remove("/var/tessellation/seed-list")

        if not path.exists("/var/tessellation/nodectl/includes"):
            makedirs("/var/tessellation/nodectl/includes")
            
        for profile in self.functions.profile_names:
            if path.exists(f"/var/tessellation/{profile}-seedlist"):
                remove(f"/var/tessellation/{profile}-seedlist")
            if path.exists(f"/var/tessellation/{self.config_obj[profile]['jar_file']}"):
                 remove(f"/var/tessellation/{self.config_obj[profile]['jar_file']}")

        sleep(.5)
        print(f'\x1b[1A', end='')    
        self.functions.print_cmd_status({
            **progress,
            "status": "complete",
            "status_color": "green",
            "newline": True,
        })
        sleep(.5)
        self.functions.print_cmd_status({
            **progress2,
            "status": "complete",
            "status_color": "green",
            "newline": True,
        })
        
        self.service_file_manipulation() # default directories are setup in the verify_directories method
       
        progress = {
            "text_start": "Removing old tmp files",
            "status": "running",
            "status_color": "yellow",
        }
        self.functions.print_cmd_status(progress)
        # remove any private key file info to keep
        # security a little more cleaned up
        if path.isfile(f"{self.p12.p12_file_location}/id_ecdsa.hex"):
            remove(f"{self.p12.p12_file_location}/id_ecdsa.hex")

        files = [
            "/var/tmp/cnng-*",
            "/var/tmp/cn-*",
            "/var/tmp/sshd_config*",
        ]
        for file in files:
            self.functions.remove_files(None,"modify_dynamic_elements",file)

        self.log.logger.debug("upgrader -> cleaning up seed list files from root of [/var/tessellation]")
        
        for env in ["testnet","mainnet","integrationnet"]:
            if path.isfile(f"/var/tessellation/{env}-seedlist"):
                remove(f"/var/tessellation/{env}-seedlist")

        # move temp rewritten rc files to backup
        rc_file_name = "{"+"}"+".bashrc*"
        _ = self.functions.process_command({
            "bashCommand": f'sudo mv /home/{self.p12.p12_username}/{rc_file_name} {self.config_obj[self.functions.default_profile]["directory_backups"]}',
            "proc_action": "subprocess_devnull",
        })

        # bug from previous < v2.13.4
        for i_path in ["/root/'2>&1'",f"/home/{self.p12.p12_username}/'2>&1'","/root/2>&1",f"/home/{self.p12.p12_username}/2>&1"]:
            if path.exists(i_path):
                rmtree(i_path)

        self.functions.print_cmd_status({
            **progress,
            "status": "complete",
            "status_color": "green",
            "newline": True,
        })

        remove_ntp_services(self.log)
        handle_time_setup(self.functions,False,self.non_interactive,False,self.log)
        self.handle_auto_complete()

        result = False
        if not self.nodectl_only:
            for profile in self.functions.profile_names:
                if self.config_obj[profile]["layer"] < 1:
                    result = self.cli.cli_execute_directory_restructure(
                        profile,
                        self.profile_progress[profile]["download_version"],
                        self.non_interactive
                    )
                    result_color = "yellow"
                    if result == "not_needed": 
                        result_color = "green"
                    elif result: 
                        result = "Successful"
                        result_color = "green"
                    elif not result:
                        result = "Failed"
                        result_color = "red"

                    if result and (self.environment == "testnet" or "v3" == self.profile_progress[profile]["download_version"][:2]):
                        residual_color = "green"
                        residual_status = "cleanup_not_needed"

                        with ThreadPoolExecutor() as executor0:
                            self.functions.status_dots = True
                            prep = {
                                "text_start": "Testing Migration Data",
                                "status": "running",
                                "status_color": "yellow",
                                "dotted_animation": True,
                                "newline": False,
                            }
                            _ = executor0.submit(self.functions.print_cmd_status,prep) 

                            if path.exists(f'{self.config_obj[profile]["directory_inc_snapshot"]}/ordinal') and path.exists(f'{self.config_obj[profile]["directory_inc_snapshot"]}/hash'):
                                for item in listdir(self.config_obj[profile]["directory_inc_snapshot"]):
                                    item_path = path.join(self.config_obj[profile]["directory_inc_snapshot"], item)
                                    if not path.isdir(item_path):
                                        residual_color = "red"
                                        residual_status = "needs_cleanup"
                                        break
                            else:
                                residual_color = "red"
                                residual_status = "migration_failure"

                            self.functions.status_dots = False
                            self.functions.print_cmd_status({
                                **prep,
                                "newline": True,
                                "status": "complete",
                                "status_color": "green",
                                "dotted_animation": False,
                            })  

                        self.functions.print_cmd_status({
                            "text_start": "Residual snapshot",
                            "brackets": "v2 to v3",
                            "status": residual_status,
                            "status_color": residual_color,
                            "newline": True,
                        })

                        if residual_status == "migration_failure":
                            self.functions.print_paragraphs([
                                ["",1], [" WARNING ",0,"yellow,on_red","bold"], ["This node's data structure appears not to have been migrated from Tessellation",0,"yellow"],
                                ["v2.x.x",0,"red"], ["to",0,"yellow"], ["v3.x.x",0,"red"], ["properly. It is recommended that you rerun the upgrade at your earliest convenience.",2,"yellow"],
                                ["You may also option to run the migration directly and then restart of the node, using the following commands:",1,"magenta"],
                                ["sudo nodectl migration_datadir -p <profile_name>",1],
                                ["sudo nodectl restart -p all",2],
                            ])

                        clean_residual = False
                        if not self.non_interactive:
                            if residual_status != "migration_failure": print()
                            self.functions.print_paragraphs([
                                ["nodectl completed a migration of the snapshot data structure required for this version of Tessellation",2,"magenta"],

                                ["There may be some residual old snapshots present.",1,"magenta"],
                                ["nodectl can attempt to clean up and free disk space",2,"magenta"],

                                ["   Migration Status:",0], [result,1,result_color,"bold"],
                                ["Residual Data Found:",0], [residual_status,2,residual_color,"bold"],

                                [" WARNING ",0,"red,on_yellow"],["Do not attempt to remove residual old snapshots if the status of migration is",0,"red"],
                                ["not",0,"magenta","bold"], ["completed.",2,"red"],
                            ])
                            if self.functions.confirm_action({
                                "yes_no_default": "y",
                                "return_on": "y",
                                "prompt": "Attempt to clean any residual snapshots?",
                                "prompt_color": "cyan",
                                "exit_if": False,
                            }): clean_residual = True

                        if clean_residual:
                            with ThreadPoolExecutor() as executor0:
                                self.functions.status_dots = True
                                do_exe = {
                                    "text_start": "Cleaning up residual snapshots",
                                    "status": "running",
                                    "dotted_animation": True,
                                    "status_color": "yellow",
                                    "newline": False,
                                }
                                _ = executor0.submit(self.functions.print_cmd_status,do_exe)

                                for item in listdir(self.config_obj[profile]["directory_inc_snapshot"]):
                                    item_path = path.join(self.config_obj[profile]["directory_inc_snapshot"], item)
                                    if not path.isdir(item_path):
                                        remove(item_path)  

                                self.functions.status_dots = False
                                self.functions.print_cmd_status({
                                    **do_exe,
                                    "status": "complete",
                                    "dotted_animation": False,
                                    "newline": True,
                                    "status_color": "green",
                                })                                     

             
    def service_file_manipulation(self):
        # version older than 0.15.0 only
        self.log.logger.warning(f"upgrader removing older <2.x.x service file if exists.")
        
        # legacy service files
        progress = {
            "status": "running",
            "text_start": "Removing older",
            "brackets": "Tessellation",
            "text_end": "files",
        }
        self.functions.print_cmd_status(progress)
        files = ["node.service","node_l0.service","node_l1.service"]
        for file in files:
            if path.isfile(f"/etc/systemd/system/{file}"):
                remove(f"/etc/systemd/system/{file}")

        self.functions.print_cmd_status({
            **progress,
            "status": "complete",
            "newline": True
        })
        
        # legacy bash files
        progress = {
            "status": "running",
            "text_start": "Removing older nodectl",
            "brackets": "bash",
            "text_end": "files",
        }
        self.functions.print_cmd_status(progress)

        files = ["cn-node-l0","cn-node-l1"]
        for file in files:
            if path.isfile(f"/usr/local/bin/{file}"):
                remove(f"/usr/local/bin/{file}")

        self.functions.print_cmd_status({
            **progress,
            "status": "complete",
            "newline": True
        })

        self.log.logger.info(f"upgrader refactoring service files based on cn-config.yaml as necessary.")
        progress = {
            "status": "running",
            "text_start": "Building >v2.0.0 Services Files",
            "right_just": 54,
        }
        self.functions.print_cmd_status(progress)
        
        self.cli.node_service.build_service(True) # True to rebuild restart_service
        self.functions.print_cmd_status({
            **progress,
            "status": "complete",
            "newline": True
        })
        
        self.log.logger.info(f"upgrader checking for profile name and/or service files changes from the cn-config.yaml.")
        self.functions.print_paragraphs([
            ["In the event that the configuration yaml services changed nodectl will attempt to clean up old service files.",1,"blue","bold"],
        ])
        
        progress = {
            "status": "running",
            "text_start": "Clean up config yaml changes v2.0.0",
        }
        self.functions.print_cmd_status(progress)
        sleep(.8)
        self.functions.print_clear_line()
        
        self.config_change_cleanup()
        self.functions.print_cmd_status({
            **progress,
            "status": "complete",
            "newline": True
        })        


    def update_system_prompt(self):
        username = self.functions.config_obj["global_p12"]["nodeadmin"]
        self.functions.set_system_prompt(username)
            
            
    def fix_swap_issues(self):
        progress = {
            "status": "running",
            "text_start": "Updating swapfile settings",
        }
        self.functions.print_cmd_status(progress)
        results = ["skip","skip"]
        
        # make permanent
        test = self.functions.test_or_replace_line_in_file({
            "file_path": "/etc/fstab",
            "search_line": "/swapfile none swap sw 0 0",                    
        })
        if not test and test != "file_not_found":
            # backup the file just in case
            copy2("/etc/fstab","/etc/fstab.bak")
            with open("/etc/fstab", 'a') as file:
                file.write("/swapfile none swap sw 0 0\n")
            results[0] = "done"
            
        test = self.functions.test_or_replace_line_in_file({
            "file_path": "/etc/sysctl.conf",
            "search_line": "vm.swappiness=",                    
        })
        if not test and test != "file_not_found":
            # backup the file just in case
            copy2("/etc/sysctl.conf","/etc/sysctl.conf.bak")
            with open("/etc/sysctl.conf", 'a') as file:
                file.write("vm.swappiness=10\n")            
        # turn it on temporarily until next reboot
        # make sure swap is on until next reboot
        for cmd in ["sysctl vm.swappiness=10","swapon /swapfile"]:
            _ = self.functions.process_command({
                "bashCommand": cmd,
                "proc_action": "subprocess_devnull",
            })
            
        if results[0] == "done" and results[1] == "done":
            result = "complete"
        elif "done"  in results:
            result = "partial"
        else:
            result = "skipped"
        
        self.log.logger.info(f"during swap fix update: update swap file [{results[0]}] and add swappiness [{results[1]}]")
        self.functions.print_cmd_status({
            **progress,
            "status": result,
            "newline": True
        })    
        self.functions.print_paragraphs([
            ["NOTE:",0,"yellow,on_magenta"], ["For partial or skipped elements, see the logs for details.",1,"yellow"],
        ])
                    
            
    def update_dependencies(self):
        if self.nodectl_only: return
        
        self.print_section("Handle Packages")
        self.functions.print_cmd_status({
            "text_start": "Download Tessellation Binaries",
            "status": "running",
            "bold": True,
            "text_color": "blue",
            "newline": True
        })

        download_version = self.profile_progress[list(self.profile_progress.keys())[0]]["download_version"]
        tools_version = self.profile_progress[list(self.profile_progress.keys())[0]]["tools_version"]

        pos = self.cli.node_service.download_constellation_binaries({
            "download_version": download_version,
            "tools_version": tools_version,
            "environment": self.environment,
            "print_version": False,
            "action": "upgrade",
        })
        print("\n"*(pos["down"]))


    def get_update_core_statuses(self, action, process, profile, status=None):
        # action = get or update
        # process = leave, stop, start, join
        # status = True or False
        if action == "get": return self.profile_progress[profile][process]
        
        self.profile_progress[profile][process] = status
        return
            
                
    def reload_node_service(self):
        self.log.logger.info("reloading systemctl service daemon")
        progress = {
            "text_start": "Reload the Node's services",
            "status": "running",
        }
        self.functions.print_cmd_status(progress)

        _ = self.functions.process_command({
            "bashCommand": "sudo systemctl daemon-reload",
            "proc_action": "subprocess_devnull",
        })
        sleep(1)
        self.functions.print_cmd_status({
            **progress,
            "status": "complete",
            "newline": True
        })
        
        # version 2.10.0 requirement
        self.log.logger.info("starting systemctl versioning service")
        progress = {
            "text_start": "Starting versioning updater",
            "status": "running",
        }
        self.functions.print_cmd_status(progress)

        for cmd in ["enable node_version_updater.service","restart node_version_updater.service"]:
            _ = self.functions.process_command({
                "bashCommand": f"sudo systemctl {cmd}",
                "proc_action": "subprocess_devnull",
            })            
            sleep(.5)

        self.functions.print_cmd_status({
            **progress,
            "status": "complete",
            "newline": True
        })
        
        
    def start_node_service(self,profile):
        if not self.get_update_core_statuses("get","start_complete",profile):
            self.get_update_core_statuses("update","start_complete",profile,True)
            self.cli.set_profile(profile)
            self.cli.cli_start({
                "argv_list": [],
                "wait": False,
                "static_nodeid": self.node_id if self.all_global else False,
                "threaded": True,
                "node_id": self.node_id,
            })
    
            
    def check_for_api_readytojoin(self,profile):
        if self.profile_progress[profile]["join_complete"]: return
        
        self.cli.node_service.set_profile(profile)
        self.cli.set_profile(profile)
        
        cmd_status = {
            "text_start": "Checking for",
            "brackets": "ReadyToJoin",
            "status": "running",
            "text_end": "state"
        }
        self.functions.print_cmd_status(cmd_status)

        self.get_update_core_statuses(
            "update",
            "ready_to_join",
            profile,self.cli.node_service.check_for_ReadyToJoin("upgrade")
        )
        
        color = "red"
        state = "failed"
        if self.get_update_core_statuses("get", "ready_to_join", profile):
            color = "green"
            state = "ReadyToJoin"
        
        self.functions.print_cmd_status({
            **cmd_status,
            "status": state,
            "status_color": color,
            "newline": True
        })
        
        service = self.functions.pull_profile({
            "req": "service",
            "profile": profile,
        })
        self.log.logger.info(f'check for api results: service [{service}] state [{state}]')


    def check_for_link_success(self,profile):
        try:
            for link_type in self.link_types:
                if self.config_obj[profile][f"{link_type}_link_enable"]:
                    link_profile = self.config_obj[profile][f"{link_type}_link_profile"]
                    if not self.profile_progress[link_profile]["ready_to_join"]:
                        return link_type
        except Exception as e:
            self.log.logger.error(f"upgrader ran into error on check_for_link_success | error [{e}]")
            
        return False

        
    def re_join_tessellation(self,profile):
        if not self.get_update_core_statuses("get","join_complete",profile):
            self.get_update_core_statuses("update","join_complete",profile,True)
            join_check_error = self.check_for_link_success(profile)
            if not join_check_error:    
                self.cli.node_service.set_profile(profile)
                self.cli.set_profile(profile)
                self.log.logger.info(f"attempting to rejoin to [{profile}]")
                if self.profile_progress[profile]["ready_to_join"]:   
                    self.functions.print_paragraphs([
                        ["Please wait while [",0], [profile,-1,"yellow","bold"], ["] attempts to join the network.",-1],["",1],
                    ])
                    if self.config_obj[profile]["gl0_link_enable"] or self.config_obj[profile]["ml0_link_enable"]:
                        self.functions.print_paragraphs([
                            [" NOTE ",0,"yellow,on_magenta","bold"], ["ml0 or ml1",0,"cyan"], ["networks will not join the Hypergraph until its",0],
                            ["gl0 or ml0",0,"cyan"], ["linked profile changes to",0], ["Ready",0,"green","bold"], ["state, this could take up to a",0],
                            ["few",0,"cyan",], ["minutes.",1]
                        ])
                    
                    self.cli.cli_join({
                        "skip_msg": False,
                        "wait": False,
                        "upgrade": True,
                        "caller": "upgrade",
                        "single_profile": False,
                        "watch": self.watch,
                        "dip": self.show_download_status,
                        "interactive": False if self.non_interactive else True,
                        "argv_list": ["-p",profile]
                    })
                else:
                    self.log.logger.warning(f"There was an issue found with the API status [{profile}]")
                    self.functions.print_paragraphs([
                        ["Issues were found with the API while attempting to join [",0,"red"], [profile,0,"yellow"],
                        ["]. The join process cannot be completed for this profile.  Continuing upgrade...",2,"red"],
                    ])
            else:
                self.functions.print_paragraphs([
                    [" ERROR ",0,"yellow,on_red"], ["This profile [",0,"red"], [profile,0,"yellow"], ["] cannot initiate the join",0,"red"],
                    ["process because it has a",0,"red"], [join_check_error.upper(),0,"yellow"], ["dependency.",0,"red"],
                    [f"The profile associated with this {join_check_error.upper()} dependency is not in",0,"red"], ["Ready",0,"green"],
                    ["state.",1,"red"],
                    ["Please try again later... Continuing upgrade...",1,"yellow"]
                ])
                if not self.non_interactive: self.functions.print_any_key({})
                
    
    def complete_process(self):
        self.functions.print_clear_line()
        states = self.functions.get_node_states("on_network",True)
        
        if self.nodectl_only:
            print("")
            self.cli.show_system_status({
                "rebuild": False,
                "wait": False,
                "print_title": False,
                "-p": "empty",
                "called": "_qs",
            })
            self.functions.print_paragraphs([ 
                ["nodectl only",0,"yellow","bold"], ["upgrade process completed!",1,"green","bold"],
            ])            
        else:
            for profile_list in self.profile_items:
                for item in profile_list:
                    if not self.get_update_core_statuses("get","complete_status",item["profile"]):
                        self.get_update_core_statuses("update","complete_status",item["profile"],True)   
                        self.cli.set_profile(item["profile"])
                        state = self.functions.test_peer_state({
                            "caller": "upgrade",
                            "profile": item["profile"],
                            "simple": True
                        })
                        if state not in states:
                            self.log.logger.warning("There may have been a timeout with the join state during installation")
                            self.functions.print_paragraphs([
                                ["An issue may have been found during this upgrade",1,"red","bold"],
                                ["Profile:",0,"magenta"],[item['profile'],1,"yellow","bold"],
                                ["sudo nodectl status",0], ["- to verify status.",1,"magenta"],
                                ["sudo nodectl show_profile_issues -p <profile_name>",0], ["- to verify cause.",1,"magenta"]
                            ])
                        else:    
                            self.functions.print_paragraphs([ 
                                [item["profile"],0,"yellow","bold"], ["upgrade process completed!",1,"green","bold"],
                            ])
        
        self.log.logger.info("upgrade -> force update of versioning object after upgrade.")
        from .shell_handler import ShellHandler
        shell = ShellHandler({
            "config_obj": self.config_obj
            },False)
        shell.argv = []
        shell.called_command = "upgrade"
        shell.handle_versioning()
        
        self.log.logger.info("Upgrade completed!")
        self.functions.print_paragraphs([
            ["Upgrade has completed!",2,"green","bold"],
            ["Optionally, please log out and back in in order to update your environment to teach nodectl about any new auto_completion tasks.",2,"yellow"]
        ])

        if path.exists('/var/run/reboot-required'):
            self.functions.print_paragraphs([
                [" IMPORTANT ",0,"yellow,on_blue"], 
                ["nodectl determined that VPS distribution level modifications may not have been applied yet. A",0,"blue","bold"],
                ["reboot",0,"red","bold"],["is necessary.",0,"blue","bold"],
                ["Recommended:",0], ["sudo nodectl reboot",2,"magenta"],
            ])
        
        
    def print_warning_for_old_code(self):
        self.log.logger.warning("A legacy service was found [node.service]")
        self.functions.print_paragraphs([
            ["This seems to be an older Node? Please make sure you adhere to the correct upgrade path.  Unexpected results may ensue, if this upgrade is continued.",1,"red"],
        ])
        
    
    def config_change_cleanup(self):
        ignore_sub_list = []
        ignore_sub_list2 = []
        for profile in self.functions.config_obj.keys():
            for key, value in self.functions.config_obj[profile].items():
                if key == "service":
                    ignore_sub_list.append(f"cnng-{value}.service")
                    ignore_sub_list2.append(f"cnng-{value}")

        ignore_list = [ignore_sub_list,ignore_sub_list2]
        arg_list = ["-t","config_change"]
        if self.non_interactive: arg_list.append("--ni")
        self.cli.clean_files({
            "action": "config_change",
            "time_check": -1,
            "non"
            "ignore_list": ignore_list,
            "argv_list": arg_list,
        })
        
    
    def setup_argv_list(self):
        input_error = False

        self.safe_to_upgrade = True
        self.watch, self.show_list, self.show_download_status = False, False, False
        self.nodectl_only, self.non_interactive, self.download_version, self.forced = False, False, False, False
        
        def print_argv(brackets):
            self.functions.print_cmd_status({
                "text_start": "Enabling option",
                "brackets": brackets,
                "status": "complete",
                "status_color": "green",
                "newline": True   
            })

        if "-f" in self.argv_list:
            self.forced = True    
            print_argv("forced")      
        if "-w" in self.argv_list:
            self.watch = True
            print_argv("watch")
        if "-l" in self.argv_list:
            self.show_list = True
            print_argv("show lists")
        if "--dip" in self.argv_list:
            self.show_download_status = True
            print_argv("dip watch")
        if "--nodectl_only" in self.argv_list or "--nodectl-only" in self.argv_list:
            self.nodectl_only = True
            print_argv( "nodectl_only")
        if "-ni" in self.argv_list or "--ni" in self.argv_list:
            self.non_interactive = True 
            print_argv("non-interactive")     

        if "-v" in self.argv_list:
            if self.argv_list.count("-v") > 1:
                extra = "all -v <version> must be preceded by accompanying -p <profile>"
                if self.argv_list.count("-v") != self.argv_list.count("-p"): input_error = True
        
                if not input_error:
                  for arg in self.argv_list:
                      if arg == "-p":
                          # if the profile doesn't exist shell_handler will intercept
                          profile = self.argv_list[self.argv_list.index("-p")+1]
                          if self.argv_list[self.argv_list.index("-p")+2] != "-v": input_error = True
                          version = self.argv_list[self.argv_list.index("-p")+3]
                          if not self.forced:
                            if not self.functions.is_version_valid(version): input_error = True
                          if input_error: break
        
                if not input_error:
                    while True:
                        for arg in self.argv_list:
                            if arg == "-p":
                                profile = self.argv_list[self.argv_list.index("-p")+1]
                                version = self.argv_list[self.argv_list.index("-p")+3]
                                break
                        if not "-p" in self.argv_list: break
                        del self.argv_list[self.argv_list.index("-p"):self.argv_list.index("-p")+4]
                        if not input_error: self.profile_progress[profile]["download_version"] = version              
                              
            else:
                self.download_version = self.argv_list[self.argv_list.index("-v")+1]
                if not self.functions.is_version_valid(self.download_version) and not self.forced: 
                    input_error = True
                    extra = "-v <version format vX.X.X>"
            
        if input_error:        
            self.error_messages.error_code_messages({
                "error_code": "upg-550",
                "line_code": "input_error",
                "extra": "upgrade option error",
                "extra2": extra,
            })
            
        if "--pass" in self.argv_list:
           self.cli_global_pass = self.argv_list[self.argv_list.index("--pass")+1]            
                
                    
    def node_id_error_handler(self,count):
        count_max = 4
        self.functions.print_paragraphs([
            ["",1],["Unable to obtain node id... ",1,"red","bold"], ["attempt [",0,"red","bold"], [f"{count}",-1,"yellow","bold"],
            ["] of [",-1,"red","bold"], [f"{count_max}",-1,"yellow","bold"], ["]",-1,"red","bold"], ["",1],
        ])
        if count > count_max-1:
            self.functions.status_dots = False
            self.error_messages.error_code_messages({
                "error_code": "upg-574",
                "line_code": "node_id_issue",
                "extra": "upgrader"
            })
        sleep(2)
        return count+1
    
    
    def p12_encrypt_passphrase(self):
        # because encryption will change the cn-config.yaml values to avoid processing necessary
        # to rebuild the configuration file after-the-fact, this feature is offered last.

        if self.config_obj["global_p12"]["encryption"]:
            self.log.logger.debug("upgrader -> nodectl detected encryption is already enabled, skipping.")
            return
        
        self.functions.print_header_title({
            "line1": "ENCRYPTION SERVICES",
            "single_line": True,
            "newline": "both"
        })
        self.functions.print_paragraphs([
            [" NEW ",0,"grey,on_green"], ["to nodectl >2.13.x",2,"green","bold"],

            ["Do you want to encrypt the passphrase in your",0,"magenta"],
            ["cn-config.yaml",0,"yellow"], ["configuration file?",1,"magenta"],
        ])
        if self.non_interactive:
            self.log.logger.warning("upgrade -> non-interactive mode detected, encryption of passphrase feature skipped.")
            self.functions.print_paragraphs([
                ["non-interactive mode detected, nodectl is skipping passphrase and encryption request.",1,"red"]
            ])
            return

        if self.functions.confirm_action({
            "yes_no_default": "y",
            "return_on": "y",
            "prompt": "Enable encrypt?",
            "prompt_color": "cyan",
            "exit_if": False,
        }):
            self.configurator = Configurator(["--upgrader"])
            self.configurator.detailed = True
            self.configurator.metagraph_list = self.functions.profile_names
            self.configurator.c.config_obj = deepcopy(self.config_obj)
            self.configurator.prepare_configuration("edit_config")
            self.configurator.passphrase_enable_disable_encryption("upgrade")


    def handle_auto_complete(self):
        self.log.logger.info("upgrader -> updating/creating auto_complete script")

        progress = {
            "text_start": "Applying auto_complete updates",
            "status": "running",
            "status_color": "yellow",
            "newline": False,
        }
        self.functions.print_cmd_status({
            **progress,
            "delay": .8,
        })

        auto_path = ac_validate_path(self.log,"upgrader")
        auto_complete_file = ac_build_script(self.cli,auto_path)
        ac_write_file(auto_path,auto_complete_file,self.functions)

        self.functions.print_cmd_status({
            **progress,
            "status": "complete",
            "status_color": "green",
            "newline": True,
        })

        
if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")        
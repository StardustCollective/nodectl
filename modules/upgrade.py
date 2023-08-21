from concurrent.futures import ThreadPoolExecutor
from os import system, path, makedirs, remove
from time import sleep
from termcolor import colored, cprint
from re import match
from types import SimpleNamespace
from hurry.filesize import size, alternative
from copy import deepcopy

from .functions import Functions
from .troubleshoot.errors import Error_codes
from .p12 import P12Class
from .command_line import CLI
from .troubleshoot.logger import Logging
from .config.config import Configuration


class Upgrader():

    def __init__(self,command_obj):
        self.log = Logging()
        self.log.logger.info("System Upgrade called, initializing upgrade.")
        
        self.config_obj = command_obj.get("config_obj")
        self.ip_address = command_obj.get("ip_address")
        self.version_obj = command_obj.get("version_obj")
        self.called_command = command_obj.get("called_command")
        self.environment = command_obj.get("environment")
        self.argv_list = command_obj.get("argv_list")

        self.non_interactive = self.download_version = self.forced = False
        self.debug = command_obj.get("debug",False)
        
        self.step = 1
        self.status = "" #empty
        self.node_id = ""
        self.safe_to_upgrade = True
        self.final_upgrade_status_list = []
        self.api_ready_list = {}
        self.profile_progress = {}     
        
        self.error_messages = Error_codes() 
        self.functions = Functions(self.config_obj) # all refs to config_obj should be from functions
        
        self.command_obj = {
            **command_obj,
            "caller": "upgrader",
            "command": "upgrade",
        }
        self.cli = CLI(self.command_obj)
        self.cli_global_pass = False
        

    def build_p12_obj(self):
        p12_obj = {
            "caller": "upgrader",
            "action": "upgrade",
            "operation": "upgrade",
            "config_obj": self.functions.config_obj,
            "cli_obj": self.cli,
        }
        self.p12 = P12Class(p12_obj)   
        
        
    def build_cli_obj(self):
        command_obj = {
            **self.command_obj,
            "config_obj": self.functions.config_obj,
            "profile_names": self.functions.profile_names,
            "caller": "upgrader",
            "command": "upgrade",
        }
        self.cli = CLI(command_obj)
                
                
    def upgrade_process(self):

        self.setup_argv_list()
        self.handle_profiles()
        self.handle_verification()
        
        self.build_p12_obj()
        self.build_cli_obj()

        self.get_node_id()    
          
        self.print_section("Handle Node Versioning")
        self.request_version()
        
        self.print_section("Take Node Offline")
        self.leave_cluster() # async_session_one
        self.stop_service() # async_session_two

        self.print_section("Node Internal Configuration")
        self.verify_directories()
        self.modify_dynamic_elements()
        self.upgrade_log_archive()  # must be done after modify to accept new config dir
                
        self.print_section("Handle Packages")
        self.update_dependencies()      

        self.print_section("Bring Node Back Online")
        self.reload_node_service()
  
        for profile_list in self.profile_items:
            for item in reversed(profile_list):
                self.start_node_service(item["profile"])
                self.check_for_api_readytojoin(item["profile"],item["service"])
                self.re_join_tessellation(item["profile"])
        
        self.complete_process()
    
    
    def handle_profiles(self):
        profile_items = self.functions.pull_profile({"req": "pairings"})
        
        self.profiles_by_env = list(self.functions.pull_profile({
            "req": "profiles_by_environment",
            "environment": self.environment
        }))
        
        # remove any profiles that don't belong to this environment
        for n, profile_list in enumerate(profile_items):
            for i, profile in enumerate(profile_list):
                if profile["profile"] not in self.profiles_by_env: profile_items.pop(n)
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
                
        self.profile_items = profile_items
        
        
    def handle_verification(self):
        self.print_section("Verify Node Upgrade")
        
        progress = {
            "text_start": "Verify upgrade paths",
            "status": "running",
            "status_color": "yellow"
        }
        self.functions.print_cmd_status(progress)
        self.cli.check_nodectl_upgrade_path({
            "called_command": "upgrade",
            "version_obj": self.version_obj,
            "argv_list": []
        })
        self.functions.print_cmd_status({
            **progress,
            "status": "complete",
            "status_color": "green",
            "newline": True,
        })
        
        self.config_copy = deepcopy(self.functions.config_obj)
        verify = Configuration({
            "implement": False,
            "action": "configure",
            "argv_list": ["None"]
        })
        verify.config_obj = {
            **verify.config_obj,
            **self.functions.config_obj,
            "upgrader": True
        }

        pass_vault = {}
        for p in self.profiles_by_env:
            if not self.functions.config_obj[p]["global_p12_passphrase"]:
                pass_vault[p] = verify.config_obj[p]["p12_passphrase"]
                verify.config_obj[p]["p12_passphrase"] = "None"
            if self.functions.config_obj[p]["global_p12_cli_pass"]:
                verify.config_obj["global_p12"]["passphrase"] = self.cli_global_pass
        pass_vault["global"] = verify.config_obj["global_p12"]["passphrase"]
        verify.config_obj["global_p12"]["passphrase"] = "None"
        verify.metagraph_list = self.profiles_by_env
        
            
        verify.prepare_p12()
        verify.setup_passwd()
        
        # reset the passphrases
        for profile in self.profiles_by_env:
            if self.functions.config_obj[profile]["p12_passphrase"] == "None":
                reset_pass = pass_vault["global"]
                if not self.functions.config_obj[profile]["global_p12_passphrase"]:
                    reset_pass = pass_vault[profile]
                self.functions.config_obj[profile]["p12_passphrase"] = reset_pass
                
        if not self.functions.config_obj["global_p12"]["passphrase"] or self.functions.config_obj["global_p12"]["passphrase"] == "None":
            self.functions.config_obj["global_p12"]["passphrase"] = pass_vault['global']

            
    def print_section(self,line):
        self.functions.print_header_title({
            "line1": line,
            "newline": "both",
            "single_line": True,
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
                    "is_global": False,
                    "profile": profile,
                })
                result = 1

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

        if self.functions.config_obj["global_elements"]["all_global"]:
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
        self.version_obj["cluster_tess_version"] = self.functions.get_version({"which": "cluster_tess"})
        
        for profile in self.profile_progress.keys():
            
            self.functions.print_paragraphs([
                ["PROFILE:   ",0], [profile,1,"yellow","bold"], 
                ["METAGRAPH: ",0],[self.environment,2,"yellow","bold"],
            ])
            
            found_tess_version = self.version_obj['cluster_tess_version'][profile]
            running_tess_version = self.version_obj["node_tess_version"][profile]["node_tess_version"]
            self.log.logger.info(f"upgrade handling versioning: profile [{profile}] latest [{found_tess_version}] current: [{running_tess_version}]")
            
            self.functions.print_cmd_status({
                "status": found_tess_version,
                "text_start": "The latest Tess version",
                "brackets": profile,
                "result_color": "green",
                "newline": True
            })
            
            if running_tess_version.lower() == "v":
                self.version_obj['node_tess_version'] = "unavailable" 
                
            self.functions.print_cmd_status({
                "status": running_tess_version,
                "text_start": "Tessellation version running currently",
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
                
            self.functions.print_paragraphs([
                ["Press enter to accept the default value between",0], ["[]",0,"white"], ["brackets.",1]
            ])
                
            while True:
                if not self.profile_progress[profile]["download_version"]:
                    version_str = colored("  Please enter version to upgrade to".ljust(45,"."),"cyan")+"["+colored(found_tess_version,"yellow",attrs=['bold'])+"] : "
                    download_version = input(version_str)
                if not download_version:
                    download_version = found_tess_version
                    break
                else:
                    if not self.forced:
                        if download_version[0] == "V":
                            download_version = download_version.replace("V","v")
                        elif download_version[0] != "v": 
                            download_version = f"v{download_version}"
                        
                    if self.functions.is_version_valid(download_version):
                        confirm = True
                        if self.forced:
                            self.functions.print_paragraphs([
                                [" WARNING ",0,"red,on_yellow"], ["forcing to version [",0,"yellow"],
                                [download_version,-1,"cyan","bold"], ["]",-1,"yellow"],["",1],
                            ])
                        else:
                            if found_tess_version != download_version:
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
                "text_start": "Using version",
                "result_color": "green",
                "newline": True
            })  
            self.profile_progress[profile]["download_version"] = download_version
            self.functions.print_paragraphs([
                ["",1], ["=","full","blue","bold"],["",1],
            ])

            
    def leave_cluster(self):
        # < 2.0.0  shutdown legacy  
        with ThreadPoolExecutor() as executor:
            for profile_list in self.profile_items:
                for item in profile_list:
                    if not self.get_update_core_statuses("get","leave_complete",item["profile"]):
                        self.get_update_core_statuses("update","leave_complete",item["profile"],True)
                        cli = CLI(self.command_obj) # rebuild
                        cli.set_profile(item["profile"])
                        print_timer = True if item["profile"] == profile_list[-1]["profile"] else False
                        leave_obj = {
                            "secs": 30,
                            "reboot_flag": False,
                            "skip_msg": False,
                            "print_timer": print_timer
                        }
                        executor.submit(cli.cli_leave, leave_obj)
                        sleep(1.5)
    
            
    def stop_service(self):
        with ThreadPoolExecutor() as executor:
            for profile_list in self.profile_items:
                for item in profile_list:
                    if not self.get_update_core_statuses("get","stop_complete",item["profile"]):
                        self.get_update_core_statuses("update","stop_complete",item["profile"],True)
                        if path.exists(f"/etc/systemd/system/cnng-{item['service']}.service") or path.exists(f"/etc/systemd/system/{item['service']}.service"): # includes legacy < v2.0.0
                            cli = CLI(self.command_obj)
                            cli.set_profile(item["profile"])
                            stop_obj = {
                                "show_timer": False,
                                "argv_list": []
                            }
                            executor.submit(cli.cli_stop,stop_obj)
                            sleep(1.5)
                        else:
                            self.functions.print_paragraphs([
                                ["unable to fine [",0,"red"], [item['service'],-1,"yellow","bold"],
                                ["] on this Node.",-1,"red"],["",1],
                            ])

 
    def upgrade_log_archive(self):
        self.log.logger.info(f"logging and archiving prior to update.")

        to_clear = ["backups","uploads","logs"]
        action = "upgrade"
        days = 30
        for item in to_clear:
            self.functions.print_header_title({
                "line1": f"Clean up {item}",
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

            argv_list = ["-ni","-t", item, "-d", days] if self.non_interactive else ["-t", item, "-d", days]
                
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
        backup = False
        confirm = True if self.non_interactive else False

        # version 2.9.0
        progress = {
            "text_start": "Removing old default seed file",
            "status": "running",
            "status_color": "yellow",
        }
        self.functions.print_cmd_status(progress)
        if path.exists("/var/tessellation/seed-list"):
            remove("/var/tessellation/seed-list")
            
        self.functions.print_cmd_status({
            **progress,
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
            remove(f"{self.p12.p12_file_location}/id_ecdsa.hex > /dev/null 2>&1")
        system(f"rm -f /var/tmp/cnng-* > /dev/null 2>&1")
        system(f"rm -f /var/tmp/cn-* > /dev/null 2>&1")

        self.functions.print_cmd_status({
            **progress,
            "status": "complete",
            "status_color": "green",
            "newline": True,
        })
        
             
    def service_file_manipulation(self):
        # version older than 0.15.0 only
        self.log.logger.warn(f"upgrader removing older <2.x.x service file if exists.")
        
        # legacy service files
        progress = {
            "status": "running",
            "text_start": "Removing older Tessellation",
            "brackets": "Tessellation",
            "text_end": "files",
        }
        self.functions.print_cmd_status(progress)
        files = ["node.service","node_l0.service","node_l1.service"]
        for file in files:
            if path.isfile(f"/etc/systemd/system/{file}"):
                system(f"rm -f /etc/systemd/system/{file} > /dev/null 2>&1")

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
            system("cp /etc/fstab /etc/fstab.bak > /dev/null 2>&1")
            system("echo '/swapfile none swap sw 0 0' | tee -a /etc/fstab > /dev/null 2>&1")
            results[0] = "done"
            
        test = self.functions.test_or_replace_line_in_file({
            "file_path": "/etc/sysctl.conf",
            "search_line": "vm.swappiness=",                    
        })
        if not test and test != "file_not_found":
            # backup the file just in case
            system("cp /etc/sysctl.conf /etc/sysctl.conf.bak > /dev/null 2>&1")
            system("echo 'vm.swappiness=10' | tee -a /etc/sysctl.conf > /dev/null 2>&1")
            
        # turn it on temporarily until next reboot
        system("sysctl vm.swappiness=10 > /dev/null 2>&1")
        # make sure swap is on until next reboot
        system("swapon /swapfile > /dev/null 2>&1")
            
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
        self.functions.print_cmd_status({
            "text_start": "Download",
            "text_end": "Constellation Network Tessellation Binaries",
            "status": "running",
            "bold": True,
            "text_color": "blue",
            "newline": True
        })

        self.cli.node_service.download_constellation_binaries({
            "download_version": self.download_version,
            "environment": self.environment,
            "print_version": False,
            "action": "upgrade",
        })


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

        system("sudo systemctl daemon-reload > /dev/null 2>&1")
        sleep(1)
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
                "wait": False
            })
            if self.functions.config_obj[profile]["layer"] > 0:
                self.functions.print_timer(5,"wait for restart",1)
    
            
    def check_for_api_readytojoin(self,profile,service):
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
        
        self.log.logger.info(f'check for api results: service [{service}] state [{state}]')
                
        
    def re_join_tessellation(self,profile):
        if not self.get_update_core_statuses("get","join_complete",profile):
            self.get_update_core_statuses("update","join_complete",profile,True)        
            self.cli.node_service.set_profile(profile)
            self.cli.set_profile(profile)
            self.log.logger.info(f"attempting to rejoin to [{profile}]")
            if self.profile_progress[profile]["ready_to_join"]:   
                self.functions.print_paragraphs([
                    ["Please wait while [",0], [profile,-1,"yellow","bold"], ["] attempts to join the network.",-1],["",1],
                ])
                if self.config_copy[profile]["gl0_link_enabled"] or self.config_copy[profile]["ml0_link_enabled"]:
                    self.functions.print_paragraphs([
                        [" NOTE ",0,"yellow,on_magenta","bold"], ["ml0 or ml1",0,"cyan"], ["networks will not join the Hypergraph until its",0],
                        ["gl0 or ml0",0,"cyan"], ["linked profile changes to",0], ["Ready",0,"green","bold"], ["state, this could take up to a",0],
                        ["few",0,"cyan",], ["minutes.",1]
                    ])
                self.cli.cli_join({
                    "skip_msg": False,
                    "wait": False,
                    "upgrade": True,
                    "single_profile": False,
                    "interactive": False if self.non_interactive else True,
                    "argv_list": ["-p",profile]
                })
            else:
                self.log.logger.warn(f"There was an issue found with the API status [{profile}]")
                print(colored("  Issue found with API status","red"),colored("profile:","magenta"),colored(profile,"yellow"))
    
    
    def complete_process(self):
        self.functions.print_clear_line()
        
        for profile_list in self.profile_items:
            for item in profile_list:
                if not self.get_update_core_statuses("get","complete_status",item["profile"]):
                    self.get_update_core_statuses("update","complete_status",item["profile"],True)   
                    self.cli.set_profile(item["profile"])
                    state = self.functions.test_peer_state({
                        "profile": item["profile"],
                        "simple": True
                    })
                    states = ["Ready","Observing","WaitingForObserving","WaitingForReady","DownloadInProgress"]
                    if state not in states:
                        self.log.logger.warn("There may have been a timeout with the join state during installation")
                        self.functions.print_paragraphs([
                            ["An issue may have been found during this upgrade",1,"red","bold"],
                            ["Profile:",0,"magenta"],[item['profile'],1,"yellow","bold"],
                            ["sudo nodectl status",0], ["- to verify status.",1,"magenta"],
                            ["sudo nodectl -cc -p <profile_name>",0], ["- to verify connections.",1,"magenta"]
                        ])
                    else:
                        self.functions.print_paragraphs([ 
                            [item["profile"],0,"yellow","bold"], ["upgrade process completed!",1,"green","bold"],
                        ])
        
        self.log.logger.info("Upgrade completed!")
        cprint("  Upgrade has completed\n","green",attrs=["bold"])
        
        
    def print_warning_for_old_code(self):
        self.log.logger.warn("A legacy service was found [node.service]")
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

        self.cli.clean_files({
            "action": "config_change",
            "time_check": -1,
            "ignore_list": ignore_list,
            "argv_list": ["-t","config_change"]
        })
        
    
    def setup_argv_list(self):
        if "-f" in self.argv_list:
            self.forced = True  
        if "-v" in self.argv_list:
            self.download_version = self.argv_list[self.argv_list.index("-v")+1]
            if not self.functions.is_version_valid(self.download_version) and not self.forced:
                self.error_messages.error_code_messages({
                    "error_code": "upg-550",
                    "line_code": "input_error",
                    "extra": "-v <version format vX.X.X>"
                })
        if "-ni" in self.argv_list:
            self.non_interactive = True      
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
    
    
if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")        
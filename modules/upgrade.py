from concurrent.futures import ThreadPoolExecutor
from os import system, path, makedirs
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
        
        self.var = SimpleNamespace(**command_obj)
        self.non_interactive = self.download_version = self.forced = False
        
        self.debug = command_obj.get("debug",False)
        
        self.step = 1
        self.status = "" #empty
        self.node_id = ""
        self.safe_to_upgrade = True
        self.final_upgrade_status_list = []
        self.api_ready_list = {}
                
        self.error_messages = Error_codes() 
        self.functions = Functions(self.var.config_obj) # all refs to config_obj should be from functions
        
        self.command_obj = {
            **command_obj,
            "caller": "upgrader",
            "command": "upgrade",
        }
        self.cli = CLI(self.command_obj)
        
        self.cli_global_pass = False
        if "--pass" in self.var.argv_list:
           self.cli_global_pass = self.var.argv_list[self.var.argv_list.index("--pass")+1]
        
        self.profile_items = self.functions.pull_profile({
            "req": "pairings",
        })  
        
        self.setup_argv_list()
        

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
            "caller": "upgrader",
            "command": "upgrade",
        }
        self.cli = CLI(command_obj)
                
                
    def upgrade_process(self):

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
    
    
    def handle_verification(self):
        self.print_section("Verify Node Upgrade")
        self.version_obj = self.cli.check_nodectl_upgrade_path({
            "called_command": "upgrade",
            "argv_list": []
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
        for profile_list in self.profile_items:
            for profile in profile_list:
                p = profile["profile"]
                if not self.functions.config_obj[p]["global_p12_passphrase"]:
                    pass_vault[p] = verify.config_obj[p]["p12_passphrase"]
                    verify.config_obj[p]["p12_passphrase"] = "None"
        pass_vault["global"] = verify.config_obj["global_p12"]["passphrase"]
        verify.config_obj["global_p12"]["passphrase"] = "None"
        if self.functions.config_obj["global_cli_pass"]:
            verify.config_obj["global_p12"]["passphrase"] = self.cli_global_pass
            
        verify.prepare_p12()
        verify.setup_passwd()
        
        # reset the passphrases
        for profile_list in self.profile_items:
            for profile in profile_list:
                if self.functions.config_obj[profile['profile']]["p12_passphrase"] == "None":
                    reset_pass = pass_vault["global"]
                    if not self.functions.config_obj[p]["global_p12_passphrase"]:
                        reset_pass = pass_vault[profile['profile']]
                    self.functions.config_obj[profile['profile']]["p12_passphrase"] = reset_pass
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

        if self.functions.config_obj["all_global"]:
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
        self.log.logger.info(f"handling versioning: latest [{self.version_obj['cluster_tess_version']}] current: [{self.version_obj['node_tess_version']}]")
        self.functions.print_cmd_status({
            "status": self.version_obj['cluster_tess_version'],
            "text_start": "The following version is the latest",
            "result_color": "green",
            "newline": True
        })
        
        if self.version_obj['node_tess_version'] == "v":
            self.version_obj['node_tess_version'] = "unavailable" 
             
        self.functions.print_cmd_status({
            "status": self.version_obj['node_tess_version'],
            "text_start": "The following version is running currently",
            "status_color": "red",
            "newline": True
        })  
        
        while True:
            if not self.download_version and not self.non_interactive:
                version_str = colored("  Please enter version to upgrade to".ljust(45,"."),"cyan")+"["+colored(self.version_obj['cluster_tess_version'],"yellow",attrs=['bold'])+"] : "
                self.download_version = input(version_str)
            if not self.download_version:
                self.download_version = self.version_obj['cluster_tess_version']
                break
            else:
                if not self.forced:
                    if self.download_version[0] == "V":
                        self.download_version = self.download_version.replace("V","v")
                    elif self.download_version[0] != "v": 
                        self.download_version = f"v{self.download_version}"
                    
                if self.functions.is_version_valid(self.download_version):
                    confirm = True
                    if self.forced:
                        self.functions.print_paragraphs([
                            [" WARNING ",0,"red,on_yellow"], ["forcing to version [",0,"yellow"],
                            [self.download_version,-1,"cyan","bold"], ["]",-1,"yellow"],["",1],
                        ])
                    else:
                        if self.version_obj['cluster_tess_version'] != self.download_version:
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
                        ["version:",0,"yellow"], [self.download_version,1,"magenta"],
                    ])
                    self.functions.confirm_action({
                        "yes_no_default": "y",
                        "return_on": "y",
                        "prompt": "Continue with selected version?",
                        "exit_if": True
                    })
                    break
                
            self.functions.print_paragraphs([
                ["Invalid version [",0,"red"], [self.download_version,-1,"yellow","bold"], ["] inputted, try again",-1,"red"],["",1],
            ])
            self.download_version = False
            
        self.functions.print_cmd_status({
            "status": self.download_version,
            "text_start": "Using version",
            "result_color": "green",
            "newline": True
        })  

            
    def leave_cluster(self):
        # < 2.0.0  shutdown legacy  
        with ThreadPoolExecutor() as executor:
            for profile_list in self.profile_items:
                for item in profile_list:
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
        # this version requires an upgrade path to v1.12.0 prior to installation
        # legacy services removed
        
        with ThreadPoolExecutor() as executor:
            for profile_list in self.profile_items:
                for item in profile_list:
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

        to_clear = ["backups","uploads","logs","snapshots"]
        action = "upgrade"
        for item in to_clear:
            self.functions.print_header_title({
                "line1": f"Clean up {item}",
                "single_line": True,
                "newline": "both",
            })
                
            days = 30 if item == "snapshots" else 7
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
        # attempt to safely migrate data snapshots to new layer0 location
        self.functions.set_default_directories() # put directories into place if default
        overall_status = "complete"
        overall_status_color = "green"
        
        leg_paths = ["logs","data"]
        for leg_path in leg_paths:
            if path.isdir(f"/var/tessellation/{leg_path}/"):
                self.log.logger.warn(f"possible legacy directory [/var/tessellation/{leg_path}] found and should be removed to avoid disk capacity issues")
                if not self.non_interactive:
                    self.functions.print_paragraphs([
                        ["WARNING",0,"yellow,on_red","bold"], ["nodectl may have found a legacy directory.",2,"yellow"],
                        ["This may be due to an improper upgrade path of an older version of nodectl and may contribute to disk capacity issues.",1,"yellow"],
                        [f" /var/tessellation/{leg_path}/",1,"magenta"],
                    ])
                    
                    confirm = self.functions.confirm_action({
                        "yes_no_default": "n",
                        "return_on": "y",
                        "prompt": "Do you want to remove this directory?",
                        "exit_if": False
                    })
                    if confirm:
                        system(f"rm -rf /var/tessellation/{leg_path}/ > /dev/null 2>&1") 
                        cprint(f"  legacy {leg_path}/ directory removed","green")
                    else:
                        cprint(f"  skipped legacy {leg_path}/ removal","red")
                else:
                    # non-interactive is on
                    self.functions.print_paragraphs([
                        ["Legacy directory",0,"yellow"], [f"{leg_path}/",0,"yellow","bold"], ["found but not removed.",2,"yellow"],
                        ["Reason:",0,"blue","bold"], ["This upgrade was executed in",0,"yellow"], ["non-interactive",0,"yellow","bold"],["mode.",1,"yellow"],
                        ["See logs for details.",1,"magenta"],
                    ])
                    overall_status = "incomplete"
                    overall_status_color = "magenta"
                    
            for profile in self.functions.config_obj.keys():
                if not path.exists(f"/var/tessellation/{profile}/"):  
                    makedirs(f"/var/tessellation/{profile}/{leg_path}/")
 
        
        file_paths = ["backups","uploads"]
        for file_path in file_paths:
            for profile_list in self.profile_items:
                for item in profile_list:
                    if not path.exists(f"/var/tessellation/{file_path}/"):
                        if self.functions.config_obj[item['profile']]["dirs"][file_path] != f"/var/tessellation/{file_path}/":
                            progress = {
                                "text_start": "Directory not found",
                                "brackets": f"{file_path}/",
                                "text_end": "creating",
                                "status": "creating"
                            }
                            self.functions.print_cmd_status(progress)
                            self.functions.print_clear_line()
                            
                            bu_status = "complete"
                            bu_color = "green"
                            try:
                                makedirs(self.functions.config_obj[item['profile']][file_path])
                            except Exception as e:
                                self.log.logger.error(f"during the upgrade process nodectl could not find or create [{file_path}] due to [{e}]")
                                bu_status = "failed"
                                bu_color = "red"
                                overall_status = "incomplete"
                                overall_status_color = "magenta"
                            else:
                                self.functions.print_paragraphs([
                                    ["IMPORTANT",0,"yellow,on_red"], ["This upgrade will not migrate data to new directories.  This should be completed by the configurator.",2,"yellow"],
                                    ["sudo nodectl configure",2,"blue","bold"]
                                ])

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
        

    def modify_dynamic_elements(self):
        
        self.fix_swap_issues()
        self.update_system_prompt()
        backup = False
        confirm = True if self.non_interactive else False

        # version 2.8.0 to 2.8.1 integrationNet only
        for profile in self.config_copy.keys():
            if self.config_copy[profile]["environment"] == "integrationnet":
                host = f"l{self.config_copy[profile]['layer']}-lb-integrationnet.constellationnetwork.io"
                if self.config_copy[profile]["layer"] < 1:
                    self.functions.print_cmd_status({
                        "text_start": "Found environment",
                        "brackets": "integrationnet",
                        "status": "found",
                        "newline": True,
                    })
                    if self.functions.test_or_replace_line_in_file({
                        "file_path": "/var/tessellation/nodectl/cn-config.yaml",
                        "search_line": "3.101.147.116",
                        "skip_backup": True,
                    }):
                        self.functions.print_paragraphs([
                            ["",1], ["A legacy integrationnet configuration variable",0],
                            [self.config_copy[profile]["edge_point"],0,"yellow","bold"],
                            ["was found, this should be corrected.",2],
                        ])
                        if not confirm:
                            confirm = self.functions.confirm_action({
                                "prompt": "Would you like nodectl to update your configuration?",
                                "yes_no_default": "y",
                                "return_on": "y",
                                "exit_if": False
                            })
                        
            if confirm:
                # need to done for each layer independently in case user uses different
                # edge hosts per profile
                if not backup:
                    backup = True
                    progress = {
                        "text_start": "Backing up config",
                        "status": "running",
                        "newline": False,
                    }
                    self.functions.print_cmd_status(progress)
                    backup_file = self.functions.get_date_time({"action": "datetime"})
                    backup_file = f"cn-config_{backup_file}"
                    try:
                        system(f"cp /var/tessellation/nodectl/cn-config.yaml {self.config_copy[profile]['backups']}/{backup_file} > /dev/null 2>&1")
                    except Exception as e:
                        self.log.logger.error(f"unable to find directory location. error [{e}]")
                        self.error_messages.error_code_messages({
                            "error_code": "upg-531",
                            "line_code": "file_not_found",
                            "extra": f"cn-config.yaml or backup dir"
                        })
                    self.functions.print_cmd_status({
                        **progress,
                        "status": "complete",
                        "status_color": "green",
                        "newline": True,
                    })

                search = ""
                search = f'        host: {self.config_copy[profile]["edge_point"]}'
                search2 = f"        host_port: 90{self.config_copy[profile]['layer']}0"
                all_first_last = "first"
                if self.config_copy[profile]['layer'] > 0:
                    all_first_last = "last"
                    
                self.functions.test_or_replace_line_in_file({
                    "file_path": "/var/tessellation/nodectl/cn-config.yaml",
                    "search_line": search,
                    "skip_backup": True,
                    "all_first_last": all_first_last,
                    "replace_line": f"        host: {host}\n"
                })
                self.functions.test_or_replace_line_in_file({
                    "file_path": "/var/tessellation/nodectl/cn-config.yaml",
                    "search_line": search2,
                    "skip_backup": True,
                    "replace_line": f"        host_port: 80\n"
                })
                
        self.service_file_manipulation() # default directories are setup in the verify_directories method
       
        # remove any private key file info to keep
        # security a little more cleaned up
        if path.isfile(f"{self.p12.p12_file_location}/id_ecdsa.hex"):
            system(f"rm -f {self.p12.p12_file_location}/id_ecdsa.hex > /dev/null 2>&1")

     
    def service_file_manipulation(self):
        # version older than 0.15.0 only
        self.log.logger.warn(f"upgrader removing older <2.x.x service file if exists.")
        
        # legacy service files
        progress = {
            "status": "running",
            "text_start": "Removing v1.12.0",
            "brackets": "service",
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
            "text_start": "Removing v1.12.0",
            "brackets": "bash",
            "text_end": "files",
        }
        self.functions.print_cmd_status(progress)

        files = ["cn-node-l0","cn-node-l1"]
        for file in files:
            if path.isfile(f"/usr/local/bin/{file}"):
                system(f"rm -f /usr/local/bin/{file} > /dev/null 2>&1")

        self.functions.print_cmd_status({
            **progress,
            "status": "complete",
            "newline": True
        })

        self.log.logger.info(f"upgrader refactoring service files based on cn-config.yaml as necessary.")
        progress = {
            "status": "running",
            "text_start": "Building v2.0.0 Services Files",
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
            "brackets": self.download_version,
            "bold": True,
            "text_color": "blue",
            "newline": True
        })
        self.cli.node_service.download_constellation_binaries({
            "download_version": self.download_version,
            "print_version": False,
            "action": "upgrade",
        })

        
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
        self.cli.set_profile(profile)
        self.cli.cli_start({
            "argv_list": [],
            "wait": False
        })
        if self.functions.config_obj[profile]["layer"] > 0:
            self.functions.print_timer(10,"wait for restart",1)
    
        
    def check_for_api_readytojoin(self,profile,service):
        self.api_ready_list = {
            **self.api_ready_list,
            f"{profile}": {"service": service, "ready": False}
        }

        self.cli.node_service.set_profile(profile)
        self.cli.set_profile(profile)
        
        cmd_status = {
            "text_start": "Checking for",
            "brackets": "ReadyToJoin",
            "status": "running",
            "text_end": "state"
        }
        self.functions.print_cmd_status(cmd_status)

        api_ready = self.cli.node_service.check_for_ReadyToJoin("upgrade") 
        self.api_ready_list[profile] = {
            **self.api_ready_list[profile],
            "ready": api_ready
        }
        
        color = "red"
        state = "failed"
        if self.api_ready_list[profile]:
            color = "green"
            state = "ReadyToJoin"
        
        self.functions.print_cmd_status({
            **cmd_status,
            "status": state,
            "status_color": color,
            "newline": True
        })
        self.log.logger.info(f"check for api results: service [{self.api_ready_list[profile]}]")
                
                
    def re_join_tessellation(self,profile):
        self.cli.node_service.set_profile(profile)
        self.cli.set_profile(profile)
        self.log.logger.info(f"attempting to rejoin to [{profile}]")
        if self.api_ready_list[profile]["ready"]:   
            self.functions.print_paragraphs([
                ["Please wait while [",0], [profile,-1,"yellow","bold"], ["] attempts to join the network.",-1],["",1],
            ])
            if self.config_copy[profile]["layer"] != "0":
                self.functions.print_paragraphs([
                    ["NOTE:",0,"yellow,on_magenta","bold"], ["Layer1",0,"cyan","underline"], ["networks will not join the Hypergraph until its",0],
                    ["Layer0",0,"cyan","underline"], ["linked profile changes to",0], ["Ready",0,"green","bold"], ["state, this could take up to a",0],
                    ["two",0,"cyan","underline"], ["minutes.",1]
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
                self.cli.set_profile(item["profile"])
                state = self.functions.test_peer_state({
                    "profile": item["profile"],
                    "simple": True
                })
                if state != "Ready" and state != "Observing" and state != "WaitingForReady":
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
        if "-f" in self.var.argv_list:
            self.forced = True  
        if "-v" in self.var.argv_list:
            self.download_version = self.var.argv_list[self.var.argv_list.index("-v")+1]
            if not self.functions.is_version_valid(self.download_version) and not self.forced:
                self.error_messages.error_code_messages({
                    "error_code": "upg-550",
                    "line_code": "input_error",
                    "extra": "-v <version format vX.X.X>"
                })
        if "-ni" in self.var.argv_list:
            self.non_interactive = True      
            
                    
    def node_id_error_handler(self,count):
        count_max = 4
        self.functions.print_paragraphs([
            ["",1],["Unable to obtain node id... ",1,"red","bold"], ["attempt [",0,"red","bold"], [f"{count}",-1,"yellow","bold"],
            ["] of [",-1,"red","bold"], [f"{count_max}",-1,"yellow","bold"], ["]",-1,"red","bold"], ["",1],
        ])
        # error_str = colored("  Unable to obtain node id... attempt [","red")+colored(count,"yellow",attrs=['bold'])
        # error_str += colored("] of [","red")+colored(count_max,"yellow",attrs=['bold'])+colored("]","red")
        # print(error_str,end="\r")
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
from os import makedirs, system, path, environ
from time import sleep
from termcolor import colored, cprint

from .functions import Functions
from .troubleshoot.errors import Error_codes
from concurrent.futures import ThreadPoolExecutor
from .p12 import P12Class
from .command_line import CLI
from .user import UserClass
from .troubleshoot.logger import Logging
from .config.config import Configuration
from .config.versioning import Versioning

class Installer():

    def __init__(self,command_obj):
        self.step = 1
        self.status = "" #empty
        self.ip_address = command_obj["ip_address"]
        self.environment_name = command_obj["environment_name"]
        self.existing_p12 = command_obj["existing_p12"]
        self.functions = command_obj["functions"]
        self.command_obj = command_obj
        
        self.error_messages = Error_codes(self.functions) 
        self.log = Logging()
        versioning = Versioning({
            "called_cmd": "show_version",
        })
        self.functions.version_obj = versioning.get_version_obj()
        self.functions.set_statics()  
        

    def install_process(self):
        self.verify_existing()
        self.build_config_file("skeleton")
        self.build_classes()
        self.build_config_file("defaults")
        self.process_distro_dependencies()
        self.download_binaries()
        self.make_swap_file()
        self.setup_user()
        self.create_dynamic_elements()
        self.generate_p12_from_install()
        self.build_config_file("p12")
        self.setup_new_configuration()
        self.populate_node_service()
        self.complete_install()
    

    def build_classes(self):
        cli_obj = {
            "caller": "installer",
            "profile": "empty",
            "command": "install",
            "command_list": [],
            "functions": self.functions,
            "ip_address": self.command_obj["ip_address"],
            "skip_services": False
        }
        self.cli = CLI(cli_obj)
        self.cli.functions.set_statics()
        self.user = UserClass(self.cli,True)
        
        self.setup_config = Configuration({
            "implement": False,
            "action": "install",
            "argv_list": ["None"]
        })
        
        
    def verify_existing(self):
        found_files = self.functions.get_list_of_files({
            "paths": ["/var/tessellation/","/home/nodeadmin/"],
            "files": ["*"],
            "exclude_paths": ["/var/tessellation/nodectl"],
            "exclude_files": ["nodectl.log"],
        })
        found_files2 = self.functions.get_list_of_files({
            "paths": ["/etc/systemd/system/"],
            "files": ["cnng-*","node_restart*"],
        })
        
        if len(found_files) > 0 or len(found_files2) > 0:
            if len(found_files) > 0:
                self.log.logger.warn("install found possible existing tessellation core components")
            if len(found_files2) > 0:
                self.log.logger.warn("install found possible existing nodectl service components")
            self.functions.print_paragraphs([
                ["",2], [" WARNING ",0,"yellow,on_red"], ["An existing Tessellation installation may be present on this server.  Preforming a fresh installation on top of an existing installation can produce",0,"red"],
                ["unexpected",0,"red","bold,underline"], ["results.",2,"red"],
                
                ["",1], [" IMPORTANT ",0,"yellow,on_red"], ["Any existing tessellation",0,"red"],
                ["configuration",0,"yellow","bold"], ["files will be removed from this server.",2,"red"],
                ["This installation cannot continue unless the old configuration file is removed.",2]
            ])
            self.functions.confirm_action({
                "yes_no_default": "n",
                "return_on": "y",
                "prompt": "Would you like to remove and continue?",
                "prompt_color": "red",
                "exit_if": True,
            })

        system(f"sudo rm {self.functions.nodectl_path}cn-config.yaml > /dev/null 2>&1")
        system(f"sudo rm {self.functions.nodectl_path}version_obj.json > /dev/null 2>&1")
        self.functions.print_cmd_status({
            "text_start": "Removing old configuration files",
            "status": "complete",
            "status_color": "green",
            "newline": True,
        })        
            

    def setup_user(self):
        self.functions.print_any_key({"newline":"top"})
        self.user.setup_user()  
        
                  
    def build_config_file(self,action):
        skeleton = None
        if action == "skeleton":
            skeleton = self.functions.pull_remote_profiles({
                "retrieve": "config_file"
            })
            self.config_obj = skeleton[self.environment_name]["json"]["nodectl"]
            self.config_obj["global_elements"] = {
                "caller": "installer",
                "environment_name": self.environment_name,
            }
            
            # download specific file to Node
            try:
                system(f'sudo wget {skeleton[self.environment_name]["yaml_url"]} -O {self.functions.nodectl_path}cn-config.yaml -o /dev/null')
            except Exception as e:
                self.log.logger.critical(f'Unable to download skeleton yaml file from repository [{skeleton[self.environment_name]["nodectl"]["yaml_url"]}] with error [{e}]')
                self.error_messages.error_code_messages({
                    "error_code": "int-149",
                    "line_code": "download_yaml",
                })
        
        elif action == "defaults":
            self.setup_config.config_obj = self.config_obj
            self.metagraph_list = self.functions.clear_global_profiles(self.config_obj)
            self.setup_config.metagraph_list = self.metagraph_list
            self.config_obj = self.setup_config.setup_config_vars()
            self.functions.config_obj = self.config_obj
            self.cli.node_service.config_obj = self.config_obj
            self.functions.set_statics()
            self.cli.functions.set_statics()
            self.cli.node_service.functions.set_statics()
            self.functions.profile_names = self.metagraph_list
            versioning = Versioning({
                "called_cmd": "install",
                "request": "install",
                "config_obj": self.config_obj
            })
            self.version_obj = versioning.get_version_obj()
            self.cli.version_obj = self.version_obj
            self.cli.node_service.version_obj = self.version_obj
            self.cli.node_service.functions.version_obj = self.version_obj
            self.cli.version_obj = self.version_obj

        elif action == "p12":
            if self.existing_p12:
                self.p12_session.p12_file_location = self.existing_p12.rsplit('/', 1)[0]+"/"
            p12_replace_list = [
                ("passphrase", f'"{self.p12_session.p12_password}"'),
                ("key_location",self.p12_session.p12_file_location),
                ("key_name", self.p12_session.p12_filename),
                ("key_alias",self.p12_session.key_alias),
                ("nodeadmin",self.user.username),
            ]
            
            for p12_item in p12_replace_list:
                self.functions.test_or_replace_line_in_file({
                    "file_path": f"{self.functions.nodectl_path}cn-config.yaml",
                    "search_line": f"    {p12_item[0]}: blank",
                    "replace_line": f"    {p12_item[0]}: {p12_item[1]}\n",
                    "skip_backup": True,
                })


    def create_dynamic_elements(self):
        print("")
        self.functions.print_header_title({
            "line1": "TESSELLATION DYNAMIC STRUCTURES",
            "single_line": True,
            "newline": "both"
        })
        
        self.functions.print_paragraphs([
            [" IMPORTANT ",2,"white,on_red"], 
            ["nodectl installation will install the new",0,"magenta"], ["Node",0,"blue","bold"], 
            ["with default",0,"magenta"],
            ["Metagraph Network Variables",2,"blue","bold"],
            
            ["Metagraph:",0], [self.config_obj['global_elements']['environment_name'],2,"yellow"],
            
            ["After installation is complete, the Node Operator may alter the",0,"magenta"], ["nodectl",0,"blue","bold"],
            ["configuration to allow connection to the",0,"magenta"], ["Metagraph",0,"blue","bold"], ["of choice via the command:",2,"magenta"],
            
            ["sudo nodectl configure",2],
        ])
        
        self.functions.print_any_key({"newline":"bottom"})

        m_progress = {
            "text_start": "Creating",
            "brackets": "Node",
            "text_end": "directories",
            "status": "running",
            "newline": True
        }
        self.functions.print_cmd_status(m_progress)
        
        def progress(text,end):
            color = "green" if end else "yellow"
            status = "complete" if end else "building"
            
            self.functions.print_cmd_status({
                "text_start": text,
                "status": status,
                "status_color": color,
                "newline": end,
                "delay": .1,
            })
                    
        self.log.logger.info("creating directory structure data, backups, and uploads") 
        
        dir_obj = {
            "tessellation": "/var/tessellation/",
            "nodectl": self.functions.nodectl_path,
        }
        for profile in self.metagraph_list:
            dir_obj[f"{profile}_backups"] = self.config_obj[profile]["directory_backups"]
            dir_obj[f"{profile}_uploads"] = self.config_obj[profile]["directory_uploads"]
            if self.config_obj[profile]["layer"] < 1:
                dir_obj[f"{profile}_data_layer0"] = f"/var/tessellation/{profile}/data/snapshot"
            else:
                dir_obj[f"{profile}_data_layer1"] = f"/var/tessellation/{profile}/"

        for ux, dir in dir_obj.items():
            progress(ux,False)
            if not path.isdir(dir):
                makedirs(dir)
            progress(ux,True)
            
        self.functions.print_cmd_status({
            **m_progress,
            "status": "complete",
            "status_color": "green"
        })
        sleep(.8) # UX allow user to see output
        
           
    def process_distro_dependencies(self):
        self.log.logger.info("installer - downloading binaries")
        print("")
        self.functions.print_header_title({
          "line1": "SYSTEM REQUIREMENTS",
          "single_line": True,
          "newline": "both"  
        })
        
        self.packages = {
            "haveged": False,
            "default-jdk": False,
            "vim": False,
            "curl": False,
            "wget": False,
            "tree": False,
        }
                
        environ['DEBIAN_FRONTEND'] = 'noninteractive'         
        for package, value in self.packages.items():
            if value == False:
                
                if package == "default-jdk":
                    print(colored(f"  {package}","cyan",attrs=['bold']),end=" ")
                    print(colored("may take a few minutes to install".ljust(40),"cyan"),end=" ")
                    print(" ".ljust(10))

                self.log.logger.info(f"installation process installing [{package}]")
                with ThreadPoolExecutor() as executor:
                    self.functions.status_dots = True
                    self.log.logger.info(f"updating the Debian operating system.")
                    environ['DEBIAN_FRONTEND'] = 'noninteractive'
                    
                    _ = executor.submit(self.functions.print_cmd_status,{
                        "text_start": "Installing dependency",
                        "brackets": package,
                        "dotted_animation": True,
                        "status": "installing",
                        "status_color": "yellow",
                    })
                            
                    bashCommand = f"apt-get install -y {package}"
                    self.functions.process_command({
                        "bashCommand": bashCommand,
                        "proc_action": "timeout",
                    })
                    
                    while True:
                        sleep(2)
                        bashCommand = f"dpkg -s {package}"
                        result = self.functions.process_command({
                            "bashCommand": bashCommand,
                            "proc_action": "timeout",
                        })
                        if "install ok installed" in str(result):
                            self.packages[f'{package}'] = True
                            break   

                    self.functions.status_dots = False
                    self.functions.print_cmd_status({
                        "text_start": "Installing dependency",
                        "brackets": package,
                        "status": "complete",
                        "newline": True
                    })


    def download_binaries(self):            
        self.cli.node_service.download_constellation_binaries({
            "action": "install",
            "environment": self.environment_name
        })
        
        self.functions.print_cmd_status({
            "text_start": "Installing Tessellation binaries",
            "status": "complete",
            "newline": True
        })


    def make_swap_file(self):
        self.log.logger.info("installer - preparing to create swapfile")
        self.functions.print_clear_line()
        progress = {
            "text_start": "Enabling OS swap",
            "status": "running",
            "brackets": "creating",
            "status_color": "yellow",
            "delay": .8
        }
        self.functions.print_cmd_status(progress)

        if path.isfile("/swapfile"):
            self.log.logger.warn("installer - swap file already exists - install skipping action")
            result = "already exists"
            color = "magenta"
            self.log.logger.warn("Installation making swap file skipped because already detected")
        else:
            self.log.logger.info("Installation making swap file")
            system("touch /swapfile") 
            # allocate 8G
            system("fallocate -l 8G /swapfile > /dev/null 2>&1")
            sleep(1)
            system("chmod 600 /swapfile")
            system("mkswap /swapfile > /dev/null 2>&1")
            sleep(1)
            system("swapon /swapfile > /dev/null 2>&1")
            result = "completed"
            color = "green"

            self.functions.print_cmd_status({
                **progress,
                "brackets": "update fstab"
            })
                
            # make permanent
            try:
                if not self.functions.test_or_replace_line_in_file({
                        "file_path": "/etc/fstab",
                        "search_line": "/swapfile none swap sw 0 0",
                }):
                    # backup the file just in case
                    system("cp /etc/fstab /etc/fstab.bak > /dev/null 2>&1")
                    system("echo '/swapfile none swap sw 0 0' | tee -a /etc/fstab > /dev/null 2>&1")
            except:
                self.log.logger.error("installation unable to update fstab to enable swapfile properly.")

            try:
                if not self.functions.test_or_replace_line_in_file({
                        "file_path": "/etc/sysctl.conf",
                        "search_line": "vm.swappiness=",                    
                    }):
                    # backup the file just in case
                    system("cp /etc/sysctl.conf /etc/sysctl.conf.bak > /dev/null 2>&1")
                    system("echo 'vm.swappiness=10' | tee -a /etc/sysctl.conf > /dev/null 2>&1")
            except:
                self.log.logger.error("installation unable to update systctl to fix swapfile swapiness settings permanently.")

            self.functions.print_cmd_status({
                **progress,
                "brackets": "swappiness",
            })  
                          
            try:
                # turn it on temporarily until next reboot
                system("sudo sysctl vm.swappiness=10 > /dev/null 2>&1")
            except:
                self.log.logger.error("installation unable to update sysctl to fix swapfile swapiness settings temporarily until next reboot.")            

        self.functions.print_cmd_status({
            **progress,
            "brackets": None,
            "status": result,
            "status_color": color,
            "delay": 0,
            "newline": True
        })   

        self.functions.print_cmd_status({
            "text_start": "System Requirements",
            "status": "complete",
            "status_color": "green",
            "newline": True,
        })   
    

    def generate_p12_from_install(self):
        if self.existing_p12:
            self.migrate_existing_p12()
            
        self.log.logger.info("installer - generating p12 file")
        action_obj = {
            "action": "generate",
            "process": "install",
            "app_env": self.environment_name,
            "user_obj": self.user,
            "cli_obj": self.cli,
            "functions": self.functions,
            "existing_p12": self.existing_p12
        }
        self.p12_session = P12Class(action_obj)
        self.p12_session.generate_p12_file()     
       

    def migrate_existing_p12(self):
        current_user = "root" if not self.user.installing_user else self.user.installing_user
        location = False
        
        possible_found = self.functions.get_list_of_files({
            "paths": ["root","home","/var/tessellation/"],
            "files": ["*.p12"],
        })
        
        verb = "Possible P12 file"
        user_action = "Please select an option"
        if len(possible_found.keys()) < 1:
            verb = "Example"
            user_action = "Please select it below"
            possible_found = [f"/home/{current_user}/my_p12_key_name.p12"]
        
        self.functions.print_paragraphs([
            ["",2], ["nodectl has detected an existing p12 migration to this new Node has been requested;",0,"yellow"],
            [f"and now needs to find and migrate this private key file. {user_action}.",2,"yellow"],
        ])
        if verb == "Example":
            self.functions.print_paragraphs([
                [f"{verb}:",0,"magenta","bold"], [possible_found[0],2]
            ])
        else:
            try:
                for option, value in possible_found.items():
                    self.functions.print_paragraphs([
                        [f"{option}",0,"magenta","bold"], [")",-1,"magenta"], [value,1,"green"]
                    ])
                self.functions.print_paragraphs([
                    [f"{len(possible_found)+1}",0,"magenta","bold"], [")",-1,"magenta"], ["input manual entry",2,"green"]
                ])
                possible_found[f"{len(possible_found)+1}"] = "custom"
                
                location = self.functions.get_user_keypress({
                    "prompt": "KEY PRESS an option",
                    "prompt_color": "magenta",
                    "options": list(possible_found.keys())
                })  
                location = possible_found[location]
            except:
                self.error_messages.error_code_messages({
                    "error_code": "int-484",
                    "line_code": "invalid_search",
                    "extra": "Did you properly upload a p12 file?"
                })
                
        if verb == "example" or location == "custom": 
            exist_location_str = colored("  Please enter full path including p12 file key: ","cyan")
            while True:
                location = input(exist_location_str)
                if path.exists(location):
                    break
                cprint("  invalid location or file name, try again","red",attrs=["bold"])
        
        if not path.exists(f"/home/{self.user.username}/tessellation/"):
            makedirs(f"/home/{self.user.username}/tessellation/")
            
        try:
            p12name = location.split("/")
            p12name_only = p12name[-1]
            p12name = p12name_only.split(".")
            p12name = p12name[0]
        except Exception as e:
            self.error_messages.error_code_messages({
                "error_code": "int-507",
                "line_code": "file_not_found",
                "extra": location if isinstance(location,str) else "unknown",
                "extra2": "Are you sure your uploaded the proper p12 file?"
            })
        
        system(f"sudo mv {location} /home/{self.user.username}/tessellation/{p12name_only} > /dev/null 2>&1")
        system(f"sudo chmod 600 /home/{self.user.username}/tessellation/{p12name_only} > /dev/null 2>&1")
        system(f"sudo chown root:root /home/{self.user.username}/tessellation/{p12name_only} > /dev/null 2>&1")
        
        self.functions.print_cmd_status({
            "text_start": "migrate p12",
            "brackets": p12name,
            "status": "complete",
            "status_color": "green",
            "newline": True,
        })
        self.existing_p12 = f"/home/{self.user.username}/tessellation/{p12name_only}"
        
        
    def setup_new_configuration(self):
        # rebuild node service with config
        self.setup_config.config_obj = {
            **self.config_obj,
            **self.setup_config.config_obj,
            **self.functions.config_obj,
            "upgrader": True
        }
        self.log.logger.info("Installation populating node service variables for build")
        self.setup_config.build_yaml_dict()
        self.setup_config.setup_config_vars()
        # replace cli and node service config object with newly created obj
        self.cli.functions.config_obj = self.setup_config.config_obj
        self.cli.node_service.config_obj = self.setup_config.config_obj
        # replace cli and fucntions object with newly created obj
        self.cli.node_service.functions = self.cli.functions
        self.cli.node_service.functions.set_statics()


    def populate_node_service(self):                
        progress = {
            "text_start": "Creating Services",
            "status": "running",
        }
        self.functions.print_cmd_status(progress)
        self.cli.node_service.profile_names = self.metagraph_list
        self.cli.node_service.build_service(True) # true will build restart_service
        
        # handle version_service enablement 
        system("sudo systemctl enable node_version_updater.service > /dev/null 2>&1")
        sleep(.3)
        system("sudo systemctl restart node_version_updater.service > /dev/null 2>&1")
        
        self.functions.print_cmd_status({
            **progress,
            "status": "complete",
            "newline": True,
            "delay": .8
        })
        
        
    def complete_install(self):
        self.log.logger.info("Installation complete ******")
        print("")

        self.functions.print_header_title({
          "line1": "INSTALLATION COMPLETE",
          "newline": "both",
          "clear": False,
        })
        
        self.functions.print_paragraphs([
            ["  CONGRATULATIONS!  ",1,"grey,on_green","bold"],
            ["Installation is complete",1],
            ["Below you will find your",0], ["nodeid",0,"yellow","bold,underline"], ["which was derived from your p12 file",1],
            ["Please report this nodeid to administrative staff to gain access to the network via the access list permissions.",2,"magenta"]
        ])
        
        success = self.cli.cli_grab_id({
            "command":"nodeid",
            "return_success": True,
            "skip_display": True,
        })
        
        if not success:
            self.functions.print_paragraphs([
                ["",1],[" WARNING ",1,"red,on_yellow"], 
                ["p12 file may have incorrect parameters or is corrupted.",0,"red"],
                ["Unable to derive nodeid.",2,"red","bold"],
                ["Please update your",0,"magenta"], ["p12",0,"yellow"], ["details",1,"magenta"],
                ["sudo nodectl configure",2,"cyan"]
            ])
        else:
            for profile in self.metagraph_list:
                if self.config_obj[profile]["seed_location"] != "disable":
                    self.cli.check_seed_list(["-p",profile,"-id",self.cli.nodeid])

        self.functions.print_paragraphs([
            ["",1], [f"Please review the next Steps in order to gain access to the {self.environment_name} environment.",0],
            ["If your Node is found as",0], ["False",0,"red","bold"], ["on the",0],
            ["check seed list(s)",0,"blue","bold"], ["output above, you will need to submit your NodeID for acceptance.",2],
            ["Please follow the instructions below, as indicated.",2],
            ["1",0,"magenta","bold"], [")",-1,"magenta"], ["Submit your NodeID to Constellation Admins.",1,"cyan"],
            ["2",0,"magenta","bold"], [")",-1,"magenta"], ["Collateralize your Node.",1,"cyan"],
            ["3",0,"magenta","bold"], [")",-1,"magenta"], [f"sudo nodectl check_seedlist -p {self.metagraph_list[0]}",1,"cyan"],
            ["4",0,"magenta","bold"], [")",-1,"magenta"], ["sudo nodectl restart -p all",2,"cyan"],
            ["enod!",2,"white","bold"],
        ])        
        
        
if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")  
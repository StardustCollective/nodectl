import pwd
import modules.uninstall as uninstaller
from os import makedirs, system, path, environ, walk
from time import sleep
from termcolor import colored, cprint
from types import SimpleNamespace
from collections import OrderedDict

from .troubleshoot.errors import Error_codes
from concurrent.futures import ThreadPoolExecutor
from .p12 import P12Class
from .command_line import CLI
from .user import UserClass
from .troubleshoot.logger import Logging
from .config.config import Configuration
from .config.configurator import Configurator
from .config.versioning import Versioning
from .quick_install import QuickInstaller
from .node_service import Node
from .upgrade import Upgrader


class Installer():

    def __init__(self,parent,argv_list):
        self.step = 1
        self.status = "" #empty
        self.parent = parent
        
        self.ip_address = parent.ip_address
        self.functions = parent.functions
        self.argv_list = argv_list
        self.p12_session = False
        self.found_errors = False

        self.action = "install"

        self.error_messages = Error_codes(self.functions) 
        self.log = Logging()
        versioning = Versioning({
            "called_cmd": "show_version",
        })
        self.functions.version_obj = versioning.get_version_obj()
        self.functions.set_statics()  
        

    def install_process(self):
        self.handle_options()
        self.setup_install()
        self.setup_environment()
        self.build_classes()
        self.validate_options()
        if self.options.quick_install:
            self.quick_installer.quick_install()
        else:
            self.prepare_p12_details()
            self.handle_exisitng()
            self.build_config_file("skeleton")
            self.build_config_file("defaults")
            self.update_os()
            self.process_distro_dependencies()
            self.download_binaries()
            self.make_swap_file()
            self.setup_user()
            self.create_dynamic_elements()
            self.generate_p12_from_install()
            self.build_config_file("p12")
            self.setup_new_configuration()
            self.encrypt_passprhase()
            self.populate_node_service()
        self.complete_install()
    

    def setup_install(self):
        self.functions.check_sudo()
        self.log.logger.debug(f"installation request started - quick install [{self.options.quick_install}]")
        self.print_main_title()
        self.parent.install_upgrade = "installation"

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

        if not self.options.quick_install:
            self.functions.print_paragraphs([
                [" QUICK INSTALL ",0,"yellow,on_blue"], ["nodectl's installer provides a",0,"white","bold"], 
                ["quick install",0,"blue","bold"], ["option that utilizes all the",0,"white","bold"], ["recommended",0,"green","bold"],
                ["default settings. This allows for a streamlined process, requiring minimal input from the future Node Operator.",2,"white","bold"],

                ["Alternatively,",0,"yellow"], ["you can choose a step-by-step installation, where nodectl will ask you questions and provide explanations",0,"white","bold"],
                ["for the necessary elements to customize the installation your node.",2,"white","bold"],
            ])
            self.options.quick_install = self.functions.confirm_action({
                "yes_no_default": "y",
                "return_on": "y",
                "exit_if": False,
                "prompt": "Install using quick install option?",                
            })

        if self.options.quick_install:
            self.functions.print_clear_line(10,{"backwards":True, "bl":-1})
            self.functions.print_paragraphs([
                [" QUICK INSTALL REQUESTED ",2,"white,on_green"],
                [" WARNING ",1,"red,on_yellow"], 
                ["Even though this is the recommended options, nodectl will use all recommended settings without prompting for confirmations, be sure this is acceptiable before continuing",0],
                ["with this setting.",0], ["This includes removal of existing Tessellation and nodectl configurations if present.",2,"red"],
                ["A few mandatory entries may be necessary; hence, nodectl will now prompt a series of questions before proceeding with the",0],
                ["installation. If these options were already entered through the command line interface (CLI),",0],
                ["the corresponding questions will be skipped.",2],
                ["nodectl",0,"yellow"], ["quick install",0,"yellow","bold"], ["will not offer detailed explaination for various prompt requests, please use the normal installation",0,"yellow"],
                ["or read the documentation.",1,"yellow"], 
                ["https://docs.constellationnetwork.io/validate/",2,"blue","bold"],
            ])
        else:
            self.functions.print_clear_line(1,{"backwards":True})

        self.parent.confirm_int_upg()

        self.print_main_title()
        self.functions.print_header_title({
            "line1": "INSTALLATION STARTING",
            "single_line": True,
            "show_titles": False,
            "newline": "bottom",
        }) 
    
    
    # Node Options and Values
    # =====================
        
    def handle_options(self):
        self.passphrases_set = False
        self.options_dict = OrderedDict()

        # option list must be in order otherwise values will not properly populate
        option_list = [
            "--environment",
            "--user", "--p12_path", "--p12_alias",
            "--user_password","--p12_passphrase",
        ]

        if "-e" in self.argv_list: 
            self.argv_list[self.argv_list.index("-e")] = "--environment"
        
        for option in option_list:
            self.options_dict[f'{option.replace("-","")}'] = self.argv_list[self.argv_list.index(option)+1] if option in self.argv_list else False

        self.options = SimpleNamespace(**self.options_dict)

        self.options.quick_install = False
        if "--quick_install" in self.argv_list:
            if self.options.p12_path and not self.options.p12_alias:
                self.error_messages.error_code_messages({
                    "error_code": "int-96",
                    "line_code": "input_error",
                    "extra": "p12 alias",
                    "extra2": "p12 cli option supplied without cooresponding p12 alias option."
                })
            self.options.quick_install = True


    def validate_options(self):
        for option, value in self.options_dict.items():
            if isinstance(value,bool):
                if option == "p12_path":
                    self.prepare_p12_details("init")
                elif option == "environment" and not self.options.environment: 
                    self.setup_environment(True)
                    self.options.environment = self.parent.environment_requested
                elif self.options.quick_install:
                    self.quick_installer.validate_options(option)

            elif option == "environment":
                self.print_cmd_status("environment","environment",False) 
            elif option == "p12_path":
                if not value.endswith(".p12"):
                    self.error_messages.error_code_messages({
                        "error_code": "int-133",
                        "line_code": "invalid_file_format",
                        "extra": value,
                        "extra2": "p12 file must end with the '.p12' extension."
                    })                       
                if not path.exists(value):
                    self.error_messages.error_code_messages({
                        "error_code": "int-140",
                        "line_code": "file_not_found",
                        "extra": value,
                        "extra2": "Please verify the exact full path to your p12 file and try again."
                    })    
                self.print_cmd_status("P12 path",path.split(value)[0],False,False)   
                self.print_cmd_status("P12 file",path.split(value)[1],False,False)   
                self.options.p12_path = value  
            elif option == "p12_alias":
                self.print_cmd_status("P12 alias","p12_alias",False)     
    
    
    def setup_environment(self,do=False):
        if self.options.quick_install and do == False: return
        if not self.options.environment and not self.options.quick_install:
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

        self.parent.verify_environments({
            "env_provided": self.options.environment,
            "action": "install" if not self.options.quick_install else "quick_install",
        }) 
        self.options.environment = self.parent.environment_requested
        
                
    def handle_exisitng(self):
        if not self.options.quick_install: self.parent.print_ext_ip()

        found_files = self.functions.get_list_of_files({
            "paths": ["var/tessellation/","home/nodeadmin/tessellation/"],
            "files": ["*"],
            "exclude_paths": ["var/tessellation/nodectl"],
            "exclude_files": ["nodectl.log"],
        })
        found_files2 = self.functions.get_list_of_files({
            "paths": ["etc/systemd/system/"],
            "files": ["cnng-*","node_restart*"],
        })
        
        if len(found_files) > 0 or len(found_files2) > 0:
            if len(found_files) > 0:
                self.log.logger.warn("install found possible existing tessellation core components")
            if len(found_files2) > 0:
                self.log.logger.warn("install found possible existing nodectl service components")
            if self.options.quick_install:
                self.log.logger.warn("install -> quick_install -> Found possible existing installation and configuration files, removing previous elements.")
            else:
                self.functions.print_paragraphs([
                    ["",1], [" WARNING ",0,"yellow,on_red"], ["An existing Tessellation installation may be present on this server.  Preforming a fresh installation on top of an existing installation can produce",0,"red"],
                    ["unexpected",0,"red","bold,underline"], ["results.",2,"red"],

                    [" RECOMMENDED ",0,"green,on_yellow"], ["Attempt an uninstall first.",1,"white"],
                    ["sudo nodectl uninstall",2],
                    
                    [" IMPORTANT ",0,"yellow,on_red"], ["Any existing tessellation",0,"red"],
                    ["configuration",0,"yellow","bold"], ["files will be removed from this server.",2,"red"],
                    ["This installation cannot continue unless the old configuration file is removed.",2,"red"],

                    ["You can exit here and uninstall first or continue.  If you continue, nodectl will first remove existing configurations.",1]
                ])
                self.functions.confirm_action({
                    "yes_no_default": "n",
                    "return_on": "y",
                    "prompt": "continue?",
                    "prompt_color": "red",
                    "exit_if": True,
                })
                self.functions.print_clear_line(1,{"backwards":True,"fl":1})
            uninstaller.install_cleaner(self.functions,self.options)
            pass


    def populate_node_service(self):
        if not self.options.quick_install:                
            progress = {
                "text_start": "Creating Services",
                "status": "running",
            }
            self.functions.print_cmd_status(progress)

        self.cli.node_service.profile_names = self.functions.clear_global_profiles(self.metagraph_list)
        self.cli.node_service.build_service(True) # true will build restart_service
        
        # handle version_service enablement 
        system("sudo systemctl enable node_version_updater.service > /dev/null 2>&1")
        sleep(.3)
        system("sudo systemctl restart node_version_updater.service > /dev/null 2>&1")
        
        if not self.options.quick_install: 
            self.functions.print_cmd_status({
                **progress,
                "status": "complete",
                "newline": True,
                "delay": .8
            })
    

    def download_binaries(self):            
        self.cli.node_service.download_constellation_binaries({
            "action": "install",
            "environment": self.options.environment,
        })
        
        self.functions.print_cmd_status({
            "text_start": "Installing Tessellation binaries",
            "status": "complete",
            "newline": True
        })

    
    # Distribution
    # =====================

    def update_os(self):
        threading, display = False, False
        if not self.options.quick_install:
            threading, display = True, True
            print("")
            self.functions.print_header_title({
                "line1": "UPDATE DISTRIBUTION",
                "single_line": True,
                "show_titles": False,
                "newline": "bottom",
            })
        self.parent.update_os(threading,display)


    def setup_user(self,quick_ssh=False):
        if self.options.quick_install:
            if quick_ssh: self.user.transfer_ssh_key()
            else: self.user.create_debian_user()
        else:
            self.functions.print_any_key({"newline":"top"})
            self.user.setup_user()  
        

    def create_dynamic_elements(self):
        if not self.options.quick_install:
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
            if not self.options.quick_install: progress(ux,False)
            if not path.isdir(dir): makedirs(dir)
            if not self.options.quick_install: progress(ux,True)
            
        if not self.options.quick_install:
            self.functions.print_cmd_status({
                **m_progress,
                "status": "complete",
                "status_color": "green"
            })
            sleep(.8) # UX allow user to see output
        
           
    def process_distro_dependencies(self):
        self.log.logger.info("installer - downloading binaries")

        if not self.options.quick_install:
            print("")
            self.functions.print_header_title({
            "line1": "SYSTEM REQUIREMENTS",
            "single_line": True,
            "newline": "both"  
            })
        
        self.packages = {
            "haveged": False,
            "openjdk-11-jdk": False,
            "vim": False,
            "curl": False,
            "wget": False,
            "tree": False,
        }
                
        environ['DEBIAN_FRONTEND'] = 'noninteractive' 

        for package, value in self.packages.items():
            if value == False:
                if package == "openjdk-11-jdk":
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


    def make_swap_file(self):
        self.log.logger.info("installer - preparing to create swapfile")
        if not self.options.quick_install:
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
            system("sudo touch /swapfile") 
            # allocate 8G
            system("sudo fallocate -l 8G /swapfile > /dev/null 2>&1")
            sleep(1)
            system("sudo chmod 600 /swapfile")
            system("sudo mkswap /swapfile > /dev/null 2>&1")
            sleep(1)
            system("sudo swapon /swapfile > /dev/null 2>&1")
            result = "completed"
            color = "green"

            if not self.options.quick_install:
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
                    system("sudo cp /etc/fstab /etc/fstab.bak > /dev/null 2>&1")
                    system("sudo echo '/swapfile none swap sw 0 0' | tee -a /etc/fstab > /dev/null 2>&1")
            except:
                self.log.logger.error("installation unable to update fstab to enable swapfile properly.")

            try:
                if not self.functions.test_or_replace_line_in_file({
                        "file_path": "/etc/sysctl.conf",
                        "search_line": "vm.swappiness=",                    
                    }):
                    # backup the file just in case
                    system("sudo cp /etc/sysctl.conf /etc/sysctl.conf.bak > /dev/null 2>&1")
                    system("sudo echo 'vm.swappiness=10' | tee -a /etc/sysctl.conf > /dev/null 2>&1")
            except:
                self.log.logger.error("installation unable to update systctl to fix swapfile swapiness settings permanently.")

            if not self.options.quick_install:
                self.functions.print_cmd_status({
                    **progress,
                    "brackets": "swappiness",
                })  
                          
            try:
                # turn it on temporarily until next reboot
                system("sudo sysctl vm.swappiness=10 > /dev/null 2>&1")
            except:
                self.log.logger.error("installation unable to update sysctl to fix swapfile swapiness settings temporarily until next reboot.")            

        if self.options.quick_install: return

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

    
    # p12 elements
    # ===================
        
    def generate_p12_from_install(self):
        generate = False
        if isinstance(self.options.p12_path,bool):
            if self.options.existing_p12: self.migrate_existing_p12()

        if not self.passphrases_set:
            self.log.logger.info("installer - generating p12 file")
            action_obj = {
                "action": "generate",
                "process": "install",
                "app_env": self.options.environment,
                "user_obj": self.user,
                "cli_obj": self.cli,
                "functions": self.functions,
                "existing_p12": self.options.p12_path
            }
            self.p12_session = P12Class(action_obj)
            if self.options.quick_install: 
                self.p12_session.quick_install = True
        else:
            generate = True

        if self.options.quick_install:
            if generate:
                self.p12_session.p12_file_location, self.p12_session.p12_filename = path.split(self.options.p12_path) 
                self.p12_session.key_alias = self.options.p12_alias
                self.p12_session.generate()
                return
            else:
                if not self.options.user_password:
                    self.user.ask_for_password()
                if not self.options.p12_passphrase:
                    self.p12_session.ask_for_keyphrase()
                self.passphrases_set = True
                if self.options.existing_p12: self.derive_p12_alias()
                return

        self.p12_session.generate_p12_file()     
       

    def derive_p12_alias(self):
        self.functions.print_cmd_status({
            "text_start": "Deriving p12 alias",
            "brackets": self.options.p12_path.split("/")[-1],
            "status": "running",
            "status_color": "yellow",
        })
        try:
            self.options.p12_alias = self.p12_session.show_p12_details(
                ["--file",self.options.p12_path,"--installer",self.options.p12_passphrase,"--alias","--return"]
            )
        except:
            self.log.logger.critical(f"installer was unable to derive the p12 alias from the p12 keystore [{self.options.p12_path}].  Please manually update the configuration in order to properly join the necessary cluster(s).")
            self.options.p12_alias = "error"
            self.found_errors = True

        self.functions.print_cmd_status({
            "text_start": "Derived p12 alias",
            "status": self.options.p12_alias,
            "status_color": "red" if self.options.p12_alias == "error" else "green",
            "newline": True,
        })


    def migrate_existing_p12(self):
        try:
            current_user = "root" if not self.user.installing_user else self.user.installing_user
        except:
            if self.options.user:
                current_user = self.options.user
            else:
                self.error_messages.error_code_messages({
                    "error_code": "int-785",
                    "line_code": "invalid_user",
                    "extra": "unable to determine user during install while importing p12 file.",
                    "extra2": "unknown"
                })

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
        
        if not self.options.quick_install:
            self.functions.print_paragraphs([
                ["",1], ["nodectl has detected that an existing p12 migration to this new Node has been requested,",0,"yellow"],
                [f"and now it needs to locate and migrate this private key file. {user_action}.",2,"yellow"],
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
        
        if self.options.quick_install:
            self.functions.print_clear_line(5,{"backwards":True})

        self.functions.print_cmd_status({
            "text_start": "Migrate p12",
            "brackets": p12name_only,
            "status": "complete",
            "status_color": "green",
            "newline": True,
        })
        self.options.p12_path = f"/home/{self.user.username}/tessellation/{p12name_only}"
        

    def prepare_p12_details(self,action=None):
        if action == "init":
            if not self.options.quick_install:
                print("")
                self.functions.print_header_title({
                    "line1": "P12 MIGRATION CHECK",
                    "single_line": True,
                    "show_titles": False,
                    "newline": "both",
                })
                self.functions.print_paragraphs([
                    ["If you choose",0,"white"], ["y",0,"yellow"], ["at the next prompt, later in the installation process;",0,"white"],
                    ["nodectl will search for existing p12 file(s) uploaded to your VPS prior to the installation. It will offer",0,"white"],
                    ["an option menu of found p12 file(s)",0,"white"], ["or",0], 
                    ["allow you to manually supply a full path to your existing p12 file.",2,"white"],
                ])
            self.options.existing_p12 = self.functions.confirm_action({
                "yes_no_default": "n",
                "return_on": "y",
                "prompt": "Are you migrating an existing p12 private key to this Node?",
                "exit_if": False,
            })
            self.functions.print_clear_line(1,{"backwards":True})
            if self.options.quick_install and not self.options.existing_p12:
                self.print_cmd_status("p12 file name","nodeadmin-node.p12",False,False) 
            else:
                if self.options.existing_p12:
                    self.options.p12_path = True
                    if self.options.quick_install:
                        print("")
                        self.migrate_existing_p12()
            return
        
        if self.options.quick_install: return

        # This is done first to save the end user time if they have
        # to upload their p12 on migration 
        if self.options.p12_path:        
            self.functions.print_paragraphs([
                [" BEFORE WE BEGIN ",2,"grey,on_yellow"], 
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

            self.print_main_title()
        else:
            self.functions.print_clear_line(1,{"backwards":True}) 


    def encrypt_passprhase(self):
        if self.options.quick_install:
            self.configurator.quick_install = True
            self.configurator.detailed = False
            encrypt = True
        else:
            self.functions.print_header_title({
                "line1": "ENCRYPTION SERVICES",
                "single_line": True,
                "newline": "both"
            })
            self.functions.print_paragraphs([
                ["Do you want to encrypt the passphrase in your",0],
                ["cn-config.yaml",0,"yellow"], ["configuration file?",1],
            ])
            encrypt = self.functions.confirm_action({
                "yes_no_default": "y",
                "return_on": "y",
                "prompt": "Encrypt?",
                "prompt_color": "magenta",
                "exit_if": False,
            })

        if encrypt:
            self.configurator.detailed = False if self.options.quick_install else "install"
            self.configurator.metagraph_list = self.metagraph_list
            self.configurator.c.config_obj = self.setup_config.config_obj
            self.configurator.prepare_configuration("edit_config")
            self.configurator.passphrase_enable_disable_encryption()
    

    # configuration
    # ===================
                    
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
    

    def build_config_file(self,action):
        skeleton = None
        if action == "skeleton" or action == "quick_install":
            skeleton = self.functions.pull_remote_profiles({
                "retrieve": "config_file"
            })
            if action == "quick_install": return skeleton
            self.config_obj = skeleton[self.options.environment]["json"]["nodectl"]
            self.config_obj["global_elements"] = {
                "caller": "installer",
                "environment_name": self.options.environment,
            }
            
            # download specific file to Node
            try:
                system(f'sudo wget {skeleton[self.options.environment]["yaml_url"]} -O {self.functions.nodectl_path}cn-config.yaml -o /dev/null')
            except Exception as e:
                self.log.logger.critical(f'Unable to download skeleton yaml file from repository [{skeleton[self.options.environment]["nodectl"]["yaml_url"]}] with error [{e}]')
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
                "called_cmd": "install" if not self.options.quick_install else "quick_install",
                "request": "install",
                "config_obj": self.config_obj
            })
            self.version_obj = versioning.get_version_obj()
            self.cli.version_obj = self.version_obj
            self.cli.node_service.version_obj = self.version_obj
            self.cli.node_service.functions.version_obj = self.version_obj
            self.cli.version_obj = self.version_obj

        elif action == "p12":
            if self.options.p12_path:
                self.p12_session.p12_file_location = self.options.p12_path.rsplit('/', 1)[0]+"/"
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


    # class action
    # =====================

    def build_classes(self):
        cli_obj = {
            "caller": "installer",
            "profile": "empty",
            "command": "install",
            "command_list": [],
            "functions": self.functions,
            "ip_address": self.parent.ip_address,
            "skip_services": False
        }
        self.cli = CLI(cli_obj)
        self.cli.functions.set_statics()
        self.user = UserClass(self.cli)
        
        if self.action == "uninstall": return

        self.setup_config = Configuration({
            "implement": False,
            "action": "install" if not self.options.quick_install else "quick_install",
            "argv_list": ["None"]
        })

        self.configurator = Configurator(["--installer"])
        self.configurator.detailed = True if not self.options.quick_install else False

        if self.options.quick_install:
            self.quick_installer = QuickInstaller({
                "parent": self,
            })
            self.user.quick_install = True
    
    
    def print_main_title(self):
        self.functions.print_header_title({
          "line1":  "INSTALLATION REQUEST",
          "line2": "TESSELLATION VALIDATOR NODE",
          "clear": True,
        })    
    

    def print_cmd_status(self,chosen,var,gen=True,lookup=True):
        if lookup: var = getattr(self.options,var)
        start = "Generated" if gen else "Chosen" 
        self.functions.print_cmd_status({
            "text_start": f"{start} {chosen}",
            "status": var,
            "newline": True,
            "status_color": "green",
        })      
    
    
    def uninstall(self):
        self.build_classes()
        node_service = Node({"functions": self.functions})
        uninstaller.start_uninstall(self.functions)
        uninstaller.stop_services(self.functions, node_service)
        uninstaller.restore_user_access(self.cli,self.functions)
        node_admins = uninstaller.remove_data(self.functions)
        uninstaller.remove_admins(self.functions,node_admins)
        uninstaller.finish_uninstall(self.functions)
        uninstaller.remove_nodectl(node_service)

        exit(0)


    def complete_install(self):
        self.log.logger.info("Installation complete ******")
        self.print_main_title()

        self.functions.print_header_title({
            "line1": "INSTALLATION COMPLETE",
            "single_line": True,
            "show_titles": False,
            "newline": "bottom",
        }) 
        
        self.functions.print_paragraphs([
            ["  CONGRATULATIONS!  ",1,"grey,on_green","bold"],
            ["Below you will find your",0], ["nodeid",0,"yellow","bold,underline"], ["which was derived from your p12 file",1],
            ["Please report this nodeid to administrative staff to gain access to the network via the access list permissions.",2,"magenta"]
        ])

        self.functions.print_cmd_status({
            "text_start": "Environment",
            "status": self.options.environment,
            "status_color": "yellow",
            "newline": True,
        })      
        self.functions.print_cmd_status({
            "text_start": "P12 Location",
            "status": path.dirname(self.options.p12_path),
            "status_color": "yellow",
            "newline": True,
        })  
        self.functions.print_cmd_status({
            "text_start": "P12 Name",
            "status": path.basename(self.options.p12_path),
            "status_color": "yellow",
            "newline": True,
        })  
        self.functions.print_cmd_status({
            "text_start": "P12 Alias",
            "status": self.options.p12_alias,
            "status_color": "red" if self.options.p12_alias == "error" else "yellow",
            "newline": True,
        })  

        print("")

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
            for profile in self.functions.clear_global_profiles(self.metagraph_list):
                if self.config_obj[profile]["seed_location"] != "disable":
                    self.cli.check_seed_list(["-p",profile,"-id",self.cli.nodeid])

        self.functions.print_paragraphs([
            ["",1], [f"Please review the next Steps in order to gain access to the {self.options.environment} environment.",0],
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
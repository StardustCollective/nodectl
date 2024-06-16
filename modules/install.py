import json
import distro
import modules.uninstall as uninstaller

from os import makedirs, system, path, environ, get_terminal_size, chmod
from shutil import copy2, move, rmtree
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
from .config.valid_commands import pull_valid_command
from .config.auto_complete import ac_validate_path, ac_build_script, ac_write_file
from .config.time_setup import remove_ntp_services, handle_time_setup

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
        self.p12_migrated = False
        self.encryption_performed = False

        self.action = "install"
        self.metagraph_name = None

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
        self.test_distro()
        self.handle_environment_setup()
        self.build_classes()
        if self.options.quick_install:
            self.quick_installer.quick_install()
        else:
            self.handle_option_validation()
            self.p12_prepare_details()
            self.handle_existing()
            self.build_config_file("skeleton")
            self.build_config_file("defaults")
            self.update_os()
            self.process_distro_dependencies()
            self.download_binaries()
            self.make_swap_file()
            self.setup_user()
            self.create_dynamic_elements()
            self.p12_generate_from_install()
            self.build_config_file("p12")
            self.setup_new_configuration()
            self.p12_encrypt_passphrase()
            self.populate_node_service()
        self.complete_install()
    

    def test_distro(self):
        distro_name = distro.name()
        distro_version = distro.version()
        continue_warn = False

        if distro_name not in ["Ubuntu","Debian"]:
            self.log.logger.warn(f"Linux Distribution not supported, results may vary: {distro_name}")
            if not self.options.quiet:
                self.functions.print_paragraphs([
                    [" WARNING ",0,"yellow,on_red"], 
                    ["nodectl was developed to run on",0,"red"],
                    ["Ubuntu",0,"yellow"], ["or",0,"red"], ["Debian 10",0,"yellow"],
                    ["Linux distributions.  Install results may vary if an install",0,"red"],
                    ["is performed on a non-supported distribution.",2,"red"],
                    ["Distribution found:",0],[distro_name,2,"yellow"],
                ])
                continue_warn = True
        if "Ubuntu" in distro_name:
            if ".10" in distro_version:
                self.log.logger.warn(f"Linux Distribution not long term support, interim release identified... may not be fully supported: {distro_name}")
                if not self.options.quiet:
                    self.functions.print_paragraphs([
                        [" WARNING ",0,"yellow,on_red"], 
                        ["nodectl was developed to run on",0,"red"],
                        ["Ubuntu Long Term Support (TLS)",0,"yellow"], ["or",0,"red"], ["Debian 10",0,"yellow"],
                        ["Linux distributions.",2,"red"],
                        ["This version is identified as a interim release.",2,"red"],
                        ["Install results may vary if an install is performed on a non-supported distribution.",2,"red"],
                        ["Distribution found:",0],[f"{distro_name} {distro_version}",2,"yellow"],

                    ])  
                    continue_warn = True
            elif "22.04" not in distro_version and "20.04" not in distro_version and "18.04" not in distro_version:
                self.log.logger.warn(f"Linux Distribution not supported, results may vary: {distro_name}")
                if not self.options.quiet:
                    self.functions.print_paragraphs([
                        [" WARNING ",0,"yellow,on_red"], 
                        ["nodectl was developed to run on",0,"red"],
                        ["Ubuntu 22.04",0,"yellow"], ["or",0,"red"], ["Debian 10",0,"yellow"],
                        ["Linux distributions.  Install results may vary if an install",0,"red"],
                        ["is performed on a non-supported distribution.",2,"red"],
                        ["Distribution found:",0],[f"{distro_name} {distro_version}",2,"yellow"],

                    ])  
                    if "24.04" in distro_version:
                        self.functions.print_paragraphs([
                            ["Ubuntu 24.04 will be supported as soon as all necessary packages",0],
                            ["used to allow the needed functionality are updated and supported by 24.04.",1],
                            ["Ubuntu 22.04 LTS will reach its end of life in April 2032.",2]

                        ])  
                    continue_warn = True

        if continue_warn: 
            self.options.quick_install = self.functions.confirm_action({
                "yes_no_default": "y",
                "return_on": "y",
                "exit_if": True,
                "prompt": "Continue?",                
            })


    def setup_install(self):
        self.functions.check_sudo()
        self.log.logger.debug(f"installation request started - quick install [{self.options.quick_install}]")
        if not self.options.quiet: self.print_main_title()
        self.parent.install_upgrade = "installation"

        if not self.options.quiet:
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

        if self.options.normal_install:
            self.log.logger.info("installer -> long normal option chosen by Node Operator option input.")
        elif not self.options.quick_install and not self.options.confirm_install:
            self.functions.print_paragraphs([
                [" QUICK INSTALL ",0,"yellow,on_blue"], ["nodectl's installer provides a",0,"white","bold"], 
                ["quick install",0,"blue","bold"], ["option that utilizes all the",0,"white","bold"], ["recommended",0,"green","bold"],
                ["default settings. This allows for a streamlined process, requiring minimal input from the future Node Operator.",2,"white","bold"],

                ["Alternatively,",0,"yellow"], ["you can choose a customization mode, step-by-step installation, where nodectl will ask you questions and provide explanations",0,"white","bold"],
                ["for the necessary elements to customize the installation of your node.",2,"white","bold"],
            ])
            self.options.quick_install = self.functions.confirm_action({
                "yes_no_default": "y",
                "return_on": "y",
                "exit_if": False,
                "prompt": "Install using quick install option?",                
            })

        if self.options.quick_install and not self.options.confirm_install:
            self.functions.print_clear_line(10,{"backwards":True, "bl":-1})
            self.functions.print_paragraphs([
                [" QUICK INSTALL REQUESTED ",2,"white,on_green"],
                [" WARNING ",1,"red,on_yellow"], 
                ["Even though this is the recommended options, nodectl will use all recommended settings without prompting for confirmations, be sure this is acceptable before continuing",0],
                ["with this setting.",2], 
                
                ["*","half","red","bold"],
                ["This includes removal of existing Tessellation and nodectl service, p12, and other configuration files if present.",1,"red"],
                ["*","half","red","bold"],["",1],

                ["A few mandatory entries may be necessary; hence, nodectl will now prompt a series of questions before proceeding with the",0],
                ["installation. If these options were already entered through the command line interface (CLI),",0],
                ["the corresponding questions will be skipped.",2],
                ["nodectl",0,"yellow"], ["quick install",0,"yellow","bold"], ["will not offer detailed explanation for various prompt requests, please use the normal installation",0,"yellow"],
                ["or read the documentation.",1,"yellow"], 
                ["https://docs.constellationnetwork.io/validate/",2,"blue","bold"],
            ])

        if not self.options.quiet:
            while True:
                term_width_test = get_terminal_size()
                if term_width_test.columns < 85:
                    self.functions.print_paragraphs([
                        [" WARNING ",1,"red,on_yellow"], 
                        ["nodectl has detected that the terminal size WIDTH is too narrow.",0,"red"],
                        ["to properly display the installer's progress indicators. While this",0,"red"],
                        ["won't affect the installation itself, it may impact the user experience.",2,"red"],
                        ["detected column width:",0],[f"{term_width_test.columns}",1,"yellow"],
                        ["To improve the display, you can optionally widen your terminal window by clicking on the terminal emulator window and dragging it out to at",0],
                        ["least",0], ["85",0,"green","bold"], ["columns.",2],
                    ])
                    next_step = self.functions.print_any_key({
                        "quit_option": True,
                        "return_key": True,
                    })
                    if next_step == "q": 
                        cprint("  Installation existed by Node Operator request","green",attrs="bold")
                        exit(0)

                    print("")
                else:
                    self.functions.print_clear_line(1,{"backwards":True})
                    break

        if not self.options.confirm_install:
            self.parent.confirm_int_upg()

        if not self.options.quiet:
            self.print_main_title()
            self.functions.print_header_title({
                "line1": "INSTALLATION STARTING",
                "single_line": True,
                "show_titles": False,
                "newline": "bottom",
            }) 
    
    
    # Node Options and Values
    # =====================
        
    def handle_quiet_mode(self):
        if not self.options.quiet: return

        quiet_requirements = [
            "cluster_config",
            "user_password","p12_passphrase",
            "quick_install"
        ]

        for quiet in quiet_requirements:
            if not self.options_dict[quiet]:
                self.error_messages.error_code_messages({
                    "error_code": "int-354",
                    "line_code": "install_failed",
                    "extra": "quiet mode requested without proper arguments or during a normal installation, must be quick install only. Please see documentation for further details."
                })                


    def handle_options(self):
        self.options_dict = OrderedDict()

        # option list must be in order otherwise values will not properly populate
        # cluster-config will be used to determine config to download if supplied
        option_list = [
            "--cluster-config",
            "--user", "--p12-destination-path", 
            "--user-password","--p12-passphrase",
            "--p12-migration-path", "--p12-alias",
            "--quick-install", "--normal", "--json-output",
            "--confirm","--override","--quiet",
        ]
        
        self.options_dict["quick_install"] = False
        self.options_dict["configuration_file"] = False
        self.options_dict["normal_install"] = False
        self.options_dict["confirm_install"] = False
        self.options_dict["override"] = False
        self.options_dict["quiet"] = False
        self.options_dict["json_output"] = False
        for option in option_list:
            if option.startswith("--"): o_option = option[2::]
            if o_option == "quick-install" and "--quick-install" in self.argv_list: 
                self.options_dict["quick_install"] = True
                continue
            if o_option == "normal" and "--normal" in self.argv_list: 
                self.options_dict["normal_install"] = True
                continue
            if o_option == "confirm" and "--confirm" in self.argv_list: 
                self.options_dict["confirm_install"] = True
                continue
            if o_option == "override" and "--override" in self.argv_list: 
                self.options_dict["override"] = True
                continue
            if o_option == "json-output" and "--json-output" in self.argv_list: 
                self.options_dict["json_output"] = True
                continue
            if o_option == "quiet" and "--quiet" in self.argv_list: 
                self.log.logger.warn("installer found --quiet request when executing installer.  This is an ADVANCED option that requires all non-default options to be added at the command line.  Failure to do so may result in undesirable install, unstable execution of nodectl, or a failed installation.")
                self.options_dict["quiet"] = True
                self.options_dict["confirm_install"] = True
                continue
            self.options_dict[o_option] = self.argv_list[self.argv_list.index(option)+1] if option in self.argv_list else False

        self.options_dict = { key.replace("-","_"): value for key, value in self.options_dict.items() }
        self.options_dict["environment"] = False
        self.options_dict["metagraph_name"] = False
        self.options_dict["existing_p12"] = False

        self.options = SimpleNamespace(**self.options_dict)
        self.handle_quiet_mode()

        if self.options.p12_migration_path:
            self.log.logger.info(f"installer found --p12-migration-path request [{self.options.p12_migration_path}]")
            self.options.existing_p12 = True

        if self.options.cluster_config:
            self.log.logger.info(f"installer found --migration-request request [{self.options.cluster_config}]")
            self.options.configuration_file = self.options.cluster_config+".yaml"
            self.options.metagraph_name = self.options.cluster_config

        if self.options.quick_install:
            self.log.logger.info("installer identified quick installation")
            if self.options.p12_destination_path and not self.options.p12_alias:
                self.log.logger.warn("installer -> p12 alias not supplied - will try to derive it dynamically.")


    def handle_option_validation(self):
        if self.options.override and not self.options.quick_install:
            self.error_messages.error_code_messages({
                "error_code": "int-235",
                "line_code": "invalid_option",
                "extra": "--override",
                "extra2": "The '--override' option can only be used in conjunction with the '--quick-install' option."
            })

        for option, value in self.options_dict.items():
            if isinstance(value,bool):
                if option == "p12_destination_path":
                    self.p12_prepare_details("init")
                elif option == "cluster_config" and not self.options.cluster_config: 
                    if not self.options.cluster_config:
                        self.handle_environment_setup(True)
                        self.options.metagraph_name = self.options.cluster_config
                        if not self.options.quiet: print("")
                        self.print_cmd_status("metagraph_name","metagraph_name",False)
                elif self.options.quick_install:
                    self.quick_installer.handle_option_validation(option)

            elif option == "metagraph_name":
                self.print_cmd_status("metagraph","metagraph_name",False) 
            elif option == "p12_destination_path":
                if not value.endswith(".p12"):
                    self.close_threads()
                    self.error_messages.error_code_messages({
                        "error_code": "int-133",
                        "line_code": "invalid_file_format",
                        "extra": value,
                        "extra2": "p12 file must end with the '.p12' extension."
                    })    
                self.print_cmd_status("P12 file",path.split(value)[1],False,False)   

            elif option == "p12_migration_path":                  
                self.print_cmd_status("P12 migration path",path.split(value)[0],False,False)   
            elif option == "p12_alias":
                self.print_cmd_status("P12 alias","p12_alias",False)
            elif option == "user":
                if self.options.quick_install and self.options.user:
                    self.user.username = self.options.user
                self.print_cmd_status("Node admin user","user",False)

        self.build_classes("p12")

        if self.options.quick_install:
            if not self.options.user_password:
                self.user.ask_for_password()
                self.options.user_password = self.user.password
                self.p12_session.user.password = self.options.user_password

            if not self.options.p12_passphrase:
                self.p12_session.ask_for_keyphrase()
                self.options.p12_passphrase = self.p12_session.p12_password
                self.p12_session.p12_password = self.options.p12_passphrase

        return     
    

    def handle_environment_setup(self,do=False):
        if (self.options.quick_install and do == False) or self.options.quiet: return
        if self.options.quiet: return

        self.log.logger.info("installer -> setting up cluster environment details.")

        if not self.options.cluster_config and not self.options.quick_install:
            self.functions.print_paragraphs([
                ["For a new installation, the Node Operator can choose to build this Node based",0,"green"],
                ["on various network clusters or Metagraph pre-defined configurations.",2,"green"],
                
                ["If the network cluster or Metagraph this Node is being built to participate on is not part of this list, it is advised to",0],
                ["choose",0], ["mainnet",0,"red,on_yellow"], ["as the default to complete the installation.",2], 
                ["The MainNet configuration template will only be a placeholder to allow this Node to install all",0],
                ["required components, to ensure successful implementation of this utility.",0],
                
                ["If a pre-defined network cluster or Metagraph listed above is not the ultimate role of this future Node,",0],
                ["following a successful installation, the next steps should be for you to refer to the Metagraph",0],
                ["Administrators of the Metagraph you are expected to finally connect with. The Administrator",0,],
                ["will offer instructions on how to obtain the required configuration file for said Metagraph.",2],
                ["Please key press number of a network cluster or Metagraph configuration below:",2,"blue","bold"],
            ])

        if not self.options.configuration_file:
            print("")
            self.functions.print_paragraphs([
                [" ",1],
                ["Please choose which Hypergraph or Metagraph you would like to install on this server:",2],
                ["HYPERGRAPH or METAGRAPH",1,"yellow","bold"],
                ["predefined choices",1,"blue","bold"],
                ["-","half","blue","bold"]
        ])

        self.options.cluster_config = self.functions.pull_remote_profiles({
            "r_and_q":"q", 
            "add_postfix": True, 
            "option_color": "blue",
            "required": self.options.configuration_file
        })
        if self.options.cluster_config.lower() == "q":
            cprint("  Installation cancelled by user\n","red")
            exit(0)
        
                
    def handle_existing(self):
        if self.options.override: return

        if not self.options.quick_install and not self.options.quiet: 
            self.parent.print_ext_ip()

        self.log.logger.info("installer -> review future node for invalid old Node install or data.")

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
                    
                    ["*","half","red","bold"],
                    [" IMPORTANT ",0,"yellow,on_red"], ["Any existing tessellation",0,"red"],
                    ["configuration",0,"yellow","bold"], [",",-1,"red"],
                    ["p12",0,"yellow","bold"], [", and/or",-1,"red"],
                    ["service",0,"yellow","bold"],
                    ["files will be removed from this server.",1,"red"],
                    ["*","half","red","bold"],["",1],

                    ["This installation cannot continue unless the old configuration file is removed.",2,"red"],

                    ["You can exit here, backup important files and use the uninstall first or continue.  If you continue, nodectl will first remove existing configurations and  elements.",2]
                ])
                self.functions.confirm_action({
                    "yes_no_default": "n",
                    "return_on": "y",
                    "prompt": "continue?",
                    "prompt_color": "red",
                    "exit_if": True,
                })
                if self.options.quick_install:
                    self.functions.print_clear_line(1,{"backwards":True,"fl":1})

            if not self.options.quick_install:
                self.print_main_title()
                self.functions.print_header_title({
                    "line1": "HANDLE EXISTING DATA",
                    "single_line": True,
                    "show_titles": False,
                    "newline": "bottom",
                })

            uninstaller.remove_data(self.functions,self.log,True,self.options.quiet)
            if not self.options.quick_install:
                self.functions.print_cmd_status({
                    "text_start": "Clean up old configuration data",
                    "status": "complete",
                    "status_color": "green",
                    "newline": True,
                })

            return


    def handle_auto_complete(self):
        self.log.logger.info("installer -> creating auto_complete script")

        if not self.options.quick_install: 
            progress = {
                "text_start": "Creating auto_complete updates",
                "status": "running",
                "status_color": "yellow",
                "newline": False,
            }
            self.functions.print_cmd_status({
                **progress,
                "delay": .8,
            })

        auto_path = ac_validate_path(self.log,"installer")
        auto_complete_file = ac_build_script(self.cli,auto_path)
        ac_write_file(auto_path,auto_complete_file,self.functions)

        if not self.options.quick_install: 
            self.functions.print_cmd_status({
                **progress,
                "status": "complete",
                "status_color": "green",
                "newline": True,
            })


    def populate_node_service(self):
        self.log.logger.info("installer -> populating node services module")
        if not self.options.quick_install:                
            progress = {
                "text_start": "Creating Services",
                "status": "running",
            }
            self.functions.print_cmd_status(progress)

        self.cli.node_service.profile_names = self.functions.clear_global_profiles(self.metagraph_list)
        self.cli.node_service.build_service(True) # true will build restart_service
        
        # handle version_service enablement
        for cmd in ["daemon-reload","enable node_version_updater.service","restart node_version_updater.service"]:
            _ = self.functions.process_command({
                "bashCommand": f"sudo systemctl {cmd}",
                "proc_action": "subprocess_devnull",
            }) 
            sleep(.3)
        
        if not self.options.quick_install: 
            self.functions.print_cmd_status({
                **progress,
                "status": "complete",
                "newline": True,
                "delay": .8
            })
    

    def download_binaries(self):  
        self.log.logger.info("installer -> installing binaries")
        download_version = self.version_obj[self.options.environment][self.metagraph_list[0]]["cluster_metagraph_version"]
        if self.options.metagraph_name == "hypergraph":
            download_version = self.version_obj[self.options.environment][self.metagraph_list[0]]["cluster_tess_version"]

        download_action = "install"
        if self.options.quick_install: download_action = "quick_install"
        if self.options.quiet: download_action = "quiet_install"

        pos = self.cli.node_service.download_constellation_binaries({
            "download_version": download_version,
            "environment": self.options.environment,
            "action": download_action,
            "tools_version": self.version_obj[self.options.environment][self.metagraph_list[0]]["cluster_tess_version"],
        })
        status = "complete" if pos["success"] else "failed"
        sleep(.8)
        if not self.options.quiet:
            if self.options.quick_install:
                print(f"\033[{pos['up']}A", end="", flush=True)
                self.functions.print_clear_line(pos['clear'],{"fl": pos['clear']})
                print(f"\033[{pos['reset']}A", end="", flush=True)
            else:
                print(f"\033[{pos['down']}B", end="", flush=True)

        if status == "failed":
            self.close_threads()
            self.error_messages.error_code_messages({
                "error_code": "int-354",
                "line_code": "install_failed",
                "extra": "unable to download required Constellation network Tessellation files"
            })

        if not self.options.quiet:
            self.functions.print_cmd_status({
                "text_start": "Installing Tessellation binaries",
                "status": status,
                "newline": True
            })
    

    # Distribution
    # =====================

    def update_os(self):
        self.log.logger.info("installer -> updating distribution packages list prior to attempting to install dependencies")
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
        self.log.logger.info("installer -> setting up user details.")
        if self.options.user:
            self.user.username = self.options.user
        if self.options.user_password:
            self.user.password = self.options.user_password
        
        if self.options.quick_install:
            if quick_ssh: 
                # second element of quick install
                self.user.transfer_ssh_key()
            else: self.user.create_debian_user()
        else:
            self.functions.print_any_key({"newline":"top"})
            if not self.options.user and not self.options.user_password:
                self.user.setup_user()
            else:
                if not self.options.user:
                    self.user.ask_for_username()
                if not self.options.user_password:
                    self.user.ask_for_password()
                self.user.create_debian_user()
                self.user.transfer_ssh_key()
        
        # update permissions
        self.functions.set_chown(path.dirname(self.options.p12_destination_path), self.user.username,self.user.username)
        self.functions.set_chown(f"/home/{self.user.username}", self.user.username,self.user.username)
        return


    def create_dynamic_elements(self):
        self.log.logger.info("installer -> Node structural requirements.")

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
                ["network variables",2,"blue","bold"],
                
                ["Network Cluster:",0], [self.options.metagraph_name,0,"yellow"], ["->",0], [self.options.environment,2,"yellow"],
                
                ["After installation is complete, the Node Operator may alter the",0,"magenta"], ["nodectl",0,"blue","bold"],
                ["configuration to allow connection to the",0,"magenta"], ["network cluster or Metagraph",0,"blue","bold"], ["of choice via the command:",2,"magenta"],
                
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
        self.log.logger.info("installer -> downloading and installing dependency binaries")

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
                if package == "openjdk-11-jdk" and not self.options.quiet:
                    print(colored(f"  {package}","cyan",attrs=['bold']),end=" ")
                    print(colored("may take a few minutes to install".ljust(40),"cyan"),end=" ")
                    print(" ".ljust(10))

                self.log.logger.info(f"installation process installing [{package}]")
                with ThreadPoolExecutor() as executor:
                    self.functions.status_dots = True
                    self.log.logger.info(f"updating the Debian operating system.")
                    environ['DEBIAN_FRONTEND'] = 'noninteractive'
                    
                    if not self.options.quiet:
                        _ = executor.submit(self.functions.print_cmd_status,{
                            "text_start": "Installing dependency",
                            "brackets": package,
                            "dotted_animation": True,
                            "timeout": False,
                            "status": "installing",
                            "status_color": "yellow",
                        })
                            
                    bashCommand = f"apt-get install -y {package}"
                    if package == "ntp":
                        bashCommand += " ntpdate -oDpkg::Options::='--force-confdef' -o Dpkg::Options::='--force-confold'"

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
                    if not self.options.quiet:
                        self.functions.print_cmd_status({
                            "text_start": "Installing dependency",
                            "brackets": package,
                            "status": "complete",
                            "newline": True
                        })
        remove_ntp_services()
        handle_time_setup(self.functions,self.options.quick_install,False,self.options.quiet,self.log)
        

    def make_swap_file(self):
        self.log.logger.info("installer -> preparing to create swapfile")
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
            self.log.logger.warn("installer -> swap file already exists - install skipping action")
            result = "already exists"
            color = "magenta"
            self.log.logger.warn("Installation making swap file skipped because already detected")
        else:
            self.log.logger.info("Installation making swap file")

            for n, cmd in enumerate([
                "touch /swapfile",
                "fallocate -l 8G /swapfile",
                "systemctl restart node_version_updater.service",
                "mkswap /swapfile",
                "swapon /swapfile",
            ]):
                _ = self.functions.process_command({
                    "bashCommand": f"sudo {cmd}",
                    "proc_action": "subprocess_devnull",
                }) 
                if n == 1:
                    sleep(1)
                    chmod("/swapfile",0o600)
                sleep(.8)

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
                    copy2("/etc/fstab","/etc/fstab.bak")
                    with open("/etc/fstab", 'a') as file:
                        file.write("/swapfile none swap sw 0 0\n")
            except:
                self.log.logger.error("installation unable to update fstab to enable swapfile properly.")

            try:
                if not self.functions.test_or_replace_line_in_file({
                        "file_path": "/etc/sysctl.conf",
                        "search_line": "vm.swappiness=",                    
                    }):
                    # backup the file just in case
                    copy2("/etc/sysctl.conf","/etc/sysctl.conf.bak")
                    with open("/etc/sysctl.conf", 'a') as file:
                        file.write("vm.swappiness=10\n")
            except:
                self.log.logger.error("installation unable to update systctl to fix swapfile swapiness settings permanently.")

            if not self.options.quick_install:
                self.functions.print_cmd_status({
                    **progress,
                    "brackets": "swappiness",
                })  
                          
            try:
                # turn it on temporarily until next reboot
                _ = self.functions.process_command({
                    "bashCommand": "sysctl vm.swappiness=10",
                    "proc_action": "subprocess_devnull",
                })
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
        
    def p12_generate_from_install(self,generate=False):
        self.log.logger.info("installer -> handle p12 generation if required.")
        if self.options.existing_p12 and not self.p12_migrated: 
            self.p12_migrate_existing()

        if not self.p12_session:
            self.build_classes("p12")

        self.p12_session.user = self.user # rebuild
        
        if self.options.quick_install:
            if generate and not self.options.existing_p12:
                self.p12_session.p12_file_location, self.p12_session.p12_filename = path.split(self.options.p12_destination_path) 
                self.p12_session.key_alias = self.options.p12_alias
                self.p12_session.p12_password = self.options.p12_passphrase
                self.p12_session.generate()
                self.options.existing_p12 = True
        else:
            if self.options.p12_destination_path:
                self.p12_session.p12_file_location = path.split(self.options.p12_destination_path)[0]
                self.p12_session.p12_filename = path.split(self.options.p12_destination_path)[1]
            else:
                if self.options.p12_migration_path:
                    self.p12_session.p12_filename = path.split(self.options.p12_migration_path)[1]
                    self.p12_session.ask_for_location()
                else:
                    self.p12_session.ask_for_p12name()
                    self.p12_session.ask_for_location() 
                self.options.p12_destination_path = f"{self.p12_session.p12_file_location}{self.p12_session.p12_filename}"
                
            if self.options.p12_passphrase:
                self.p12_session.p12_password = self.options.p12_passphrase
            else:
                self.p12_session.ask_for_keyphrase()

            if self.options.p12_alias:
                self.p12_session.key_alias = self.options.p12_alias
            elif not self.options.existing_p12:
                self.p12_session.ask_for_file_alias() 
                self.options.p12_alias = self.p12_session.key_alias

            if not self.options.existing_p12:
                self.p12_session.generate()   

        if generate:
            if not self.options.p12_destination_path:
                self.options.p12_destination_path = f"{self.p12_session.p12_file_location}/{self.p12_session.p12_filename}"
                self.options.p12_destination_path = self.functions.cleaner(self.options.p12_destination_path,"double_slash")
            if not self.options.p12_passphrase:
                self.options.p12_passphrase = self.p12_session.p12_password
            if not self.options.p12_alias and not self.options.existing_p12:
                self.options.p12_alias = self.p12_session.key_alias
       

    def p12_derive_alias(self,verify=False):
        self.log.logger.info("installer -> attempting to derive p12 alias...")
        if not self.options.quick_install:
            self.functions.print_cmd_status({
                "text_start": "Deriving p12 alias",
                "brackets": self.options.p12_destination_path.split("/")[-1],
                "status": "running",
                "status_color": "yellow",
            })

        if not self.options.p12_passphrase:
            try:
                self.options.p12_passphrase = self.p12_session.p12_password
            except:
                self.log.logger.warn("installer unable to obtain p12 passphrase, unexpected results on the installer may be presented, but may not affect the installation.")
                
        try:
            self.options.p12_alias = self.p12_session.show_p12_details(
                ["--file",self.options.p12_destination_path,"--installer",self.options.p12_passphrase,"--alias","--return"]
            )
        except:
            self.log.logger.critical(f"installer was unable to derive the p12 alias from the p12 keystore [{self.options.p12_destination_path}].  Please manually update the configuration in order to properly join the necessary cluster(s).")
            self.options.p12_alias = "error"
            self.found_errors = True
        else:
            if not self.options.p12_alias:
                self.found_errors = True
                self.options.p12_alias = "unable_to_derive"

        if verify:
            if verify != self.options.p12_alias:
                self.log.logger.error(f"installer -> found requested option alias [{verify}] but found [{self.options.p12_alias}] error found [{'true' if not self.found_errors else 'false'}]")
                self.log.logger.warn(f"installer ->  using found [{self.options.p12_alias}] which might cause user errors in the future.  Important, if this was a quick installation, nodectl will create a default alias that may not match a migrated p12 file, without an alias supplied; in this case, this warning can be ignored.")

        if self.options.quick_install: return

        self.functions.print_cmd_status({
            "text_start": "Derived p12 alias",
            "status": self.options.p12_alias,
            "status_color": "red" if self.options.p12_alias == "error" else "green",
            "newline": True,
        })


    def p12_display_existing_list(self):
        try:
            current_user = "root" if not self.user.installing_user else self.user.installing_user
        except:
            if self.options.user:
                current_user = self.options.user
            else:
                self.close_threads()
                self.error_messages.error_code_messages({
                    "error_code": "int-785",
                    "line_code": "invalid_user",
                    "extra": "unable to determine user during install while importing p12 file.",
                    "extra2": "unknown"
                })

        location = False
        
        possible_found = self.functions.get_list_of_files({
            "paths": ["root","home","var/tessellation/","var/tmp","tmp"],
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
        
        if self.options.p12_migration_path:
            location = self.options.p12_migration_path
        else:
            try:
                for option, value in possible_found.items():
                    self.functions.print_paragraphs([
                        [f"{option}",0,"magenta","bold"], [")",-1,"magenta"], [value,1,"green"]
                    ])
            except:
                self.functions.print_paragraphs([
                    [" WARNING ",0,"red,on_yellow"],["Unable to location existing p12 files on this VPS.",1,"red"],
                ])
            else:
                self.functions.print_paragraphs([
                    [f"{len(possible_found)+1}",0,"magenta","bold"], [")",-1,"magenta"], ["input manual entry",2,"green"]
                ])
                possible_found[f"{len(possible_found)+1}"] = "custom"
            
            location = "custom" # set default to custom 
            if len(possible_found) > 1:
                try:
                    location = self.functions.get_user_keypress({
                        "prompt": "KEY PRESS an option",
                        "prompt_color": "magenta",
                        "options": list(possible_found.keys())
                    })  
                    location = possible_found[location]
                except:
                    self.close_threads()
                    self.error_messages.error_code_messages({
                        "error_code": "int-484",
                        "line_code": "invalid_search",
                        "extra": "Did you properly upload a p12 file?"
                    })
                
        if verb == "example" or location == "custom": 
            self.functions.print_paragraphs([
                ["a",0,"yellow"],[") to abort",-1],["",1],
            ])
            exist_location_str = colored("  Please enter full path including p12 file key: ","cyan")
            while True:
                location = input(exist_location_str)
                if path.exists(location):
                    break
                if location.lower() == "a":
                    cprint("  Aborting migration...","yellow")
                    location = False
                    self.options.existing_p12 = False
                    self.p12_migrated = False
                    break
                self.functions.print_paragraphs([
                    ["invalid location of file name, please try again.",1,"bold"],
                ])
        
        if not path.exists(f"/home/{self.user.username}/tessellation/"):
            makedirs(f"/home/{self.user.username}/tessellation/")

        self.options.p12_migration_path = location
    
    
    def p12_migrate_existing(self):
        self.log.logger.info("installer -> migrating p12.") 
        if not self.options.p12_migration_path:
            self.p12_display_existing_list()
        if not self.options.existing_p12:
            return  # user aborted manual p12
        
        is_migration_path_error = False
        
        try:
            p12file = path.split(self.options.p12_migration_path)[1]
        except:
            is_migration_path_error = True
        else:
            if not path.exists(self.options.p12_migration_path):
                is_migration_path_error = True

        if is_migration_path_error:
            self.close_threads()
            self.error_messages.error_code_messages({
                "error_code": "int-827",
                "line_code": "file_not_found",
                "extra": self.options.p12_migration_path if isinstance(self.options.p12_migration_path,str) else "unknown",
                "extra2": "Are you sure your uploaded the proper p12 file?"
            })

        if not p12file.endswith(".p12"):
            self.close_threads()
            self.error_messages.error_code_messages({
                "error_code": "int-837",
                "line_code": "invalid_file_format",
                "extra": self.options.p12_migration_path if isinstance(self.options.p12_migration_path,str) else "unknown",
                "extra2": "Are you sure your uploaded the proper p12 file?"
            })     

        dest_p12_destination_path = f"/home/{self.user.username}/tessellation/{p12file}"
        if self.options.p12_destination_path:
            dest_p12_destination_path = self.options.p12_destination_path
        else:
            self.options.p12_destination_path = dest_p12_destination_path

        dest_p12_destination_path_only = path.split(dest_p12_destination_path)[0]
        if not path.exists(dest_p12_destination_path_only):
            makedirs(dest_p12_destination_path_only)

        move(self.options.p12_migration_path, dest_p12_destination_path)
        chmod(dest_p12_destination_path, 0o400)
        try:
            self.functions.set_chown(dest_p12_destination_path, "root","root")
            self.p12_migrated = True
        except Exception as e:
            self.log.logger.error("installer -> unable to set permissions, please verify permission settings.")
    
        if self.options.quick_install:
            return

        if not self.options.quick_install and self.options.p12_destination_path:
            self.options.p12_destination_path = dest_p12_destination_path

        self.functions.print_cmd_status({
            "text_start": "Migrate p12",
            "brackets": p12file,
            "status": "complete",
            "status_color": "green",
            "newline": True,
        })
        

    def p12_prepare_details(self,action=None):
        self.log.logger.info("installer -> preparing p12 details.")
        if action == "init":
            if not self.options.quick_install:
                if not self.options.existing_p12:
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

            if not self.options.existing_p12 and not self.options.quiet:
                self.options.existing_p12 = self.functions.confirm_action({
                    "yes_no_default": "n",
                    "return_on": "y",
                    "prompt": "Are you migrating an existing p12 private key to this Node?",
                    "exit_if": False,
                })
                if self.options.quick_install:
                    self.functions.print_clear_line(1,{"backwards":True})

            # note: if there is not a p12_destination_path, it will be formulated after the Node Operator
            #       chooses a username, later in the installation.
                
            if self.options.quick_install and not self.options.existing_p12:
                if not self.options.p12_destination_path:
                    self.options.p12_destination_path = f"/home/{self.options.user}/tessellation/{self.options.user}-node.p12"
                self.print_cmd_status("p12 file name",path.split(self.options.p12_destination_path)[1],False,False)

            if self.options.existing_p12:
                if self.options.quick_install:
                    if not self.options.quiet: print("")
                    self.p12_migrate_existing()
            return
        
        if self.options.quick_install: return

        # This is done first to save the end user time if they have
        # to upload their p12 on migration 
        if self.options.p12_migration_path or self.options.existing_p12:        
            self.functions.print_paragraphs([
                ["",1], [" BEFORE WE BEGIN ",2,"grey,on_yellow"], 
                ["If",0,"cyan","bold,underline"], ["this Node will be using",0],
                ["an existing",0], ["p12 private key",0,"yellow","bold"], [", the installation should be exited and the",-1],
                ["existing",0,"yellow","bold"], ["p12 private key uploaded to a known secure local directory on this server.",0],
                ["Alternatively, you can simply pause here and upload the p12 private key file, and then continue.",2],
                
                ["Please see the Constellation Doc Hub Validator section for instructions on how to do this.",2,"magenta"],
                
                ["Later in the installation, the Node Operator will be given the opportunity to migrate over the existing p12 private key.",0],
                ["At the necessary time, a request for the",0], ["p12 name",0,"yellow","bold"], ["and",0], ["directory location",0,"yellow","bold"],
                ["will be given.",0], ["Once nodectl understands where the p12 file is located and necessary credentials, it will then be migrated by the installation to the proper location.",2],

                ["Alternatively, you can pause here, open a new terminal, upload the p12 private key to this VPS, then return to this terminal and continue the installation.",2]
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


    def p12_encrypt_passphrase(self):
        if self.options.p12_alias == "error": 
            self.log.logger.error("installer -> unable to encrypt passphrase because the p12 file associated with this installation was unable to be authenticated, passphrase could be incorrect")
            return
        
        self.log.logger.info("installer -> encrypting p12 passphrase.")
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
            self.encryption_performed = True
            self.configurator.detailed = False if self.options.quick_install else "install"
            self.configurator.metagraph_list = self.metagraph_list
            self.configurator.c.config_obj = self.setup_config.config_obj
            if self.found_errors:
                self.encryption_performed = False
                self.log.logger.error("installer -> There may be an issue with your p12 values, installer cannot encrypt the private key store passphrase.  Please fix any issues and use the configure module to encrypt later if desired.")
            else:
                self.configurator.prepare_configuration("edit_config")
                self.configurator.passphrase_enable_disable_encryption("install")
        else:
            # user requested to skip encryption
            self.encryption_performed = True # avoid user error message
    

    # configuration
    # ===================
                    
    def setup_new_configuration(self):
        self.log.logger.info("installer -> rebuild node and services configurations.")
        self.setup_config.config_obj = {
            **self.config_obj,
            **self.setup_config.config_obj,
            **self.functions.config_obj,
            "upgrader": True
        }
        self.log.logger.info("installer -> populating node service variables for build")
        self.setup_config.functions.set_install_statics()
        self.setup_config.versioning = self.versioning
        self.setup_config.build_yaml_dict(False,False)
        self.setup_config.setup_config_vars()
        self.setup_config.p12 = self.p12_session
        self.setup_config.p12.config_obj = self.setup_config.config_obj
        if self.options.p12_alias != "error": # most likely passphrase invalid
            self.setup_config.setup_p12_aliases("global_p12")
        # replace cli and node service config object with newly created obj
        self.cli.functions.config_obj = self.setup_config.config_obj
        self.cli.node_service.config_obj = self.setup_config.config_obj
        # replace cli and functions object with newly created obj
        self.cli.node_service.functions = self.cli.functions
        self.cli.node_service.functions.set_statics()
    

    def build_config_file(self,action):
        self.log.logger.info("installer -> rebuild node and services configurations.")
        skeleton = None

        if action == "skeleton" or action == "quick_install":
            if not isinstance(self.options.cluster_config,dict):
                skeleton = self.functions.pull_remote_profiles({
                    "retrieve": "config_file"
                })
                skeleton_yaml = skeleton[self.options.cluster_config]["yaml_url"]

            if action == "quick_install": return skeleton

            if not self.options.metagraph_name:
                self.config_obj = skeleton[self.options.cluster_config]["json"]["nodectl"]
            else:
                try:
                    self.config_obj = skeleton[self.options.metagraph_name]["json"]["nodectl"]
                except:
                    self.config_obj = self.options.cluster_config["json"]["nodectl"]
                    skeleton_yaml = self.options.cluster_config["yaml_url"]

            self.config_obj["global_elements"] = {
                "caller": "installer",
                **self.config_obj["global_elements"],
            }
            
            # download specific file to Node
            try:
                self.functions.download_file({
                    "url": skeleton_yaml,
                    "local": f"{self.functions.nodectl_path}cn-config.yaml"
                })
            except Exception as e:
                self.log.logger.critical(f'Unable to download skeleton yaml file from repository [{skeleton_yaml}] with error [{e}]')
                self.close_threads()
                self.error_messages.error_code_messages({
                    "error_code": "int-149",
                    "line_code": "download_yaml",
                })
        
        elif action == "defaults":
            self.options.metagraph_name = self.config_obj["global_elements"]["metagraph_name"]
            self.options.environment = self.config_obj[next(iter(self.config_obj.keys()))]["environment"]
            self.setup_config.config_obj = self.config_obj
            self.metagraph_list = self.functions.clear_global_profiles(self.config_obj)
            self.setup_config.metagraph_list = self.metagraph_list
            self.setup_config.functions.set_install_statics()
            self.config_obj = self.setup_config.setup_config_vars()
            self.functions.config_obj = self.config_obj
            self.cli.node_service.config_obj = self.config_obj
            self.functions.set_statics()
            self.cli.functions.set_statics()
            self.cli.node_service.functions.set_statics()
            self.functions.profile_names = self.metagraph_list
            self.versioning = Versioning({
                "called_cmd": "install" if not self.options.quick_install else "quick_install",
                "request": "install",
                "config_obj": self.config_obj,
                "show_spinner": True if not self.options.quiet else False,
            })
            self.version_obj = self.versioning.get_version_obj()
            self.cli.version_obj = self.version_obj
            self.cli.node_service.version_obj = self.version_obj
            self.cli.node_service.functions.version_obj = self.version_obj
            self.cli.version_obj = self.version_obj

        elif action == "p12":
            if self.options.p12_destination_path:
                # self.p12_session.p12_file_location = self.options.p12_destination_path.rsplit('/', 1)[0]+"/"
                self.p12_session.p12_file_location, self.p12_session.p12_filename  = path.split(self.options.p12_destination_path)

            try:
                _ = self.p12_session.key_alias
            except:
                self.p12_derive_alias(self.options.p12_alias)
                self.p12_session.key_alias = self.options.p12_alias

            if self.p12_session.p12_password == "blank" or self.p12_session.p12_password == "":
                self.p12_session.p12_password = self.options.p12_passphrase

            if not self.options.p12_destination_path:
                self.options.p12_destination_path = f"{self.p12_session.p12_file_location}{self.p12_session.p12_filename}"

            p12_replace_list = [
                ("passphrase", f'"{self.p12_session.p12_password}"'),
                ("key_location",self.p12_session.p12_file_location),
                ("key_name", self.p12_session.p12_filename),
                ("key_alias",self.p12_session.key_alias),
                ("nodeadmin",self.user.username),
            ]

            # write new config yaml
            for p12_item in p12_replace_list:
                self.functions.test_or_replace_line_in_file({
                    "file_path": f"{self.functions.nodectl_path}cn-config.yaml",
                    "search_line": f"    {p12_item[0]}: blank",
                    "replace_line": f"    {p12_item[0]}: {p12_item[1]}\n",
                    "skip_backup": True,
                })

            return


    # class action
    # =====================

    def build_classes(self,p12=False):
        if p12:
            self.log.logger.info("installer -> generating p12 file object")
            action_obj = {
                "process": "install",
                "user_obj": self.user,
                "cli_obj": self.cli,
                "functions": self.functions,
                "existing_p12": self.options.p12_destination_path
            }
            self.p12_session = P12Class(action_obj)
            self.p12_session.solo = True
            if self.options.quick_install: 
                self.p12_session.quick_install = True
            return
        
        cli_obj = {
            "caller": "installer",
            "profile": "empty",
            "command": "install" if not self.options.quiet else "quiet_install",
            "command_list": [],
            "functions": self.functions,
            "ip_address": self.parent.ip_address,
            "skip_services": False
        }
        self.cli = CLI(cli_obj)
        self.cli.functions.set_statics()
        self.cli.version_class_obj = self.parent.version_class_obj
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
        if self.options.quiet: return
        if lookup: var = getattr(self.options,var)
        if chosen == "metagraph_name": chosen = "hypergraph/metagraph"
        start = "Generated" if gen else "Chosen" 
        self.functions.print_cmd_status({
            "text_start": f"{start} {chosen}",
            "status": var,
            "newline": True,
            "status_color": "green",
        })      
    
    
    def uninstall(self):
        self.log.logger.info("installer -> executing uninstall process.")
        self.options = SimpleNamespace(quiet=False)
        self.build_classes()
        node_service = Node({"functions": self.functions})
        node_service.log = self.log
        uninstaller.start_uninstall(self.functions,self.log)
        uninstaller.stop_services(self.functions, node_service,self.log)
        self.parent.auto_restart_handler("disable","cli")
        uninstaller.restore_user_access(self.cli,self.functions,self.log)
        node_admins = uninstaller.remove_data(self.functions,self.log)

        uninstaller.remove_admins(self.functions,node_admins,self.log)
        uninstaller.finish_uninstall(self.functions)

        if node_admins[0] == "logger_retention":
            self.log.logger.info("moving nodectl to /var/tmp and completing uninstall.  Thank you for using nodectl.")
        self.log.logger.info("uninstaller -> handling removal of nodectl executable ")
        if node_admins[0] == "logger_retention":
            copy2("/var/tessellation/nodectl/nodectl.log", "/var/tmp/nodectl.log")
            sleep(.5)
            rmtree("/var/tessellation")

        uninstaller.remove_nodectl(node_service)


    def close_threads(self):
        self.functions.status_dots = False
        self.functions.event = False


    def print_cluster_config_details(self):
        self.functions.print_cmd_status({
            "text_start": "HyperGraph/Metagraph",
            "status": self.options.metagraph_name,
            "status_color": "yellow",
            "newline": True,
        })      
        self.functions.print_cmd_status({
            "text_start": "Environment",
            "status": self.options.environment,
            "status_color": "yellow",
            "newline": True,
        })      
        self.functions.print_cmd_status({
            "text_start": "P12 Location",
            "status": path.dirname(self.options.p12_destination_path),
            "status_color": "yellow",
            "newline": True,
        })  
        self.functions.print_cmd_status({
            "text_start": "P12 Name",
            "status": path.basename(self.options.p12_destination_path),
            "status_color": "yellow",
            "newline": True,
        })  
        self.functions.print_cmd_status({
            "text_start": "P12 Alias",
            "status": self.options.p12_alias,
            "status_color": "red" if self.options.p12_alias == "error" else "yellow",
            "newline": True,
        })  

    
    def complete_install(self):
        self.log.logger.info("Installation complete !!!")

        success = self.cli.cli_grab_id({
            "command":"nodeid",
            "return_success": True,
            "skip_display": True,
            "threading": False,
        })
        dag_address = self.cli.cli_nodeid2dag([self.cli.nodeid.strip("\n"), "return_only"])

        node_details = {
            "HyperGraphMetaGraph": self.options.metagraph_name,
            "Environment": self.options.environment,
            "P12Path": path.dirname(self.options.p12_destination_path),
            "P12": path.basename(self.options.p12_destination_path),
            "Alias": self.options.p12_alias,
            "NodeId": self.cli.nodeid.strip("\n"),
            "DAGAddress": dag_address
        }

        if self.options.json_output:
            with open(f"{self.functions.nodectl_path}node_details.json","w") as node_detail_file:
                json.dump(node_details,node_detail_file,indent=4)

        if self.options.quiet:
            print(node_details)
            return
        
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

        self.print_cluster_config_details()

        def print_error():
            self.functions.print_paragraphs([
                ["",1],[" WARNING ",1,"red,on_yellow"], 
                ["p12 file may have incorrect parameters or is corrupted.",0,"red"],
                ["Unable to derive nodeid.",2,"red","bold"],

                ["Please update your",0,"red"], ["p12",0,"yellow"], ["details:",1,"red"],
                ["step 1)",0,"magenta","bold"], ["verify your p12 passphrase",1],
                ["step 2)",0,"magenta","bold"], ["verify your p12 alias",1],
                [" - sudo nodectl show_p12_details --alias",1,"magenta"], 
                ["step 3)",0,"magenta","bold"], ["update your configuration",1],
                [" - sudo nodectl configure",1,"magenta"], 
                ["step 4",0,"magenta","bold"], ["follow steps to update global p12 parameters",1],
                ["step 5)",0,"magenta","bold"], ["obtain node id for submission",1],
                [" - sudo nodectl id -p <profile_name>",2,"magenta"],
            ])

        if not self.encryption_performed:
            self.functions.print_paragraphs([
                ["",1], [" ENCRYPTION FAILURE ",0,"red,on_yellow"], 
                ["An issue was detected with the p12 private key store. To encrypt the passphrase, ensure that the passphrase",0,"red"],
                ["is correct and tested. After confirming the passphrase, you can attempt to encrypt it again.",2,"red"],

                ["You may use the configurator to update the p12 settings and attempt encryption by following",0,"red"],
                ["the prompts via the following command:",1,"red"],
                ["sudo nodectl configure",1],
            ])
            success = False

        metagraph_list = self.functions.clear_global_profiles(self.metagraph_list)

        if self.encryption_performed:
            print("")
            print(f"\033[1A", end="", flush=True)

        if not success:
            print_error()
        else:
            for profile in metagraph_list: # make sure 
                if self.config_obj[profile]["seed_location"] != "disable":
                    self.cli.check_seed_list(["-p",profile,"-id",self.cli.nodeid])
                    break # only need to check once for an installation

        self.functions.print_paragraphs([
            ["DAG WALLET ADDRESS",1,"blue","bold"], 
            [dag_address,2,"white","bold"],

            [f"Please review the next Steps in order to gain access to the",0],
            [self.options.metagraph_name,0,"yellow"], ["->",0], [self.options.environment,0,"yellow"], 
            ["environment.",2],
        ])     

        next_step = 1
        if success:
            self.functions.print_paragraphs([
                ["If your Node is found as",0], ["False",0,"red","bold"], ["on the",0],
                ["check seed list(s)",0,"blue","bold"], ["output above, you will need to submit your NodeID for acceptance.",2],
            ])     
        self.functions.print_paragraphs([
            ["Please follow the instructions below, as indicated.",2,"blue","bold"],
        ])     
        if not success:
            self.functions.print_paragraphs([
                ["1",0,"magenta","bold"], [")",-1,"magenta"], ["Correct any errors of your p12 key store.",1,"red"],
            ])  
            next_step = 2   

        self.functions.print_paragraphs([
            [f"{next_step}",0,"magenta","bold"], [")",-1,"magenta"], ["Submit your NodeID to Constellation Admins.",1,"cyan"],
            [f"{next_step+1}",0,"magenta","bold"], [")",-1,"magenta"], ["Collateralize your Node.",1,"cyan"],
            [f"{next_step+2}",0,"magenta","bold"], [")",-1,"magenta"], [f"sudo nodectl check_seedlist -p {metagraph_list[0]}",1,"cyan"],
            [f"{next_step+3}",0,"magenta","bold"], [")",-1,"magenta"], ["sudo nodectl restart -p all",1,"cyan"],
            [f"{next_step+4}",0,"magenta","bold"], [")",-1,"magenta"], [f"Log out and log back in with as {self.options.user} with your new {self.options.user} password.",2,"cyan"],
            ["enod!",2,"white","bold"],
        ])     

        self.log.logger.info("nodectl installation completed in []")   
        
        
if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")  
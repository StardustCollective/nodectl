import random
from concurrent.futures import ThreadPoolExecutor

from termcolor import colored, cprint
from os import system, path, environ, makedirs, listdir, chmod, remove
from sys import exit
from getpass import getpass, getuser
from types import SimpleNamespace
from copy import deepcopy, copy
from string import ascii_letters
from secrets import compare_digest, choice
from time import sleep
from requests import get
from re import search, compile
from itertools import chain
from zlib import compress

from .migration import Migration
from .config import Configuration
from ..troubleshoot.logger import Logging
from ..node_service import Node
from ..troubleshoot.errors import Error_codes
from ..troubleshoot.errors import Error_codes
from .versioning import Versioning

try:
    from ..shell_handler import ShellHandler
except ImportError:
    # installation may be calling this Class which will not need
    # the ShellHandler which would also cause a circular reference
    pass

class Configurator():
    
    def __init__(self,argv_list):
        self.log = Logging()
        self.log.logger.info("configurator request initialized")

        self.config_path = "/var/tessellation/nodectl/"
        self.config_file = "cn-config.yaml"
        self.config_file_path = "/var/tessellation/nodectl/cn-config.yaml"
        self.yaml_path = "/var/tmp/cnng-new-temp-config.yaml"
        self.profile_to_edit = None
        self.config_obj = {}
        
        self.keep_pass_visible = True
        self.action = False
        self.error_hint = False
        self.is_all_global = False
        self.clean_profiles = False
        self.preserve_pass = False
        self.upgrade_needed = False
        self.restart_needed = True
        self.is_new_config = False
        self.skip_prepare = False
        self.override = False
        self.is_file_backedup = False
        self.backup_file_found = False
        self.node_service = False
        self.skip_clean_profiles_manual = False
        self.dev_enable_disable = False
        self.requested_profile = None
        self.header_title = None
        self.installer = False
        self.quick_install = False
        self.encryption_failed = True

        self.edit_error_msg = ""
        self.detailed = "init"
        if "-a" in argv_list: self.detailed = False
        elif "-d" in argv_list: self.detailed = True

        self.p12_items = [
            "nodeadmin", "key_location", "key_name", "key_alias", "passphrase"
        ]
        self.profile_name_list = [] 
        self.predefined_configuration = {}

        if "-p" in argv_list:
            self.requested_profile = argv_list[argv_list.index("-p")+1]
        
        self.confirmed_backup = True if "-cb" in argv_list else False
                        
        if "help" in argv_list:
            self.prepare_configuration("edit_config")
            self.c.functions.check_for_help(["help"],"configure")
        elif "-ep" in argv_list:
            self.action = "edit_profile"
        elif "-e" in argv_list:
            self.action = "edit"
        elif "-n" in argv_list:
            self.requested_profile = None
            self.action = "new"

        self.prepare_configuration("new_config")
        self.error_messages = Error_codes(self.c.functions)

        self.handle_single_options(argv_list)

        if "--installer" in argv_list or "--upgrader" in argv_list:
            if "--installer" in argv_list:
                self.log.logger.info("installation module creating new configuration object")
            else:
                self.log.logger.info("upgrader module creating new configuration object")
            # upgrader will use same elements as installer
            self.installer = True
            self.action = "install"
            self.detailed = False
            return

        self.setup()
        

    def handle_single_options(self,argv_list):
        send_error = False
        if "--developer_mode" in argv_list:
            try:
                if argv_list[argv_list.index("--developer_mode")+1] == "enable" or argv_list[argv_list.index("--developer_mode")+1] == "disable":
                    self.dev_enable_disable = argv_list[argv_list.index("--developer_mode")+1]
                    self.action = "dev_mode"
                else:
                    send_error = "developer_mode"
            except:
                send_error = "developer_mode"
        if "--includes" in argv_list:
            try:
                if argv_list[argv_list.index("--includes")+1] == "enable" or argv_list[argv_list.index("--includes")+1] == "disable":
                    self.dev_enable_disable = argv_list[argv_list.index("--includes")+1]
                    self.action = "includes_section"
                else:
                    send_error = "includes"
            except:
                send_error = "includes"

        if send_error:
            self.error_messages.error_code_messages({
                "error_code": "cfr-131",
                "line_code": "invalid_option",
                "extra": send_error,
                "extra2": "valid options are 'enable' or 'disable'"
            })


    def prepare_node_service_obj(self):
        self.node_service = Node({"functions": self.c.functions}) 
        self.node_service.functions.log = self.log
        self.node_service.functions.version_obj = self.c.functions.version_obj
        self.node_service.functions.set_statics()
        self.node_service.functions.pull_profile({"req":"profile_names"})
                
                
    def prepare_configuration(self,action,implement=False):
        if action == "migrator":
            self.migrate = Migration({
            "functions": self.c.functions,
            "caller": "configurator"
            })
            return
        
        try:
            self.old_last_cnconfig = deepcopy(self.c.config_obj)
        except:
            self.old_last_cnconfig = False
    
        try:
            self.c.configurator_verified = True
        except: 
            pass
        
        self.c = Configuration({
            "action": action,
            "implement": implement,
            "skip_report": True,
            "argv_list": [action,"configurator"],
        })

        versioning = Versioning({
            "config_obj": self.config_obj,
            "print_messages": False,
            "called_cmd": "show_version",
        })
        
        self.c.config_obj["global_elements"] = {"caller":"config"}
        self.c.functions.log = self.log
        self.c.functions.version_obj = versioning.version_obj
        self.c.functions.set_statics()
        self.c.functions.pull_profile({"req":"profile_names"})
                
        self.wrapper = self.c.functions.print_paragraphs("wrapper_only")
        
        if action == "edit_config":
            self.config_obj_apply = {}
            if path.isfile(self.config_file_path):
                system(f"sudo cp {self.config_file_path} {self.yaml_path} > /dev/null 2>&1")
            else:
                self.error_messages.error_code_messages({
                    "error_code": "cfr-101",
                    "line_code": "config_error",
                    "extra": "existence"
                })


    def setup(self):
        option = "start"
        while True:
            top_newline = "bottom"
            self.c.functions.print_header_title({
                "line1": "NODECTL",
                "line2": "CONFIGURATION TOOL",
                "clear": True,
            })

            intro2 = "This feature of nodectl will help you initialize a new configuration or update/edit an existing configuration file."  
            intro3 = "will attempt to migrate/integrate your configurations changes in order to ensure a smooth transition and operations of your"
            
            paragraphs = [
                ["Welcome to the",0], ["nodectl",0,"blue","bold,underline"],
                ["configuration tool.",2],
            ]
            self.c.functions.print_paragraphs(paragraphs)
            
            try:
                if self.detailed == "init" and not self.dev_enable_disable:
                    paragraphs = [
                        [intro2,2],
                        ["nodectl",0,"blue","bold"], [intro3,0],
                        ["Node",0,"green","underline"], ["via",0], 
                        ["nodectl",0,"blue","bold"], [".",-1],["",2],
                    
                        ["Detailed Mode ",0,"grey,on_yellow","bold,underline"],["will walk you through all steps/questions; with detailed explanations of each element of the configuration.",2],
                        ["Advanced Mode ",0,"grey,on_yellow","bold,underline"],["will be non-verbose, with no walk through explanations, only necessary questions.",2],
                        
                        ["The configuration tool does only a",0,"red"], ["limited amount",0,"red","bold"],
                        ["of data type or value verification. After the configuration tool creates",0,"red"],
                        ["a new configuration or edits an existing configuration, it will attempt",0,"red"],
                        ["to verify the end resulting configuration.",2,"red"],  

                        ["You can also choose the",0], ["-d",0,"yellow","bold"], ["option at the command line to enter detailed mode directly.",1],
                        ["You can also choose the",0], ["-a",0,"yellow","bold"], ["option at the command line to enter advanced mode directly.",2],
                    ]

                    self.c.functions.print_paragraphs(paragraphs)
                    
                    adv_mode = False
                    adv_mode = self.c.functions.confirm_action({
                        "prompt": "Switch to advanced mode?",
                        "yes_no_default": "n",
                        "return_on": "y",
                        "exit_if": False
                    })
                    self.detailed = False if adv_mode == True else True
                    top_newline = "both"
            except:
                pass

            self.c.functions.print_header_title({
                "line1": "MAIN MENU",
                "show_titles": False,
                "newline": top_newline
            })
            

            if ( self.action == "edit" or self.action == "help" or self.action == "includes_section" or
                 self.action == "edit_profile" or self.action == "dev_mode") and option != "reset":
                option = "e"
            elif self.action == "new" and option != "reset":
                option = "n"
            else:
                option = self.c.functions.print_option_menu({
                    "options": [
                        "New Configuration",
                        "Edit Existing Configuration",
                    ],
                    "let_or_num": "let",
                    "color": "magenta",
                    "r_and_q": "q",
                })
            
            if option.lower() == "q":
                self.c.functions.print_auto_restart_warning()
                self.quit_configurator()
            
            self.backup_config()
            
            if option.lower() == "n":
                self.is_new_config = True
                self.new_config()
            elif option.lower() == "e":
                self.is_new_config = False
                self.edit_config()
                
            option = "reset"
    
        
    def new_config(self):
        self.restart_needed = False
        self.action = "new"
        self.c.functions.print_header_title({
            "line1": "NODECTL",
            "line2": "create new configuration",
            "clear": True,
            "upper": False,
        })  
        
        if self.detailed:
            self.c.functions.print_paragraphs([
                ["nodectl",0,"blue","bold"], ["can build a configuration for you based on",0], ["predefined",0,"blue","bold"],
                ["profiles. These profiles are setup by the Constellation Network or Metagraph Administrators",0],
                ["(or Layer0) companies that plan to ride on the Hypergraph.",2],

                ["Before continuing, please make sure you have the following checklist completed, to save time.",2,"yellow"],
                
                ["You should have obtained this information during the installation of your",0], ["Node",0,"blue","bold"],
                ["originally.",2],
                
                ["  - p12 file name",1,"magenta"],
                ["  - p12 file location",1,"magenta"],
                ["  - p12 passphrase",1,"magenta"],
                
                ["Warning!",0,"red","bold"],["Invalid entries will either be rejected at runtime or flagged as invalid by",0], 
                ["nodectl",0,"blue","bold"], ["before runtime.",0], ["nodectl",0,"blue","bold"], ["does not validate entries during the configuration entry process.",2]
            ] )

        self.build_config_obj()
        self.get_predefined_configs()
        self.handle_global_p12()
        self.request_p12_details({
            "get_existing_global": True if self.override else False,
        })
        self.config_obj_apply = {}      
        
        self.metagraph_list = self.c.functions.clear_global_profiles(self.config_obj)
        
        # grab only the profile associated p12 items
        self.config_obj_apply = {f"{profile}": {key: value for key, value in 
            self.config_obj[profile].items() if "p12" in key} for profile in self.metagraph_list}        

        # grab global_p12 section
        self.config_obj_apply = {
            **self.config_obj_apply,
            **{key: value for key, value in self.config_obj.items() if "p12" in key}
        }

        self.apply_vars_to_config()
        self.upgrade_needed = False

        self.build_service_file({
            "action": "Create",
        }) 
        
        self.cleanup_old_profiles()
        self.cleanup_service_files(False)
        if not self.override: self.cleanup_create_snapshot_dirs() 
        self.prepare_configuration("edit_config",False)
        self.move_config_backups()
        
        self.c.functions.print_paragraphs([
            ["",1],[" CONGRATULATIONS ",1,"yellow,on_green"],
            ["A new profile has been created successfully.",2,"green","bold"],
        ]) 
        self.ask_review_config()

    # =====================================================
    # PRE-DEFINED PROFILE BUILD METHODS
    # =====================================================  
      
    def get_predefined_configs(self):
        self.c.functions.print_header_title({
            "line1": "NODECTL",
            "line2": "profile based configuration",
            "clear": True,
            "upper": False,
        })  

        def print_scenarios():
            self.c.functions.print_header_title({
                "line1": "BUILD NEW CONFIGURATION",
                "single_line": True,
                "newline": "bottom"
            })
            self.c.functions.print_paragraphs([
                ["Scenario One:",1,"cyan","bold"], ["This entails setting up a brand new Node. In this case, it is highly recommended that you",0,"green"],
                ["exit here",0,"red"], ["and utilize the installer to build your new Node. Refer to the documentation for full details and options on how to use the installer.",1,"green"],
                ["recommended:",0,"yellow"], ["sudo nodectl install –quick-install",2],

                ["Scenario Two:",1,"cyan","bold"], ["This involves an existing Node where you need to apply a new configuration to handle new features or add",0,"green"],
                ["secondary profiles that",0,"green"], ["do not",0,"yellow"], 
                ["share the same profile name and",0,"green"], ["will not",0,"yellow"], ["interfere with the existing configuration (clusters and profiles)",0,"green"],
                ["already on this Node.",2,"green"],

                ["Scenario Three:",1,"cyan","bold"], ["You are here for in reference to",0,"green"],["scenario two",0,], ["but",0,"red","bold"],
                ["the new configuration",0,"green"], ["is going to conflict",0,"red"], ["with an existing profile of a different cluster on this Node.",2,"green"],

                ["Scenario Four:",1,"cyan","bold"], ["You have encountered a configuration error that is preventing you from continuing to use nodectl",0,"red"],
                ["and would like to attempt to overwrite your configuration, preserve as much information as possible, and avoid losing any data.",2,"red"],

                ["-","half"],["",1],
            ])

        if self.detailed:   
            self.c.functions.print_paragraphs([
                ["Welcome to the new configuration nodectl configurator feature. While in detailed mode, nodectl will",0,"green"],
                ["strive to assist you in creating your new configuration as straightforwardly as possible.  However, if you are unsure",0,"green"],
                ["of any concepts presented, utilizing the documentation website is recommended.",1,"green"],
                ["https://docs.constellationnetwork.io/validate",2,"blue","bold"],

                ["The first step is to determine the true purpose of your intentions that brought you to the new configuration configurator section.",2,"green"],

                ["Definitions",1,"cyan","bold"],
                ["Cluster:",0,"yellow"],["A network of connected Nodes.",1],
                ["Hypergraph:",0,"yellow"],["Constellation's main cluster.",1],
                ["Metagraph:",0,"yellow"],["Business or non-constellation owned cluster, that links to the Hypergraph layer0 cluster.",2],
            ])

            print_scenarios()  

            self.c.functions.confirm_action({
                "prompt": "Continue? ",
                "yes_no_default": "y",
                "return_on": "y",
                "exit_if": True,            
            })

            system("clear")
            print_scenarios()
            self.c.functions.print_paragraphs([
                ["Most likely you are continuing because you decided that scenario",0,"green"],
                ["two, three, or four",0,"yellow"], ["fit your requirements.",2,"green"],
                ["Are you here because of scenario",0,"green"], ["FOUR",0,"yellow"], 
                ["(overriding an existing or corrupt configuration)?",2,"green"],
            ])
            self.override = self.c.functions.confirm_action({
                "prompt": "Yes? ",
                "yes_no_default": "y",
                "return_on": "y",
                "exit_if": False,            
            })
            if self.override:
                self.c.functions.print_paragraphs([
                    ["",1],[" WARNING ",0,"red,on_yellow"], ["nodectl will attempt to pull information from your current",0],
                    ["configuration in order to persist data. However, you may encounter various nodectl errors during this process",0],
                    ["if the configuration is not recoverable.",2],
                    
                    ["The purpose of this attempt to override the existing configuration is to persist data.",0],
                    ["If errors occur, nodectl will automatically exit.",2], 

                    ["You can restart the configurator,",0], ["decline",0,"red"], ["the override configuration option, proceed with the next steps,",0],
                    ["and then after the process is completed, use the configurator to update your various",0],
                    ["non-default information, such as private key [p12] details.",2],

                    ["See the documentation for further details:",1],
                    ["https://docs.constellationnetwork.io/validate",2,"blue","bold"],
                ])
                self.c.functions.print_any_key({"prompt":"Press any key to continue"})
            else:
                system("clear")
                print_scenarios()
                self.c.functions.print_paragraphs([
                    ["If you are here because of scenario",0,"green"], ["THREE",0,"red"], ["there may be a situation where you are migrating your node to",0,"green"],
                    ["another (new) cluster that happens to share the same profile name as the existing profile name already on this Node. If",0,"green"],
                    ["and only if you are joining a new cluster that shares the same profile name, it is important to stop your Node’s original",0,"green"],
                    ["profile by issuing a leave and stop command to remove your Node from the old cluster. Failure to do so can lead",0,"green"],
                    ["to undesired and unknown results or errors.",1,"green"],
                    ["Command:",0,"yellow"], ["sudo nodectl stop -p <profile_name>",2,"cyan"],
                ])

                self.c.functions.confirm_action({
                    "prompt": "Exit new configuration build to stop profiles? ",
                    "yes_no_default": "y",
                    "return_on": "n",
                    "exit_if": True,            
                })

        self.c.functions.print_header_title({
            "line1": "CHOOSING NEW PROFILE DEFINITION",
            "single_line": True,
            "newline": "both"
        })

        if self.detailed:        
            self.c.functions.print_paragraphs([
                ["Please choose the",0], ["profile",0,"blue","bold"], ["below that matches the configuration you are seeking to build.",2],
                ["If not found, please consult the Constellation Network Doc Hub for details or contact Constellation Network Administration on Discord.",2],
                ["You can also put in a request to have your Metagraph's configuration added, by contacting a Constellation Network representative.",2],
            ]) 
        if self.override: 
            self.prepare_configuration(action="edit_config_from_new")
            self.old_last_cnconfig = deepcopy(self.c.config_obj)
    
        if path.isfile(self.yaml_path):
            # clean up old file
            system(f"sudo rm -f {self.yaml_path}")
            
        self.c.functions.print_cmd_status({
            "text_start": "building configuration skeleton",
            "newline": True,
        })

        self.c.functions.print_header_title({
            "line1": "PREDEFINED OPTIONS",
            "show_titles": False,
            "newline": "both"
        })
        
        environment_details = self.c.functions.pull_remote_profiles({
            "r_and_q":"q", 
            "add_postfix": True, 
            "retrieve": "chosen_profile",
        })
        
        if environment_details == "r": 
            self.action = "init"
            self.setup()
        if environment_details == "q": self.quit_configurator()
        
        environment = environment_details.pop(0)
        print("")
        self.c.functions.print_cmd_status({
            "text_start": "Predefined configuration chosen",
            "status": environment,
            "newline": True,
        })
        system(f'sudo wget {environment_details[0]["yaml_url"]} -O {self.yaml_path} -o /dev/null')
        self.metagraph_list = self.c.functions.clear_global_profiles(environment_details[0]["json"]["nodectl"])
        self.config_obj = environment_details[0]["json"]["nodectl"]

        self.c.functions.print_cmd_status({
            "text_start": "building configuration skeleton",
            "newline": True,
            "status": "complete",
            "status_color": "green"
        })
        
    
    def build_config_obj(self):
        self.config_obj = {
            "global_elements": {
                "caller": "config",
            }
        }
        self.prepare_configuration("migrator")
        if self.action == "new":
            self.migrate.keep_pass_visible = True

        
    # =====================================================
    # P12 BUILD METHODS
    # =====================================================
    
    def request_p12_details(self,command_obj):
        ptype = command_obj.get("ptype","global")
        set_default = command_obj.get("set_default",False)
        get_existing_global = command_obj.get("get_existing_global",True)
        profile = command_obj.get("profile","None")
        preserved = command_obj.get("preserved","preserved")
        
        line_skip = 1
        new_config_warning = ""
        skip_to_end = False
        
        if self.is_new_config:
            new_config_warning = "Existing configuration will be overwritten!"
            line_skip = 2
        
        if ptype == "global_edit_prepare":
            ptype = "global"
        else:
            blank_found = False
            if get_existing_global:
                for p12_key in self.c.config_obj["global_p12"].keys():
                    try:
                        if self.c.config_obj["global_p12"][p12_key] == "blank":
                            blank_found = True
                            break
                    except: 
                        pass

            if get_existing_global and not blank_found and self.backup_file_found and not self.preserve_pass:
                self.c.functions.print_paragraphs([
                    ["An existing configuration file was found on the system.",0,"white","bold"],
                    ["nodectl will attempt to validate the existing configuration, you can safely ignore any errors.",2,"white","bold"],
                    
                    ["Do you want to preserve the existing",0,"white","bold"],
                    ["Global",0,"yellow,on_blue"], ["p12 details?",1,"white","bold"],

                    [new_config_warning,line_skip,"red"]
                ])
                self.preserve_pass = self.c.functions.confirm_action({
                    "prompt": "Preserve Global p12 details? ",
                    "yes_no_default": "n",
                    "return_on": "y",
                    "exit_if": False                
                })
            
            if self.preserve_pass and get_existing_global:
                if not self.skip_prepare:
                    prepare_action = "new_config_init"
                    if self.override: prepare_action = "edit_config_from_new"
                    self.prepare_configuration(prepare_action)
                self.config_obj["global_p12"] = self.c.config_obj["global_p12"]
                if self.c.error_found:
                    self.log.logger.critical("Attempting to pull existing p12 information for the configuration file failed.  Valid inputs did not exist.")
                    self.log.logger.error(f"configurator was unable to retrieve p12 detail information during a configuration [{self.action}]")
                    self.print_error()
                self.prepare_configuration("new_config")
                self.c.functions.print_cmd_status({
                    "text_start": f"Existing global p12 details {preserved}",
                    "newline": True,
                    "status": "success",
                    "status_color": "green",
                })
                
                if self.is_all_global: return
                skip_to_end = True
        
        if not skip_to_end:
            if set_default:
                nodeadmin_default = self.config_obj["global_p12"]["nodeadmin"]
                location_default = self.config_obj["global_p12"]["key_location"]
                p12_default = self.config_obj["global_p12"]["key_name"]

            else:
                try:
                    self.sudo_user = environ["SUDO_USER"] 
                except:  
                    self.sudo_user = getuser()
                    
                if self.sudo_user == "root" or self.sudo_user == "ubuntu" or self.sudo_user == "admin":
                    self.sudo_user = "nodeadmin"
                    
                nodeadmin_default = self.sudo_user
                location_default = f"/home/{self.sudo_user}/tessellation/"
                p12_default = ""
            
            p12_required = False if set_default else True
            
            questions = {
                "nodeadmin": {
                    "question": f"  {colored('Enter in the admin username for this Node','cyan')}",
                    "description": "This is the Debian Operating system username used to administer your Node. It was created during Node installation. Avoid the 'root', 'admin', or 'ubuntu' user.",
                    "default": nodeadmin_default,
                    "required": False,
                },
                "key_location": {
                    "question": f"  {colored('Enter in p12 file path','cyan')}",
                    "description": "This is the location on your Debian Operating system where the p12 private key file is located.",
                    "default": location_default,
                    "required": False,
                },
                "key_name": {
                    "question": f"  {colored('Enter in your p12 file name: ','cyan')}",
                    "description": "This is the name of your p12 private key file.  It should have a '.p12' extension.",
                    "default": p12_default,
                    "required": p12_required,
                },
            }
            
            if self.keep_pass_visible:
                description = "Enter in a passphrase. The passphrase [also called 'keyphrase' or simply 'password'] will not be seen as it is entered. This configurator does NOT create new p12 private key files. "
                description += "The Node Operator should enter in their EXISTING p12 passphrase.  This configurator also does NOT change or alter the p12 file in ANY way. "
                description += "A p12 file should have been created during the original installation of nodectl on this Node. "
                description += "If the Node Operator wants to modify the p12 passphrase, the 'sudo nodectl passwd12' command can be used. "
                description += "To remove the passphrase from the configuration, enter in \"None\" as the passphrase, and confirm with \"None\". "
                description += "MAKE SURE TO SAVE YOUR PASSPHRASE IN A SAFE LOCATION! Losing your passphrase is not recoverable!"
                
                pass_questions = {
                    "passphrase": {
                        "question": f"  {colored('Enter in p12 passphrase: ','cyan')}",
                        "description": description,
                        "required": True,
                        "v_type": "pass",
                    },
                    "pass2": {
                        "question": f"  {colored('Confirm this passphrase: ','cyan')}",
                        "required": True,
                        "v_type": "pass",
                    },
                }
    
            print("")
            
            self.c.functions.print_header_title({
                "line1": f"{ptype} PROFILE P12 ENTRY",
                "single_line": True,
                "newline": False if self.detailed else "bottom"
            })
            p12_answers = self.ask_confirm_questions({"questions": questions})
            p12_pass = {"passphrase": "None", "pass2": "None"}

            if self.keep_pass_visible:
                single_visible_str = f'{colored("Would you like to","cyan")} {colored("hide","yellow",attrs=["bold"])} {colored("the passphrase for this profile","cyan")}'
                if ptype == "global":
                    single_visible_str = f'{colored("Would you like to","cyan")} {colored("hide","yellow",attrs=["bold"])} {colored("the global passphrase","cyan")}'
                if not self.c.functions.confirm_action({
                    "prompt": single_visible_str,
                    "yes_no_default": "n",
                    "return_on": "y",
                    "exit_if": False                
                }):
                    while True:
                        confirm = True
                        p12_pass = self.ask_confirm_questions({
                            "questions": pass_questions,
                            "confirm": False
                        })
                        if not compare_digest(p12_pass["passphrase"],p12_pass["pass2"]):
                            confirm = False
                            cprint("  passphrase did not match","red",attrs=["bold"])
                        if '"' in p12_pass["pass2"]:
                            confirm = False
                            cprint("  passphrase cannot include quotes","red",attrs=["bold"])
                        if confirm:
                            break
                        
            del p12_pass["pass2"]
            if p12_answers["key_location"] != "global" and p12_answers["key_location"][-1] != "/":
                p12_answers["key_location"] = p12_answers["key_location"]+"/"
            p12_answers["key_store"] = self.c.create_path_variable(p12_answers["key_location"],p12_answers["key_name"])

            p12_values = {
                **p12_answers,
                **p12_pass,
            }
                        
            if ptype == "global":
                self.config_obj["global_p12"] = p12_values
            
        noun = "Global" if ptype == "global" else profile.capitalize()
        self.c.functions.print_cmd_status({
            "text_start": f"{noun} p12 entries",
            "newline": True,
            "status": "complete",
            "status_color": "green",
        })
        
        if not self.is_all_global and profile == "None":
            self.is_all_global = False
            p12_value = {} # reset
            for profile in self.metagraph_list:
                self.c.functions.print_header_title({
                    "line1": f"{profile} PROFILE P12 ENTRY",
                    "single_line": True,
                    "newline": "both",
                })
                if not self.c.functions.confirm_action({
                    "prompt": f"Would you like to keep the profile {profile} with the global settings?",
                    "yes_no_default": "n",
                    "return_on": "y",
                    "exit_if": False                
                }):                
                    self.request_p12_details({ 
                        "ptype": "single",
                        "profile": profile,
                        "get_existing_global": False
                    })
                
            ptype = "Done"
            
        if ptype == "single":
            del p12_values["key_store"]
            for p12key, p12value in p12_values.items():
                self.config_obj[profile][f"p12_{p12key}"] = p12value
            
        if ptype != "Done": return p12_values
        return


    def handle_global_p12(self):
        self.c.functions.print_header_title({
            "line1": "SECURITY DETAILS",
            "single_line": True,
            "newline": "both",
        }) 
        cprint("  Security and Authentication","cyan")
        
        if self.detailed:
            print("")  # user visual experience
        
        if self.detailed:
            paragraphs = [

                ["A",0], ["Node",0,"blue","bold"], ["cannot access the Constellation Network Hypergraph",0],
                ["without a",0,"cyan"], ["p12 private key file",0,"yellow","bold"], ["that is used to authenticate against network access regardless of PRO score or seedlist.",2],
                ["This same p12 key file is used as your Node’s wallet and derives the DAG address from the p12 file's",0],
                ["public key file, which Constellation Network uses as your node ID.",2],
                
                ["The p12 key file should have been created during installation:",1,'yellow'],  
                ["sudo nodectl install",2], 
                
                ["If you need to create a p12 private key file:",1,"yellow"],
                ["sudo nodectl generate_p12",2],

                ["nodectl",0,"blue","bold"], ["has three configuration options for access into various network clusters via a user defined configuration profile.",2],

            ]
            self.c.functions.print_paragraphs(paragraphs)

            wrapper = self.c.functions.print_paragraphs("wrapper_only")
            wrapper.subsequent_indent = f"{' ': <18}"
            
            print(wrapper.fill(f"{colored('1','magenta',attrs=['bold'])}{colored(': Global     - Setup a global wallet that will work with all profiles.','magenta')}"))
            print(wrapper.fill(f"{colored('2','magenta',attrs=['bold'])}{colored(': Dedicated  – Setup a unique p12 file per profile.','magenta')}"))
            
            text3 = ": Both       - Setup a global wallet that will work with any profiles that are configured to use the global settings; also, allow the Node to have clusters that uses dedicated (individual) wallets, per cluster."
            print(wrapper.fill(f"{colored('3','magenta',attrs=['bold'])}{colored(text3,'magenta')}"))

        self.is_all_global = self.c.functions.confirm_action({
            "prompt": f"\n  Set {colored('ALL','yellow','on_blue',attrs=['bold'])} {colored('profile p12 wallets to Global?','cyan')}",
            "yes_no_default": "y",
            "return_on": "y",
            "exit_if": False
        })
        
        print("")

        self.c.functions.print_header_title({
            "line1": "GLOBAL P12 DETAILS",
            "single_line": True,
            "newline": "top" if self.detailed else "both",
            "show_titles": False,
        })
        
        if self.detailed:
            global_text1 = "The global p12 file settings are required regardless of whether or not they are used."
            global_text2 = "The global settings are used to authenticate nodectl for each instance of the utility that is running."
            global_text3a = "You do not need to specify the passphrase. If you do not specify the passphrase, you will be asked "
            global_text3b = "for the global and individual passphrases on each execution of this utility; for commands that require authentication."
    
            paragraphs = [
                ["IMPORTANT:",0,"red","bold"], [global_text1,2,"white","bold"],
                
                [global_text2,2,"white","bold"],
                
                [global_text3a+global_text3b,2,"white","bold"],
                
                ["REMINDER:",0,"yellow","bold"], ["default values are inside the",0], ["[]",0,"yellow","bold"],
                ["brackets. To accept, just hit the",0], ["<enter>",0,"magenta","bold"], ["key.",2]
            ]
            print("")
            self.c.functions.print_paragraphs(paragraphs)
        
        
    def process_p12_details(self,ptype,answers):
        progress = {
            "text_start": f"populating {ptype} p12 entries",
            "status": "running",
            "delay": .5,
            "newline": False,
        }
        self.c.functions.print_cmd_status(progress)
        
        if answers is not None:
            if "pass2" in answers:
                answers.pop("pass2")
        
            if ptype == "global":
                self.config_obj["global_p12"] = {}
                for k, v in answers.items():
                    self.config_obj["global_p12"][k] = v
            else:
                for k, v in answers.items():
                    self.config_obj[ptype][k] = v
    
        self.c.functions.print_cmd_status({
            **progress,
            "delay": 0,
            "status": "complete",
            "newline": True,
        })
        
        if not self.migrate.keep_pass_visible:
            self.config_obj["global_p12"]["passphrase"] = "None"
            if ptype != "global":
                self.config_obj[ptype]["passphrase"] = "None"
            
        # only ask to preserve passphrase on global
        self.preserve_pass = True  
    
    
    def apply_vars_to_config(self):
        ignore_list = []
        search_dup_only = False
        
        for profile, values in self.config_obj_apply.items():
            if "do_not_change" in self.config_obj_apply[profile]:
                search_dup_only = True
            for p_key, p_value in values.items():
                    replace_line = f"    {p_key}: {p_value}\n"
                    if search_dup_only: replace_line = False
                    _ , ignore_line = self.c.functions.test_or_replace_line_in_file({
                        "file_path": self.yaml_path,
                        "search_line": f"    {p_key}:",
                        "replace_line": replace_line,
                        "skip_backup": True,
                        "all_first_last": "first",
                        "skip_line_list": ignore_list,
                        "allow_dups": False 
                    })
                    ignore_list.append(ignore_line)
            search_dup_only = False
            if "global" in profile:  # key
                for item, value in values.items():
                    self.c.functions.test_or_replace_line_in_file({
                        "file_path": self.yaml_path,
                        "search_line": f"    {item}:",
                        "replace_line": f"    {item}: {value}\n",
                        "skip_backup": True,
                    })
                    
        system(f"sudo cp {self.yaml_path} {self.config_file_path} > /dev/null 2>&1")
        system(f"sudo rm -f {self.yaml_path} > /dev/null 2>&1")

        if not self.quick_install:
            print("")
            self.c.functions.print_cmd_status({
                "text_start": "Configuration changes applied",
                "status": "successfully",
                "status_color": "green",
                "newline": True,
                "delay": 1.5,
            })

        if self.action not in ["new","install"]: self.prepare_configuration("edit_config",True)


    def build_service_file(self,command_obj):
        # profiles=(list of str) # profiles that service file is created against
        # action=(str) # Updating, Creating for user review
        profile_list = command_obj.get("profiles",self.metagraph_list)
        action = command_obj.get("action","create")
        
        self.c.functions.print_header_title({
            "line1": "BUILD SERVICES",
            "single_line": True,
            "newline": "both"
        })
        
        progress = {
            "text_start": f"{action} Service file",
            "status": "running",
            "newline": True,
        }
        for profile in profile_list:
            self.c.functions.print_cmd_status({
                **progress,
                "brackets": profile,
            })
        
        if not self.node_service: self.prepare_node_service_obj()
        self.node_service.config_obj = deepcopy(self.config_obj if len(self.config_obj)>0 else self.c.config_obj)
        self.node_service.profile_names = profile_list
        self.node_service.create_service_bash_file({
            "create_file_type": "service_file",
        })
        
        # build bash file is completed at start,restart,upgrade because there are 
        # multiple edits that cause the need to recreate the bash file
        # and the file will be only temporarily created.
        
        for profile in profile_list:
            self.c.functions.print_cmd_status({
                **progress,
                "status": "complete",
                "newline": True,
            })
        
                        
    # =====================================================
    # MANUAL BUILD METHODS
    # =====================================================
    
    def manual_section_header(self, profile, header):
        self.c.functions.print_header_title(self.header_title)
        self.c.functions.print_header_title({
            "line1": f"{profile} PROFILE {header}",
            "show_titles": False,
            "single_line": True,
            "newline": False if self.detailed else "bottom"
        })


    def manual_build_node_type(self,profile=False):
        profile = self.profile_to_edit if not profile else profile

        self.manual_section_header(profile,"NODE TYPE")
        
        if self.detailed:
            self.c.functions.print_paragraphs([
                ["",1], ["There are only two options: 'validator' and 'genesis'. Unless you are an advanced",0,"white","bold"],
                ["administrator, the 'validator' option should be chosen.",2,"white","bold"],
            ])
            
        self.c.functions.print_paragraphs([
            ["Constellation Node Types",1,"yellow,on_blue"],
            ["=","half","blue","bold"],
        ])

        option = self.c.functions.print_option_menu({
            "options": [
                "Validator",
                "Genesis",
            ],
            "let_or_num": "let",
            "r_and_q": "q",
            "color": "magenta",
        })
        
        if option.lower() == "q":
            self.quit_configurator()
        if option.lower() == "v":
            defaults = {"node_type": "validator"}
        if option.lower() == "g":
            defaults = {"node_type": "genesis"}

        self.manual_append_build_apply({
            "questions": False, 
            "profile": profile,
            "defaults": defaults,
        })
        
        
    def manual_define_meta(self,profile=False):
        profile = self.profile_to_edit if not profile else profile

        self.manual_section_header(profile,"CLUSTER TYPE")
        
        if self.detailed:
            self.c.functions.print_paragraphs([
                ["",1], ["There are only two options: 'gl' and 'ml'.",2,"white","bold"],
                ["nodectl identifies 'gl' as",0,"white","bold"], ["global layer.",1,"yellow","bold"],
                ["nodectl identifies 'ml' as",0,"white","bold"], ["metagraph layer.",2,"yellow","bold"],
                
                ["This value helps nodectl determine the order of how each cluster needs to be started.  It is an",0,"white","bold"],
                ["important aspect of allowing a Node to connect to the network successfully.",0,"white","bold"],
                ["Layer 1 clusters should always be identified as 'ml'",2,"white","bold"],
            ])
            
        self.c.functions.print_paragraphs([
            ["Cluster Types",1,"yellow,on_blue"],
            ["=","half","blue","bold"],
        ])

        option = self.c.functions.print_option_menu({
            "options": [
                "gl",
                "ml",
            ],
            "let_or_num": "num",
            "r_and_q": "q",
            "color": "magenta",
        })
        
        if option.lower() == "q":
            self.quit_configurator()
        if option.lower() == "1":
            defaults = {"meta_type": "gl"}
        if option.lower() == "2":
            defaults = {"meta_type": "ml"}

        self.manual_append_build_apply({
            "questions": False, 
            "profile": profile,
            "defaults": defaults,
        })


    def manual_log_level(self):
        profile = "global_elements"

        self.header_title = {
            "line1": "EDIT GLOBAL SECTION",
            "line2": "Log Details",
            "show_titles": False,
            "clear": True,
            "newline": "both",
        }

        self.manual_section_header(profile,"SET LOGGING LEVEL")
        
        if self.detailed:
            self.c.functions.print_paragraphs([
                ["",1], ["You can set the log level to the most verbose DEBUG all the way to off NOSET.",0,"white","bold"],
                ["It is recommended to use INFO as your log level to avoid unnecessary logging when reviewing.",2,"white","bold"],
            ])

        option = self.c.functions.print_option_menu({
            "options": ["NOTSET","DEBUG","INFO","WARN","ERROR","CRITICAL"],
            "let_or_num": "let",
            "return_value": True,
            "color": "magenta",
        })
        
        if option.lower() == "q":
            self.quit_configurator()
            
        self.config_obj_apply = {"global_elements": {"log_level": option}}
        self.apply_vars_to_config()


    def manual_build_description(self,profile=False):
        default = "None" if not profile else self.c.config_obj[profile]["description"]
        profile = self.profile_to_edit if not profile else profile

        self.manual_section_header(profile,"DESCRIPTION") 
        
        questions = {
            "description": {
                "question": f"  {colored('Enter a description for this profile: ','cyan')}",
                "description": f"This is a description for the Node Operator to help identify the usage of this profile {profile}. It is local description only and does not affect the configuration.",
                "default": default,
                "required": False,
            },
        }
        
        self.manual_append_build_apply({
            "questions": questions, 
            "profile": profile,
        })
        
        self.config_obj = deepcopy(self.c.config_obj) 
        self.build_service_file({
            "profiles": [profile],
            "action": "Updating",
            "rebuild": False,
        })


    def manual_args(self,profile=False):
        profile = self.profile_to_edit if not profile else profile
        custom_args_envs = {}
        add_or_remove = False
        c_types = ["custom_args","custom_env_vars"]
        arg_types = ["custom option arguments","custom environment variables"]
        
        self.manual_section_header(profile,"CUSTOM ARGUMENTS") 
        self.c.functions.print_paragraphs([
            ["",1],["Please choose the type of custom argument(s) you would like to append, update, or remove:",2]
        ])
        option = self.c.functions.print_option_menu({
            "options": arg_types,
            "let_or_num": "num",
            "color": "magenta",
        })
        option = int(option)-1
        c_type = "args" if option == 0 else "env_vars"
        self.manual_section_header(profile, arg_types[option])
        print("")
        if self.c.config_obj[profile][f"custom_{c_type}_enable"]:
            enable_disable_str = "disable" 
            return_on = "n"
        else: 
            enable_disable_str = "enable"
            return_on = "y"
        enable_disable = self.c.functions.confirm_action({
            "yes_no_default": "n",
            "return_on": return_on,
            "prompt": f"Do you want to {enable_disable_str} {arg_types[option]}",
            "exit_if": False
        })
        defaults = {f"custom_{c_type}_enable": f"{enable_disable}"}
        start_line = f"    custom_{c_type}_enable: {enable_disable}\n"
        
        if enable_disable:
            description = "Custom arguments are key pairs (name of an option and its value) that will be added as an "
            description += "option to the command line that starts the Node's process during the start phase of the process "
            if c_type == "env_vars":
                description = "Custom environment variables are key pairs (name of a distribution shell environment variable and its value) "
                description += "that will be added to the shell environment prior to the start of the Node's process "
            description += "that runs on your Node to allow it to prepare to join a cluster.  This value should be added only "
            description += "as instructed or required by the Administrators of a cluster." 
            self.c.functions.print_paragraphs([
                ["",1], [description,2,"white","bold"],
                ["If you enter a key value that already exists, it will be overwritten in the configuration",0,"yellow"],
                ["by the new value entered here.",2,"yellow"],
                ["Do not include the 'custom_args_' or 'custom_env_vars' in your key name.",2,"red"],
            ])
            
            add_or_remove = self.c.functions.print_option_menu({
                "options": [f"add or update {arg_types[option]}",f"remove existing {arg_types[option]}"],
                "let_or_num": "let",
                "return_value": True,
                "color": "magenta",
            })
            add_or_remove = add_or_remove.split(" ")[0]
            cprint(f"  Enter entries to {add_or_remove}","green")
            
            while True:
                does_not_exist = False
                key_name = input(colored(f"  Enter {arg_types[option]} key name: ","cyan"))
                if add_or_remove == "add":
                    key_value = input(colored(f"  Enter {arg_types[option]} value: ","cyan"))
                else: 
                    try: key_value = self.c.config_obj[profile][f"custom_{c_type}_{key_name}"]
                    except: does_not_exist = True
                
                if c_type in key_name: key_name.replace(f"custom_{c_type}_","")
                if does_not_exist:
                    self.c.functions.print_cmd_status({
                        "text_start": f"custom {c_type}",
                        "brackets": key_name,
                        "text_end": "not found",
                        "status": "skipping",
                        "status_color": "yellow",
                        "newline": True,
                    })
                elif key_name != "" and key_value != "":
                    custom_args_envs[f"custom_{c_type}_{key_name}"] = key_value           
                if not self.c.functions.confirm_action({
                    "yes_no_default": "n",
                    "return_on": "y",
                    "prompt": f"Do you want to enter another {arg_types[option]}?",
                    "exit_if": False
                }): 
                    break
        
        if len(custom_args_envs) > 0:
            self.c.functions.print_paragraphs([
                ["",1], ["Verify Values",1,"blue","bold"],
                ["=============",1,"blue","bold"],
            ])
            for key, value in custom_args_envs.items():
                cprint(f'  {key.replace(f"custom_{c_type}_","")} = {value}',"yellow")
            
            print("")    
            if self.c.functions.confirm_action({
                "yes_no_default": "y",
                "return_on": "n",
                "prompt": f"Verify custom entries to {'add/update' if add_or_remove == 'add' else 'remove'}",
                "exit_if": False
            }):
                cprint("  Canceling custom variable process","red")
                sleep(1.5)
                return             
        
        for key,value in custom_args_envs.items():
            if f"custom_{c_type}" not in key: custom_args_envs[f"{c_type}_{key}"] = value 
            else: custom_args_envs[f"{key}"] = value 

        if add_or_remove == "add":
            for key in self.c.config_obj[profile].keys():
                if key in custom_args_envs.keys():
                    defaults = {
                        **defaults,
                        f"{key}": f"{custom_args_envs[key]}",
                    }
                    del custom_args_envs[key]
            
        self.manual_append_build_apply({
            "questions": False, 
            "profile": profile,
            "defaults": defaults,
        })
        
        list_of_lines = [f"    {key}: {value}\n" for key, value in custom_args_envs.items()]
        if len(list_of_lines) > 0:
            self.append_remove_config_lines({
                "profile": profile,
                "append": True if add_or_remove == "add" else False,
                "start_line": start_line,
                "end_line": self.metagraph_list[self.metagraph_list.index(profile)+1],
                "exclude_string": "link_profile",
                "list_of_lines": list_of_lines
            })
        
        
    def manual_build_edge_point(self,profile=False):
        if profile:
            host_default = self.c.config_obj[profile]["edge_point"]
            port_default = self.c.config_obj[profile]["edge_point_tcp_port"]
            required = False
        else:
            host_default = None; port_default = "80"; profile = self.profile_to_edit
            required = True
            
        self.manual_section_header(profile,"EDGE POINTS") 
        
        default_desc = "You can use the word \"default\" to allow nodectl to use known default values."
        description1 = "Generally a layer0 or layer1 network should have a device on the network (most likely a load balancer type "
        description1 += "device/system/server) where API (application programming interface) calls can be directed.  These calls will hit the "
        description1 += "edge device and direct those API requests into the network.  This value can be a FQDN (full qualified domain name) hostname " 
        description1 += "or IP address.  Do not enter a URL/URI (should not include http:// or https://).  Please contact your Administrator for "
        description1 += "this information. "
        description1 += default_desc
        
        description2 = f"When listening on the network, a network connected server (edge point server entered for this profile {profile}) "
        description2 += "will listen for incoming connections on a specific TCP (Transport Control Protocol) port.  You should consult with the "
        description2 += "Administrators to obtain this port value. "
        description2 += default_desc
        
        questions = {
            "edge_point": {
                "question": f"  {colored('Enter the edge point hostname or ip address: ','cyan')}",
                "description": description1,
                "default": host_default,
                "required": required,
            },
            "edge_point_tcp_port": {
                "question": f"  {colored('Enter the TCP port the network Edge device is listening on','cyan')}",
                "description": description2,
                "default": port_default,
                "required": False,
            },
        }
        
        self.manual_append_build_apply({
            "questions": questions, 
            "profile": profile,
        })


    def manual_append_build_apply(self,command_obj):
        profile = command_obj.get("profile",False)
        questions = command_obj.get("questions",False)
        defaults = command_obj.get("defaults",False)
        confirm = command_obj.get("confirm",True)
        apply = command_obj.get("apply",True)
        is_global = command_obj.get("is_global",False)
        custom = False
        
        no_change_list = []
        if questions: 
            no_change_list.append(command_obj.get("no_change_list_questions",list(questions.keys())))
        if defaults: 
            no_change_list.append(command_obj.get("no_change_list_defaults",list(defaults.keys())))
        if len(no_change_list) > 0:
            no_change_list = list(chain(*no_change_list))
        append_obj = {}
        
        # identify profiles that do not change
        if not is_global:
            for i_profile in self.metagraph_list:
                if i_profile == profile: continue

                for item in no_change_list:
                    if i_profile not in append_obj: append_obj[i_profile] = {}
                    try: append_obj[i_profile][item] = self.c.config_obj[i_profile][item]
                    except Exception as e:
                        if "custom_" in item: 
                            custom = True
                            self.log.logger.debug(f"Did not find custom variable in config, skipping [{item}] | [{e}]")
                        else:
                            self.error_messages.error_code_messages({
                                "error_code": "cfr-1046",
                                "line_code": "config_error",
                                "extra": "format"
                            })
                    append_obj[i_profile]["do_not_change"] = True

            # append and add to the append_obj
            for i_profile in self.metagraph_list:
                if i_profile != profile: 
                    i_append_obj = {}
                    for item in no_change_list:
                        try: i_append_obj[f"{item}"] = self.c.config_obj[i_profile][item]
                        except: 
                            if custom: continue
                    append_obj[f"{i_profile}"] = {**i_append_obj, "do_not_change": True}
                
        # append the changing items to the append obj
        if not defaults: defaults = {}
        if questions:
            append_obj = {
                f"{profile}": {
                    **defaults,
                    **self.ask_confirm_questions({
                        "questions": questions,
                        "confirm": confirm,
                    }),
                },
                **append_obj,
            } 
        elif defaults: append_obj = {
            f"{profile}": {
                **defaults,
            },
            **append_obj,
        }  
                 
        self.config_obj_apply = {**self.config_obj_apply, **append_obj} 
        
        # reorder search so that replacement happens
        # at the correct lines in the correct order if not global section
        if not is_global:
            for i_profile in reversed(self.metagraph_list):
                self.config_obj_apply = {f"{i_profile}": self.config_obj_apply.pop(i_profile), **self.config_obj_apply }
        
        if apply: self.apply_vars_to_config() 
        
        
    def manual_build_layer(self,profile=False):
        default = "1" if not profile else self.c.config_obj[profile]["layer"]
        profile = self.profile_to_edit if not profile else profile
        
        self.manual_section_header(profile,"DLT LAYER")
        
        description = "The distributed ledger technology 'DLT' generally called the blockchain "
        description += "($DAG Constellation Network uses directed acyclic graph 'DAG') is designed by layer type. This needs to be a valid "
        description += "integer (number) between 0 and 4, for the 5 available layers. Constellation Network or Metagraph clusters are generally always layer 0 or 1. "
        description += "Hypergraph/Metagraph Layer 0 can be referred to as ML0, Hypergraph/Metagraph Layer1 can be referred to as ML1 and the Constellation "
        description += "Network Global Layer0 Hypergraph can be referred to as GL0.  ML0 and ML1 should link to GL0.  ML1 should link to ML0. "
        description += "See the linking section for link options and details."
        
        questions = {
            "layer": {
                "question": f"  {colored(f'What blockchain (DLT) layer is this profile {profile} running','cyan')}",
                "description": description,
                "default": default,
                "required": False,
            },
        }
        
        self.manual_append_build_apply({
            "questions": questions, 
            "profile": profile
        })
        
        
    def manual_collateral(self,profile=False):
        default = "0" if not profile else self.c.config_obj[profile]["collateral"]
        profile = self.profile_to_edit if not profile else profile
        
        self.manual_section_header(profile,"COLLATERAL")
        
        description = "In order to participate on a cluster a Node may be required to hold collateral within the "
        description += "active (hot) wallet located on this Node.  In the event that collateral is waved or there is not a requirement "
        description += "to hold collateral, this value can be set to 0. Please contact administration to "
        description += "define this requirement. "
        
        questions = {
            "collateral": {
                "question": f"  {colored(f'Enter the collateral amount required for this profile {profile}','cyan')}",
                "description": description,
                "default": default,
                "required": False,
            },
        }
        
        self.manual_append_build_apply({
            "questions": questions, 
            "profile": profile
        })
        
        
    def manual_build_environment(self,profile=False):
        default = None if not profile else self.c.config_obj[profile]["environment"]
        profile = self.profile_to_edit if not profile else profile
        required = True if not profile else False
        
        self.manual_section_header(profile,"ENVIRONMENT")  
          
        description = "Hypergraph/Metagraph Layer 0 can be referred to as ML0, Hypergraph/Metagraph Layer1 can be referred to as ML1 and the Constellation "
        description += "Network Global Layer0 Hypergraph can be referred to as GL0. "
        description += "This networks require an environment identifier used internally; by the network, to define certain " 
        description += "operational variables. Depending on the Metagraph, this is used to define " 
        description += "customized elements within the Metagraph. You should obtain this information " 
        description += "from the Administrators of this network. "
                
        questions = {
            "environment": {
                "question": f"  {colored('Enter network environment identifier: ','cyan')}",
                "description": description,
                "default": default,
                "required": required,
            },
        }
        self.manual_append_build_apply({
            "questions": questions, 
            "profile": profile
        })
    
            
    def manual_build_tcp(self,profile=False):
        port_start = "You must define a TCP (Transport Control Protocol) port that your Node will run on, to accept"
        port_ending = "This can be any port; however, it is highly recommended to keep the port between 1024 and 65535.  Constellation has been using ports in the 9000-9999 range. Do not reuse any ports you already defined, as this will cause conflicts. You may want to consult with your network cluster administrator for recommended port values."
        
        if profile:
            public_default = self.c.config_obj[profile]["public_port"]  
            p2p_default = self.c.config_obj[profile]["p2p_port"]     
            cli_default = self.c.config_obj[profile]["cli_port"]  

        try: 
            _ = int(self.c.config_obj[profile]["layer"])
        except:
            self.log.logger.error(f'invalid blockchain layer entered [{self.c.config_obj[profile]["layer"]}] cannot continue')
            self.error_messages.error_code_messages({
                "error_code": "cfr-369",
                "line_code": "invalid_layer",
                "extra": self.c.config_obj["layer"]
            })
            
        self.manual_section_header(profile,"TCP PORTS") 
                            
        questions = {
            "public_port": {
                "question": f"  {colored('Enter the public TCP port for this Node','cyan')}",
                "description": f"{port_start} public inbound traffic. {port_ending}",
                "required": False,
                "default": public_default,
            },
            "p2p_port": {
                "question": f"  {colored('Enter the P2P TCP port for this Node','cyan')}",
                "description": f"{port_start} peer to peer (p2p) traffic. {port_ending}",
                "required": False,
                "default": p2p_default,
            },
            "cli_port": {
                "question": f"  {colored('Enter the localhost TCP port for this Node','cyan')}",
                "description": f"{port_start} internal/local host requests to access its own API (application program interface). {port_ending}",
                "required": False,
                "default": cli_default,
            },
        }
        
        self.manual_append_build_apply({
            "questions": questions, 
            "profile": profile
        })
        
        self.c.functions.print_paragraphs([
            ["",1],[" WARNING ",0,"red,on_yellow"], ["You must now update your firewall settings to allow",0],
            ["ports",0], 
            [f"{self.c.profile_obj[profile]['public_port']}, {self.c.profile_obj[profile]['p2p_port']}",0,"yellow"], 
            ["through inbound via the ingress rules.",2],
        ])
        self.c.functions.print_any_key({"prompt":"Press any key to return to the main menu"})
        
        
    def manual_build_service(self,profile=False):
        default = None if not profile else self.c.config_obj[profile]["service"]
        required = True if not profile else False
        profile = self.profile_to_edit if not profile else profile
        
        self.manual_section_header(profile,"SYSTEM SERVICES") 
        
        questions = {
            "service": {
                "question": f"  {colored(f'Enter Debian service name for this profile: ','cyan')}",
                "description": f"The Node that will run on this Debian based operating system will use a service. The service controls the server level 'under the hood' operations of this profile [{profile}]. Each profile runs its own service.  nodectl will create and control this service for the Node Operator. You have the ability to give it a specific name.",
                "default": default,
                "required": required
            },
        }
        
        self.manual_append_build_apply({
            "questions": questions, 
            "profile": profile
        })
            
            
    def manual_build_link(self,profile=False): 
        title_profile = self.profile_to_edit if not profile else profile
        
        gl0_linking, ml0_linking = True, True
        gl0_ask_questions, ml0_ask_questions = False, False
        questions, defaults = False, False
        
        layer_types = ["gl0","ml0"]
        
        def print_header():
            link_description = "Generally, a Hypergraph/Metagraph Layer0 (ML0) and/or Hypergraph/Metagraph Layer1 (ML1) will be required to link to the Hypergraph Global Layer0 "
            link_description += "(GL0) network to transmit consensus information between the local Node and the Validator Nodes on the Layer0 network. "
            link_description += "The Node Operator should consult with your Constellation Network or Metagraph Administrators for further details. "
            link_description += "Also, a ML1 will be required to link to the ML0 thereby creating to separate links. "
            link_description += "IMPORTANT: If you plan to use the recommended process of linking to ML1 to GL0, ML1 to ML0, and/or ML0 to GL0 "
            link_description += "through another profile residing on this Node, it is required to answer \"yes\" to the link to self question, "
            link_description += "when asked by this configurator feature; otherwise, all necessary values will not be populated and unexpected "
            link_description += "results/errors may be experienced. "

            print("")
            self.manual_section_header(title_profile,"LINK SETUP")
            self.c.functions.print_paragraphs([
                ["",1],
                ["Terminology",1,"yellow","bold"],
                ["GL0",0,"blue","bold"],[":",-1,"blue"], ["Global Layer0 Hypergraph",1,"cyan"],
                ["ML0",0,"blue","bold"],[":",-1,"blue"], ["Cluster Layer0",1,"cyan"],
                ["ML1",0,"blue","bold"],[":",-1,"blue"], ["Cluster Layer1",2,"cyan"],
                [link_description,1,"white","bold"],
            ]) 
            self.print_quit_option()
        
        def set_link_obj(l_type,value):
            return {
                f"{l_type}_link_key": value,
                f"{l_type}_link_host": value,
                f"{l_type}_link_port": value,                
                f"{l_type}_link_profile": value,                
            }

        def self_linking(l_type, defaults):
            set_self_successful = False
            self_items = {}
            if self.c.functions.confirm_action({
                "yes_no_default": "n",
                "return_on": "y",
                "prompt": f"Do you want to link {l_type.upper()} to itself?",
                "exit_if": False
            }):
                self_items = set_link_obj(l_type,"self")
                print("")
                cprint(f"  Which profile do you want to {l_type.upper()} to link with?","magenta")
                
                linkable_profiles = []
                for i_profile in self.metagraph_list:
                    if i_profile != profile:
                        if self.c.config_obj[i_profile]["layer"] < 1:
                            linkable_profiles.append(i_profile)
                
                if len(linkable_profiles) < 1:
                    cprint("  No available profiles to link to cancelling","red")
                else:
                    option = self.c.functions.print_option_menu({
                        "options": linkable_profiles,
                        "let_or_num": "num",
                        "color": "magenta",
                        "return_value": True
                    })
                    self_items[f"{l_type}_link_profile"] = option   
                    defaults = {
                        **defaults,
                        **self_items
                    }
                    set_self_successful = True
                    
            return [defaults, set_self_successful]
            
        def ask_link_questions(l_type, questions, key_default, host_default, port_default):
            warning_msg = f"running a {'ML0' if l_type == 'ml0' else 'GL0'} network on the same Node as the Node running this cluster.  In order to do this you cancel this setup and choose the 'self' option when requested."
            questions = {
                **questions,
                f"{l_type}_link_key": {
                    "question": f"  {colored(f'Enter the {l_type.upper()} link public key','cyan')} : ",
                    "description": f"You need to identify the public key of the Node that you going to attempt to link to. This is required for security purposes to avoid man-in-the-middle cybersecurity attacks.  It is highly recommended to use the public key of your own Node if you are {warning_msg} If you are not using your own Node, you will need to obtain the public p12 key from the Node you are attempting to link through.",
                    "default": key_default,
                    "required": False,
                },          
                f"{l_type}_link_host": {
                    "question": f"  {colored(f'Enter the {l_type.upper()} link host ip address','cyan')} : ",
                    "description": f"You need to identify the public ip address of the Node that you going to attempt to link with. It is highly recommended to use your own Node if you are {warning_msg}",
                    "default": host_default,
                    "required": False,
                },  
                f"{l_type}_link_port": {
                    "question": f"  {colored(f'Enter the {l_type.upper()} link public port','cyan')} : ",
                    "description": f"You need to identify the public TCP port open on the Node that you going to attempt to link with. It is highly recommended to use your own Node if you are {warning_msg}",
                    "default": port_default,
                    "required": False,
                },  
            }
            return questions        
 
        def retain_info(profile, gl0_linking, ml0_linking,print_msg=True):
            if print_msg:
                self.c.functions.print_cmd_status({
                    "text_start": "Values for",
                    "brackets": l_type.upper(),
                    "text_end": "will be",
                    "status": "retained",
                    "status_color": "green",
                    "newline": True,
                })
            current_boj = {
                f"{l_type}_link_key": self.c.config_obj[profile][f"{l_type}_link_key"],
                f"{l_type}_link_host": self.c.config_obj[profile][f"{l_type}_link_host"],
                f"{l_type}_link_port": self.c.config_obj[profile][f"{l_type}_link_port"],             
                f"{l_type}_link_profile": self.c.config_obj[profile][f"{l_type}_link_profile"],               
            }
            if l_type == "gl0": gl0_linking = False
            if l_type == "ml0": ml0_linking = False
            return current_boj, gl0_linking, ml0_linking

        if profile:  # left in place in case full manual profile creation is reinstituted
            print(" ")
            print_header()
            print(" ")

            for l_type in layer_types:
                status = "disabled"; status_color = "red"
                if self.c.config_obj[profile][f"{l_type}_link_enable"]:
                    status = "enabled"; status_color = "green"
                self.c.functions.print_cmd_status({
                    "text_start": "Linking for",
                    "brackets": f"{profile} -> {l_type.upper()}",
                    "text_end": "found",
                    "status": status,
                    "status_color": status_color,
                    "newline": True
                })
                if status == "disabled":
                    if self.c.functions.confirm_action({
                            "yes_no_default": "n",
                            "return_on": "y",
                            "prompt": f"Do you want to enable the {l_type.upper()} link?",
                            "exit_if": False
                        }):
                            if not defaults: defaults = {}
                            defaults = {**defaults, f"{l_type}_link_enable": "True"} 
                    elif l_type == "gl0": gl0_linking = False
                    elif l_type == "ml0": ml0_linking = False
                elif status == "enabled":
                    if self.c.functions.confirm_action({
                        "yes_no_default": "n",
                        "return_on": "y",
                        "prompt": f"Do you want to disable the {l_type.upper()} link?",
                        "exit_if": False
                    }):
                        disable = set_link_obj(l_type,"None")
                        if not defaults: defaults = {}
                        defaults = {**defaults, **disable, f"{l_type}_link_enable": "False" }
                        if l_type == "gl0": gl0_linking = False
                        if l_type == "ml0": ml0_linking = False
                    else:
                        if self.c.functions.confirm_action({
                                "yes_no_default": "n",
                                "return_on": "y",
                                "prompt": f"Do you want to retain old values for the {l_type.upper()} link?",
                                "exit_if": False
                            }):
                                if not defaults: defaults = {}
                                c_defaults, gl0_linking, ml0_linking = retain_info(profile, gl0_linking, ml0_linking)
                                defaults = {**c_defaults, **defaults}
                                
                retain_original = False
                if eval(f"{l_type}_linking"):
                    results = self_linking(l_type, defaults if defaults else {})
                    if not defaults: defaults = {}
                    if results[1]: defaults = {**defaults, **results[0]}
                    elif l_type == "gl0": gl0_ask_questions = True
                    elif l_type == "ml0": ml0_ask_questions = True
                else:
                    retain_original = True

                if eval(f"{l_type}_ask_questions"):
                    key_default = self.c.config_obj[profile][f"{l_type}_link_key"]
                    host_default = self.c.config_obj[profile][f"{l_type}_link_host"]
                    port_default = self.c.config_obj[profile][f"{l_type}_link_port"]
                    if not questions: questions = {}
                    if not defaults: defaults = {}
                    defaults = {**defaults, f"{l_type}_link_profile": "None"}
                    questions = {
                        **questions,
                        **ask_link_questions(l_type, questions, key_default, host_default, port_default)
                    }
                else:
                    retain_original = True
                    
                if retain_original:
                    c_defaults, gl0_linking, ml0_linking = retain_info(profile, gl0_linking, ml0_linking,False)
                    if defaults:
                        defaults = {**c_defaults, **defaults}
                    else:
                        defaults = c_defaults
        
        
        self.manual_append_build_apply({
            "questions": questions, 
            "profile": profile,
            "defaults": defaults,
        })
        
        
    def manual_define_token_identifier(self,profile=False):
        if profile == "global_elements": pass
        else: 
            default = "global" if not profile else self.c.config_obj[profile]["token_identifier"]
        profile = self.profile_to_edit if not profile else profile
        defaults, questions = False, False
        key_name = "token_identifier"

        if profile == "global_elements":
            default = "disable"
            self.header_title = {
                "line1": "EDIT GLOBAL SETTINGS",
                "line2": "Metagraph Token Identifier",
                "show_titles": False,
                "clear": True,
                "newline": "both",
            }
            key_name = "metagraph_token_identifier"            
            
        self.manual_section_header(profile,"TOKEN IDENTIFIER")
        print("")
        
        description = "When working within a Metagraph, you will need to define the Metagraph's ID "
        description += "this ID will identify the Metagraph that you are connecting to via an identifier that "
        description += "resembles a DAG wallet address; however, it is a not a wallet address. "
        description += "You should obtain this identifier from the Metagraph administration.  It should normally be "
        description += "supplied with a pre-defined configuration.  Constellation Network MainNet, TestNet, and IntegrationNet "
        description += "should have this key pair value set to 'disable'. "
        description += "If the 'token_identifier' is set to 'global', the global 'metagraph_token_identifier' will be used. "
        
        if self.detailed:
            self.c.functions.print_paragraphs([
                [description,2,"white","bold"]
            ])
            
        prompt = "Set token identifier to disable?"
        if profile == "global_elements":
            prompt = "Set global token identifier to disable?"
        if self.c.functions.confirm_action({
            "prompt": prompt,
            "yes_no_default": "y",
            "return_on": "y",
            "exit_if": False
        }):
            defaults = {
                f"{key_name}": "disable",
            }        
        else:
            question = f"  {colored(f'Enter the token identifier required for this profile = {profile}','cyan')}"
            if profile == "global_elements":
                question = f"  {colored(f'Enter the global token identifier to use for all profiles','cyan')}"
            questions = {
                f"{key_name}": {
                    "question": question,
                    "description": "Metagraph token Identifier",
                    "default": default,
                    "required": False,
                },
            }
    
        self.manual_append_build_apply({
            "questions": questions, 
            "profile": profile,
            "defaults": defaults,
            "is_global": True if profile == "global_elements" else False
        })
        
        
    def manual_define_token_coin(self,profile=False):
        key_name = "token_coin_id" 
        if profile == "global_elements":
            default = "default"
            self.header_title = {
                "line1": "EDIT GLOBAL SETTINGS",
                "line2": "Token Company Specifier",
                "show_titles": False,
                "clear": True,
                "newline": "both",
            }
            key_name = "metagraph_token_coin_id"
        else:
            default = "global" if not profile else self.c.config_obj[profile][key_name]
        profile = self.profile_to_edit if not profile else profile
        defaults, questions, manual = False, False, False
        
        self.manual_section_header(profile,"TOKEN COMPANY SPECIFIER ID")
        print("")
        
        description = "The Metagraph you are working with may have a dedicated token specific to that Metagraph. "
        description += "If the token is recognized by CoinGecko it will be displayed when issuing the 'dag','price', or 'market' commands. "
        description += "If the token is NOT recognized by CoinGecko, you should enter 'constellation-labs' or 'default'. "
        description += "This will set nodectl to 'constellation-labs' and display '$DAG' when appropriate. "
        description += "This value must be the CoinGecko 'api id' for the token/coin you want to be added to nodectl's lookup commands. "
        description += "You can find the 'id' by going to the CoinGecko website at 'https://www.coingecko.com/en/all-cryptocurrencies' and search through the "
        description += "list until you find your 'Coin' and click on it.  On the LEFT side of the details for your 'Coin' you will see 'API ID'. Enter that "
        description += "value here, when requested."
        
        description2 = "Handle Hypergraph/Metagraph cryptocurrency token symbol identification."

        if self.detailed:
            self.c.functions.print_paragraphs([
                [description,2,"white","bold"]
            ])

        if profile == "global_elements":
            if self.c.functions.confirm_action({
                "prompt": "Set token coin id to default?",
                "yes_no_default": "y",
                "return_on": "y",
                "exit_if": False
            }):
                defaults = {
                    f"{key_name}": default,
                } 
            else:
                manual = True       
        else:            
            self.c.functions.print_paragraphs([
                ["Do you want to setup the token id to follow the global settings, set it up manually, or use the default?",2],
            ])
            option = self.c.functions.print_option_menu({
                "options": ["global","manual","default"],
                "return_where": "Edit",
                "r_and_q": "r",
                "color": "cyan",
                "newline": True,
                "return_value": True,
            })
            if option == "r": return
            elif option == "global" or option == "default":
                defaults = {
                    f"{key_name}": option,
                }     
            elif option == "manual":
                manual = True  

        if manual:
            question = f"  {colored(f'Enter the network cluster token coin api id for this profile = {profile}','cyan')}"
            if profile == "global_elements":
                question = f"  {colored(f'Enter the network cluster token coin api id to use for all profiles','cyan')}"
            questions = {
                f"{key_name}": {
                    "question": question,
                    "description": description2,
                    "default": default,
                    "required": False,
                },
            }
    
        self.manual_append_build_apply({
            "questions": questions, 
            "profile": profile,
            "defaults": defaults,
            "is_global": True if profile == "global_elements" else False
        })

  
    def manual_build_dirs(self,profile=False):   
        title_profile = self.profile_to_edit if not profile else profile
        self.manual_section_header(title_profile,"DIRECTORY STRUCTURE")
        defaults, questions = False, False
        
        if self.detailed:
            self.c.functions.print_paragraphs([
                ["",1], ["You can setup your Node to use the default directories for all definable directories.",2,"magenta"],
                [" IMPORTANT ",0,"white,on_blue"], ["Directories being migrated to (and from) must already exist.",2],
            ])
            
        dir_default = self.c.functions.confirm_action({
            "prompt": "Use defaults?",
            "yes_no_default": "y",
            "return_on": "y",
            "exit_if": False
        })

        if dir_default:
            self.c.functions.print_cmd_status({
                "text_start": "Using defaults for directory structures",
                "status": "complete",
                "newline": True,
            })
            defaults = {
                "directory_backups": "default",
                "directory_uploads": "default"
            }            
            print("")
        else:
            up_default = bk_default = "default"
            if profile:
                up_default = self.c.config_obj[profile]["directory_uploads"]
                bk_default = self.c.config_obj[profile]["directory_backups"]
            
            defaultdescr = "Alternatively, the Node Operator can enter the string \"default\" to allow nodectl to use default values. "
            description1 = "The uploads directory is where any files that may be needed for troubleshooting or "
            description1 += "analysis are placed by nodectl. This directory should be a full path! "
            description1 += defaultdescr
            
            description2 = "The backups directory is where any files that may need to be restored or referenced at a later date are "
            description2 += "placed by nodectl. This directory should be a full path!"
            description2 += defaultdescr
            
            questions = {
                "directory_uploads": {
                    "question": f"  {colored('Enter a valid','cyan')} {colored('uploads','yellow')} {colored('directory','cyan')}",
                    "description": description1,
                    "required": False,
                    "default": up_default
                },
                "directory_backups": {
                    "question": f"  {colored('Enter a valid','cyan')} {colored('backups','yellow')} {colored('directory','cyan')}",
                    "description": description2,
                    "required": False,
                    "default": bk_default,
                },
            }
            
        self.manual_append_build_apply({
            "questions": questions, 
            "profile": profile,
            "defaults": defaults,
            "apply": False  # don't apply this will be done later
        })
 
 
    def manual_build_file_repo(self, file_repo_type, profile=False): 
        if file_repo_type == "pro_rating" and self.c.config_obj[profile]["layer"] > 0:
            self.c.functions.print_paragraphs([
                ["",1],[" ERROR ",0,"yellow,on_red"],["Due to security reasons,",0,"red"],
                ["trust label ratings should not be configured on layer1 cluster profiles.",1,"red"],
            ])
            self.c.functions.print_any_key({}) 
            system("clear")
            return False
        
        title_profile = self.profile_to_edit if not profile else profile
        questions, defaults = False, False
        allow_disable = True
        one_off = "location"
        
        verb = "seed list" 
        if file_repo_type == "priority_source": verb = "priority source list"
        elif file_repo_type == "pro_rating": verb = "trust label ratings"
        elif file_repo_type == "jar": 
            verb = "jar binary"
            allow_disable = False
            one_off = "version"
        self.manual_section_header(title_profile,f"PRO SCORE - {verb.upper()}")
        print("")
        
        if self.detailed:
            self.c.functions.print_paragraphs([
                ["",1], ["You can setup your Node to use the default"],
                [verb,0,"yellow"], ["elements.",2],
            ])
            if file_repo_type == "pro_rating":
                self.c.functions.print_paragraphs([
                    [" WARNING ",0,"red,on_yellow"], ["If you choose the default values you will need to make",0,"red"],
                    ["sure the default file location and file exist on the Node before continuing; however,",0,"red"],
                    ["the verification will fail.",2,"red"],
                    ["If you are unsure about this ratings file details, it is recommended to choose",0],
                    ["disable",0,"magenta"],["as your option settings.",2],
                    ["    default file name:",0,"magenta"],[self.c.functions.default_pro_rating_file,1,"yellow"],
                    ["default file location:",0,"magenta"],[self.c.functions.default_pro_rating_location,2,"yellow"],
                ])
            
        dir_default = self.c.functions.confirm_action({
            "prompt": "Use defaults?",
            "yes_no_default": "y",
            "return_on": "y",
            "exit_if": False
        })
        
        if dir_default:
            defaults = True
            self.c.functions.print_cmd_status({
                "text_start": f"Using defaults for {file_repo_type.upper()}-LIST structures",
                "status": "complete",
                "newline": True,
            })
            if int(self.c.config_obj[profile]["layer"]) < 1:
                defaults = {
                    f"{file_repo_type}_{one_off}": "default",
                    f"{file_repo_type}_file": "default",
                    f"{file_repo_type}_location": "default",
                    f"{file_repo_type}_repository": "default",
                }
                if file_repo_type == "jar" or file_repo_type == "seed":
                    defaults[f"{file_repo_type}_version"] = "default"

            else:
                defaults = {
                    f"{file_repo_type}_{one_off}": "disable",
                    f"{file_repo_type}_file": "disable",
                    f"{file_repo_type}_location": "disable",
                    f"{file_repo_type}_repository": "disable",
                } 
                if file_repo_type == "jar" or file_repo_type == "seed":
                    defaults[f"{file_repo_type}_version"] = "default"
            
            if file_repo_type == "pro_rating":
                del defaults[f"{file_repo_type}_repository"]
                 
            print("")
            
        else:
            if profile:
                if one_off == "version": loc_default = "default"
                else: loc_default = self.c.config_obj[profile][f"{file_repo_type}_{one_off}"]
                file_default = self.c.config_obj[profile][f"{file_repo_type}_file"]
                if file_repo_type != "pro_rating":
                    repo_default = self.c.config_obj[profile][f"{file_repo_type}_repository"]
                if file_repo_type == "jar" or file_repo_type == "seed":
                    repo_version_default = self.c.config_obj[profile][f"{file_repo_type}_version"]
                    repo_local_location_default = self.c.config_obj[profile][f"{file_repo_type}_location"]
            else:
                def_value = "default" if int(self.c.config_obj[profile]["layer"]) < 1 else "disable"
                loc_default, file_default, repo_default = def_value, def_value, def_value
            
            defaultdescr = "Alternatively, the Node Operator can enter the string \"default\" to allow nodectl to use default values. "
            if allow_disable: defaultdescr += "Enter the string \"disable\" to disable this feature for this profile."
            
            description1 = ""
            if file_repo_type == "priority_source":
                description1 += f"The {verb} is a specialized access-list that is mostly designated for network cluster special access-list "
                description1 += f"elements, out of the scope of nodectl.  The values associated with these configuration values "
                description1 += f"should be obtained directly from the administrators. "
            description1 += f"The {verb} is part of the PRO (proof of reputable observation) elements of Constellation Network. "
            description1 += "Enter the location (needs to be a full path not including the file name. Note: The file name will be defined "
            description1 += "succeeding this entry.) on your local Node. This is where the Node Operator would like to store the local copy of "
            description1 += "this data file, list, or access list. "
            if file_repo_type == "seed":
                description1 += "This is a requirement to authenticate to the cluster the Node Operator is "
                description1 += "attempting to connect to. "
            if file_repo_type == "pro_rating":
                description1 += "Trust labels constitute integral aspects of the Proof of Reputable Observation (PRO) system. "
                description1 += "They impact several facets, such as determining the nodes from which to obtain snapshots. Trust labels "
                description1 += "are off-chain information concerning the security of nodes and their potential to harm the network. These labels "
                description1 += "are local bias values that you supply to your nodes during the joining process to the cluster. They "
                description1 += "are specific to each node. Consequently, different nodes can exhibit varying degrees of bias. "
            if file_repo_type == "jar":
                description1 = f"The {verb} version is used by nodectl's configuration to help determine the "
                description1 += "version during the upgrade process or from the command line when using the refresh "
                description1 += "binaries feature. This is required for Metgraphs.  MainNet, TestNet, and IntegrationNet network clusters, should leave "
                description1 += "this field set to 'default'. "


            description1 += defaultdescr

            description2 = f"The file name to be used to contain the {verb} entries.  This should be a single string value with no spaces (if you "
            description2 += "want to use multiple strings, delineate them with an underscore, dash, or other). "
            adj = "will"
            if file_repo_type == "pro_rating":
                adj = "should"
                description2 += "The Node Operator should create this file on their own. "
            else:
                description2 += f"After the {verb} is downloaded from a cluster "
                description2 += "repository (defined succeeding this entry), the contents will be saved to this file.  The file (downloaded from the repository) " 
                description2 += "must contain the exact same information as all other Nodes that participate on the cluster. "
            description2 += f"The file {adj} be placed in the location defined by the {file_repo_type} location variable entered above. "
            description2 += defaultdescr
            
            description3 = f"The {verb} repository is the location on the Internet (generally a github repository or artifact location) where nodectl can download "
            description3 += f"the {verb} associated with the network cluster. Do not enter a URL or URI (do not include "
            description3 += "http:// or https:// in the FQDN (fully qualified domain name)). The Node Operator should obtain this information "
            description3 += "from the administrators. "
            description3 += defaultdescr
            
            description5 = f"The {verb} location is the location on the local VPS/Server where nodectl should place and can access "
            description5 += f"the {verb} binary file ( identified by the {verb}_file ) to access to run the Tessellation Node protocol services. "
            description5 += defaultdescr

            one_off2 = "directory"
            if file_repo_type == "jar":
                description4 = f"The jar repository needs to have a version associated with it.  This will make sure that that correction version "
                description4 += "of the jar binaries are downloaded, allowing you to stay current with the network cluster in question."
                one_off2 = "version"
                
            questions = {
                f"{file_repo_type}_{one_off}": {
                    "question": f"  {colored(f'Enter a valid {verb} {one_off2}','cyan')}",
                    "description": description1,
                    "required": False,
                    "default": loc_default,
                },
                f"{file_repo_type}_location": {
                    "question": f"  {colored(f'Enter a valid {verb} location name','cyan')}",
                    "description": description5, 
                    "required": False,
                    "default": repo_local_location_default
                },
                f"{file_repo_type}_file": {
                    "question": f"  {colored(f'Enter a valid {verb} file name','cyan')}",
                    "description": description2, 
                    "required": False,
                    "default": file_default
                },
            }
            if file_repo_type != "pro_rating":
                questions = {
                    **questions,
                    f"{file_repo_type}_repository": {
                        "question": f"  {colored(f'Enter a valid {verb} repository','cyan')}",
                        "description": description3,
                        "required": False,
                        "default": repo_default
                    },
                }
            if file_repo_type == "jar" or file_repo_type == "seed":
                questions = {
                    **questions,
                    f"{file_repo_type}_version": {
                        "question": f"  {colored(f'Enter a valid {verb} repository version','cyan')}",
                        "description": description4,
                        "required": False,
                        "default": repo_version_default
                    },
                }
        
        # re-enable the once deprecated versioning on tessellation jar before removal
        # if one_off == "version" or one_off2 == "version":  
        #     if questions: questions.pop(f"{file_repo_type}_{one_off}")  # version will be removed.
        #     del defaults["jar_version"]
            
        self.manual_append_build_apply({
            "questions": questions, 
            "profile": profile,
            "defaults": defaults,
        })
        
        return True

                
    def manual_build_memory(self,profile=False):
        xms_default = "1024M"
        xmx_default = None
        xss_default = "256K"
        required = True
        if profile:
            xms_default = self.c.config_obj[profile]["java_xms"]
            xmx_default = self.c.config_obj[profile]["java_xmx"]
            xss_default = self.c.config_obj[profile]["java_xss"]
            required = False
        else:
            profile = self.profile_to_edit
        
        self.manual_section_header(profile,"JAVA MEMORY HEAPS")
        
        if self.detailed:
            self.c.functions.print_paragraphs([
                ["",1], ["You can setup your Node to use the default java memory heap values.",1],
                ["K",0,"yellow","underline"], ["for kilobytes,",0], ["M",0,"yellow","underline"], ["for Megabytes, and",0], ["G",0,"yellow","underline"], ["for Gigabytes.",1],
                ["example:",0,"magenta"], ["1024M",2,"yellow"]
            ])

        questions = {
            "java_xms": {
                "question": f"  {colored('Enter the java','cyan')} {colored('Xms','yellow')} {colored('desired value','cyan')}",
                "description": "Xms is used for setting the initial and minimum heap size. The heap is an area of memory used to store objects instantiated by Node's java software running on the JVM.",
                "required": False,
                "default": xms_default,
            },
            "java_xmx": {
                "question": f"  {colored('Enter the java','cyan')} {colored('Xmx','yellow')} {colored('desired value: ','cyan')}",
                "description": "Xmx is used for setting the maximum heap size. Warning: the performance of the Node will decrease if the max heap value is set lower than the amount of live data. This can force your Node to perform garbage collections more frequently, because memory space may be needed more habitually.",
                "required": required,
                "default": xmx_default,
            },
            "java_xss": {
                "question": f"  {colored('Enter the java','cyan')} {colored('Xss','yellow')} {colored('desired value','cyan')}",
                "description": "Your Node will run multiple threads and these threads have their own stacks.  This parameter is used to limit how much memory a stack consumes.",
                "required": False,
                "default": xss_default
            },
        }
        
        self.manual_append_build_apply({
            "questions": questions, 
            "profile": profile
        })
        
        
    def manual_build_p12(self,profile=False):
        if profile:
            self.is_all_global = False
            self.keep_pass_visible = True
            self.manual_section_header(profile,"P12 UPDATES")
            self.c.functions.print_paragraphs([
                ["",1], ["You are requesting to update the [",-1,"magenta"],["p12",-1,"yellow","bold"], 
                ["] settings for the configuration profile [",-1,"magenta"],
                [profile,-1,"yellow","bold"],["]. ",-1,"magenta"],["",2],
            ])

        if self.detailed:
            self.c.functions.print_paragraphs([
                ["The configuration file for this Node is setup with profile sections for each cluster.",0,"white","bold"],
                ["Each profile can be configured with unique or shared (global) p12 private key file (wallet setup) details. These details",0,"white","bold"],
                ["help nodectl understand what wallets and authorization values to use for each cluster configured.",2,"white","bold"],
                
                [f"Do you want to setup your configuration using a single p12 private key file for this profile?",2,"white","bold"],
                
                ["This will place the \"global\" key word in the configuration",0,"white","bold"],
                [f"for this profile",0,"white","bold"],
                ["and as a result the p12 private key information in the global section will be used",0,"white","bold"],
                ["for the configured profiles with \"global\" set as their values.",2,"white","bold"],
            ])
        dedicated_p12 = self.c.functions.confirm_action({
            "prompt": f"Use the global p12 settings for {colored(profile,'yellow')} {colored('profile(s)?','cyan')}",
            "yes_no_default": "y",
            "return_on": "n",
            "exit_if": False
        })
        single_p12_obj = {}
        if dedicated_p12:
            self.config_obj = deepcopy(self.c.config_obj)
            p12_obj = self.request_p12_details({
                "profile": profile,
                "ptype": "single",
                "get_existing_global": False,
                "set_default": True
            })
            for p12_item in p12_obj.keys():
                single_p12_obj[f"p12_{p12_item}"] = p12_obj[p12_item]
        else:
            for p12_item in self.p12_items:
                single_p12_obj[f"p12_{p12_item}"] = "global"
                
        self.manual_append_build_apply({
                "profile": profile,
                "questions": False,
                "defaults": single_p12_obj,
        })
            
        return


    # =====================================================
    # COMMON BUILD METHODS  
    # =====================================================

      
    def ask_confirm_questions(self, command_obj):
        questions = command_obj["questions"]
        confirm = command_obj.get("confirm",True)
        
        alternative_confirm_keys = questions.get("alt_confirm_dict",{})
        if len(alternative_confirm_keys) > 0:
            alternative_confirm_keys = questions.pop("alt_confirm_dict")
            
        while True:
            value_dict = {}
            
            for key, values in questions.items():
                default = questions[key].get("default",None)
                required = questions[key].get("required",True)
                description = questions[key].get("description",None)
                v_type = questions[key].get("v_type","str")
            
                question = values["question"]
                if default != None and default != "None":
                    question = f"{question} {colored('[','cyan')}{colored(default,'yellow',attrs=['bold'])}{colored(']: ','cyan')}"

                while True:
                    print("")
                    if description != None and self.detailed:
                        self.c.functions.print_paragraphs([[description,2,"white","bold"]])
                    if v_type == "pass":
                        input_value = getpass(question)
                    else:
                        input_value = input(question)
                        if v_type == "bool":
                            if input_value.lower() == "y" or input_value.lower() == "yes":
                                input_value = "y" 
                            elif input_value.lower() == "n" or input_value.lower() == "no":
                                input_value = "n"
                            else:
                                input_value = ""
                                             
                    if required and input_value.strip() == "":
                        print(colored("  valid entry required","red"))
                    elif input_value.strip() == "":
                        input_value = "None Entered" 
                        if default != None:
                            input_value = default
                        break
                    else:
                        break

                value_dict[key] = str(input_value)

            user_confirm = True
            if confirm:
                confirm_dict = copy(value_dict)
                if len(alternative_confirm_keys) > 0:
                    for new_key, org_key in alternative_confirm_keys.items():
                        confirm_dict[new_key] = confirm_dict.pop(org_key)
                    
                self.c.functions.print_header_title({
                    "line1": "CONFIRM VALUES",
                    "show_titles": False,
                    "newline": "top"
                })
                
                paragraphs = [
                    ["If you reached this confirmation",0,"yellow"], ["unexpectedly",0, "yellow","bold,underline"], [",from the input [above] you may have hit",0,"yellow"], ["<enter>",0], 
                    ["along with your option; therefore, choosing the default.  You can choose",0,"yellow"],
                    ["n",0,"bold"], ["here and reenter the correct value.",2,"yellow"]
                ]            
                
                for key, value in confirm_dict.items():
                    paragraphs.append([f"{key.replace('_',' ')}:",0,"magenta"])
                    paragraphs.append([value,1,"yellow","bold"])                        
                self.c.functions.print_paragraphs(paragraphs)
                
                user_confirm = self.c.functions.confirm_action({
                    "prompt": f"\n  Please confirm values are as requested:",
                    "yes_no_default": "y",
                    "return_on": "y",
                    "exit_if": False
                })
                print("")
                
            if user_confirm:
                return value_dict
            
    # =====================================================
    # EDIT CONFIG METHODS  
    # =====================================================
    
    def edit_config(self):
        # self.action = "edit"
        return_option = "init"
        
        while True:
            self.prepare_configuration("edit_config",True)
            self.metagraph_list = self.c.metagraph_list
            
            if self.action == "edit_profile" or self.action == "edit_change_profile":
                option = "e"
            elif self.action == "dev_mode" or self.action == "includes_section":
                option = "de"
            else:
                self.c.functions.print_header_title({
                    "line1": "NODECTL EDITOR READY",
                    "single_line": True,
                    "clear": True,
                    "newline": "both",
                })  

                if self.detailed:        
                    self.c.functions.print_paragraphs([
                        ["nodectl",0,"blue","bold"], ["configuration yaml",0],["was found, loaded, and validated.",2],
                        
                        ["If the configuration",0,"red","bold"], ["found on the",0,"red"], ["Node",0,"red","underline"], ["reports a known issue;",0,"red"],
                        ["It is recommended to go through each",0,"red"],["issue",0,"yellow","underline"], ["one at a time, revalidating the configuration",0,"red"],
                        ["after each edit, in order to make sure that dependent values, are cleared by each edit made.",2,"red"],
                        
                        ["If not found, please use the",0], ["manual",0,"yellow","bold"], ["setup and consult the Constellation Network Doc Hub for details.",2],
                    ])
                
                self.c.functions.print_header_title({
                    "line1": "OPTIONS MENU",
                    "show_titles": False,
                    "newline": "bottom"
                })

                # options = ["E","A","G","R","L","M","Q"]
                options = ["E","G","R","L","P","M","Q","T","I"]
                if return_option.upper() not in options:
                    self.c.functions.print_paragraphs([
                        ["E",-1,"magenta","bold"], [")",-1,"magenta"], ["E",0,"magenta","underline"], ["dit Individual Profile Sections",-1,"magenta"], ["",1],
                        # ["A",-1,"magenta","bold"], [")",-1,"magenta"], ["A",0,"magenta","underline"], ["ppend New Profile to Existing",-1,"magenta"], ["",1],
                        ["G",-1,"magenta","bold"], [")",-1,"magenta"], ["G",0,"magenta","underline"], ["lobal P12 Configuration",-1,"magenta"], ["",1],
                        ["I",-1,"magenta","bold"], [")",-1,"magenta"], ["Global Cluster",0,"magenta"],["Token",0,"magenta"], ["I",0,"magenta","underline"], ["dentifier",-1,"magenta"],["",1],
                        ["T",-1,"magenta","bold"], [")",-1,"magenta"], ["Global Cluster",0,"magenta"],["T",0,"magenta","underline"], ["oken Coin Id",-1,"magenta"], ["",1],
                        ["R",-1,"magenta","bold"], [")",-1,"magenta"], ["Auto",0,"magenta"], ["R",0,"magenta","underline"], ["estart Configuration",-1,"magenta"], ["",1],
                        ["L",-1,"magenta","bold"], [")",-1,"magenta"], ["Set",0,"magenta"],["L",0,"magenta","underline"], ["og Level",-1,"magenta"], ["",1],
                        ["P",-1,"magenta","bold"], [")",-1,"magenta"], ["P",0,"magenta","underline"], ["assphrase Encryption",-1,"magenta"], ["",1],
                        ["M",-1,"magenta","bold"], [")",-1,"magenta"], ["M",0,"magenta","underline"], ["ain Menu",-1,"magenta"], ["",1],
                        ["Q",-1,"magenta","bold"], [")",-1,"magenta"], ["Q",0,"magenta","underline"], ["uit",-1,"magenta"], ["",2],
                    ])

                    return_option = "init" # reset
                    option = self.c.functions.get_user_keypress({
                        "prompt": "KEY PRESS an option",
                        "prompt_color": "cyan",
                        "options": options
                    })
                else:
                    option = return_option.lower()
            
            if option == "e":
                print("")
                self.header_title = {
                    "line1": "EDIT PROFILES",
                    "show_titles": False,
                    "clear": True,
                    "newline": "both",
                }  
                
                return_option = None
                if self.action == "edit_profile": 
                    return_option = self.edit_profiles()
                if return_option == "q": 
                    self.quit_configurator()
                elif return_option == "e": 
                    self.requested_profile = None
                    self.action = "edit_change_profile"
                    self.edit_profiles() # return option can change again
                elif return_option == "m":
                    self.action = "edit"
                elif return_option != "r": 
                    return_option = self.edit_profile_sections()
            elif option == "g": self.edit_append_profile_global("p12")
            elif option == "de": 
                self.developer_enable_disable()
                self.quit_configurator(False)
            elif option == "r": self.edit_auto_restart()
            elif option == "p": 
                self.passphrase_enable_disable_encryption("configurator")
                self.c.functions.print_cmd_status({
                    "text_start": "Resetting global configuration",
                    "newline": True,
                })
                self.edit_append_profile_global("p12")
            elif option == "l": self.manual_log_level()
            elif option == "i": self.manual_define_token_identifier("global_elements")
            elif option == "t": self.manual_define_token_coin("global_elements")
            elif option == "m":
                self.action = False
                self.setup()
            if option == "q": self.quit_configurator()

                
    def edit_profiles(self):
        self.c.functions.print_header_title({
            "line1": "SELECT AVAILABLE PROFILES",
            "single_line": True,
            "newline": "bottom",
        })  
        
        self.c.functions.print_paragraphs([
            ["nodectl",0,"blue","bold"], ["found the following profiles:",2]
        ])        
        
        # did a manual edit of the profile by node operator cause issue?
        try:
            _ = self.c.metagraph_list
        except:
            self.error_messages.error_code_messages({
                "error_code": "cfr-1887",
                "line_code": "config_error",
                "extra": "format",
                "extra2": "existence",
            })
            
        options = copy(self.c.metagraph_list) # don't want metagraph_list altered
        if self.requested_profile in options:
            choice = self.requested_profile
        else:
            choice = self.c.functions.print_option_menu({
                "options": options,
                "return_value": True,
                "return_where": "Edit",
                "color": "magenta",
                "r_and_q": "both",
            })
        if choice == "r": 
            self.action = "edit"
            self.edit_config()
        if choice == "q": 
            self.quit_configurator()
            
        self.profile_to_edit = choice
        return choice
            
        
    def edit_profile_sections(self,topic="EDIT"):

        def print_config_section():
            self.c.functions.print_header_title({
                "line1": "CONFIGURATOR SECTION",
                "line2": f"{topic}",
                "show_titles": False,
                "newline": "top",
                "clear": True,
                "upper": False,
            })
            
        print_config_section()

        profile = self.profile_to_edit
        if self.profile_to_edit == None:
            if self.requested_profile:
                profile = self.requested_profile
                self.profile_to_edit = profile
            else:
                profile = self.edit_profiles()
            
                         
        section_change_names = [
            ("System Service",4),
            ("Directory Structure",5),
            ("DLT Layer Type",6),
            ("Environment Name",7),
            ("Java Memory Heap",8),
            ("Seed List Setup",9),
            ("Tessellation Binaries",10),
            ("Source Priority Setup",11),
            ("Profile Description",12),
            ("Profile P12 Key Setup",13),
            ("Node Type",14),
            ("Custom Variables",15),
            ("Collateral Requirements",16),
            ("API Edge Point",17),
            ("API TCP Ports",18),
            ("Consensus Linking",19),
            ("Network Cluster Type",20),
            ("Token Identifier",21),
            ("Rating File Setup",22),
            ("Token Coin ID",23),
        ]
        section_change_names.sort()
                        
        while True:
            do_print_title, do_validate = True, True
            secondary_menu = False
            option = 0
            self.called_option = "profile editor"
            if profile == None:
                self.edit_profile_sections()
            self.edit_enable_disable_profile(profile,"prepare")
            bright_profile = colored(profile,"magenta",attrs=["bold"])

            print(f"{colored('  2','magenta',attrs=['bold'])}{colored(f') Change name [{bright_profile}','magenta')}{colored(']','magenta')}")
            print(f"{colored('  3','magenta',attrs=['bold'])}{colored(f') Delete profile [{bright_profile}','magenta')}{colored(']','magenta')}")
            
            option_list = ["1","2","3"]

            self.c.functions.print_header_title({
                "line1": f"CHOOSE A SECTION",
                "single_line": True,
                "newline": "both"
            })
            
            for p, section in enumerate(section_change_names):
                p = p+4
                p_option = colored(f" {p}","magenta",attrs=["bold"]) if p < 10 else colored(f'{p}',"magenta",attrs=["bold"])
                option_list.append(f'{p}')
                section = colored(f")  {section[0]}","magenta")
                print(self.wrapper.fill(f"{p_option}{section}")) 
                    
            p_option = colored("H","magenta",attrs=["bold"])
            section = colored(")elp","magenta")
            print("\n",self.wrapper.fill(f"{p_option}{section}")) 
                    
            p_option = colored(" R","magenta",attrs=["bold"])
            section = colored(")eview Config","magenta")
            print(self.wrapper.fill(f"{p_option}{section}")) 
                    
            p_option = colored(" P","magenta",attrs=["bold"])
            section = colored(")rofile Menu","magenta")
            print(self.wrapper.fill(f"{p_option}{section}")) 
                    
            p_option = colored(" M","magenta",attrs=["bold"])
            section = colored(")ain Menu","magenta")
            print(self.wrapper.fill(f"{p_option}{section}")) 
                    
            p_option = colored(" Q","magenta",attrs=["bold"])
            section = colored(")uit","magenta")
            print(self.wrapper.fill(f"{p_option}{section}")) 
            print("")

            options2 = ["H","R","M","P","Q"]
            option_list.extend(options2)
            
            prompt = colored("  Enter an option: ","magenta",attrs=["bold"])
            option = input(prompt)
        
            if option == "m": 
                self.action = "edit"
                return "m"
            elif option == "p": 
                self.action = "edit_profile"
                return "e"
            elif option == "h": 
                self.move_config_backups()
                self.c.functions.config_obj = deepcopy(self.c.config_obj)
                self.c.functions.config_obj["global_elements"]["metagraph_name"] = "None"
                self.c.functions.profile_names = self.metagraph_list
                self.c.functions.check_for_help(["help"],"configure")
            elif option == "q": self.quit_configurator()
            elif option == "r":
                self.c.view_yaml_config("migrate")
                print_config_section()
                
            if option not in options2:
                try: option =int(option)
                except: option = -1
                if option > 3:
                    secondary_menu = True
                    try: option = option-3
                    except: option = -1
                    if option > len(section_change_names): option = -1
                
            if option not in options2 and option > -1:
                if secondary_menu: option = section_change_names[option-1][1]

                if option == 1:
                    self.called_option = "enable_disable"
                    self.edit_enable_disable_profile(profile)
                    
                elif option == 2:
                    self.called_option = "Profile Name Change"
                    profile = self.edit_profile_name(profile) # returns new profile name
                    self.prepare_configuration("edit_config",True)
                    do_validate = False
                    
                elif option == 3:
                    self.called_option = "Delete Profile"
                    self.delete_profile(profile)
                    return "E" # return to edit menu
                        
                elif option == 4:
                    self.called_option = "Service Name Change"
                    self.edit_service_name(profile)

                elif option == 5:
                    self.called_option = "Directory structure modification"  
                    self.migrate_directories(profile)
                    self.error_hint = "dir"
                                                            
                elif option == 6:
                    self.called_option = "layer modification"
                    self.manual_build_layer(profile)
                    self.edit_error_msg = f"Configurator found a error while attempting to edit the [{profile}] [layer] [{self.action}]"
                    
                elif option == 7:
                    self.called_option = "Environment modification"
                    self.manual_build_environment(profile)
                    do_validate = False

                elif option == 8:
                    self.called_option = "Java heap memory modification"
                    self.manual_build_memory(profile)
                    self.edit_error_msg = f"Configurator found a error while attempting to edit the [{profile}] [java heap memory] [{self.action}]"

                elif option == 9 or option == 10 or option == 11 or option == 22:
                    self.called_option = "PRO modification"
                    file_repo_type = "seed" 
                    if option == 11: file_repo_type ="priority_source"
                    if option == 10: file_repo_type = "jar"
                    if option == 22: file_repo_type = "pro_rating"
                    do_validate = self.manual_build_file_repo(file_repo_type,profile)
                    self.edit_error_msg = f"Configurator found a error while attempting to edit the [{profile}] [pro seed list] [{self.action}]"
                   
                elif option == 12:
                    self.called_option = "Description modification"  
                    self.manual_build_description(profile)
                    do_validate = False
                    
                elif option == 13:
                    self.called_option = "P12 modification"
                    self.manual_build_p12(profile)
                    
                elif option == 14:
                    self.called_option = "Node type modification"  
                    self.manual_build_node_type(profile)
                    
                elif option == 15:
                    self.called_option = "Custom Arguments"
                    self.manual_args(profile)
                    do_validate = False      
                                                                               
                elif option == 16:
                    self.called_option = "layer modification"
                    self.manual_collateral(profile)
                    self.edit_error_msg = f"Configurator found a error while attempting to edit the [{profile}] [collateral] [{self.action}]"

                elif option == 17:
                    self.called_option = "Edge Point Modification"    
                    self.manual_build_edge_point(profile)
                    self.edit_error_msg = f"Configurator found a error while attempting to edit the [{profile}] [edge_point] [{self.action}]"
                    
                elif option == 18:
                    self.called_option = "TCP modification"
                    self.tcp_change_preparation(profile)
                    self.manual_build_tcp(profile)
                    self.edit_error_msg = f"Configurator found a error while attempting to edit the [{profile}] [TCP build] [{self.action}]"

                elif option == 19:
                    self.called_option = "Layer0 link"
                    self.manual_build_link(profile)
                    self.error_hint = "link"
                                                            
                elif option == 20:
                    self.called_option = "metagraph name"
                    self.manual_define_meta(profile)
                    self.edit_error_msg = f"Configurator found a error while attempting to edit the [{profile}] [meta type] [{self.action}]"
                                                            
                elif option == 21:
                    self.called_option = "token identifer"
                    self.manual_define_token_identifier(profile)
                    self.edit_error_msg = f"Configurator found a error while attempting to edit the [{profile}] [token id] [{self.action}]"
                                                            
                elif option == 23:
                    self.called_option = "token_coin_id"
                    self.manual_define_token_coin(profile)
                    self.edit_error_msg = f"Configurator found a error while attempting to edit the [{profile}] [token] [{self.action}]"
                                        
                if do_validate: 
                    self.validate_config()
                if do_print_title: print_config_section()
            elif option not in options2:
                cprint("  Invalid Option, please try again","red")
            
            self.prepare_configuration("edit_config",False) # reload config in case operator requests 


    def edit_auto_restart(self):
        self.c.functions.print_header_title({
            "line1": "AUTO RESTART EDITOR",
            "show_titles": False,
            "newline": "top",
        })
        
        warning = False
        self.restart_needed = self.upgrade_needed = False
        
        for profile in self.c.config_obj.keys():
            if profile == "global_p12":
                if self.c.config_obj[profile]["passphrase"] == "None":
                    warning = True
                    break
            elif profile in self.c.metagraph_list:
                if self.c.config_obj[profile]["p12_passphrase"] == "None":
                    warning = True
                    break
                
        if warning:
            self.c.functions.print_paragraphs([
                [" WARNING ",0,"yellow,on_red"], ["nodectl's",0, "blue","bold"], ["auto_restart will not be able to automate authentication to the",0,"red"],
                ["Hypergrpah",0, "blue","bold"], ["unless a passphrase is present in the configuration.",2,"red"],
                ["Please make necessary changes and try again",2,"yellow"]
            ])
            self.c.functions.get_user_keypress({
                "prompt": "press any key to return to main menu",
                "prompt_color": "magenta",
                "options": ["any_key"],
            })
            return
        
        auto_restart_desc = "nodectl has a special automated feature called 'auto_restart' that will monitor your Node's on-line status. "
        auto_restart_desc += "In the event your Node is removed from 'Ready' state, or it is identified that your Node is not properly connected "
        auto_restart_desc += "to the current cluster, nodectl will attempt to bring the Node back online. "
        auto_restart_desc += "Please be aware that there are several different ways in which your Node might lose connection.  One "
        auto_restart_desc += "specific situation: It is important to understand that if Tessellation is upgraded to a new version, "
        auto_restart_desc += "nodectl will not auto_upgrade, unless the auto_upgrade feature is enabled. Please issue a "
        auto_restart_desc += "'sudo nodectl auto_restart help' for details."
        
        auto_upgrade_desc = "nodectl has a special automated feature called 'auto_upgrade' that will monitor your Node's on-line status. "
        auto_upgrade_desc += "In the event your Node is removed from the network because of a version upgrade, this feature will attempt "
        auto_upgrade_desc += "to bring your Node back up online; by including an Tessellation upgrade, with the restart. "
        auto_upgrade_desc += "'auto_restart' must be enabled in conjunction with 'auto_upgrade'."
        auto_upgrade_desc += "Please be aware that this can be a dangerous feature, as in the (unlikely) event there are bugs presented in the new "
        auto_upgrade_desc += "releases, your Node will be upgraded regardless.  It is important to pay attention to your Node even if this feature "
        auto_upgrade_desc += "is enabled.  Please issue a 'sudo nodectl auto_upgrade help' for details."
        
        on_boot_desc = "nodectl has an automated feature called 'on_boot' that simply allow your Node to start the 'auto_restart' "
        on_boot_desc += "feature on restart ('warm' or 'cold' boot) of your VPS (virtual private server) or bare metal (physical) server "
        on_boot_desc += "housing your Node. If you choose to enable 'on_boot' be aware that in the event you need to disable 'auto_restart' "
        on_boot_desc += "in the future, for whatever purpose, it will re-engage if the system is restarted by a 'warm' or 'cold' boot."
        
        restart = "disable" if self.c.config_obj["global_auto_restart"]["auto_restart"] else "enable"
        upgrade = "disable" if self.c.config_obj["global_auto_restart"]["auto_upgrade"] else "enable"
        on_boot = "disable" if self.c.config_obj["global_auto_restart"]["on_boot"] else "enable"
        
        questions = {
            "auto_restart": {
                "question": f"  {colored('Do you want to [','cyan')}{colored(restart,'yellow',attrs=['bold'])}{colored('] auto_restart?','cyan')}",
                "description": auto_restart_desc,
                "default": "y" if restart == "disable" else "n",
                "required": False,
            },
            "auto_upgrade": {
                "question": f"  {colored('Do you want to [','cyan')}{colored(upgrade,'yellow',attrs=['bold'])}{colored('] auto_upgrade?','cyan')}",
                "description": auto_upgrade_desc,
                "default": "y" if upgrade == "disable" else "n",
                "required": False,
            },
            "on_boot": {
                "question": f"  {colored('Do you want to [','cyan')}{colored(on_boot,'yellow',attrs=['bold'])}{colored('] start on boot up?','cyan')}",
                "description": on_boot_desc,
                "default": "y" if on_boot == "disable" else "n",
                "required": False,
            },
            "alt_confirm_dict": {
                f"{restart} auto_restart": "auto_restart",
                f"{upgrade} auto_upgrade": "auto_upgrade",
                f"{on_boot} on_boot": "on_boot",
            }
        }
        
        while True:
            restart_error = False
            enable_answers = self.ask_confirm_questions({"questions": questions})
            enable_answers["auto_restart"] = enable_answers["auto_restart"].lower()
            enable_answers["auto_upgrade"] = enable_answers["auto_upgrade"].lower()
            enable_answers["on_boot"] = enable_answers["on_boot"].lower()
            
            for command in ["auto_restart","auto_upgrade","on_boot"]:
                enable_answers[command] = enable_answers[command].lower()
                if enable_answers[command] == "yes": 
                    enable_answers[command] == "y"
                elif enable_answers[command] == "no": 
                    enable_answers[command] == "n"
                elif enable_answers[command] == "no": 
                    enable_answers[command] == "n"
                if enable_answers[command] != "n" and enable_answers[command] != "y":
                    restart_error = True
                    self.c.functions.print_paragraphs([
                        [" WARNING ",0,"yellow,on_red"], ["invalid options chosen, this configuration change will not take effect.",1,"red"],
                        ["Please try again",2,"magenta"],
                    ])
                    self.c.functions.print_any_key({})
                    break
            if restart_error: break

            # auto_upgrade restrictions
            if restart == "disable" and upgrade == "disable":
                if enable_answers["auto_restart"] == "y" and enable_answers["auto_upgrade"] == "n":
                    # cannot disable auto restart if auto upgrade is enabled
                    restart_error = True

            if restart == "disable" and upgrade == "enable":
                if enable_answers["auto_restart"] == "y" and enable_answers["auto_upgrade"] == "y":
                    # cannot disable auto restart if auto upgrade is being enabled
                    restart_error = True

            if restart == "enable" and upgrade == "enable":
                if enable_answers["auto_restart"] == "n" and enable_answers["auto_upgrade"] == "y":
                    # cannot disable auto restart if auto upgrade is enabled
                    restart_error = True
                    
            # on_boot restrictions
            if restart == "disable" and on_boot == "disable":
                if enable_answers["auto_restart"] == "y" and enable_answers["on_boot"] == "n":
                    # cannot enable on boot if auto_restart is disabled
                    restart_error = True
                    
            if restart == "disable" and on_boot == "enable":
                if enable_answers["auto_restart"] == "y" and enable_answers["on_boot"] == "y":
                    # cannot disable auto restart if on_boot is being enabled
                    restart_error = True      
                                  
            if restart == "enable" and on_boot == "enable":
                if enable_answers["auto_restart"] == "n" and enable_answers["on_boot"] == "y":
                    # cannot enable on boot if auto_restart is disabled
                    restart_error = True

            if not restart_error:
                try:
                    shell = ShellHandler(self.c.config_obj,False)
                except:
                    from ..shell_handler import ShellHandler
                    shell = ShellHandler(self.c.config_obj,False)

                shell.argv = []
                shell.profile_names = self.metagraph_list
                # auto restart
                if restart == "enable" and enable_answers["auto_restart"] == "y":
                    self.c.functions.print_cmd_status({
                        "text_start": "Starting auto_restart service",
                        "status": "starting",
                        "status_color": "yellow"
                    })
                    shell.auto_restart_handler("enable")
                    self.c.functions.print_cmd_status({
                        "text_start": "Starting auto_restart service",
                        "status": "started",
                        "status_color": "green",
                        "newline": True,
                    })
                elif restart == "disable" and enable_answers["auto_restart"] == "y":
                    shell.called_command = "configurator"
                    shell.auto_restart_handler("disable",True)
                    self.c.functions.print_cmd_status({
                        "text_start": "Stopping auto_restart service",
                        "status": "stopped",
                        "status_color": "green",
                        "newline": True,
                    })
                
                # on boot
                if on_boot == "enable" and enable_answers["on_boot"] == "y":
                    self.c.functions.print_cmd_status({
                        "text_start": "Enabling auto_restart on boot",
                        "status": "enabling",
                        "status_color": "yellow",
                    })
                    system('sudo systemctl enable node_restart@"enable" > /dev/null 2>&1')
                    self.c.functions.print_cmd_status({
                        "text_start": "Enabling auto_restart on boot",
                        "status": "enabled",
                        "status_color": "green",
                        "newline": True,
                    })
                elif on_boot == "disable" and enable_answers["on_boot"] == "y":
                    self.c.functions.print_cmd_status({
                        "text_start": "Disabling auto_restart on boot",
                        "status": "disabling",
                        "status_color": "yellow",
                    })
                    system('sudo systemctl disable node_restart@"enable" > /dev/null 2>&1')
                    self.c.functions.print_cmd_status({
                        "text_start": "Disabling auto_restart on boot",
                        "status": "disabled",
                        "status_color": "green",
                        "newline": True,
                    })
                break
            self.c.functions.print_paragraphs([
                [" ERROR ",0,"yellow,on_red"], ["auto_upgrade cannot be enabled without auto_restart, please try again.",1,"red"]
            ])

        self.config_obj_apply = {"global_auto_restart":{}}
        self.config_obj_apply["global_auto_restart"]["auto_restart"] = "False" if enable_answers["auto_restart"] == "y" else "True"
        self.config_obj_apply["global_auto_restart"]["auto_upgrade"] = "False" if enable_answers["auto_upgrade"] == "y" else "True"
        self.config_obj_apply["global_auto_restart"]["on_boot"] = "False" if enable_answers["on_boot"] == "y" else "True"
        if restart == "enable":
            self.config_obj_apply["global_auto_restart"]["auto_restart"] = "True" if enable_answers["auto_restart"] == "y" else "False"
        if upgrade == "enable":
            self.config_obj_apply["global_auto_restart"]["auto_upgrade"] = "True" if enable_answers["auto_upgrade"] == "y" else "False"
        if on_boot == "enable":
            self.config_obj_apply["global_auto_restart"]["on_boot"] = "True" if enable_answers["on_boot"] == "y" else "False"
        
        if not restart_error: self.apply_vars_to_config()

        
    def edit_append_profile_global(self,s_type):
        line1 = "EDIT P12 GLOBAL" if s_type else "APPEND NEW PROFILE"
        line2 = "Private Keys" if s_type else "to configuration"
        
        self.header_title = {
            "line1": line1,
            "line2": line2,
            "show_titles": False,
            "clear": True,
            "newline": "both",
        }

        # self.migrate.keep_pass_visible = True
        if s_type == "p12":
            self.preserve_pass = True
            self.skip_prepare = True
            self.is_all_global = True
            self.request_p12_details({
                "preserved": "identified"
            })  # preserve old values for default
            self.request_p12_details({
                "ptype": "global_edit_prepare",
                "set_default": True
            })

            self.config_obj_apply["global_p12"] = self.config_obj["global_p12"]
                    
        self.apply_vars_to_config()    

        if s_type != "p12":
            self.build_service_file({
                "profiles": self.profile_name_list,
                "action": "Create",
                "rebuild": True,
            })   

    
    def delete_profile(self,profile):
        self.c.functions.print_header_title({
            "line1": f"DELETE A PROFILE",
            "line2": profile,
            "single_line": True,
            "clear": True,
            "newline": "both",
            "upper": False,
        })

        notice = [
            ["",1],
            [" WARNING! ",2,"grey,on_red"],
            ["This will",0,"red"], ["not",0,"red","bold"], ["only",0,"yellow","underline"], ["remove the profile from the configuration;",0,"red"],
            ["moreover, this will also remove all",0,"red"], ["data",0,"magenta","bold,underline"], ["from the",0,"red"],
            ["Node",0,"yellow","bold"], ["pertaining to profile",0,"red"], [profile,0,"yellow","bold,underline"],["",2],
            
            ["-",0,"magenta","bold"], ["configuration",1,"magenta"],
            ["-",0,"magenta","bold"], ["services",1,"magenta"],
            ["-",0,"magenta","bold"], ["associated bash files",1,"magenta"],
            ["-",0,"magenta","bold"], ["blockchain data (snapshots)",2,"magenta"],
            
            [" WARNING! ",0,"red,on_yellow"],["If you have any profiles linking to this profile (GL0 or ML0) you will need to use the",0,"yellow"],
            ["configurator to update the consensus linking per profile, the configurator will not update these elements for you.",2,"yellow"]
        ]

        confirm_notice = self.confirm_with_word({
            "notice": notice,
            "action": "change",
            "word": "YES",
            "profile": profile,
            "default": "n"
        })
        if not confirm_notice:
            return False    
        
        print("")
        self.c.functions.print_cmd_status({
            "text_start": "Starting deletion process",
            "newline": True,
        })
        self.handle_service(profile,"service")  # leave and stop first
        
        self.config_obj = deepcopy(self.c.config_obj)
        self.old_last_cnconfig = deepcopy(self.c.config_obj)
        del self.config_obj[profile]
        self.cleanup_service_file_msg()
        self.cleanup_service_files()
        
        for n, end_profile in enumerate(self.metagraph_list):
            if profile == end_profile:
                next_profile = self.metagraph_list[n+1]
                break
            
        self.append_remove_config_lines({
            "profile": profile,
            "start_line": f"  {profile}:\n",
            "end_line": f"  {next_profile}:\n"
        })

        self.c.functions.print_cmd_status({
            "text_start": f"Profile",
            "brackets": profile,
            "status": "deleted",
            "status_color": "red",
            "newline": True,
            "delay": 1.5,
        })
        
        
    def edit_profile_name(self, old_profile):
        self.c.functions.print_header_title({
            "line1": "CHANGE PROFILE NAME",
            "line2": old_profile,
            "clear": True,
            "show_titles": False,
            "upper": False,
        })
        
        self.c.functions.print_paragraphs([
            [" WARNING! ",0,"grey,on_red","bold"], ["This is a dangerous command and should be done with precautions.",0],
            ["It will migrate an entire profile's settings and directory structure.",0],
            ["Moreover, some",0],["metagraph",0,"blue","bold"], ["default",0,"yellow"], ["settings are reliant on identifying",0],
            ["predefined static profile names.",2],
            
            ["Please make sure you know what you are doing before continuing...",1],
            ["press ctrl+c to quit at any time",2,"yellow"],     
                   
            ["Please enter in the new profile name you would like to change to at the input.",1,"magenta"],

        ])
        
        new_profile_question = colored("  new profile: ","yellow")
        while True:
            new_profile = input(new_profile_question)
            if new_profile != "":
                break
            print("\033[F",end="\r")
                
        print("")
        
        if new_profile in self.metagraph_list:
            if new_profile == old_profile:
                self.log.logger.error(f"Attempt to change profile names that match, taking no action | new [{new_profile}] -> old [{old_profile}].")
                prompt = f"{new_profile} equals {old_profile}, nothing to do!"
            else:
                self.log.logger.error(f"Attempt to change profile name already exists for another profile in this configuration, taking no action | new [{new_profile}] -> old [{old_profile}]")
                prompt = f"{new_profile} already exists for another configured profile in your configuration."
                
            self.c.functions.print_paragraphs([
                [" ERROR ",1,"yellow,on_red"], [prompt,1,"red"],
            ])
            self.c.functions.print_any_key({})
            return False
        
        self.c.functions.print_header_title({
            "line1": f"OLD: {old_profile}",
            "line2": f"NEW: {new_profile}",
            "clear": False,
            "show_titles": False,
            "upper": False,
        })
            
        notice = [
            ["",2], [" NOTICE ",1,"blue,on_yellow","bold"], 
            ["This Node's service name will not changed.",2,"yellow"],
            ["Although this is",0],["not",0,"green","bold"],
            ["an issue and your Node will not be affected; be aware that",0], 
            ["this is being conveyed in case the Node Administrator wants to correlate the",0],
            ["service name",0,"cyan"], ["with the",0], ["profile name.  You can use the profile editor",0],
            ["in the configurator to update the service name.",1,"cyan",],
            ["service name:",0,"yellow"], [self.c.config_obj[old_profile]["service"],2,"magenta"],
            
            [" NOTICE ",1,"blue,on_yellow","bold"], 
            ["Custom defined directory structures will not be changed.",2,"yellow"],
            
            ["The Node's directory path will change to accommodate the new profile migration.",0],
            ["This is may",0],["not",0,"green","bold"],
            ["be an issue. Be aware that this is being conveyed in case the Node Administrator has configured",0],
            ["custom path locations for backups and or uploads that include the old [",0],
            [old_profile,0,"yellow"], ["] name included in the path file. If this is the case,",0],
            ["the Node Operator will have to update the custom directory locations using the configuration editor, and",0],
            ["may need to manually migrate any files from the new profile path to the custom location to preserve this",0],
            ["information and properly manage any disk usage that may be used by abandoned files.",1],
            ["backups:",0,"yellow"], [self.c.config_obj[old_profile]["directory_backups"],1,"magenta"],
            ["uploads:",0,"yellow"], [self.c.config_obj[old_profile]["directory_uploads"],2,"magenta"],
        ]
        
        confirm_notice = self.confirm_with_word({
            "notice": notice,
            "action": "change",
            "word": "YES",
            "profile": new_profile,
            "default": "n"
        })
        if not confirm_notice:
            return False

        replace_list = [
            [f"  {old_profile}:",f"  {new_profile}:\n"],
            [f"    gl0_link_profile: {old_profile}",f"    gl0_link_profile: {new_profile}\n"],
            [f"    ml0_link_profile: {old_profile}",f"    ml0_link_profile: {new_profile}\n"],
        ]
        for group in replace_list:
            self.c.functions.test_or_replace_line_in_file({
                "file_path": self.yaml_path,
                "search_line": group[0],
                "replace_line": group[1],
                "skip_backup": True,
            })

        progress = {
            "status_color": "green",
            "status": "complete",
            "newline": True,
        }
        self.c.functions.print_cmd_status({
            **progress,
            "text_start": "Remove",
            "brackets": old_profile,
            "text_end": "profile"
        })
        self.c.functions.print_cmd_status({
            **progress,
            "text_start": "Build",
            "brackets": new_profile,
            "text_end": "profile"
        })
        self.c.functions.print_cmd_status({
            **progress,
            "text_start": "Update data link dependencies",
        })

        system(f"mv {self.yaml_path} {self.config_file_path} > /dev/null 2>&1")
        
        self.c.functions.print_cmd_status({
            **progress,
            "text_start": "Migrate over config yaml",
        })
        
        self.prepare_configuration("edit_config",True)
        self.c.functions.print_cmd_status({
            **progress,
            "text_start": "Process new configuration",
        })        
        
        self.config_obj = deepcopy(self.c.config_obj) 
        self.metagraph_list[self.metagraph_list.index(old_profile)] = new_profile
                
        self.build_service_file({
            "profiles": [new_profile],
            "action": "Updating",
            "rebuild": False,
        })
        
        progress = {
            "text_start": "Handle backend manipulation",
            "brackets": new_profile,
            "status": "running"
        }
        self.c.functions.print_cmd_status(progress)
        self.log.logger.debug(f"configurator edit request - moving [{old_profile}] to [{new_profile}]")
        
        try: system(f"mv /var/tessellation/{old_profile}/ /var/tessellation/{new_profile}/ > /dev/null 2>&1")
        except:
            self.error_messages.error_code_messages({
                "error_code": "cfr-2275",
                "line_code": "not_new_install",
            })

        self.c.functions.print_cmd_status({
            **progress,
            "status": "complete",
            "newline": True,
        })  
        
        self.log.logger.info(f"Changed profile names | new [{new_profile}] -> old [{old_profile}]")
        self.c.functions.print_any_key({})
        return new_profile
               

    def edit_service_name(self, profile):
        self.manual_build_service(profile)
        self.cleanup_service_file_msg()
        self.cleanup_service_files()
        self.build_service_file({
            "profiles": [profile], 
            "action": "Create",
            "rebuild": False,
        })
        print("")
        self.c.functions.print_any_key({})
        
        
    def edit_enable_disable_profile(self, profile, task="None"):
        c_enable_disable = f"Enable {profile} [{colored('disabled','magenta',attrs=['bold'])}{colored(']','magenta')}"
        enable_disable = "enable"
        if self.c.config_obj[profile]["profile_enable"] == True:
            c_enable_disable = f"Disable {profile} [{colored('enabled','magenta',attrs=['bold'])}{colored(']','magenta')}" 
            enable_disable = "disable"
        c_enable_disable = colored(f') {c_enable_disable}','magenta')

        if task == "prepare":            
            self.c.functions.print_header_title({
                "line1": profile,
                "single_line": True,
                "newline": "both",
            })
            print(f"{colored('  1','magenta',attrs=['bold'])}{c_enable_disable}")
        else:
            defaults = {
                "profile_enable": "True" if enable_disable == "enable" else "False"
            }
            
            self.manual_append_build_apply({
                "questions": False,
                "defaults": defaults,
                "profile": profile,
            })
            
            if self.c.config_obj["global_auto_restart"]["auto_restart"] == True:
                try:
                    shell = ShellHandler(self.c.config_obj,False)
                except:
                    from ..shell_handler import ShellHandler
                    shell = ShellHandler(self.c.config_obj,False)
                shell.argv = []
                shell.profile_names = self.metagraph_list
                self.c.functions.print_cmd_status({
                    "text_start": "Restarting auto_restart service",
                    "status": "restarting",
                    "status_color": "yellow"
                })
                shell.auto_restart_handler("restart",True)
                self.c.functions.print_cmd_status({
                    "text_start": "Restarting auto_restart service",
                    "status": "restarted",
                    "status_color": "green",
                    "newline": True,
                })
                self.c.functions.print_any_key({})
                
                
    def developer_enable_disable(self):
        if self.action == "dev_mode":
            key = "developer_mode"
            start = "Developer Mode"
        if self.action == "includes_section":
            start = "Includes Section"
            key = "includes"

        self.config_obj_apply = {
            "global_elements": 
                {f"{key}": "True" if self.dev_enable_disable == "enable" else "False"}
            }
        self.apply_vars_to_config()
        
        self.c.functions.print_cmd_status({
            "text_start": start,
            "status": "enabled" if self.dev_enable_disable == "enable" else "disabled",
            "status_color": "green" if self.dev_enable_disable == "enable" else "red",
            "newline": True,
        })
        

    def perform_encryption(self,profile,encryption_obj,effp,pass3,caller):
        pass_key = "passphrase"
        first_run, write_append = False, True

        if profile != "global_p12":
            pass_key = "p12_passphrase"
            if self.c.config_obj[profile][pass_key] == "global":
                return "skip","skip"
            
        enc_pass = self.c.config_obj[profile][pass_key].strip()
        enc_pass = str(enc_pass) # required if passphrase is enclosed in quotes

        if caller != "configurator" and enc_pass == "None":
            self.error_messages.error_code_messages({
                "error_code": "cfr-3092",
                "line_code": "invalid_passphrase",
                "extra": "Must be present in configuration",
            })

        if not self.quick_install and not pass3:
            self.c.functions.print_header_title({
                "line1": "GLOBAL P12" if profile == "global_p12" else profile.upper(),
                "newline": "both",
                "single_line": True,
            })

        default_seed = ''.join(choice(ascii_letters) for _ in range(16))
        if self.quick_install or self.action == "install":
            pass3 = enc_pass
        else:
            pass_correct = False
            if not pass3:
                first_run = True
                self.c.functions.print_paragraphs([
                    ["Press enter your p12 passphrase for encryption.",2,"white","bold"],
                ])
                pass1 = getpass(f"  p12 passphrase: ")
                pass1 = self.c.p12.keyphrase_validate({
                    "profile": "global" if profile == "global_p12" else profile,
                    "passwd": pass1,
                    "operation": "encryption",
                })
                pass3 = pass1.strip()
        
        if not self.quick_install and first_run:
            print("")
            for s_status in ["deriving","redacting","forgetting","finished"]:
                self.c.functions.print_cmd_status({
                    "text_start": "Encryption",
                    "text_start": "seed phrase",
                    "brackets": s_status,
                    "status_color": "green" if s_status == "finished" else "magenta",
                    "status": "complete" if s_status == "finished" else "preparing",
                    "newline": True if s_status == "finished" else False,
                })
                sleep(1)

            print("")
            self.c.functions.print_cmd_status({
                **encryption_obj,
                "brackets": "global" if profile == "global_p12" else profile,
            })    

        try:
            hashed, enc_key = self.c.functions.get_persist_hash({"pass1": pass3, "salt2": default_seed})
            if not hashed: raise Exception("hashing issue")
            if not enc_key: raise Exception("encryption generation issue")
        except Exception as e:
            self.log.logger.critical(f"configurator --> [{e}]")
            self.error_messages.error_code_messages({
                "error_code": "cfr-3110",
                "line_code": "system_error",
                "extra": e,
            })

        enc_list, enc_de, enc_h = self.build_uuid_mangle(len(hashed))
        sleep(.8)

        enc_str = ""
        for n, i in enumerate(enc_list):
            if n < 1: enc_str += hashed[:i]
            elif n == len(enc_list): hashed[enc_list.index(i)-1:]
            else: enc_str += hashed[enc_list.index(i)-1:i]
            
        fe, fe_list = "", []
        fe_list = []
        index = 0
        for length in enc_list:
            fe_list.append(hashed[index:index + length])
            index += length
        for pi, _ in enc_de: fe += fe_list[pi]  
        enc_key = f"{profile}::{enc_key}{enc_h}"
    
        sleep(.4)
        if path.isfile(effp):
            elp = self.c.functions.test_or_replace_line_in_file({
                "file_path": effp,
                "search_line": profile,
                "replace_line": enc_key+"\n",
                "allow_dups": False,
            })[1]
            if elp > 0: # a line was replaced
                write_append = False
        if write_append:
            with open(f"{effp}","a") as f:
                f.write(enc_key+"\n")

        fe = fe.strip()

        return fe, pass3


    def passphrase_enable_disable_encryption(self,caller):
        self.log.logger.info("configurator -> encryption method envoked.")

        if self.action != "install": system("clear")

        enable = False if self.c.config_obj["global_p12"]["encryption"] else True

        if self.action == "install" and not enable:
            self.log.logger.warn("configurator -> During install or upgrade -> encryption found enabled already.")
            return
        
        efp = "/etc/security/"
        eff = "cnngsenc.conf"
        effp = f"{efp}{eff}"

        if self.quick_install:
            encryption_obj = {} 
        else:
            print("\n"*2)
            self.c.functions.print_header_title({
                "line1": f"PASSPHRASE ENCRYPTION",
                "line2": "Enable Encryption" if enable else "Disable Encryption",
                "clear": True,
                "show_titles": False,
            })

            e_action = "Building" if enable else "Removing"
            encryption_obj = {
                "text_start": f"{e_action} encryption elements",
                "status": "running",
                "status_color": "yellow",
                "newline": False,
            }

        encryption_list = self.metagraph_list
        encryption_list.insert(0,"global_p12")
        if enable:
            if self.detailed:
                self.c.functions.print_paragraphs([
                    ["",1],[" IMPORTANT ",1,"yellow,on_red"], 
                    ["Enabling encryption will encrypt your passphrase in the configuration file",0],
                    ["linked to",0], ["nodectl",0,"yellow"], ["functionality.",2],
                    ["In the unlikely event the encrypted hash stops working [for whatever reason],",0],
                    ["you can simply",0],["disable",0,"red"], ["this functionality,",0],
                    ["update/change your passphrase, and upon completion,",0],
                    ["re-enable",0,"green"], ["the encryption feature.",2],

                    ["Encryption will be turned on globally for all profiles. Each unique profile passphrase may be encrypted with a different key.",2],

                    ["For security purposes nodectl will",0,"red","bold"], ["not",0,"yellow"], 
                    ["decrypt the passphrase upon disabling the",0,"red","bold"],
                    ["encryption feature.",2,"red","bold"],

                    [" WARNING ",1,"yellow,on_red"], 
                    ["If the configuration file was manually updated, any updated encryption elements [or other] will be",0,"red","bold"],
                    ["overwritten",0,"magenta","bold"], ["causing old encryption data that may be allowing nodectl to handle previously encrypted",0,"red","bold"],
                    ["elements to stop working, to be overwritten, and removed!",1,"red","bold"],
                ])
                if not self.action == "install":
                    print("")
                    self.c.functions.confirm_action({
                        "yes_no_default": "y",
                        "return_on": "y",
                        "prompt": "Do you want to enable encryption?",
                        "exit_if":  True
                    })
                    print("")

            efp_error = False if path.exists(efp) else True
            if not efp_error: 
                try: remove(effp)  
                except:
                    self.log.logger.warn("configurator -> encryption service -> unable to remove an existing encryption key file -> this error can be safely ignored.")
            if efp_error:
                self.log.logger.error("configurator -> encryption service -> unable to find necessary file system distribution file security. Is this a Debian OS?")
                self.error_messages.error_code_messages({
                    "error_code": "cfr-3150",
                    "line_code": "system_error",
                    "extra": "invalid file system",
                })  

            pass3 = False
            for profile in encryption_list:

                for n in range(0,3):
                    fe, pass3 = self.perform_encryption(profile,encryption_obj,effp,pass3,caller)
                    if fe == "skip": break

                    sleep(.8)
                    test_p = self.c.functions.get_persist_hash({
                        "pass1": fe, 
                        "enc_data": True,
                        "profile": profile,
                        "test_only": True,
                    })
                    if test_p: break
                    else:
                        if not self.quick_install:
                            cprint("\n  please wait...","magenta")
                            self.log.logger.warn(f"configurator -> encryption service -> encryption did not complete successfully, trying again [{n+1}] of [3]")

                if fe == "skip": continue

                if test_p == pass3:
                    self.log.logger.info(f"configurator -> profile [{profile}] encryption tests passed, continuing")
                else:
                    self.log.logger.error(f"configurator -> profile [{profile}] unable to properly encrypt, aborting encryption")
                    if not self.quick_install:
                        self.c.functions.print_paragraphs([
                            [" ERROR ",0,"yellow,on_red"], ["During attempts to encrypt the passphrase and invalid SHA hash produced and nodectl was",0,"red"],
                            ["unable to be verified. The encryption operation was cancelled to avoid disabling nodectl's ability to validate the",0,"red"],
                            ["p12 file on this Node. You can try again or change your p12 passphrase. The passphrase should not contain:",1,"red"],
                            ["  - spaces",1,"yellow"],
                            ["  - $ (dollar signs)",1,"yellow"],
                            ["  - single or double quotes",1,"yellow"],
                            ["  - section signs",2,"yellow"],
                            ["sudo nodectl passwd12",2],
                        ])
                        try: remove(effp)
                        except: pass
                        self.c.functions.print_timer({
                            "seconds": 6,
                            "step": -1,
                            "phrase": "",
                            "end_phrase": "pausing",
                        })
                
                if profile == "global_p12":
                    self.config_obj_apply = {
                        **self.config_obj_apply,
                        f"{profile}": {
                            "encryption": "True",
                            "passphrase": fe,
                        }
                    } 
                else:
                    self.config_obj_apply = {
                        **self.config_obj_apply,
                        f"{profile}": {
                            "p12_passphrase": fe,
                        }
                    } 
                if not self.quick_install:
                    self.c.functions.print_cmd_status({
                        **encryption_obj,
                        "brackets": "global" if profile == "global_p12" else profile,
                        "newline": True,
                        "status": "completed",
                        "status_color": "green",
                    }) 

        else:
            if self.detailed:
                self.c.functions.print_paragraphs([
                    ["",1],[" WARNING ",0,"yellow,on_red"], 
                    ["Disabling encryption is permanent.",2],

                    ["Profile specific",0,"red"], ["non-global",0,"yellow"], ["passphrases will",0,"red"], 
                    ["NOT",0,"red","bold"], ["be restored in your Node's configuration file.",0,"red"],
                    ["Each specific p12 configurations will be reset to",0,"red"], ["None",2,"yellow","bold"],

                    [f"Please reset specific",0,"red"], ["dedicated profile",0,"yellow"], 
                    ["passphrases via the configurator to",0,"red"],
                    ["resume nodectl's ability to automate processes that require the",0,"red"],
                    ["p12",0,"yellow"], ["key store elements to function.",2,"red"],

                    ["Alternatively, you can resume using",0,"red"],
                    ["--pass <passphrase>",0], ["at the command prompt.",2,"red"],

                    ["You will be redirected automatically to reset your global p12 passphrase.",2,"green"],
                ])

            self.c.functions.confirm_action({
                "yes_no_default": "n",
                "return_on": "y",
                "prompt": "Do you want to remove encryption?",
                "exit_if": True
            })

            self.c.functions.print_paragraphs([
                ["",1], ["This is permanent...",1,"red","bold"],
            ])
            
            self.c.functions.print_cmd_status({
                **encryption_obj,
            })  

            if path.exists(effp): remove(effp)    
            sleep(.4) 

            for profile in encryption_list:
                if profile == "global_p12":
                    self.config_obj_apply = {
                        **self.config_obj_apply,
                        "global_p12": {
                            "encryption": "False",
                            "passphrase": "None",
                        }
                    } 
                elif self.c.config_obj[profile]["p12_passphrase"] != "global":
                    self.config_obj_apply = {
                        **self.config_obj_apply,
                        f"{profile}": {
                            "p12_passphrase": "None",
                        }
                    } 
                        
        self.apply_vars_to_config()
        if not self.quick_install:
            self.c.functions.print_cmd_status({
                **encryption_obj,
                "newline": True,
                "status": "completed",
                "status_color": "green",
            })  
            sleep(1)

    # =====================================================
    # OTHER
    # =====================================================

    def backup_config(self):
        print("")
        if not self.is_file_backedup:
            progress = {
                "text_start": "Backup",
                "brackets": "cn-config.yaml",
                "text_end": "if exists",
                "status": "checking",
                "status_color": "yellow",
            }
            
            try: 
                self.c.functions.set_default_variables({"skip_error",True})
                backup_dir = self.c.config_obj[self.c.functions.default_profile]["directory_backups"]
            except:
                backup_dir = self.config_path
                                
            self.c.functions.print_cmd_status(progress)
            if path.isfile(self.config_file_path):
                self.backup_file_found = True
                c_time = self.c.functions.get_date_time({"action":"datetime"})
                if not path.isdir(backup_dir):
                    makedirs(backup_dir)
                dest = f"{backup_dir}backup_cn-config_{c_time}"
                system(f"cp {self.config_file_path} {dest} > /dev/null 2>&1")
                self.c.functions.print_cmd_status({
                    **progress,
                    "status": "complete",
                    "status_color": "green",
                    "newline": True,
                })
                self.c.functions.print_paragraphs([
                    ["A previous",0], ["cn-config.yaml",0,"yellow"],
                    ["was found on the system.",2],
                    
                    ["In the event the backup directory was not found, a backup was created in the existing directory. The location is shown below.",1],
                    [dest,2,"blue","bold"]
                ])
            else:
                self.c.functions.print_cmd_status({
                    **progress,
                    "status": "skipped",
                    "status_color": "red",
                    "newline": True,
                })
                print(colored("  existing config not found","red"))
                
            if self.confirmed_backup:
                sleep(1)
            else:
                self.c.functions.print_any_key({})

        self.is_file_backedup = True       

    
    def migrate_directories(self,profile):
        dir_list = ["directory_uploads","directory_backups"]
        values = []
        
        migration_dirs = {dir: {"old_name": self.c.config_obj[profile][dir], "changed": False} for dir in dir_list}
        self.manual_build_dirs(profile)
        values = [self.c.config_obj[profile][key] for key in dir_list if key in self.c.config_obj[profile]]
         
        for c_dir in dir_list:
            if self.config_obj_apply[profile][c_dir] != migration_dirs[c_dir]["old_name"]:
                migration_dirs[c_dir] = {
                    **migration_dirs[c_dir],
                    "new_name": self.config_obj_apply[profile][c_dir],
                    "changed": True
                }
                
        migration_dirs["profile"] = profile
                
        def file_dir_error(directory, new_path):
            self.c.functions.print_clear_line()
            self.c.functions.print_paragraphs([
                ["An error occurred attempting to automate the creation of [",-1,"red"],[f"{new_path}",-1,"yellow","bold"],
                ["]",-1,"red"],[f". In the event that you are attempting to point your Node's {directory} towards",0,"red"],
                ["an external storage device, nodectl will continue the configuration change without migrating",0,"red"],
                [f"the {directory} to the new user defined location.",0,"red"],["nodectl will leave this up to the Node Operator.",2],
            ])
                         
        def check_for_default(directory, new_path, old_path):
            path_list = [new_path,old_path]; updated_path_list = []
            for c_path in path_list:
                if c_path == "default":
                    updated_path_list.append(f'/var/tessellation/{directory}/')
                else:
                    updated_path_list.append(c_path) 
                        
            return updated_path_list
                           
        profile = migration_dirs.pop("profile")   
        for directory, values in migration_dirs.items():
            directory_name = directory.replace("directory_","")
            status = "skipped"
            status_color = "yellow"
            
            if values["changed"]:
                new_path = values["new_name"]
                old_path = values["old_name"]
                
                new_path, old_path = check_for_default(directory_name, new_path, old_path)

                if new_path != "disable" or new_path != old_path:
                    do_migration = True
                    
                    progress = {
                        "text_start": "Migrating directory",
                        "brackets": directory_name,
                        "text_end": "location",
                        "status": "migrating",
                        "status_color": "magenta",
                        "delay": .8,
                    }                    
                    self.c.functions.print_cmd_status(progress)
                            
                    if not path.exists(new_path):
                        try:
                            makedirs(new_path)
                        except Exception as e:
                            self.log.logger.error(f"unable to create new [{new_path}] directory from configurator - migration issue | error [{e}]")
                            file_dir_error(directory, new_path)
                            do_migration = False

                    if do_migration:
                        if not path.exists(old_path) and old_path != "disable":
                            self.log.logger.error(f"unable to find [old] directory from configurator - unable to migrate. | old path not found [{old_path}]")
                            file_dir_error(directory, new_path)
                            do_migration = False
                        elif old_path != "disable":
                            old_path = f"{old_path}/" if old_path[-1] != "/" else old_path
                            new_path = f"{new_path}/" if new_path[-1] != "/" else new_path
                            
                        if old_path != new_path:
                            with ThreadPoolExecutor() as executor:
                                self.c.functions.event = True
                                _ = executor.submit(self.c.functions.print_spinner,{
                                    "msg": "migrating files please wait ",
                                    "color": "magenta",
                                    "newline": "both"
                                    })
                                cmd = f"rsync -a {old_path} {new_path} > /dev/null 2>&1"
                                system(cmd)
                                self.c.functions.event = False
                                clean_up = {
                                    "text_start": "Cleaning up directories",
                                    "brackets": directory_name,
                                }
                                self.c.functions.print_cmd_status({
                                    "status": "running",
                                    "status_color": "yellow",
                                    "newline": True,
                                    **clean_up,
                                })
                                confirm = self.c.functions.confirm_action({
                                    "yes_no_default": "n",
                                    "return_on": "y",
                                    "prompt": "Do you want to remove the old directory?",
                                    "exit_if": False
                                })
                                if confirm:                                
                                    system(f"rm -rf {old_path} > /dev/null 2>&1")
                                    self.c.functions.print_cmd_status({
                                        **clean_up,
                                        "status": "complete",
                                        "status_color": "green",
                                        "newline": True,
                                    })
                                else:
                                    self.c.functions.print_cmd_status({
                                        **clean_up,
                                        "status": "skipped",
                                        "status_color": "yellow",
                                    })
                            status = "complete"
                            status_color = "green"
                                    
                self.c.functions.print_cmd_status({
                    **progress,
                    "status": status,
                    "status_color": status_color,
                    "newline": True
                })
                
        sleep(1) # allow Node Operator to see output
        self.apply_vars_to_config() 
            

    def print_old_file_warning(self,stype):
        if not self.old_last_cnconfig:
            if self.detailed:
                self.c.functions.print_paragraphs([
                    [" WARNING ",0,"red,on_yellow"],[":",0,"red"],
                    ["nodectl's configurator could not find an old configuration.",0,"yellow"],
                    [f"This is not an issue; however, in the event that old configuration {stype} were configured",0,"yellow"],
                    ["on this Node, the configurator will not be able to clean them up; instead, you should",0,"yellow"],
                    [f"review your Node's directory structure for abandoned {stype}.",2,"yellow"],
                    ["Profile Directories Found",2,"blue","bold"]
                ])
                if stype == "profiles": system("sudo tree /var/tessellation/ -I 'data|logs|nodectl|backups|uploads|*.jar|*seedlist'")
            return True
        return False
                
                
    def cleanup_old_profiles(self):
        cleanup = False
        clean_up_old_list = []
        self.log.logger.info("configurator is verifying old profile cleanup.")
        
        self.c.functions.print_header_title({
            "line1": "CLEAN UP OLD PROFILES",
            "single_line": True,
            "newline": "both"
        })

        if self.print_old_file_warning("profiles"): return
                
        for old_profile in self.old_last_cnconfig.keys():
            if old_profile not in self.config_obj.keys():
                cleanup = True
                clean_up_old_list.append(old_profile)
                self.log.logger.warn(f"configuration found abandoned profile [{old_profile}]")
        
        for old_profile in clean_up_old_list:
            self.c.functions.print_cmd_status({
                "text_start": "Abandoned",
                "brackets": old_profile,
                "text_end": "profile",
                "status": "found",
                "color": "red",
                "newline": True,
            })
            
        if cleanup:
            self.c.functions.print_paragraphs([
                ["It is recommended to clean up old profiles to:",1,"magenta"],
                ["  - Avoid conflicts",1],
                ["  - Avoid undesired Node behavior",1],
                ["  - Free up disk",2],
            ])
            self.clean_profiles = self.c.functions.confirm_action({
                "yes_no_default": "y",
                "return_on": "y",
                "prompt": "Remove old profiles?",
                "exit_if": False
            })   
            if not self.clean_profiles: self.skip_clean_profiles_manual = True 
            if self.clean_profiles:
                for profile in clean_up_old_list:
                    system(f"sudo rm -rf /var/tessellation/{profile} > /dev/null 2>&1")
                    self.log.logger.info(f"configuration removed abandoned profile [{profile}]")      
                    self.c.functions.print_cmd_status({
                        "text_start": "Removed",
                        "brackets": profile,
                        "text_end": "profile",
                        "status": "complete",
                        "color": "green",
                        "newline": True,
                    })
        else:  
            self.c.functions.print_paragraphs([
                ["No old profiles were identified.",1,"green","bold"],
            ])
                

    def cleanup_service_file_msg(self):
        self.c.functions.print_cmd_status({
            "text_start": "Cleaning up old service files",
            "status": "running",
            "new_line": True,
        })  
        print("")
        
        
    def cleanup_service_files(self,delete=True):
        cleanup, print_abandoned = False, False
        clean_up_old_list = []
        self.log.logger.info("configurator is verifying old service file cleanup.")
        
        self.c.functions.print_header_title({
            "line1": "CLEAN UP OLD SERVICE FILES",
            "single_line": True,
            "newline": "both"
        })
        
        if self.print_old_file_warning("services"): return
        
        if not self.old_last_cnconfig:
            self.c.functions.print_cmd_status({
                "text_start": "skipping cleanup",
                "newline": True,
            })
            return
        
        for old_profile in self.old_last_cnconfig.keys():
            if old_profile not in self.config_obj.keys():
                if "global" not in old_profile:
                    cleanup = True
                    if self.action == "new" or old_profile == self.profile_to_edit:
                        clean_up_old_list.append(old_profile)
                        self.log.logger.warn(f'configuration found abandoned service file for [{old_profile}] name [{self.old_last_cnconfig[old_profile]["service"]}]')
        
        clean_up_old_list2 = copy(clean_up_old_list)

        for old_profile in clean_up_old_list2:
            try: # new config will fall into exception
                if self.c.config_obj[old_profile]["service"] == self.old_last_cnconfig[old_profile]["service"] and not delete:
                    clean_up_old_list.pop(clean_up_old_list.index(old_profile))
                else: print_abandoned = True
            except Exception as e:
                self.log.logger.error(f"configurator --> cleaning up services found new configuration - skipping [{e}]")
                print_abandoned = True
                
            if print_abandoned:
                self.c.functions.print_cmd_status({
                    "text_start": "Abandoned",
                    "brackets": self.old_last_cnconfig[old_profile]["service"],
                    "text_end": "service",
                    "status": "found",
                    "color": "red",
                    "newline": True,
                })
            print_abandoned = False
                    
        if cleanup and len(clean_up_old_list) > 0:
            self.c.functions.print_paragraphs([
                ["",1],
                ["It is recommended to clean up old services files to:",1,"magenta"],
                ["  - Avoid conflicts",1],
                ["  - Avoid undesired Node behavior",1],
                ["  - Proper organization",1],
                ["  - Free up disk",2],
            ])
            user_confirm = self.c.functions.confirm_action({
                "yes_no_default": "y",
                "return_on": "y",
                "prompt": "Remove old service files?",
                "exit_if": False
            })    
            if user_confirm:
                for profile in clean_up_old_list:
                    service = self.old_last_cnconfig[profile]["service"]
                    service_name = f"cnng-{service}.service"
                    system(f"sudo rm -f /etc/systemd/system/{service_name} > /dev/null 2>&1")
                    self.log.logger.info(f"configuration removed abandoned service file [{service_name}]")      
                    self.c.functions.print_cmd_status({
                        "text_start": "Removed",
                        "brackets": service,
                        "text_end": "service file",
                        "status": "complete",
                        "color": "green",
                        "newline": True,
                    })
        else:  
            self.c.functions.print_paragraphs([
                ["No old service files were identified.",1,"green","bold"],
            ])
                    
                        
    def cleanup_create_snapshot_dirs(self):
        self.log.logger.info("configurator is verifying snapshot data directory existence and contents.")
                    
        # this will look at the new configuration and if it sees that a config
        # with the same name (or the same config) has data snapshots, it will
        # offer to remove them.
        
        self.c.functions.print_header_title({
            "line1": "MANAGE OLD SNAPSHOTS",
            "single_line": True,
            "newline": "both"
        })        
        
        try:
            old_metagraph_list = self.c.functions.clear_global_profiles(self.old_last_cnconfig)
        except Exception as e:
            self.error_messages.error_code_messages({
                "error_code": "cfr-3215",
                "line_code": "config_error",
                "extra": "configurator",
                "extra2": e,
            })
           
        for profile in old_metagraph_list:
            found_snap = False
            if self.old_last_cnconfig[profile]["layer"] < 1:
                found_snap_list = [
                    f"/var/tessellation/{profile}/data/snapshot",
                    f"/var/tessellation/{profile}/data/incremental_snapshot",
                    f"/var/tessellation/{profile}/data/incremental_snapshot_tmp",
                ]
                
                for lookup_path in found_snap_list:
                    if path.isdir(lookup_path) and listdir(lookup_path):
                        self.log.logger.warn("configurator found snapshots during creation of a new configuration.")
                        found_snap = True
                
                    if found_snap:
                        found_snap = False
                        lookup_path_abbrv = lookup_path.split("/")[-1]
                        self.log.logger.info("configurator cleaning up old snapshots")
                        self.c.functions.print_paragraphs([
                            ["",1], ["An existing",0], ["snapshot",0,"cyan","bold"],
                            ["directory structure exists",1], 
                            ["profile:",0], [profile,1,"yellow"],
                            ["snapshot dir:",0], [lookup_path_abbrv,1,"yellow"],
                            [f"Existing old {lookup_path_abbrv} may cause unexpected errors and conflicts with new clusters, nodectl will remove snapshot contents from this directory",2,"red","bold"],
                        ])
                        user_confirm = self.c.functions.confirm_action({
                            "yes_no_default": "y",
                            "return_on": "y",
                            "prompt": "Remove snapshot contents?",
                            "exit_if": False
                        })   
                        if user_confirm:  
                            progress = {
                                "text_start": "Cleaning",
                                "brackets": profile,
                                "text_end": lookup_path_abbrv,
                                "status": "running",
                                "status_color": "yellow",
                            }         
                            self.c.functions.print_cmd_status({
                                **progress
                            })
                            system(f"sudo rm -rf {lookup_path} > /dev/null 2>&1")
                            sleep(1)
                            self.c.functions.print_cmd_status({
                                **progress,
                                "status": "complete",
                                "status_color": "green",
                                "newline": True,
                            })  
                            sleep(1.5) # allow Node Operator to see results
                        else:
                            self.log.logger.critical("during build of a new configuration, snapshots may have been found and Node Operator declined to remove, unexpected issues by arise.") 


        for profile in self.metagraph_list:
            progress = {
                "text_start": "Building new profile directories",
                "brackets": profile,
                "status": "running",
                "status_color": "yellow",
            }         
            self.c.functions.print_cmd_status(progress)
            status, color = "exists", "yellow"
            if not path.isdir(f"/var/tessellation/{profile}/"):
                status, color = "complete","green"
                makedirs(f"/var/tessellation/{profile}/")        
            self.c.functions.print_cmd_status({
                **progress,
                "status": status,
                "status_color": color,
                "newline": True,
            })  
        
                
    def tcp_change_preparation(self,profile):
        if self.detailed:
            self.c.functions.print_paragraphs([
                ["",1], ["In order to complete this edit request, the services",0],
                ["related to Node profile",0,"cyan"], [profile,0,"yellow","bold"],
                ["must be stopped.",2],
            ])
        else:
            # only ask if advanced (detailed) mode is on
            stop = self.c.functions.confirm_action({
                "yes_no_default": "y",
                "return_on": "y",
                "prompt": "Do you want to stop services before continuing?",
                "exit_if": False
            })      
            if not stop:
                stop = self.c.functions.confirm_action({
                    "yes_no_default": "y",
                    "return_on": "y",
                    "prompt": "Are you sure you want to continue without stopping?",
                    "exit_if": True
                })   
        self.handle_service(profile,profile)


    def build_uuid_mangle(self,size,max_value=15):
        iuuid = self.c.functions.get_uuid().replace("-","")
        hex_value = bytes.fromhex(iuuid)
        integer_value = int.from_bytes(hex_value, byteorder='big')
        digit_string = str(integer_value)
        iuuid_int_list = []
        current_value = ""

        for digit in digit_string:
            current_value += digit
            current_value_int = int(current_value)
            if current_value_int > max_value:
                current_value = ""
                continue
            if 4 < current_value_int < max_value+1:
                if sum(iuuid_int_list)+current_value_int <= size:
                    iuuid_int_list.append(current_value_int)
                else:
                    while True:
                        last_number = size - (sum(iuuid_int_list)+current_value_int)
                        if last_number == 0: 
                            if sum(iuuid_int_list) < size:
                                iuuid_int_list.append(size - sum(iuuid_int_list))
                                break
                        if last_number < 0:
                            last_number = iuuid_int_list[-1]+last_number
                        iuuid_int_list[-1] = last_number
                        if iuuid_int_list[-1] < 0:
                            iuuid_int_list.pop()
                    break
                current_value = ""  
        
        if sum(iuuid_int_list) < size:
            remainder = size - sum(iuuid_int_list)
            while remainder > max_value:
                pull = random.randint(10,max_value)
                iuuid_int_list.append(pull)
                remainder -= pull
            if remainder > 0:
                iuuid_int_list.append(remainder)

            iuuid_int_list.append(size - sum(iuuid_int_list))

        while True:
            if len(iuuid_int_list) > max_value:
                ct1 = iuuid_int_list.pop()
                ct2 = iuuid_int_list.pop()
                if ct1+ct2 > max_value:
                    iuuid_int_list.append(ct1)
                    for ct3 in iuuid_int_list:
                        if ct3+ct2 < max_value-1:
                            iuuid_int_list.append(ct3+ct2)
                        else:
                            madd = min(max_value - x for x in iuuid_int_list)
                            iuuid_int_list = [x + min(ct2, madd) for x in iuuid_int_list]
                            break
                else:
                    iuuid_int_list.append(ct1+ct2)
            else:
                break
      
        iuuid_int_list2 = copy(iuuid_int_list)
        iuuid_int_list2 = list(enumerate(iuuid_int_list2))
        random.shuffle(iuuid_int_list2)
        iuuid_int_list3 = ":" + ''.join('{:X}{:X}'.format(x, y) for x, y in iuuid_int_list2)

        return iuuid_int_list,iuuid_int_list2, iuuid_int_list3


    def print_error(self):
        self.c.functions.print_paragraphs([
            ["",1], [" ERROR ",0,"grey,on_red","bold"],
            ["During the configuration editing session",1,"red"],
            ["[",0,"red"], [self.called_option,0,"yellow","bold"], ["] an incorrect input was detected",2,"red"],
        ])
        if self.error_hint:
            if self.error_hint == "dir":
                self.c.functions.print_paragraphs([
                    [" HINT ",0,"grey,on_yellow","bold"], ["If",0,"cyan","bold"], ["attempting to change directory structure for any elements,",0],
                    ["the directory structure must exist already.",2],
                ])
            if self.error_hint == "link":
                self.c.functions.print_paragraphs([
                    [" HINT ",0,"grey,on_yellow","bold"], ["If",0,"cyan","bold"], ["attempting to change or add a link key,",0],
                    ["please make sure it is a valid 128bit hexadecimal value.",1],
                    [" HINT ",0,"grey,on_yellow","bold"], ["If",0,"cyan","bold"], ["attempting to change or add a link host,",0],
                    ["please make sure it is a valid FQDN (Full Qualified Domain Name) or decimal period delineated value.",2],
                ])
            self.error_hint = False # reset
        self.c.functions.print_paragraphs([
            ["Please review the nodectl logs and/or Node operator notes and try again",2],
            
            ["You can attempt to restore your",0,"magenta"], ["cn-config.yaml",0,"yellow","bold"], ["from backups.",1,"magenta"],
            ["You can also attempt to retry your entries at the main menu",2,"magenta"], 
        ])
        
        if not self.is_new_config:
            self.c.functions.print_any_key({"prompt":"Press any key to continue"})
            self.edit_profile_sections("RETRY")
        else:
            exit("  invalid input detected")
        

    def print_quit_option(self):
        self.c.functions.print_paragraphs([
            [f"Press the ctrl+c keys to quit any time",1,"yellow"],
        ]) 


    def validate_config(self):
        self.c.functions.print_cmd_status({
            "text_start": "Basic validation on config",
            "status": "complete" if self.c.configurator_verified else "failed",
            "dotted_animated": True,
            "status_color": "green" if self.c.configurator_verified else "red",
            "newline": True,
        })
                    
        if not self.c.configurator_verified:
            self.log.logger.error(self.edit_error_msg)
            self.print_error()   
        
                  
    def handle_service(self,profile,s_type):
        # user will be notified to do a full restart at the of the process
        # to return to the network instead of doing it here.  This will ensure
        # all updates are enabled/activated/updated.
        
        if not self.node_service: self.prepare_node_service_obj()
        self.node_service.config_obj = deepcopy(self.config_obj if len(self.config_obj)>0 else self.c.config_obj)

        self.c.functions.profile_names = self.metagraph_list
        self.c.functions.get_service_status()
        service = self.c.config_obj[profile]["service"]
        self.node_service.profile = profile
        
        actions = ["leave","stop"]
        for s_action in actions:
            if self.c.config_obj["global_elements"]["node_service_status"][profile] == "inactive (dead)":
                break
            self.c.functions.print_cmd_status({            
                "text_start": "Updating Service",
                "brackets": f"{service} => {s_action}",
                "text_end": s_type,
                "status": "stopping",
                "status_color": "yellow",
                "delay": .8
            })
            self.node_service.change_service_state({
                "profile": profile,
                "action": s_action,
                "cli_flag": True,
                "service_name": f"cnng-{self.c.config_obj[profile]['service']}",
                "caller": "configurator"
            })
            if s_action == "leave":
                self.c.functions.print_timer({
                    "seconds": 40,
                    "phrase": "Gracefully",
                    "step": -1,
                    "end_phrase": "leaving cluster"
                })
                    
        self.c.functions.print_cmd_status({
            "text_start": "Updating Service",
            "brackets": f"{service} => {s_action}",
            "text_end": s_type,
            "status": "complete",
            "status_color": "green",
            "newline": True
        })  


    def ask_review_config(self):
        user_confirm = self.c.functions.confirm_action({
            "yes_no_default": "y",
            "return_on": "y",
            "prompt": "Review the created configuration?",
            "exit_if": False
        })   
        if user_confirm:           
            self.c.view_yaml_config("migrate")     
            

    def quit_configurator(self,requested=True):
        self.move_config_backups()
        if path.isfile(self.yaml_path): system(f"rm -f {self.yaml_path} > /dev/null 2>&1")
        if requested:
            cprint("  Configurator exited upon Node Operator request","green")
        exit(0)  
        

    def append_remove_config_lines(self, command_obj):
        # this method will default to list_of_lines if not False
        # if list_of_line is provided, the appending of the list
        # will happen after the start_line specifier
        
        # start and end will remove

        profile = command_obj.get("profile",self.profile_to_edit)
        append = command_obj.get("append",False)
        remove_yaml = command_obj.get("remove_yaml",False)
        list_of_lines = command_obj.get("list_of_lines", False)
        exclude_string = command_obj.get("exclude_string",False)
        start_line = command_obj.get("start_line",False) # start_line will be removed
        end_line = command_obj.get("end_line",False) # end line will not be removed 
        
        def look_for_update(line,list_of_lines):
            line = line.split(":")[0]
            for test_line in list_of_lines:
                test_line = test_line.split(":")[0]
                if line == test_line:
                    return True
            return False
                
        update, check_for_update = False, False
        do_write = False if append else True
        
        f = open(self.config_file_path)
        with open(self.yaml_path,"w") as temp_file:
            config_lines = list(f)
            for line in config_lines:
                if not list_of_lines:
                    if line == start_line: 
                        do_write = False
                    if line == end_line: do_write = True
                    if do_write: temp_file.write(line)
                elif append:
                    if profile in line and not exclude_string: do_write = True; check_for_update = True
                    if profile in line and exclude_string not in line: do_write = True; check_for_update = True
                    if check_for_update: update = look_for_update(line,list_of_lines)
                    if not update: temp_file.write(line)
                    if line == start_line and do_write:
                        for append_line in list_of_lines:
                            temp_file.write(append_line)
                        do_write = False
                    if line == end_line: check_for_update = False
                else: # remove
                    if profile in line and not exclude_string: check_for_update = True
                    if profile in line and exclude_string not in line: check_for_update = True
                    if check_for_update:
                        for append_line in list_of_lines:
                            if line == append_line: 
                                do_write = False
                                break
                    if do_write: temp_file.write(line)
                    do_write = True
                    if line == end_line: check_for_update = False
                            
        f.close()
        system(f"sudo cp {self.yaml_path} {self.config_file_path} > /dev/null 2>&1")
        if remove_yaml: system(f"sudo rm -f {self.yaml_path} > /dev/null 2>&1")
        if list_of_lines:
            self.c.functions.print_cmd_status({
                "text_start": f"Configuration changes {'appended' if append else 'removed'}",
                "status": "successfully",
                "status_color": "green",
                "newline": True,
                "delay": 1.5,
            })


    def confirm_with_word(self,command_obj):
        notice = command_obj.get("notice",False)
        word = command_obj.get("word")
        action = command_obj.get("action")
        profile = command_obj.get("profile")
        default = command_obj.get("default","n")  # "y" or "n"
        
        confirm_str = f"{colored(f'  Confirm {action} by entering exactly [','cyan')} {colored(f'YES-{profile}','green')} {colored(']','cyan')}: "
        confirm = input(confirm_str)
        
        def word_any_key(prompt):
            print("")
            self.c.functions.get_user_keypress({
                "prompt": prompt,
                "prompt_color": "red",
                "options": ["any_key"],
            })      
                  
        if f"{word}-{profile}" == confirm:
            if self.detailed:
                self.c.functions.print_paragraphs(notice)

            if notice:
                confirm_notice = self.c.functions.confirm_action({
                    "yes_no_default": default,
                    "return_on": "y",
                    "prompt": "Continue?",
                    "exit_if": False
                })
                if not confirm_notice:
                    word_any_key("Action cancelled by Node Operator, press any key")
                    return False    
                
            return True
        
        word_any_key("Confirmation phrase did not match, cancelling operation, press any key")
        return False
    
                         
    def move_config_backups(self):
        # move any backup configs out of the config dir and into the backup dir
        backup_dir = "empty"
        
        try:
            for profile in self.metagraph_list: # grab first available
                backup_dir = self.c.config_obj[profile]["directory_backups"]
                break
        except: pass

        if backup_dir == "default": backup_dir = "/var/tessellation/backups/"  
                  
        if backup_dir == "empty":
            self.log.logger.warn("backup migration skipped.")
            if self.detailed:
                self.c.functions.print_paragraphs([
                    ["",1], ["While attempting to migrate backups from a temporary location the Configurator was not able",0,"red"],
                    ["to determine a properly configured backup directory location.",2,"red"],
                    ["Configuration backups not moved to proper backup directory due to cancellation request.",1,"red"],
                    ["location retained:",0,"red"], [f"{self.config_path}",2,"yellow","bold"],
                    ["Configurations may contain sensitive information, please handle removal manually.",1,"magenta"]
                ])
                self.c.functions.print_any_key({})
        else:
            system(f"mv {self.config_path}backup_cn-config_* {backup_dir} > /dev/null 2>&1")
            self.log.logger.info("configurator migrated all [cn-config.yaml] backups to first known backup directory")
    
                          
if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")
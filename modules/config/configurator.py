from concurrent.futures import ThreadPoolExecutor

from termcolor import colored, cprint
from os import system, path, environ, makedirs, listdir
from sys import exit
from getpass import getpass, getuser
from types import SimpleNamespace
from copy import deepcopy, copy
from secrets import compare_digest
from time import sleep
from requests import get

from .migration import Migration
from .config import Configuration
from ..troubleshoot.logger import Logging
from ..node_service import Node
from ..troubleshoot.errors import Error_codes
from ..shell_handler import ShellHandler
from ..troubleshoot.errors import Error_codes

class Configurator():
    
    def __init__(self,argv_list):
        self.log = Logging()
        self.error_messages = Error_codes()
        self.log.logger.info("configurator request initialized")

        self.debug = False
                        
        self.config_path = "/var/tessellation/nodectl/"
        self.config_file = "cn-config.yaml"
        self.yaml_path = "/var/tmp/cnng-new-temp-config.yaml"
        self.profile_to_edit = None
        self.config_obj = {}
        self.detailed = False if "-a" in argv_list else "init"
        self.keep_pass_visible = True
        self.action = False
        self.is_all_global = False
        self.profile_details = False
        self.preserve_pass = False
        self.upgrade_needed = False
        self.restart_needed = True
        self.is_new_config = False
        self.skip_convert = False  # self.convert_config_obj()
        self.skip_prepare = False
        self.is_file_backedup = False
        self.backup_file_found = False
        self.edit_error_msg = ""
        
        self.p12_items = [
            "nodeadmin", "key_location", "key_name", "key_alias", "passphrase"
        ]
        self.profile_name_list = [] 
        self.predefined_configuration = {}
        
        if "help" in argv_list:
            self.prepare_configuration("edit_config")
            self.show_help()
        elif "-ep" in argv_list:
            self.action = "edit_profile"
        elif "-e" in argv_list:
            self.action = "edit"
        elif "-n" in argv_list:
            self.action = "new"

        self.prepare_configuration("new_config")
        self.setup()
        

    def prepare_configuration(self,action,implement=False):
        if action == "migrator":
            self.migrate = Migration({
            "config_obj": self.c.functions.config_obj,
            "caller": "configurator"
            })
            return
        
        try:
            self.old_last_cnconfig = deepcopy(self.c.config_obj)
        except:
            self.old_last_cnconfig = False
    
        self.c = Configuration({
            "action": action,
            "implement": implement,
            "skip_report": True,
            "argv_list": [action],
        })
            
        if not self.profile_details:
            self.profile_details = {}
        
        self.c.config_obj["global_elements"] = {"caller":"config"}
        self.node_service = Node({
            "config_obj": self.c.config_obj
        },False) 

        self.node_service.functions.pull_profile({"req":"profile_names"})
        self.c.functions.pull_profile({"req":"profile_names"})
                
        self.wrapper = self.c.functions.print_paragraphs("wrapper_only")
        
        if action == "edit_config":
            self.config_obj_apply = {}
            if path.isfile("/var/tessellation/nodectl/cn-config.yaml"):
                system(f"sudo cp /var/tessellation/nodectl/cn-config.yaml {self.yaml_path} > /dev/null 2>&1")
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
                if self.detailed == "init":
                    paragraphs = [
                        [intro2,2],
                        ["nodectl",0,"blue","bold"], [intro3,0],
                        ["Node",0,"green","underline"], ["via",0], 
                        ["nodectl",0,"blue","bold"], [".",-1],["",2],
                    
                        ["Detailed Mode ",0,"grey,on_yellow","bold,underline"],["will walk you through all steps/questions; with detailed explanations of each element of the configuration.",2],
                        ["Advanced Mode ",0,"grey,on_yellow","bold,underline"],["will be non-verbose, with no walk through explanations, only necessary questions.",2],
                        
                        ["The configuration tool does only a limited amount",0,"red","bold"],
                        ["of data type or value verification. After the configuration tool creates a new configuration or edits an existing configuration, it will attempt",0,"red","bold"],
                        ["to verify the end resulting configuration.",2,"red","bold"],  

                        ["You can also choose the",0], ["-a",0,"yellow","bold"], ["option at the command line to enter advanced mode directly.",2],
                    ]

                    self.c.functions.print_paragraphs(paragraphs)
                    
                    adv_mode = False
                    if not self.debug:
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
            
            if (self.action == "edit" or self.action == "help" or self.action == "edit_profile") and option != "reset":
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
                self.is_new_config = self.skip_convert = True
                self.new_config()
            elif option.lower() == "e":
                self.is_new_config = self.skip_convert = False
                self.edit_config()
                
            option = "reset"
    
        
    def new_config(self):
        self.restart_needed = False
        self.action = "new"
        self.c.functions.print_header_title({
            "line1": "NODECTL",
            "line2": "create new configuration",
            "clear": True,
        })  
        
        if self.detailed:
            self.c.functions.print_paragraphs([
                ["nodectl",0,"blue","bold"], ["can build a configuration for you based on",0], ["predefined",0,"blue","bold"],
                ["profiles. These profiles are setup by the Metagraph Administrators (or Layer0) companies that plan to ride on the Hypergraph.",2],

                ["Before continuing, please make sure you have the following checklist completed, to save time.",2,"yellow"],
                
                ["You should have obtained this information during the installation of your",0], ["Node",0,"blue","bold"],
                ["originally.",2],
                
                ["  - p12 file name",1,"magenta"],
                ["  - p12 file location",1,"magenta"],
                ["  - p12 passphrase",1,"magenta"],
                ["  - p12 wallet alias",2,"magenta"],
                
                ["Warning!",0,"red","bold"],["Invalid entries will either be rejected at runtime or flagged as invalid by",0], 
                ["nodectl",0,"blue","bold"], ["before runtime.",0], ["nodectl",0,"blue","bold"], ["does not validate entries during the configuration entry process.",2]
            ] )

        self.build_config_obj()
        self.get_predefined_configs()
        self.handle_global_p12()
        self.request_p12_details({})
        self.config_obj_apply = {}      
          
        # debug
        self.c.functions.print_json_debug(self.config_obj,False)
        
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
        self.cleanup_service_files()
        self.cleanup_create_snapshot_dirs() 
        
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
        })  

        if self.detailed:        
            self.c.functions.print_paragraphs([
                ["Please choose the",0], ["profile",0,"blue","bold"], ["below that matches the configuration you are seeking to build.",2],
                ["If not found, please use the",0], ["manual",0,"yellow","bold"], ["setup and consult the Constellation Network Doc Hub for details.",2],
                ["You can also put in a request to have your Metagraph's configuration added, by contacting a Constellation Network representative.",2],
            ])

        self.c.functions.print_header_title({
            "line1": "BUILD NEW CONFIGURATION",
            "single_line": True,
            "newline": "both"
        })
        
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
            "retrieve":"chosen_profile",
            "return_where": "Previous"
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
        
        # self.has_existing_p12 = self.c.functions.confirm_action({
        #     "yes_no_default": "n",
        #     "return_on": "y",
        #     "prompt": "Are you migrating an existing p12 private key to this Node?",
        #     "exit_if": False,
        # })

        # self.predefined_configuration = predefined_configs[option]
        # del predefined_configs
                
        # self.build_profile()
        # self.c.functions.print_cmd_status({
        #     **progress,
        #     "status": "complete",
        #     "newline": True
        # })
        
        # if not self.is_all_global:
        #     for n in range(0,len(option)+1):
        #         print("")
        #         if self.detailed:
        #             paragraph = [
        #                 ["During the configuration build, it was requested [selected] to not set all the p12 private information to all profiles.",2,"green"],
                        
        #             ]
        #             self.c.functions.print_paragraphs(paragraph)
                    
        #         if int(option) < 3: # dag
        #             non_global = self.c.functions.confirm_action({
        #                 "prompt": f"Update dedicated p12 on profile dag-l{n}?",
        #                 "yes_no_default": "n",
        #                 "return_on": "y",
        #                 "exit_if": False
        #             })
        #             if non_global:
        #                 self.preserve_pass = False
        #                 self.handle_global_p12(f"dag-l{n}")
                        
        # return True

    
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
            if get_existing_global and self.backup_file_found and not self.preserve_pass:
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
                    self.prepare_configuration(f"new_config_init")
                self.config_obj["global_p12"] = self.c.config_obj["global_p12"]
                if self.c.error_found:
                    self.log.logger.critical("Attempting to pull existing p12 information for the configuration file failed.  Valid inputs did not exist.")
                    self.log.logger.error(f"configurator was unable to retrieve p12 detail information during a configuration [{self.action}]")
                    self.print_error("Retrieving p12 details")
                self.prepare_configuration("new_config")
                self.c.functions.print_cmd_status({
                    "text_start": f"Existing global p12 details {preserved}",
                    "newline": True,
                    "status": "success",
                    "status_color": "green",
                })
                
                if self.is_all_global:
                    return
                skip_to_end = True
        
        if not skip_to_end:
            if set_default:
                nodeadmin_default = self.config_obj["global_p12"]["nodeadmin"]
                location_default = self.config_obj["global_p12"]["key_location"]
                p12_default = self.config_obj["global_p12"]["key_name"]
                alias_default = self.config_obj["global_p12"]["key_alias"]   
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
                alias_default = ""
            
            p12_required = False if set_default else True
            alias_required = False if set_default else True  
            
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
                "key_alias": {
                    "question": f"  {colored('Enter in p12 wallet alias name: ','cyan')}",
                    "description": "This should be a single string (word) [connect multiple words with snake_case or dashes eg) 'my alias' becomes 'my_alias' or 'my-alias']. This is the alias (simple name) given to your p12 private key file; also known as, your wallet. SAVE THIS ALIAS IN A SAFE SECURE PLACE! If you forget your alias you made not be able to authenticate to the Hypergraph or Metagraph.",
                    "default": alias_default,
                    "required": alias_required,
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
                "line1": f"{ptype.upper()} PROFILE P12 ENTRY",
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
            for profile in self.metagraph_list:
                self.c.functions.print_header_title({
                    "line1": f"{profile.upper()} PROFILE P12 ENTRY",
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
            
        return p12_values


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

                ["A",0], ["Validator Node",0,"blue","bold"], ["cannot access the Constellation Network Hypergraph",0],
                ["without a",0,"cyan"], ["p12 private key file",0,"yellow","bold"], ["that is used to authenticate against network access regardless of PRO score or seedlist.",2],
                ["This same p12 key file is used as your Node’s wallet and derives the DAG address from the p12 file's",0],
                ["public key file, which Constellation Network uses as your node ID.",2],
                
                ["The p12 key file should have been created during installation:",1,'yellow'],  
                ["sudo nodectl install",2], 
                
                # ["If you need to create a p12 private key file:",1,"yellow"],
                # ["sudo nodectl generate_p12",2],

                ["nodectl",0,"blue","bold"], ["has three configuration options for access into various Metagraphs or Layer0 channels via a user defined configuration profile.",2],

            ]
            self.c.functions.print_paragraphs(paragraphs)

            wrapper = self.c.functions.print_paragraphs("wrapper_only")
            wrapper.subsequent_indent = f"{' ': <18}"
            
            print(wrapper.fill(f"{colored('1','magenta',attrs=['bold'])}{colored(': Global     - Setup a global wallet that will work with all profiles.','magenta')}"))
            print(wrapper.fill(f"{colored('2','magenta',attrs=['bold'])}{colored(': Dedicated  – Setup a unique p12 file per profile.','magenta')}"))
            
            text3 = ": Both       - Setup a global wallet that will work with any profiles that are configured to use the global settings; also, allow the Node to have Metagraphs that uses dedicated (individual) wallets, per Metagraph or Layer0 network."
            print(wrapper.fill(f"{colored('3','magenta',attrs=['bold'])}{colored(text3,'magenta')}"))
        
        self.is_all_global = self.c.functions.confirm_action({
            "prompt": f"\n  Set {colored('ALL','yellow','on_blue',attrs=['bold'])} {colored('profile p12 wallets to Global?','cyan')}",
            "yes_no_default": "y",
            "return_on": "y",
            "exit_if": False
        })
        
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
        
        #for key,values in self.config_obj_apply.items():
        for profile, values in self.config_obj_apply.items():
            # for profile in self.metagraph_list:
            #     if key == profile:
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
                    
        system(f"sudo cp {self.yaml_path} /var/tessellation/nodectl/cn-config.yaml > /dev/null 2>&1")
        system(f"sudo rm -f {self.yaml_path} > /dev/null 2>&1")
        if self.action != "new": self.prepare_configuration("edit_config",True)


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
        
                        
    # # =====================================================
    # # MANUAL BUILD METHODS
    # # =====================================================
    
    def manual_section_header(self, profile, header):
        self.c.functions.print_header_title(self.header_title)
        self.c.functions.print_header_title({
            "line1": f"{profile.upper()} PROFILE {header}",
            "show_titles": False,
            "single_line": True,
            "newline": False if self.detailed else "bottom"
        })
        
        
    # def manual_build(self,default=True):
        
    #     if default: 
    #         self.header_title = {
    #             "line1": "New Manual Profile",
    #             "line2": "Builder",
    #             "show_titles": False,
    #             "clear": True,
    #             "newline": "both",
    #         }
    #         self.manual_build_setup()

    #     while True:
    #         self.manual_build_profile()
    #         self.manual_build_node_type()
    #         self.manual_build_layer()
    #         self.manual_build_environment()
    #         self.manual_build_description()
    #         self.manual_build_edge_point()
    #         self.manual_build_tcp()
    #         self.manual_build_service()
    #         self.manual_build_link()
    #         self.manual_build_dirs()
    #         self.manual_build_memory()
    #         self.manual_build_file_repo()
    #         self.manual_build_p12()
            
    #         self.build_profile()
            
    #         another = self.c.functions.confirm_action({
    #             "prompt": "Add another profile?",
    #             "yes_no_default": "n",
    #             "return_on": "y",
    #             "exit_if": False
    #         })
    #         if not another:
    #             break
            
    #         self.c.functions.print_header_title({
    #             "line1": "ANOTHER NEW PROFILE",
    #             "line2": f"Last Created: {self.profile_details['profile_name']}",
    #             "clear": True,
    #             "newline": "top"
    #         })
        
    #     self.c.functions.print_cmd_status({
    #         "text_start": "Configuration profile build complete",
    #         "status": "complete",
    #         "newline": True,
    #     })
    #     self.c.functions.print_cmd_status({
    #         "text_start": "Submitting for verification and build",
    #         "status": "running",
    #     })
            


        
              
    # def manual_build_setup(self):
    #     self.c.functions.print_header_title({
    #         "line1": "MANUAL CONFIGURATION SETUP",
    #         "show_titles": False,
    #         "clear": True,
    #         "newline": "both"
    #     })
        
    #     if self.detailed:
    #         paragraph = [
    #             ["WARNING",0,"red,on_white","bold"],
    #             ["Please make sure you understand and know all the proper configuration settings when using this option.",2,"white"],
                
    #             ["Since the",0,],["advanced",0,"white","underline"],
    #             ["option was chosen, a brief explanation will be presented for each option.",2],
                
    #             ["Recommended/Default options will be presented in",0,],["[]",0,"yellow","bold"],
    #             ["simply hit the",0], ["<enter>",0, "magenta","bold"], ["key to accept.",2],
    #         ]
    #         self.c.functions.print_paragraphs(paragraph)
        
    #     self.handle_global_p12("global") # adds to config_obj by default
            
    #     self.c.functions.print_header_title({
    #         "line1": "PREPARE PROFILES",
    #         "single_line": True,
    #         "newline": "both" if not self.detailed else "top"
    #     })
        
        
    # def manual_build_profile(self,profile=False):
    #     default = None if not profile else profile
    #     required = True if not profile else False
    #     profile_title = profile if profile else ""
    #     self.manual_section_header(profile_title,"NAME")
            
    #     questions = {
    #         "profile_name": {
    #             "question": f"  {colored('Enter new profile name to add to this Node: ','cyan')}",
    #             "description": "It is important to pick a profile name that you do not want to change too often. This is because the profile name is used to create the directory structure that holds a lot of variable (changing or scaling in and out) data, changing this name in the future will cause a lot of data migration on your Node.",
    #             "default": default,
    #             "required": required,
    #         }
    #     }
        
    #     while True:
    #         self.profile_details = self.ask_confirm_questions({"questions": questions})
            
    #         self.c.functions.print_header_title(self.header_title)
    #         self.manual_section_header(self.profile_details['profile_name'],"SPECIFICS")
            
    #         if not self.is_duplicate_profile(self.profile_details['profile_name']):
    #             break
            
    #         self.c.functions.print_paragraphs([
    #             [" ERROR ",0,"yellow,on_red","bold"], ["A profile matching [",0],
    #             [self.profile_details['profile_name'],-1,"yellow","bold"], ["] already exists. Please try again.",-1],
    #             ["",2],
    #         ])

    #     print("")
    #     self.profile = f"[{self.profile_details['profile_name']}]"
    #     self.profile_name_list.append(self.profile_details['profile_name'])
        
        
    def manual_build_node_type(self,profile=False):
        profile = self.profile_to_edit if not profile else profile

        self.manual_section_header(profile,"NODE TYPE")
        
        if self.detailed:
            self.c.functions.print_paragraphs([
                ["",1], ["There are only two options: 'validator' and 'genesis'. Unless you are an advanced Metagraph ",0,"white","bold"],
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
            questions = {"node_type": "validator"}
        if option.lower() == "g":
            questions = {"node_type": "genesis"}

        self.manual_append_build_apply({
            "questions": questions, 
            "profile": profile,
            "defaults": True,
        })


    def manual_build_description(self,profile=False):
        default = "none" if not profile else self.c.config_obj[profile]["description"]
        profile = self.profile if not profile else profile

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
        description1 = "Generally a layer0 or Metagraph (layer1) network should have a device on the network (most likely a load balancer type "
        description1 += "device/system/server) where API (application programming interface) calls can be directed.  These calls will hit the "
        description1 += "edge device and direct those API requests into the network.  This value can be a FQDN (full qualified domain name) hostname " 
        description1 += "or IP address.  Do not enter a URL/URI (should not include http:// or https://).  Please contact your layer0 or Metagraph Administrator for "
        description1 += "this information. "
        description1 += default_desc
        
        description2 = f"When listening on the network, a network connected server (edge point server entered for this profile {profile}) "
        description2 += "will listen for incoming connections on a specific TCP (Transport Control Protocol) port.  You should consult with the "
        description2 += "Layer0 or Metagraph Administrators to obtain this port value. "
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
        
        no_change_list = command_obj.get("no_change_list",list(questions.keys()))
        append_obj = {}
        
        # identify profiles that do not change
        for i_profile in self.metagraph_list:
            if i_profile == profile:
                continue

            for item in no_change_list:
                if i_profile not in append_obj:
                    append_obj[i_profile] = {}

                append_obj[i_profile][item] = self.c.config_obj[i_profile][item]
                append_obj[i_profile]["do_not_change"] = True

        # append and add to the append_obj
        for i_profile in self.metagraph_list:
            if i_profile != profile:
                i_append_obj = {}
                for item in no_change_list:
                    i_append_obj[f"{item}"] = self.c.config_obj[i_profile][item]
                append_obj[f"{i_profile}"] = {**i_append_obj, "do_not_change": True}
                
        # append the changing items to the append obj
        append_obj = {
            f"{profile}": {
                **self.ask_confirm_questions({
                    "questions": questions,
                    "confirm": confirm,
                    "defaults": defaults,
                }),
            },
            **append_obj,
        }   
                 
        self.config_obj_apply = {
            **self.config_obj_apply,
            **append_obj
        } 
        
        # reorder search so that replacement happens
        # at the correct lines in the correct order
        for i_profile in reversed(self.metagraph_list):
            self.config_obj_apply = {f"{i_profile}": self.config_obj_apply.pop(i_profile), **self.config_obj_apply }
        
        if apply: self.apply_vars_to_config() 
        
        
    def manual_build_layer(self,profile=False):
        default = "1" if not profile else self.c.config_obj[profile]["layer"]
        profile = self.profile_to_edit if not profile else profile
        
        self.manual_section_header(profile,"DLT LAYER")
        
        description = "The distributed ledger technology 'DLT' generally called the blockchain "
        description += "($DAG Constellation Network uses directed acyclic graph 'DAG') is designed by layer type. This needs to be a valid "
        description += "integer (number) between 0 and 4, for the 5 available layers. Metagraphs are generally always layer 0 or 1. "
        description += "Metagraph Layer 0 can be referred to as ML0, Metagraph Layer1 can be referred to as ML1 and the Constellation "
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
        
        description = "In order to participate on a Metagraph or Hypergraph a Node may be required to hold collateral within the "
        description += "active (hot) wallet located on this Node.  In the event that collateral is waved or there is not a requirement "
        description += "to hold collateral, this value can be set to 0. Please contact the Metagraph or Hypergraph administration to "
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
        profile = self.profile if not profile else profile
        required = True if not profile else False
        
        self.manual_section_header(profile,"ENVIRONMENT")  
          
        description = "Metagraph Layer 0 can be referred to as ML0, Metagraph Layer1 can be referred to as ML1 and the Constellation "
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
        port_ending = "This can be any port; however, it is highly recommended to keep the port between 1024 and 65535.  Constellation has been using ports in the 9000-9999 range. Do not reuse any ports you already defined, as this will cause conflicts. You may want to consult with your layer0 or Metagraph administrator for recommended port values."

        tcp_range = [9000,9010,9020,9030,9040]
        
        if profile:
            public_default = self.c.config_obj[profile]["public_port"]  
            p2p_default = self.c.config_obj[profile]["p2p_port"]     
            cli_default = self.c.config_obj[profile]["cli_port"]  
        else:
            profile = self.profile_to_edit
            for n, range in enumerate(tcp_range):
                if self.profile_details["layer"] == str(n):
                    public_default = f"{range}"
                    p2p_default = f"{range+1}"
                    cli_default = f"{range+2}" 
                    break
                else:
                    self.log.logger.error(f"invalid transport layer entered? [{self.profile_details['layer']}] cannot derive default values")
                    p2p_default = cli_default = public_default = None

        try: 
            _ = int(self.c.config_obj[profile]["layer"])
        except:
            self.log.logger.error(f'invalid blockchain layer entered [{self.c.config_obj[profile]["layer"]}] cannot continue')
            self.error_messages.error_code_messages({
                "error_code": "cfr-369",
                "line_code": "invalid_layer",
                "extra": self.profile_details["layer"]
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
        dict_link,dict_link2, dict_link3 = {}, {}, {}      
        link = False if not profile else True
        title_profile = self.profile_to_edit if not profile else profile
        
        gl0_linking, ml0_linking, gl0_self, ml0_self = True, True, True, True
        defaults, gl0_ask_questions, ml0_ask_questions = False, False, False
        
        layer_types = ["gl0","ml0"]
        questions = {}
        
        def print_header():
            print("")
            self.manual_section_header(title_profile,"LINK SETUP") 
            
        link_description = "Generally, a Metagraph Layer0 (ML0) and/or Metagraph Layer1 (ML1) will be required to link to the Hypergraph Global Layer0 "
        link_description += "(GL0) network to transmit consensus information between the local Node and the Validator Nodes on the Layer0 network. "
        link_description += "The Node Operator should consult with your Metagraph Administrators for further details. "
        link_description += "Also, a ML1 will be required to link to the ML0 thereby creating to separate links. "
        link_description += "IMPORTANT: If you plan to use the recommended process of linking to ML1 to GL0, ML1 to ML0, and/or ML0 to GL0 "
        link_description += "through another profile residing on this Node, "
        link_description += "enter \"self\" for the NodeId and enter \"self\" for the IP address.  Failure to do so will "
        link_description += "result in this profile \"thinking\" it is linking to a remote Node."
        
        def set_link_obj(l_type,value):
            return {
                f"{l_type}_enable_link": "False" if value == "None" else "True",
                f"{l_type}_link_key": value,
                f"{l_type}_link_host": value,
                f"{l_type}_link_port": value,                
                f"{l_type}_link_profile": value,                
            }

        def self_linking(l_type,questions):
            set_self = False
            self_items = {}
            
            if self.c.functions.confirm_action({
                "yes_no_default": "n",
                "return_on": "y",
                "prompt": f"Do you want to link {l_type.upper()} to itself?",
                "exit_if": False
            }):
                self_items = set_link_obj(l_type,"self")
                print("")
                cprint("  Which profile do you want to link to?","cyan")
                
                linkable_profiles = []
                for i_profile in self.metagraph_list:
                    if i_profile != profile:
                        if self.c.config_obj[i_profile]["layer"] < 1:
                            linkable_profiles.append(i_profile)
                
                if len(linkable_profiles) < 1:
                    cprint("  No avaliable profiles to link to cancelling","red")
                else:
                    option = self.c.functions.print_option_menu({
                        "options": linkable_profiles,
                        "let_or_num": "num",
                        "color": "magenta",
                        "return_value": True
                    })
                    self_items[f"{l_type}_link_profile"] = option   
            
                    questions = {
                        **questions,
                        **self_items
                    }
                    set_self = True
            
            return [set_self, questions]
            
        def ask_link_questions(l_type, questions, key_default, host_default, port_default):
            warning_msg = f"running a {'ML0' if l_type == 'ml0' else 'GL0'} network on the same Node as the Node running this Metagraph.  In order to do this you cancel this setup and choose the 'self' option when requested."
            questions = {
                **questions,
                f"{l_type}_link_key": {
                    "question": f"  {colored(f'Enter the {l_type.upper()} link public key','cyan')}",
                    "description": f"You need to identify the public key of the Node that you going to attempt to link to. This is required for security purposes to avoid man-in-the-middle cybersecurity attacks.  It is highly recommended to use the public key of your own Node if you are {warning_msg} If you are not using your own Node, you will need to obtain the public p12 key from the Node you are attempting to link through.",
                    "default": key_default,
                    "required": False,
                },          
                f"{l_type}_link_host": {
                    "question": f"  {colored(f'Enter the {l_type.upper()} link host ip address','cyan')}",
                    "description": f"You need to identify the public ip address of the Node that you going to attempt to link with. It is highly recommended to use your own Node if you are {warning_msg}",
                    "default": host_default,
                    "required": False,
                },  
                f"{l_type}_link_port": {
                    "question": f"  {colored(f'Enter the {l_type.upper()} link public port','cyan')}",
                    "description": f"You need to identify the public TCP port open on the Node that you going to attempt to link with. It is highly recommended to use your own Node if you are {warning_msg}",
                    "default": port_default,
                    "required": False,
                },  
            }
            return questions        
 
        if profile:  # left in place in case full manual profile creation is reinstituted
            print(" ")
            print_header()
            print(" ")

            for l_type in layer_types:
                if self.c.config_obj[profile][f"{l_type}_link_enable"]:
                    if self.c.functions.confirm_action({
                        "yes_no_default": "n",
                        "return_on": "y",
                        "prompt": f"Do you want to disable the {l_type.upper()} link?",
                        "exit_if": False
                    }):
                        disable = set_link_obj(l_type,"None")
                        questions = {
                            **questions,
                            **disable
                        }
                        if l_type == "gl0": gl0_linking = False
                        if l_type == "ml0": ml0_linking = False
                else:
                    if self.c.functions.confirm_action({
                        "yes_no_default": "n",
                        "return_on": "n",
                        "prompt": f"Do you want to enable the {l_type.upper()} link?",
                        "exit_if": False
                    }):
                        if l_type == "gl0": gl0_linking = False
                        if l_type == "ml0": ml0_linking = False
                        
            if gl0_linking:
                results = self_linking("gl0",questions)
                if not results[0]:
                    gl0_ask_questions = True
                questions = results[1]
            if ml0_linking:
                results = self_linking("ml0",questions)
                if not results[0]:
                    ml0_ask_questions = True
                questions = results[1]
                
            if gl0_ask_questions:
                defaults = True
                key_default = self.c.config_obj[profile]["gl0_link_key"]
                host_default = self.c.config_obj[profile]["gl0_link_host"]
                port_default = self.c.config_obj[profile]["gl0_link_port"]
                questions = ask_link_questions(questions,key_default,host_default,port_default)
                
            if ml0_ask_questions:
                defaults = True
                key_default = self.c.config_obj[profile]["ml0_link_key"]
                host_default = self.c.config_obj[profile]["ml0_link_host"]
                port_default = self.c.config_obj[profile]["ml0_link_port"]
                questions = ask_link_questions(questions,key_default,host_default,port_default)

        if not gl0_linking and not ml0_linking and not gl0_ask_questions and not ml0_ask_questions:
            return
        
        self.manual_append_build_apply({
            "questions": questions, 
            "profile": profile,
        })
 
 
    def manual_build_dirs(self,profile=False):   
        title_profile = self.profile_to_edit if not profile else profile
        self.manual_section_header(title_profile,"DIRECTORY STRUCTURE")
        defaults = False
        
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
            defaults = True
            self.c.functions.print_cmd_status({
                "text_start": "Using defaults for directory structures",
                "status": "complete",
                "newline": True,
            })
            questions = {
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
        title_profile = self.profile_to_edit if not profile else profile
        questions = {}
        defaults = False
        allow_disable = True
        one_off = "location"
        
        verb = "seed list" 
        if file_repo_type == "priority_source": verb = "priority source list"
        if file_repo_type == "jar": 
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
                questions = {
                    f"{file_repo_type}_{one_off}": "default",
                    f"{file_repo_type}_file": "default",
                    f"{file_repo_type}_repository": "default"
                }
            else:
                questions = {
                    f"{file_repo_type}_{one_off}": "disable",
                    f"{file_repo_type}_file": "disable",
                    f"{file_repo_type}_repository": "disable"
                } 
             
            print("")
            
        else:
            if profile:
                location_default = self.c.config_obj[profile][f"{file_repo_type}_{one_off}"]
                file_default = self.c.config_obj[profile][f"{file_repo_type}_file"]
                repo_default = self.c.config_obj[profile][f"{file_repo_type}_repository"]
            else:
                def_value = "default" if int(self.c.config_obj[profile]["layer"]) < 1 else "disable"
                location_default, file_default, repo_default = def_value, def_value, def_value
            
            defaultdescr = "Alternatively, the Node Operator can enter the string \"default\" to allow nodectl to use default values. "
            if allow_disable: defaultdescr += "Enter the string \"disable\" to disable this feature for this profile."
            
            description1 = ""
            if file_repo_type == "priority_source":
                description1 += f"The {verb} is a specialized access-list that is mostly designated for Metagraph special access-list "
                description1 += f"elements, out of the scope of nodectl.  The values associated with these configuration values "
                description1 += f"should be obtained directly from the Metagraph administrators. "
            description1 += f"The {verb} is part of the PRO (proof of reputable observation) elements of Constellation Network. "
            description1 += "Enter the location (needs to be a full path not including the file name.  Note: The file name will be defined "
            description1 += "succeeding this entry.) on your local Node.  This is where the Node Operator would like to store the local copy of "
            description1 += "this access list. "
            if file_repo_type == "seed":
                description1 += "This is a requirement to authenticate to the Metagraph and/or Hypergraph the Node Operator is "
                description1 += "attempting to connect to. "
            if file_repo_type == "jar":
                description1 = f"The {verb} version is the version number associated with the Metagraph or Hypergraph.  It is necessary that "
                description1 += "nodectl understand where it is intending to download the proper jar binaries from. In the event that the "
                description1 += "Metagraph associated jar binaries are located as artifacts in a github repository, is a prime example of the "
                description1 += "importance of knowing the version number. "
                description1 += "The version should be in the form: vX.X.X where X is a number.  Example) v2.0.0. "
            description1 += defaultdescr

            description2 = f"The file name to be used to contain the {verb} entries.  This should be a single string value with no spaces (if you "
            description2 += f"want to use multiple strings, delineate them with an underscore, dash, or other). After the {verb} is downloaded "
            description2 += "from a Metagraph or Hypergraph "
            description2 += "repository (defined succeeding this entry), the contents will be saved to this file.  The file (downloaded from the repository) " 
            description2 += "must contain the exact same information as all other Nodes that participate on the cluster. "
            description2 += "The file will be placed in the location defined by the seed location variable entered above. "
            description2 += defaultdescr
            
            description3 = f"The {verb} repository is the location on the Internet (generally a github repository or artifact location) where nodectl can download "
            description3 += f"the {verb} associated with the Metagraph or Hypergraph. Do not enter a URL or URI (do not include "
            description3 += "http:// or https:// in the FQDN (fully qualified domain name)). The Node Operator should obtain this information "
            description3 += "from the Metagraph or Hypergraph administrators. "
            description3 += defaultdescr
            
            one_off2 = "version" if file_repo_type == "jar" else "directory"
            questions = {
                f"{file_repo_type}_{one_off}": {
                    "question": f"  {colored(f'Enter a valid {verb} {one_off2}','cyan')}",
                    "description": description1,
                    "required": False,
                    "default": location_default,
                },
                f"{file_repo_type}_file": {
                    "question": f"  {colored(f'Enter a valid {verb} file name','cyan')}",
                    "description": description2, 
                    "required": False,
                    "default": file_default
                },
                f"{file_repo_type}_repository": {
                    "question": f"  {colored(f'Enter a valid {verb} repository','cyan')}",
                    "description": description3,
                    "required": False,
                    "default": repo_default
                },
            }
            
        self.manual_append_build_apply({
            "questions": questions, 
            "profile": profile,
            "defaults": defaults,
        })

                
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
                ["The configuration file for this Node is setup with profile sections for each Metagraph or Hypergraph cluster.",0,"white","bold"],
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
                "questions": single_p12_obj,
                "defaults": True,
        })
            
        return

#     # =====================================================
#     # COMMON BUILD METHODS  
#     # =====================================================

      
    def ask_confirm_questions(self, command_obj):
        questions = command_obj["questions"]
        confirm = command_obj.get("confirm",True)
        defaults = command_obj.get("defaults",False)
        
        if defaults: return questions
        
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
        
    
#     def build_profile(self):
#         profiles = []
#         try:
#             profiles.append(self.profile_details["profile_name"])
#         except:
#             # pre-defined selected
#             environment = self.environment
            
#             self.profile_name_list = profiles = ["dag-l0","dag-l1"]
#             if "integrationnet" in environment:
#                 self.profile_name_list = profiles = ["intnet-l0","intnet-l1"]
                
#             layers = ["0","1"]
#             tcp_ports = [["9000","9001","9002"],["9010","9011","9012"]]
#             java = [["1024M","7G","256K"],["1024M","3G","256K"]]
#             p12 = ["global","global","global","global","global"]; p12 = [p12,p12]
#             node_type = ["validator","validator"]
            
#             services = ["node_l0","node_l1"] 
#             if "integrationnet" in environment:
#                 services = ["intnetserv_l0","intnetserv_l1"]   
                
#             dirs = [["default","default","default"],["disable","default","default"]]
#             host = [self.edge_host0,self.edge_host1]
            
#             description = [
#                 "Constellation Network Global Hypergraph",
#                 "Constellation Network Layer1 Metagraph" 
#             ]
#             link_zero = [["False","None","None","None","None"],["True","self","self","self",profiles[0]]]
#             https = "False"
            
#             port = ["80","80"]
                
#             seed_location = ["/var/tessellation/","disable"]
#             seed_file = ["seed-list","disable"]
#             enable = "True"
#         else: # manual
#             profile_obj = self.profile_details

#             if "enable" not in profile_obj:
#                 enable = "True"
#             else:
#                 enable = profile_obj["enable"]
                
#             # ====================
#             # PREPARE MEMORY
#             # ====================
#             java =  [
#                 [
#                     profile_obj["java_jvm_xms"],
#                     profile_obj["java_jvm_xmx"],
#                     profile_obj["java_jvm_xss"],
#                 ]
#             ]
            
#             # ====================
#             # PREPARE LAYER
#             # ====================
#             layers = [profile_obj["layer"]]  # blockchain_invalid tested at 'manual_tcp_build'
            
#             # ====================
#             # PREPARE TCP PORTS
#             # ====================
#             try:
#                 int(profile_obj["public"]),
#                 int(profile_obj["p2p"]),
#                 int(profile_obj["cli"]),
#             except:
#                 self.log.logger.error(f"invalid TCP ports given cannot continue, exiting utility public [{profile_obj['public']}], p2p [{profile_obj['p2p']}], cli [{profile_obj['cli']}]")
#                 self.error_messages.error_code_messages({
#                     "error_code": "cfr-829",
#                     "line_code": "invalid_tcp_ports",
#                     "extra": f"public [{profile_obj['public']}], p2p [{profile_obj['p2p']}], cli [{profile_obj['cli']}]"
#                 })
#             public = str(profile_obj["public"])
#             p2p = str(profile_obj["p2p"])
#             cli = str(profile_obj["cli"])
#             tcp_ports = [[public,p2p,cli]] 
            
#             # ====================
#             # PREPARE EDGE POINTS
#             # ====================
#             try:
#                 port = [str(profile_obj["host_port"])]
#             except:
#                 self.log.logger.error(f"edge point host port may be invalid [{profile_obj['host_port']}] using [80] as default")
#                 port = ["80"]
                
#             host = [profile_obj["host"]]
            
#             try:
#                 https = "True" if profile_obj["https"].lower() == "y" or profile_obj["https"].lower() == "yes" else "False"
#             except:
#                 self.log.logger.error(f"new configuration build; secure https option was not a valid entry [{profile_obj['https']}] defaulting to False")
#                 https = "False"
                                
#             # ====================
#             # PREPARE DIRECTORIES
#             # ====================
#             dirs = [
#                 [profile_obj['snapshots'], profile_obj['backups'], profile_obj['uploads']]
#             ]
                                
#             # ====================
#             # PREPARE SERVICES
#             # ====================
            
#             services = [profile_obj["service"]]
                        
#             # ====================
#             # PREPARE NODE TYPE
#             # ====================
#             if profile_obj["node_type"] != "validator" and profile_obj["node_type"] != "genesis":
#                 self.log.logger.error(f"invalid Node type entered by user [{profile_obj['node_type']}] defaulting to 'validator'")
#                 profile_obj["node_type"] = "validator"
                
#             node_type = [profile_obj["node_type"]]
            
#             # ====================
#             # DESCRIPTION AND ENVIRONMENT
#             # ====================
#             description = [profile_obj["description"]]
#             environment = profile_obj["environment"]

#             # ====================
#             # PREPARE SEED / PRO DETAILS
#             # ====================
#             seed_location = [profile_obj.get("seed_location")]
#             seed_file = [profile_obj.get("seed_file")]
            
#             # ====================
#             # PREPARE P12 DETAILS
#             # ====================
#             key_name = profile_obj.get("p12_key_name", "global")
#             alias = profile_obj.get("key_alias", "global")
#             passphrase = profile_obj.get("passphrase", "global")
#             nodeadmin = profile_obj.get("nodeadmin", "global")
#             location = profile_obj.get("key_location", "global")
#             p12 = [
#                 [nodeadmin, location, key_name, alias, passphrase]
#             ]
            
#             # ====================
#             # PREPARE LINK PROFILE
#             # ====================
#             if profile_obj["gl0_link"].lower() == "y" or profile_obj["gl0_link"].lower() == "yes":
#                 link_zero = [
#                     [
#                         "True",
#                         profile_obj["gl0_key"],
#                         profile_obj["gl0_host"],
#                         profile_obj["gl0_port"],
#                         profile_obj["link_profile"]
#                     ]
#                 ]
#             else:
#                 link_zero = [["False","None","None","None","None"]]

#         try:
#             for n, profile in enumerate(profiles):
#                 profile_obj = {
#                     f"{profile}": {
#                         "enable": enable,
#                         "layer": layers[n],
#                         "https": https,
#                         "host": host[n],
#                         "host_port": port[n],
#                         "environment": environment,
#                         "public": tcp_ports[n][0],
#                         "p2p":  tcp_ports[n][1],
#                         "cli":  tcp_ports[n][2],
#                         "service": services[n],
#                         "gl0_enable": link_zero[n][0],
#                         "gl0_key": link_zero[n][1],
#                         "gl0_host": link_zero[n][2],
#                         "gl0_port": link_zero[n][3],
#                         "link_profile": link_zero[n][4],
#                         "snapshots": dirs[n][0],
#                         "backups": dirs[n][1],
#                         "uploads": dirs[n][2],
#                         "java_jvm_xms": java[n][0],
#                         "java_jvm_xmx": java[n][1],
#                         "java_jvm_xss": java[n][2],
#                         "p12_nodeadmin": p12[n][0],
#                         "p12_key_location": p12[n][1],
#                         "p12_key_name": p12[n][2],
#                         "p12_key_alias": p12[n][3],
#                         "p12_passphrase": p12[n][4],
#                         "node_type": node_type[n],
#                         "description": description[n],
#                         "seed_location": seed_location[n],
#                         "seed_file": seed_file[n],
#                     }
#                 } 
                
#                 self.config_ob = {
#                     **self.config_ob,
#                     **profile_obj,
#                 }
                
#         except Exception as e:
#             self.log.logger.error(f"Error building user defined profile details | error [{e}]")
#             self.error_messages.error_code_messages({
#                 "error_code": "cfr-1066",
#                 "line_code": "profile_build_error",
#                 "extra": e
#             })
            
#         return



        

#     def build_yaml(self,quiet=False):
#         # correlates to migration class - build_yaml
        
#         # self.build_known_skelton(1)
#         # sorted_profile_obj =  sorted(self.config_obj.items(), key = lambda x: x[1]["layer"])
#         sorted_profile_obj =  sorted(self.config_obj.items(), key = lambda x: (x[1]["layer"], x[0]))
#         sorted_config_obj = {"profiles": {}}
#         for profile in sorted_profile_obj:
#             sorted_config_obj[profile[0]] = profile[1]
#         self.config_ob = sorted_config_obj
#         # self.build_yaml(True)
        
#         progress = {
#             "text_start": "building",
#             "brackets": "cn-config.yaml",
#             "text_end": "file",
#             "status": "in progress",
#             "status_color": "yellow",
#             "newline": False,
#         }
#         self.c.functions.print_cmd_status(progress)

#         self.migrate.create_n_write_yaml()
        
#         # profile sections
#         for profile in self.config_obj.keys():
#             details = self.config_obj[profile]
#             link_port = "None"
#             if details["gl0_enable"] == "True":
#                 try:
#                     link_port = self.config_obj[details["link_profile"]]["public"]
#                 except:
#                     link_port = details["gl0_port"]
#                     try:
#                         int(link_port)
#                     except Exception as e:
#                         self.error_messages.error_code_messages({
#                             "error_code": "cfr-1137",
#                             "line_code": "link_to_profile",
#                             "extra": profile,
#                             "extra2": details["link_profile"]
#                         })

#             for p_detail in self.p12_items:
#                 if p_detail == "passphrase":
#                     try:
#                         if details["p12_passphrase_global"] == "True" or self.is_all_global:
#                             details[p_detail] = "global"
#                     except:
#                         if self.action == "new" or self.is_all_global:
#                             details[p_detail] = "global"

#                 elif self.is_all_global:
#                     details[p_detail] = "global"

#             if details["passphrase"] != "None" and details["passphrase"] != "global":
#                 details["passphrase"] = f'"{details["passphrase"]}"'
                
#             rebuild_obj = {
#                 "nodegarageprofile": profile,
#                 "nodegarageenable": details["enable"],
#                 "nodegarageblocklayer": details["layer"],
#                 "nodegarageedgehttps": details["https"],
#                 "nodegarageedgehost": details['host'],
#                 "nodegarageedgeporthost": details["host_port"],
#                 "nodegarageenvironment": details["environment"],
#                 "nodegaragepublic": details["public"],
#                 "nodegaragep2p": details["p2p"],
#                 "nodegaragecli":details["cli"],
#                 "nodegarageservice": details["service"],
#                 "nodegaragelinkenable": details["gl0_enable"],
#                 "nodegarage0layerkey": details["gl0_key"],
#                 "nodegarage0layerhost": details["gl0_host"],
#                 "nodegarage0layerport": str(link_port),
#                 "ndoegarage0layerlink": details["link_profile"],
#                 "nodegaragexms": details["java_jvm_xms"],
#                 "nodegaragexmx": details["java_jvm_xmx"],
#                 "nodegaragexss": details["java_jvm_xss"],
#                 "nodegaragenodetype": details["node_type"],
#                 "nodegaragedescription": details["description"],
#                 "nodegaragesnaphostsdir": details["snapshots"],
#                 "nodegaragebackupsdir": details["backups"],
#                 "nodegarageuploadsdir": details["uploads"],
#                 "nodegaragenodeadmin": details["p12_nodeadmin"],
#                 "nodegaragekeylocation": details["p12_key_location"],
#                 "nodegaragep12name": details["p12_key_name"],
#                 "nodegaragewalletalias": details["p12_key_alias"],
#                 "nodegaragepassphrase": details["p12_passphrase"],
#                 "nodegarageseedlistloc": details["seed_location"],
#                 "nodegarageseedlistfile": details["seed_file"],
#                 "create_file": "config_yaml_profile",
#             }
#             self.migrate.configurator_builder(rebuild_obj)
        
        
#         # auto_restart and upgrade section
#         rebuild_obj = {
#             "nodegarageeautoenable": str(self.config_obj["global_auto_restart"]["enable"]),
#             "nodegarageautoupgrade": str(self.config_obj["global_auto_restart"]["auto_upgrade"]),
#             "create_file": "config_yaml_autorestart",
#         }
#         self.migrate.configurator_builder(rebuild_obj)
        
#         # p12 section
#         if self.config_obj["global_p12"]["passphrase"] != "None":
#             self.config_obj["global_p12"]["passphrase"] = f'"{self.config_obj["global_p12"]["passphrase"]}"'
            
#         rebuild_obj = {
#             "nodegaragenodeadmin": self.config_obj["global_p12"]["nodeadmin"],
#             "nodegaragekeylocation": self.config_obj["global_p12"]["key_location"],
#             "nodegaragep12name": self.config_obj["global_p12"]["key_name"],
#             "nodegaragewalletalias": self.config_obj["global_p12"]["wallet_alias"],
#             "nodegaragepassphrase": self.config_obj["global_p12"]["passphrase"],
#             "create_file": "config_yaml_p12",
#         }

#         self.migrate.configurator_builder(rebuild_obj)
        
#         complete = self.migrate.final_yaml_write_out()
#         self.move_config_backups()
        
#         if complete:
#             self.c.functions.print_cmd_status({
#                 **progress,
#                 "status": "complete",
#                 "status_color": "green",
#                 "newline": True,
#             })
#             if not quiet:
#                 self.ask_review_config()
#                 self.c.functions.print_header_title({
#                     "line1": "CONFIGURATOR UPDATED",
#                     "show_titles": False,
#                     "newline": "both",
#                     "clear": True
#                 })
#                 self.c.functions.print_cmd_status({
#                     "text_start": "Validating",
#                     "brackets": "new",
#                     "text_end": "config",
#                     "status": "please wait",
#                     "status_color": "yellow",
#                     "newline": True,
#                 })
            
#             self.move_config_backups()
#             self.prepare_configuration("edit_config",True) # rebuild 
            
#             press_any = False
#             if self.upgrade_needed:            
#                 self.c.functions.print_paragraphs([
#                     ["WARNING:",0,"yellow,on_blue","bold"],["This Node will need to be upgraded in order for changes to take affect.",2,"yellow"],
#                     ["sudo nodectl upgrade",2,"grey,on_yellow","bold"],
#                 ])
#                 press_any = True
#             elif self.restart_needed:
#                 self.c.functions.print_paragraphs([
#                     ["WARNING:",0,"yellow,on_blue","bold"],["This Node will need to be restarted in order for changes to take affect.",2,"yellow"],
#                     [" sudo nodectl restart -p all ",2,"grey,on_yellow","bold"],
#                 ])
#                 press_any = True
#             if press_any:
#                 self.c.functions.print_any_key({})
                    
#         else:
#             self.error_messages.error_code_messages({
#                 "error_code": "cfr-1177",
#                 "line_code": "missing_dirs"
#             })
        
        
#     def build_known_skelton(self,option):
#         # option == numeric request or profile name
#         # make copy of complex config config_obj without reference
#         self.config_obj = deepcopy(self.c.config_obj)
        
#         try:
#             int(option)
#         except:
#             for key, value in self.c.config_obj[option].items():
#                 self.profile_details[key] = str(value)
#         else:
#             singles = ["enable","layer","environment","service","node_type","description"]
#             key_replacements = {
#                 "xms": "java_jvm_xms",
#                 "xmx": "java_jvm_xmx",
#                 "xss": "java_jvm_xss",
#             }
#             for profile in self.c.config_obj.keys():
#                 profile_details = {}
                
#                 obj = self.config_obj[profile]
#                 for key, value in obj.items():
#                     if key in singles:
#                         profile_details[key] = str(value)
#                     else:
#                         for i_key, i_value in obj[key].items():
#                             if i_key in key_replacements:
#                                 i_key = key_replacements[i_key]
#                             if i_key == "enable": # layer0_link
#                                 i_key = "gl0_enable"
#                             profile_details[i_key] = str(i_value)
                
#                 profile_details["gl0_link"] = "y" if profile_details["gl0_enable"] == "True" else "n"
#                 profile_details["profile_name"] = profile
#                 self.config_obj[profile] = profile_details
        
#         self.prepare_configuration("migrator")
            
            
#     # =====================================================
#     # EDIT CONFIG METHODS  
#     # =====================================================
    
    def edit_config(self):
        # self.action = "edit"
        return_option = "init"
        
        while True:
            self.prepare_configuration("edit_config",True)
            self.metagraph_list = self.c.metagraph_list
            
            if self.action == "edit_profile":
                option = "e"
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
                        
                        ["If the configuration found on the",0,"red"], ["Node",0,"red","underline"], ["reports a known issue;",0,"red"],
                        ["It is recommended to go through each",0,"red"],["issue",0,"yellow","underline"], ["one at a time, revalidating the configuration",0,"red"],
                        ["after each edit, in order to make sure that dependent values, are cleared by each edit",2,"red"],
                        
                        ["If not found, please use the",0], ["manual",0,"yellow","bold"], ["setup and consult the Constellation Network Doc Hub for details.",2],
                    ])
                
                self.c.functions.print_header_title({
                    "line1": "OPTIONS MENU",
                    "show_titles": False,
                    "newline": "bottom"
                })

                options = ["E","A","G","R","M","Q"]
                if return_option not in options:
                    self.c.functions.print_paragraphs([
                        ["E",-1,"magenta","bold"], [")",-1,"magenta"], ["E",0,"magenta","underline"], ["dit Individual Profile Sections",-1,"magenta"], ["",1],
                        # ["A",-1,"magenta","bold"], [")",-1,"magenta"], ["A",0,"magenta","underline"], ["ppend New Profile to Existing",-1,"magenta"], ["",1],
                        ["G",-1,"magenta","bold"], [")",-1,"magenta"], ["G",0,"magenta","underline"], ["lobal P12 Section",-1,"magenta"], ["",1],
                        ["R",-1,"magenta","bold"], [")",-1,"magenta"], ["Auto",0,"magenta"], ["R",0,"magenta","underline"], ["estart Section",-1,"magenta"], ["",1],
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
                return_option = self.edit_profiles()
                if return_option == "q": option = return_option
                elif return_option != "r": self.edit_profile_sections()
            elif option == "a": self.edit_append_profile_global(False)
            elif option == "g": self.edit_append_profile_global(True)
            elif option == "r": self.edit_auto_restart()
            elif option == "m":
                self.action = False
                self.setup()
            if option == "q": self.quit_configurator()

                
    def edit_profiles(self):
        print("")
        self.header_title = {
            "line1": "Edit Profiles",
            "show_titles": False,
            "clear": True,
            "newline": "top",
        }       
             
        self.c.functions.print_header_title({
            "line1": "Edit Profiles",
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
        menu_options = []
        def print_config_section():
            self.c.functions.print_header_title({
                "line1": "CONFIGURATOR SECTION",
                "line2": f"{topic}",
                "show_titles": False,
                "newline": "top",
                "clear": True
            })
        print_config_section()

        profile = self.profile_to_edit
         
        section_change_names = [
            ("API Edge Point",18),
            ("API TCP Ports",19),
            ("Consensus Linking",20),
            ("System Service",4),
            ("Directory Structure",5),
            ("DLT Layer Type",6),
            ("Environment Name",7),
            ("Java Memory Heap",8),
            ("Seed List Setup",9),
            ("Tessellation Binaries",10),
            ("Node Type",11),
            ("Policy Description",12),
            ("Profile Private p12 Key",13),
            ("Source Priority Setup",14),
            ("Java Binary Setup",15),
            ("Custom Variables",16),
            ("Collateral Requirements",17),
        ]
        section_change_names.sort()
                        
        while True:
            do_build_profile, do_build_yaml, do_print_title, do_validate = True, True, True, True 
            do_terminate = False
            option = 0
            
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
                section = colored(f")  {section}","magenta")
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
        
            if option == "m": return
            elif option == "p": return "E"
            elif option == "h": self.show_help()
            elif option == "q": self.quit_configurator()
            elif option == "r":
                self.c.view_yaml_config("migrate")
                print_config_section()
                
            if option not in options2:
                try: option = int(option)-4
                except: option = -1
                if option > len(section_change_names): option = -1
            if option not in options2 and option > -1:
                option = section_change_names[option][1]

                if option == "1":
                    self.edit_enable_disable_profile(profile)
                    
                elif option == "2":
                    self.edit_profile_name(profile)
                    self.called_option = "Profile Name Change"
                    
                elif option == "3":
                    self.delete_profile(profile)
                    self.called_option = "Delete Profile"
                    
                    
                    
                    
                    
                    
                    
                elif option == 6:
                    self.manual_build_layer(profile)
                    self.edit_error_msg = f"Configurator found a error while attempting to edit the [{profile}] [layer] [{self.action}]"
                    self.called_option = "layer modification"

                    
                elif option == 17:
                    self.manual_collateral(profile)
                    self.edit_error_msg = f"Configurator found a error while attempting to edit the [{profile}] [collateral] [{self.action}]"
                    self.called_option = "layer modification"

                    
                elif option == 7:
                    self.manual_build_environment(profile)
                    self.called_option = "Environment modification"
                    do_validate = False
                    
                elif option == 12:
                    self.manual_build_description(profile)
                    self.called_option = "Description modification"   
                    do_validate = False
                    
                elif option == 8:
                    self.manual_build_memory(profile)
                    self.edit_error_msg = f"Configurator found a error while attempting to edit the [{profile}] [java heap memory] [{self.action}]"
                    self.called_option = "Java heap memory modification"
                                                         
                elif option == 19:
                    self.tcp_change_preparation(profile)
                    self.manual_build_tcp(profile)
                    self.edit_error_msg = f"Configurator found a error while attempting to edit the [{profile}] [TCP build] [{self.action}]"
                    self.called_option = "TCP modification"

                elif option == 18:
                    self.manual_build_edge_point(profile)
                    self.edit_error_msg = f"Configurator found a error while attempting to edit the [{profile}] [edge_point] [{self.action}]"
                    self.called_option = "Edge Point Modification"
                        
                elif option == 4:
                    self.edit_service_name(profile)
                    self.called_option = "Service Name Change"
                    
                elif option == 9 or option == 14 or option == 10:
                    file_repo_type = "seed" 
                    if option == 14: file_repo_type ="priority_source"
                    if option == 10: file_repo_type = "jar"
                    self.manual_build_file_repo(file_repo_type,profile)
                    self.called_option = "PRO modification"
                    self.edit_error_msg = f"Configurator found a error while attempting to edit the [{profile}] [pro seed list] [{self.action}]"
                   
                elif option == 11:
                    self.manual_build_node_type(profile)
                    self.called_option = "Node type modification"                    

                elif option == 5:
                    self.migrate_directories(profile)
                    self.called_option = "Directory structure modification"                    
                    
                elif option == 13:
                    self.manual_build_p12(profile)
                    self.called_option = "P12 modification"

                elif option == 20:
                    self.manual_build_link(profile)
                    self.called_option = "Layer0 link"
                    
                if do_validate: self.validate_config(profile)
                if do_print_title: print_config_section()
            elif option not in options2:
                cprint("  Invalid Option, please try again","red")


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
        auto_restart_desc += "'auto_restart' must be enabled in conjunction with 'auto_upgrade'."
        auto_upgrade_desc += "Please be aware that this can be a dangerous feature, as in the (unlikely) event there are bugs presented in the new "
        auto_upgrade_desc += "releases, your Node will be upgraded regardless.  It is important to pay attention to your Node even if this feature "
        auto_upgrade_desc += "is enabled.  Please issue a 'sudo nodectl auto_upgrade help' for details."
        
        restart = "disable" if self.c.config_obj["global_auto_restart"]["auto_restart"] else "enable"
        upgrade = "disable" if self.c.config_obj["global_auto_restart"]["auto_upgrade"] else "enable"
        
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
            "alt_confirm_dict": {
                f"{restart} auto_restart": "auto_restart",
                f"{upgrade} auto_upgrade": "auto_upgrade",
            }
        }
        
        while True:
            restart_error = False
            enable_answers = self.ask_confirm_questions({"questions": questions})
            enable_answers["auto_restart"] = enable_answers["auto_restart"].lower()
            enable_answers["auto_upgrade"] = enable_answers["auto_upgrade"].lower()
            if restart == "disable" and upgrade == "disable":
                if enable_answers["auto_restart"] == "y" and enable_answers["auto_upgrade"] == "n":
                    restart_error = True

            if restart == "disable" and upgrade == "enable":
                if enable_answers["auto_restart"] == "y" and enable_answers["auto_upgrade"] == "y":
                    restart_error = True

            if restart == "enable" and upgrade == "enable":
                if enable_answers["auto_restart"] == "n" and enable_answers["auto_upgrade"] == "y":
                    restart_error = True
                
            if not restart_error:
                shell = ShellHandler(self.c.config_obj,False)
                shell.argv = []
                shell.profile_names = self.metagraph_list
                if restart == "enable" and enable_answers["auto_restart"] == "y":
                    self.c.functions.print_paragraphs([
                        ["auto_restart",0,"yellow","bold"], ["will be enabled.",1],
                    ])
                    # shell.auto_restart_handler("enable",False,False)
                elif restart == "disable" and enable_answers["auto_restart"] == "y":
                    self.c.functions.print_paragraphs([
                        ["auto_restart",0,"yellow","bold"], ["will be disabled.",1],
                    ])
                    # shell.auto_restart_handler("disable",False,False)
                break
            self.c.functions.print_paragraphs([
                [" ERROR ",0,"yellow,on_red"], ["auto_upgrade cannot be enabled without auto_restart, please try again.",1,"red"]
            ])

        self.config_obj_apply = {"global_auto_restart":{}}
        self.config_obj_apply["global_auto_restart"]["auto_restart"] = "False" if enable_answers["auto_restart"] == "y" else "True"
        self.config_obj_apply["global_auto_restart"]["auto_upgrade"] = "False" if enable_answers["auto_upgrade"] == "y" else "True"
        if restart == "enable":
            self.config_obj_apply["global_auto_restart"]["auto_restart"] = "True" if enable_answers["auto_restart"] == "y" else "False"
        if upgrade == "enable":
            self.config_obj_apply["global_auto_restart"]["auto_upgrade"] = "True" if enable_answers["auto_upgrade"] == "y" else "False"
        
        self.apply_vars_to_config()

        
    def edit_append_profile_global(self,p12_only):
        line1 = "Edit P12 Global" if p12_only else "Append new profile"
        line2 = "Private Keys" if p12_only else "to configuration"
        
        self.header_title = {
            "line1": line1,
            "line2": line2,
            "show_titles": False,
            "clear": True,
            "newline": "both",
        }

        # self.migrate.keep_pass_visible = True
        if p12_only:
            self.profile_details["p12_passphrase_global"] = 'True'
            self.preserve_pass = True
            self.skip_convert = True
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
        else:
            self.manual_build(False)
            self.restart_needed = False
            
        self.apply_vars_to_config()    

        if not p12_only:
            self.build_service_file({
                "profiles": self.profile_name_list,
                "action": "Create",
                "rebuild": True,
            })   
                 
    
#     def delete_profile(self,profile):
#         self.c.functions.print_header_title({
#             "line1": f"DELETE A PROFILE",
#             "line2": profile,
#             "single_line": True,
#             "clear": True,
#             "newline": "both"
#         })

#         notice = [
#             ["",1],
#             [" WARNING! ",2,"grey,on_red"],
#             ["This will",0,"red"], ["not",0,"red","bold"], ["only",0,"yellow","underline"], ["remove the profile from the configuration;",0,"red"],
#             ["moreover, this will also remove all",0,"red"], ["data",0,"magenta","bold,underline"], ["from the",0,"red"],
#             ["Node",0,"yellow","bold"], ["pertaining to profile",0,"red"], [profile,0,"yellow","bold,underline"],["",2],
            
#             ["-",0,"magenta","bold"], ["configuration",1,"magenta"],
#             ["-",0,"magenta","bold"], ["services",1,"magenta"],
#             ["-",0,"magenta","bold"], ["associated bash files",1,"magenta"],
#             ["-",0,"magenta","bold"], ["blockchain data (snapshots)",2,"magenta"],
#         ]

#         confirm_notice = self.confirm_with_word({
#             "notice": notice,
#             "action": "change",
#             "word": "YES",
#             "profile": profile,
#             "default": "n"
#         })
#         if not confirm_notice:
#             return False    
        
#         print("")
#         self.c.functions.print_cmd_status({
#             "text_start": "Starting deletion process",
#             "newline": True,
#         })
#         self.handle_service(profile,"service")  # leave and stop first
#         self.cleanup_service_file_msg()
#         self.config_obj.pop(profile)

#         self.c.functions.print_cmd_status({
#             "text_start": f"Profile",
#             "brackets": profile,
#             "status": "deleted",
#             "status_color": "red",
#             "newline": True
#         })

#         return True
        
        
#     def edit_profile_name(self, old_profile):
#         self.c.functions.print_header_title({
#             "line1": "Change Profile Name",
#             "line2": old_profile,
#             "clear": True,
#             "show_titles": False,
#         })
        
#         self.c.functions.print_paragraphs([
#             [" WARNING! ",0,"grey,on_red","bold"], ["This is a dangerous command and should be done with precaution.  It will migrate an entire profile's settings and directory structure.",2],
            
#             ["Please make sure you know what you are doing before continuing...",2],
            
#             ["Please enter in the new profile name you would like to change to at the input.",1,"magenta"]
#         ])
        
#         new_profile_question = colored("  new profile: ","yellow")
#         while True:
#             new_profile = input(new_profile_question)
#             if new_profile != "":
#                 break
#             print("\033[F",end="\r")
                
#         print("")
        
#         if new_profile == old_profile:
#             self.log.logger.error(f"Attempt to change profile names that match, taking no action | new [{new_profile}] -> old [{old_profile}]")
#             self.c.functions.get_user_keypress({
#                 "prompt": f"error: {new_profile} equals {old_profile}, press any key to return",
#                 "prompt_color": "red",
#                 "options": ["any_key"],
#             })
#             cprint("  Skipping, nothing to do!","yellow")
#             return False
        
#         self.c.functions.print_header_title({
#             "line1": f"OLD: {old_profile}",
#             "line2": f"NEW: {new_profile}",
#             "clear": False,
#             "show_titles": False,
#         })
            
#         notice = [
#             ["",1], [ "NOTICE ",0,"blue,on_yellow","bold,underline"], 
#             ["The Node's",0,"yellow"],["service name",0,"cyan","underline"], ["has not changed.",2,"yellow"],
#             ["Although this is",0],["not",0,"yellow","bold,underline"],
#             ["an issue and your Node will not be affected; moreover, this is being conveyed in case the Node Administrator wants to correlate the",0],
#             ["service name",0,"cyan","underline"], ["with the",0], ["profile name",0,"cyan","underline"], [".",2]
#         ]
        
#         confirm_notice = self.confirm_with_word({
#             "notice": notice,
#             "action": "change",
#             "word": "YES",
#             "profile": new_profile,
#             "default": "n"
#         })
#         if not confirm_notice:
#             return False

#         self.profile_details["profile_name"] = new_profile
#         # change the key for the profiles
#         self.c.config_obj[new_profile] = self.c.config_obj.pop(old_profile)
#         self.config_obj[new_profile] = self.config_obj.pop(old_profile)
        
#         dir_progress = {
#             "text_start": "updating directory structure",
#             "status_color": "yellow",
#             "newline": True,
#         }
#         dirs = ["snapshots","backups","uploads"]
#         self.c.functions.print_cmd_status({
#             "text_start": "Update data link dependencies",
#             "status_color": "green",
#             "status": "complete",
#             "newline": True,
#         })
#         for replace_link_p in self.c.config_obj.keys():
#             if self.c.config_obj[replace_link_p]["gl0_link_profile"] == old_profile:
#                 self.config_obj[replace_link_p]["link_profile"] = new_profile
#             for dir_p in dirs:
#                 if old_profile in self.config_obj[replace_link_p][dir_p]: 
#                     self.c.functions.print_cmd_status({
#                         **dir_progress,
#                         "status": dir_p,
#                     })
#                     dir_value = self.config_obj[replace_link_p][dir_p]
#                     self.config_obj[replace_link_p][dir_p] = dir_value.replace(old_profile,new_profile)
                
#         self.build_service_file({
#             "profiles": [new_profile],
#             "action": "Updating",
#             "rebuild": False,
#         })
        
#         progress = {
#             "text_start": f"Changing profile name {old_profile}",
#             "brackets": new_profile,
#             "status": "running"
#         }
#         self.c.functions.print_cmd_status(progress)
#         self.log.logger.debug(f"configurator edit request - moving [{old_profile}] to [{new_profile}]")
        
#         try:
#             system(f"mv /var/tessellation/{old_profile}/ /var/tessellation/{new_profile}/ > /dev/null 2>&1")
#             pass
#         except:
#             self.error_messages.error_code_messages({
#                 "error_code": "cfr-2275",
#                 "line_code": "not_new_install",
#             })

#         self.c.functions.print_cmd_status({
#             **progress,
#             "status": "complete",
#         })  
        
#         self.log.logger.info(f"Changed profile names | new [{new_profile}] -> old [{old_profile}]")
#         return True                  

    
    def edit_service_name(self, profile):
        self.manual_build_service(profile)
        self.cleanup_service_file_msg()
        self.cleanup_service_files()
        # self.c.config_obj[profile]["service"] = self.profile_details["service"]
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
        if self.c.profile_obj[profile]["enable"] == True:
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
            if enable_disable == "enable":
                new = "True"; new_v = "disable" 
                old_v = "enable"
            else:
                new = "False"; new_v = "enable"
                old_v = "disable"
            
            confirmation = self.edit_confirm_choice(new_v,old_v,"enable", profile)
            if confirmation:
                self.profile_details["enable"] = new
                return True
            return False

        
#     def edit_confirm_choice(self, old, new, section, profile):
#         self.c.functions.print_paragraphs([
#             ["",1],["For section [",0], [section,-1,"yellow","bold"], ["]",-1],["",1],
#             ["Are you sure you want to change [",-1], [old,-1,"red","bold"], ["] to [",-1], [new,-1,"green","bold"],["]?",-1],["",1]
#         ])   
        
#         if self.c.functions.confirm_action({
#             "yes_no_default": "y",
#             "return_on": "y",
#             "prompt": f"Confirm choice to {new}?",
#             "exit_if": False
#         }):
#             warning_confirm = True
#             if section == "enable" and new == "disable":
#                 for replace_link_p in self.c.config_obj.keys():
#                     if self.c.config_obj[replace_link_p]["gl0_link_profile"] == profile:
#                         self.c.functions.print_paragraphs([
#                             [" WARNING ",0,"red,on_yellow"], ["Selected Profile [",0], [replace_link_p,-1,"yellow"], 
#                             ["] seems to be reliant on [",-1], [profile,-1,"yellow","bold"], ["]. Continuing will",-1],
#                             ["introduce possible errors.  Either remove the dependent profile from the other profiles before",0],
#                             ["continuing, quit, or proceed with this understanding.",2]
#                         ])
#                         warning_confirm = self.c.functions.confirm_action({
#                             "yes_no_default": "n",
#                             "return_on": "y",
#                             "prompt": f"Still perform {new}?",
#                             "prompt_color": "red",
#                             "exit_if": False
#                         })
#             if warning_confirm:        
#                 return True
#         cprint("  Action cancelled","red")
#         return False
    
          
#     def edit_globals(self):
#         pass
    
    
#     # =====================================================
#     # OTHER
#     # =====================================================
    
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
                backup_dir = "/var/tessellation/nodectl"
                                
            self.c.functions.print_cmd_status(progress)
            if path.isfile(f"/var/tessellation/nodectl/cn-config.yaml"):
                self.backup_file_found = True
                c_time = self.c.functions.get_date_time({"action":"datetime"})
                if not path.isdir(backup_dir):
                    makedirs(backup_dir)
                backup_dir = self.c.functions.cleaner(backup_dir,"trailing_backslash")
                dest = f"{backup_dir}/cn-config_{c_time}"
                system(f"cp /var/tessellation/nodectl/cn-config.yaml {dest} > /dev/null 2>&1")
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
                
            self.c.functions.print_any_key({})

        self.is_file_backedup = True       


#     def show_help(self):
#         cli = CLI({
#             "caller": "config",
#             "config_obj": self.c.config_obj,
#             "ip_address": None,
#             "command": "help",
#             "version_obj": None
#         })
        
#         cli.version_obj = cli.functions.get_version({"which": "nodectl_all"})
        
#         cli.functions.print_help({
#                 "nodectl_version_only": True,
#                 "title": True,
#                 "extended": "configure",
#                 "usage_only": False,
#                 "hint": False,
#         })
       
    
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
        self.log.logger.info("configuator is verifying old profile cleanup.")
        
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
            user_confirm = self.c.functions.confirm_action({
                "yes_no_default": "y",
                "return_on": "y",
                "prompt": "Remove old profiles?",
                "exit_if": False
            })    
            if user_confirm:
                for profile in clean_up_old_list:
                    system(f"sudo rm -rf /var/tessellation/{profile} > /dev/null 2>&1")
                    self.log.logger.info(f"configuration removed abandend profile [{profile}]")      
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
        
        
    def cleanup_service_files(self):
        cleanup = False
        clean_up_old_list, remove_profiles_from_cleanup = [], []
        self.log.logger.info("configuator is verifying old service file cleanup.")
        
        self.c.functions.print_header_title({
            "line1": "CLEAN UP OLD SERVICE FILES",
            "single_line": True,
            "newline": "both"
        })
        
        if self.print_old_file_warning("profiles"): return
            
        for old_profile in self.old_last_cnconfig.keys():
            if old_profile not in self.config_obj.keys():
                if "global" not in old_profile:
                    cleanup = True
                    if self.action == "new" or old_profile == self.profile_to_edit:
                        clean_up_old_list.append(old_profile)
                    self.log.logger.warn(f"configuration found abandoned profile [{old_profile}]")
        
        clean_up_old_list2 = copy(clean_up_old_list)
        for old_profile in clean_up_old_list2:
            if self.c.config_obj[old_profile]["service"] == self.old_last_cnconfig[old_profile]["service"]:
                clean_up_old_list.pop(clean_up_old_list.index(old_profile))
            else:
                self.c.functions.print_cmd_status({
                    "text_start": "Abandoned",
                    "brackets": self.old_last_cnconfig[old_profile]["service"],
                    "text_end": "service",
                    "status": "found",
                    "color": "red",
                    "newline": True,
                })
                    
        if cleanup and len(clean_up_old_list) > 0:
            self.c.functions.print_paragraphs([
                ["It is recommended to clean up old services files. to:",1,"magenta"],
                ["  - Avoid conflicts",1],
                ["  - Avoid undesired Node behavior",1],
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
                    self.log.logger.info(f"configuration removed abandend service file [{service_name}]")      
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
        self.log.logger.info("configuator is verifying snapshot data directory existance and contents.")
                    
        # this will look at the new configuration and if it sees that a config
        # with the same name (or the same config) has data snapshots, it will
        # offer to remove them.
        
        self.c.functions.print_header_title({
            "line1": "MANAGE OLD SNAPSHOTS",
            "single_line": True,
            "newline": "both"
        })        
        
        for profile in self.metagraph_list:
            found_snap = False
            if self.config_obj[profile]["layer"] == "1":
                if not path.isdir(f"/var/tessellation/{profile}/"):
                    makedirs(f"/var/tessellation/{profile}/")
            elif self.config_obj[profile]["layer"] < 1:
                found_snap_list = [
                    f"/var/tessellation/{profile}/data/snapshot",
                    f"/var/tessellation/{profile}/data/incremental_snapshot",
                    f"/var/tessellation/{profile}/data/incremental_snapshot_tmp",
                ]
                
                for lookup_path in found_snap_list:
                    test = listdir(lookup_path)
                    if path.isdir(lookup_path) and listdir(lookup_path):
                        self.log.logger.warn("configurator found snapshots during creation of a new configuration.")
                        found_snap = True
                    elif not path.isdir(lookup_path):
                        makedirs(lookup_path)
                
                    if found_snap:
                        found_snap = False
                        lookup_path_abbrv = lookup_path.split("/")[-1]
                        self.log.logger.info("configuartor cleaning up old snapshots")
                        self.c.functions.print_paragraphs([
                            ["",1], ["An existing",0], ["snapshot",0,"cyan","bold"],
                            ["directory structure exists",1], 
                            ["profile:",0], [profile,1,"yellow"],
                            ["snapshot dir:",0], [lookup_path_abbrv,1,"yellow"],
                            ["Existing old snapshots may cause unexpected errors and conflicts, nodectl will remove snapshot contents from this directory",2,"red","bold"],
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
                            if not path.isdir(lookup_path):
                                makedirs(lookup_path)
                            self.c.functions.print_cmd_status({
                                **progress,
                                "status": "complete",
                                "status_color": "green",
                                "newline": True,
                            })  
                            sleep(1.5) # allow Node Operator to see results
                        else:
                            self.log.logger.critical("during build of a new configuration, snapshots may have been found and Node Operator declined to remove, unexpected issues by arise.")                  
        
        
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


    def print_error(self):
        self.c.functions.print_paragraphs([
            ["",1], [" ERROR ",0,"grey,on_red","bold"],
            ["During the configuration editing session [",0,"red"],
            [self.called_option,-1,"yellow","bold"], ["] an incorrect input was detected",-1,"red"],["",2],
            
            [" HINT ",0,"grey,on_yellow","bold"], ["If",0,"cyan","bold"], ["attempting to change directory structure or any elements,",0],
            ["the directory structure must exist already.",2],
            
            ["Please review the nodectl logs and/or Node operator notes and try again",2],
            
            ["You can also attempt to restore your",0,"magenta"], ["cn-config.yaml",0,"yellow","bold"], ["from backups.",2,"magenta"]
        ])
        
        if not self.is_new_config:
            self.c.functions.print_any_key({})
            self.edit_profile_sections("RETRY")
        else:
            exit(1)
        
    
    def validate_config(self,profile):
        verified = True
        self.c.build_yaml_dict()
        self.c.setup_config_vars()
        verified = self.c.validate_profile_types(profile,True)

        if not verified:
            self.log.logger.error(self.edit_error_msg)
            self.print_error()   
                  

#     def confirm_with_word(self,command_obj):
#         notice = command_obj.get("notice",False)
#         word = command_obj.get("word")
#         action = command_obj.get("action")
#         profile = command_obj.get("profile")
#         default = command_obj.get("default","n")  # "y" or "n"
        
#         confirm_str = f"{colored(f'  Confirm {action} by entering exactly [','cyan')} {colored(f'YES-{profile}','green')} {colored(']','cyan')}: "
#         confirm = input(confirm_str)
        
#         def word_any_key(prompt):
#             print("")
#             self.c.functions.get_user_keypress({
#                 "prompt": prompt,
#                 "prompt_color": "red",
#                 "options": ["any_key"],
#             })      
                  
#         if f"{word}-{profile}" == confirm:
#             if self.detailed:
#                 self.c.functions.print_paragraphs(notice)

#             if notice:
#                 confirm_notice = self.c.functions.confirm_action({
#                     "yes_no_default": default,
#                     "return_on": "y",
#                     "prompt": "Continue?",
#                     "exit_if": False
#                 })
#                 if not confirm_notice:
#                     word_any_key("action cancelled by Node Operator, press any key")
#                     return False    
                
#             return True
        
#         word_any_key("confirmation phrase did not match, cancelling operation, press any key")
#         return False
        
            
#     def convert_config_obj(self):
#         # self.c.functions.print_json_debug(self.config_obj,False)
        
#         sections = deepcopy(self.c.test_dict)
#         sections.pop("top"); sections.pop("profiles")
#         sections["java"] = ["java_jvm_xms","java_jvm_xms","java_jvm_xms"]
#         sections["gl0_link"][0] = "gl0_enable"
#         singles = ["enable","layer","environment","service","node_type","description"]
        
#         for profile in self.c.config_obj.keys():
#             for section in self.c.config_obj[profile].keys():
#                 if section in singles:
#                   self.c.config_obj[profile][section] = self.profile_details[section]

#             for subsection in sections:
#                 for item in sections[subsection]:
#                     self.c.config_obj[profile][subsection][item] = self.profile_details[item]
        

    def handle_service(self,profile,s_type):
        # user will be notified to do a full restart at the of the process
        # to return to the network instead of doing it here.  This will ensure
        # all updates are enabled/activated/updated.
        
        self.c.functions.config_obj = self.node_service.config_obj
        self.c.functions.profile_names = self.metagraph_list
        self.c.functions.get_service_status()
        service = self.c.config_obj[profile]["service"]
        self.node_service.profile = profile
        
        actions = ["leave","stop"]
        for s_action in actions:
            if self.node_service.config_obj["global_elements"]["node_service_status"][profile] == "inactive (dead)":
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
                self.c.functions.print_timer(40,"to gracefully leave the network")
                    
        self.c.functions.print_cmd_status({
            "text_start": "Updating Service",
            "brackets": f"{service} => {s_action}",
            "text_end": s_type,
            "status": "complete",
            "status_color": "green",
            "newline": True
        })   
        
    
#     def is_duplicate_profile(self,profile_name):
#         for profile in self.config_obj.keys():
#             if profile_name == profile:
#                 return True   
#         return False
    
                         
#     def move_config_backups(self):
#         # move any backup configs out of the config dir and into the backup dir
#         backup_dir = "empty"
        
#         try:
#             for key in self.c.config_obj.keys():
#                 backup_dir = self.c.config_obj[key]["directory_backups"]
#                 break
#         except: # global
#             for key in self.config_obj.keys():
#                 backup_dir = self.config_obj[key]["backups"]
#                 break 
                       
#         if backup_dir == "default":
#             backup_dir = "/var/tessellation/backups/"  
                  
#         if backup_dir == "empty":
#             self.log.logger.warn("backup migration skipped.")
#             if self.detailed:
#                 self.c.functions.print_paragraphs([
#                     ["",1],["Configuration not moved to proper backup directory due to cancellation request.",1,"red"],
#                     ["location retained:",0,"red"], [f"{self.config_path}",1,"yellow","bold"],
#                     ["Configurations may contain sensitive information, please handle removal manually.",1,"magenta"]
#                 ])
#                 self.c.functions.print_any_key({})
#         else:
#             system(f"mv {self.config_path}cn-config_yaml_* {backup_dir} > /dev/null 2>&1")
#             self.log.logger.info("configurator migrated all [cn-config.yaml] backups to first known backup directory")

        
    def ask_review_config(self):
        user_confirm = self.c.functions.confirm_action({
            "yes_no_default": "y",
            "return_on": "y",
            "prompt": "Review the created configuration?",
            "exit_if": False
        })   
        if user_confirm:           
            self.c.view_yaml_config("migrate")     
            

    def quit_configurator(self):
        cprint("  Configurator exited upon Node Operator request","green")
        exit(0)             
        
                          
if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")
import uuid
from os import environ, path, system, makedirs, mkdir, getcwd, remove, chmod
from re import match, search
from shutil import copy2, move
from time import sleep
from getpass import getpass
from termcolor import colored, cprint
from types import SimpleNamespace
from uuid import uuid4
from random import randint
from .functions import Functions
from .troubleshoot.errors import Error_codes
from .troubleshoot.logger import Logging
from .config.versioning import Versioning

class P12Class():
        
    def __init__(self,command_obj):

        self.log = Logging()
        
        self.id_file_name = "id_ecdsa.hex"
        self.p12_file_location = ""
        self.p12_filename = ""
        self.p12_password = ""
        
        self.app_env = command_obj.get("app_env","")
        self.profile = command_obj.get("profile","global")
        self.existing_p12 = command_obj.get("existing_p12",False) # installation migration
        self.user = command_obj.get("user_obj",None)
        self.cli = command_obj.get("cli_obj",None)
        self.process = command_obj.get("process",None)
        self.functions = command_obj["functions"]
        self.version_obj = self.functions.version_obj
        self.config_obj = self.functions.config_obj 

        try:
            self.log_key = self.config_obj["global_elements"]["log_key"]
        except:
            self.log_key = "main"

        self.profile = self.functions.default_profile
        self.quick_install = False
        self.p12_migration = False
        self.pass_quit_request = False
        self.solo = False # part of install or solo request to create p12
        self.secure_mount_exists = False

        self.error_messages = Error_codes(self.functions) 
        self.handle_pass_file(False)

        if "profile" in command_obj:
            self.profile = command_obj["profile"]

        if not self.app_env and self.process != "install":                  
            try:
                self.app_env = self.config_obj[self.profile]["environment"]
            except Exception as e:
                try:
                    self.app_env = self.config_obj["global_elements"]["metagraph_name"]
                except Exception as ee: 
                    self.error_messages.error_code_messages({
                        "error_code": "p-51",
                        "line_code": "config_error",
                        "extra": "format",
                        "extra2": f"config keys missing | {e} | {ee}"
                    })
  

    def set_p12_alias(self,profile):
        key = "p12_alias"
        if profile == "global_p12": key = "key_alias"
        if isinstance(self.config_obj[profile][key],bool):
            self.config_obj[profile][key] = self.show_p12_details(["-p",profile,"--return","--alias","--installer",self.p12_password]) 


    def generate_p12_file(self): 
        # used for install, upgrade, and solo
        self.ask_for_p12name()     
        self.ask_for_keyphrase()
        self.ask_for_file_alias()
        
        if self.solo:
            self.ask_for_location() 
        if not self.existing_p12:
            self.generate()
        elif self.solo and self.process != "install":
            self.generate() 
     

    def validate_value(self,pattern,value):
        if match(pattern,value):
            return True
        return False
    
    
    def ask_for_location(self):
        try:
            self.p12_file_location = self.config_obj["global_p12"]["key_store"]
        except:
            self.existing_p12 = False
            
        if not self.existing_p12:
            self.p12_file_location = f"/home/{self.user.username}/tessellation/"
            # path will be created if it doesn't exist at p12 generation (generate method)
            self.functions.print_clear_line()
            self.functions.print_paragraphs([
                ["",1], ["Default location for your p12 file storage created.",1],
            ])
        if self.existing_p12:
            self.p12_file_location, _ = path.split(self.existing_p12)

        self.functions.print_paragraphs([
            ["location:",0], [self.p12_file_location,2,"yellow"],
            ["Note",0,"grey,on_yellow"], ["The default location can be modified.",1,"white","bold"],
            ["sudo nodectl configure",2],
        ])
        

    def ask_for_p12name(self):
        if self.existing_p12:
            self.p12_file_location, self.p12_filename = path.split(self.existing_p12)
            return
            
        if not self.quick_install:
            self.functions.print_header_title({
            "line1": "P12 GENERATION",
            "newline": "top", 
            "show_titles": False,
            "clear": True,
            })
        default_value = f"{self.user.username}-node.p12"
        
        def test_for_exist():
            p12_full_path = f"/home/{self.user.username}/tessellation/{self.p12_filename}"

            if path.exists(p12_full_path):
                status = "skipped"
                status_color = "red"
                self.functions.print_paragraphs([
                    [" WARNING ",0,"white,on_red"], ["existing p12 found.",1,"red"],
                    ["p12 found:",0,"blue",'bold'],[p12_full_path,1,"yellow"],
                ])
                cprint("  Existing p12 file found.","red",attrs=["bold"])
                confirm = self.functions.confirm_action({
                    "yes_no_default": "y",
                    "return_on": "y",
                    "prompt": "remove existing p12?",
                    "exit_if": False
                })
                progress = {
                    "text_start": "removing",
                    "brackets": self.p12_filename,
                    "status": "running",
                    "status_color": "yellow",
                }
                self.functions.print_cmd_status(progress)
                if confirm:
                    if path.isfile(p12_full_path): remove(p12_full_path)
                    status = "complete"
                    status_color = "green"
                    
                self.functions.print_cmd_status({
                    **progress,
                    "status": status,
                    "status_color": status_color,
                    "newline": True,
                })

                if confirm: return True

                self.functions.print_paragraphs([
                    [" WARNING ",0,"white,on_red"], ["existing p12 not removed",1,"red"],
                ])
                confirm = self.functions.confirm_action({
                    "yes_no_default": "y",
                    "return_on": "y",
                    "prompt": "Continue?",
                    "exit_if": True
                })

                return False
            return True
            
        while True:
            cprint("  Please enter a name for your p12","magenta")
            ask_question = colored("  private key file [","magenta")+colored(default_value,"yellow",attrs=["bold"])+colored("] : ","magenta")
            value = input(ask_question)
            if value == "" or not value:
                self.p12_filename = default_value
                if test_for_exist(): break
            else:
                prompt_str = colored("Please confirmed that: ",'cyan')+colored(value,"yellow",attrs=['bold'])+colored(" is correct","cyan")
                confirm = self.functions.confirm_action({
                    "yes_no_default": "y",
                    "return_on": "y",
                    "prompt": prompt_str,
                    "exit_if": False
                })
                if confirm:
                    self.p12_filename = value
                    test_for_exist()
                    if self.validate_value(r"^[a-zA-Z0-9](?:[a-zA-Z0-9 ._-]*[a-zA-Z0-9])?\.[a-zA-Z0-9_-]+$",self.p12_filename):
                        self.log.logger[self.log_key].info(f"p12 file accepted [{value}]")
                        break
                    self.log.logger[self.log_key].warning("invalid p12 file name inputted")
                    cprint("  File name seems invalid, try again","red")

       
    def ask_for_file_alias(self):
        self.functions.print_paragraphs([
            ["",1], ["Please create or supply a simple name to help you remember your",0],
            ["p12's",0,"yellow"], ["private key name.",1],
        ])

        try:
            if self.existing_p12: 
                default_alias = self.show_p12_details(["--file",self.existing_p12,"--return","--alias","--installer",self.p12_password])
                self.functions.print_paragraphs([
                    ["nodectl found an existing alias:",0],[default_alias,1,"yellow"],
                ])
            else: 
                default_alias = f"{self.user.username}-alias"
        except:
            self.log.logger[self.log_key].error("unable to determine alias")
            default_alias = f"{self.user.username}-alias"

        while True:
            cprint("  Please enter the alias name for your p12","magenta")
            ask_question = colored("  private key [","magenta")+colored(default_alias,"yellow",attrs=["bold"])+colored("] : ","magenta")
            alias = input(ask_question)
            if alias == "":
                alias = default_alias
                break
            else:
                prompt_str = colored("Please confirmed that: ",'cyan')+colored(alias,"yellow",attrs=['bold'])+colored(" is correct","cyan")
                confirm = self.functions.confirm_action({
                    "yes_no_default": "y",
                    "return_on": "y",
                    "prompt": prompt_str,
                    "exit_if": False
                })
                if confirm:
                    self.log.logger[self.log_key].info(f"p12 alias accepted [{alias}]")
                    break
                
        self.key_alias = alias


    def ask_for_keyphrase(self):
        p12_verb = "create a"
        if self.existing_p12:
            p12_verb = "verify the"

        if self.quick_install:
            self.functions.print_paragraphs([
                [f"We need to {p12_verb} passphrase for our p12 file.",1],
            ])
        elif not self.existing_p12:
            self.user.print_password_descriptions(10,"passphrase",True)
            self.functions.print_paragraphs([
                ["This passphrase will allow you to authenticate to the",0], ["Hypergrpah",0,"yellow","bold"],[".",-1],["",1],
                ["This passphrase will allow you to authenticate to your Node's",0], ["Wallet",0,"yellow","bold"],[".",-1],["",1],
                [f"You should {p12_verb}",0], ["unique",0,"yellow","bold"], ["passphrase and write it down!",2],
                ["We recommend you save this to a secure location and, do",0], ["NOT",0,"yellow,on_red","bold,underline"],
                ["forget the passphrase!",2],
                ["In your notes:",1,"white","bold"],
                ["\"This is the passphrase to access my Node's",0,"magenta"],["hot",0,"red","bold"],
                ["wallet and gain access to the Hypergraph.\"",2,"magenta"],
            ])

        self.log.logger[self.log_key].info("p12 passphrase input requested")
        
        for attempt in range(1,4):
            self.p12_password = self.user.get_verify_password(10,"your p12 private key","passphrase")
            if self.p12_migration:
                self.path_to_p12 = path.dirname(self.existing_p12)+"/"
                self.p12_filename = path.basename(self.existing_p12)
                self.entered_p12_keyphrase = self.p12_password

                existing_unlock = self.unlock()
                if not existing_unlock:
                    self.log.logger[self.log_key].warning(f"p12 passphrase invalid, unable to access private keystore [{attempt}] of [3]")
                    self.functions.print_cmd_status({
                        "text_start": "Unable to unlock p12",
                        "brackets": f"{attempt} of 3",
                        "status": "Try Again" if attempt < 3 else "Failed",
                        "status_color": "magenta" if attempt < 3 else "red",
                        "newline": True,
                    })
                    if attempt > 2:
                        self.functions.print_paragraphs([
                            ["",1], [" WARNING ",0,"yellow,on_red"], ["The p12 passphrase responsible for digital",0,"red"],
                            ["signatures and authentication challenges against the cluster, including the retrieval of the public node ID,",0,"red"],
                            ["appears to be",0,"red"], ["invalid.",2,"red","bold"], 

                            ["nodectl does not allow",0,"yellow"], ["sectional signs",0,"red"],["or",0,"yellow"],["spaces",0,"red"], 
                            ["in the passphrase string.",2,"yellow"],

                            ["To ensure best practices, pertaining to the use of nodectl, it is recommended to change your passphrase used to unlock your p12 keystore to one that does not",0],
                            ["contain these characters.",1],
                            ["Command:",0,"yellow"],["sudo nodectl passwd12",2,"blue","bold"],

                            ["The installation may continue; however, retrieval of the p12 keystore details will fail.",0,"magenta"],
                            ["Please use the",0,"magenta"], ["configurator",0,"yellow"], ["to update your passphrase at the",0,"magenta"],
                            ["conclusion of the installation:",1,"magenta"],
                            ["Command:",0,"yellow"],["sudo nodectl configure",2,"blue","bold"],
                        ])

                        self.functions.confirm_action({
                            "prompt": "Continue installation?",
                            "yes_no_default": "y",
                            "return_on": "y",
                            "exit_if": True
                        })
                        break
                else:
                    self.functions.print_cmd_status({
                        "text_start": "Migrating",
                        "brackets": "p12 keystore",
                        "status": "unlocked",
                        "status_color": "green",
                        "newline": True,
                    })
                    break
            else:
                break

        
    def keyphrase_validate(self,command_obj):
        operation = command_obj["operation"]
        passwd = command_obj.get("passwd",False)
        caller = command_obj.get("caller",False)
        profile = command_obj.get("profile","global")
        mobile = command_obj.get("mobile",False)

        de, manual = False, False
        
        self.log.logger[self.log_key].info(f"p12 keyphrase validation process started")
        
        for attempts in range(0,5):
            if profile == "global":
                self.set_variables(True,None)      
                if self.config_obj["global_p12"]["encryption"] and not manual: 
                    de = True
            else:
                if not self.config_obj[profile]["global_p12_passphrase"] and self.config_obj[profile]["global_p12_encryption"]: de = True
                self.set_variables(False,profile)   
            
            try:
                if profile == "global" and passwd == False and self.config_obj["global_elements"]["global_upgrader"] == False:
                    if caller in ["export_private_key","view_config"]:
                        cprint("  This command requires manual re-entry of your p12 passphrase","yellow")
                    else:
                        cprint("  Global profile passphrase doesn't match, is incorrect, or is not found.","yellow")
            except:
                self.error_messages.error_code_messages({
                    "error_code": "p12-227",
                    "line_code": "invalid_passphrase"
                })
            
            if de: 
                if attempts < 1 and not passwd:
                    try:
                        passwd = self.config_obj["global_p12"]["passphrase"]
                    except:
                        passwd = False
                self.log.logger[self.log_key].debug(f"p12 keyphrase validation process - attempting decryption")
                for _ in range(0,4):
                    de_passwd = self.functions.get_persist_hash({
                        "pass1": passwd,
                        "profile": profile,
                        "enc_data": True,
                    })
                    if de_passwd:
                        passwd = de_passwd
                        break
                    sleep(.5)
                    passwd = self.config_obj["global_p12"]["passphrase"]
            if not passwd:
                if caller in ["export_private_key","view_config"]:
                    self.functions.print_paragraphs([
                        ["You may press",0],["q",0,"yellow"],["+",0],
                        ["<enter>",0,"yellow"],
                        ["to quit",1],
                    ])
                pass_ask = colored(f'  Please enter your p12 passphrase to validate','cyan')
                if profile != "global":
                    pass_ask += colored(f'\n  profile [','cyan')
                    pass_ask += colored(profile,'yellow',attrs=['bold'])
                    pass_ask += colored('] for','cyan')
                pass_ask += colored(f" {operation}: ","cyan")
                passwd = getpass(pass_ask,)
                passwd = passwd.strip()
                if passwd.lower() == "q" and caller in ["export_private_key","view_config"]:
                    self.pass_quit_request = True
                    return
                de, manual = False, True
            
            self.entered_p12_keyphrase = passwd
                
            valid = self.unlock()
            if valid:
                if operation == "config_file" and manual == True:
                    self.config_obj["global_elements"]["p12_cli_pass_global"] = True
                    if profile == "global":
                        self.config_obj["global_p12"]["passphrase"] = passwd
                        if self.config_obj["global_elements"]["all_global"]:
                            for pass_profile in self.config_obj.keys():
                                if "global" not in pass_profile:
                                    self.config_obj[pass_profile]["p12_passphrase"] = passwd
                    else:
                        self.config_obj[profile]["p12_passphrase"] = passwd
                if "global" in profile:
                    self.config_obj["global_p12"]["p12_validated"] = valid
                else:
                    self.config_obj[profile]["p12_validated"] = valid
                break

            self.log.logger[self.log_key].warning(f"invalid keyphrase entered [{attempts}] of 3")
            if attempts > 0 or mobile:
                if mobile:
                    attempts += 1
                self.functions.print_clear_line()
                print(f"{colored('  Passphrase invalid, please try again attempt [','red',attrs=['bold'])}{colored(attempts,'yellow')}{colored('] of 3','red',attrs=['bold'])}")
            passwd = False
            
            if attempts > 2:
                self.error_messages.error_code_messages({
                    "error_code": "p-146",
                    "line_code": "invalid_passphrase",
                    "extra": None,
                    "extra2": None
                })        
        
        if self.process != "service_restart":
            self.functions.print_cmd_status({
                "text_start": "P12 file keyphrase (passphrase)",
                "brackets": profile,
                "status": "validated!",
                "status_color": "green",
            })                
            sleep(1.3)

        if operation == "upgrade":
            print("") # overcome '\r'
        return self.entered_p12_keyphrase
                

    def handle_pass_file(self,create=True):
        nodectl_secure_mount = "/mnt/nodectlsecure"
        if self.functions.get_distro_details()["info"]["wsl"]:
            nodectl_secure_mount = f"/tmp/nodectlsecure"

        def remove():
            self.functions.remove_files(
                f"{nodectl_secure_mount}/*", 
                "cleanup_function",
                True, False, True,
            )

        if create:
            if not self.secure_mount_exists:
                with open("/proc/mounts","r") as found_mounts:
                    f_mount = found_mounts.read()
                    if nodectl_secure_mount in f_mount:
                        self.secure_mount_exists = True
            if not self.secure_mount_exists:
                if not path.exists(nodectl_secure_mount): #double check
                    mkdir(nodectl_secure_mount)
                    chmod(nodectl_secure_mount,0o700)
                _ = self.functions.process_command({
                    "bashCommand": f"sudo mount -t tmpfs -o size=1M,mode=0700 tmpfs {nodectl_secure_mount}",
                    "proc_action": "subprocess_run_check_only",
                })    

            passfile = f"{nodectl_secure_mount}/{uuid4()}"
            for n in range(0,3):
                try:
                    with open(passfile,"w") as f:
                        f.write(self.entered_p12_keyphrase)
                    chmod(passfile,0o600)
                except:
                    self.log.logger[self.log_key].error("handle_pass_file -> error with passphrase authentication file write.")
                    if n > 0:
                        self.error_messages.error_code_messages({
                            "error_code": "p-441",
                            "line_code": "open_file",
                            "extra": "/mnt/nodectlsecure/*",
                            "extra2": "file_write",
                        })
                    remove()
            return passfile
        else:
            remove()


    def unlock(self):
        return_result = False
        passfile = self.handle_pass_file()

        bashCommand1 = f"openssl pkcs12 -in {self.path_to_p12}{self.p12_filename} -clcerts -nokeys -passin file:{passfile}"
        
        # check p12 against method 1
        results = self.functions.process_command({
            "bashCommand": bashCommand1,
            "proc_action": "wait", 
            "return_error": True
        })
        if "friendlyName" in str(results):
            self.log.logger[self.log_key].info("p12 file unlocked successfully - [openssl]")
            return_result = True
        
        # check p12 against method 2
        if not return_result:
            self.log.logger[self.log_key].error("p12 file unlocked failed with method 1 [openssl]")
            bashCommand2 = f"keytool -list -v -keystore {self.path_to_p12}{self.p12_filename} -storepass:file {passfile} -storetype PKCS12"
            bashCommand2 = self.functions.handle_java_prefix(bashCommand2)
            results = self.functions.process_command({
                "bashCommand": bashCommand2,
                "proc_action": "wait"
            })
            if "Valid from:" in str(results):
                self.log.logger[self.log_key].info("p12 file unlocked successfully - keytool")
                return_result = True
        
        # check p12 against method 3
        if not return_result:
            self.log.logger[self.log_key].error("p12 file unlocked failed with method 2 [keytool]")
            bashCommand = "openssl version"
            results = self.functions.process_command({
                "bashCommand": bashCommand,
                "proc_action": "subprocess_co", 
                "return_error": True
            })
            if "OpenSSL 3" in results:        
                bashCommand3 = bashCommand1.replace("pkcs12","pkcs12 -provider default -provider legacy")
                results = self.functions.process_command({
                    "bashCommand": bashCommand3,
                    "proc_action": "wait", 
                    "return_error": True
                })
                if not "invalid password" in str(results.lower()) and not "error" in str(results.lower()):
                    self.log.logger[self.log_key].info("p12 file unlocked successfully - openssl")
                    return_result = True
                else:
                    self.log.logger[self.log_key].error("p12 file unlocked failed with method 3a [openssl legacy]")
            else:
                msg = "p12 -> attempt to authenticate via nodectl with 4 different methods and failed. Unable to process because the SSL version is out-of-date, "
                msg += f"consider upgrading the distributions OpenSSL package. | version found [{results.strip()}]"
                self.log.logger[self.log_key].error("p12 file unlocked failed with all attempts.")
                self.log.logger[self.log_key].warning(msg)
        
        self.handle_pass_file(False)
        if not return_result: 
            self.log.logger[self.log_key].info("p12 file authentication failed - keytool and openssl tried")
        return return_result

      
    def set_variables(self,is_global,profile):
        # version >= 1.11.0
        self.log.logger[self.log_key].info("p12 file importing variables.")
        try:
            if is_global:
                self.path_to_p12 = self.config_obj["global_p12"]["key_location"]
                self.p12_filename = self.config_obj["global_p12"]["key_name"]
            else:
                self.path_to_p12 = self.config_obj[profile]["p12_key_location"]
                self.p12_filename = self.config_obj[profile]["p12_key_name"]

            if not self.path_to_p12.endswith("/"):
                self.path_to_p12 = f"{self.path_to_p12}/"
        except Exception as e:
            self.log.logger[self.log_key].critical(f"P12Class -> set variables -> unable to scrap valid entries from configuration [{e}]")
            self.error_messages.error_code_messages({
                "error_code": "p-494",
                "line_code": "invalid_configuration_request",
                "extra": "p12 location details",
            })
        
        
    def export_private_key_from_p12(self):
        is_global = True if self.profile == "global" else False
        self.extract_export_config_env({
            "global": is_global,
            "profile": self.profile,
        })
        id_hex_file = f"{self.path_to_p12}{self.id_file_name}"
        id_file_exists = path.exists(id_hex_file)
        if id_file_exists:
            remove(id_hex_file)
            
        bashCommand = f"/usr/bin/java -jar /var/tessellation/cl-keytool.jar export"
        _ = self.functions.process_command({
            "bashCommand": bashCommand,
            "proc_action": "subprocess_devnull",
        })

        try:
            f = open(id_hex_file,"r")
        except:
             self.error_messages.error_code_messages({
                "error_code": "p-432",
                "line_code": "open_file",
                "extra": "id_hex_file",
                "extra2": None
            })   

        hex_result = f.readline()
        
        self.functions.print_header_title({
            "line1": "ECDSA HEX ID VALUE EXPORTED",
            "line2": "KEEP PRIVATE! - DANGER!",
            "clear": True,
        })

        self.functions.print_paragraphs([
            ["Export Operation Complete. You can 'swipe' the id displayed below to add it to your clipboard",2],
            [" WARNING ",0,"yellow,on_red","bold"], ["THIS IS YOUR PRIVATE KEY",1,"red","bold,underline"],
            ["DO NOT EXPOSE TO ANYONE, AS YOUR",0,"red"], ["HOT WALLET",0,"red","underline"],
            ["AND NODE CAN BE COMPROMISED!",2,"red"],
            
            ["PRIVATE KEY FOR [",0], [self.p12_filename,-1,"yellow","bold"], ["]",-1], ["",1],
            ["=","full","white","bold"],
            [hex_result,1,"green","bold"],
            ["=","full","white", "bold"], ["",1],
            
        ])

        self.log.logger[self.log_key].info("p12 file private key request completed.")
        
        f.close()
        if path.isfile(id_hex_file): 
            remove(id_hex_file)
        
        
    def extract_export_config_env(self,command_obj):
        # is_global=(bool) - use global vars or profile
        # profile=(str) - profile needed

        is_global = command_obj.get("global",True)
        profile = command_obj.get("profile",False)
        env_vars = command_obj.get("env_vars",False)
        return_success = command_obj.get("return_success",False)
        ext_p12 = command_obj.get("ext_p12",False)
        caller = command_obj.get("caller",False)
        self.log.logger[self.log_key].debug(f"p12 --> config environment export requested by [{caller}]")

        pass1 = None
        enc = False
        
        if ext_p12:
            self.p12_file_location = self.path_to_p12 = path.split(ext_p12)[0]
            self.p12_filename = path.split(ext_p12)[1]
            self.functions.print_paragraphs([
                [f"File:",0,"yellow"],[self.p12_filename,1],
            ])
            self.key_alias, self.p12_password = self.show_p12_details(["--file",ext_p12,"--return","--alias","--passphrase"])
            env_vars = True
        else:    
            p_sub_key = "p12_passphrase"
            if is_global or self.config_obj[profile]["global_p12_passphrase"]: 
                profile = "global_p12"
                p_sub_key = "passphrase"

            if self.process != "install" and not self.solo:
                if self.config_obj["global_p12"]["encryption"]:
                    enc = True
                    if env_vars: pass1 = self.p12_password
                    else: pass1 = self.config_obj[profile][p_sub_key]
                    pass1 = self.functions.get_persist_hash({
                        "pass1": pass1,
                        "profile": profile,
                        "enc_data": True,
                    }) 
                else: pass1 = self.config_obj[profile][p_sub_key]   

        if env_vars:
            environ['CL_STOREPASS'] = f"{pass1}" if enc else f"{self.p12_password}"
            # used for p12 generation on install of solo p12 build
            environ['CL_KEYSTORE'] = f"{self.p12_file_location}/{self.p12_filename}"
            environ['CL_KEYPASS'] = f"{self.p12_password}"
            environ['CL_PASSWORD'] = f"{self.p12_password}"
            environ['CL_KEYALIAS'] = f"{self.key_alias}"
            return

        indiv_p12_obj = {"passphrase": pass1}
        try:
            indiv_p12_obj["key_alias"] = self.config_obj[profile]["key_alias"]
        except:
            indiv_p12_obj["key_alias"] = self.show_p12_details(["-p", profile, "--alias", "--return", "--config"])

        try:
            for skey in ["nodeadmin","key_location","key_name","key_store"]:
                p12_key = skey
                if profile != "global_p12": skey = f"p12_{skey}"
                indiv_p12_obj[p12_key] = self.config_obj[profile][skey] 
        except Exception as e:
            self.log.logger[self.log_key].critical(f"extract_export_config_env -> unable to extract p12 details from configuration. [{e}]")
            self.error_messages.error_code_messages({
                "error_code": "p-508",
                "line_code": "invalid_passphrase",
                "extra2": "wrong",
            })

        self.log.logger[self.log_key].info("p12 file exporting p12 details into env variables.")
            
        passes = ["CL_PASSWORD","CL_KEYPASS","CL_STOREPASS"]
        for key in passes:
            environ[key] = indiv_p12_obj["passphrase"]
            
        try:
            environ["CL_KEYALIAS"] = indiv_p12_obj["key_alias"]
        except Exception as e:
            self.log.logger[self.log_key].critical(f"unable to load environment variables for p12 extraction. | error [{e}] error_code [p-504]")
            if return_success: return False
            self.error_messages.error_code_messages({
                "error_code": "p-504",
                "line_code": "config_error",
                "extra": "format"
            })

        try:
            environ["CL_KEYSTORE"] = indiv_p12_obj["key_store"]
        except Exception as e:
            self.log.logger[self.log_key].critical(f"unable to load environment variables for p12 extraction. | error [{e}] error_code [p-514]")
            if return_success: return False
            self.error_messages.error_code_messages({
                "error_code": "p-514",
                "line_code": "config_error",
                "extra": "format"
            })
        self.path_to_p12 = indiv_p12_obj["key_location"]
        self.p12_username = indiv_p12_obj["nodeadmin"]
        self.p12_filename = indiv_p12_obj["key_name"]

        return True # if command is not looking for bool, will be ignored.

                  
    def generate(self):
        print_exists_warning = False
        if not self.quick_install:
            progress = {
                "text_start": "Generating p12",
                "brackets": self.p12_filename,
                "status": "running"
            }
            self.functions.print_cmd_status(progress)

        self.extract_export_config_env({
            "env_vars": True,
            "caller": "generate",
        })

        if path.isfile(f"{self.p12_file_location}/{self.p12_filename}"):
            if self.quick_install:
                self.log.logger[self.log_key].warning(f"quick install found an existing p12 file, removing old file.  Node operator was warned prior to installation. removing [{self.p12_file_location}/{self.p12_filename}].")
                if path.isfile(f"{self.p12_file_location}/{self.p12_filename}"):
                    remove(f"{self.p12_file_location}/{self.p12_filename}")
            else:
                self.log.logger[self.log_key].warning(f"p12 file already found so process skipped [{self.p12_file_location}/{self.p12_filename}].")
                print_exists_warning = True
                result = "exists skipping"
                color = "magenta"
        elif not path.exists(self.p12_file_location):
            self.log.logger[self.log_key].info(f"p12 file path being created {self.p12_file_location}")
            makedirs(self.p12_file_location)
            self.log.logger[self.log_key].info(f"p12 file ownership permissions set {self.p12_file_location}/{self.p12_filename}")
            self.functions.set_chown(self.p12_file_location,self.user.username,self.user.username)
              
        self.log.logger[self.log_key].info(f"p12 file creation initiated {self.p12_file_location}/{self.p12_filename}")  
        # do not use sudo here otherwise the env variables will not be associated
        bashCommand = "/usr/bin/java -jar /var/tessellation/cl-keytool.jar generate"
        result = self.functions.process_command(({
            "bashCommand": bashCommand,
            "proc_action": "timeout"
        }))

        self.log.logger[self.log_key].info(f"p12 file permissions set {self.p12_file_location}/{self.p12_filename}")
        self.functions.set_chown(f"{self.p12_file_location}/{self.p12_filename}",self.user.username, self.user.username)
        chmod(f"{self.p12_file_location}/{self.p12_filename}",0o400)
        result = "completed"
        color = "green"

        if not self.quick_install:
            self.functions.print_cmd_status({
                **progress,
                "status": result,
                "status_color": color,
                "newline": True
            })
            if print_exists_warning:
                self.functions.print_paragraphs([
                    ["",1], [" WARNING ",2,"yellow,on_red"], 
                    ["You have chosen a p12 file name that already exists on the system.  If your",0,"yellow"], 
                    ["passphrase",0,"yellow","bold"], ["is not the same as the previous passphrase, this installation will fail.",2],
                    ["Recommendation",0], [f"Remove the previous p12 file and restart the {self.cli.command_obj['caller']}",1,"yellow"]
                ])

        
    def change_passphrase(self,command_obj):
        p12_key_name = command_obj.get("p12_key_name")
        p12_location = command_obj.get("p12_location")
        p12_location = f"{p12_location}{p12_key_name}"
        org_pass = command_obj.get("original")
        new_pass = command_obj.get("new")
        
        self.functions.print_paragraphs([
            ["private key file (p12):",0,"white","bold"],
            [p12_location,1,"yellow"]
        ])
        self.log.logger[self.log_key].info(f"p12 file passphrase change initiated [{p12_location}]")
        
        temp_p12_file = "/tmp/cnng-temporary.p12"
        p12_file_exists = path.exists(temp_p12_file)
        if p12_file_exists:
            remove(temp_p12_file)
        
        # backup old p12 file
        datetime = self.functions.get_date_time({"action":"datetime"})
        self.log.logger[self.log_key].info(f"p12 file backup created [{p12_location}{datetime}.bak]")
        
        profile = self.functions.pull_profile({
            "req": "default_profile"
        })
        backup_dir = self.config_obj[profile]["directory_backups"]
        p12_key_name_bk = p12_key_name.replace(".p12","_")
        if path.exists(p12_location):
            copy2(p12_location,f"{backup_dir}{p12_key_name_bk}{datetime}.p12.bak")
        else:
            self.error_messages.error_code_messages({
                "error_code": "p-350",
                "line_code": "file_not_found",
                "extra": f"{p12_location}",
                "extra2": None
            })    
        
        # change passphrase
        bashCommand = f"keytool -importkeystore "
        bashCommand = self.functions.handle_java_prefix(bashCommand)
        bashCommand = f"sudo {bashCommand}"
        bashCommand += f"-srckeystore {p12_location} -srcstoretype PKCS12 "
        bashCommand += f"-srcstorepass {org_pass} "
        bashCommand += f"-destkeystore {temp_p12_file} -deststoretype PKCS12 "
        bashCommand += f"-deststorepass {new_pass} -destkeypass {new_pass}"

        results = self.functions.process_command(({
            "bashCommand": bashCommand,
            "proc_action": "wait"
        }))
        if "error" in results:
            self.log.logger[self.log_key].error("p12 passphrase update failed")
            if path.isfile(temp_p12_file): remove(temp_p12_file)
            return results
        
        # migrate new p12 into place
        if path.isfile(temp_p12_file):
            move(temp_p12_file,p12_location)     
        return "success"
        
        
    def show_p12_details(self, command_list):
            
        # Define the keys for the dictionary
        p12_values = [
            "alias", "owner", "owner_cn", "iowner", "iowner_cn", "sha1", "sha256", "sig_alg", 
            "pub_alg", "version", "value", "entry_number", "creation_date", "entry_type"
        ]
        p12_output_dict = {key: "unknown" for key in p12_values}
        passfile, return_alias, return_pass, alias_only = False, False, False, False


        def attempt_decrypt(profile,p12_passwd):
            enc_profile = "Unknown"
            if self.config_obj["global_elements"]["all_global"]: enc_profile = "global"
            else: enc_profile = profile
            p12_passwd = self.functions.get_persist_hash({
                "pass1": p12_passwd,
                "profile": enc_profile,
                "enc_data": True,
            })
            return p12_passwd 


        if "--passphrase" in command_list:
            return_pass = True
        if "--alias" in command_list:
            if "--return" in command_list: return_alias = True
            alias_only = True

        if "--file" in command_list:
            p12_location = command_list[command_list.index("--file")+1]
        elif "-p" in command_list:
            profile = command_list[command_list.index("-p")+1]
            if profile != "global_p12" and self.config_obj[profile]["global_p12_passphrase"]: 
                profile = "global_p12"
            if profile == "global_p12":
                p12_location = self.config_obj[profile]["key_store"]    
                p12_passwd = self.config_obj[profile]["passphrase"]
            else:
                p12_location = self.config_obj[profile]["p12_key_store"]    
                p12_passwd = self.config_obj[profile]["p12_passphrase"]
        else:
            command_list.append("help")
            self.functions.check_for_help(command_list,"show_p12_details")
            
        if not path.exists(p12_location):
            if "--config" in command_list:
                return False
            self.error_messages.error_code_messages({
                "error_code": "p-568",
                "line_code": "open_file",
                "extra": p12_location,
                "extra2": "p12",
            })
            
        self.log.logger[self.log_key].info(f"show_p12_details -> initiated - p12 file location [{p12_location}]")
        
        if "--installer" in command_list:
            p12_passwd = command_list[command_list.index("--installer")+1]
            try: 
                _ = self.config_obj["global_p12"]["encryption"]
            except:
                self.config_obj = {
                    **self.config_obj,
                    "global_p12": {
                        "encryption": False,
                    }
                }
        elif "--file" in command_list:
            pass_ask = colored(f'  Please enter your p12 passphrase to validate: ','cyan')
            p12_passwd = getpass(pass_ask,)

        elif self.config_obj["global_p12"]["encryption"] and not self.solo:
            p12_passwd = attempt_decrypt(profile,p12_passwd.strip())

        self.entered_p12_keyphrase = p12_passwd
        for _ in range(0,2):
            if not path.isfile(passfile):
                passfile = self.handle_pass_file()
            
            bashCommand = f"keytool -list -v -keystore {p12_location} -storepass:file {passfile} -storetype PKCS12"
            bashCommand = self.functions.handle_java_prefix(bashCommand)
            result_str = self.functions.process_command({
                "bashCommand": bashCommand,
                "proc_action": "timeout",
            })
            results = result_str.split("\n")
            if not "keytool error" in result_str:
                break
            try:
                p12_passwd = attempt_decrypt(profile,p12_passwd)
                self.entered_p12_keyphrase = p12_passwd
            except Exception as e:
                self.handle_pass_file(False)
                self.log.logger[self.log_key].critical(f"p12 module was unable to process this p12 file [{e}]")
                if "--installer" in command_list: raise Exception
                self.error_messages.error_code_messages({
                    "error_code": "p-725",
                    "line_code": "invalid_passphrase",
                })
            finally:
                self.handle_pass_file(False)
        self.handle_pass_file(False)

        if not results or results == "":
            if "--config" in command_list:
                return False
            self.functions.print_paragraphs([
                ["nodectl was not able to process this p12 file?",2,"red","bold"],
            ])
            exit(0)
      
        for item in results:
            if "keystore contains" in item:
                p12_output_dict["entry_number"] = item.split(" ")[-2].strip()
                continue
            value = item.split(":")[-1].strip()

            if "keytool error" in item:
                self.log.logger[self.log_key].error(f"p12 -> show_p12_details p12 authentication issue: error [{value}] p12 file [{p12_location}]") 
                if self.process == "install": return
                self.error_messages.error_code_messages({
                    "error_code": "p-603",
                    "line_code": "invalid_passphrase",
                    "extra": value+" or decryption error. See nodectl logs.",
                })

            elif "Alias name" in item: 
                p12_output_dict["alias"] = item.split(":")[-1].strip()
            elif "Creation date" in item:
                p12_output_dict["creation_date"] = item.split(":")[-1].strip()
            elif "Entry type" in item:
                p12_output_dict["entry_type"] = item.split(":")[-1].strip()
            elif "Owner" in item:
                owner = value.split(",")[0]
                p12_output_dict["owner"] = owner.split("=")[-1]
                owner_cn = value.split(",")[-1]
                p12_output_dict["owner_cn"] = owner_cn.split("=")[-1]
            elif "Issuer" in item:
                iowner = value.split(",")[0]
                p12_output_dict["iowner"] = iowner.split("=")[-1]
                iowner_cn = value.split(",")[-1]
                p12_output_dict["iowner_cn"] = iowner_cn.split("=")[-1]
            elif "SHA1" in item:
                p12_output_dict["sha1"] = item.split(":",1)[-1].strip()
            elif "SHA256" in item:
                p12_output_dict["sha256"] = item.split(":",1)[-1].strip()
            elif "Signature algorithm" in item:
                p12_output_dict["sig_alg"] = value
            elif "Public Key" in item:
                p12_output_dict["pub_alg"] = value
            elif "Version" in item:
                p12_output_dict["version"] = value
                
        p12_dir = path.dirname(p12_location)
        if p12_dir == "": p12_dir = getcwd()
        
        if not "--installer" in command_list and not "--config" in command_list:
            self.functions.print_paragraphs([
                ["",1],["  P12 FILE DETAILS  ",2,"blue,on_yellow","bold"],
            ])

        if return_alias and return_pass:
            return (p12_output_dict["alias"],p12_passwd)
        elif return_alias: return p12_output_dict["alias"]
        elif return_pass: return p12_passwd

        if alias_only:
            print_out_list = [
                {
                    "header_elements": {
                        "P12 NAME": path.basename(p12_location),
                        "P12 ALIAS": colored(p12_output_dict["alias"],"green"),
                    },
                },                
            ]
        else:
            if self.solo: 
                self.p12_file_location = path.split(p12_location)[0]
                self.p12_filename = path.split(p12_location)[1]
                self.p12_password = p12_passwd
                self.key_alias = p12_output_dict["alias"]
                self.extract_export_config_env({
                    "env_vars": True,
                    "caller": "show_p12_details",
                })
                cmd = "/usr/bin/java -jar /var/tessellation/cl-wallet.jar show-id"
                node_id = self.functions.process_command({
                    "bashCommand": cmd,
                    "proc_action": "poll"
                })
                node_id = node_id.strip()
            print_out_list = [
                {
                    "header_elements": {
                        "P12 NAME": path.basename(p12_location),
                        "P12 LOCATION": p12_dir,
                    },
                    "spacing": 25,
                },                
                {
                    "SHA1 FINGER PRINT": p12_output_dict["sha1"],
                },                
                {
                    "SHA256 FINGER PRINT": p12_output_dict["sha256"],
                },                
                {
                    "P12 ALIAS": colored(p12_output_dict["alias"],"green"),
                },                
                {
                    "header_elements": {
                        "CREATED": p12_output_dict["creation_date"],
                        "VERSION": p12_output_dict["version"],
                        "KEYS FOUND": p12_output_dict["entry_number"],
                    },
                    "spacing": 18,
                },                
                {
                    "header_elements": {
                        "ENTRY TYPE": p12_output_dict["entry_type"],
                        "SIGNATURE ALGO": p12_output_dict["sig_alg"],
                        "PUBLIC ALGO": p12_output_dict["pub_alg"],
                    },
                    "spacing": 18,
                },                
                {
                    "header_elements": {
                        "OWNER": p12_output_dict["owner"],
                        "COMMON NAME": p12_output_dict["owner_cn"],
                    },
                    "spacing": 25,
                },                
                {
                    "header_elements": {
                        "ISSUER": p12_output_dict["iowner"],
                        "COMMON NAME": p12_output_dict["iowner_cn"],
                    },
                    "spacing": 25,
                },                
                {
                    "header_elements": {
                        "NODE ID": node_id,
                    },
                    "spacing": 25,
                },                
            ]
        
        for header_elements in print_out_list:
            self.functions.print_show_output({
                "header_elements" : header_elements
            })
            
        pass
                
    
    def create_individual_p12(self, cli):
        
        if "--username" in cli.command_list:
            p12_username = cli.command_list[cli.command_list.index("--username")+1]
        else:
            p12_username = self.config_obj["global_p12"]["nodeadmin"]
            
        if "--location" in cli.command_list:
            self.p12_file_location = cli.command_list[cli.command_list.index("--location")+1]
            if self.p12_file_location[-1] != "/":
                self.p12_file_location = self.p12_file_location+"/"
        else:
            self.p12_file_location = self.config_obj["global_p12"]["key_location"]

        try:
            with open('/etc/passwd', 'r') as passwd_file:
                test = any(line.startswith(p12_username + ':') for line in passwd_file)
                if not test:
                    raise FileNotFoundError
        except FileNotFoundError:
            self.error_messages.error_code_messages({
                "error_code": "p-709",
                "line_code": "invalid_user",
                "extra": "individual p12 creation",
                "extra2": p12_username,
            })
        
        if not path.exists(self.p12_file_location):
            self.error_messages.error_code_messages({
                "error_code": "p-719",
                "line_code": "file_not_found",
                "extra": self.p12_file_location,
                "extra2": "verify the location you entered exists or in the configuration is valid.",
            })

        if "--file" in cli.command_list:
            self.p12_file_location += cli.command_list[cli.command_list.index("--file")+1]
            if path.isfile(self.p12_file_location):
                self.functions.print_paragraphs([
                      [" WARNING ",0,"white,on_red"], ["nodectl found an existing",0,"red"],
                      ["file with the same name.  If you continue, that file will be",0,"red"],
                      ["removed permanently by being overwritten.",1,"red"],  
                    ])
                self.functions.confirm_action({
                    "prompt": "Overwrite existing p12?",
                    "yes_no_default": "y",
                    "return_on": "y",
                    "exit_if": True
                })
            self.existing_p12 = self.p12_file_location               

        from .user import UserClass
        self.user = UserClass(cli)
        self.user.username = p12_username
        
        self.cli = {"command_obj": {"caller": "create_p12"}}
        self.cli = SimpleNamespace(**self.cli)
        self.generate_p12_file()    
        
        self.functions.confirm_action({
            "prompt": "Review the details of your new p12 file?",
            "yes_no_default": "y",
            "return_on": "y",
            "exit_if": True
        })

        if self.p12_file_location[-1] != "/": self.p12_file_location += "/"
        self.show_p12_details(["--file",self.p12_file_location+self.p12_filename])
        
             
if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")
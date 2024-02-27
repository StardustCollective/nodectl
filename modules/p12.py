from os import environ, path, system, makedirs, getcwd
from re import match

from time import sleep
from getpass import getpass
from termcolor import colored, cprint
from types import SimpleNamespace

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
        self.profile = self.functions.default_profile
        self.quick_install = False
        self.solo = False # part of install or solo request to create p12

        self.error_messages = Error_codes(self.functions) 
        
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
            self.p12_file_location, self.p12_file = path.split(self.existing_p12)
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
                    system(f"sudo rm {p12_full_path} > /dev/null 2>&1")
                    status = "complete"
                    status_color = "green"
                    
                self.functions.print_cmd_status({
                    **progress,
                    "status": status,
                    "status_color": status_color,
                    "newline": True,
                })
                if not confirm:
                    self.functions.print_paragraphs([
                      [" WARNING ",0,"white,on_red"], ["exising p12 not removed",0,"red"],
                      ["unexpected results may ensue...",1,"red"],  
                    ])
                
        while True:
            cprint("  Please enter a name for your p12","magenta")
            ask_question = colored("  private key file [","magenta")+colored(default_value,"yellow",attrs=["bold"])+colored("] : ","magenta")
            value = input(ask_question)
            if value == "" or not value:
                self.p12_filename = default_value
                test_for_exist()
                break
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
                    if self.validate_value("^[a-zA-Z0-9](?:[a-zA-Z0-9 ._-]*[a-zA-Z0-9])?\.[a-zA-Z0-9_-]+$",self.p12_filename):
                        self.log.logger.info(f"p12 file accepted [{value}]")
                        break
                    self.log.logger.warn("invalid p12 file name inputted")
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
            self.log.logger.error("unable to determine alias")
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
                    self.log.logger.info(f"p12 alias accepted [{alias}]")
                    break
                
        self.key_alias = alias


    def ask_for_keyphrase(self):
        if self.quick_install:
            self.functions.print_paragraphs([
                ["We need to create passphrase for our p12 file.",1],
            ])
        else:
            self.user.print_password_descriptions(10,"passphrase",True)
            self.functions.print_paragraphs([
                ["This passphrase will allow you to authenticate to the",0], ["Hypergrpah",0,"yellow","bold"],[".",-1],["",1],
                ["This passphrase will allow you to authenticate to your Node's",0], ["Wallet",0,"yellow","bold"],[".",-1],["",1],
                ["You should create a",0], ["unique",0,"yellow","bold"], ["passphrase and write it down!",2],
                ["We recommend you save this to a secure location and, do",0], ["NOT",0,"yellow,on_red","bold,underline"],
                ["forget the passphrase!",2],
                ["In your notes:",1,"white","bold"],
                ["\"This is the passphrase to access my Node's",0,"magenta"],["hot",0,"red","bold"],
                ["wallet and gain access to the Hypergraph.\"",2,"magenta"],
            ])

        self.log.logger.info("p12 passphrase input requested")
        
        if self.existing_p12:
            self.user.migrating_p12 = True
        self.p12_password = self.user.get_verify_password(10,"your p12 private key","passphrase")
        
        
    def keyphrase_validate(self,command_obj):
        operation = command_obj["operation"]
        passwd = command_obj.get("passwd",False)
        profile = command_obj.get("profile","global")
        de, manual = False, False
        
        self.log.logger.info(f"p12 keyphrase validation process started")
        
        for attempts in range(1,4):
            if profile == "global":
                self.set_variables(True,None)      
                if self.config_obj["global_p12"]["encryption"]: de = True
            else:
                if not self.config_obj[profile]["global_p12_password"] and ["profile_p12_encryption"]: de = True
                self.set_variables(False,profile)   
            
            try:
                if profile == "global" and passwd == False and self.config_obj["global_elements"]["global_upgrader"] == False:
                    cprint("  Global profile passphrase doesn't match, is incorrect, or is not found.","yellow")
            except:
                self.error_messages.error_code_messages({
                    "error_code": "p12-227",
                    "line_code": "invalid_passphrase"
                })
            
            if de: 
                passwd = self.functions.get_persist_hash({
                    "pass1": passwd,
                    "profile": profile,
                    "enc_data": True,
                })
            if not passwd:
                pass_ask = colored(f'  Please enter your p12 passphrase to validate','cyan')
                if profile != "global":
                    pass_ask += colored(f'\n  profile [','cyan')
                    pass_ask += colored(profile,'yellow',attrs=['bold'])
                    pass_ask += colored('] for','cyan')
                pass_ask += colored(f" {operation}: ","cyan")
                passwd = getpass(pass_ask,)
                passwd = passwd.strip()
                manual = True
            
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

            self.log.logger.warn(f"invalid keyphrase entered [{attempts}] of 3")
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
                

    def unlock(self):
        bashCommand1 = f"openssl pkcs12 -in '{self.path_to_p12}{self.p12_file}' -clcerts -nokeys -passin 'pass:{self.entered_p12_keyphrase}'"
        
        # check p12 against method 1
        results = self.functions.process_command({
            "bashCommand": bashCommand1,
            "proc_action": "wait", 
            "return_error": True
        })
        if not "Invalid password" in str(results):
            self.log.logger.info("p12 file unlocked successfully - openssl")
            return True
        
        # check p12 against method 2
        bashCommand2 = f"keytool -list -v -keystore {self.path_to_p12}{self.p12_file} -storepass {self.entered_p12_keyphrase} -storetype PKCS12"
        results = self.functions.process_command({
            "bashCommand": bashCommand2,
            "proc_action": "wait"
        })
        if "Valid from:" in str(results):
            self.log.logger.info("p12 file unlocked successfully - keytool")
            return True
        
        # check p12 against method 3
        bashCommand = "openssl version"
        results = self.functions.process_command({
            "bashCommand": bashCommand,
            "proc_action": "subprocess_co", 
            "return_error": True
        })
        if "OpenSSL 3" in results:        
            bashCommand3 = bashCommand1.replace("pkcs12","pkcs12 -legacy")
            results = self.functions.process_command({
                "bashCommand": bashCommand3,
                "proc_action": "wait", 
                "return_error": True
            })
            if not "Invalid password" in str(results):
                self.log.logger.info("p12 file unlocked successfully - openssl")
                return True
        else:
            msg = "p12 -> attempt to authenticate via nodectl method 3 (of 3) with '-legacy' option failed. Unable to process because the SSL version is out-of-date, "
            msg += f"consider upgrading the distributions OpenSSL package. | version found [{results.strip()}]"
            self.log.logger.warn(msg)
        
        self.log.logger.info("p12 file authentication failed - keytool and openssl tried")
        return False

      
    def set_variables(self,is_global,profile):
        # version >= 1.11.0
        self.log.logger.info("p12 file importing variables.")
        if is_global:
            self.path_to_p12 = self.config_obj["global_p12"]["key_location"]
            self.p12_file = self.config_obj["global_p12"]["key_name"]
        else:
            self.path_to_p12 = self.config_obj[profile]["p12_key_location"]
            self.p12_file = self.config_obj[profile]["p12_key_name"]

        if not self.path_to_p12.endswith("/"):
            self.path_to_p12 = f"{self.path_to_p12}/"
        
        
    def export_private_key_from_p12(self):
        is_global = True if self.profile == "global" else False
        self.extract_export_config_env({
            "global": is_global,
            "profile": self.profile,
        })
        id_hex_file = f"{self.path_to_p12}{self.id_file_name}"
        id_file_exists = path.exists(id_hex_file)
        if id_file_exists:
            system(f"rm {id_hex_file} > /dev/null 2>&1")
            
        bashCommand = f"java -jar /var/tessellation/cl-keytool.jar export"
        system(bashCommand)

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
            
            ["PRIVATE KEY FOR [",0], [self.p12_file,-1,"yellow","bold"], ["]",-1], ["",1],
            ["=","full","white","bold"],
            [hex_result,1,"green","bold"],
            ["=","full","white", "bold"], ["",1],
            
        ])

        self.log.logger.info("p12 file private key request completed.")
        
        f.close()
        bashCommand = f"rm -f {id_hex_file} > /dev/null 2>&1"
        system(bashCommand)
        
        
    def extract_export_config_env(self,command_obj):
        # is_global=(bool) - use global vars or profile
        # profile=(str) - profile needed

        is_global = command_obj.get("global",True)
        profile = command_obj.get("profile",False)
        env_vars = command_obj.get("env_vars",False)
        return_success = command_obj.get("return_success",False)

        pass1 = None
        enc = False

        p_sub_key = "p12_passprhase"
        if is_global: 
            profile = "global_p12"
            p_sub_key = "passphrase"

        if self.process != "install":
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
        skeys = ["nodeadmin","key_location","key_name","key_alias","key_store"]
        for skey in skeys:
            p12_key = skey
            if profile != "global_p12": skey = f"p12_{skey}"
            indiv_p12_obj[p12_key] = self.config_obj[profile][skey] 

        self.log.logger.info("p12 file exporting p12 details into env variables.")
            
        passes = ["CL_PASSWORD","CL_KEYPASS","CL_STOREPASS"]
        for key in passes:
            environ[key] = indiv_p12_obj["passphrase"]
            
        try:
            environ["CL_KEYALIAS"] = indiv_p12_obj["key_alias"]
        except Exception as e:
            self.log.logger.critical(f"unable to load environment variables for p12 extraction. | error [{e}] error_code [p-504]")
            if return_success: return False
            self.error_messages.error_code_messages({
                "error_code": "p-504",
                "line_code": "config_error",
                "extra": "format"
            })

        try:
            environ["CL_KEYSTORE"] = indiv_p12_obj["key_store"]
        except Exception as e:
            self.log.logger.critical(f"unable to load environment variables for p12 extraction. | error [{e}] error_code [p-514]")
            if return_success: return False
            self.error_messages.error_code_messages({
                "error_code": "p-514",
                "line_code": "config_error",
                "extra": "format"
            })
        self.path_to_p12 = indiv_p12_obj["key_location"]
        self.p12_username = indiv_p12_obj["nodeadmin"]
        self.p12_file = indiv_p12_obj["key_name"]

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

        self.extract_export_config_env({"env_vars":True})

        if path.isfile(f"{self.p12_file_location}/{self.p12_filename}"):
            if self.quick_install:
                self.log.logger.warn(f"quick install found an existing p12 file, removing old file.  Node operator was warned prior to installation. removing [{self.p12_file_location}/{self.p12_filename}].")
                system(f"sudo rm -f {self.p12_file_location}/{self.p12_filename} > /dev/null 2>&1")
            else:
                self.log.logger.warn(f"p12 file already found so process skipped [{self.p12_file_location}/{self.p12_filename}].")
                print_exists_warning = True
                result = "exists skipping"
                color = "magenta"
        elif not path.exists(self.p12_file_location):
            self.log.logger.info(f"p12 file path being created {self.p12_file_location}")
            makedirs(self.p12_file_location)
            self.log.logger.info(f"p12 file ownership permissions set {self.p12_file_location}/{self.p12_filename}")
            system(f"chown {self.user.username}:{self.user.username} {self.p12_file_location} > /dev/null 2>&1")
              
        self.log.logger.info(f"p12 file creation initiated {self.p12_file_location}/{self.p12_filename}")  
        # do not use sudo here otherwise the env variables will not be associated
        bashCommand = "java -jar /var/tessellation/cl-keytool.jar generate"
        self.functions.process_command(({
            "bashCommand": bashCommand,
            "proc_action": "timeout"
        }))

        self.log.logger.info(f"p12 file permissions set {self.p12_file_location}/{self.p12_filename}")
        system(f"chown {self.user.username}:{self.user.username} {self.p12_file_location}/{self.p12_filename} > /dev/null 2>&1")
        system(f"chmod 400 {self.p12_file_location}/{self.p12_filename} > /dev/null 2>&1")
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
        self.log.logger.info(f"p12 file passphrase change initiated [{p12_location}]")
        
        temp_p12_file = "/tmp/cnng-temporary.p12"
        p12_file_exists = path.exists(temp_p12_file)
        if p12_file_exists:
            system(f"rm {temp_p12_file} > /dev/null 2>&1")
        
        # backup old p12 file
        datetime = self.functions.get_date_time({"action":"datetime"})
        self.log.logger.info(f"p12 file backup created [{p12_location}{datetime}.bak]")
        
        profile = self.functions.pull_profile({
            "req": "default_profile"
        })
        backup_dir = self.config_obj[profile]["directory_backups"]
        p12_key_name_bk = p12_key_name.replace(".p12","_")
        if path.exists(p12_location):
            system(f"cp {p12_location} {backup_dir}{p12_key_name_bk}{datetime}.p12.bak > /dev/null 2>&1")
        else:
            self.error_messages.error_code_messages({
                "error_code": "p-350",
                "line_code": "file_not_found",
                "extra": f"{p12_location}",
                "extra2": None
            })    
        
        # change passphrase
        bashCommand = f"sudo keytool -importkeystore "
        bashCommand += f"-srckeystore {p12_location} -srcstoretype PKCS12 "
        bashCommand += f"-srcstorepass {org_pass} "
        bashCommand += f"-destkeystore {temp_p12_file} -deststoretype PKCS12 "
        bashCommand += f"-deststorepass {new_pass} -destkeypass {new_pass}"

        results = self.functions.process_command(({
            "bashCommand": bashCommand,
            "proc_action": "wait"
        }))
        if "error" in results:
            self.log.logger.error("p12 passphrase update failed")
            system(f"sudo rm {temp_p12_file} > /dev/null 2>&1")
            return results
        
        # migrate new p12 into place
        system(f"sudo mv {temp_p12_file} {p12_location} > /dev/null 2>&1")       
        return "success"
        
        
    def show_p12_details(self, command_list):
        alias, owner, owner_cn, iowner = "unknown", "unknown", "unknown", "unknown"
        sha1, sha256, sig_alg, pub_alg = "unknown", "unknown", "unknown", "unknown"
        version, value, entry_number = "unknown", "unknown", "unknown"
        return_alias, alias_only = False, False

        if "--alias" in command_list:
            if "--return" in command_list: return_alias = True
            alias_only = True

        if "--file" in command_list:
            p12_location = command_list[command_list.index("--file")+1]
        elif "-p" in command_list:
            profile = command_list[command_list.index("-p")+1]
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
            
        self.log.logger.info(f"show_p12_details -> initiated - p12 file location [{p12_location}]")
        
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

        if self.config_obj["global_p12"]["encryption"]:
            enc_profile = "Unknown"
            if self.config_obj["global_elements"]["all_global"]: enc_profile = "global"
            else: enc_profile = profile
            p12_passwd = self.functions.get_persist_hash({
                "pass1": p12_passwd,
                "profile": enc_profile,
                "enc_data": True,
            }) 

        bashCommand = f"keytool -list -v -keystore {p12_location} -storepass {p12_passwd} -storetype PKCS12" # > /dev/null 2>&1"
    
        results = self.functions.process_command({
            "bashCommand": bashCommand,
            "proc_action": "wait",
        })
        results = results.split("\n")

        if not results or results == "":
            if "--config" in command_list:
                return False
            self.functions.print_paragraphs([
                ["nodectl was not able to process this p12 file?",2,"red","bold"],
            ])
            exit(0)
      
        for item in results:
            if "keystore contains" in item:
                entry_number = item.split(" ")[-2].strip()
                continue
            value = item.split(":")[-1].strip()

            if "keytool error" in item:
                self.log.logger.error(f"p12 -> show_p12_details p12 authentication issue: error [{value}] p12 file [{p12_location}]") 
                if self.process == "install": return
                self.error_messages.error_code_messages({
                    "error_code": "p-603",
                    "line_code": "invalid_passphrase",
                    "extra": value+" or decryption error. See nodectl logs.",
                })

            elif "Alias name" in item: 
                alias = item.split(":")[-1].strip()
            elif "Creation date" in item:
                creation_date = item.split(":")[-1].strip()
            elif "Entry type" in item:
                entry_type = item.split(":")[-1].strip()
            elif "Owner" in item:
                owner = value.split(",")[0]
                owner = owner.split("=")[-1]
                owner_cn = value.split(",")[-1]
                owner_cn = owner_cn.split("=")[-1]
            elif "Issuer" in item:
                iowner = value.split(",")[0]
                iowner = iowner.split("=")[-1]
                iowner_cn = value.split(",")[-1]
                iowner_cn = iowner_cn.split("=")[-1]
            elif "SHA1" in item:
                sha1 = item.split(":",1)[-1].strip()
            elif "SHA256" in item:
                sha256 = item.split(":",1)[-1].strip()
            elif "Signature algorithm" in item:
                sig_alg = value
            elif "Public Key" in item:
                pub_alg = value
            elif "Version" in item:
                version = value
                
        p12_dir = path.dirname(p12_location)
        if p12_dir == "": p12_dir = getcwd()
        
        if not "--installer" in command_list and not "--config" in command_list:
            self.functions.print_paragraphs([
                ["",1],["  P12 FILE DETAILS  ",2,"blue,on_yellow","bold"],
            ])

        if return_alias: return alias

        if alias_only:
            print_out_list = [
                {
                    "header_elements": {
                        "P12 NAME": path.basename(p12_location),
                        "P12 ALIAS": colored(alias,"green"),
                    },
                },                
            ]
        else:
            print_out_list = [
                {
                    "header_elements": {
                        "P12 NAME": path.basename(p12_location),
                        "P12 LOCATION": p12_dir,
                    },
                    "spacing": 25,
                },                
                {
                    "SHA1 FINGER PRINT": sha1,
                },                
                {
                    "SHA256 FINGER PRINT": sha256,
                },                
                {
                    "P12 ALIAS": colored(alias,"green"),
                },                
                {
                    "header_elements": {
                        "CREATED": creation_date,
                        "VERSION": version,
                        "KEYS FOUND": entry_number,
                    },
                    "spacing": 18,
                },                
                {
                    "header_elements": {
                        "ENTRY TYPE": entry_type,
                        "SIGNATURE ALGO": sig_alg,
                        "PUBLIC ALGO": pub_alg,
                    },
                    "spacing": 18,
                },                
                {
                    "header_elements": {
                        "OWNER": owner,
                        "COMMON NAME": owner_cn,
                    },
                    "spacing": 25,
                },                
                {
                    "header_elements": {
                        "ISSUER": iowner,
                        "COMMON NAME": iowner_cn,
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

        from .user import UserClass
        self.user = UserClass(cli,True)
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
        self.show_p12_details(["--file",self.p12_file_location+self.p12_filename])
        
             
if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")
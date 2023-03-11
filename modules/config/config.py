import yaml
import json

from termcolor import colored
from time import sleep
from copy import deepcopy
from re import match
from os import system, path, get_terminal_size
from sys import exit

from .migration import Migration
from ..troubleshoot.errors import Error_codes
from ..functions import Functions
from ..p12 import P12Class
from ..troubleshoot.logger import Logging

class Configuration():
    
    def __init__(self,command_obj):
        
        self.functions = Functions({
            "caller": "config",
            "sudo_rights": False
        })
        self.functions.check_sudo()
        
        self.log = Logging()
        self.log.logger.info("configuration setup initialized")
        
        self.argv_list = command_obj["argv_list"]
        

            
        if "help" in self.argv_list[0]:
            return

        self.config_obj = {}
        self.error_list = []
        self.error_found = False  # for configurator
        self.auto_restart = True if "auto_restart" in self.argv_list or "service_restart" in self.argv_list else False
        
        try:
            self.called_command = self.argv_list[1]
        except:
            self.called_command = "exit"
            
        # rebuild functions with errors and logging
        self.functions = Functions({
            "caller": "config",
        })

        self.error_messages = Error_codes() 
        
        execute = command_obj["implement"]
        self.action = command_obj["action"]
        self.yaml_file = '/var/tessellation/nodectl/cn-config.yaml'
        
        if "view" in self.action or self.action == "-vc":
            self.view_yaml_config("normal")
        
        self.validated = True
        self.profile_check = False

        skip_validation = ["configure","new_config","install"]
        self.do_validation = False if self.action in skip_validation else True

                
        self.current_layer = None
        self.profile_enable = {
            "profile": None,
            "enabled": True
        }
        
        if execute or self.do_validation:
            self.implement_config()
        

    def is_passphrase_required(self):
        passphrase_required_list = [
            "start","stop","upgrade","restart","check_seedlist",
            "nodeid","id","export_private_key",
            "leave","join", "upgrade",
            "passwd","clean_snapshots","clean_files",
            "auto_restart", "refresh_binaries","sec"
        ]                
        if self.called_command in passphrase_required_list:
            return True
        return False
    
    
    def implement_config(self):
        continue_list = ["normal","edit_config","edit_on_error"]
                
        self.build_yaml_dict()
        self.validate_yaml_keys()
        self.remove_disabled_profiles()
        self.setup_config_vars()
        if len(self.error_list) == 0:
            if self.action in continue_list:
                self.prepare_p12()
                if self.action != "edit_config":
                    self.setup_passwd()
                self.setup_self_settings()
        
        if self.do_validation:
            if len(self.error_list) == 0:
                result = self.validate_profiles()
                if result:
                    self.setup_schemas()
                    for profile in self.profiles:
                        self.verify_profile_keys(profile)
                    if self.validated:
                        self.validate_services()
                        self.validate_p12_exists()
                        self.validate_link_dependencies()
            else:
                self.validated = False
            self.print_report()

        if self.action not in continue_list:
            exit(0)
        if self.action == "edit_on_error":
            self.edit_on_error_args = ["-e"]
            return
        
        
    def build_yaml_dict(self,return_dict=False):
        while True:
            try:
                with open(self.yaml_file, 'r', encoding='utf-8') as f:
                    yaml_data = f.read()
            except:
                if path.isfile("/usr/local/bin/cn-node") and not path.isfile("/var/tessellation/nodectl/cn-config.yaml"):
                    if self.called_command != "upgrade":
                        self.error_messages.error_code_messages({
                            "error_code": "cfg-99",
                            "line_code": "upgrade_needed"
                        })
                    
                    self.migration()
                    self.do_validation = False
                else:
                    self.send_error("cfg-99") 
            else:
                break

        try:
            yaml_dict = yaml.safe_load(yaml_data)
        except Exception as e:
            continue_to_error = True
            self.log.logger.error(f"configuration file [cn-config.yaml] error code [cfg-32] not able to be loaded into memory, nodectl will attempt to issue a fix... | error: [{e}]")
            if "passphrase" in str(e):
                change_made = self.yaml_passphrase_fix()
                if change_made:
                    with open(self.yaml_file, 'r', encoding='utf-8') as f:
                        yaml_data = f.read()
                    try:
                        yaml_dict = yaml.safe_load(yaml_data)
                    except Exception as ee:
                        self.log.logger.critical(f"configuration file [cn-config.yaml] error code [cfg-32] not able to be loaded into memory, issue with formatting. | error: [{ee}]")
                    else:
                        continue_to_error = False

            if continue_to_error:
                self.error_messages.error_code_messages({
                    "error_code": "cfg-32",
                    "line_code": "config_error",
                    "extra": "format",
                    "extra2": None
                })      

        self.config_obj = {
            **self.config_obj,
            **yaml_dict["nodectl"]
        }
        
        if return_dict:
            return self.config_obj
        
        try:
            _ = json.dumps(yaml_dict, sort_keys=True, indent=4)
        except:
            self.log.logger.critical("configuration file [cn-config.yaml] error code [cfg-37] able to be formatted for reading, issue with formatting.")
            self.error_messages.error_code_messages({
                "error_code": "cfg-37",
                "line_code": "config_error",
                "extra": "format",
                "extra2": None
            }) 
        
        self.config_obj["global_cli_pass"] = False # initialize 
        self.config_obj["upgrader"] = False # initialize 
        self.config_obj["all_global"] = False # initialize 
        
        self.validate_global_setting()
        try:
            self.handle_global_passphrase()
        except KeyError:
            pass
        
        for profile in self.config_obj["profiles"].keys():
            for p12_key in self.config_obj["profiles"][profile]["p12"].keys():
                if self.action == "edit_config":
                    if "global" in p12_key:
                        self.config_obj["profiles"][profile]["p12"][p12_key] = False
                else:
                    if "global" not in p12_key and "global" in self.config_obj["profiles"][profile]["p12"][p12_key]:
                        self.config_obj["profiles"][profile]["p12"][p12_key] = self.config_obj["global_p12"][p12_key]

            self.config_obj["profiles"][profile]["p12"]["cli_pass"] = False # initialize
        

    def yaml_passphrase_fix(self):
        temp_file = "/var/tmp/cn-config_temp.yaml"
        skip_values = ["None","global",'"']
        system(f"cp {self.yaml_file} {temp_file} > /dev/null 2>&1")
        y_file = self.yaml_file.split("/")[-1]
        return_value = False
        
        progress = {
            "text_start": "Attempt to correct",
            "brackets": f"{y_file}",
            "status": "correcting",
            "status_color": "magenta",
        }
        self.functions.print_cmd_status(progress)
        
        f = open(self.yaml_file)
        
        with open(temp_file,'w') as fix_yaml:
            for n,line in enumerate(f):
                if n == 0:
                    if line != "---\n":
                        fix_yaml.write("---\n")
                if "passphrase" in line:
                    if not any([x in line for x in skip_values]):
                        if not '"' in line:
                            return_value = True
                            fix_line = line.split(":")
                            fix_line[1] = fix_line[1].replace("\n","")
                            fix_line[1] = f'"{fix_line[1][1::]}"\n'
                            line = f'{fix_line[0]}: {fix_line[1]}'
                fix_yaml.write(line)

        f.close()
        
        system(f"mv {temp_file} {self.yaml_file} > /dev/null 2>&1")
        self.functions.print_cmd_status({
            **progress,
            "status": "complete",
            "status_color": "green",
            "newline": True,
        })
        
        return return_value
        
        
    def migration(self):
        self.migrate = Migration({
            "config_obj": self.functions.config_obj
        })
        if self.migrate.migrate():
            self.view_yaml_config("migrate")
        

    def view_yaml_config(self,action):
        self.functions.print_header_title({
            "line1": "YAML CONFIGURATION",
            "line2": "cn-config.yaml review",
            "clear": True,
            "newline": "top"
        })
        
        if "--json" in self.argv_list:
            self.validated, self.do_validation = True, False
            self.action = "normal"
            self.implement_config()
            self.functions.print_clear_line()
            print(colored(json.dumps(self.config_obj,indent=3),"cyan",attrs=['bold']))
            exit(1)
            
        do_more = False if "-np" in self.argv_list else True
        console_size = get_terminal_size()
        more_break = round(console_size.lines)-15
        more = False
        
        if path.isfile("/var/tessellation/nodectl/cn-config.yaml"):
            with open("/var/tessellation/nodectl/cn-config.yaml","r") as file:
                for n,line in enumerate(file):
                    print(colored(line.strip("\n"),"blue",attrs=['bold']))
                    if do_more and n % more_break == 0 and n > 0:
                        more = self.functions.print_any_key({
                            "quit_option": "q",
                            "newline": "both",
                        })
                        if more:
                            break
            file.close()

            print(f'\n{"  ":=<50}')
            
            paragraph = [
                ["In the event you find an error, you can issue:",1,"yellow"],
                ["'sudo nodectl configure'",2],
                ["Direct editing of the",0,"red"],
                ["cn-config.yaml",0,"grey,on_yellow"],
                ["is",0,"red"], ["discouraged",0,"red","bold"],
                ["and could result in undesired or unexpected results.",1,"red"]
            ]
            self.functions.print_paragraphs(paragraph)
            print(f'{"  ":=<50}')
        else:
            self.send_error("cfg-220") 

        if action == "migrate":
            self.functions.print_any_key({})
            return
        exit(0)
                
        
    def handle_global_passphrase(self):
        # grab cli passphrase if present
        if "--pass" in self.argv_list:
            self.config_obj["global_cli_pass"] = True
            self.config_obj["global_p12"]["passphrase"] = self.argv_list[self.argv_list.index("--pass")+1]
            
        init = {}
        for profile in self.config_obj["profiles"].keys():
            for p12_key in self.config_obj["profiles"][profile]["p12"].keys():
                p12_item = self.config_obj["profiles"][profile]["p12"][p12_key]
                init[f"p12_{p12_key}_global"] = False
                if self.config_obj["profiles"][profile]["p12"][p12_key] == "global" and "cli" not in p12_item:
                    init[f"p12_{p12_key}_global"]= True
            
            for key, value in init.items():
                self.config_obj["profiles"][profile]["p12"][key] = value

            pass
                      
    
    def setup_config_vars(self):
        # sets up the automated values not present in the 
        # yaml file
        
        dirs = {
            "backups": "/var/tessellation/backups/",
            "uploads": "/var/tessellation/uploads/",
            "snapshots": "/var/tessellation/cnng-profile_name/data/snapshot/"
        }
        
        def create_path_variable(path, file):
            try:
                if path[-1] != "/":
                    path = f"{path}/{file}"
                else:
                    path = f"{path}{file}"
            except:
                return False
            return path

        def error_found():
            self.error_found = True
            self.error_list.append({
                "title": "section_missing",
                "section": "global",
                "profile": None,
                "type": "section",
                "key": "multiple",
                "value": "global_p12",
                "special_case": None
            }) 
                        
        try:
            self.config_obj["global_p12"]["key_store"] = create_path_variable(
                self.config_obj["global_p12"]["key_location"],
                self.config_obj["global_p12"]["p12_name"],
            ) 
        except:
            error_found()
        
        for profile in self.config_obj["profiles"].keys():
            # handle "global" key word
            # any keys that are global will be reset to the global value
            # setup the key_store dynamic value based on existing or new values
            try:
                self.config_obj["profiles"][profile]["p12"]["key_store"] = create_path_variable(
                    self.config_obj["profiles"][profile]["p12"]["key_location"],
                    self.config_obj["profiles"][profile]["p12"]["p12_name"]
                )
            except KeyError:
                    self.error_list.append({
                        "title": "section_missing",
                        "section": "global",
                        "profile": profile,
                        "type": "section",
                        "key": "multiple",
                        "value": "p12",
                        "special_case": None
                    })
                    
            # does the profile link through itself?
            try:
                self.config_obj["profiles"][profile]["layer0_link"]["is_self"] = True
                if self.config_obj["profiles"][profile]["layer0_link"]["link_profile"] == "None":
                    self.config_obj["profiles"][profile]["layer0_link"]["is_self"] = False
            except KeyError:
                    self.error_list.append({
                        "title": "section_missing",
                        "section": "global",
                        "profile": profile,
                        "type": "section",
                        "key": "link_profile",
                        "value": "link_profile",
                        "special_case": None
                    })
                    
            try:
                self.config_obj["profiles"][profile]["pro"]["seed_path"] = create_path_variable(
                    self.config_obj["profiles"][profile]["pro"]["seed_location"],
                    self.config_obj["profiles"][profile]["pro"]["seed_file"]
                )
            except KeyError:
                self.error_list.append({
                    "title": "section_missing",
                    "section": "pro",
                    "profile": profile,
                    "type": "section",
                    "key": "multiple",
                    "value": "p12",
                    "special_case": None
                })
                    
            for dir, location in dirs.items():
                if self.config_obj["profiles"][profile]["dirs"][dir] == "default":
                    if dir == "snapshots":
                        location = location.replace("cnng-profile_name",profile)
                    self.config_obj["profiles"][profile]["dirs"][dir] = location                    
                    
        self.config_obj["caller"] = None  # init key (used outside of this class)
            
            
    def prepare_p12(self):
        self.log.logger.debug("p12 passphrase setup...")
           
        p12_obj = {
            "caller": "config",
            "action": "normal_ops",
            "process": "normal_ops",
            "config_obj": self.config_obj,
        }
        self.p12 = P12Class(p12_obj)
                    
    
    def remove_disabled_profiles(self):
        remove_list = []
        for profile in self.config_obj["profiles"].keys():
            if not self.config_obj["profiles"][profile]["enable"]:
                if "edit_config" not in self.argv_list:
                    remove_list.append(profile)

        for profile in remove_list:
            self.config_obj["profiles"].pop(profile)

            
    def setup_passwd(self,force=False):
        def verify_passwd(passwd, profile):
            clear, top_new_line, show_titles = False, False, True 
            if profile == "global" and ( not self.config_obj["upgrader"] or self.argv_list[1] != "upgrade" ):
                clear = True
            if self.config_obj["upgrader"] or self.argv_list[1] == "upgrade":
                if profile != "global":
                    print("") # newline
                show_titles = False
                top_new_line = "top"
                
            if not passwd:
                self.functions.print_header_title({
                    "line1": "PASSPHRASE REQUIRED",
                    "line2": profile.upper(),
                    "clear": clear,
                    "show_titles": show_titles,
                    "newline": top_new_line
                })  
            
            self.p12.keyphrase_validate({
                "operation": "config_file",
                "profile": profile,
                "passwd": passwd,
            })   
            return  
            
        passwd = self.config_obj["global_p12"]["passphrase"]
        if passwd == None or passwd == "None":
            self.config_obj["global_cli_pass"] = True
            passwd = False

        if self.is_passphrase_required() or force:
            verify_passwd(passwd,"global")  
        
        if not self.config_obj["all_global"]:
            for profile in self.config_obj["profiles"].keys():
                # print(json.dumps(self.config_obj,indent=3))
                if not self.config_obj["profiles"][profile]["p12"]["p12_passphrase_global"]:
                    passwd = self.config_obj["profiles"][profile]["p12"]["passphrase"]
                    if passwd == "None" or passwd == None:
                        self.config_obj["profiles"][profile]["p12"]["cli_pass"] = True
                        passwd = False
                    if self.is_passphrase_required():
                        verify_passwd(passwd,profile)
        
    
    def setup_self_settings(self):
        # configuration key word "self" for linking to global l0
        def grab_nodeid(profile):
            pattern = "^[a-fA-F0-9]{128}$"
            self.p12.set_variables(False,profile)
            for _ in range(0,3):
                self.p12.extract_export_config_env({
                    "is_global": False,
                })
                cmd = "java -jar /var/tessellation/cl-wallet.jar show-id"
                self.nodeid = self.functions.process_command({
                    "bashCommand": cmd,
                    "proc_action": "poll"
                })
                if match(pattern,self.nodeid):
                    return True
                sleep(2)
            return False
                       
        write_out = False
        attempts = 0
        print_str = colored('  Replacing configuration ','green')+colored('"self "',"yellow")+colored('items: ','green')
        profile_obj = self.config_obj["profiles"]; self.profile_obj = profile_obj
        
        if not self.auto_restart:
            self.functions.print_clear_line()
        
        for profile in profile_obj.keys():
            if profile_obj[profile]["enable"] and self.action != "edit_config":
                if profile_obj[profile]["layer0_link"]["layer0_host"] == "self":
                    print(f"{print_str}{colored('link host ip','yellow')}",end="\r")
                    profile_obj[profile]["layer0_link"]["layer0_host"] = self.functions.get_ext_ip() 
                if profile_obj[profile]["layer0_link"]["layer0_key"] == "self":
                    self.setup_passwd(True)
                    while True:
                        print(f"{print_str}{colored('link host public key','yellow')}",end="\r")
                        if not write_out:
                            write_out = True
                            success = grab_nodeid(profile)
                        if success:
                            self.nodeid = self.nodeid.strip("\n")
                            profile_obj[profile]["layer0_link"]["layer0_key"] = self.nodeid
                            break
                        sleep(2)
                        attempts += 1
                        if attempts > 2:
                            self.error_messages.error_code_messages({
                                "error_code": "cfg-337",
                                "line_code": "node_id_issue",
                                "extra": "config"
                            })

            if write_out:  
                done_ip, done_key, current_profile, skip_write = False, False, False, False
                self.log.logger.warn("found [self] key words in yaml setup, changing to static values to speed up future nodectl executions")        
                f = open("/var/tessellation/nodectl/cn-config.yaml")
                with open("/var/tmp/cn-config-temp.yaml","w") as newfile:
                    for line in f:
                        skip_write = False
                        if f"{profile}:" in line:
                            current_profile = True
                        if current_profile:
                            if "layer0_key: self" in line and not done_key:
                                newfile.write(f"        layer0_key: {self.nodeid}\n")
                                done_key,skip_write = True, True
                            elif "layer0_host: self" in line and not done_ip:
                                newfile.write(f"        layer0_host: {self.functions.get_ext_ip()}\n")
                                done_ip, skip_write = True, True
                        if not skip_write:
                            newfile.write(line)
                newfile.close()
                f.close()
                system("mv /var/tmp/cn-config-temp.yaml /var/tessellation/nodectl/cn-config.yaml > /dev/null 2>&1")


    def validate_yaml_keys(self):
        def test_missing(key):
            try:
                _ = self.obj[key]
            except Exception as e:
                return True
            return False
                
        self.test_dict = {
            "top": ["profiles","auto_restart","global_p12","global_cli_pass","upgrader","all_global"],
            "profiles": [
                "enable","layer","edge_point","environment","ports","service",
                "layer0_link","dirs","java","p12","node_type","description"
            ],
            "edge_point": ["https","host","host_port"],
            "ports": ["public","p2p","cli"],
            "layer0_link":  ["enable","layer0_key","layer0_host","layer0_port","link_profile"],
            "dirs": ["snapshots","backups","uploads"],
            "java":  ["xms","xmx","xss"],
            "p12": ["nodeadmin","key_location","p12_name","wallet_alias","passphrase"]
            
        } 
                
        prof_obj = self.config_obj["profiles"]
        missing_list = []
        
        for n, (k, v) in enumerate(self.test_dict.items()):
            if n == 0:
                self.obj = self.config_obj
                missing = list(filter(test_missing,v))
                if len(missing) > 0:
                    missing_list.append(["top",missing])
            elif n == 1:
                try:
                    self.obj = self.config_obj["profiles"]
                except:
                    missing_list.append(["profiles","profiles","profiles"])
            if n > 0:
                for profile in prof_obj:
                    if n == 1:
                        self.obj = prof_obj[profile]
                    else:
                        self.obj = prof_obj[profile][k]
                                    
                    missing = list(filter(test_missing,v))
                    if len(missing) > 0:
                        missing_list.append([profile, k, missing])

        title = "invalid cn-config.yaml"
        if len(missing_list) > 0:
            self.validated = False
            for error in missing_list:
                section = profile = missing_keys = None
                if error[0] == "top":
                    missing_keys = error[1]
                else:
                    profile = error[0]
                    section = error[1]
                    missing_keys = error[2]
                    
                self.error_list.append({
                    "title": title,
                    "section": section,
                    "profile": profile,
                    "missing_keys": missing_keys, 
                    "key": None,
                    "type": "yaml",
                    "special_case": None,
                    "value": "skip"
                })                        
                
                            
    def validate_profiles(self):
        self.log.logger.debug("[validate_config] method called.")
        
        # test #1 - at least one profile
        self.profiles = self.config_obj["profiles"].keys()
        if len(self.profiles) < 1:
            self.validated = False
            self.error_list.append({
                "title":"no_profiles",
                "section": None,
                "profile": None,
                "missing_keys": None, 
                "key": None,
                "special_case": None,
                "value": "skip"
            })
            return False
        return True
    
    
    def validate_services(self):
        service_names = []
        for i_profile in self.profiles:
            service_names.append(self.config_obj["profiles"][i_profile]["service"]) 
            
        if len(service_names) != len(set(service_names)):
            self.error_list.append({
                "title":"Service Name Duplicates",
                "section": None,
                "profile": None,
                "missing_keys": None, 
                "key": "service",
                "value": "skip",
                "type": None,
                "special_case": None
            })
            self.validated = False
        

    def validate_global_setting(self):
        global_count = 0
        
        try:
            for profile in self.config_obj["profiles"].keys():
                g_tests = []
                g_tests.append(self.config_obj["profiles"][profile]["p12"]["p12_name"])
                g_tests.append(self.config_obj["profiles"][profile]["p12"]["passphrase"])
                if g_tests.count("global") != 0 and g_tests.count("global") != len(g_tests):
                    self.validated = False
                    self.error_list.append({
                        "title":"global settings issue",
                        "section": "p12",
                        "profile": profile,
                        "missing_keys": None, 
                        "type": "global",
                        "key": "p12_name, passphrase",
                        "special_case": None,
                        "value": "skip"
                    })
                elif g_tests.count("global") != 0:
                    # test if everything is set to global
                    global_count += 1
        except:
            self.send_error("cfg-705","format","existence")

            
        if len(self.config_obj["profiles"].keys()) == global_count:
            self.config_obj["all_global"] = True
            
        if self.validated:
            return True
        return False
                  

    def validate_p12_exists(self):
        for profile in self.config_obj["profiles"].keys():
            p12 = self.config_obj["profiles"][profile]["p12"]["p12_name"]
            location = self.config_obj["profiles"][profile]["p12"]["key_location"]
            if location != "global" and location[-1] == "/":
                location = location[:-1]
                if not path.isfile(f"{location}/{p12}"):
                    self.validated = False
                    self.error_list.append({
                        "title":"p12 not found",
                        "section": "p12",
                        "profile": profile,
                        "missing_keys": None, 
                        "type": "p12_nf",
                        "key": p12,
                        "special_case": None,
                        "value": f"{location}/{p12}",
                    })
                    

    def validate_link_dependencies(self):
        # this is done after the disabled profiles are removed.
        link_profiles = []
        for profile in self.profiles:
            link_profile = self.config_obj["profiles"][profile]["layer0_link"]["link_profile"]
            if link_profiles != "None":
                link_profiles.append((profile,link_profile)) 
                
        for profile in link_profiles:
            if self.config_obj["profiles"][profile[0]]["layer0_link"]["enable"]:
                if profile[0] == profile[1]:
                    self.error_list.append({
                        "title":"Link Profile Dependency Conflict",
                        "section": "layer0_link",
                        "profile": profile[0],
                        "missing_keys": None, 
                        "key": "link_profile",
                        "value": profile[1],
                        "type": None,
                        "special_case": "Cannot link profile to itself"
                    })  
                    self.validated = False              
                elif profile[1] not in self.profiles:
                    self.error_list.append({
                        "title":"Link Profile Dependency Not Met",
                        "section": "layer0_link",
                        "profile": profile[0],
                        "missing_keys": None, 
                        "key": "link_profile",
                        "value": profile[1],
                        "type": None,
                        "special_case": None
                    })
                    self.validated = False   

                                    
    def setup_schemas(self):   
        # ===================================================== 
        # schema order of sections needs to be in the exact
        # same order as the yaml file setup both in the profile
        # list values and each profile subsection below that...
        # =====================================================         
        self.schema = {
            "profiles": [
                ["enable","bool"],
                ["layer","layer"],
                ["edge_point","key"],
                ["environment","str"],
                ["ports","key"],
                ["service","str"],
                ["layer0_link","key"],
                ["dirs","key"],
                ["java","key"],
                ["p12","key"],
                ["pro","key"],
                ["node_type","node_type"],
                ["description","str"],
            ],
            "edge_point": [
                ["https","bool"],
                ["host","host"], 
                ["host_port","port"],
            ],
            "ports": [
                ["public","high_port"],
                ["p2p","high_port"],
                ["cli","high_port"],
            ],
            "layer0_link": [
                ["enable","bool"], 
                ["layer0_key","128hex"], 
                ["layer0_host","host"], 
                ["layer0_port","self_port"],
                ["link_profile","str"],
                ["is_self","bool"], # automated value [not part of yaml]
            ],
            "dirs": [
                ["snapshots","path"],
                ["backups","path"],
                ["uploads","path"],
            ],
            "java": [
                ["xms","mem_size"],
                ["xmx","mem_size"],
                ["xss","mem_size"],
            ],
            "p12": [
                ["nodeadmin","str"],
                ["key_location","path"],
                ["p12_name","str"],
                ["wallet_alias","str"],
                ["passphrase","str"],
                ["p12_passphrase_global","bool"], # automated value [not part of yaml]
                ["p12_key_location_global","bool"], # automated value [not part of yaml]
                ["p12_p12_name_global","bool"], # automated value [not part of yaml]
                ["p12_nodeadmin_global","bool"], # automated value [not part of yaml]
                ["p12_wallet_alias_global","bool"], # automated value [not part of yaml]
                ["cli_pass","bool"], # automated value [not part of yaml]
                ["key_store","str"], # automated value [not part of yaml]
            ],
            "pro": [
                ["seed_location","path"],
                ["seed_file","str"],
                ["seed_path","str"], # automated value [not part of yaml]
            ],
            "auto_restart": [
                ["enable","bool"],
                ["auto_upgrade","bool"],
            ],
            "global_p12": [
                ["nodeadmin","str"],
                ["key_location","path"],
                ["p12_name","str"],
                ["wallet_alias","str"],
                ["passphrase","str"],
                ["key_store","str"], # automated value [not part of yaml]
            ]
        }
        
        # make sure to update verify_profile_types -> int_types or enabled_section
        # as needed if the schema changes
        
        # set section progress dict
        self.global_section_completed = {
            "global_p12": False,
            "auto_restart": False,
        }

        
    def verify_profile_keys(self,profile):
        values = []
        types = []
        skip = False
        
        for section, check_keys in self.schema.items():
            verify = True
            key_list = [x[0] for x in check_keys]
            get_key_value_list = [ x for x in check_keys if x[1] != "key"]
            
            if section == "profiles":
                try:
                    found_list = list(self.config_obj[section][profile])
                except:
                    found_list = []
            elif section in self.global_section_completed.keys():  # other key sections
                try:
                    found_list = list(self.config_obj[section])
                except:
                    found_list = []
            else: # sub_keys
                try:
                    found_list = list(self.config_obj["profiles"][profile][section])
                except:
                    found_list = []
            
            # exception
            if "cli_pass" in key_list:
                try:
                    found_list.pop(found_list.index("p12_cli_pass_global"))
                except:
                    pass # will force error
                
            if sorted(key_list) != sorted(found_list): # main keys
                if section in self.global_section_completed.keys() and self.global_section_completed[section]:
                    skip = True
                if section in self.global_section_completed.keys():
                    self.global_section_completed[section] = True
                    profile = "N/A"
                    
                if not skip:
                    missing =  [x for x in key_list if x not in found_list]
                    self.validated = False
                    self.error_list.append({
                        "title": "key_existence",
                        "section": section,
                        "profile": profile,
                        "type": "key",
                        "key": "multiple",
                        "value": missing,
                        "special_case": None
                    })
            else:
                for value in get_key_value_list:
                    if section == "profiles":
                        values.append(self.config_obj[section][profile][value[0]]) # first element of first list in list of lists
                    elif section in self.global_section_completed.keys():
                        values.append(self.config_obj[section][value[0]])
                    else:
                        values.append(self.config_obj["profiles"][profile][section][value[0]])
                    types.append(value[1])
                    
                get_key_list = [x[0] for x in get_key_value_list]
                
                if section in self.global_section_completed.keys(): 
                    verify = False
                    if self.global_section_completed[section] == False: 
                        self.global_section_completed[section] = True
                        verify = True
                        
                if verify:
                    if section in self.global_section_completed:
                        profile = "N/A"
                    self.verify_profile_types({
                        "section": section,
                        "values": values,
                        "profile": profile,
                        "types": types,
                        "key_list": get_key_list
                    })  
                
                values = [] # reset list  
                types = [] # reset list        
                        
                                    
    def verify_profile_types(self,obj):
        section = obj["section"]
        values = obj['values']
        profile = obj['profile']
        types = obj['types']
        keys = obj['key_list']
        
        return_on = obj.get("return_on",False)
        validated = True
        special_case = None
        
        int_types = ["int","port","high_port","layer"] 
        enabled_sections = ["profiles","layer0_link","auto_restart"]

        # test for required enable boolean
        if section in enabled_sections:
            if "enable" not in keys:
                validated = False
                error_key = "enable"
                value = "missing key"
            else:
                index = keys.index("enable")
                if values[index] == False:
                    if section == "profiles":
                        self.profile_enable["profile"] = profile
                        self.profile_enable["enable"] = False
                    return
        
        if section == "profiles":
            if "layer" in keys:
                self.current_layer = values[keys.index("layer")]
                        
        if validated:
            for n, value in enumerate(values):
                title = "invalid type" # default
                
                if return_on and not validated:
                    return validated
                validated = True
                                 
                if types[n] in int_types:
                    try:
                        value = int(value)
                    except:
                        validated = False
                        
                    if types[n] == "layer" and validated: # Crypto Blockchain Layer 0,1,2,3,4
                                                            # - 0 hardware layer 
                                                            # - 1 data layer
                                                            # - 2 network layer
                                                            # - 3 consensus layer
                                                            # - 4 application layer.
                        if value > 4:
                            title = "blockchain layer"
                            validated = False
                    if types[n] == "self_port" and value == "self":
                        pass 
                    if (types[n] == "port" or types[n] == "self_port" or types[n] == "high_port") and validated: 
                        lower = 1
                        if types[n] == "high_port":
                            lower = 1024
                        if value < lower or value > 65535:
                            title = "TCP port"
                            validated = False 

                if types[n] == "str":
                    if not isinstance(value,str):
                        validated = False   

                if types[n] == "128hex":
                    pattern = "^[a-fA-F0-9]{128}$"
                    if not match(pattern,value) and value != "self":
                        validated = False   
                                                        
                elif types[n] == "host":
                    if value != "self" and not self.functions.test_hostname_or_ip(value):
                        validated = False  
                        
                elif types[n] == "bool":
                    if not isinstance(value,bool):
                        validated = False
                        
                elif types[n] == "y_or_n":
                    if value != "yes" and value != "no":
                        validated = False
                        
                elif types[n] == "node_type":
                    if value != "genesis" and value != "validator":
                        title = "Node type"
                        validated = False
                
                elif types[n] == "list_of_strs":
                    if not isinstance(value,list):
                        validated = False
                    else:
                        for v in value:
                            if not isinstance(v,str):
                                validated = False
                                break

                elif types[n] == "path":
                    if value != "global":
                        if "key_location" in keys or (value == "default" or value == "disable"):
                            if value == "disable" and ( keys[n] != "snapshots" and keys[n] != "seed_location" ):
                                title = "disable is an invalid keyword"
                                validated = False
                        if value == "disable" and (profile == "N/A" or self.config_obj["profiles"][profile]["layer"] < 1):
                            title = "disable is an invalid keyword for layer0"
                            validated = False
                        elif value != "disable" and value != "default":
                            title = "invalid or path not found"
                            if not path.isdir(value):
                                validated = False
                        if value[-1] != "/" and (value != "default" and value != "disable"):
                            validated = False
                            title = "invalid path definition missing '/'"

                elif types[n] == "mem_size":
                    if not match("^(?:[0-9]){1,4}[MKG]{1}$",str(value)):
                        title = "memory sizing format"
                        validated = False
                    
                if keys[n] == "passphrase":
                    if not isinstance(value,str) and value != None and value != "None":
                        validated = False
                    if value == None: # exception to str type requirement for passphrase
                        validated = True
                                
                if keys[n] == "p12_name":
                    if value != "global":
                        p12_test = value.split(".")
                        if not isinstance(p12_test[0],str):
                            validated = False
                        try:
                            _ = p12_test[1]
                        except:
                            title = "invalid p12_name"
                            validated = False
                        else:
                            if p12_test[1] != "p12":
                                title = "invalid extension"
                                validated = False

                error_key = keys[n]

                if not validated:
                    self.validated = False  
                    self.error_list.append({
                        "title": title,
                        "section": section,
                        "profile": profile,
                        "type": types[n],
                        "key": error_key,
                        "value": value,
                        "special_case": special_case
                    })
                    
        if return_on:
            return validated

                        
    def print_report(self):
        value_text = "Value Found"
        wallet_error1 = "wallet alias must match what was"
        wallet_error2 = "configured during p12 original"
        wallet_error3 = "creation 'key alias'."
        
        node_type1 = "options include 'validator' or 'genesis'"
        node_type2 = "currently nodectl does not support genesis nodes."        
        
        mem1 = "must be between 1 and 4 integers (numbers) and"
        mem2 = "the CAPITAL letter K, M, or G"        
        mem3 = "K = KiloBytes"        
        mem4 = "M = MegaBytes"        
        mem5 = "G = GigaBytes"        
        mem6 = "Example) 1024M"        
        
        p12_name_error1 = "must contain '.p12' extension"
        key_location1 = "the path did not test valid"
        string2 = "and must be a string."
        
        service_dups = "one or more profiles have the same service name."
        service_dups2 = "each profile must have a unique service name."
        
        dir1 = "the directory does not exist or is invalid"
        dir2 = "create directory or modify location string."
        
        hex1 = "an invalid public id (nodeid) was found."
        hex2 = "either not a valid hex or not 128bytes"
        
        global1 = "both keys must contain valid values"
        global2 = "or both must contain the 'global'"
        global3 = "key word."

        yaml1 = "the configuration yaml file is missing"
        yaml2 = "one or multiple keys to allow nodectl"
        yaml3 = "to properly function."
                
        hints = {
            "ports": "port must be a integer between 1 and 65535",
            "high_port": "port must be a integer between 1024 and 65535",
            "wallet_alias": f"{wallet_error1} {wallet_error2} {wallet_error3}",
            "p12_name": f"{p12_name_error1} {string2}",
            "key_location": f"{key_location1} {string2}",
            "p12_nf": "unable to location the p12 file, file not found.",
            "passphrase": "must be a string or empty value.",
            "str": "must be a string.",
            "bool": "must include a boolean (true/false)",
            "enable": "must include a boolean (true/false) enable key.",
            "multiple": "configuration key(s) are missing",
            "list_of_strs": "must be a list of strings",
            "mem_size": f"{mem1} {mem2} {mem3} {mem4} {mem5} {mem6}",
            "node_type": f"{node_type1} {node_type2}",
            "service": f"{service_dups} {service_dups2}",
            "link_profile": "dependency link profile not found",
            "dirs": f"{dir1} {dir2}",
            "128hex": f"{hex1} {hex2}",
            "layer0_link": "invalid link type",
            "global": f"{global1} {global2} {global3}",
            "yaml": f"{yaml1} {yaml2} {yaml3}",
            "edge_point": "must be a valid host or ip address",
            "pro": "must be a valid existing path or file",
        }
        
        if self.action != "normal" or not self.validated:
            self.functions.print_header_title({
                "line1": "CONFIGURATION",
                "line2": "validator",
                "clear": True,
            })
            
        if not self.validated:
            self.functions.print_paragraphs([
                [" WARNING! ",2,"yellow,on_red","bold"], ["CONFIGURATION FILE DO NOT VALIDATE",1,"red"],
                ["Issues Found:",0,"yellow"], [str(len(self.error_list)),2,"red"],
            ])

            try:
                for error in self.error_list:
                    if error["key"] in hints:
                        hint = hints[error["key"]]
                        if error["key"] == "multiple":
                            value_text = "    Missing"
                    elif error["type"] in hints:
                        hint = hints[error["type"]]
                    else:
                        hint = hints[error["section"]]
                        
                    if error["special_case"] != None:
                        hint = error["special_case"]
                
                    config_key = ""
                    if error["key"] == None and error["missing_keys"] != None:
                        for key_str in error["missing_keys"]:
                            config_key += key_str+", "
                        config_key = config_key[:-2]
                    else:
                        config_key = error["key"]

                    self.functions.print_paragraphs([
                        ["Error Type:",0,"magenta"], [error["title"],1],
                        ["   Profile:",0,"magenta"], [error["profile"],1],
                        ["   Section:",0,"magenta"], [error["section"],1],
                        ["Config Key:",0,"magenta"], [config_key,1],
                    ])           
                            
                    wrapper = self.functions.print_paragraphs("wrapper_only")
                    wrapper.initial_indent = "        "
                    wrapper.subsequent_indent = "              "
                    line = f"{colored('hint:','magenta')} {colored(hint,'cyan')}"
                    
                    print(wrapper.fill(line))
                    if error["value"] != "skip":
                        self.functions.print_paragraphs([
                            [value_text,0,"yellow"], [error["value"],2,"red","bold"],
                        ]) 
            except:
                self.send_error("cfg-1094")

            if self.action == "edit_config":
                return "error_found"
            
            print("")
            re_on_error = self.functions.confirm_action({
                "prompt": "Would you like to edit the configuration?",
                "yes_no_default": "n",
                "return_on": "y",
                "exit_if": False
            })
            if re_on_error:
                self.action = "edit_on_error"
                return "edit_on_error"
            
            self.functions.print_paragraphs([
                ["",1], ["To fix, enter in:",1],
                ["sudo nodectl configure",2,"green","bold"],
            ])
            self.functions.print_auto_restart_warning()
            exit(1)
        
        if self.action != "normal":
            self.functions.print_paragraphs([ 
                ["Configuration file:",0,"green"], [" VALIDATED! ",2,"grey,on_green","bold"],
            ])
            pass
                
                
    def send_error(self,code,extra="existence",extra2=None):
        self.log.logger.critical(f"configuration file [cn-config.yaml] error code [{code}] not reachable - should be in /var/tessellation/nodectl/")
        self.error_messages.error_code_messages({
            "error_code": code,
            "line_code": "config_error",
            "extra": extra,
            "extra2": extra2
        }) 
        
        
if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation") 
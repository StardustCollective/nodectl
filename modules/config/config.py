import yaml
import json

from termcolor import colored
from time import sleep
from copy import deepcopy
from re import match
from os import system, path, get_terminal_size
from sys import exit
from secrets import compare_digest

from .migration import Migration
from ..troubleshoot.errors import Error_codes
from ..functions import Functions
from ..p12 import P12Class
from ..troubleshoot.logger import Logging

class Configuration():
    
    def __init__(self,command_obj):
        
        self.functions = Functions({
            "global_elements": {"caller":"config"},
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
            "global_elements": {"caller": "config"},
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
                
        self.setup_schemas()
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
                    self.skip_global_validation = False
                    for profile in self.profiles:
                        self.validate_profile_keys(profile)
                    if self.validated:
                        self.validate_port_duplicates()
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
                    
                    # self.migration() # deprecated v2.9.0
                    self.error_messages.error_code_messages({
                        "error_code": "cfg-143",
                        "line_code": ""
                    })
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
            **yaml_dict["nodectl"],
            "global_elements": {},
        }
        
        self.metagraph_list = self.functions.clear_global_profiles(self.config_obj)
        
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
        
        self.config_obj["global_elements"]["global_cli_pass"] = False # initialize 
        self.config_obj["global_elements"]["global_upgrader"] = False # initialize 
        self.config_obj["global_elements"]["all_global"] = False # initialize 
        
        self.validate_global_setting()
        try:
            self.handle_cli_passphrase()
        except KeyError:
            pass


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
                
        
    def handle_cli_passphrase(self):
        # grab cli passphrase if present
        if "--pass" in self.argv_list:
            self.config_obj["global_elements"]["global_cli_pass"] = True
            self.config_obj["global_p12"]["passphrase"] = self.argv_list[self.argv_list.index("--pass")+1]
            
        # init = {}
    
        # for profile in self.config_obj.keys():
        #     if "global" not in profile:
        #         for p12_key in self.config_obj[profile].keys():
        #             if "p12" in p12_key:
        #                 p12_item = self.config_obj[profile][p12_key]
        #                 init[f"global_{p12_key}"] = False
        #                 if self.config_obj[profile][p12_key] == "global" and "cli" not in p12_item:
        #                     init[f"global_{p12_key}"] = True
            
        #         for key, value in init.items():
        #             self.config_obj[profile][key] = value
    
        # 1 == 1
        
        
    def create_path_variable(self, path, file):
        try:
            path = f"{path}/{file}" if path[-1] != "/" else f"{path}{file}"
        except:
            return False
        return path


    def setup_config_vars(self):
        # sets up the automated values not present in the 
        # yaml file
        
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
                    
        dirs = {
            "directory_backups": "/var/tessellation/backups/",
            "directory_uploads": "/var/tessellation/uploads/",
            "seed_file": "seed-list",
            "seed_location": "/var/tessellation",
            "jar_file": ["cl-node.jar","cl-dag-l1.jar"],
            "repository": "github.com/Constellation-Labs/tessellation/"
        }
        
        # snaps = {
        #     "CL_SNAPSHOT_STORED_PATH":
        #         "/var/tessellation/cnng-profile_name/data/snapshot/"
        #     ,
        #     "CL_INCREMENTAL_SNAPSHOT_STORED_PATH":
        #         "/var/tessellation/cnng-profile_name/data/incremental_snapshot/"
        #     ,
        #     "CL_INCREMENTAL_SNAPSHOT_TMP_STORED_PATH":
        #         "/var/tessellation/cnng-profile_name/data/incremental_snapshot_tmp/"
        #     ,
        # }
            
        try:
            self.config_obj["global_p12"]["key_store"] = self.create_path_variable(
                self.config_obj["global_p12"]["key_location"],
                self.config_obj["global_p12"]["key_name"],
            ) 
        except:
            error_found()
        
        for profile in self.metagraph_list:
            try:
                self.config_obj[profile]["p12_key_store"] = self.create_path_variable(
                    self.config_obj[profile]["p12_key_location"],
                    self.config_obj[profile]["p12_key_name"]
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
                self.config_obj[profile]["layer0_link_is_self"] = True
                if self.config_obj[profile]["layer0_link_profile"] == "None":
                    self.config_obj[profile]["layer0_link_is_self"] = False
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
                    
            for tdir, location in dirs.items():
                try:
                    if self.config_obj[profile][tdir] == "default":
                        self.config_obj[profile][tdir] = location   
                        if tdir == "jar_file":
                            self.config_obj[profile]["jar_file"] = location[0]
                            if int(self.config_obj[profile]["layer"]) > 0:
                                self.config_obj[profile]["jar_file"] = location[1]
                except Exception as e:
                    error_found()

            try:
                self.config_obj[profile]["seed_path"] = self.create_path_variable(
                    self.config_obj[profile]["seed_location"],
                    self.config_obj[profile]["seed_file"]
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
                                    
            # snap_obj = {}
            # for default_snap_dir, location in snaps.items():
            #     for config_snap_dir in self.config_obj[profile].keys():
            #         if "custom_env_vars" in config_snap_dir and self.config_obj[profile]["custom_env_vars_enable"]:
            #             if default_snap_dir in config_snap_dir:
            #                 break 
            #         elif self.config_obj[profile]["layer"] > 0:
            #             snap_obj[f"customer_env_{default_snap_dir}"] = "default"
            #         else:
            #             snap_obj[f"customer_env_{default_snap_dir}"] = location
                
            # self.config_obj[profile] = {
            #     **self.config_obj[profile],
            #     **snap_obj,
            # }
                    
        self.config_obj["global_elements"]["caller"] = None  # init key (used outside of this class)
            
            
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
        
        for profile in self.metagraph_list:
            if not self.config_obj[profile]["enable"]:
                if "edit_config" not in self.argv_list:
                    remove_list.append(profile)

        for profile in remove_list:
            self.config_obj.pop(profile)
            self.metagraph_list.pop(profile)

            
    def setup_passwd(self,force=False):
        def verify_passwd(passwd, profile):
            clear, top_new_line, show_titles = False, False, True 
            if profile == "global" and ( not self.config_obj["global_elements"]["global_upgrader"] or self.argv_list[1] != "upgrade" ):
                clear = True
            if self.config_obj["global_elements"]["global_upgrader"] or self.argv_list[1] == "upgrade":
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
            self.config_obj["global_elements"]["global_cli_pass"] = True
            passwd = False

        if self.is_passphrase_required() or force:
            verify_passwd(passwd,"global")  
        
        if not self.config_obj["global_elements"]["all_global"]:
            for profile in self.config_obj.keys():
                # print(json.dumps(self.config_obj,indent=3))
                if not self.config_obj[profile]["global_p12_passphrase"]:
                    passwd = self.config_obj[profile]["p12_passphrase"]
                    if passwd == "None" or passwd == None:
                        self.config_obj[profile]["global_p12_cli_pass"] = True
                        passwd = False
                    if self.is_passphrase_required():
                        verify_passwd(passwd,profile)
                else:
                    self.config_obj[profile]["p12_passphrase"] = self.config_obj["global_p12"]["passphrase"]

        
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
        profile_obj = self.config_obj; self.profile_obj = profile_obj
        
        if not self.auto_restart:
            self.functions.print_clear_line()
        
        for profile in self.metagraph_list:
            if profile_obj[profile]["enable"] and self.action != "edit_config":
                if profile_obj[profile]["layer0_link_host"] == "self":
                    print(f"{print_str}{colored('link host ip','yellow')}",end="\r")
                    sleep(.8) # allow user to see
                    profile_obj[profile]["layer0_link_host"] = self.functions.get_ext_ip() 
                if profile_obj[profile]["layer0_link_port"] == "self":
                    print(f"{print_str}{colored('link public port','yellow')}",end="\r")
                    sleep(.8) # allow user to see
                    link_profile_port = self.config_obj[self.config_obj[profile]["layer0_link_profile"]]["public_port"]
                    profile_obj[profile]["layer0_link_port"] = link_profile_port 
                if profile_obj[profile]["layer0_link_key"] == "self":
                    self.setup_passwd(True)
                    while True:
                        print(f"{print_str}{colored('link host public key','yellow')}",end="\r")
                        if not write_out:
                            write_out = True
                            success = grab_nodeid(profile)
                        if success:
                            self.nodeid = self.nodeid.strip("\n")
                            profile_obj[profile]["layer0_link_key"] = self.nodeid
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
                done_ip, done_key, done_port, current_profile, skip_write = False, False, False, False, False
                self.log.logger.warn("found [self] key words in yaml setup, changing to static values to speed up future nodectl executions")        
                f = open("/var/tessellation/nodectl/cn-config.yaml")
                with open("/var/tmp/cn-config-temp.yaml","w") as newfile:
                    for line in f:
                        skip_write = False
                        if f"{profile}:" in line:
                            current_profile = True
                        if current_profile:
                            if "layer0_link_key: self" in line and not done_key:
                                newfile.write(f"    layer0_link_key: {self.nodeid}\n")
                                done_key,skip_write = True, True
                            elif "layer0_link_host: self" in line and not done_ip:
                                newfile.write(f"    layer0_link_host: {self.functions.get_ext_ip()}\n")
                                done_ip, skip_write = True, True
                            elif "layer0_link_port: self" in line and not done_port:
                                newfile.write(f"    layer0_link_port: {link_profile_port}\n")
                                done_port, skip_write = True, True
                        if not skip_write:
                            newfile.write(line)
                newfile.close()
                f.close()
                system("mv /var/tmp/cn-config-temp.yaml /var/tessellation/nodectl/cn-config.yaml > /dev/null 2>&1")


    def setup_schemas(self):   
        # ===================================================== 
        # schema order of sections needs to be in the exact
        # same order as the yaml file setup both in the profile
        # list values and each profile subsection below that...
        # =====================================================         
        self.schema = {
            "metagraphs": [
                ["enable","bool"],
                ["metagraph_name","str"],
                ["description","str"],
                ["node_type","node_type"],                
                ["layer","layer"],
                ["service","str"],
                ["environment","str"],
                ["edge_point","host"],
                ["edge_point_tcp_port","port"],
                ["public_port","high_port"], 
                ["p2p_port","high_port"], 
                ["cli_port","high_port"], 
                ["layer0_link_enable","bool"],
                ["layer0_link_key","128hex"], 
                ["layer0_link_host","host"], 
                ["layer0_link_port","self_port"],
                ["layer0_link_profile","str"],
                ["layer0_link_is_self","bool"], # automated value [not part of yaml]
                ["directory_backups","path_def"],
                ["directory_uploads","path_def"],
                ["java_xms","mem_size"],
                ["java_xmx","mem_size"],
                ["java_xss","mem_size"],
                ["repository","host_def"], 
                ["jar_file","str"],
                ["p12_nodeadmin","str"],
                ["p12_key_location","path"],
                ["p12_key_name","str"],
                ["p12_key_alias","str"],
                ["p12_passphrase","str"], 
                ["p12_key_store","str"], # automated value [not part of yaml]              
                ["seed_location","path_def_dis"],
                ["seed_file","str"],             
                ["seed_path","path_def_dis"], # automated value [not part of yaml]
                ["custom_args_enable","bool"],
                ["custom_env_vars_enable","bool"],
                ["global_p12_all_global","bool"], # automated value [not part of yaml]
                ["global_p12_passphrase","bool"], # automated value [not part of yaml]
                ["global_p12_key_location","bool"], # automated value [not part of yaml]
                ["global_p12_key_name","bool"], # automated value [not part of yaml]
                ["global_p12_nodeadmin","bool"], # automated value [not part of yaml]
                ["global_p12_key_alias","bool"], # automated value [not part of yaml]
                ["global_p12_cli_pass","bool"], # automated value [not part of yaml]
            ],
            "global_auto_restart": [
                ["enable","bool"],
                ["auto_upgrade","bool"],
                ["rapid_restart","bool"],
            ],
            "global_p12": [
                ["nodeadmin","str"],
                ["key_location","path"],
                ["key_name","str"],
                ["key_alias","str"],
                ["passphrase","str"],
                ["key_store","str"], # automated value [not part of yaml]
            ]
        }
        
        # make sure to update validate_profile_types -> int_types or enabled_section
        # as needed if the schema changes
        
        # set section progress dict
        self.global_section_completed = {
            "global_p12": False,
            "global_auto_restart": False,
        }
        
        
    def validate_yaml_keys(self):
        # self.common_test_dict = {
        #     "auto_restart": ["enable","auto_upgrade","rapid_restart"],
        #     "global_p12": ["nodeadmin","key_location","key_name","key_alias","passphrase"],
        #     "cnng_dynamic_profiles": [
        #         "enable","metagraph_name","description","node_type","layer","service",
        #         "environment","edge_point","edge_point_tcp_port",
        #         "public_port","p2p_port","cli_port",
        #         "layer0_link_enable","layer0_link_key","layer0_link_host","layer0_link_port","layer0_link_profile",
        #         "directory_backups","directory_uploads",
        #         "java_xms","java_xmx",
        #         "java_xss","repository",
        #         "jar_file",
        #         "p12_nodeadmin","p12_key_location","p12_key_name","p12_key_alias","p12_passphrase",
        #         "seed_location","seed_file",
        #         "custom_args_enable","custom_env_vars_enable",
        #     ],
        # }
        # profile_value_list = self.common_test_dict["cnng_dynamic_profiles"]
        missing_list = []
        
        for config_key, config_value in self.config_obj.items():
            if "global" not in config_key:
                # testing profiles
                # key_test_list = list(config_value.keys())
                # schema_test_list = [item[0] for item in self.schema["metagraphs"]]
                missing =  [item[0] for item in self.schema["metagraphs"]] - config_value.keys()
                missing = [x for x in missing if x not in ["seed_path","layer0_link_is_self","p12_key_store"]]
                for item in missing:
                    missing_list.append([config_key, item])
        
        
        # for config_key, config_value in self.config_obj.items():
        #     if config_key not in self.common_test_dict.keys() and "global" not in config_key:
        #         # testing profiles
        #         missing = list(profile_value_list - config_value.keys())
        #         possible_invalid = list(config_value.keys() - profile_value_list)
        #         possible_invalid = [x for x in missing if "global" not in x and "custom" not in x]
        #         missing += possible_invalid
        #         for item in missing:
        #             missing_list.append([config_key, item])

        if len(missing_list) > 0:
            self.validated = False
            for error in missing_list:
                profile, missing_key = error
                self.error_list.append({
                    "title": "invalid cn-config.yaml",
                    "section": "metagraph profiles",
                    "profile": profile,
                    "missing_keys": missing_key, 
                    "key": None,
                    "type": "yaml",
                    "special_case": None,
                    "value": "skip"
                })                        
                
                            
    def validate_profiles(self):
        self.log.logger.debug("[validate_config] method called.")
        self.num_of_global_sections = 3  # auto_restart, global_p12, global_elements
        profile_minimum_requirement = 1
        self.profiles = []
        
        # test #1 - at least one profile
        self.profiles = list(self.config_obj.keys())
        if len(self.profiles) < self.num_of_global_sections+profile_minimum_requirement:
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
        
        # for profile in profiles_list:
        #     # clean up globals
        #     if not "global" in profile:
        #         self.profiles.append(profile)
                
        return True
    
    
    def validate_services(self):
        service_names = []
        for i_profile in self.metagraph_list:
            service_names.append(self.config_obj[i_profile]["service"]) 
            
        if len(service_names) != len(set(service_names)):
            self.error_list.append({
                "title":"Service Name Duplicates",
                "section": None,
                "profile": None,
                "missing_keys": None, 
                "key": "service",
                "value": service_names,
                "type": None,
                "special_case": None
            })
            self.validated = False
        

    def validate_global_setting(self):
        # key_name, passphrase, and alias all have to match if set to global
        self.config_obj["global_elements"]["all_global"] = True
        try:
            for profile in self.metagraph_list:
                self.config_obj[profile]["global_p12_all_global"] = False
                g_tests = [self.config_obj[profile][f"p12_{x}"] for x in self.config_obj["global_p12"] if x in ["key_name","passphrase","key_alias"]]
                self.config_obj[profile] = {
                    **self.config_obj[profile],
                    **{ f"global_p12_{x}": False for x in self.config_obj["global_p12"] },
                }
                    
                if g_tests.count("global") != 0 and g_tests.count("global") != len(g_tests):
                    self.validated = False
                    self.error_list.append({
                        "title":"global settings issue",
                        "section": "p12",
                        "profile": profile,
                        "missing_keys": None, 
                        "type": "global",
                        "key": "p12_key_name, p12_passphrase, p12_alias",
                        "special_case": None,
                        "value": "skip"
                    })
                    
                g_tests = [self.config_obj[profile][f"p12_{x}"] for x in self.config_obj["global_p12"]]
                if g_tests.count("global") == len(self.config_obj["global_p12"]):
                    # test if everything is set to global
                    self.config_obj[profile]["global_p12_all_global"] = True

        except Exception as e:
            self.log.logger.critical(f"configuration format failure detected | exception [{e}]")
            self.send_error("cfg-705","format","existence")
            
        for profile in self.metagraph_list:
            if not self.config_obj[profile]["global_p12_all_global"]:
                self.config_obj["global_elements"]["all_global"] = False
            for p12_key, p12_value in self.config_obj[profile].items():
                if self.action == "edit_config":
                    if "p12_" in p12_key and "global" in p12_key:
                        self.config_obj[profile][p12_key] = False
                else:
                    if "p12_" in p12_key and "global" not in p12_key and "global" in p12_value:
                        self.config_obj[profile][f"global_{p12_key}"] = True
                        self.config_obj[profile][p12_key] = self.config_obj["global_p12"][p12_key[4:]]
            self.config_obj[profile]["global_p12_cli_pass"] = False # initialize

        return self.validated
                  

    def validate_p12_exists(self):
        for profile in self.metagraph_list:
            if not path.isfile(self.config_obj[profile]["p12_key_store"]):
                self.validated = False
                self.error_list.append({
                    "title":"p12 not found",
                    "section": "p12",
                    "profile": profile,
                    "missing_keys": None, 
                    "type": "p12_nf",
                    "key": "p12",
                    "special_case": None,
                    "value": self.config_obj[profile]["p12_key_store"],
                })
                    

    def validate_link_dependencies(self):
        # this is done after the disabled profiles are removed.
        link_profiles = []
        for profile in self.metagraph_list:
            link_profile = self.config_obj[profile]["layer0_link_profile"]
            if link_profile != "None":
                link_profiles.append((profile,link_profile)) 
                
        for profile in link_profiles:
            if self.config_obj[profile[0]]["layer0_link_enable"]:
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

        
    def validate_profile_keys(self,profile):
        custom_requirements = ["custom_env_vars_enable","custom_args_enable"]
        found_list = list(self.config_obj[profile])        
        skip = True if "elements" in profile else False

        if "global" not in profile:
            found_list = [x for x in found_list if x in custom_requirements or "custom" not in x]
            key_list = [x[0] for x in self.schema["metagraphs"]]
            section = "metagraphs"
        elif not skip:
            key_list = [x[0] for x in self.schema[profile]]
            section = profile.replace("global_","")
            
        if not skip and sorted(key_list) != sorted(found_list):
            missing1 = [x for x in key_list if x not in found_list]
            missing2 = [x for x in found_list if x not in key_list]
            missing = set(missing1 + missing2)
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
        
        if "global" not in profile:
            self.validate_profile_types(profile)

                
    def validate_profile_types(self,profile,return_on=False):
        validated = True
        special_case = None
        skip_validation = False
        
        # int_types = ["int","port","high_port","layer"] 
        valuation_dict = {
            "bool": bool,
            "int": int,
            "float": float,
            "str": str,
            "layer": [0,1],
            "node_type": ["validator","genesis"],
            "port": range(1,65535),
            "high_port": range(1024,65535),
            "self_port": range(1024,65535),
        }
        
        for section, section_types in self.schema.items():
            if "global" in section and not self.skip_global_validation:
                profile = section
            for key, test_value in self.config_obj[profile].items():
                for section_key, req_type in section_types:
                    if key == section_key:
                        validated = False
                        
                        if skip_validation:
                            if "layer0_link" in key:
                                validated = True
                            else:
                                skip_validation = False
                            
                        # debugging
                        # if key == "layer0_link_host" and profile == "intnet-l1":
                        #     1 == 1
                        
                        if req_type in valuation_dict.keys():
                            try:
                                validated = isinstance(test_value,valuation_dict[req_type])   
                            except Exception as e:
                                for value in valuation_dict[req_type]:
                                    if test_value == value:
                                        validated = True
                                        break
                                    title = "invalid range"
                            if not validated:
                                title = "invalid type"
                            if "key_name" in key and req_type == "str":
                                if test_value[-4::] != ".p12":
                                    title = "missing .p12 extension"
                            if key == "layer0_link_enable" and not test_value:
                                skip_validation = True
                            if "passphrase" in key and test_value != "none" and req_type != "bool":
                                if "'" in test_value or '"' in test_value:
                                    title = "invalid single and or double quotes in passphrase"
                            if key == "layer0_link_port" and test_value == "self":
                                validated = True
                            
                        elif "host" in req_type:
                            if req_type == "host_def" and test_value == "default":
                                validated = True
                            elif self.functions.test_hostname_or_ip(test_value) or test_value == "self":
                                validated = True
                            else:
                                title = "invalid host or ip"
                        
                        elif req_type == "128hex":
                            pattern = "^[a-fA-F0-9]{128}$"
                            if not match(pattern,test_value) and test_value != "self":
                                title = "invalid nodeid"
                            else:
                                validated = True 
                                
                        elif req_type == "list_of_strs":
                            title = "invalid list of strings"
                            if isinstance(test_value,list):
                                validated = True
                            if validated:
                                for v in test_value:
                                    if not isinstance(v,str):
                                        validated = False
                                        break                          

                        elif "path" in req_type:
                            # global paths replaced already
                            if "path" in key:
                                # dynamic value skip validation
                                validated = True
                            if "path_def" in req_type and test_value == "default":
                                validated = True
                            elif req_type == "path_def_dis" and test_value == "disable":
                                validated = True
                            elif path.isdir(test_value):
                                validated = True
                            elif test_value == "disable" and self.config_obj[profile]["layer"] < 1:
                                title = f"{test_value} is an invalid keyword for layer0"
                            elif test_value == "disable" or test_value == "default" or self.config_obj[profile]["layer"] < 1:
                                title = f"{test_value} is an invalid keyword"
                            elif test_value[-1] != "/":
                                title = "invalid path definition missing '/'"
                            elif not path.isdir(test_value):
                                title = "invalid or path not found"
                            else:
                                validated = True
                                
                        elif req_type == "mem_size":
                            if not match("^(?:[0-9]){1,4}[MKG]{1}$",str(test_value)):
                                title = "memory sizing format"
                            else:
                                validated = True
                        
                        if not validated:
                            self.validated = False
                            self.error_list.append({
                                "title": title,
                                "section": section,
                                "profile": profile,
                                "type": req_type,
                                "key": key,
                                "value": test_value,
                                "special_case": special_case
                            })        
                    
        if return_on:
            return validated
        self.skip_global_validation = True

        
    def validate_port_duplicates(self):
        found_ports = []
        found_keys = []
        error_keys = []
        ignore = ["layer0_link_port","edge_point_tcp_port"]
        
        for section in self.metagraph_list:
            for key, value in self.config_obj[section].items():
                if "port" in key and key not in ignore and value != 'None' and value != 'self':
                    found_keys.append(key)
                    found_ports.append(value) 
                        
        if len(found_ports) != len(set(found_ports)):
            duplicates = [x for x in found_ports if found_ports.count(x) > 1]
            duplicates = set(duplicates)
            for dup in duplicates:
                index = found_ports.index(dup)
                error_keys.append(found_keys[index])
                                
            self.validated = False
            self.error_list.append({
                "title": "duplicate api port values found",
                "section": "metagraphs",
                "profile": "metagraphs",
                "type": "api_port_dups",
                "missing_keys": error_keys,
                "key": None,
                "value": duplicates,
                "special_case": None,
            })    
                        
                                       
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
            "api_port_dups": "Tessellation API ports cannot conflict.",
            "high_port": "port must be a integer between 1024 and 65535",
            "wallet_alias": f"{wallet_error1} {wallet_error2} {wallet_error3}",
            "p12_key_name": f"{p12_name_error1} {string2}",
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
            "host": "must be a valid host or ip address",
            "host_def": "must be a valid host or ip address",
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
                [" WARNING! ",2,"yellow,on_red","bold"], ["CONFIGURATION FILE DID NOT VALIDATE",1,"red"],
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
                        if isinstance(error["missing_keys"],list):
                            for key_str in error["missing_keys"]:
                                config_key += key_str+", "
                            config_key = config_key[:-2]
                        else:
                            config_key = error["missing_keys"]
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
                    ok_to_ignore = True if "snapshot" in error["key"] else False
                    
            except:
                self.send_error("cfg-1094")

            if self.action == "edit_config":
                if ok_to_ignore:
                    self.functions.print_paragraphs([
                        ["Issue found can safely be ignored for new configurations.",1,"green"],
                    ])
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
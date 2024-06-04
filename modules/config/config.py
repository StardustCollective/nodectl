import yaml
import json

from termcolor import colored
from time import sleep, time
from random import randint
from re import match
from os import system, path, get_terminal_size, makedirs, listdir
from shutil import copy2, move
from sys import exit
from glob import glob
from shlex import quote

from .migration import Migration
from ..functions import Functions
from ..p12 import P12Class
from ..troubleshoot.errors import Error_codes
from ..troubleshoot.logger import Logging
from .versioning import Versioning


class Configuration():
    
    def __init__(self,command_obj):

        self.log = Logging()
        self.log.logger.info("configuration setup initialized")
        
        self.versioning_service = False
        self.argv_list = command_obj["argv_list"]

        self.skip_final_report = command_obj.get("skip_report",False)

        if "uvos" in self.argv_list: 
            # do not log if versioning service initialized Configuration
            self.versioning_service = True
            self.skip_final_report = True
            for handler in self.log.logger.handlers[:]:
                self.log.logger.removeHandler(handler)
                
        if "help" in self.argv_list[0] or "main_error" in self.argv_list[0]: return

        self.config_obj = {}
        self.error_list = []
        
        # for configurator
        self.error_found = False
        self.configurator_verified = False 

        self.auto_restart = True if "auto_restart" in self.argv_list or "service_restart" in self.argv_list else False

        try:
            self.called_command = self.argv_list[1]
            if "--installer" in self.argv_list:
                self.called_command = "install"
        except:
            self.called_command = "exit"
        
        execute = command_obj["implement"]
        self.action = command_obj["action"]        
    
        self.configurator_verified = True
                
        if "view" in self.action or self.action == "-vc":
            self.view_yaml_config("normal")
        
        self.validated = True
        self.profile_check = False

        skip_validation = ["configure","new_config","install","quick_install","uninstall","restore_config"]
        self.do_validation = False if self.action in skip_validation else True
        if self.action == "new_config_init": self.action = "edit_config"
        if self.called_command == "uninstall": 
            self.action = "edit_config"
            self.skip_final_report = True

        self.requested_configuration = False
        self.current_layer = None
        self.profile_enable = {
            "profile": None,
            "enabled": True
        }
        self.build_function_obj(False)
        if execute or self.do_validation:
            self.implement_config()
        

    def build_function_obj(self,config_obj):
        check_sudo = False
        if not config_obj:
            config_obj = {
                "global_elements": {"caller":"config"},
                "sudo_rights": False,
            }
            check_sudo = True
        else:
            try:
                _ = config_obj["global_elements"]
            except:
                config_obj["global_elements"] = {"caller":"config"}
                
            config_obj["global_elements"] = {
                **config_obj["global_elements"],
                "caller": "config"
            }
        self.functions = Functions(config_obj)
        self.error_messages = Error_codes(self.functions)
        if check_sudo: self.functions.check_sudo()
        
                
    def implement_config(self):
        continue_list = ["normal","edit_config","edit_on_error","edit_config_from_new"]
        
        self.setup_schemas()
        self.build_yaml_dict(True,True)
        self.check_for_migration()
        self.finalize_config_tests()
        self.validate_yaml_keys()
        self.remove_disabled_profiles()
        self.setup_config_vars()
        if len(self.error_list) < 1:
            if self.action in continue_list:
                self.prepare_p12()
                if self.action != "edit_config":
                    self.setup_passwd()
                if "edit_config" not in self.action:
                    self.setup_p12_aliases("global_p12")
                    self.setup_self_settings()
        
        if self.action == "edit_config_from_new": return
        if self.do_validation:
            if len(self.error_list) < 1:
                result = self.validate_profiles()
                if result:
                    self.skip_global_validation = False
                    for profile in self.profiles:
                        self.validate_profile_keys(profile)
                    self.setup_path_formats("global_p12")
                    if self.validated:
                        self.validate_port_duplicates()
                        self.validate_seedlist_duplicates()
                        self.validate_services()
                        self.validate_p12_exists()
                        self.validate_link_dependencies()
            else:
                self.validated = False
            self.print_report()

        self.functions.get_includes()
        self.cleanup_backups()
        if self.action not in continue_list:
            exit(0)
        if self.action == "edit_on_error":
            self.edit_on_error_args = ["-e"]
            self.requested_configuration = True
            return
        
        
    def build_yaml_dict(self,nodectl_only=False,setup_version=True):
        # nodectl_only refers to version fetch type
        self.yaml_file = f'{self.functions.nodectl_path}cn-config.yaml'
        try:
            with open(self.yaml_file, 'r', encoding='utf-8') as f:
                yaml_data = f.read()
        except:
            if path.isfile("/usr/local/bin/cn-node") and not path.isfile(f"{self.functions.nodectl_path}cn-config.yaml"):
                if self.called_command != "upgrade":
                    self.error_messages.error_code_messages({
                        "error_code": "cfg-164",
                        "line_code": "upgrade_path_needed"
                    })
                self.error_messages.error_code_messages({
                    "error_code": "cfg-143",
                    "line_code": ""
                })
                self.do_validation = False
            else:
                self.send_error("cfg-99") 

        try:
            self.yaml_dict = yaml.safe_load(yaml_data)
        except Exception as e:
            continue_to_error = True
            self.log.logger.error(f"configuration file [cn-config.yaml] error code [cfg-32] not able to be loaded into memory, nodectl will attempt to issue a fix... | error: [{e}]")
            if "passphrase" in str(e):
                change_made = self.yaml_passphrase_fix()
                if change_made:
                    with open(self.yaml_file, 'r', encoding='utf-8') as f:
                        yaml_data = f.read()
                    try:
                        self.yaml_dict = yaml.safe_load(yaml_data)
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
                   
        self.nodectl_config_simple_format_check = list(self.yaml_dict.keys())
        self.config_obj = {
            **self.config_obj,
            **self.yaml_dict[self.nodectl_config_simple_format_check[0]],
        }
        
        self.build_function_obj(self.config_obj) # rebuild function obj
        called_cmd = "show_version" if nodectl_only else "config_obj"

        if setup_version:
            self.versioning = Versioning({
                "config_obj": self.config_obj,
                "print_messages": False,
                "called_cmd": called_cmd,
            })
        self.functions.version_obj = self.versioning.get_version_obj()
        self.functions.set_statics()


    def check_for_migration(self,check_only=False):
        nodectl_version = self.functions.version_obj["node_nodectl_version"]
        nodectl_yaml_version = self.functions.version_obj["node_nodectl_yaml_version"]
                 
        validate = True
        if len(self.nodectl_config_simple_format_check) > 1 or "nodectl" not in self.nodectl_config_simple_format_check[0]:
            validate = False
            
        if not validate:
            self.error_messages.error_code_messages({
                "error_code": "cfg-180",
                "line_code": "config_error",
                "extra": "format",
                "extra2": None,
            })
        
        try:
            found_yaml_version = self.config_obj["global_elements"]["nodectl_yaml"]
        except:
            found_yaml_version = False
        
        if self.called_command in ["configurator","uninstall"]:
            self.log.logger.debug(f"configuration module found {self.called_command} request, skipping migration attempts.")
        elif not found_yaml_version or found_yaml_version != nodectl_yaml_version:
            if self.called_command == "auto_restart": 
                self.log.logger.warn(f"configuration validator found migration path for nodectl version [{nodectl_version}] - auto_restart detected, ignoring")
                exit(0)
            elif self.called_command == "upgrade_nodectl": 
                    self.log.logger.warn(f"configuration validator found migration path for nodectl version [{nodectl_version}] - nodectl_upgrade detected, by-passing")
                    self.functions.print_paragraphs([
                        [" WARNING ",0,"yellow,on_red"], ["upgrade may be required!",1,"yellow"],
                    ])
                    return
            elif self.called_command != "upgrade":
                self.error_messages.error_code_messages({
                    "error_code": "cfg-199",
                    "line_code": "upgrade_needed",
                    "extra": "Configuration yaml version mismatch."
                })
            self.log.logger.info(f"configuration validator found migration path for nodectl version [{nodectl_version}] - sending to migrator")
            self.migration()
        else:
            self.log.logger.debug(f"configuration validator did not find a migration need for current configuration format - nodectl version [{nodectl_version}]")    
            
            
    def finalize_config_tests(self):
        self.metagraph_list = self.functions.clear_global_profiles(self.config_obj)
        
        try:
            _ = json.dumps(self.yaml_dict, sort_keys=True, indent=4)
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
        copy2(self.yaml_file,temp_file)
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

        if path.isfile(temp_file):
            move(temp_file,self.yaml_file)
        self.functions.print_cmd_status({
            **progress,
            "status": "complete",
            "status_color": "green",
            "newline": True,
        })
        
        return return_value
        
        
    def migration(self):
        self.functions.config_obj = {
            **self.config_obj,
            **self.functions.config_obj,            
        }
        self.migrate = Migration({
            "caller": "config",
            "parent": self,
        })
        self.migrate.migrate()
        if self.migrate.verify_config_request:
            self.view_yaml_config("migrate")
        if self.migrate.do_migrate:
            self.build_yaml_dict(False,False)
            self.setup_config_vars({
                "key": "edge_point",
                "profile": list(self.config_obj.keys())[0],
                "environment": self.config_obj[list(self.config_obj.keys())[0]]["environment"],
            })
        

    def view_yaml_config(self,action):
        print_req = "all"
        if self.called_command == "view_config" or self.called_command == "-vc":
            self.build_function_obj({
                "global_elements": {"caller":"config"},
                "sudo_rights": True if "help" in self.argv_list else False,
            })
        
        self.argv_list.append("special_case")
        self.functions.check_for_help(self.argv_list,"view_config")
        self.functions.print_header_title({
            "line1": "YAML CONFIGURATION",
            "line2": "cn-config.yaml review",
            "clear": True,
            "newline": "top",
            "upper": False,
        })
        
        if "--section" in self.argv_list:
            print_req = ("section",self.argv_list[self.argv_list.index("--section")+1])
        elif "--passphrase" in self.argv_list: print_req = "pass"
        elif "--jar" in self.argv_list: print_req = "jar"
        elif "--custom" in self.argv_list: print_req = "custom"
        elif "--seed" in self.argv_list: print_req = "seed"
        elif "--priority" in self.argv_list: print_req = "priority"
        elif "--java" in self.argv_list: print_req = "java"
        elif "--directory" in self.argv_list: print_req = "directory"
        elif "--token" in self.argv_list: print_req = "token"
        elif "--link" in self.argv_list: print_req = "link"
        elif "--edge" in self.argv_list: print_req = "edge"
        elif "--basics" in self.argv_list: print_req = "basics"
        elif "--ports" in self.argv_list or "--tcp" in self.argv_list: print_req = "port"
        elif "--pro" in self.argv_list: print_req = "pro_"
        elif "--json" in self.argv_list:
            self.validated, self.do_validation = True, False
            self.action = "normal"
            self.implement_config()
            self.functions.print_clear_line()
            print(colored(json.dumps(self.config_obj,indent=3),"cyan",attrs=['bold']))
            exit("  view config yaml in json format")
            
        do_more = False if "-np" in self.argv_list else True
        section_start, more = False, False
        n = 1
        
        def execute_print(line,req,n): 
            if "global_p12" in line:
                pass
            if req != "all" and req != "section":
                do_print = False
                if line.startswith("#") or line.startswith("-"): return n 
                elif req not in line and (not match(r'^  [^\s].*:$', line) and n > 1) or "global" in line: 
                    if req == "pass":
                        if "global" in line and "p12" in line or "encryption" in line: 
                            do_print = True
                    if req == "token" and line.startswith("  global_elements") or req in line: 
                        do_print = True
                    if req == "basics":
                        basics = ["profile_enable","environment","description",
                                  "node_type","meta_type","layer","collateral","service",
                                  "yaml_config_name","metagraph_name","local_api","includes",
                                  "developer_mode","log_level","nodectl_yaml"]
                        for key in basics:
                            if key in line:
                                do_print = True
                                break
                        if match(r'^  [^\s].*:$', line) and (not "global_p12" in line and not "global_auto_restart" in line):
                                 do_print = True
                    
                    if not do_print: return n

            print(colored(line.strip("\n"),"blue",attrs=['bold']))
            return n+1
        
        if path.isfile(f"{self.functions.nodectl_path}cn-config.yaml"):
            with open(f"{self.functions.nodectl_path}cn-config.yaml","r") as file:
                for line in file:
                    console_size = get_terminal_size()
                    more_break = round(console_size.lines)-15

                    if isinstance(print_req,tuple):
                        if print_req[0] == "section" or section_start:
                            if section_start or match(r'^  [^\s].*:$', line):
                                if section_start or print_req[1] in line:
                                    if section_start and match(r'^  [^\s].*:$', line):
                                        break
                                    section_start = True
                                    n = execute_print(line,"section",n)
                    else:
                        n = execute_print(line,print_req,n)
                    
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
            try:
                self.config_obj["global_p12"]["passphrase"] = self.argv_list[self.argv_list.index("--pass")+1]
            except:
                self.functions.check_for_help(["help"],"configure")

        
    def create_path_variable(self, path, file):
        try:
            path = f"{path}/{file}" if path[-1] != "/" else f"{path}{file}"
        except:
            return False
        
        path = self.functions.cleaner(path,"double_slash")
        return path


    def setup_config_vars(self,one_off=False):
        # one_off: called from migrator to find edge_point* ( introduced >v2.13.0 )
        # sets up the automated values not present in the 
        # yaml file

        if self.action == "edit_config_from_new": return # updating defaults not necessary

        def error_found(
                section,missing_keys=False,value=False,
                profile=False,special=False
        ):
            self.error_found = True
            self.error_list.append({
                "title": "section_missing",
                "section": section,
                "profile": profile if profile else None,
                "type": "section",
                "key": "multiple",
                "missing_keys": missing_keys if missing_keys else None,
                "value": value if value else "global_p12",
                "special_case": special if special else None
            }) 
            
        # The following defaults objects is for config elements that can be set to
        # "default" by the Node Operator to obtain the current default values.  
            
        defaults = {
            "directory_backups": f"{self.functions.default_tessellation_dir}backups/",
            "directory_uploads": f"{self.functions.default_tessellation_dir}uploads/",
            "seed_location": self.functions.default_seed_location, # profile will be added to the path during iteration below
            "pro_rating_file": "ratings.csv",
            "pro_rating_location": self.functions.default_pro_rating_location,
            "priority_source_file": "priority-list",
            "priority_source_location": self.functions.default_priority_source_location,
            "jar_file": {
                "hypergraph":  {
                    0: "cl-node.jar",
                    1: "cl-dag-l1.jar",
                },
                "dor-metagraph": {
                    "dor-l0": " metagraph-l0.jar",
                    "dor-dl1": "data-l1.jar",
                    "dor-cl1": "currency-l1.jar",
                },
            },
            "jar_repository": {
                "dor-metagraph": "github.com/Constellation-Labs/dor-metagraph/", 
            },
            "edge_point": {
                "mainnet": "mainnet.constellationnetwork.io",
                "testnet": "testnet.constellationnetwork.io",
                "integrationnet": "integrationnet.constellationnetwork.io",
                "dor-metagraph": "54.191.143.191",
            },
            "seed_file": {
                "dor-metagraph": {
                    "dor-l0": "ml0-",
                    "dor-dl1": "dl1-",
                    "dor-cl1": "cl1-",
                },
            },
            "token_coin_id": {
                "mainnet": "constellation-labs",
                "testnet": "constellation-labs",
                "integrationnet": "constellation-labs",
                "dor-metagraph": "dor",
            },
            "token_identifier": {
                "hypergraph": "disable",
                "dor-metagraph": "DAG0CyySf35ftDQDQBnd1bdQ9aPyUdacMghpnCuM",
            },
            "edge_point_tcp_port": {
                "hypergraph": 443,
                "dor-metagraph": 9000
            },
            "public_port": [9000,9010],
            "p2p_port": [9001,9011],
            "cli_port": [9002,9012],
            "java_xms": "1024M",
            "java_xss": "256K",
            "java_xmx": ["7G","3G"],
            "collateral": {
                "hypergraph": 0,
                "dor-metagraph": 0,
            },
            "service": {
                "hypergraph": {
                    "mainnet": "node_l",
                    "testnet": "node_l",
                    "integrationnet": "intnetserv_l",
                },
                "dor-metagraph": {
                    "dor-l0": "dor_ml",
                    "dor-dl1": "dor_dl",
                    "dor-cl1": "dor_cl",
                }
            }
        }
        
        def handle_edge_point(o_profile, o_environment, metagraph_name):
            if metagraph_name in ["mainnet","testnet","integrationnet"]: metagraph_name = "hypergraph" # < v2.13.0
            if "dor" in o_environment: metagraph_name = "dor_metagraph" # < v2.13.0
            
            if self.config_obj[o_profile]["edge_point"] == "default" and metagraph_name == "hypergraph":
                prefix_layer = f'l{self.config_obj[o_profile]["layer"]}-lb-'
                self.config_obj[o_profile]["edge_point"] = f'{prefix_layer}{defaults["edge_point"][o_environment]}'
            elif self.config_obj[o_profile]["edge_point"] == "default":
                self.config_obj[o_profile]["edge_point"] = defaults["edge_point"][metagraph_name]
            if self.config_obj[o_profile]["edge_point_tcp_port"] == "default":
                self.config_obj[o_profile]["edge_point_tcp_port"] = defaults["edge_point_tcp_port"][metagraph_name]
            return
        
        if isinstance(one_off,dict):
            if one_off["key"] == "edge_point":
                handle_edge_point(one_off["profile"], one_off["environment"], one_off["environment"])
                return
            if one_off["key"] == "default_edge":
                host_default, port_default  = False, False
                try:
                    if defaults["edge_point"][one_off["env"]] in one_off["host"]:
                        host_default = True
                    if defaults["edge_point_tcp_port"][one_off["graph"]] == one_off["port"]:
                        port_default = True
                except: pass
                return (host_default,port_default)
            if one_off["key"] == "default_col":
                try:
                    return True if defaults["collateral"][one_off["graph"]] == one_off["col"] else False
                except: return False
            if one_off["key"] == "default_service":
                try:
                    service = defaults["service"][one_off["graph"]]
                    service = service[one_off["env"]]
                    service = f"{service}{one_off['layer']}"
                    return service if service == one_off["service"] else False 
                except: return False                                               
            if one_off["key"] == "default_tcp":
                result_set = list()
                try:
                    for port in ["public_port","p2p_port","cli_port"]:
                        result_set.append(True if defaults[port][one_off["layer"]] == one_off[port] else False)
                    return result_set
                except: return (False,False,False)                                               

        try:
            self.config_obj["global_p12"]["key_store"] = self.create_path_variable(
                self.config_obj["global_p12"]["key_location"],
                self.config_obj["global_p12"]["key_name"],
            ) 
        except:
            error_found(False,"key_store")

        metagraph_name = self.config_obj["global_elements"]["metagraph_name"]
        if isinstance(metagraph_name,list):
            # placeholder for multiple Node VPS
            pass

        if self.config_obj["global_elements"]["metagraph_token_coin_id"] == "default":
            if metagraph_name == "hypergraph":
                self.config_obj["global_elements"]["metagraph_token_coin_id"] = "constellation-labs" 
            else:
                try:
                    self.config_obj["global_elements"]["metagraph_token_coin_id"] = defaults["token_coin_id"][metagraph_name]
                except:
                    self.log.logger.warn("config -> during configuration setup, nodectl could not determine the coin token id, defaulting to [constellation-labs]")
                    self.config_obj["global_elements"]["metagraph_token_coin_id"] = "constellation-labs"

        if self.config_obj["global_elements"]["metagraph_token_identifier"] == "default":
            try:
                self.config_obj["global_elements"]["metagraph_token_identifier"] = defaults["token_identifier"][metagraph_name]
            except:
                self.log.logger.warn("config -> during configuration setup, nodectl could not determine the token identifier")
                error_found("global","metagraph_token_identifier")

        for profile in self.metagraph_list:
            self.config_obj[profile]["p12_key_alias"] = "str" # init (updated outside this method)

            try:
                self.config_obj[profile]["p12_key_store"] = self.create_path_variable(
                    self.config_obj[profile]["p12_key_location"],
                    self.config_obj[profile]["p12_key_name"]
                )
            except KeyError:
                    error_found("profile","p12_key_store","valid p12 keystore value",profile)
                
            # does the profile link through itself?
            try:
                self.config_obj[profile]["ml0_link_is_self"] = True
                if self.config_obj[profile]["ml0_link_profile"] == "None":
                    self.config_obj[profile]["ml0_link_is_self"] = False
            except KeyError:
                error_found("profile","ml0_link_profile","error with linking section",profile)
            try:
                self.config_obj[profile]["gl0_link_is_self"] = True
                if self.config_obj[profile]["gl0_link_profile"] == "None":
                    self.config_obj[profile]["gl0_link_is_self"] = False
            except KeyError:
                error_found("profile","gl0_link_profile","error with linking section",profile)

            self.config_obj[profile]["is_jar_static"] = False        
            if self.config_obj[profile]["jar_repository"] != "default":
                self.config_obj[profile]["is_jar_static"] = True

            try:
                if self.config_obj[profile]["token_coin_id"] == "global":
                    self.config_obj[profile]["token_coin_id"] = self.config_obj["global_elements"]["metagraph_token_coin_id"] 
            except KeyError:
                error_found("profile","token_coin_id","error with profile section",profile)

            try:         
                if self.config_obj[profile]["token_identifier"] == "global":
                    self.config_obj[profile]["token_identifier"] = self.config_obj["global_elements"]["metagraph_token_identifier"]
            except KeyError:
                error_found("profile","token_identifier","error with profile section",profile)

            environment = self.config_obj[profile]["environment"]

            layer = int(self.config_obj[profile]["layer"])
            for tdir, def_value in defaults.items():
                try:
                    if self.config_obj[profile][tdir] == "default":
                        if tdir == "seed_file": 
                            self.config_obj[profile][tdir] = f"{environment}-{self.functions.default_seed_file}"
                            if metagraph_name != "hypergraph":
                                self.config_obj[profile][tdir] = f"{defaults[tdir][metagraph_name][profile]}{self.config_obj[profile][tdir]}" 
                        elif tdir == "priority_source_file": 
                            self.config_obj[profile][tdir] = f"{metagraph_name}-{def_value}" 
                        elif tdir == "jar_repository": 
                            try:
                                self.config_obj[profile][tdir] = defaults[tdir][metagraph_name]
                            except:
                                # hypergraph exception
                                self.config_obj[profile][tdir] = "github.com/Constellation-Labs/tessellation/"
                        elif "edge_point" in tdir:
                            handle_edge_point(profile,environment, metagraph_name)
                        elif tdir == "seed_location":
                            self.config_obj[profile][tdir] = f"{def_value}/{profile}"
                            self.config_obj[profile][tdir] = self.functions.cleaner(self.config_obj[profile][tdir],"double_slash")
                        elif tdir == "collateral":
                            try:
                                self.config_obj[profile][tdir] = def_value[metagraph_name]
                            except:
                                self.log.logger.warn("config -> during configuration setup, nodectl could not determine collateral setting to [0]")
                                self.config_obj[profile][tdir] = 0                            
                        elif tdir == "service":
                            try:
                                services = def_value[metagraph_name]
                            except:
                                raise Exception("invalid service default value")
                            else:
                                s_key = profile
                                if metagraph_name == "hypergraph": s_key = environment
                                self.config_obj[profile][tdir] = f"{services[s_key]}{layer}"
                        elif tdir == "jar_file":
                            j_key = profile
                            if metagraph_name == "hypergraph":
                                j_key = layer
                            self.config_obj[profile][tdir] = def_value[metagraph_name][j_key]
                        elif isinstance(def_value,list):
                            self.config_obj[profile][tdir] = def_value[layer]
                        elif tdir == "token_coin_id":
                            try:
                                self.config_obj[profile][tdir] = defaults[tdir][metagraph_name]
                            except:
                                self.log.logger.warn("config -> during configuration setup, nodectl could not determine the token coin setting to default [constellation-labs]")
                                self.config_obj[profile][tdir] = "constellation-labs"                            
                        else: 
                            self.config_obj[profile][tdir] = def_value  
                except Exception as e:
                    self.log.logger.error(f"setting up configuration variables error detected [{e}]")
                    error_found("profile",tdir,"error setting defaults",profile)

            self.config_obj[profile]["jar_github"] = False 
            if "github.com" in self.config_obj[profile]["jar_repository"]:
                self.config_obj[profile]["jar_github"] = True 

            try:
                if self.config_obj[profile]["seed_repository"] == "default": 
                    self.config_obj[profile]["seed_repository"] = self.config_obj[profile]["jar_repository"] 
            except KeyError:
                error_found("profile","seed_repository","error with profile section",profile)
            
            try:
                if self.config_obj[profile]["jar_location"] == "default": 
                    self.config_obj[profile]["jar_location"] = f"{self.functions.default_tessellation_dir}{profile}/"
            except KeyError:
                error_found("profile","jar_location","error with profile section",profile)
            
            self.config_obj[profile]["seed_github"] = False 
            if "github.com" in self.config_obj[profile]["seed_repository"]:
                self.config_obj[profile]["seed_github"] = True 
                
            try:
                if self.config_obj[profile]["seed_version"] == "default":
                    self.config_obj[profile]["seed_version"] = self.config_obj[profile]["jar_version"]
            except KeyError:
                self.log.logger.error(f"setting up configuration variables error detected [seed_version]")
                error_found("profile","seed_version","invalid or missing value",profile)
                
            try:
                self.config_obj[profile]["jar_path"] = self.create_path_variable(
                    self.config_obj[profile]["jar_location"],
                    self.config_obj[profile]["jar_file"]
                )
            except KeyError as e:
                self.log.logger.error(f"setting up configuration variables error detected [{e}]")
                error_found("profile",e.args[0],"invalid or missing value",profile)
                
            try:
                if self.config_obj[profile]["seed_location"] == "disable":
                    self.config_obj[profile]["seed_path"] = "disable"
                elif self.config_obj[profile]["seed_location"] == "default":
                    self.config_obj[profile]["seed_path"] = "default"
                else:
                    self.config_obj[profile]["seed_path"] = self.create_path_variable(
                        self.config_obj[profile]["seed_location"],
                        self.config_obj[profile]["seed_file"]
                    )
            except KeyError as e:
                self.log.logger.error(f"setting up configuration variables error detected [{e}]")
                error_found("profile",e.args[0],"invalid or missing value",profile)
                
            try:
                value = "location of filename"
                if self.config_obj[profile]["priority_source_location"] == "disable":  
                    self.config_obj[profile]["priority_source_path"] = "disable"
                elif self.config_obj[profile]["priority_source_location"] == "default":
                    self.config_obj[profile]["priority_source_path"] = "default"
                else:
                    self.config_obj[profile]["priority_source_path"] = self.create_path_variable(
                        self.config_obj[profile]["priority_source_location"],
                        self.config_obj[profile]["priority_source_file"]
                    )
                    # exception rating file is a static user added file
                    if not path.exists(self.config_obj[profile]["priority_source_location"]):
                        value = self.config_obj[profile]["priority_source_location"]
                        raise KeyError
            except KeyError as e:
                self.log.logger.error(f"setting up configuration variables error detected [{e}]")
                error_found("profile",e.args[0],"invalid or missing value",profile)
                
            try:
                value = "invalid location of filename"
                if self.config_obj[profile]["pro_rating_location"] == "disable":  
                    self.config_obj[profile]["pro_rating_path"] = "disable"
                elif self.config_obj[profile]["pro_rating_location"] == "default":
                    self.config_obj[profile]["pro_rating_path"] = "default"
                else:
                    self.config_obj[profile]["pro_rating_path"] = self.create_path_variable(
                        self.config_obj[profile]["pro_rating_location"],
                        self.config_obj[profile]["pro_rating_file"]
                    )
                    # exception rating file is a static user added file
                    if not path.exists(self.config_obj[profile]["pro_rating_path"]):
                        value = self.config_obj[profile]["pro_rating_path"]
                        raise KeyError
            except KeyError as e:
                self.log.logger.error(f"setting up configuration variables error detected [{e}]")
                error_found("profile",e.args[0],value,profile)
                
            self.config_obj[profile]["p12_validated"] = False # initialize to False
            self.config_obj[profile]["static_peer"] = False # initialize to False
        
        if "install" in self.action:
            return self.config_obj
        
        if self.config_obj["global_elements"]["local_api"] != "enable" and self.config_obj["global_elements"]["local_api"] != "disable":
            self.log.logger.error(f"setting up configuration variables error detected [local_api]")
            error_found("global_elements","local API definition invalid",self.config_obj["global_elements"]["local_api"],"global")
        
        self.config_obj["global_elements"]["caller"] = None  # init key (used outside of this class)
        self.config_obj["global_p12"]["p12_validated"] = False  # init key (used outside of this class)
        self.config_obj["global_p12"]["key_alias"] = "str" # init key (updated outside this class)
            
            
    def prepare_p12(self):
        self.log.logger.debug("p12 passphrase setup...")
           
        p12_obj = {
            "caller": "config",
            "action": "normal_ops",
            "process": "normal_ops",
            "functions": self.functions,
        }
        self.p12 = P12Class(p12_obj)
        self.p12.functions = self.functions
                        
    
    def remove_disabled_profiles(self):
        remove_list = []
        
        for profile in self.metagraph_list:
            if not self.config_obj[profile]["profile_enable"]:
                if "edit_config" not in self.argv_list:
                    remove_list.append(profile)

        for profile in remove_list:
            self.config_obj.pop(profile)
            self.metagraph_list.pop(self.metagraph_list.index(profile))


    def is_passphrase_required(self):
        passphrase_required_list = [
            "start","stop","upgrade","restart","check_seedlist",
            "nodeid","id","export_private_key","show_p12_details",
            "leave","join", "upgrade",
            "passwd","clean_snapshots","clean_files",
            "auto_restart", "refresh_binaries","sec"
        ]                
        if self.called_command in passphrase_required_list:
            return True
        return False
    

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
                    "line2": profile,
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
            for profile in self.metagraph_list:
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
                    "global": False,
                    "profile": profile,
                })
                cmd = "java -jar /var/tessellation/cl-wallet.jar show-id"
                self.nodeid = self.functions.process_command({
                    "bashCommand": cmd,
                    "proc_action": "poll"
                })
                if match(pattern,self.nodeid):
                    return True
                sleep(1)
            return False

        write_out, success = False, False
        attempts = 0
        print_str = colored('  Replacing configuration ','green')+colored('"self "',"yellow")+colored('items: ','green')
        profile_obj = self.config_obj; self.profile_obj = profile_obj

        if not self.auto_restart and not self.versioning_service:
            self.functions.print_clear_line()
        
        try:
            for profile in self.metagraph_list:
                self.setup_p12_aliases(profile)
                if profile_obj[profile]["profile_enable"] and self.action != "edit_config":
                    for m_or_g in ["ml0","gl0"]:
                        if profile_obj[profile][f"{m_or_g}_link_host"] == "self":
                            print(f"{print_str}{colored('link host ip','yellow')}",end="\r")
                            sleep(.8) # allow user to see
                            profile_obj[profile][f"{m_or_g}_link_host"] = self.functions.get_ext_ip() 

                        if profile_obj[profile][f"{m_or_g}_link_port"] == "self":
                            print(f"{print_str}{colored('link public port','yellow')}",end="\r")
                            sleep(.8) # allow user to see
                            link_profile_port = self.config_obj[self.config_obj[profile][f"{m_or_g}_link_profile"]]["public_port"]
                            profile_obj[profile][f"{m_or_g}_link_port"] = link_profile_port 

                        if profile_obj[profile][f"{m_or_g}_link_key"] == "self":
                            self.setup_passwd(True)
                            while True:
                                print(f"{print_str}{colored('link host public key','yellow')}",end="\r")
                                if not write_out:
                                    write_out = True
                                    if not success:
                                        success = grab_nodeid(profile)
                                if success:
                                    self.nodeid = self.nodeid.strip("\n")
                                    profile_obj[profile][f"{m_or_g}_link_key"] = self.nodeid
                                    break
                                sleep(2)
                                attempts += 1
                                if attempts > 2:
                                    self.error_messages.error_code_messages({
                                        "error_code": "cfg-337",
                                        "line_code": "node_id_issue",
                                        "extra": "config"
                                    })
                        if profile_obj[profile][f"{m_or_g}_link_key"] == "external":
                            node_id = self.functions.get_api_node_info({
                                "api_host": profile_obj[profile][f"{m_or_g}_link_host"],
                                "api_port": profile_obj[profile][f"{m_or_g}_link_port"],
                                "info_list": ["id"],
                            })[0]
                            self.log.logger.info(f"config -> external [{m_or_g}] link key found, acquired: nodeid [{node_id}]")
                            profile_obj[profile][f"{m_or_g}_link_key"] = node_id

                if write_out:  
                    g_done_ip, g_done_key, g_done_port, current_profile, skip_write = False, False, False, False, False
                    m_done_ip, m_done_key, m_done_port = False, False, False
                    self.log.logger.warn("config -> found [self] key words in yaml setup, changing to static values to speed up future nodectl executions")        
                    f = open(f"{self.functions.nodectl_path}cn-config.yaml")
                    with open("/var/tmp/cn-config-temp.yaml","w") as newfile:
                        for line in f:
                            skip_write = False
                            if f"{profile}:" in line:
                                current_profile = True
                            if current_profile:
                                if "ml0_link_key: self" in line and not m_done_key:
                                    newfile.write(f"    ml0_link_key: {self.nodeid}\n")
                                    self.log.logger.info(f"config -> self [ml0] link key found, updating config [{self.nodeid}]")
                                    m_done_key,skip_write = True, True
                                elif "ml0_link_host: self" in line and not m_done_ip:
                                    newfile.write(f"    ml0_link_host: {self.functions.get_ext_ip()}\n")
                                    m_done_ip, skip_write = True, True
                                elif "ml0_link_port: self" in line and not m_done_port:
                                    newfile.write(f"    ml0_link_port: {link_profile_port}\n")
                                    m_done_port, skip_write = True, True

                                elif "gl0_link_key: self" in line and not g_done_key:
                                    newfile.write(f"    gl0_link_key: {self.nodeid}\n")
                                    g_done_key,skip_write = True, True
                                elif "gl0_link_host: self" in line and not g_done_ip:
                                    newfile.write(f"    gl0_link_host: {self.functions.get_ext_ip()}\n")
                                    g_done_ip, skip_write = True, True
                                elif "gl0_link_port: self" in line and not g_done_port:
                                    newfile.write(f"    gl0_link_port: {link_profile_port}\n")
                                    g_done_port, skip_write = True, True

                            if not skip_write:
                                newfile.write(line)
                    newfile.close()
                    f.close()
                    if path.isfile("/var/tmp/cn-config-temp.yaml"):
                        move("/var/tmp/cn-config-temp.yaml",f"{self.functions.nodectl_path}cn-config.yaml")

        except Exception as e:
            self.error_messages.error_code_messages({
                "error_code": "cfg-942",
                "line_code": "unknown_error",
                "extra": e,
            })
    

    def setup_p12_aliases(self,profile):
        argv_list = ["-p", profile, "--alias", "--return", "--config"]
        p12_alias = self.p12.show_p12_details(argv_list)

        if not p12_alias:
            self.validated = False
            self.error_list.append({
                "title":"p12 alias extraction",
                "section": "p12",
                "profile": profile,
                "missing_keys": None, 
                "type": "global",
                "key": "p12_key_name, p12_passphrase",
                "special_case": None,
                "value": "skip"
            })
        
        key = "p12_key_alias"
        if profile == "global_p12": key = "key_alias"
        self.config_obj[profile][key] = p12_alias


    def setup_schemas(self):   
        # ===================================================== 
        # schema order of sections needs to be in the exact
        # same order as the yaml file setup both in the profile
        # list values and each profile subsection below that...
        # =====================================================         
        self.schema = {
            "metagraphs": [
                ["profile_enable","bool"],
                ["environment","str"],
                ["description","str"],
                ["node_type","node_type"],                
                ["meta_type","meta_type"],                
                ["layer","layer"],   
                ["collateral","int"],
                ["service","str"],
                ["edge_point","host"],
                ["edge_point_tcp_port","port"],
                ["public_port","high_port"], 
                ["p2p_port","high_port"], 
                ["cli_port","high_port"], 
                ["gl0_link_enable","bool"],
                ["gl0_link_key","128hex"], # automated value [not part of yaml]
                ["gl0_link_host","host"], 
                ["gl0_link_port","self_port"],
                ["gl0_link_profile","str"],
                ["gl0_link_is_self","bool"], # automated value [not part of yaml]
                ["ml0_link_enable","bool"],
                ["ml0_link_key","128hex"], # automated value [not part of yaml]
                ["ml0_link_host","host"], 
                ["ml0_link_port","self_port"],
                ["ml0_link_profile","str"],
                ["token_identifier","wallet"],
                ["token_coin_id","str"],
                ["ml0_link_is_self","bool"], # automated value [not part of yaml]
                ["directory_backups","path_def"],
                ["directory_uploads","path_def"],
                ["java_xms","mem_size"],
                ["java_xmx","mem_size"],
                ["java_xss","mem_size"],
                ["jar_location","path_def"],
                ["jar_path","path_def"], # automated value [not part of yaml]
                ["jar_repository","host_def"], 
                ["jar_version","str"],
                ["jar_file","str"],
                ["is_jar_static","bool"], # automated value [not part of yaml]
                ["jar_github","bool"], # automated value [not part of yaml]
                ["p12_nodeadmin","str"],
                ["p12_key_location","path"],
                ["p12_key_name","str"],
                ["p12_key_alias","str"], # automated value [not part of yaml]
                ["p12_passphrase","str"], 
                ["p12_key_store","str"], # automated value [not part of yaml] 
                ["p12_validated","bool"], # automated value [not part of yaml]             
                ["seed_location","path_def_dis"],
                ["seed_repository","host_def_dis"],
                ["seed_github","bool"], # automated value [not part of yaml]
                ["seed_version","str"],
                ["seed_file","str"],             
                ["seed_path","path_def_dis"], # automated value [not part of yaml]
                ["pro_rating_location","path_def_dis"], 
                ["pro_rating_file","str"], 
                ["pro_rating_path","path_def_dis"], # automated value [not part of yaml]     
                ["priority_source_location","path_def_dis"],
                ["priority_source_repository","host_def_dis"],
                ["priority_source_file","str"],             
                ["priority_source_path","path_def_dis"], # automated value [not part of yaml]
                ["custom_args_enable","bool"],
                ["custom_env_vars_enable","bool"],
                ["global_p12_all_global","bool"], # automated value [not part of yaml]
                ["global_p12_passphrase","bool"], # automated value [not part of yaml]
                ["global_p12_key_location","bool"], # automated value [not part of yaml]
                ["global_p12_key_name","bool"], # automated value [not part of yaml]
                ["global_p12_nodeadmin","bool"], # automated value [not part of yaml]
                ["global_p12_encryption","bool"], # automated value [not part of yaml]
                ["global_p12_key_alias","bool"], # automated value [not part of yaml]
                ["global_p12_cli_pass","bool"], # automated value [not part of yaml]
                ["static_peer","bool"], # automated value [not part of yaml]
            ],
            "global_auto_restart": [
                ["auto_restart","bool"],
                ["auto_upgrade","bool"],
                ["on_boot","bool"],
                ["rapid_restart","bool"],
            ],
            "global_p12": [
                ["nodeadmin","str"],
                ["key_location","path"],
                ["key_name","str"],
                ["key_alias","str"], # automated value [not part of yaml]
                ["passphrase","str"],
                ["encryption","bool"], 
                ["key_store","str"], # automated value [not part of yaml]
                ["p12_validated","bool"], # automated value [not part of yaml]
            ],
            "global_elements": [
                ["yaml_config_name","str"],
                ["metagraph_name","str"],
                ["metagraph_token_identifier","wallet"],
                ["metagraph_token_coin_id","str"],
                ["local_api","str"],
                ["nodectl_yaml","str"],
                ["includes","bool"],
                ["developer_mode","bool"],  
                ["log_level","log_level"],
                ["use_offline","bool"],
            ]
        }
        
        # make sure to update validate_profile_types -> int_types or enabled_section
        # as needed if the schema changes
        
        # set section progress dict
        self.global_section_completed = {
            "global_p12": False,
            "global_auto_restart": False,
        }
        
        
    def setup_path_formats(self,profile):
        def check_slash(st_val,path_value,s_type):
            if "def" in st_val and path_value == "default": return
            if "dis" in st_val and path_value == "disable": return
            try:
                if path_value[-1] != "/": 
                    self.config_obj[profile][s_type] = f"{path_value}/"
            except:
                self.error_messages.error_code_messages({
                    "error_code": "cfg-896",
                    "line_code": "config_error",
                    "extra": "format",
                })
                           
        try:
            for section, section_types in self.schema.items():
                if "global" not in profile and "global" not in section:
                    for s_type, st_val in section_types:
                        if "path" not in s_type and "path" in st_val:
                            path_value = self.config_obj[profile][s_type]
                            check_slash(st_val,path_value,s_type)
        except Exception as e:
            self.log.logger.error(f"setup_path_formats -> p12 issue found - may have a configuration file error - check for trailing slash in p12 path file.")
            self.error_messages.error_code_messages({
                "error_code": "cfg-819",
                "line_code": "config_error",
                "extra": "format",
            })
                        
        if profile == "global_p12":
            path_value = self.config_obj[profile]["key_location"]
            s_type = "key_location"
            check_slash("key_location",path_value,s_type)
                

    def validate_yaml_keys(self):
        missing_list = []
        not_in_list = [
            "seed_path","pro_rating_path","static_peer",
            "gl0_link_is_self","ml0_link_is_self",
            "p12_key_store","jar_github", "jar_path",
        ]

        for config_key, config_value in self.config_obj.items():
            if "global" not in config_key:
                missing =  [item[0] for item in self.schema["metagraphs"]] - config_value.keys()
                missing = [x for x in missing if x not in not_in_list]
                for item in missing:
                    missing_list.append([config_key, item])
            if "global" in config_key:
                section = self.schema[config_key]
                missing_list = [[config_key, section_item[0]] for section_item in section if section_item[0] not in config_value.keys()]

        if len(missing_list) > 0:
            self.validated = False
            for error in missing_list:
                profile, missing_key = error
                self.error_list.append({
                    "title": "invalid cn-config.yaml",
                    "section": "hypergraph/metagraph profiles",
                    "profile": profile,
                    "missing_keys": missing_key, 
                    "key": None,
                    "type": "yaml",
                    "special_case": None,
                    "value": "skip"
                })                        
                
                            
    def validate_profiles(self):
        self.log.logger.debug("[validate_config] method called.")
        self.num_of_global_sections = 3  # global_auto_restart, global_p12, global_elements
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
        self.config_obj["global_elements"]["use_offline"] = True
        # global_p12_keys = ["key_name","passphrase","key_alias"] # test to make sure if one key is global all must be
        global_p12_keys = ["key_name","passphrase"] # test to make sure if one key is global all must be

        default_globals = ["global_p12_all_global", "global_p12_encryption", 
                           "global_p12_key_alias", "global_p12_key_location"]
        
        for profile in self.metagraph_list:
            try:
                self.config_obj[profile].update({key: False for key in default_globals})
                g_tests = [self.config_obj[profile][f"p12_{x}"] for x in self.config_obj["global_p12"] if x in global_p12_keys]
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
                        "key": "p12_key_name, p12_passphrase",
                        "special_case": None,
                        "value": "skip"
                    })
                    
                g_tests = [self.config_obj[profile][f"p12_{x}"] for x in self.config_obj["global_p12"] if x != "encryption"]
                if g_tests.count("global") == len(self.config_obj["global_p12"])-1: # ignore encryption element
                    # test if everything is set to global
                    self.config_obj[profile].update({key: True for key in default_globals})

                if self.config_obj[profile]["p12_nodeadmin"] == "global":
                    self.config_obj[profile]["global_p12_nodeadmin"] = True
                if self.config_obj[profile]["p12_key_location"] == "global":
                    self.config_obj[profile]["global_p12_key_location"] = True
                if self.config_obj[profile]["p12_passphrase"] == "global":
                    self.config_obj[profile]["global_p12_passphrase"] = True

                if self.config_obj["global_p12"]["encryption"]: 
                    self.config_obj[profile]["global_p12_encryption"] = True

                if self.config_obj[profile]["token_coin_id"] == "global":
                    self.config_obj[profile]["token_coin_id"] = self.config_obj["global_elements"]["metagraph_token_coin_id"]

            except Exception as e:
                self.log.logger.critical(f"configuration format failure detected | exception [{e}]")
                if self.action == "edit_config_from_new":
                    self.log.logger.warn("configuration -> configuration override detected, ignoring error and continuing.")
                    # since we have an error, we will bypass the p12 details and assume they are global
                    self.config_obj[profile]["global_p12_all_global"] = True
                    continue
                else:
                    self.send_error("cfg-705","format","existence")
            
        for profile in self.metagraph_list:
            if not self.config_obj[profile]["global_p12_all_global"]:
                self.config_obj["global_elements"]["all_global"] = False
            for p12_key, p12_value in self.config_obj[profile].items():
                if self.action == "edit_config":
                    if "p12_" in p12_key and "global" in p12_key:
                        self.config_obj[profile][p12_key] = False
                else:
                    if "p12_" in p12_key and "global" not in p12_key:
                        if "global" in p12_value:
                            self.config_obj[profile][f"global_{p12_key}"] = True
                            self.config_obj[profile][p12_key] = self.config_obj["global_p12"][p12_key[4:]]
                        else:
                            self.config_obj[profile][f"global_{p12_key}"] = False
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
        for m_or_g in ["ml0","gl0"]:
            link_profiles = []            
            for profile in self.metagraph_list:
                link_profile = self.config_obj[profile][f"{m_or_g}_link_profile"]
                if link_profile != "None":
                    link_profiles.append((profile,link_profile)) 
                    
            for profile in link_profiles:
                if self.config_obj[profile[0]][f"{m_or_g}_link_enable"]:
                    if profile[0] == profile[1]:
                        self.error_list.append({
                            "title":"Link Profile Dependency Conflict",
                            "section": f"{m_or_g}_link",
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
                            "section": f"{m_or_g}_link",
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
            section = "cluster"
        elif not skip:
            key_list = [x[0] for x in self.schema[profile]]
            section = profile.replace("global_","")
            
        if not skip and sorted(key_list) != sorted(found_list):
            missing1 = [x for x in key_list if x not in found_list]
            missing2 = [x for x in found_list if x not in key_list]
            missing = set(missing1 + missing2)
            special_case = "missing"
            if len(missing2) > len(missing1): special_case = "invalid"
            self.validated = False
            self.error_list.append({
                "title": "key_existence",
                "section": section,
                "profile": profile,
                "type": "key",
                "key": "multiple",
                "value": missing,
                "special_case": special_case
            })
        
        if "global" not in profile:
            self.validate_profile_types(profile)
        if self.validated:
            self.setup_path_formats(profile)

                
    def validate_profile_types(self,profile,return_on=False):
        validated, return_on_validated = True, True
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
            "meta_type": ["gl","ml"],
            "port": range(1,65535),
            "high_port": range(1024,65535),
            "self_port": range(1024,65535),
        }
        
        try:
            for section, section_types in self.schema.items():
                if "global" in section and not self.skip_global_validation:
                    profile = section
                for key, test_value in self.config_obj[profile].items():
                    for section_key, req_type in section_types:
                        if key == section_key: 
                            validated = False
                            
                            if skip_validation:
                                if "gl0_link" in key or "ml0_link" in key: validated = True
                                else: skip_validation = False
                            
                            if req_type in valuation_dict.keys():
                                try: validated = isinstance(test_value,valuation_dict[req_type])   
                                except Exception as e:
                                    for value in valuation_dict[req_type]:
                                        if test_value == value:
                                            validated = True
                                            break
                                        title = "invalid range"
                                if not validated: 
                                    title = "invalid type"
                                if "key_name" in key and req_type == "str":
                                    if test_value[-4::] != ".p12": title = "missing .p12 extension"
                                    else: validated = True
                                if (key == "gl0_link_enable" or key == "ml0_link_enable") and not test_value:
                                    skip_validation = True
                                if "passphrase" in key and test_value != "none" and req_type != "bool":
                                    if test_value == None:
                                        title = "invalid passphrase format entered as blank"
                                    elif "'" in test_value or '"' in test_value:
                                        title = "invalid single and or double quotes in passphrase"
                                if (key == "gl0_link_port" or key == "ml0_link_port") and test_value == "self":
                                    validated = True
                                
                            elif "host" in req_type:
                                if req_type == "host_def" and test_value == "default": validated = True
                                elif req_type == "host_def_dis" and test_value == "disable": validated = True
                                elif self.functions.test_hostname_or_ip(test_value,False) or test_value == "self": validated = True
                                else: title = "invalid host or ip"
                            
                            elif req_type == "128hex":
                                pattern = "^[a-fA-F0-9]{128}$"
                                if not match(pattern,test_value) and test_value != "self": title = "invalid nodeid"
                                else: validated = True 
                            
                            elif req_type == "wallet":
                                pattern = "^DAG[0-9][A-Za-z0-9]{36}"
                                if test_value == "global" or test_value == "disable": validated = True
                                elif not match(pattern,test_value): title = "invalid token identifier"
                                else: validated = True 
                                    
                            elif req_type == "list_of_strs":
                                title = "invalid list of strings"
                                if isinstance(test_value,list): validated = True
                                if validated:
                                    for v in test_value:
                                        if not isinstance(v,str):
                                            validated = False
                                            break                          

                            elif "path" in req_type:
                                # global paths replaced already
                                try:
                                    if "path" in key: validated = True # dynamic value skip validation
                                    if "path_def" in req_type and test_value == "default": validated = True
                                    elif req_type == "path_def_dis" and test_value == "disable": validated = True
                                    elif path.isdir(test_value): validated = True
                                    elif test_value == "disable" and self.config_obj[profile]["layer"] < 1:
                                        title = f"{test_value} is an invalid keyword for layer0"
                                    elif self.action == "edit_config" and "p12" in key and test_value == "global": validated = True
                                    elif test_value == "disable" or test_value == "default" or self.config_obj[profile]["layer"] < 1:
                                        title = f"{test_value} is an invalid keyword"
                                    elif not path.isdir(test_value): title = "invalid or path not found"
                                    else: validated = True
                                except KeyError as e:
                                    self.log.logger.debug(f"config -> configuration object missing keys | error [{e}]")
                                    validated = False
                                    title = "invalid configuration file"
                                except Exception as e:
                                    self.log.logger.debug(f"config -> configuration profile types issue | error [{e}]")
                                    validated = False
                                    title = "invalid configuration file"
                                    
                            elif req_type == "mem_size":
                                if not match("^(?:[0-9]){1,4}[MKG]{1}$",str(test_value)): title = "memory sizing format"
                                else: validated = True
                            
                            elif req_type == "log_level":
                                levels = ["NOTSET","DEBUG","INFO","WARN","ERROR","CRITICAL"]
                                if test_value.upper() not in levels: title = "invalid log level"
                                else: validated = True
                                
                            if not validated:
                                self.validated = False
                                return_on_validated = False
                                self.error_list.append({
                                    "title": title,
                                    "section": section,
                                    "profile": profile,
                                    "type": req_type,
                                    "key": key,
                                    "value": test_value,
                                    "special_case": special_case
                                })        
        except:
            self.log.logger.critical("config -> unable to validate configuration.  Corrupt or invalid.")
            self.error_messages.error_code_messages({
                "error_code": "cfg-1597",
                "line_code": "config_error",
                "extra": "format",
            })   
                     
        if return_on:
            return return_on_validated
        if not return_on_validated: 
            self.configurator_verified = False # only change once 
        self.skip_global_validation = True

        
    def validate_port_duplicates(self):
        found_ports = []
        found_keys = []
        error_keys = []
        ignore = ["gl0_link_port","ml0_link_port","edge_point_tcp_port"]
        
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
                "section": "cluster",
                "profile": "cluster",
                "type": "api_port_dups",
                "missing_keys": error_keys,
                "key": None,
                "value": duplicates,
                "special_case": None,
            })    


    def validate_seedlist_duplicates(self):
        seeds = []; duplicates = []
        seeds = [self.config_obj[profile]["seed_path"] for profile in self.metagraph_list if "disable" not in self.config_obj[profile]["seed_path"]]
        seeds_set = set(seeds)
        if len(seeds_set) != len(seeds):
            self.validated = False
            for seed in seeds:
                if seeds.count(seed) > 1 and seed not in duplicates:
                    duplicates.append(seed)
        
        if not self.validated:
            self.error_list.append({
                "title": "duplicate seed path found",
                "section": "cluster",
                "profile": "cluster",
                "type": "seed_path_dups",
                "missing_keys": "seed_location, seed_file",
                "key": None,
                "value": duplicates,
                "special_case": None,
            })  
            

    def cleanup_backups(self):
        try:
            profile = self.functions.clear_global_profiles(self.config_obj)[0]
        except:
            self.log.logger.warn("config --> unable to determine backup location, skipping cleanup.")
            return
        
        source = glob("/var/tessellation/nodectl/*backup*")
        for file in source:
            bashCommand = f"sudo mv {quote(file)} {quote(self.config_obj[profile]['directory_backups'])}"
            _ = self.functions.process_command({
                "bashCommand": bashCommand,
                "proc_action": "subprocess_devnull",
            })


    def print_report(self):
        if self.skip_final_report:
            return
        
        skip_special_case = False
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
            "seed_path_dups": "cannot have the same file name and path for different profiles.",
            "high_port": "port must be a integer between 1024 and 65535",
            "int": "collateral must be an integer value",
            "wallet_alias": f"{wallet_error1} {wallet_error2} {wallet_error3}",
            "p12_key_name": f"{p12_name_error1} {string2}",
            "key_location": f"{key_location1} {string2}",
            "p12_nf": "unable to location the p12 file, file not found.",
            "passphrase": "must be a string or empty value.",
            "str": "must be a string.",
            "bool": "must include a boolean (true/false)",
            "enable": "must include a boolean (true/false) enable key.",
            "auto_restart": "must include a boolean (true/false) enable key.",
            "auto_upgrade": "must include a boolean (true/false) enable key.",
            "rapid_restart": "must include a boolean (true/false) enable key.",
            "multiple": "configuration key(s) are missing",
            "invalid_key": "configuration found keys that are invalid and should not be in the configuration.",
            "list_of_strs": "must be a list of strings",
            "mem_size": f"{mem1} {mem2} {mem3} {mem4} {mem5} {mem6}",
            "node_type": f"{node_type1} {node_type2}",
            "meta_type": "options include 'gl' or 'ml'",
            "service": f"{service_dups} {service_dups2}",
            "link_profile": "dependency link profile not found",
            "pro_rating": "either the path to the file or file configured does not exist.",
            "dirs": f"{dir1} {dir2}",
            "128hex": f"{hex1} {hex2}",
            "gl0_link": "invalid link type",
            "ml0_link": "invalid link type",
            "global": f"{global1} {global2} {global3}",
            "yaml": f"{yaml1} {yaml2} {yaml3}",
            "edge_point": "must be a valid host or ip address",
            "host": "must be a valid host or ip address",
            "host_def": "must be a valid host or ip address",
            "pro": "must be a valid existing path or file",
            "path_def_dis": "must be a valid existing path or file",
            "cluster": "There is a misconfigured element in your cluster profile",
            "log_level": "Log level of INFO (recommended) or NOTSET, DEBUG, INFO, WARN, ERROR, CRITICAL required"
        }
        
        if self.action != "normal" or not self.validated:
            self.functions.print_header_title({
                "line1": "CONFIGURATION",
                "line2": "validator",
                "clear": True,
                "upper": False,
            })
            
        if not self.validated:
            self.functions.print_paragraphs([
                [" WARNING! ",2,"yellow,on_red","bold"], ["CONFIGURATION FILE DID NOT VALIDATE",1,"red"],
                ["Issues Found:",0,"yellow"], [str(len(self.error_list)),2,"red"],
            ])

            try:
                for error in self.error_list:
                    if error["key"] in hints:
                        if error["key"] == "multiple":
                            if error["special_case"] == "invalid": 
                                value_text = "    Invalid"
                                hint = hints["invalid_key"]
                                skip_special_case = True
                            else: 
                                value_text = "    Missing"
                                hint = hints[error["key"]]
                    elif error["type"] in hints:
                        hint = hints[error["type"]]
                    else:
                        hint = hints[error["section"]]
                        
                    if error["special_case"] != None and not skip_special_case:
                        skip_special_case = False
                        hint = error["special_case"]
                
                    config_key = ""
                    test_missing = False
                    if error["key"] == None and error["missing_keys"] != None:
                        test_missing = True
                    elif error["title"] == "section_missing" and error["missing_keys"] != None:
                        test_missing = True
                    
                    if test_missing:
                        if isinstance(error["missing_keys"],list):
                            for key_str in error["missing_keys"]:
                                config_key += key_str+", "
                            config_key = config_key[:-2]
                        else:
                            config_key = error["missing_keys"]
                    else:
                        config_key = error["key"]

                    error = {key:value if value != None else 'n/a' for key, value in error.items()}
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
                    
            except Exception as e:
                self.log.logger.error(f"config -> print_report -> found error [{e}]")
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
            exit("  configuration error")
        
        if self.action != "normal":
            self.functions.print_paragraphs([ 
                ["Configuration file:",0,"green"], [" VALIDATED! ",2,"grey,on_green","bold"],
            ])
            pass
                
                
    def send_error(self,code,extra="existence",extra2=None):
        self.log.logger.critical(f"configuration file [cn-config.yaml] error code [{code}] not reachable - should be in {self.functions.nodectl_path}")
        self.error_messages.error_code_messages({
            "error_code": code,
            "line_code": "config_error",
            "extra": extra,
            "extra2": extra2
        }) 


if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation") 
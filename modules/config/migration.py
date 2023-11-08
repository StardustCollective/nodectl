from termcolor import colored, cprint
from types import SimpleNamespace
from os import system, path, makedirs
from copy import deepcopy

from .versioning import Versioning
from ..troubleshoot.logger import Logging
from ..node_service import Node
from ..troubleshoot.errors import Error_codes
from ..functions import Functions


class Migration():
    
    def __init__(self,command_obj):
        self.functions = command_obj["functions"]
        self.config_obj = self.functions.config_obj
        self.version_obj = self.functions.version_obj
        
        self.log = Logging()
        self.log.logger.debug("migration process started...")
        self.errors = Error_codes(self.functions)
        self.caller = command_obj.get("caller","default")
        self.ingest = False 
        self.yaml = "" # initialize 
    
    
    def migrate(self):
        self.start_migration()
        self.handle_old_profiles()
        if not self.verify_config_type():
            return
        self.backup_config()
        self.create_n_write_yaml()
        return self.confirm_config()
        

    def printer_config_header(self):
        self.functions.print_header_title({
            "line1": "VERSION 2.0",
            "line2": "Configuration Migration",
            "clear": True,
        })
                
    
    def handle_old_profiles(self):
        self.config_keys = self.config_obj.keys()
        self.profile_keys = self.config_obj["profiles"].keys()
        self.old_config_keys = ["profiles","auto_restart","global_p12","global_elements"]
        self.old_profile_subsections = [
            "edge_point","ports","layer0_link",
            "dirs","java","p12","pro"]
        self.old_profile_keys = self.old_profile_subsections + [
            "enable","layer","environment","service",
            "node_type","description"]
        self.old_dir_keys = ["uploads","backups"]
        self.old_p12_keys = ["nodeadmin","key_location","p12_name","wallet_alias","passphrase"]
                
                
    def verify_config_type(self):
        try:
            config_yaml_version = self.config_obj["global_elements"]["nodectl_yaml"]
        except:
            pass
        else:
            if config_yaml_version == self.functions.node_nodectl_yaml_version:
                return False

        valid = True
        
        for key in self.config_keys:
            if key not in self.old_config_keys:
                valid = False
                
        if valid:
            for profile in self.profile_keys:
                for i_key in self.config_obj["profiles"][profile].keys():
                    if i_key not in self.old_profile_keys:
                        valid = False
                
        if not valid:
            self.errors.error_code_messages({
                "error_code": "mig-59",
                "line_code": "config_error",
                "extra": "format",
                "extra2": None
            })
        
        return True
        

    def start_migration(self):
        # version 2.0.0 only!
        # used to upgrade from v1.12.0 (upgrade path)
        # v0.1.0 -> v0.14.1 -> v1.8.1 -> v1.12.0 -> v2.0.0
        # This should be removed in the next minor version update or patch.
        self.printer_config_header()

        self.functions.print_paragraphs([
            ["During program initialization, an outdated and/or improperly formatted",0,"blue","bold"], ["configuration",0,"yellow","bold"],["file was found",0,"blue","bold"], 
            ["on this server/Node.",2,"blue","bold"],
            
            ["nodectl will backup your original configruation file and attempt to migrate to the new",0,"blue","bold"],
            ["required",0,"yellow,on_red","bold"], ["format.",2,"blue","bold"],
        ])

        self.functions.confirm_action({
            "yes_no_default": "y",
            "return_on": "y",
            "prompt": f"Attempt update and migrate configuration file?",
            "exit_if": True
        })

        
    def backup_config(self):
        self.functions.print_clear_line()
        if not self.ingest:
            print("") # UX clean up
        progress = {
            "text_start": "Backing up cn-config yaml",
            "status": "running",
            "status_color": "yellow",
        }
        self.functions.print_cmd_status(progress)
                        
        backup_dir = "/var/tessellation/backups"
        datetime = self.functions.get_date_time({"action":"datetime"})
        for profile in self.config_obj["profiles"].keys():
            for section, value in self.config_obj["profiles"][profile].items():
                if section == "dirs":
                    backup_dir = value
                    if backup_dir == "default":
                        backup_dir = "/var/tessellation/backups"
                    break
            break
            
        system(f"mv {self.functions.nodectl_path}cn-config.yaml /var/tessellation/backups/cn-config.{datetime}backup.yaml > /dev/null 2>&1")        

        self.functions.print_cmd_status({
            **progress,
            "status": "complete",
            "status_color": "green",
            "newline": True,
            "delay": .8
        })
        
        self.log.logger.warn("backing up cn-config.yaml file to default backup directory from original configuration, this file should be removed at a later date.")
        
        self.functions.print_paragraphs([
            ["",1], [" DANGER ",0,"yellow,on_red"], ["THE",0,"red","bold"], ["cn-config.yaml",0, "yellow","bold"], 
            ["FILE MAY CONTAIN A P12 PASSPHRASE, FOR SECURITY PURPOSES, PLEASE REMOVE AS NECESSARY!",2,"red","bold"],
            
            [" CAUTION ",0,"red,on_yellow"],["After the",0,"yellow"], ["migration",0,"cyan","bold"], ["is complete, the",0,"yellow"], 
            ["upgrader",0,"magenta","bold"], ["will continue and will prompt you to remove the contents of the backup directory",0,"yellow"],
            ["where the original",0,"yellow"], ["cn-config.yaml",0,"white,on_blue"], ["has been backed up within.",2,"yellow"], 
            
            ["If you choose to empty the contents",0,"yellow"],
            ["of this directory, you will remove the backup",0,"yellow"], ["cn-config.yaml",0,"cyan"], ["file.",2,"yellow"],
            
            ["backup filename:",0], [f"cn-config.{datetime}backup.yaml",1,"magenta"],
            ["backup location:",0], ["/var/tessellation/backups/",1,"magenta"],
        ])


    # =======================================================
    # build methods
    # =======================================================


    def migrate_profiles(self):
        # =======================================================
        # create profile sections
        # =======================================================
        rebuild_obj = {}
        self.found_environment = "NA"
        
        port_keys = ["nodegaragepublic","nodegaragep2p","nodegaragecli"]
        layer0_ports = [9000,9001,9002]; layer1_ports = [9010,9011,9012]
        rebuild_defaults = {
            "nodegaragehost": [
                "l0-lb-mainnet.constellationnetwork.io",
                "l1-lb-mainnet.constellationnetwork.io",
                "l0-lb-testnet.constellationnetwork.io",
                "l1-lb-testnet.constellationnetwork.io",
                "l0-lb-integrationnet.constellationnetwork.io",
                "l1-lb-integrationnet.constellationnetwork.io",
            ],
            "nodegaragehostport": "80",
            "nodegaragedirectorybackups": "/var/tessellation/backups",
            "nodegaragedirectoryuploads": "/var/tessellation/uploads",
            "nodegaragexms": "1024M",
            "nodegaragexmx": ["7G","3G"],
            "nodegaragexss": "256K",
            "nodegarageseedlocation": "/var/tessellation",
            "nodegarageseedfile": "seed-list",
        }
        
        for profile in self.config_obj["profiles"].keys():
            rebuild_obj["nodegarageprofile"] = profile
            self.found_environment = self.config_obj["profiles"][profile]["environment"] # will set final found env to value
            for section, value in self.config_obj["profiles"][profile].items():
                link_section = "ml0link" if section == "layer0_link" else "" # enable dup key value
                if section in self.old_profile_subsections:
                    for i_section, value in self.config_obj["profiles"][profile][section].items():
                        if link_section == "ml0link": # exception
                            i_section = i_section.replace("layer0","")
                            i_section = i_section.replace("link","")
                        elif i_section in self.old_dir_keys:
                            i_section = f"directory{i_section}"
                        elif i_section in self.old_p12_keys:
                            i_section = f"p12{i_section}"
                            i_section = "p12keyalias" if i_section == "p12wallet_alias" else i_section
                            i_section = "p12keyname" if i_section == "p12p12_name" else i_section
                        rebuild_obj[f"nodegarage{link_section}{i_section.replace('_','')}"] = value
                        if link_section == "ml0link":
                            value =  False if "enable" in i_section else "None"
                            rebuild_obj[f"nodegaragegl0link{i_section.replace('_','')}"] = value
                else:
                    section = "blocklayer" if section == "layer" else section # exception
                    rebuild_obj[f"nodegarage{section.replace('_','')}"] = value
                        
            # replace default values
            rebuild_obj_copy = deepcopy(rebuild_obj)
            for key, value in rebuild_obj_copy.items():
                layer = self.config_obj["profiles"][profile]["layer"]
                if key in port_keys:
                    index = port_keys.index(key)
                    if layer < 1:
                        value = "default" if value == layer0_ports[index] and key == port_keys[index] else value
                        rebuild_obj[key] = value
                    elif layer > 0:
                        value = "default" if value == layer1_ports[index] and key == port_keys[index] else value
                        rebuild_obj[key] = value
                if key in rebuild_defaults.keys():
                    if "port" in key and rebuild_obj[key] == value:
                        rebuild_obj["nodegarageedgepointtcpport"] = "default"
                    elif "host" in key and value in rebuild_obj[key]:
                        if str(layer) in value[0:2]:
                            rebuild_obj["nodegarageedgepointhost"] = "default"
                    elif ("backups" in key or "uploads" in key) and value[:-1] in rebuild_defaults[key]:
                        rebuild_obj[key] = "default"
                    elif ("xms" in key or "xss" in key) and value == rebuild_defaults[key]:
                        rebuild_obj[key] = "default"
                    elif "xmx" in key and value == rebuild_defaults[key][layer]:
                        rebuild_obj[key] = "default"    
                    elif "seedlocation" in key and value[:-1] in rebuild_defaults[key]:                        
                        rebuild_obj[key] = "default"    
                    elif "seedfile" in key and value == rebuild_defaults[key]:                        
                        rebuild_obj[key] = "default"    

            # new key pair >= v2.9.0
            rebuild_obj = {
                **rebuild_obj,
                "nodegaragecollateral": 0,
                "nodegaragemetatype": "ml",
                "nodegaragetokenidentifier": "disable",
                "nodegaragejarrepository": "default",
                "nodegaragejarfile": "default",
                # "nodegaragejarversion": "default",  # future?
                "nodegarageprioritysourcelocation": "default",
                "nodegarageprioritysourcerepository": "default",
                "nodegarageprioritysourcefile": "default",
                "nodegaragecustomargsenable": False,
                "nodegaragecustomenvvarsenable": False,
                "nodegarageseedrepository": "default",
            }

            rebuild_obj["create_file"] = "config_yaml_profile"
            rebuild_obj["show_status"] = False
            self.yaml += self.build_yaml(rebuild_obj) 
    
           
    def build_yaml(self,rebuild_obj): 

        create_file = rebuild_obj.pop("create_file")
        action = rebuild_obj.pop("action","continue")
        show_status = rebuild_obj.pop("show_status",True)
        
        if show_status:
            self.functions.print_cmd_status({
                "text_start": "Creating configuration file",
                "status": "creating",
                "status_color": "yellow",
            })
            
        profile = self.node_service.create_files({"file": create_file})

        if action != "skip":
            try:
                for yaml_item in rebuild_obj.keys():
                    if "layer" in yaml_item:
                        pass
                    profile = profile.replace(yaml_item,str(rebuild_obj[yaml_item]))
            except Exception as e:
                self.errors.error_code_messages({
                    "error_code": "mig-348",
                    "line_code": "profile_build_error",
                    "extra": e
                })

        return profile
                
    
    def create_n_write_yaml(self): 
        self.node_service = Node({
            "config_obj": {
                "global_elements": {
                    "caller":"config"
                },
            },
            "functions": self.functions,
        })  
        

        rebuild_obj = {
            "action": "skip",
            "create_file": "config_yaml_init"
        }        
        
        # =======================================================
        # start building the yaml file initial comments and setup
        # =======================================================
        
        # status progress in build_yaml method
        if self.caller == "configurator":
            rebuild_obj["show_status"] = False
        else:
            rebuild_obj["action"] = "skip"
            print(" ") # blank line before continuing  
        
        self.yaml = self.build_yaml(rebuild_obj)
        
        if self.caller != "configurator":
            self.full_v1_migrate()
        
        
    def full_v1_migrate(self):
        # migration of cn-node verses config update
        self.migrate_profiles()
        
        # =======================================================
        # build yaml auto_restart section
        # =======================================================
        
        rebuild_obj = {
            "nodegarageeautoenable": "False",
            "nodegarageautoupgrade": "False",
            "nodegarageonboot": "False",
            "nodegaragerapidrestart": "False",
            "create_file": "config_yaml_autorestart",
        }
        self.yaml += self.build_yaml(rebuild_obj)

        # =======================================================
        # build yaml p12 and global var section
        # =======================================================
        
        rebuild_obj = {
            "nodegaragep12nodeadmin": self.config_obj["global_p12"]["nodeadmin"],
            "nodegaragep12keylocation": self.config_obj["global_p12"]["key_location"],
            "nodegaragep12keyname": self.config_obj["global_p12"]["p12_name"],
            "nodegaragep12keyalias": self.config_obj["global_p12"]["wallet_alias"],
            "nodegaragep12passphrase": f'"{self.config_obj["global_p12"]["passphrase"]}"',
            "create_file": "config_yaml_p12",
        }
        self.yaml += self.build_yaml(rebuild_obj)
        
        # =======================================================
        # build yaml global elements section
        # =======================================================        
        rebuild_obj = {
            "nodegaragemetagraphname": self.found_environment,
            "nodegaragenodectlyaml": self.functions.node_nodectl_yaml_version,
            "nodegarageloglevel": "INFO",
            "create_file": "config_yaml_global_elements",
        }
        self.yaml += self.build_yaml(rebuild_obj)

        # =======================================================
        # write final yaml out to file and offer review
        # =======================================================
        self.final_yaml_write_out()
        
        
    def final_yaml_write_out(self):
        if not path.isdir(self.functions.nodectl_path):
            makedirs(self.functions.nodectl_path)
        with open(f"{self.functions.nodectl_path}cn-config.yaml","w") as newfile:
            newfile.write(self.yaml)
        newfile.close()
            
        self.functions.print_cmd_status({
            "text_start": "Creating configuration file",
            "status": "complete",
            "status_color": "green",
            "newline": True,
        })


    def configurator_builder(self,rebuild_obj):
        self.yaml += self.build_yaml(rebuild_obj)
        
        
    def confirm_config(self):
        self.functions.print_clear_line()
        self.functions.print_paragraphs([
            ["",1],["cn-config",0,"yellow","bold"], ["MIGRATION COMPLETED SUCCESSFULLY!!",1,"green","bold"],
            ["Ready to continue with upgrade",2,"blue","bold"],
        ])
        
        verify = self.functions.confirm_action({
            "yes_no_default": "n",
            "return_on": "y",
            "prompt": "Would you like to review your new configuration?",
            "exit_if": False
        })  
        return verify
                       
                       
if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")
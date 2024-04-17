from os import system, path, makedirs

from .versioning import Versioning
from ..troubleshoot.logger import Logging
from ..node_service import Node
from ..troubleshoot.errors import Error_codes

class Migration():
    
    def __init__(self,command_obj):
        self.parent = command_obj.get("parent",False)

        if self.parent:
            self.functions = self.parent.functions
        else:
            self.functions = command_obj["functions"]

        self.config_obj = self.functions.config_obj
        
        self.profiles = self.functions.pull_profile({
            "req": "list",
        })
        self.log = Logging()
        self.functions.log = self.log
        self.log.logger.debug("migration process started...")
        self.errors = Error_codes(self.functions)
        self.caller = command_obj.get("caller","default")
        self.retention = {}
        self.ingest, self.verify_config_request, self.do_migrate = False, False, False 
        self.yaml = "" # initialize 
    
    
    def migrate(self):
        self.start_migration()
        self.edge_point_handler()
        self.setup_versioning()
        verify = self.verify_config_type()
        if not verify: return
        self.backup_config()
        self.create_n_write_yaml()
        self.final_yaml_write_out()
        self.confirm_config()
        

    def print_config_header(self):
        self.functions.print_header_title({
            "line1": "VERSION 2.0",
            "line2": "Configuration Migration",
            "clear": True,
            "upper": False,
        })
            

    def edge_point_handler(self):
        # make a copy to replace the updated config
        # after versioning is completed.
        for profile in self.parent.yaml_dict["nodectl"].keys():
            if "global" not in profile:
                self.retention[profile] = {
                    "ep": self.config_obj[profile]["edge_point"],
                    "ep_tcp": self.config_obj[profile]["edge_point_tcp_port"]
                } 


    def setup_profiles(self):
        upgrade_error = False
        try:
            self.profiles = self.functions.clear_global_profiles(list(self.config_obj.keys()))
        except:
            self.log.logger.error("migration module unable to pull profiles from the configuration")
            upgrade_error = True

        return upgrade_error


    def setup_versioning(self):
        self.parent.setup_config_vars({
            "key": "edge_point",
            "profile": list(self.config_obj.keys())[0],
            "environment": self.functions.environment_name,
        })

        upgrade_error = self.setup_profiles()
        if upgrade_error:
            self.errors.error_code_messages({
                "error_code": "mig-86",
                "line_code": "upgrade_path_needed",
            })

        # versioning exceptions
        # handle any new configuration elements that have
        # been added to the versioning class but may not
        # be present in the old configuration
        # v2.13.0
        for profile in self.profiles:
            try:
                _ = self.config_obj[profile]["jar_path"]
            except:
                self.config_obj[profile]["jar_path"] = "/var/tessellation/"

        versioning = Versioning({
            "config_obj": self.config_obj,
            "print_messages": True,
            "called_cmd": "migrator",
            "force": False,
        })
        self.version_obj = versioning.get_version_obj()


    def verify_config_type(self):
        upgrade_error = False
        upgrade_error = self.setup_profiles()

        try:
            yaml_version = str(self.functions.is_new_version(
                self.config_obj["global_elements"]["nodectl_yaml"],
                self.version_obj["node_upgrade_path_yaml_version"],
                "migration module",
                "nodectl yaml version"
            ))
            if yaml_version == "current_less":
                # This version of nodectl needs to follow an upgrade path to migrate properly
                self.log.logger.warn(f'migration module determined incorrect nodectl yaml version | [{self.config_obj["global_elements"]["nodectl_yaml"]}]')
                upgrade_error = True
        except:
            upgrade_error = True
            
        if upgrade_error:
            self.errors.error_code_messages({
                "error_code": "mig-108",
                "line_code": "upgrade_path_needed",
            })
            
        # simple verification only
        valid = True
        requirements = {
            # should be the old version counts
            "global_count": 3, 
            "global_p12_count": 5,
            "global_elements_count": 4,
            "global_auto_restart_count": 4, 
            "profile_count": 46*len(self.profiles),          
        }

        for key in self.config_obj.keys():
            if "global" in key:
                requirements["global_count"] -= 1
                for i_key in self.config_obj[key].keys():
                    if i_key == "caller": continue
                    if "auto" in key: requirements["global_auto_restart_count"] -= 1
                    elif "p12" in key: requirements["global_p12_count"] -= 1
                    elif "element" in key: requirements["global_elements_count"] -= 1
            else:
                for _ in self.config_obj[key].keys():
                    requirements["profile_count"] -= 1
                    
        for requirement in requirements.values():
            if requirement > 0:
                self.log.logger.error(f'migration module determined possible nodectl configuration yaml error, unable to continue') 
                valid = False
                
        if not valid:
            self.errors.error_code_messages({
                "error_code": "mig-59",
                "line_code": "config_error",
                "extra": "format",
                "extra2": None
            })
        
        self.log.logger.info(f'migration module quick verification of previous configuration is valid, continuing migration')
        return True
        

    def start_migration(self):
        # version 2.0.0 only!
        # used to upgrade from v1.12.0 (upgrade path)
        # v0.1.0 -> v0.14.1 -> v1.8.1 -> v1.12.0 -> v2.0.0
        # This should be removed in the next minor version update or patch.
        self.print_config_header()

        self.functions.print_paragraphs([
            ["During program initialization, an outdated and/or improperly formatted",0,"blue","bold"], ["configuration",0,"yellow","bold"],["file was found",0,"blue","bold"], 
            ["on this server/Node.",2,"blue","bold"],
            
            ["nodectl will backup your original configuration file and attempt to migrate to the new",0,"blue","bold"],
            ["required",0,"yellow,on_red","bold"], ["format.",2,"blue","bold"],
        ])

        self.functions.confirm_action({
            "yes_no_default": "y",
            "return_on": "y",
            "prompt": f"Attempt update and migrate configuration file?",
            "exit_if": True
        })

        self.do_migrate = True

        
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

        try:
            backup_dir = self.config_obj[self.profiles[0]]["directory_backups"]
            if backup_dir == "default":
                backup_dir = "/var/tessellation/backups/"
        except:
            backup_dir = "/var/tessellation/backups/"

        if backup_dir[-1] != "/": backup_dir = backup_dir+"/"

        datetime = self.functions.get_date_time({"action":"datetime"})
        dest = f"{backup_dir}backup_cn-config_{datetime}"

        self.log.logger.debug(f'migration module backing up the configuration to [{dest}]')
        system(f"mv {self.functions.nodectl_path}cn-config.yaml {dest} > /dev/null 2>&1")        

        self.functions.print_cmd_status({
            **progress,
            "status": "complete",
            "status_color": "green",
            "newline": True,
            "delay": .8
        })
        
        self.log.logger.warn("backing up cn-config.yaml file to default backup directory from original configuration, this file should be removed at a later date.")
        
        self.functions.print_paragraphs([
            ["",1], [" DANGER ",0,"yellow,on_red"], ["The backup configuration YAML file",0,"red","bold"], 
            ["MAY CONTAIN A P12 PASSPHRASE, FOR SECURITY PURPOSES, PLEASE REMOVE AS NECESSARY!",2,"red","bold"],
            
            [" CAUTION ",0,"red,on_yellow"],["After the",0,"yellow"], ["migration",0,"cyan","bold"], ["is complete, the",0,"yellow"], 
            ["upgrader",0,"cyan","bold"], ["will continue and will prompt you to remove the contents of the backup directory",0,"yellow"],
            ["where the original",0,"yellow"], ["configuration YAML file",0,"cyan","bold"], ["has been backed up within.",2,"yellow"], 
            
            ["If you choose to empty the contents",0,"yellow"],
            ["of this directory, you will remove the backup",0,"yellow"], ["configuration YAML file",0,"cyan"], ["file.",2,"yellow"],
            
            ["backup filename:",0], [f"{path.split(dest)[1]}",1,"magenta"],
            ["backup location:",0], [f"{path.split(dest)[0]}",1,"magenta"],
        ])


    # =======================================================
    # build methods
    # =======================================================

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
            self.preform_migration()
        
        
    def preform_migration(self):

        # =======================================================
        # build yaml profile section
        # =======================================================
        self.log.logger.debug('migration module building new configuration skelton')

        # version 2.13 changes environment with hypergraph
        token_identifier = "disable"
        token_coin = "global"
        if self.config_obj["global_elements"]["metagraph_name"] not in ["testnet","mainnet","integrationnet","hypergraph"]:
            token_identifier = "global"

        for profile in self.profiles:
            rebuild_obj = {
                "nodegarageprofile": profile,
                "nodegarageenable": self.config_obj[profile]["profile_enable"],
                "nodegarageenvironment": self.config_obj[profile]["environment"],
                "nodegaragedescription": self.config_obj[profile]["description"],
                "nodegaragenodetype": self.config_obj[profile]["node_type"],
                "nodegaragemetatype": self.config_obj[profile]["meta_type"],
                "nodegarageblocklayer": self.config_obj[profile]["layer"],
                "nodegaragecollateral": "default", # updated in v2.13.0 | self.config_obj[profile]["collateral"],
                "nodegarageservice": "default", # updated in v2.13.0 | self.config_obj[profile]["service"],
                "nodegarageedgepointhost": self.retention[profile]["ep"], # self.config_obj[profile]["edge_point"],
                "nodegarageedgepointtcpport": self.retention[profile]["ep_tcp"], # self.config_obj[profile]["edge_point_tcp_port"],
                "nodegaragepublic": self.config_obj[profile]["public_port"],
                "nodegaragep2p": self.config_obj[profile]["p2p_port"],
                "nodegaragecli": self.config_obj[profile]["cli_port"],
                "nodegaragegl0linkenable": self.config_obj[profile]["gl0_link_enable"],
                "nodegaragegl0linkkey": self.config_obj[profile]["gl0_link_key"],
                "nodegaragegl0linkhost": self.config_obj[profile]["gl0_link_host"],
                "nodegaragegl0linkport": self.config_obj[profile]["gl0_link_port"],
                "nodegaragegl0linkprofile": self.config_obj[profile]["gl0_link_profile"],
                "nodegarageml0linkenable": self.config_obj[profile]["ml0_link_enable"],
                "nodegarageml0linkkey": self.config_obj[profile]["ml0_link_key"],
                "nodegarageml0linkhost": self.config_obj[profile]["ml0_link_host"],
                "nodegarageml0linkport": self.config_obj[profile]["ml0_link_port"],
                "nodegarageml0linkprofile": self.config_obj[profile]["ml0_link_profile"],
                "nodegaragetokenidentifier": token_identifier, # new to v2.13.0  # self.config_obj[profile]["token_identifier"],
                "nodegaragemetatokencoinid": token_coin, # new to v2.13.0
                "nodegaragedirectorybackups": self.config_obj[profile]["directory_backups"],
                "nodegaragedirectoryuploads": self.config_obj[profile]["directory_uploads"],
                "nodegaragexms": self.config_obj[profile]["java_xms"],
                "nodegaragexmx": self.config_obj[profile]["java_xmx"],
                "nodegaragexss": self.config_obj[profile]["java_xss"],
                "nodegaragejarlocation": "default", # new to v2.13.0,
                "nodegaragejarrepository": self.config_obj[profile]["jar_repository"],
                "nodeagaragejarversion": "default", # new to v2.13.0
                "nodegaragejarfile": self.config_obj[profile]["jar_file"],
                "nodegaragep12nodeadmin": self.config_obj[profile]["p12_nodeadmin"],
                "nodegaragep12keylocation": self.config_obj[profile]["p12_key_location"],
                "nodegaragep12keyname": self.config_obj[profile]["p12_key_name"],
                "nodegaragep12passphrase": self.config_obj[profile]["p12_passphrase"],
                "nodegarageseedlocation": self.config_obj[profile]["seed_location"],
                "nodegarageseedrepository": self.config_obj[profile]["seed_repository"],
                "nodegarageseedfile": self.config_obj[profile]["seed_file"],
                "nodegarageseedversion": "disable" if self.config_obj[profile]["seed_file"] == "disable" else "default", # new to v2.13.0,
                "nodegarageprioritysourcelocation": self.config_obj[profile]["priority_source_location"],
                "nodegarageprioritysourcerepository": self.config_obj[profile]["priority_source_repository"],
                "nodegarageprioritysourcefile": self.config_obj[profile]["priority_source_file"],
                "nodegaragecustomargsenable": self.config_obj[profile]["custom_args_enable"],
                "nodegaragecustomenvvarsenable": self.config_obj[profile]["custom_env_vars_enable"], 
                "nodegarageratingfile": self.config_obj[profile]["pro_rating_file"], 
                "nodegarageratinglocation": self.config_obj[profile]["pro_rating_location"], 
                "create_file": "config_yaml_profile",
            }
            self.yaml += self.build_yaml(rebuild_obj)
        
        # =======================================================
        # build yaml auto_restart section
        # =======================================================
        
        rebuild_obj = {
            "nodegarageeautoenable": self.config_obj["global_auto_restart"]["auto_restart"],
            "nodegarageautoupgrade": self.config_obj["global_auto_restart"]["auto_upgrade"],
            "nodegarageonboot": self.config_obj["global_auto_restart"]["on_boot"],
            "nodegaragerapidrestart": self.config_obj["global_auto_restart"]["rapid_restart"],
            "create_file": "config_yaml_autorestart",
        }
        self.yaml += self.build_yaml(rebuild_obj)

        # =======================================================
        # build yaml p12 and global var section
        # =======================================================
        
        rebuild_obj = {
            "nodegaragep12nodeadmin": self.config_obj["global_p12"]["nodeadmin"],
            "nodegaragep12keylocation": self.config_obj["global_p12"]["key_location"],
            "nodegaragep12keyname": self.config_obj["global_p12"]["key_name"],
            "nodegaragep12passphrase": f'"{self.config_obj["global_p12"]["passphrase"]}"',
            "nodegaragep12encryption": "False", # new to v2.13.0
            "create_file": "config_yaml_p12",
        }
        self.yaml += self.build_yaml(rebuild_obj)
        
        # =======================================================
        # build yaml global elements section
        # =======================================================    
            
        # version 2.13 changes environment with hypergraph
        metagraph_name = self.config_obj["global_elements"]["metagraph_name"]
        
        try:
            config_name = self.config_obj["global_elements"]["yaml_config_name"]
        except:
            config_name =  self.config_obj[self.profiles[0]]["environment"]

        token_coin_id = "default"
        token_identifier = "disable"
        if self.config_obj["global_elements"]["metagraph_name"] in ["testnet","mainnet","integrationnet"]:
            config_name = metagraph_name
            metagraph_name = "hypergraph"
        elif metagraph_name == "dor-metagraph":
            config_name = "dor-metagraph-mainnet"
            token_coin_id = "default"
            token_identifier = "default"

        rebuild_obj = {
            "nodegarageyamlconfigname": config_name,
            "nodegaragemetagraphname": metagraph_name,
            "nodegaragemetatokenidentifier": token_identifier,
            "nodegaragemetagraphtokencoinid": token_coin_id, # new to v2.13.0
            "nodegaragelocalapi": "disable", # new to v2.13.0
            "nodegarageincludes": "False", # new to v2.13.0
            "nodegaragedevelopermode": self.config_obj["global_elements"]["developer_mode"],
            "nodegaragenodectlyaml": self.version_obj["node_nodectl_yaml_version"],
            "nodegarageloglevel": self.config_obj["global_elements"]["log_level"],

            "create_file": "config_yaml_global_elements",
        }
        self.yaml += self.build_yaml(rebuild_obj)


    def final_yaml_write_out(self):
        # =======================================================
        # write final yaml out to file and offer review
        # =======================================================
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
        self.log.logger.info('migration module completed configuration build')
        self.functions.print_clear_line()
        self.functions.print_paragraphs([
            ["",1],["cn-config.yaml upgraded",1,"green"], 
            ["MIGRATION COMPLETED SUCCESSFULLY!!",1,"green","bold"],
            ["Ready to continue with upgrade",2,"blue","bold"],
        ])
        
        self.verify_config_request = self.functions.confirm_action({
            "yes_no_default": "n",
            "return_on": "y",
            "prompt": "Would you like to review your new configuration?",
            "exit_if": False
        })  
                       
if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")
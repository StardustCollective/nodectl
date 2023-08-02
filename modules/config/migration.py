from termcolor import colored, cprint
from types import SimpleNamespace
from os import system, path, makedirs

from ..troubleshoot.logger import Logging
from ..node_service import Node
from ..troubleshoot.errors import Error_codes
from ..functions import Functions


class Migration():
    
    def __init__(self,command_obj):
        var = SimpleNamespace(**command_obj)
        self.log = Logging()
        self.log.logger.debug("migration process started...")
        self.errors = Error_codes()
        self.caller = command_obj.get("caller","default")
        self.ingest = False 
        
        self.functions = Functions(var.config_obj)
        self.yaml = "" # initialize 
    
    def migrate(self):
        self.start_migration()
        self.backup_config()
        self.create_n_write_yaml()
        
        return self.confirm_config()
        

    def printer_config_header(self):
        self.functions.print_header_title({
            "line1": "VERSION 2.0",
            "line2": "Configuration Migration",
            "clear": True,
        })
                
                
    def start_migration(self):
        # version 2.0.0 only!
        # used to upgrade from v1.12.0 (upgrade path)
        # v0.1.0 -> v0.14.1 -> v1.8.1 -> v1.12.0 -> v2.0.0
        # This should be removed in the next minor version update or patch.
        self.printer_config_header()

        self.functions.print_paragraphs([
            ["During program initialization, an outdated improperly formatted",0,"blue","bold"], ["configuration",0,"yellow","bold,underline"],["file was found",0,"blue","bold"], 
            ["on this server/Node.",2,"blue","bold"],
            
            ["nodectl will backup your original configruation file and attempt to migrate to the new",0,"blue","bold"],
            [" required ",0,"yellow,on_red","bold"], ["format.",2,"blue","bold"],
        ])

        confirm = self.functions.confirm_action({
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
            "text_start": "Backing up cn-node file",
            "status": "running",
            "status_color": "yellow",
        }
        self.functions.print_cmd_status(progress)
                        
        backup_dir = "/var/tessellation/backups"
        datetime = self.functions.get_date_time({"action":"datetime"})
        for key in self.functions.config_obj["profiles"].keys():
            for section in key.items():
                if section == "dirs":
                    backup_dir = self.functions.config_obj["profiles"][key]["dirs"]["backups"]
                    if backup_dir == "default":
                        backup_dir = "/var/tessellation/backups"
                break
            break
            
        system(f"mv /var/tessellation/nodectl/cn-config.yaml /var/tessellation/backups/cn-config.{datetime}backup.yaml > /dev/null 2>&1")        

        self.functions.print_cmd_status({
            **progress,
            "status": "complete",
            "status_color": "green",
            "newline": True,
            "delay": .8
        })
        
        self.log.logger.warn("backing up cn-config.yaml file to default backup directory from original configuration, this file should be removed at a later date.")
        
        self.functions.print_paragraphs([
            ["",1], [" DANGER ",0,"yellow,on_red"], ["THE",0,"red","bold"], ["cn-node",0, "yellow","underline"], 
            ["FILE MAY CONTAIN A P12 PASSPHRASE, FOR SECURITY PURPOSES, PLEASE REMOVE AS NECESSARY!",2,"red","bold"],
            
            [" CAUTION ",0,"red,on_yellow"],["After the",0,"yellow"], ["migration",0,"cyan","underline"], ["is complete, the",0,"yellow"], 
            ["upgrader",0,"magenta","bold"], ["will continue and will prompt you to remove the contents of the backup directory",0,"yellow"],
            ["where the",0,"yellow"], [" cn-node ",0,"white,on_blue"], ["has been backed up within. If you choose to empty the contents",0,"yellow"],
            ["of this directory, you will remove the backup",0,"yellow"], ["cn-node",0,"cyan","underline"], ["file.",2,"yellow"],
            
            ["backup filename:",0], [f"cn-node.{datetime}backup",1,"magenta"],
            ["backup location:",0], ["/var/tessellation/backups/",1,"magenta"],
        ])

    # =======================================================
    # build methods
    # =======================================================


    def migrate_profiles(self):
        # =======================================================
        # create profile sections using Constellation Network defaults
        # and inputs from the legacy cn-node file that was identified
        # =======================================================
        ports = [[9000,9001,9002],[9010,9011,9012]]
        for n in range(0,2):
            link_bool = "False" if n == 0 else "True"
            rebuild_obj = {
                "nodegarageprofile": f"dag-l{n}",
                "nodegarageenable": "True",   
                "nodegaragelayer": f"{n}",
                "nodegarageedgehttps": "False",
                "nodegarageedgehost": f"l{n}-lb-{self.config_details['environment']}.constellationnetwork.io",
                "nodegarageedgeporthost": "80",
                "nodegarageenvironment": self.config_details["environment"],
                "nodegaragepublic": str(ports[n][0]),
                "nodegaragep2p": str(ports[n][1]),
                "nodegaragecli": str(ports[n][2]),
                "nodegarageservice": f"node_l{n}",
                "nodegaragelinkenable": link_bool,
                "nodegarage0layerkey": "None",
                "nodegarage0layerhost": "None",
                "nodegarage0layerport": "None",
                "ndoegarage0layerlink": "None",
                "nodegaragexms": "1024M",
                "nodegaragexmx": "7G",
                "nodegaragexss": "256K",
                "nodegaragenodetype": "validator",
                "nodegaragedescription": "Constellation Network Global Hypergraph",
                "nodegaragesnaphostsdir": "default",
                "nodegaragebackupsdir": "default",
                "nodegarageuploadsdir": "default",
                "nodegaragenodeadmin": "global",
                "nodegaragekeylocation": "global",
                "nodegaragep12name": "global",
                "nodegaragewalletalias": "global",
                "nodegaragepassphrase": "global",
                "nodegarageseedlistloc": "/var/tessellation/",
                "nodegarageseedlistfile": "seed-list",
            }

            link_profile = "dag-l0"
            if self.config_details['environment'] == "integrationnet":
                rebuild_obj["nodegarageenvironment"] = "integrationnet"
                rebuild_obj["nodegarageedgehost"] = f"l{n}-lb-integrationnet.constellationnetwork.io"
                rebuild_obj["nodegarageprofile"] = f"intnet-l{n}" 
                rebuild_obj["nodegarageservice"] = f"intnetserv_l{n}"
                # rebuild_obj["nodegarageedgeporthost"] = f"90{n}0"
                link_profile = "intnet-l0"        
                                        
            if n == 1:
                # rewrite for layer1
                rebuild_obj["nodegarage0layerkey"] = "self"
                rebuild_obj["nodegarage0layerhost"] = "self"
                rebuild_obj["nodegarage0layerport"] = str(ports[0][0])
                rebuild_obj["ndoegarage0layerlink"] = link_profile
                rebuild_obj["nodegaragesnaphostsdir"] = "disable"
                rebuild_obj["nodegaragexmx"] = "3G"
                rebuild_obj["nodegaragedescription"] = "Constellation Network Layer1 Metagraph" 
                rebuild_obj["nodegarageseedlistloc"] = "disable"
                rebuild_obj["nodegarageseedlistfile"] = "disable"

            rebuild_obj["create_file"] = "config_yaml_profile"
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
                    profile = profile.replace(yaml_item,rebuild_obj[yaml_item])
            except Exception as e:
                self.errors.error_code_messages({
                    "error_code": "mig-348",
                    "line_code": "profile_build_error",
                    "extra": e
                })
        
        return profile
                
    
    def create_n_write_yaml(self): 
        self.node_service = Node({
            "config_obj": {"caller":"config"}
        },False)  

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
            "create_file": "config_yaml_autorestart",
        }
        self.yaml += self.build_yaml(rebuild_obj)

        # =======================================================
        # build yaml p12 and global var section
        # =======================================================
        
        rebuild_obj = {
            "nodegaragenodeadmin": self.config_details["nodeadmin"],
            "nodegaragekeylocation": self.config_details["keystore"],
            "nodegaragep12name": self.config_details["p12_name"],
            "nodegaragewalletalias": self.config_details["alias"],
            "nodegaragepassphrase": f'"{self.config_details["passphrase"]}"',
            "create_file": "config_yaml_p12",
        }
        self.yaml += self.build_yaml(rebuild_obj)

        # =======================================================
        # write final yaml out to file and offer review
        # =======================================================
        
        if not path.isdir("/var/tessellation/nodectl/"):
            makedirs("/var/tessellation/nodectl/")
            
        self.final_yaml_write_out()
        
        
    def final_yaml_write_out(self):
        if path.isdir("/var/tessellation/nodectl/"):
            with open("/var/tessellation/nodectl/cn-config.yaml","w") as newfile:
                newfile.write(self.yaml)
            newfile.close()
            
            self.functions.print_cmd_status({
                "text_start": "Creating configuration file",
                "status": "complete",
                "status_color": "green",
                "newline": True,
            })
        else:
            return False
        return True
         

    def configurator_builder(self,rebuild_obj):
        self.yaml += self.build_yaml(rebuild_obj)
        
        
    def confirm_config(self):
        self.functions.print_clear_line()
        self.functions.print_paragraphs([
            ["cn-node",0,"yellow","bold"], ["MIGRATION COMPLETED SUCCESSFULLY!!",1,"green","bold"],
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
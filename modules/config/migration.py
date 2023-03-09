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
        confirm = self.start_migration()
        if not confirm:
            return
        
        self.keep_pass_visible = self.handle_passphrase()
        
        self.ingest_cn_node()
        self.backup_cn_node()
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
            ["During program initialization, a",0,"blue","bold"], ["configuration",0,"yellow","bold,underline"],["file was found",0,"blue","bold"], 
            ["missing",0,"yellow,on_red","bold"], ["on this server/Node.",2,"blue","bold"],
            
            ["nodectl found an existing file",0,"blue","bold"], ["cn-node",0, "yellow","bold,underline"],
            ["file on your existing server/Node. nodectl can backup this file and attempt to migrate to the new",0,"blue","bold"],
            ["required",0,"yellow,on_red","bold"], ["format.",2,"blue","bold"],
        ])

        confirm = self.functions.confirm_action({
            "yes_no_default": "y",
            "return_on": "y",
            "prompt": f"Attempt cn-node file migration?",
            "exit_if": False
        })
        
        return confirm   
        
        
    def handle_passphrase(self,disclaimer=True):
        paragraphs = [
            ["",2],["nodectl v2",0,"cyan","bold"], ["allows removal of the passphrase from your configuration. It is up to the",0,"blue","bold"],
            ["Node Operator administering this Node to decide on the best course of action.",2,"blue","bold"],
        ]
        self.functions.print_paragraphs(paragraphs)
        paragraphs = [
            ["PROS:",0,"green","bold"], ["- One less location with an exposed clear-text passphrase.",1,"green"],
        ]
        self.functions.print_paragraphs(paragraphs,{"sub_indent": "          " })
        wrapper = self.functions.print_paragraphs("wrapper_only")
        wrapper.initial_indent = "        "
        wrapper.subsequent_indent = "          "

        cprint(wrapper.fill("- Adds small layer of security to force a possible attacker to work harder to gain access to the Node's wallet."),"green")
        print("")
        
        paragraphs = [
            ["CONS:",0,"yellow","bold"], ["- Your passphrase will be requested whenever required by nodectl.",1,"red"],
        ]
        self.functions.print_paragraphs(paragraphs,{"sub_indent": "          " })
        
        exposed = colored("exposed","red",attrs=["bold"])
        exposed1 = '- In the event your Node is compromised, your passphrase will still be'
        exposed2 = 'because any nefarious actor able to penetrate your system authentication practices will '
        exposed2 += 'know how to expose any passphrases in use by the processes running on the VPS/Node.'
        exposed2 = colored(exposed2,"red")
        cprint(wrapper.fill(f"{exposed1} {exposed} {exposed2}"),"red")
        
        print("")
        recommend = colored("Recommended:","blue",attrs=["bold"])
        recommend2 = colored("Keep passphrases","cyan")
        wrapper.initial_indent = "  "
        cprint(wrapper.fill(f"{recommend} {recommend2}"),"cyan")
        print("")
        
        keep_pass_visible = self.functions.confirm_action({
            "yes_no_default": "y",
            "return_on": "y",
            "prompt": "Keep passphrase visible in configuration?",
            "exit_if": False
        })
        
        if not keep_pass_visible:
            print("")
            paragraphs = [
                ["WARNING!",0,"red","bold"],["The passphrases will not be in the configuration.  Make sure you have them written down in a safe place",0],
                ["losing your passphrase is equivalent to losing the access to your bank accounts with no way of recovering.",2],
                
                ["Remember this is one of the most important self governing elements of decentralized finance!",2,"red","bold"]
            ]
            self.functions.print_paragraphs(paragraphs)
            
        if disclaimer:
            paragraphs = [
                ["",1],["nodectl v2",0,"cyan","bold"], ["introduces the ability to use different Node wallets",0,"blue","bold"],
                ["(p12 private keys)",0,"yellow"], ["per profile",0,"blue","bold"], ["(layer0 and/or layer1 State Channels)",0,"yellow"],[".",-1,"blue","bold"],
                ["",2],
                
                ["A new concept for",0,"blue","bold"], ["nodectl v2",0,"cyan","bold"], ["includes a",0,"blue","bold"],
                ["GLOBAL",0,"yellow,on_magenta","bold"], ["section within the configuration that can be used to assign a single p12 to all or some",0,"blue","bold"],
                ["of the profiles, on your Node.",2,"blue","bold"],
                
                ["The p12 content details from the Node's",0,"blue","bold"], ["global p12",0,"yellow"], ["cn-node",0, "cyan"],
                ["file including credentials will be added to the",0,"blue","bold"], ["global p12",0,"yellow"],
                ["section of the new configuration file.",2,"blue","bold"],
                
                ["You can setup the global p12 wallet configuration to handle all or only selected profiles of your choosing.",2,"green","bold"]
            ]
            self.functions.print_paragraphs(paragraphs)
            
            while True:
                confirm = self.functions.confirm_action({
                    "yes_no_default": "y",
                    "return_on": "y",
                    "prompt": "I have read the information above:",
                    "exit_if": True
                })
                if confirm:
                    break
            
            self.printer_config_header()
        return keep_pass_visible   
        
        
    def ingest_cn_node(self):
        print("")
        self.ingest = True
        progress = {
            "text_start": "Ingesting",
            "text_end": "file",
            "brackets": "cn-node",
            "status": "running",
            "status_color": "yellow",
            "newline": True,
        }
        self.functions.print_cmd_status(progress)
        
        self.config_details = {}
        with open("/usr/local/bin/cn-node","r") as f:
            for line in f:
                if "CL_PASSWORD" in line and self.keep_pass_visible:
                    var = "passphrase"
                elif "CL_KEYSTORE" in line:
                    var = "keystore"
                elif " CL_KEYALIAS" in line:
                    var = "alias"
                elif "CL_APP_ENV" in line:
                    var = "environment"
                elif "CL_PUBLIC_HTTP_PORT" in line:
                    var = "public"
                elif "CL_P2P_HTTP_PORT" in line:
                    var = "p2p"
                elif "CL_CLI_HTTP_PORT" in line:
                    var = "cli"
                else:
                    continue
                cn_var = line.split("=")
                cn_var = cn_var[1].replace("'","").strip()
                self.config_details[var] = cn_var
        f.close()
        
        if not self.keep_pass_visible:
            self.config_details["passphrase"] = "None"
        
        # grab username
        parts = self.config_details["keystore"].split("/")
        username = parts[2]
        p12_file = parts[-1]
        
        confirm_list = {
            "admin user": username,
            "p12 filename": p12_file
        }
        
        for key,value  in confirm_list.items():
            print(colored("\n  nodectl found [","cyan"),colored(value,"yellow",attrs=['bold']),colored(f"] as your Node's {key}.","cyan"))
            user_confirm = self.functions.confirm_action({
                "yes_no_default": "y",
                "return_on": "y",
                "prompt": "Is this correct?",
                "exit_if": False
            })
            if not user_confirm:
                while True:
                    print(colored(f"  Please enter your Node's {key}:","cyan"),end=" ")
                    value = input("")
                    print(colored("  confirm [","cyan"),colored(value,"yellow",attrs=['bold']),colored("]","cyan"),end=" ")
                    user_confirm = self.functions.confirm_action({
                        "yes_no_default": "n",
                        "return_on": "y",
                        "prompt": "is correct?",
                        "exit_if": False
                    })            
                    if user_confirm:
                        break
            if key == "admin user":
                self.config_details["nodeadmin"] = value
            else:
                self.config_details["p12_name"] = value
        
        self.config_details["keystore"] = self.config_details["keystore"].replace(p12_file,"")
        self.functions.print_cmd_status({
            **progress,
            "status": "complete",
            "status_color": "green",
        })
        
        
    def backup_cn_node(self):
        self.functions.print_clear_line()
        if not self.ingest:
            print("") # UX clean up
        progress = {
            "text_start": "Backing up cn-node file",
            "status": "running",
            "status_color": "yellow",
        }
        self.functions.print_cmd_status(progress)
                        
        datetime = self.functions.get_date_time({"action":"datetime"})
        
        default_dirs = [
            "/var/tessellation/uploads/",
            "/var/tessellation/backups/",
            "/var/tessellation/dag-l0/data/snapshot/"
        ]
        for dir in default_dirs:
            if not path.isdir(dir):
                makedirs(dir)
                
        system(f"mv /usr/local/bin/cn-node /var/tessellation/backups/cn-node.{datetime}backup > /dev/null 2>&1")        
        self.functions.print_cmd_status({
            **progress,
            "status": "complete",
            "status_color": "green",
            "newline": True,
            "delay": .8
        })
        
        self.log.logger.warn("backing up legacy cn-node file to [/var/tessellation/backups] this file should be removed at a later date.")
        
        self.functions.print_paragraphs([
            ["",1], ["THE",0,"red","bold"], ["cn-node",0, "yellow","underline"], 
            ["FILE MAY CONTAIN A P12 PASSPHRASE, FOR SECURITY PURPOSES, PLEASE REMOVE AS NECESSARY!",2,"red","bold"],
            
            ["After the",0], ["migration",0,"cyan","underline"], ["is complete, the",0], 
            ["upgrader",0,"yellow","bold"], ["will continue and will prompt you to remove the contents of the backup directory",0],
            ["where the",0], [" cn-node ",0,"white,on_blue"], ["has been backed up within.  If you choose to empty the contents",0],
            ["of this directory, you will remove the backup",0], ["cn-node",0,"cyan","underline"], ["file.",2],
            
            ["backup filename:",0], [f"cn-node.{datetime}backup",1,"yellow"],
            ["backup location:",0], ["/var/tessellation/backups/",1,"yellow"],
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
                "nodegaragedescription": "Constellation Network Global Layer0",
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
            if n == 1:
                # rewrite for layer1
                rebuild_obj["nodegarage0layerkey"] = "self"
                rebuild_obj["nodegarage0layerhost"] = "self"
                rebuild_obj["nodegarage0layerport"] = str(ports[0][0])
                rebuild_obj["ndoegarage0layerlink"] = "dag-l0"
                rebuild_obj["nodegaragesnaphostsdir"] = "disable"
                rebuild_obj["nodegaragexmx"] = "3G"
                rebuild_obj["nodegaragedescription"] = "Constellation Network Layer1 State Channel" 
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
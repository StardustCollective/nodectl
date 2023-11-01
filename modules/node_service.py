from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from os import system, path, makedirs
from sys import exit
from time import sleep
from termcolor import colored, cprint
from requests import Session
from types import SimpleNamespace

from .functions import Functions
from .troubleshoot.errors import Error_codes
from .troubleshoot.logger import Logging
from .troubleshoot.ts import Troubleshooter
from .config.versioning import Versioning

class Node():
        
    def __init__(self,command_obj):
        self.log = Logging()
                
        self.functions = command_obj.get("functions",False)
        if self.functions:
            self.config_obj = self.functions.config_obj
            self.version_obj = self.functions.version_obj
        else:
            self.config_obj = command_obj["config_obj"]
        
        self.troubleshooter = Troubleshooter({
            "config_obj": self.config_obj,
        })        
        self.error_messages = Error_codes(self.functions) 
        self.profile = command_obj.get("profile",None)
        self.profile_names = command_obj.get("profile_names",None)
        self.auto_restart = command_obj.get("auto_restart",False)
        
        # Node replacement variables
        # during installation and upgrade
        self.ip_address = None
        self.username = None
        self.p12_file_location = None
        self.p12_filename = None
        self.p12_password  = None 
        self.wallet_alias = None
        self.environment_name = None
        
        # during installation, the nodeid will be blank
        # until after the p12 is created causing the install
        # to create the cnng bash files and then write over it.
        self.nodeid = "nodegaragenodeid" 

        self.source_node_choice = None  # initialize source

        self.node_service_status = {
            "node_l0": None,
            "node_l1": None,
        }
 
         
    def set_profile_api_ports(self):
        # dictionary
        # [public]
        # [p2p]
        # [cli]
        self.api_ports = self.functions.pull_profile({
            "req": "ports",
            "profile": self.profile,
        })
        
   
    def set_profile(self,profile):
        self.functions.pull_profile({  # test if profile is valid
            "profile": profile,
            "req": "exists"
        })
        self.profile = profile
        self.set_profile_api_ports() 
        self.node_service_name = self.functions.pull_profile({
            "req": "service",
            "profile": profile,
        })


    def set_github_repository(self,repo,profile,download_version):
        if repo == "default":
            repo = "https://github.com/Constellation-Labs/tessellation"
            
        if self.config_obj[profile]["jar_github"]:
            repo = f"{repo}/releases/download/{download_version}"
        
        return repo
    
    
    def download_constellation_binaries(self,command_obj):
        # download_version=(bool) "default"
        # print_version=(bool) True
        download_version = command_obj.get("download_version","default")
        print_version = command_obj.get("print_version",True)
        action = command_obj.get("action","normal")
        requested_profile = command_obj.get("profile",False)
        environment = command_obj.get("environment",False)
        argv_list = command_obj.get("argv_list",[])
        backup = command_obj.get("backup", True)
        
        if "-v" in argv_list: download_version = argv_list(argv_list.index("-v")+1)
        
        if self.auto_restart: profile_names = [requested_profile]
        else: profile_names = self.functions.profile_names
        
        def screen_print_download_results(file,first=False):
            backup = ""
            
            if file != "cur_pos":
                i_file = file_obj[file] # readability
                colors = {"fetching": "magenta", "complete": "green", "failed": "red"}
                color = colors.get(i_file['state'])
                state_str = colored(i_file['state'],color,attrs=['bold'])
                
                new_pos = i_file['pos']+2
                old_pos = file_obj["cur_pos"]
                print_pos = new_pos-old_pos if file_obj["cur_pos"] is not None else 1
                for _ in range(0,print_pos):
                    backup += "\033[F"
                    
                if not first:
                    print(backup)
                    
                self.functions.print_cmd_status({
                    "text_start": "Fetch Tessellation binary",
                    "brackets": file,
                    "status": state_str,
                    "newline": True
                })
                return i_file['pos']
            
        def threaded_download(download_list):
            file_obj_copy = download_list[0]
            file = download_list[1]
            auto_restart = download_list[2]
            copy_state = "complete"
            tess_dir = "/var/tessellation/"
            
            try:
                profile = file_obj_copy[file]["profile"]
            except:
                profile = first_profile
            
            download_version = file_obj_copy[file]["version"]
            
            uri = file_obj_copy[file]["location"]
            uri = self.functions.cleaner(uri,"trailing_backslash")
            if uri[0:3] != "http" and uri != "default":
                # default to https://
                uri = f"https://{uri}"
                
            if download_version == "default":
                # retrieved from the edge point
                download_version = self.version_obj[environment][profile]["cluster_tess_version"]
            uri = self.set_github_repository(uri,profile,download_version)

            attempts = 0
            if not path.exists(tess_dir):
                makedirs(tess_dir)
                
            self.log.logger.info(f"downloading binary jar files: {file}")
            while True:
                if file != "cur_pos":
                    if file_obj_copy[file]["state"] != "complete":
                        bashCommand = f"sudo wget {uri}/{file} -O /var/tessellation/{file} -o /dev/null"
                        self.functions.process_command({
                            "bashCommand": bashCommand,
                            "proc_action": "timeout"
                        })
                        if self.functions.get_size(f'{tess_dir}{file}',True) == 0:
                            copy_state = "failed"
                            
                        system(f"sudo chmod 755 {tess_dir}{file} > /dev/null 2>&1")
                
                    file_obj_copy[file]["state"] = copy_state

                if auto_restart:
                    if copy_state == "complete":
                        self.log.logger.debug(f"auto_restart - auto_upgrade - node_service - completed successfully [{file}]")
                        return True
                    sleep(2)
                    attempts = attempts + 1
                    if attempts > 3:
                        self.log.logger.critical(f"auto_restart - auto_upgrade - node service is unable to download [{file}]")
                        return False
                    self.log.logger.error(f"auto_restart - auto_upgrade - node service is unable to download [{file}] trying again attempt [{attempts}]")
                else:
                    cur_pos = screen_print_download_results(file)
                    file_obj_copy["cur_pos"] = cur_pos
                    return file_obj_copy

        if not environment:
            self.error_messages.error_code_messages({
                "error_code": "ns-95",
                "line_code": "environment_error",
                "extra": "binary downloads",
            })
        
        # if download_version == "default":
        #     self.version_obj["cluster_tess_version"] = self.functions.get_version({
        #         "which": "cluster_tess",
        #         "print_version": print_version,
        #         "action": action
        #     })
        
        file_pos = 3
        if action == "upgrade":
            download_version = download_version[profile_names[0]]["download_version"]
        file_obj = {
            "cl-keytool.jar": { "state": "fetching", "pos": 1, "location": "default", "version": download_version},
            "cl-wallet.jar":  { "state": "fetching", "pos": 2, "location": "default", "version": download_version},
        }
        
        if self.auto_restart:
            # avoid race condition if same file is downloaded at the same time only
            # download tool jars if root profile.
            root_profile = self.functions.test_for_root_ml_type(environment)
            if requested_profile != root_profile: file_obj, file_pos = {}, 0

        for n, profile in enumerate(profile_names):
            # version = download_version
            if self.config_obj[profile]["environment"] == environment:
                first_profile = profile if n < 1 else first_profile
                file_obj[self.config_obj[profile]["jar_file"]] = {
                    "state": "fetching",
                    "pos": n+file_pos,
                    "location": self.config_obj[profile]["jar_repository"],
                    "version": download_version,
                    "profile": profile
                }
                
        # reorder cursor positions
        for n, file in enumerate(file_obj):
            file_obj[file]["pos"] = len(file_obj)-n
        file_obj["cur_pos"] = 1
        files = list(file_obj.keys())
        
        if backup:
            self.functions.backup_restore_files({
                "file_list": files,
                "location": "/var/tessellation",
                "action": "backup"
            })
        
        if self.auto_restart:
            result = True
            for file in files:
                if file != "cur_pos": 
                    single_result = threaded_download([file_obj,file,self.auto_restart]) # not threaded with auto_restart
                    if not single_result: 
                        result = False # once set to false, don't update again
            return result
        else:
            for file in files:
                screen_print_download_results(file,True)
            
        with ThreadPoolExecutor() as executor:
            for file in files:
                if file != "cur_pos": 
                    return_obj = executor.submit(threaded_download,[file_obj,file,self.auto_restart])
                    file_obj = return_obj.result()
        
        for _ in range(0,file_obj['cur_pos']-1):
            print("") # return to bottom of screen
            
        for n in range(0,5):
            fail_count = 0
            for file in file_obj.keys():
                if file != "cur_pos":
                    if file_obj[file]["state"] == "failed":
                        fail_count += 1
                    file_obj[file]["pos"] = file_obj[file]["pos"]+1
            if fail_count > 0 and n < 4:
                cprint("  Possible corrupt files downloaded, trying again","red")
                with ThreadPoolExecutor() as executor:
                    for file in file_obj.keys():
                        if file != "cur_pos": 
                            return_obj = executor.submit(threaded_download,[file_obj,file,self.auto_restart])
                            file_obj = return_obj.result()
            elif fail_count > 0 and n > 3:
                self.functions.print_paragraphs([
                    ["Possible network issues downloading files, please try again later.",1,"red"],
                    ["Original binaries will be automatically restored if they were present before the download process initiated.",1,"yellow"]
                ])
                self.functions.backup_restore_files({
                    "file_list": files,
                    "location": "/var/tessellation",
                    "action": "restore"
                })
            elif fail_count == 0:
                break
            
        # if action != "install":
        for profile in profile_names:
            command_obj = {
                **command_obj,
                "profile": profile,
                "global_elements": {"metagraph_name": self.functions.config_obj[profile]["environment"]},
                "download_version": download_version,
            }
            self.download_update_seedlist(command_obj)
           

    def download_update_seedlist(self,command_obj):
        # ===============================
        # NOTE
        # Since seed lists will be removed for PRO score in
        # the future releases of Tessellation, nodectl will use
        # hardcoded seed-list download locations.
        # 
        # This method can be either removed or refactored
        # after new Metagraph Channel requirements are identified
        # ===============================
        
        self.log.logger.debug("node service - download seed list initiated...")
        profile = command_obj.get("profile",self.profile)
        install_upgrade = command_obj.get("install_upgrade",True)
        download_version = command_obj.get("download_version",None)
        environment_name = self.functions.config_obj[profile]["environment"]
        seed_path = self.functions.config_obj[profile]["seed_path"]    
        seed_file = self.config_obj[profile]['seed_file']
        seed_repo = self.config_obj[profile]['seed_repository']
        print_message = True
        
        if self.auto_restart or install_upgrade:
            print_message = False    
        
        if not self.auto_restart:
            progress = {
                "text_start": "Fetching cluster seed file",
                "brackets": f"{environment_name}->{profile}",
                "status": "fetching",
            }
        
        if "disable" in seed_path:
            if not self.auto_restart:
                self.functions.print_cmd_status({
                    **progress,
                    "status": "disabled/skipped",
                    "status_color": "red",
                    "newline": True,
                })
            return
        
        # includes seed-list access-list  
        if download_version == "default":
            self.log.logger.info(f"downloading seed list [{environment_name}] seedlist]")   

        if self.config_obj[profile]["seed_repository"] == "default":
            if environment_name == "testnet":
                bashCommand = f"sudo wget https://constellationlabs-dag.s3.us-west-1.amazonaws.com/testnet-seedlist -O {seed_path} -o /dev/null"
            elif environment_name == "integrationnet":
                bashCommand = f"sudo wget https://constellationlabs-dag.s3.us-west-1.amazonaws.com/integrationnet-seedlist -O {seed_path} -o /dev/null"
            elif environment_name == "mainnet":
                if download_version == "default":
                    download_version = self.version_obj[environment_name][self.functions.default_profile]["cluster_tess_version"]
                bashCommand = f"sudo wget https://github.com/Constellation-Labs/tessellation/releases/download/{download_version}/mainnet-seedlist -O {seed_path} -o /dev/null"
        else:
            # makes ability to not include https or http
            if "http://" not in seed_repo and "https://" not in seed_repo:
                seed_repo = f"https://{seed_repo}"
            bashCommand = f"sudo wget {seed_repo}/{seed_file} -O {seed_path} -o /dev/null"
            
        if not self.auto_restart:
            self.functions.print_cmd_status(progress)
        
        # execute download and test for zero file size   
        for n in range(0,4):
            self.functions.process_command({
                "bashCommand": bashCommand,
                "proc_action": "timeout"
            })
            self.log.logger.debug(f"Attempting to download seedlist with command: [{bashCommand}]")
            system(bashCommand)
            if path.exists(seed_path):
                if self.functions.get_size(seed_path,True) > 0:
                    system(f"chmod 644 {seed_path} > /dev/null 2>&1")
                    break
            if n == 3:
                if self.auto_restart:
                    self.log.logger.critical("unable to obtain seed-list, please check configuration?")
                else:
                    self.error_messages.error_code_messages({
                        "error_code": "ns-241",
                        "line_code": "seed-list"
                    })
            sleep(1)
        
        self.log.logger.debug(f"node service - download seed list completed")
        if not self.auto_restart:
            self.functions.print_cmd_status({
                **progress,
                "status": "complete",
                "newline": True,
            })


    def create_service_bash_file(self,command_obj):
        # create_file_type=(str)
        # background_build=(bool) # default True;  build the auto_restart service?
        
        def replace_service_file_items(profile,template,create_file_type):
            if create_file_type in ["service_file","version_service"]:
                chmod = "644"
                template = template.replace(
                    "nodegarageservicedescription",
                    self.config_obj[profile]["description"]
                )
                template = template.replace(
                    "nodegarageworkingdir",
                    profile
                )
                template = template.replace(
                    "nodegarageexecstartbash",
                    f"cnng-{self.config_obj[profile]['service']}"
                ) 

            elif create_file_type == "service_bash":
                chmod = "755"
                
                template = template.replace(
                    "nodegarageservicename",
                    profile
                ) 
                
                if self.config_obj[profile]["seed_path"] == "disable/disable":
                    template = template.replace("--seedlist nodegarageseedlistv","")
                    template = template.rstrip()
                else:
                    template = template.replace(
                        "nodegarageseedlistv",
                        self.config_obj[profile]["seed_location"]+"/"+self.config_obj[profile]["seed_file"]
                    )
                    template = template.replace("//","/") # avoid double //
                    template = template.rstrip()
                    
                template = template.replace(
                    "nodegaragetessbinaryfile",
                    self.config_obj[profile]["jar_file"]
                )   
                template = template.rstrip()                   
                    
                template = template.replace(
                    "nodegaragecollateral",
                    str(self.config_obj[profile]["collateral"])
                )   
                template = template.rstrip()                   
                    
                port_types = ["public_port","p2p_port","cli_port"]
                for key, value in self.config_obj[profile].items():
                    # java heap updates
                    if "java_" in key:
                        java_mem_type = key[-3::]
                        template = template.replace(
                            f"nodegarage{java_mem_type}v",
                            str(value)
                        )
                        template = template.rstrip()
                        
                    # tcp port updates
                    if key in port_types:
                        template = template.replace(
                            f"nodegarage{key}",
                            str(value)
                        )
                        template = template.rstrip()
                            
                    # token identifier
                    if key == "token_identifier":
                        if value == "disable":
                            template = template.replace("--l0-token-identifier nodegaragetoken","")
                        else: template = template.replace("nodegaragetoken",value)
                        template = template.rstrip()
                            
                    # custom arguments
                    if self.config_obj[profile]["custom_args_enable"]:
                        if "custom_args_enable" not in key and "custom_args_" in key:
                            template = f'{template} --{key.replace("custom_args_","")} {value}'
                            template = template.rstrip()
                            
            # clean up the template
            substring = "/usr/bin/java"
            index = template.find(substring)
            pre_template = template[:index]; post_template = self.functions.cleaner(template[index:],"new_line")
            template = f"{pre_template}{post_template}"
            
            # append background switch to command
            if create_file_type == "service_bash":
                template = f"{template} &"
            template = f"{template}\n"
            return(template,chmod)               
               
        # ===========================================

        single_profile = command_obj.get("single_profile",False)
        background_services = command_obj.get("background_services",False)
        create_file_type = command_obj["create_file_type"]
        
        for profile in self.profile_names:
            profile = single_profile if single_profile else profile
            template = self.create_files({"file": create_file_type})
            template, chmod = replace_service_file_items(profile,template,create_file_type)
                        
            if create_file_type == "version_service":
                service_dir_file = f"/etc/systemd/system/node_version_updater.service"
            elif create_file_type == "service_file":
                service_dir_file = f"/etc/systemd/system/cnng-{self.config_obj[profile]['service']}.service"
            elif create_file_type == "service_bash":
                profile_service = self.config_obj[profile]['service']
                if single_profile:
                    profile_service = self.config_obj[single_profile]['service']
                self.temp_bash_file = service_dir_file = f"{self.functions.nodectl_path}cnng-{profile_service}"
                
            with open(service_dir_file,'w') as file:
                file.write(template)
            file.close()
            
            system(f"chmod {chmod} {service_dir_file} > /dev/null 2>&1")
            if single_profile:
                return
            sleep(.5)
        
        for bg_service in ["node_restart","node_version_updater"]:
            if background_services or not path.isfile(f"/etc/systemd/system/{bg_service}@.service"):
                service = self.create_files({"file": "service_restart"})        
                service_dir_file = f"/etc/systemd/system/{bg_service}@.service"
                with open(service_dir_file,'w') as file:
                    file.write(service)
                file.close()
                system(f"chmod 644 {service_dir_file} > /dev/null 2>&1")        


    def build_service(self,background_build=False):
        self.log.logger.debug("build services method called [build services]")
        build_files = ["service_file","service_bash","version_service"]
        for b_file in build_files:
            self.create_service_bash_file({
                "create_file_type": b_file,
                "background_services": background_build,
            })
                     

    def build_environment_vars(self,command_obj):
        profile = command_obj.get("profile")
        self.env_conf_file = f"{self.functions.nodectl_path}profile_{profile}.conf" # removed in outside method
        
        if not self.auto_restart:
            self.functions.print_cmd_status({
                "text_start": "building environment",
                "status": "creating",
                "status_color": "yellow"
            })
            
        if path.exists(self.env_conf_file):
            self.log.logger.warn(f"found possible abandoned environment file [{self.env_conf_file}] removing.")
            system(f"rm {self.env_conf_file} > /dev/null 2>&1")
            
        with open(self.env_conf_file,"w") as f:
            if self.config_obj[profile]["custom_env_vars_enable"]:
                for env, value in self.config_obj[profile].items():
                    if "custom_env_vars" in env and env != "custom_env_vars_enable":
                        f.write(f'{env.replace("custom_env_vars_","")}={value}\n')
                        
            f.write(f"CL_EXTERNAL_IP={self.functions.get_ext_ip()}\n")
            f.write(f"CL_APP_ENV={self.functions.config_obj[profile]['environment']}\n")
            
            for link_type in ["gl0","ml0"]:
                if self.functions.config_obj[profile][f"{link_type}_link_enable"]:
                    subkey = "GLOBAL_" if link_type == "gl0" else ""
                    f.write(f"CL_{subkey}L0_PEER_ID={self.functions.config_obj[profile][f'{link_type}_link_key']}\n")
                    f.write(f"CL_{subkey}L0_PEER_HTTP_HOST={self.functions.config_obj[profile][f'{link_type}_link_host']}\n")
                    link_profile = self.functions.config_obj[profile][f'{link_type}_link_profile']
                    link_port = self.functions.config_obj[profile][f'{link_type}_link_port']
                    if link_profile in self.functions.config_obj.keys():
                        # forces auto_correct of port if inconsistent with link_profile public
                        link_port = self.functions.config_obj[link_profile]['public_port']
                    f.write(f"CL_{subkey}L0_PEER_HTTP_PORT={link_port}\n")
                
            p12_keys = [
                ['CL_PASSWORD','p12_passphrase'],
                ['CL_KEYPASS','p12_passphrase'],
                ['CL_STOREPASS','p12_passphrase'],
                ['CL_KEYALIAS','p12_key_alias'],
                ['CL_KEYSTORE','p12_key_store'],
            ]
            for key, value in self.functions.config_obj[profile].items():
                for env_key_value in p12_keys:
                    if key == env_key_value[1]:
                        f.write(f'{env_key_value[0]}="{self.functions.config_obj[profile][key]}"\n')
        f.close()

        if not self.auto_restart:        
            self.functions.print_cmd_status({
                "text_start": "building environment",
                "status": "complete",
                "status_color": "green",
                "newline": True,
            }) 

          
    def build_temp_bash_file(self, command_obj):
        if not self.auto_restart:
            self.functions.print_cmd_status({
                "text_start": "Updating services file",
                "status": "creating",
                "status_color": "yellow"
            })
        
        self.create_service_bash_file(command_obj)
        
        if not self.auto_restart:        
            self.functions.print_cmd_status({
                "text_start": "Updating services file",
                "status": "complete",
                "status_color": "green",
                "newline": True,
            })   
        

    def build_remote_link(self,link_type):
        for n in range(0,4):
            source_node_list = self.functions.get_api_node_info({
                "api_host": self.config_obj[self.profile][f"{link_type}_link_host"],
                "api_port": self.config_obj[self.profile][f"{link_type}_link_port"],
                "info_list": ["id","host","p2pPort","state"]
            })
            if source_node_list[3] == "Ready":
                return True

            self.functions.print_cmd_status({
                "text_start": f"{link_type.upper()} Link Node in",
                "brackets": source_node_list[3],
                "text_end": "state | not",
                "status": "Ready",
                "status_color": "red"
            })
            if n > 2:
                self.functions.print_paragraphs([
                    [" ERROR ",0,"yellow,on_red"], ["Cannot join with link node not in \"Ready\" state.",1,"red"],
                    ["Exiting join process, please try again later or check Node configuration.",2,"red"],
                ])
                self.functions.print_auto_restart_warning()
                return False
            
            error_str = colored("before trying again ","red")+colored(n,"yellow",attrs=["bold"])
            error_str += colored(" of ","red")+colored("3","yellow",attrs=["bold"])
            with ProcessPoolExecutor() as executor:
                early_quit = executor.submit(self.functions.key_pressed({
                    "quit_option": "quit_only",
                    "newline": True,    
                }))
                if early_quit:
                    cprint("  Node Operator requested to quit operations","green")
                    exit(0)
            self.functions.print_timer(5,error_str)
        
        executor.shutdown(wait=False,cancel_futures=True)
        return False
        
                               
    def check_for_ReadyToJoin(self,caller):
        for n in range(1,4):
            state = self.functions.test_peer_state({
                "profile": self.profile,
                "simple": True
            })
            if state == "ReadyToJoin":
                return True
            print(colored(f"  API not ready on {self.profile}","red"),colored(state,"yellow"),end=" ")
            print(f'{colored("attempt ","red")}{colored(n,"yellow",attrs=["bold"])}{colored(" of 3","red")}',end="\r")
            sleep(1.5)
            
        if caller == "upgrade":
            return False
        
        self.error_messages.error_code_messages({
            "error_code": "ns-156",
            "line_code": "api_error",
            "extra": self.profile,
            "extra2": None
        })
 
 
    def change_service_state(self,command_obj):
        action = command_obj["action"]
        service_name = command_obj["service_name"]
        caller = command_obj["caller"]
        profile = command_obj.get("profile",self.profile)
        service_display = self.functions.cleaner(service_name,'service_prefix')
            
        self.log.logger.debug(f"changing service state method - action [{action}] service_name [{service_display}] caller = [{caller}]")
        self.functions.get_service_status()
        if action == "start":
            if "inactive" not in self.functions.config_obj["global_elements"]["node_service_status"][profile]:
                if not self.auto_restart:
                    self.functions.print_clear_line()
                    self.functions.print_paragraphs([
                        ["Skipping service change request [",0,"yellow"], [service_display,-1,], ["] because the service is already set to",-1,"yellow"],
                        [self.functions.config_obj["global_elements"]['node_service_status'][profile],1,"yellow"]
                    ])
                self.log.logger.warn(f"change service state [{service_display}] request aborted because service [inactive (dead)]")
                return
            
            self.build_environment_vars({"profile": profile})
            self.build_temp_bash_file({
                "create_file_type": "service_bash",
                "single_profile": profile,
            })

        if action == "stop":
            if self.functions.config_obj["global_elements"]["node_service_status"][profile] == "inactive (dead)":
                self.log.logger.warn(f"service stop on profile [{profile}] skipped because service [{service_display}] is [{self.functions.config_obj['global_elements']['node_service_status'][profile]}]")
                if not self.auto_restart:
                    self.functions.print_clear_line()
                    self.functions.print_cmd_status({
                        "text_start": "Skipping service",
                        "brackets": service_display,
                        "text_end": "status already",
                        "status": "ApiNotReady",
                        "newline": True
                    })
                return "skip_timer"
        else: # don't do on stop
            bashCommand = f"systemctl daemon-reload" # done for extra stability
            _ = self.functions.process_command({
                "bashCommand": bashCommand,
                "proc_action": "poll"
            })
            
        self.log.logger.debug(f"changing service state method - action [{action}] service [{service_display}] caller = [{caller}] - issuing systemctl command")

        bashCommand = f"systemctl {action} {service_name}"
        _ = self.functions.process_command({
            "bashCommand": bashCommand,
            "proc_action": "timeout" if action == "stop" else "wait",
            "timeout": 5 if action == "stop" else 180
        })

        if action == "start":
            # clean up for a little more security of passphrases and cleaner installation
            system(f"rm {self.env_conf_file} {self.temp_bash_file} > /dev/null 2>&1")
            pass
        
        
    def leave_cluster(self,command_obj):
        # secs=50=(int),cli_flag=(bool)=False):
        secs = command_obj.get("secs",30)
        cli_flag = command_obj.get("cli_flag",False)
        profile = command_obj.get("profile",self.profile)
        skip_thread = command_obj.get("skip_thread",False)
        threaded = command_obj.get("threaded",False)
        self.set_profile(profile)

        state = self.functions.test_peer_state({
            "threaded": threaded,
            "profile": self.profile,
            "skip_thread": skip_thread,
            "simple": True
        }) 
               
        if state not in self.functions.not_on_network_list: # otherwise skip
            cmd = f"curl -X POST http://127.0.0.1:{self.api_ports['cli']}/cluster/leave"
            self.functions.process_command({
                "bashCommand": cmd,
                "proc_action": "timeout"
            })
            if not cli_flag:
                sleep(secs)
                
        return state
                       

    def join_cluster(self,command_obj):
        # action(str)
        action = command_obj["action"]
        caller = command_obj.get("caller",False) # for troubleshooting and logging
        interactive = command_obj.get("interactive",True)
        final = False  # only allow 2 non_interactive attempts
        
        self.set_profile_api_ports()
        
        self.log.logger.info(f"joining cluster profile [{self.profile}]")
        layer_zero_ready = False
        join_failure = False
        exception_found = False
        state = None
        
        # profile is set by cli.set_profile method
        gl0_link_profile = self.functions.config_obj[self.profile]["gl0_link_profile"]
        gl0_linking_enabled = self.functions.config_obj[self.profile]["gl0_link_enable"]
        ml0_link_profile = self.functions.config_obj[self.profile]["ml0_link_profile"]
        ml0_linking_enabled = self.functions.config_obj[self.profile]["ml0_link_enable"]
        profile_layer = self.functions.config_obj[self.profile]["layer"]
        link_types = ["gl0","ml0"]
        headers = {
            'Content-type': 'application/json',
        }

        if caller: self.log.logger.debug(f"join_cluster called from [{caller}]")
        
        found_link_types = []
        if gl0_linking_enabled or ml0_linking_enabled:
            self.log.logger.info(f"join environment [{self.functions.config_obj[self.profile]['environment']}] - join request waiting for Layer0 to become [Ready]")
            if not self.auto_restart:
                for link_type in link_types:
                    verb = "profile" if eval(f"{link_type}_link_profile") != "None" else ""
                    link_word = eval(f"{link_type}_link_profile") if verb == "profile" else "Remote Link"
                    graph_type = "Hypergraph" if link_type == "gl0" else "Metagraph"
                    if eval(f"{link_type}_linking_enabled"):
                        self.functions.print_paragraphs([
                            [f"Waiting on {verb}",0,"yellow"],[link_word,0,"green"],["state to be",0,"yellow"],
                            ["Ready",0,"green"], [f"before initiating {graph_type} join.",1,"yellow"]
                        ])
                        found_link_types.append(link_type)
                    if eval(f"{link_type}_linking_enabled") and eval(f"{link_type}_link_profile") == "None":
                        layer_zero_ready = self.build_remote_link(link_type)
                        if not layer_zero_ready:
                            if link_type == "gl0": gl0_linking_enabled = False
                            elif link_type == "ml0": ml0_linking_enabled = False

        self.source_node_choice = self.functions.get_info_from_edge_point({
            "caller": f"{caller} -> join_cluster",
            "profile": self.profile,
            "desired_key": "state",
            "desired_value": "Ready",
            "return_value": "all",
            "api_endpoint_type": "consensus",
        })
        
        # join header header data
        data = { 
                "id": self.source_node_choice["id"], 
                "ip": self.source_node_choice["ip"], 
                "p2pPort": self.source_node_choice["p2pPort"] 
        }
        self.log.logger.info(f"join cluster -> joining via [{data}]")

        join_session = Session()  # this is a requests Session external library
                
        if gl0_linking_enabled or ml0_linking_enabled:
            for link_type in link_types:
                if eval(f"{link_type}_link_profile") != "None":  # if None should be static
                    try:
                        _ = self.functions.pull_profile({
                            "req": "ports",
                            "profile": eval(f"{link_type}_link_profile")
                        })  
                    except:
                        self.error_messages.error_code_messages({
                            "error_code": "ser-357",
                            "line_code": "link_to_profile",
                            "extra": self.profile,
                            "extra2": eval(f"{link_type}_link_profile")
                    })
            
                    while True:
                        for n in range(1,10):
                            start = n*12-12
                            if n == 1:
                                start = 1

                            state = self.functions.test_peer_state({
                                "profile": eval(f"{link_type}_link_profile"),
                                "simple": True
                            })

                            if not self.auto_restart:
                                self.functions.print_cmd_status({
                                    "text_start": "Current Found State",
                                    "brackets": eval(f"{link_type}_link_profile"),
                                    "status": state,
                                    "newline": True,
                                })
                                
                            if state == "Ready":
                                layer_zero_ready = True
                                break
                            if state != "Observing" and state != "WaitingForReady":
                                layer_zero_ready = False
                                join_failure = True
                                break

                            if action == "cli":
                                self.functions.print_clear_line()
                                self.functions.print_timer(12,f"out of [{colored('108s','yellow')}{colored(']','magenta')}, {colored('for L0 to move to Ready','magenta')}".ljust(42),start)
                            else:
                                self.functions.print_timer(12,"Sleeping prior to retry")
                        if layer_zero_ready or join_failure:
                            break

                        if not self.auto_restart and not layer_zero_ready:
                            self.functions.print_paragraphs([
                                ["",1], [" ERROR ",0,"red,on_yellow"],
                                [f"nodectl was unable to find the {link_type.upper()} Node or Profile peer link in 'Ready' state.  The Node Operator can either",0,"red"],
                                [f"continue to wait for the state to become 'Ready' or exit now and try again to join after the link profile or Node becomes",0,"red"],
                                [f"'Ready'.",2,"red"],

                                ["If the Node Operator chooses to exit, issue the following commands to verify the status of each profile and restart when 'Ready' state is found:",1],                        
                                ["sudo nodectl status",1,"yellow"],
                                [f"sudo nodectl restart -p {self.profile}",2,"yellow"],
                            ])

                            if interactive:
                                self.functions.confirm_action({
                                    "yes_no_default": "y",
                                    "return_on": "y",
                                    "prompt": "Would you like to continue waiting?",
                                    "exit_if": True,
                                })
                                cprint("  Continuing to wait...","green")
                            else:
                                cprint("  Non-interactive mode detected...","yellow")
                                if final:
                                    break
                                final = True  # only allow one retry
                    
        if (profile_layer == 0 and not gl0_linking_enabled) or layer_zero_ready:
            if not self.auto_restart:
                self.functions.print_cmd_status({
                    "text_start": "Preparing to join cluster",
                    "brackets": self.profile,
                    "newline": True,
                })
                sleep(1)
                
            self.log.logger.info(f"attempting to join profile [{self.profile}] through localhost port [{self.api_ports['cli']}] action [{action}]")
            for n in range(1,5):
                try:
                    _ = join_session.post(f'http://127.0.0.1:{self.api_ports["cli"]}/cluster/join', headers=headers, json=data)
                except Exception as e:
                    exception = e
                else:
                    exception = "none"
                    break
                exception_found = True
                self.log.logger.error(f"{action} join attempt failed with [{exception}] retrying | [{self.profile}]")
                if not self.auto_restart:
                    self.functions.print_cmd_status({
                        "text_start": "Join attempt",
                        "brackets": f"{n} of {4}",
                        "status": "unsuccessful",
                        "status_color": "red",
                        "newline": True
                    })
                    self.functions.print_timer(8,"pausing")
            
            if exception_found and action == "auto_join":
                # needs to be first
                self.log.logger.critical(f"auto_join was unable to join the network | error: [{exception} | returning unsuccessfully")
            elif "NewConnectionError" in str(exception):
                self.error_messages.error_code_messages({
                    "error_code": "ser-346",
                    "line_code": "new_connect_error",
                    "extra": self.profile,
                    "extra2": exception
                })
            elif "Max retries exceeded" in str(exception):
                self.error_messages.error_code_messages({
                    "error_code": "ser-349",
                    "line_code": "max_retries",
                    "extra": self.profile,
                    "extra2": exception
                })
            elif "Connection refused" in str(exception):
                self.error_messages.error_code_messages({
                    "error_code": "ser-351",
                    "line_code": "connect_refused",
                    "extra": self.profile,
                    "extra2": exception
                })
            elif exception != "none":
                self.error_messages.error_code_messages({
                    "error_code": "ser-353",
                    "line_code": "join_error",
                    "extra2": self.profile,
                    "extra": exception
                })
            if exception_found and not self.auto_restart:
                print("")  # need a newline
                
            result = "done".ljust(32)
        else:
            try: return_str = found_link_types.pop()
            except: return_str == self.profile
            else:
                for link_type in found_link_types:
                    return_str += f" and {link_type}"
            result = f"{return_str} not Ready".ljust(32)
                
        if action == "cli":
            return result       
        
        
    def create_files(self,command_obj):
        # file=(str), environment_name=(str) default "mainnet", upgrade_required=(bool) default False
        # messy method so placed at the end of file for readability.
        
        var = SimpleNamespace(**command_obj)
        var.environment_name = command_obj.get("environment_name","mainnet")
        var.upgrade_required = command_obj.get("upgrade_required",False)
        var.pre_release = command_obj.get("pre_release",False)
        
        cur_file2 = "" # initialize
        
        if var.file == "service_file":
            cur_file = f'''[Unit]
Description=nodegarageservicedescription
StartLimitBurst=50
StartLimitIntervalSec=0

[Service]
Type=forking
EnvironmentFile={self.functions.nodectl_path}profile_nodegarageworkingdir.conf
WorkingDirectory=/var/tessellation/nodegarageworkingdir
ExecStart={self.functions.nodectl_path}nodegarageexecstartbash

[Install]
WantedBy=multi-user.target
'''
     
        if var.file == "service_bash":
            cur_file = '''#!/bin/bash
            
# This file is used by the [nodegarageservicename] profile
# to run your Node's debian service.
#
# Node Operators should not alter this file;
# rather, utilize the: 'sudo nodectl configure' command to  
# alter this file and avoid undesired affects.
# =========================================================

/usr/bin/java -jar '-Xmsnodegaragexmsv' '-Xmxnodegaragexmxv' '-Xssnodegaragexssv' /var/tessellation/nodegaragetessbinaryfile run-validator --public-port nodegaragepublic_port --p2p-port nodegaragep2p_port --cli-port nodegaragecli_port --seedlist nodegarageseedlistv --collateral nodegaragecollateral --l0-token-identifier nodegaragetoken
'''
        
        if var.file == "service_restart":
            cur_file = '''[Unit]
Description=Constellation Node auto_restart service
StartLimitBurst=50
StartLimitIntervalSec=15
After=multi-user.target

[Service]
Type=Simple
WorkingDirectory=/usr/local/bin
Environment="SCRIPT_ARGS=%I"
ExecStart=nodectl service_restart $SCRIPT_ARGS
Restart=always
RestartSec=15
RuntimeMaxSec=14400
ExecStop=/bin/true

[Install]
WantedBy=multi-user.target
'''
        
        if var.file == "version_service":
            cur_file = '''[Unit]
Description=Constellation Node version update service
After=multi-user.target

[Service]
Type=simple
WorkingDirectory=/usr/local/bin
ExecStart=nodectl uvos
Restart=always
RestartSec=2m
ExecStop=/bin/true

[Install]
WantedBy=multi-user.target
'''
        
        if var.file == "config_yaml_init":
            cur_file = '''---
# NODECTL CONFIGURATION FILE
# @netmet72
# =========================================================
# IMPORTANT IMPORTANT IMPORTANT IMPORTANT
#
# It is discouraged to update this file manually.  nodectl may
# update this file through automation at any time, causing any
# changes you make to be lost.
#
# Do NOT update this file unless you know what you are
# doing !!  Please see the Constellation Network
# documentation hub for details on how to configure
# this file.
# =========================================================
# Metagraph sections isolated by profile key name
# =========================================================
# Custom Options and Environment Variables
# ---------------------------------------------------------
# Required arguments must be listed BEFORE any custom
# entered options or environment variables !!
#
# Failure to do so may create undesired results from
# nodectl (especially the configurator) the Node Operator
# should use the configurator over manually updating this 
# config file.
# ---------------------------------------------------------
# Required arguments 
# ---------------------------------------------------------
# custom_args_enable: True (or False)
# custom_env_vars_enable: True (or False)
# ---------------------------------------------------------
# MANUAL ENTRY MUST PREFIX "custom_args_" to your arg
# custom_args_var1: value1
# custom_args_var2: value2
# MANUAL ENTRY MUST PREFIX "custom_env_var_" to your env_var
# ---------------------------------------------------------
# MANUAL ENTRY MUST BE IN CORRECT ORDER FOR CONFIGURATOR
# TO WORK PROPERLY.  
# custom_args_enable followed by all custom_args
# custom_env_vars_enabled followed by all custom_env_var
# Failure to do so will lead to unexpected behavior
# ---------------------------------------------------------
# Examples)
# custom_env_vars_CL_SNAPSHOT_STORED_PATH: /location1/here/
# custom_env_vars_CL_INCREMENTAL_SNAPSHOT_STORED_PATH: /location2/here/
# custom_env_vars_CL_INCREMENTAL_SNAPSHOT_TMP_STORED_PATH: /location3/here/
# =========================================================

nodectl:
'''
        
        if var.file == "config_yaml_profile":
            cur_file = '''  nodegarageprofile:
    profile_enable: nodegarageenable
    environment: nodegarageenvironment
    description: nodegaragedescription
    node_type: nodegaragenodetype
    meta_type: nodegaragemetatype
    layer: nodegarageblocklayer
    collateral: nodegaragecollateral
    service: nodegarageservice
    edge_point: nodegarageedgepointhost
    edge_point_tcp_port: nodegarageedgepointtcpport
    public_port: nodegaragepublic
    p2p_port: nodegaragep2p
    cli_port: nodegaragecli
    gl0_link_enable: nodegaragegl0linkenable
    gl0_link_key: nodegaragegl0linkkey
    gl0_link_host: nodegaragegl0linkhost
    gl0_link_port: nodegaragegl0linkport
    gl0_link_profile: nodegaragegl0linkprofile
    ml0_link_enable: nodegarageml0linkenable
    ml0_link_key: nodegarageml0linkkey
    ml0_link_host: nodegarageml0linkhost
    ml0_link_port: nodegarageml0linkport
    ml0_link_profile: nodegarageml0linkprofile
    token_identifier: nodegaragetokenidentifier
    directory_backups: nodegaragedirectorybackups
    directory_uploads: nodegaragedirectoryuploads
    java_xms: nodegaragexms
    java_xmx: nodegaragexmx
    java_xss: nodegaragexss
    jar_repository: nodegaragejarrepository
    jar_file: nodegaragejarfile
    p12_nodeadmin: nodegaragep12nodeadmin
    p12_key_location: nodegaragep12keylocation
    p12_key_name: nodegaragep12keyname
    p12_key_alias: nodegaragep12keyalias
    p12_passphrase: nodegaragep12passphrase
    seed_location: nodegarageseedlocation
    seed_repository: nodegarageseedrepository
    seed_file: nodegarageseedfile
    priority_source_location: nodegarageprioritysourcelocation
    priority_source_repository: nodegarageprioritysourcerepository
    priority_source_file: nodegarageprioritysourcefile
    custom_args_enable: nodegaragecustomargsenable
    custom_env_vars_enable: nodegaragecustomenvvarsenable      
'''
        
        if var.file == "config_yaml_autorestart":
            cur_file = '''  global_auto_restart:
    auto_restart: nodegarageeautoenable
    auto_upgrade: nodegarageautoupgrade
    on_boot: nodegarageonboot
    rapid_restart: nodegaragerapidrestart
'''
        
        if var.file == "config_yaml_p12":
            cur_file = '''  global_p12:
    nodeadmin: nodegaragep12nodeadmin
    key_location: nodegaragep12keylocation
    key_name: nodegaragep12keyname
    key_alias: nodegaragep12keyalias
    passphrase: nodegaragep12passphrase
'''
        
        if var.file == "config_yaml_global_elements":
            cur_file = '''  global_elements:
    metagraph_name: nodegaragemetagraphname         
    nodectl_yaml: nodegaragenodectlyaml
    log_level: nodegarageloglevel
'''

        elif var.file == "upgrade":
            url = "https://github.com/stardustCollective/nodectl/releases/download/NODECTL_VERSION/nodectl_ARCH"
            cur_file = '''#!/bin/bash

red='\033[1;31m'
blue='\033[1;36m'
pink='\033[1;35m'
green='\033[1;32m'
yellow='\033[1;33m'
clr='\033[0m'
'''
            cur_file += f'''
sudo mv /usr/local/bin/nodectl NODECTL_BACKUPnodectl_NODECTL_OLD
sleep 2
sudo wget {url} -P /usr/local/bin -O /usr/local/bin/nodectl -o /dev/null
sleep 1
'''
            cur_file += '''
sudo chmod +x /usr/local/bin/nodectl
echo ""
echo "  ${green}COMPLETED! nodectl upgraded to NODECTL_VERSION ${clr}"
sleep 1

if [ -e "/usr/local/bin/nodectl" ]; then
    size=$(stat -c %s "/usr/local/bin/nodectl")
    if [ "$size" -eq 0 ]; then
       echo "  ${red}Error found, file did not download properly, please try again."
       exit 0
    fi
else
    echo "  ${red}Error found, file did not download properly, please try again."
    exit 0
fi

sudo nodectl update_version_object -f
sudo nodectl verify_nodectl
sudo nodectl version
echo ""
'''
            if var.upgrade_required:
                cur_file2 = '''
echo "  ${blue}This version of nodectl requires an upgrade be performed"
echo "  ${blue}on your Node.\n"
read -e -p "  ${pink}Press ${yellow}Y ${pink}then ${yellow}[ENTER] ${pink}to upgrade or ${yellow}N ${pink}then ${yellow}[ENTER] ${pink}to cancel:${blue} " CHOICE

if [[ ("$CHOICE" == "y" || "$CHOICE" == "Y") ]]; then
    echo "${clr}"
    sudo nodectl upgrade
fi
exit 0

'''
            else:
                cur_file2 += '''
echo "  ${yellow}This version of nodectl ${pink}DOES NOT ${yellow}require an upgrade be performed"
read -e -p "  ${blue}Press ${yellow}[ENTER] ${blue}to continue...${clr}" CHOICE
exit 0
'''
        return cur_file+cur_file2
    
    
if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")            
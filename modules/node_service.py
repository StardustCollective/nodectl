from os import path, remove, chmod
from sys import exit
from time import sleep
from termcolor import colored, cprint
from requests import Session
from types import SimpleNamespace

from modules.troubleshoot.errors import Error_codes
from modules.download_service import Download

from modules.config.create_files import create_files

class Node():
        
    def __init__(self,command_obj):
        self.log = False
                
        self.functions = command_obj.get("functions",False)
        if self.functions:
            self.config_obj = self.functions.config_obj
            self.version_obj = self.functions.version_obj
        else:
            self.config_obj = command_obj["config_obj"]
        
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
        self.version_class_obj = None
        self.cn_requests = None

        # during installation, the nodeid will be blank
        # until after the p12 is created causing the install
        # to create the cnng bash files and then write over it.
        self.nodeid = "nodegaragenodeid" 

        self.source_node_choice = None  # initialize source

        self.node_service_status = {
            "node_l0": None,
            "node_l1": None,
        }


    def set_profile(self,profile):
        self.functions.pull_profile({  # test if profile is valid
            "profile": profile,
            "req": "exists"
        })
        self.profile = profile
        
        self.api_ports = self.functions.pull_profile({
            "req": "ports",
            "profile": self.profile,
        })
        
        self.node_service_name = self.functions.pull_profile({
            "req": "service",
            "profile": profile,
        })
    
    
    def set_self_value(self, name, value):
        setattr(self, name, value)

        
    # def _set_link_obj(self):
    #     # profile is set by cli.set_profile method
    #     return {
    #         "gl0_linking_enabled": self.functions.config_obj[self.profile]["gl0_link_enable"],
    #         "ml0_linking_enabled": self.functions.config_obj[self.profile]["ml0_link_enable"],
    #         "gl0_link_ready": False,
    #         "ml0_link_ready": False,
    #         "gl0_link_profile": self.functions.config_obj[self.profile]["gl0_link_profile"],
    #         "ml0_link_profile": self.functions.config_obj[self.profile]["ml0_link_profile"]         
    #     }   
             
    def get_node_service_value(self,name):
        return getattr(self, name)
    
    
    def get_self_value(self,value,default=False):
        return getattr(self, value, default)
    
    
    # def _get_link_types(self):
    #     if self.link_obj["gl0_linking_enabled"] or self.link_obj["ml0_linking_enabled"]:
    #         self._print_log_msg("info",f"join environment [{self.functions.config_obj[self.profile]['environment']}] - join request waiting for Layer0 to become [Ready]")
    #         for link_type in self.link_types:
    #             if not self.auto_restart:
    #                 verb = " profile" if self.link_obj[f"{link_type}_link_profile"] != "None" else ""
    #                 link_word = self.link_obj[f"{link_type}_link_profile"] if verb == " profile" else f"Remote Link [{self.functions.config_obj[self.profile][f'{link_type}_link_host']}:{self.functions.config_obj[self.profile][f'{link_type}_link_port']}]"
    #                 if verb == " profile":
    #                     link_word = self.link_obj[f"{link_type}_link_profile"] 
    #                 else:
    #                     f"Remote Link [{self.functions.config_obj[self.profile][f'{link_type}_link_host']}:{self.functions.config_obj[self.profile][f'{link_type}_link_port']}]"
    #                 graph_type = "Hypergraph" if self.functions.config_obj[self.profile]['meta_type'] == "gl" else "cluster"
    #             if self.link_obj[f"{link_type}_linking_enabled"]:
    #                 if not self.auto_restart:
    #                     self.functions.print_paragraphs([
    #                         [f"Waiting on{verb}",0,"yellow"],[link_word,0,"green"],["state to be",0,"yellow"],
    #                         ["Ready",0,"green"], [f"before initiating {graph_type} join.",1,"yellow"]
    #                     ])
    #                 self.found_link_types.append(link_type)
    #             if self.link_obj[f"{link_type}_linking_enabled"]: 
    #                 self.link_obj[f"{link_type}_link_ready"] = self.build_remote_link(link_type,interactive)        
        
                    
    def download_constellation_binaries(self,command_obj):
        action = command_obj.get("action",False)
        if action and not "install" in action:
            if not self.version_obj:
                self.version_obj = self.config_obj['global_elements']['version_obj']

        # self.version_class_obj.set_parameters()
        # self.version_class_obj.cn_requests["config_obj"] = self.config_obj
        # self.version_class_obj.execute_versioning()
                
        download_service = Download({
            "command_obj": command_obj,
            "get_self_value": self.get_self_value,
            "set_self_value": self.set_self_value,
        })
        
        download_service.set_parameters()
        return download_service.execute_downloads()


    def create_service_bash_file(self,command_obj):
        # create_file_type=(str)
        # background_build=(bool) # default True;  build the auto_restart service?
        
        def replace_service_file_items(profile,template,create_file_type):
            chmod_code = "755" # default
            if create_file_type in ["service_file","version_service"]:
                chmod_code = "644"
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
                template = template.replace(
                    "nodegarageservicename",
                    profile
                ) 
                
                layer0 = 9
                layer1 = 11
                if "layer_scheduling_priority" in self.config_obj["global_elements"]:
                    try: 
                        layer0 = int(self.config_obj["global_elements"]["layer_scheduling_priority"]["layer0"])
                        layer1 = int(self.config_obj["global_elements"]["layer_scheduling_priority"]["layer1"])
                        if layer0 < 1:
                            raise("invalid schedule")
                        if layer1 < layer0 or layer1 < 1:
                            raise("invalud schedule")
                    except Exception as e:
                        self.log.logger[self.log_key].error(f"build service bash entities | invalid [{e}] ... canceling request")
                        self.error_messages.error_code_messages({
                            "error_code": "ns-634",
                            "line_code": "config_error",
                            "extra": "format",
                            "extra2": "layer scheduling priority custom configuration error",
                        })

                c_layer = layer0 if self.config_obj[profile]["layer"] < 1 else layer1
                template = template.replace("nodegaragecpupriority",f'{c_layer}')
                
                if self.config_obj[profile]["seed_path"] == "disable":
                    template = template.replace("--seedlist nodegarageseedlistv","")
                    template = template.rstrip()
                else:
                    template = template.replace(
                        "nodegarageseedlistv",
                        self.config_obj[profile]["seed_path"]
                    )
                    template = template.replace("//","/") # avoid double //
                    template = template.rstrip()
                
                if self.config_obj[profile]["pro_rating_path"] == "disable":
                    template = template.replace("--ratings nodegarageratingv","")
                    template = template.rstrip()
                else:
                    template = template.replace(
                        "nodegarageratingv",
                        self.config_obj[profile]["pro_rating_path"]
                    )
                    template = template.replace("//","/") # avoid double //
                    template = template.rstrip()
                    
                template = template.replace(
                    "nodegaragetessbinaryfilepath",
                    self.config_obj[profile]["jar_path"]
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
            post_template = self.functions.cleaner(post_template,"double_spaces")
            template = f"{pre_template}{post_template}"
            
            # append background switch to command
            if create_file_type == "service_bash":
                template = f"{template} &"
            template = f"{template}\n"
            return(template,chmod_code)               
               
        # ===========================================

        single_profile = command_obj.get("single_profile",False)
        background_services = command_obj.get("background_services",False)
        create_file_type = command_obj["create_file_type"]

        for profile in self.profile_names:
            profile = single_profile if single_profile else profile
            template = self.create_files({"file": create_file_type})
            template, chmod_code = replace_service_file_items(profile,template,create_file_type)
                        
            if create_file_type == "version_service":
                service_dir_file = f"/etc/systemd/system/node_version_updater.service"
            elif create_file_type == "service_file":
                service_dir_file = f"/etc/systemd/system/cnng-{self.config_obj[profile]['service']}.service"
            elif create_file_type == "auto_restart_service_log":
                service_dir_file = "/var/tessellation/nodectl/auto_restart_logger.sh"
                single_profile = True
            elif create_file_type == "service_bash":
                profile_service = self.config_obj[profile]['service']
                if single_profile:
                    profile_service = self.config_obj[single_profile]['service']
                self.temp_bash_file = service_dir_file = f"{self.functions.nodectl_path}cnng-{profile_service}"
                
            with open(service_dir_file,'w') as file:
                file.write(template)
            file.close()
            
            chmod(service_dir_file,int(f"0o{chmod_code}",8))
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
                chmod(service_dir_file,0o644)        


    def build_service(self,background_build=False):
        self._print_log_msg("debug","build services method called [build services]")
        build_files = ["service_file","service_bash","version_service","auto_restart_service_log"]
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
            self._print_log_msg("warning",f"found possible abandoned environment file [{self.env_conf_file}] removing.")
            remove(self.env_conf_file)
            
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
                        epass = self.functions.config_obj[profile][key]
                        if self.config_obj["global_p12"]["encryption"] and "PASS" in env_key_value[0]:
                            eprofile = profile
                            if self.functions.config_obj[profile]["global_p12_passphrase"]: eprofile = "global"
                            epass = self.functions.get_persist_hash({
                                "pass1": epass,
                                "profile": eprofile,
                                "enc_data": True,
                            })                             
                        f.write(f'{env_key_value[0]}="{epass}"\n')
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
        

    def build_remote_link(self,link_type,interactive):
        not_ready_option = None
        n = -1
        try_again = True

        while True:
            n += 1
            user_wait = False
                
            link_host = self.config_obj[self.profile][f"{link_type}_link_host"]
            link_profile = self.config_obj[self.profile][f"{link_type}_link_profile"]
            
            if not self.config_obj["global_elements"]["cluster_info_lists"].get(link_profile):
                self.cn_requests.set_self_value("config_obj",self.config_obj)
                self.cn_requests.set_self_value("peer",False)
                self.cn_requests.set_self_value("use_local",False)
                self.cn_requests.set_self_value("get_state",False)
                self.cn_requests.set_self_value("use_ep",True)
                self.cn_requests.set_self_value("profile_names",[link_profile])
                self.cn_requests.set_cluster_cache()
                self.config_obj = self.cn_requests.get_self_value("config_obj")
                self.config_obj["global_elements"]["cluster_info_lists"][link_profile].pop()
                
            for attempt in range(0,2):
                link_node = next(
                    (node for node in self.config_obj["global_elements"]["cluster_info_lists"][link_profile] if node["ip"] == link_host), False
                )
                if link_node: 
                    break

            if not link_node: 
                extra2 = "Is the profile linking configured correctly? nodectl was unable to find "
                extra2 += "or connect to the linking settings in this configuration. This could also " 
                extra2 += "indicate that the profile or the external node this node is configured to "
                extra2 += "link to is not part of the cluster."
                if n > 2:                    
                    self.error_messages.error_code_messages({
                        "error_code": "ns-634",
                        "line_code": "config_error",
                        "extra": "format",
                        "extra2": extra2,
                    })
                self._print_log_msg("error",f"build_remote_link -> unable to determine the source node links | target_linking_node [{str(link_node)}]")
                continue # try again... 

            self.cn_requests.set_self_value("peer",link_node["ip"])
            self.cn_requests.set_self_value("api_public_port",link_node["publicPort"])
            link_node["state"] = self.cn_requests.get_current_peer_state(link_profile,True)
            if not self.auto_restart:
                self.functions.print_cmd_status({
                    "text_start": f"{link_type.upper()} Link State:",
                    "brackets": link_node["state"],
                    "text_end": "" if link_node["state"] == "Ready" else "not",
                    "status": "Ready",
                    "status_color": "green" if link_node["state"] == "Ready" else "red",
                    "newline": True
                })

            if link_node["state"] == "Ready":
                self._print_log_msg("debug",f"build_remote_link -> source node [{link_node['ip']}] in state [{link_node['state']}].")
                return True

            if n > 2:
                if link_node['state'] == "WaitingForReady" and try_again:
                    try_again = False
                    n = 0  
                else:                  
                    self._print_log_msg("error",f"build_remote_link -> node link not [Ready] | source node [{link_node['state']}].")
                    if not self.auto_restart:
                        self.functions.print_paragraphs([
                            [" ERROR ",0,"yellow,on_red"], ["Cannot join with link node not in \"Ready\" state.",1,"red"],
                            ["Exiting join process, please try again later or check node configuration.",2,"red"],
                        ])
                        self.functions.print_auto_restart_warning()
                    return False
            
            error_str = colored("before trying again ","magenta")+colored(n+1,"yellow",attrs=["bold"])
            error_str += colored(" of ","red")+colored("3","yellow",attrs=["bold"])

            if interactive and not self.auto_restart:
                self.functions.print_paragraphs([
                    ["Press",0],["w",0,"yellow"], ["to wait 30 seconds",1],
                    ["Press",0],["s",0,"yellow"], ["to skip join",1],
                    ["Press",0],["q",0,"yellow"], ["to quit",1],
                ])
                not_ready_option =self.functions.get_user_keypress({
                    "prompt": "KEY press and OPTION",
                    "prompt_color": "magenta",
                    "options": ["W","S","Q"],
                })
                if not_ready_option.upper() == "Q":
                    cprint("  Node Operator requested to quit operations","green")
                    exit(0)

                if not_ready_option.upper() == "S": 
                    break

                error_str = colored("before trying again ","magenta")
                user_wait = True

            if not self.auto_restart:
                self.functions.print_timer({
                    "seconds": 29, # 29
                    "phrase": error_str,
                })
                if n > 3 and not user_wait: # 3
                    break

        return False
        
                               
    def check_for_ReadyToJoin(self,caller):
        for n in range(1,4):
            state = self.cn_requests.get_current_local_state(self.profile, True)
            if state == "ReadyToJoin":
                return True
            if n < 2: print("")
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
        cn_requests = command_obj["cn_requests"]
            
        self._print_log_msg("debug",f"changing service state method - action [{action}] service_name [{service_display}] caller = [{caller}]")
        cn_requests.config_obj = self.functions.get_service_status(cn_requests.config_obj, True)
        
        if action == "start":
            if cn_requests.config_obj["global_elements"]["node_service_status"][f"{profile}_service_return_code"] < 1:
                if not self.auto_restart:
                    self.functions.print_clear_line()
                    self.functions.print_paragraphs([
                        ["Skipping service change request [",0,"yellow"], [service_display,-1,], ["] because the service is already set to",-1,"yellow"],
                        [cn_requests.config_obj["global_elements"]['node_service_status'][profile],1,"yellow"]
                    ])
                self._print_log_msg("warning",f"change service state [{service_display}] request aborted because service [inactive (dead)]")
                return
            
            self.build_environment_vars({"profile": profile})
            self.build_temp_bash_file({
                "create_file_type": "service_bash",
                "single_profile": profile,
            })

        if action == "stop":
            if cn_requests.config_obj["global_elements"]["node_service_status"][f"{profile}_service_return_code"] > 0:
                self._print_log_msg("warning",f"service stop on profile [{profile}] skipped because service [{service_display}] is [{self.functions.config_obj['global_elements']['node_service_status'][profile]}]")
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
            
        self._print_log_msg("debug",f"changing service state method - action [{action}] service [{service_display}] caller = [{caller}] - issuing systemctl command")

        bashCommand = f"systemctl {action} {service_name}"
        _ = self.functions.process_command({
            "bashCommand": bashCommand,
            "proc_action": "subprocess_run_check_text" if action == "stop" else "wait",
            "timeout": 30 if action == "stop" else 180
        })

        if action == "start":
            # clean up for a little more security of passphrases and cleaner installation
            self.functions.remove_files({
                "file_or_list": [self.env_conf_file,self.temp_bash_file],
                "caller": f"change_service_state [{caller}]",
            })
        
        
    def leave_cluster(self,command_obj):
        print("leave_cluster --- moved to cn_requsts")
        exit(0)
        # # secs=50=(int),cli_flag=(bool)=False):
        # secs = command_obj.get("secs",30)
        # cli_flag = command_obj.get("cli_flag",False)
        # profile = command_obj.get("profile",self.profile)
        # # skip_thread = command_obj.get("skip_thread",False)
        # # threaded = command_obj.get("threaded",False)
        # state = command_obj.get("state","ApiNotReady")
        # self.set_profile(profile)


        # # state = self.functions.test_peer_state({
        # #     "caller": "leave",
        # #     "threaded": threaded,
        # #     "profile": self.profile,
        # #     "skip_thread": skip_thread,
        # #     "simple": True
        # # })         
        
        # if state not in self.functions.not_on_network_list: # otherwise skip
        #     self._print_log_msg("debug",f"cluster leave process | profile [{profile}] state [{state}] ip [127.0.0.1]")
        #     cmd = f"curl -X POST http://127.0.0.1:{self.api_ports['cli']}/cluster/leave"
        #     self.functions.process_command({
        #         "bashCommand": cmd,
        #         "proc_action": "timeout"
        #     })
        #     if not cli_flag:
        #         sleep(secs)
                
        # return state
                       

    # def join_cluster(self,command_obj):
    #     self._print_log_msg("info",f"joining cluster profile [{self.profile}]")
        
    #     from modules.submodules.join_service import JoinService
    #     join_service = JoinService(self,command_obj)
    #     join_service.set_self_value("cn_requests",self.cn_requests)
    #     join_service.set_self_value("profile",self.profile)
        
    #     join_service.set_parameters()
        
    #     # action(str)
    #     # action = command_obj["action"]
    #     # caller = command_obj.get("caller",False) # for troubleshooting and logging
    #     # interactive = command_obj.get("interactive",True)
        
    #     # final = False  # only allow 2 non_interactive attempts
    #     # join_breakout = False
    #     # exception_found = False 
    #     # state = None        

    #     # join_session = Session()
        
    #     # headers = {
    #     #     'Content-type': 'application/json',
    #     # }    
        
    #     self.set_profile_api_ports()
        
        
    #     # profile is set by cli.set_profile method
    #     # profile_layer = self.functions.config_obj[self.profile]["layer"]
    #     join_service.set_link_obj()
    #     # link_obj = {
    #     #     "gl0_linking_enabled": self.functions.config_obj[self.profile]["gl0_link_enable"],
    #     #     "ml0_linking_enabled": self.functions.config_obj[self.profile]["ml0_link_enable"],
    #     #     "gl0_link_ready": False,
    #     #     "ml0_link_ready": False,
    #     #     "gl0_link_profile": self.functions.config_obj[self.profile]["gl0_link_profile"],
    #     #     "ml0_link_profile": self.functions.config_obj[self.profile]["ml0_link_profile"]         
    #     # }

    #     # profile_layer = self.functions.config_obj[self.profile]["layer"]

    #     # headers = {
    #     #     'Content-type': 'application/json',
    #     # }

    #     join_service.print_caller_log()
    #     # if caller:
    #     #     self._print_log_msg("debug",f"join_cluster called from [{caller}]")
        
    #     join_service.get_link_types()
    #     # self.found_link_types = []
    #     # if self.link_obj["gl0_linking_enabled"] or self.link_obj["ml0_linking_enabled"]:
    #     #     self._print_log_msg("info",f"join environment [{self.functions.config_obj[self.profile]['environment']}] - join request waiting for Layer0 to become [Ready]")
    #     #     for link_type in self.link_types:
    #     #         if not self.auto_restart:
    #     #             verb = " profile" if self.link_obj[f"{link_type}_link_profile"] != "None" else ""
    #     #             link_word = self.link_obj[f"{link_type}_link_profile"] if verb == " profile" else f"Remote Link [{self.functions.config_obj[self.profile][f'{link_type}_link_host']}:{self.functions.config_obj[self.profile][f'{link_type}_link_port']}]"
    #     #             if verb == " profile":
    #     #                 link_word = self.link_obj[f"{link_type}_link_profile"] 
    #     #             else:
    #     #                 f"Remote Link [{self.functions.config_obj[self.profile][f'{link_type}_link_host']}:{self.functions.config_obj[self.profile][f'{link_type}_link_port']}]"
    #     #             graph_type = "Hypergraph" if self.functions.config_obj[self.profile]['meta_type'] == "gl" else "cluster"
    #     #         if self.link_obj[f"{link_type}_linking_enabled"]:
    #     #             if not self.auto_restart:
    #     #                 self.functions.print_paragraphs([
    #     #                     [f"Waiting on{verb}",0,"yellow"],[link_word,0,"green"],["state to be",0,"yellow"],
    #     #                     ["Ready",0,"green"], [f"before initiating {graph_type} join.",1,"yellow"]
    #     #                 ])
    #     #             self.found_link_types.append(link_type)
    #     #         if self.link_obj[f"{link_type}_linking_enabled"]: 
    #     #             self.link_obj[f"{link_type}_link_ready"] = self.build_remote_link(link_type,interactive)

    #     join_service.set_join_peer()
    #     join_service.set_join_data_obj()
    #     # # join header header data
    #     # data = { 
    #     #         "id": self.source_node_choice["id"], 
    #     #         "ip": self.source_node_choice["ip"], 
    #     #         "p2pPort": self.source_node_choice["p2pPort"] 
    #     # }
    #     # self._print_log_msg("info",f"join cluster -> joining via [{data}]")

    #     # join_service.print_joining_msgs()
    #     # if not self.auto_restart:
    #     #     if self.config_obj["global_elements"]["metagraph_name"] != "hypergraph":
    #     #         token_identifier = self.config_obj[self.profile]["token_identifier"][:5] + ".." + self.config_obj[self.profile]["token_identifier"][-5:]
    #     #         self.functions.print_cmd_status({
    #     #             "text_start": "Token identifier",
    #     #             "status": token_identifier,
    #     #             "brackets": self.profile,
    #     #             "status_color": "yellow",
    #     #             "newline": True,
    #     #         })

    #     #     self.functions.print_cmd_status({
    #     #         "text_start": "Joining with peer",
    #     #         "status": self.source_node_choice["ip"],
    #     #         "brackets": f'{self.source_node_choice["id"][0:8]}...{self.source_node_choice["id"][-8:]}',
    #     #         "status_color": "yellow",
    #     #         "newline": True,
    #     #     })
        
    #     # join_session = Session()  # this is a requests Session external library
        
    #     # are we clear to join?
    #     join_service.set_clear_to_join()
    #     # for link_type in self.link_types:
    #     #     if profile_layer == 0 and not self.link_obj["gl0_linking_enabled"]:
    #     #         break
    #     #     if self.link_obj[f"{link_type}_linking_enabled"] and not self.link_obj[f"{link_type}_link_ready"]:
    #     #         clear_to_join = False

    #     join_service.process_prepare_to_join()
    #     # if clear_to_join:
    #     #     for link_type in self.link_types:
    #     #         gl0ml0 = self.link_obj[f"{link_type}_link_profile"]
    #     #         if gl0ml0 != "None":  # if None should be static
    #     #             try:
    #     #                 _ = self.functions.pull_profile({
    #     #                     "req": "ports",
    #     #                     "profile": gl0ml0
    #     #                 })  
    #     #             except:
    #     #                 self._print_log_msg("error",f"join link to profile error for profile [{self.profile}] link type [{link_type}]")
    #     #                 if self.auto_restart:
    #     #                     exit(1)
    #     #                 self.error_messages.error_code_messages({
    #     #                     "error_code": "ser-357",
    #     #                     "line_code": "link_to_profile",
    #     #                     "extra": self.profile,
    #     #                     "extra2": gl0ml0
    #     #             })
                
    #     #             while True:
    #     #                 for n in range(1,10):
    #     #                     start = n*12-12
    #     #                     if n == 1:
    #     #                         start = 1

    #     #                     state = self.functions.test_peer_state({
    #     #                         "caller": "join",
    #     #                         "profile": gl0ml0,
    #     #                         "simple": True
    #     #                     })

    #     #                     if not self.auto_restart:
    #     #                         self.functions.print_cmd_status({
    #     #                             "text_start": "Current Found State",
    #     #                             "brackets": gl0ml0,
    #     #                             "status": state,
    #     #                             "newline": True,
    #     #                         })
                                
    #     #                     if state == "Ready":
    #     #                         self.link_obj[f"{link_type}_link_ready"] = True
    #     #                         break
    #     #                     if state != "Observing" and state != "WaitingForReady":
    #     #                         self.link_obj[f"{link_type}_link_ready"] = False
    #     #                         join_breakout = True
    #     #                         break

    #     #                     if action == "cli":
    #     #                         self.functions.print_clear_line()
    #     #                         self.functions.print_timer({
    #     #                             "seconds": 12,
    #     #                             "phrase": f"out of [{colored('108s','yellow')}{colored(']','magenta')}, {colored('for L0 to move to Ready','magenta')}".ljust(42),
    #     #                             "start": start
    #     #                         })
    #     #                     else:
    #     #                         self.functions.print_timer({
    #     #                             "seconds": 12,
    #     #                             "phrase": "sleeping",
    #     #                             "end_phrase": "prior to retry",
    #     #                             "step": -1,
    #     #                             "p_type": "cmd",
    #     #                         })
    #     #                 if self.link_obj[f"{link_type}_link_ready"] or join_breakout:
    #     #                     break

    #     #                 if not self.auto_restart and not self.link_obj[f"{link_type}_link_ready"]:
    #     #                     if isinstance(self.profile,bool):
    #     #                         self.profile = "Unknown"
    #     #                     self.functions.print_paragraphs([
    #     #                         ["",1], [" ERROR ",0,"red,on_yellow"],
    #     #                         [f"nodectl was unable to find the {str(link_type.upper())} node or profile peer link in 'Ready' state.  The Node Operator can either",0,"red"],
    #     #                         [f"continue to wait for the state to become 'Ready' or exit now and try again to join after the link profile or node becomes",0,"red"],
    #     #                         [f"'Ready'.",2,"red"],

    #     #                         ["If the Node Operator chooses to exit, issue the following commands to verify the status of each profile and restart when 'Ready' state is found:",1],                        
    #     #                         ["sudo nodectl status",1,"yellow"],
    #     #                         [f"sudo nodectl restart -p {str(self.profile)}",2,"yellow"],
    #     #                     ])

    #     #                     if self.profile == "Unknown":
    #     #                         cprint("  Profile error, unable to continue...","red")
    #     #                         exit(0)

    #     #                     if interactive:
    #     #                         self.functions.confirm_action({
    #     #                             "yes_no_default": "y",
    #     #                             "return_on": "y",
    #     #                             "prompt": "Would you like to continue waiting?",
    #     #                             "exit_if": True,
    #     #                         })
    #     #                         cprint("  Continuing to wait...","green")
    #     #                     else:
    #     #                         cprint("  Non-interactive mode detected...","yellow")
    #     #                         if final:
    #     #                             break
    #     #                         final = True  # only allow one retry
        
    #     join_service.print_join_status()            
    #         # if not self.auto_restart:
    #         #     self.functions.print_cmd_status({
    #         #         "text_start": "Join cluster status",
    #         #         "brackets": self.profile,
    #         #         "spinner": "dotted",
    #         #         "newline": True,
    #         #         "status": "Preparing",
    #         #         "status_color": "green"
    #         #     })
    #         #     sleep(1)
        
    #     join_service.process_join()        
    #         # self._print_log_msg("info",f"attempting to join profile [{self.profile}] through localhost port [{self.api_ports['cli']}] action [{action}]")
    #         # for n in range(1,5):
    #         #     try:
    #         #         _ = join_session.post(f'http://127.0.0.1:{self.api_ports["cli"]}/cluster/join', headers=headers, json=data)
    #         #     except Exception as e:
    #         #         exception = e
    #         #     else:
    #         #         exception = "none"
    #         #         break
    #         #     exception_found = True
    #         #     self._print_log_msg("error",f"{action} join attempt failed with [{exception}] retrying | [{self.profile}]")
    #         #     if not self.auto_restart:
    #         #         self.functions.print_cmd_status({
    #         #             "text_start": "Join attempt",
    #         #             "brackets": f"{n} of {4}",
    #         #             "status": "unsuccessful",
    #         #             "status_color": "red",
    #         #             "newline": True
    #         #         })
    #         #         self.functions.print_timer({
    #         #             "seconds": 8,
    #         #             "phrase": "Pausing",
    #         #             "p_type": "cmd",
    #         #             "step": -1,
    #         #             "end_phrase": f"of {colored('8','cyan',attrs=['bold'])} {colored('seconds','magenta')}"
    #         #         })
            
    #     join_service.handle_exceptions()
    #         # if exception_found and action == "auto_join":
    #         #     # needs to be first
    #         #     self.log.logger[self.log_key].critical(f"auto_join was unable to join the network | error: [{exception} | returning unsuccessfully")
    #         # elif "NewConnectionError" in str(exception):
    #         #     self.error_messages.error_code_messages({
    #         #         "error_code": "ser-346",
    #         #         "line_code": "new_connect_error",
    #         #         "extra": self.profile,
    #         #         "extra2": exception
    #         #     })
    #         # elif "Max retries exceeded" in str(exception):
    #         #     self.error_messages.error_code_messages({
    #         #         "error_code": "ser-349",
    #         #         "line_code": "max_retries",
    #         #         "extra": self.profile,
    #         #         "extra2": exception
    #         #     })
    #         # elif "Connection refused" in str(exception):
    #         #     self.error_messages.error_code_messages({
    #         #         "error_code": "ser-351",
    #         #         "line_code": "connect_refused",
    #         #         "extra": self.profile,
    #         #         "extra2": exception
    #         #     })
    #         # elif exception != "none":
    #         #     self.error_messages.error_code_messages({
    #         #         "error_code": "ser-353",
    #         #         "line_code": "join_error",
    #         #         "extra2": self.profile,
    #         #         "extra": exception
    #         #     })
    #         # if exception_found and not self.auto_restart:
    #         #     print("")  # need a newline
                
    #         # result = "done".ljust(32)

    #     join_service.handle_not_clear_to_join()
    #     # else:
    #     #     self._print_log_msg("warning","join_cluster --> node was found not clear to join... join skipped.")
    #     #     try: return_str = self.found_link_types.pop()
    #     #     except: return_str = self.profile
    #     #     else:
    #     #         for link_type in self.found_link_types:
    #     #             return_str += f" and/or {link_type}"
    #     #     result = f"{return_str} not Ready".ljust(32)
                
    #     if join_service.action == "cli":
    #         return join_service.result       
        
        
    def create_files(self,command_obj):
        # file=(str), environment_name=(str) default "mainnet", upgrade_required=('full' or bool) default False
        # messy method so placed at the end of file for readability.
        
        var = SimpleNamespace(**command_obj)
        var.environment_name = command_obj.get("environment_name","mainnet")
        var.upgrade_required = command_obj.get("upgrade_required",False)
        var.pre_release = command_obj.get("pre_release",False)

        return create_files(self.functions,var)        
    
    
    def _print_log_msg(self,log_type,msg):
            log_method = getattr(self.log, log_type, None)
            log_method(f"{self.__class__.__name__} --> node_service -> {msg}")    
            
    
         
             
             
if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")
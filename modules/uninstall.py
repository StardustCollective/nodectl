
import shutil
from os import makedirs, system, path, environ, walk, remove, chmod
from pathlib import Path
from time import sleep
from termcolor import colored
from concurrent.futures import ThreadPoolExecutor, as_completed


def start_uninstall(functions,log):
    _ = functions.process_command({"proc_action": "clear"})

    functions.print_header_title({
        "line1": "NODECTL UNINSTALL",
        "single_line": True,
        "newline": "both"
    })

    functions.print_paragraphs([
        [" WARNING ",0,"yellow,on_red"], ["This will",0,"red"], ["attempt",0,"yellow","bold"],
        ["to remove all aspects of this",0,"red"],["Constellation Network",0,"blud","bold"], 
        ["Node.",2,"red"],

        ["Including:",1,"red"],
        ["   - All p12 files*",1],
        ["   - Constellation Binaries",1],
        ["   - Backups",1],
        ["   - Configurations",1],
        ["   - Node services",1],
        ["   - Remove nodeadmin account",1],
        ["   - Restore root access",1],
        ["   - Restore special account access",1],
        ["   - Seedlists",1],
        ["   - Snapshots",1],
        ["   - Uploads",2],

        ["Excluding:",1,"yellow"],
        ["    - Java Installation",1],
        ["    - Haveged Installation",1],
        ["    - External Utility Installs",1],
        ["    - Secure Shell Keys",2],

        ["Please make sure you have a backup of any and all important files before continuing.",1,"red"],
        ["nodectl will not remove SSH keys and non-specific Constellation Network applications, these will need to be done manually.",1,"red"],
        ["This execution cannot be undone.",1,"yellow","bold"],
        ["*You will be offered the option to backup the p12 files, during un-installation.",2,"grey"],

        ["Must type",0], ["CONSTELLATION",0,"yellow","bold"], ["exactly to confirm or",0], 
        ["n",0,"yellow"], ["to cancel this uninstall execution.",1],
    ])

    _ = functions.confirm_action({
        "yes_no_default": "n",
        "return_on": "CONSTELLATION",
        "strict": True,
        "prompt_color": "red",
        "prompt": "Uninstall this Constellation Network node?",
        "incorrect_input": "incorrect input must be 'CONSTELLATION'", 
        "exit_if": True
    })

    log.logger["main"].info("uninstaller initialized --> beginning nodectl removal")
    functions.print_header_title({
        "line1": "BEGINNING UNINSTALL",
        "single_line": True,
        "newline": "both"
    })


def print_status(functions,icmd,running,animate=False,result=False):
    color = "yellow" if running else "green"
    status = "running" if running else "complete"
    if result:
        color = "red"
        status = result

    functions.print_cmd_status({
        "text_start": icmd,
        "dotted_animation": animate,
        "status": status,
        "status_color": color,
        "newline": False if running else True,
    })


def discover_data(services,p12s):
    for sdir in ["/etc","/root","/home","/tmp","/var"]:
        for root, _, ftypes in walk(sdir):
            for ftype in ftypes:
                if ftype.startswith("cnng") and ftype not in services:
                    services.append(path.join(root, ftype))
                elif ftype.endswith(".p12") and ftype not in p12s:
                    p12s.append(path.join(root, ftype))
    
    return services, p12s


def remove_data(functions,log,install=False,quiet=False, quick_install=False):
    install_type = "uninstaller"
    if install: install_type = "installer"
    log.logger["main"].info(f"{install_type} -> removing node data")

    # first element is the title
    d_dirs = ["data","/var/tessellation"]
    services = ["services","node_version_updater.service","node_version_updater@.service","node_restart@.service"]
    p12s = ["key stores"]
    seedlists = ["seed lists"]

    try:
        node_admins = [functions.config_obj["global_p12"]["nodeadmin"]]
    except:
        log.logger["main"].warning(f"{install_type} -> did not find any existing node admins")

    if install:
        retain_log = True
    else:
        retain_log = functions.confirm_action({
            "yes_no_default": "n",
            "return_on": "y",
            "strict": True,
            "prompt_color": "cyan",
            "prompt": "Would you like to retain the nodectl log file?", 
            "exit_if": False
        })
    if retain_log:
        log.logger["main"].info("retaining nodectl.log in [/var/tmp/] as [nodectl.log]")
        if not install:
            functions.print_paragraphs([
                ["nodectl logs will be located here:",1],
                ["location:",0], ["/var/tmp/nodectl.log",1,"yellow"],
            ])
        if not install:
            node_admins.insert(0, "logger_retention")

    if install:
        retain_p12 = False
    else:
        functions.print_paragraphs([
            ["",1],[" WARNING ",0,"red,on_yellow"],["Retaining the node's",0],
            ["p12 files",0,"yellow"], ["can introduce security vulnerabilities because",0],
            ["your p12 files will be remain on this VPS.",1],
        ])
        retain_p12 = functions.confirm_action({
            "yes_no_default": "n",
            "return_on": "y",
            "strict": True,
            "prompt_color": "cyan",
            "prompt": "Would you like to retain the node p12 files?", 
            "exit_if": False
        })
    if retain_p12:
        log.logger["main"].info("retaining node p12 files in [/var/tmp/]")
        if not install:
            functions.print_paragraphs([
                ["nodectl p12s will be located here:",1],
                ["location:",0], ["/var/tmp/",2,"yellow"],
            ])

    if install:  # installer will just use the default dirs, services lists
        if not quiet:
            print(colored("  Handling removal of existing node data","cyan"),end="\r")
        try:
            if path.isdir(f'/home/{functions.config_obj["global_p12"]["nodeadmin"]}'):
                log.logger["main"].warning(f'{install_type} -> found nodeadmin user [{functions.config_obj["global_p12"]["nodeadmin"]}], removed')
                remove_admins(functions,["nodeadmin"],log,True)
        except:
            log.logger["main"].warning(f'{install_type} -> was not able to find a configured nodeadmin user, skipping removal')
            if not quiet:
                if not quick_install:
                    functions.print_paragraphs([
                        [" WARNING ",0,"red,on_yellow"],["nodectl was not able to determine a previous installation",0,"magenta"],
                        ["nodectl administration user account. Therefore removal of such account has been skipped.",2,"magenta"], 
                        ["You can safely ignore this error; however, if you do not want any user data to be retained on this VPS",0,"magenta"],
                        ["you will need to manually remove the known administrative user.",2,"magenta"],
                    ])                    
    else:
        for profile in functions.profile_names:
            for key, value in functions.config_obj[profile].items():
                if "dir" in key and "/var/tessellation/" not in value:
                    d_dirs.append(value)
                elif "service" in key:
                    services.append(f"cnng-{value}.service")
                elif "seed_path" in key and "/var/tessellation/" not in value and value != "disable":
                    seedlists.append(functions.config_obj[profile]["seed_path"])
                elif "p12_nodeadmin" in key and value != "global" and not isinstance(value,bool):
                    if value not in node_admins:
                        node_admins.append(value)

    if install:
        services, p12s = discover_data(services,p12s)
    else:
        functions.print_cmd_status({
            "text_start": "Preparing node data",
            "status": "Please Wait",
            "status_color": "magenta",
            "newline": True,
        })
        functions.print_paragraphs([
            ["This may take a few minutes, please exercise patience",1,"yellow"]
        ])
        with ThreadPoolExecutor() as executor:
            functions.status_dots = True
            status_obj = {
                "text_start": f"Discovering node data",
                "status": "running",
                "status_color": "yellow",
                "dotted_animation": True,
                "newline": False,
            }
            _ = executor.submit(functions.print_cmd_status,status_obj)

            services, p12s = discover_data(services,p12s)

            functions.status_dots = False
            functions.print_cmd_status({
                **status_obj,
                "status": "completed",
                "status_color": "green",
                "dotted_animation": False,
                "newline": True,
            })

    remove_lists = [d_dirs,services,seedlists]
    if not install: remove_lists.append(p12s) # keep p12s for migration purposes

    if install and not quiet:  # installer will just use the default dirs, services lists
        functions.print_cmd_status({
            "text_start": "Removing existing node data",
            "status": "please wait",
            "status_color": "yellow",
            "newline": False,
        })

    for remove_list in remove_lists:
        if retain_p12:
            retain_p12 = False
            for values in remove_lists:
                if values[0] == "key stores":
                    move_values = values[1:]
                    for p12_file_path in move_values:
                        if path.isfile(p12_file_path):
                            copy_no = 0
                            p12_file_tmp = f"/var/tmp/{path.split(p12_file_path)[1]}"
                            if path.isfile(p12_file_tmp):
                                while True:
                                    copy_no += 1
                                    p12_file_tmp_copy = f"{p12_file_tmp}.{copy_no}"
                                    if not path.isfile(p12_file_tmp_copy):
                                        p12_file_tmp = p12_file_tmp_copy
                                        break
                            log.logger["main"].info(f"{install_type} -> moving p12 [{path.split(p12_file_tmp)[1]}] to [{path.split(p12_file_tmp)[0]}].")
                            shutil.copy2(p12_file_path, p12_file_tmp)

        command = f"Removing node related data"
        log_list = []
        if retain_log and remove_list == remove_lists[0]: # only once
            try:
                for file in Path("/var/tessellation/nodectl/logs/").glob("nodectl*.log*"):
                    shutil.copy2(file, Path("/var/tmp/") / file.name)
            except:
                log.logger["main"].info(f"{install_type} -> moving log files failed, skipping...")

        if install:
            if not quiet: # redraw install of blank screen
                functions.print_cmd_status({
                    "text_start": "Removing existing node data",
                    "status": "please wait",
                    "status_color": "yellow",
                    "newline": False,
                })

        with ThreadPoolExecutor() as executor:
            functions.status_dots = True
            if not install:
                command = f"Removing node related {remove_list.pop(0)}"
            status_obj = {
                "text_start": command,
                "status": "running",
                "status_color": "yellow",
                "dotted_animation": True,
                "newline": False,
            }
            if not install and not quiet:
                _ = executor.submit(functions.print_cmd_status,status_obj)
            # command = f"Removing node related {remove_list.pop(0)}"
            # print_status(functions,command,True,True)

            for d_f in remove_list:
                if len(remove_list) > 0:
                    for d_f in remove_list:
                        if not d_f.startswith("/"): d_f = f"/etc/systemd/system/{d_f}"
                        log_list.append(["info",f"{install_type} -> removing [{d_f}]"])
                        try:
                            if path.isdir(d_f):
                                shutil.rmtree(d_f)
                            else:
                                remove(d_f)
                        except Exception as e:
                            log_list.append(["warn",f"{install_type} -> did not remove [{d_f}] reason [{e}] trying th"])
                sleep(1)
            functions.status_dots = False  

        if not install and not quiet:
            print_status(functions,command,False)
        
    # remove auto_complete element
    try:
        remove("/etc/bash_completion.d/nodectl_auto_complete.sh")
    except:
        log_list.append(["warn",f"{install_type} -> did not find any existing auto_complete file on system, skipping."])
    else:
        log_list.append(["info",f"{install_type} -> removed auto_complete configuration [/etc/bash_completion.d/nodectl_auto_complete.sh]"])

    if retain_log:
        if not path.exists("/var/tessellation/nodectl/"):
            makedirs("/var/tessellation/nodectl")
        shutil.copy2("/var/tmp/nodectl.log","/var/tessellation/nodectl/nodectl.log")

    for log_item in log_list:
        if log_item[0] == "info": log.logger["main"].info(log_item[1])
        if log_item[0] == "warn": log.logger["main"].warning(log_item[1])

    if not install:
        return node_admins # for remove_admins function


def restore_user_access(cli,functions,log):
    log.logger["main"].info("uninstaller -> attempting to restore originally user access.")
    restore_users = []
    found_error = False
    
    for user in ["admin","ubuntu","root"]:
        exists = functions.process_command({
            "bashCommand": f"sudo id {user}",
            "proc_action": "subprocess_run_pipe",
        })
        if exists:
            restore_users.append(user)
    if len(restore_users) > 0:
        log.logger["main"].info(f"uninstaller -> restoring [{restore_users}]")
        for user in restore_users:
                skip_reload = False if user == restore_users[-1] else True
                command = f"Restoring {user} SSH access"
                print_status(functions,command,True)
                if not skip_reload: print("") # sshd will reload with message
                result = cli.ssh_configure({
                    "command": "enable_root_ssh",
                    "user": user,
                    "do_confirm": False,
                    "argv_list": ["uninstall"],
                    "skip_reload_status": skip_reload
                })
                
                if result: 
                    log.logger["main"].error(f"uninstaller -> restoring [{restore_users}] result [{result}]")
                    found_error = True
                    result = result.split(" ")[0]
                print_status(functions,command,False,False,result)

    if found_error:
        functions.print_paragraphs([
            ["",1],["The",0], ["'auth_not_found'",0,"red","bold"], ["message encountered while attempting to restore the user's SSH authorization file",0],
            ["can be safely ignored.",0,"green"], ["This message indicates that nodectl's custom backup authorization file was not located on this device.",2],
            [" HOWEVER ",0,"blue,on_yellow"], ["It is recommended to try accessing your VPS from your local system before closing this terminal session.",0,"yellow"],
            ["This step ensures that access to your VPS is not interrupted.",2,"yellow"],
        ])


def remove_admins(functions,node_admins,log,install=False):
    install_type = "uninstaller"
    if install: install_type = "installer"
    log.logger["main"].info(f"{install_type} -> handling removal of nodectl node admin roles. admins {node_admins}")
    # remove nodeadmin
    if environ.get('SUDO_USER',None) in node_admins:
        node_admins = [user for user in node_admins if user != environ.get('SUDO_USER',None)] # remove admin from list
        if not install:
            functions.print_paragraphs([
                ["",1],[" WARNING ",0,"yellow,on_red"], ["nodectl has determined that you are running this script as",0,"red"],
                [f'{functions.config_obj["global_p12"]["nodeadmin"]}',0,"yellow"], ["user. This special user account was creating during the initiate installation of nodectl on this VPS.",0,"red"],
                ["nodectl cannot remove this user, because that user is in use.  You will need to manually remove this user if required.",2,"red"],
            ])
    if len(node_admins) > 0:
        with ThreadPoolExecutor() as executor:
            functions.status_dots = True
            node_admins = [adm for adm in node_admins if adm != "logger_retention"]
            for node_admin in node_admins:
                command = f"Removing Admin {node_admin}"
                if not install:
                    _ = executor.submit(print_status,functions,command,True,True)  
                result = functions.process_command({
                    "bashCommand": f"sudo userdel {node_admin}",
                    "proc_action": "subprocess_run_pipe", 
                })      
                if not result:
                    log.logger["main"].warning(f"{install_type} -> unable to remove [{node_admin}] user, please review server structure and perform manual removal if necessary.")
                    if not install:
                        try:
                            if node_admin.lower() == "blank":
                                functions.print_paragraphs([
                                    [" WARNING ",0,"yellow,on_red"], ["unable to determine",0,"red"],
                                    ["nodeadmin user",0,"yellow","bold"], ["name. Please manually remove",0,"red"],
                                    [f"the nodeadmin user from this system",2,"red"],
                                ])  
                            else:                              
                                functions.print_paragraphs([
                                    [" WARNING ",0,"yellow,on_red"], ["unable to remove",0,"red"],
                                    [node_admin,0,"yellow","bold"], ["user. Please manually remove",0,"red"],
                                    [f"{node_admin} from this system",2,"red"],
                                ])
                        except:
                            pass
                else:
                    shutil.rmtree(f"/home/{node_admin}/")
                functions.status_dots = False    


def finish_uninstall(functions):
    # refresh systemctl daemon to forget about the nodectl services
    _ = functions.process_command({
        "bashCommand": "sudo systemctl daemon-reload",
        "proc_action": "subprocess_devnull",
    })

    functions.print_paragraphs([
        ["",1], 
        ["If nodectl created a swap file during initial installation, the swap file was not removed to prevent potential conflicts",0,"magenta"],
        ["with other [possible] elements, or impacting performance on this VPS. This includes the 'swappiness' settings.",2,"magenta"],

        ["nodectl has",0,"green"], ["successfully",0,"green","bold"],
        ["removed the node components from the system.",2,"green"],

        ["Thank you for your participation with Constellation Network. We hope to see you back soon!",2,"blue","bold"],
        
        ["Executing final removal of the",0],["nodectl",0,"yellow"], ["binary.",1],
    ])


def stop_services(functions, node_service,log):
    log.logger["main"].info("uninstaller -> leaving and stopping any active services gracefully.")
    
    def process_profile(profile):
        node_service.leave_cluster({
            "cli_flag": True,
            "profile": profile,
            "threaded": True,
        })
        node_service.change_service_state({
            "action": "stop",
            "service_name": functions.config_obj[profile]["service"],
            "caller": "uninstaller",
            "profile": profile,
        })

    for cmd in [
        ("disable node_version_updater.service","versioning"),
        ("disable node_restart@.service","auto_restart"),
        ("disable node_restart.service",None),
        ("stop node_version_updater.service","versioning"),
        ("stop node_restart@.service","auto_restart"),
        ("stop node_restart.service",None),
    ]:
        status = "complete"
        color = "green"
        try:
            _ = functions.process_command({
                "bashCommand": f"sudo systemctl {cmd[0]}",
                "proc_action": "subprocess_return_code",
            })
        except:
            status = "incomplete"
            color = "magenta"
            log.logger["main"].warning(f"uninstaller -> may have been an issue stopping and disabling the {cmd[1]} service.")
        if cmd[1] is not None:
            action = "Stopping"
            if "disable" in cmd[0]:
                action = "Disabling"
            functions.print_cmd_status({
                "text_start": f"{action} {cmd[1]} service",
                "status": status,
                "status_color": color,
                "newline": True,
            })

    with ThreadPoolExecutor() as executor:
        futures = [executor.submit(process_profile, profile) for profile in functions.profile_names]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"An error occurred: {e}")


def remove_nodectl(node_service):
    removal_script = node_service.create_files({
        "file": "uninstall_nodectl",
    })
    removal_script_loc = "/var/tmp/uninstall-nodectl"
    with open(removal_script_loc,'w') as file:
        file.write(removal_script)
    file.close
    chmod(removal_script_loc,0o755)
    _ = node_service.functions.process_command({
        "bashCommand": f"sudo {removal_script_loc}",
        "proc_action": "subprocess_run_check_only",
    })
    sleep(.8)
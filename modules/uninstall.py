
import shutil
from os import makedirs, system, path, environ, walk, remove

from time import sleep
from termcolor import colored
from concurrent.futures import ThreadPoolExecutor, as_completed


def start_uninstall(functions,log):
    system("clear")
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
        ["   - All p12 files",1],
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
        ["nodectl will not remove SSH keys and non-specific Constellation applications, these will need to be done manually.",1,"red"],
        ["This execution cannot be undone.",2,"yellow","bold"],

        ["Must type",0], ["CONSTELLATION",0,"yellow","bold"], ["exactly to confirm or",0], 
        ["n",0,"yellow"], ["to cancel this uninstall execution.",1],
    ])

    _ = functions.confirm_action({
        "yes_no_default": "n",
        "return_on": "CONSTELLATION",
        "strict": True,
        "prompt_color": "red",
        "prompt": "Uninstall this Constellation Network Node?", 
        "exit_if": True
    })

    log.logger.info("uninstaller initialized --> beginning nodectl removal")
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


def remove_data(functions,log,install=False):
    install_type = "uninstaller"
    if install: install_type = "installer"
    log.logger.info(f"{install_type} -> removing Node data")

    # first element is the title
    d_dirs = ["data","/var/tessellation"]
    services = ["services","node_version_updater.service","node_version_updater@.service","node_restart@.service"]
    p12s = ["key stores"]
    seedlists = ["seed lists"]

    try:
        node_admins = [functions.config_obj["global_p12"]["nodeadmin"]]
    except:
        log.logger.warn(f"{install_type} -> did not find any existing Node admins")

    if install:
        retain = True
    else:
        retain = functions.confirm_action({
            "yes_no_default": "n",
            "return_on": "y",
            "strict": True,
            "prompt_color": "cyan",
            "prompt": "Would you like to retain the nodectl log file?", 
            "exit_if": False
        })
    if retain:
        log.logger.info("retaining nodectl.log in /var/tmp/ as [nodectl.log]")
        if not install:
            functions.print_paragraphs([
                ["nodectl logs will be located in the here:",1],
                ["location:",0], ["/var/tmp/nodectl.log",1,"yellow"],
            ])
        shutil.copy2("/var/tessellation/nodectl/nodectl.log", "/var/tmp/nodectl.log")
        if not install:
            node_admins.insert(0, "logger_retention")

    if install:  # installer will just use the default dirs, services lists
        print(colored("  Handling removal of existing Node data","cyan"),end="\r")
        if path.isdir("/home/nodeadmin"):
            log.logger.warn(f"{install_type} -> found nodeadmin user, removing... ")
            remove_admins(functions,["nodeadmin"],log,True)
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

    for sdir in ["/etc","/root","/home","/tmp","/var/tmp"]:
        for root, _, ftypes in walk(sdir):
            for ftype in ftypes:
                if ftype.startswith("cnng") and ftype not in services:
                    services.append(path.join(root, ftype))
                elif ftype.endswith(".p12") and ftype not in p12s:
                    p12s.append(path.join(root, ftype))

    remove_lists = [d_dirs,services,seedlists]
    if not install: remove_lists.append(p12s) # keep p12s for migration purposes

    if install:  # installer will just use the default dirs, services lists
        functions.print_cmd_status({
            "text_start": "Removing existing Node Data",
            "status": "please wait",
            "status_color": "yellow",
            "newline": False,
        })
    for remove_list in remove_lists:
        command = f"Removing Node related data"
        log_list = []
        if install: # redraw install of blank screen
            functions.print_cmd_status({
                "text_start": "Removing existing Node Data",
                "status": "please wait",
                "status_color": "yellow",
                "newline": False,
            })
        else:
            command = f"Removing Node related {remove_list.pop(0)}"
            print_status(functions,command,True,True)
        for d_f in remove_list:
            if len(remove_list) > 0:
                for d_f in remove_list:
                    if not d_f.startswith("/"): d_f = f"/etc/systemd/system/{d_f}"
                    try:
                        if path.isdir(d_f):
                            shutil.rmtree(d_f)
                        else:
                            remove(d_f)
                    except Exception as e:
                        log_list.append(f"{install_type} -> did not remove [{d_f}] reason [{e}] trying th")
                    # system(f"sudo rm -rf {d_f} > /dev/null 2>&1")

            sleep(1)

        if not install:
            print_status(functions,command,False)
        
    # remove auto_complete element
    try:
        remove("/etc/bash_completion.d/nodectl_auto_complete.sh")
    except:
        log.logger.warn(f"{install_type} -> did not find any existing auto_complete file on system, skipping.")
    else:
        log.logger.warn(f"{install_type} -> removed auto_complete configuration [/etc/bash_completion.d/nodectl_auto_complete.sh]")

    if retain:
        if not path.exists("/var/tessellation/nodectl/"):
            makedirs("/var/tessellation/nodectl")
        shutil.copy2("/var/tmp/nodectl.log","/var/tessellation/nodectl/nodectl.log")

    for log_item in log_list:
        log.logger.warn(log_item)

    if not install:
        return node_admins # for remove_admins function


def restore_user_access(cli,functions,log):
    log.logger.info("uninstaller -> attempting to restore originally user access.")
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
        log.logger.info(f"uninstaller -> restoring [{restore_users}]")
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
                    log.logger.error(f"uninstaller -> restoring [{restore_users}] result [{result}]")
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
    log.logger.info(f"{install_type} -> handling removal of nodectl Node Admin roles. admins {node_admins}")
    # remove nodeadmin
    if environ.get('SUDO_USER',None) in node_admins:
        node_admins = [user for user in node_admins if user != environ.get('SUDO_USER',None)] # remove admin from list
        if not install:
            functions.print_paragraphs([
                ["",1],[" WARNING ",0,"yellow,on_red"], ["nodectl has determined that you are running this script as",0,"red"],
                ["nodeadmin",0,"yellow"], ["user. This special user account was creating during the initiate installation of nodectl on this VPS.",0,"red"],
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
                    log.logger.warn(f"{install_type} -> unable to remove [{node_admin}] user, please review server structure and perform manual removal if necessary.")
                    if not install:
                        functions.print_paragraphs([
                            [" WARNING ",0,"yellow,on_red"], ["unable to remove",0,"red"],
                            [node_admin,0,"yellow","bold"], ["user. Please manually remove",0,"red"],
                            [f"{node_admin} from this system",2,"red"],
                        ])
                else:
                    shutil.rmtree(f"/home/{node_admin}/")
                functions.status_dots = False    


def finish_uninstall(functions):
    # refresh systemctl daemon to forget about the nodectl services
    system("sudo systemctl daemon-reload > /dev/null 2>&1")

    functions.print_paragraphs([
        ["",1], ["nodectl has",0,"green"], ["successfully",0,"green","bold"],
        ["removed the Node components from the system.",2,"green"],
        ["Thank you for your participation with Constellation Network. We hope to see you back soon!",2,"blue","bold"],
        ["Executing final removal of the",0],["nodectl",0,"yellow"], ["binary.",1],
    ])


def stop_services(functions, node_service,log):
    log.logger.info("uninstaller -> leaving and stopping any active services gracefully.")
    
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

    status = "complete"
    color = "green"
    try:
        system("sudo systemctl disable node_version_updater.service > /dev/null 2>&1")
        system("sudo systemctl disable node_restart@.service > /dev/null 2>&1")
        system("sudo systemctl stop node_version_updater.service > /dev/null 2>&1")
    except:
        status = "incomplete"
        color = "magenta"
        log.logger.warn("uninstaller -> may have been an issue stopping and disabling the auto_restart or upgrader service.")
    functions.print_cmd_status({
        "text_start": "Stopping updater service",
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
    system(f"sudo chmod +x {removal_script_loc}")
    system(f"sudo {removal_script_loc}")
    sleep(.8)
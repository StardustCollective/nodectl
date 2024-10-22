import subprocess
import os
import sys

def handle_ipv6(action, log, functions, argv_list):
    log.logger.info(f"handle_ipv6 -> modify [/etc/sysctl.conf] to disable IPv6.")
    need_reboot = False
    sysctl_conf = '/etc/sysctl.conf'
    grub_conf = '/etc/default/grub'

    verb = "Enablement" if action == "enable" else "Disablement"
    if action == "status": verb = "Status"
    non_interactive = True if "--ni" in argv_list or "-ni" in argv_list else False

    functions.print_header_title({
        "line1": f"IPv6 {verb}",
        "single_line": True,
        "newline": "both"
    })

    if not non_interactive and action != "status":
        functions.print_paragraphs([
            ["This request will allow nodectl to",0,"yellow"],
            [action,0,"red","bold"], ["IPv6 on this VPS.",1,"yellow"],
        ])
        functions.confirm_action({
                "yes_no_default": "y",
                "return_on": "y",
                "prompt": f"Attempt to {action} IPv6?",
                "prompt_color": "cyan",
                "exit_if": True,
        })

    update_type = "none"
    if action == "status":
        pass
    elif  "--grub" in argv_list:
        update_type = "grub"
    elif "--sysctl" in argv_list:
        update_type = "sysctl"
    elif "--all" in argv_list:
        update_type = "all"
    else:
        update_type = get_update_type(action, functions)

    interface = get_interface(functions)

    functions.print_cmd_status({
        "text_start": "Interface found",
        "status": interface,
        "status_color": "yellow",
        "newline": True,
    })

    content, grub_content = read_configs(log,sysctl_conf,grub_conf)

    if update_type == "all" or update_type == "sysctl":
        execute_sysctl(interface,action,sysctl_conf,content,functions,log)

    if update_type == "all" or update_type == "grub":
        need_reboot = execute_grub(action,grub_conf,grub_content,functions,log)

    content, grub_content = read_configs(log,sysctl_conf,grub_conf)

    handle_status(grub_content,content,functions)
    reboot_request(functions,need_reboot)


def read_configs(log,sysctl_conf,grub_conf):
    log.logger.info("handle_ipv6 -> checking if IPv6 settings present in sysctl.conf")
    with open(sysctl_conf, 'r') as f:
        content = f.read()

    log.logger.info("handle_ipv6 -> checking if IPv6 settings present in GRUB config")
    with open(grub_conf, 'r') as f:
        grub_content = f.read()

    return content, grub_content


def get_interface(functions):
    interface = False
    result = subprocess.run(['ip', 'route'], capture_output=True, text=True, check=True)
    for line in result.stdout.splitlines():
        if line.startswith('default'):
            # The interface name is typically the 5th word in the 'default' line
            interface = line.split()[4]
    if not interface:
        functions.print_paragraphs([
            ["Unable to determine proper network interface, operation cancelled by nodectl.",1,"red"]
        ])
        sys.exit(0)
    
    return interface


def get_update_type(action, functions):
    functions.print_paragraphs([
        ["",1],["Update Method Option Not Found:",1,"blue","bold"],
    ])

    options = ["grub","sysctl","both","quit"]
    if action == "disable": 
        options = ["grub (caution)","sysctl (recommended)","both (caution)","quit"]

    update_type = functions.print_option_menu({
        "options": options,
        "let_or_num": "let",
        "return_value": True,
    })
    update_type = update_type.replace("(caution)","").replace("(recommended)","").strip()

    if update_type == "quit":
        functions.print_paragraphs([
            ["Operation cancelled by user.",1,"red"]
        ])
        sys.exit(0)

    return update_type


def handle_status(grub_content,content,functions):
    print()
    g_status = "enabled" if 'ipv6.disable=1' not in grub_content else "disabled"
    s_status = "enabled" if "disable_ipv6" not in content else "disabled"
    print_out_list = [
        {
            "header_elements" : {
                "IPv6 systctl Status": s_status,
                "IPv6 Grub Status": g_status,
            },
        },
    ]
    for header_elements in print_out_list:
        functions.print_show_output({
            "header_elements" : header_elements
    })
    print("")
    sys.exit(0)

    
def execute_sysctl(interface,action,sysctl_conf,content,functions,log):
    apply = True

    ipv6_settings = f'''# Disable IPv6
sudo ip -6 addr flush dev {interface}
sudo ip -6 route flush dev {interface}
sudo sysctl net.ipv6.conf.{interface}.disable_ipv6=1
'''

    ipv6_obj = {
        "text_start": "Handling IPv6 sysctl Config",
        "status": "running",
        "status_color": "yellow",
        "delay": 0.8,
        "newline": False,        
    }
    functions.print_cmd_status(ipv6_obj)

    if action == "disable" and 'disable_ipv6' not in content:
        log.logger.info("handle_ipv6 -> Appending IPv6 disable settings to [sysctl.conf]")
        with open(sysctl_conf, 'a') as f:
            f.write(ipv6_settings)
        ipv6_obj["status"] = "Updating"
    elif action == "enable" and "disable_ipv6" in content:
        content = content.replace(ipv6_settings,"")
        with open(sysctl_conf, 'w') as f:
            f.write(content)
        ipv6_obj["status"] = "Updating"
    else:
        log.logger.warning("handle_ipv6 -> Not updating IPv6 disable settings to sysctl.conf because the configuration is already in place.")
        ipv6_obj["status"] = "NotNeeded"
        ipv6_obj["status_color"] = "green"
        ipv6_obj["newline"] = True
        apply = False

        functions.print_cmd_status(ipv6_obj)

    if apply:
        need_reboot = True
        log.logger.info("handle_ipv6 -> Apply IPv6 in sysctl changes.") 
        subprocess.run(['sudo', 'sysctl', '-p'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ipv6_obj["status"] = "Completed"
        ipv6_obj["status_color"] = "green"
        ipv6_obj["newline"] = True
        functions.print_cmd_status(ipv6_obj)


def execute_grub(action,grub_conf, grub_content,functions,log):
    need_reboot, apply = True, True 
    ipv6_obj = {
        "text_start": "Handling IPv6 GRUB",
        "status": "running",
        "status_color": "yellow",
        "delay": 0.8,
        "newline": False,        
    }

    functions.print_cmd_status(ipv6_obj)
    log.logger.info("handle_ipv6 -> Update GRUB to disable IPv6 at the kernel level.")
    ipv6_obj["newline"] = True

    if action == "disable" and 'ipv6.disable=1' not in grub_content:
        log.logger.info("handle_ipv6 -> Modify GRUB to disable IPv6.")
        new_grub_content = grub_content.replace(
            'GRUB_CMDLINE_LINUX_DEFAULT="',
            'GRUB_CMDLINE_LINUX_DEFAULT="ipv6.disable=1 '
        )

        log.logger.info("handle_ipv6 -> Applying GRUB config.")
        with open(grub_conf, 'w') as f:
            f.write(new_grub_content)
    elif action == "enable" and 'ipv6.disable=1' in grub_content:
        log.logger.info("handle_ipv6 -> Modify GRUB to disable IPv6.")
        new_grub_content = grub_content.replace(
            "ipv6.disable=1 c", "c"
        )
        log.logger.info("handle_ipv6 -> Applying GRUB config.")
        with open(grub_conf, 'w') as f:
            f.write(new_grub_content)
    else:
        log.logger.warning("handle_ipv6 -> Not necessary to modify GRUB; IPv6 already disabled.")
        ipv6_obj["status"] = "NotNeeded"
        ipv6_obj["status_color"] = "green"
        apply = False
        need_reboot = False

    if apply:
        # Update GRUB configuration for Debian or Ubuntu
        grub_update_cmd = 'update-grub' if os.path.exists('/usr/sbin/update-grub') else 'grub-mkconfig -o /boot/grub/grub.cfg'
        subprocess.run(['sudo', grub_update_cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log.logger.info("handle_ipv6 -> GRUB updated to disable IPv6 at boot level.")
        ipv6_obj["status"] = "Completed"
        ipv6_obj["status_color"] = "green"

    functions.print_cmd_status(ipv6_obj)
    return need_reboot


def reboot_request(functions, need_reboot):
    if need_reboot:
        functions.print_paragraphs([
            ["",1],[" IMPORTANT ",0,"yellow,on_blue"], 
            ["nodectl determined that VPS distribution level modifications may not have been applied yet. A",0,"blue","bold"],
            ["reboot",0,"red","bold"],["is necessary.",1,"blue","bold"],
            ["Recommended:",0], ["sudo nodectl reboot",2,"magenta"],
        ])


if __name__ == "__main__":
    print("This module is not designed to be run independently, please refer to the documentation")  
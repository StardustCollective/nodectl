import subprocess
import os
import sys

def handle_ipv6(action, log, functions, non_interactive):
    log.logger.info(f"handle_ipv6 -> modify [/etc/sysctl.conf] to disable IPv6.")
    need_reboot, apply = False, True

    verb = "Enablement" if action == "enable" else "Disablement"
    if action == "status": verb = "Status"

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
        
    sysctl_conf = '/etc/sysctl.conf'
    ipv6_settings = '''# Disable IPv6
net.ipv6.conf.all.disable_ipv6 = 1
net.ipv6.conf.default.disable_ipv6 = 1
net.ipv6.conf.lo.disable_ipv6 = 1
'''

    ipv6_obj = {
        "text_start": "Handling IPv6 Configuration",
        "status": "running",
        "status_color": "yellow",
        "delay": 0.8,
        "newline": False,        
    }
    functions.print_cmd_status(ipv6_obj)

    log.logger.info("handle_ipv6 -> checking if IPv6 settings are already present in sysctl.conf")
    with open(sysctl_conf, 'r') as f:
        content = f.read()

    if action != "status":
        if action == "disable" and 'disable_ipv6' not in content:
            need_reboot = True
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

    grub_conf = '/etc/default/grub'
    with open(grub_conf, 'r') as f:
        grub_content = f.read()

    apply = True # reset 

    if action == "status":
        print("\n")
        status = "enabled" if 'ipv6.disable=1' not in grub_content else "disabled"
        print_out_list = [
            {
                "header_elements" : {
                    "IPv6 Status": status
                },
            },
        ]
        for header_elements in print_out_list:
            functions.print_show_output({
                "header_elements" : header_elements
        })
        print("")
        sys.exit(0)

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

    if apply:
        # Update GRUB configuration for Debian or Ubuntu
        grub_update_cmd = 'update-grub' if os.path.exists('/usr/sbin/update-grub') else 'grub-mkconfig -o /boot/grub/grub.cfg'
        subprocess.run(['sudo', grub_update_cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log.logger.info("handle_ipv6 -> GRUB updated to disable IPv6 at boot level.")
        ipv6_obj["status"] = "Completed"
        ipv6_obj["status_color"] = "green"

    functions.print_cmd_status(ipv6_obj)
    reboot_request(functions,need_reboot)


def reboot_request(functions, need_reboot):
    if need_reboot:
        functions.print_paragraphs([
            ["",1],[" IMPORTANT ",0,"yellow,on_blue"], 
            ["nodectl determined that VPS distribution level modifications may not have been applied yet. A",0,"blue","bold"],
            ["reboot",0,"red","bold"],["is necessary.",1,"blue","bold"],
            ["Recommended:",0], ["sudo nodectl reboot",2,"magenta"],
        ])
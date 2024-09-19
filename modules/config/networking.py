import subprocess
import os

def disable_ipv6(log, functions, non_interactive, quick_install):
    log.logger.info(f"disable_ipv6 -> modify [/etc/sysctl.conf] to disable IPv6.")
    need_reboot = False
    if quick_install: non_interactive = True

    if not quick_install:
        functions.print_header_title({
            "line1": "IPv6 Disablement",
            "single_line": True,
            "newline": "both"
        })

    if not non_interactive:
        functions.print_paragraphs([
            ["Tessellation may not properly work with a node that has",0], ["IPv6",0,"yellow"],
            ["enabled.  This may cause an issue with",0],["advanced",0,"green","bold"], 
            ["Node Administrators.",2],

            ["This VPS should being used exclusively for Constellation Network Node Operations.",0,"magenta"],
            ["Unless you are an advanced Administrator, you should say",0,"magenta"], ["y",0,"green","bold"], 
            ["to this request and allow nodectl to complete the IPv6 disablement.",1,"magenta"],
        ])
        if functions.confirm_action({
                            "yes_no_default": "y",
                            "return_on": "n",
                            "prompt": "Attempt to disable IPv6?",
                            "prompt_color": "cyan",
                            "exit_if": False,
                        }):
            functions.print_paragraphs([
                ["Skipping IPv6 configuration modification",1,"red"],
            ])
            return
        
    sysctl_conf = '/etc/sysctl.conf'
    ipv6_settings = '''
# Disable IPv6
net.ipv6.conf.all.disable_ipv6 = 1
net.ipv6.conf.default.disable_ipv6 = 1
net.ipv6.conf.lo.disable_ipv6 = 1
'''

    if not quick_install: print("")
    ipv6_obj = {
        "text_start": "Handling IPv6 Configuration",
        "status": "running",
        "status_color": "yellow",
        "delay": 0.8,
        "newline": False,        
    }
    if not quick_install:
        functions.print_cmd_status(ipv6_obj)

    log.logger.info("disable_ipv6 -> checking if IPv6 settings are already present in sysctl.conf")
    with open(sysctl_conf, 'r') as f:
        content = f.read()

    if 'disable_ipv6' not in content:
        need_reboot = True
        log.logger.info("disable_ipv6 -> Appending IPv6 disable settings to sysctl.conf")
        with open(sysctl_conf, 'a') as f:
            f.write(ipv6_settings)
        ipv6_obj["status"] = "Updating"
    else:
        log.logger.warning("disable_ipv6 -> Not appending IPv6 disable settings to sysctl.conf because the configuration is already in place.")
        ipv6_obj["status"] = "NotNeeded"
        ipv6_obj["status_color"] = "green"
        ipv6_obj["newline"] = True

    if not quick_install:
        functions.print_cmd_status(ipv6_obj)

    if 'disable_ipv6' not in content:
        need_reboot = True
        log.logger.info("disable_ipv6 -> Apply IPv6 in sysctl changes.") 
        subprocess.run(['sudo', 'sysctl', '-p'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ipv6_obj["status"] = "Completed"
        ipv6_obj["status_color"] = "green"
        ipv6_obj["newline"] = True
        if not quick_install:
            functions.print_cmd_status(ipv6_obj)

    ipv6_obj = {
        "text_start": "Handling IPv6 GRUB",
        "status": "running",
        "status_color": "yellow",
        "delay": 0.8,
        "newline": False,        
    }

    if not quick_install:
        functions.print_cmd_status(ipv6_obj)
    log.logger.info("disable_ipv6 -> Update GRUB to disable IPv6 at the kernel level.")
    ipv6_obj["newline"] = True

    grub_conf = '/etc/default/grub'
    with open(grub_conf, 'r') as f:
        grub_content = f.read()

    if 'ipv6.disable=1' not in grub_content:
        log.logger.info("disable_ipv6 -> Modify GRUB to disable IPv6.")
        new_grub_content = grub_content.replace(
            'GRUB_CMDLINE_LINUX_DEFAULT="',
            'GRUB_CMDLINE_LINUX_DEFAULT="ipv6.disable=1 '
        )

        log.logger.info("disable_ipv6 -> Applying GRUB config.")
        with open(grub_conf, 'w') as f:
            f.write(new_grub_content)

        # Update GRUB configuration for Debian or Ubuntu
        grub_update_cmd = 'update-grub' if os.path.exists('/usr/sbin/update-grub') else 'grub-mkconfig -o /boot/grub/grub.cfg'
        subprocess.run(['sudo', grub_update_cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log.logger.info("disable_ipv6 -> GRUB updated to disable IPv6 at boot level.")
        ipv6_obj["status"] = "Completed"
        ipv6_obj["status_color"] = "green"
    else:
        log.logger.warning("disable_ipv6 -> Not necessary to modify GRUB; IPv6 already disabled.")
        ipv6_obj["status"] = "NotNeeded"
        ipv6_obj["status_color"] = "green"

    if not quick_install:
        functions.print_cmd_status(ipv6_obj)

    return need_reboot
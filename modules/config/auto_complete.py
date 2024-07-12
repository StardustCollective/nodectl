import re
import base58
import psutil

from hashlib import sha256

from time import sleep, perf_counter
from datetime import datetime, timedelta
from os import system, path, get_terminal_size, remove, walk, chmod, stat, makedirs, SEEK_END, SEEK_CUR
from sys import exit
from types import SimpleNamespace
from getpass import getpass
from termcolor import colored, cprint
from secrets import compare_digest

from .valid_commands import pull_valid_command


def ac_validate_path(log,action):
    auto_path = "/etc/bash_completion.d/nodectl_auto_complete.sh"
    if not path.exists(path.split(auto_path)[0]):
        log.logger.error(f"{action} -> unable to determine auto complete BASH 4 path?  Are you sure bash is installed?")
        makedirs("/etc/bash_completion.d/")
    return auto_path


def ac_build_script(cli,auto_path):
    auto_complete_file = cli.node_service.create_files({
        "file": "auto_complete",
    })
    valid_commands = pull_valid_command()
    valid_commands = ' '.join(cmd for sub_cmd in valid_commands for cmd in sub_cmd if not cmd.startswith("_"))

    install_options = "--normal --quick-install --user --p12-destination-path --user-password " # make sure ends with a space
    install_options += "--p12-passphrase --p12-migration-path --p12-alias --cluster-config --confirm --quiet" 
    
    upgrade_options = "--ni --nodectl_only --pass -v -f"

    viewconfig_options = "--passphrase --jar --custom --seed --priority --java --directory "
    viewconfig_options += "--token --link --edge --basics --ports --tcp --pro --json --section"

    displaychain_options = "-p --np --json_output --full_report --days, --json_output"

    find_options = "-s -t"
    auto_complete_file = auto_complete_file.replace("nodegaragelocalcommands",valid_commands)
    auto_complete_file = auto_complete_file.replace("nodegarageinstalloptions",install_options)
    auto_complete_file = auto_complete_file.replace("nodegarageupgradeoptions",upgrade_options)
    auto_complete_file = auto_complete_file.replace("nodegarageviewconfigoptions",viewconfig_options)
    auto_complete_file = auto_complete_file.replace("nodegaragedisplaychainoptions",displaychain_options)
    auto_complete_file = auto_complete_file.replace("nodegaragefindoptions",find_options)
    auto_complete_file = auto_complete_file.replace('\\n', '\n')    

    return auto_complete_file


def ac_write_file(auto_path,auto_complete_file,functions):
    with open(auto_path,"w") as auto_complete:
        auto_complete.write(auto_complete_file)

    chmod(auto_path,0o644)
    username = functions.config_obj['global_p12']['nodeadmin']
    _ = functions.process_command({
        "bashCommand": f"sudo -u {username} -i bash -c '. /etc/bash_completion'",
        "proc_action": "subprocess_devnull",
    })
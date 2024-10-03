from time import sleep, perf_counter
from datetime import datetime, timedelta
from os import system, path, get_terminal_size, popen, remove, chmod, makedirs, walk, SEEK_END, SEEK_CUR
from shutil import copy2, move
from sys import exit, setrecursionlimit
from types import SimpleNamespace
from getpass import getpass
from termcolor import colored, cprint
from secrets import compare_digest
from copy import deepcopy
from scapy.all import sniff
from concurrent.futures import ThreadPoolExecutor, wait as thread_wait
from .troubleshoot.logger import Logging

class Menu():
    def __init__(self,command_obj) -> None:
        self.log = Logging()
        self.config_obj = command_obj["config_obj"]
        self.profile_names = command_obj["profile_names"]
        self.functions = command_obj["functions"]

        self.main_options = []
        self.main_options_bl = []
        self.main_options_l0 = []
        self.main_options_env_bl = []
        self.main_options_env_l0 = []
        self.main_options_skip = []

        self.argv = []
        for _ in range(0,7):
            self.argv.append("empty")


    def per_profile(self,cmd,i_options,layer0):
        for profile in self.profile_names:
            if layer0 and self.config_obj[profile]["layer"] > 0:
                continue
            i_options.append(f"{cmd} -p {profile}")
        return i_options


    def per_environment(self,cmd,i_options,layer0):
        for profile in self.profile_names:
            if layer0 and self.config_obj[profile]["layer"] > 0:
                continue
            i_options.append(f"{cmd} -e {self.config_obj[profile]['environment']}")
        return i_options


    def create_menu(self):
        options = []
        for cmd in self.main_options:
            if cmd in self.main_options_bl:
                options = self.per_profile(cmd,options,False)
            elif cmd in self.main_options_l0:
                options = self.per_profile(cmd,options,True)
            
            if cmd in self.main_options_env_bl:
                options = self.per_environment(cmd,options,False)
            elif cmd in self.main_options_env_l0:
                options = self.per_environment(cmd,options,True)
            elif cmd in self.main_options_skip: 
                continue
            else:
                options.append(cmd)

        return options


    def build_root_menu(self):
        while True:
            self.functions.print_header_title({
                "line1": "CONSOLE MENU",
                "single_line": True,
                "newline": "both",
            })

            self.main_options = [
                "status -p all",
                "status",
                "check_consensus",
                "blank_spacer",
                "restart -p all",
                "restart",
                "blank_spacer",
                "upgrade --ni",
                "upgrade_nodectl",
                "blank_spacer",
                "verify_nodectl",
                "revision",
                "upgrade_vps --ni",
                "blank_spacer",
                "check_versions",
                "auto_restart restart",
                "list",
                "blank_spacer",
                "GENERAL COMMANDS",
                "TROUBLESHOOT COMMANDS",
            ]
            self.main_options_bl = ["status","restart"] # both layers
            self.main_options_l0 = ["check_consensus"]
            self.main_options_skip = ["status","restart","check_consensus"]

            options = self.create_menu()

            choice = self.handle_choice(options,"q")
            choice = self.build_submenus(choice)
            if (isinstance(choice,tuple) and choice[0] != 'r') or choice == "q":
                break
        return choice


    def build_general_menu(self):
        self.main_options = [
            "reboot",
            "refresh_binaries",
            "blank_spacer",
            "view_config",
            "view_config --basics",
            "view_config --passphrase",
            "view_config --section global_elements",
            "blank_spacer",
            "export_private_key",
            "blank_spacer",
            "price",
            "dag",
        ]
        self.main_options_bl = ["export_private_key","dag"]
        self.main_options_l0 = []
        self.main_options_env_l0 = ["refresh_binaries"]
        self.main_options_skip = ["export_private_key"]


    def build_troubleshoot_menu(self):
        self.main_options = [
            "show_cpu_memory",
            "blank_spacer",
            "peers",
            "blank_spacer",
            "check_connection",
            "blank_spacer",
            "show_profile_issues",
            "blank_spacer",
            "show_dip_error",
            "logs",
        ]
        self.main_options_bl = ["peers","check_connection","show_profile_issues","logs"] # both layers
        self.main_options_l0 = ["show_dip_error"]
        self.main_options_skip = ["peers","check_connection","show_profile_issues","show_dip_error","logs"]


    def build_submenus(self,choice):
        if choice[0] == "GENERAL": 
            self.build_general_menu()
        elif choice[0] == "TROUBLESHOOT": 
            self.build_troubleshoot_menu()
        else:
            return choice

        self.functions.print_header_title({
            "line1": f"{choice[0]} MENU",
            "single_line": True,
            "newline": "both",
        })

        return self.handle_choice(self.create_menu(),"both")
    

    def handle_choice(self, options, r_and_q):
        choice = self.functions.print_option_menu({
                "options": options,
                "return_value": True,
                "let_or_num": "let",
                "prepend_let": True,
                "return_where": "Edit",
                "color": "blue",
                "r_and_q": r_and_q,
                "return_where": "Main"
            })
        
        if choice != "q" and choice != "r": 
            choice = choice.split(" ")
            self.functions.print_paragraphs([
                ["Option Chosen:",0,"yellow"], [choice[1],2],
            ])

            if len(choice) > 1:
                choice_argv = choice[2:]
                for i,argv in enumerate(choice_argv):
                    self.argv[i] = argv

            choice = (choice[1],self.argv)

        return choice
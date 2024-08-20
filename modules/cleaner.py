from time import time
from os import system, path, listdir, stat, remove, SEEK_END, SEEK_CUR
from termcolor import colored, cprint
from hurry.filesize import size, alternative

from .functions import Functions
from .troubleshoot.errors import Error_codes
from .troubleshoot.logger import Logging
from .config.versioning import Versioning

class Cleaner():
    
    def __init__(self,command_obj):
        self.functions = command_obj["functions"]
        self.config_obj = self.functions.config_obj
        del command_obj["functions"]
        self.argv_list = command_obj["argv_list"]
        self.snapshot_called = False
        self.version_obj = self.functions.version_obj
        
        self.log = Logging()
        self.error_messages = Error_codes(self.functions)    
        
        if command_obj["action"] == "snapshots":
            self.clean_snapshots()
        else:
            self.clean_files(command_obj)
    

    def clean_snapshots(self):
        self.functions.print_header_title({
            "line1": "CLEAN SNAPSHOTS",
            "clear": True,
            "newline": "top",
        })
        
        self.functions.print_paragraphs([
            ["  WARNING  ",0,"yellow,on_red","bold"], ["Are you sure your want to execute this command?",2,"red","bold"],
            
            ["This will remove data snapshots and cause your",0], ["Node",0,"yellow","bold"],
            ["to transfer extra data when/if necessary. This will cause an increase in the throughput",0],
            ["I/O",0,"yellow"], ["on the Node.",2],
            
            ["This should be done",0], ["only",0,"yellow","underline"], ["when either completely necessary due to disk space issues",0],
            ["or when specifically requested from an Administrator (or experienced Node Operator) of the Hypergraph or a metagraph.",2],
            
            ["Check system health via:",1],
            ["sudo nodectl health",2,"green"],
            
            ["OPTIONS",1,"magenta","bold"], ["-------",1,"magenta"],
            ["1",0,"magenta","bold"], [")",-1,"magenta"], ["Clean snapshots older than 30 days",1,"magenta"],
            ["2",0,"magenta","bold"], [")",-1,"magenta"], ["Clean all snapshots",1,"magenta"],
            ["Q",0,"magenta","bold"], [")",-1,"magenta"], ["uit",-1,"magenta"], ["",2]
        ])

        options_dict = {"1": 30, "2": 730, "Q": "Q"}
        option = self.functions.get_user_keypress({
            "prompt": "KEY PRESS an option",
            "prompt_color": "cyan",
            "quit_option": "Q",
            "options": list(options_dict.keys())
        })
        
        self.functions.print_paragraphs([
            ["Option:",0], [option,0,"yellow","bold,underline"], ["chosen, exact",0], ["YES",0, "yellow","bold,underline"],
            ["required to continue.",1]
        ])
        confirm = self.functions.confirm_action({
            "yes_no_default": "NO",
            "return_on": "YES",
            "strict": True,
            "prompt_color": "red",
            "prompt": "Are you sure you want to continue?",
            "exit_if": True
        })

        if confirm:
            self.log.logger.info(f"Request to reset snapshot cache requested and confirmed | option [{option}]")
            self.snapshot_called = True
            self.clean_files({
                "action": "snapshots",
                "argv_list": ["-t","snapshots","-d",options_dict.get(option)]
            })                
            cprint("  Request to clear snapshot cache completed","green",attrs=['bold'])


    def clean_files(self,command_obj):
        # upload=(bool)False, 
        # action=(str)[install, config_change, upgrade, snapshot, normal], 
        # argv_list=(list) 
        #    -t, dir_type=(str) [uploads, backups, logs]
        #    --ni (non-interactive)
        # ignore_list(list) list of list in order of directories list,
        
        action = command_obj.get("action")
        argv_list = command_obj.get("argv_list",self.argv_list)
        ignore_list = command_obj.get("ignore_list",[])        

        non_interactive = False
        if "-ni" in argv_list or "--ni" in argv_list:
            non_interactive = True
            
        self.total_file_count = 0
        show_help = False

        if action != "snapshots" and ("-t" not in argv_list or "help" in argv_list):
            show_help = True
            
        try:
            dir_type = argv_list[argv_list.index("-t")+1]
        except:
            show_help = True
            dir_type = None
            
        # do not allow "snapshots" command to be called directly
        if action == "snapshots" and not self.snapshot_called:
            show_help = True
        
        if show_help:       
            self.functions.print_help({
                "extended": "clean_files"
            })
                        
        if action == "normal":
            self.functions.print_header_title({
                "line1": "FILE CLEAN UP REQUEST",
                "line2": dir_type,
                "newline": "top",
                "clear": True,
            })
            self.functions.print_paragraphs([
                ["1",0,"magenta","bold"], [")",-1,"magenta"], ["Clear files Older than 30 days",1,"magenta"],
                ["2",0,"magenta","bold"], [")",-1,"magenta"], ["Clear files Older than 07 days",1,"magenta"],
                ["3",0,"magenta","bold"], [")",-1,"magenta"], ["Clear all files",1,"magenta"],
                ["Q",0,"magenta","bold"], [")",-1,"magenta"], ["uit",-1,"magenta"], ["",2],
            ])
        
        self.log.logger.info(f"clear logs - {dir_type} method invoked")
        skip = False       
        time_check = 0
        now = time()
        
        if action == "snapshots" or (action == "upgrade" and dir_type == "snapshots"):
            dir_type = "snapshots"
            days = argv_list[argv_list.index("-d")+1]
        elif dir_type == "config_change":
            days = 365
        elif action == "upgrade":
            days = argv_list[argv_list.index("-d")+1]
        else:
            options_dict = {"1":30,"2": 7, "3": 730, "Q": "Q"}
            option = self.functions.get_user_keypress({
                "prompt": "KEY PRESS an option",
                "prompt_color": "cyan",
                "quit_option": "Q",
                "options": list(options_dict.keys())
            })
            days = options_dict.get(option,-1)
            
        if days > -1:
            time_check = -1 if days == 730 else now - days * 86400
            
            dirs = self.functions.get_dirs_by_profile({"profile":"all"}) # {"profile": {dirs}}
            skip = self.find_or_replace_files(dir_type,dirs,"find_only",time_check,ignore_list)
            if not skip:
                confirm = "y"
                if not non_interactive:
                    input_text = colored(f"  Are you sure you want to clear the selected {dir_type}? [","magenta")+colored("n","yellow")+colored("]: ","magenta")
                    confirm = input(input_text)
                if confirm.lower() == "y" or confirm.lower() == "yes":
                    self.log.logger.info("user request to clear logs requested and confirmed.")
                    self.find_or_replace_files(dir_type,dirs,"remove",time_check,ignore_list)
                else:
                    self.log.logger.info(f"Request to clear logs skipped by user.")
                    cprint("  Remove action cancelled","green",attrs=['bold'])
        else:
            self.log.logger.info(f"Request to clear logs cancelled by user.")
            cprint("  Remove action cancelled","green",attrs=['bold'])


    def find_or_replace_files(self,dir_type,dirs,action,time_check,ignore_list):
        # action = find_only or remove
        # single = single file ( or directory ) bool
        # time_check = time to check against
        
        calc_size = 0
        verb = ""
        file_list = []
        skip = False
            
        valid_values = ["logs","uploads","backups","snapshots","config_change"]
        if dir_type not in valid_values:
            self.functions.print_help({
                "usage_only": True
            })

        log_path_list = []
        
        if dir_type == "logs":
            dir_type = "directory_logs"
            subdirs = ["directory_archived","directory_json_logs"]
            for profile in dirs.keys():
                for c_dir in subdirs:
                    if path.isdir(dirs[profile][c_dir]):  # make sure all paths exist
                        log_dict = {
                            "layer": self.functions.config_obj[profile]["layer"],
                            "log_path": dirs[profile][c_dir]
                        
                        }
                        log_path_list.append(log_dict)
                    else:
                        self.log.logger.warn(f"during a log cleanup attempt a directory was not found and skipped [{dirs[profile][c_dir]}]")
        elif dir_type == "config_change":
            log_path_list.append({
                "layer": "na",
                "log_path": f"/etc/systemd/system/"
            })              
            log_path_list.append({
                "layer": "na",
                "log_path": f"/usr/local/bin/"
            })   
        else:
            # snapshots, backups, uploads
            dir_type = f"directory_{dir_type}"
            for profile in dirs.keys():
                try: 
                    log_path_list.append({
                        "layer": "na",
                        "log_path": dirs[profile][dir_type]
                    })
                except: # snapshot disabled exception
                    pass
            # remove duplicates
            log_path_list = [dict(t) for t in {tuple(d.items()) for d in log_path_list}]

        file_count = 0
        
        if dir_type == "directory_snapshots" and action == "find_only":
            cprint("  snapshot directories can be large, please wait patiently...","yellow")
        if dir_type == "directory_snapshots" and action != "find_only":
            cprint("  snapshot directories can be large, snapshot removal will take a lot of time","yellow")
            cprint("  please wait patiently...","yellow")
            
        for n, log_dict in enumerate(log_path_list):
            pre_text = "" if len(log_path_list) < 2 or dir_type == "config_change" else f"[layer{log_dict['layer']}]" 
            log_path = log_dict["log_path"] # readability
            try:
                c_ignore_list = ignore_list[n]
            except:
                c_ignore_list = []

            if log_path != "disabled":
                try:
                    for f in listdir(log_path):
                        file = path.join(log_path, f)
                        key_word = "log" if dir_type != "config_change" else "cnng-"
                        all_file_type = ["directory_snapshots","directory_uploads","directory_backups"] # scalability later
                        
                        if time_check == -1 or stat(file).st_mtime < time_check:
                            if key_word in file or dir_type in all_file_type:
                                if f not in c_ignore_list:
                                    single_file = False if path.isdir(file) else True
                                    calc_size += self.functions.get_size(file,single_file)
                                    file_count += 1

                                    if action == "find_only":
                                        verb = " to be"
                                        file_list.append(f'{colored("  remove?","yellow")} {colored(pre_text,"cyan")} {file}')
                                    else:
                                        self.functions.print_clear_line()
                                        if dir_type == "directory_snapshots":
                                            print(
                                                colored(f"  removing [","red"),
                                                file_count,
                                                colored("] of [","red"),
                                                self.total_file_count,
                                                colored("]","red"),
                                                end="\r"
                                            )
                                        else:
                                            print(f'{colored("  removing:","red")} {colored(pre_text,"cyan")} {file}',end="\r")
                                        self.functions.remove_files(file,"find_or_replace_files")

                except:
                    if dir_type == "config_change":
                        self.log.logger.warn("during configuration change unable to find file to replace.")
                        pass
                    else:
                        self.error_messages.error_code_messages({
                            "error_code": "cln-291",
                            "line_code": "upgrade_needed",
                            "extra": "Missing Directories"
                        })
                        
        converted_calc_size = size(calc_size, system=alternative)
        if calc_size == 0 and file_count == 0:
            self.functions.print_cmd_status({
                "text_start": "Skipping clean nothing to remove | file count:",
                "status": "0 files [0B]",
                "status_color": "blue",
                "newline": True
            })
            skip = True
        else:
            self.functions.print_clear_line()
            for p_file in file_list:
                if dir_type != "directory_snapshots" and action == "find_only":
                    print(p_file) 
            self.functions.print_clear_line()
            paragraphs = [
                [f"disk space{verb} recovered:",0,"white","bold"], [converted_calc_size,1,"cyan","bold"],
                [f"file count:",0,"white","bold"], [str(file_count),1,"cyan","bold"],                
            ]
            if verb != " to be":
                paragraphs.insert(0,[" recovery complete ",1,"grey,on_green"])

            self.functions.print_paragraphs(paragraphs)
            self.total_file_count = file_count # snapshots display
        return skip
    
    
if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")        

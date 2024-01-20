import json

from re import match
from os import system, path, mkdir, listdir
from sys import exit
from termcolor import colored, cprint
from hurry.filesize import size, alternative
from concurrent.futures import ThreadPoolExecutor

from time import time, sleep

from ..functions import Functions
from .logger import Logging

class SendLogException(Exception):
    pass

class Send():
    
    def __init__(self,command_obj):
        
        self.log = Logging()
        self.command_list = command_obj["command_list"]
        self.config_obj = command_obj["config_obj"]
        
        self.functions = Functions(self.config_obj)
        self.profile = self.command_list[self.command_list.index("-p")+1]
        self.ip_address = command_obj["ip_address"]

        
    def prepare_and_send_logs(self):
        changed_ip = self.ip_address.replace(".","-")
        date = self.functions.get_date_time({"action":"datetime"})
        
        archive_location = f"/var/tessellation/{self.profile}/logs/archived"
        tar_dest= self.functions.config_obj[self.profile]["directory_uploads"]
        backup_dest = self.functions.config_obj[self.profile]["directory_backups"]
        
        # to avoid issues
        if not path.isdir(self.functions.config_obj[self.profile]["directory_backups"]):
            mkdir(self.functions.config_obj[self.profile]["directory_backups"])
        if not path.isdir(self.functions.config_obj[self.profile]["directory_uploads"]):
            mkdir(self.functions.config_obj[self.profile]["directory_uploads"])
                
        tar_file_name = f"{changed_ip}_{date}_logs.tar.gz"
        
        self.functions.print_header_title({
            "line1": "RETRIEVE NODE LOGS",
            "line2": self.profile,
            "clear": True,
        })
        
        self.functions.print_paragraphs([
            ["C",0,"magenta","bold"], [")",-1,"magenta"], ["Current Logs",0,"magenta"], ["",1],
            ["B",0,"magenta","bold"], [")",-1,"magenta"], ["Backup Logs",0,"magenta"], ["",1],
            ["D",0,"magenta","bold"], [")",-1,"magenta"], ["Specific Date",0,"magenta"], ["",1],
            ["R",0,"magenta","bold"], [")",-1,"magenta"], ["Specific Date Range",0,"magenta"], ["",1],
            ["A",0,"magenta","bold"], [")",-1,"magenta"], ["Archived Logs",0,"magenta"], ["",1],
            ["X",0,"magenta","bold"], [")",-1,"magenta"], ["Exit",0,"magenta"], ["",2],
        ])
                
        choice = self.functions.get_user_keypress({
            "prompt": "KEY PRESS an option",
            "prompt_color": "cyan",
            "options": ["C","B","A","X","D","R"],
        })
        
        if choice == "a":
            self.log.logger.info(f"Request to upload Tessellation archive logs initiated")
            tar_package = self.listing_setup([archive_location])
                
        if choice == "b":
            self.log.logger.info(f"Request to upload backup Tessellation logs initiated")
            tar_package = self.listing_setup([backup_dest])      
            
        if choice == "d" or choice == "r":
            self.log.logger.info(f"Request to upload Tessellation date specific logs")
            cprint("  Date format must be [YYYY-MM-DD]","white",attrs=["bold"])
            dates_obj = {
                "location_dir": [archive_location],
                "start": None,
                "end": None
            }
            for n in range(0,2):
                while True:
                    verb = "desired"
                    if choice == "r" and n == 0:
                        verb = "start"
                    if choice == "r" and n == 1:
                        verb = "end"
                    choice_input = colored(f"  Please enter in the {verb} date you are searching for: ","cyan")
                    inputted_date = input(choice_input)
                    verb = "start" if choice == "d" else verb 
                    if match("^\d{4}\-(0[1-9]|1[012])\-(0[1-9]|[12][0-9]|3[01])$",inputted_date):
                        dates_obj[verb] = inputted_date
                        break
                    cprint("  invalid date, try again","red")
                    
                if choice == "d":
                    break
            tar_package = self.listing_setup(dates_obj)
                
        if choice == "c":
            self.functions.print_cmd_status({
                "text_start": "Current logs process started",
                "newline": True,
            })
            self.log.logger.info(f"Request to upload Tessellation current logs initiated")
            tar_archive_dir = ""
            tar_creation_path = "/tmp/tess_logs"
            tar_creation_origin = f"/var/tessellation/{self.profile}"

            if path.isdir(tar_creation_path):
                system(f"rm -rf {tar_creation_path} > /dev/null 2>&1")
            mkdir(tar_creation_path)
            
            with ThreadPoolExecutor() as executor:
                self.functions.status_dots = True
                self.log.logger.info(f"send_logs is building temporary tarball path and transferring files.")
                
                _ = executor.submit(self.functions.print_cmd_status,{
                    "text_start": "Transferring required files",
                    "dotted_animation": True,
                    "status": "copying",
                    "status_color": "yellow"
                })
                        
                cmd = f"rsync -a {tar_creation_origin}/ {tar_creation_path}/ "
                cmd += f"--exclude /data --exclude /logs/json_logs --exclude /logs/archived/ "
                cmd += "> /dev/null 2>&1"
                system(cmd)     

                self.functions.status_dots = False
                self.functions.print_cmd_status({
                    "text_start": "Transferring required files",
                    "status": "complete",
                    "newline": True
                })  
            
            dir_size = self.functions.get_dir_size(tar_creation_path)
            tar_package = {
                "tar_archive_dir": tar_archive_dir,
                "tar_creation_path": tar_creation_path,
                "tar_file_list": None,
            }

        if choice == "x":
            cprint("  User terminated program","green")
            exit(0)
            
        self.functions.print_paragraphs([
            ["",1],["Generating the tarball file my take up to",0], ["1",0,"yellow"],
            ["minute per Gb.",1], 
            ["Please exercise patience during this waiting process.",1,"red","bold"]
        ])
        
        if tar_package["tar_file_list"] == None:
            cmd = f"sudo tar -zcf {tar_dest}{tar_file_name} {tar_package['tar_creation_path']}{tar_package['tar_archive_dir']}"
        else:
            cmd = f"sudo tar -zcf {tar_dest}{tar_file_name} "
            dir_size = 0
            for file in tar_package["tar_file_list"]:
                cmd += f"{tar_package['tar_creation_path']}/{file} "
                dir_size += self.functions.get_size(f"{tar_package['tar_creation_path']}/{file}",True)
        
        dir_size = size(dir_size,system=alternative)
        self.functions.print_paragraphs([
            ["",1],["Total size of files to be added to tarball:",0], 
            [dir_size,1,"yellow","bold"]
        ])

        with ThreadPoolExecutor() as executor:
            self.functions.status_dots = True
            self.log.logger.info(f"send_logs is building temporary tarball path and transferring files.")
            
            _ = executor.submit(self.functions.print_cmd_status,{
                "text_start": "Generating gzip tarball",
                "dotted_animation": True,
                "status": "creating",
                "status_color": "yellow"
            })
                    
            self.functions.process_command({
                "bashCommand": cmd,
                "proc_action": "poll"
            })

            self.functions.status_dots = False
            self.log.logger.info(f"tarball creation requested saved to [{tar_dest}] size [{dir_size}]")
            self.functions.print_cmd_status({
                "text_start": "Generating gzip tarball",
                "status": "complete",
                "newline": True
            })  

        dsize = size(path.getsize(f"{tar_dest}{tar_file_name}"))
        self.functions.print_paragraphs([
            ["New tarball size:",0], 
            [dsize,2,"yellow","bold"]
        ])
        
        if " B" in dsize: # whitespace in front
            self.functions.print_paragraphs([
                [" WARNING ",0,"grey,on_red"],
                ["This size of the tarball is in",0,"yellow"], ["bytes",0,"yellow","underline"],
                ["this indicates an empty directory, please check before continuing.",2,"yellow"]
            ])
        else:
            try:
                size_parts = dsize.split(".")
                size_part = int(size_parts[0])
            except:
                pass
            else:
                if size_part > 50:
                    self.functions.print_paragraphs([
                        [" WARNING ",0,"grey,on_red"],
                        ["This size of the tarball is",0,"yellow"], ["large",0,"yellow","underline"],[".",-1,"yellow"],
                        ["You may seek an alternative method to deliver this file to the developers.",2,"yellow"]
                    ])

        self.functions.print_paragraphs([
            ["Do you want to upload this file:",0,"magenta"], [tar_file_name,0,"yellow","bold"],
            ["to the developers?",0,"magenta"]
        ])

        confirm = self.functions.confirm_action({
            "prompt": "upload?",
            "yes_no_default": "n",
            "return_on": "y",
            "exit_if": False,
        })

        if confirm:
            self.functions.print_paragraphs([
                ["",1], ["Depending on the size of the tarball, this may take some time to upload,",0],
                ["please be patient.",2,"red"]
            ])
            
            cmd = f"sudo curl --upload-file {tar_dest}{tar_file_name} https://transfer.sh/{tar_file_name}"
            cmd_results = self.functions.process_command({
                "bashCommand": cmd,
                "proc_action": "poll"
            })
            self.functions.print_paragraphs([
                ["log tarball transferred to developers",1,"magenta"],
                ["Please provide the following link to the developers for download and analysis.",1,"white","bold"],
                [cmd_results,2],
            ])

        # clean up
        self.log.logger.warn(f"send log tmp directory clean up, removing [{tar_package['tar_creation_path']}]")
        system(f"rm -rf {tar_package['tar_creation_path']} > /dev/null 2>&1")

        self.functions.print_paragraphs([
            ["Log tarball created and also located:",0,"green"],
            [tar_dest,2]
        ])     
        
        
    def listing_setup(self, location_date_input):
        file_choices = []
        date_request = False
        
        if isinstance(location_date_input,dict):
            location_list = location_date_input["location_dir"]
            date_request = True
        else:
            location_list = location_date_input
            
        while True:
            print(" ")
            count = 1
            dir_list = []
            
            for location in location_list:
                for f in listdir(location):
                    file = path.join(location, f)
                    file = file.split("/")
                    file_name_index = len(file)-1

                    if "log" in file[file_name_index]:
                        if date_request:
                            if location_date_input["end"] != None and location_date_input["start"] not in file[file_name_index] and location_date_input["end"] not in file[file_name_index]:
                                continue
                            elif location_date_input["end"] == None and location_date_input["start"] not in file[file_name_index]:
                                continue
                        self.functions.print_paragraphs([
                            [f"{count}     ",0,"yellow"], [self.profile,0,"magenta"], ["=>",0,"white","bold"], [file[file_name_index],1]
                        ])
                        count = count + 1
                        dir_list.append(file[file_name_index])
                        
            print(colored("  X".ljust(5),"yellow"),colored("Exit/Cancel","red"))
            
            if len(file_choices) > 0:
                print(""); cprint("  Current files for upload...","green")
            for file_show in file_choices:
                cprint(f"  {file_show}","cyan")
            choice_input = colored("\n  Please choose file to upload: ","magenta")
            
            while True:
                file_choice = input(choice_input)
                if file_choice.lower() == "x":
                    cprint("  Action Cancelled","green")
                    exit(0)
                try:
                    file_choice = int(file_choice)
                except:
                    pass
                else:
                    if file_choice <= len(dir_list):
                        tar_file = f"{dir_list[file_choice-1]}"  # file
                        if tar_file not in file_choices:
                            file_choices.append(tar_file)
                        
                        another = colored("  Add another file to upload? [","magenta")+colored("n","yellow")+colored("]: ","magenta")
                        another_choice = input(another)
                        if another_choice.lower() != "y":
                            return {
                                "tar_archive_dir": f"{dir_list[file_choice-1]}/",  # where are the files
                                "tar_creation_path": f"{location}",  # path to place tar
                                "tar_file_list": file_choices,
                            }
                        break
                    
                cprint("  invalid option","red")
                

    def scrap_log(self, command_obj):
        # scraps backwards (newest to oldest)
        profile = command_obj["profile"]
        msg = command_obj["msg"]
        key = command_obj["key"]
        value = command_obj["value"]
        timestamp = command_obj.get("timestamp",False)
        timeout = command_obj.get("timeout",30)
        thread = command_obj.get("thread", True)
        parent = command_obj.get("parent",False)
        
        start_time = time()
        go = 0
        
        
        self.log_file = self.log_file = f"/var/tessellation/{profile}/logs/json_logs/app.json.log"        
        
        try:
            with ThreadPoolExecutor() as executor:
                if thread:
                    self.functions.event = True
                    sleep(1) # slow it down
                    _ = executor.submit(self.functions.print_spinner,{
                        "msg": msg,
                        "color": "cyan",
                        "spinner_type": "dotted",
                        "timeout": timeout if timeout else False,
                    }) 
                
                while go < timeout:
                    with open(self.log_file, 'r') as file:        
                        for n, line in enumerate(reversed(file.readlines())):
                            try:
                                log_entry = json.loads(line)
                                found_value = log_entry.get(key)
                                if value in found_value:
                                    if timestamp:
                                        c_log_stamp = log_entry["@timestamp"]
                                        elapsed = self.functions.get_date_time({
                                            "action": "get_elapsed",
                                            "old_time": timestamp,
                                            "new_time": c_log_stamp,
                                            "format": "%Y-%m-%dT%H:%M:%S.%fZ",
                                        })
                                    if thread: self.functions.event = False
                                    if timestamp:
                                        if elapsed.days < 0:  # avoid ref before assignment
                                            continue
                                    return log_entry
                            except json.JSONDecodeError as e:
                                self.log.logger.debug(f"send_log -> scrapping log found [{e}] retry [{time() - start_time}] of [{timeout}]")

                            current_time = time()
                            if current_time - start_time > timeout: 
                                raise SendLogException("waiting timeout")
                            if timestamp and n > 5000: 
                                raise SendLogException("log entries may be too old to continue")
                            
                    go = time() - start_time
                        
                if thread: self.functions.event = False
                return False
                          
        except Exception as e:
            self.log.logger.warn(f"send_logs -> Reached an Exception -> error: [{e}]")  
            if thread: self.functions.event = False  
            return False     
        
                        
if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")                      
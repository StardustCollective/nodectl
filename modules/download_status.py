import json

from re import search
from time import sleep, perf_counter
from sys import exit
from os import system, path, get_terminal_size
from termcolor import colored
from re import sub
from copy import deepcopy 
from types import SimpleNamespace
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from .troubleshoot.errors import Error_codes

class DownloadStatus():
    
    def __init__(self,command_obj):
        self.parent = command_obj["parent"]
        
        self.command_obj = command_obj["command_obj"]
        self.command_list = self.command_obj["command_list"]
        self.caller = self.command_obj.get("caller","download_status")
        
        self.functions = self.parent.functions
        self.config_obj = self.parent.config_obj
        self.error_messages = Error_codes(self.config_obj) 
        self.valid_output_received = False
        
        self.log = self.parent.log
        self.log.logger.info("DownloadStatus module initiated")
        
        self.estimated_finished = "calculating..."
        self.remaining_time = -1
        self.back_and_forth = 0
        
        self.initialize = True
        self.initialize_timer = True
        self.initialize_ordinals = True
        self.initialize_height = True
        self.terminate_program = False
        
        self.dip_process_complete = False
        
        self.create_scrap_commands()


    def create_scrap_commands(self):
        cmds, self.bashCommands = [],{}
        self.log_file = self.log_file = f"/var/tessellation/{self.parent.profile}/logs/json_logs/app.json.log"
        
        if self.config_obj[self.parent.profile]["layer"] > 0 and self.caller != "status":
            self.error_messages.error_code_messages({
                "error_code": "ds-39",
                "line_code": "invalid_layer",
                "extra": f"{self.parent.profile} not supported by download_status feature"
            })
            
        # Grab the startingPoint ordinal start value
        # grep 'Download for startingPoint' /var/tessellation/dag-l0/logs/app.log | tail -n 1 | sed -n 's/.*SnapshotOrdinal(\([0-9]\+\)).*/\1/p'
        cmds.append({
            "action": "startstop",
            "keys": ["start","end"],
            "message": "Download for startingPoint"
        })

        # Grab last Download snapshot hash value
        cmds.append({
            "action": "current",
            "keys": ["current"],
            "message": "Downloading snapshot"
        })
        
        # Grab last ConsensusStateUpdater Ordinal
        cmds.append({
            "action": "latest",
            "keys": ["latest"],
            "message": "State updated ConsensusState",
        })
        
        # BlockAcceptanceManager exception
        cmds.append({
            "action": "height",
            "keys": ["current_height"],
            "message": "Accepted block: BlockReference"
        })
        
        self.cmds = cmds


    # Data Retrieval and builders
    def pull_local_dip_details(self):
        dip_details = []
                
        if self.initialize_ordinals: 
            old_values = defaultdict(lambda: -1)
            self.initialize_ordinals = False
        elif self.initialize_height:
            old_values = defaultdict(lambda: -1)
            self.initialize_height = False
        else: 
            old_values = deepcopy(self.dip_vals)
        
        try:
            with ThreadPoolExecutor() as executor:
                if self.initialize:
                    self.functions.event = True
                    _ = executor.submit(self.functions.print_spinner,{
                        "msg": f"Loading Node data",
                        "color": "cyan",
                    })     
                with open(self.log_file, 'r') as file:
                    for n, line in enumerate(reversed(list(file))):
                        try:
                            dip_details.append(json.loads(line))
                        except json.JSONDecodeError as e:
                            self.log.logger.warn(f"download_status -> Unable to parse JSON from log -> decoding error: [{e}]") 
                        if n > 249 and not self.initialize: break  
                    self.functions.event = False
                          
        except Exception as e:
            self.log.logger.warn(f"download_status -> Unable to open JSON from log -> error: [{e}]") 
            
        for cmd in self.cmds:
            for n, j_obj in enumerate(dip_details):
                if n < 1:
                    timestamp = j_obj["@timestamp"]
                    parts = timestamp.split('.')
                    timestamp = '.'.join(parts[:-1]) # remove sub-seconds.
                    timestamp = f"{timestamp[:-9]}-{timestamp[10:]}"
                    
                message = j_obj["message"] # readability 
                
                if cmd["action"] == "startstop":
                    if not self.initialize: 
                        try:
                            start = old_values.start
                        except:
                            try:
                                start = old_values["start"]
                            except: 
                                pass
                        break
                    
                    start = -1
                    end = -1
                    if cmd["message"] in j_obj["message"]:
                        start = search(r"Download for startingPoint=SnapshotOrdinal\((\d+)\)", message)
                        end = search(r'SnapshotMetadata{ordinal=SnapshotOrdinal{value=(\d+)},', message)

                        if start: start = start.group(1)
                        else: start = old_values["start"]

                        if end: end = end.group(1)
                        else: end = old_values["end"]
                        
                        try:
                            if int(start) < 1: start = end # use the end value instead if 0 if found
                        except Exception as e:
                            pass
                        
                        break # on first
                    
                if cmd["action"] == "current":
                    current = -1
                    if cmd["message"] in message:
                        current = search(r'SnapshotOrdinal{value=(\d+)}', message)
                        
                        if current: current = current.group(1)
                        else: current = old_values["current"]
                        break # on first
                    
                if cmd["action"] == "height":
                    height = -1
                    if cmd["message"] in message:
                        height = search(r'height=(\d+)', message)
                        
                        if height: height = height.group(1)
                        else: height = old_values["height"]
                        break # on first
                
        self.dip_status = {
            **self.dip_status,
            "timestamp": timestamp,
            "start": int(start),
            "current": int(current),
            "current_height": int(height)
        }
        
        
    def pull_ordinal_values(self):
        self.dip_status = {}
        
        metrics = self.functions.get_snapshot({
            "environment": self.config_obj[self.profile]["environment"],
            "profile": self.profile,
            "return_values": ["height","subHeight","ordinal"],
            "return_type": "list",
        })
        
        try: self.dip_status["height"] = metrics[0]
        except: self.dip_status["height"] = -1
        try: self.dip_status["subHeight"] = metrics[1]
        except: self.dip_status["subHeight"] = -1
        try: self.dip_status["latest"] = metrics[2]
        except: self.dip_status["latest"] = -1 

        self.pull_local_dip_details()
           

    def pull_dip_state(self):
        state = self.functions.test_peer_state({
            "profile": self.profile,
            "simple": True,
            "print_output": False,
            "skip_thread": True,
        })
        
        if state != "DownloadInProgress": 
            if state != "WaitingForDownload": 
                self.handle_end_of_dip(state)
            else: self.handle_wfd_state(state)  
            
            
    def test_update_status(self):
        tested_for_change = False
        if self.dip_vals.last_found == self.dip_vals.use_current:
            for _ in range(0,3):
                tested_for_change = True
                
                warning = "  snapshot download paused, standby..."
                if self.dip_vals.use_height: 
                    warning = "  block acceptance paused, standby..."
                if self.back_and_forth > 2: warning = "  Node is pausing to wait for valid consensus"

                sleep(1)
                self.pull_ordinal_values()
                self.dip_vals.use_current = self.dip_status["current"]
                
                if self.dip_vals.use_height:
                    self.dip_vals.use_current = self.dip_status["current_height"]
                    
                if self.dip_vals.last_found != self.dip_vals.use_current: break
                print(colored(warning,"blue"))
                print(f'\x1b[1A', end='')
                        
        if tested_for_change: self.functions.print_clear_line()
            
        if self.dip_vals.last_found == self.dip_vals.use_current:
            self.back_and_forth += 1
            sleep(1)
            self.dip_vals.use_height = False if self.dip_vals.use_height else True
            self.handle_dip_values()
            self.build_percent_hashes()
        else:
            self.dip_vals.last_found = self.dip_vals.use_current
            self.back_and_forth = 0 # reset
    
    
    def build_percent_hashes(self):
        self.dip_vals.last_hash_marks = self.dip_vals.hash_marks
        console_size = get_terminal_size()
        columns = int(console_size.columns*.62)
        
        try:
            hash_marks = int((self.dip_vals.percentage/100)*columns)
            self.dip_vals.hash_marks = "#"*hash_marks + "." * (columns - hash_marks)
        except ZeroDivisionError:
            self.log.logger.error(f"download_status - attempting to derive hash progress indicator resulted in [ZeroDivisionError] as [{e}]")
        
        try:
            _ = f"{self.dip_vals.hash_marks}"
        except Exception as e:
            self.log.logger.warn(f"download_status - formatting error on dynamic string creation - [{e}]")
            self.dip_vals.hash_marks = self.dip_vals.last_hash_marks
        
        if self.dip_vals.percentage1 < 0: 
            self.dip_vals.percentage1 = 0
        if self.dip_vals.percentage2 < 0: 
            self.dip_vals.percentage1 = 99
        
        try:
            height_percent = self.dip_vals.percentage2
            snapshot_percent = self.dip_vals.percentage1
            self.dip_vals.percentage = snapshot_percent
            if self.dip_vals.use_height: self.dip_vals.percentage = height_percent
            # below code when when attempting to use weighted percentage.
            # height_percent = int((self.dip_vals.percent_weight2 / 100.0) * self.dip_vals.percentage2)
            # snapshot_percent = int((self.dip_vals.percent_weight1 / 100.0) * self.dip_vals.percentage1)
            # self.dip_vals.percentage = height_percent + snapshot_percent
        except ZeroDivisionError as e:
            self.log.logger.error(f"download_status - attempting to derive percenter resulted in [ZeroDivisionError] as [{e}]")
            
        if self.dip_vals.percentage < 1: self.dip_vals.percentage = 1
        if self.dip_vals.percentage > 99: self.dip_vals.percentage = 99    
    
                
    # Handlers    
    def handle_wfd_state(self, state):
        if state != "WaitingForDownload": return
        self.functions.print_clear_line(5)
        self.functions.print_paragraphs([
            ["WaitingForDownload",0,"yellow"], ["state pauses the Node operation, nothing to report.",1],
        ])
        self.functions.print_cmd_status({
            "text_start":"Node Ordinal goal:",
            "brackets": str(self.dip_status['latest']),
            "status": state,
            "status_color": "yellow",
            "newline": True,
        })
        
        if not "-ni" in self.command_list and not "--ni" in self.command_list:
            self.functions.print_paragraphs([
                ["adding",0,"magenta"],["--ni",0,"yellow"]
            ])
            self.functions.print_clear_line()
            wfd_confirm = {
                "yes_no_default": "n",
                "return_on": "y",
                "prompt": "Would you like continue to wait?",
                "prompt_color": "magenta",
                "exit_if": True,                            
            }
            self.functions.confirm_action(wfd_confirm)
            
        while True:
            state = self.functions.test_peer_state({
                "profile": self.profile,
                "simple": True
            })                    
            self.functions.print_timer(5,"before checking again")
            if state != "WaitingForDownload": break
            try: wfd_attempts += 1 
            except: wfd_attempts = 1
            self.functions.print_paragraphs([
                ["Found State:",0],[state,1,"yellow"],
                ["Attempts",0], [str(wfd_attempts),0,"yellow"], ["of",0], ["10",1,"yellow"],
            ])
            if wfd_attempts > 9: 
                self.functions.confirm_action(wfd_confirm)
                print(f'\x1b[4A', end='')
                self.functions.print_clear_line(5)
                print(f'\x1b[1A', end='')
                wfd_attempts = 1
            print(f'\x1b[2A', end='')
            sleep(1)
                
                
    def handle_end_of_dip(self,state):
            self.functions.print_clear_line(6)
            print(f'\x1b[3A', end='')
            
            if self.valid_output_received:
                self.functions.print_paragraphs([
                    [" COMPLETED ",0,"grey,on_green","bold"], 
                    ["This Node is no longer in",0],["DownloadInProgress",0,"yellow"],["state.",1],
                    ["Cancelling progress indicators.",2],
                ])
            else:
                self.functions.print_paragraphs([
                    [" WARNING ",0,"red,on_yellow"], ["Request to watch the progress of",0,"red"],
                    ["the state: DownloadInProgress was requested, however",0,"red"],
                    ["this Node does not seem to be in this state.",1,"red"],
                    ["Nothing to report on...",2,"yellow"],
                ])
            self.functions.print_paragraphs([
                ["ON NODE VALUES",1,"magenta"],
                ["State Found:",0,],[state,1,"blue","bold"],
                ["Last found ordinal:",0], [str(self.dip_status['latest']),1,"blue","bold"],
            ])

            self.dip_process_complete = True
            self.functions.event = False
            self.functions.cancel_event = True
            self.terminate_program = True
            if self.caller != "upgrade" and self.caller != "cli_restart": 
                self.functions.print_paragraphs([
                    [""],["Press",0], ["q",0,"yellow"], ["to quit and exit to CLI prompt.",1],
                ])
                exit(0)
        

    def handle_dip_values(self):
        self.pull_dip_state()
        
        absolute = False
        backwards = False
        set_current = "end"
        if self.dip_vals.use_height: 
            start = self.dip_vals.start_height
            end = self.dip_status["height"]
            current = self.dip_status["current_height"]
            set_current = "start"
        else:   
            end = self.dip_status["current"] - self.dip_status["start"]
            current = self.dip_status["current"]  
            start = self.dip_status["start"]
            if start > current: absolute = True
            backwards = True
            # end = self.dip_status["latest"]
            # current = self.dip_status["current"]     
            # if self.dip_vals.start < 1: start = self.dip_status["start"]
            # else: start = self.dip_vals.start
            # if start > current: absolute = True
            # backwards = True
        
        try:
            percentage = self.functions.get_percentage_complete({
                "start": start,
                "end": end,
                "current": current,
                "absolute": absolute,
                "backwards": backwards,
                "set_current": set_current,
            })
        except Exception as e:
            percentage = 1   
            
        if self.dip_vals.use_height:
            if self.dip_status["height"] < 1: 
                try:
                    self.dip_vals.goal = self.dip_vals["start_height"]
                except:
                    self.dip_vals.goal = self.dip_vals.start_height
            else: 
                self.dip_vals.goal = end
                
            self.dip_vals.use_current = self.dip_status["current_height"]
            self.dip_vals.left = self.dip_vals.goal - self.dip_vals.use_current
            self.dip_vals.percentage2 = percentage
        else:
            self.dip_vals.use_current = self.dip_status["current"]
            self.dip_vals.use_end = self.dip_status["latest"]
            self.dip_vals.percentage1 = percentage
            self.dip_vals.goal = start

            self.dip_vals.left = abs(start-current)
            if self.dip_vals.left > self.dip_vals.previous_left:
                self.dip_vals.left = self.dip_vals.use_current - self.dip_vals.goal
            else:
                self.dip_vals.previous_left = self.dip_vals.left
            

            
            # if start < 2: self.dip_vals.goal = self.dip_status["end"]
            if start < 2: self.dip_vals.goal = self.dip_status["latest"]
            else: self.dip_vals.goal = start
            
        if self.dip_vals.goal == -1 and self.dip_vals.freeze_display < 0 and not self.initialize:
            self.dip_vals.freeze_display = 0


    def handle_time_estimate(self):
        if not "--estimate" in self.command_list: 
            self.estimated_finished = "Watching Ordinal Downloads"
            self.est_countdown = "*"
            self.est_title = "Status:"
            if self.dip_vals.use_height:
                self.estimated_finished = "Watching Snapshot Height Status"
            return
        self.est_title = "Est Finish:"
        
        current_time = perf_counter()
        elapsed = current_time - self.start_time
        start_cal_timer = 30
        remaining_time = -1
        
        if self.back_and_forth > 2:
            self.estimated_finished = f"unable to derive | attempt"
            self.est_countdown = self.back_and_forth
            return
        
        try:
            if start_cal_timer - int(elapsed) > 0:
                self.estimated_finished = f"creating baseline..."
                self.est_countdown = f"{start_cal_timer-int(elapsed):3}"
                return

            self.initialize_timer = False      
                       
            if self.dip_vals.use_height:
                processed = self.dip_vals.goal - self.dip_vals.use_current
            else:
                processed = abs(self.dip_vals.use_current - self.dip_vals.use_end)
            try:
                padding = (self.dip_vals.use_current-processed)*-1
                if padding < 0:
                    self.dip_vals.processed = padding
                    self.dip_vals.processed = self.dip_vals.processed * .05 # 60% 
                    self.dip_vals.processed += processed
                else:
                    self.dip_vals.processed -= processed
                percent_complete = self.dip_vals.processed / self.dip_vals.use_end
                remaining_time = elapsed / percent_complete
            except: 
                remaining_time = -1

            self.remaining_time = remaining_time
            
            if remaining_time < 0: remaining_time = 0
            estimated_finished = self.functions.get_date_time({
                "action": "future_datetime",
                "elapsed": int(remaining_time),
                "format": "%H:%M:%S on %Y-%m-%d"
            })
            self.estimated_finished = estimated_finished

            time_left = self.functions.get_date_time({
                "action": "future_datetime",
                "return_format": "time_obj",
                "elapsed": int(self.remaining_time),
            })
            till_done_timestamp = self.functions.get_date_time({
                "action": "get_elapsed",
                "new_time": time_left,
            })     
            self.est_countdown = self.functions.get_date_time({
                "action": "estimate_elapsed",
                "elapsed": till_done_timestamp
            })     
            
        except Exception as e:
            pass
        
        pass
    
    
    def clear_and_exit(self,skip_lines=True):
        if skip_lines:
            print("\n" * 4)
        exit(0)   
                

    def download_status(self,dip_pass=1):
        try:
            self.download_status_process(dip_pass)
        except BlockingIOError:
            print("Issue with session, may have timed out")
            exit(0)


    # Main method
    def download_status_process(self,dip_pass=1):
        with ThreadPoolExecutor() as executor:
            if self.caller == "download_status":
                try:
                    executor.submit(self.functions.get_user_keypress,{
                        "parent": self,
                        "prompt": None,
                        "options": ["Q"],
                        "quit_option": "Q",
                        "quit_with_exception": True,
                    }) 
                except:
                    self.terminate_program = True
                    exit(0)

            self.start_time = perf_counter()
        
            if "-p" in self.command_list:
                self.profile = self.command_list[self.command_list.index("-p")+1]
                self.log.logger.info(f"download_status called and using profile [{self.profile}]")
            else: self.command_list.append("help")
            
            self.functions.check_for_help(self.command_list,"download_status")
            
            if self.caller == "status" and not path.exists(self.log_file):
                    self.dip_status = {
                        "end": "Not Found",
                        "current": "Not Found",
                        "latest": "Not Found",
                    }
            else:
                self.pull_ordinal_values()
                
            self.initialize = False    
                    
            if self.caller == "status":
                self.log.logger.info(f'download_status - ordinal/snapshot lookup found | target download [{self.dip_status}] ')
                if self.dip_status["current"] == -1: self.dip_status["current"] = self.dip_status["latest"]
                return self.dip_status
            
            if self.caller == "upgrade" or self.caller == "cli_restart": 
                self.functions.print_clear_line()
                print("")
            else: system("clear") 
            
            if self.caller == "download_status": # and dip_pass < 2:
                self.functions.print_header_title({
                    "line1": "DOWNLOAD IN PROGRESS STATUS",
                    "single_line": True,
                    "show_titles": False,
                    "newline": "both"
                })

            self.dot = "start"                  
            dip_current_values = {
                "start": self.dip_status["start"],
                "start_height": self.dip_status["current_height"],
                "marks_last": -1,
                "spacing": 0,
                "use_height": False,
                "use_height_old": 0,
                "use_height_step": 0,
                "last_found": 0,
                "processed": 0,
                "height_processed": 0,
                "percentage": 0, "percentage1": 0, "percentage2": 0, 
                "percent_weight1": 100, "percent_weight2": 30,  # 1 snaps 2 height
                "use_current": self.dip_status["current"],
                "use_end": self.dip_status["latest"],
                "freeze_display": -1,
                "previous_left": -1,
                "last_hash_marks": "", "hash_marks": "",       
            } 
            self.dip_vals = SimpleNamespace(**dip_current_values)       

            try:
                while self.dip_vals.use_current <= self.dip_vals.use_end:
                    if self.dip_process_complete: return
                    if self.terminate_program: self.clear_and_exit()
                    
                    self.handle_dip_values()
                    
                    self.test_update_status()
                    self.dip_vals.last_found = self.dip_vals.use_current
                    
                    self.build_percent_hashes()
                    self.handle_time_estimate()
                    
                    self.print_output(dip_pass)
                    self.pull_ordinal_values()
                    
                    if "--snapshot" in self.command_list: break
            except TypeError as e:
                self.log.logger.error(f"DownloadStatus -> download_status -> TypeError [{e}] -> skipping update and restarting pass from [{dip_pass}] to [{dip_pass+1}]")
            except Exception as e:
                self.log.logger.error(f"DownloadStatus -> download_status -> Error [{e}] -> skipping update and restarting pass from [{dip_pass}] to [{dip_pass+1}]")

            if "--snapshot" in self.command_list or self.terminate_program: 
                self.clear_and_exit()

            # double check recursively
            self.initialize = True
            # self.initialize_height = True
            # self.initialize_ordinals = True
            dip_pass += 1

            self.download_status(dip_pass)
            self.functions.event = False
        

    # Print methods
    def print_output(self,dip_pass):
        self.valid_output_received = True
        
        if self.dip_vals.freeze_display > 0:
            self.functions.print_clear_line(4)
            print(f'\x1b[6A', end='')
            self.dip_vals.freeze_display = -1
            return
        
        dotted = ["    ",".   ","..  ","... ","...."]    
        try:
            self.dot = dotted[dotted.index(self.dot)+1]
        except: self.dot = dotted[0]
        
        self.functions.print_paragraphs([
            [f"ORDINAL STATUS CHECK PASS #{dip_pass} {self.dot}",1,"green"]
        ])
        
        self.functions.print_clear_line()
        print(
            colored("  Q to quit |","blue"),
            colored(self.dip_status["timestamp"],"yellow"),
        )
        
        self.functions.print_clear_line()
        print(
            colored(f"  {self.est_title} {colored(self.estimated_finished,'green')}","yellow"),
            colored("[","cyan"),
            colored(self.est_countdown,"blue",attrs=["bold"]),
            colored("]","cyan"),
            
        )

        if self.dip_vals.freeze_display == 0: 
            print("") # move cursor over percentage line  
            self.dip_vals.freeze_display = 1
            return
                         
        # make sure no invalid values get created
        try: _ = str(self.dip_vals.use_current)
        except: self.dip_vals.use_current = 0
        
        try: _ = str(self.dip_vals.goal)
        except: self.dip_vals.goal = 0
        
        try: _ = str(self.dip_vals.left)
        except: self.dip_vals.left = 0
        
        try: _ = str(self.dip_vals.percentage)
        except: self.dip_vals.percentage = 0
        
        if self.dip_vals.left < 1: d_color = "cyan"
        elif self.dip_vals.left > 1000: d_color = "red"
        elif self.dip_vals.left > 500: d_color = "magenta"
        elif self.dip_vals.left > 300: d_color = "yellow"
        else: d_color = "green"

        downloading = str(self.dip_vals.use_current)
        is_left = str(self.dip_vals.left)
        if self.dip_vals.use_current < 0:
            downloading, is_left = "Paused","Paused"

        
        self.functions.print_clear_line()

        if self.dip_vals.use_height:
            print(
                colored("  Block Height:","magenta"), 
                colored(f'{str(self.dip_vals.use_current)}',"blue",attrs=["bold"]), 
                colored("of","magenta"), 
                colored(str(self.dip_vals.goal),"blue",attrs=["bold"]), 
                colored("[","magenta"),
                colored(str(self.dip_vals.left),d_color),
                colored("]","magenta"),
            ) 
        else:
            print(
                colored("  Start","magenta"), 
                colored(f'{str(self.dip_status["latest"])}',"blue",attrs=["bold"]),
                colored("| Goal","magenta"),
                colored(str(self.dip_vals.goal),"blue",attrs=["bold"]),
                colored("| Downloading","magenta"),
                colored(f'{downloading}',"blue",attrs=["bold"]), 
                colored("| Left","magenta"),
                colored(f'{is_left}',d_color,attrs=["bold"]), 
            ) 
            
        self.functions.print_clear_line()
        print(
            colored("  [","cyan"),
            colored(self.dip_vals.hash_marks,"yellow"),
            colored(f"{']': >{self.dip_vals.spacing}}","cyan"),
            colored(f"{self.dip_vals.percentage}","green"),
            colored(f"{'%': <3}","green"),
        )
        if self.dip_vals.percentage < 100:
                print(f'\x1b[5A', end='')
            

if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation") 
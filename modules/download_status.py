from time import sleep, perf_counter
from sys import exit
from os import system, path
from termcolor import colored
from re import sub
from types import SimpleNamespace

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
         
        self.log = self.parent.log
        self.log.logger.info("DownloadStatus module initiated")
        
        self.estimated_finished = "calculating..."
        self.remaining_time = -1
        self.initialize_timing = True
        
        self.create_scrap_commands()


    def create_scrap_commands(self):
        cmds, self.bashCommands = [],{}
        log_file = self.log_file = f"/var/tessellation/{self.parent.profile}/logs/app.log"
        
        if self.config_obj[self.parent.profile]["layer"] > 0 and self.caller != "status":
            self.error_messages.error_code_messages({
                "error_code": "ds-39",
                "line_code": "invalid_layer",
                "extra": f"{self.parent.profile} not supported by download_status feature"
            })
            
        # Grab the startingPoint ordinal start value
        # grep 'Download for startingPoint' /var/tessellation/dag-l0/logs/app.log | tail -n 1 | sed -n 's/.*SnapshotOrdinal(\([0-9]\+\)).*/\1/p'
        cmd = f"grep 'Download for startingPoint' {log_file} | tail -n 1 | sed -n 's/.*SnapshotOrdinal(\([0-9]\+\)).*/\\1/p'"
        cmds.append(cmd)
        # Grab the startingPoint ordinal end value
        cmd = f"grep 'Download for startingPoint' {log_file} | tail -n 1 | awk -F'value=' "
        cmd += "'{print $2}' | awk -F'}' '{print $1}'"
        cmds.append(cmd)
        # Grab last Download snapshot hash value
        cmd = "grep 'Downloading snapshot' "
        cmd += f"{log_file} | tail -n 1 | awk -F 'value=' "
        cmd += "'{print $2}' | cut -d ',' -f 1 | sed 's/}//'"
        cmds.append(cmd)
        # Grab last ConsensusStateUpdater Ordinal
        cmd = f"grep -A1 'ConsensusStateUpdater' {log_file} | grep 'key=SnapshotOrdinal"
        cmd += "{value=' | tail -n 1 | awk -F'value=' '{print $2}' | awk -F'}' '{print $1}'"
        cmds.append(cmd)
        # BlockAcceptanceManager exception
        # grep 'Accepted block: BlockReference' /var/tessellation/dag-l0/logs/app.log | tail -n 1 | awk -F 'height=' '{split($2,a,","); print a[1]}'
        # Execute the commands in a pipeline
        grep_cmd = ["grep", "Accepted block: BlockReference", log_file]
        tail_cmd = ["tail", "-n", "1"]
        awk_cmd = ["awk", "-F", "height=", '{split($2,a,","); gsub("[^0-9]", "", a[1]); print a[1]}']
        cmd = [grep_cmd,tail_cmd,awk_cmd]  # to avoid escape sequences in the command
        cmds.append(cmd)
        # Grab the time from the logs
        # tail -n 1 /var/tessellation/nodectl/nodectl.log | awk '{print $1, $2, $3}'
        cmd = f"tail -n 1 {log_file} | awk "
        cmd += "'{print $1, $2}'"
        cmds.append(cmd)
        
        lookup_keys = ["start","end","current","latest","current_height","timestamp"]
        process_command_type = ["subprocess_co","subprocess_co","subprocess_co","subprocess_co","pipeline","subprocess_co"]
        for n, cmd in enumerate(cmds):
            self.bashCommands = {
                **self.bashCommands,
                f"{lookup_keys[n]}": [process_command_type[n],cmd],
            }


    def pull_ordinal(self,bashCommand):
        ord_value = self.functions.process_command({
            "bashCommand": bashCommand[1],
            "proc_action": bashCommand[0], 
        }).strip("\n")
        if ord_value == '' or ord_value == None: ord_value = "Not Found"
        try: return int(ord_value)
        except: return ord_value         
        
        
    def pull_ordinal_values(self):
        self.dip_status = {}
        metrics = self.functions.get_api_node_info({
            "api_host": self.functions.be_urls[self.config_obj[self.profile]["environment"]],
            "api_port": 443,
            "api_endpoint": "/global-snapshots/latest",
            "info_list": ["height","subHeight"],   
        })
        
        try: self.dip_status["height"] = metrics[0]
        except: self.dip_status["height"] = 0
        try: self.dip_status["subHeight"] = metrics[1]
        except : self.dip_status["subHeight"] = 0
        
        for key, bashCommand in self.bashCommands.items():
            self.dip_status[key] = self.pull_ordinal(bashCommand)
           
    
    def handle_wfd_state(self, state):
        if state != "WaitingForDownload": return
        self.functions.print_clear_line(5)
        self.functions.print_paragraphs([
            ["WaitingForDownload",0,"yellow"], ["state pauses the Node operation, nothing to report.",1],
        ])
        self.functions.print_cmd_status({
            "text_start":"Node Ordinal goal:",
            "brackets": str(self.dip_status['end']),
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
            self.functions.print_clear_line(4)
            self.functions.print_paragraphs([
                [" WARNING ",0,"red,on_yellow"], ["Request to watch the progress of",0,"red"],
                ["the state: DownloadInProgress was requested, however",0,"red"],
                ["this Node does not seem to be in this state.",1,"red"],
                ["Nothing to report on...",2,"yellow"],
                
                ["ON NODE VALUES",1,"magenta"],
                ["State Found:",0,],[state,1,"blue","bold"],
                ["Ordinal value goal:",0], [str(self.dip_status['end']),1,"blue","bold"],
                ["Last found ordinal:",0], [str(self.dip_status['latest']),1,"blue","bold"],
            ])
            try: 
                differential = self.dip_status['latest']-self.dip_status['end']
                differential = str(f"+{differential}") if differential > -1 else str(differential)
            except: differential = "N/A"

            self.functions.print_paragraphs([
                ["Differential:",0], [differential,2,"blue","bold"]
            ])
            if self.caller != "upgrade" and self.caller != "cli_restart": exit(0)
            return
        

    def handle_snapshot(self):
        if self.dip_vals.use_height: return
        
        try:
            self.dip_vals.percentage1 = self.functions.get_percentage_complete(self.dip_vals.start, self.dip_status["end"], self.dip_status["current"],True)
        except:
            self.dip_vals.percentage1 = 1   
            
        self.dip_vals.use_current = self.dip_status["current"]
        self.dip_vals.use_end = self.dip_status["end"]
        self.dip_vals.goal = self.dip_status["start"]
        
        
    def handle_height(self):
        if not self.dip_vals.use_height: return
         
        self.dip_vals.goal = self.dip_status["height"]
        try:
            self.dip_vals.percentage2 = self.functions.get_percentage_complete(self.dip_vals.start_height, self.dip_status["height"], self.dip_status["current_height"])
        except:
            self.dip_vals.percentage2 = 1

        self.dip_vals.use_current = self.dip_status["current_height"]
        self.dip_vals.left = self.dip_vals.goal - self.dip_vals.use_current
                
                
    def test_update_status(self):
        backup = False
        if self.dip_vals.last_found == self.dip_vals.use_current:
            for _ in range(0,5):
                backup = True
                warning = "  snapshot download paused, standby..."
                if self.dip_vals.use_height: warning = "  block acceptance paused, standby..."
                sleep(1)
                self.pull_ordinal_values()
                self.dip_vals.use_current = self.dip_status["current"]
                if self.dip_vals.use_height:
                    self.dip_vals.use_current = self.dip_status["current_height"]
                    
                if self.dip_vals.last_found != self.dip_vals.use_current: break
                print(colored(warning,"blue"))
                print(f'\x1b[1A', end='')
                        
        if backup: self.functions.print_clear_line()
            
        if self.dip_vals.last_found == self.dip_vals.use_current:
            sleep(1)
            self.dip_vals.use_height = False if self.dip_vals.use_height else True
            self.dip_vals.use_end = self.dip_status["end"]
            self.dip_vals.use_current = self.dip_status["current"]
            if self.dip_vals.use_height:
                self.dip_vals.use_end = self.dip_status["height"]
                self.dip_vals.use_current = self.dip_status["current_height"]
        else:
            self.dip_vals.last_found = self.dip_vals.use_current
        
    
    def build_percent_hashes(self):
        self.dip_vals.last_hash_marks = self.dip_vals.hash_marks
        
        try:
            self.dip_vals.hash_marks = "#"*(self.dip_vals.percentage // 2)
            if len(self.dip_vals.hash_marks) > self.dip_vals.marks_last: 
                self.dip_vals.spacing = (100 - self.dip_vals.percentage) // 2
                self.dip_vals.marks_last = len(self.dip_vals.hash_marks)     
        except ZeroDivisionError:
            self.log.logger.error(f"download_status - attempting to derive hash progress indicator resulted in [ZeroDivisionError] as [{e}]")
        
        try:
            _ = f"{self.dip_vals.hash_marks}"
        except Exception as e:
            self.log.logger.warn(f"download_status - formatting error on dynamic string creation - [{e}]")
            self.dip_vals.hash_marks = self.dip_vals.last_hash_marks
        
        try:
            self.dip_vals.percentage = int((self.dip_vals.percent_weight1 / 100.0) * self.dip_vals.percentage1 + (self.dip_vals.percent_weight2 / 100.0) * self.dip_vals.percentage2)
        except ZeroDivisionError as e:
            self.log.logger.error(f"download_status - attempting to derive percenter resulted in [ZeroDivisionError] as [{e}]")
            
        if self.dip_vals.percentage < 1: self.dip_vals.percentage = 1
        if self.dip_vals.percentage > 99: self.dip_vals.percentage = 100      
        
                        
    def download_status(self,dip_pass=1):
        start_time = perf_counter()
        
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
                
        if self.caller == "status":
            self.log.logger.info(f'download_status - ordinal/snapshot lookup found | target download [{self.dip_status["end"]}] current [{self.dip_status["current"]}] latest [{self.dip_status["latest"]}] ')
            if self.dip_status["end"] == "Not Found": self.dip_status["end"] = self.dip_status["latest"]
            if self.dip_status["current"] == "Not Found": self.dip_status["current"] = self.dip_status["latest"]
            return self.dip_status
        
        if self.caller == "upgrade" or self.caller == "cli_restart": 
            self.functions.print_clear_line()
            print("")
        else: system("clear") 
         
        if dip_pass < 2 and self.caller == "download_status":
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
            "percent_weight1": 50, "percent_weight2": 100,
            "use_current": self.dip_status["current"],
            "use_end": self.dip_status["end"],
            "freeze_display": False,
            "last_hash_marks": "", "hash_marks": "",       
        } 
        self.dip_vals = SimpleNamespace(**dip_current_values)       

        while self.dip_vals.use_current <= self.dip_vals.use_end:
            self.test_dip_state()
                
            self.handle_snapshot()
            self.handle_height()
            
            self.test_update_status()
            self.dip_vals.last_found = self.dip_vals.use_current
            
            self.build_percent_hashes()
            self.handle_time_estimate(start_time)
            
            try:
                if int(self.dip_vals.use_end) < int(self.dip_vals.use_current): 
                    self.dip_vals.use_end = int(self.dip_vals.use_current)
                    
                self.dip_vals.left = self.dip_vals.use_current - self.dip_vals.goal
                if self.dip_vals.use_height: self.dip_vals.left *= -1
            except:
                # "not found" literal
                self.dip_vals.freeze_display = True
                
            
            if not self.dip_vals.freeze_display:
                self.print_output(dip_pass)
                    
            if self.dip_vals.freeze_display: 
                self.functions.print_clear_line(3)
                print(f'\x1b[4A', end='')
                self.dip_vals.freeze_display = False     
                            
            sleep(.5)
            self.pull_ordinal_values()

        # double check recursively
        self.test_dip_state()
        dip_pass += 1
        sleep(.5)
        self.download_status(dip_pass)
        self.functions.event = False
        

    def print_output(self,dip_pass):
        dotted = ["    ",".   ","..  ","... ","...."]    
        try:
            self.dot = dotted[dotted.index(self.dot)+1]
        except: self.dot = dotted[0]
        
        self.functions.print_paragraphs([
            [f"ORDINAL STATUS CHECK PASS #{dip_pass} {self.dot}",1,"green"]
        ])
        
        self.functions.print_clear_line()
        print(
            colored("  ctrl-c to quit |","blue"),
            colored(self.dip_status["timestamp"].split(",")[0],"yellow"),
        )
        
        self.functions.print_clear_line()
        print(
            colored(f"  Est Finish: {colored(self.estimated_finished,'green')}","yellow"),
            colored("[","cyan"),
            colored(self.est_countdown,"blue",attrs=["bold"]),
            colored("]","cyan"),
            
        )
        
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
                colored(f'{str(self.dip_status["end"])}',"blue",attrs=["bold"]),
                colored("| Goal","magenta"),
                colored(str(self.dip_vals.goal),"blue",attrs=["bold"]),
                colored("| Downloading","magenta"),
                colored(f'{str(self.dip_vals.use_current)}',"blue",attrs=["bold"]), 
                colored("| Left","magenta"),
                colored(f'{str(self.dip_vals.left)}',d_color,attrs=["bold"]), 
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
            
    
    def test_dip_state(self):
        state = self.functions.test_peer_state({
            "profile": self.profile,
            "simple": True,
            "print_output": False,
            "skip_thread": True,
        })
        
        if state != "DownloadInProgress": 
            if state != "WaitingForDownload": self.handle_end_of_dip(state)
            else: self.handle_wfd_state(state)  
            
                        
    def handle_time_estimate(self,start_time):
        current_time = perf_counter()
        elapsed = current_time - start_time
        start_cal_timer = 10
        remaining_time = -1
        
        try:
            if start_cal_timer - int(elapsed) > 0:
                self.estimated_finished = f"calculating..."
                self.est_countdown = f"{start_cal_timer-int(elapsed):3}"
                return

            if (int(start_time) - int(elapsed)) % 5 != 0 and not self.initialize_timing:
                return       

            self.initialize_timing = False      
                       
            if self.dip_vals.use_height:
                try:
                    processed = self.dip_vals.goal - self.dip_vals.use_current
                    self.dip_vals.height_processed += processed
                    processed = self.dip_vals.height_processed
                    percent_complete = processed / self.dip_vals.start_height
                    remaining_time = elapsed / percent_complete
                except: 
                    remaining_time = -1
            else:
                try:
                    processed = self.dip_vals.left - (self.dip_vals.start - self.dip_vals.use_current)
                    self.dip_vals.processed += processed
                    processed = self.dip_vals.processed
                    percent_complete = processed / self.dip_status["end"]
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
            till_done_time_stamp = self.functions.get_date_time({
                "action": "get_elapsed",
                "new_time": time_left,
            })     
            self.est_countdown = self.functions.get_date_time({
                "action": "estimate_elapsed",
                "elapsed": till_done_time_stamp
            })     
            
        except Exception as e:
            pass
        
        pass


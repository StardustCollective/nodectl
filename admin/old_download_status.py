def show_download_status(self,command_obj,dip_pass=1):
    # show DownloadInProgress Status
    command_list = command_obj.get("command_list")
    dip_pass = command_obj.get("dip_pass",1)
    caller = command_obj.get("caller","show_download_status")
    
    if "-p" in command_list:
        self.profile = command_list[command_list.index("-p")+1]
        self.log.logger.info(f"show_download_status called and using profile [{self.profile}]")
    else: command_list.append("help")
    
    cmds, bashCommands = [],{}
    log_file = f"/var/tessellation/{self.profile}/logs/app.log"
    
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


    def pull_ordinal(bashCommand):
        ord_value = self.functions.process_command({
            "bashCommand": bashCommand[1],
            "proc_action": bashCommand[0], 
        }).strip("\n")
        if ord_value == '' or ord_value == None: ord_value = "Not Found"
        try: return int(ord_value)
        except: return ord_value
        
        
    def pull_ordinal_values(bashCommands):
        dip_status = {}
        metrics = self.functions.get_api_node_info({
            "api_host": self.functions.be_urls[self.config_obj[self.profile]["environment"]],
            "api_port": 443,
            "api_endpoint": "/global-snapshots/latest",
            "info_list": ["height","subHeight"],   
        })
        
        try: dip_status["height"] = metrics[0]
        except: dip_status["height"] = 0
        try: dip_status["subHeight"] = metrics[1]
        except : dip_status["subHeight"] = 0
        
        for key, bashCommand in bashCommands.items():
            dip_status[key] = pull_ordinal(bashCommand)
        return dip_status


    lookup_keys = ["start","end","current","latest","current_height","timestamp"]
    process_command_type = ["subprocess_co","subprocess_co","subprocess_co","subprocess_co","pipeline","subprocess_co"]
    for n, cmd in enumerate(cmds):
        bashCommands = {
            **bashCommands,
            f"{lookup_keys[n]}": [process_command_type[n],cmd],
            
        }  
        
    dip_status = pull_ordinal_values(bashCommands)    
            
    if caller == "status":
        self.log.logger.info(f'show status ordinal/snapshot lookup found | target download [{dip_status["end"]}] current [{dip_status["current"]}] latest [{dip_status["latest"]}] ')
        if dip_status["end"] == "Not Found": dip_status["end"] = dip_status["latest"]
        if dip_status["current"] == "Not Found": dip_status["current"] = dip_status["latest"]
        return dip_status
    
    if caller == "upgrade" or caller == "cli_restart": 
        self.functions.print_clear_line()
        print("")
    else: system("clear") 
        
    if dip_pass < 2 and caller == "show_download_status":
        self.functions.print_header_title({
            "line1": "DOWNLOAD IN PROGRESS STATUS",
            "single_line": True,
            "show_titles": False,
            "newline": "both"
        })

    state = self.functions.test_peer_state({
        "profile": self.profile,
        "simple": True
    })
    if state != "DownloadInProgress":
        if state == "WaitingForDownload":
            self.functions.print_paragraphs([
                ["WaitingForDownload",0,"yellow"], ["state pauses the Node operation, nothing to report.",1],
            ])
            self.functions.print_cmd_status({
                "text_start":"Node Ordinal goal:",
                "brackets": str(dip_status['end']),
                "status": state,
                "status_color": "yellow",
                "newline": True,
            })
            
            if not "-ni" in command_list and not "--ni" in command_list:
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
                
        else:
            self.functions.print_clear_line(4)
            self.functions.print_paragraphs([
                [" WARNING ",0,"red,on_yellow"], ["Request to watch the progress of",0,"red"],
                ["the state: DownloadInProgress was requested, however",0,"red"],
                ["this Node does not seem to be in this state.",1,"red"],
                ["Nothing to report on...",2,"yellow"],
                
                ["ON NODE VALUES",1,"magenta"],
                ["State Found:",0,],[state,1,"blue","bold"],
                ["Ordinal value goal:",0], [str(dip_status['end']),1,"blue","bold"],
                ["Last found ordinal:",0], [str(dip_status['latest']),1,"blue","bold"],
            ])
            try: 
                differential = dip_status['latest']-dip_status['end']
                differential = str(f"+{differential}") if differential > -1 else str(differential)
            except: differential = "N/A"

            self.functions.print_paragraphs([
                ["Differential:",0], [differential,2,"blue","bold"]
            ])
            if caller != "upgrade" and caller != "cli_restart": exit(0)
            return
    
    dip_status = pull_ordinal_values(bashCommands)
    start = dip_status["start"]
    start_height = dip_status["current_height"]
    marks_last = -1
    spacing = 0
    use_height = False
    use_height_old = 0
    use_height_step = 0
    ordinal_nochange = -1
    last_found, last_left = 0, 0
    percentage1, percentage2 = 0, 0
    percent_weight1, percent_weight2 = 50, 100
    use_current = dip_status["current"]
    use_end = dip_status["end"]
    freeze_display = False  
    # calc_rate = True  
    # rate_calc_start = perf_counter()
    
    while use_current < use_end:
        if not use_height:
            goal = dip_status["start"]
            percentage1 = self.functions.get_percentage_complete(start, dip_status["end"], dip_status["current"],True)
            use_current = dip_status["current"]
            if last_found == use_current:
                sleep(1)
                ordinal_nochange += 1
                if ordinal_nochange > 10: 
                    use_height = True
                    use_end = dip_status["height"]
                    use_current = dip_status["current_height"]
            last_found = use_current
        else:
            if start_height == "Not Found": 
                break
            percentage2 = self.functions.get_percentage_complete(start_height, dip_status["height"], dip_status["current_height"])
            use_current = dip_status["current_height"]
            ordinal_nochange = 0
            goal = use_end
                    
        try:
            percentage = int((percent_weight1 / 100.0) * percentage1 + (percent_weight2 / 100.0) * percentage2)
        except ZeroDivisionError as e:
            self.log.logger.error(f"show download status - attempting to derive percenter resulted in [ZeroDivisionError] as [{e}]")
                
        if percentage < 1: percentage = 1
        
        try:
            hash_marks = "#"*(percentage // 2)
            if len(hash_marks) > marks_last: 
                spacing = (100 - percentage) // 2
                marks_last = len(hash_marks)     
        except ZeroDivisionError:
            self.log.logger.error(f"show download status - attempting to derive hash progress indicator resulted in [ZeroDivisionError] as [{e}]")
            
        print(colored(f"  STATUS CHECK PASS #{dip_pass}","green"))
        
        if use_current == "Not Found": 
            break
        elif int(use_end) < int(use_current): use_end = int(use_current)
        left = use_current - goal
        if use_height: 
            self.functions.print_clear_line()
            left = use_end - use_current
            if left == use_height_old:
                use_height_step += 1
            use_height_old = left
            if use_height_step > 10:
                use_height = False
                use_height_step = 0
                freeze_display = True

        # future dev place holder
        # if calc_rate: 
        #     rate_calc_stop = perf_counter()
        #     elapsed_time = rate_calc_stop - rate_calc_start
        #     if elapsed_time > 30:
        #         rate = last_left - left
        #         try:
        #             estimated_time = (use_end - use_current) / rate
        #         except ZeroDivisionError as e:
        #             self.log.logger.error(f"show download status - attempting to derive new estimated time - resulted in [ZeroDivisionError] as [{e}]")
        #         calc_rate = False

        # print out status progress indicator
        if not freeze_display:
            self.functions.print_clear_line()
            print(
                colored("  Q to quit |","blue"),
                colored(dip_status["timestamp"].split(",")[0],"yellow")
            )
            
            self.functions.print_clear_line()
            
            # make sure no invalid values get created
            try: _ = str(use_current)
            except: use_current = ""
            
            try: _ = str(goal)
            except: goal = ""
            
            try: _ = str(left)
            except: left = ""
            
            try: _ = str(percentage)
            except: percentage = ""
            
            if use_height:
                print(
                    colored("  Block Height:","magenta"), 
                    colored(f'{str(use_current)}',"blue",attrs=["bold"]), 
                    colored("of","magenta"), 
                    colored(str(goal),"blue",attrs=["bold"]), 
                    colored("[","magenta"),
                    colored(str(left),"cyan"),
                    colored("]","magenta"),
                ) 
            else:
                if left > 1000: d_color = "red"
                elif left > 500: d_color = "magenta"
                elif left > 300: d_color = "yellow"
                else: d_color = "green"
                print(
                    colored("  Ordinals: Last","magenta"), 
                    colored(str(goal),"blue",attrs=["bold"]),
                    colored("| Downloading","magenta"),
                    colored(f'{str(use_current)}',"blue",attrs=["bold"]), 
                    colored("| Left","magenta"),
                    colored(str(left),d_color,attrs=["bold"]), 
                ) 
                
            self.functions.print_clear_line()
            print(
                colored("  [","cyan"),
                colored(hash_marks,"yellow"),
                colored(f"{']': >{spacing}}","cyan"),
                colored(f"{percentage}","green"),
                colored(f"{'%': <3}","green"),
            )
            if percentage < 100:
                print(f'\x1b[4A', end='')
        else: 
            self.functions.print_clear_line(3)
            print(f'\x1b[3A', end='')
            freeze_display = False                
        sleep(.3)

        dip_status = pull_ordinal_values(bashCommands)

    # double check recursively
    dip_pass += 1
    sleep(.5)
    self.show_download_status({
        "command_list": command_list,
        "caller": caller, 
        "dip_pass": dip_pass,
    })
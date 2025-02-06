from os import system, popen, path
from subprocess import Popen, check_output, PIPE, run
from sys import exit
from concurrent.futures import ThreadPoolExecutor, wait as thread_wait
from datetime import datetime

from .troubleshoot.errors import Error_codes
from .troubleshoot.logger import Logging


class Status():
    
    def __init__(self,functions):
        self.date_stamp = datetime.now().strftime("%Y-%m-%d")
        
        self.version_obj = functions.version_obj
        self.functions = functions
        self.log_key = "main"
        
        self.node_state = ""
        self.hd_space = ""
        self.usage = ""
        self.memory = ""
        self.swap = ""
        self.invalid_logins = ""
        self.lower_port = ""
        self.higher_port = ""
        self.port_range = ""
        self.max_auth_attempts = ""
        self.last_action = "none"
        self.error_count = 0
        self.process_memory = {}
        self.mem_swap_min = 1000000

        self.called_command = None
        self.log_found_flag = False
        self.new_method = False
        self.successful_sec_check = False

        self.uptime = 30
        self.load = .7

        self.error_codes = Error_codes(self.functions)
        self.log = Logging()
                        
        self.ip_address = self.functions.get_ext_ip()
        self.profile_names = self.functions.pull_profile({
            "req": "list",
            "profile": None,
            "auto_restart": False
        })  
        
        self.functions.get_service_status()


    def execute_status(self):
        self.get_server_details()
        if self.called_command != "sec": 
            self.get_status_dir_sizes()
        self.security_check()
        return self.successful_sec_check


    def find_log_file(self):
        # removed due to version update
        # however may need to use this function repurposed
        # in future releases to navigate through rolled/archived
        # logs
        bashCommand = "ls -l /var/log"
        ps = Popen(bashCommand.split(), 
                            stdout=PIPE)
        try:
            output = check_output(["grep","tessellation"], stdin=ps.stdout)
        except:
            _ = self.functions.process_command({
                "bashCommand": f"touch /var/log/tessellation_dag_log_{self.date_stamp}",
                "proc_action": "subprocess_devnull",
            })
            self.log_file = f'tessellation_dag_log_{self.date_stamp}'
        else:
            self.log_found_flag = True
            ps.wait()
            output = output.decode("utf-8")
            output = output.split("\n")
            file = []
            file = [ item for item in output if item != ""]
            file = file[-1].split()
            self.log_file = f"/var/log/{file[-1]}"
            

    def get_server_details(self):
        self.hd_space = self.functions.check_dev_device()
        self.command_list = {
            "memory": "free | awk '{print $4}'",
            "uptime": "uptime",
        }
        
        for key,value in self.command_list.items():
            if key == "memory":
                memory = popen(value)
                memory = memory.read()
                self.parse_memory(memory)
                _ , _ , self.process_memory = self.functions.check_cpu_memory_thresholds()
                for key, value in self.process_memory.items():
                    if key == "thresholds": continue
                    self.process_memory[key]["RSS"] = self.functions.set_byte_size(value["RSS"])
                    self.process_memory[key]["VMS"] = self.functions.set_byte_size(value["VMS"])
                self.memory_percent = self.process_memory["thresholds"]["mem_percent"]
                self.cpu_percent = self.process_memory["thresholds"]["cpu_percent"]
            elif key == "uptime":
                with open('/proc/uptime','r') as uptime_file:
                    uptime_seconds = float(uptime_file.readline().split()[0])
                    self.current_result = str(int(uptime_seconds /(60*60*24)))
                self.parse_uptime_load()

        self.distro_value = self.functions.get_distro_details()
       
        
    def parse_uptime_load(self):

        if  int(self.current_result) > self.uptime:
            self.system_up_time = f"WARN@{str(self.current_result)}"
        else:
            self.system_up_time = f"OK@{str(self.current_result)}"

        if float(self.cpu_percent/100) > float(self.load):
            self.usage = f"WARN@{self.cpu_percent}%"
        else:
            self.usage = f"OK@{self.cpu_percent}%" 
            
        # self.usage = self.usage.strip("\n")
        # self.system_up_time = self.system_up_time.strip("\n")


    def parse_memory(self,memory):
        details = memory.split("\n")
        details.pop(0)
        details.pop()

        for n, usage in enumerate(details):
            if int(usage) < self.mem_swap_min:
                if n == 0:
                    self.memory = f"LOW@ {'{:,}'.format(int(usage))}"
                else:
                    self.swap = f"LOW@ {'{:,}'.format(int(usage))}"
            else:
                if n == 0:
                    self.memory = f"OK@ {'{:,}'.format(int(usage))}"
                else:
                    self.swap = f"OK@ {'{:,}'.format(int(usage))}\n"
               
  
    def security_check(self):
        if not self.new_method:
            self.log.logger[self.log_key].debug("security check of auth log initiated...")
        else:
            self.log.logger[self.log_key].debug("security check using journalctl initiated...")

        invalid_str = ""
        accepted_str = ""
                
        self.max_auth_attempt_count = 0
        self.error_auths_count = 0
        accepted_auths_count = 0

        if not self.new_method:
            # OLD METHOD: Read auth.log files (Debian 11 / Ubuntu 22.04)
            if not path.exists("/var/log/auth.log"):
                self.log.logger[self.log_key].error("unable to read file [/var/log/auth.log] during health check.")
                self.functions.print_paragraphs([
                    [" FILE NOT FOUND ", 0, "red,on_yellow"],
                    ["nodectl was unable to find a valid authorization log on the VPS or server that this Node was installed on?", 2, "red"],
                    ["Are you sure this is a valid Debian based operating system?  Unable to properly access files", 0, "red"],
                    ["to verify security checks, exiting...", 2, "red"],
                ])
                return
                
            creation_time = path.getctime("/var/log/auth.log")
            log_files = ["/var/log/auth.log"]
            # If a rotated log is available, use its creation time instead
            if path.exists("/var/log/auth.log.1"):
                log_files.append("/var/log/auth.log.1")
                creation_time = path.getctime("/var/log/auth.log.1")
            self.creation_time = datetime.fromtimestamp(creation_time)

            # Process each file
            for log_file in log_files:
                # Get list of invalid user entries (prints field 8 and field 12, i.e. username and port)
                cmd = "cat " + log_file + " | grep \"]: Invalid user\" | awk '{print $8 \" \" $12}'"
                read_stream_invalid = popen(cmd)
                # Get list of accepted logins (prints timestamp and user from the accepted line)
                cmd = ("cat " + log_file +
                    " | grep \"]: Accepted publickey\" | awk '{print $1\" \"$2\" \"$3\" \"$9\" --> IP address: \"$11}'")
                read_stream_accepted = popen(cmd)
                # Count maximum authentication attempts exceeded
                cmd = ("cat " + log_file +
                    " | grep -i \"error: maximum authentication attempts exceeded\" | wc -l")
                read_stream_max = popen(cmd)
                # Count errors in the auth log
                cmd = "cat " + log_file + " | grep -i \"error\" | wc -l"
                read_stream_errors = popen(cmd)

                invalid_str += read_stream_invalid.read()
                accepted_str += read_stream_accepted.read()
                self.max_auth_attempt_count += int(read_stream_max.read())
                self.error_auths_count += int(read_stream_errors.read())
        else:
            # Debian Ubuntu 24.04 / Debian 12
            boot_line = popen("journalctl -o short-iso -t sshd | head -n 1").read().strip()
            if boot_line:
                # Assuming a line like "2025-01-31T12:34:56 hostname sshd[12345]: <message>"
                timestamp_str = boot_line.split()[0]  # e.g. "2025-01-31T12:34:56"
                try:
                    self.creation_time = datetime.fromisoformat(timestamp_str)
                except Exception:
                    self.creation_time = datetime.now()
            else:
                self.creation_time = datetime.now()

            # Build journalctl commands with a short output format (similar to auth.log)
            # Adjust the filtering (-t sshd) if your system uses a different tag.
            invalid_cmd = ("journalctl -o short -t sshd | grep ']: Invalid user' | "
                        "awk '{print $8 \" \" $12}'")
            accepted_cmd = ("journalctl -o short -t sshd | grep ']: Accepted publickey' | "
                            "awk '{print $1\" \"$2\" \"$3\" \"$9\" --> IP address: \"$11}'")
            max_cmd = ("journalctl -o short -t sshd | grep -i 'error: maximum authentication attempts exceeded' | wc -l")
            error_cmd = ("journalctl -o short -t sshd | grep -i 'error' | wc -l")

            invalid_str = popen(invalid_cmd).read()
            accepted_str = popen(accepted_cmd).read()
            self.max_auth_attempt_count = int(popen(max_cmd).read())
            self.error_auths_count = int(popen(error_cmd).read())            
            

        invalid_list = invalid_str.split("\n")
        accepted_list = accepted_str.split("\n")
        
        # clean out empty lines
        invalid_list = [n for n in invalid_list if n]
        self.accepted_list = [n for n in accepted_list if n]

        self.invalid_logins = len(invalid_list)
        self.accepted_logins = len(self.accepted_list)

        lower_port = 65535
        higher_port = 0

        for user_port in invalid_list:
            parts = user_port.split(" ")
            try: 
                int(parts[1])
            except:
                pass
            else:
                if int(parts[1]) < lower_port:
                    lower_port = int(parts[1])
                if int(parts[1]) > higher_port:
                    higher_port = int(parts[1])

        self.lower_port = lower_port if lower_port < 65535 else 0
        self.higher_port = higher_port
        self.port_range = f"{self.lower_port}-{self.higher_port}"
        self.successful_sec_check = True


    def get_status_dir_sizes(self):
        dirs = self.functions.get_dirs_by_profile({"profile": "all"})
        dir_sizes = list()
        self.profile_sizes = dict()
        workers = self.distro_value["info"]["count"]

        self.functions.print_paragraphs([
            ["Calculating directory sizes...",1],
        ])
        self.functions.status_single_file = True
        for profile in dirs:
            for profile_dir in dirs[profile].keys():
                if dirs[profile][profile_dir] == "disabled": 
                    continue
                if profile_dir == "directory_inc_snapshot" and not self.non_interactive:
                    self.functions.print_paragraphs([
                        ["",1],[" WARNING ",0,"yellow,on_blue"], ["The health feature reviews the status",0,"red"],
                        ["of the node's snapshot chain. This could take up to",0,"red"], 
                        ["ten",0,"yellow","bold"],["minutes",0,"red"], ["to complete, but typically it should be under",0,"red"],
                        ["two",0,"yellow","bold"],["minutes on a properly spec'd VPS.",1,"red"],
                    ])    
                    if self.functions.confirm_action({
                        "yes_no_default": "y",
                        "return_on": "n",
                        "prompt": f"Calculate snapshot directory size?",
                        "exit_if": False,
                    }): 
                        dir_sizes.append((profile_dir,"skipped"))
                        self.functions.print_cmd_status({
                            "text_start": "Calculating",
                            "brackets": profile_dir,
                            "status": "skipped",
                            "newline": True,
                            "status_color": "magenta",
                        })
                        continue 

                with ThreadPoolExecutor() as executor:
                    self.functions.status_dots = True
                    c_obj = {
                        "text_start": "Calculating",
                        "brackets": profile_dir,
                        "status": "running",
                        "timeout": False,
                        "dotted_animation": True,
                        "newline": False,
                        "status_color": "yellow",
                    }
                    _ = executor.submit(self.functions.print_cmd_status,c_obj)

                    dsize = 0
                    if path.exists(dirs[profile][profile_dir]):
                        dsize = run(['du', '-sb', dirs[profile][profile_dir]], stdout=PIPE)
                        dsize = int(dsize.stdout.split()[0])
                        dsize = self.functions.set_byte_size(dsize)
                    dir_sizes.append((profile_dir, dsize))
                    
                    self.functions.status_dots = False

                c_obj["status"] = "Complete" 
                c_obj["status_color"] = "green"
                c_obj["newline"] = True
                c_obj["dotted_animation"] = False
                c_obj["timeout"] = False
                self.functions.print_cmd_status(c_obj)

            self.profile_sizes[profile] = dir_sizes
            dir_sizes = [] # reset

        return

            
if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")
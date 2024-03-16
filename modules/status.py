from os import system, popen, path
from subprocess import Popen, check_output, PIPE
from hurry.filesize import size, alternative
from sys import exit

from datetime import datetime

from .troubleshoot.errors import Error_codes
from .troubleshoot.logger import Logging


class Status():
    
    def __init__(self,functions):
        self.date_stamp = datetime.now().strftime("%Y-%m-%d")
        
        self.version_obj = functions.version_obj
        self.functions = functions
                
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
        self.log_found_flag = False
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
        self.get_server_details()
        self.get_status_dir_sizes()
        self.security_check()


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
            system(f'touch /var/log/tessellation_dag_log_{self.date_stamp} > /dev/null 2>&1')
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
        self.hd_space = self.check_dev_device()
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
                    self.process_memory[key]["RSS"] = size(value["RSS"],system=alternative)
                    self.process_memory[key]["VMS"] = size(value["VMS"],system=alternative)
            elif key == "uptime":
                # fix problem with uptime less than 1 day
                result_stream = popen("uptime")
                result_test = result_stream.read()
                if "day" in result_test:
                    command = "uptime | awk '{print $3\" \"$12}'"
                elif "min" in result_test:
                    command = "uptime | awk '{print $3\" \"$11}'"
                else:
                    command = "uptime | awk '{print $3\" \"$10}'"
                result_stream = popen(command)
                self.current_result = result_stream.read()
                self.parse_uptime_load()
 
            
    def check_dev_device(self):
        cmds = ["dev/vda1","/dev/xvda1","dev/sda1","dev/root","/dev/nvme0n1p1"]
        for cmd in cmds:
            device = popen(f"df -h | grep '{cmd} ' | awk "+"'{print $5\" of \"$3}'")
            device = device.read()
            if device:
                return device
        return "unknown"
      
        
    def parse_uptime_load(self):
        details = self.current_result.split(" ")
        details[0] = self.functions.cleaner(details[0],"new_line")
        details[0] = self.functions.cleaner(details[0],"commas")
        details[1] = self.functions.cleaner(details[1],"new_line")
        details[1] = self.functions.cleaner(details[1],"commas")

        try: 
            int(details[0])
        except:
            details[0] = 1

        if int(details[0]) > self.uptime:
            self.system_up_time = f"WARN@{details[0]}"
        else:
            self.system_up_time = f"OK@{details[0]}"

        if float(details[1]) > float(self.load):
            self.usage = f"WARN@{details[1]}"
        else:
            self.usage = f"OK@{details[1]}" 
            
        self.usage = self.usage.strip("\n")
        self.system_up_time = self.system_up_time.strip("\n")


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
        self.log.logger.debug("security check of auth log initiated...")
        invalid_str = ""
        accepted_str = ""
                
        self.max_auth_attempt_count = 0
        self.error_auths_count = 0
        accepted_auths_count = 0
                
        if not path.exists("/var/log/auth.log"):
            self.log.logger.error("unable to read file [/var/log/auth.log] during health check.")
            self.functions.print_paragraphs([
                [" FILE NOT FOUND ",0,"red,on_yellow"], 
                ["nodectl was unable to find a valid authorization log on the VPS or server that this Node was installed on?",2,"red"],
                ["Are you sure this is a valid Debian based operation system?  Unable to to properly access files",0,"red"],
                ["to verify security checks, exiting...",2,"red"],
            ])
            exit("  Linux distribution file access error")
            
        creation_time = path.getctime("/var/log/auth.log")
        dir_list = ["/var/log/auth.log"]
        if path.exists("/var/log/auth.log.1"):
            dir_list.append("/var/log/auth.log.1")
            creation_time = path.getctime(f"/var/log/auth.log.1")
        self.creation_time = datetime.fromtimestamp(creation_time)

        # for dir in dir_list:
        for dir in dir_list:
            # list of Invalid user statements parsed
            cmd = "cat "+dir+" | grep \"]: Invalid user\" | awk '{print $8 \" \" $12}'"
            read_stream_invalid = popen(cmd)
            
            # list of accepted logins            
            cmd = "cat "+dir+" | grep \"]: Accepted publickey\" | awk '{print $1\" \"$2\" \"$3\" \"$9\" --> IP address: \"$11}'"
            read_stream_accepted_list = popen(cmd)            
            
            # count of maximum exceeded logins
            cmd = "cat "+dir+" | grep -i \"error: maximum authentication attempts exceeded\" | wc -l"
            read_stream_max = popen(cmd)
            
            # count of errors found in auth log
            cmd = "cat "+dir+" | grep -i \"error\" | wc -l"
            read_stream_errors = popen(cmd)
            
            invalid_str += read_stream_invalid.read()
            accepted_str += read_stream_accepted_list.read()
            
            self.max_auth_attempt_count += int(read_stream_max.read())
            self.error_auths_count += int(read_stream_errors.read())

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


    def get_status_dir_sizes(self):
        dirs = self.functions.get_dirs_by_profile({"profile": "all"})
        dir_sizes = list()
        self.profile_sizes = dict()
        
        for profile in dirs:
            for profile_dir in dirs[profile].keys():
                dsize = self.functions.get_dir_size(dirs[profile][profile_dir])
                dsize = size(dsize,system=alternative)
                dir_sizes.append((profile_dir, dsize))
            self.profile_sizes[profile] = dir_sizes
            dir_sizes = [] # reset

            
if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")
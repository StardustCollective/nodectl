import re

from os import system, path, makedirs, getenv
from getpass import getpass, getuser
from shutil import copyfile
from termcolor import colored, cprint
from secrets import compare_digest

from .troubleshoot.errors import Error_codes

class UserClass:
    
    def __init__(self,cli_obj):
        
        self.username = ""
        self.password = ""
        
        self.functions = cli_obj.functions
        self.error_messages = Error_codes(self.functions) 
        self.version_obj = self.functions.version_obj
        self.cli_obj = cli_obj
        
        self.aws = False
        self.ssh_key = False
        
        self.username = None
        self.password = None

        self.keep_user = False
        self.migrating_p12 = False
        self.quick_install = False
        
        
    def setup_user(self):
        self.ask_for_username()
        self.ask_for_password()
        self.create_debian_user()
        self.transfer_ssh_key()

  
    def ask_for_username(self):
        print("")
        self.functions.print_header_title({
          "line1": "CREATE USER",
          "newline": "top",
          "show_titles": False,
          "clear": True,
        })
            
        progress = {
            "text_start": "detecting user",
            "status": "running",
            "delay": .5            
        }
        self.functions.print_cmd_status(progress)            
        
        try:
            current_user = getenv("SUDO_USER")
        except:
            current_user = getuser()
        self.installing_user = current_user
            
        self.functions.print_cmd_status({
            **progress,
            "status": current_user,
            "status_color": "magenta",
            "delay": 0,
            "newline": True
        })
        
        user_type = "non-commonly known"
        if current_user == "root" or current_user == "ubuntu" or current_user == "admin":
            self.functions.print_paragraphs([
                [" WARNING ",0,"yellow,on_red"], ["User:",0,"red"], [current_user,0,"yellow","bold"],
                ["is a dangerous user to use on a day-to-day basis.",2,"red"],
            ])
        
        if current_user == "root":
            user_type = "non-root"
        
        if current_user == "nodeadmin":
            self.functions.print_paragraphs([
                ["",1],[" DETECTED NODEADMIN ",0,"white,on_blue"], 
                ["This user already exists and is being used for this installation. This is the recommended user to",0,"white","bold"],
                ["administer your Node.",2,"white","bold"],
            ])
            self.keep_user = self.functions.confirm_action({
                "yes_no_default": "y",
                "return_on": "y",
                "prompt": "Keep this user?",
                "exit_if": False,
            })
            if self.keep_user:
                self.username = "nodeadmin"
                self.functions.print_cmd_status({
                    "text_start": "Keeping User",
                    "status": current_user,
                    "status_color": "green",
                    "newline": True,
                })
                return
            
        self.functions.print_paragraphs([
            ["You should create a",0], [user_type,0,"yellow","bold"], ["user to administer your Node.",2],
            ["It is recommended to use",0,], ["nodeadmin",0,"yellow","bold"], ["as the Node Administrator.",2],
            ["This is recommended because it will help during troubleshooting, administering, etc. as you follow any instructional documentation or tutorials.",2],
        ])
        
        while True:
            cprint("  Please enter in the new user you would like to","magenta")
            ask_question = colored("  create [","magenta")+colored("nodeadmin","yellow",attrs=["bold"])+colored("]: ","magenta")
            user = input(ask_question)
            if not user:
                user = "nodeadmin"
                break
            else:
                prompt_str = colored("Please confirmed that: ",'cyan')+colored(user,"yellow",attrs=['bold'])+colored(" is correct","cyan")
                confirm = self.functions.confirm_action({
                    "yes_no_default": "y",
                    "return_on": "y",
                    "prompt": prompt_str,
                    "exit_if": False
                })
                if confirm:
                    break
                
        self.username = user
        self.test_if_user_exists()


    def test_if_user_exists(self):
        try:
            with open('/etc/passwd', 'r') as passwd_file:
                u_exists = any(line.startswith(self.username + ':') for line in passwd_file)
        except FileNotFoundError:
            u_exists = False       
        
        self.keep_user = False
        if u_exists:
            self.functions.print_paragraphs([
                ["",1],[" NOTICE ",0,"white,on_blue"], ["The user that you requested to add",0],
                ["already exists on this Debian based VPS or Server instance.",2],
            ])
            prompt_str = f"Update password for {self.username}"
            confirm = self.functions.confirm_action({
                "yes_no_default": "n",
                "return_on": "n",
                "prompt": prompt_str,
                "exit_if": False
            })
            if confirm:
                self.keep_user = True

        
    def ask_for_password(self):
        if self.keep_user: return
        
        self.functions.print_paragraphs([
            ["",1], ["We need to create a password for",0],
            [self.username,0,"yellow"], ["user:",1],
        ])
        if not self.quick_install:
            self.print_password_descriptions(10,"password")
            self.functions.print_paragraphs([
                ["This password will allow access to enter",0,"white"], ["sudo",0,"cyan","bold"], ["(superuser do).",2,"white"],
                ["Please create a",0,"white"], ["unique",0,"yellow","bold"], ["password and write it down!",2,"white"],
                ["It is recommended to save this password to a secure location and do",0,"white"], ["NOT",0,"red","bold"],["forget it!",0,"white"],
                ["If choosing to write it down, label in your notes:",1,"white"],
                [f"\"{self.username} user password to access sudo (administrator) rights on the Node.\"",2]
            ])
        
        self.password = self.get_verify_password(10,self.username,"password")
        

    def get_user(self):
        return getuser()
    
            
    def print_password_descriptions(self,length,type,already_user=False):
        
        paragraphs = [
                    ["",1], ["We will end of up with",0,"red"], ["3",0,"yellow"], ["separate",0,"red"], ["unique",0,"yellow","bold"],["passphrases.",2,"red"],
                    
                    ["1",0,"magenta","bold"], ["SSH KEY passphrase/keyphrase",0,"yellow"], ["- already created",2,"green","bold"],
                    
                    ["2",0,"magenta","bold"], [f"User {self.username}'s VPS admin password",0,"yellow"], ["",2],
                    
                    ["3",0,"magenta","bold"], ["P12 Private key passphrase/keyphrase",2,"yellow"],
                    
                    ["You will not see your password as you type it, this is for security purposes.",1,"magenta"],
                    ["Your password should contain capital & lowercase letters, numbers, special characters, but",0,"magenta"], ["no",0,"red","bold,underline"],
                    ["spaces, single or double quotes.",2,"magenta"],
                    
                    [f"This {type} should be {length} in length.",1],
                    [" WARNING ",0,"grey,on_yellow","bold"], ["nodectl does not work well with",0,"red"], ["section signs",0,"yellow","bold"], ["special characters.",2,"red"], 
        ] 

        if already_user:
            paragraphs.insert(11,["- already created",0,"green","bold"])
        
        self.functions.print_paragraphs(paragraphs)
      
      
    def get_verify_password(self,length,name,type):
        # dict
        # length = minimum characters for pass length
        # name = p12 or username
        # type = password, keyphrase, or passphrase
        
        # pattern = "^(?=.*?[A-Z])(?=.*?[a-z])(?=.*?[0-9])(?=.*?[#?!@$%^&*-])(?=.*?[^'])([^'\"]*$)" # no single quotes, double quotes, or periods.
        pattern = "^(?=.*[A-Z])(?=.*[a-z])(?=.*[0-9])(?=.*[#?!@$%^&*-])[^'\"\\s.]+$" # no single quotes, double quotes, spaces or periods.
        conjunction = "an" if length < 10 else "a"
        cprint(f">> Please enter {conjunction} {length} character minimum","magenta")
        first = f">> {type} for {name}: "
        second = f">> Please confirm {name}'s {type}: "

        
        match_error = colored("  Your ","red")+colored(f"{type}s","red",attrs=["bold"])+colored(" did not match","red")
        
        blank_error = colored("  Your ","red")+colored(f"{type}s","red",attrs=["bold"])+colored(" seem to be blank?","red")
        
        len_error = colored("  Your ","red")+colored(type,"red",attrs=["bold"])+colored(" must be at least ","red")
        len_error += colored(length,"yellow",attrs=["bold"])+colored(" characters long.","red")
        
        char_error = colored("  Your ","red")+colored(type,"red",attrs=["bold"])+colored(" must ","red")+colored("not","red",attrs=["bold"])
        char_error += colored(" contain spaces, single or double quotes or periods","red")+"\n"
        char_error += colored("  and, your passphrase ","red")+colored("must","red",attrs=["bold"])+colored(" contain at least 1 lowercase\n","red")
        char_error += colored("  uppercase, and special character.\n","red")

        error_list = {
            "len": len_error,
            "match": match_error,
            "char": char_error,
            "blank": blank_error,
        }

        while True:
            results = []
            pass1 = getpass(colored(first,"magenta"))
            pass2 = getpass(colored(second,"magenta"))

            try:
                if not compare_digest(pass1,pass2):
                    results.append("match")
            except:
                self.error_messages.error_code_messages({
                    "error_code": "usr-211",
                    "line_code": "invalid_passphrase_pass",
                })
        
            if not self.migrating_p12:
                if len(pass1) < length:
                    results.append("len")
                
                if not re.match(pattern, pass1) or not re.match(pattern, pass2):
                    results.append("char")
                    
                if "." in pass1 or "." in pass2:
                    results.append("char")
                
                if pass1 == '' or pass2 == '':
                    results.append("blank")
                
            valid = True
            for result in results:
                if "match" in result or "len" in result or "blank" in result or "char" in result:
                    if valid:
                        print("")
                    valid = False
                    print(error_list[result])
                    
            if valid == True:
                return pass1
                
            print("")


    def create_debian_user(self):
        if not self.quick_install:
            print("") # newline
            progress = {
                "text_start": "Adding new user",
                "brackets": self.username,
                "status": "creating",
                "status_color": "yellow",
            }
            self.functions.print_cmd_status(progress)

        bashCommand = f"openssl passwd -1 {self.password}"
        encrypt_passwd = self.functions.process_command({
            "bashCommand": bashCommand,
            "proc_action": "timeout"
        })
        bashCommand = f"useradd -p {encrypt_passwd} {self.username} -m -s /bin/bash"
        _ = self.functions.process_command({
            "bashCommand": bashCommand,
            "proc_action": "timeout"
        })

        if not self.quick_install:
            self.functions.print_cmd_status({
                **progress,
                "status": "complete",
                "status_color": "green",
                "newline": True,
                "delay": .5
            })
            
            self.functions.print_cmd_status({
                **progress,
                "status": "running",
                "text_end": "to sudo group",
                "delay": .8
            })
        
        system(f"usermod -aG sudo {self.username} > /dev/null 2>&1")
        self.functions.set_system_prompt(self.username)
                     
        if not self.quick_install:
            self.functions.print_cmd_status({
                **progress,
                "status": "complete",
                "status_color": "green",
                "text_end": "to sudo group",
                "newline": True,
                "delay": 1,
            })
         
           
    def transfer_ssh_key(self):
        if not self.quick_install:
            self.functions.print_header_title({
            "line1": "SSH KEYS",
            "show_titles": False,
            "newline": "top",
            "clear": True,
            }) 
                     
            self.functions.print_paragraphs([
                ["There are",0], ["2",0,"yellow"], ["main",0,"cyan","underline"], ["ways to connection to VPS or bare metal servers.",2],
                
                ["1",0,"magenta","bold"], ["SSH KEY passphrase/keyphrase",1,"yellow"],
                ["2",0,"magenta","bold"], ["VPS admin user's password",2,"yellow"],
                
                ["IT IS HIGHLY RECOMMENDED YOU SETUP THIS VPS WITH SSH KEYS",2,"red","bold"],
                
                ["If you followed the provided instructions and are not an advanced user, you most likely setup your VPS with",0],
                ["SSH key",0,"yellow","bold"], ["pairs.",2],
            ])
            
            confirm = self.functions.confirm_action({
                "yes_no_default": "y",
                "return_on": "y",
                "prompt": "Did you use an SSH key pair?",
                "prompt_color": "magenta",
                "exit_if": False
            })
            if not confirm:
                return

            progress = {
                "text_start": "Transferring SSH key to",
                "brackets": self.username,
                "status": "transfer",
                "status_color": "yellow",
            }
            print("")
            self.functions.print_cmd_status(progress)
        
        self.file = "authorized_keys"
        dest_dir = f"/home/{self.username}/.ssh/"
        dest_dir_file = dest_dir+self.file
        src_dir_file = f"/root/.ssh/"+self.file
        disable_root_user = True
        warning = False
        
        end_status, end_color = "completed", "green"
        
        if not path.exists(dest_dir):
            makedirs(dest_dir)
            
        if path.isfile(f"/root/.ssh/{self.file}"):
            copyfile(src_dir_file,dest_dir_file)
        elif path.isfile(dest_dir_file):
            if not self.quick_install:
                self.functions.print_paragraphs([
                    ["",1], [f"Found the {self.username} user ssh key file already?",1,"yellow"],
                    ["Are you sure this is a new installation?",1,"red"],
                    ["nodectl will skip this step",1],
                ])            
        elif path.isfile(f"/root/.ssh/backup_{self.file}"):
            disable_root_user = False
            if self.quick_install:
                confirm, warning = True, False
            else:
                if self.quick_install:
                    confirm = True
                else:
                    self.functions.print_paragraphs([
                        ["",1],["Found the root user ssh key file was disabled?",0,"red"],
                        ["Are you sure this is a new installation?",1,"red"],
                        
                        [f"Do you want to transfer SSH key from the root user to the new {self.username} user?",1],
                    ])
                        
                    confirm = self.functions.confirm_action({
                        "yes_no_default": "n",
                        "return_on": "y",
                        "prompt": "Confirm:",
                        "exit_if": False
                    })  

                status = "skipped"
                status_color = "red"
                progress = {
                    "text_start": "removing",
                    "brackets": self.file,
                    "status": "running",
                    "status_color": "yellow",
                }
                self.functions.print_cmd_status(progress)    

            if confirm:
                try:
                    copyfile(f"/root/.ssh/backup_{self.file}",dest_dir_file) 
                    status = "complete"
                    status_color = "green"
                except:
                    self.log.logger.error("transfer ssh key -> unable to copy file -> skipping")

            if not self.quick_install:
                self.functions.print_cmd_status({
                    **progress,
                    "status": status,
                    "status_color": status_color,
                    "newline": True,
                })  
                warning = True if status == "skipped" else warning
            
        if warning and not self.quick_install:
            self.functions.print_paragraphs([
                ["",2], [" WARNING ",0,"white,on_magenta"], ["Installation was not able to find an",0,"red"],
                ["'authorized keys'",0,"yellow","bold"], ["file. Skipping step!",2,"red"],
                ["Are you sure this has not already been done?",1,"red"]
            ])
            end_status, end_color = "skipped", "red"
            
        # extra work for AWS instances - if on GCP or DO
        # this won't effect the file.
        # clean up the exit function in the file
        try:
            with open(dest_dir_file, 'r') as cur_file:
                filedata = cur_file.read()
        except:
            if not self.quick_install:
                self.error_messages.error_code_messages({
                    "error_code": "u-211",
                    "line_code": "not_new_install",
                    "extra": None,
                    "extra2": None
                }) 
            else:
                self.log.logger.error(f"transfer_ssh_key -> quick installer -> unable to read file [{dest_dir_file}]") 
        
        index = filedata.find('ssh-rsa')
        filedata = filedata[index:]
        
        with open(dest_dir_file,'w') as cur_file:
            cur_file.write(filedata)
            
        system(f"chown {self.username}:{self.username} {dest_dir_file} > /dev/null 2>&1")
        system(f"chmod 600 {dest_dir_file} > /dev/null 2>&1")

        if not self.quick_install:
            self.functions.print_cmd_status({
                **progress,
                "status": end_status,
                "status_color": end_color,
                "newline": True,
            })
        
        if disable_root_user:
            self.disable_root_user()
            
        # since we said "yes" to SSH verse password
        if self.quick_install:
            confirm = True
        else:
            self.functions.print_paragraphs([
                ["",1],[" Recommended ",0,"yellow,on_green","bold"], 
                ["During the installation",0], ["SSH",0,"blue","bold"], ["was chosen.",1],
                ["Do you want to disable username/password based authentication on this Node at the",0],
                ["Operating System level to improve security?",2],
            ])
            
            verb = "unchanged"
            
            confirm = self.functions.confirm_action({
                "yes_no_default": "y",
                "return_on": "y",
                "prompt": "Disable username/password access?",
                "exit_if": False
            })
        
        if confirm:
            self.cli_obj.ssh_configure({
                "command": "disable_user_auth",
                "argv_list": ["install"] if not self.quick_install else ["quick_install"],
                "do_confirm": False,
            })
            verb = "disabled"
            
        if not self.quick_install:
            self.functions.print_cmd_status({
                "text_start": "Username/Password authentication",
                "status": verb,
                "status_color": "green" if verb == "disabled" else "red"
            })


    def disable_root_user(self):
        # check for non-root users
        if self.quick_install:
            confirm = True
        else:
            self.functions.print_paragraphs([
                ["",1], ["The root user should not have access via",0], ["SSH",0,"yellow","bold"], ["nor should AWS's default",0],
                ["ubuntu",0,"yellow","bold"], ["user or other provider's",0], ["admin",0,"yellow","bold"],
                ["users.",2],
                
                ["Access should be disabled so that",0,"white","bold"], ["only",0,"white","bold"], ["the",0,"white","bold"],
                ["Node Administrator",0,"white","bold"], ["has access to this VPS with the",0,"white","bold"], 
                [self.username,0,"yellow","bold"], ["user.",2,"white","bold"],
                
                ["This is recommended.",2,"magenta","bold"],                
            ])
        
            confirm = self.functions.confirm_action({
                "yes_no_default": "y",
                "return_on": "y",
                "prompt": "Disable SSH access to these root and special accounts?",
                "exit_if": False
            })

        if not confirm: return
        if not self.quick_install:
            progress = {
                "text_start": "Disable",
                "brackets": "SSH",
                "text_end": "for special accounts",
                "status": "disable",
                "status_color": "yellow",
            }
            self.functions.print_cmd_status(progress)
        
        possible_users = {
            "admin": False, 
            "ubuntu": False
        }
        
        for poss_user,value in possible_users.items():
            bashCommand = f"id -u {poss_user}"
            is_userid = self.functions.process_command({
                "bashCommand": bashCommand,
                "proc_action": "poll"
            })
            try:
                int(is_userid.strip("\n"))
            except:
                pass
            else:
                possible_users[poss_user] = True
                
        try:
            do_confirm = False if self.cli_obj.command_obj["caller"] == "installer" else True
        except:
            do_confirm = True
        if self.quick_install: do_confirm = False

        self.cli_obj.ssh_configure({
            "command": "disable",
            "argv_list": ["install"] if not self.quick_install else ["quick_install"],
            "do_confirm": do_confirm,
        })
        
        end_status = "complete"
        end_color = "green"
        for poss_user,value in possible_users.items():        
            if value is True:
                if "ubuntu" in poss_user and path.isfile("/ubuntu/.ssh/authorized_keys"):
                    try:
                        system(f"mv /home/ubuntu/.ssh/{self.file} /home/ubuntu/.ssh/backup_{self.file} > /dev/null 2>&1")
                    except:
                        if not self.quick_install:
                            cprint("  could not move ubuntu ssh key file","red")
                        end_status = "partial",
                        end_color = "yellow"
                elif "admin" in poss_user and path.isfile("/admin/.ssh/authorized_keys"):
                    try:
                        system(f"mv /home/admin/.ssh/{self.file} /home/admin/.ssh/backup_{self.file} > /dev/null 2>&1")
                    except:
                        if not self.quick_install:
                            cprint("  could not move admin ssh key file","red")
                        end_status = "partial",
                        end_color = "yellow"
                else:
                    if end_status != "complete":
                        end_status = "skipped"
                        end_color = "red"                    

        if not self.quick_install:
            self.functions.print_cmd_status({
                **progress,
                "status": end_status,
                "status_color": end_color,
                "newline": True,
            })

            
if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")  
  
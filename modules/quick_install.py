from os import get_terminal_size 
from time import sleep
from types import SimpleNamespace
from termcolor import colored
from concurrent.futures import ThreadPoolExecutor


class QuickInstaller():

    def __init__(self,parent):
        self.parent = parent['parent']
        self.options = self.parent.options 
        self.log = self.parent.log
        self.log_key = "main"
        self.terminate_program = False
        self.hash_marks = SimpleNamespace()
        self.setup_progress_bar()


    def setup_progress_bar(self):
        self.steps = [
            ("Initializing",None,"init"),
            ("Handle Existing Configurations",self.parent.handle_existing,"hec"),
            ("Obtain Install Parameters",self.parent.handle_option_validation,"hop"),
            ("Initialize Node Configuration",(self.parent.build_config_file,"skeleton"),"bnc1"),
            ("Building Node Configuration",(self.parent.build_config_file,"defaults"),"bnc2"),
            ("Updating Distribution OS",self.parent.update_os,"upd"),
            ("Installing Dependencies",self.parent.process_distro_dependencies,"dep"),
            ("Download Tessellation Protocol Binaries",self.parent.download_binaries,"bin"),
            ("Setting Up Swap File",self.parent.make_swap_file,"swp"),
            ("Setting Up Node Administration",self.parent.setup_user,"usr"),
            ("Handling Protocol Structure",self.parent.create_dynamic_elements,"dyn"),
            ("Generating P12 File",(self.parent.p12_generate_from_install,True),"p12"),
            ("Populating Configuration",(self.parent.build_config_file,"p12"),"pc1"),
            ("Finalizing Configuration",self.parent.setup_new_configuration,"pc2"),
            ("Building Services",self.parent.populate_node_service,"ser"),
            ("Handling SSH Security",(self.parent.setup_user,"ssh"),"ssh"),
            ("Setup Auto Complete",(self.parent.handle_auto_complete),"ac"),
            ("Handling Encryption Services",self.parent.p12_encrypt_passphrase,"enc"),
            ("Completing Installation",None,"cinst"),
        ] 

        keys = ["start","end","p_start","p_end"]
        hash_marks = {key: 0 for key in keys}
        self.hash_marks = SimpleNamespace(**hash_marks)
        self.hash_marks.max_length = max(len(s[0]) for s in self.steps)


    def quick_install(self):
        self.quick_execute()


    def quick_execute(self):
        if not self.options.quiet: 
            self.parent.print_main_title()
        for n, t_step in enumerate(self.steps):
            desc = t_step[0]
            code = t_step[2]
            self.log.logger[self.log_key].debug(f"quick-install --> {desc} | [{code}]")
            if isinstance(t_step[1],tuple):
                funct = t_step[1][0]
                parm = t_step[1][1]
            elif t_step[1] == None:
                funct = None
                parm = None
            else:
                funct = t_step[1]
                parm = None
            if self.options.quiet:
                self.quiet_install(funct,parm)
            else:
                self.handle_percent_hashes(t_step,desc,funct,parm,code,True)
                if n > 0: 
                    self.handle_percent_hashes(t_step,desc,funct,parm,code,False)

    
    def quiet_install(self,funct,parm):
        if funct == None: return
        try:
            if parm == None: 
                funct()
            else: 
                funct(parm)
        except Exception as e:
            self.log.logger[self.log_key].error(f"quick_installer -> during quiet install -> error encountered, logging and attempting to continue | error [{e}]")


    def handle_percent_hashes(self,t_step,desc,funct,parm,code,initial):
        console_size = get_terminal_size()
        cut_percent = .65
        if console_size.columns > 150:
            cut_percent = .55
        if console_size.columns > 175:
            cut_percent = .45
        columns = int(console_size.columns*cut_percent)

        percent_is = self.steps.index(t_step)+1
        percent_of = len(self.steps)-1
        percentage = percent_is/percent_of*100
        if percentage > 100: percentage = 100
        threading = True

        metagraph = self.parent.options.cluster_config
        if not metagraph:
            metagraph = "preparing"
        elif metagraph == "hypergraph":
            metagraph = self.parent.options.environment

        self.parent.functions.print_paragraphs([
            [f"nodectl installing [",0,"blue","bold"],
            [metagraph,0,"cyan","bold"],
            [f"]",1,"blue","bold"],
        ])

        e_codes = ["dep","bin","cinst","enc","bnc1","hop"]
        if code in e_codes and not initial:
            threading = False
            self.parent.functions.print_clear_line()
            if code == "dep":
                self.parent.functions.print_paragraphs([
                    ["Dependencies can take a few minutes.",1,"yellow"]
                ])    
            elif code == "bin":
                self.parent.functions.print_paragraphs([
                    ["Fetching Tessellation binaries.",1,"yellow"]
                ])  
            if code == "hop":
                self.parent.functions.print_cmd_status({
                    "text_start": desc,
                    "status": "preparing",
                    "status_color": "yellow",
                    "newline": True,
                })
                self.parent.functions.print_clear_line(3)
                print(f"\033[3A", end="", flush=True)

        if code == "p12" and self.parent.options.existing_p12:
            desc = desc.replace("Generating","Handling") 
        
        if not initial:
            with ThreadPoolExecutor() as executor:
                if threading:
                    self.parent.functions.status_dots = True
                    _ = executor.submit(self.parent.functions.print_cmd_status,{
                        "text_start": desc,
                        "dotted_animation": True,
                        "status": "installing",
                        "status_color": "yellow",
                    })
                try:
                    if funct != None and not initial: 
                        if parm == None: funct()
                        else: funct(parm)
                except Exception as e:
                    self.log.logger[self.log_key].error(f"quick_installer -> error encountered, logging and attempting to continue | error [{e}]")
                    self.parent.close_threads()
                    
                self.parent.functions.status_dots = False 

            up_codes = ["dep","bin"]
            up = 0
            if code in up_codes and not initial:
                if code == "dep": up = len(self.parent.packages)+2
                self.parent.functions.print_clear_line(up,{"backwards":True})

            if code == "hop":
                print("")
                self.parent.functions.print_timer({
                    "seconds": 6,
                    "step": -1,
                    "phrase": "Starting",
                    "end_phrase": "ctrl+c to cancel",
                    "status": "Preparing",
                    "p_type": "cmd",
                })
                self.parent.print_main_title()
                print("")
                self.parent.functions.print_cmd_status({
                    "text_start": "Finishing user input",
                    "status": "pausing",
                    "status_color": "green",
                })

        try:
            self.hash_marks.end = int((percentage/100)*columns)
            self.hash_marks.p_end = int(percentage)
            self.parent.functions.print_clear_line()

            for hash in range(self.hash_marks.start+1, self.hash_marks.end+1):
                step_str = colored(f'  {desc}',"green")

                if self.hash_marks.p_start > 100: self.hash_marks.p_start = 100
                p_percent = colored(f"{self.hash_marks.p_start}%","cyan",attrs=["bold"])

                print(step_str)
                print(colored("  [","blue",attrs=["bold"]),end=" ")
                hash_line = colored("#","yellow")*hash+" "+p_percent+" "+"." * ((columns-2) - hash)

                print(hash_line,end=" ")
                print(colored("]","blue",attrs=["bold"]))

                sleep(.1)

                print(f'\x1b[2A', end='')

                if initial: 
                    print(f'\x1b[1A', end='')
                    return
                
                self.hash_marks.p_start = self.hash_marks.p_start+1

            while self.hash_marks.p_start < self.hash_marks.p_end+1:
                p_percent = colored(f"{self.hash_marks.p_start}%","cyan",attrs=["bold"])
                print(f"{step_str} .... {p_percent}")
                self.hash_marks.p_start = self.hash_marks.p_start+1
                print(f'\x1b[1A', end='')
                sleep(.25)
            self.hash_marks.start = self.hash_marks.end

        except ZeroDivisionError:
            self.log.logger[self.log_key].error(f"quick_installer - handle_percent_hashes -attempting to derive hash progress indicator resulted in [ZeroDivisionError]")
        
        sleep(.5)
        reset_lines = 1
        print(f'\x1b[{reset_lines}A', end='')


    def handle_option_validation(self,option):
        self.parent.user.keep_user = False
        self.parent.user.quick_install = True
        if option == "user" and not self.parent.options.user: 
                self.parent.options.user = self.parent.user.username = "nodeadmin"
                if not self.options.quiet:
                    self.parent.print_cmd_status("Admin user","user",True)
        if option == "p12_destination_path":
            if not self.parent.options.p12_destination_path:
                self.parent.options.p12_destination_path = f"/home/{self.parent.options.user}/tessellation/{self.parent.options.user}-node.p12"
        if option == "p12_alias" and not self.options.p12_alias:
            if not self.parent.options.p12_migration_path:
                self.parent.options.p12_alias = f"{self.parent.options.user}-alias"
                if not self.options.quiet:
                    self.parent.print_cmd_status("P12 alias","p12_alias",True)
        if option == "p12_passphrase":
            self.parent.p12_generate_from_install()
        if option == "cluster-config":
            if not self.options.quiet:
                self.parent.print_cmd_status("metagraph","metagraph",True)


if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")  
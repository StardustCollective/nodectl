from os import system
from sys import exit
from termcolor import colored, cprint
from types import SimpleNamespace

from .logger import Logging

class Error_codes():
    
    def __init__(self,functions,debug=False):
        self.log = Logging()
        self.debug = debug
        self.functions = functions
        try: self.functions.test_valid_functions_obj()
        except:
            # exception for config_obj send instead of functions obj
            from ..functions import Functions
            self.functions = Functions(self.functions)

    def error_code_messages(self,command_obj):
        # error_code,line_code=None, extra=None, extra2=None:
        var = SimpleNamespace(**command_obj)
        var.extra = command_obj.get("extra",False)
        var.extra2 = command_obj.get("extra2",False)
        
        self.error_code = var.error_code
        self.print_error("start") if self.error_code else print("")
                
        if self.debug:
            print("error debugs:",var.error_code,var.line_code,var.extra,var.extra2)
            return
        
        if var.error_code == None:
            self.functions.print_paragraphs([
                ["Are you sure this was a clean installation?",2,"red","bold"],
                ["Tessellation critical files are missing.",2],
            ])
            
        elif "not_new_install" in str(var.line_code):
            self.functions.print_paragraphs([
                ["Are you sure this was a clean installation?",2,"red","bold"],
                ["Unable to process some information that is necessary for the installation of Tessellation to be successful.",2,"red","bold"],
                ["Suggestion:",0,"yellow","bold,underline"], ["Attempt a new installation with a clean image of a",0],
                ["Debian Based",0,"cyan","underline"],["OS.",2],
            ])

            
        elif "upgrade_needed" in str(var.line_code):
            self.log.logger.error(f"missing components to the VPS running nodectl.  This may not be a valid configuration? | error code: [{var.line_code}]")
            self.functions.print_paragraphs([
                ["Possible Upgrade Required!",1,"red","bold"],
                ["Necessary configuration files or directories are missing.",2,"red","bold"],
            ])
            if var.extra:
                self.functions.print_paragraphs([
                    [f"{var.extra}",2,"yellow","bold"],
                ])            
                if var.extra != "Missing Directories":
                    self.functions.print_paragraphs([
                        ["Legacy Node files were found on this VPS",2,"red","bold"], 
                    ])            
            self.functions.print_paragraphs([
                ["Please issue the following command to attempt to rectify the issue:",1,"magenta"],
                ["sudo nodectl upgrade",2,"cyan","bold"],
            ])            

            
        elif "upgrade_path_needed" in str(var.line_code):
            self.log.logger.error(f"missing components to the VPS running nodectl. The necessary upgrade path may not have been followed? This may not be a valid configuration? | error code: [{var.line_code}]")
            self.functions.print_paragraphs([
                ["Possible Upgrade Required!",0,"red"], ["This must be done by following the necessary upgrade path",1,"red","bold"],
                ["Necessary configuration components may be missing.",2,"red"],
                ["Please issue the following command to attempt to rectify the issue:",1,"magenta"],
                ["sudo nodectl upgrade_path",2,"cyan","bold"],
                ["Once the necessary path is found, please use the",0,"yellow"], ["wget",0,"cyan","bold"], ["followed by an",0,"yellow"],
                ["sudo nodectl upgrade",0,"cyan","bold"], ["to follow the necessary version path upgrades.",2],
            ])            


        elif var.line_code == "environment_error":
            self.log.logger.critical(f"missing metagraph environment variable, unable to continue")
            self.functions.print_paragraphs([
                ["nodectl attempted to start a command:",0,"red","bold"], [var.extra,2,"yellow,on_red","bold"],
                ["Please verify the Metagraph environment variable is correct or present.",2,"red","bold"],
                ["Are you sure you have a",0,"magenta"],["valid",0,"magenta"], ["environment requested in your command, loaded or configured?",2,"magenta"]
            ])
            if var.extra2:
                self.functions.print_paragraphs([
                    ["Environment Requested:",0], [var.extra2,2,"yellow","bold"]
                ])
                        
                        
        elif "upgrade_incompatibility" in str(var.line_code):
            self.log.logger.critical(f"Upgrade cannot continue because nodectl found multiple metagraph environment that is not supported by this version of nodectl: environment [{var.extra}]")
            self.functions.print_paragraphs([
                ["NODECTL VERSION INCOMPATIBILITIES POSSIBLE",2,"red","bold"],

                ["nodectl found metagraph environments installed on this Node that may not be supported by this version of nodectl.",0,"yellow"],
                ["In order to prevent undesirable results from the use of nodectl, the utility will exit here.",2,"red"],
                
                ["In order to continue, it is recommend to perform upgrade or revert the version of nodectl installed on this system with the proper version.",2],
                ["Please see the Constellation documentation portal for more details.",2],
                ["https://docs.constellationnetwork.io/validate/",2],
            ])

            
        elif "lb_not_up" in str(var.line_code):
            self.log.logger.critical(f"Edge Device [load balancer] does not seem to be up: {var.extra}")
            self.functions.print_paragraphs([
                ["HALTING ALL ACTIONS",2,"red","bold"],
                [var.extra,2,"yellow"],
                ["Health Status Check on the",0,"red","bold"], ["EDGE DEVICE",0,"yellow","underline,bold"], ["did not return a valid response.",2,"red","bold"],
                ["Possible Causes",2,"cyan","bold"],
                ["  - Your Node does not have Internet connection.",1],
                ["  - Source Node may not be reachable",1],
                ["  - Edge Node may not be reachable",2],
            ])

            
        elif "verification_failure" in str(var.line_code):
            self.log.logger.critical(f"Unable to verify nodectl properly, please review and try again | {var.extra}")
            self.functions.print_paragraphs([
                ["HALTING ALL ACTIONS",2,"red","bold"],
                ["A request to validate the authenticity of nodectl was interrupted or failed.  This does not indicate that",0],
                ["nodectl did not verify rather, nodectl could not obtain the proper elements to setup and",0],
                ["perform the validation process",2],
                ["Possible Reason:",0,"yellow"], [var.extra,2],
            ])

        elif "service" in str(var.line_code):
            self.log.logger.critical("attempt to access the service file seems to have failed.")
            self.functions.print_paragraphs([
                ["Something isn't quite right?",2,"red","bold"],
                ["Are you sure the",0,"red","bold"], ["Node",0, "yellow","bold,underline"],
                ["service is running?",0,"red","bold"],
                ["Please review the logs for more detailed information.",1,"red","bold"],
                ["  - app.log",1],
                ["  - nodectl.log",2],
                ["If this was a request against an external Node.",1,"red","bold"],
                ["  - Is the Node online?",2],
            ])
            if var.error_code == "service_join":
                self.functions.print_paragraphs([
                    ["You may not be joined to the",0,"red","bold"],["Global Layer0",0,"yellow","bold"],
                    ["or a",0,"red","bold"],["Metagraph?",2,"yellow","bold"],
                ])
            else:
                self.functions.print_paragraphs([
                    ["Are you sure you entered valid information?",2,"red","bold"],
                ])                
            self.functions.print_paragraphs([
                ["Attempt command for more details:",1,"blue","bold"],
                ["sudo nodectl status",2,"cyan","bold"],
            ])                
            
            
        elif "join_error" in str(var.line_code):
            self.log.logger.critical(f"attempt to join cluster failed | profile [{var.extra2}].")
            self.functions.print_paragraphs([
                ["Something went wrong during the join to profile:",0,"red","bold"],
                [var.extra2,2,"yellow","bold"],
            ])

            if var.extra:
                self.functions.print_paragraphs([
                    ["Join Error Code:",0,"white","bold"], [var.extra,2,"red"],
                ])   
            self.functions.print_paragraphs([
                ["You may not be joined to the",0,"red","bold"],["Global Layer0",0,"cyan","bold"],
                ["or a",2,"red","bold"],["Metagraph?",2,"cyan","bold"],
                ["Are you sure the",0,"red","bold"], ["Node",0,"yellow","bold,underline"],
                ["service is running?",2,"red","bold"]
            ])
            
        elif "new_connect_error" in str(var.line_code) or "max_retries" in str(var.line_code) or "connect_refused" in str(var.line_code):
            self.log.logger.critical(f"connection error during the join attempt [{var.extra}] | error: [{var.extra2}]")
            self.functions.print_paragraphs([
                ["Connection Error during join detected.",2,"red","bold"],
                ["Are you sure the",0,"red","bold"], ["Node service",0,"yellow","bold"], ["is running?",2,"red","bold"],
                ["  Profile:",0,"magenta","bold"],[var.extra,2,"yellow","bold"],
                ["See logs for error message returned from protocol.",2]
            ])
            
        elif "link_to_profile" in str(var.line_code):
            self.log.logger.critical(f"unable to retrieve port information for profile [{var.extra}] from source profile [{var.extra2}]")
            self.functions.print_paragraphs([
                ["Connection Link to Profile Error during join detected.",2,"red","bold"],
                ["Please verify that your configuration",0,"red","bold"], ["layer0_link",0,"yellow","bold,underline"],
                ["is setup properly",2,"red","bold"],
                ["       PROFILE:",0,"magenta","bold"], [var.extra,1,"yellow"],
                ["SOURCE PROFILE:",0,"magenta","bold"], [var.extra2,2,"yellow"],
            ])
            
            
        elif var.line_code == "api_error":
            extra2 = "unknown" if var.extra2 == None else var.extra2
            self.log.logger.critical(f"API timeout error detected.  url [{extra2}] nodectl terminating...")
            self.functions.print_paragraphs([
                ["Timed Out or Error encountered while waiting for API.",1,"red","bold"],
                ["An API call returned an invalid response.",2,"red","bold"],
                ["Possible other reasons could be service related? Are you sure the",0,"red","bold"],
                ["Node",0,"yellow","underline"], ["service(s) are running?",2,"red","bold"],
                ["Make sure your",0,"magenta"], ["firewall",0,"magenta","underline"], ["has the proper TCP ports opened.",2,"magenta"],
            ])
            if var.extra != None:
                self.functions.print_paragraphs([
                    ["Profile:",0,], [var.extra,2,"yellow","bold"],
                ])
            
            
        elif var.line_code == "seed-list":
            self.log.logger.critical("attempt to download seed list failed or resulted in a zero file size.")
            self.functions.print_paragraphs([
                ["Something isn't quite right?",2,"red","bold"],
                ["nodectl",0,"red","bold,underline"], ["was unable to download the seed-list associated with the Global Layer0",2,"red","bold"],
                ["Please check your outbound Internet access and try again later.",2,"yellow","bold"],
            ])
            
            
        elif var.line_code == "off_network":
            self.log.logger.critical(f"attempt to issue command that returned empty values. Is the Node on the network?")
            self.functions.print_paragraphs([
                ["Something isn't quite right?",2,"red","bold"],
                ["nodectl",0,"red","bold,underline"], ["was unable to access data associated with the command entered?",1,"red","bold"],
                ["Are you sure this Node is on the HyperGraph?",2,"red","bold"],
                ["Network Unreachable",2,"bold","magenta"]
            ])
            
            
        elif var.line_code == "join":
            self.log.logger.critical("attempt to join cluster failed.")
            self.functions.print_paragraphs([
                ["Something isn't quite right?",2,"red","bold"],
                ["nodectl",0,"red","bold,underline"], ["detected you are not",0,"red","bold"], ["properly joined to the",0,"red","bold"],
                ["Hypergraph.",2,"yellow","bold"],
                ["Are you sure your",0,"red","bold"], ["Node",0,"yellow","bold,underline"], 
                ["is joined to the current network?",2,"red","bold"],
                ["try command:",1,"yellow"], ["sudo nodectl join -p <profile_name>",2]
            ])            
    
            
        elif var.line_code == "ssh_keys":
            self.log.logger.critical("authorized_keys file missing in the root user directory.")
            self.functions.print_paragraphs([
                ["authorized keys",0,"yellow","underline"], ["file is missing in the root user directory.",2,"red","bold"],
                ["Please verify the file is present; as well as, please check your",0,"red","bold"], ["firewall",0,"red","bold,underline"],
                ["settings.",2,"red","bold"]
            ])            
            
            
        elif var.line_code == "invalid_passphrase":
            self.log.logger.critical("p12 passphrase entered incorrectly too many times!")
            self.functions.print_paragraphs([
                ["P12",0,"yellow","bold"], ["passphrase",0,"red","bold,underline"], ["was incorrectly entered.",2,"red","bold"],
                ["Please",0,"red","bold"], ["verify",0,"yellow","bold"], ["these passphrase attempts were made by an authorized Node Operator.",2,"red","bold"],
                ["Please be diligent and review your Node's security, and other settings!",2,"magenta","bold"],
                ["Try issuing command:",1,"yellow"],
                ["sudo nodectl sec",2],
            ])            
            
        elif var.line_code == "invalid_passphrase_pass":
            self.log.logger.critical("password validation check failed.")
            self.functions.print_paragraphs([
                ["While comparing passphrases or passwords or validation, an invalid character(s) that did not match an ASCII value",0,"red"],
                ["was detected?",0,"red"],
            ])            
            
        elif var.line_code == "invalid_passphrase_pass":
            self.log.logger.critical("password validation check failed.")
            self.functions.print_paragraphs([
                ["While comparing passphrases or passwords or validation, an invalid character(s) that did not match an ASCII value",0,"red"],
                ["was detected?",0,"red"],
            ])            
            
            
        elif var.line_code == "invalid_address":
            self.log.logger.critical(f"attempt to use an invalid {var.extra} address detected [{var.extra2}]")
            self.functions.print_paragraphs([
                ["Invalid",0,"red","bold"], [var.extra,0,"red","bold,underline"], ["address may have been entered.",2,"red","bold"],
                ["Please",0,"red","bold"], ["verify",0,"yellow","bold"], ["the address entered",2,"red","bold"],
                ["Address Entered:",0,"yellow","bold"],[var.extra2,2],
            ])            
            
            
        elif var.line_code == "term":
            self.log.logger.critical("invalid terminal type, exited program")
            self.functions.print_paragraphs([
                ["Invalid terminal type detected:",0,"yellow"], [var.extra,2,"magenta","bold"],
                ["Please enable a",0], ["xterm",0,"yellow","bold"], ["terminal session to continue.",2],
            ])            
            
            
        elif var.line_code == "ip_not_found":
            self.log.logger.warn("unable to find the external IP address of the Node, there may be internet access issues ensuring, exited program")
            self.functions.print_paragraphs([
                ["In an attempt to search the Metagraph with an IP address,",0,"red"],
                [var.extra,0,"yellow","bold"],
                ["is invalid or not found, please check this",0,"red"] ,["ip address",0,"red","underline"], ["and try again.",2,"red"],
            ])            
            
            
        elif var.line_code == "version_fetch":
            self.log.logger.warn("unable to fetch version, exited program")
            self.first_line = f"Tessellation attempted version fetch failed"
            self.second_line = "Please report this to a Constellation Network Administrator"
            
                        
        elif var.line_code == "sudo_error":
            self.log.logger.critical(f"permissions error detected | {var.extra}")
            self.functions.print_paragraphs([
                ["nodectl attempted to perform actions as a none sudo user.",2,"red","bold"],
                ["Please try again with the correct user permissions.",2,"magenta","bold"]
            ])
            
            
        elif var.line_code == "peer_count_error":
            self.log.logger.critical("tessellation attempted check peers and failed, this may be an API error, or external access error.")
            self.functions.print_paragraphs([
                ["Tessellation attempted check peers and failed.",2,"red","bold"],
                ["This Node's network configuration may be incorrect, please check profile configuration.",2,"magenta"],
            ])
            
            
        elif var.line_code == "node_id_issue":
            self.log.logger.critical("tessellation attempted to extract the node id from the configuration p12 private key file:  p12 password is wrong, p12 private key is corrupted, key store location is wrong, or p12 private key file name in the configuration is wrong.")
            self.functions.print_paragraphs([
                ["Tessellation attempted to extract and derive the",0,"red","bold"], ["nodeid",0,"magenta","bold"],
                ["from this Node unsuccessfully.",2,"red","bold"],
                
                ["This Node's network configuration may be incorrect, please check profile configuration. You may have corrupted binaries?",2,"magenta"],
                
            ]) 
            if var.extra == "invalid":           
                self.functions.print_paragraphs([                
                    ["Hints:",1,"yellow","bold"],
                    ["  - node id must be 128 byte public key hex encoded value",2],
                ])   
            if var.extra == "external":
                self.functions.print_paragraphs([                
                    ["Hint:",0,"yellow","bold"],
                    ["This node may not be online at the moment.",2],
                ])                  
            else:         
                self.functions.print_paragraphs([                
                    ["Hints:",1,"yellow","bold"],
                    ["  - p12 passphrase is correct",1],
                    ["  - p12 keystore location is correct",1],
                    ["  - p12 name is correct",1],
                    ["  - p12 alias is correct",1],
                    ["  - p12 private key file is corrupted",2],
                    ["  - try: sudo nodectl refresh_binaries",2],
                ])            
            if var.extra == "config":
                self.functions.print_paragraphs([
                    ["Configuration setup failed",2,"red","bold"]
                ])
            
            
        elif var.line_code == "invalid_tcp_ports":
            self.log.logger.error("invalid TCP ports found, displaying error message to user and exiting")
            self.functions.print_paragraphs([
                ["nodectl found an invalid TCP port or port range has been used and cannot continue.",2,"red","bold"],
                ["ports:",0,"white","bold"], [var.extra,2,"yellow","bold"],
            ])
            
            
        elif var.line_code == "invalid_layer":
            self.log.logger.error("invalid blockchain layer found, displaying error message to user and exiting")
            self.functions.print_paragraphs([
                ["nodectl found an invalid blockchain layer inputted",2,"red","bold"],
                ["layer:",0,"white","bold"], [var.extra,2,"yellow","bold"],
            ])            
            
            
        elif var.line_code == "input_error":
            self.log.logger.warn(f"invalid input from user was entered for option [{var.extra}], exited program.")
            self.functions.print_paragraphs([
                ["nodectl found an invalid input entered by the Node Operator.",2,"red","bold"],
                ["Please try again later or issue the",0], ["help",0,"yellow","bold"], 
                ["option with the command in question for extended details",2],
            ])  
            if var.extra:
                self.functions.print_paragraphs([
                    ["option or hint: ",0], [var.extra,2,"yellow"]
                ])       
            
        
        elif var.line_code == "invalid_search":
            self.log.logger.warn(f"invalid search attempted could not continue.")
            self.functions.print_paragraphs([
                ["System has attempted to access a file to perform a search that returned an empty value.",0,"red"],
                ["or",0,"yellow","bold"], ["the search request was unable to properly find the item or log entry requested.",1,"red"],
                ["Operation cancelled to avoid unexpected errors | Please try again later.",1,"magenta"],
            ]) 
            if var.extra:
                self.functions.print_paragraphs([
                    ["hint: ",0], [var.extra,2,"yellow"]
                ])   
                
                                     
        elif var.line_code == "file_not_found":
            self.log.logger.warn(f"invalid file location or name [{var.extra}], exited program.")
            self.functions.print_paragraphs([
                ["System has attempted to access a file that does not exist.",2,"red","bold"],
                [" File: ",0,"blue,on_yellow","bold"], [var.extra,2],
                ["Operation cancelled to avoid unexpected errors | Please try again later.",2,"magenta"],
            ])     
            if var.extra2:
                self.functions.print_paragraphs([
                    [" Hint: ",0,"blue","bold"], [var.extra2,2,"yellow"],
                ])                         
                        
            
        elif var.line_code == "dependency":
            self.log.logger.critical(f"an error processig a command outside the realm of nodectl was encounted [{var.extra2}], exited program.")
            self.functions.print_paragraphs([
                ["An error has occured while attempting to process a distribution system command.",2,"red","bold"],
                [" Missing Component: ",0,"blue,on_yellow","bold"], [var.extra,2],
                ["Operation cancelled to avoid unexpected errors.",2,"magenta"],
                ["Try installing the dependency and try again",1],
                ["sudo apt install",0,"yellow"], [var.extra,2,"yellow"],
            ])            
            
            
        elif var.line_code == "invalid_output_file":
            self.log.logger.warn(f"invalid file location or name [{var.extra}], exited program. file not allowed")
            self.functions.print_paragraphs([
                ["System detected an attempt to output data to an invalid output location.",0,"red","bold"],
                ["nodectl is setup to output files to the default uploads directory.  If an alternate directory location is desired, please modified the",0,"red","bold"],
                ["nodectl configuration via:",0,"red","bold"],["sudo nodectl configure",2],
                [" File: ",0,"blue,on_yellow","bold"], [var.extra,2],
                ["Operation cancelled to avoid unexpected errors.",2,"magenta"],
            ])            
            
            
        elif var.line_code == "invalid_file_format":
            self.log.logger.warn(f"invalid file format for file [{var.extra}], exited program. file could not be processed")
            self.functions.print_paragraphs([
                ["System detected an attempt import data from a file or a file.",0,"red","bold"],
                ["nodectl is setup to access a file that may have been altered manually or is corrupted.",0,"red","bold"],
                ["Please contact a System Administrator for assistance:",0,"red","bold"],["sudo nodectl configure",2],
                [" File: ",0,"blue,on_yellow","bold"], [var.extra,2],
                ["In some cases you can attempt to remove the file and have nodectl recreate it for you.",2,"magenta"],
            ])            
            
            
        elif var.line_code == "profile_error":
            if var.extra is None: var.extra = "unknown"
            self.log.logger.critical(f"invalid profile entered for execution [{var.extra}]")
            self.functions.print_paragraphs([
                ["Tessellation attempted load a non-existent profile -",0,"red","bold"], [var.extra,2,"yellow,on_red","bold"],
                ["Network configuration may be incorrect, please check profile or configuration",2,"red","bold"],
                ["Are you should you have a",0,"magenta"],["valid",0,"magenta","underline"], ["profile loaded or configured?",2,"magenta"]
            ])
            
            
        elif var.line_code == "open_file":
            self.log.logger.critical(f"unable to read [{var.extra}]")
            self.functions.print_paragraphs([
                ["Something went wrong attempting to read or open a necessary file.",2,"red","bold"],
                ["file:",0,"white","bold"], [var.extra,2,"yellow"],
            ])            

            if var.extra == "id_hex_file":
                self.functions.print_paragraphs([
                    ["This error occurred while attempting to export the",0,"red"], ["p12",0,"yellow","bold"],
                    ["private key file.",2,"red"],
                    ["There may be an invalid character in your passphrase or you may",0,"red"], ["not",0,"red","underline"],
                    ["have a valid",0,"red"], ["p12",0,"yellow","bold"], ["file on your system.",2,"red"],
                ])
            elif var.extra == "cn-node": 
                self.functions.print_paragraphs([  
                    ["Are you sure you have a valid cn-node configuration file on your system?",2,"red","bold"]
                ])                   
            self.functions.print_paragraphs([
                ["Please review your",0], ["cn-config.yaml",0,"yellow","bold"], ["file, before continuing.",2]
            ]) 
            
            
        elif var.line_code == "download_yaml":
            self.log.logger.critical(f"unable to download valid configuration file [cn-config.yaml]")
            self.functions.print_paragraphs([
                ["nodectl installer attempted to download an invalid or non-existent yaml pre-defined configuration.",0,"red"],
                ["The installer cannot continue, please try installation again or seek assistance from the official Constellation Discord channel.",0,"red"],
            ])
            
        elif var.line_code == "config_error":
            self.log.logger.critical(f"unable to load configuration file [cn-config.yaml]")
            if var.extra == "existence":
                self.functions.print_paragraphs([
                    ["nodectl attempted load a non-existent configuration!",1,"red","bold"],
                    ["Please verify that your configuration file is located in the proper directory.",2,"red"],
                    ["directory location:",0,"white","bold"], ["/var/tessellation/nodectl",2],
                    ["This is important to allow the file to properly load.",2,"red","bold"],
                    ["To correct error, issue:",0,"magenta"], ["sudo nodectl configure",2]
                ])
            if var.extra == "format" or var.extra2 == "existence":
                self.functions.print_paragraphs([
                    ["nodectl attempted to load an invalid configuration!",1,"red","bold"],
                    ["Please verify that your configuration",0,"red"], ["yaml",0,"red","underline"],
                    ["file is in the proper format.",2,"red"],
                    
                    ["This error may have been caused by",0,"magenta"], ["manual intervention",0, "red","underline"],
                    ["of the configuration file. Manual editing on the configuration file should be left to advanced Administrators only.",2,"magenta"],
                    ["The configuration file may have been corrupted due to an interruption during configuration by nodectl.",2,"magenta"],
                    ["Alternatively, it is advised to attempt to correct issues via nodectl's configure option or use nodectl to build a new configuration.",1,"magenta"],
                    ["Use command:",0,"yellow"], ["sudo nodectl configure",2],
                ])
            if var.extra == "configurator":
                self.log.logger.error(f"configurator error found [{extra2}]")
                self.functions.print_paragraphs([
                    ["During an attempt to clean up old directory structure elements",1,"red"],
                    ["an unrecoverable issue was encountered by nodectl.",2,"red"],
                    ["It is suggested that you join the appropriate Discord channel and",0,"magenta"],
                    ["and contact a Constellation Administrator.",2,"magenta"],
                ])
           
        self.print_error()
           
                      
    def print_error(self,when="end"):
        if when == "start":
            self.functions.print_paragraphs([
                ["",1], [" OOPS! CRITICAL ERROR ",1,"red,on_yellow"], 
                ["Terminating",0], ["nodectl",0,"cyan","underline"], ["utility or current thread process.",2],
                ["Error Code:",0,"white","bold"], [self.error_code,2,"yellow","bold"],
            ])
            return
        
        self.functions.print_paragraphs([
            ["If you feel this message is in error, please contact an administrator for support.",2,"blue","bold"],
            ["TERMINATING",0,"yellow,on_red","bold"], ["nodectl",0,"yellow","bold"]                           
        ])

        exit("  nodectl critical error detected")  

        
if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")        
   
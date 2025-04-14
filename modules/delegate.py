import json

from time import sleep
from types import SimpleNamespace
from getpass import getpass
from termcolor import colored, cprint
from sys import exit

from modules.crypto.crypto_class import NodeCtlCryptoClass

class DelegatedStaking:    
    def __init__(self,command_obj):
        self.config_obj = command_obj["config_obj"]
        self.profile = command_obj["profile"]
        self.action = command_obj["action"]
        
        self.ds_config = SimpleNamespace(**self.config_obj["global_elements"]["delegated_staking"])
        self.log = command_obj["log"]
        self.log_key = "main"
        self.log.logger[self.log_key].info("Delegated staking class obj initialized.")

        self.error_messages = command_obj["error_messages"]
        self.debug = False
        self.error = False

        self.functions = command_obj["functions"]
        
        self.data = None
        self.verbose = False
        self.dbl_verbose = False
        self.update_required = False
        self.first_run = False
        self.update_executed = False
        self.spacing_value = 18

        self._validate_config()
        self.set_crypto()
        self.set_nodeid()
        self.set_init_values()


    def _log_msg(self,level,msg):
        msg = f"DelegatedStaking --> {msg}"
        self.functions.handle_log_msg(level,msg)

    # ==== primary actions ====

    def general_router(self):
        self.print_title(f"REQUESTED {self.action}")
        self.handle_payload_init()
        self.handle_last_ref_init()
        self.handle_compare_last_ref()


    def update(self):
        self.general_router()

        if not self.update_required:
            self.print_no_update_needed()

        self.handle_final_payload_build()
        self.functions.print_header_title({
            "line1": "STATUS BEFORE UPDATE",
            "single_line": True,
            "newline": "bottom",
        })
        self.print_value_comparison() 
        self.print_disable_warning()
        self.get_p12p()

        self.crypto.p12p = self.p12p
        self.crypto.data = self.payload_value
        
        self.crypto.extract_p12_keys()
        self.crypto.load_keys()

        self.functions.print_cmd_status({
            "text_start": "p12 authentication",
            "status": "validated",
            "status_color": "green",
            "newline": True,
        })
        
        self.crypto.serialize_brotli()
        self.crypto.hash_data()
        self.crypto.sign_data()
        self.crypto.set_signature_hex()

        if self.crypto.verify_signature():
            self.error = self.crypto.error
            self.handle_error("crypto_error","del-67")

        if self.debug or self.dbl_verbose: 
            self.crypto.debug = True
        self.crypto.log_data()

        self.handle_final_payload_build()
        self.send_payload()

        self.dbl_verbose = False
        self.verbose = False # do not reprint payload if verbose is enabled

        cprint("  Pausing to allow network to process.","yellow")
        self.functions.print_timer({
            "seconds": 3,
            "phrase": "Pausing",
            "p_type": "cmd",
            "step": -1,
            "end_phrase": f"of {colored('3','yellow',attrs=['bold'])} {colored('seconds','magenta')}"
        })
        print("")
        self.status() # verify all is well


    def remove(self):
        self.print_title(f"REQUESTED {self.action}")
        self.print_disable_warning()


    def status(self):
        self.general_router()
        self.handle_final_payload_build()
        self.print_value_comparison()
        exit(0)    


    def send_payload(self):
        session = self.functions.set_request_session()
    
        try:
            response = session.post(self.ds_url, json=self.complete_payload)
        except Exception as e:
            self._log_msg("error",f"Attempt to send payload to the metagraph failed | [{e}]")
            self.error = f"{e}"
            self.handle_error("api_error","del-97")
        else:
            error = False
            try:
                if response.status_code == 200:
                    response_text = str(response.reason)
                else: 
                    error = str(response.text)
            except Exception as ee:
                error = str(ee)

            if error:
                self._log_msg("error",f"payload was not sent to the metagraph layer0 | failed with error [{error}]")
                self.functions.print_paragraphs([
                    ["",1],[" ERROR ",0,"yellow,on_red"], 
                    ["There was an error attempting to send the delegated staking to the metagraph. Please see the logs for further details.",1,"red"],
                    ["Delegated staking",0,"magenta"], ["not",0,"red","bold"], ["processed.",2,"magenta"],
                ])
                exit(1)
            else:
                self.functions.print_paragraphs([
                    ["",1],[" SUCCESS ",0,"red,on_green"], 
                    ["You have successfully submitted your delegated staking update to the metagraph!",2,"green","bold"],
                ])
                self._log_msg("info",f"payload sent to the metagraph layer0 | [{self.ds_url}] | [{response_text}]")


    # ==== set methods ====

    def set_init_values(self):
        self.compare_values = {
            "name": [False,self.ds_config.name],
            "description": [False,self.ds_config.description],
            "rewardFraction": [False,self.ds_config.rewardFraction],
        }
        self.ds_url = f"{self.functions.default_edge_point['uri']}/node-params/"

        try:
            self.wallet = self.config_obj["global_elements"]["nodeid_obj"][f"{self.profile}_wallet"]
        except:
            self.handle_error("version_fetch","del-120")


    def set_nodeid(self):
        self.nodeid = self.config_obj["global_elements"]["nodeid_obj"][self.profile]
    
    
    def set_crypto(self):
        try:
            self.crypto = NodeCtlCryptoClass({
                "log": self.log,
                "config_obj": self.config_obj,
                "error_messages": self.error_messages,
                "profile": self.profile,
            })
        except Exception as e:
            self._log_msg("error","Unable to build nodectl's crypto library.")
        else:
            self._log_msg("info","Successfully built nodectl's crypto library.")


    # ==== get methods ====

    def get_p12p(self):
        self.functions.print_paragraphs([
            [" IMPORTANT ",0,"red,on_yellow"], ["Due to the nature of this operation involving",0],
            ["$DAG",0,"yellow"], ["digital currency transfers, transactions, and manipulations,",0],
            ["authentication is required before proceeding.",2],

            ["You are being prompted to enter your",0], ["p12 passphrase",0,"yellow"], 
            ["to verify your identity and secure the transaction process. This step ensures that only",0],
            ["authorized users can execute sensitive operations.",2],

            ["Please have your",0], ["p12 passphrase",0,"yellow"], ["readily available to continue.",2],
        ])
        p12p = getpass(colored("  Please enter your p12 passphrase: ","magenta"))
        self.p12p = p12p.strip()


    # ==== handlers ====

    def handle_compare_last_ref(self):
        if self.first_run and self.update_executed: return

        url = f"{self.ds_url}{self.nodeid}"

        for _ in range(1,3):
            response = self.functions.get_from_api(url,"yaml")
            if response == "Not Found":
                self._log_msg("warning","Response from lookup resulted in a [404 not found] this may be because the node has not yet participated in an active delegated staking session. You may safely ignore this message unless other issues arise.")
                sleep(1)
            else:
                break
        
        if response == "Not Found":
            if self.action == "status":
                self.print_not_configured_message()
            self.print_first_run()
            self.first_run = True
            self.update_required = True
            self.payload_value["parent"]["ordinal"] = 0
            self.payload_value["parent"]["hash"] = "0000000000000000000000000000000000000000000000000000000000000000"
            self.compare_values["name"][0] = True
            self.compare_values["description"][0] = True
            self.compare_values["rewardFraction"][0] = True
            return
        
        self.payload_value["parent"]["ordinal"] = response["lastRef"]["ordinal"]
        self.payload_value["parent"]["hash"] = response["lastRef"]["hash"]

        api_response_mapping = {
            "name": ("nodeMetadataParameters","name"),
            "description": ("nodeMetadataParameters","description"),
            "rewardFraction": ("delegatedStakeRewardParameters","rewardFraction")
        }

        for key in self.ds_config_match:
            section, response_key = api_response_mapping[key]
            local_value = getattr(self.ds_config, key, "no match value")
            api_value = response["latest"]["value"][section][response_key]

            if self.update_executed:
                if self.payload_value["parent"]["ordinal"] == response["lastRef"]["ordinal"]:
                    local_value = api_value

            if local_value == api_value:
                self.ds_config_match[key]["match_str"] = colored(f"{'True':<{self.spacing_value}}", "green", attrs=["bold"])
                self.ds_config_match[key]["match"] = True
            else:
                self.update_required = True


    def handle_error(self,line,code,extra2=False):
        error_obj = {
            "line_code": line,
            "error_code": code,
            "extra": f"{self.error}",
        }
        if extra2:
            error_obj["extra2"] = extra2

        self.error_messages.error_code_messages(error_obj)


    def handle_payload_init(self):
        self._log_msg("info","Building payload update for post.")
        self.payload_value = {

            "delegatedStakeRewardParameters": {
                "rewardFraction": self.ds_config.rewardFraction,
            },
            "nodeMetadataParameters": {
                "name": self.ds_config.name,
                "description": self.ds_config.description,
            },
            "source": self.wallet,
            "parent": {
                "ordinal": None,
                "hash": None
            }
        }

        self.payload_proofs = {
            "proofs": [
                {
                    "id": self.nodeid,
                    "signature": None,
                }
            ]
        }


    def handle_final_payload_build(self):
        self.payload_proofs["proofs"][0]["signature"] = self.crypto.hex_signature
        self.complete_payload = {
            "value": {**self.payload_value},
            **self.payload_proofs
        }


    def handle_last_ref_init(self):
        if len(self.ds_config.name) > self.spacing_value:
            self.spacing_value = len(self.ds_config.name)+2
        self.ds_config_match = {
            "name": {
                "match_str": colored(f"{'False':<{self.spacing_value}}","red",attrs=["bold"]),
                "match": False,
                "value": self.ds_config.name,
            },
            "description": {
                "match_str": colored(f"{'False':<{self.spacing_value}}","red",attrs=["bold"]),
                "match": False,
                "value": self.ds_config.description,
            },
            "rewardFraction": {
                "match_str": colored(f"{'False':<{self.spacing_value}}","red",attrs=["bold"]),
                "match": False,
                "value": self.ds_config.rewardFraction,
            }
        }


    # ==== print methods ====

    def print_title(self,title):
        if self.update_executed: return

        self.functions.print_header_title({
            "line1": title,
            "single_line": True,
            "newline": "bottom"
        })


    def print_value_comparison(self):
        if not self.update_executed:
            self.update_executed = True
        elif self.first_run:
            self.print_first_run_complete()

        last_hash = self.complete_payload["value"]["parent"]["hash"]
        last_hash_short = f"{last_hash[:8]}...{last_hash[-8:]}"
        reward_percent = f"{(self.ds_config_match['rewardFraction']['value'] / 1e8) * 100}%"

        self._log_msg("info",f'Last Ordinal: {self.complete_payload["value"]["parent"]["ordinal"]}')
        self._log_msg("info",f"Last hash: {last_hash}")
        self._log_msg("info",f'Current Name: {self.ds_config_match["name"]["value"]}')        
        self._log_msg("info",f'Current Description: {self.ds_config_match["description"]["value"]}')        
        self._log_msg("info",f'Current Commission: {self.ds_config_match["rewardFraction"]["value"]} [{reward_percent}]')

        print_out_list = [
            {
                "header_elements": {
                    "NAME": self.ds_config_match["name"]["value"],
                    "COMMISSION": reward_percent,
                },
                "spacing": self.spacing_value,
            },
            {
                "header_elements": {
                    "NAME MATCH": self.ds_config_match["name"]["match_str"],
                    "COMM MATCH": self.ds_config_match["rewardFraction"]["match_str"]
                },
                "spacing": self.spacing_value,
            },
            {
                "header_elements": {                
                    "DESCRIPTION": self.ds_config_match["description"]["value"],
                },
                "spacing": self.spacing_value,
            },
            {
                "header_elements": {
                    "DESCRIPTION MATCH": self.ds_config_match["description"]["match_str"]
                },
                "spacing": self.spacing_value,
            },
            {
                "header_elements": {
                    "LAST ORDINAL": self.complete_payload["value"]["parent"]["ordinal"],
                    "LAST HASH": last_hash_short
                },
                "spacing": self.spacing_value,
            },
        ]
    
        for header_elements in print_out_list:
            self.functions.print_show_output({
                "header_elements" : header_elements
            }) 

        if self.verbose and self.update_required: # do not print if no update made
            self.functions.print_paragraphs([
                ["",1],["PAYLOAD VALUE",2,"blue","bold"],
                ["*","half","green","bold"],
                ["** PAYLOAD START **",1,"white"],
                ["*","half","green","bold"],
            ])
            print(colored(json.dumps(self.complete_payload,indent=4),"light_yellow"),end="\n")
            self.functions.print_paragraphs([
                ["*","half","green","bold"],
                ["** PAYLOAD END **",1,"white"],
                ["*","half","green","bold"],
            ])
        print("")


    def print_first_run_complete(self):
        self.functions.print_paragraphs([
            [" CONGRATULATIONS ",2,"yellow,on_green"],
            ["The",0], ["nodectl utility",0,"yellow"], 
            ["has completed your first delegated staking update.",2,"green"],

            ["No future action or requirements are needed at this time.",2,"green"],

            ["To confirm your",0], ["delegated staking",0,"yellow"], ["configuration",0],
            ["please issue the delegate",0],["status",0,"yellow"],["command.",1],
            ["Command:",0,"blue","bold"], ["sudo nodectl delegate status",2,"yellow"],
        ])

        exit(0)


    def print_not_configured_message(self):
        self.functions.print_paragraphs([
            [" DELEGATED STAKING STATUS RESULT ",2,"yellow,on_red"],
            ["The",0,"magenta"], ["nodectl utility",0,"yellow"], 
            ["has determined that you attempted to retrieve the",0,"magenta"],
            ["delegated staking status",0,"yellow"], ["for this node,",0,"magenta"],
            ["but",0,"magenta"], ["no previous updates",0,"magenta","bold"],
            ["to this node's delegated staking parameters were found on the metagraph.",2,"magenta"],

            ["If you reached this message, it likely means your configuration is in place",0],
            ["but, you have not yet issued your first update request.",2],

            ["Command:",0,"blue","bold"], ["sudo nodectl update",2,"yellow"],

            ["If you believe you have reached this message in error",0],
            ["please try again.",0,"magenta"], ["If the issue persists, contact an Administrator on",0],
            ["Constellation Network's official Discord channel",0,"blue","bold"], ["for assistance.",2], 

            ["You may also visit the",0], ["Constellation Network's official Documentation Hub",0,"blue","bold"],
            ["for detailed documentation about this feature and how to use it.",2],
        ])

        exit(0)


    def print_no_update_needed(self):
        self.functions.print_paragraphs([
            [" DELEGATED UPDATE REQUEST CANCELLED ",2,"yellow,on_red"],
            ["The",0], ["nodectl utility",0,"yellow"], 
            ["has determined that there are no changes in the requested update. Therefore,",0],
            ["there is no need to update the delegated staking parameters on this node.",2],
            ["No further action is required.",2], 
        ])
        self.status()
        

    def print_first_run(self):
        self.functions.print_paragraphs([
            [" WARNING ",0,"red,on_yellow"], ["The nodectl utility has detected",0,"red"],
            ["that this is the first time",0],  ["delegated staking",0,"yellow"], 
            ["has been requested from this node using the",0],
            ["p12 key store",0,"yellow"], ["currently configured.",2],

            ["As a result, the starting ordinal and hash values will be initialized to all",0],
            ["zero",0,"yellow"], ["values."], ["This behavior is normal and required for the initial setup.",2],

            ["Please proceed with the staking request as usual.",2],
        ])
        self.functions.confirm_action({
            "yes_no_default": "n",
            "prompt_color": "magenta",
            "return_on": "y",
            "prompt": f"Is this your first update?",
            "exit_if": True,
        })
        print("")


    def print_confirm(self):
        self.functions.confirm_action({
            "yes_no_default": "n",
            "return_on": "CONSTELLATION",
            "strict": True,
            "prompt": f"Send request and update delegated staking?",
            "exit_if": True,
        })            


    def print_disable_warning(self):
        if self.first_run or self.action == "remove":
            self.functions.print_paragraphs([
                [" IMPORTANT ",2,"red,on_green","bold"],
                ["Once delegating staking is enabled on a",0], ["validator node",0,"yellow"],
                ["it",0], ["cannot be disabled.",2,"red","bold"], 

                [" NO NEGATIVE IMPACT ",2,"red,on_green","bold"], 
                ["Delegating your node to the community of delegated stakers has no negative effects on your",0],
                ["node's performance or node rewards. This process is designed to enhance network participation",0],
                ["without compromising your node's functionality or incentives.",2],
            ])

    # ==== misc ====

    def _validate_config(self):
        errors = []
        length_requirement = 140

        valid_keys = ["enable","name","description","rewardFraction"]
        found_keys = list(vars(self.ds_config).keys())
        if set(valid_keys) != set(found_keys):
            errors.append("invalid config file format. missing keys?.")

        if not isinstance(self.ds_config.enable,bool):
            errors.append("invalid config file format. enable not bool.")

        try:
            if self.ds_config.rewardFraction < 5000000 or self.ds_config.rewardFraction > 10000000:
                raise
        except:
            errors.append("invalid commission percent between 5 and 10.")

        for key in ["name","description"]:
            val_value = getattr(self.ds_config,key)
            try:
                if isinstance(val_value, bytes):
                    val_value = val_value.decode("utf-8")
                if not isinstance(val_value, str):
                    errors.append(f"invalid string [{key}]")
                if len(val_value) > length_requirement or len(val_value) < 5:
                    errors.append(f"invalid string length [{key}] at [{len(val_value)}]")
            except:
                errors.append(f"invalid encoding [utf] for [{key}]")
   
        if len(errors) > 0:
            self.error = "format"
            self.handle_error(
                "config_error",
                "del-548",
                errors,
            )


if __name__ == "__main__":
    print("This module is not designed to be run independently, please refer to the documentation")
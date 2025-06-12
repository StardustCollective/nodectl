from time import sleep

class PeerCount():
    
    def __init__(self, command_obj):
        self.command_obj = command_obj
        self._set_parameters(command_obj)


    def _set_parameters(self,command_obj):
        self.parent_getter = command_obj["getter"]
        self.parent_setter = command_obj["setter"]
        
        self.peer_obj = command_obj.get("peer_obj", False)
        self.edge_obj = command_obj.get("edge_obj", False)
        self.profile = command_obj.get("profile", self.parent_getter("default_profile"))
        self.compare = command_obj.get("compare", False)
        self.count_only = command_obj.get("count_only", False)
        self.pull_node_id = command_obj.get("pull_node_id", False)
        self.count_consensus = command_obj.get("count_consensus", False)
        self.refresh = command_obj.get("refresh", False)
        self.called_command = command_obj.get("called_command", False)
        self.error_messages = self.parent_getter("error_messages")
        
        self.log = self.parent_getter("log")
        self.functions = self.parent_getter("functions")
        
        self.peer_list = list()
        self.state_list = list()
        self.peers_publicport = list()

        self.peers_ready = list()        
        self.peers_observing = list()
        self.peers_waitingforready = list()
        self.peers_waitingforobserving = list()
        self.peers_downloadinprogress = list()
        self.peers_waitingfordownload = list()
        
        self.node_states = None
        
        self._set_config_cn_requests()
        
        
    def _set_config_cn_requests(self):
        self.cn_requests = self.command_obj.get("cn_requests", False)
        if not self.cn_requests:
            self.cn_requests = self.parent_getter("cn_requests")
            
        self.config_obj = self.command_obj.get("config_obj", False)
        if not self.config_obj:
            self.config_obj = self.cn_requests.get_self_value("config_obj")
            
        self.cluster_peer_list = self.config_obj["global_elements"]["cluster_info_lists"][self.profile]
        
        
    def get_tcp_stack(self):
        if not self.peer_obj:
            try:
                ip_address = self.parent_getter("default_edge_point")["host"]
                api_port = self.parent_getter("default_edge_point")["host_port"]
            except:
                ip_address = self.parent_getter("default_edge_point")[self.profile]["host"]
                api_port = self.parent_getter("default_edge_point")[self.profile]["host_port"]                
        else:
            ip_address = self.cn_requests.local_ip if self.peer_obj["ip"] == "127.0.0.1" else self.peer_obj["ip"]
            api_port = next((node["publicPort"] for node in self.cluster_peer_list if node.get('ip') == ip_address), None)
            if api_port is None and ip_address == self.cn_requests.local_ip:
                api_port = self.cn_requests.config_obj[self.profile]["publicPort"]
        
        if ip_address is None:
            self.error_messages.error_code_messages({
                "error_code": "pc-57",
                "line_code": "invalid_address",
                "extra": "ip address",
                "extra2": ip_address,
            })
        if api_port is None:
            self.error_messages.error_code_messages({
                "error_code": "pc-57",
                "line_code": "invalid_address",
                "extra": "tcp port",
                "extra2": ip_address,
            })
                
        self.api_port = api_port
        self.ip_address = ip_address
        

    def get_cluster_tcp_stack(self):
        try:        
            if self.compare:
                cluster_ip = self.ip_address
            elif not self.edge_obj:
                cluster_ip = self.edge_obj["ip"]
                api_port = self.edge_obj["publicPort"]
            elif self.edge_obj["ip"] == "127.0.0.1" or self.ip_address == "self":
                cluster_ip = "127.0.0.1"
                api_port = self.parent.config_obj[self.profile]["public_port"]
            else:
                cluster_ip = self.edge_obj["ip"]
                try:
                    api_port = self.edge_obj["publicPort"]
                except:
                    api_port = self.parent.get_info_from_edge_point({
                        "caller": "get_peer_count",
                        "profile": self.profile,
                        "desired_key": "publicPort",
                        "specific_ip": self.edge_obj["ip"],
                    })
        except Exception as e:
            self.parent.log.logger[self.log_key].error(f"Unable to determine cluster_ip, exiting request [{e}]")
            self.parent.error_messages.error_code_messages({
                "line_code": "api_error",
                "error_code": "fnt-411",
                "extra": self.profile,
                "extra2": self.parent.config_obj[self.profile]["edge_point"],
            })

        self.cluster_ip = cluster_ip
        try:
            self.api_port = api_port
        except:
            pass # leave default value


    def get_peers(self):
        url = f"http://{self.cluster_ip}:{self.api_port}/cluster/info"
        if self.api_port == 443:
            url = url.replace("http://","https://").replace(f":{self.api_port}","")
            
        session, s_timeout = self.parent.set_request_session(True)
        
        for _ in range(0,4):
            try:
                peers = session.get(url,timeout=s_timeout)
            except Exception as e:
                self.parent.log.logger[self.log_key].error(f"peer_count --> get_peers --> error found [{url}] error [{e}].")
                peers = "error"
                sleep(1)
            else:
                self.parent.log.logger[self.log_key].debug(f"peer_count --> get_peers --> [{url}].")
                break
            finally:
                session.close()

        self.peers = peers


    def set_peer_count_obj(self):
        final_peer_obj = None
        node_online = False
        ip_address = self.parent.ip_address if self.ip_address == "127.0.0.1" or self.ip_address == "self" else self.ip_address
        id_ip = ("ip","id") if len(ip_address) < 128 else ("id","ip")
        try:
            for line in self.peers:
                if ip_address in line[id_ip[0]]:
                    if self.pull_node_id:
                        self.our_node_id = line[id_ip[1]]
                        final_peer_obj = "error"
                        return
                    node_online = True
                    self.peer_list.append(line[id_ip[0]])
                    self.peers_publicport.append(line['publicPort'])
                    self._handle_states(line)
                    self.state_list.append("*")
                else:
                    # append state abbreviations
                    for state in self.node_states:
                        if state[0] in line["state"]:
                            self._handle_states(line)
                            self.peer_list.append(line[id_ip[0]])
                            self.peers_publicport.append(line['publicPort'])
                            self.state_list.append(state[1])
        except Exception as e:
            self.parent.log.logger[self.log_key].error(f"get peer count - an error occurred attempting to review the line items on a /cluster/info api request | error [{e}]")
        
        final_peer_obj = {
            "peer_list": self.peer_list,
            "peers_publicport": self.peers_publicport,
            "state_list": self.state_list,
            "observing": self.peers_observing,
            "waitingforready": self.peers_waitingforready,
            "waitingforobserving": self.peers_waitingforobserving,
            "waitingfordownload": self.peers_waitingfordownload,
            "downloadinprogress": self.peers_downloadinprogress,
            "ready": self.peers_ready,
            "peer_count": len(self.peer_list),
            "observing_count": len(self.peers_observing),
            "waitingforready_count": len(self.peers_waitingforready),
            "waitingforobserving_count": len(self.peers_waitingforobserving),
            "waitingfordownload_count": len(self.peers_waitingfordownload),
            "downloadinprogress_count": len(self.peers_downloadinprogress),
            "consensus_count": self.consensus_count["nodectl_found_peer_count"],
            "ready_count": len(self.peers_ready),
            "node_online": node_online
        }        

        self.id_ip = id_ip
        self.final_peer_obj = final_peer_obj


    def handle_count_only(self):
        if not self.count_only: return

        if self.refresh:
            if self.called_command == "join":
                self.cn_requests.set_self_value("peer", False)
                self.cn_requests.set_self_value("use_local", True)
            else:            
                self.cn_requests.set_self_value("peer",self.ip_address)
                self.cn_requests.set_self_value("api_public_port",self.api_port)
            self.cn_requests.set_self_value("get_state", False) # want cluster/info
            self.cn_requests.set_cluster_cache()
            self.cluster_peer_list = self.cn_requests.config_obj["global_elements"]["cluster_info_lists"][self.profile]
            
        count = len(self.cluster_peer_list)
        return count
 

    def handle_consensus(self):
        if self.count_consensus:
            consensus_count = self.parent.get_cluster_info_list({
                "profile": self.profile,
                "ip_address": self.ip_address,
                "port": self.api_port,
                "api_endpoint": "/consensus/latest/peers",
                "spinner": False,
                "attempt_range": 4,
                "error_secs": 3
            })
            try:
                consensus_count = consensus_count.pop()
            except:
                consensus_count = {'nodectl_found_peer_count': "UnableToDerive"}
        else:
            consensus_count = {'nodectl_found_peer_count': "UnableToDerive"} 

        self.consensus_count = consensus_count 


    def _handle_states(self, line):
        if line["state"] == "Observing":
            self.peers_observing.append(line['ip'])  # count observing nodes
        elif line["state"] == "Ready":
            self.peers_ready.append(line['ip'])  # count ready nodes
        elif line["state"] == "WaitingForReady":
            self.peers_waitingforready.append(line['ip'])
        elif line["state"] == "WaitingForObserving":
            self.peers_waitingforobserving.append(line['ip'])
        elif line["state"] == "DownloadInProgress":
            self.peers_downloadinprogress.append(line['ip'])
        elif line["state"] == "WaitingForDownload":
            self.peers_waitingfordownload.append(line['ip'])




if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation") 
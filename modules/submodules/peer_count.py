from time import sleep

class PeerCount():
    
    def __init__(self,command_obj):
        self.parent = None
        self._set_parameters(command_obj)


    def get_tcp_stack(self):
        if not self.peer_obj:
            ip_address = self.parent.default_edge_point["host"]
            api_port = self.parent.default_edge_point["host_port"]
        else:
            ip_address = self.peer_obj["ip"]  
            localhost_ports = self.parent.pull_profile({
                "req": "ports",
                "profile": self.profile,
            })
            
            if self.peer_obj["ip"] == "127.0.0.1":
                api_port = localhost_ports["public"]
            else:
                try:
                    api_port = self.peer_obj["publicPort"]
                except:
                    api_port = self.parent.get_info_from_edge_point({
                        "caller": "get_peer_count",
                        "profile": self.profile,
                        "desired_key": "publicPort",
                        "specific_ip": ip_address,
                    })  
            self.localhost_ports = localhost_ports

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
            
        session = self.parent.set_request_session(True)
        s_timeout = (0.2,0.6)
        
        for _ in range(0,4):
            try:
                peers = session.get(url,timeout=s_timeout)
            except:
                peers = "error"
                sleep(1)
            else:
                break
            finally:
                session.close()

        self.peers = peers


    def _set_parameters(self,command_obj):
        self.peer_obj = command_obj.get("peer_obj",False)
        self.edge_obj = command_obj.get("edge_obj",False)
        self.profile = command_obj.get("profile",None)
        self.compare = command_obj.get("compare",False)
        self.count_only = command_obj.get("count_only",False)
        self.pull_node_id = command_obj.get("pull_node_id",False)
        self.count_consensus = command_obj.get("count_consensus",False)

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

        self.final_peer_obj = final_peer_obj


    def handle_count_only(self):
        if not self.count_only: return

        count = self.parent.get_cluster_info_list({
            "ip_address": self.ip_address,
            "port": self.api_port,
            "api_endpoint": "/cluster/info",
            "spinner": False,
            "attempt_range": 4,
            "error_secs": 3
        })
        try:
            count = count.pop()
        except:
            pass  # skip to unimportant error if the cluster info comes back bad during iteration
        if count:
            count = (count["nodectl_found_peer_count"])

        return count      


    def handle_consensus(self):
        if self.count_consensus:
            consensus_count = self.parent.get_cluster_info_list({
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
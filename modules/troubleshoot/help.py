from termcolor import colored


def title(command):
  title_header1 = colored(f"\n  {command.upper()} COMMAND- extended help","green")
  title_header2 = "\n  "
  title_header2 += colored("=".ljust(len(title_header1)-11,"="),"green")
  return "\n"+title_header1+title_header2+"\n"


def build_help(functions,command_obj):
      
    extended = command_obj.get("extended",False)
    extended_option = None
    help_text = "" # initialize
    
    usage_only = command_obj.get("usage_only",False)
    nodectl_version_only = command_obj.get("nodectl_version_only",False)

    simple_command_list = [
      "list","whoami","show_node_states","passwd12",
      "reboot","disable_root_ssh","enable_root_ssh",
      "clean_snapshots","update_seedlist", "check_source_connection",
      "health","sec","price","markets", "upgrade_path", 
      "check_seedlist_participation", "check_version", "uptime","uninstall",
      "show_cpu_memory","execute_starchiver",
    ]
    
    functions.print_paragraphs([
      ["@netmet72",1]
    ])
    
    command_str = "usage: sudo nodectl ["
    command_str_start = command_str
    for command_name in sorted(command_obj["valid_commands"]):
      command_str += f", {command_name}"
    command_str += " ]"
    command_str = command_str.replace(",","",1)
    spacing = len(command_str_start)+3
    functions.print_paragraphs([
      [command_str,1]
    ],{
      "indent": "  ",
      "sub_indent": f"{' ' * spacing}",
    })

    functions.print_paragraphs([
      ["optional:",0],["--pass",0,"yellow"],["<passphrase>",1],
      ["    note:",0],["--pass will override the configuration's passphrase entry",2,"magenta"],
      ["See extended help for more details including",0],["required",0,"blue","bold"], 
      ["parameters per command.",2],
      ["command: ",0], ["sudo nodectl <command> help",2,"yellow","bold"],
    ])
    

    if not extended and not usage_only and not nodectl_version_only:
        help_text += '''
  Options:

    CLI options - please see extended help for short-cut options and
                  various options for each command (sudo nodectl <command> help)
    
    upgrade    | upgrade Tessellation version
    install    | install Tessellation - Turn your bare metal or
                 VPS into a Validator Node

    uninstall  | restore your VPS to default state before nodectl
                 was installed.
                 
    configure            | setup your Node's configuration via
                           pre-configured profiles, advanced user setup,
                           or a user friendly guided setup.
    validate_config  | import configuration file and
                           attempt to validate it's basic
                           needs and patterns
    view_config  | view the cn-config.yaml file
                           
    help    | show this menu
    
    version         | show version of nodectl
    check_versions | show versions current and latest
                         versions of nodectl and Tessellation
                         and whether they match
                            
    status  | - show the state of the Node's service
    quick_status | - show an abbreviated version of the status command
                     that looks at the local API only
                                       
    -p | - required parameter for several commands
           issue the -p with the name of the profile
           following the -p flag
                Requires -p:
                    - status
                    - start
                    - stop
                    - restart
                    - slow_restart
                    - restart_only
                    - join
                    - leave
                    - count
                    - find
                    - peers
                    - check_connection
                    - check_source_connection
                    - export_private_key
                    - dag
              
    start   | - start node services on Node

    stop    | - stop node services on Node

    join    | - join the current cluster
        
    leave   | - force node to leave cluster
    
    find    | - Is my IP address found on the network
                if an ip address <x.x.x.x> is supplied
                the system will lookup that IP address
                entered to determine if it is found on
                the network
    
    peers   | - show a list of all IP addresses found
                on the network.
    
    list    | - show a list of all the profiles
                currently available on this version
                of nodectl.
                
    show_current_rewards  | - shows the last 50 ordinals finds dag
                              addresses found and amount accumulated
                              in the current approximate time frame.
             
    log -l <log_type> -g <grep_word> -f  | - show logs for requested log type
    
    whoami  | - show your system's external ip
    nodeid2dag | - convert nodeid to dag wallet address
    
    id -p <profile>                 | - show your system's node id address
    nodeid -p <profile>             | - show your system's node id address
    export_private_key -p <profile> | - show your p12's private key
    
    passwd12            | - change your p12's passphrase
                            
    restart  | - restart node services on Node and join
    
    restart_only | - restart node services on Node but don't join.
    
    upgrade_vps | - more simple verbose method of updating and upgrading
                    your VPS.

    check_seedlist | - check the seed list access to see if 
                             your nodeid is present on the seed list
    
    update_seedlist -e <environment_name> | - update the local copy of the seed list 
      
    uptime       | - check system, cluster, and Node uptime.
                           
    slow_restart | - restart the node with a 600 second delay to
                         make sure it is fully off the network in the
                         event you are seeing connection issues or other
    
    reboot | - acts exactly same as a distribution reboot; however, this command
               will make sure the Node software does a clean 'leave' to leave
               the network prior to rebooting the system.
    
    clean_snapshots | - clean out the snapshot cache directory
                          * this should only be done by advanced users during
                            troubleshooting or genesis block creation! *
                            will clean snapshots older than 30 days only.
                            see extended help (sudo nodectl -cs help)
    
    clean_files    | - clear files types older than 7 or 30 days, or all 
                            -t ["logs","backups","uploads"]
                           
    check_source_connection | - checks the debug api for peer on both the
                                     node that the edge initially joined to
                                     and the edge node and reports back status
    
    check_connection | - checks the debug api for peer against
                             the entire network cluster you are
                             connected to and report back status
                             
    check_seedlist_participation | - show access-list verse network comparison
                                     (pre-PRO score temporary feature)
    
    check_consensus -p <profile> | - check if Node is participating in consensus on layer0
    
    check_minority_fork -p <profile> | - check if Node is in a minority fork
      
    download_status  -p <profile> | - show a progress indicator following the 
                                      progress of your DownloadInProgress None State
                                                                                             
    show_node_states  | - show a list of known Node states                    
    
    show_service_log -p <profile> | - show the distribution service logs 
                                       associated with profile 
    
    show_p12_details | - show details of a p12 file.
                                
    show_dip_error -p <profile>  | - show any occurances of a DownloadInProgress error
                                     located in the logs.
                                            
    refresh_binaries -e <env> | - download latest binaries
                                  for latest release of Tessellation
                              
    upgrade_nodectl | - upgrade nodectl to latest version
    upgrade_path    | - check nodectl upgrade path and verify where
                        current version is in relationship to the path
    
    disable_root_ssh | - have nodectl restrict access to your root user
    
    enable_root_ssh  | - have nodectl reenable access to your root user    
    
    change_ssh_port -p <port> | - change the port number used to access your
                               Node via the SSH protocol.  The port number
                               should be between 1024 and 65535.  Please be
                               careful not to use a port already in use or
                               that might be used by the Node for various 
                               API access.  Default well known port = 22
                               
    send_logs -p <profile>  |  - create a tarball of your log files for diagnosis  
                                     will offer option to upload for the developers
                                     to access va transfer.sh
                                     resulting file name = <your-node-ip-address>_logs.tar.gz
                         
    auto_restart <disable> <check_pid>   |  Starts a background nodectl service that will 
                                            keep an eye on the network and restart your 
                                            services if they go offline.
                                            
                                            auto_restart disable - turns this service off
                                            auto_restart check_pid - checks if it is running
                                            
                                            see extended help for configurable auto_restart
                                            details... sudo nodectl auto_restart help
                                            
    verify_nodectl  |  Checks the digital signature of the nodectl binary for authenticity    
    
    create_p12 |  Create a single independent p12 file.                                    
                     
    health  | - show basic health elements of your Node
              - show the current 15 minute CPU load and 
                if WARNING or LOW
              - show the disk usage of your system's 
                main storage volume
              - show the uptime in days with 
                WARNING or LOW
              - show Memory of your system and if 
                WARNING or LOW
              - show the Swap Drive or your system and 
                if WARNING or LOW
              
    sec     | - show basic security statistics
              - show how many log errors were identified 
                through all the logs
              - show a count of access attempts 
                that were denied
              - show how many times an entity attempted 
                to access your system multiple times 
                before being blocked via system default 
                timers
              - show the TCP port range that the entity 
                attempted access between
              
    price   | Do a quick lookup for Crypto prices
              currently:  Constellation Network, 
                          Lattice Exchange, 
                          BitCoin, 
                          Ethereum, 
                          Quant Network
                          
    markets  | Do a lookup on the top 10 market
               makers in the Crypto industry and
               print out brief report.  Note: If
               Constellation Network is not in the
               top 10 at the current moment in time
               it will be added to the report in its
               current position.
             
        '''
        
        
    if extended == "check_source_connection":
        help_text += title("CHECK SOURCE CONNECTION")
        help_text += f'''
  This command takes a profile argument.

  required:
  {colored('-p <profile_name>','green')}
  
  alternative shorthand option:
  {colored('-csc','green')}
    
  When executed the {colored('check_source_connection','cyan')} command will attempt
  to find a random Node on the current known Hypergraph cluster.
  
  NOTE: The random Node does to need to be joined into the consensus
  of the cluster, only be properly joined to the cluster and in
  Ready state.

  Example output:
  
  {colored('FULL CONNECTION','blue',attrs=['bold'])}              {colored('PROFILE','blue',attrs=['bold'])}
  True                         dag-l0
  {colored('SOURCE -> STATE','blue',attrs=['bold'])}              {colored('EDGE -> STATE','blue',attrs=['bold'])}
  True | Ready                 True | Ready

   {colored('FULL CONNECTION','yellow')}: Both the source Node picked by nodectl and 
                    the local [edge] Node that executed the {colored('check_source_connection','cyan')}
                    command can see each other [True] or cannot [False]
           {colored('PROFILE','yellow')}: The profile that this command was run against
   {colored('SOURCE -> STATE','yellow')}: Can the SOURCE Node see the edge Node [True|False]
                    The source Node's state is in [Ready] state
     {colored('EDGE -> STATE','yellow')}: Can the EDGE Node see the source Node [True|False]
                    The edge Node's state is in [Ready] state
            '''
            
            
    if extended == "check_connection":
        help_text += title("check connection")
        help_text += f'''
  {colored('check_connection','cyan')} takes one required parameter and
  offers two optional parameters
  
  required:
  {colored('-p <profile_name>','green')}
  
  optional:
  {colored('-s <ip_address>','green')}  
  {colored('-e <ip_address>','green')}
    
  alternative shorthand option:
  {colored('-cc','green')}

  This command will execute a search on the currently
  connected Hypergraph cluster.  
  
  It will use a "source" specified by an optional {colored('-s','cyan')} or 
  it will pick a random selected source Node.
  
  It will search again the Node the {colored('check_connection','cyan')} command was
  executed upon unless an edge device to check against the 
  source is specified by an optional {colored('-e','cyan')} option.
  
  The command will compare the Nodes found on the {colored('source','cyan')} against
  the Nodes found on the {colored('edge','cyan')}.  If the Nodes connected
  to each do {colored('not','red')} match, the command will display those Nodes
  that are missing between the two.

  {colored("Dictionary","white",attrs=['bold'])}  
  ----------
  {colored('*','green')}   > Indicates the ip searched against
        was either the edge and source ip
  {colored('i','green')}   > Initial State
  {colored('rj','green')}  > ReadyToJoin State
  {colored('ss','green')}  > StartingSession State
  {colored('s','green')}   > SessionStarted State
  {colored('rd','green')}  > ReadyToDownload State
  {colored('wd','green')}  > WaitingForDownload State
  {colored('wr','green')}  > WaitingForReady State
  {colored('dp','green')}  > DownloadInProgress State
  {colored('ob','green')}  > Observing State
      > Ready
  {colored('l','green')}   > Leaving State
  {colored('o','green')}   > Offline State
  {colored('a','green')}   > ApiNotReady State (nodectl only)
  {colored('a','green')}   > ApiNotResponding State (nodectl only)

  {colored("If Node shows False","white",attrs=['bold'])}
  ===================
  {colored("There may be circumstances where your Node is showing a","yellow")}
  {colored("False positive.  The network may still be converging or","yellow")}
  {colored("another Node may be causing your Node to show False.","yellow")}
  
  In some cases you may need to wait a little time and check
  the Node (check-connection) again.

  However, if you are seeing {colored('many','cyan')} Nodes "missing", please
  wait a period of time and check again anyway. 
  
  You may be {colored('edge','cyan')} the network and a restart is required
  {colored('sudo nodectl restart help','cyan')} 
  
  You can contact a System Administrator to see if your log files
  may help to figure out if your issue is correctable.

  Example Usage
  -------------
  scenario for help >
   - Node you joined to originally (source) : 10.1.1.1
   - The IP of your Node (edge) : 10.2.2.2
   - The IP of another Node (other) : 10.3.3.3
   - The IP of another Node (other) : 10.4.4.4
    
  show this menu
  # {colored('sudo nodectl check-connection help ','cyan')}

  check random "source" against the local "edge" Node
  # {colored('sudo nodectl check-connection -p <profile_name>','cyan')}

  check random "source" Node against "other" Node
  # {colored('sudo nodectl check-connection -p dag-l0 -e 10.3.3.3','cyan')}

  check "any other Node" against "any other Node"
  # {colored('sudo nodectl check-connection -p dag-l0 -s 10.3.3.3 -s 10.4.4.4','cyan')}
            '''
            
    if extended == "configure":
        help_text += title(extended)
        help_text += f'''
  This command will attempt to guide the Node Operator 
  through the creating or editing the {colored('cn-config.yaml','cyan')} 
  file.
  
  The {colored('cn-config.yaml','cyan')} file is an {colored('extremely important','red',attrs=['bold'])}
  file that {colored('nodectl','cyan')} uses to determine how it 
  should control and configure your {colored('Constellation','blue',attrs=['bold'])}
  {colored('Network Validator Node','blue',attrs=['bold'])}.
  
  optional:
  
  {colored('-a','green')} | enter configuration in advanced mode
       advanced mode will skip detailed explanations
       of the arguments being requested
  {colored('-n','green')} | skip directly to a new configuration
  {colored('-e','green')} | skip directly to configuration editor
  {colored('-ep','green')} | skip directly to configuration profile editor
  {colored('-cb','green')} | confirm backup to avoid having to confirm the backup during setup
  
  In new configuration mode:
  -------------------------
  {colored('nodectl','cyan')} will offer you two (2) options
  
    {colored('1. Predefined Profile settings','yellow')}
    {colored('2. Manual Configuration','yellow')}
    
  In edit configuration mode:
  -------------------------
  {colored('nodectl','cyan')} will offer you several options
  
    {colored('1. Edit Profiles','yellow')}
    {colored('2. Edit Global Settings','yellow')}
    
  If advanced mode is {colored('not','red')} requested, {colored('nodectl','cyan')} will
  offer you help on each entry for both new and
  edit mode.
  
  Example Usage
  -------------
  show this help screen
  # {colored('sudo nodectl configure help','cyan')} 
   
  enter default configurator
  # {colored('sudo nodectl configure','cyan')}  
   
  enter configurator directly to new config options
  # {colored('sudo nodectl configure -n','cyan')}  
   
  enter configurator directly to edit config options
  # {colored('sudo nodectl configure -e','cyan')}  
   
  enter configurator directly to edit config options
  in advanced mode
  # {colored('sudo nodectl configure -a -e','cyan')}  
   
  enter configurator directly to edit config profile options
  # {colored('sudo nodectl configure -ep','cyan')}  
   
  enter configurator directly to edit config profile options
  in advanced mode
  # {colored('sudo nodectl configure -a -ep','cyan')}  
        '''
  
    if extended == "send_logs":
      help_text += title("Send Logs")
      help_text += f'''
  This command is a debug command used to help accumulate
  log files to send to Developers or System Engineering
  to dissect; to better the code base.
  
  During the execution you will be offered a menu to
  upload:
    {colored('current','cyan')} logs  
    {colored('backup','cyan')} logs  
    {colored('specific date','cyan')} logs  
    {colored('date range','cyan')} logs  
    {colored('archived','cyan')} logs  
    
  Once you follow the prompts a tarball gzipped file
  will appear in the uploads directory and the system
  will offer you the ability to upload the results to 
  the {colored('transfer.sh','cyan')} service.
  
  required:
  {colored('-p <profile_name>','green')}
  
  Example Usage
  -------------
  show this help screen
  # {colored('sudo nodectl send_logs help','cyan')}
     or
  # {colored('sudo nodectl -sl help','cyan')}
  
  execute a log preparation for upload
  # {colored('sudo nodectl send_logs -p <profile_name>','cyan')}  
     or
  # {colored('sudo nodectl -sl -p <profile_name>','cyan')}  
      '''
  
    if extended == "show_cpu_memory":
      help_text += title("Show CPU and MEMORY")
      help_text += f'''
  The command {colored(extended,"cyan")} will review the VPS system that
  this Node is running on and display the current CPU
  and memory percentages, and the determined status
  of the CPU and memory based on a statically set threshold.

  {colored('current','cyan')}:    CPU usage percent found
              at the time of the execution
              of this command.  
  {colored('threshold','cyan')}:  Statically defined
              percentage before status will be
              deemed not OK.  
  {colored('CPU/MEMORY','cyan')}: green OK
              red PROBLEM  
      '''
  
    if extended == "check_consensus":

      help_text += title("Check Consensus")
      help_text += f'''
  This command is a simple check against the edge
  point in order to verify that the Node is 
  participating in consensus for the profile
  specified.
  
  required:
  {colored('-p <profile_name>','green')}
  
  optional:
  {colored('-s <ip_address>','green')}
  {colored('--id <ip_address>','green')}
  {colored('--file <full_file_path>','green')}
  
  Is the {colored('-s','cyan')} option is requested the
  consensus will be checked against the IP address inputted.
  
  Is the {colored('--id','cyan')} option is requested the
  consensus will be checked against the nodeid public key inputted.
  
  Is the {colored('--file','cyan')} option is requested the
  consensus will be checked against the file that contains at least
  one nodeid public key or multiple nodeids formatted in one line
  per nodeid public key.
  
  Example Usage
  -------------
  show this help screen
  # {colored('sudo nodectl check_consensus help','cyan')}
     or
  # {colored('sudo nodectl -con help','cyan')}
  
  execute consensus check
  # {colored('sudo nodectl check_consensus -p <profile_name>','cyan')}  
     or
  # {colored('sudo nodectl -con -p <profile_name>','cyan')}  
  
  execute consensus check against Node with 
  profile name dag-l0 and IP address 10.10.10.10.
  # {colored('sudo nodectl check_consensus -p dag-l0 -s 10.10.10.10','cyan')}  
     or
  # {colored('sudo nodectl -con -p dag-l0 -s 10.10.10.10','cyan')}  
  
  execute consensus check against list of node ids with 
  profile name dag-l0 and file containing node id list called test.csv
  locationed in the the /tmp/ directory on the Node.
  # {colored('sudo nodectl check_consensus -p dag-l0 --file /tmp/test.csv','cyan')}  
     or
  # {colored('sudo nodectl -con -p dag-l0 --file /tmp/test.csv','cyan')}  
      '''
  
    if extended == "cli_create_p12":

      help_text += title("Create a P12 File")
      help_text += f'''
  This command will create a p12 file and place
  it on the system in a location of the Operator's
  choosing.
  
  If a location is not supplied, the global p12
  configured location will be used by default.
  
  If a username is not supplied, the global p12
  username will be used by default
  
  optional:
  {colored('--file <p12_filename>','green')}
  
  optional:
  {colored('--location <full_path_to_file>','green')}
  
  Example Usage
  -------------
  show this help screen
  # {colored('sudo nodectl create_p12 help','cyan')}
  
  build a new p12 file using the global configured
  Node admin username:
  # {colored('sudo nodectl create_p12','cyan')}  

  build a new p12 file using a user named test.p12 and
  the file location /tmp/my_new_p12_files.
  # {colored('sudo nodectl create_p12 --file test.p12 --location /tmp/my_new_p12_files/','cyan')}  
      '''
      
    if extended == "check_minority_fork":

      help_text += title("Check Minority Fork")
      help_text += f'''
  This command is a simple check if the Node
  is no longer on the majority cluster and
  properly participating.
  
  required:
  {colored('-p <profile_name>','green')}
  OR required:
  {colored('-e <environment_name>','green')}
  
  Example Usage
  -------------
  show this help screen
  # {colored('sudo nodectl check_minority_fork help','cyan')}
     or
  # {colored('sudo nodectl -con help','cyan')}
  
  execute minority fork check using profile
  # {colored('sudo nodectl check_minority_fork -p <profile_name>','cyan')}  
     or
  # {colored('sudo nodectl -cmf -p <profile_name>','cyan')}  
  
  execute minority fork check using environment
  # {colored('sudo nodectl check_minority_fork -e mainnet','cyan')}  
     or
  # {colored('sudo nodectl -cmf -e mainnet','cyan')}  
      '''
  
    if extended == "download_status":
      help_text += title("Send Logs")
      help_text += f'''
  The {colored('download_status','cyan')} command can be used to 
  monitor the progress of your Node's {colored('DownloadInProgress','yellow')} state.
    
  During a Node's {colored('join','yellow')} process, to become part of the cluster 
  for the profile(s) configured, the Node undergoes a series of essential 
  initialization tasks to ensure it integrates and functions properly
  as a peer on the cluster.

  Once your Node completes the initial phases of authentication and 
  becomes a peer on the cluster, it must synchronize and gain knowledge 
  about the known blockchain before actively participating in consensus 
  and earning rewards.  
  
  Constellation Network employs an {colored('incremental snapshot','yellow')} strategy 
  to minimize the ingress "cost" for downloading blockchain snapshots. When a new 
  Node joins the cluster, it will undergo a {colored('one time','red')} extended period
  of learning about the entire blockchain. For an existing Node rejoining the cluster, 
  it is required to calculate the differences between its previous state and the 
  current blockchain state.
    
  Following authentication, your Node may temporarily remain in the 
  {colored('WaitingForDownload','yellow')} state, which is a relatively inactive phase 
  with no notable progress.  Due to this, when you execute the 
  {colored('download_status','cyan')} command, it will monitor your Node's status, via
  a timer [verses a progress indicator], continually checking until the 
  Node transitions to {colored('DownloadInProgress','yellow')}.
  
  When in {colored('DownloadInProgress','yellow')} state, nodectl will actively oversee your Node's activities, 
  presenting a progress indicator on the screen that provides an estimate 
  of the completion percentage for this process.  
  
  Part 1: {colored('Downloading snapshots','cyan')}: Above the progress indicator, you'll find 
          the snapshots being downloaded to your Node, displayed by their 
          corresponding ordinal. This will be represented as a decreasing 
          counter.

  Part 2: {colored('BlockAcceptanceManager','cyan')}: The progress indicator will be
          modified. You will see the "height" of the last snapshot block and 
          the current "height" reached. This will be displayed as an increasing 
          counter.
  
  To the right of the counters, you will see a differential counter to help ease the 
  calculation of what is left to be processed from either part 1 or part 2.

  required:
  {colored('-p <profile_name>','green')}
  
  alternative shorthand option:
  {colored('-ds','green')}
  
  Example Usage
  -------------
  show this help screen
  # {colored('sudo nodectl download_status help','cyan')}
     or
  # {colored('sudo nodectl -ds help','cyan')}
  
  execute a log preparation for upload
  # {colored('sudo nodectl download_status -p <profile_name>','cyan')}  
     or
  # {colored('sudo nodectl -ds -p <profile_name>','cyan')}  
      '''
    
    if extended == "peers":
      help_text += title(extended)
      help_text += f'''
  This command will attempt to list all the peers found on 
  the cluster and list their IP addresses for review.

  required:
  {colored('-p <profile_name>','green')}
  
  optional:
  {colored('-t <target_node>','green')} ( ip or hostname )
  {colored('-c','green')} count peers
  {colored('--csv','green')} create csv output instead of print out
  {colored('--output <file_name>','green')} used with --csv to create
                                            custom file name for csv
                                            output.
          The --output can only be a filename.  If you would like to
          have your output saved to an alternate location, you can
          update the configuration file via the 'configure' command.
          
          {colored('sudo nodectl configure','cyan')} 
  
  extended:
  {colored('--basic','green')}
  {colored('--extended','green')}
  
  Normal output from the peers command will show all the peers
  seen on a given network cluster (profile dependent)
  this will include:
    - node ip with public port 
      - 10.10.10.10:1000 = 10.10.10.10 with public TCP port of 1000
    - nodeid (shortened)
    - DAG wallet shortened
    
  You can utilize the {colored('--basic','green')} option to force
  nodectl to only show the PEER IP:TCP PORT column
    
  You can utilize the {colored('--extended','green')} option to force
  nodectl to only show all fields in long format.
  
  Dictionary
  ----------
  *   > Indicates the ip searched against
        was either the edge and source ip
  i   > Initial State
  rj  > ReadyToJoin State
  ss  > StartingSession State
  l   > Leaving State
  s   > SessionStarted State
  o   > Offline State

  Example Usage
  -------------
  show this help screen
  # {colored('sudo nodectl peers help','cyan')}
  
  show nodes on cluster from random peer on the cluster
  from a specific profile
  # {colored('sudo nodectl peers -p <profile_name>','cyan')}
  
  show YOUR Nodes's peers
  # {colored('sudo nodectl peers -p <profile_name> -t self','cyan')}

  show peers on the cluster utilizing a specific
  target ip address.
  # {colored('sudo nodectl peers -p <profile_name> -t <ip_address or hostname>','cyan')}

  show count of peers your node is able to see. (synonymous with 'find' command)
  show peers on the cluster utilizing a specific
  # {colored('sudo nodectl peers -p <profile_name> -c','cyan')}
  
  source target ip address to count against.
  # {colored('sudo nodectl peers -p <profile_name> -t <ip_address or hostname> -c','cyan')}
  
  =======

  example usage for a profile called {colored('dag-l0','white',attrs=['bold'])}
  # {colored('sudo nodectl peers -p dag-l0','cyan')}

  example usage for {colored('--basic','white',attrs=['bold'])}
  # {colored('sudo nodectl peers -p dag-l0 --basic','cyan')}

  example usage for {colored('--extended','white',attrs=['bold'])}
  # {colored('sudo nodectl peers -p dag-l0 --extended','cyan')}
  
  =======
    
  create a csv file 
  # {colored('sudo nodectl peers -p <profile_name> --csv','cyan')}
  create a csv file named test.csv
  # {colored('sudo nodectl peers -p <profile_name> --csv --output test.csv','cyan')}
  
        '''
        
    if extended == "show_node_states":
        extended_option = "-sns"
        help_text += title("show node states")
        help_text += f'''
  The {colored('show_node_states','cyan')} command does not take any arguments 
  and displays the list of the known Node States that you may
  find on the Cluster or that nodectl defines when not on the cluster.
  
  {colored("nodectl only states:","cyan")}
  {colored('ApiNotReady','magenta')}:      shown if nodectl can not reach the Node's
                   internal API server. 
  {colored('ApiNotResponding','magenta')}: shown if nodectl can not reach the Node's
                   internal API server, due to cpu or memory issues. 
  {colored('SessionNotFound','magenta')}:  shown if nodectl can not read the Node's
                   session via the internal API server. 
  {colored('SessionIgnored','magenta')}:   shown if nodectl is not online and there
                   is not a session to display. 
  '''
        
    if extended == "auto_restart":
        help_text += title("auto restart")
        help_text += f'''
  The {colored('auto_restart','cyan')} takes arguments.
  
  {colored('  - enable','green')}
  {colored('  - disable','green')}
  {colored('  - restart','green')}
  {colored('  - status','green')}
  {colored('  - check_pid','green')}

  {colored('IMPORTANT','red',attrs=['bold'])} 
  {colored('Do not rely on auto_restart completely as it is not "fool proof".','red')}
  
  You can setup {colored('nodectl','blue',attrs=['bold'])} to handle and control auto_restart
  from its configuration file.  By {colored('default','green')} this feature is disabled.  
  Issue {colored('sudo nodectl configure','cyan')} to enable.
  
  {colored('Auto restart','green')} is a special feature of nodectl that will continuously monitor
  your Node to make sure the various profiles are on the cluster
  and that each profiles state on the cluster is in {colored('Ready','green')} state,
  and the {colored('Session','green')} is up-to-date.
  
  Processing each profile in its own thread (i/o) nodectl will wait a
  randomly set time (per thread) and check the Node's condition after
  each successive random sleep timer expires.
  
  In the event that your Node is identified to have either:
    - Its {colored('service','cyan')} in an inactive state
    - Node's cluster {colored('state','cyan')} is {colored('not','red')} 'Ready'
    - The Node's known cluster {colored('session','cyan')} does not match the cluster's
      known {colored('session','cyan')}.
  the Node will begin an automatic restart.
  
  If the {colored('session','cyan')} of the cluster does not match the Node session that was 
  established at the cluster's genesis at the beginning of the cluster's initialization,
  an {colored('auto_restart','cyan')} will be triggered.
  
  This session will change if a {colored('restart','cyan')} or {colored('roll-back','cyan')} is identified. 
   
  If your Node is currently joined to an older {colored('session','cyan')} it will no longer be participating 
  on the proper cluster (what can be considered a 'floating island'),
  {colored('auto_restart','cyan')} will attempt to correct the situation.
  
  {colored('IMPORTANT','red')}
  An {colored('auto_restart','cyan')} may take up to {colored('18 minutes to complete','white',attrs=['bold'])}.  
  This is because the Node will detect one or both profiles down and restart the Global layer0 first
  before it then attempts to bring up any other layers.  To avoid timing conflicts
  with other Node's that may have auto_restart enabled {colored('auto_restart','cyan')} has random
  timers put in place throughout a restart process.  As you will need to properly
  link your layer1 to the Global layer0. {colored('Understanding','green')} this is a
  background and unattended process, the {colored('delay','cyan')} is created on purpose.
  
  It is {colored('recommended','cyan')} by the developers to link to layer1 through your
  Node's own Global layer0 connection.
  
  {colored('IMPORTANT','red')}
  {colored('auto_restart','cyan')} is not perfect and should be used as a tool
  to help keep your Node up in a consistent fashion; however, it may not be
  fool proof, and {colored('you should still monitor your Node manually','red',attrs=['bold'])} to make sure it
  stays online with the proper known cluster session.
  
  If you are using {colored('auto_restart','cyan')} please remember if you are physically 
  monitoring your Node while it is enabled, and have patience to allow it 
  to figure out how to get back online by itself as necessary.  Forcing a manual restart
  will disable {colored('auto_restart','cyan')}.  If enabled in the configuration, nodectl
  will attempt to reenable auto_restart after any command that requires it to be 
  temporarily disabled.
  
  {colored('IMPORTANT','red')}
  In order to avoid duplicate or unwanted behavior such as your Node
  restarting when you do not want it started, the {colored('auto_restart','cyan')}
  feature will automatically disable if you attempt to issue any command
  that manipulates the services.
    - leave
    - stop
    - start
    - join
    - restart
    - upgrade
  
  {colored('AUTO UPGRADE','green')}
  You can enable this feature by issuing:
  {colored('sudo nodectl configure -e','cyan')}
  
  {colored('Auto upgrade','cyan')} can only be enabled with auto restart enabled.
  
  During a Tessellation upgrade, the session will change.  This will trigger
  an auto restart.  During the restart, nodectl will identify the version of 
  Tessellation on the Node verses what is running on the cluster. If it does not
  match, nodectl will attempt to upgrade the Tessellation binaries before 
  continuing.
  
  {colored('IMPORTANT','red')}
  {colored('nodectl','blue',attrs=['bold'])} will not auto_upgrade itself.  Newer versions of 
  nodectl may require a {colored('upgrade','green')} be executed in order to update 
  any system services or files that may have changed [for any of 
  many reasons].
  
  {colored('** IMPORTANT **','red',attrs=['bold'])}
  {colored('nodectl','blue',attrs=['bold'])} {colored('auto_restart/auto_upgrade','yellow')} 
  Will {colored('not','red',attrs=['bold'])} work unless the p12 passphrase is present in the configuration
  file.  In order to join the network unattended, {colored('nodectl','blue',attrs=['bold'])} will need to
  know how to authenticate against the Hypergraph.
    
  Example Usage
  -------------

  show this help screen
  # {colored('sudo nodectl auto_restart help','cyan')}
  # {colored('sudo nodectl auto_upgrade help','cyan')}

  persist auto_restart in configuration and auto_upgrade
  # {colored('sudo nodectl configure','cyan')}
  choose Edit --> Auto Restart Section
  
  manual enable auto_restart services
  # {colored('sudo nodectl auto_restart enable','cyan')}

  manual disable auto_restart services
  # {colored('sudo nodectl auto_restart disable','cyan')}

  manual restart auto_restart services
  # {colored('sudo nodectl auto_restart restart','cyan')}

  check if auto_restart is running by searching for
  the process id ({colored('pid','white',attrs=['bold'])}) of the auto_restart service.
  The command will also show status of auto features set in
  the configuration.
  # {colored('sudo nodectl auto_restart check_pid','cyan')}
   or
  # {colored('sudo nodectl auto_restart status','cyan')}
  
  '''      
        
        
    if extended == "reboot":
        help_text += title("reboot")
        help_text += f'''
  The {colored('reboot','cyan')} command does not take any arguments 
  and offers the Node Operator the ability to reboot their
  physical or VPS (Virtual Private Server in the cloud) via 
  a {colored('warm boot','yellow')}.
  
  For Node Operation this command is {colored('preferred/recommended','green',attrs=['bold'])} 
  over normal operating system reboot command. 
  
  When issued the {colored('nodectl reboot','cyan')} command will gracefully
  leave the profiles defined in the nodectl configuration file 
  before rebooting the Node.
  
  Definition:  {colored('warm boot:','yellow')} restart your entire system via software
               {colored('cold boot:','yellow')} physical start and stop of your Server or VPS
   
  '''      
        
        
    if extended == "refresh_binaries":
        help_text += title(extended)
        help_text += f'''
  The {colored(extended,'cyan')} command takes several arguments.
  
  This command will download and overwrite the existing Tessellation
  binaries files that are required to run your Node.  The result of 
  this command will be to download the binaries from the latest
  release and is independent of a system upgrade.
  
  This command can be used to {colored("refresh",'cyan')} your binaries in the event
  that you have a corrupted system.
  
  This command should be accompanied by the restart command in order
  to allow your Node to utilize the new binary files.
  
  This includes the latest seed-list access list file.
  
  required:
  {colored('-e <environment_name>','green')}
       
  optional option alias:
  {colored('-rtb','green')} 
       
  optional:
  {colored('-v <version_string>','cyan')} 
  
  If {colored('-v <version_string>','cyan')} not added the latest known version will be downloaded. The
  {colored('-v <version_string>','cyan')} should only be used in the event of a downgrade request or 
  other unique scenarios that may warrant a older (or newer) release.
  
    Example Usage
  -------------
  show this help screen
  # {colored(f'sudo nodectl {extended} help','cyan')}
  
  execute the {extended} command
  # {colored(f'sudo nodectl {extended} -e <environment_name>','cyan')}
  
  execute the {extended} command for mainnet with static 
  version of example v1.11.4
  # {colored(f'sudo nodectl {extended} -e mainnet -v v1.11.4 ','cyan')}
  '''      
        
        
    if extended == "show_service_log":
        help_text += title(extended)
        help_text += f'''
  The {colored(extended,'cyan')} command takes one argument.
  
  This command will search the Debian distribution based journal 
  specifically for service logs which launch the Tessellation process
  that allows a Node profile to connect to a cluster.
  
  You can press {colored("q",'cyan')} to quit the log viewing
  at any time.  
  
  You can press {colored("the space bar",'cyan')} to advance to the next
  screen in the logs, if multiple pages of logs are available.

  required:
  {colored('-p <profile_name>','green')}
       
  optional option alias:
  {colored('-ssl','green')} 
  
    Example Usage
  -------------
  show this help screen
  # {colored(f'sudo nodectl {extended} help','cyan')}
  
  execute the {extended} command
  # {colored(f'sudo nodectl {extended} -p <profile>','cyan')}
  '''      
        
        
    if extended == "show_dip_error":
        help_text += title(extended)
        help_text += f'''
  The {colored(extended,'cyan')} command takes one argument.
  
  This command will search the Tessellation log files for a 
  given configured profile on the Node and output any 
  occurrences of an error associated with the {colored('DownloadInProgress','yellow')}
  which may result in the Node's state changing to {colored('WaitingForDownload','yellow')}.
  
  required:
  {colored('-p <profile_name>','green')}
       
  optional option alias:
  {colored('-sde','green')} 
  
    Example Usage
  -------------
  show this help screen
  # {colored(f'sudo nodectl {extended} help','cyan')}
  
  execute the {extended} command
  # {colored(f'sudo nodectl {extended} -p <profile>','cyan')}
  '''      
        
        
    if extended == "check_seedlist_participation":
        help_text += title(extended)
        help_text += f'''
  The {colored(extended,'cyan')} command does not take any arguments.
  
  This command is a temporary feature of nodectl designed for pre-PRO
  analysis and setup only.
  
  This command can be used to {colored("review",'cyan')} seed list access-list
  participation for any/all given profile(s) in the configuration
  that has a seed-list setup.
       
  optional option:
  {colored('-cslp','green')} 
  '''      
        
        
    if extended == "view_config" or extended == "_vc":
        extended = "view_config"
        help_text += title(extended)
        help_text += f'''
  The {colored(extended,'cyan')} command does not take any arguments.
  
  nodectl uses a configuration file in YAML format.
  This command will offer the Node Operator the ability to review
  the contents of this YAML file {colored('cn-config.yaml','cyan')}.
  
  options:
  {colored('-np','cyan')} : no pagination
  
  optional option:
  {colored('-vc','green')} 
  
  
  '''      
  
    if extended == "check_versions":
        help_text += title(extended)
        help_text += f'''
  
  This command will request nodectl will go out and review the latest versions 
  of both Constellation Network Tessellation and nodectl. nodectl will review 
  the current github repo and compare it to the versions running
  on the Node.  
  
  It will report back {colored('True','green')} or {colored('False','red')}
  based on whether the versions match.
  
  If a profile name is not supplied, nodectl will use the first found
  profile configured on the Node.
     
  optional option:
  {colored('-cv','green')} 
  
  optional parameters:
  {colored('-p <profile_name>','cyan')} 
  '''      
  
    if extended == "uptime":
        help_text += title(extended)
        help_text += f'''
  
  This command nodectl will go out and pull the uptime for the cluster
  the Node itself and the system supporting the node.

  - Cluster:  How long has the cluster been up
  - Node:     How long has the Node been up
  - System:   How long has the system whether
              a Bare Metal or virtualize server
              been up
  
  optional parameters:
  {colored('-p <profile_name>','cyan')} 
  '''      
        
        
    if extended == "validate_config" or extended == "_val":
        extended = "validate_config"
        help_text += title(extended)
        help_text += f'''
  The {colored(extended,'cyan')} command does not take any arguments.
  
  nodectl uses a configuration file in YAML format.
  This command will offer the Node Operator the ability to validate
  the contents of this YAML file {colored('cn-config.yaml','cyan')}.
  
  {colored('WARNING:','yellow')} The configuration validator can only attempt to
           validate the contents of {colored('cn-config.yaml','cyan')} file to 
           the best of its ability. It is advantageous to make 
           the best attempts to enter the correct information and 
           not rely on the validator to be the final oracle.
           
           See the {colored('Constellation Network Documentation Hub','blue',attrs=['bold'])} for 
           a detailed explanation of each element in the 
           {colored('cn-config.yaml','cyan')} file. 
     
  optional option:
  {colored('-val','green')} 
  '''      
        
        
    if extended == "upgrade_path":
        help_text += title(extended)
        help_text += f'''
  The {colored(extended,'cyan')} command does not take any arguments 
  and offers the Node Operator the ability to check their Node's
  current nodectl version for upgrade path requirements.
  
  If the Node is not at the most current version of nodectl, this
  command will warn you of this fact, let you know what the next
  necessary upgrade is, and will show you upgrade path requirements.
   
  optional option:
  {colored('-up','green')} 
  '''      
        
        
    if extended == "create_p12_key":
        help_text += title(extended)
        help_text += f'''
  The {colored(extended,'cyan')} command takes up to four optional argument and 
  attempts to create a new p12 file, independent of the Node's operations.  This
  new wallet can be used in any way necessary by the creator.
  
  shortcut option:
  {colored('-cpk','green')}
  
  optional option:
  {colored('--name','green')} 
  {colored('--keystore','green')} 
  {colored('--pass','green')} 
  {colored('--alias','green')} 
  
  If you do not offer any or all of the optional options during execution of
  the command, you will be prompted for them individually in an interactive
  manner by {colored('nodectl','cyan')}. 
    
     {colored('--name','yellow')}:  Name of the p12 key file you would like
                                    to create.  This must have the {colored('.p12','cyan')}
                                    extension.
  {colored('--keystore','yellow')}:  The location that you would like the p12 key file
                                     to be saved to after creation.
   {colored('--pass','yellow')}:  The passphrase that you would like to use to unlock the
                                  p12 key file. 
        {colored('--alias','yellow')}:  The p12 key file's wallet alias.
        
  Example Usage
  -------------
  show this help screen
  # {colored('sudo nodectl create_p12_key help','cyan')}
     or
  # {colored('sudo nodectl -cpk help','cyan')}
  
  normal interactive operation
  # {colored('sudo nodectl create_p12_key','cyan')}
     or
  # {colored('sudo nodectl -cpk','cyan')}      
  
  normal non-interactive operation
  # {colored('sudo nodectl create_p12_key --name myp12.key --keystore /home/nodeadmin/p12_files/','cyan')}
    {colored('--pass swordfish --alias myp12alias','cyan')}
     or
  # {colored('sudo nodectl -cpk --name myp12.key --keystore /home/nodeadmin/p12_files/','cyan')}
    {colored('--pass swordfish --alias myp12alias','cyan')}
     
'''

        
    if extended == "nodeid":
        help_text += title("nodeid or id")
        help_text += f'''
  The {colored('nodeid','cyan')} and {colored('id','cyan')} are interchangeable commands that result in the same output. 
  
  The command takes one optional argument and attempts to display the {colored('NODE ID','yellow')} 
  associated with the p12 file found on the system (from the configuration).
  
  required:
  {colored('-p <profile_name>','green')}
  
  optional:
  {colored('-wr','green')} ( alternative tool set )
  {colored('-t <ip_address>','green')} ( target ip address )
    
  The -wr option will attempt to extract the node id from the 
  wallet.jar file via the public key 
  
  Omitting the -wr will do a normal lookup using the show-id 
  option that is normally the best option to display the node id.
  
  The -t option will lookup the nodeid based on the ip address specified
  after the -t is entered on the command line
  
     {colored('IP ADDRESS','yellow')}:  The IP address of the Node the command was issued against.
  {colored('P12 FILE NAME','yellow')}:  Name of the p12 file found on the Node.
   {colored('P12 LOCATION','yellow')}:  System path to the p12 file found on the Node.
        {colored('NODE ID','yellow')}:  The Node ID extracted from the p12 file.
  
  Example Usage
  -------------
  show this help screen
  # {colored('sudo nodectl nodeid help','cyan')}
     or
  # {colored('sudo nodectl id help','cyan')}
  
  normal operation
  # {colored('sudo nodectl nodeid -p <profile_name>','cyan')}
     or
  # {colored('sudo nodectl id -p <profile_name>','cyan')}
  
  alternative method
  # {colored('sudo nodectl nodeid -wr -p <profile_name>','cyan')}
     or
  # {colored('sudo nodectl id -p <profile_name> -wr','cyan')}
   
  lookup nodeid for ip address 10.10.10.10 on profile dag-l0
  # {colored('sudo nodectl nodeid -p dag-l0 -t 10.10.10.10','cyan')}
  '''      
        
        
    if extended == "dag":
        help_text += title("dag")
        help_text += f'''
  The {colored('dag','cyan')} command takes no arguments and attempts to display the {colored('$DAG','yellow')} 
  wallet details associated with the p12 file found on the system (from the configuration).
  
  required:
  {colored('-p <profile_name>','green')}
  
  optional:
  {colored(' -w <DAG_address>','green')}
  {colored(' -b ','green')} ( brief )
  {colored('-np ','green')} ( no pagination )
  {colored('--csv','green')} create csv output instead of print out
  {colored('--output <file_name>','green')} used with --csv to create
                                            custom file name for csv
                                            output.
                                            
          The --output can only be a filename.  If you would like to
          have your output saved to an alternate location, you can
          update the configuration file via the 'configure' command.
          
          {colored('sudo nodectl configure','cyan')}                                                 
     {colored('IP ADDRESS','yellow')}:  The IP address of the Node the command was issued against.
  {colored('P12 FILE NAME','yellow')}:  Name of the p12 file found on the Node.
   {colored('$DAG ADDRESS','yellow')}:  The address associated with your p12 Node's wallet.
   {colored('$DAG BALANCE','yellow')}:  Balance of $DAG tokens found for your wallet, in the ledger.
     {colored('$USD VALUE','yellow')}:  Converts the $DAG tokens to $USD based on the current price per $DAG.
     {colored('$DAG PRICE','yellow')}:  Price CoinGecko returns for the $DAG at the current moment of the command issuance.
              
  It the {colored('-b','cyan')} command is not specified, immediately following the main wallet output information
  (as shown above) a table of data related to the last 350 snapshots will be presented to the
  Node operator.  This will include:
  
    - {colored('TIMESTAMP','yellow')}
    - {colored('ORDINAL','yellow')}
    - {colored('REWARD OF THAT SNAPSHOT','yellow')}
    - {colored('TOTAL REWARDS FOR SNAPSHOT TIME FRAME','yellow')}
  
  Finally the estimated time period which included the last 350 snapshots
  will be displayed.
  
  Example Usage
  -------------
  show this help screen
  # {colored('sudo nodectl dag help','cyan')}
  
  show dag information
  # {colored('sudo nodectl dag -p <profile_name>','cyan')}
  
  show dag information for another wallet
  # {colored('sudo nodectl dag -p <profile_name> -w <DAG_wallet_address>','cyan')}
  
  show dag wallet balances only
  # {colored('sudo nodectl dag -p <profile_name> -b','cyan')}
  
  show full dag wallet details but do not paginate
  # {colored('sudo nodectl dag -p <profile_name> -np','cyan')}

  create a csv file 
  # {colored('sudo nodectl dag -p <profile_name> --csv','cyan')}
  create a csv file named test.csv
  # {colored('sudo nodectl dag -p <profile_name> --csv --output test.csv','cyan')}
  '''      
        
        
    if extended == "passwd12":
        help_text += title(extended)
        help_text += f'''
  The {colored('passwd12','cyan')} command does not take any arguments 
  and offers the Node Operator the ability to change their p12
  keystore file's passphrase through an interactive experience.
  
  This command will {colored('not','red')} update the {colored('cn-config.yaml','green')} file.
  
  Please run the {colored('sudo nodectl configure','cyan')} command to
  update your passphrase (if necessary) after completing 
  the passphrase update utility command.
  
  '''      
        
        
    if extended == "upgrade_nodectl":
        help_text += title(extended)
        help_text += f'''
  The {colored('upgrade_nodectl','cyan')} command will launch the process requirements
  to upgrade the nodectl binary on your Node.
  
  optional:
  {colored('-v <version>','green')}
  
  usage
  -------------
  show this help screen
  # {colored('sudo nodectl upgrade_nodectl help','cyan')}
  
  execute an upgrade of nodectl
  # {colored('sudo nodectl upgrade_nodectl','cyan')}
  
  execute an upgrade of nodectl to version "v2.12.0"
  # {colored('sudo nodectl upgrade_nodectl -v v2.12.0','cyan')}
      
  '''      
        
        
    if extended == "list":
        help_text += title(extended)
        help_text += f'''
  The {colored('list','cyan')} command does not take any arguments 
  and displays the details of the profiles 
  found in the {colored('cn-config.yaml','green')} file.
  
    optional:
    {colored('-p','green')} : print out only profile names on the Node
  '''      
        
        
    if extended == "price":
        help_text += title(extended)
        help_text += f'''
  The {colored(extended,'cyan')} command does not take any arguments.
  
  Performs a quick lookup for crypto prices via CoinGecko's public API
  
      currently:  {colored('Constellation Network','green',attrs=['bold'])}, 
                  {colored('Lattice Exchange','yellow')}, 
                  {colored('BitCoin','yellow')}, 
                  {colored('Ethereum','yellow')}, 
                  {colored('Quant Network','yellow')}
  '''      
        
        
    if extended == "markets":
        help_text += title(extended)
        help_text += f'''
  The {colored(extended,'cyan')} command does not take any arguments.
  
  Performs a quick lookup for crypto markets via CoinGecko's public API
  
  The command will list the {colored('Top 10','cyan')} Crypto markets at the current moment in 
  time and in the event that {colored('Constellation Network','green')} is not in the top ten, 
  it will list it's current position in relation to the rest of the known 
  markets.
  '''      
        
        
    if extended == "verify_nodectl":
        help_text += title(extended)
        help_text += f'''
  The {colored(extended,'cyan')} command does not take any arguments.
  
  Since Python is a interpreted language and nodectl is open source, it
  it is hard to incorpotate a way to prevent man-in-the-middle attacks to
  obviate authenticity concerns; however, we will still try :-)
  
  nodectl is compliled into a binary and the binary is code signed using
  an internal private key.  The code signed hash and the public key are
  available on the github respository and downloaded via an HTTPS connection.  
  
  {colored(extended,'cyan')} will download [every time requested] the:
   - public key
   - hash of the binary
   - signature signed by the private key
   
  The utility will verify the binary by decrypting the binary using the hash 
  utilizing the public key and comparing to the signature of the
  digital hash.  {colored(extended,'cyan')} will also offer you manual instructions 
  on how to verify that the hash and public key match what is available on 
  the repository. 

  Be aware that if you download a version of nodectl from a nefarious source 
  [ unkowningly ] "they" can easily provided a public key and binary hash from that
  same source which will give you a {colored('FALSE POSITIVE','red')} sense of authenticity.
  
  As safe guards, nodectl will provide you with the proper link to view the
  public key and binary hash manually, so that you can see if they match what 
  is on your node directly, this is a manual intervention that will asure you 
  that you have a valid copy of nodectl. As also shown above ^
    
  public_key (of current version only) replace <version> with currently
  version not including periods:  eg) v2.10.0 = v2100
  
  https://github.com/StardustCollective/nodectl/blob/<version>/admin/nodectl_public 
  
  signature file (of current version only)
  https://github.com/StardustCollective/nodectl/releases/download/<version>/nodectl.sig 
      
  digital_code_sign_hash (of current version only)
  https://github.com/StardustCollective/nodectl/blob/<version>/admin/nodectl_public    
  
  Note: public key and hash are available as part of the code base under the 
        admin folder for ease of viewing
        signature file is a binary available in the version assets
        
  If you would like to compare public and binary hash for versions lower than
  the current version, you can download them from the release artifacts on the
  Github repository, tagged for that specific version.
  '''      
        
        
    if extended == "markets":
        help_text += title(extended)
        help_text += f'''
  The {colored(extended,'cyan')} command does not take any arguments.
  
  Performs a quick lookup for crypto markets via CoinGecko's public API
  
  The command will list the {colored('Top 10','cyan')} Crypto markets at the current moment in 
  time and in the event that {colored('Constellation Network','green')} is not in the top ten, 
  it will list it's current position in relation to the rest of the known 
  markets.
  '''      
        
        
    if extended == "install":
        help_text += title(extended)
        help_text += f'''
  The {colored('install','cyan')} command does not take any arguments and will attempt
  to turn your VPS, Bare Metal or Containers [box] into Constellation
  Nodes!
  
  {colored('IMPORTANT','red',attrs=['bold'])}: This is for creating a brand new node on your box, 
  and should {colored('not','red',attrs=['bold'])} be used on an existing Node. Doing so may have 
  unexpected and uncertain results.
  
  {colored('REQUIREMENTS','green',attrs=['bold'])}
     - Debian Based Linux System
     - 16Gb RAM
     - 4x vCPU
     - 160Gb HD
     - Internet Access
  '''      
          
    if extended == "upgrade":
        help_text += title(extended)
        help_text += f'''
  The {colored(f'{extended}','cyan')} command takes optional arguments and will attempt
  to {colored('upgrade','green',attrs=['bold'])} the local Constellation Node!
  
  optional:
  {colored('--nodectl_only','green')}
        If added, nodectl will only upgrade the necessary components that nodectl
        may require to function properly.  It will avoid the need of installing and
        restarting the Node's Tessellation services. 
  {colored('--ni','green')} - ({colored('non-interactive','cyan')})
        If the {colored('--ni','cyan')} option is given at the command entry point, the upgrade 
        will not ask for interaction and will choose all default values 
        including:
          - picking the latest found {colored('version','yellow')} (unless {colored('-v','cyan')} is specified as well)
          - choosing {colored('yes','yellow')} to clearing the backups, uploads and logs with the default
            values of 7 days (logs) and 30 days (snapshots)
          - {colored('Note:','yellow',attrs=['bold'])} You will still be prompted for a valid passphrase
            unless the {colored('--pass','green')} option is passed as well.
          - {colored("Warning:","red",attrs=['bold'])} non-interactive mode will still request your passphrase
            on startup of the {colored('nodectl','cyan')} utility if omitted from the configuration yaml.
          - {colored("Warning:","red",attrs=['bold'])} non-interactive mode will still request for your authorization
            to upgrade when the upgrade path is incorrect (you are not at a valid version level).
  {colored('-v','green')} - {colored('version','cyan')}
        If specified at the command line, the value given will be used 
        and the Node Operator will not be prompted for a {colored('Tessellation','cyan')} version.
        The version parameter must in the following format {colored('vX.X.X','yellow')} where 
        the {colored('X','yellow')} is an integer (number).
        example) {colored('v2.0.0','cyan')}
  {colored('-f','green')} - {colored('force','cyan')}
        If specified at the command line, nodectl will not check version 
        specifications when accompanied by the {colored('--ni','cyan')} or {colored('-v','cyan')} parameter.  
        This will by-pass warning messages if you are attempting
        to install versions of nodectl or Tessellation that are not current, 
        custom, or that do not meet the current standard versioning 
        format specifications.
  
  {colored('IMPORTANT','red',attrs=['bold'])}: This is not the same as the {colored('upgrade_nodectl','cyan')} command.
  
  This command serves a couple of purposes:
  
  {colored('1.','blue',attrs=['bold'])} {colored('Tessellation upgrade','green',attrs=['bold'])} This command should be executed when there are updated new 
     Constellation Network releases of the Tessellation packages.  It is best to keep 
     with the latest versions of {colored('Tessellation','cyan')} in order to keep up with new features, 
     security fixes, bug fixes, and overall compatibility with the Hypergraph cluster 
     your Node plans to or is participating in.
     
  {colored('2.','blue',attrs=['bold'])} {colored('nodectl upgrade','green',attrs=['bold'])} As new versions of {colored('nodectl','cyan')} are released, there are 
     two types of releases.
     
        {colored('a.','cyan')} An update to nodectl that fixes some routine bugs, security updates,
           or new features that do {colored('not','red',attrs=['bold'])} need an upgrade. In this case,
           you will {colored('not','red',attrs=['bold'])} be requested to use this command.
           
        {colored('b.','cyan')} An update to nodectl that manipulates or adds new system files or 
           or new features that {colored('will','green',attrs=['bold'])} require you to issue
           an upgrade.  {colored('NOTE','yellow')}: nodectl will request this upgrade after a
           {colored('sudo nodectl upgrade_nodectl','cyan')} is issued as part of that command's
           automation process.  
           
           See {colored('sudo nodectl upgrade_nodectl help','cyan')}.  
           
   {colored('WARNING','yellow',attrs=['bold'])}: The {colored(f'{extended}','cyan')} command will cause your Node to leave the cluster(s) it is 
            participating in, during the upgrade process.  The {colored(f'nodectl','cyan')} utility will 
            attempt to remove your Node from all clusters, upgrade, and then 
            return your Node to the cluster(s).
  '''      
        
        
    if extended == "whoami":
        help_text += title(extended)
        help_text += f'''
  The {colored('whoami','cyan')} command displays the external ip address 
  of your Node. Unless optional -id is specified.
  
  The external IP of your Node is the address that allows your Node
  to communicate with the rest of the systems on the Internet.  This
  is the address that your Node will use to communicate with the rest
  of the decentralized Nodes that make up the Global Layer0, cluster or
  Metagraph that your Node will attempt to communications 
  with via p2p connections and APIs.
  
  optional option:
  {colored('-id <full_node_id> -p <profile_name>','green')}
  
  The -id option followed by the full nodeid requested, will lookup
  the node id and return its IP address.  This command will 
  {colored('require','cyan')} the {colored('-p','cyan')} with the
  profile name of the network you are searching.
  
  example)
  # {colored('sudo nodectl whoami -id <node_id> -p <profile>','cyan')}
  '''
        
        
    if extended == "nodeid2dag":
        help_text += title(extended)
        help_text += f'''
  The {colored('nodeid2dag','cyan')} command will take in a required
  128 byte hexadecimal string and converts it into 
  its associated Constellation Network DAG 
  wallet address.
  
  required:
  {colored('<node id>','green')}
  
  example)
  # {colored('sudo nodectl nodeid2dag <node_id>','cyan')}
  '''
        
        
    if extended == "health":
        help_text += title(extended)
        help_text += f'''
  The {colored(extended,'cyan')} command does not take any arguments 
  and displays the basic health elements of your Node.

  {colored("OK","green")}:   Falls within normal operating parameters
  {colored("LOW","red")}:  Falls outside of normal operating parameters
  {colored("WARN","yellow")}: Falls outside of normal operating parameters
  
  {colored("15M CPU","blue",attrs=['bold'])}:      Average usage of CPU over 15 minute intervals
  {colored("DISK USAGE","blue",attrs=['bold'])}:   How much hard drive (DISK) space is in use
  {colored("UPTIME_DAYS","blue",attrs=['bold'])}:  How long the operating system has been running
                since the last boot/reboot
  {colored("MEMORY","blue",attrs=['bold'])}:       RAM usage
  {colored("SWAP","blue",attrs=['bold'])}:         SWAP space HD usage
  '''
        
        
    if extended == "sec":
        help_text += title("show security")
        help_text += f'''
  The {colored(extended,'cyan')} command does not take any arguments 
  and displays parsed elements from the {colored('auth.log','cyan')} file on your
  Debian operating system.
  
  The results will be based off the current and last "rolled" auth.log file.
  
  {colored("LOG ERRORS          ACCESS ACCEPTED     ACCESS DENIED       MAX EXCEEDED        PORT RANGE","blue",attrs=['bold'])}
  10                  31                  41                  39                  1024-4000

  {colored("LOG ERRORS","cyan")}:       How many ERROR statements were found
  {colored("ACCESS ACCEPTED","cyan")}:  Count of how many logins were requested and accepted
  {colored("ACCESS DENIED","cyan")}:    Count of how many Invalid logins were found
  {colored("MAX EXCEEDED","cyan")}:     Count of how many Invalid logins were blocked due to excessive attempts
  {colored("PORT RANGE","cyan")}:       What the minium and maximum port range for the denied attempts were identified
  
  {colored("Since Date","blue",attrs=['bold'])}: The creation date of the last {colored('auth.log','cyan')} that was reviewed.
  '''
  
        
    if extended == "show_current_rewards":
        help_text += title(extended)
        help_text += f'''
  This command takes several parameters
  (see below)
  
  Search the Constellation Backend explorer and
  pull the last 50 global snapshots.
  
  The command will output a paginated list of
  DAG addresses and the amount of DAG accumulated
  per DAG address over the course of the time
  between the START SNAPSHOT timestamp listed
  and the END SNAPSHOT timestamp listed.
  
  This only pertains to global MainNet rewards*
  This does not apply to TestNet rewards*
  
  Order of arguments does not matter.
  
  short argument:
  {colored('-scr','magenta')}
  
  optional:
  {colored('-p <profile>','green')}
  {colored('-w <dag_wallet_address>','green')}
  {colored('-s <snapshot_history_size>','green')}
  {colored('-np','green')} no pagination (do not paginate)
  {colored('--csv','green')} create csv output instead of print out
  {colored('--output <file_name>','green')} used with --csv to create
                                            custom file name for csv
                                            output.
  
          The --output can only be a filename.  If you would like to
          have your output saved to an alternate location, you can
          update the configuration file via the 'configure' command.
          
          {colored('sudo nodectl configure','cyan')} 
                                              
  If a wallet address is not specified the first known wallet address
  obtained from the configuration will be used.  If a {colored('-p <profile>','green')} is specified
  the wallet address known to entered profile will be used.
  
  If a {colored('-s <snapshot_history_size>','green')} is specified the history
  size entered will be used.  Must be between 10 and 375 snapshots.  The default
  value is 50.
  
  Note: Currently this command only searches on the MainNet layer0
        global network..
        
        If the{colored('-w <dag_wallet_address>','green')} is used, the {colored('-p <dag_wallet_address>','red')} will be ignored unless the profile
        fails to be present on the Node (exist in the configuration).
        
  Example Usage
  -------------
  show this help screen
  # {colored('sudo nodectl show_current_rewards help','cyan')}
  # {colored('sudo nodectl -scr help','cyan')}

  If the {colored('-p <profile>','green')} if not specified, nodectl
  will use the first known profile. The profile will be ignored
  if the -f option is entered.
  # {colored('sudo nodectl show_current_rewards','cyan')}
  # {colored('sudo nodectl show_current_rewards -p <profile_name>','cyan')}

  If the {colored('-w <dag_address>','green')} is specified, nodectl
  will the requested DAG address against the MainNet explorer.
  # {colored('sudo nodectl show_current_rewards -w <dag_address>','cyan')}
  
  If the {colored('-np','green')} is not specified nodectl 
  will attempt to paginate the output to the 
  current known screen height.
    
  create a csv file 
  # {colored('sudo nodectl show_current_rewards --csv','cyan')}
  create a csv file named test.csv
  # {colored('sudo nodectl show_current_rewards --csv --output test.csv','cyan')}
  '''
      
    if extended == "find":
        help_text += title(extended)
        help_text += f'''
  This command takes several parameters
  (see below)
  
  This command will attempt to find the requested peer
  on the current connected network cluster.

  The find command offers insight into the 
    - number of nodes on the cluster
    - number of nodes in 'Ready' state
    - number of nodes in 'Observing' state
    - number of nodes in 'WaitingForReady' state
    
  It will show you the profile searched (required)
  and offer you confirmation that your Node is
  seen on the cluster.

  required:
  {colored('-p <profile_name>','green')}
  
  You may specify a 'source' node that will be used as
  to lookup the 'target' node on the cluster and return
  a True or False depending on whether or not it is found
  
  optional:
  {colored('-s <source_node>','green')} ( ip or hostname )
  {colored('-t <target_node>','green')} ( ip or hostname )
  
  {colored('NOTE:','yellow')} Choosing a source node that is not on the network 
  may result in an error or false negative.
  
  {colored('NOTE:','yellow')} You can use the keyword {colored('self','green')}
  to indicate the local (localhost) Node for either {colored('-s','cyan')} or {colored('-t','cyan')}
  
  Example Usage
  -------------
  show this help screen
  # {colored('sudo nodectl find help','cyan')}

  Check if your Node is listed/seen on the
  cluster using a random source Node that is
  already found on the cluster.
  # {colored('sudo nodectl find -p <profile_name>','cyan')}

  Check if your Node is listed/seen on the
  cluster using a specific source Node.
  # {colored('sudo nodectl find -p <profile_name> -s <source_ip_host>','cyan')}

  Check if your Node is listed/seen on the
  cluster using a specific source Node and
  a specific target Node (other then your own)
  # {colored('sudo nodectl find -p <profile_name> -s <source_ip_host> -t <target_ip_host>','cyan')}

  Order of the values does not matter

  example 1
  ---
  If our node is 10.1.1.1
  check if 10.1.1.1 is listed/seen by another
  random Node on the cluster we are connected to
  # {colored('sudo nodectl find -p dag-l0 ','cyan')}
  or
  # {colored('sudo nodectl find -p dag-l0 -t 10.1.1.1','cyan')}

  example 2
  ---
  If our node is 10.1.1.1
  check if 10.1.1.1 is listed/seen by a Node
  identified by the -s option on the cluster
  we are connected to
  # {colored('sudo nodectl find -p dag-l0 -s 10.2.2.2','cyan')}
  or
  # {colored('sudo nodectl find -p dag-l0 -s 10.2.2.2 -t 10.1.1.1','cyan')}
  
  Examples using {colored('self','cyan')} keyword
  # {colored('sudo nodectl find -p dag-l0 -s self -t 10.1.1.1','cyan')}
  # {colored('sudo nodectl find -p dag-l0 -s 10.2.2.2 -t self','cyan')}

  example 3
  ---
  If a different target node 10.1.1.2 identified by a -t
  is listed/seen by a Node identified by the -s Node
  option on the cluster we are connected to
  # {colored('sudo nodectl find -p dag-l0 -s 10.2.2.2 -t 10.1.1.2','cyan')}

        '''
        
        
    if extended == "logs":
        help_text += title(extended)
        help_text += f'''
  This command will print out the contents of the
  logs that have been requested.

  There are several options available to the 
  Node Operator

  Syntax:
  # {colored("sudo nodectl logs -p <profile_name> <log_name> [-g <grep_value>] [-f]","cyan")}

  example)
  Request to follow the log app.log from the dag-l0 profile filtering out the word "error" from each line.

  # {colored("sudo nodectl -p dag-l0 -l app -g error -f","cyan")}

  {colored("PARAMETERS","white",attrs=['bold'])}
  ========================
  {colored("-p","cyan")} <profile>  <== The name of the profile. This is important
                    because (for example) the {colored("app.log","cyan")} shares the 
                    same log name for each profile.  The Node Operator will need
                    to specify which profile to review.
                  
  {colored("-l","cyan")} <log_name> <== Name of the log that you would like to review
                    Options:
                      - {colored("app","cyan")}
                      - {colored("http","cyan")}
                      - {colored("nodectl","cyan")}
                    
  {colored("-g","cyan")} <word>     <== filter out (grep) the word {colored("<word>","cyan")}.
                    This is case insensitive
                  
  {colored("-f","cyan")}            <== follow the log line by line.  As a new line is
                    added to the log during execution of user or
                    program initiated elements that might print
                    to the log file being monitored.
                  
                    To cancel out of the "{colored("-f","cyan")}" command you will
                    simultaneously press and hold the control ({colored("ctrl","cyan")})
                    key on your keyboard and press the "{colored("c","cyan")}" key.

  # {colored("sudo nodectl logs","cyan")}

  This command will give you an option of which profile and log you
  would like to view.  This does not offer the ability to follow or
  grep out any specific information.
        ''' 
        
        
    if extended == "clean_files":
        help_text += title(extended)
        help_text += f'''
  The command {colored(extended,"cyan")} will offers the Node Operator the
  ability to clear specified logs or special stored files 
  that may not be needed anymore.

  Syntax:
  # {colored("sudo nodectl clear_logs -t <log_type>","cyan")}
  
  Optional Shorthand:
  {colored("-cf","yellow")}

  Required Parameters:
  {colored("-t","cyan")} (type)
  
  Possible Values for {colored("-t","yellow")} option:
  ------------------------------
  {colored("logs","yellow")}:      clear logs located in the default 
             or specified log directories
             - logs command handles json_logs and archived logs
  {colored("uploads","yellow")}:   clear uploads located in the default 
             or specified log directories
  {colored("backups","yellow")}:   clear backups located in the default 
             or specified log directories
  
  Once the command is executed the Node Operator will be 
  offered a CLI menu of removal options to choose.
  
  The option will be carried out and the Node Operator 
  will be offered a visual confirmation of the files to 
  be removed, number of files, and size to be freed by 
  their removal.
  
  example usage:
  --------------
  show this help screen
  # {colored(f'sudo nodectl {extended} help','cyan')}  
  
  request to clear Tessellation logs which
  will include the archived and json_logs
  # {colored("sudo nodectl clean_files -t logs","cyan")}
  or
  # {colored("sudo nodectl -cf -t logs","cyan")}
        ''' 
        
        
    if extended == "clean_snapshots":
        help_text += title("clean snapshots")
        help_text += f'''
  The command does not take any arguments.

  The core data objects that drive the HGTP Cluster are the data
  snapshots.  These snapshot files can be seen similar in concept to
  what a database might do operationally on a standard web2 
  application; however, decentralized, and used on the Hypergraph
  to coordinate data validation and consensus.

  From time to time, these files can build up and cause your 
  Node to run out of disk space.

  The clean snapshots command will offer the Node Operator the
  ability to clean out the older [{colored(" > 30 days ","cyan")}] files from the
  Node.

  {colored("NOTE","yellow")}: In the event that your Node requires another snapshot file
  that has been deleted by this command (or manually by the
  Node Operator [{colored("discouraged","red")}]) your Node may attempt
  to download the snapshots again.  This will cause excessive
  I/O and performance issues with your Node.

  {colored("Continue with caution","yellow")}
        ''' 
        
        
    if extended == "check_seedlist":
        help_text += title("check seedlist")
        help_text += f'''
  The command takes one argument.
  
  required:
  {colored('-p <profile_name>','green')} 
  
  optional:
  {colored('-id <node_id>','yellow')} 
  {colored('-t <target_ip_address>','yellow')} 
  
  {colored("check_seedlist","cyan")} will pull your nodeid out of your 
  p12 file and compare it to the seedlist downloaded from
  Constellation Network's authorized list.
  
  This command is specific to current restrictions placed
  on the Hypergraph for controlled access prior to the
  PRO Score [{colored("proof of reputable observation","yellow")}] release.
  
    Example Usage
  -------------
  show this help screen
  # {colored(f'sudo nodectl {extended} help','cyan')}  
  
  {extended} for the configured profile_name
  # {colored(f'sudo nodectl {extended} -p <profile_name>','cyan')}  
  
  {extended} for the configured profile_name dag-l0 for ip address 10.10.10.10
  # {colored(f'sudo nodectl {extended} -p dag-l0 -t 10.10.10.10','cyan')}  
  
  {extended} for the configured profile_name "dag-l0" looking for <node_id>
  where <nodeid> is replaced with a 128bit nodeid
  # {colored(f'sudo nodectl {extended} -p dag-l0 -id <node_id>','cyan')}  
        ''' 
        
        
    if extended == "start" or extended == "stop":
        help_text += title(f"{extended} service")
        help_text += f'''
  The command takes a single argument.
  
  required:
  {colored('-p <profile_name>','green')} 
    
  nodectl uses debian linux services to run each profile.  
  The {extended} command will attempt to {extended} the service.
  
  Example Usage
  -------------
  show this help screen
  # {colored(f'sudo nodectl {extended} help','cyan')}  
  
  {extended} the service on a configured profile_name
  # {colored(f'sudo nodectl {extended} -p <profile_name>','cyan')}  
        ''' 
        
        
    if extended == "leave":
        help_text += title(f"{extended} service")
        help_text += f'''
  The command takes a single argument.
 
  required:
  {colored('-p <profile_name>','green')}  
    
  While your Node is participating in a cluster performing
  consensus and validating data, it is part of a decentralized
  cluster, working with it's peers.
  
  Before you attempt to stop the service that is running your
  Node's current profile(s)
  {colored("sudo nodectl stop help","cyan")}
  
  A Node Operator should {colored("gracefully","green",attrs=['bold'])} exit
  the current cluster using the {colored("leave","cyan")} command.
   
  Example Usage
  -------------
  show this help screen
  # {colored(f'sudo nodectl {extended} help','cyan')}  
  
  {extended} the cluster on a configured profile_name
  # {colored(f'sudo nodectl {extended} -p <profile_name>','cyan')}  
        ''' 
        
        
    if extended == "restart":
        help_text += title(f"{extended} service")
        help_text += f'''
  The command takes multiple arguments.
  
  This command will execute a series of steps to
  bring your Node offline and then restart it and
  bring it back online.
  
  {colored("ORDER OF OPERATIONS","white",attrs=['bold'])}
   - leave all
   - stop all
   - start layer0
   - join layer0
   - start layer1 (identified via link_layer configuration)
   - join layer1 when layer0 reaches {colored("Ready","green")} state
  
  {colored("sudo nodectl leave help","cyan")}
  {colored("sudo nodectl stop help","cyan")}
  {colored("sudo nodectl start help","cyan")}
  {colored("sudo nodectl join help","cyan")}
  
  {colored("sudo nodectl restart -p all","cyan")} {colored("is highly recommend","green",attrs=['bold'])}
  
  A restart {colored("-p all","cyan")} will restart all profiles in specific order based
  on the profile's {colored("layer0_link","cyan")} parameters.
  
  required:
  {colored('-p <profile_name>','green')}  
  
  optional:
  {colored('-p all','green')} 
  {colored('-w','green')} - {colored('watch','cyan')}
        If specified at the command line, nodectl will execute the 
        restart in watch mode.  This mode simple will watch as the network
        joins to all peers. On large Hypergraph networks, this can take up
        to 5 minutes.
        
        If '-w' is not specified, the join process will wait for the 
        Node to reach a valid states (Ready States or Observing States) to
        conclude it is properly joined, and continue.

        if {colored("-p all","cyan")} is specified, nodectl will continue
        to watch the join process until the layer0 is in {colored("Ready","cyan")} state.
  {colored('-r','green')} - {colored('retries','cyan')}
        If specified at the command line, nodectl will replace all retries
        on failure with a numeric integer following the -r option.
  {colored('--peer <ip_address>','green')} - {colored('retries','cyan')}
        If specified at the command line, nodectl will lookup that specific
        peer ip address, if it is participating in consensus, nodectl will
        use that node to join the cluster.  Note: This is an IP address only 
        without the port specified. 

  Example Usage
  -------------
  show this help screen
  # {colored(f'sudo nodectl restart help','cyan')}  
  
  restart the service on a configured profile_name
  # {colored(f'sudo nodectl restart -p <profile_name>','cyan')}  
  
  restart the service on all configured profiles based on layer0_link
  # {colored(f'sudo nodectl restart -p all','cyan')}  
        ''' 
        
        
    if extended == "export_private_key":
        help_text += title("export private key")
        help_text += f'''
  required:
  {colored('-p <profile_name>','green')}  
  
  {colored("export_private_key","cyan")} will pull your private out of 
  your p12 file and print it to the screen.
  
  [ {colored("WARNING","red",attrs=["bold"])} ]
  {colored("Do not share this private key with anyone that you","red")}
  {colored("do not completely trust with your financial assets.","red")}
    
  Import the {colored("private key","cyan")} produced by this command
  into your StarGazer wallet in order to control your Node's 
  wallet.
  
  Example Usage
  -------------
  show this help screen
  # {colored(f'sudo nodectl export-private-key help','cyan')}  
  
  Export private key for p12 file used by profile <profile_name>
  # {colored(f'sudo nodectl export-private-key -p <profile_name>','cyan')}  
        ''' 
        
        
    if extended == "update_seedlist":
        help_text += title("update seedlist")
        help_text += f'''
  required:
  {colored('-e <environment_name>','green')}  
  
  {colored("update_seedlist","cyan")} will pull down the latest 
  seedlist from the Constellation Network repositories. This
  command can be used in the event your Node is unable to
  connect to the network.  
  
  Using the {colored("sudo nodectl check_seedlist","cyan")} you can confirm
  if your Node is seen on the access lists; if not, issue the
  {colored("update_seedlist","cyan")} command to attempt to correct the issue.
  
  {colored("NOTE","yellow")}: If you update the seedlist and still receive
  a {colored("False","red")}, you may need to contact a Constellation Network 
  support Administrator for further help.
    
  This command is specific to current restrictions placed
  on the Hypergraph for controlled access prior to the
  PRO Score [{colored("proof of reputable observation","yellow")}] release.
  
  Example Usage
  -------------
  show this help screen
  # {colored(f'sudo nodectl {extended} help','cyan')}  
  
  {extended} for configured environment
  # {colored(f'sudo nodectl {extended} -e <profile_name>','cyan')}  
        ''' 
        
        
    if extended == "show_service_status":
        help_text += title("show service status")
        help_text += f'''
  
  {colored("show_service_status","cyan")} will review the processes
  running on the Node, and display their current known state.

  OWNER: What profile on the Node owns the process being displayed.
  SERVICE: Name of the service that the OWNER of the process is using.
  PID = Process ID of the service as assigned by the Debian systemd system 
        manager, used to handle the logging and various utilities for the 
        assigned process.
  STATUS CODE: The code returned by the systemd manager.  These codes can
               be standard codes or custom codes for a particular 
               process in use.   
               0 = Healthy
               256 = Process exited with error
               768 = Process not running
  STATUS: Human friendly translation of the STATUS CODE
      - active (running)
      - inactive (dead)
  
  Example Usage
  -------------
  show this help screen
  # {colored(f'sudo nodectl {extended} help','cyan')}  
  
  {extended} for configured environment
  # {colored(f'sudo nodectl {extended}','cyan')}  
        ''' 
        
        
    if extended == "upgrade_vps":
        help_text += title("upgrade the VPS")
        help_text += f'''
  
  {colored("upgrade_vps","cyan")} will simply perform a
  more non-technical user friendly method of making sure 
  your VPS (or bare metal server) is up-to-date with the
  most recent packages, utilities, security requirements,
  and core distribution elements (kernels, services, etc.)

  The feature will offer you instructions on how to handle
  any interactive requirements, including handling purple
  boxes.

  The feature will update the package lists to make sure the
  VPS's Linux distribution knows that is the latest and
  available packages; followed by, issuing an upgrade to
  install and update any necessary elements.

  The command an 'apt' update and 'apt' upgrade from nodectl
  instead of the user having to do it directly from the
  Linux distribution. 
  
  Example Usage
  -------------
  show this help screen
  # {colored(f'sudo nodectl {extended} help','cyan')}  
  
  {extended} for configured environment
  # {colored(f'sudo nodectl {extended}','cyan')}  
        ''' 
        
        
    if extended == "join_all":
        help_text += title("join -p all")
        help_text += f'''
  {colored("This command has been removed after v1.12.0 of nodectl.","red")}
  
  {colored("REASON","yellow")}
  {colored("------","yellow")}
  
  It is recommended to link the Layer1 profile to Layer0 via
  the directly connected Node {colored("[ for Nodes that are running dual layers","magenta")} 
  {colored("l0 and l1 ]","magenta")} because the Node's own Layer0 is the most reliably known 
  Node [ to itself ].  This increases stability because the Node will
  know that Layer0 is up and operational and able to be reliably linked to.
  
  Layer1 profile services will "fail" when started prior to having
  a Layer0 profile to link to.  During a "join -p all" the services
  need to be started already.  Since the Node did not join Layer0 
  yet, Layer1 service will fail before the join API call can be 
  executed.  Therefor during a "join -p all" the Node's layer1
  will need to have its service restarted after Layer0 joins.
  
  "join -p all" option is not reliable.
  
  {colored("sudo nodectl restart -p all","cyan")} should be used instead.
  
  alternatively
    {colored("sudo nodectl join -p <profile_name_of_layer0>","cyan")}
    followed by
    {colored("sudo nodectl restart -p <profile_name_of_layer1>","cyan")}
  
        ''' 
        
        
    if extended == "join":
        help_text += title("join")
        help_text += f'''
  The command takes a single argument.
  
  required:
  {colored('-p <profile_name>','green')}  
    
  After your Node has it's services properly and
  successfully started
  {colored("sudo nodectl status help","cyan")}
  
  This command will parse your configuration file for
  the proper cluster join settings then attempt
  to join the cluster
  
  optional:
    {colored('--peer <ip_address>','green')} - {colored('retries','cyan')}
        If specified at the command line, nodectl will lookup that specific
        peer ip address, if it is participating in consensus, nodectl will
        use that node to join the cluster.  Note: This is an IP address only 
        without the port specified.

  Example Usage
  -------------
  show this help screen
  # {colored(f'sudo nodectl {extended} help','cyan')}  
  
  {extended} the cluster on a configured profile_name
  # {colored(f'sudo nodectl {extended} -p <profile_name>','cyan')}  
        ''' 
        
        
    if extended == "show_p12_details":
        help_text += title("Show P12 Details")
        help_text += f'''
  This command will extract the non-priviledged details out 
  of your p12 file.
  
  If provided with a {colored('-p','cyan')} option, the p12 configured on the
  Node via that profile, will be evaluated.
  
  If provided with a {colored('--file','cyan')} option the p12
  file supplied will be evaluated.
  
  P12 Name:  The name of the file being evaluated
  P12 Location: Locati on of the p12 file
  SHA1 FingerPrint:   Hash (or checksum), a fixed-size cryptographic hash function that produces a 
                      160-bit (20-byte) hash value. It is commonly used in various security 
                      applications and protocols to verify the integrity of data, including 
                      digital certificates.
  SHA256 FingerPrint: Hash (or checksum), produces a 256-bit (32-byte) hash value. Like other 
                      cryptographic hash functions, SHA-256 takes an input (or message) and 
                      produces a fixed-size string of characters, making it suitable for 
                      verifying the integrity of data.
  Creation Date:  When was the certificate created.
  Version:        The version number of the certificate.
  Keys Found:     How many keys does this p12 key store file hold.
  Signature Algo: Method or algorithm used to generate a digital signature and 
                  verify its authenticity.
  Public Algo:    Public algorithm that is a type of cryptographic algorithm that 
                  uses two mathematically distinct keys.
    - The public key is shared openly, and it's used for encryption or verification. 
    - The private key is kept secret and is used for decryption or signing.
  Entry Type:     Refers to the different types of cryptographic objects or entities 
                  that can be stored within the file.
    - PrivateKeyEntry: Private key and its associated X.509 certificate chain.
    - Certificate-only Entry: Contains only the X.509 certificate or certificates 
                              without the private key.
    - Secret Key Entry: Include entries for symmetric (secret) keys.
    
  Owner/Issuer: The known owner of the private key that signed this certificate. 
  Owner/Issuer: Common Name: primary identifier associated with the 
                             certificate holder, which could be 
                             an individual, organization, server, or 
                             other entity.
    
  required:
  {colored('-p <profile_name>','green')}  
  alternate required:
  {colored('--file <path_to_file>','green')}  
  
  short_cut:
  {colored("-spd","green")}
  
  Example Usage
  -------------
  show this help screen
  # {colored(f'sudo nodectl {extended} help','cyan')} 
  or 
  # {colored(f'sudo nodectl -spd help','cyan')}  
  
  show p12 for a configured profile_name
  # {colored(f'sudo nodectl {extended} -p <profile_name>','cyan')}  
  
  show p12 for a stand alone p12 file located in /tmp and called test.p12
  # {colored(f'sudo nodectl {extended} --file /tmp/test.p12','cyan')}  
        ''' 
        
        
    if extended == "status" or extended == "quick_status":
        help_text += title("status")
        help_text += f'''
  The command takes a few options.
  
  required:
  {colored('-p <profile_name> | all','green')}  
  
  optional:
  {colored('-w <seconds>','green')} 
  
  The {colored('-w','cyan')} will engage the {colored('watch','cyan')} option. The watch option will continuously watch
  your Node's profile status for the default of 15 seconds. If the watch option is 
  followed by an integer above 5 seconds, the watch feature will refresh the 
  status for the Node Operator entered amount of seconds. If a number of 5 or 
  less is entered, a {colored('RANGE ERROR','red')} message will show on the CLI output and will 
  automatically be defaulted back to 15 seconds.  
    
  Status Command Elements:
    - {colored('profile','cyan')}: Which profile are we reviewing.
    - {colored('service','cyan')}: The name of the profile's service that is used to run the Node.
    - {colored('join state','cyan')}: The present stage of the Node.
    - {colored('API TCP','cyan')}: The TCP/IP ports associated with the:
               - Public API
               - Peer-to-Peer API
               - Internal only CLI API.
    - {colored('ordinals','cyan')}: State of ordinals associated with the Node.
                - The latest ordinal on the Node.
                - The last ordinal downloaded to the Node.
                - The latest ordinal found on the block explorer.
    - {colored('sessions','cyan')}: Comparison of the Node v. Cluster session.
    - {colored('on network','cyan')}: True or False if the Node is on the correct cluster.
    - {colored('up time','cyan')}: Amount of time the Node, VPS, and Cluster has been consecutively
               up and running.
    - {colored('nodeid','cyan')}: shortened abbreviation of the Node's public key.
    - {colored('in consensus','cyan')}: True, False or Preparing. If in {colored('preparing','cyan')}, the Node may 
                    be in a stage that is not ready for consensus but is properly moving towards a 
                    stage that allow it to join consensus when reached.
                  
  {colored('Note','yellow')}: When the Node starts up or restarts, it will review the latest ordinal,
        download that ordinal and then work its way backward to the last known ordinal
        it ever knew about.  This can cause the {colored('last dled','cyan')} to show
        as a lower ordinal than the latest on the Node.
    
  {colored('States','yellow')}: Initial,Offline,ReadyToJoin,StartingSession,SessionStarted,
          ReadyToDownload,WaitingForDownload,DownloadInProgress,
          Observing,WaitingForReady,Ready,Leaving,Offline,ApiNotReady,ApiNotResponding
  
  {colored('Quick Status','green')}:
  This command will show an abbreviated version of the status command that
  reviews the status of your Node based on the local API on the Node.
  Local API calls can produce false information if the Node is
  forked.  This produces a quick response because it does not
  
  Example Usage
  -------------
  show this help screen
  # {colored(f'sudo nodectl {extended} help','cyan')}  
  
  show {extended} on the cluster for all profiles
  # {colored(f'sudo nodectl {extended}','cyan')}  
  
  show {extended} on the cluster for a configured profile_name
  # {colored(f'sudo nodectl {extended} -p <profile_name>','cyan')}  
  
  show {extended} and watch for the default 15 seconds
  # {colored(f'sudo nodectl {extended} -p <profile_name> -w','cyan')}  
  
  show {extended} and watch for the 30 seconds
  # {colored(f'sudo nodectl {extended} -p <profile_name> -w 30','cyan')}  
        ''' 
    
        
    if extended == "change_ssh_port":
        help_text += title("change ssh port")
        help_text += f'''
  To help secure your Node down a little further it is recommended 
  to change the {colored("well known port number","yellow")} for SSH
  [ secure shell protocol ] from port {colored("22","cyan")} to a more
  indiscriminate port between [1024 and 65535].
  
  This command will execute the SSH port change on your Node by updating
  the ssh configuration and restarting the SSH daemon.

  required:
  {colored('--port <new_port_number>','green')}
  
  Port number must be between {colored("1024","cyan")} and {colored("65535","cyan")}
  
  Port number should not conflict with the {colored("public","cyan")}, {colored("p2p","cyan")}, and {colored("cli","cyan")} port numbers
  configured in the configuration file for all profiles.
  
  {colored("NOTE:","yellow",attrs=['bold'])} This is just a preventative measure and does not 
  ensure your Node will be fully protected from nefarious actors.  
  However, every step helps.
  
  {colored("WARNING:","red",attrs=['bold'])} is command will manipulate non-Tessellation Constellation 
  Network services on your VPS.
  
  Example Usage
  -------------
  show this help screen
  # {colored(f'sudo nodectl change_ssh_port help','cyan')}  
  
  ({colored("It is not recommended to use the same port as this example on your Node","yellow")})
  change the port from 22 to 33333
  # {colored(f'sudo nodectl change_ssh_port --port 33333','cyan')}  
  ''' 
    
        
    if extended == "update_version_object":
        help_text += title("Update Versioning Object")
        help_text += f'''
  This command can be used to manually update the Node's version
  object.  This functionality is completed automatically by the 
  nodectl's versioning service every 5 minutes.
  
  To ensure that you have the latest version details you can 
  utilize this command to update the object immediately.
  
  When executed, if the versioning object is deemed not in need
  of an update, it will not update the object unless the {colored("-f","cyan")}
  option is used to force an update.

  optional:
  {colored('--force','green')} force
  {colored('-v','green')} verify
  {colored('--print','green')} print the contents of the object
    
  The {colored("-v","cyan")} optional option can be used to verify that the
  contents of the versioning object is valid and contains the proper key
  pair values.
    
  The {colored("--print","cyan")} optional option can be used to print out
  the contents of the versioning object.
    
  Example Usage
  -------------
  show this help screen
  # {colored(f'sudo nodectl update_version_object help','cyan')}  
  
  force an update to the versioning object.
  # {colored(f'sudo nodectl update_version_object --force','cyan')}  
  
  verify the versioning object.
  # {colored(f'sudo nodectl update_version_object -v','cyan')}  
  
  print the versioning object.
  # {colored(f'sudo nodectl update_version_object --print','cyan')}  
  ''' 
        
        
    if extended == "disable_root_ssh" or extended == "enable_root_ssh":
        help_text += title(extended)
        help_text += f'''
  The {colored(extended,'cyan')} command does not take any arguments. 
  
  {colored("WARNING:","red",attrs=['bold'])} is command will manipulate non-Tessellation Constellation 
  Network files on your VPS.
    
  The {colored("disable_root_ssh","cyan")} command will remove the root access statement from the 
  {colored("ssh configuration","cyan")}; as well as, rename the 
  {colored("authorized_keys","cyan")} file in the root user's home directory
  causing root user to fail to access the proper file, disabling
  root access via SSH.
    
  The {colored("enable_root_ssh","cyan")} command will do the opposite of the disable command.
  
  ''' 
  
    if extended in simple_command_list:
        help_text += f'''
  Example Usage
  -------------
  show this help screen
  # {colored(f'sudo nodectl {extended} help','cyan')}
  
  execute the {extended} command
  # {colored(f'sudo nodectl {extended}','cyan')}
  
  ''' 
    if extended_option != None:
        help_text += f'''execute using option command
  # {colored(f'sudo nodectl {extended_option}','cyan')}
  '''
          
    return help_text
  
  
if __name__ == "__main__":
    print("This class module is not designed to be run independently, please refer to the documentation")        
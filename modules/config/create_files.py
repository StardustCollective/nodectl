def create_files(functions,var): 
    cur_file, cur_file2 = "",""
    
    if var.file == "service_file":
        cur_file = service_file(functions.nodectl_path)
     
    if var.file == "service_bash":
        cur_file = service_bash()

    if var.file == "auto_restart_service_log":
        cur_file = auto_restart_service_log()
    
    if var.file == "service_restart":
        cur_file = service_restart()
        
    if var.file == "version_service":
        cur_file =  version_service()
    
    if var.file == "config_yaml_init":
        cur_file = config_yaml_init()
    
    if var.file == "config_yaml_profile":
        cur_file = config_yaml_profile()
        
    if var.file == "config_yaml_autorestart":
        cur_file = config_yaml_autorestart()
        
    if var.file == "config_yaml_p12":
        cur_file = config_yaml_p12()

    if var.file == "config_yaml_global_elements":
        cur_file = config_yaml_global_elements()

    if var.file == "alerting":
        cur_file = alerting()

    if var.file == "delegated_staking":
        cur_file = delegated_staking()
    
    if var.file == "uninstall_nodectl":
        cur_file = uninstall_nodectl()

    elif var.file == "upgrade":
        cur_file = upgrade()

        if var.upgrade_required:
            cur_file2 = upgrade_required()
        else:
            cur_file2 += upgrade_not_required(cur_file2)


    if var.file == "auto_complete":
        cur_file = auto_complete()

    return cur_file+cur_file2


def service_file(nodectl_path):
    cur_file = f'''[Unit]
Description=nodegarageservicedescription
StartLimitBurst=50
StartLimitIntervalSec=0

[Service]
Type=forking
EnvironmentFile={nodectl_path}profile_nodegarageworkingdir.conf
WorkingDirectory=/var/tessellation/nodegarageworkingdir
ExecStart={nodectl_path}nodegarageexecstartbash
SuccessExitStatus=143
TimeoutStopSec=10s

[Install]
WantedBy=multi-user.target
'''  
    return cur_file 


def service_bash():
    cur_file = '''#!/bin/bash
            
# This file is used by the [nodegarageservicename] profile
# to run your node's debian service.
#
# Node Operators should not alter this file;
# rather, utilize the: 'sudo nodectl configure' command to
# alter this file and avoid undesired affects.
# =========================================================

nice -n nodegaragecpupriority /usr/bin/java -jar -Xmsnodegaragexmsv -Xmxnodegaragexmxv -Xssnodegaragexssv nodegaragetessbinaryfilepath run-validator --public-port nodegaragepublic_port --p2p-port nodegaragep2p_port --cli-port nodegaragecli_port --seedlist nodegarageseedlistv --ratings nodegarageratingv --collateral nodegaragecollateral --l0-token-identifier nodegaragetoken
'''   
    return cur_file


def auto_restart_service_log():
    cur_file = '''#!/bin/bash
formatted_date=$(date "+%b %d %H:%M:%S")
pid=$$
echo "$formatted_date [$pid]: INFO : systemd saw auto_restart service has been started or restarted." >> /var/tessellation/nodectl/logs/nodectl.log
'''    
    return cur_file


def service_restart():
    cur_file = '''[Unit]
Description=Constellation Network node auto_restart service
StartLimitBurst=50
StartLimitIntervalSec=15
After=multi-user.target

[Service]
Type=Simple
WorkingDirectory=/usr/local/bin
Environment="SCRIPT_ARGS=%I"
ExecStartPre=/var/tessellation/nodectl/auto_restart_logger.sh
ExecStart=nodectl service_restart $SCRIPT_ARGS
Restart=always
RestartSec=300
RuntimeMaxSec=3600
ExecStop=/bin/true

[Install]
WantedBy=multi-user.target
'''
    return cur_file


def version_service():
    cur_file = '''[Unit]
Description=Constellation Network node version update service
After=multi-user.target

[Service]
Type=simple
WorkingDirectory=/usr/local/bin
ExecStart=nodectl uvos
Restart=always
RestartSec=2m
ExecStop=/bin/true

[Install]
WantedBy=multi-user.target
'''
    return cur_file


def config_yaml_init():
    cur_file = '''---
# NODECTL CONFIGURATION FILE
# @netmet72
# =========================================================
# IMPORTANT IMPORTANT IMPORTANT IMPORTANT
#
# It is discouraged to update this file manually.  nodectl may
# update this file through automation at any time, causing any
# changes you make to be lost.
#
# Do NOT update this file unless you know what you are
# doing !!  Please see the Constellation Network
# documentation hub for details on how to configure
# this file.
# =========================================================
# Network cluster sections isolated by profile key name
# =========================================================
# Custom Options and Environment Variables
# ---------------------------------------------------------
# Required arguments must be listed BEFORE any custom
# entered options or environment variables !!
#
# Failure to do so may create undesired results from
# nodectl (especially the configurator) the Node Operator
# should use the configurator over manually updating this
# config file.
# ---------------------------------------------------------
# Required arguments
# ---------------------------------------------------------
# custom_args_enable: True (or False)
# custom_env_vars_enable: True (or False)
# ---------------------------------------------------------
# MANUAL ENTRY MUST PREFIX "custom_args_" to your arg
# custom_args_var1: value1
# custom_args_var2: value2
# MANUAL ENTRY MUST PREFIX "custom_env_var_" to your env_var
# ---------------------------------------------------------
# MANUAL ENTRY MUST BE IN CORRECT ORDER FOR CONFIGURATOR
# TO WORK PROPERLY.
# custom_args_enable followed by all custom_args
# custom_env_vars_enabled followed by all custom_env_var
# Failure to do so will lead to unexpected behavior
# ---------------------------------------------------------
# Examples)
# custom_env_vars_CL_SNAPSHOT_STORED_PATH: /location1/here/
# custom_env_vars_CL_INCREMENTAL_SNAPSHOT_STORED_PATH: /location2/here/
# custom_env_vars_CL_INCREMENTAL_SNAPSHOT_TMP_STORED_PATH: /location3/here/
# =========================================================

nodectl:
'''
    return cur_file


def config_yaml_profile():
    cur_file = '''  nodegarageprofile:
    profile_enable: nodegarageenable
    environment: nodegarageenvironment
    description: nodegaragedescription
    node_type: nodegaragenodetype
    meta_type: nodegaragemetatype
    layer: nodegarageblocklayer
    collateral: nodegaragecollateral
    service: nodegarageservice
    edge_point: nodegarageedgepointhost
    edge_point_tcp_port: nodegarageedgepointtcpport
    public_port: nodegaragepublic
    p2p_port: nodegaragep2p
    cli_port: nodegaragecli
    gl0_link_enable: nodegaragegl0linkenable
    gl0_link_key: nodegaragegl0linkkey
    gl0_link_host: nodegaragegl0linkhost
    gl0_link_port: nodegaragegl0linkport
    gl0_link_profile: nodegaragegl0linkprofile
    ml0_link_enable: nodegarageml0linkenable
    ml0_link_key: nodegarageml0linkkey
    ml0_link_host: nodegarageml0linkhost
    ml0_link_port: nodegarageml0linkport
    ml0_link_profile: nodegarageml0linkprofile
    token_identifier: nodegaragetokenidentifier
    token_coin_id: nodegaragemetatokencoinid
    directory_backups: nodegaragedirectorybackups
    directory_uploads: nodegaragedirectoryuploads
    java_xms: nodegaragexms
    java_xmx: nodegaragexmx
    java_xss: nodegaragexss
    jar_location: nodegaragejarlocation
    jar_repository: nodegaragejarrepository
    jar_version: nodeagaragejarversion
    jar_file: nodegaragejarfile
    p12_nodeadmin: nodegaragep12nodeadmin
    p12_key_location: nodegaragep12keylocation
    p12_key_name: nodegaragep12keyname
    seed_location: nodegarageseedlocation
    seed_repository: nodegarageseedrepository
    seed_version: nodegarageseedversion
    seed_file: nodegarageseedfile
    pro_rating_location: nodegarageratinglocation
    pro_rating_file: nodegarageratingfile
    priority_source_location: nodegarageprioritysourcelocation
    priority_source_repository: nodegarageprioritysourcerepository
    priority_source_file: nodegarageprioritysourcefile
    custom_args_enable: nodegaragecustomargsenable
    custom_env_vars_enable: nodegaragecustomenvvarsenable
'''
    return cur_file


def config_yaml_autorestart():
    cur_file = '''  global_auto_restart:
    auto_restart: nodegarageeautoenable
    auto_upgrade: nodegarageautoupgrade
    on_boot: nodegarageonboot
    rapid_restart: nodegaragerapidrestart
'''
    return cur_file


def config_yaml_p12():
    cur_file = '''  global_p12:
    nodeadmin: nodegaragep12nodeadmin
    key_location: nodegaragep12keylocation
    key_name: nodegaragep12keyname
    encryption: nodegaragep12encryption
'''
    return cur_file


def config_yaml_global_elements():
    cur_file = '''  global_elements:
    yaml_config_name: nodegarageyamlconfigname
    metagraph_name: nodegaragemetagraphname
    metagraph_token_identifier: nodegaragemetatokenidentifier
    metagraph_token_coin_id: nodegaragemetagraphtokencoinid     
    local_api: nodegaragelocalapi
    includes: nodegarageincludes
    nodectl_yaml: nodegaragenodectlyaml
    developer_mode: nodegaragedevelopermode
    log_level: nodegarageloglevel
'''
    return cur_file


def alerting():
    cur_file = '''---
alerting:
  enable: True
  gmail: 'nodegarageemail'
  token: 'nodegaragegmailtoken'
  send_method: 'nodegaragemethod' # 'multi' or 'single'
  recipients:
    - 'nodegarageemailone'
  begin_alert_utc: nodegaragebegin  # 0-23 or 'disable'
  end_alert_utc: nodegarageend   # 0-23 or 'disable'
  report_hour_utc: nodegaragereport  # 0-23 or 'disable'
  report_currency: nodegaragecurrencyreport # True or False
  local_time_zone: 'nodeagaragelocaltimezone'            
  label: 'nodegaragelabel' # 'None' or 'My Label Here" - keep label short
'''  
    return cur_file


def delegated_staking():
    cur_file = '''---
# Do not update this file manually
# please use nodectl's configurator
# to avoid unnecessary errors.
# 
# - sudo nodectl configure 
#
# enable must be set to 'True' for
# the nodectl utility to pick up 
# these delegation parameters.

delegated_staking:
  enable: True
  name: 'nodegaragedelstname' 
  description: 'nodegaragedelstdescription'
  rewardFraction: nodegaragedelstpercent
'''  
    return cur_file


def uninstall_nodectl():
    cur_file = '''#!/bin/bash
sleep 1
red='\033[1;31m'
blue='\033[1;36m'
green='\033[1;32m'
clr='\033[0m'

if [ -f "/usr/local/bin/nodectl" ]; then
  rm -f /usr/local/bin/nodectl
  echo "  ${blue}Removing nodectl binary........................ ${green}complete${clr}"
else
  echo "  ${blue}Removing nodectl binary........................ ${red}failed${clr}"
fi
rm -f "$0"
'''
    return cur_file


def upgrade():
    url = "https://github.com/stardustCollective/nodectl/releases/download/NODECTL_VERSION/nodectl_ARCH"
    cur_file = '''#!/bin/bash

red='\033[1;31m'
blue='\033[1;36m'
pink='\033[1;35m'
green='\033[1;32m'
yellow='\033[1;33m'
clr='\033[0m'
'''
    cur_file += f'''
sudo mv /usr/local/bin/nodectl NODECTL_BACKUPnodectl_NODECTL_OLD
sleep 2
sudo wget {url} -P /usr/local/bin -O /usr/local/bin/nodectl -o /dev/null
sleep 1
'''
    cur_file += '''
sudo chmod +x /usr/local/bin/nodectl
echo ""
echo "  ${green}COMPLETED! nodectl upgraded to NODECTL_VERSION ${clr}"
sleep 1

if [ -e "/usr/local/bin/nodectl" ]; then
    size=$(stat -c %s "/usr/local/bin/nodectl")
    if [ "$size" -eq 0 ]; then
       echo "  ${red}Error found, file did not download properly, please try again."
       exit 0
    fi
else
    echo "  ${red}Error found, file did not download properly, please try again."
    exit 0
fi

sudo nodectl update_version_object --force
sudo nodectl verify_nodectl --skip_override
sudo nodectl version
echo ""
'''
    return cur_file


def upgrade_required():
    cur_file2 = '''
echo "  ${blue}This version of nodectl requires a nodectl_only upgrade be performed"
echo "  ${blue}on your node.\n"
read -e -p "  ${pink}Press ${yellow}Y ${pink}then ${yellow}[ENTER] ${pink}to upgrade or ${yellow}N ${pink}then ${yellow}[ENTER] ${pink}to cancel:${blue} " CHOICE

if [[ ("$CHOICE" == "y" || "$CHOICE" == "Y") ]]; then
    echo "${clr}"
    sudo nodectl upgrade --nodectl_only -y
fi
echo "$CHOICE" > /var/tessellation/nodectl/cnng_upgrade_results.txt 2>/dev/null
echo "${clr}"
exit 0

'''
    return cur_file2


def upgrade_not_required(cur_file2):
    cur_file2 += '''
echo "  ${yellow}This version of nodectl ${pink}DOES NOT ${yellow}require an upgrade be performed"
read -e -p "  ${blue}Press ${yellow}[ENTER] ${blue}to continue...${clr}" CHOICE
echo "${clr}"
exit 0
'''
    return cur_file2


def auto_complete():
    cur_file = '''_nodectl_complete()
{
    local cur prev words cword opts
    _get_comp_words_by_ref -n : cur prev words cword

    # Only proceed if 'nodectl' is the command or follows 'sudo'
    if [[ ! " ${words[@]} " =~ " nodectl " ]]; then
        return 0
    fi

    # Commands for 'nodectl'
    local commands="nodegaragelocalcommands"

    # Options for each command
    local install_opts="nodegarageinstalloptions"
    local upgrade_opts="nodegarageupgradeoptions"
    local viewconfig_opts="nodegarageviewconfigoptions"
    local autorestart_opts="nodegarageautorestartoptions"
    local delegate_opts="nodegaragedelegateoptions"
    local displaychain_opts="nodegaragedisplaychainoptions"
    local find_opts="nodegaragefindoptions"
    local default_opts="help"

    # Determine the current command
    local current_command=""
    for word in ${words[@]}; do
        if [[ " ${commands} " == *" ${word} "* ]]; then
            current_command=${word}
            break
        fi
    done

    case "${current_command}" in
        install)
            case "${prev}" in
                --user)
                    COMPREPLY=($(compgen -W "<user_name>" -- ${cur}))
                    return 0
                    ;;
                --p12-destination-path)
                    COMPREPLY=($(compgen -W "<path_to_where_p12_lives>" -- ${cur}))
                    return 0
                    ;;
                --user-password)
                    COMPREPLY=($(compgen -W "<user_password>" -- ${cur}))
                    return 0
                    ;;
                --p12-passphrase)
                    COMPREPLY=($(compgen -W "<p12_passphrase>" -- ${cur}))
                    return 0
                    ;;
                --p12-migration-path)
                    COMPREPLY=($(compgen -W "<path_to_file_p12_being_migrated>" -- ${cur}))
                    return 0
                    ;;
                --p12-alias)
                    COMPREPLY=($(compgen -W "<p12_alias_name>" -- ${cur}))
                    return 0
                    ;;
                *)
                    COMPREPLY=($(compgen -W "${install_opts}" -- ${cur}))
                    return 0
                    ;;
            esac
            ;;
        upgrade)
            case "${prev}" in
                --pass)
                    COMPREPLY=($(compgen -W "<password>" -- ${cur}))
                    return 0
                    ;;
                *)
                    COMPREPLY=($(compgen -W "${upgrade_opts}" -- ${cur}))
                    return 0
                    ;;
            esac
            ;;
        auto_restart)
            case "${prev}" in
                *)
                    COMPREPLY=($(compgen -W "${autorestart_opts}" -- ${cur}))
                    return 0
                    ;;
            esac
            ;;
        delegate)
            case "${prev}" in
                *)
                    COMPREPLY=($(compgen -W "${delegate_opts}" -- ${cur}))
                    return 0
                    ;;
            esac
            ;;
        view_config|-vc)
            case "${prev}" in
                --section)
                    COMPREPLY=($(compgen -W "<section_name>" -- ${cur}))
                    return 0
                    ;;
                *)
                    COMPREPLY=($(compgen -W "${viewconfig_opts}" -- ${cur}))
                    return 0
                    ;;
            esac
            ;;
        display_snapshot_chain)
            case "${prev}" in
                -p)
                    COMPREPLY=($(compgen -W "<profile>" -- ${cur}))
                    return 0
                    ;;
                --days)
                    COMPREPLY=($(compgen -W "<number_of_days>" -- ${cur}))
                    return 0
                    ;;
                --json_output)
                    COMPREPLY=($(compgen -W "<file_name or path>" -- ${cur}))
                    COMPREPLY=($(compgen -W "--pretty_print" -- ${cur}))
                    return 0
                    ;;
                *)
                    COMPREPLY=($(compgen -W "${displaychain_opts}" -- ${cur}))
                    return 0
                    ;;
            esac
            ;;
        find_options)
            case "${prev}" in
                -t)
                    COMPREPLY=($(compgen -W "<<target_ip_nodeid, ordinal <ordinal_number>, or hash <hash_number>>" -- ${cur}))
                    return 0
                    ;;
                -s)
                    COMPREPLY=($(compgen -W "<source_ip_nodeid>" -- ${cur}))
                    return 0
                    ;;
                --days)
                    COMPREPLY=($(compgen -W "<number_of_days>" -- ${cur}))
                    return 0
                    ;;
                --json_output)
                    COMPREPLY=($(compgen -W "<file_name or path>" -- ${cur}))
                    return 0
                    ;;
                *)
                    COMPREPLY=($(compgen -W "${displaychain_opts}" -- ${cur}))
                    return 0
                    ;;
            esac
            ;;
        *)
            ;;
        
    esac

    if [[ ${cur} == -* ]] ; then
        COMPREPLY=($(compgen -W "${default_opts}"))
        return 0
    fi

    if [[ $cword -eq 2 ]]; then
        COMPREPLY=($(compgen -W "${commands}" -- ${cur}))
        return 0
    fi
}

complete -F _nodectl_complete sudo
'''
    return cur_file


if __name__ == "__main__":
    print("This module is not designed to be run independently, please refer to the documentation")  
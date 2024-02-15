def pull_valid_command():
    valid_commands = [
        "check_versions",
        "change_ssh_port",
        "check_seedlist",
        "check_source_connection",
        "check_minority_fork",
        "create_p12",
        "check_versions",
        "check_consensus",

        "dag",
        "disable_root_ssh",
        "download_status",
        
        "find",

        "join",

        "leave",
        "list",

        "restart",
        "restart_only",



        "uptime",
        "id",
        "nodeid",

        "quick_status",
        
        "enable_root_ssh",

        "view_config",
        "validate_config",
        "clean_files",
        "verify_nodectl",


        "find",
        "peers",
        "whoami",
        "nodeid2dag",

        "passwd12",
        "reboot",
        "upgrade_nodectl",
        "help",

        "show_p12_details",

        "show_node_proofs",
        "check_connection",

        "check_seedlist_participation",

        "auto_restart",
        "install",
        "uninstall",
        "upgrade",
        "upgrade_path",
        "upgrade_vps",

        "refresh_binaries",

        "show_service_status",
        "show_service_log",
        "send_logs",
        "show_dip_error",
        "start",
        "stop",
        "show_current_rewards",
        "slow_restart",
        "status",
        "show_node_states",


        "price",
        "sec",
        "market",
        "migrate_node",

        "update_seedlist",
        "export_private_key",
        "logs",
    ]

    service_cmds = [
        "service_restart",
        "uvos",
    ]
    valid_short_cuts = [
        "_sr","_s","_qs","_cv","_vc","_val","_cf",
        "_vn","_scr","_sns","_h","_csl","_csc","_snp",
        "_cc","_sl","_cslp","_ds","_up","_rtb","_ssl",
        "_sde","_usl","_con","_cmf","_spd",
        "log","prices","markets","_sss",
    ]
    
    removed_cmds = [
        "clear_uploads","_cul","_cls","clear_logs",
        "clear_snapshots","clear_backups",
        "reset_cache","_rc","clean_snapshots","_cs",
        "upgrade_nodectl_testnet",
    ]
    
    return (valid_commands,valid_short_cuts,service_cmds,removed_cmds)
    

    
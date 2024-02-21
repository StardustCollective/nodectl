def pull_valid_command():
    valid_commands = [
        "auto_restart",

        "check_versions",
        "change_ssh_port",
        "check_seedlist",
        "check_source_connection",
        "check_minority_fork",
        "create_p12",
        "check_versions",
        "check_consensus",
        "clean_files",
        "check_connection",
        "check_seedlist_participation",
        
        "dag",
        "disable_root_ssh",
        "download_status",

        "enable_root_ssh",     
        "export_private_key",

        "find",
        "find",

        "help",

        "id",
        "install",

        "join",

        "leave",
        "list",
        "logs",

        "market",
        "migrate_node",

        "nodeid",
        "nodeid2dag",
        
        "peers",
        "passwd12",
        "price",

        "quick_status",

        "reboot",
        "refresh_binaries",
        "restart",
        "restart_only",
        "restore_config",

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
        "show_p12_details",
        "show_node_proofs",
        "sec",

        "upgrade",
        "upgrade_nodectl",
        "upgrade_path",
        "upgrade_vps",
        "uninstall",
        "uptime",
        "update_seedlist",

        "view_config",
        "validate_config",
        "verify_nodectl",

        "whoami",
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
    

    
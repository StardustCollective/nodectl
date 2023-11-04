def pull_valid_command():
    valid_commands = [
        "restart",
        "slow_restart",
        "restart_only",
        "join",
        "start",
        "stop",
        "leave",
        "status",
        "quick_status",
        "uptime",
        "id",
        "nodeid",
        "dag",
        "check_versions",
        "disable_root_ssh",
        "enable_root_ssh",
        "change_ssh_port",
        "view_config",
        "validate_config",
        "clean_files",
        "verify_nodectl",
        "list",
        "show_current_rewards",
        "find",
        "peers",
        "whoami",
        "nodeid2dag",
        "show_node_states",
        "passwd12",
        "reboot",
        "upgrade_nodectl",
        "help",
        "check_seedlist",
        "check_source_connection",
        "show_node_proofs",
        "check_connection",
        "send_logs",
        "check_seedlist_participation",
        "download_status",
        "auto_restart",
        "install",
        "upgrade",
        "upgrade_path",
        "refresh_binaries",
        "show_service_logs",
        "health",
        "price",
        "markets",
        "show_dip_error",
    ]

    service_cmds = [
        "service_restart",
        "uvos",
    ]
    valid_short_cuts = [
        "_sr","_s","_qs","_cv","_vc","_val","_cf",
        "_vn","_scr","_sns","_h","_csl","_csc","_snp",
        "_cc","_sl","_cslp","_ds","_up","_rtb","_ssl",
        "_sde",
    ]
    
    removed_cmds = [
        "clear_uploads","_cul","_cls","clear_logs",
        "clear_snapshots","clear_backups",
        "reset_cache","_rc","clean_snapshots","_cs",
        "upgrade_nodectl_testnet",
    ]
    
    return (valid_commands,valid_short_cuts,service_cmds,removed_cmds)
    

    
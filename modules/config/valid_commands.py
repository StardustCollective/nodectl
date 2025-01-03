def pull_valid_command():
    valid_commands = [
        "auto_restart",

        "backup_config",
        
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
        "check_tcp_ports",
        "console",

        "dag",
        "disable_root_ssh",
        "download_status",
        "display_snapshot_chain",

        "enable_root_ssh",     
        "export_private_key",
        "execute_starchiver",
        "execute_tests",

        "find",

        "getting_started",

        "help",
        "health",

        "id",
        "install",
        "ipv6",

        "join",

        "leave",
        "list",
        "logs",

        "market",
        "migrate_datadir",
        "mobile",

        "nodeid",
        "nodeid2dag",
        "node_last_snapshot",
        
        "peers",
        "passwd12",
        "price",
        "prepare_file_download",

        "quick_status",

        "reboot",
        "refresh_binaries",
        "restart",
        "restart_only",
        "restore_config",
        "revision",

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
        "show_cpu_memory",
        "show_profile_issues",
        "sec",
        "sync_node_time",

        "upgrade",
        "upgrade_nodectl",
        "upgrade_path",
        "upgrade_vps",
        "uninstall",
        "uptime",
        "update_seedlist",
        "update_version_object",

        "view_config",
        "validate_config",
        "verify_nodectl",
        "verify_specs",

        "whoami",
    ]

    service_cmds = [
        "service_restart",
        "uvos","test_only",
    ]
    
    valid_short_cuts = [
        "_sr","_s","_qs","_cv","_vc","_val","_cf",
        "_vn","_scr","_sns","_h","_csl","_csc","_snp",
        "_cc","_sl","_cslp","_ds","_up","_rtb","_ssl",
        "_sde","_usl","_con","_cmf","_spd", "_ctp",
        "log","prices","markets","_sss","_snt",
    ]
    
    removed_cmds = [
        "clear_uploads","_cul","_cls","clear_logs",
        "clear_snapshots","clear_backups",
        "reset_cache","_rc","clean_snapshots","_cs",
        "upgrade_nodectl_testnet","remove_snapshots",
    ]
    
    return (valid_commands,valid_short_cuts,service_cmds,removed_cmds)
    
    
if __name__ == "__main__":
    print("This module is not designed to be run independently, please refer to the documentation")  
    
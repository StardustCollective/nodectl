from os import system
from datetime import datetime
from sys import argv, exit

debug = False
test_no = False
use_defaults = None

system("clear")
print("  Constellation Network")
print("  nodectl unit test script")
print(f"  v1.0.0")
print(f'  {datetime.now().strftime("%Y-%m-%d-%H:%M:%SZ")}')

print("\n  WARNING! User input only does basic validation")
print("           if you enter an invalid profile(s) it will")
print("           create errors.")
print("\n  We need to add some profiles to test against")
print("")

# test is the test command
# desc is the description of the test
# note is any extra note you may want to show
# profiles is the number of profiles (-p <profile_name>) you want to include
#   - 0 = no profiles
#   - 1 = the first profile
#   - 2 = all profiles

defaults = {
    "profiles": 0,
    "note": None,
    "loop": False,
}
default_profiles = [
    ["intnet-l0","intnet-l1"],
    ["dag-l0","dag-l1"]
]
default_ips = [
    ["104.248.118.251","138.68.224.28"], # integrationnet
    ["54.177.255.227","54.193.165.70"], # testnet
    ["52.53.46.33","54.215.18.98"] # mainnet
]

def build_tests(ips):
    tests = [
        {
            **defaults,
            "test": "sudo nodectl version",
            "desc": "show the version of nodectl",
        },
        {
            **defaults,
            "test": "sudo nodectl update_version_object -f -v --print",
            "desc": "update the version object, verify it, and print results",
        },
        {
            **defaults,
            "test": "sudo nodectl verify_nodectl",
            "desc": "determine if nodectl is authentic (digitally signed)",
        },
        {
            **defaults,
            "test": "sudo nodectl check_consensus",
            "desc": "check consensus requiring you to choose a profile, you should choose the layer0 profile.",
        },
        {
            **defaults,
            "test": "sudo nodectl show_p12_details",
            "desc": "review p12 details.",
            "profiles": 1,
        },
        {
            **defaults,
            "test": f"sudo nodectl check_consensus -s {ips[0]}",
            "desc": "check consensus of a node other than your own on layer0",
            "profiles": 1,
        },
        {
            **defaults,
            "test": f"sudo nodectl check_minority_fork",
            "desc": "check if profile is in a minority fork",
            "profiles": 1,
        },
        {
            **defaults,
            "test": "sudo nodectl status",
            "desc": "status command test individual profiles",
            "profiles": 2,
        },
        {
            **defaults,
            "test": "sudo nodectl status",
            "desc": "status command test all profiles",
        },
        {
            **defaults,
            "test": f"sudo nodectl uptime",
            "desc": "show uptime stats",
        },
        {
            **defaults,
            "test": f"sudo nodectl show_node_proofs -np",
            "desc": "show current node snapshot proofing.",
            "profiles": 1,
        },
        {
            **defaults,
            "test": f"sudo nodectl show_dip_error",
            "desc": "testing for DownloadInProgress error.",
            "profiles": 1,
        },
        {
            **defaults,
            "test": f"sudo nodectl quick_status",
            "desc": "testing the quick status command",
        },
        {
            **defaults,
            "test": f"sudo nodectl quick_status",
            "desc": "testing individual quick status profiles",
            "profiles": 2,
        },
        {
            **defaults,
            "test": f"sudo nodectl list",
            "desc": "testing test list command",
        },
        {
            **defaults,
            "test": f"sudo nodectl check_versions",
            "desc": "testing the check version command",
            "note": "you will be asked to continue because it did not\n       see the versions match, you can\n       say YES, as this release is in pre-release"
        },
        {
            **defaults,
            "test": f"sudo nodectl check_seedlist",
            "desc": "seed list check for both profiles",
            "note": "layer1 should show a disabled message",
            "profiles": 2,
        },
        {
            **defaults,
            "test": f"sudo nodectl update_seedlist",
            "desc": "update seed list check for both profiles",
            "note": "layer1 should show a disabled message",
            "profiles": 2,
        },
        {
            **defaults,
            "test": f"sudo nodectl validate_config",
            "desc": "run the configuration through a validation check",
        },
        {
            **defaults,
            "test": f"sudo nodectl show_service_log",
            "desc": "review the service logs via the journalctl",
            "note": "you will need to hit the space bar\n       to page through the results and\n      'q' at the end to exit.",
            "profiles": 1,
        },
        {
            **defaults,
            "test": f"sudo nodectl upgrade_path",
            "desc": "review the upgrade path command",
            "note": "you may get a warning because the release is in pre-release",
        },
        {
            **defaults,
            "test": f"sudo nodectl nodeid",
            "desc": "obtain nodeid for a profile",
            "profiles": 1,
        },
        {
            **defaults,
            "test": f"sudo nodectl id",
            "desc": "obtain nodeid for a profile using",
            "note": "alias id instead of nodeid",
            "profiles": 1,
        },
        {
            **defaults,
            "test": f"sudo nodectl nodeid -t {ips[0]}",
            "desc": f"obtain nodeid for specified ip: {ips[0]}",
            "note": "short format output",
            "profiles": 1,
        },
        {
            **defaults,
            "test": f"sudo nodectl nodeid -t {ips[0]} -l",
            "desc": f"obtain nodeid for specified ip: {ips[0]}",
            "note": "long format output",
            "profiles": 1,
        },
        {
            **defaults,
            "test": f"sudo nodectl whoami",
            "desc": f"look for node's external ip address",
        },
        {
            **defaults,
            "test": f"sudo nodectl whoami -id 3458a688925a4bd89f2ac2c695362e44d2e0c2903bdbb41b341a4d39283b22d8c85b487bd33cc5d36dbe5e31b5b00a10a6eab802718ead4ed7192ade5a5d1941",
            "desc": f"look for node's external ip address",
            "note": "this test shows ip of one of the source testnet constellation nodes\n       if you are not on testnet, this will not work.",
            "profiles": 1,
        },
        {
            **defaults,
            "test": f"sudo nodectl view_config -np",
            "desc": f"view the configuration",
        },
        {
            **defaults,
            "test": f"sudo nodectl show_node_states",
            "desc": f"view the node states known by nodectl",
        },
        {
            **defaults,
            "test": f"sudo nodectl peers --basic -np",
            "desc": f"view peers on each profile",
            "note": f"basic format",
            "profiles": 2,
        },
        {
            **defaults,
            "test": f"sudo nodectl peers",
            "desc": f"view peers on each profile",
            "note": f"normal format pagination you can\n       hit q to exit command to save time.",
            "profiles": 2,
        },
        {
            **defaults,
            "test": f"sudo nodectl peers --extended",
            "desc": f"view peers on a profile",
            "note": f"extended format with pagination",
            "profiles": 1,
        },
        {
            **defaults,
            "test": f"sudo nodectl find",
            "desc": f"review your node via the find command",
            "profiles": 1,
        },
        {
            **defaults,
            "test": f"sudo nodectl find -s self -t {ips[0]}",
            "desc": f"find target node using self",
            "profiles": 1,
        },
        {
            **defaults,
            "test": f"sudo nodectl find -s {ips[0]} -t {ips[1]}",
            "desc": f"find target using external source peer",
            "note": f"MAY SHOW FALSE this is a successful test either way.",
            "profiles": 1,
        },
        {
            **defaults,
            "test": f"sudo nodectl send_logs",
            "desc": f"test preparing logs to for upload to support.",
            "note": "please choose current logs\n       Say 'n' to cancel upload.",
            "profiles": 1,
        },
        {
            **defaults,
            "test": f"sudo nodectl check_seedlist_participation",
            "desc": f"how many nodes are on the cluster verse seedlist.",
        },
        {
            **defaults,
            "test": f"sudo nodectl logs -l app",
            "desc": f"view known app logs for profile.",
            "note": "this may take a long time to reach the\n       end of the output.",
            "profiles": 2,
        },
        {
            **defaults,
            "test": f"sudo nodectl dag",
            "desc": f"view dag details.",
            "profiles": 1,
        },
        {
            **defaults,
            "test": f"sudo nodectl nodeid2dag 3458a688925a4bd89f2ac2c695362e44d2e0c2903bdbb41b341a4d39283b22d8c85b487bd33cc5d36dbe5e31b5b00a10a6eab802718ead4ed7192ade5a5d1941",
            "desc": f"convert a nodeid to a dag address - source constellation node.",
            "profiles": 1,
        },
        {
            **defaults,
            "test": f"sudo nodectl -csc",
            "desc": f"view the relationship between the source node and local node.",
            "profiles": 2,
        },
        {
            **defaults,
            "test": f"sudo nodectl -cc",
            "desc": f"view the relationship between the local node and node on cluster.",
            "profiles": 2,
        },
        {
            **defaults,
            "test": f"sudo nodectl prices",
            "desc": f"view several coin/token prices",
        },
        {
            **defaults,
            "test": f"sudo nodectl markets",
            "desc": f"view market status.",
        },
        {
            **defaults,
            "test": f"sudo nodectl sec",
            "desc": f"view security elements.",
        },
        {
            **defaults,
            "test": f"sudo nodectl show_current_rewards",
            "desc": f"view current rewards on the cluster.",
            "profiles": 1,
        },
        {
            **defaults,
            "test": f"sudo nodectl refresh_binaries",
            "desc": f"re-download the tessellation binaries.",
        },
        {
            **defaults,
            "test": f"sudo nodectl leave",
            "desc": f"leave all profiles",
            "note": "next few tests follow an order",
            "profiles": 2,
        },
        {
            **defaults,
            "test": f"sudo nodectl stop",
            "desc": f"stop all profiles",
            "profiles": 2,
        },
        {
            **defaults,
            "test": f"sudo nodectl start",
            "desc": f"start all profiles",
            "profiles": 2,
        },
        {
            **defaults,
            "test": f"sudo nodectl join",
            "desc": f"join profile",
            "note": "will only be joining the layer0",
            "profiles": 1,
        },
        {
            **defaults,
            "test": f"sudo nodectl -qs",
            "desc": "preform a quick status [duplicate]",
            "note": f"after the join loop...",
            "profiles": 1,
            "loop": True,
        },
        {
            **defaults,
            "test": f"sudo nodectl restart -p all",
            "desc": "preform a restart of all profiles",
            "note": f"after the join loop...",
            "profiles": 0,
        },
    ]
    return tests


def print_option_menu(mtype):
    use_defaults = input(f"  Use default {mtype}? [n]: ")
    if use_defaults.lower() == "y" or use_defaults.lower() == "yes":
        if mtype == "test ips": return True
        print("\n  1. IntegrationNet")
        print("  2. TestNet")
        print("  3. MainNet")
        while True:
            option = input("  pick option: ")
            try: option = int(option)
            except: pass
            else:
                option -= 1    
            if option > -1 and option < 4: break
            print("  invalid option") 
        return option
    return False


if debug:
    profiles = default_profiles[1]
    ips = default_ips[1]
else:
    option = print_option_menu("profiles")
    if not isinstance(option,bool):
        profiles = default_profiles[0]
        if option > 0: profiles = default_profiles[1]
        ips = default_ips[option]
    else:
        profiles = [] # reset
        system("sudo nodectl list")
        for n in range(0,2):
            while True:
                print("\n  ** IMPORTANT ** - Layers must be correct.")
                profile = input(f"  Please enter profile name for your layer{n} profile: ")
                if profiles.count(profile) < 1:
                    profiles.append(profile)
                    break
                print("  invalid entry try again")
        print("  complete\n")
        print("  We need to enter in a couple of valid ip addresses of nodes.")
        print("  Please review the list and enter in some ip addresses.")
        print("  Remember, these will not be validated so please enter them carefully.\n")
            
        ips = [] # reset
        for n in range(0,2):
            system(f"sudo nodectl peers -p {profiles[n]} -np --basic")
            print("")

            while True:
                ip = input(f"  Copy and paste an ip from above to use #{n+1} of 2 : ")
                ip = ip.split(":")[0]
                if ips.count(ip) < 1:
                    ips.append(ip)
                    break
                print("  invalid entry try again")

tests = build_tests(ips)
no_of_tests = len(tests)
no_of_tests += sum([1 for item in tests if item["profiles"] > 1])
    
if "-l" in argv: 
    tests = build_tests(ips)
    for n, test in enumerate(tests): 
        number = f"{n+1}" if n > 8 else f" {n+1}"
        print(f'  Test No: {number} --> description: {test["desc"]}')
    print("  Note: Number of tests displayed includes sub-profile duplicate tests.")
    test_no = input("  Enter test number to run: ")
    try: test_no = int(test_no)
    except: exit(0)
elif "-r" in argv: 
    try: test_no = int(test_no)
    except: print("invalid test number!"); exit(0)
elif "-h" in argv or "help" in argv:
    print("  usage: nodect_unittest [-h | help, -r, -l]")
    print("\n  help or -h:  show this screen")
    print("  -l : list the tests available and offer prompt to run a test listed")
    print("  -r <test number>: directly run a test number")
    print("\n  example)  nodectl_unittest")
    print("\n            nodectl_unittest -l")
    print("\n            nodectl_unittest -r 1")
    
    
print("  =========================")
print("  ==   BEGINNING TESTS   ==")
print("  =========================")
print(f"  Number of tests: {no_of_tests}")
print("  =========================\n\n")


def print_new_test_msg(cmd):
    print(f"  ................................................")
    print(f"  ................=== new test ===................")
    print(f"  ................................................")
    print(f"  test: {cmd}")
    print("  press 's' to skip or enter to continue")
    print(f"  ................................................",end=" ")
    action = input("")
    if action.lower() == "s": return True
    return False
    
    
def print_test_title(n):
    str = f"  ==   TESTS #{n} of {len(tests)}"
    pad = 28 - len(str)
    print("  ===========================")
    print(f"  {str} {'==': >{pad}}")
    print("  ===========================")


def continue_msg():
    print("\n  If you received an error or other, please keep notes.")
    print("  Press <enter> key to continue to next test")
    print("  Press 'q' key to continue to quit test",end=" ")
    quit = input("")
    if quit.lower() == "q":
        exit(0)
    print("\n\n")
    

def loop():
    print("\n  If not in 'ready' state, press enter")
    print("  If in 'Ready' then press 'c' to continue test")
    print("\n  If you run into an issue and need to quit press 'c' enter") 
    print("  and then 'q' enter at next message.")
    print("\n  If you are in 'WaitingForDownload' you will need to quit here.",end=" ")
    pressed = input("")
    if pressed.lower() == 'c': return True
    return False
            
            
for n, test in enumerate(tests):
    if test_no and n+1 != test_no: continue
    skip, next = False, False
    if n > 0: skip = print_new_test_msg(test["test"])
    if skip: continue
    print(f'  description: {test["desc"]}')
    if test["note"] != None:
        print(f'  Notes: {test["note"]}')
    
    cmd = f'{test["test"]}'
    if test["profiles"] > 0:
        for i in range(0,test["profiles"]):
            if test["profiles"] > 1: print_test_title(f"{n+1}")
            elif test["profiles"] > 0: print_test_title(f"{n+1}-{i+1}")
            profile_cmd = f'{cmd} -p {profiles[i]}'
            print(f'  command to execute: {profile_cmd}\n')
            
            while True:
                system(profile_cmd)
                if test["loop"]: next = loop()
                if next: break
                elif not test["loop"] or next: break
                
            continue_msg()
    else: 
        if n > 0: print_test_title(n+1)
        print(f'  command to execute: {test["test"]}\n')
        system(cmd)
        continue_msg()
        
        
print("  Unit testing complete!")
print("  Please contact your Team Lead and let them know your results")
print("  The Constellation Network team thanks you!")
exit(0)
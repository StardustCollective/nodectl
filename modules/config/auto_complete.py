import argparse
import argcomplete

# Create an ArgumentParser
parser = argparse.ArgumentParser(description="Your command-line app description")

# Add arguments to your parser
auto_arguments = [
    ("show_status","-s"),
    ("quick_status","-qs"),
    ("restart"),
    ("slow_restart","-sr"),
    ("join"),
    ("id"),("dag"),("nodeid"),
    ("check_versions","-cv"),
    ("disable_root_ssh"),("enable_root_ssh"),("change_ssh_port"),
]

for auto_list in auto_arguments:
    parser.add_argument(auto_list, help='issue help after command for help')

# Call argcomplete.autocomplete to enable auto-completion
argcomplete.autocomplete(parser)

# Parse the command-line arguments
args = parser.parse_args()

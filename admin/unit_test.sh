#!/bin/bash

function print_title() {
    echo ""
    echo "==============================="
    echo "  Next Test to Run..."
    echo "==============================="
    echo -e "==  ${TEST}"
    echo -e "==  \033[1;33m${COMMAND}\033[0m"
    if [[ $EXTRA != "None" ]]; then
        echo -e "==  ${EXTRA}"
    fi
    echo "==============================="
    return
}

function continue_or_quit() {
    echo ""
    read -e -p " Press [ENTER] to execute test [Q]uit [S]kip " CHOICE
    echo ""
}

declare -A TESTS
declare -A COMMANDS
echo " nodectl unit tests bash script"
echo " v1.1"
echo " ------------------------------"
echo ""
echo " nodectl will now issue a list command to supply current profiles in use"
read -e -p " Press [ENTER] to execute " CHOICE
sudo nodectl list

echo ""
echo " Using the results from above"
read -e -p " Please enter a profile name to test against: " PROFILE_NAME

echo ""
echo " Using the results from above"
read -e -p " Please enter A SECOND profile name to test against: " PROFILE_NAME2

echo ""
echo " This unit test will issue a peers command"
echo " against the profile $PROFILE_NAME"

read -e -p " Press enter to issue a peers command " CHOICE
sudo nodectl peers -p $PROFILE_NAME -np --basic

echo ""
echo " Choose an IP to use in the tests as source"
read -e -p " IP from the list above: " IP1

echo ""
echo " Choose A SECOND IP to use in the tests as target"
read -e -p " IP from the list above: " IP2

# ======================================
# TEST LISTS
# ======================================

echo "====================================="
echo "==    BEGINNING UNIT TESTS         =="
echo "====================================="
COUNTER=0

tests=(
    ("status all - test" "sudo nodectl status" "None")
    ("status l0 - test" "sudo nodectl status -p $PROFILE_NAME" "None")
    ("status l1 - test" "sudo nodectl status -p $PROFILE_NAME2" "None")
    ("seedlist check l0 - test" "sudo nodectl check_seedlist -p $PROFILE_NAME" "None")
)

commands=(sudo nodectl)
TESTS[COUNTER]="status all - test"
COMMANDS[COUNTER]="sudo nodectl status"
EXTRA[COUNTER]="None"

let COUNTER++

TESTS[COUNTER]="status l0 - test"
COMMANDS[COUNTER]="sudo nodectl status -p $PROFILE_NAME"
EXTRA[COUNTER++]="None"

TESTS[COUNTER]="status l1 - test"
COMMANDS[COUNTER]="sudo nodectl status -p $PROFILE_NAME2"
EXTRA[COUNTER++]="None"

TESTS[COUNTER]="list - test"
COMMANDS[COUNTER]="sudo nodectl list"
EXTRA[COUNTER++]="None"

TESTS[COUNTER]="seedlist check l0 - test"
COMMANDS[COUNTER]="sudo nodectl check_seedlist -p $PROFILE_NAME"
EXTRA[COUNTER++]="None"

TESTS[COUNTER]="seedlist check l1 - test"
COMMANDS[COUNTER]="sudo nodectl check_seedlist -p $PROFILE_NAME2"
EXTRA[COUNTER++]="should show disable message"

TESTS[COUNTER]="status l1 - test"
COMMANDS[COUNTER]="sudo nodectl upgrade_path"
EXTRA[COUNTER++]="This will show the latest is not detected because it is beta"

TESTS[COUNTER]="update l0 seedlist test"
COMMANDS[COUNTER]="sudo nodectl update_seedlist -p $PROFILE_NAME"
EXTRA[COUNTER++]="None"

TESTS[COUNTER]="update l1 seedlist test"
COMMANDS[COUNTER]="sudo nodectl update_seedlist -p $PROFILE_NAME2"
EXTRA[COUNTER++]="should get disable message"

TESTS[COUNTER]="clear_uploads test"
COMMANDS[COUNTER]="sudo nodectl clear_uploads"
EXTRA[COUNTER++]="should get removed message"

TESTS[COUNTER]="leave l0 test"
COMMANDS[COUNTER]="sudo nodectl leave -p $PROFILE_NAME"
EXTRA[COUNTER++]="None"

TESTS[COUNTER]="leave l1 test"
COMMANDS[COUNTER]="sudo nodectl leave -p $PROFILE_NAME2"
EXTRA[COUNTER++]="None"

TESTS[COUNTER]="stop l0 test"
COMMANDS[COUNTER]="sudo nodectl stop -p $PROFILE_NAME"
EXTRA[COUNTER++]="None"

TESTS[COUNTER]="stop l1 test"
COMMANDS[COUNTER]="sudo nodectl stop -p $PROFILE_NAME2"
EXTRA[COUNTER++]="None"

TESTS[COUNTER]="start l0 test"
COMMANDS[COUNTER]="sudo nodectl start -p $PROFILE_NAME"
EXTRA[COUNTER++]="None"

TESTS[COUNTER]="start l1 test"
COMMANDS[COUNTER]="sudo nodectl start -p $PROFILE_NAME2"
EXTRA[COUNTER++]="Should get an error - ApiNotReady"

TESTS[COUNTER]="join l0 test"
COMMANDS[COUNTER]="sudo nodectl join -p $PROFILE_NAME"
EXTRA[COUNTER++]="None"

TESTS[COUNTER]="start l1 test"
COMMANDS[COUNTER]="sudo nodectl start -p $PROFILE_NAME2"
EXTRA[COUNTER++]="Should reach ReadyToJoin this test"

TESTS[COUNTER]="join l1 test"
COMMANDS[COUNTER]="sudo nodectl join -p $PROFILE_NAME2"
EXTRA[COUNTER++]="None"

TESTS[COUNTER]="restart all test"
COMMANDS[COUNTER]="sudo nodectl restart -p all"
EXTRA[COUNTER++]="None"

TESTS[COUNTER]="view config test"
COMMANDS[COUNTER]="sudo nodectl view_config"
EXTRA[COUNTER++]="None"

TESTS[COUNTER]="check versions test"
COMMANDS[COUNTER]="sudo nodectl check_versions"
EXTRA[COUNTER++]="None"

TESTS[COUNTER]="show node states test"
COMMANDS[COUNTER]="sudo nodectl show_node_states"
EXTRA[COUNTER++]="None"

TESTS[COUNTER]="show peers l0 test"
COMMANDS[COUNTER]="sudo nodectl peers -p $PROFILE_NAME"
EXTRA[COUNTER++]="None"

TESTS[COUNTER]="show peers l1 test"
COMMANDS[COUNTER]="sudo nodectl peers -p $PROFILE_NAME2"
EXTRA[COUNTER++]="None"

TESTS[COUNTER]="find l0 test"
COMMANDS[COUNTER]="sudo nodectl find -p $PROFILE_NAME"
EXTRA[COUNTER++]="None"

TESTS[COUNTER]="find l0 with source test"
COMMANDS[COUNTER]="sudo nodectl find -p $PROFILE_NAME -s $IP1"
EXTRA[COUNTER++]="None"

TESTS[COUNTER]="find l0 with source and target test"
COMMANDS[COUNTER]="sudo nodectl find -p $PROFILE_NAME -s $IP1 -t $IP2"
EXTRA[COUNTER++]="None"

TESTS[COUNTER]="whoami test"
COMMANDS[COUNTER]="sudo nodectl whoami"
EXTRA[COUNTER++]="None"

TESTS[COUNTER]="whoami test against remote nodeid"
COMMANDS[COUNTER]="sudo nodectl whoami -id f1322ca97b3374caa38deb14cce786e47cb8cfdbb58dddb14b1fce698b1830c6f8bbf5dfc47b60464ce3fe7b7d66930d05e5de86177ba36891629bbd6da1fc84 -p $PROFILE_NAME"
EXTRA[COUNTER++]="None"

TESTS[COUNTER]="check connections l0 test"
COMMANDS[COUNTER]="sudo nodectl check_connection -p $PROFILE_NAME"
EXTRA[COUNTER++]="None"

TESTS[COUNTER]="check connections l1 test"
COMMANDS[COUNTER]="sudo nodectl check_connection -p $PROFILE_NAME2"
EXTRA[COUNTER++]="None"

TESTS[COUNTER]="check source connections l0 test"
COMMANDS[COUNTER]="sudo nodectl check_source_connection -p $PROFILE_NAME"
EXTRA[COUNTER++]="None"

TESTS[COUNTER]="check source connections l1 test"
COMMANDS[COUNTER]="sudo nodectl check_source_connection -p $PROFILE_NAME2"
EXTRA[COUNTER++]="None"

TESTS[COUNTER]="already joined test"
COMMANDS[COUNTER]="sudo nodectl join -p $PROFILE_NAME"
EXTRA[COUNTER++]="should already in ready message"

TESTS[COUNTER]="check sec test"
COMMANDS[COUNTER]="sudo nodectl sec"
EXTRA[COUNTER++]="None"

TESTS[COUNTER]="price test"
COMMANDS[COUNTER]="sudo nodectl price"
EXTRA[COUNTER++]="None"

TESTS[COUNTER]="markets test"
COMMANDS[COUNTER]="sudo nodectl markets"
EXTRA[COUNTER++]="None"

TESTS[COUNTER]="dag wallet test"
COMMANDS[COUNTER]="sudo nodectl dag -p $PROFILE_NAME"
EXTRA[COUNTER++]="May be slow and will show zero balance"

TESTS[COUNTER]="seed list pariticpation test"
COMMANDS[COUNTER]="sudo nodectl -cslp"
EXTRA[COUNTER++]="None"

TESTS[COUNTER]="check health test"
COMMANDS[COUNTER]="sudo nodectl health"
EXTRA[COUNTER++]="None"

TESTS[COUNTER]="export private key test -p $PROFILE_NAME"
COMMANDS[COUNTER]="sudo nodectl export_private_key -p $PROFILE_NAME"
EXTRA[COUNTER++]="None"

TESTS[COUNTER]="validate configuration test"
COMMANDS[COUNTER]="sudo nodectl validate_config"
EXTRA[COUNTER++]="None"

TESTS[COUNTER]="nodeid command test"
COMMANDS[COUNTER]="sudo nodectl nodeid -p $PROFILE_NAME"
EXTRA[COUNTER++]="None"

TESTS[COUNTER]="nodeid command test external"
COMMANDS[COUNTER]="sudo nodectl nodeid -p $PROFILE_NAME -t $IP1"
EXTRA[COUNTER++]="None"

# ======================================
# ======================================

length=${#TESTS[@]}

for (( i=0; i<${length}; i++ ));
do
    TEST="${TESTS[$i]}"
    COMMAND="${COMMANDS[$i]}"
    EXTRA="${EXTRA[$i]}"

    print_title
    continue_or_quit

    if [[ $CHOICE == "q" || $CHOICE == "Q" ]]; then
        return
    fi

    if [[ $CHOICE != "s" && $CHOICE != "S" ]]; then
        ${COMMANDS[$i]}
    fi
    
done

echo "unit testing completed"
echo "thank you!"
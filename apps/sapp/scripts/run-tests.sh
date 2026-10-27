#! /usr/bin/env bash
set -eu -o pipefail

# set -x
export PS4='+ [${BASH_SOURCE[0]##*/}:${LINENO}${FUNCNAME[0]:+:${FUNCNAME[0]}}] '

# :help: run sapp tests
PROG=${0##*/}
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
usage() {
    cat <<EOF
Usage: $PROG [<option>]

Run SApp tests

Options:
  --debug      Print commands and their arguments as they are executed.
  --ut         Run unit tests
  --st         Run System tests
  --it         Run integration tests
  -h, --help   Show this help and exit.
EOF
}

die() {
    echo "$PROG: $*" >&2
    exit 1
}

TEMP=$(getopt --options h: \
              --longoptions help,debug,ut,st,it \
              --name "$PROG" -- "$@" || true)

eval set -- "$TEMP"

test=all
debug_p=false

while true; do
    case "$1" in
        -h|--help)           usage; exit ;;
        --ut)                test=ut; shift ;;
        --st)                test=st; shift ;;
        --it)                test=it; shift ;;
        --debug)             debug_p=true; shift ;;
        --)                  shift; break ;;
        *)                   break ;;
    esac
done

$debug_p && set -x

run_ut() {
    echo -en "\n Running Unit tests \n"
    REPORT_DIR=$SCRIPT_DIR/test-reports/ut
    APP_ROOT=$SCRIPT_DIR/../cognos
    mkdir -p "$REPORT_DIR"

    /usr/local/svk/svk-app/env/bin/python3 -m pytest --ignore-glob "$APP_ROOT"/ui/tests/it \
        --cov-report xml:"$REPORT_DIR"/coverage.xml \
        --cov-report term \
        --junit-xml="$REPORT_DIR"/junit.xml \
        --cov-branch \
        --cov
}

run_st() {
    echo -en "\n System Tests Not Implemented \n"
}

run_it_selenium(){
	echo -en "\n Running Selenium Tests \n"
	TEST_DIR=$SCRIPT_DIR/../cognos/ui/tests/it/selenium
	mkdir -p "$TEST_DIR"
	
	/usr/local/svk/svk-app/env/bin/python3 "$TEST_DIR"/test_runner.py
}

run_it() {
    echo -en "\n Running Integration Tests \n"
    run_it_selenium
}

run_all() {
    run_ut
    run_st
    run_it
}

run_$test

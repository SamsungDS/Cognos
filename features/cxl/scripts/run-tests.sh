#! /usr/bin/env bash
set -eu -o pipefail

# set -x
export PS4='+ [${BASH_SOURCE[0]##*/}:${LINENO}${FUNCNAME[0]:+:${FUNCNAME[0]}}] '

# :help: run sapp tests
PROG=${0##*/}

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

svk_cxl_ut() {
   "$TEST_UT_PATH/cxl_ut" --output-junit "$REPORTS_DIR/gitlab_junit.xml"
}

run_init() {

    # Path variables
    SCRIPT_DIR=$(cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd)
    PROJECT_ROOT=$(realpath "$SCRIPT_DIR/../")
    TEST_UT_PATH="$PROJECT_ROOT/build/tests"
    REPORTS_DIR="$PROJECT_ROOT/build/reports"

}

run_ut() {
    echo -en "\n Running Unit tests \n"

    #build executable
    svk_cxl_ut 

    echo "Generating coverage reports"
    # Using path to framework object files
    gcovr \
        --xml "$REPORTS_DIR/gitlab_coverage.xml" \
        --sonarqube "$REPORTS_DIR/sonar_coverage.xml" \
        --txt \
        --root "$PROJECT_ROOT" \
        --exclude "$PROJECT_ROOT/build" \
        "$PROJECT_ROOT/build"

}

run_st() {
    echo -en "\n System Tests Not Implemented \n"
}

run_it() {
    echo -en "\n Integration Tests Not Implemented \n"
}



run_all() {
    run_ut
    run_st
    run_it
}

run_$test


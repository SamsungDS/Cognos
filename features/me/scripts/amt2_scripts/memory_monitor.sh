#!/bin/bash
CONFIG_FILE="$(dirname "$0")/amt2_config.json"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: config.json not found at $CONFIG_FILE"
    exit 1
fi

PYTHON=/usr/local/svk/venv/me/amt2/bin/python3

read_config() {
    "$PYTHON" -c "import json,sys; c=json.load(open('$CONFIG_FILE')); print(c['$1'])"
}

DAMO=$(read_config damo_path)
pid=$(read_config target_pid)
INTERVAL=$(read_config monitor_interval_s)
MAX_FILES=$(read_config max_csv_files)
REPORT_DIR="./report_$pid"
mkdir -p "$REPORT_DIR"

"$DAMO" stop

echo "[+] Starting DAMON on Kernel 6.11 for PID $pid..."
# On 6.11, use the standard damo start but without the problematic snapshot flag
"$DAMO" start -s 100 -a 500000 -u 2000000 --target_pid $pid \
           --damos_action stat --damos_access_rate 0% 100% \
           --monitoring_nr_regions_range 512 1024

echo "[+] Monitoring active. Snapshots every ${INTERVAL}s..."

while [ -d "/proc/$pid" ]; do
    TIMESTAMP=$(date +%s)
    
    # 1. Update the scheme stats first
    echo update_schemes_stats > /sys/kernel/mm/damon/admin/kdamonds/0/state
    
    # 2. Update the tried_regions (The "Action Status" file on 6.11)
    # On 6.11, this is the trigger that populates the regions folders
    echo update_schemes_tried_regions > /sys/kernel/mm/damon/admin/kdamonds/0/state
    
    # Give kernel time to write the physical region folders
    sleep 1

    # 3. Check if directories were created
    if [ -d "/sys/kernel/mm/damon/admin/kdamonds/0/contexts/0/schemes/0/tried_regions/" ]; then
        echo "[+] Tried_regions found, processing to csv..."
        "$PYTHON" ./memory_profiler.py "$pid" -o "$REPORT_DIR/access_map.$TIMESTAMP.csv"
    else
        echo "[-] No tried_regions found yet. Kernel is still aggregating..."
    fi

    # Cleanup
    ls -1t "$REPORT_DIR"/access_map.*.csv 2>/dev/null | tail -n +"$((MAX_FILES + 1))" | xargs -r rm -- 
    sleep "$INTERVAL"
done

"$DAMO" stop
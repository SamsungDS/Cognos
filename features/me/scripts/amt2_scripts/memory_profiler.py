#!/usr/bin/env python3
import os
import csv
import json
import argparse

# Path to DAMON Sysfs for scheme 0 - Updated for Linux 6.11
SYSFS_BASE = "/sys/kernel/mm/damon/admin/kdamonds/0/contexts/0/schemes/0/tried_regions"
TRIED_REGIONS = SYSFS_BASE

def load_config(config_path=None):
    if config_path is None:
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "amt2_config.json")
    if not os.path.exists(config_path):
        print(f"Warning: amt2_config.json not found at {config_path}. Using defaults.")
        return {}
    with open(config_path, 'r') as f:
        return json.load(f)

_config = load_config()
HOT_THRESHOLD = _config.get("hot_threshold", 2)
WARM_THRESHOLD = _config.get("warm_threshold", 1)

def build_numa_map():
    """Builds a fast lookup list of (start, end, node_id) from sysfs."""
    numa_map = []
    try:
        node_path = "/sys/devices/system/node"
        for node_dir in os.listdir(node_path):
            if not node_dir.startswith("node"): continue
            node_id = int(node_dir.replace("node", ""))
            
            with open("/sys/devices/system/memory/block_size_bytes", 'r') as f:
                block_size = int(f.read().strip(), 16)
                
            mem_blocks = [d for d in os.listdir(f"{node_path}/{node_dir}") if d.startswith("memory")]
            for block in mem_blocks:
                try:
                    with open(f"/sys/devices/system/memory/{block}/phys_index", 'r') as f:
                        idx = int(f.read().strip(), 16)
                    start = idx * block_size
                    numa_map.append((start, start + block_size, node_id))
                except: continue
    except Exception as e:
        print(f"[-] Warning building NUMA map: {e}")
    return numa_map

def virt_to_phys(pid, vaddr):
    """Translates Virtual Address to Physical Address using /proc/pid/pagemap."""
    try:
        with open(f"/proc/{pid}/pagemap", "rb") as f:
            f.seek((vaddr // 4096) * 8)
            entry = int.from_bytes(f.read(8), "little")
        if not (entry >> 63) & 1: return None 
        pfn = entry & ((1 << 55) - 1)
        return pfn * 4096 + (vaddr % 4096)
    except: return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pid", type=int, help="Target PID")
    parser.add_argument("-o", "--output", required=True, help="Output CSV path")
    args = parser.parse_args()

    if not os.path.exists(TRIED_REGIONS):
        print(f"[-] Error: {TRIED_REGIONS} not found.")
        return

    numa_map = build_numa_map()
    
    regions = []
    # Ensure numerical sorting of the region directories
    entries = [d for d in os.listdir(TRIED_REGIONS) if d.isdigit()]
    for entry in sorted(entries, key=int):
        base = os.path.join(TRIED_REGIONS, entry)
        try:
            with open(f"{base}/start") as f: start = int(f.read(), 0)
            with open(f"{base}/end") as f: end = int(f.read(), 0)
            with open(f"{base}/nr_accesses") as f: freq = int(f.read())
            regions.append((start, end, freq))
        except: continue

    with open(args.output, "w", newline="") as f:
        writer = csv.writer(f)
        # Updated Header: Node -> NUMA_Node
        writer.writerow(["VA_Start", "VA_End", "Size_MB", "Accesses", "Hotness", "NUMA_Node", "PA_Start"])
        
        for v_start, v_end, freq in regions:
            p_start = virt_to_phys(args.pid, v_start)
            if p_start is None: continue
            
            node = next((n for s, e, n in numa_map if s <= p_start < e), "Unknown")
            hotness = "Hot" if freq >= HOT_THRESHOLD else ("Warm" if freq >= WARM_THRESHOLD else "Cold")
            size_mb = (v_end - v_start) / (1024 * 1024)

            writer.writerow([
                hex(v_start), 
                hex(v_end), 
                round(size_mb, 2), 
                int(freq),   # Forced to integer
                hotness, 
                node, 
                hex(p_start)
            ])

if __name__ == "__main__":
    main()
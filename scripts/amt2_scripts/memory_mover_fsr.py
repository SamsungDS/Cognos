#!/usr/bin/env python3
import os
import resource
import psutil
import csv
import sys
import glob
import ctypes
import time
import gc
from ctypes import c_int, c_ulong, POINTER, c_void_p

# Load libc
libc = ctypes.CDLL("libc.so.6")

# Define syscall number for move_pages (usually 279 on x86_64)
# Check /usr/include/asm/unistd_64.h
SYS_MOVE_PAGES = 279

# Define argument types for move_pages
# long move_pages(int pid, unsigned long count, void **pages, 
#                 const int *nodes, int *status, int flags);
libc.syscall.argtypes = [ctypes.c_long, ctypes.c_int, ctypes.c_ulong, 
                         ctypes.POINTER(ctypes.c_void_p), 
                         ctypes.POINTER(ctypes.c_int), 
                         ctypes.POINTER(ctypes.c_int), ctypes.c_int]
libc.syscall.restype = ctypes.c_long

def move_pages_wrapper(pid, page_list, target_node, source_node):
    """
    Checks current page locations and moves only those not in target_node.
    """
    if not page_list:
        return 0

    count = len(page_list)
    pages_arr = (ctypes.c_void_p * count)(*page_list)
    status_arr = (ctypes.c_int * count)()

    # 1. Query current locations (pass NULL for nodes)
    libc.syscall(SYS_MOVE_PAGES, pid, count, pages_arr, None, status_arr, 0)
    
    current_statuses = list(status_arr)
    
    # 2. Identify pages that need moving
    to_move_indices = [
        i for i, node in enumerate(current_statuses) 
        if node != target_node and node >= 0  # Ignore errors/already there
    ]

    # Optional: Filter specifically for source_node if provided
    if source_node is not None:
        to_move_indices = [i for i in to_move_indices if current_statuses[i] == source_node]

    pages_at_target = current_statuses.count(target_node)
    pages_to_migrate = len(to_move_indices)

    #print(f"Summary: {pages_at_target} already at target, {pages_to_migrate} to move.")

    if not to_move_indices:
        return 0

    # 3. Perform the actual move for filtered pages
    move_count = len(to_move_indices)
    move_pages_arr = (ctypes.c_void_p * move_count)(*[page_list[i] for i in to_move_indices])
    move_nodes_arr = (ctypes.c_int * move_count)(*[target_node] * move_count)
    move_status_arr = (ctypes.c_int * move_count)(*[16] * move_count)

    ret = libc.syscall(SYS_MOVE_PAGES, pid, move_count, move_pages_arr, 
                       move_nodes_arr, move_status_arr, 0)
    successful_moves = 0
    if (ret == 0):
        successful_moves = sum(1 for i in range(move_count) if move_status_arr[i] == target_node)
    
    return successful_moves


def call_ctype_move_pages(pid, source_node, target_node, hot_pages_list, chunk_size=65536):
    """
    Processes the page list in chunks to prevent Python OOM 
    and syscall timeouts.
    """
    total_nr_pages = len(hot_pages_list)
    if total_nr_pages == 0:
        print("No addresses found.")
        return 0

    total_success = 0

    # Process in chunks (default 64k pages at a time)
    for i in range(0, total_nr_pages, chunk_size):
        chunk = hot_pages_list[i : i + chunk_size]

        # Convert addresses to c_void_p (Handles both Hex string and Int)
        pages_ptrs = []
        for pg in chunk:
            addr_int = int(pg, 16) if isinstance(pg, str) else pg
            pages_ptrs.append(ctypes.c_void_p(addr_int))

        ret_val = move_pages_wrapper(pid, pages_ptrs, target_node, source_node)

        if ret_val != 0:
            total_success += ret_val

    return total_success

def print_memory_usage():
    process = psutil.Process(os.getpid())
    # RSS is the physical memory used (in bytes)
    mem_bytes = process.memory_info().rss 
    print(f"Current Memory Footprint (RSS) of this python program: {mem_bytes / 1024**2:.2f} MB")

def get_fsr_ranges(pid, fsr_size_mb=512):
    fsr_size_bytes = fsr_size_mb * 1024 * 1024
    fsr_list = []
    total_bytes = 0
    maps_path = f"/proc/{pid}/maps"

    try:
        with open(maps_path, 'r') as f:
            for line in f:
                parts = line.split()
                if len(parts) < 5: continue
                
                addr_range = parts[0]
                perms = parts[1]
                
                # Check for Read/Write Private memory
                if perms.startswith('rw'):
                    # IMPORTANT: If there is a 6th column, it MUST NOT be a file path
                    # We only allow [heap] or empty (anonymous)
                    if len(parts) > 5:
                        pathname = parts[-1]
                        if pathname.startswith('/') or pathname.startswith('lib'):
                            continue # Skip libraries and files
                    
                    start_hex, end_hex = addr_range.split('-')
                    start = int(start_hex, 16)
                    end = int(end_hex, 16)
                    
                    total_bytes += (end - start)
                    curr = start
                    while curr < end:
                        chunk_end = min(curr + fsr_size_bytes, end)
                        fsr_list.append((curr, chunk_end))
                        curr = chunk_end
    except Exception as e:
        print(f"Error reading maps: {e}")
        
    return fsr_list, total_bytes

def parse_classified_data_from_dir(directory_path):
    """Parses all .csv files and returns only unique VA ranges."""
    unique_regions = {} 
    search_pattern = os.path.join(directory_path, "*.csv")
    csv_files = glob.glob(search_pattern)
    
    for file_path in csv_files:
        try:
            with open(file_path, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Ensure addresses are integers immediately
                    v_start = int(row['VA_Start'], 16)
                    v_end = int(row['VA_End'], 16)
                    
                    if (v_start, v_end) not in unique_regions:
                        unique_regions[(v_start, v_end)] = {
                            'VA_Start': v_start,
                            'VA_End': v_end,
                            'Accesses': int(row['Accesses']),
                            'Hotness': row['Hotness'],
                            'NUMA_Node': int(row['NUMA_Node'])
                        }
        except Exception as e:
            print(f"Error parsing {file_path}: {e}")
            
    return list(unique_regions.values())

def map_classified_to_fsrs(classified_dir, fsr_list, pid, fast_numa, slow_numa, action, already_promoted_fsrs, already_demoted_fsrs):
    """Maps VA ranges from CSVs to FSR indices and returns pages to promote/demote."""
    all_regions = parse_classified_data_from_dir(classified_dir)
    hot_fsr_indices = set()
    cold_fsr_indices = set()

    hotness_priority = {"Hot": 0, "Warm": 1, "Cold": 2}
    all_regions.sort(key=lambda x: (hotness_priority.get(x['Hotness'], 3), x['VA_Start']))

    for region in all_regions:
        v_start, v_end = region['VA_Start'], region['VA_End']

        found_fsrs = [
            idx for idx, (fsr_start, fsr_end) in enumerate(fsr_list)
            if fsr_start < v_end and fsr_end > v_start
        ]

        if action in ['p', 'a'] and region['Hotness'] in ("Hot", "Warm"):
            for idx in found_fsrs:
                if idx not in already_promoted_fsrs:
                    already_promoted_fsrs.add(idx)
                    hot_fsr_indices.add(idx)

        if action in ['d', 'a'] and region['Hotness'] == "Cold":
            for idx in found_fsrs:
                if idx not in already_demoted_fsrs:
                    already_demoted_fsrs.add(idx)
                    cold_fsr_indices.add(idx)

    # Promotion takes priority over demotion
    cold_fsr_indices = cold_fsr_indices.difference(hot_fsr_indices)

    def expand_fsrs_to_pages(indices, fsr_list, p_size):
        pages = []
        for idx in sorted(indices):
            f_start, f_end = fsr_list[idx]
            for addr in range(f_start, f_end, p_size):
                pages.append(addr)
        return pages

    try:
        p_size_val = resource.getpagesize()
    except:
        p_size_val = 4096

    hot_pages = expand_fsrs_to_pages(hot_fsr_indices, fsr_list, p_size_val)
    cold_pages = expand_fsrs_to_pages(cold_fsr_indices, fsr_list, p_size_val)

    return hot_pages, cold_pages


def process_vma_do_move(target_pid, target_dir, fast_numa_node, slow_numa_node, action, fsr_size_mb, already_promoted_fsrs, already_demoted_fsrs):
    fsr_list, total_mapped_size = get_fsr_ranges(target_pid, fsr_size_mb)

    if fsr_list is None or not fsr_list:
        print(f"No anonymous memory regions found for PID {target_pid}.")
        sys.exit(1)

    hot_pages, cold_pages = map_classified_to_fsrs(target_dir, fsr_list, target_pid, fast_numa_node, slow_numa_node, action, already_promoted_fsrs, already_demoted_fsrs)

    if any((int(p, 16) if isinstance(p, str) else p) % 4096 != 0 for p in hot_pages):
        print("WARNING: Non-aligned pages detected!")
    hot_pg_moved = 0
    cold_pg_moved = 0

    if hot_pages:
        print(f"Hot pages detected")
        hot_pg_moved = call_ctype_move_pages(target_pid, slow_numa_node, fast_numa_node, hot_pages)

    if cold_pages:
        print(f"Cold pages detected")
        cold_pg_moved = call_ctype_move_pages(target_pid, slow_numa_node, fast_numa_node, cold_pages)

    return hot_pg_moved, cold_pg_moved


def load_config(config_path=None):
    import json
    if config_path is None:
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "amt2_config.json")
    if not os.path.exists(config_path):
        print(f"Error: amt2_config.json not found at {config_path}")
        sys.exit(1)
    with open(config_path, 'r') as f:
        return json.load(f)

# --- Execution ---
if __name__ == "__main__":
    config = load_config()

    try:
        target_pid = int(config["target_pid"])
    except (KeyError, ValueError):
        print("Error: 'target_pid' must be an integer in amt2_config.json")
        sys.exit(1)

    fast_numa_node = int(config["fast_numa_node"])
    slow_numa_node = int(config["slow_numa_node"])
    action = config["action"]
    fsr_size_mb = int(config["fsr_size_mb"])
    move_interval = int(config["move_interval_s"])

    target_dir = f"./report_{target_pid}"
    if not os.path.isdir(target_dir):
        print(f"Error: The directory '{target_dir}' does not exist.")
        sys.exit(1)

    total_hot_p_moved = 0
    total_cold_p_moved = 0
    already_promoted_fsrs = set()
    already_demoted_fsrs = set()
    PAGE_SIZE = os.sysconf("SC_PAGESIZE")
    print(f"--- Movement Report for PID {target_pid} ---")
    print(f"FSR size = {fsr_size_mb} MB")
    print(f"Movement interval = {move_interval}s")
    print(f"In progress: ...")
    while(True):

        try:
        # Signal 0 doesn't kill, it just checks for existence/permissions
            os.kill(target_pid, 0)
        except (OSError, TypeError):
            print(f"[-] PID {target_pid} does not exist or is not accessible. Exiting.")
            sys.exit(1)
        except KeyboardInterrupt:
            sys.exit(0)
        hot_p_moved, cold_p_moved = process_vma_do_move(target_pid, target_dir, fast_numa_node, slow_numa_node, action, fsr_size_mb, already_promoted_fsrs, already_demoted_fsrs)
        total_hot_p_moved += hot_p_moved
        total_cold_p_moved += cold_p_moved
        promoted_mb = (total_hot_p_moved * PAGE_SIZE) / (1024 * 1024)
        demoted_mb = (total_cold_p_moved * PAGE_SIZE) / (1024 * 1024)
        print(f"Total PROMOTED: {promoted_mb:.2f} MB | Total DEMOTED: {demoted_mb:.2f} MB ...")
        gc.collect()
        time.sleep(move_interval)



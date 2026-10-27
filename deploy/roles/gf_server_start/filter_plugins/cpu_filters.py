# filter_plugins/cpu_filters.py

def cpu_range_to_string(cpu_list):
    """ Convert list of integers to 'start-end' string, e.g., '0-13,84-85' """
    if not cpu_list:
        return ""
    cpu_list = sorted(cpu_list)
    ranges = []
    start = cpu_list[0]
    end = cpu_list[0]

    for i in range(1, len(cpu_list)):
        if cpu_list[i] == end + 1:
            end = cpu_list[i]
        else:
            if start == end:
                ranges.append(f"{start}")
            else:
                ranges.append(f"{start}-{end}")
            start = cpu_list[i]
            end = cpu_list[i]

    if start == end:
        ranges.append(f"{start}")
    else:
        ranges.append(f"{start}-{end}")

    return ",".join(ranges)


def process_cpus(gfs_data, dram_sequences):
    """
    Process CPU chunks per DRAM node.

    Args:
        gfs_data: Dict from gf_get_numa_ids_sockets[item.key]
            - 'dram': list of DRAM IDs (e.g., [1, 3])
            - 'cpu_ids': list of strings (e.g., ["64 65 ... 70", "99 100 ... 106"])
        dram_sequences: List of DRAM IDs (e.g., [1, 3, 1, 3, 1])

    Returns:
        List of range strings, one per process, in order of dram_sequences.
    """
    if not dram_sequences:
        return []

    # Map dram_id → cpu_ids_str
    dram_to_cpu_ids = dict(zip(gfs_data['dram'], gfs_data['cpu_ids']))

    # Count how many times each dram_id appears
    usage_count = {}
    for dram_id in dram_sequences:
        usage_count[dram_id] = usage_count.get(dram_id, 0) + 1

    # Precompute chunks for each dram_id
    chunks_by_dram = {}
    for dram_id, count in usage_count.items():
        if dram_id not in dram_to_cpu_ids:
            raise ValueError(f"DRAM {dram_id} not found in gfs_data.dram")

        cpu_ids_str = dram_to_cpu_ids[dram_id]
        cpu_list = sorted(map(int, cpu_ids_str.split()))
        # Remove last 4 CPUs
        cpu_list = cpu_list[:-4]

        if not cpu_list:
            continue

        n = len(cpu_list)
        chunk_size = n // count
        remainder = n % count

        chunks = []
        start_idx = 0
        for i in range(count):
            size = chunk_size + (1 if i < remainder else 0)
            end_idx = start_idx + size
            chunk = cpu_list[start_idx:end_idx]
            chunks.append(cpu_range_to_string(chunk))
            start_idx = end_idx

        chunks_by_dram[dram_id] = chunks

    # Now assign in order
    result = []
    for dram_id in dram_sequences:
        chunks = chunks_by_dram[dram_id]
        chunk = chunks.pop(0)
        result.append(chunk)

    return result


# Register Filter
class FilterModule:
    def filters(self):
        return {
            'process_cpus': process_cpus
        }
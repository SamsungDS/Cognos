# filter_plugins/preprocess_dram.py

def preprocess_dram(dram_input, socket_dramlist):
    """
    Maps each DRAM channel ID to a modulo index (0 to socket_dramlist_len - 1).

    Args:
        dram_input:

    Returns:
        list[int]: List of modulo indices (d % socket_dramlist_len) for each DRAM channel.
                   Returns empty list if input is invalid.

    Example:
        Input: gf_server_start_dram_idx = ['0', '1', '2', '3', '4', '5'], socket_dramlist_len = 4
        Output: ['0', '1', '2', '3', '0', '1']
    """
    if not dram_input or not socket_dramlist:
        return []

    try:
        if isinstance(dram_input, str):
            gf_server_start_dram_idx = [int(x) for x in dram_input.split()]
        elif isinstance(dram_input, list):
            gf_server_start_dram_idx = [int(x) for x in dram_input]
        else:
            return []
    except (ValueError, TypeError):
        return []

    socket_dramlist_len = len(socket_dramlist)
    if socket_dramlist_len <= 0:
        return []

    return [socket_dramlist[d % socket_dramlist_len] for d in gf_server_start_dram_idx]

# Register Filter
class FilterModule:
    def filters(self):
        return {
            'preprocess_dram': preprocess_dram
        }  

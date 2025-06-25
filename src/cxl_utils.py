import sys
import subprocess
import re

def get_cxl_base_address(bdf):
    try:
        cmd = f"lspci -vvv -s {bdf}"
        result = subprocess.run(cmd, shell=True, check=True, stdout=subprocess.PIPE, text=True)
        output = result.stdout
    except Exception as e:
        print(f"ERROR: Failed to run lspci: {e}", file=sys.stderr)
        sys.exit(1)
    # Look for "Range1"
    for line in output.splitlines():
        if 'Range1' in line:
            match = re.search(r'Range1:\s*([0-9a-fA-F]+)\s*-\s*[0-9a-fA-F]+', line)
            if match:
                return int(match.group(1), 16)
    print("ERROR: Range1 not found", file=sys.stderr)
    sys.exit(2)
	
if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1]=="get_base_address":
        bdf = sys.argv[2]
        try:
          addr = get_cxl_base_address(bdf)
          print(addr)
        except Exception as e:
            print(f"ERROR:{e}", file=sys.stderr)
            sys.exit(1)
    else:  
        print("Usage: python3 cxl_utils.py get_base_address <bdf>", file=sys.stderr)
        sys.exit(3)

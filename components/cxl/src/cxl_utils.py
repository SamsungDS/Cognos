import sys
import subprocess
import re

def get_cxl_base_address(bdf):
    try:
        cmd = f"lspci -vvv -s {bdf}"
        result = subprocess.run(cmd, shell=True, check=True,
                                stdout=subprocess.PIPE, text=True)
        output = result.stdout
    except Exception as e:
        print(f"[CXL] [ERROR] Failed to run lspci: {e}", file=sys.stderr)
        sys.exit(1)
    base_addr = None
    for line in output.splitlines():
        if 'Range1:' in line:
            match = re.search(r'Range1:\s*([0-9a-fA-F]+)-([0-9a-fA-F]+)', line)
            if match:
                base = int(match.group(1), 16)
                end = int(match.group(2), 16)
                if base!=0:
                    base_addr = base
                elif base ==0 and end!=0:
                    base_addr = end
                break
            print(f"[CXL] [INFO] for bdf {bdf} the base address is {base_addr}")
    if base_addr is None or base_addr ==0:
        print("[CXL] [ERROR] No valid Range1 base address found", file=sys.stderr)
        sys.exit(2)
    return base_addr

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1]=="get_base_address":
        bdf = sys.argv[2]
        try:
          addr = get_cxl_base_address(bdf)
          print(addr)
        except Exception as e:
            print(f"[CXL] [ERROR] {e}", file=sys.stderr)
            sys.exit(1)
    else:  
        print("[CXL] [Usage]: python3 cxl_utils.py get_base_address <bdf>", file=sys.stderr)
        sys.exit(3)

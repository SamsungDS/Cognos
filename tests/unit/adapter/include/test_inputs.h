#ifndef TEST_INPUTS
#define TEST_INPUTS

// The const char array of the above unsigned char kernel log input shoing
// hardware address allocation for NUMA devices
const char kernel_log_inp[] = R"(
[    0.008490] kernel: ACPI: SRAT 0x000000006643F000 00A278 (v03 SUPERM SMCI--MB 00000002 AMI  20230628)
[    0.008556] kernel: ACPI: Reserving SRAT table memory at [mem 0x6643f000-0x66449277]
[    0.008842] kernel: ACPI: SRAT: Node 0 PXM 0 [mem 0x00000000-0x7fffffff]
[    0.008844] kernel: ACPI: SRAT: Node 0 PXM 0 [mem 0x100000000-0x207fffffff]
[    0.008845] kernel: ACPI: SRAT: Node 1 PXM 1 [mem 0x60f80000000-0x62f7fffffff]
[    0.008850] kernel: ACPI: SRAT: Node 2 PXM 14 [mem 0x2080000000-0x607fffffff]
[    0.008851] kernel: ACPI: SRAT: Node 3 PXM 15 [mem 0x62f80000000-0x66f7fffffff]
)";

// ras-mc-ctl output that contains errors for NUMA devices (this shows the
// location of hardware addresses)
//  const char array of the above ras_err unsigned char array
const char* ras_err =
    "0x0000abcd\n0x2080000001\n0x2080000001\n0x62f80000002\n0x2080000001\n0x62f"
    "80000002\n0x2080000001\n0x62f80000002\n0x2080000001\n0x2080000001\n0x62f80"
    "000002\n0x2080000001\n0x62f80000002\n0x2080000001\n0x62f80000002\n0x607ffa"
    "c000\n0x607ffac000\n0x607fedba\n0x607fedba\n0x607fedba\n0x6726353756160\n0"
    "x6752549220352\n0x6726861201408\n0x6665717731328\n0x6752933019648\n0x21428"
    "277248\n0x6752692854784\n0x6752692854784\n0x6752692854784\n0x6752811167744"
    "\n0x6752925016064\n0x6753016598528\n0x6752863039488\n0x6752808140800\n0x67"
    "52953528320\n0x6752953528320\n0x6726811381760\n0x6726811381760\n0x67268113"
    "81760\n0x6752567394304\n0x6752567394304\n0x6752567394304\n0x6752567394304"
    "\n0x6752567394304\n0x6752567394304\n0x6752567394304\n0x6719918673920\n0x67"
    "19918673920\n0x6719918673920\n0x6719918673920\n0x6753000484864\n0x67530004"
    "84864\n0x6723759763456\n0x6723759763456\n0x6723759763456\n0x6752770760704"
    "\n0x6752770760704\n0x6752546738176\n0x6752546738176\n0x6733058465792\n0x67"
    "33058465792\n0x6752516038656\n0x6752516038656\n0x6719126683648\n0x67191266"
    "83648\n0x6665370640384\n0x6665370640384\n0x6745590898688\n0x6745590898688"
    "\n0x67d53836\n0x6244981e000\n0x6244981e000\n0x6244981e000\n0x6244981e000\n"
    "0x6106cf3a000\n0x6106cf3a000\n0x6753003851776\n0x0000f31c\n0x61fc206e000\n"
    "0x61fc206e000\n0x61fc206e000\n0x62448555000\n0x62448555000\n0x61c968de000"
    "\n0x61c968de000\n0xc78969000\n0xcf1932000\n0xcf1932000\n0xcf1932000\n0xcf1"
    "932000\n0xcf1932000\n0xcf1932000\n0xcf658d000\n0xcf658d000\n0x6244c821000"
    "\n0x6245b539000\n0x6245b539000\n0x60feb3e9000\n0x62280b8c000\n0x62280b8c00"
    "0\n0x62280b8c000\n0x62436afd000\n0x62436afd000\n0x66e7fbfd032\n0x66e7fbfd0"
    "32\n0x620c7d3d000\n0x624471be000\n0xc70c0a000\n0x3e0f0e0000\n0x3e1a711000"
    "\n0xc09166000\n0xc09166000\n0x66e7f6ae000\n0xcf7f54000\n0x27389329408\n0x8"
    "c135e000\n0x66e7fbfd000\n0x66e7f6ae000\n0x66e7f6ae000\n0xc742c8000\n0xc358"
    "99000\n0xc35899000\n0xc35899000\n0x66e7fbfd000\n0x66e7f6ae000\n0x66e7fbfd0"
    "00\n0x66e7fbfd000\n0x3db7cc8000\n0xcb38de000\n0x66e7f6ae000\n0x66e7f6ae000"
    "\n0x3db7cc8000\n0xc70fef000\n0xba2334000\n0xc8acd3000\n0xcbbca0000\n0xb0eb"
    "b4000\n0x33c1a5000\n0xc4cc62000\n0x2e344b000\n0x2e344b000\n0xc6ee88000\n0x"
    "66e7fbfd000\n0x66e7fbfd032\n0x32d0aa000\n0xbaffbc000\n0x66e7fbfd000\n0x66e"
    "7f6ae000\n0x3db4102000\n0x62f80000000\n0x62f80000064\n0x62f80000032\n0x62f"
    "80000032\n0x62f80000032\n0x66e7fbfd000\n0x66e7f6ae000\n0xd20ac3000\n0xcb2c"
    "3a000\n0x66e7fbfd000\n0x2eeb3e000\n0xcf1b96000\n0x315b2b000\n0x66e7fbfd000"
    "\n0x62f80000032\n0x66e7f6ae000\n0x3db7cc8000\n0x620b1880000\n0x62f80000000"
    "\n0x60feb63e000\n0x1a6f49000\n0x1a6f49000\n0x66e7f60d000\n0x56413181c000\n"
    "0x56413181c000\n0x56413181c000\n0x56413181c000\n0x55731032064\n0xcf9d41000"
    "\n0xcf9d41000\n0xcf9d41000\n0x68da86000\n0x68da86000\n0x66e7f60d000";

// const char arry of bad config json file
const char* badconfig_json = R"(
{
  "grep_CXL": "cat /proc/iomem|grep CXL",
  "grep_acpi_srat": "[ -f /var/log/dmesg ] && cat /var/log/dmesg || [ -x dmesg ] && dmesg|grep -i acpi|grep -i srat",
  "regex_iomem" "^[\\s]*[0-9a-z]+-[0-9a-z]+[\\s]*:[\\s]*CXL[\\s]*Window[\\s]*[0-9]+$",
  "regex_addr_range": ".*mem[\\s]*([0-9a-z]+-[0-9a-z]+).*",
  "mce_inject_template_string": "CPU {cpu} BANK 1\nSTATUS CORRECTED\nADDR {addr}\n",
  "rasdaemon_exec_command": "rasdaemon -f -r /dev/null 2>&1 > ",
  "ras_mc_ctl_error_addresses": "ras-mc-ctl --errors|awk -F',' '{printf \"\\n\" $7}'|cut -d'=' -f2"
}
)";

// input from an empty json file
unsigned char config0_json[] = {};
unsigned int config0_json_len = 0;

// Input from a valid config.json file
const char config_json[] = R"(
{
  "grep_CXL": "cat /proc/iomem|grep CXL",
  "grep_acpi_srat": "[ -f /var/log/dmesg ] && cat /var/log/dmesg || [ -x dmesg ] && dmesg|grep -i acpi|grep -i srat",
  "regex_iomem": "^[\\s]*[0-9a-z]+-[0-9a-z]+[\\s]*:[\\s]*CXL[\\s]*Window[\\s]*[0-9]+$",
  "regex_addr_range": ".*mem[\\s]*([0-9a-z]+-[0-9a-z]+).*",
  "mce_inject_template_string": "CPU {cpu} BANK 1\nSTATUS CORRECTED\nADDR {addr}\n",
  "rasdaemon_exec_command": "rasdaemon -f -r /dev/null 2>&1 > ",
  "ras_mc_ctl_error_addresses": "ras-mc-ctl --errors|awk -F',' '{printf \"\\n\" $7}'|cut -d'=' -f2"
}
)";

// Input from a Json file that lacks the entry for "grep_CXL" key
const char config1_json[] = R"(
{
  "grep_acpi_srat": "[ -f /var/log/dmesg ] && cat /var/log/dmesg || [ -x dmesg ] && dmesg|grep -i acpi|grep -i srat",
  "regex_iomem": "^[\\s]*[0-9a-z]+-[0-9a-z]+[\\s]*:[\\s]*CXL[\\s]*Window[\\s]*[0-9]+$",
  "regex_addr_range": ".*mem[\\s]*([0-9a-z]+-[0-9a-z]+).*",
  "mce_inject_template_string": "CPU {cpu} BANK 1\nSTATUS CORRECTED\nADDR {addr}\n",
  "rasdaemon_exec_command": "rasdaemon -f -r /dev/null 2>&1 > ",
  "ras_mc_ctl_error_addresses": "ras-mc-ctl --errors|awk -F',' '{printf \"\\n\" $7}'|cut -d'=' -f2"
}
)";

// Input from a Json file that lacks the entry for "grep_acpi_srat" key
const char config2_json[] = R"(
{
  "grep_CXL": "cat /proc/iomem|grep CXL",
  "regex_iomem": "^[\\s]*[0-9a-z]+-[0-9a-z]+[\\s]*:[\\s]*CXL[\\s]*Window[\\s]*[0-9]+$",
  "regex_addr_range": ".*mem[\\s]*([0-9a-z]+-[0-9a-z]+).*",
  "mce_inject_template_string": "CPU {cpu} BANK 1\nSTATUS CORRECTED\nADDR {addr}\n",
  "rasdaemon_exec_command": "rasdaemon -f -r /dev/null 2>&1 > ",
  "ras_mc_ctl_error_addresses": "ras-mc-ctl --errors|awk -F',' '{printf \"\\n\" $7}'|cut -d'=' -f2"
}
)";

// Input from a Json file that lacks the entry for "regex_iomem" key
const char config3_json[] = R"(
{
  "grep_CXL": "cat /proc/iomem|grep CXL",
  "grep_acpi_srat": "[ -f /var/log/dmesg ] && cat /var/log/dmesg || [ -x dmesg ] && dmesg|grep -i acpi|grep -i srat",
  "regex_addr_range": ".*mem[\\s]*([0-9a-z]+-[0-9a-z]+).*",
  "mce_inject_template_string": "CPU {cpu} BANK 1\nSTATUS CORRECTED\nADDR {addr}\n",
  "rasdaemon_exec_command": "rasdaemon -f -r /dev/null 2>&1 > ",
  "ras_mc_ctl_error_addresses": "ras-mc-ctl --errors|awk -F',' '{printf \"\\n\" $7}'|cut -d'=' -f2"
}
)";

// Input from a Json file that lacks the entry for "regex_addr_range" key
const char config4_json[] = R"(
{
  "grep_CXL": "cat /proc/iomem|grep CXL",
  "grep_acpi_srat": "[ -f /var/log/dmesg ] && cat /var/log/dmesg || [ -x dmesg ] && dmesg|grep -i acpi|grep -i srat",
  "regex_iomem": "^[\\s]*[0-9a-z]+-[0-9a-z]+[\\s]*:[\\s]*CXL[\\s]*Window[\\s]*[0-9]+$",
  "mce_inject_template_string": "CPU {cpu} BANK 1\nSTATUS CORRECTED\nADDR {addr}\n",
  "rasdaemon_exec_command": "rasdaemon -f -r /dev/null 2>&1 > ",
  "ras_mc_ctl_error_addresses": "ras-mc-ctl --errors|awk -F',' '{printf \"\\n\" $7}'|cut -d'=' -f2"
}
)";

// Input from a Json file that lacks the entry for "rasdaemon_exec_command" key
const char config5_json[] = R"(
{
  "grep_CXL": "cat /proc/iomem|grep CXL",
  "grep_acpi_srat": "[ -f /var/log/dmesg ] && cat /var/log/dmesg || [ -x dmesg ] && dmesg|grep -i acpi|grep -i srat",
  "regex_iomem": "^[\\s]*[0-9a-z]+-[0-9a-z]+[\\s]*:[\\s]*CXL[\\s]*Window[\\s]*[0-9]+$",
  "regex_addr_range": ".*mem[\\s]*([0-9a-z]+-[0-9a-z]+).*",
  "mce_inject_template_string": "CPU {cpu} BANK 1\nSTATUS CORRECTED\nADDR {addr}\n",
  "ras_mc_ctl_error_addresses": "ras-mc-ctl --errors|awk -F',' '{printf \"\\n\" $7}'|cut -d'=' -f2"
}
)";

// Input from a Json file that lacks the entry for
// "ras_mc_ctl_error_addresses" key
unsigned char config6_json[] = R"(
{
  "grep_CXL": "cat /proc/iomem|grep CXL",
  "grep_acpi_srat": "[ -f /var/log/dmesg ] && cat /var/log/dmesg || [ -x dmesg ] && dmesg|grep -i acpi|grep -i srat",
  "regex_iomem": "^[\\s]*[0-9a-z]+-[0-9a-z]+[\\s]*:[\\s]*CXL[\\s]*Window[\\s]*[0-9]+$",
  "regex_addr_range": ".*mem[\\s]*([0-9a-z]+-[0-9a-z]+).*",
  "mce_inject_template_string": "CPU {cpu} BANK 1\nSTATUS CORRECTED\nADDR {addr}\n",
  "rasdaemon_exec_command": "rasdaemon -f -r /dev/null 2>&1 > "
}
)";

#endif

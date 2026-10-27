# Restore VM Snapshot with (PowerShell) PowerCLI

# Stop if any error is encountered
$ErrorActionPreference = "Stop"

# Collect credentials from environment
$VCSA_HOSTNAME = $Env:VCSA_HOSTNAME
$VCSA_USER = $Env:VCSA_USER
$VCSA_PASS = $Env:VCSA_PASS
# TARGET_VM (set per job) takes precedence over the project-level VM_NAME
$VM_NAME = if ($Env:TARGET_VM) { $Env:TARGET_VM } else { $Env:VM_NAME }

# Ignore self-signed cert errors
Set-PowerCLIConfiguration -InvalidCertificateAction Ignore -Confirm:$false
# Opt out of customer improvement program
Set-PowerCLIConfiguration -Scope User -ParticipateInCEIP $false -Confirm:$false

# Connect to VCSA
Connect-VIServer -Server $VCSA_HOSTNAME -User $VCSA_USER -Password $VCSA_PASS

# Revert VM to most recent snapshot
$VM = Get-VM -Name $VM_NAME
$SNAP = Get-Snapshot -VM $VM | Sort-Object -Property Created -Descending | Select-Object -First 1
Set-VM -VM $VM -Snapshot $SNAP -Confirm:$false

# A snapshot taken without memory leaves the VM powered off after the revert
if ((Get-VM -Name $VM_NAME).PowerState -ne "PoweredOn") {
    Start-VM -VM $VM_NAME -Confirm:$false
}

# Restore VM Snapshot with (PowerShell) PowerCLI

# Stop if any error is encountered
$ErrorActionPreference = "Stop"

# Collect credentials from environment
$VCSA_HOSTNAME = $Env:VCSA_HOSTNAME
$VCSA_USER = $Env:VCSA_USER
$VCSA_PASS = $Env:VCSA_PASS
$VM_NAME = $Env:VM_NAME

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

# Thin wrapper. The check list and isolation live in tools/run_checks.py so the
# POSIX and PowerShell entry points can never drift apart again.
param(
    [ValidateSet('full', 'dashboard', 'mirror')]
    [string]$Scope = 'full'
)

Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)
& python -B tools/run_checks.py $Scope
exit $LASTEXITCODE

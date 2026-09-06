param(
  [ValidateSet('start-menu','desktop','both')]
  [string]$Location = 'start-menu',
  [switch]$Remove
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$appRoot = Join-Path $env:LOCALAPPDATA 'Joblooper'
$iconPath = Join-Path $appRoot 'joblooper.ico'
$startMenu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Joblooper.lnk'
$desktop = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Joblooper.lnk'
$targets = if ($Location -eq 'both') { @($startMenu, $desktop) } elseif ($Location -eq 'desktop') { @($desktop) } else { @($startMenu) }

if ($Remove) {
  foreach ($target in $targets) {
    if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Force }
  }
  Write-Output "Removed selected Joblooper shortcut(s). Runtime data was not touched."
  exit 0
}

$python = (Get-Command python -ErrorAction Stop).Source
New-Item -ItemType Directory -Path $appRoot -Force | Out-Null
$encodedIcon = (Get-Content -LiteralPath (Join-Path $repoRoot 'assets\joblooper.ico.b64') -Raw).Trim()
[IO.File]::WriteAllBytes($iconPath, [Convert]::FromBase64String($encodedIcon))
$shell = New-Object -ComObject WScript.Shell
foreach ($target in $targets) {
  $shortcut = $shell.CreateShortcut($target)
  $shortcut.TargetPath = $python
  $shortcut.Arguments = '"' + (Join-Path $repoRoot 'jl.py') + '" dashboard'
  $shortcut.WorkingDirectory = $repoRoot
  $shortcut.IconLocation = $iconPath + ',0'
  $shortcut.Description = 'Open the local governed Joblooper application workspace'
  $shortcut.WindowStyle = 7
  $shortcut.Save()
}
Write-Output "Installed Joblooper shortcut(s): $($targets -join ', ')"

<#
.SYNOPSIS
  Installs the Pcapy Wireshark plugins on Windows.
.DESCRIPTION
  Installs the "Pcapy: phone" capture interface, the Lua dissector (pcapy.app / pcapy.uid fields)
  and a "Pcapy" profile with an App column. Folders are taken from Wireshark itself (tshark -G folders),
  falling back to %APPDATA%\Wireshark. The capture interface needs Python 3 (the "py" launcher or "python").
.PARAMETER Uninstall
  Remove the plugin files (the Pcapy profile is kept).
.PARAMETER ExtcapDir
  Install the capture interface here.
.PARAMETER PluginsDir
  Install the Lua dissector here.
.PARAMETER ProfileDir
  Create the Pcapy profile here.
.PARAMETER Tshark
  Path of tshark.exe used to ask Wireshark for its folders.
#>
[CmdletBinding()]
param(
    [switch]$Uninstall,
    [string]$ExtcapDir,
    [string]$PluginsDir,
    [string]$ProfileDir,
    [string]$Tshark
)

$ErrorActionPreference = 'Stop'
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path

function Find-Tshark {
    if ($Tshark) { return $Tshark }
    $cmd = Get-Command tshark -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($root in @($env:ProgramFiles, ${env:ProgramFiles(x86)})) {
        if ($root) {
            $candidate = Join-Path $root 'Wireshark\tshark.exe'
            if (Test-Path $candidate) { return $candidate }
        }
    }
    return $null
}

# Value of one line of `tshark -G folders`, e.g. "Personal Extcap path".
function Get-WiresharkFolder([string]$ts, [string]$label) {
    if (-not $ts) { return $null }
    try {
        $line = & $ts -G folders 2>$null | Where-Object { $_ -like "${label}:*" } | Select-Object -First 1
        if ($line) { return ($line -replace "^${label}:\s*", '').Trim() }
    } catch { }
    return $null
}

$ts = Find-Tshark
if (-not $ExtcapDir)  { $ExtcapDir  = Get-WiresharkFolder $ts 'Personal Extcap path' }
if (-not $PluginsDir) { $PluginsDir = Get-WiresharkFolder $ts 'Personal Lua Plugins' }
if (-not $ProfileDir) {
    $cfg = Get-WiresharkFolder $ts 'Personal configuration'
    if (-not $cfg) { $cfg = Join-Path $env:APPDATA 'Wireshark' }
    $ProfileDir = Join-Path $cfg 'profiles\Pcapy'
}
if (-not $ExtcapDir)  { $ExtcapDir  = Join-Path $env:APPDATA 'Wireshark\extcap' }
if (-not $PluginsDir) { $PluginsDir = Join-Path $env:APPDATA 'Wireshark\plugins' }

# The Python script lives in a subfolder; only the .bat launcher sits where Wireshark looks for extcap programs.
$ExtcapSub = Join-Path $ExtcapDir 'pcapy'

if ($Uninstall) {
    Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $ExtcapDir 'pcapy_extcap.bat')
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $ExtcapSub
    Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $PluginsDir 'pcapy.lua')
    Write-Host "Removed the Pcapy plugin files from:"
    Write-Host "  $ExtcapDir"
    Write-Host "  $PluginsDir"
    if (Test-Path $ProfileDir) {
        Write-Host "The profile was kept; delete it in Wireshark (Edit > Configuration Profiles) or remove $ProfileDir"
    }
    Write-Host "Restart Wireshark."
    return
}

New-Item -ItemType Directory -Force -Path $ExtcapDir, $ExtcapSub, $PluginsDir | Out-Null
Copy-Item -Force (Join-Path $Here 'extcap\pcapy_extcap.py')  (Join-Path $ExtcapSub 'pcapy_extcap.py')
Copy-Item -Force (Join-Path $Here 'extcap\pcapy_extcap.bat') (Join-Path $ExtcapDir 'pcapy_extcap.bat')
Copy-Item -Force (Join-Path $Here 'lua\pcapy.lua')           (Join-Path $PluginsDir 'pcapy.lua')
Write-Host "Installed extcap : $(Join-Path $ExtcapDir 'pcapy_extcap.bat') (script in $ExtcapSub)"
Write-Host "Installed Lua    : $(Join-Path $PluginsDir 'pcapy.lua')"

$prefs = Join-Path $ProfileDir 'preferences'
if (Test-Path $prefs) {
    Write-Host "Profile 'Pcapy' already exists, left untouched ($ProfileDir)"
} else {
    New-Item -ItemType Directory -Force -Path $ProfileDir | Out-Null
    Copy-Item -Force (Join-Path $Here 'profile\preferences') $prefs
    Write-Host "Created profile  : Pcapy ($ProfileDir) - choose it in the status bar, bottom right"
}

if (-not ((Get-Command py -ErrorAction SilentlyContinue) -or (Get-Command python -ErrorAction SilentlyContinue))) {
    Write-Warning "Python 3 was not found on PATH. The capture interface needs it: https://www.python.org/downloads/"
}
Write-Host "Restart Wireshark to load the plugins."

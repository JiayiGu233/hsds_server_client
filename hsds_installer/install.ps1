$CurrentPath = Get-Location
$DestinationPathRoot = "C:\Sioux"
$DestinationPath = "C:\Sioux\hsds_installer"
$NSSMPath = "C:\Sioux\Tools\nssm-2.24\win64\nssm.exe"
$HSDSServiceName = "HSDS_Server"
$WatchdogServiceName = "Watchdog_Service"
# $HSDSexe = "C:\Program Files\Python39\Scripts\hsds.exe"
$HSDSPath = Join-Path $DestinationPath "hsds"
$WatchdogScript = Join-Path $DestinationPath "watchdog_service.py"
$HSDSLog = Join-Path $DestinationPath "logs\hs.log"
$HSDSData = Join-Path $HSDSPath "hsds_data"
$HSDSPassword = Join-Path $DestinationPath ".\password.txt"
$ReqFile = Join-Path $DestinationPath "requirements.txt"
$VenvPath = Join-Path $DestinationPath "venv"
$PythonExe = Join-Path $VenvPath "Scripts\python.exe"

Write-Host "Copying hsds_installer folder to $DestinationPathRoot ..."
Copy-Item -Path "$CurrentPath" -Destination $DestinationPathRoot -Recurse -Force

Write-Host "Changing directory to $HSDSPath ..."
Set-Location $HSDSPath

$WatchdogConfigFile = Join-Path $DestinationPath "trace_path.json"
$watchdogDirs = @()

Write-Host "`nPlease press ENTER to add paths to Traces."
[void][System.Console]::ReadLine()

do {
    $path = Read-Host "Enter path to a trace folder"
    if (-not (Test-Path $path)) {
        Write-Host "ERROR: The path '$path' does not exist." -ForegroundColor Red
        $retry = Read-Host "Do you want to enter another path? (y/n)"
        if ($retry -eq 'y') {
            continue
        } else {
            break
        }
    } else {
        $watchdogDirs += $path
        $more = Read-Host "Do you want to enter another path? (y/n)"
    }
} while ($more -eq 'y')

Write-Host "`nYou have entered the following trace directories:"
$watchdogDirs | ForEach-Object { Write-Host " - $_" }

[void][System.Console]::ReadLine()

$watchdogObj = @{ watchdog_dirs = $watchdogDirs }
$watchdogObj | ConvertTo-Json -Depth 2 | Out-File -Encoding UTF8 $WatchdogConfigFile
Write-Host "SUCCESS: Saved directories to $WatchdogConfigFile"

if (-not (Test-Path $NSSMPath)) {
    Copy-Item -Path "$DestinationPath\nssm-2.24" -Destination "$DestinationPathRoot\Tools" -Recurse -Force
}

$pythonPathResult = & where.exe python | Where-Object { $_ -like "*Python39*" } | Select-Object -First 1
$pythonPath = $pythonPathResult.Trim()
if (-not $pythonPath) {
    Write-Error "Could not find Python 3.9 in PATH."
    exit 1
}
Write-Host "[INFO] Python 3.9 is at: $pythonPath"

# 创建 venv 虚拟环境
if (-not (Test-Path $PythonExe)) {
    & $pythonPath -m venv $VenvPath
}

Write-Host "Installing Python dependencies from requirements.txt ..."
& $PythonExe -m pip install --upgrade pip
& $PythonExe -m pip install -r $ReqFile
function Get-ToolPath($toolName) {
    $scriptsPath = Join-Path $VenvPath "Scripts"
    $fullPath = Join-Path $scriptsPath "$toolName.exe"
    if (Test-Path $fullPath) {
        return $fullPath
    } else {
        Write-Error "$toolName.exe not found in virtual environment"
        exit 1
    }
}

$HsdsExePath = Get-ToolPath "hsds"
$HsloadPath = Get-ToolPath "hsload"
$HslsPath = Get-ToolPath "hsls"

Write-Host "[INFO] hsds.exe is at: $HsdsExePath"
Write-Host "[INFO] hsload.exe is at: $HsloadPath"
Write-Host "[INFO] hsls.exe is at: $HslsPath"

Write-Host "Setting environment variables..."
setx USER_NAME "admin" /M
setx USER_PASSWORD "admin" /M
setx ADMIN_USERNAME "admin" /M
setx ADMIN_PASSWORD "admin" /M
Write-Host "Environment variables set. (Please login again)"


$HSDSArgument = "--logfile $HSDSLog --root_dir $HSDSData --password_file $HSDSPassword"
& $NSSMPath install $HSDSServiceName $HsdsExePath
& $NSSMPath set $HSDSServiceName AppParameters $HSDSArgument
& $NSSMPath set $HSDSServiceName Start SERVICE_AUTO_START
& $NSSMPath set $HSDSServiceName AppStdout "$DestinationPath\logs\HSDS_stdout.log"
& $NSSMPath set $HSDSServiceName AppStderr "$DestinationPath\logs\HSDS_stderr.log"
& $NSSMPath start $HSDSServiceName
& $NSSMPath get $HSDSServiceName

& $NSSMPath install $WatchdogServiceName $PythonExe  
& $NSSMPath set $WatchdogServiceName AppParameters $WatchdogScript
& $NSSMPath set $WatchdogServiceName AppDirectory $DestinationPath
& $NSSMPath set $WatchdogServiceName Start SERVICE_AUTO_START
& $NSSMPath set $WatchdogServiceName AppStdout "$DestinationPath\logs\watchdog_stdout.log"
& $NSSMPath set $WatchdogServiceName AppStderr "$DestinationPath\logs\watchdog_stderr.log"
& $NSSMPath start $WatchdogServiceName
& $NSSMPath get $WatchdogServiceName


Write-Host "`nInstallation complete. Both $HSDSServiceName and $WatchdogServiceName have been scheduled to run at system startup. Please reboot"
Pause
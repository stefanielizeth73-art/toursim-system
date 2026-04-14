param(
    [int]$Port = 5000
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $projectRoot "venv\Scripts\python.exe"
$pythonExe = if (Test-Path $venvPython) { $venvPython } else { "python" }

$startedApp = $false
$appProcess = $null
$cloudflaredProcess = $null

function Test-PortListening {
    param([int]$TargetPort)

    $connection = Get-NetTCPConnection -LocalPort $TargetPort -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    return $null -ne $connection
}

function Wait-ForLocalServer {
    param(
        [int]$TargetPort,
        [int]$TimeoutSeconds = 30
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $null = Invoke-WebRequest -Uri "http://127.0.0.1:$TargetPort" -UseBasicParsing -TimeoutSec 2
            return $true
        } catch {
            Start-Sleep -Milliseconds 800
        }
    }

    return $false
}

function Wait-ForPublicUrl {
    param(
        [string]$LogPath,
        [int]$TimeoutSeconds = 30
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Path $LogPath) {
            $match = Select-String -Path $LogPath -Pattern 'https://[-a-z0-9]+\.trycloudflare\.com' -AllMatches -ErrorAction SilentlyContinue |
                Select-Object -First 1
            if ($match) {
                return $match.Matches[0].Value
            }
        }

        Start-Sleep -Milliseconds 800
    }

    return $null
}

function Get-LanAddress {
    $addresses = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object {
            $_.IPAddress -notlike "127.*" -and
            $_.IPAddress -notlike "169.254.*" -and
            $_.PrefixOrigin -ne "WellKnown"
        } |
        Select-Object -ExpandProperty IPAddress

    return $addresses | Select-Object -First 1
}

function Stop-IfRunning {
    param($Process)

    if ($null -ne $Process -and -not $Process.HasExited) {
        Stop-Process -Id $Process.Id -Force
    }
}

function Ensure-Cloudflared {
    param([string]$BinaryPath)

    $needsDownload = $true
    if (Test-Path $BinaryPath) {
        $fileInfo = Get-Item $BinaryPath
        $needsDownload = $fileInfo.Length -lt 1024
    }

    if ($needsDownload) {
        Write-Host "Downloading cloudflared for the first run..."
        Invoke-WebRequest `
            -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" `
            -OutFile $BinaryPath `
            -TimeoutSec 120
    }
}

try {
    if (Test-PortListening -TargetPort $Port) {
        Write-Host "Port $Port is already in use. Reusing the running local service."
    } else {
        Write-Host "Starting the Flask app..."
        $launchCommand = @"
\$env:FLASK_HOST='0.0.0.0'
\$env:PORT='$Port'
\$env:FLASK_DEBUG='0'
Set-Location '$projectRoot'
& '$pythonExe' 'app.py'
"@

        $appProcess = Start-Process -FilePath "powershell.exe" `
            -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $launchCommand) `
            -WorkingDirectory $projectRoot `
            -WindowStyle Hidden `
            -PassThru

        $startedApp = $true
    }

    if (-not (Wait-ForLocalServer -TargetPort $Port)) {
        throw "The local service did not start in time. Please make sure app.py can run normally first."
    }

    $lanAddress = Get-LanAddress
    if ($lanAddress) {
        Write-Host "LAN URL: http://$lanAddress`:$Port"
    } else {
        Write-Host "No LAN IPv4 address was found. A public share link will still be created."
    }

    $toolDir = Join-Path $env:LOCALAPPDATA "ToursimShare"
    $cloudflaredPath = Join-Path $toolDir "cloudflared.exe"
    $logPath = Join-Path $toolDir "cloudflared.log"

    if (-not (Test-Path $toolDir)) {
        New-Item -ItemType Directory -Path $toolDir | Out-Null
    }

    Ensure-Cloudflared -BinaryPath $cloudflaredPath

    if (Test-Path $logPath) {
        Remove-Item $logPath -Force
    }

    Write-Host "Creating a public share link..."
    $cloudflaredProcess = Start-Process -FilePath $cloudflaredPath `
        -ArgumentList @("tunnel", "--url", "http://127.0.0.1:$Port", "--logfile", $logPath, "--loglevel", "info") `
        -WindowStyle Hidden `
        -PassThru

    $publicUrl = Wait-ForPublicUrl -LogPath $logPath -TimeoutSeconds 45
    if (-not $publicUrl) {
        throw "Failed to create the public share link. Please try again in a moment."
    }

    Write-Host ""
    Write-Host "Share this URL with other people:"
    Write-Host $publicUrl -ForegroundColor Green
    Write-Host ""
    Write-Host "Keep this window open. Press Enter to stop sharing."
    [void][Console]::ReadLine()
}
finally {
    Stop-IfRunning -Process $cloudflaredProcess

    if ($startedApp) {
        Stop-IfRunning -Process $appProcess
    }
}

$ErrorActionPreference = "SilentlyContinue"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$url = "http://localhost:5050"

function Test-JarvisReady {
    try {
        $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 1
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
    } catch {
        return $false
    }
}

if (-not (Test-JarvisReady)) {
    $python = Join-Path $projectRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $python)) {
        $python = "python"
    }

    $jarvis = Join-Path $projectRoot "jarvis.py"
    $command = "set `"JARVIS_NO_BROWSER=1`" && `"$python`" `"$jarvis`""

    Start-Process -FilePath $env:ComSpec `
        -ArgumentList "/c", $command `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden
}

for ($i = 0; $i -lt 45; $i++) {
    if (Test-JarvisReady) {
        break
    }
    Start-Sleep -Milliseconds 500
}

$chromeCandidates = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LocalAppData\Google\Chrome\Application\chrome.exe"
)

$chrome = $chromeCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($chrome) {
    Start-Process -FilePath $chrome -ArgumentList "--app=$url", "--start-maximized"
} else {
    Start-Process $url
}

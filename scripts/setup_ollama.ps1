#Requires -Version 5.1
<#
.SYNOPSIS
  Full deployment for CUA-Skill Agent on Windows (Python deps + Ollama model).

.DESCRIPTION
  1. Check Python 3.10+
  2. Create/use .venv and pip install project dependencies
  3. Install Ollama for Windows (if missing) via silent OllamaSetup.exe
  4. Check / start Ollama service
  5. Download Qwen2.5-VL GGUF + mmproj from HuggingFace (if missing)
  6. Create custom model: qwen2.5vl-vision (matches agent/config_ollama.json)
  7. Run smoke tests (skill matcher + optional vision API)

.PARAMETER ModelName
  Ollama model tag to create. Default: read from agent/config_ollama.json

.PARAMETER Force
  Re-download GGUF files, recreate model, and reinstall Python packages.

.PARAMETER SkipDownload
  Skip HuggingFace download; assume GGUF files already exist in scripts/models/.

.PARAMETER SkipPython
  Skip Python virtualenv and pip install steps.

.PARAMETER SkipModel
  Skip Ollama model download/create (only install Python deps).

.PARAMETER SkipOllamaInstall
  Skip automatic Ollama for Windows installation (assume already installed).

.PARAMETER SkipTest
  Skip Ollama vision API smoke test.

.PARAMETER SkipVerify
  Skip test_match.py at the end.

.PARAMETER NoVenv
  Install packages into current Python instead of project .venv.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\setup_ollama.ps1

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\setup_ollama.ps1 -Force
#>
[CmdletBinding()]
param(
    [string]$ModelName = "qwen2.5vl-vision",
    [switch]$Force,
    [switch]$SkipDownload,
    [switch]$SkipPython,
    [switch]$SkipModel,
    [switch]$SkipOllamaInstall,
    [switch]$SkipTest,
    [switch]$SkipVerify,
    [switch]$NoVenv
)

$ErrorActionPreference = "Stop"

$ProjectRoot   = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ScriptsDir    = Join-Path $ProjectRoot "scripts"
$ModelsDir     = Join-Path $ScriptsDir "models"
$Modelfile     = Join-Path $ScriptsDir "Modelfile.qwen2.5vl-vision"
$ConfigPath    = Join-Path $ProjectRoot "agent\config_ollama.json"
$Requirements  = Join-Path $ProjectRoot "agent\requirements.txt"
$VenvDir       = Join-Path $ProjectRoot ".venv"
$OllamaHost    = "http://127.0.0.1:11434"
$OllamaInstallerUrl = "https://ollama.com/download/OllamaSetup.exe"
$ExtraPackages = @("flask", "pywin32")

$HFRepo        = "chatpig/qwen2.5-vl-7b-it-gguf"
$MainGGUF      = "qwen2.5-vl-7b-it-q4_k_m.gguf"
$MmprojGGUF    = "mmproj-qwen2.5-vl-7b-it-q4_0.gguf"

$script:PythonExe = $null

function Write-Step([string]$Msg) {
    Write-Host ""
    Write-Host "==> $Msg" -ForegroundColor Cyan
}

function Write-Ok([string]$Msg) {
    Write-Host "[OK] $Msg" -ForegroundColor Green
}

function Write-Warn([string]$Msg) {
    Write-Host "[WARN] $Msg" -ForegroundColor Yellow
}

function Find-PythonExe {
    if ($env:PYTHON_FOR_SETUP -and (Test-Path $env:PYTHON_FOR_SETUP)) {
        return $env:PYTHON_FOR_SETUP
    }

    foreach ($pair in @(
        @{ Cmd = "py"; Args = @("-3", "-c", "import sys; print(sys.executable)") },
        @{ Cmd = "python"; Args = @("-c", "import sys; print(sys.executable)") },
        @{ Cmd = "python3"; Args = @("-c", "import sys; print(sys.executable)") }
    )) {
        try {
            $out = & $pair.Cmd @($pair.Args) 2>$null
            if ($LASTEXITCODE -eq 0 -and $out) {
                $path = "$out".Trim()
                if ($path -and (Test-Path $path)) { return $path }
            }
        } catch {}
    }

    try {
        $where = & where.exe python 2>$null | Select-Object -First 1
        if ($where -and (Test-Path $where)) { return $where.Trim() }
    } catch {}

    return $null
}

function Get-PythonCommand {
    if ($script:PythonExe) { return $script:PythonExe }
    throw "Python not initialized. Run Install-ProjectDependencies first."
}

function Install-ProjectDependencies {
    if ($SkipPython) {
        Write-Warn "Skipping Python dependency install (-SkipPython)."
        $script:PythonExe = Find-PythonExe
        if (-not $script:PythonExe) {
            throw "Python not found. Install Python 3.10+ from https://www.python.org/downloads/"
        }
        return
    }

    Write-Step "Python environment"

    $basePython = Find-PythonExe
    if (-not $basePython) {
        throw @"
Python 3.10+ not found.
Install from https://www.python.org/downloads/ and check 'Add python.exe to PATH', then re-run this script.
"@
    }
    Write-Ok "Found Python: $basePython"

    $ver = & $basePython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    $parts = $ver.Split(".")
    if ([int]$parts[0] -lt 3 -or ([int]$parts[0] -eq 3 -and [int]$parts[1] -lt 10)) {
        throw "Python 3.10+ required, found $ver"
    }
    Write-Ok "Python version: $ver"

    if ($NoVenv) {
        $script:PythonExe = $basePython
        Write-Warn "Using system Python (-NoVenv)."
    } else {
        $venvPython = Join-Path $VenvDir "Scripts\python.exe"
        if (-not (Test-Path $venvPython)) {
            Write-Host "  Creating virtualenv: $VenvDir"
            & $basePython -m venv $VenvDir
            if ($LASTEXITCODE -ne 0) { throw "Failed to create virtualenv" }
            Write-Ok "Virtualenv created"
        } else {
            Write-Ok "Using existing virtualenv: $VenvDir"
        }
        $script:PythonExe = $venvPython
    }

    Write-Host "  Upgrading pip..."
    & $script:PythonExe -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed" }

    if (-not (Test-Path $Requirements)) {
        throw "Missing requirements file: $Requirements"
    }

    $pipArgs = @("-m", "pip", "install", "-r", $Requirements) + $ExtraPackages
    if ($Force) { $pipArgs += "--upgrade" }

    Write-Host "  Installing: agent/requirements.txt + $($ExtraPackages -join ', ')"
    & $script:PythonExe @pipArgs
    if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

    Write-Ok "Python dependencies installed"

    Write-Host "  Verifying imports..."
    & $script:PythonExe -c "import flask, pyautogui, win32gui, pywinauto, requests, PIL; print('imports OK')"
    if ($LASTEXITCODE -ne 0) { throw "Import verification failed" }
    Write-Ok "Core packages import successfully"
}

function Find-OllamaExe {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"),
        "C:\Program Files\Ollama\ollama.exe",
        (Get-Command ollama -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
    ) | Where-Object { $_ -and (Test-Path $_) }

    if ($candidates.Count -gt 0) { return $candidates[0] }
    return $null
}

function Find-OllamaApp {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Ollama\Ollama.exe"),
        "C:\Program Files\Ollama\Ollama.exe"
    ) | Where-Object { $_ -and (Test-Path $_) }

    if ($candidates.Count -gt 0) { return $candidates[0] }
    return $null
}

function Install-OllamaWindows {
    if (Find-OllamaExe) {
        Write-Ok "Ollama already installed: $(Find-OllamaExe)"
        return
    }

    if ($SkipOllamaInstall) {
        throw @"
Ollama is not installed and -SkipOllamaInstall was specified.
Install manually from https://ollama.com/download/windows or re-run without -SkipOllamaInstall.
"@
    }

    Write-Step "Install Ollama for Windows"
    Write-Warn "This downloads OllamaSetup.exe (~300 MB) and installs per-user (no admin required)."

    $installerPath = Join-Path $env:TEMP "OllamaSetup.exe"
    Write-Host "  Downloading: $OllamaInstallerUrl"
    Write-Host "  Saving to  : $installerPath"

    if (Get-Command curl.exe -ErrorAction SilentlyContinue) {
        & curl.exe -L --progress-bar -o $installerPath $OllamaInstallerUrl
        if ($LASTEXITCODE -ne 0) { throw "Failed to download Ollama installer" }
    } else {
        Invoke-WebRequest -Uri $OllamaInstallerUrl -OutFile $installerPath -UseBasicParsing
    }

    if (-not (Test-Path $installerPath)) {
        throw "Ollama installer download failed: $installerPath"
    }

    Write-Host "  Running silent install (/VERYSILENT) — may take 1-3 minutes..."
    $proc = Start-Process -FilePath $installerPath -ArgumentList @(
        "/VERYSILENT",
        "/NORESTART",
        "/SP-"
    ) -Wait -PassThru

    if ($proc.ExitCode -ne 0) {
        throw "Ollama installer exited with code $($proc.ExitCode). Try manual install: https://ollama.com/download/windows"
    }

    for ($i = 1; $i -le 60; $i++) {
        $exe = Find-OllamaExe
        if ($exe) {
            Write-Ok "Ollama installed: $exe"
            return
        }
        Start-Sleep -Seconds 2
        if ($i % 5 -eq 0) { Write-Host "  waiting for Ollama files... ($i/60)" }
    }

    throw "Ollama installer finished but ollama.exe was not found. Install manually from https://ollama.com/download/windows"
}

function Start-OllamaApp {
    $app = Find-OllamaApp
    if ($app) {
        Write-Host "  Starting Ollama desktop app..."
        Start-Process -FilePath $app | Out-Null
        Start-Sleep -Seconds 4
    }
}

function Test-OllamaApi {
    try {
        $resp = Invoke-RestMethod -Uri "$OllamaHost/api/tags" -TimeoutSec 5 -Method Get
        return $true, $resp
    } catch {
        return $false, $null
    }
}

function Start-OllamaService {
    Install-OllamaWindows

    $ollamaExe = Find-OllamaExe
    if (-not $ollamaExe) {
        throw "Ollama binary not found after install attempt."
    }
    Write-Ok "Found Ollama: $ollamaExe"

    $ok, $tags = Test-OllamaApi
    if ($ok) {
        Write-Ok "Ollama API already running at $OllamaHost"
        return $ollamaExe
    }

    Write-Warn "Ollama API not responding. Starting Ollama..."
    Start-OllamaApp

    $ok, $null = Test-OllamaApi
    if (-not $ok) {
        Write-Warn "Starting ollama serve..."
        Start-Process -FilePath $ollamaExe -ArgumentList "serve" -WindowStyle Hidden | Out-Null
    }

    for ($i = 1; $i -le 30; $i++) {
        Start-Sleep -Seconds 2
        $ok, $null = Test-OllamaApi
        if ($ok) {
            Write-Ok "Ollama API is up ($OllamaHost)"
            return $ollamaExe
        }
        Write-Host "  waiting for Ollama API... ($i/30)"
    }
    throw "Ollama failed to start within 60 seconds. Open the Ollama app from Start menu, then re-run."
}

function Get-ConfigModelName {
    if (-not (Test-Path $ConfigPath)) { return $ModelName }
    try {
        $cfg = Get-Content $ConfigPath -Raw | ConvertFrom-Json
        $name = $cfg.planner.expertises.ollama.model_name
        if ($name) { return $name }
    } catch {}
    return $ModelName
}

function Test-ModelExists([string]$Name) {
    $ok, $tags = Test-OllamaApi
    if (-not $ok) { return $false }
    foreach ($m in $tags.models) {
        $tag = $m.name
        if ($tag -eq $Name -or $tag -eq "${Name}:latest" -or $tag.StartsWith("${Name}:")) {
            return $true
        }
    }
    return $false
}

function Download-HfFile([string]$FileName, [string]$DestPath) {
    if ((Test-Path $DestPath) -and -not $Force) {
        Write-Ok "Already exists: $FileName"
        return
    }

    New-Item -ItemType Directory -Force -Path (Split-Path $DestPath) | Out-Null
    $url = "https://huggingface.co/$HFRepo/resolve/main/$FileName"

    Write-Host "  Downloading $FileName"
    Write-Host "  URL: $url"
    Write-Warn "Large file — may take a while (~$FileName)."

    if (Get-Command curl.exe -ErrorAction SilentlyContinue) {
        & curl.exe -L --progress-bar -o $DestPath $url
        if ($LASTEXITCODE -ne 0) { throw "curl download failed for $FileName" }
    } else {
        Invoke-WebRequest -Uri $url -OutFile $DestPath -UseBasicParsing
    }

    if (-not (Test-Path $DestPath)) {
        throw "Download failed: $DestPath"
    }
    Write-Ok "Downloaded $FileName ($([math]::Round((Get-Item $DestPath).Length / 1GB, 2)) GB)"
}

function Invoke-Ollama([string]$OllamaExe, [string[]]$OllamaArgs) {
    Write-Host "  ollama $($OllamaArgs -join ' ')"
    & $OllamaExe @OllamaArgs
    if ($LASTEXITCODE -ne 0) {
        throw "ollama command failed: ollama $($OllamaArgs -join ' ')"
    }
}

function Test-VisionModel([string]$Name) {
    Write-Step "Smoke test: Ollama vision API"
    $pngB64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z/C/HwAFgwJ/lQ3+jQAAAABJRU5ErkJggg=="
    $payload = @{
        model = $Name
        messages = @(
            @{
                role = "user"
                content = @(
                    @{ type = "text"; text = "What color is this image? One word only." }
                    @{ type = "image_url"; image_url = @{ url = "data:image/png;base64,$pngB64" } }
                )
            }
        )
        stream = $false
    }

    $json = $payload | ConvertTo-Json -Depth 8
    $resp = Invoke-RestMethod -Uri "$OllamaHost/v1/chat/completions" -Method Post `
        -ContentType "application/json" -Body $json -TimeoutSec 120

    $answer = $resp.choices[0].message.content
    Write-Ok "Vision API responded: $answer"
}

function Install-OllamaModel([string]$Name) {
    if ($SkipModel) {
        Write-Warn "Skipping Ollama model setup (-SkipModel)."
        return
    }

    Write-Step "Ollama vision model: $Name"

    if ((Test-ModelExists $Name) -and -not $Force) {
        Write-Ok "Model '$Name' already installed."
        if (-not $SkipTest) {
            try { Test-VisionModel $Name } catch { Write-Warn "Vision test failed: $_" }
        }
        return
    }

    $OllamaExe = Start-OllamaService

    if (-not (Test-Path $Modelfile)) {
        throw "Missing Modelfile: $Modelfile"
    }

    Write-Step "Prepare model files"
    New-Item -ItemType Directory -Force -Path $ModelsDir | Out-Null

    $mainPath   = Join-Path $ModelsDir $MainGGUF
    $mmprojPath = Join-Path $ModelsDir $MmprojGGUF

    if (-not $SkipDownload) {
        Download-HfFile $MainGGUF $mainPath
        Download-HfFile $MmprojGGUF $mmprojPath
    } else {
        if (-not (Test-Path $mainPath))   { throw "Missing $mainPath (remove -SkipDownload or copy files manually)" }
        if (-not (Test-Path $mmprojPath)) { throw "Missing $mmprojPath (remove -SkipDownload or copy files manually)" }
        Write-Ok "Using existing GGUF files in $ModelsDir"
    }

    Write-Step "Create Ollama model '$Name'"
    $buildDir = Join-Path $env:TEMP "cua-ollama-build-$Name"
    if (Test-Path $buildDir) { Remove-Item $buildDir -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $buildDir | Out-Null

    Copy-Item $Modelfile (Join-Path $buildDir "Modelfile")
    Copy-Item $mainPath   (Join-Path $buildDir $MainGGUF)
    Copy-Item $mmprojPath (Join-Path $buildDir $MmprojGGUF)

    Push-Location $buildDir
    try {
        if ($Force -and (Test-ModelExists $Name)) {
            Write-Warn "Removing existing model '$Name'"
            try { Invoke-Ollama $OllamaExe @("rm", $Name) } catch { Write-Warn "ollama rm skipped: $_" }
        }
        Invoke-Ollama $OllamaExe @("create", $Name, "-f", "Modelfile")
    } finally {
        Pop-Location
    }

    Write-Ok "Model '$Name' created."

    if (-not $SkipTest) {
        try {
            Test-VisionModel $Name
        } catch {
            Write-Warn "Vision smoke test failed: $_"
            Write-Warn "Model was created; check GPU memory (recommend 8 GB+ VRAM)."
        }
    }
}

function Invoke-ProjectVerification {
    if ($SkipVerify) {
        Write-Warn "Skipping verification (-SkipVerify)."
        return
    }

    $py = Get-PythonCommand
    Write-Step "Verify: skill matcher (test_match.py)"
    Push-Location $ProjectRoot
    try {
        & $py (Join-Path $ProjectRoot "test_match.py")
        if ($LASTEXITCODE -ne 0) { throw "test_match.py failed" }
        Write-Ok "Skill matcher tests passed"
    } finally {
        Pop-Location
    }
}

# ---- main ----
Write-Host ""
Write-Host "CUA-Skill Agent — Full Setup (Python + Ollama)" -ForegroundColor White
Write-Host "Project: $ProjectRoot"

Install-ProjectDependencies

$ModelName = Get-ConfigModelName
Install-OllamaModel -Name $ModelName

Invoke-ProjectVerification

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "  Python : $(Get-PythonCommand)"
if (-not $NoVenv -and -not $SkipPython) {
    Write-Host "  Venv   : $VenvDir"
    Write-Host "  Activate: .\.venv\Scripts\Activate.ps1"
}
Write-Host "  Model  : $ModelName"
Write-Host "  API    : $OllamaHost"
Write-Host "  Config : $ConfigPath"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  python test_quick.py 1"
Write-Host "  python run.py `"Open Notepad`""
Write-Host "  python web\app.py"

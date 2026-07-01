#Requires -Version 5.1
<#
.SYNOPSIS
  Deploy Ollama vision model for CUA-Skill Agent (Windows).

.DESCRIPTION
  1. Checks / starts Ollama service
  2. Downloads Qwen2.5-VL GGUF + mmproj from HuggingFace (if missing)
  3. Creates custom model: qwen2.5vl-vision (matches agent/config_ollama.json)
  4. Runs a quick API smoke test

  Model name in config: agent/config_ollama.json -> planner.expertises.ollama.model_name

.PARAMETER ModelName
  Ollama model tag to create. Default: qwen2.5vl-vision

.PARAMETER Force
  Re-download GGUF files and recreate the model even if it already exists.

.PARAMETER SkipDownload
  Skip HuggingFace download; assume GGUF files already exist in scripts/models/.

.PARAMETER SkipTest
  Skip post-install vision API test.

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
    [switch]$SkipTest
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ScriptsDir  = Join-Path $ProjectRoot "scripts"
$ModelsDir   = Join-Path $ScriptsDir "models"
$Modelfile   = Join-Path $ScriptsDir "Modelfile.qwen2.5vl-vision"
$ConfigPath  = Join-Path $ProjectRoot "agent\config_ollama.json"
$OllamaHost  = "http://127.0.0.1:11434"

$HFRepo      = "chatpig/qwen2.5-vl-7b-it-gguf"
$MainGGUF    = "qwen2.5-vl-7b-it-q4_k_m.gguf"      # ~4.4 GB, fits 8 GB VRAM
$MmprojGGUF  = "mmproj-qwen2.5-vl-7b-it-q4_0.gguf" # ~580 MB vision projector

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

function Write-Err([string]$Msg) {
    Write-Host "[ERROR] $Msg" -ForegroundColor Red
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

function Test-OllamaApi {
    try {
        $resp = Invoke-RestMethod -Uri "$OllamaHost/api/tags" -TimeoutSec 5 -Method Get
        return $true, $resp
    } catch {
        return $false, $null
    }
}

function Start-OllamaService {
    $ollamaExe = Find-OllamaExe
    if (-not $ollamaExe) {
        throw "Ollama not found. Install from https://ollama.com/download/windows then re-run this script."
    }
    Write-Ok "Found Ollama: $ollamaExe"

    $ok, $tags = Test-OllamaApi
    if ($ok) {
        Write-Ok "Ollama API already running at $OllamaHost"
        return $ollamaExe
    }

    Write-Warn "Ollama API not responding. Starting ollama serve..."
    Start-Process -FilePath $ollamaExe -ArgumentList "serve" -WindowStyle Hidden | Out-Null

    for ($i = 1; $i -le 30; $i++) {
        Start-Sleep -Seconds 2
        $ok, $null = Test-OllamaApi
        if ($ok) {
            Write-Ok "Ollama API is up ($OllamaHost)"
            return $ollamaExe
        }
        Write-Host "  waiting for Ollama... ($i/30)"
    }
    throw "Ollama failed to start within 60 seconds. Open Ollama app manually, then re-run."
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
    Write-Host "  Dest: $DestPath"
    Write-Warn "Large file — this may take a while depending on network speed."

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

function Invoke-Ollama([string]$OllamaExe, [string[]]$Args) {
    Write-Host "  ollama $($Args -join ' ')"
    & $OllamaExe @Args
    if ($LASTEXITCODE -ne 0) {
        throw "ollama command failed: ollama $($Args -join ' ')"
    }
}

function Test-VisionModel([string]$Name) {
    Write-Step "Smoke test: vision API"
    $body = @{
        model = $Name
        messages = @(
            @{
                role = "user"
                content = "Reply with exactly one word: OK"
            }
        )
        stream = $false
    } | ConvertTo-Json -Depth 6

    # Minimal 1x1 PNG (valid image bytes)
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

# ---- main ----
Write-Host ""
Write-Host "CUA-Skill Agent — Ollama Model Setup" -ForegroundColor White
Write-Host "Project: $ProjectRoot"

$ModelName = Get-ConfigModelName
Write-Ok "Target model (from config): $ModelName"

if ((Test-ModelExists $ModelName) -and -not $Force) {
    Write-Ok "Model '$ModelName' already installed."
    if (-not $SkipTest) {
        try { Test-VisionModel $ModelName } catch { Write-Warn "Vision test failed: $_" }
    }
    Write-Host ""
    Write-Host "Done. Run: python run.py `"Open Notepad`"" -ForegroundColor Green
    exit 0
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

Write-Step "Create Ollama model '$ModelName'"
$buildDir = Join-Path $env:TEMP "cua-ollama-build-$ModelName"
if (Test-Path $buildDir) { Remove-Item $buildDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $buildDir | Out-Null

Copy-Item $Modelfile (Join-Path $buildDir "Modelfile")
Copy-Item $mainPath   (Join-Path $buildDir $MainGGUF)
Copy-Item $mmprojPath (Join-Path $buildDir $MmprojGGUF)

Push-Location $buildDir
try {
    if ($Force -and (Test-ModelExists $ModelName)) {
        Write-Warn "Removing existing model '$ModelName'"
        try { Invoke-Ollama $OllamaExe @("rm", $ModelName) } catch { Write-Warn "ollama rm skipped: $_" }
    }
    Invoke-Ollama $OllamaExe @("create", $ModelName, "-f", "Modelfile")
} finally {
    Pop-Location
}

Write-Ok "Model '$ModelName' created."

if (-not $SkipTest) {
    try {
        Test-VisionModel $ModelName
    } catch {
        Write-Warn "Vision smoke test failed: $_"
        Write-Warn "Model was created; check GPU memory (recommend 8 GB+ VRAM) and Ollama logs."
    }
}

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "  Model : $ModelName"
Write-Host "  API   : $OllamaHost"
Write-Host "  Config: $ConfigPath"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  pip install -r agent\requirements.txt flask pywin32"
Write-Host "  python test_quick.py 1"
Write-Host "  python run.py `"Open Notepad`""

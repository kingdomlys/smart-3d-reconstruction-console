param(
    [string]$EnvName = "tripo_env",
    [string]$RepoDir = "third_party/TripoSR"
)

$ErrorActionPreference = "Stop"

Write-Host "Creating conda env: $EnvName"
conda create -y -n $EnvName python=3.10

Write-Host "Cloning TripoSR into $RepoDir"
if (-not (Test-Path $RepoDir)) {
    git clone https://github.com/VAST-AI-Research/TripoSR $RepoDir
}

Write-Host "Installing TripoSR dependencies"
conda run -n $EnvName python -m pip install -U pip
conda run -n $EnvName python -m pip install -r $RepoDir/requirements.txt

Write-Host "Optional: install rembg"
conda run -n $EnvName python -m pip install rembg

Write-Host "Done. Set TRIPOSR_PY to the env python and TRIPOSR_CMD to the TripoSR entry script."

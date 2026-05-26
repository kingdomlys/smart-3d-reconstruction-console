param(
    [string]$EnvName = "gs_env",
    [string]$RepoDir = "third_party/gaussian-splatting"
)

$ErrorActionPreference = "Stop"

Write-Host "Creating conda env: $EnvName"
conda create -y -n $EnvName python=3.10

Write-Host "Cloning gaussian-splatting into $RepoDir"
if (-not (Test-Path $RepoDir)) {
    git clone https://github.com/graphdeco-inria/gaussian-splatting $RepoDir
}

Write-Host "Installing 3DGS dependencies"
conda run -n $EnvName python -m pip install -U pip
conda run -n $EnvName python -m pip install -r $RepoDir/requirements.txt

Write-Host "Done. Set DGS_TRAIN_SCRIPT to the train.py in the repo."

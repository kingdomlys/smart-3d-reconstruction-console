param(
    [string]$EnvName = "colmap_env"
)

$ErrorActionPreference = "Stop"

Write-Host "Creating conda env: $EnvName"
conda create -y -n $EnvName python=3.10

Write-Host "Installing COLMAP (conda-forge)"
conda run -n $EnvName conda install -y -c conda-forge colmap

Write-Host "Done. Set COLMAP_BIN to the colmap executable if needed."

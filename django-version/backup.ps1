param(
    [string]$OutputDirectory = (Join-Path $PSScriptRoot 'backups')
)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
    $dbContainer = (docker compose ps -q db).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $dbContainer) { throw 'PostgreSQL no está en ejecución.' }
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $archive = "/tmp/mesa-mantenimiento-$stamp.dump"
    $target = Join-Path $OutputDirectory "mesa-mantenimiento-$stamp.dump"
    try {
        docker compose exec -T db pg_dump -U mesa -d mesa_mantenimiento -Fc -f $archive
        if ($LASTEXITCODE -ne 0) { throw 'Falló pg_dump.' }
        docker cp "${dbContainer}:$archive" $target
        if ($LASTEXITCODE -ne 0) { throw 'No fue posible copiar el respaldo.' }
        Write-Output $target
    }
    finally {
        docker compose exec -T db rm -f -- $archive | Out-Null
    }
}
finally {
    Pop-Location
}
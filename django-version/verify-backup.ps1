param(
    [Parameter(Mandatory = $true)]
    [string]$BackupFile
)
$ErrorActionPreference = 'Stop'
$source = (Resolve-Path -LiteralPath $BackupFile).Path
Push-Location $PSScriptRoot
try {
    $dbContainer = (docker compose ps -q db).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $dbContainer) { throw 'PostgreSQL no está en ejecución.' }
    $stamp = Get-Date -Format 'yyyyMMddHHmmss'
    $testDatabase = "mesa_restore_$stamp"
    $archive = "/tmp/$testDatabase.dump"
    try {
        docker cp $source "${dbContainer}:$archive"
        if ($LASTEXITCODE -ne 0) { throw 'No fue posible copiar el archivo al contenedor.' }
        docker compose exec -T db createdb -U mesa $testDatabase
        if ($LASTEXITCODE -ne 0) { throw 'No fue posible crear la base temporal.' }
        docker compose exec -T db pg_restore -U mesa -d $testDatabase --no-owner --no-privileges $archive
        if ($LASTEXITCODE -ne 0) { throw 'La restauración de prueba falló.' }
        docker compose exec -T db psql -U mesa -d $testDatabase -At -c "SELECT COUNT(*) FROM maintenance_workorder"
        if ($LASTEXITCODE -ne 0) { throw 'La base restaurada no contiene las tablas de la aplicación.' }
        Write-Output 'Restauración de prueba correcta.'
    }
    finally {
        docker compose exec -T db dropdb -U mesa --if-exists $testDatabase 2>$null | Out-Null
        docker compose exec -T db rm -f -- $archive 2>$null | Out-Null
    }
}
finally {
    Pop-Location
}
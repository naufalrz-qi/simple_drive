# agent_backup.ps1
# Script to backup MS SQL Server, compress with 7z, and upload via API

param (
    [string]$DbServer = "localhost",
    [string]$DbName = "SOLID_SIM",
    [string]$DbUser = "sa",
    [string]$DbPass = "12qwaszx#DB",
    [string]$TempDir = "C:\Temp",
    [string]$SevenZipPath = "C:\Program Files\7-Zip\7z.exe",
    [string]$ApiUrl = "http://king-arthur/upload",
    [string]$ApiKey = "f54d707d6e0e765b9b33a944a6816bb9d0ddd4f5200a51aa1e3bda3c20efd1dc",
    [string]$UploadPath = "AutoDBBackups"
)

# Ensure TempDir exists
if (-not (Test-Path $TempDir)) {
    New-Item -ItemType Directory -Force -Path $TempDir | Out-Null
}

$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BakFile = "$TempDir\$DbName_$Timestamp.bak"
$ZipFile = "$TempDir\$DbName_$Timestamp.7z"

Write-Host "Starting backup for $DbName to $BakFile..."

# Execute SQL Backup using sqlcmd
$SqlCmd = "sqlcmd -S $DbServer -U $DbUser -P `"$DbPass`" -Q `"BACKUP DATABASE [$DbName] TO DISK = '$BakFile' WITH FORMAT, INIT;`""
Invoke-Expression $SqlCmd

if (-not (Test-Path $BakFile)) {
    Write-Error "Backup failed! .bak file not found."
    exit 1
}

Write-Host "Backup completed. Compressing with 7z..."

# Compress using 7z (High Compression, low resource: 2 threads, 32MB dict)
& $SevenZipPath a -t7z -mx=9 -mmt=2 -md=32m $ZipFile $BakFile

if (-not (Test-Path $ZipFile)) {
    Write-Error "Compression failed! .7z file not found."
    exit 1
}

Write-Host "Compression completed. Uploading to $ApiUrl..."

# Upload to API using curl.exe since Invoke-RestMethod struggles with multipart/form-data natively
$CurlCmd = "curl.exe -X POST `"$ApiUrl`" -H `"Authorization: Bearer $ApiKey`" -F `"path=$UploadPath`" -F `"file=@$ZipFile`""
Invoke-Expression $CurlCmd

Write-Host "Upload attempt finished. Cleaning up temporary files..."
Remove-Item -Force $BakFile
Remove-Item -Force $ZipFile

Write-Host "Done!"

# === Konfigurasi ===
$UploadUrl = "http://localhost:5000/upload"
$CheckUrl = "http://localhost:5000/items?path=/NewFolder"  # disesuaikan dengan folder remote
$FolderLocal = "D:\Data\"
$RemoteFolder = "/NewFolder"  # sesuai path yang dicek juga

# === Ambil file .7z terbaru ===
$latestFile = Get-ChildItem -Path $FolderLocal -Filter *.7z |
              Sort-Object LastWriteTime -Descending |
              Select-Object -First 1

if (-not $latestFile) {
    Write-Output "❌ No .7z files found in $FolderLocal"
    exit 1
}

Write-Output "📦 Latest file found: $($latestFile.Name)"

# === Cek apakah file sudah ada di server ===
try {
    $response = Invoke-RestMethod -Uri $CheckUrl -Method GET
    $exists = $response | Where-Object { $_.name -eq $latestFile.Name }

    if ($exists) {
        Write-Output "✅ File '$($latestFile.Name)' already exists on server. Skipping upload."
        exit 0
    }
} catch {
    Write-Error "⚠️ Failed to check remote items: $_"
    exit 1
}

# === Upload file pakai curl ===
$curlExe = "C:\curl\bin\curl.exe"
$localFilePath = $latestFile.FullName

Write-Output "⏫ Uploading $($latestFile.Name)..."

$curlArgs = @(
    "-X", "POST", $UploadUrl,
    "-F", "file=@$localFilePath",
    "-F", "path=$RemoteFolder"
)

& $curlExe @curlArgs

if ($LASTEXITCODE -eq 0) {
    Write-Output "✅ Upload success."
} else {
    Write-Error "❌ Upload failed with exit code $LASTEXITCODE"
    exit 1
}

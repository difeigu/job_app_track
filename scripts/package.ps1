[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$distDirectory = Join-Path $projectRoot 'dist'
$archivePath = Join-Path $distDirectory 'job_app_track-1.0.0.zip'

# Include only reviewed source files. Never copy the project directory recursively.
$publicFiles = @(
    '.gitattributes',
    '.gitignore',
    'README.md',
    'requirements.txt',
    'app.py',
    'db.py',
    'scraper.py',
    'run.bat',
    'templates/index.html',
    'static/css/style.css',
    'static/js/app.js',
    'scripts/package.ps1'
)

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
New-Item -ItemType Directory -Force -Path $distDirectory | Out-Null
$stream = [System.IO.File]::Open($archivePath, [System.IO.FileMode]::Create)
$archive = [System.IO.Compression.ZipArchive]::new(
    $stream, [System.IO.Compression.ZipArchiveMode]::Create
)
try {
    foreach ($relativePath in $publicFiles) {
        $sourcePath = Join-Path $projectRoot $relativePath
        if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
            throw "Missing package file: $relativePath"
        }
        $entryName = 'job_app_track/' + $relativePath.Replace('\', '/')
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $archive, $sourcePath, $entryName,
            [System.IO.Compression.CompressionLevel]::Optimal
        ) | Out-Null
    }
}
finally {
    $archive.Dispose()
    $stream.Dispose()
}

Write-Output "Created $archivePath ($($publicFiles.Count) source files; no database)."

<#
.SYNOPSIS
  Build the offline, one-click Aveon client deployment package.

.DESCRIPTION
  Produces deployment\out\AveonSetup\ (and AveonSetup.zip with -CreateZip):

    INSTALL.cmd / UNINSTALL.cmd / install.ps1 / install-config.psd1
    prereqs\     offline installers (VC++, Python 3.12, ODBC 18, URL Rewrite, ARR, SQL Express)
    wheels\      every backend Python package, so the client needs no internet
    sdk32\       32-bit eSSL zkemkeeper SDK
    templates\   scheduled-task XMLs + backend .env template
    app\         backend source, prebuilt frontend\dist, database\schema.sql, watchdog

  Copy the zip to the client server, extract, double-click INSTALL.cmd.

.PARAMETER DownloadPrereqs
  Download any installer missing from the cache (deployment\prereqs\). Every
  file must carry a valid Microsoft / Python Software Foundation signature.
  Only needed once; later builds reuse the cache.

.PARAMETER ExcludeSqlExpress
  Leave the ~700 MB SQL Server Express media out (package ~80 MB). Use for
  clients that already run SQL Server; the installer then requires one.

.PARAMETER Brand
  White-label name (default "Aveon Infotech"). Baked into the login page and
  browser title, used as the default organisation name, install folder
  (C:\<Brand>) and IIS site name, and names the output <Brand>Setup(.zip).

.EXAMPLE
  .\build-client-package.ps1 -DownloadPrereqs -CreateZip
.EXAMPLE
  .\build-client-package.ps1 -Brand Dotcode -CreateZip        # -> out\DotcodeSetup.zip
.EXAMPLE
  .\build-client-package.ps1 -ExcludeSqlExpress -CreateZip -OutputRoot .\out\AveonSetup-NoSQL
#>
param(
    [string] $Brand = "Aveon Infotech",
    [string] $Organization = "",     # client's organisation name (sidebar / report header); data only, not branding
    [string] $OutputRoot = "",
    [string] $PrereqCache = (Join-Path $PSScriptRoot "prereqs"),
    [switch] $DownloadPrereqs,
    [switch] $ExcludeSqlExpress,
    [switch] $CreateZip
)

$ErrorActionPreference = "Stop"
$brandSlug = ($Brand -replace '[^A-Za-z0-9]', '')
if (-not $brandSlug) { throw "Brand must contain letters or digits" }
if ($brandSlug -eq "AveonInfotech") { $brandSlug = "Aveon" }
if (-not $OutputRoot) { $OutputRoot = Join-Path $PSScriptRoot "out\${brandSlug}Setup" }
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$backendSource = Join-Path $projectRoot "backend"
$frontendSource = Join-Path $projectRoot "frontend"
$installerSource = Join-Path $PSScriptRoot "installer"
$buildPython = Join-Path $backendSource ".venv\Scripts\python.exe"   # 3.12 x64, same as the client

# Installer file name -> download source. aka.ms links are avoided (hijacked on some
# networks); VC++ and ODBC resolve their current direct URL through winget when available.
$Prereqs = [ordered]@{
    "VC_redist.x64.exe"       = @{ winget = "Microsoft.VCRedist.2015+.x64"; url = "https://aka.ms/vs/17/release/vc_redist.x64.exe" }
    "python-3.12.7-amd64.exe" = @{ url = "https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe" }
    "msodbcsql18.msi"         = @{ winget = "Microsoft.msodbcsql.18"; url = "https://go.microsoft.com/fwlink/?linkid=2280794" }
    "rewrite_amd64_en-US.msi" = @{ url = "https://download.microsoft.com/download/1/2/8/128E2E22-C1B9-44A4-BE2A-5859ED1D4592/rewrite_amd64_en-US.msi" }
    "requestRouter_amd64.msi" = @{ url = "https://download.microsoft.com/download/E/9/8/E9849D6A-020E-47E4-9FD0-A023E99B54EB/requestRouter_amd64.msi" }
    "SQLEXPR_x64_ENU.exe"     = @{ ssei = "https://go.microsoft.com/fwlink/p/?linkid=2216019" }   # SQL Server Express (fwlink serves the current release, 2025 / MSSQL17)
}

function Step([string]$msg) { Write-Host ""; Write-Host "==> $msg" -ForegroundColor Cyan }

function Copy-Tree([string]$Source, [string]$Destination, [string[]]$ExcludeDirs = @(), [string[]]$ExcludeFiles = @()) {
    $rcArgs = @($Source, $Destination, "/E", "/R:1", "/W:1", "/NFL", "/NDL", "/NJH", "/NJS", "/NP")
    if ($ExcludeDirs.Count)  { $rcArgs += "/XD"; $rcArgs += $ExcludeDirs }
    if ($ExcludeFiles.Count) { $rcArgs += "/XF"; $rcArgs += $ExcludeFiles }
    & robocopy @rcArgs | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy '$Source' -> '$Destination' failed ($LASTEXITCODE)" }
}

function Test-Signed([string]$path) {
    $sig = Get-AuthenticodeSignature $path
    return ($sig.Status -eq "Valid" -and $sig.SignerCertificate.Subject -match "Microsoft|Python Software Foundation")
}

function Get-WingetUrl([string]$id) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { return $null }
    $line = winget show --id $id --exact --accept-source-agreements 2>$null | Select-String "Installer Url:\s*(\S+)" | Select-Object -First 1
    if ($line) { return $line.Matches[0].Groups[1].Value } else { return $null }
}

# --------------------------------------------------------------------------
# 1. Prerequisite installers (cache)
# --------------------------------------------------------------------------
Step "Prerequisite installers ($PrereqCache)"
New-Item -ItemType Directory -Force $PrereqCache | Out-Null
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$missing = @()
if ($ExcludeSqlExpress) { $Prereqs.Remove("SQLEXPR_x64_ENU.exe"); Write-Host "  (SQL Server Express excluded)" }
foreach ($name in $Prereqs.Keys) {
    $target = Join-Path $PrereqCache $name
    if ((Test-Path $target) -and (Test-Signed $target)) { Write-Host "  cached  $name"; continue }
    if (Test-Path $target) { Write-Warning "$name has no valid signature - replacing"; Remove-Item $target -Force }
    if (-not $DownloadPrereqs) { $missing += $name; continue }

    $src = $Prereqs[$name]
    try {
        if ($src.ssei) {
            # SQL Express: fetch the small web bootstrapper, then let it download the offline media.
            $ssei = Join-Path $env:TEMP "SQL-SSEI-Expr.exe"
            Invoke-WebRequest -UseBasicParsing -Uri $src.ssei -OutFile $ssei
            if (-not (Test-Signed $ssei)) { throw "bootstrapper signature invalid" }
            $media = Join-Path $env:TEMP "AveonSqlMedia"
            Write-Host "  download $name (SQL Express offline media, ~250 MB)..."
            $p = Start-Process $ssei -ArgumentList "/ACTION=Download", "/MEDIAPATH=`"$media`"", "/MEDIATYPE=Core", "/QUIET" -Wait -PassThru
            $file = Get-ChildItem $media -Filter "SQLEXPR*_x64_ENU.exe" -Recurse | Select-Object -First 1
            if (-not $file) { throw "SSEI exit $($p.ExitCode), no SQLEXPR_x64_ENU.exe produced" }
            Copy-Item $file.FullName $target -Force
        } else {
            $url = $null
            if ($src.winget) { $url = Get-WingetUrl $src.winget }
            if (-not $url) { $url = $src.url }
            Write-Host "  download $name <- $url"
            Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $target
        }
        if (-not (Test-Signed $target)) { Remove-Item $target -Force; throw "downloaded file is not validly signed" }
        Write-Host "  ok      $name" -ForegroundColor Green
    } catch {
        $missing += $name
        Write-Warning "  $name : $($_.Exception.Message)"
    }
}
if ($missing.Count) {
    Write-Host ""
    Write-Host "Missing prerequisite installers in $PrereqCache :" -ForegroundColor Red
    foreach ($m in $missing) { Write-Host "  - $m   ($($Prereqs[$m].url)$($Prereqs[$m].ssei))" -ForegroundColor Red }
    throw "Re-run with -DownloadPrereqs, or download the files above manually into $PrereqCache."
}

# --------------------------------------------------------------------------
# 2. Fresh output folder
# --------------------------------------------------------------------------
Step "Output folder $OutputRoot"
if (Test-Path $OutputRoot) { Remove-Item -Recurse -Force $OutputRoot }
New-Item -ItemType Directory -Force $OutputRoot | Out-Null
$app = Join-Path $OutputRoot "app"

# --------------------------------------------------------------------------
# 3. Frontend: clean production build straight into the package
# --------------------------------------------------------------------------
Step "Building frontend (brand: $Brand)"
$distOut = Join-Path $app "frontend\dist"
Push-Location $frontendSource
$prevBrand = $env:VITE_BRAND_NAME
try {
    if (-not (Test-Path "node_modules")) { & npm.cmd install; if ($LASTEXITCODE) { throw "npm install failed" } }
    # Brand is a build-time constant in the bundle (login page, <title>, meta tags).
    $env:VITE_BRAND_NAME = $Brand
    # Separate outDir + emptyOutDir: the package never picks up stale hashed bundles
    # or IIS-managed files (aspnet_client) from the live frontend\dist.
    & npm.cmd run build -- --outDir "$distOut" --emptyOutDir
    if ($LASTEXITCODE) { throw "frontend build failed" }
} finally { $env:VITE_BRAND_NAME = $prevBrand; Pop-Location }
if (-not (Select-String -Path (Join-Path $distOut "index.html") -SimpleMatch $Brand -Quiet)) { throw "brand '$Brand' not found in built index.html" }
[IO.File]::WriteAllText((Join-Path $OutputRoot "brand.txt"), $Brand, (New-Object Text.UTF8Encoding($false)))
if ($Organization) {
    [IO.File]::WriteAllText((Join-Path $OutputRoot "organization.txt"), $Organization, (New-Object Text.UTF8Encoding($false)))
    Write-Host "  organisation: $Organization"
}
if (-not (Test-Path (Join-Path $distOut "web.config"))) { throw "web.config missing from built dist (expected from frontend\public)" }

# --------------------------------------------------------------------------
# 4. Backend source, database, watchdog
# --------------------------------------------------------------------------
Step "Copying backend, database, watchdog"
Copy-Tree $backendSource (Join-Path $app "backend") `
    -ExcludeDirs @(".venv", "venv", "__pycache__", ".pytest_cache", "snapshots") `
    -ExcludeFiles @(".env", "*.log", "backend_*.txt", "*.pyc")
Copy-Item (Join-Path $projectRoot "database\schema.sql") (New-Item -ItemType Directory -Force (Join-Path $app "database")) -Force
# Standalone empty-database script for DBAs (same schema the installer creates).
New-Item -ItemType Directory -Force (Join-Path $OutputRoot "docs") | Out-Null
& $buildPython (Join-Path $backendSource "scripts\export_empty_schema.py") --brand "$Brand" --database $brandSlug --out (Join-Path $OutputRoot "docs\${brandSlug}_EmptyDatabase.sql") | Out-Null
if ($LASTEXITCODE) { throw "export_empty_schema.py failed" }
New-Item -ItemType Directory -Force (Join-Path $app "deployment") | Out-Null
Copy-Item (Join-Path $PSScriptRoot "health-watchdog.ps1") (Join-Path $app "deployment") -Force

# --------------------------------------------------------------------------
# 5. Offline Python wheels (cp312 / win_amd64)
# --------------------------------------------------------------------------
Step "Downloading Python wheels"
if (-not (Test-Path $buildPython)) { throw "Build Python not found: $buildPython (create backend\.venv with Python 3.12 x64)" }
$wheels = Join-Path $OutputRoot "wheels"
& $buildPython -m pip download -r (Join-Path $backendSource "requirements.txt") -d $wheels `
    --only-binary=:all: --platform win_amd64 --python-version 3.12 --implementation cp --disable-pip-version-check -q
if ($LASTEXITCODE) { throw "pip download failed" }
Write-Host "  $((Get-ChildItem $wheels -Filter *.whl).Count) wheels"

# --------------------------------------------------------------------------
# 6. Installer, templates, SDK, prerequisites, docs
# --------------------------------------------------------------------------
Step "Copying installer + prerequisites"
foreach ($f in "INSTALL.cmd", "UNINSTALL.cmd", "install.ps1", "install-config.psd1", "UPDATE.cmd", "update.ps1") {
    Copy-Item (Join-Path $installerSource $f) $OutputRoot -Force
}
Copy-Tree (Join-Path $installerSource "templates") (Join-Path $OutputRoot "templates")
Copy-Tree (Join-Path $installerSource "sdk32") (Join-Path $OutputRoot "sdk32")
New-Item -ItemType Directory -Force (Join-Path $OutputRoot "prereqs") | Out-Null
foreach ($name in $Prereqs.Keys) { Copy-Item (Join-Path $PrereqCache $name) (Join-Path $OutputRoot "prereqs") -Force }
New-Item -ItemType Directory -Force (Join-Path $OutputRoot "docs") | Out-Null
# Docs: brand the product name (task/folder names are <slug>-prefixed at install time).
$steps = (Get-Content (Join-Path $PSScriptRoot "DEPLOYMENT-STEPS.md") -Raw)
if ($brandSlug -ne "Aveon") { $steps = $steps.Replace("AveonSetup", "${brandSlug}Setup").Replace("C:\Aveon", "C:\$brandSlug").Replace("Aveon", $Brand) }
[IO.File]::WriteAllText((Join-Path $OutputRoot "docs\DEPLOYMENT-STEPS.md"), $steps, (New-Object Text.UTF8Encoding($false)))
# The PDF manuals are Aveon-branded; ship them only with the Aveon package.
foreach ($doc in $(if ($brandSlug -eq "Aveon") { "Client-Installation-Manual.pdf", "User-Manual.pdf" } else { @() })) {
    $p = Join-Path $PSScriptRoot "docs\$doc"
    if (Test-Path $p) { Copy-Item $p (Join-Path $OutputRoot "docs") -Force }
}

# Sanity: nothing machine-specific may leak into the package.
$leaks = Get-ChildItem $OutputRoot -Recurse -File -Include *.ps1, *.cmd, *.xml, *.template, *.psd1 |
    Select-String -SimpleMatch "D:\ESSL\ESSL_SW" -List
if ($leaks) { $leaks | ForEach-Object { Write-Warning "hard-coded dev path: $($_.Path):$($_.LineNumber)" } }

$sizeMb = [math]::Round(((Get-ChildItem $OutputRoot -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), 1)
Write-Host ""
Write-Host "Package ready: $OutputRoot ($sizeMb MB)" -ForegroundColor Green

# --------------------------------------------------------------------------
# 7. Zip
# --------------------------------------------------------------------------
if ($CreateZip) {
    Step "Creating zip"
    $zipPath = "$OutputRoot.zip"
    if (Test-Path $zipPath) { Remove-Item -Force $zipPath }
    Compress-Archive -Path (Join-Path $OutputRoot "*") -DestinationPath $zipPath -CompressionLevel Optimal
    Write-Host "Zip ready: $zipPath ($([math]::Round((Get-Item $zipPath).Length / 1MB, 1)) MB)" -ForegroundColor Green

    # Update-only package for servers that are already installed: the code, the wheels and UPDATE.cmd
    # (no prerequisites, no SQL / IIS questions; backend\.env is kept). -> <out>\<Brand>Update.zip
    $updateZip = Join-Path (Split-Path $OutputRoot -Parent) "${brandSlug}Update.zip"
    if (Test-Path $updateZip) { Remove-Item -Force $updateZip }
    $parts = @("app", "wheels", "brand.txt", "UPDATE.cmd", "update.ps1") | ForEach-Object { Join-Path $OutputRoot $_ } | Where-Object { Test-Path $_ }
    Compress-Archive -Path $parts -DestinationPath $updateZip -CompressionLevel Optimal
    Write-Host "Update zip ready: $updateZip ($([math]::Round((Get-Item $updateZip).Length / 1MB, 1)) MB)" -ForegroundColor Green
}

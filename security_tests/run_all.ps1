# =============================================================================
# Runner PowerShell — jalankan semua test k6 berurutan
# =============================================================================
# Penggunaan:
#   .\run_all.ps1                                   # default ke localhost
#   .\run_all.ps1 -BaseUrl https://pkimm-ftik-umko.my.id
#   .\run_all.ps1 -BaseUrl https://... -SkipLoad    # skip load baseline
# =============================================================================

param(
    [string]$BaseUrl = "http://localhost:8000",
    [switch]$SkipLoad,
    [switch]$SkipChatbot
)

$ErrorActionPreference = "Continue"  # jangan stop kalau satu test gagal

# Cek k6 ada
$k6 = Get-Command k6 -ErrorAction SilentlyContinue
if (-not $k6) {
    Write-Host "ERROR: k6 tidak ditemukan di PATH." -ForegroundColor Red
    Write-Host "Install: winget install k6 --source winget" -ForegroundColor Yellow
    exit 1
}

# Pastikan folder reports ada
$reportDir = Join-Path $PSScriptRoot "reports"
if (-not (Test-Path $reportDir)) {
    New-Item -ItemType Directory -Path $reportDir | Out-Null
}

# Daftar test (urutan penting: smoke dulu)
$tests = @(
    @{ File = "00_smoke.js";                       Wajib = $true  },
    @{ File = "01_security_headers.js";            Wajib = $false },
    @{ File = "05_csrf_protection.js";             Wajib = $false },
    @{ File = "06_endpoint_enumeration.js";        Wajib = $false },
    @{ File = "02_rate_limit_login.js";            Wajib = $false },
    @{ File = "04_rate_limit_forgot_password.js";  Wajib = $false },
    @{ File = "09_open_redirect.js";               Wajib = $false },
    @{ File = "11_xss_sanitization.js";            Wajib = $false },
    @{ File = "12_sensitive_data_exposure.js";     Wajib = $false },
    @{ File = "03_rate_limit_chatbot.js";          Wajib = $false; Skip = $SkipChatbot },
    @{ File = "07_ip_spoofing.js";                 Wajib = $false; Skip = $SkipChatbot },
    @{ File = "10_rate_limit_otp.js";              Wajib = $false },
    @{ File = "08_load_baseline.js";               Wajib = $false; Skip = $SkipLoad }
)

Write-Host ""
Write-Host "================================================================"
Write-Host "  SECURITY TEST SUITE — PK IMM FTIK UMKO"
Write-Host "================================================================"
Write-Host "  Target  : $BaseUrl"
Write-Host "  Tanggal : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "  Reports : $reportDir"
Write-Host "================================================================"
Write-Host ""

$results = @()
$startAll = Get-Date

foreach ($test in $tests) {
    if ($test.Skip) {
        Write-Host "[SKIP] $($test.File)" -ForegroundColor DarkGray
        continue
    }

    $testPath = Join-Path $PSScriptRoot "tests\$($test.File)"
    $jsonOut = Join-Path $reportDir ($test.File -replace '\.js$', '.json')

    Write-Host ""
    Write-Host "----------------------------------------------------------------"
    Write-Host "[RUN] $($test.File)" -ForegroundColor Cyan
    Write-Host "----------------------------------------------------------------"

    $start = Get-Date
    & k6 run --quiet --summary-export=$jsonOut -e BASE_URL=$BaseUrl $testPath
    $exitCode = $LASTEXITCODE
    $duration = (Get-Date) - $start

    $status = if ($exitCode -eq 0) { "PASS" } else { "FAIL" }
    $color = if ($exitCode -eq 0) { "Green" } else { "Red" }
    Write-Host "[$status] $($test.File) ($([int]$duration.TotalSeconds)s)" -ForegroundColor $color

    $results += [PSCustomObject]@{
        Test = $test.File
        Status = $status
        Duration = "$([int]$duration.TotalSeconds)s"
        ExitCode = $exitCode
    }

    # Kalau smoke gagal, hentikan — sisanya tidak akan bermakna
    if ($test.Wajib -and $exitCode -ne 0) {
        Write-Host ""
        Write-Host "ERROR: Smoke test gagal — abort sisa test." -ForegroundColor Red
        Write-Host "Pastikan target $BaseUrl bisa diakses dan tidak down." -ForegroundColor Yellow
        exit 2
    }
}

$totalDuration = (Get-Date) - $startAll

Write-Host ""
Write-Host "================================================================"
Write-Host "  RINGKASAN"
Write-Host "================================================================"
$results | Format-Table -AutoSize
Write-Host "Total durasi: $([int]$totalDuration.TotalSeconds) detik"
Write-Host ""
Write-Host "Hasil JSON tersimpan di: $reportDir"
Write-Host "Salin REPORT_TEMPLATE.md → reports\REPORT_<tanggal>.md untuk dokumentasi"
Write-Host "================================================================"

# Exit code 0 kalau semua pass, non-zero kalau ada yang fail
$failed = ($results | Where-Object { $_.Status -eq "FAIL" }).Count
exit $failed

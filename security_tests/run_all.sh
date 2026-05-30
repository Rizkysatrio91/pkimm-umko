#!/usr/bin/env bash
# =============================================================================
# Runner bash — jalankan semua test k6 berurutan (Linux/macOS/WSL)
# =============================================================================
# Penggunaan:
#   ./run_all.sh                                   # default localhost
#   ./run_all.sh https://pkimm-ftik-umko.my.id
#   SKIP_LOAD=1 ./run_all.sh https://...           # skip load baseline
# =============================================================================

set -uo pipefail

BASE_URL="${1:-http://localhost:8000}"
SKIP_LOAD="${SKIP_LOAD:-0}"
SKIP_CHATBOT="${SKIP_CHATBOT:-0}"

# Cek k6 ada
if ! command -v k6 >/dev/null 2>&1; then
    echo "ERROR: k6 tidak ditemukan di PATH."
    echo "Install: https://k6.io/docs/get-started/installation/"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPORT_DIR="$SCRIPT_DIR/reports"
mkdir -p "$REPORT_DIR"

# Daftar test (urutan penting: smoke dulu)
declare -a TESTS=(
    "00_smoke.js|wajib"
    "01_security_headers.js"
    "05_csrf_protection.js"
    "06_endpoint_enumeration.js"
    "02_rate_limit_login.js"
    "04_rate_limit_forgot_password.js"
    "09_open_redirect.js"
    "11_xss_sanitization.js"
    "12_sensitive_data_exposure.js"
    "03_rate_limit_chatbot.js|chatbot"
    "07_ip_spoofing.js|chatbot"
    "10_rate_limit_otp.js"
    "08_load_baseline.js|load"
)

cat <<EOF

================================================================
  SECURITY TEST SUITE — PK IMM FTIK UMKO
================================================================
  Target  : $BASE_URL
  Tanggal : $(date '+%Y-%m-%d %H:%M:%S')
  Reports : $REPORT_DIR
================================================================
EOF

START_ALL=$(date +%s)
declare -a RESULTS=()
FAIL_COUNT=0

for entry in "${TESTS[@]}"; do
    test_file="${entry%%|*}"
    flag=""
    [[ "$entry" == *"|"* ]] && flag="${entry##*|}"

    if [[ "$flag" == "load" && "$SKIP_LOAD" == "1" ]]; then
        echo "[SKIP] $test_file"
        continue
    fi
    if [[ "$flag" == "chatbot" && "$SKIP_CHATBOT" == "1" ]]; then
        echo "[SKIP] $test_file"
        continue
    fi

    test_path="$SCRIPT_DIR/tests/$test_file"
    json_out="$REPORT_DIR/${test_file%.js}.json"

    echo
    echo "----------------------------------------------------------------"
    echo "[RUN] $test_file"
    echo "----------------------------------------------------------------"

    start=$(date +%s)
    k6 run --quiet --summary-export="$json_out" -e BASE_URL="$BASE_URL" "$test_path"
    exit_code=$?
    duration=$(( $(date +%s) - start ))

    if [[ $exit_code -eq 0 ]]; then
        echo "[PASS] $test_file (${duration}s)"
        RESULTS+=("PASS  $test_file  ${duration}s")
    else
        echo "[FAIL] $test_file (${duration}s)"
        RESULTS+=("FAIL  $test_file  ${duration}s")
        FAIL_COUNT=$((FAIL_COUNT + 1))

        if [[ "$flag" == "wajib" ]]; then
            echo
            echo "ERROR: Smoke test gagal — abort sisa test."
            echo "Pastikan target $BASE_URL bisa diakses dan tidak down."
            exit 2
        fi
    fi
done

TOTAL_DURATION=$(( $(date +%s) - START_ALL ))

cat <<EOF

================================================================
  RINGKASAN
================================================================
EOF
for r in "${RESULTS[@]}"; do
    echo "  $r"
done
echo
echo "Total durasi: ${TOTAL_DURATION} detik"
echo
echo "Hasil JSON tersimpan di: $REPORT_DIR"
echo "Salin REPORT_TEMPLATE.md → reports/REPORT_<tanggal>.md untuk dokumentasi"
echo "================================================================"

exit $FAIL_COUNT

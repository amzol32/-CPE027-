#!/usr/bin/env bash
# Creates the GitHub repo, labels, milestones and issues for the remaining iterations, then pushes.
# Usage: bash scripts/bootstrap_github.sh <owner>/<repo> [--public]
# Needs the GitHub CLI logged in (gh auth login). Review the issue list below before running.
set -euo pipefail

REPO="${1:?usage: bootstrap_github.sh <owner>/<repo> [--public]}"
VIS="--private"; [[ "${2:-}" == "--public" ]] && VIS="--public"

command -v gh >/dev/null || { echo "install the GitHub CLI first: https://cli.github.com"; exit 1; }
gh auth status >/dev/null || { echo "run: gh auth login"; exit 1; }

if ! gh repo view "$REPO" >/dev/null 2>&1; then
  gh repo create "$REPO" $VIS --source=. --remote=origin --description "Median + EMA smoothing of 3 capacitive soil-moisture sensors (ESP32-S3)"
fi
git push -u origin main --tags

for l in "firmware:0e8a16" "analysis:1d76db" "hardware:fbca04" "report:d93f0b" "test-data:5319e7"; do
  gh label create "${l%%:*}" --color "${l##*:}" --repo "$REPO" 2>/dev/null || true
done

mk() { gh api "repos/$REPO/milestones" -f title="$1" -f description="$2" >/dev/null 2>&1 || true; }
mk "v0.5 Hardware bring-up" "Firmware flashed, 3 sensors reading, calibrated"
mk "v0.6 Evidence"          "Tests 2-4 logged and analysed"
mk "v1.0 Report freeze"     "Report and slides filled from measured data"

iss() { gh issue create --repo "$REPO" --title "$1" --body "$2" --label "$3" --milestone "$4" >/dev/null && echo "created: $1"; }

M5="v0.5 Hardware bring-up"; M6="v0.6 Evidence"; M10="v1.0 Report freeze"
iss "Set breadboard PSU to 5 V and verify rails" "Schematic note says 6 V. Set 5 V, measure 5 V and 3.3 V rails with a multimeter, add flyback diode and bulk capacitor at the pump." hardware "$M5"
iss "Flash soil_dsp.ino and confirm 3 sensors + TFT + dashboard" "Install esp32 core 3.x and Adafruit GFX/ST7789. Confirm all three ADC channels move when a probe is wetted. Note the dashboard URL." firmware "$M5"
iss "Test 1: calibrate (60 s air, 60 s water)" "Press d then w, log both runs, run analyze_log.py calib, commit data/runs/<date>-calib and calibration.json. Probes at the same depth." test-data "$M5"
iss "Set thresholds from calibration readings in the germination medium" "theta_dry, h, theta_wet, Tmax, lockout, blanking. Record the values; they go in report section IV.E." hardware "$M5"
iss "Test 2: steady state, >= 30 min, pump disabled" "Log, run analyze_log.py steady, commit logs + results tables/figures." test-data "$M6"
iss "Test 3: step response" "Record the exact t_s when water is added and the volume. Run analyze_log.py step." test-data "$M6"
iss "Test 4: pump interference with and without blanking" "Pump into a separate cup so probes do not get wetter. Press t. Run analyze_log.py pump with blanking on/off in the script." test-data "$M6"
iss "Fill Tables 6-1 to 6-3 and Section VI from results/" "Use docs/PAPER_PATCHES.md. Only measured values." report "$M10"
iss "Update abstract RESULTS SENTENCE and Conclusion" "Do not claim improvements Tables 6-2 and 6-3 do not show." report "$M10"
iss "Update slides to the three-sensor version" "Text in docs/WORKFLOW.md." report "$M10"
iss "Fix cross-document inconsistencies" "List in docs/PAPER_PATCHES.md section 5." report "$M10"
echo "done"

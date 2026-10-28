# Iteration plan and GitHub process

## Branches and review

- `main` always builds: CI runs `make test` and compiles the firmware for `esp32:esp32:esp32s3`.
- Work on `feat/<topic>` or `fix/<topic>`, open a pull request, merge when CI is green. One teammate reviews; the reviewer runs `make test` locally for firmware changes.
- Tag each finished iteration `v0.x`. The final report version is `v1.0.0`.
- Measurement logs that the report depends on are committed under `data/runs/<date>-<test>/` together with the `calibration.json` and the firmware commit hash that produced them. That is the evidence trail for every number.
- Never commit `secrets.h` (git-ignored).

## Iterations

| Tag | Milestone | Deliverable | Done when |
|---|---|---|---|
| v0.1 | Baseline read-out | `firmware/legacy_readout`: three sensors on the TFT, relay test | Your original sketch (done) |
| v0.2 | DSP core | `dsp.h` + unit tests | `make unit` passes (done) |
| v0.3 | Analysis tooling | `analyze_log.py`, `dsp_ref.py`, crosscheck, synthetic data | `make synth crosscheck` passes (done) |
| v0.4 | Firmware pipeline + dashboard | `soil_dsp.ino`, `dashboard.h`, host simulation | `make sim` passes (done); compiles in CI |
| v0.5 | Hardware bring-up | Firmware flashed; all three sensors reading; calibrated; dashboard loads | Test 1 log + `calibration.json` committed |
| v0.6 | Evidence | Tests 2, 3, 4 logged and analysed | `results/` tables and figures generated from real logs |
| v1.0 | Report freeze | Report filled from `results/`, slides updated | Every `[ ]` filled from a measured number; no synthetic data quoted |

## Risk list (check at each iteration)

| Risk | Mitigation |
|---|---|
| Pump glitches reach the ADC | Flyback diode, bulk capacitor, blanking, running median; Test 4 measures it. Best fix: separate pump supply |
| A probe not fully in air or water during calibration | Firmware refuses to unlock the pump if a span is under 300 counts; `calib` warns |
| Three probes see different moisture (placement) | Same depth, spaced at least 3 cm; note placement in the report |
| Thresholds not tuned to the medium | Set them from calibration readings in the actual medium before Test 4 and the regulation tests |
| Logging gaps | The analysis script warns when the median sample interval is not 1 s |

## Creating the repository

```bash
# from the project root, after `gh auth login`
bash scripts/bootstrap_github.sh <github-user-or-org>/<repo-name>
```

It creates the repository, labels, milestones and the issues for iterations v0.5 to v1.0, and pushes `main` with the tags. The local history already contains iterations v0.1 to v0.4.

To do it by hand: create an empty repository on GitHub, then

```bash
git remote add origin git@github.com:<user>/<repo>.git
git push -u origin main --tags
```

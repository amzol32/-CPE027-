#!/usr/bin/env python3
"""Prove the firmware DSP (firmware/soil_dsp/dsp.h) and the analysis script (dsp_ref.py) agree.

Compiles tests/test_dsp.cpp, runs its `dump` mode on a log, and compares every stage
(m1..m3, x, z, y, yma) with the numpy reference. Exit code 1 on mismatch.

    python3 analysis/crosscheck.py --log data/synthetic/synthetic_steady.csv --cal data/synthetic/calibration.json
"""
import argparse
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import dsp_ref as D  # noqa: E402
from analyze_log import load_cal, load_log  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True)
    ap.add_argument("--cal", required=True)
    ap.add_argument("--tol", type=float, default=2e-3)
    a = ap.parse_args()

    exe = os.path.join(ROOT, "build", "test_dsp")
    os.makedirs(os.path.dirname(exe), exist_ok=True)
    subprocess.check_call(["g++", "-std=c++17", "-O2", "-I", os.path.join(ROOT, "firmware", "soil_dsp"),
                           os.path.join(ROOT, "tests", "test_dsp.cpp"), "-o", exe])
    cal = load_cal(a.cal)
    args = [exe, "dump", a.log]
    for i in range(3):
        args += [str(cal["adry"][i]), str(cal["awet"][i])]
    args.append(str(cal["alpha"]))
    out = subprocess.check_output(args, text=True).strip().splitlines()
    fw = np.array([[float(v) for v in line.split(",")] for line in out[1:]])

    t, adc, pump = load_log(a.log)
    ref = D.pipeline(adc, cal["adry"], cal["awet"], alpha=cal["alpha"], n_med=5, m_ma=10)
    pairs = {"m1": (fw[:, 1], ref["m"][0]), "m2": (fw[:, 2], ref["m"][1]), "m3": (fw[:, 3], ref["m"][2]),
             "x": (fw[:, 4], ref["x"]), "z": (fw[:, 5], ref["z"]), "y": (fw[:, 6], ref["y"]),
             "yma": (fw[:, 7], ref["yma"])}
    ok = True
    for k, (f, r) in pairs.items():
        err = float(np.max(np.abs(f - r)))
        flag = "ok" if err <= a.tol else "MISMATCH"
        ok &= err <= a.tol
        print(f"{k:4s} max|firmware - python| = {err:.2e}  {flag}")
    print("firmware DSP and analysis script AGREE" if ok else "firmware DSP and analysis script DIFFER")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

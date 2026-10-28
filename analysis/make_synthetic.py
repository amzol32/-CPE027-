#!/usr/bin/env python3
"""Generate SYNTHETIC logs so analyze_log.py can be exercised before real data exists.

These files are NOT measurements. Never put numbers from them in the report.
They follow the signal model of the report, x_i[n] = s[n] + d_i + v_i[n] + p_i[n]:
  - slow true moisture s[n]
  - per-sensor offset d_i (different dry/wet counts for each sensor)
  - white noise v_i[n]
  - impulsive interference p_i[n] (random single-sensor spikes; pump-switch
    disturbances that hit all three sensors)
"""
import argparse
import json
import os

import numpy as np

# Illustrative ADC counts only (v1.2 reads differently from the two v2.0 boards).
CAL = {"adry": [2950.0, 2780.0, 2810.0], "awet": [1250.0, 1180.0, 1210.0]}


def idx_to_adc(idx, i):
    return CAL["adry"][i] - idx / 100.0 * (CAL["adry"][i] - CAL["awet"][i])


def write_log(path, t, idx, pump):
    adc = np.vstack([idx_to_adc(idx[i], i) for i in range(3)])
    adc = np.rint(adc)
    with open(path, "w") as f:
        f.write("t_s,s1,s2,s3,pump\n")
        for n in range(len(t)):
            f.write(f"{t[n]:.3f},{int(adc[0, n])},{int(adc[1, n])},{int(adc[2, n])},{int(pump[n])}\n")


def noisy(rng, s, sigma, spike_p=0.0, spike_h=15.0):
    n = len(s)
    out = []
    for i in range(3):
        v = rng.normal(0, sigma[i], n)
        p = np.zeros(n)
        hit = rng.random(n) < spike_p
        p[hit] = rng.choice([-1, 1], hit.sum()) * spike_h * (0.5 + rng.random(hit.sum()))
        out.append(s + v + p)
    return np.vstack(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/synthetic")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    rng = np.random.default_rng(a.seed)
    sigma = [1.6, 1.1, 1.3]
    zero = lambda n: np.zeros(n, int)

    # calibration logs: 60 s air, 60 s water
    t = np.arange(60.0)
    # in calibration the indices are by definition 0/100; add a little count noise instead
    for name, base in (("air", 0.0), ("water", 100.0)):
        idx = np.vstack([np.full(60, base) for _ in range(3)])
        adc = np.vstack([idx_to_adc(idx[i], i) + rng.normal(0, 6, 60) for i in range(3)])
        with open(os.path.join(a.out, f"synthetic_calib_{name}.csv"), "w") as f:
            f.write("t_s,s1,s2,s3,pump\n")
            for n in range(60):
                f.write(f"{t[n]:.3f},{int(round(adc[0, n]))},{int(round(adc[1, n]))},{int(round(adc[2, n]))},0\n")

    # steady state: 40 min, true moisture hovering near 36 (close to a dry threshold of 35)
    n = 40 * 60
    t = np.arange(float(n))
    s = 36.0 + 0.8 * np.sin(2 * np.pi * t / 1500.0)
    idx = noisy(rng, s, sigma, spike_p=0.004)
    write_log(os.path.join(a.out, "synthetic_steady.csv"), t, idx, zero(n))

    # step: 5 min dry (25), water added at t=300 s, first-order rise to 62 with tau=40 s (plus 8 s delay)
    n = 15 * 60
    t = np.arange(float(n))
    s = np.where(t < 308, 25.0, 25.0 + (62.0 - 25.0) * (1 - np.exp(-(t - 308) / 40.0)))
    idx = noisy(rng, s, sigma, spike_p=0.002)
    write_log(os.path.join(a.out, "synthetic_step.csv"), t, idx, zero(n))

    # pump interference: 12 cycles of 6 s on / 14 s off; all sensors disturbed for ~2 s after each switch
    n = 5 * 60
    t = np.arange(float(n))
    pump = np.zeros(n, int)
    for c in range(12):
        pump[20 + c * 20: 26 + c * 20] = 1
    s = np.full(n, 45.0)
    idx = noisy(rng, s, sigma, spike_p=0.0)
    trans = np.nonzero(pump[1:] != pump[:-1])[0] + 1
    for k in trans:
        for d, h in ((0, 0.0), (1, 22.0), (2, 9.0)):
            if k + d < n and d > 0:
                idx[:, k + d] += h * np.array([1.0, 0.8, 1.2]) * rng.choice([-1, 1])
    write_log(os.path.join(a.out, "synthetic_pump.csv"), t, idx, pump)

    with open(os.path.join(a.out, "SYNTHETIC_README.txt"), "w") as f:
        f.write("These CSV files are simulated to exercise the analysis script. They are NOT measurements.\n")
    print("wrote synthetic logs to", a.out)


if __name__ == "__main__":
    main()

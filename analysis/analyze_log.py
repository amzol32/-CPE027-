#!/usr/bin/env python3
"""analyze_log.py - fills Tables 6-1, 6-2, 6-3 and the pump-interference result.

Input logs are the CSV written by the firmware over serial:
    t_s,s1,s2,s3,pump          (raw 12-bit ADC counts, relay state 0/1)

Sub-commands
  calib   Test 1: adry / awet per sensor from an air log and a water log -> calibration.json, Table 6-1
  steady  Test 2: std, peak-to-peak, spikes, toggles, spectrum -> Table 6-2, Fig 6-1, Fig 6-2
  step    Test 3: 90% response time (t90) -> Table 6-3, step_response.png
  pump    Test 4: spikes during relay switching, with and without blanking

Every number printed is computed from the log you pass in; nothing is estimated.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dsp_ref as D  # noqa: E402

NAMES = {
    "raw1": "Raw (sensor 1)",
    "x": "Cross-sensor median",
    "yma": "Moving average (M = {M})",
    "yma_extra": "Moving average (M = {Mx}, same noise gain as EMA)",
    "y": "Median + EMA (proposed)",
}


# --------------------------------------------------------------------------- io
def load_log(path):
    rows = []
    with open(path, "r", errors="ignore") as f:
        for line in f:
            parts = line.strip().split(",")
            if len(parts) < 4:
                continue
            try:
                vals = [float(p) for p in parts[:5]]
            except ValueError:
                continue  # header, comments or serial-monitor text
            if len(vals) == 4:
                vals.append(0.0)
            rows.append(vals)
    if len(rows) < 10:
        sys.exit(f"{path}: fewer than 10 numeric rows - is this the right file?")
    a = np.array(rows)
    t, adc, pump = a[:, 0], a[:, 1:4].T, a[:, 4].astype(int)
    dt = np.diff(t)
    if np.median(dt) > 0 and (abs(np.median(dt) - 1.0) > 0.05 or dt.max() > 2.5):
        print(f"WARNING {path}: expected 1 Hz; median dt={np.median(dt):.3f}s, max gap={dt.max():.1f}s. "
              "Spectrum and response times assume uniform 1 Hz sampling.", file=sys.stderr)
    return t, adc, pump


def load_cal(path):
    with open(path) as f:
        c = json.load(f)
    c.setdefault("alpha", 0.1)
    c.setdefault("N", 5)
    c.setdefault("M", 10)
    c.setdefault("theta_dry", 35.0)
    c.setdefault("blank_s", 3.0)
    return c


# --------------------------------------------------------------------- measures
def spike_count(s, thr):
    """Samples that deviate from the centred 5-point median of the SAME signal by more than thr.
    The same absolute threshold (index units) is used for every signal so counts are comparable."""
    s = np.asarray(s, float)
    n = len(s)
    c = 0
    for i in range(n):
        w = s[max(0, i - 2): min(n, i + 3)]
        if abs(s[i] - np.median(w)) > thr:
            c += 1
    return int(c)


def toggles(s, thr):
    """Number of times the decision (s >= thr) changes. Plain crossing count, no hysteresis."""
    b = np.asarray(s) >= thr
    return int(np.count_nonzero(b[1:] != b[:-1]))


def signal_stats(s, thr, spike_thr):
    s = np.asarray(s, float)
    return {
        "std": float(np.std(s, ddof=1)),
        "p2p": float(np.ptp(s)),
        "spikes": spike_count(s, spike_thr),
        "toggles": toggles(s, thr),
        "mean": float(np.mean(s)),
    }


def t90(t, s, t_step, pre, tail, hold=5):
    """90% response time after t_step. Baseline = mean of the `pre` s before the step, final = mean of the last
    `tail` s. The 90% level must be reached and held for `hold` consecutive samples, so noise crossing the
    level early does not count."""
    t = np.asarray(t, float)
    s = np.asarray(s, float)
    base = s[(t >= t_step - pre) & (t < t_step)].mean()
    final = s[t >= t[-1] - tail].mean()
    level = base + 0.9 * (final - base)
    sign = 1.0 if final >= base else -1.0
    ok = sign * (s - level) >= 0
    idx = np.nonzero(t >= t_step)[0]
    for i in idx:
        if i + hold <= len(s) and ok[i:i + hold].all():
            return float(t[i] - t_step), float(base), float(final)
    return float("nan"), float(base), float(final)


# ---------------------------------------------------------------------- spectrum
def welch(x, seg=256, fs=1.0):
    x = np.asarray(x, float)
    x = x - x.mean()
    if len(x) < 2 * seg:
        seg = max(32, 2 ** int(np.floor(np.log2(max(len(x) // 2, 32)))))
    step = seg // 2
    w = np.hanning(seg)
    acc, cnt = None, 0
    for i in range(0, len(x) - seg + 1, step):
        seg_x = x[i:i + seg] - x[i:i + seg].mean()
        X = np.abs(np.fft.rfft(seg_x * w)) / (w.sum() / 2.0)  # amplitude in index units
        acc = X ** 2 if acc is None else acc + X ** 2
        cnt += 1
    f = np.fft.rfftfreq(seg, 1.0 / fs)
    return f, np.sqrt(acc / cnt)


# ------------------------------------------------------------------------ helpers
def run_pipeline(t, adc, pump, cal, blank=True):
    return D.pipeline(adc, cal["adry"], cal["awet"], alpha=cal["alpha"], n_med=cal["N"], m_ma=cal["M"],
                      m_ma_extra=cal.get("M_extra", 19), t=t, pump=pump,
                      blank_s=cal["blank_s"] if blank else 0.0)


def label(key, cal):
    return NAMES[key].format(M=cal["M"], Mx=cal.get("M_extra", 19))


def fmt(v, nd=2):
    return "n/a" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v:.{nd}f}"


def get_plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"figure.dpi": 130, "axes.grid": True, "grid.alpha": 0.3, "font.size": 9})
    return plt


# ------------------------------------------------------------------------ commands
def cmd_calib(a):
    out = {"adry": [], "awet": []}
    ta, aa, _ = load_log(a.air)
    tw, aw, _ = load_log(a.water)
    keep_a, keep_w = ta >= ta[0] + a.skip, tw >= tw[0] + a.skip
    lines = ["Table 6-1. Calibration Reference Readings (ADC counts)",
             "| Sensor | adry (air) | awet (water) | Span (adry - awet) | std air | std water |",
             "|---|---|---|---|---|---|"]
    for i in range(3):
        d, w = aa[i][keep_a], aw[i][keep_w]
        out["adry"].append(round(float(d.mean()), 1))
        out["awet"].append(round(float(w.mean()), 1))
        lines.append(f"| {i + 1} | {d.mean():.1f} | {w.mean():.1f} | {d.mean() - w.mean():.1f} | {d.std(ddof=1):.1f} | {w.std(ddof=1):.1f} |")
    spans = [d - w for d, w in zip(out["adry"], out["awet"])]
    lines.append("")
    lines.append(f"Spread between sensors: adry range {max(out['adry']) - min(out['adry']):.1f} counts, "
                 f"awet range {max(out['awet']) - min(out['awet']):.1f} counts, span range {max(spans) - min(spans):.1f} counts "
                 f"({100 * (max(spans) - min(spans)) / np.mean(spans):.1f}% of mean span).")
    if min(spans) < 300:
        lines.append("WARNING: a span below ~300 counts means that probe was not fully in air / water - recalibrate it.")
    out.update({"alpha": a.alpha, "N": 5, "M": a.M, "M_extra": a.M_extra, "theta_dry": a.theta_dry, "blank_s": a.blank})
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    with open(a.out, "w") as f:
        json.dump(out, f, indent=2)
    print("\n".join(lines))
    print(f"\nwrote {a.out}")
    print("Firmware: type 'cal' commands or paste these into secrets/Calibration if you override them:")
    print("  adry =", out["adry"], " awet =", out["awet"])


def cmd_steady(a):
    cal = load_cal(a.cal)
    t, adc, pump = load_log(a.log)
    if pump.any():
        print("WARNING: pump was ON during the steady-state log; Test 2 requires the pump disabled.", file=sys.stderr)
    r = run_pipeline(t, adc, pump, cal, blank=False)
    sigs = {"raw1": r["m"][0], "x": r["x"], "yma": r["yma"], "yma_extra": r["yma_extra"], "y": r["y"]}
    keep = t >= t[0] + a.warmup
    if a.theta == "median":
        theta = float(np.median(r["x"][keep]))
        theta_note = "median of the cross-sensor signal (worst case: the signal hovers on the threshold)"
    else:
        theta = float(a.theta)
        theta_note = "user-specified"
    res = {"theta": theta, "theta_note": theta_note, "spike_thr": a.spike_thr, "warmup_s": a.warmup,
           "duration_min": float((t[keep][-1] - t[keep][0]) / 60.0), "n_samples": int(keep.sum()), "signals": {}}
    for k, s in sigs.items():
        res["signals"][k] = signal_stats(s[keep], theta, a.spike_thr)
    # individual raw sensors for the narrative
    res["raw_per_sensor_std"] = [float(np.std(r["m"][i][keep], ddof=1)) for i in range(3)]
    raw, prop, ma = res["signals"]["raw1"], res["signals"]["y"], res["signals"]["yma"]
    res["std_reduction_pct_vs_raw1"] = 100.0 * (1 - prop["std"] / raw["std"])
    res["std_reduction_pct_ma_vs_raw1"] = 100.0 * (1 - ma["std"] / raw["std"])
    res["theory"] = {"ema_noise_gain": D.ema_noise_gain(cal["alpha"]), "ma_noise_gain": 1 / np.sqrt(cal["M"]),
                     "ema_time_constant_s": D.ema_time_constant(cal["alpha"]),
                     "ema_equiv_ma_length": (2 - cal["alpha"]) / cal["alpha"]}

    # ---- tables
    L = ["Table 6-2. Steady-State Signal Quality (Test 2, moisture index units)",
         f"(window: {res['duration_min']:.1f} min after a {a.warmup:.0f} s warm-up; spike threshold {a.spike_thr} index units; "
         f"toggle threshold θ = {theta:.2f}, {theta_note})",
         "| Signal | Std. dev. | Peak-to-peak | Spikes | Toggles at θ |", "|---|---|---|---|---|"]
    for k in ("raw1", "x", "yma", "y", "yma_extra"):
        s = res["signals"][k]
        extra = " [extra row]" if k == "yma_extra" else ""
        L.append(f"| {label(k, cal)}{extra} | {s['std']:.3f} | {s['p2p']:.2f} | {s['spikes']} | {s['toggles']} |")
    L += ["", f"Std. dev. reduction, raw sensor 1 -> proposed: {res['std_reduction_pct_vs_raw1']:.1f}%",
          f"Std. dev. reduction, raw sensor 1 -> moving average: {res['std_reduction_pct_ma_vs_raw1']:.1f}%",
          f"Raw std per sensor: " + ", ".join(f"S{i + 1}={v:.3f}" for i, v in enumerate(res["raw_per_sensor_std"])),
          f"Theory for white noise: EMA alpha={cal['alpha']} -> noise std x{res['theory']['ema_noise_gain']:.3f}, "
          f"time constant {res['theory']['ema_time_constant_s']:.1f} s, equal-noise MA length {res['theory']['ema_equiv_ma_length']:.0f}; "
          f"MA M={cal['M']} -> noise std x{res['theory']['ma_noise_gain']:.3f}. "
          "Measured values above this theory mean the noise is not white (slow drift is not removed by smoothing)."]
    text = "\n".join(L)
    print(text)

    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "steady_results.json"), "w") as f:
        json.dump(res, f, indent=2)
    with open(os.path.join(a.out, "table_6-2.md"), "w") as f:
        f.write(text + "\n")

    # ---- Fig 6-1 time series
    plt = get_plt()
    fig, ax = plt.subplots(figsize=(9, 3.8))
    ax.plot(t[keep] / 60, sigs["raw1"][keep], color="#bbbbbb", lw=0.8, label=label("raw1", cal))
    ax.plot(t[keep] / 60, sigs["x"][keep], color="#5a7fb5", lw=0.9, label=label("x", cal))
    ax.plot(t[keep] / 60, sigs["yma"][keep], color="#d28a2c", lw=1.2, label=label("yma", cal))
    ax.plot(t[keep] / 60, sigs["y"][keep], color="#2e7d32", lw=1.6, label=label("y", cal))
    ax.axhline(theta, color="k", ls="--", lw=0.8, label=f"θ = {theta:.1f}")
    ax.set_xlabel("Time (min)")
    ax.set_ylabel("Moisture index")
    ax.set_title("Raw and smoothed moisture index under steady conditions")
    ax.legend(ncol=3, fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.2))
    fig.tight_layout()
    fig.savefig(os.path.join(a.out, "steady_timeseries.png"), bbox_inches="tight")
    plt.close(fig)

    # ---- Fig 6-2 spectrum
    fig, ax = plt.subplots(figsize=(7.5, 4))
    for k, c in (("raw1", "#999999"), ("x", "#5a7fb5"), ("yma", "#d28a2c"), ("y", "#2e7d32")):
        f_, P = welch(sigs[k][keep])
        ax.semilogy(f_[1:], P[1:], color=c, lw=1.2, label=label(k, cal))
    ax.set_xlabel("Frequency (Hz)   [fs = 1 Hz, Nyquist = 0.5 Hz]")
    ax.set_ylabel("Amplitude (index units)")
    ax.set_title("Magnitude spectrum before and after smoothing (Welch, Hann window)")
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(os.path.join(a.out, "steady_spectrum.png"), bbox_inches="tight")
    plt.close(fig)

    # ---- extra: theoretical filter responses
    f = np.linspace(0, 0.5, 500)
    fig, ax = plt.subplots(figsize=(7.5, 4))
    ax.plot(f, D.ema_response(cal["alpha"], f), color="#2e7d32", label=f"EMA α = {cal['alpha']}")
    ax.plot(f, D.ma_response(cal["M"], f), color="#d28a2c", label=f"Moving average M = {cal['M']}")
    ax.plot(f, D.ma_response(cal.get("M_extra", 19), f), color="#d28a2c", ls=":", label=f"Moving average M = {cal.get('M_extra', 19)}")
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel("|H(f)|")
    ax.set_title("Theoretical magnitude responses of the linear smoothing stages")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(a.out, "filter_responses.png"), bbox_inches="tight")
    plt.close(fig)
    print(f"\nwrote steady_results.json, table_6-2.md, steady_timeseries.png, steady_spectrum.png, filter_responses.png to {a.out}")


def cmd_step(a):
    cal = load_cal(a.cal)
    t, adc, pump = load_log(a.log)
    r = run_pipeline(t, adc, pump, cal, blank=False)
    sigs = {"raw1": r["m"][0], "yma": r["yma"], "y": r["y"], "yma_extra": r["yma_extra"], "x": r["x"]}
    res = {"t_step_s": a.t_step, "signals": {}}
    L = ["Table 6-3. Step Response (Test 3)",
         f"(water added at t = {a.t_step:.1f} s; baseline = {a.pre:.0f} s before; final = last {a.tail:.0f} s; 90% level must hold {a.hold} samples)",
         "| Signal | t90 (s) | baseline | final |", "|---|---|---|---|"]
    for k in ("raw1", "yma", "y", "yma_extra", "x"):
        v, b, fnl = t90(t, sigs[k], a.t_step, a.pre, a.tail, a.hold)
        res["signals"][k] = {"t90_s": v, "baseline": b, "final": fnl}
        tag = " [extra row]" if k in ("yma_extra", "x") else ""
        L.append(f"| {label(k, cal)}{tag} | {fmt(v, 1)} | {b:.2f} | {fnl:.2f} |")
    d = res["signals"]["y"]["t90_s"] - res["signals"]["raw1"]["t90_s"]
    res["added_delay_vs_raw_s"] = None if np.isnan(d) else float(d)
    L.append("")
    L.append("Added response time, proposed vs raw sensor 1: " + (fmt(d, 1) + " s" if not np.isnan(d) else "n/a (a signal never reached 90%)"))
    L.append("Note: raw t90 includes the true water-spreading time of the medium; the filter adds delay on top of that.")
    text = "\n".join(L)
    print(text)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "step_results.json"), "w") as f:
        json.dump(res, f, indent=2)
    with open(os.path.join(a.out, "table_6-3.md"), "w") as f:
        f.write(text + "\n")
    plt = get_plt()
    fig, ax = plt.subplots(figsize=(9, 3.8))
    lo, hi = a.t_step - a.pre, min(t[-1], a.t_step + a.window)
    m = (t >= lo) & (t <= hi)
    ax.plot(t[m] - a.t_step, sigs["raw1"][m], color="#bbbbbb", lw=0.8, label=label("raw1", cal))
    ax.plot(t[m] - a.t_step, sigs["yma"][m], color="#d28a2c", lw=1.2, label=label("yma", cal))
    ax.plot(t[m] - a.t_step, sigs["y"][m], color="#2e7d32", lw=1.6, label=label("y", cal))
    ax.axvline(0, color="k", ls="--", lw=0.8)
    ax.set_xlabel("Time since water was added (s)")
    ax.set_ylabel("Moisture index")
    ax.set_title("Step response")
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(os.path.join(a.out, "step_response.png"), bbox_inches="tight")
    plt.close(fig)
    print(f"\nwrote step_results.json, table_6-3.md, step_response.png to {a.out}")


def cmd_pump(a):
    cal = load_cal(a.cal)
    t, adc, pump = load_log(a.log)
    trans = D.pump_transitions(pump)
    if len(trans) == 0:
        sys.exit("No relay transitions in this log (pump column never changes).")
    nob = run_pipeline(t, adc, pump, cal, blank=False)
    blk = run_pipeline(t, adc, pump, cal, blank=True)
    sigs = {
        "Raw sensor 1": nob["m"][0], "Raw sensor 2": nob["m"][1], "Raw sensor 3": nob["m"][2],
        "Cross-sensor median (no blanking)": nob["x"],
        "Proposed y (no blanking)": nob["y"],
        "Cross-sensor median (with blanking)": blk["x"],
        "Proposed y (with blanking)": blk["y"],
    }
    res = {"transitions": int(len(trans)), "window_s": a.window, "spike_thr": a.spike_thr, "rows": {}}
    L = ["Test 4. Pump interference",
         f"({len(trans)} relay transitions; a sample counts if it deviates from the median of the {a.ref} samples before the switch "
         f"by more than {a.spike_thr} index units, within {a.window:.0f} s after the switch; blanking = {cal['blank_s']} s)",
         "| Signal | Spiked samples | Max deviation |", "|---|---|---|"]
    for name, s in sigs.items():
        cnt, mx = 0, 0.0
        for k in trans:
            if k < a.ref:
                continue
            ref = np.median(s[k - a.ref:k])
            j = k + 1
            while j < len(t) and t[j] - t[k] <= a.window:
                dev = abs(s[j] - ref)
                mx = max(mx, dev)
                cnt += dev > a.spike_thr
                j += 1
        res["rows"][name] = {"spiked_samples": int(cnt), "max_dev": float(mx)}
        L.append(f"| {name} | {int(cnt)} | {mx:.2f} |")
    text = "\n".join(L)
    print(text)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "pump_results.json"), "w") as f:
        json.dump(res, f, indent=2)
    with open(os.path.join(a.out, "table_pump.md"), "w") as f:
        f.write(text + "\n")
    plt = get_plt()
    fig, ax = plt.subplots(figsize=(9, 3.8))
    ax.plot(t / 60, nob["m"][0], color="#bbbbbb", lw=0.8, label="Raw sensor 1")
    ax.plot(t / 60, nob["y"], color="#c0392b", lw=1.2, label="Proposed, no blanking")
    ax.plot(t / 60, blk["y"], color="#2e7d32", lw=1.5, label="Proposed, with blanking")
    ax.fill_between(t / 60, 0, 1, where=pump > 0, transform=ax.get_xaxis_transform(), color="#5a7fb5", alpha=0.15, label="Pump ON")
    ax.set_xlabel("Time (min)")
    ax.set_ylabel("Moisture index")
    ax.set_title("Pump-switching interference")
    ax.legend(fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(os.path.join(a.out, "pump_interference.png"), bbox_inches="tight")
    plt.close(fig)
    print(f"\nwrote pump_results.json, table_pump.md, pump_interference.png to {a.out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)

    c = sp.add_parser("calib", help="Test 1")
    c.add_argument("--air", required=True)
    c.add_argument("--water", required=True)
    c.add_argument("--out", default="data/calibration.json")
    c.add_argument("--skip", type=float, default=5.0, help="seconds to drop at the start of each log")
    c.add_argument("--alpha", type=float, default=0.1)
    c.add_argument("--M", type=int, default=10)
    c.add_argument("--M-extra", dest="M_extra", type=int, default=19)
    c.add_argument("--theta-dry", dest="theta_dry", type=float, default=35.0)
    c.add_argument("--blank", type=float, default=3.0)
    c.set_defaults(fn=cmd_calib)

    s = sp.add_parser("steady", help="Test 2")
    s.add_argument("--log", required=True)
    s.add_argument("--cal", default="data/calibration.json")
    s.add_argument("--out", default="results")
    s.add_argument("--theta", default="median", help="toggle threshold: a number, or 'median' (default)")
    s.add_argument("--spike-thr", dest="spike_thr", type=float, default=5.0)
    s.add_argument("--warmup", type=float, default=60.0)
    s.set_defaults(fn=cmd_steady)

    p = sp.add_parser("step", help="Test 3")
    p.add_argument("--log", required=True)
    p.add_argument("--cal", default="data/calibration.json")
    p.add_argument("--out", default="results")
    p.add_argument("--t-step", dest="t_step", type=float, required=True, help="time (t_s) water was added")
    p.add_argument("--pre", type=float, default=60.0)
    p.add_argument("--tail", type=float, default=120.0)
    p.add_argument("--hold", type=int, default=5)
    p.add_argument("--window", type=float, default=600.0, help="plot window after the step (s)")
    p.set_defaults(fn=cmd_step)

    q = sp.add_parser("pump", help="Test 4")
    q.add_argument("--log", required=True)
    q.add_argument("--cal", default="data/calibration.json")
    q.add_argument("--out", default="results")
    q.add_argument("--spike-thr", dest="spike_thr", type=float, default=5.0)
    q.add_argument("--window", type=float, default=5.0)
    q.add_argument("--ref", type=int, default=10)
    q.set_defaults(fn=cmd_pump)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()

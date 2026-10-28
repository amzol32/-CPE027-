"""Reference (numpy/python) implementation of the pipeline in firmware/soil_dsp/dsp.h.

analyze_log.py uses these so the numbers in the report come from exactly the
same filter definitions as the firmware. analysis/crosscheck.py proves it by
running the C++ dsp.h and this module on the same log and comparing outputs.
"""
from __future__ import annotations

import numpy as np


def to_index(adc, adry, awet):
    """Eq. (2): relative moisture index 0..100 (clamped)."""
    span = max(float(adry) - float(awet), 1.0)
    return np.clip(100.0 * (float(adry) - np.asarray(adc, float)) / span, 0.0, 100.0)


def median3(m):
    """Eq. (3): cross-sensor median. m has shape (3, n)."""
    return np.median(np.asarray(m, float), axis=0)


def running_median(x, n=5):
    """Eq. (4). Until the window fills, uses sorted(window)[len//2] (matches dsp.h)."""
    x = np.asarray(x, float)
    out = np.empty_like(x)
    for i in range(len(x)):
        w = sorted(x[max(0, i - n + 1): i + 1])
        out[i] = w[len(w) // 2]
    return out


def ema(x, alpha=0.1):
    """Eq. (5). Seeded with the first sample (no startup ramp), as in dsp.h."""
    x = np.asarray(x, float)
    y = np.empty_like(x)
    y[0] = x[0]
    for i in range(1, len(x)):
        y[i] = alpha * x[i] + (1.0 - alpha) * y[i - 1]
    return y


def moving_average(x, m=10):
    """Eq. (6). Expanding window until M samples are available (matches dsp.h)."""
    x = np.asarray(x, float)
    c = np.cumsum(np.insert(x, 0, 0.0))
    out = np.empty_like(x)
    for i in range(len(x)):
        lo = max(0, i - m + 1)
        out[i] = (c[i + 1] - c[lo]) / (i + 1 - lo)
    return out


def pump_transitions(pump):
    """Indices k where the relay state differs from sample k-1."""
    p = np.asarray(pump, int)
    return np.nonzero(p[1:] != p[:-1])[0] + 1


def apply_blanking(m, t, pump, blank_s):
    """Firmware blanking: after a relay switch logged at tick k, readings taken
    in the following blank_s seconds (strictly after k) are replaced by the last
    valid value. m has shape (3, n); returns a copy."""
    m = np.array(m, float)
    if blank_s <= 0:
        return m
    t = np.asarray(t, float)
    n = m.shape[1]
    blank = np.zeros(n, bool)
    for k in pump_transitions(pump):
        # samples strictly after the switch tick, within blank_s of it
        j = k + 1
        while j < n and (t[j] - t[k]) < blank_s - 1e-6:
            blank[j] = True
            j += 1
    out = m.copy()
    last_valid = m[:, 0].copy()
    for i in range(n):
        if blank[i]:
            out[:, i] = last_valid
        else:
            last_valid = m[:, i].copy()
    return out


def pipeline(adc, adry, awet, alpha=0.1, n_med=5, m_ma=10, m_ma_extra=None,
             t=None, pump=None, blank_s=0.0):
    """Run the full chain. adc has shape (3, n) of raw ADC counts.

    Returns dict with calibrated indices (m), blanked indices (mb), x, z, y,
    yma and optionally yma_extra.
    """
    adc = np.asarray(adc, float)
    m = np.vstack([to_index(adc[i], adry[i], awet[i]) for i in range(3)])
    mb = apply_blanking(m, t, pump, blank_s) if (blank_s > 0 and t is not None and pump is not None) else m
    x = median3(mb)
    z = running_median(x, n_med)
    y = ema(z, alpha)
    out = {"m": m, "mb": mb, "x": x, "z": z, "y": y, "yma": moving_average(x, m_ma)}
    if m_ma_extra:
        out["yma_extra"] = moving_average(x, m_ma_extra)
    return out


# ---- theory helpers (for the frequency-response figure) ----
def ema_response(alpha, f, fs=1.0):
    w = 2 * np.pi * np.asarray(f) / fs
    return np.abs(alpha / (1.0 - (1.0 - alpha) * np.exp(-1j * w)))


def ma_response(m, f, fs=1.0):
    w = 2 * np.pi * np.asarray(f) / fs
    with np.errstate(divide="ignore", invalid="ignore"):
        h = np.abs(np.sin(m * w / 2) / (m * np.sin(w / 2)))
    h[np.asarray(w) == 0] = 1.0
    return h


def ema_noise_gain(alpha):
    """Std of white noise after the EMA relative to its input: sqrt(a/(2-a))."""
    return float(np.sqrt(alpha / (2.0 - alpha)))


def ema_time_constant(alpha):
    """-1/ln(1-alpha) samples."""
    return float(-1.0 / np.log(1.0 - alpha))

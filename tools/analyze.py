"""Turn a logged CSV into the wiki figure + numbers for that test.

Usage:
    python tools/analyze.py T0 data/T0_20261003_0930.csv
    python tools/analyze.py C3 data/C3_*.csv        # several files are concatenated

Figures go to figures/, numbers to results/summary.json (one entry per test).
Which register is wetness and which is temperature is set in tools/config.json.
"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
CFG = json.load(open(os.path.join(ROOT, "tools", "config.json")))
FIG = os.path.join(ROOT, "figures")
RES = os.path.join(ROOT, "results", "summary.json")

BLUE, GREEN, GRAY, ORANGE = "#0071e3", "#34c759", "#86868b", "#ff9500"
plt.rcParams.update({
    "font.family": ["Helvetica Neue", "Arial", "PingFang TC", "sans-serif"],
    "font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
    "axes.edgecolor": "#d2d2d7", "axes.grid": True, "grid.color": "#f0f0f2",
    "figure.dpi": 150, "savefig.bbox": "tight",
})


def load(paths):
    frames = []
    for i, p in enumerate(paths):
        d = pd.read_csv(p, keep_default_na=True)
        d["file"] = i
        frames.append(d)
    d = pd.concat(frames, ignore_index=True)
    d["time"] = pd.to_datetime(d["host_time"])
    d["marker"] = d["marker"].fillna("").astype(str).str.strip()
    d["wet"] = d[CFG["wet_register"]]
    d["leaf_t"] = d[CFG["temp_register"]]
    d.loc[d["ok"] != 1, ["wet", "leaf_t"]] = np.nan
    d["td"] = dewpoint(d["sht_t"], d["sht_rh"])
    d["min"] = (d["time"] - d["time"].iloc[0]).dt.total_seconds() / 60
    return d


def dewpoint(t, rh):
    a, b = 17.62, 243.12  # Magnus, over water
    g = np.log(np.clip(rh, 1, 100) / 100) + a * t / (b + t)
    return b * g / (a - g)


def save(fig, name):
    os.makedirs(FIG, exist_ok=True)
    out = os.path.join(FIG, name)
    fig.savefig(out)
    print("figure ->", out)


def record(test, numbers):
    os.makedirs(os.path.dirname(RES), exist_ok=True)
    allres = json.load(open(RES)) if os.path.exists(RES) else {}
    allres[test] = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in numbers.items()}
    json.dump(allres, open(RES, "w"), indent=2, ensure_ascii=False)
    for k, v in allres[test].items():
        print(f"  {k:28s} {v}")


def marker_rows(d, prefix):
    return d[d["marker"].str.lower().str.startswith(prefix)]


# ---------- T0: side by side at room conditions ----------
def t0(d):
    diff = d["leaf_t"] - d["sht_t"]
    fig, ax = plt.subplots(1, 3, figsize=(13, 3.4))
    ax[0].plot(d["min"], d["sht_t"], color=GRAY, label="SHT air T")
    ax[0].plot(d["min"], d["leaf_t"], color=BLUE, label="leaf sensor T")
    ax[0].set(xlabel="minutes", ylabel="°C", title="Temperature, side by side"); ax[0].legend(frameon=False)
    ax[1].plot(d["min"], d["wet"], color=GREEN)
    ax[1].set(xlabel="minutes", ylabel="wetness reading", title="Wetness reading (dry sensor)")
    m = (d["leaf_t"] + d["sht_t"]) / 2
    bias, sd = diff.mean(), diff.std()
    ax[2].scatter(m, diff, s=6, color=BLUE, alpha=.5)
    for y, ls in [(bias, "-"), (bias + 1.96 * sd, "--"), (bias - 1.96 * sd, "--")]:
        ax[2].axhline(y, color=GRAY, ls=ls, lw=1)
    ax[2].set(xlabel="mean of the two (°C)", ylabel="leaf − SHT (°C)", title="Bland–Altman")
    save(fig, "T0_side_by_side.png")
    record("T0", {"minutes": float(d["min"].iloc[-1]), "read_success_pct": float(100 * (d["ok"] == 1).mean()),
                  "temp_bias_C": float(bias), "temp_LoA_C": float(1.96 * sd),
                  "wet_noise_SD": float(d["wet"].std()), "wet_dry_mean": float(d["wet"].mean())})


# ---------- C1: humidifier chamber, leaf kept dry ----------
def c1(d):
    fog = marker_rows(d, "fog")
    fig, ax = plt.subplots(1, 2, figsize=(11, 3.6))
    ax[0].plot(d["min"], d["sht_rh"], color=GRAY, label="SHT RH %")
    ax[0].plot(d["min"], d["wet"], color=GREEN, label="leaf wetness reading")
    for t in fog["min"]:
        ax[0].axvline(t, color=ORANGE, ls="--", lw=1)
    ax[0].set(xlabel="minutes", title="Humidity ramp"); ax[0].legend(frameon=False)
    sc = ax[1].scatter(d["sht_rh"], d["wet"], c=d["min"], s=8, cmap="Blues")
    ax[1].set(xlabel="reference RH (%)", ylabel="wetness reading", title="Does humid air alone read as wet?")
    plt.colorbar(sc, ax=ax[1], label="minutes")
    save(fig, "C1_humidity_cross_sensitivity.png")
    before = d if fog.empty else d[d["min"] < fog["min"].iloc[0]]
    base = d[d["sht_rh"] < 70]["wet"]
    out = {"rh_max": float(d["sht_rh"].max()),
           "wet_at_rh_below_70": float(base.mean()) if len(base) else None}
    for lo in (80, 90, 95):
        s = before[before["sht_rh"] >= lo]["wet"]
        out[f"wet_max_dry_leaf_rh_ge_{lo}"] = float(s.max()) if len(s) else None
    record("C1", out)


# ---------- C2: droplet dose response ----------
def c2(d):
    marks = d[d["marker"] != ""].index.tolist() + [d.index[-1] + 1]
    rows = []
    for i, j in zip(marks[:-1], marks[1:]):
        m = d.loc[i, "marker"].lower().split()
        if m[0] != "dose":
            continue
        seg = d.loc[i:j - 1]
        seg = seg[seg["time"] >= seg["time"].iloc[-1] - pd.Timedelta(seconds=30)]
        rows.append({"dose": float(m[1]), "wet": seg["wet"].median()})
    r = pd.DataFrame(rows)
    if r.empty:
        sys.exit("No 'dose X' markers found. Type e.g. 'dose 0', 'dose 2' while logging.")
    g = r.groupby("dose")["wet"].agg(["mean", "std", "count"]).reset_index()
    fig, ax = plt.subplots(figsize=(5, 3.6))
    ax.scatter(r["dose"], r["wet"], color=GRAY, s=14, alpha=.6, label="single run")
    ax.errorbar(g["dose"], g["mean"], yerr=g["std"].fillna(0), color=GREEN, marker="o", capsize=3, label="mean ± SD")
    ax.set(xlabel=f"water applied ({CFG['dose_unit']})", ylabel="wetness reading", title="Wetness vs water applied")
    ax.legend(frameon=False)
    save(fig, "C2_dose_response.png")
    g.to_csv(os.path.join(ROOT, "results", "C2_dose_table.csv"), index=False)
    sat = g.loc[g["mean"] >= 0.95 * g["mean"].max(), "dose"].min()
    record("C2", {"n_doses": int(len(g)), "reps_min": int(g["count"].min()),
                  "dry_reading": float(g["mean"].iloc[0]), "max_reading": float(g["mean"].max()),
                  "dose_reaching_95pct_of_max": float(sat), "mean_rep_SD": float(g["std"].mean())})


# ---------- C3: dry-down, threshold and time constant ----------
def c3(d):
    starts = marker_rows(d, "wet").index.tolist()
    if not starts:
        sys.exit("No 'wet' markers found.")
    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    th, t_vis, t50 = [], [], []
    for k, s in enumerate(starts):
        end = starts[k + 1] if k + 1 < len(starts) else d.index[-1] + 1
        run = d.loc[s:end - 1].copy()
        run["t"] = (run["time"] - run["time"].iloc[0]).dt.total_seconds() / 60
        w0, wb = run["wet"].iloc[:5].max(), run["wet"].iloc[-10:].median()
        half = run[run["wet"] <= wb + (w0 - wb) / 2]
        if len(half):
            t50.append(half["t"].iloc[0])
        dry = run[run["marker"].str.lower().str.startswith("dry")]
        ax.plot(run["t"], run["wet"], lw=1.4, label=f"run {k + 1}")
        if len(dry):
            th.append(dry["wet"].iloc[0]); t_vis.append(dry["t"].iloc[0])
            ax.scatter(dry["t"], dry["wet"], color="black", zorder=3, s=18)
    if th:
        ax.axhline(np.mean(th), color=ORANGE, ls="--", lw=1.2, label=f"threshold ≈ {np.mean(th):.1f}")
    ax.set(xlabel="minutes after wetting", ylabel="wetness reading",
           title="Dry-down (● = looks dry by eye)")
    ax.legend(frameon=False, fontsize=8)
    save(fig, "C3_drydown_threshold.png")
    record("C3", {"runs": len(starts), "threshold_mean": float(np.mean(th)) if th else None,
                  "threshold_SD": float(np.std(th, ddof=1)) if len(th) > 1 else None,
                  "visual_dry_min_mean": float(np.mean(t_vis)) if t_vis else None,
                  "half_drying_min_mean": float(np.mean(t50)) if t50 else None})
    if th:
        print(f"\n>> put \"wet_threshold\": {np.mean(th):.1f} into tools/config.json before analysing C4")


# ---------- C4: cold-sensor dew test ----------
def c4(d):
    th = CFG["wet_threshold"]
    out = marker_rows(d, "out")
    t0_ = out["min"].iloc[0] if len(out) else 0
    e = d[d["min"] >= t0_].copy()
    e["below_td"] = e["leaf_t"] < e["td"]
    e["is_wet"] = e["wet"] > th
    fig, ax = plt.subplots(2, 1, figsize=(8, 5), sharex=True)
    ax[0].plot(e["min"], e["leaf_t"], color=BLUE, label="leaf sensor T")
    ax[0].plot(e["min"], e["td"], color=ORANGE, label="dew point of room air (SHT)")
    ax[0].fill_between(e["min"], 0, 1, where=e["below_td"].values, transform=ax[0].get_xaxis_transform(),
                       color=ORANGE, alpha=.12, label="sensor colder than dew point")
    ax[0].set(ylabel="°C", title="Dew physics check"); ax[0].legend(frameon=False, fontsize=8)
    ax[1].plot(e["min"], e["wet"], color=GREEN)
    ax[1].axhline(th, color=GRAY, ls="--", lw=1)
    ax[1].set(xlabel="minutes", ylabel="wetness reading")
    save(fig, "C4_dew_test.png")

    def first(mask):
        s = e.loc[mask, "min"]
        return float(s.iloc[0]) if len(s) else None
    def last(mask):
        s = e.loc[mask, "min"]
        return float(s.iloc[-1]) if len(s) else None
    agree = float(100 * (e["below_td"] == e["is_wet"]).mean())
    res = {"threshold_used": th, "cold_until_min": last(e["below_td"]), "wet_from_min": first(e["is_wet"]),
           "wet_until_min": last(e["is_wet"]), "pct_samples_agree": agree}
    if res["cold_until_min"] is not None and res["wet_until_min"] is not None:
        res["dry_lag_after_crossing_td_min"] = res["wet_until_min"] - res["cold_until_min"]
    record("C4", res)


# ---------- T5: overnight stability ----------
def t5(d):
    hours = d["min"].iloc[-1] / 60
    expected = d["min"].iloc[-1] * 60 / (CFG["overnight_sample_s"]) + 1
    slope = np.polyfit(d["min"][d["wet"].notna()] / 60, d["wet"].dropna(), 1)[0]
    fig, ax = plt.subplots(2, 1, figsize=(8, 4.6), sharex=True)
    ax[0].plot(d["min"] / 60, d["sht_t"], color=GRAY, label="SHT")
    ax[0].plot(d["min"] / 60, d["leaf_t"], color=BLUE, label="leaf sensor")
    ax[0].set(ylabel="°C", title="Overnight stability"); ax[0].legend(frameon=False)
    ax[1].plot(d["min"] / 60, d["wet"], color=GREEN)
    ax[1].set(xlabel="hours", ylabel="wetness reading")
    save(fig, "T5_overnight.png")
    record("T5", {"hours": float(hours), "uptime_pct": float(min(100, 100 * (d["ok"] == 1).sum() / expected)),
                  "wet_drift_per_h": float(slope), "temp_bias_C": float((d["leaf_t"] - d["sht_t"]).mean())})


TESTS = {"T0": t0, "C1": c1, "C2": c2, "C3": c3, "C4": c4, "T5": t5}

if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in TESTS:
        sys.exit(__doc__)
    TESTS[sys.argv[1]](load(sys.argv[2:]))

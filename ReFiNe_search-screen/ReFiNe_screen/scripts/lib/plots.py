"""Performance figures for ReFiNe_screen runs (static PNGs, matplotlib).

Read the report CSVs written by s4b / s4a; never touch artifacts or the LLM.
Every figure answers one question in its title and puts the numbers on the marks:

  abstract_overview[_group].png  Where did the papers go? (kept / dropped per human outcome)
                                 How accurate was each check? (sensitivity & specificity, 95% CI)
  fulltext_overview.png          How well does each criterion agree with humans? (95% CI)
                                 Why do they disagree? (disagreement types per criterion)
  compare_abstract[_group].png   Did a new prompt help? (headline metrics across runs)

Palette: validated reference palette (dataviz skill), light mode.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e4e3df"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"   # categorical slots 1-3 (validated)
NEUTRAL = "#b9b7ae"                                     # "dropped" / "not found" (not a series hue)
GOOD, CRITICAL = "#0ca30c", "#d03b3b"                   # status: always with icon + words


def _mpl():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2,
        "ytick.color": INK, "axes.titlesize": 11.5, "axes.titleweight": "bold", "axes.titlecolor": INK,
        "axes.titlelocation": "left", "axes.titlepad": 10, "font.family": "DejaVu Sans",
    })
    return plt


def _read(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _f(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return math.nan


def _i(x) -> int:
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return 0


def _clean_axes(ax, xlabel: str | None = None) -> None:
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(axis="y", length=0)
    ax.tick_params(axis="x", colors=INK2)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    if xlabel:
        ax.set_xlabel(xlabel, color=INK2)


def _dot_ci_panel(ax, rows: list[tuple[str, list[tuple[str, float, float, float, str]]]], title: str,
                  target: float | None = None, series: list[tuple[str, str, str]] = ()) -> None:
    """Dot + 95% CI per row and series; numbers in a text column right of the plot.

    rows:   [(row label, [(series name, est, lo, hi, extra_text), ...])], values in 0..1
    series: [(series name, colour, short label for the number column), ...]
    """
    n_series = max(1, len(series))
    offsets = [0.0] if n_series == 1 else [(0.14 - 0.28 * k / (n_series - 1)) for k in range(n_series)]
    colors = {name: c for name, c, _ in series}
    shorts = {name: sh for name, _, sh in series}
    for r, (label, vals) in enumerate(rows):
        y = len(rows) - 1 - r
        parts = []
        for k, (sname, est, lo, hi, extra) in enumerate(vals):
            yy = y + offsets[k % len(offsets)]
            c = colors.get(sname, BLUE)
            short = shorts.get(sname, "")
            if math.isnan(est):
                parts.append(f"{short} n/e".strip())
                continue
            if not math.isnan(lo):
                ax.plot([lo * 100, hi * 100], [yy, yy], color=c, linewidth=2, solid_capstyle="round", alpha=0.5)
            ax.plot(est * 100, yy, "o", color=c, markersize=8, markeredgecolor=SURFACE, markeredgewidth=1.5,
                    zorder=3, clip_on=False)
            parts.append(f"{short} {est * 100:.0f}%{extra}".strip())
        ax.text(104, y, "  ·  ".join(parts), va="center", ha="left", fontsize=9, color=INK, clip_on=False)
    ax.set_yticks([len(rows) - 1 - r for r in range(len(rows))], [lab for lab, _ in rows])
    ax.set_ylim(-0.6, len(rows) - 0.4)
    ax.set_xlim(0, 100)
    ax.set_xticks(range(0, 101, 20), [f"{v}%" for v in range(0, 101, 20)])
    if target is not None:
        ax.axvline(target * 100, color=INK2, linewidth=1, linestyle=(0, (4, 3)), zorder=1)
    _clean_axes(ax, "estimate (dot) with 95% confidence interval (line)")
    ax.set_title(title, pad=30 if len(series) > 1 else 12)
    if len(series) > 1:
        from matplotlib.lines import Line2D
        handles = [Line2D([], [], marker="o", linestyle="", color=c, markersize=7, label=n) for n, c, _ in series]
        ax.legend(handles=handles, loc="lower left", bbox_to_anchor=(-0.01, 1.0), ncol=len(series), frameon=False,
                  fontsize=8.5, handletextpad=0.3, columnspacing=1.2, borderaxespad=0.2)


# ---------------------------------------------------------------------------
# Abstract stage
# ---------------------------------------------------------------------------

def plot_abstract(reports_dir: Path, group: str | None = None, run_name: str = "",
                  recall_target: float = 0.95) -> Path:
    plt = _mpl()
    sfx = f"_{group}" if group else ""
    m = {r["target"]: r for r in _read(reports_dir / f"abstract_metrics{sfx}.csv")}
    elig, incl = m["decision vs human-eligible"], m["decision vs human-included"]

    # human outcome categories (included ⊂ eligible)
    inc_k, inc_d = _i(incl["tp"]), _i(incl["fn"])
    el_k, el_d = _i(elig["tp"]) - inc_k, _i(elig["fn"]) - inc_d
    ne_k, ne_d = _i(elig["fp"]), _i(elig["tn"])
    n = _i(elig["n"])
    kept = inc_k + el_k + ne_k
    cats = [("Finally included\nby humans", inc_k, inc_d, "lost"),
            ("Passed humans' first checks,\nnot finally included", el_k, el_d, "dropped"),
            ("Rejected by humans", ne_k, ne_d, "dropped")]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 4.9), gridspec_kw={"width_ratios": [1, 1], "wspace": 0.62})
    # --- panel 1: where did the papers go -------------------------------------------
    for r, (label, k, d, word) in enumerate(cats):
        y = len(cats) - 1 - r
        tot = k + d
        ax1.barh(y, k, color=BLUE, height=0.55, edgecolor=SURFACE, linewidth=2)
        ax1.barh(y, d, left=k, color=NEUTRAL, height=0.55, edgecolor=SURFACE, linewidth=2)
        if k:
            ax1.text(k / 2, y, f"{k}", ha="center", va="center", color="white", fontsize=9.5, fontweight="bold")
        if d:
            ax1.text(k + d / 2, y, f"{d}", ha="center", va="center", color=INK, fontsize=9.5, fontweight="bold")
        if r == 0:
            ok = d == 0
            msg = f"{'✓' if ok else '✗'} {d} of {tot} lost ({100 * d / tot:.0f}%)" if tot else "no papers"
            ax1.text(tot + max(n, 1) * 0.015, y, msg, va="center", fontsize=9.5, fontweight="bold",
                     color=GOOD if ok else CRITICAL)
        else:
            ax1.text(tot + max(n, 1) * 0.015, y, f"{100 * k / tot:.0f}% kept" if tot else "", va="center",
                     fontsize=9, color=INK2)
    ax1.set_yticks(range(len(cats)), [c[0] for c in reversed(cats)])
    ax1.set_xlim(0, max(c[1] + c[2] for c in cats) * 1.32 + 1)
    _clean_axes(ax1, "papers")
    from matplotlib.patches import Patch
    ax1.legend(handles=[Patch(color=BLUE, label="kept for full text"), Patch(color=NEUTRAL, label="dropped")],
               loc="lower left", bbox_to_anchor=(-0.01, 1.0), ncol=2, frameon=False, fontsize=8.5, borderaxespad=0.2)
    ax1.set_title(f"Where did the {n} papers go?  Kept {kept} ({100 * kept / n:.0f}%)" if n else "No papers", pad=30)

    # --- panel 2: accuracy of each check --------------------------------------------
    def sv(r, metric):
        return (_f(r.get(metric)), _f(r.get(f"{metric}_lo")), _f(r.get(f"{metric}_hi")))

    rows = []
    for label, r in (("Overall vs finally included", incl), ("Overall vs passed first checks", elig)):
        se, sp = sv(r, "sensitivity"), sv(r, "specificity")
        rows.append((label, [("sensitivity (kept when humans said yes)", *se, ""),
                             ("specificity (dropped when humans said no)", *sp, "")]))
    for t, r in m.items():
        if t.startswith("gate:"):
            gid = t[5:].split(" (")[0]
            proxy = "proxy" in t
            se, sp = sv(r, "sensitivity"), sv(r, "specificity")
            rows.append((f"Gate: {gid}" + ("*" if proxy else ""),
                         [("sensitivity (kept when humans said yes)", *se, ""),
                          ("specificity (dropped when humans said no)", *(sp if not proxy else (math.nan,) * 3), "")]))
    _dot_ci_panel(ax2, rows, "How accurate was each check?", target=recall_target,
                  series=[("sensitivity (kept when humans said yes)", BLUE, "sens"),
                          ("specificity (dropped when humans said no)", ORANGE, "spec")])
    ax2.axhline(len(rows) - 2.5, color=GRID, linewidth=1)

    head = f"Abstract screening — run {run_name}" + (f", {group} split" if group else "")
    fig.suptitle(head, x=0.01, ha="left", fontsize=13, fontweight="bold", color=INK, y=1.08)
    fig.text(0.01, -0.06, f"Dashed line = {recall_target * 100:.0f}% sensitivity target.  "
             "* proxy reference with no human 'no' cases: only sensitivity can be estimated (n/e = not estimable).  "
             "'Overall' rows judge the final keep/drop decision.", fontsize=8, color=INK2)
    out = reports_dir / "figures" / f"abstract_overview{sfx}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_compare_abstract(runs: list[tuple[str, Path]], group: str | None = None, out_path: Path | None = None) -> Path:
    """Headline abstract metrics across runs (e.g. prompt v2 vs v3 on the same split)."""
    plt = _mpl()
    sfx = f"_{group}" if group else ""
    colors = [BLUE, ORANGE, AQUA]
    if len(runs) > 3:
        raise ValueError("compare at most 3 runs per figure (colour-safe limit)")
    metrics = [("Included papers kept\n(sensitivity, must stay ~100%)", "decision vs human-included", "sensitivity"),
               ("First-check papers kept\n(sensitivity)", "decision vs human-eligible", "sensitivity"),
               ("Rejected papers dropped\n(specificity)", "decision vs human-eligible", "specificity"),
               ("Kept papers that humans\nfinally included (precision)", "decision vs human-included", "ppv")]
    data = {}
    for name, rdir in runs:
        data[name] = {t["target"]: t for t in _read(rdir / f"abstract_metrics{sfx}.csv")}
    from metrics import wilson
    rows = []
    for label, target, metric in metrics:
        rows.append((label, [(name, _f(data[name][target][metric]), _f(data[name][target][f"{metric}_lo"]),
                              _f(data[name][target][f"{metric}_hi"]), "") for name, _ in runs]))
    keep = []
    for name, _ in runs:
        r = data[name]["decision vs human-eligible"]
        k, n = _i(r["tp"]) + _i(r["fp"]), _i(r["n"])
        lo, hi = wilson(k, n)
        keep.append((name, k / n if n else math.nan, lo, hi, f" ({k}/{n})"))
    rows.append(("Papers sent to full text\n(workload — lower is cheaper)", keep))
    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    _dot_ci_panel(ax, rows, "Did the new prompt help?" + (f"  ({group} split)" if group else ""),
                  series=[(name, colors[k], name) for k, (name, _) in enumerate(runs)])
    out = out_path or (runs[-1][1] / "figures" / f"compare_abstract{sfx}.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# Full-text stage
# ---------------------------------------------------------------------------

DISAGREE_TYPES = [  # (label, colour, test(human, llm))
    ("LLM: not reported (n/a), humans gave a score", NEUTRAL, lambda h, l: l == "n/a" and h in ("1", "0")),
    ("LLM said no, humans yes", ORANGE, lambda h, l: h == "1" and l == "0"),
    ("LLM said yes, humans no", BLUE, lambda h, l: h == "0" and l == "1"),
    ("Humans n/a, LLM gave a score", AQUA, lambda h, l: h == "n/a" and l in ("1", "0")),
]


def plot_fulltext(report_dir: Path, run_name: str = "") -> Path:
    plt = _mpl()
    agr = _read(report_dir / "agreement.csv")
    dis = _read(report_dir / "disagreements.csv")
    agr.sort(key=lambda r: _f(r["agree"]))                       # worst first (top)
    crits = [r["criterion"] for r in agr]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 0.42 * len(crits) + 2.4), sharey=False,
                                   gridspec_kw={"width_ratios": [1, 1.1], "wspace": 0.75})
    rows = [(r["criterion"], [("agreement", _f(r["agree"]), _f(r["agree_lo"]), _f(r["agree_hi"]),
                               f"   κ {_f(r['kappa_3class']):.2f}" if not math.isnan(_f(r["kappa_3class"])) else "   κ n/e"
                               )]) for r in agr]
    _dot_ci_panel(ax1, rows, "How often does the LLM agree with humans?", series=[("agreement", BLUE, "")])
    total_agree = sum(_i(r["n_agree"]) for r in agr)
    total_n = sum(_i(r["n_scored"]) for r in agr)

    # --- panel 2: why they disagree ------------------------------------------------
    counts = {c: [0] * len(DISAGREE_TYPES) for c in crits}
    for d in dis:
        for k, (_, _, test) in enumerate(DISAGREE_TYPES):
            if d["criterion"] in counts and test(d["human"], d["llm"]):
                counts[d["criterion"]][k] += 1
                break
    ys = {c: len(crits) - 1 - i for i, c in enumerate(crits)}
    for c in crits:
        left = 0
        for k, (lab, col, _) in enumerate(DISAGREE_TYPES):
            v = counts[c][k]
            if v:
                ax2.barh(ys[c], v, left=left, color=col, height=0.6, edgecolor=SURFACE, linewidth=2)
                if v >= 2:
                    ax2.text(left + v / 2, ys[c], str(v), ha="center", va="center", fontsize=8.5,
                             color="white" if col in (BLUE, ORANGE) else INK)
                left += v
        n_scored = next(_i(r["n_scored"]) for r in agr if r["criterion"] == c)
        ax2.text(left + 0.4, ys[c], f"{left} of {n_scored}", va="center", fontsize=8.5, color=INK2)
    ax2.set_yticks([ys[c] for c in crits], crits)
    ax2.set_ylim(-0.7, len(crits) - 0.3)
    mx = max((sum(v) for v in counts.values()), default=1)
    ax2.set_xlim(0, mx * 1.25 + 1)
    _clean_axes(ax2, "disagreements (papers)")
    from matplotlib.patches import Patch
    ax2.legend(handles=[Patch(color=col, label=lab) for lab, col, _ in DISAGREE_TYPES], loc="lower left",
               bbox_to_anchor=(-0.01, 1.0), ncol=2, frameon=False, fontsize=8.5, borderaxespad=0.2)
    ax2.set_title("Why do they disagree?", pad=48)
    ax1.set_title("How often does the LLM agree with humans?", pad=48)
    ax2.legend_.set_bbox_to_anchor((-0.01, 1.0))

    fig.suptitle(f"Full-text screening — run {run_name}:  {total_agree}/{total_n} ratings agree "
                 f"({100 * total_agree / total_n:.0f}%)" if total_n else "Full-text screening",
                 x=0.01, ha="left", fontsize=13, fontweight="bold", color=INK, y=1.07)
    fig.text(0.01, -0.03, "Agreement over 1 / 0 / n/a (κ = Cohen's kappa); criteria sorted worst first. Grey 'not reported' "
             "bars usually mean the detail is missing from the converted text (supplements, tables, cited protocols).",
             fontsize=8, color=INK2)
    out = report_dir / "figures" / "fulltext_overview.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out


def safe_plot(fn, *args, **kwargs) -> Path | None:
    """Run a plot function without ever failing the calling stage."""
    try:
        out = fn(*args, **kwargs)
        print(f"figure -> {out}")
        return out
    except ImportError:
        print("[warn] matplotlib not installed — skipping figures (pip install matplotlib)")
    except Exception as exc:  # noqa: BLE001 — figures are a convenience; never break a report
        print(f"[warn] figure failed: {exc}")
    return None


# ---------------------------------------------------------------------------
# End-to-end pipeline
# ---------------------------------------------------------------------------

FATES = [  # (key, legend label, colour)
    ("dropped_abstract", "dropped at abstract", "#8f8d86"),
    ("no_fulltext", "no full text (not downloaded / not rated)", "#d9d8d2"),
    ("excluded_fulltext", "excluded at full text", ORANGE),
    ("included", "included by the pipeline", BLUE),
]


def plot_pipeline(reports_dir: Path, run_name: str = "") -> Path:
    """Fate of reference-positive and -negative papers through the whole pipeline."""
    plt = _mpl()
    fates = _read(reports_dir / "pipeline_fates.csv")          # rule, reference, fate, n
    crit = _read(reports_dir / "pipeline_failed_criteria.csv")  # criterion, n_zero, n_na (eligible, strict)
    counts: dict[tuple[str, str], dict[str, int]] = {}
    for r in fates:
        counts.setdefault((r["rule"], r["reference"]), {})[r["fate"]] = _i(r["n"])

    rows = [("Eligible studies — strict rule", "strict", "1"), ("Eligible studies — lenient rule", "lenient", "1"),
            ("Not eligible — strict rule", "strict", "0"), ("Not eligible — lenient rule", "lenient", "0")]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 4.6), gridspec_kw={"width_ratios": [1.35, 1], "wspace": 0.45})
    ymap = {}
    for i, (label, rule, ref) in enumerate(rows):
        y = len(rows) - 1 - i + (0.35 if ref == "1" else 0)   # small gap between the two halves
        ymap[y] = label
        c = counts.get((rule, ref), {})
        total = sum(c.get(k, 0) for k, _, _ in FATES)
        left = 0
        for k, _, col in FATES:
            v = c.get(k, 0)
            if v:
                ax1.barh(y, v, left=left, color=col, height=0.62, edgecolor=SURFACE, linewidth=2)
                if v / max(total, 1) > 0.045:
                    ax1.text(left + v / 2, y, str(v), ha="center", va="center", fontsize=8.5,
                             color="white" if col in (BLUE, ORANGE, "#8f8d86") else INK)
                left += v
        inc = c.get("included", 0)
        if total:
            good = ref == "1"
            ax1.text(total * 1.015, y, f"{inc}/{total} included ({100 * inc / total:.0f}%)", va="center",
                     fontsize=9, fontweight="bold" if good else "normal", color=INK)
    ax1.set_yticks(list(ymap), list(ymap.values()))
    ax1.set_xlim(0, max((sum(c.values()) for c in counts.values()), default=1) * 1.42)
    _clean_axes(ax1, "papers")
    from matplotlib.patches import Patch
    ax1.legend(handles=[Patch(color=col, label=lab) for _, lab, col in FATES], loc="lower left",
               bbox_to_anchor=(-0.01, 1.0), ncol=2, frameon=False, fontsize=8.5, borderaxespad=0.2)
    ax1.set_title("Where did each paper end up?", pad=44)

    # --- why eligible papers were excluded at full text ---------------------------
    crit.sort(key=lambda r: _i(r["n_zero"]) + _i(r["n_na"]))
    ys = range(len(crit))
    for y, r in zip(ys, crit):
        z, na = _i(r["n_zero"]), _i(r["n_na"])
        if z:
            ax2.barh(y, z, color=ORANGE, height=0.6, edgecolor=SURFACE, linewidth=2)
        if na:
            ax2.barh(y, na, left=z, color="#d9d8d2", height=0.6, edgecolor=SURFACE, linewidth=2)
        if z + na:
            ax2.text(z + na + 0.3, y, f"{z} no · {na} not reported", va="center", fontsize=8.5, color=INK2)
    ax2.set_yticks(list(ys), [r["criterion"] for r in crit])
    mx = max((_i(r["n_zero"]) + _i(r["n_na"]) for r in crit), default=1)
    ax2.set_xlim(0, mx * 1.6 + 1)
    _clean_axes(ax2, "eligible papers (rated at full text)")
    ax2.legend(handles=[Patch(color=ORANGE, label="LLM said no (0)"), Patch(color="#d9d8d2", label="LLM: not reported (n/a)")],
               loc="lower left", bbox_to_anchor=(-0.01, 1.0), ncol=2, frameon=False, fontsize=8.5, borderaxespad=0.2)
    ax2.set_title("Which criteria failed for eligible papers?", pad=44)

    fig.suptitle(f"End-to-end pipeline — run {run_name}", x=0.01, ha="left", fontsize=13, fontweight="bold",
                 color=INK, y=1.13)
    fig.text(0.01, -0.07, "Strict: included only if every full-text criterion is 1. Lenient: included unless a criterion "
             "is 0 (n/a allowed). Balanced sets (50/50) give valid sensitivity/specificity, not real-search precision.",
             fontsize=8, color=INK2)
    out = reports_dir / "figures" / "pipeline_overview.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out
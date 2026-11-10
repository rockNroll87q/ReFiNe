"""Agreement metrics for LLM-vs-human screening comparisons.

Pure-python (no numpy/sklearn dependency). Conventions:

* Binary metrics take (truth, pred) pairs of bools where True = "criterion met"
  (or "eligible / keep"). Sensitivity = recall of human positives; specificity
  = recall of human negatives; PPV/NPV as usual; Cohen's kappa on the 2x2.
* Proportions get Wilson score 95% CIs (well-behaved near 0/1 and for small n,
  unlike the Wald interval). Kappa gets a percentile bootstrap 95% CI
  (resampling papers; fixed seed for reproducibility).
* Multiclass agreement (e.g. {1, 0, n/a}) reports % agreement + Cohen's kappa.

Limitations to keep in mind when reading the numbers:
* All estimates are UNWEIGHTED: they describe the evaluated sample, not the
  full search output, unless that sample is a simple random sample of it.
  The current combined set is enriched for human-eligible papers, so PPV/NPV
  in particular do not transfer (they depend on prevalence).
* Kappa is prevalence-sensitive: with very skewed margins (e.g. human_subjects,
  ~99% positive) kappa can be low or undefined despite near-perfect agreement.
  Read it alongside sensitivity/specificity, never alone.
* Bootstrap CIs for kappa are unreliable for tiny cells (< ~5 per cell).
"""

from __future__ import annotations

import math
import random
from collections import Counter
from dataclasses import dataclass, field

NAN = float("nan")


def wilson(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n == 0:
        return NAN, NAN
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def cohen_kappa(pairs: list[tuple], labels: list | None = None) -> float:
    """Unweighted Cohen's kappa for (rater_a, rater_b) pairs.

    Returns NaN (not estimable) when either rater used a single category: kappa
    is then 0 or undefined by construction regardless of agreement, which is
    uninformative (sklearn would return 0.0 here; we deliberately do not).
    """
    n = len(pairs)
    if n == 0 or len({a for a, _ in pairs}) < 2 or len({b for _, b in pairs}) < 2:
        return NAN
    labels = labels or sorted({x for p in pairs for x in p}, key=str)
    po = sum(1 for a, b in pairs if a == b) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[lab] * cb[lab] for lab in labels) / (n * n)
    return NAN if pe >= 1.0 else (po - pe) / (1 - pe)


def bootstrap_ci(pairs: list[tuple], stat, n_boot: int = 2000, seed: int = 0) -> tuple[float, float]:
    """Percentile bootstrap 95% CI of stat(pairs), resampling pairs with replacement."""
    n = len(pairs)
    if n < 2:
        return NAN, NAN
    rng = random.Random(seed)
    vals = []
    for _ in range(n_boot):
        v = stat([pairs[rng.randrange(n)] for _ in range(n)])
        if not math.isnan(v):
            vals.append(v)
    if len(vals) < n_boot * 0.5:  # mostly undefined resamples -> CI not meaningful
        return NAN, NAN
    vals.sort()
    return vals[int(0.025 * (len(vals) - 1))], vals[int(0.975 * (len(vals) - 1))]


# ---------------------------------------------------------------------------
# Binary
# ---------------------------------------------------------------------------

@dataclass
class Prop:
    k: int
    n: int

    @property
    def p(self) -> float:
        return self.k / self.n if self.n else NAN

    @property
    def ci(self) -> tuple[float, float]:
        return wilson(self.k, self.n)

    def fmt(self) -> str:
        if not self.n:
            return "n/e"  # not estimable
        lo, hi = self.ci
        return f"{100 * self.p:.1f}% ({100 * lo:.0f}–{100 * hi:.0f}) [{self.k}/{self.n}]"


@dataclass
class BinaryResult:
    tp: int
    fp: int
    fn: int
    tn: int
    kappa: float
    kappa_ci: tuple[float, float]

    @property
    def n(self) -> int:
        return self.tp + self.fp + self.fn + self.tn

    @property
    def sensitivity(self) -> Prop:
        return Prop(self.tp, self.tp + self.fn)

    @property
    def specificity(self) -> Prop:
        return Prop(self.tn, self.tn + self.fp)

    @property
    def ppv(self) -> Prop:
        return Prop(self.tp, self.tp + self.fp)

    @property
    def npv(self) -> Prop:
        return Prop(self.tn, self.tn + self.fn)

    @property
    def accuracy(self) -> Prop:
        return Prop(self.tp + self.tn, self.n)

    def fmt_kappa(self) -> str:
        if math.isnan(self.kappa):
            return "n/e"
        lo, hi = self.kappa_ci
        ci = "" if math.isnan(lo) else f" ({lo:.2f}–{hi:.2f})"
        return f"{self.kappa:.2f}{ci}"

    def as_dict(self, prefix: str = "") -> dict:
        d = {"n": self.n, "tp": self.tp, "fp": self.fp, "fn": self.fn, "tn": self.tn}
        for name in ("sensitivity", "specificity", "ppv", "npv", "accuracy"):
            p = getattr(self, name)
            lo, hi = p.ci
            d.update({name: _r(p.p), f"{name}_lo": _r(lo), f"{name}_hi": _r(hi)})
        d.update({"kappa": _r(self.kappa), "kappa_lo": _r(self.kappa_ci[0]), "kappa_hi": _r(self.kappa_ci[1])})
        return {prefix + k: v for k, v in d.items()}


def _r(x: float) -> str:
    return "" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.4f}"


def binary_metrics(pairs: list[tuple[bool, bool]], n_boot: int = 2000) -> BinaryResult:
    """pairs = [(truth, pred), ...] with True = positive (criterion met / keep)."""
    c = Counter(pairs)
    kappa_fn = lambda ps: cohen_kappa(ps, [True, False])  # noqa: E731
    return BinaryResult(
        tp=c[(True, True)], fp=c[(False, True)], fn=c[(True, False)], tn=c[(False, False)],
        kappa=kappa_fn(pairs), kappa_ci=bootstrap_ci(pairs, kappa_fn, n_boot),
    )


# ---------------------------------------------------------------------------
# Multiclass (1 / 0 / n/a)
# ---------------------------------------------------------------------------

@dataclass
class AgreementResult:
    labels: list
    confusion: dict = field(default_factory=dict)  # (human, llm) -> n
    kappa: float = NAN
    kappa_ci: tuple[float, float] = (NAN, NAN)

    @property
    def n(self) -> int:
        return sum(self.confusion.values())

    @property
    def agreement(self) -> Prop:
        return Prop(sum(v for (h, l), v in self.confusion.items() if h == l), self.n)

    def fmt_kappa(self) -> str:
        return BinaryResult(0, 0, 0, 0, self.kappa, self.kappa_ci).fmt_kappa()

    def confusion_md(self, row_name: str = "human", col_name: str = "LLM") -> list[str]:
        cols = self.labels + sorted({l for _, l in self.confusion if l not in self.labels}, key=str)
        lines = [f"| {row_name} \\ {col_name} | " + " | ".join(map(str, cols)) + " |",
                 "|---|" + "---|" * len(cols)]
        for h in self.labels:
            lines.append(f"| {h} | " + " | ".join(str(self.confusion.get((h, c), 0)) for c in cols) + " |")
        return lines


def multiclass_agreement(pairs: list[tuple[str, str]], labels: list[str] | None = None,
                         n_boot: int = 2000) -> AgreementResult:
    labels = labels or ["1", "0", "n/a"]
    kappa_fn = lambda ps: cohen_kappa(ps, labels)  # noqa: E731
    return AgreementResult(labels=labels, confusion=dict(Counter(pairs)),
                           kappa=kappa_fn(pairs), kappa_ci=bootstrap_ci(pairs, kappa_fn, n_boot))

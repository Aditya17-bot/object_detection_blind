"""Render the paper's four figures as PNGs.

Two consumers, one source:

* `main.tex` uses \\includegraphics instead of TikZ/pgfplots. The TikZ version
  was correct but blew Overleaf's free-tier compile timeout, which presents to
  the user as a paywall rather than as a timeout.
* `build_docx.py` embeds the same PNGs, so the Word version and the LaTeX
  version cannot drift into showing different numbers.

    venv/Scripts/python.exe paper/build_figures.py

Numbers are declared once at the top of this file. When a run changes them,
change them HERE and nowhere else in the figure pipeline.
"""

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from pathlib import Path

OUT = Path(__file__).parent / "figures"
DPI = 300

# --- palette: the running app's own UI colours, deliberately --------------
AMBER = "#B57500"
TEAL = "#10707F"
ROSE = "#C13239"
MOSS = "#3B7A4E"
SLATE = "#5A6672"
PANEL = "#F2F5F8"
INK = "#1B2026"

# --- the numbers (eval set e4eeca83070e2d66 clean / f9e775b6a65279a4 asr) --
CATEGORIES = ["canonical", "paraphrase", "multi-intent", "out-of-scope",
              "ambiguous", "overall"]
KEYWORD = [100.0, 0.0, 0.0, 95.0, 3.3, 39.5]
LLM_ONLY = [45.0, 48.6, 30.0, 47.5, 43.3, 45.0]
TWO_TIER = [100.0, 47.1, 10.0, 45.0, 43.3, 53.0]

FABRICATION = [("tool-mediated", 0.0, "0 / 200"),
               ("free text", 42.5, "85 / 200")]

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif"],
    "axes.edgecolor": SLATE,
    "axes.labelcolor": INK,
    "text.color": INK,
    "xtick.color": SLATE,
    "ytick.color": SLATE,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.02,
})


def _box(ax, x, y, w, h, text, sub=None, edge=SLATE, face="white", lw=0.9):
    ax.add_patch(FancyBboxPatch(
        (x - w / 2, y - h / 2), w, h,
        boxstyle="round,pad=0.012,rounding_size=0.02",
        linewidth=lw, edgecolor=edge, facecolor=face, zorder=2))
    if sub:
        ax.text(x, y + 0.018, text, ha="center", va="center",
                fontsize=6.6, zorder=3)
        ax.text(x, y - 0.030, sub, ha="center", va="center",
                fontsize=5.2, color=SLATE, zorder=3)
    else:
        ax.text(x, y, text, ha="center", va="center", fontsize=6.6, zorder=3)


def _arrow(ax, p, q, color=SLATE, style="-", lw=0.9, shrink=3.0):
    ax.add_patch(FancyArrowPatch(
        p, q, arrowstyle="-|>", mutation_scale=7, linewidth=lw,
        color=color, linestyle=style, zorder=1,
        shrinkA=shrink, shrinkB=shrink))


def _label(ax, x, y, text, color=SLATE, size=5.2, ha="center"):
    """Edge label on an opaque patch. Without the mask these sit directly on
    the arrows they annotate and both become unreadable at column width."""
    ax.text(x, y, text, fontsize=size, color=color, ha=ha, va="center",
            zorder=4, linespacing=1.1,
            bbox=dict(boxstyle="round,pad=0.14", facecolor="white",
                      edgecolor="none"))


# --------------------------------------------------------------------------
# F1 -- the system, drawn as the authority boundary
# --------------------------------------------------------------------------

def figure_system():
    fig, ax = plt.subplots(figsize=(3.33, 2.55))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    lx, rx = 0.21, 0.75
    w, h = 0.36, 0.105
    ys = [0.80, 0.615, 0.43, 0.245]

    ax.axvline(0.485, 0.04, 0.90, color=SLATE, linestyle=(0, (3, 3)),
               linewidth=0.8)
    ax.text(lx, 0.955, "may SELECT a capability", ha="center", fontsize=5.6,
            color=SLATE)
    ax.text(rx, 0.955, "authors ALL spoken guidance", ha="center",
            fontsize=5.6, color=AMBER)

    _box(ax, lx, ys[0], w, h, "microphone")
    _box(ax, lx, ys[1], w, h, "Vosk ASR", "grammar-constrained")
    _box(ax, lx, ys[2], w, h, "tier 0 parser", "5 us, on handset")
    _box(ax, lx, ys[3], w, h, "tier 1 router", "local LLM, on laptop")

    _box(ax, rx, ys[0], w, h, "camera", "YUV420 frames")
    _box(ax, rx, ys[1], w, h, "YOLOv8s + custom", "on laptop")
    _box(ax, rx, ys[2], w, h, "position", "zone, bucket, gated metres",
         edge=AMBER, face="#FDF6E7", lw=1.5)
    _box(ax, rx, ys[3], w, h, "decision", "what to say now",
         edge=AMBER, face="#FDF6E7", lw=1.5)
    _box(ax, rx, 0.075, w, h, "speech . sonar . haptics")

    for a, b in zip(ys, ys[1:]):
        _arrow(ax, (lx, a - h / 2), (lx, b + h / 2))
        _arrow(ax, (rx, a - h / 2), (rx, b + h / 2))
    _arrow(ax, (rx, ys[3] - h / 2), (rx, 0.075 + h / 2))

    _label(ax, lx + 0.045, (ys[2] + ys[3]) / 2, "miss only", ha="left")
    _label(ax, rx + 0.045, (ys[0] + ys[1]) / 2, "Wi-Fi", ha="left")

    _arrow(ax, (lx + w / 2, ys[2]), (rx - w / 2, ys[3] + 0.028),
           color=TEAL, style=(0, (3, 2)), lw=1.2)
    _arrow(ax, (lx + w / 2, ys[3]), (rx - w / 2, ys[3] - 0.012),
           color=TEAL, style=(0, (3, 2)), lw=1.2)
    _label(ax, 0.485, ys[3] + 0.098, "tool + arg", color=TEAL, size=5.4)

    fig.savefig(OUT / "f1_system.png", dpi=DPI)
    plt.close(fig)


# --------------------------------------------------------------------------
# F2 -- two-tier router
# --------------------------------------------------------------------------

def figure_router():
    fig, ax = plt.subplots(figsize=(3.33, 2.75))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    w, h = 0.29, 0.095
    _box(ax, 0.50, 0.955, 0.26, 0.078, "utterance")
    _box(ax, 0.50, 0.830, 0.54, 0.078, "tier 0 keyword grammar", face=PANEL)
    _box(ax, 0.795, 0.650, w, h, "local LLM", "JSON tool call", face=PANEL)
    _box(ax, 0.795, 0.470, w, h, "validate", "tool? class? arg?", face=PANEL)
    _box(ax, 0.175, 0.470, w, h, "validated", "action list",
         edge=MOSS, face="#EAF3EC")
    _box(ax, 0.175, 0.285, w, h, "execute", "decision.py",
         edge=MOSS, face="#EAF3EC")
    _box(ax, 0.525, 0.215, 0.26, h, "abstain", "fixed template",
         edge=ROSE, face="#FBECEC")
    _box(ax, 0.855, 0.215, 0.28, h, "grounded reply", "capped",
         edge=AMBER, face="#FDF6E7")
    _box(ax, 0.285, 0.050, 0.20, 0.070, "speak")

    _arrow(ax, (0.50, 0.916), (0.50, 0.869))
    _arrow(ax, (0.29, 0.791), (0.175, 0.518))
    _arrow(ax, (0.71, 0.791), (0.795, 0.698))
    _arrow(ax, (0.795, 0.602), (0.795, 0.518))
    _arrow(ax, (0.650, 0.470), (0.320, 0.470))
    _arrow(ax, (0.735, 0.422), (0.580, 0.263), color=ROSE)
    _arrow(ax, (0.870, 0.422), (0.865, 0.263), color=AMBER)
    _arrow(ax, (0.175, 0.422), (0.175, 0.333))
    _arrow(ax, (0.205, 0.237), (0.255, 0.085))
    _arrow(ax, (0.470, 0.168), (0.330, 0.078))
    _arrow(ax, (0.790, 0.168), (0.390, 0.052))

    _label(ax, 0.235, 0.640, "hit, 5 us")
    _label(ax, 0.830, 0.755, "miss")
    _label(ax, 0.485, 0.470, "pass")
    _label(ax, 0.618, 0.372, "reject,\nprose,\ntimeout", color=ROSE, size=4.8)
    _label(ax, 0.935, 0.345, "reply", color=AMBER)

    fig.savefig(OUT / "f2_router.png", dpi=DPI)
    plt.close(fig)


# --------------------------------------------------------------------------
# F3 -- accuracy by category
# --------------------------------------------------------------------------

def figure_accuracy():
    fig, ax = plt.subplots(figsize=(3.33, 1.85))
    x = range(len(CATEGORIES))
    width = 0.27
    ax.bar([i - width for i in x], KEYWORD, width, label="keyword",
           color=SLATE, alpha=0.75, edgecolor=SLATE, linewidth=0.4)
    ax.bar(list(x), LLM_ONLY, width, label="LLM only",
           color=TEAL, alpha=0.85, edgecolor=TEAL, linewidth=0.4)
    ax.bar([i + width for i in x], TWO_TIER, width, label="two-tier",
           color=AMBER, alpha=0.9, edgecolor=AMBER, linewidth=0.4)

    ax.set_ylim(0, 106)
    ax.set_ylabel("accuracy (%)", fontsize=6.5)
    ax.set_xticks(list(x))
    ax.set_xticklabels(CATEGORIES, fontsize=5.8, rotation=18, ha="right")
    ax.tick_params(axis="y", labelsize=5.8, length=2)
    ax.tick_params(axis="x", length=0)
    ax.yaxis.grid(True, linestyle=(0, (2, 3)), linewidth=0.5, color="#C9D0D8")
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_linewidth(0.6)
    ax.spines["bottom"].set_linewidth(0.6)
    ax.legend(fontsize=5.8, ncol=3, frameon=False,
              loc="lower center", bbox_to_anchor=(0.5, 1.0))

    fig.savefig(OUT / "f3_accuracy.png", dpi=DPI)
    plt.close(fig)


# --------------------------------------------------------------------------
# F4 -- fabricated perception
# --------------------------------------------------------------------------

def figure_fabrication():
    fig, ax = plt.subplots(figsize=(3.33, 1.15))
    labels = [row[0] for row in FABRICATION]
    values = [row[1] for row in FABRICATION]
    notes = [row[2] for row in FABRICATION]
    colors = [MOSS, ROSE]

    bars = ax.barh(range(len(labels)), values, height=0.45, color=colors,
                   alpha=0.8, edgecolor=colors, linewidth=0.5)
    for bar, value, note in zip(bars, values, notes):
        ax.text(value + 1.6, bar.get_y() + bar.get_height() / 2,
                f"{value:.1f}%  ({note})", va="center", fontsize=5.8)

    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=6.2)
    ax.set_xlim(0, 100)
    ax.set_xlabel("responses containing fabricated perception (%)",
                  fontsize=6.2)
    ax.tick_params(axis="x", labelsize=5.8, length=2)
    ax.tick_params(axis="y", length=0)
    ax.xaxis.grid(True, linestyle=(0, (2, 3)), linewidth=0.5, color="#C9D0D8")
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_linewidth(0.6)

    fig.savefig(OUT / "f4_fabrication.png", dpi=DPI)
    plt.close(fig)


def main():
    OUT.mkdir(exist_ok=True)
    figure_system()
    figure_router()
    figure_accuracy()
    figure_fabrication()
    for path in sorted(OUT.glob("*.png")):
        print(f"wrote {path.relative_to(Path(__file__).parent.parent)} "
              f"({path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()

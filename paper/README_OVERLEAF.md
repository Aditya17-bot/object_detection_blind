# Getting this into Overleaf

`main.tex` is **self-contained**. Every figure is TikZ/pgfplots, so there are no
image files to upload, nothing to re-export when a number changes, and every
diagram stays editable inside Overleaf.

## The five-minute version

1. overleaf.com → **New Project** → **Upload Project** → upload `main.tex` alone
   (or drag the whole `paper/` folder; the other files are ignored by LaTeX).
2. Menu → **Compiler: pdfLaTeX**. The `acmart` class ships with Overleaf, so
   there is nothing to install.
3. Compile. You should get a two-column ACM paper with two TikZ diagrams
   (system, router) and two pgfplots charts (accuracy, fabrication).

If you would rather not upload by hand: `Menu → GitHub` and point Overleaf at
`github.com/Aditya17-bot/object_detection_blind`, then set the main document to
`paper/main.tex`.

## Before you submit

- **Author block.** Fill in `\affiliation` and add co-authors. Right now it says
  "Add affiliation".
- **Rights.** The template is set to `nonacm` so it compiles clean as a draft.
  When ACM sends you the rights form, remove `nonacm` from the
  `\documentclass` options and paste in the `\setcopyright`, `\acmConference`,
  `\acmDOI`, `\acmISBN` block they give you. Also delete these two draft lines
  near the top:

  ```latex
  \settopmatter{printacmref=false}
  \renewcommand\footnotetextcopyrightpermission[1]{}
  ```

- **References.** There are none yet — the related-work section names systems in
  prose. ASSETS will want proper citations. Add a `.bib`, drop
  `natbib=false` from the class options, and cite: Be My Eyes, Seeing AI,
  Envision, OrCam, Microsoft Soundscape, WeWALK; plus selective prediction /
  learning-to-defer, and constrained decoding / tool use for LLMs.
- **Page limit.** ASSETS Late-Breaking Work is 4–6 pages excluding references.
  The current draft runs long. If you need to cut: §2 Related work compresses to
  one paragraph, and the registry table (Table 4) can move to a repository link.

## Where every number comes from

| Table / figure | Source file |
|---|---|
| T3 accuracy, Fig. 3 | `test_output/agent_eval_{keyword,llm_only,two_tier}.md` |
| T4 latency, T5 over-trigger | same three files |
| T6 fabrication, Fig. 5 | `test_output/agent_eval_llm_freetext.md` |
| qwen3 sensitivity note | `test_output/agent_eval_two_tier_qwen3.md` |
| system latency figures | `test_output/gpu_bench.md`, server logs |

Eval set sha256 `e4eeca83070e2d66`, model `llama3.2:3b` under Ollama.
**Quote the hash with any number you move into the paper** — it changes the
moment ASR transcripts are written into the set.

## Regenerating a number

```bash
venv/Scripts/python.exe eval_agent.py --config two_tier --model llama3.2:3b
```

Configs: `keyword`, `llm_only`, `two_tier`, `llm_freetext`. Add
`--condition asr` once transcripts exist. Reports land in `test_output/` in a
markdown shape that pastes straight into the paper.

## Editing the figures

The diagrams are TikZ in the body of `main.tex`, right where they are used.

- **Fig. 1 (system)** — nodes are declared top to bottom; the three dashed
  groups come from the `\begin{scope}[on background layer]` block. To restyle
  the "deterministic core", change the `core/.style` line.
- **Fig. 2 (router)** — same idea; the abstain branch is `no/.style` (rose) and
  the reply channel is the amber node.
- **Figs. 3 and 5 (charts)** — `pgfplots` `\addplot coordinates {...}`. Swap the
  numbers in place; no external data file.

Colours are defined once at the top (`amber`, `teal`, `rose`, `moss`, `slate`)
and match the running app's own UI, which is deliberate — the screenshots and
the figures should look like the same system.

## The visual version

A browser-readable dossier of the same material — architecture, all the charts,
the timeline, the limitations — is published as an artifact:
<https://claude.ai/code/artifact/d6e5e754-5c6c-4e6e-946e-3fb762f99503>

Print it to PDF from the browser if you want a handout. It is not a substitute
for `main.tex`; it is the version to show someone who is not going to read a
two-column paper.

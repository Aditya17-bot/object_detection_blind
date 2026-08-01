# Two builds of the same paper

| | file | needs |
|---|---|---|
| **Word** | `BlindAssist_paper.docx` | nothing — open it |
| **PDF** | `BlindAssist_paper.pdf` | nothing — 6 pages, already exported |
| **LaTeX** | `main.tex` + `references.bib` + `figures/` | Overleaf or a local TeX |

Both are ACM `sigconf` two-column layout, 6 pages including references, and they
share the same figure PNGs so a number cannot differ between them.

## If you just want the paper

Open `paper/BlindAssist_paper.docx` in Word or upload it to Google Docs: title
block across the top, two columns, four figures, four tables, 53 numbered
references. `BlindAssist_paper.pdf` is the same document already exported.

**To change the text, edit `paper/build_docx.py` and re-run it** — do not
edit the .docx by hand, the next build overwrites it:

```bash
venv/Scripts/python.exe paper/build_figures.py    # only if a number changed
venv/Scripts/python.exe paper/build_docx.py
powershell -ExecutionPolicy Bypass -File tools/docx_to_pdf.ps1 \
    -DocxPath paper/BlindAssist_paper.docx -PdfPath paper/BlindAssist_paper.pdf
```

## About the Overleaf paywall

Diagnosed from `blind_object.pdf`, the 7-page output of the run that stopped.

It was **not** a feature limit, and the document was not broken: `acmart`
rendered correctly, and both TikZ diagrams came out fine. What did not happen is
the **bibliography pass**. Every citation in that PDF reads `[?]`, so `pdflatex`
ran once and the `bibtex` + two further `pdflatex` passes that resolve citations
never did — the compile ran out of time part-way through the sequence, and
Overleaf surfaces that as an upgrade prompt.

Four vector figures on top of `acmart` is what consumed the budget. Pre-rendering
them removes it: `paper/build_figures.py` writes four PNGs into `paper/figures/`
and `main.tex` uses `\includegraphics`, so no TikZ or pgfplots remains and the
whole sequence finishes in seconds. The figure *sources* did not disappear —
they are Python now, and easier to edit than the TikZ was.

**If you still see `[?]` citations**, that is this same symptom and not a
missing `.bib`: hit Recompile again, or Menu → Clear cached files and recompile.
The `.docx`/`.pdf` build has no such failure mode because there is no compiler.

## Getting it into Overleaf

1. overleaf.com → **New Project** → **Upload Project**.
2. Upload `main.tex`, `references.bib`, **and the `figures/` folder** (all four
   PNGs). The folder matters: `\graphicspath{{figures/}}` expects it.
3. Menu → **Compiler: pdfLaTeX**. The `acmart` class ships with Overleaf.
4. Compile **twice** — the first pass writes the `.aux` BibTeX reads. If
   citations render as `[?]`, hit Recompile again.

If you would rather not upload by hand: `Menu → GitHub`, point Overleaf at
`github.com/Aditya17-bot/object_detection_blind`, and set the main document to
`paper/main.tex`.

## Keeping the builds in sync

Chart numbers live in one place (`build_figures.py`). **The prose is duplicated**
between `main.tex` and `build_docx.py`, so a wording change must be made in
both, and `PAPER.md` is the long-form master carrying reasoning too long for six
pages. Three files, one paper.

## Before you submit — in priority order

1. **Verify every reference.** `references.bib` was assembled from memory, not
   exported from a database. Titles, authors, venues and years are believed
   correct; page numbers, volume/issue and publisher are the fields most likely
   to be wrong, and there are **no DOIs**, deliberately — an unverified DOI is
   worse than an absent one. Paste each key into the ACM DL or DBLP, export its
   BibTeX, replace the entry wholesale. This is not optional: the paper argues
   that a system should decline to state what it cannot verify, and a reviewer
   who catches a fabricated citation in *that* paper will reject it on the spot.
   Entries most worth double-checking first: `adnin2024genai`,
   `kuriakose2022review`, `csapo2013auditory`, `qin2024toolllm`.
2. **Author block.** Fill in `\affiliation` and add co-authors. It currently
   says "Add affiliation".
3. **Rights.** The class is set to `nonacm` so it compiles clean as a draft.
   When ACM sends the rights form, remove `nonacm` from `\documentclass` and
   paste in their `\setcopyright`, `\acmConference`, `\acmDOI`, `\acmISBN`
   block. Also delete these two draft lines near the top:

   ```latex
   \settopmatter{printacmref=false}
   \renewcommand\footnotetextcopyrightpermission[1]{}
   ```

4. **Page limit.** The draft runs roughly 6 pages of body plus references.
   - **CHI Late-Breaking Work** (6 pp excluding references): fits as written.
   - **ASSETS Posters & Demos** (4 pp): needs real cuts. Take them in this
     order — Table 4 (registry) to a repository link, §2 Related work down to
     one paragraph per thread, Figure 3 (it duplicates Table 1), then the
     registry paragraph in §5.
   - **ASSETS full paper**: there is enough material, but expect reviewers to
     press hard on the absence of blind participants. §8 and §9 name that
     openly, which is the strongest available position without a study.
5. **Accessibility of the PDF.** ASSETS requires it. Every figure already has a
   `\Description{}`; check that they still describe the figure after any edit,
   and run the ACM accessibility checklist over the compiled PDF.

## Where every number comes from

| Table / figure | Source file |
|---|---|
| Table 1 accuracy, Fig. 3 | `test_output/agent_eval_{keyword,llm_only,two_tier}.md` |
| Table 2 over-trigger + latency | same three files |
| Fig. 4 fabrication | `test_output/agent_eval_llm_freetext.md` |
| Table 3 spoken condition | `test_output/agent_eval_{keyword,two_tier}_asr.md` |
| Table 3 matched text baseline | `test_output/agent_eval_{keyword,two_tier}_asrsubset.md` |
| qwen3 sensitivity note | `test_output/agent_eval_two_tier_qwen3.md` |
| detector timings | `test_output/gpu_bench.md`, server logs |

Model `llama3.2:3b` under Ollama; all configurations run 2026-08-01 against the
current harness. **Two set hashes, and they are not interchangeable:**

- `e4eeca83070e2d66` — clean condition, before the spoken transcripts existed.
- `f9e775b6a65279a4` — after `asr_collect.py align` wrote them in. Only the
  `asr` arrays differ, so clean numbers are unaffected, but **the matched
  baseline in Table 3 was run under the new hash** and must be quoted with it.

Quote the hash with any number you move into the paper.

## Regenerating a number

```bash
venv/Scripts/python.exe eval_agent.py --config two_tier --model llama3.2:3b
```

Configs: `keyword`, `llm_only`, `two_tier`, `llm_freetext`. Add
`--condition asr` once transcripts exist. Reports land in `test_output/` in a
markdown shape that pastes straight into the paper. Read the **Mismatches**
section, not the summary tables — that is where the failures are legible.

## Editing the figures

All four live in `paper/build_figures.py`; re-run it and both builds pick the
new PNGs up.

- **Fig. 1 (system)** — two lanes at fixed coordinates, separated by a dashed
  vertical line. The left lane may only select; the right lane authors all
  speech. The two teal dashed arrows crossing that line are the paper's central
  claim, drawn. Move a node by editing its `(x, y)`.
- **Fig. 2 (router)** — same fixed-coordinate style. The rose arrow is the
  reject path into abstention, the amber one is the conversational reply
  channel. Both end at `speak`, and **neither passes through `execute`**; that
  separation is the point of the figure, so preserve it if you rearrange.
- **Figs. 3 and 4 (charts)** — the numbers are constants at the top of the file
  (`KEYWORD`, `LLM_ONLY`, `TWO_TIER`, `FABRICATION`). Change them there.

Edge labels are drawn on an opaque white patch (`_label`). Without that they sit
on top of the arrows they annotate and both become unreadable at column width —
which is what the first draft of Fig. 2 did.

Colours are defined once at the top (`AMBER`, `TEAL`, `ROSE`, `MOSS`, `SLATE`)
and match the running app's UI, which is deliberate — screenshots and figures
should look like the same system.

## The visual version

A browser-readable dossier of the same material — architecture, all the charts,
the timeline, the limitations — is published as an artifact:
<https://claude.ai/code/artifact/d6e5e754-5c6c-4e6e-946e-3fb762f99503>

Print it to PDF from the browser if you want a handout. It is not a substitute
for `main.tex`; it is the version to show someone who is not going to read a
two-column paper.

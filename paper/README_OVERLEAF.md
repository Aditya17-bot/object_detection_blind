# Getting this into Overleaf

`main.tex` needs exactly one companion file, `references.bib`. Every figure is
TikZ/pgfplots, so there are no images to upload, nothing to re-export when a
number changes, and every diagram stays editable inside Overleaf.

## The five-minute version

1. overleaf.com → **New Project** → **Upload Project** → upload `main.tex` and
   `references.bib` (or drag the whole `paper/` folder; LaTeX ignores the rest).
2. Menu → **Compiler: pdfLaTeX**. The `acmart` class ships with Overleaf.
3. Compile **twice** — the first pass writes the `.aux` BibTeX reads. Overleaf
   usually does this for you; if citations render as `[?]`, hit Recompile again.

You should get a two-column ACM paper with two TikZ diagrams (system, router),
two pgfplots charts (accuracy, fabrication), three tables, and a reference list.

If you would rather not upload by hand: `Menu → GitHub`, point Overleaf at
`github.com/Aditya17-bot/object_detection_blind`, and set the main document to
`paper/main.tex`.

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
| qwen3 sensitivity note | `test_output/agent_eval_two_tier_qwen3.md` |
| detector timings | `test_output/gpu_bench.md`, server logs |

Eval set sha256 `e4eeca83070e2d66`, model `llama3.2:3b` under Ollama, all four
configurations re-run 2026-08-01 against the current harness.
**Quote the hash with any number you move into the paper** — it changes the
moment ASR transcripts are written into the set, and numbers under two different
hashes are not comparable.

`PAPER.md` is the long-form master and carries reasoning that does not fit in
six pages. When a number changes, change it in **both** files.

## Regenerating a number

```bash
venv/Scripts/python.exe eval_agent.py --config two_tier --model llama3.2:3b
```

Configs: `keyword`, `llm_only`, `two_tier`, `llm_freetext`. Add
`--condition asr` once transcripts exist. Reports land in `test_output/` in a
markdown shape that pastes straight into the paper. Read the **Mismatches**
section, not the summary tables — that is where the failures are legible.

## Editing the figures

The diagrams are TikZ in the body of `main.tex`, right where they are used.

- **Fig. 1 (system)** — two lanes at fixed coordinates, separated by a dashed
  vertical line at `x=2.35`. The left lane may only select; the right lane
  authors all speech. The two teal dashed arrows crossing that line are the
  paper's central claim drawn. Move a node by editing its `at (x,y)`.
- **Fig. 2 (router)** — same fixed-coordinate style. The rose arrow is the
  reject path into abstention, the amber one is the conversational reply
  channel. Both end at `speak`, and neither passes through `execute`; that
  separation is the point of the figure, so keep it if you rearrange.
- **Figs. 3 and 4 (charts)** — `pgfplots` `\addplot coordinates {...}`. Swap the
  numbers in place; no external data file.

Colours are defined once at the top (`amber`, `teal`, `rose`, `moss`, `slate`)
and match the running app's UI, which is deliberate — screenshots and figures
should look like the same system.

## The visual version

A browser-readable dossier of the same material — architecture, all the charts,
the timeline, the limitations — is published as an artifact:
<https://claude.ai/code/artifact/d6e5e754-5c6c-4e6e-946e-3fb762f99503>

Print it to PDF from the browser if you want a handout. It is not a substitute
for `main.tex`; it is the version to show someone who is not going to read a
two-column paper.

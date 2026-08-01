"""Build the Word version of the paper, laid out like an ACM sigconf paper.

    venv/Scripts/python.exe paper/build_figures.py
    venv/Scripts/python.exe paper/build_docx.py

Why this exists: Overleaf's free tier stops compiling before `main.tex`
finishes and presents that as a paywall. This produces the same paper as a
.docx that opens in Word, Google Docs or LibreOffice with no compiler at all.

`main.tex` remains the LaTeX submission artifact and this file mirrors it.
They share the figure PNGs, so a number can never differ between the two
figures -- but the PROSE is duplicated, so when one changes, change both. The
numbers are declared once, at the top, and both consumers read them from here.
"""

from pathlib import Path

from docx_writer import Docx

HERE = Path(__file__).parent
FIGS = HERE / "figures"
COL = 3.33                       # column width, inches

TITLE = "Say Less, Never Mislead"
SUBTITLE = ("Cross-Layer Selective Abstention in an Offline Assistive "
            "Perception System, Extended to a Tool-Mediated Voice Agent")
AUTHOR = "Aditya"

CLEAN_HASH = "e4eeca83070e2d66"
ASR_HASH = "f9e775b6a65279a4"

# --------------------------------------------------------------------------
# References, ACM numeric style: sorted by first author surname.
# --------------------------------------------------------------------------

REFERENCES = [
    ("adnin2024genai", "Rudaiba Adnin and Maitraye Das. 2024. “I Look at It "
     "as the King of Knowledge”: How Blind People Use and Understand "
     "Generative AI Tools. In Proceedings of the 26th International ACM "
     "SIGACCESS Conference on Computers and Accessibility (ASSETS)."),
    ("ahmetovic2016navcog", "Dragan Ahmetovic, Cole Gleason, Chengxiong Ruan, "
     "Kris Kitani, Hironobu Takagi, and Chieko Asakawa. 2016. NavCog: A "
     "Navigational Cognitive Assistant for the Blind. In MobileHCI."),
    ("bemyeyes", "Be My Eyes. Be My Eyes: See the World Together. "
     "https://www.bemyeyes.com/"),
    ("bigham2010vizwiz", "Jeffrey P. Bigham, Chandrika Jayant, Hanjie Ji, Greg "
     "Little, Andrew Miller, Robert C. Miller, Robin Miller, Aubrey "
     "Tatarowicz, Brandyn White, Samual White, and Tom Yeh. 2010. VizWiz: "
     "Nearly Real-Time Answers to Visual Questions. In UIST."),
    ("breznitz1984crywolf", "Shlomo Breznitz. 1984. Cry Wolf: The Psychology "
     "of False Alarms. Lawrence Erlbaum Associates."),
    ("chow1970reject", "C. K. Chow. 1970. On Optimum Recognition Error and "
     "Reject Tradeoff. IEEE Transactions on Information Theory 16, 1."),
    ("csapo2013auditory", "Ádám Csapó and György "
     "Wersényi. 2013. Overview of Auditory Representations in "
     "Human-Machine Interfaces. ACM Computing Surveys 46, 2."),
    ("elyaniv2010selective", "Ran El-Yaniv and Yair Wiener. 2010. On the "
     "Foundations of Noise-Free Selective Classification. Journal of Machine "
     "Learning Research 11."),
    ("envision", "Envision. Envision: Perceive Possibility. "
     "https://www.letsenvision.com/"),
    ("geifman2017selectivenet", "Yonatan Geifman and Ran El-Yaniv. 2017. "
     "Selective Classification for Deep Neural Networks. In NeurIPS."),
    ("guerreiro2019cabot", "João Guerreiro, Daisuke Sato, Saki Asakawa, "
     "Huixu Dong, Kris M. Kitani, and Chieko Asakawa. 2019. CaBot: Designing "
     "and Evaluating an Autonomous Navigation Robot for Blind People. In "
     "ASSETS."),
    ("guo2017calibration", "Chuan Guo, Geoff Pleiss, Yu Sun, and Kilian Q. "
     "Weinberger. 2017. On Calibration of Modern Neural Networks. In ICML."),
    ("gurari2018vizwiz", "Danna Gurari, Qing Li, Abigale J. Stangl, Anhong "
     "Guo, Chi Lin, Kristen Grauman, Jiebo Luo, and Jeffrey P. Bigham. 2018. "
     "VizWiz Grand Challenge: Answering Visual Questions from Blind People. "
     "In CVPR."),
    ("hendrycks2017baseline", "Dan Hendrycks and Kevin Gimpel. 2017. A "
     "Baseline for Detecting Misclassified and Out-of-Distribution Examples "
     "in Neural Networks. In ICLR."),
    ("ji2023hallucination", "Ziwei Ji, Nayeon Lee, Rita Frieske, Tiezheng Yu, "
     "Dan Su, Yan Xu, Etsuko Ishii, Yejin Bang, Andrea Madotto, and Pascale "
     "Fung. 2023. Survey of Hallucination in Natural Language Generation. "
     "ACM Computing Surveys 55, 12."),
    ("jocher2023ultralytics", "Glenn Jocher, Ayush Chaurasia, and Jing Qiu. "
     "2023. Ultralytics YOLO. Software. "
     "https://github.com/ultralytics/ultralytics"),
    ("kacorri2017teachable", "Hernisa Kacorri, Kris M. Kitani, Jeffrey P. "
     "Bigham, and Chieko Asakawa. 2017. People with Visual Impairment "
     "Training Personal Object Recognizers: Feasibility and Challenges. In "
     "CHI."),
    ("kadavath2022know", "Saurav Kadavath, Tom Conerly, Amanda Askell, Tom "
     "Henighan, Dawn Drain, Ethan Perez, et al. 2022. Language Models "
     "(Mostly) Know What They Know. arXiv:2207.05221."),
    ("kuriakose2022review", "Bineeth Kuriakose, Raju Shrestha, and Frode Eika "
     "Sandnes. 2022. Tools and Technologies for Blind and Visually Impaired "
     "Navigation Support: A Review. IETE Technical Review 39, 1."),
    ("lee2004trust", "John D. Lee and Katrina A. See. 2004. Trust in "
     "Automation: Designing for Appropriate Reliance. Human Factors 46, 1."),
    ("lin2014coco", "Tsung-Yi Lin, Michael Maire, Serge Belongie, James Hays, "
     "Pietro Perona, Deva Ramanan, Piotr Dollár, and C. Lawrence "
     "Zitnick. 2014. Microsoft COCO: Common Objects in Context. In ECCV."),
    ("llama3", "Llama Team, AI @ Meta. 2024. The Llama 3 Herd of Models. "
     "arXiv:2407.21783."),
    ("lookout", "Google. Lookout: Assisted Vision. "
     "https://support.google.com/accessibility/android/answer/9031274"),
    ("macleod2017captions", "Haley MacLeod, Cynthia L. Bennett, Meredith "
     "Ringel Morris, and Edward Cutrell. 2017. Understanding Blind People's "
     "Experiences with Computer-Generated Captions of Social Media Images. "
     "In CHI."),
    ("madras2018defer", "David Madras, Toniann Pitassi, and Richard Zemel. "
     "2018. Predict Responsibly: Improving Fairness and Accuracy by Learning "
     "to Defer. In NeurIPS."),
    ("maynez2020faithfulness", "Joshua Maynez, Shashi Narayan, Bernd Bohnet,"
     "and Ryan McDonald. 2020. On Faithfulness and Factuality in Abstractive "
     "Summarization. In ACL."),
    ("meijer1992voice", "Peter B. L. Meijer. 1992. An Experimental System for "
     "Auditory Image Representations. IEEE Transactions on Biomedical "
     "Engineering 39, 2."),
    ("morris2016twitter", "Meredith Ringel Morris, Annuska Zolyomi, Catherine "
     "Yao, Sina Bahram, Jeffrey P. Bigham, and Shaun K. Kane. 2016. “With "
     "Most of It Being Pictures Now, I Rarely Use It”: Understanding "
     "Twitter's Evolving Accessibility to Blind Users. In CHI."),
    ("mozannar2020defer", "Hussein Mozannar and David Sontag. 2020. "
     "Consistent Estimators for Learning to Defer to an Expert. In ICML."),
    ("ollama", "Ollama. Ollama: Get Up and Running with Large Language Models "
     "Locally. https://ollama.com"),
    ("orcam", "OrCam. OrCam MyEye. https://www.orcam.com/"),
    ("parasuraman1997misuse", "Raja Parasuraman and Victor Riley. 1997. "
     "Humans and Automation: Use, Misuse, Disuse, Abuse. Human Factors 39, "
     "2."),
    ("parisi2022talm", "Aaron Parisi, Yao Zhao, and Noah Fiedel. 2022. TALM: "
     "Tool Augmented Language Models. arXiv:2205.12255."),
    ("povey2011kaldi", "Daniel Povey, Arnab Ghoshal, Gilles Boulianne, et al. "
     "2011. The Kaldi Speech Recognition Toolkit. In IEEE ASRU."),
    ("qin2024toolllm", "Yujia Qin, Shihao Liang, Yining Ye, Kunlun Zhu, Lan "
     "Yan, Yaxi Lu, Yankai Lin, Xin Cong, Xiangru Tang, Bill Qian, et al. "
     "2024. ToolLLM: Facilitating Large Language Models to Master 16000+ "
     "Real-World APIs. In ICLR."),
    ("radford2023whisper", "Alec Radford, Jong Wook Kim, Tao Xu, Greg "
     "Brockman, Christine McLeavey, and Ilya Sutskever. 2023. Robust Speech "
     "Recognition via Large-Scale Weak Supervision. In ICML."),
    ("ranftl2022midas", "René Ranftl, Katrin Lasinger, David Hafner, "
     "Konrad Schindler, and Vladlen Koltun. 2022. Towards Robust Monocular "
     "Depth Estimation: Mixing Datasets for Zero-Shot Cross-Dataset Transfer. "
     "IEEE TPAMI 44, 3."),
    ("redmon2016yolo", "Joseph Redmon, Santosh Divvala, Ross Girshick, and "
     "Ali Farhadi. 2016. You Only Look Once: Unified, Real-Time Object "
     "Detection. In CVPR."),
    ("sato2017navcog3", "Daisuke Sato, Uran Oh, Kakuya Naito, Hironobu "
     "Takagi, Kris Kitani, and Chieko Asakawa. 2017. NavCog3: An Evaluation "
     "of a Smartphone-Based Blind Indoor Navigation Assistant with Semantic "
     "Features in a Large-Scale Environment. In ASSETS."),
    ("schick2023toolformer", "Timo Schick, Jane Dwivedi-Yu, Roberto "
     "Dessì, Roberta Raileanu, Maria Lomeli, Luke Zettlemoyer, Nicola "
     "Cancedda, and Thomas Scialom. 2023. Toolformer: Language Models Can "
     "Teach Themselves to Use Tools. In NeurIPS."),
    ("scholak2021picard", "Torsten Scholak, Nathan Schucher, and Dzmitry "
     "Bahdanau. 2021. PICARD: Parsing Incrementally for Constrained "
     "Auto-Regressive Decoding from Language Models. In EMNLP."),
    ("seeingai", "Microsoft. Seeing AI: Talking Camera App for the Blind and "
     "Low Vision Community. https://www.seeingai.com/"),
    ("sendelbach2013alarm", "Sue Sendelbach and Marjorie Funk. 2013. Alarm "
     "Fatigue: A Patient Safety Concern. AACN Advanced Critical Care 24, 4."),
    ("soundscape", "Microsoft Research. Microsoft Soundscape: A Map Delivered "
     "in 3D Sound. "
     "https://www.microsoft.com/en-us/research/product/soundscape/"),
    ("stangl2020descriptions", "Abigale Stangl, Meredith Ringel Morris, and "
     "Danna Gurari. 2020. “Person, Shoes, Tree. Is the Person Naked?” "
     "What People with Vision Impairments Want in Image Descriptions. In "
     "CHI."),
    ("vanerp2005waypoint", "Jan B. F. van Erp, Hendrik A. H. C. van Veen, "
     "Chris Jansen, and Trevor Dobbins. 2005. Waypoint Navigation with a "
     "Vibrotactile Waist Belt. ACM Transactions on Applied Perception 2, 2."),
    ("vosk", "Alpha Cephei. Vosk Offline Speech Recognition API. "
     "https://alphacephei.com/vosk/"),
    ("wewalk", "WeWALK. WeWALK Smart Cane. https://wewalk.io/"),
    ("wickens2007imperfect", "Christopher D. Wickens and Stephen R. Dixon. "
     "2007. The Benefits of Imperfect Diagnostic Automation: A Synthesis of "
     "the Literature. Theoretical Issues in Ergonomics Science 8, 3."),
    ("willard2023guided", "Brandon T. Willard and Rémi Louf. 2023. "
     "Efficient Guided Generation for Large Language Models. "
     "arXiv:2307.09702."),
    ("wilson1927interval", "Edwin B. Wilson. 1927. Probable Inference, the "
     "Law of Succession, and Statistical Inference. Journal of the American "
     "Statistical Association 22, 158."),
    ("yao2023react", "Shunyu Yao, Jeffrey Zhao, Dian Yu, Nan Du, Izhak "
     "Shafran, Karthik Narasimhan, and Yuan Cao. 2023. ReAct: Synergizing "
     "Reasoning and Acting in Language Models. In ICLR."),
    ("zhao2020wayfinding", "Yuhang Zhao, Elizabeth Kupferstein, Hathaitorn "
     "Rojnirun, Leah Findlater, and Shiri Azenkot. 2020. The Effectiveness "
     "of Visual and Audio Wayfinding Guidance on Smartglasses for People "
     "with Low Vision. In CHI."),
]

NUMBER = {key: index for index, (key, _) in enumerate(REFERENCES, 1)}


def c(*keys):
    """In-text citation, ACM numeric."""
    return "[" + ", ".join(str(NUMBER[k]) for k in keys) + "]"


MONO = dict(font="Consolas", size=8.2)
IT = dict(italic=True)
BF = dict(bold=True)


def build():
    doc = Docx(title=TITLE, author=AUTHOR)

    doc.title_block(
        TITLE, SUBTITLE, AUTHOR,
        ["Add affiliation, Add city, Add country", "aditya17sep@gmail.com"])
    doc.section_break_two_columns()

    # -- abstract ---------------------------------------------------------
    doc.heading("", "Abstract")
    doc.body([
        "Sighted users silently discard a system's wrong answers; blind users "
        "cannot. We report BlindAssist, an offline camera-based guidance "
        "system for blind and low-vision users, and argue that ",
        ("selective abstention", IT),
        "—declining to speak when an output would be unreliable—is a "
        "first-class design objective at every layer, not an error-handling "
        "detail. We describe five mechanisms spanning perception "
        "(reliability-gated metric distance), planning (an openness threshold "
        "that can answer “stop”), transport (no-data distinguished "
        "from verified-clear), attention (proximity-gated warnings with an "
        "on-demand directional counterpart), and dialogue: a tool-mediated "
        "voice agent in which a local offline language model selects among "
        "fourteen deterministic capabilities and authors no guidance. On 200 "
        "labelled utterances, deterministic-first two-tier routing improves "
        "overall accuracy from 39.5% to 53.0% while keeping 100% on trained "
        "phrasings that an LLM-only router drops to 45.0%, and the same model "
        "asked to answer freely rather than to choose a tool fabricates "
        "perceptual content in 42.5% of responses. It also costs: "
        "out-of-scope over-triggering rises from 5.0% to 55.0%. A "
        "spoken-input condition, recorded by two speakers who did not author "
        "the set, then removes most of the agent layer's remaining advantage "
        "— two-tier's margin over the keyword baseline falls from 6.8 "
        "points to 0.9 — while the deterministic tier's abstention "
        "survives intact. We report both as negative results rather than "
        "tune them away.",
    ], first=True)

    doc.para([("CCS Concepts: ", BF),
              ("• Human-centered computing → Accessibility "
               "technologies; Ubiquitous and mobile computing; • "
               "Computing methodologies → Artificial intelligence.",
               dict(size=8.3))],
             align="both", before=70, after=40)
    doc.para([("Keywords: ", BF),
              ("blind and low-vision users, assistive technology, abstention, "
               "on-device machine learning, voice agents, tool use, "
               "hallucination", dict(size=8.3))],
             align="both", after=40)

    # -- 1 introduction ---------------------------------------------------
    doc.heading("1", "Introduction")
    doc.body(
        "A sighted person using an assistive app performs a silent, "
        "continuous audit. The app says “chair on your right”; they "
        "glance right; there is no chair; they discard the claim and lose "
        "nothing. That audit loop is invisible in design documents precisely "
        "because it is free.", first=True)
    doc.body([
        "For a blind user it does not exist. Every spoken claim is accepted "
        "or acted on, because there is no cheap channel to check it against. "
        "The asymmetry is not hypothetical: blind readers of "
        "machine-generated image captions have been shown to construct "
        "elaborate and confident interpretations of descriptions that were "
        "simply wrong, because nothing in the interaction offered grounds "
        "for doubt " + c("macleod2017captions") + ", and the same pattern "
        "recurs with generative assistants, whose fluency is itself read as "
        "a reliability signal " + c("adnin2024genai", "stangl2020descriptions")
        + ". The human-factors literature supplies the other half: unreliable "
        "automation does not merely fail to help, it drives disuse of the aid "
        "as a whole " + c("parasuraman1997misuse", "lee2004trust") + ", and "
        "below a reliability crossover an imperfect alert is worse than no "
        "alert at all " + c("wickens2007imperfect", "breznitz1984crywolf")
        + ".",
    ])
    doc.body([
        "This inverts a default that most interactive systems take for "
        "granted: ", ("answer something", IT),
        ". Under the asymmetry, a confidently wrong answer is not a degraded "
        "answer—it is worse than silence, because silence costs the user "
        "one query and a wrong answer costs them their calibration of when to "
        "trust the system at all.",
    ])
    doc.body(
        "This paper reports BlindAssist, a working offline guidance system (a "
        "Python reference implementation and an Android/Flutter port driven "
        "by a shared pure-logic core with mirrored test suites), and makes "
        "one architectural claim:")
    doc.block_quote([
        ("Under the verification asymmetry, selective abstention should be "
         "designed per layer, with layer-specific abstention "
         "criteria—not delegated to a single confidence threshold at "
         "the output.", IT)])
    doc.body([
        ("Contributions. ", BF),
        ("C1", BF), ", a cross-layer selective-abstention pattern "
        "instantiated five times with layer-specific criteria. ",
        ("C2", BF), ", a tool-mediated voice agent for a safety-critical "
        "speech channel: the model emits only a validated {tool, argument} "
        "pair drawn from a fixed registry, and every ", ("guidance", IT),
        " token originates in deterministic code or a fixed template. ",
        ("C3", BF), ", deterministic-first two-tier routing, which we show "
        "is not a latency optimisation with an accuracy cost but strictly "
        "better on the traffic it covers. ",
        ("C4", BF), ", a capability registry with enforced cross-site "
        "consistency across two languages. ",
        ("C5", BF), ", an evaluation, on a protocol frozen before the router "
        "was implemented, in which abstention rate and fabricated-perception "
        "count are first-class metrics rather than failure modes.",
    ])

    # -- 2 related work ---------------------------------------------------
    doc.heading("2", "Related work")
    doc.body([
        ("Assistive perception systems. ", BF),
        "Crowd- and cloud-backed visual question answering established the "
        "interaction " + c("bigham2010vizwiz") + " and the dataset tradition "
        + c("gurari2018vizwiz") + " this system inherits, against a backdrop "
        "of everyday interfaces whose visual content is simply unavailable "
        + c("morris2016twitter") + "; today's scene-description apps "
        + c("bemyeyes", "seeingai", "envision", "lookout") + " produce rich "
        "descriptions but are latency- and connectivity-dependent, verbose by "
        "design, and not built for continuous walking obstacle avoidance. "
        "Dedicated wearables " + c("orcam") + " give excellent near-field "
        "reading at hardware cost. Indoor navigation assistants localise the "
        "traveller rather than the objects in front of them "
        + c("ahmetovic2016navcog", "sato2017navcog3", "guerreiro2019cabot")
        + ", spatial-audio wayfinding operates at beacon granularity "
        + c("soundscape") + ", and electronic travel aids " + c("wewalk")
        + " give proximity without object identity or fine direction; surveys "
        + c("kuriakose2022review") + " and comparative studies "
        + c("zhao2020wayfinding") + " map the space. Work on blind users "
        "training their own recognisers " + c("kacorri2017teachable")
        + " shares our premise that the recogniser is not the whole of the "
        "problem. What we did not find in this literature is a system that "
        "treats ", ("declining to answer", IT), " as a designed and evaluated "
        "behaviour rather than an error path.",
    ], first=True)
    doc.body([
        ("Abstention. ", BF),
        "Classification with a reject option is old " + c("chow1970reject")
        + " and has a modern formal treatment in selective prediction "
        + c("elyaniv2010selective", "geifman2017selectivenet") + ", learning "
        "to defer " + c("madras2018defer", "mozannar2020defer") + ", and "
        "confidence estimation "
        + c("hendrycks2017baseline", "guo2017calibration") + ". That work "
        "asks when a ", ("model", IT), " should abstain, and answers with a "
        "score threshold. We treat abstention as an ", ("interface", IT),
        " property instead: five different layers of one system, each with a "
        "failure mode of its own, each abstaining on a criterion derived from "
        "that failure mode rather than from a shared confidence number.",
    ])
    doc.body([
        ("Hallucination containment. ", BF),
        "Fluent, unsupported generation is well characterised "
        + c("ji2023hallucination", "maynez2020faithfulness") + ", and models' "
        "own confidence signals are only partly informative "
        + c("kadavath2022know") + ". Tool use "
        + c("schick2023toolformer", "yao2023react", "parisi2022talm",
            "qin2024toolllm") + " and constrained decoding "
        + c("scholak2021picard", "willard2023guided") + " are standard "
        "engineering. Our step is not the mechanism but ", ("why", IT),
        " it is applied: for a consumer who cannot visually reject a wrong "
        "answer, containment is a safety property, and the design target is "
        "not “minimise fabricated perception” but “make it "
        "inexpressible”. We report the ablation that prices that "
        "constraint.",
    ])
    doc.body([
        ("Non-visual output. ", BF),
        "Obstacle sonification " + c("meijer1992voice", "csapo2013auditory")
        + " and vibrotactile direction " + c("vanerp2005waypoint")
        + " are established modalities; our contribution is not the modality "
        "but a single ordinal-localisation core that drives speech, stereo "
        "sonar and haptics with consistent semantics and shared anti-spam "
        "timing.",
    ])

    # -- 3 system ---------------------------------------------------------
    doc.heading("3", "System")
    doc.body([
        "A handset streams camera frames to a tethered laptop over Wi-Fi; the "
        "laptop runs YOLOv8s " + c("redmon2016yolo", "jocher2023ultralytics")
        + " trained on COCO " + c("lin2014coco") + " plus a small custom "
        "door/dustbin detector; the handset keeps every output modality "
        "native—speech, stereo-panned proximity sonar, haptics, "
        "grammar-constrained offline speech recognition "
        + c("vosk", "povey2011kaldi") + ", and on-device OCR. All guidance "
        "logic lives in a pure layer with no camera, no model and no clock of "
        "its own, mirrored 1:1 between Python and Dart with identical test "
        "suites (221 and 159 tests). Figure 1 shows the arrangement.",
    ], first=True)
    doc.body([
        "Objects are localised ", ("ordinally", IT), ": a 3×3 zone grid "
        "from the box centre, and a per-class proximity bucket (very close / "
        "close / medium / far) from box area. Metric distance exists but is "
        "gated (§4).",
    ])
    doc.body(
        "On-device inference measured ≈2.5 s per frame on the handset "
        "for both the GPU and NNAPI delegates, which is why inference is "
        "tethered. On the laptop GPU both detectors together cost 21 ms; "
        "total server time per frame during a field walk was ≈305 ms, so "
        "the dominant cost is frame reconstruction and transport rather than "
        "detection.")

    doc.image("f1_system.png", (FIGS / "f1_system.png").read_bytes(),
              COL, COL * 2.55 / 3.33)
    doc.caption("Figure 1.",
                "The two dashed arrows crossing the boundary are the whole "
                "safety argument: the router may point at a capability, but "
                "it may not speak through one. Tier 0 runs on the handset, so "
                "every trained phrase still works with the laptop switched "
                "off.")

    # -- 4 mechanisms -----------------------------------------------------
    doc.heading("4", "Five ways to decline")
    doc.body([
        ("Perception: reliability-gated metric distance. ", BF),
        "Distance comes from a pinhole model, d = h_real · F / h_box, "
        "and is spoken as “about N metres” only if three gates "
        "pass: the box does not touch a frame edge, the class name clears a "
        "confidence threshold, and the object is not already close. The "
        "edge-clip gate matters most: a truncated box reads ",
        ("falsely far", IT), ", so the error points in the dangerous "
        "direction, precisely for the nearest and largest objects. When any "
        "gate fails the system speaks the ordinal bucket instead. Learned "
        "monocular depth " + c("ranftl2022midas") + " would improve the "
        "estimate but not remove the need for the gate, since its failure "
        "cases are also silent.",
    ], first=True)
    doc.body([
        ("Planning: openness-thresholded path advice. ", BF),
        "Each of left/ahead/right is scored by the proximity rank of its ",
        ("closest", IT), " obstacle rather than by summed occupied area; the "
        "naive metric lets a far bulky object outrank a near small hazard and "
        "steers the user into it. Doorways are excluded from obstacle mass. "
        "If even the emptiest third holds a close obstacle, the system "
        "refuses to name a least-bad direction and says “Stop, no clear "
        "path”.",
    ])
    doc.body([
        ("Transport: absence is not a negative. ", BF),
        "A failed frame returns ", ("null", MONO), ", never an empty list. An "
        "empty list means a ", ("verified-clear", IT), " scene, and acting on "
        "it silences the sonar, resets escalation state, and makes Find "
        "report “not visible” for an object that may be directly "
        "ahead. On no-data the engine pauses guidance and says so.",
    ])
    doc.body([
        ("Attention: proximity-gated warnings with a pull counterpart. ", BF),
        "Added after the first field walk, where the verdict was “it "
        "keeps saying all the objects, it's too much of a cluster”. "
        "Continuous warnings now fire only at close range or nearer; "
        "everything removed from the push channel is reachable by asking (",
        ("check", MONO), ": “is there anything in front of me?”), "
        "answered by the same ordinal core, in tier 0, with no model and no "
        "network. The reasoning is the alarm-fatigue result "
        + c("sendelbach2013alarm", "breznitz1984crywolf") + " applied to a "
        "user whose only guidance channel is the one being flooded: an "
        "unheeded warning has negative value, because it spent attention and "
        "delivered nothing.",
    ])
    doc.body([
        ("Dialogue: routing abstention. ", BF),
        "Unknown tool, unknown object class, missing argument, prose instead "
        "of JSON, timeout or any exception all become abstention, and the "
        "clarifying question is selected from a fixed table by key rather "
        "than written by the model.",
    ])

    # -- 5 agent layer ----------------------------------------------------
    doc.heading("5", "The agent layer")
    doc.body([
        "BlindAssist's offline recogniser is grammar-constrained: only "
        "phrases in an explicit list can be transcribed ", ("at all", IT),
        ", so free speech is not mis-parsed—it is never heard. A trigger "
        "word therefore opens a dictation window, transcribed either by a "
        "local Whisper model " + c("radford2023whisper") + " on the laptop "
        "or, with the laptop off, by a second recogniser built on the same "
        "already-loaded 40 MB model with its grammar removed. The transcript "
        "goes first to the deterministic parser and only then, on a miss, to "
        "the router (Figure 2).",
    ], first=True)
    doc.body([
        ("The authority boundary. ", BF),
        "The model receives the tool registry, the class enumeration, a "
        "deterministic state block (visible classes with zone, proximity and "
        "count; mode; last announcement; object memory) and the utterance, "
        "and must return JSON. Everything after that treats its output as "
        "untrusted input. Multi-turn references such as “is it still "
        "there” therefore resolve against the detector's own output, "
        "never against a description: perception never re-enters the model.",
    ])
    doc.body([
        ("Where the boundary moved. ", BF),
        "The system as first built enforced the stronger rule—",
        ("no spoken token whatsoever", IT), " originated in the model. After "
        "the first field walk the developer-user asked for conversation: the "
        "ability to ask a question in their own words and be answered rather "
        "than routed. We granted exactly that. A reply travels in a separate "
        "channel that the executor cannot route through any capability; it is "
        "grounded in the same state block, length-capped and truncated at a "
        "sentence; loose prose emitted where a tool call belongs is still "
        "discarded; and one flag restores the absolute rule for the ablation. "
        "The honest formulation of C2 is therefore “no ", ("guidance", IT),
        " token originates in the model”, which is weaker than where we "
        "started, and we report it as weakened.",
    ])
    doc.body([
        ("Tiering across a network boundary. ", BF),
        "On the handset the two tiers fall on opposite sides of a Wi-Fi link. "
        "The client re-validates the server's reply against the same closed "
        "registry before executing, so the containment guarantee does not "
        "rest on trusting the transport, and a reply containing one unusable "
        "action is discarded whole—executing the half that happened to "
        "parse is itself an unverified action.",
    ])
    doc.body([
        ("Registry. ", BF),
        "Fourteen capabilities (Table 4) were previously declared in four "
        "places: a parser, its phrase list, a dispatcher, and the Dart "
        "equivalents. The sites had already drifted—the web dispatcher "
        "silently dropped five capabilities the parser could produce. One "
        "declarative table now drives the recogniser's phrase list at "
        "runtime, generates the model's tool schema, backs a single executor, "
        "and emits a committed manifest that both languages' test suites "
        "assert against field by field. We claim ",
        ("enforced consistency across sites", IT), ", not literal "
        "single-source generation: the field-validated parser is deliberately "
        "left in place rather than regenerated, because the regression risk "
        "of rewriting it exceeds the value of the stronger claim.",
    ])

    doc.image("f2_router.png", (FIGS / "f2_router.png").read_bytes(),
              COL, COL * 2.75 / 3.33)
    doc.caption("Figure 2.",
                "Two-tier routing. Every path except the amber reply channel "
                "produces text written by deterministic code or selected from "
                "a fixed template; the reply channel cannot reach any "
                "capability's output.")

    # -- 6 evaluation -----------------------------------------------------
    doc.heading("6", "Evaluation")
    doc.body(
        "The perception and guidance layers were checked first on seven "
        "recorded phone clips, which produced 31 announcements; every "
        "announcement saves an annotated keyframe, and all 31 were reviewed "
        "against the image. Direction was correct on 31/31 and there were no "
        "phantom announcements, while 6 of 31 carried a wrong class name with "
        "the warning behaviour still correct—the pattern that motivates "
        "speaking the generic word “obstacle” below a confidence "
        "threshold. These numbers are small and author-reviewed, and we "
        "report them as a sanity check on the deterministic core rather than "
        "as a perception result. The rest of this section concerns the "
        "dialogue layer.", first=True)
    doc.body([
        "The protocol and a set of 200 labelled utterances were frozen and "
        "committed ", ("before", IT), " the router was implemented, so the "
        "router could not be tuned against its own test set. Categories: ",
        ("canonical", IT), " (40, phrasings the grammar covers), ",
        ("paraphrase", IT), " (70), ", ("multi-intent", IT), " (20), ",
        ("out-of-scope", IT), " (40, gold label: abstain) and ",
        ("ambiguous", IT), " (30, gold depends on a state block encoded in "
        "the record). Out-of-scope records are plausible things a user would "
        "say to an assistive device—weather, calls, messages, time, "
        "battery—rather than nonsense strings, which would be easy to "
        "abstain on and would inflate the metric.",
    ])
    doc.body([
        "Configurations: keyword-only, LLM-only (tier 0 stubbed to always "
        "miss), and two-tier. Routing accuracy is exact match on the ",
        ("ordered", IT), " action list; a two-action utterance routed to one "
        "correct action scores zero, because the user asked for two things "
        "and got one. The ", ("over-trigger rate", IT), " is the fraction of "
        "out-of-scope utterances answered with any action, and is the safety "
        "metric of this layer. The fabrication check verifies that every "
        "executed spoken string is a member of the set the deterministic core "
        "could produce for that record, plus the fixed templates; the harness "
        "fails loudly otherwise. Intervals are Wilson "
        + c("wilson1927interval") + "; no significance testing between "
        "configurations is claimed at this set size, and the comparison is "
        "descriptive.",
    ])
    doc.body([
        ("The spoken condition. ", BF),
        "Two speakers who did not author the set read a stratified 60-record "
        "subset aloud, once each, in a normal room. Recordings were "
        "transcribed by the same recogniser the handset uses for open "
        "dictation, with the grammar removed, so this is the condition the "
        "deployed system actually operates in rather than a simulation of "
        "it. Utterance boundaries were recovered by aligning the recognised "
        "word stream to the known script; where fewer than a third of an "
        "utterance's words aligned, the record was dropped rather than paired "
        "with a transcript we could not trust. 107 transcripts over 59 "
        "records survived that gate. Because the gate removes the utterances "
        "the recogniser handled worst, the spoken-condition numbers below are "
        "if anything optimistic.",
    ])
    doc.body([
        "Model: ", ("llama3.2:3b", MONO), " " + c("llama3", "ollama")
        + " on the tether laptop. Criteria that would falsify each claim were "
        "recorded in the protocol before the runs.",
    ])

    # -- 7 results --------------------------------------------------------
    doc.heading("7", "Results")

    doc.table(
        [("Category", "n", "keyword", "LLM-only", "two-tier"),
         ("canonical", "40", "100.0", "45.0", "100.0"),
         ("paraphrase", "70", "0.0", "48.6", "47.1"),
         ("multi-intent", "20", "0.0", "30.0", "10.0"),
         ("out-of-scope", "40", "95.0", "47.5", "45.0"),
         ("ambiguous", "30", "3.3", "43.3", "43.3"),
         ("overall", "200", "39.5", "45.0", "53.0")],
        [0.95, 0.35, 0.68, 0.68, 0.67], aligns=["left"] + ["right"] * 4)
    doc.caption("Table 1.",
                "Routing accuracy (%), clean text, n = 200. Wilson 95% CIs on "
                "the overall row: keyword 33.0–46.4, LLM-only "
                "38.3–51.9, two-tier 46.1–59.8.")

    doc.image("f3_accuracy.png", (FIGS / "f3_accuracy.png").read_bytes(),
              COL, COL * 1.85 / 3.33)
    doc.caption("Figure 3.",
                "Routing accuracy by category, n = 200. For out-of-scope, "
                "“accuracy” means correctly abstaining. The keyword "
                "bars at zero are not degradation but absence: a grammar "
                "cannot hear what is not in its grammar.")

    doc.body("Three things in Table 1 matter more than the overall column.",
             first=True)
    doc.body([
        ("The baseline's shape is the motivation stated as data. ", BF),
        "It is perfect on the phrasings it was designed for and ",
        ("zero", IT), " on paraphrase and multi-intent—not degraded, "
        "absent.",
    ])
    doc.body([
        ("Tiering strictly dominates LLM-only. ", BF),
        "LLM-only loses 55% of the canonical category: the model mis-routes "
        "utterances the keyword parser gets right by construction, usually by "
        "substituting a plausible neighbour (", ("describe", MONO), " for ",
        ("count", MONO), ", ", ("walk", MONO), " for ", ("zones", MONO),
        "). Two-tier keeps 100% there because those utterances never reach "
        "the model, and still collects most of the paraphrase gain. The "
        "deterministic tier is not a latency optimisation with an accuracy "
        "cost; it is more accurate ", ("and", IT), " faster on the traffic it "
        "covers.",
    ])
    doc.body([
        ("The abstention collapse is the headline, and it is negative. ", BF),
        "The keyword baseline abstains on 95% of out-of-scope input for "
        "free—an unmatched utterance returns nothing. Both "
        "language-model configurations spend nearly all of it (Table 2): a 3B "
        "model choosing among fourteen tools nearly always finds one it "
        "likes. “Call my mum” becomes ", ("read", MONO),
        "; “what time is it” becomes ", ("clock", MONO),
        "; “take a photo” becomes ", ("walk", MONO), ". We report "
        "this unmitigated because the protocol was frozen before the router "
        "existed and tuning the prompt against this set is what the freeze "
        "forbids. It does not falsify C1 or C2—no run fabricated "
        "perception, and tier-0 abstention is intact for the traffic tier 0 "
        "covers—but it falsifies any reading of C5 in which adding a "
        "local model is a free improvement.",
    ])

    doc.table(
        [("", "keyword", "LLM-only", "two-tier"),
         ("abstained", "38", "19", "18"),
         ("answered anyway", "2", "21", "22"),
         ("over-trigger rate", "5.0%", "52.5%", "55.0%"),
         ("tier-0 hit, p50", "5 µs", "—", "5 µs"),
         ("tier-1 hit, p50", "—", "1172 ms", "1188 ms"),
         ("tier-1 hit, p95", "—", "1578 ms", "1500 ms"),
         ("served by tier 0", "30.0%", "0%", "30.0%"),
         ("conversational replies", "0", "4", "6")],
        [1.24, 0.70, 0.70, 0.69], aligns=["left"] + ["right"] * 3)
    doc.caption("Table 2.",
                "Out-of-scope behaviour (n = 40) and routing latency. Wilson "
                "95% CIs on the over-trigger rates: keyword "
                "1.4–16.5, LLM-only 37.5–67.1, two-tier "
                "39.8–69.3.")

    doc.body([
        "Both keyword over-triggers are substring collisions: “read my "
        "email” contains ", ("read", IT), "; “how do i get to the "
        "bus stop” contains ", ("stop", IT), ". They are the price of "
        "matching on keywords, and they are exactly the errors a router with "
        "sentence-level context should remove—it does not, because tier "
        "0 claims them before the model is consulted. That is the cost side "
        "of C3 stated plainly.",
    ], first=True)
    doc.body(
        "Per-call tier-1 latency is essentially identical across the two "
        "configurations (1172 vs 1188 ms at p50), so two-tier's latency "
        "advantage is entirely a question of how much traffic reaches the "
        "model: 30% of utterances are served at 5 µs, and the trained "
        "commands users issue most often are exactly that 30%. Tier 1 is "
        "usable for on-demand questions and unusable inside a continuous "
        "guidance loop; every capability here is on-demand, which is a fact "
        "about this system rather than a general result.")

    doc.image("f4_fabrication.png", (FIGS / "f4_fabrication.png").read_bytes(),
              COL, COL * 1.15 / 3.33)
    doc.caption("Figure 4.",
                "The same model, the same deterministic state block. Asked to "
                "choose a tool, it fabricated nothing in any configuration; "
                "asked to answer, it fabricated in 42.5% of responses. The "
                "zero is by construction, not by tuning; the 42.5% is a "
                "keyword-based lower bound counting invented objects only.")

    doc.body(
        "Figure 4 is the clearest result in the paper, and the character of "
        "the inventions is worse than the rate suggests. Asked to “find "
        "bottle” with a state block listing no bottle, the model "
        "replied:", first=True)
    doc.block_quote([
        ("“i'm walking in front of you, my cane tapping on the ground. "
         "i've stopped about 6 feet away from your right side. there's a "
         "small…”", IT)])
    doc.body(
        "It invents an object, a distance in feet, a bearing, and a "
        "first-person travelling companion with a cane. For a sighted user "
        "this is a curiosity to dismiss. For the user this system is built "
        "for it arrives in the same voice, at the same volume, with the same "
        "confidence as a real detection.")

    doc.subheading("7.1  What real speech does to all of this")
    doc.table(
        [("", "keyword", "keyword", "two-tier", "two-tier"),
         ("", "text", "spoken", "text", "spoken"),
         ("canonical", "100.0", "84.2", "100.0", "84.2"),
         ("paraphrase", "0.0", "0.0", "16.7", "13.0"),
         ("multi-intent", "0.0", "0.0", "8.3", "8.7"),
         ("out-of-scope", "91.7", "91.3", "41.7", "30.4"),
         ("ambiguous", "0.0", "0.0", "58.3", "52.6"),
         ("overall", "37.3", "34.6", "44.1", "35.5"),
         ("over-trigger", "8.3", "8.7", "58.3", "69.6")],
        [0.92, 0.60, 0.60, 0.60, 0.61], header_rows=2,
        aligns=["left"] + ["right"] * 4)
    doc.caption("Table 3.",
                "Accuracy (%) on the matched subset: the same 59 records, as "
                "written text and as 107 real transcripts from two speakers. "
                "The subset's category mix differs from the full set, so "
                "these columns compare only with each other, not with "
                "Table 1.")

    doc.body([
        "The spoken condition changes the conclusion, which is why the "
        "protocol specified it in advance. Three readings.",
    ], first=True)
    doc.body([
        ("The deterministic tier barely notices. ", BF),
        "Keyword accuracy falls 37.3 → 34.6 and its over-trigger rate is "
        "flat (8.3 → 8.7). A grammar that matches on a handful of "
        "content words degrades gracefully when the recogniser drops a "
        "function word.",
    ])
    doc.body([
        ("The agent layer's advantage mostly evaporates. ", BF),
        "Two-tier beats the baseline by 6.8 points on written text (44.1 vs "
        "37.3) and by 0.9 points on the same utterances spoken (35.5 vs "
        "34.6). The paraphrase coverage the agent exists to provide is "
        "largely destroyed upstream of it: a paraphrase is long, contains "
        "unconstrained vocabulary, and is exactly what a 40 MB open-dictation "
        "model transcribes worst. An evaluation on clean text substantially "
        "overstates what this layer delivers to a user who speaks to it.",
    ])
    doc.body([
        ("Recognition noise degrades abstention selectively. ", BF),
        "Under ASR the keyword configuration's out-of-scope abstention holds "
        "(91.7 → 91.3) while two-tier's falls (41.7 → 30.4), "
        "pushing over-triggering from 58.3% to 69.6%. A garbled out-of-scope "
        "utterance is not a signal to the model that it should decline; it is "
        "additional room for interpretation. The layer that abstains by "
        "construction keeps abstaining, and the layer that abstains by "
        "judgement abstains less exactly when the input got worse. That is "
        "the paper's thesis showing up as a measurement rather than an "
        "argument.",
    ])
    doc.body([
        ("A capability added after the freeze. ", BF),
        "The ", ("check", MONO), " capability was implemented after the set "
        "was committed. Two records are affected and neither was "
        "re-labelled: one paraphrase whose gold we consider superseded, and "
        "one ambiguous record whose failure mode changed from silent "
        "abstention to a confident answer to a different question—"
        "strictly worse, and the predictable cost of widening a keyword "
        "grammar. A third instance was caught by the frozen out-of-scope "
        "category before any user met it: the first implementation treated "
        "any “left” as a direction, so “how much battery is "
        "left” routed to a scene query, raising over-trigger to 7.5%. "
        "“Left” and “right” are ordinary English words; "
        "“ahead”, “front” and “forward” are "
        "not, so the rule now requires a positional lead-in for the "
        "ambiguous pair only.",
    ])

    # -- 8 discussion -----------------------------------------------------
    doc.heading("8", "Discussion and limitations")
    doc.body([
        ("No blind participants. ", BF),
        "The system has been field-walked by a single sighted developer. "
        "Every claim here about what is ", ("safer", IT), " is a design "
        "argument supported by mechanism and by deterministic tests, not by "
        "user data. A study with blind participants is the necessary next "
        "step and specifically the one that could falsify the premise: users "
        "may prefer a guessed answer to an abstention, and the over-trigger "
        "rate we optimise against may not be the quantity that matters to "
        "them.",
    ], first=True)
    doc.body([
        ("Over-triggering is measured, not solved. ", BF),
        "55% on text and 69.6% on speech is the largest open problem this "
        "evaluation exposes. Rejection examples in the prompt, a second-pass "
        "scope classifier, and a model-confidence gate "
        + c("hendrycks2017baseline") + " are all available; none is "
        "evaluated, because each would be tuning against a frozen set. A "
        "held-out set comes first.",
    ])
    doc.body([
        ("The spoken condition is small and gated. ", BF),
        "Two speakers, 59 records, 107 transcripts, one recogniser, one room. "
        "The alignment gate that recovers utterance boundaries drops the "
        "worst-recognised utterances, so the degradation reported in "
        "§7.1 is a floor on the true degradation, not an estimate of "
        "it. A larger panel, more rooms, and the Whisper path as a second "
        "recogniser arm would all sharpen it; none of them is likely to move "
        "the direction of the effect.",
    ])
    doc.body([
        ("One model, one machine. ", BF),
        "A second arm with a reasoning model (", ("qwen3:4b", MONO),
        ") returned no parseable tool call on 102 of 140 tier-1 calls at "
        "6–8 s each, so tier 1 contributed nothing and the run scored "
        "exactly the keyword baseline. The validation boundary degraded to "
        "fewer capabilities rather than to wrong ones, which is the designed "
        "behaviour, but the comparison is not informative about model size "
        "until thinking output is disabled.",
    ])
    doc.body([
        ("The clock mapping is camera-frame, not O&M. ", BF),
        "Frame width spans 10–2 o'clock over roughly a 60° field of "
        "view, so “2 o'clock” means the right frame edge, not the "
        "90° a trained traveller would turn. This needs relabelling or a "
        "genuine remapping before the system claims compatibility with "
        "Orientation & Mobility instruction.",
    ])
    doc.body([
        ("Distance is coarse and the fabrication detector is crude. ", BF),
        "Roughly ±30–40% at 5 m with an uncalibrated focal "
        "constant; the gating argument concerns ", ("when", IT), " to speak a "
        "number, not how good it is, but a one-time per-device calibration "
        "would strengthen any accuracy claim. The fabrication detector flags "
        "invented objects only, missing invented distances, bearings and "
        "counts—several of which appear in the samples it did flag. It "
        "is a lower bound.",
    ])
    doc.body([
        ("Chat replies are counted, not judged. ", BF),
        "They are excluded from the fabrication metric by definition and "
        "listed for inspection, but we do not measure whether they are "
        "correct or well-calibrated. They are now part of what the system "
        "says, so a user study would have to.",
    ])
    doc.body([
        ("Tether dependency. ", BF),
        "The remote-primary architecture assumes a laptop and a local "
        "network; §4 makes the failure safe, not absent. On-device "
        "viability awaits a lighter detector head or hardware whose delegate "
        "partitions the model cleanly.",
    ])

    # -- 9 ethics ---------------------------------------------------------
    doc.heading("9", "Ethics, positionality and availability")
    doc.body(
        "The author is a sighted student developer and is not a member of the "
        "population this system is built for. Nothing here was co-designed "
        "with blind users, and the one field walk was performed by the "
        "author. We have tried to make that limitation load-bearing rather "
        "than decorative: every safety claim is tied to a mechanism and a "
        "test that a reader can inspect, so that a blind participant study "
        "can falsify the design arguments rather than merely fail to confirm "
        "them. No human-subjects data was collected and no ethics approval "
        "was required for the work reported; a participant study is not "
        "attempted here precisely because doing it informally, with an "
        "unvalidated prototype and no approval, would be the wrong way to "
        "involve the population concerned. The two speakers who recorded the "
        "spoken condition read a fixed list of system commands, contributed "
        "voluntarily, and are identified only as A and B.", first=True)
    doc.body(
        "The system runs offline by design—detection on a locally "
        "tethered laptop, speech recognition, synthesis and OCR on the "
        "handset—so no camera frame, no utterance and no location leaves "
        "the user's own devices. The tether is an unencrypted local link, "
        "which is adequate for a prototype on a personal hotspot and would "
        "need transport security before any deployment.")
    doc.body([
        "Source code, the capability registry manifest, the frozen evaluation "
        "protocol, the 200-record labelled set and every run report are "
        "available at github.com/Aditya17-bot/object_detection_blind. "
        "Clean-condition results carry the eval-set SHA-256 prefix ",
        (CLEAN_HASH, MONO), "; adding the spoken transcripts changes it to ",
        (ASR_HASH, MONO), ", and only the transcripts differ between them.",
    ])

    # -- 10 conclusion ----------------------------------------------------
    doc.heading("10", "Conclusion")
    doc.body(
        "For users who cannot audit what a system tells them, abstention is "
        "not an error path—it is a feature that must be designed, "
        "implemented and measured at every layer where the system can be "
        "wrong. We showed five such designs in a working offline assistive "
        "system, each with criteria specific to its layer's failure mode, and "
        "extended the pattern to a voice agent whose language model may "
        "choose what the system does and never what it says about the world. "
        "The interesting claim is not that tool mediation prevents "
        "fabrication—it plainly does—but that the same principle "
        "that motivates it also explains a distance gate, a path threshold, a "
        "null-versus-empty distinction and a warning-rate ceiling three "
        "layers away. The spoken-input result sharpens rather than softens "
        "that: the mechanisms that abstain by construction were the ones "
        "still abstaining when the input degraded.", first=True)

    # -- registry table ---------------------------------------------------
    doc.table(
        [("Tool", "Argument", "Backed by"),
         ("walk", "—", "engine mode"),
         ("find", "class, required", "find_message"),
         ("describe", "—", "summarize_scene"),
         ("count", "class, required", "count_message"),
         ("recall", "class, required", "object memory"),
         ("path", "—", "clear_path"),
         ("check", "direction, required", "check_direction"),
         ("read", "—", "on-device OCR"),
         ("clock / zones", "—", "bearing style"),
         ("sonar", "on/off", "sonar controller"),
         ("mute", "on/off, required", "speech controller"),
         ("stop / repeat", "—", "speech controller"),
         ("abstain", "template key", "fixed template table")],
        [0.90, 1.20, 1.23], aligns=["left", "left", "left"])
    doc.caption("Table 4.",
                "The capability registry. One declarative table drives the "
                "recogniser's phrase list, the model's tool schema, the "
                "executor, and a manifest both languages' test suites assert "
                "against.")

    # -- references -------------------------------------------------------
    doc.heading("", "References")
    for index, (_, text) in enumerate(REFERENCES, 1):
        doc.para([(f"[{index}]  ", dict(size=7.6)), (text, dict(size=7.6))],
                 align="both", after=26, hanging=0.16 * 1440, line=200)

    out = HERE / "BlindAssist_paper.docx"
    doc.save(out)
    print(f"wrote {out}  ({out.stat().st_size // 1024} KB)")
    print(f"  {len(REFERENCES)} references, {len(doc.images)} figures")


if __name__ == "__main__":
    build()

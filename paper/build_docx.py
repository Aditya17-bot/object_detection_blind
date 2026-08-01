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
    doc.body(
        "A sighted person using an assistive app checks what it says almost "
        "without noticing, and when it is wrong they drop the claim and lose "
        "nothing. A blind person has no cheap way to run that check, so a "
        "confident wrong answer is accepted and acted on, and it costs more "
        "than silence would have. We built BlindAssist, an offline "
        "camera-based guidance system for blind and low-vision users, around "
        "that difference, and the design idea we want to argue for is that a "
        "system should be able to decline to answer at every layer where it "
        "can be wrong, with each layer deciding on its own terms rather than "
        "on one shared confidence score. We describe five such mechanisms, "
        "covering distance estimation, path advice, network failure, how often "
        "the system is allowed to interrupt, and finally a voice agent where a "
        "local offline language model chooses among fourteen deterministic "
        "capabilities and writes none of the guidance. On 200 labelled "
        "utterances, putting a keyword parser in front of the model raises "
        "overall routing accuracy from 39.5% to 53.0% and keeps 100% on the "
        "phrasings the parser already covers, which an LLM-only router drops "
        "to 45.0%, and the same model asked to answer in prose instead of "
        "choosing a tool invents perceptual content in 42.5% of its replies. "
        "The cost is that out-of-scope over-triggering rises from 5.0% to "
        "55.0%, though a sweep over five local models shows that collapse "
        "belongs to the small ones: at 9.2B parameters accuracy reaches 69.5% "
        "with over-triggering back down to 10.0%, at 6 s per query. We also "
        "recorded two speakers reading the same utterances aloud, and most of "
        "what the agent layer gained disappears, with its margin over the "
        "keyword baseline falling from 6.8 points to 0.9 while the "
        "deterministic layer's abstention barely moves. We report the negative "
        "results, and one finding we retracted after running a larger model, "
        "as they came out.", first=True)

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
        "A sighted person using an assistive app is running a check the whole "
        "time without thinking about it. The app says “chair on your "
        "right”, they glance right, there is no chair, and they drop the "
        "claim and carry on. Nothing in the design of the app has to account "
        "for that, because the check is free and it happens whether the "
        "designer planned it or not.", first=True)
    doc.body(
        "A blind user does not have that check. Every spoken claim is either "
        "accepted or acted on, because there is no cheap way to test it "
        "against anything, and this is not a hypothetical worry. Blind readers "
        "of machine-generated image captions have been observed building "
        "detailed and confident interpretations of descriptions that were "
        "simply wrong, since nothing in the interaction gave them a reason to "
        "doubt " + c("macleod2017captions") + ", and the same thing shows up "
        "again with generative assistants, where fluency itself gets read as a "
        "sign of reliability "
        + c("adnin2024genai", "stangl2020descriptions") + ". The "
        "human-factors literature has the other half of it: automation that is "
        "unreliable does not just fail to help, it makes people stop using the "
        "aid at all " + c("parasuraman1997misuse", "lee2004trust") + ", and "
        "past a certain point an imperfect alert leaves the user worse off "
        "than no alert would have "
        + c("wickens2007imperfect", "breznitz1984crywolf") + ".")
    doc.body(
        "So the default that most interactive systems are built on, which is "
        "to answer something rather than nothing, is the wrong default here. A "
        "confident wrong answer costs the user more than silence, because "
        "silence costs them one query and a wrong answer costs them their "
        "sense of when the system can be trusted at all, and that is much "
        "harder to get back.")
    doc.body(
        "This paper reports BlindAssist, a working offline guidance system "
        "with a Python reference implementation and an Android/Flutter port "
        "that share one pure-logic core and mirrored test suites. The claim we "
        "want to make about it is architectural:")
    doc.block_quote([
        ("Given that the user cannot verify what they are told, the ability to "
         "decline should be designed into every layer separately, with each "
         "layer deciding on criteria that come from its own failure mode, "
         "rather than being handed to one confidence threshold at the output.",
         IT)])
    doc.body(
        "We support that with five mechanisms already running in the system, "
        "an agent layer built on the same principle, and an evaluation that "
        "was frozen before the agent existed. The results include two findings "
        "that did not go the way we expected, and we have kept both.")

    # -- 2 related work ---------------------------------------------------
    doc.heading("2", "Related work")
    doc.body(
        "Crowd- and cloud-backed visual question answering set up the "
        "interaction " + c("bigham2010vizwiz") + " and the dataset tradition "
        + c("gurari2018vizwiz") + " that this system inherits, and it did so "
        "against a background where a lot of everyday visual content simply is "
        "not available to a blind user at all " + c("morris2016twitter")
        + ". The scene-description apps in use today "
        + c("bemyeyes", "seeingai", "envision", "lookout") + " give rich "
        "descriptions, but they depend on latency and connectivity, they are "
        "verbose by design, and they are not built for the continuous business "
        "of not walking into things. Dedicated wearables " + c("orcam")
        + " read near-field text very well at the price of buying hardware. "
        "Indoor navigation assistants locate the traveller rather than the "
        "objects in front of them "
        + c("ahmetovic2016navcog", "sato2017navcog3", "guerreiro2019cabot")
        + ", spatial-audio wayfinding works at beacon granularity "
        + c("soundscape") + ", and electronic travel aids " + c("wewalk")
        + " report proximity without saying what the object is or exactly "
        "where; surveys " + c("kuriakose2022review") + " and comparative "
        "studies " + c("zhao2020wayfinding") + " cover the space. Work on "
        "blind users training their own recognisers " + c("kacorri2017teachable")
        + " starts from the same premise we do, that getting the recogniser "
        "right is not the whole problem. What we could not find in this "
        "literature was a system where declining to answer is treated as a "
        "behaviour to be designed and measured rather than as the error path.",
        first=True)
    doc.body(
        "Abstention itself is old. Classification with a reject option goes "
        "back to Chow " + c("chow1970reject") + ", and it has a modern "
        "treatment in selective prediction "
        + c("elyaniv2010selective", "geifman2017selectivenet") + ", learning "
        "to defer " + c("madras2018defer", "mozannar2020defer") + " and "
        "confidence estimation "
        + c("hendrycks2017baseline", "guo2017calibration") + ". All of that "
        "asks when a model should abstain and answers with a threshold on a "
        "score. We are asking a different question, about an interface rather "
        "than a classifier, and our answer is that five separate layers of one "
        "system each have their own way of being wrong and should each abstain "
        "on grounds that come from that.")
    doc.body(
        "Fluent generation that is not supported by anything is well described "
        + c("ji2023hallucination", "maynez2020faithfulness") + ", and a "
        "model's own confidence signal only tells you so much "
        + c("kadavath2022know") + ". Tool use "
        + c("schick2023toolformer", "yao2023react", "parisi2022talm",
            "qin2024toolllm") + " and constrained decoding "
        + c("scholak2021picard", "willard2023guided") + " are ordinary "
        "engineering by now. What we are adding is the reason for applying "
        "them: when the person on the other end cannot look and see that the "
        "answer is wrong, containment stops being a quality measure and "
        "becomes a safety one, and the target changes from making fabricated "
        "perception rare to making it something the system cannot express. We "
        "report the ablation that shows what that costs.")
    doc.body(
        "Obstacle sonification " + c("meijer1992voice", "csapo2013auditory")
        + " and vibrotactile direction " + c("vanerp2005waypoint") + " are "
        "established, so the modalities are not our contribution. What we did "
        "was drive all of them from one ordinal localisation core, so speech, "
        "stereo sonar and haptics carry the same meaning and share the same "
        "timing rules.")

    # -- 3 system ---------------------------------------------------------
    doc.heading("3", "System")
    doc.body(
        "A handset streams camera frames to a tethered laptop over Wi-Fi, the "
        "laptop runs YOLOv8s " + c("redmon2016yolo", "jocher2023ultralytics")
        + " trained on COCO " + c("lin2014coco") + " together with a small "
        "custom door and dustbin detector, and everything the user actually "
        "hears or feels stays on the phone: speech, stereo-panned proximity "
        "sonar, haptics, grammar-constrained offline speech recognition "
        + c("vosk", "povey2011kaldi") + " and on-device OCR. All the guidance "
        "logic sits in a layer with no camera, no model and no clock of its "
        "own, and that layer is written twice, once in Python and once in "
        "Dart, with test suites that mirror each other (221 and 159 tests). "
        "Figure 1 shows how it fits together.", first=True)
    doc.body(
        "Objects are located ordinally, by which we mean a 3×3 zone grid "
        "taken from the box centre and a per-class proximity bucket of very "
        "close, close, medium or far taken from box area. A distance in metres "
        "does exist, but it is gated (§4).")
    doc.body(
        "Running the detectors on the phone measured about 2.5 s per frame for "
        "both the GPU and the NNAPI delegate, which is why inference is "
        "tethered at all. On the laptop GPU the two detectors together cost "
        "21 ms, while total server time per frame during a field walk was "
        "about 305 ms, so almost all of the remaining cost is reconstructing "
        "and moving the frame rather than looking at it.")

    doc.image("f1_system.png", (FIGS / "f1_system.png").read_bytes(),
              COL, COL * 2.55 / 3.33)
    doc.caption("Figure 1.",
                "The two dashed arrows crossing the boundary carry the whole "
                "safety argument. The router is allowed to point at a "
                "capability and is not allowed to speak through one. Tier 0 "
                "runs on the handset, so every trained phrase still works with "
                "the laptop switched off.")

    # -- 4 mechanisms -----------------------------------------------------
    doc.heading("4", "Five ways to decline")
    doc.subheading("4.1  Perception: distance that is gated on reliability")
    doc.body(
        "Distance comes out of a pinhole model, d = h_real · F / h_box, and it "
        "is spoken as “about N metres” only when three conditions "
        "hold, which are that the box does not touch a frame edge, that the "
        "class name clears a confidence threshold, and that the object is not "
        "already close. The first of those matters most. A box cut off by the "
        "edge of the frame is shorter than the object really is, so the model "
        "reads it as further away, and that error points the wrong way for "
        "exactly the nearest and largest things in the scene, which are the "
        "ones most likely to be clipped. When any of the three fails the "
        "system falls back to the ordinal bucket, which it can always say "
        "honestly. Learned monocular depth " + c("ranftl2022midas") + " would "
        "give a better estimate, but it would not remove the need for the "
        "gate, because its failure cases are quiet too.", first=True)

    doc.subheading("4.2  Planning: path advice with a threshold on openness")
    doc.body(
        "Each of left, ahead and right is scored by how close its nearest "
        "obstacle is, rather than by how much area is occupied in that third. "
        "Scoring by area inverts in a case that comes up constantly, where a "
        "bulky object further away outranks a small hazard close by, and the "
        "advice then points the user at the hazard. Doorways are left out of "
        "the obstacle mass, since a door is a thing to walk through. If even "
        "the emptiest third has a close obstacle in it, the system does not "
        "pick the least bad direction, it says “Stop, no clear path”, "
        "because a recommender that always names a direction has no way of "
        "saying that none of them is any good.", first=True)

    doc.subheading("4.3  Transport: absence is not the same as a negative")
    doc.body([
        "A frame that fails to come back returns ", ("null", MONO),
        " and never an empty list. An empty list means the scene was looked at "
        "and found clear, and acting on that when it is not true has three "
        "specific effects: the sonar goes quiet, which means “path "
        "clear”, the escalation state resets, and Find reports “not "
        "visible” for something that may be right in front of the user. On "
        "no data the engine pauses guidance and says that it has, rather than "
        "turning its own outage into a confident answer.",
    ], first=True)

    doc.subheading("4.4  Attention: fewer warnings, and a way to ask")
    doc.body([
        "This one came out of the first field walk rather than out of the "
        "design. The verdict was that it kept saying all the objects and it "
        "was too much of a cluster, which is the alarm-fatigue result "
        + c("sendelbach2013alarm", "breznitz1984crywolf") + " arriving in a "
        "setting where the channel being flooded is the only guidance channel "
        "the user has. A warning that is not heeded has negative value, since "
        "it spent attention and gave nothing back. Continuous warnings now "
        "fire only at close range or nearer, and everything taken out of that "
        "channel can still be asked for: ", ("check", MONO), " answers "
        "“is there anything in front of me?” from the same ordinal "
        "core, in tier 0, with no model and no network involved. A user who "
        "asks has by asking given the attention that the continuous channel is "
        "not allowed to assume.",
    ], first=True)

    doc.subheading("4.5  Dialogue: abstaining from routing")
    doc.body(
        "An unknown tool, an unknown object class, a missing argument, prose "
        "where JSON should be, a timeout, or any exception at all become an "
        "abstention, and even the clarifying question that gets asked is "
        "picked from a fixed table by key rather than written by the model.",
        first=True)

    # -- 5 agent layer ----------------------------------------------------
    doc.heading("5", "The agent layer")
    doc.body(
        "BlindAssist's offline recogniser is grammar-constrained, so only "
        "phrases in an explicit list can be transcribed at all, and free "
        "speech is therefore not mis-parsed, it is never heard in the first "
        "place. A trigger word opens a dictation window, which is transcribed "
        "either by a local Whisper model " + c("radford2023whisper") + " on "
        "the laptop or, with the laptop off, by a second recogniser built on "
        "the same 40 MB model that is already loaded with its grammar removed. "
        "The transcript goes to the deterministic parser first and only "
        "reaches the router if that misses (Figure 2).", first=True)
    doc.body(
        "The model is given the tool registry, the class enumeration, a "
        "deterministic state block listing the visible classes with zone, "
        "proximity and count along with the current mode, the last "
        "announcement and object memory, and the utterance, and it has to "
        "return JSON. Everything past that point treats what comes back as "
        "untrusted input. A reference like “is it still there” "
        "therefore gets resolved against what the detector saw and not against "
        "a description, so perception never goes back into the model.")
    doc.body(
        "We should say where the boundary moved, because it did. The system as "
        "first built enforced a stronger rule, that no spoken token whatsoever "
        "came from the model. After the first field walk the developer-user "
        "asked for conversation, by which he meant the ability to ask a "
        "question in his own words and get an answer instead of getting "
        "routed, and we granted that and nothing more. A reply travels in a "
        "separate channel that the executor cannot push through any "
        "capability, it is grounded in the same state block, it is "
        "length-capped and cut at a sentence, loose prose emitted where a tool "
        "call belongs is still thrown away, and one flag puts the absolute "
        "rule back for the ablation in §7.2. So the honest version of the "
        "claim is that no guidance token comes from the model, which is weaker "
        "than where we started, and we would rather say that than let the "
        "earlier wording stand.")
    doc.body(
        "On the handset the two tiers sit on opposite sides of a Wi-Fi link, "
        "and the client re-validates whatever the server sends against the "
        "same closed registry before executing any of it, so the containment "
        "guarantee does not depend on trusting the network. A reply with one "
        "unusable action in it is thrown away whole rather than partly "
        "executed, since running the half that happened to parse would itself "
        "be an unverified action.")
    doc.body(
        "Fourteen capabilities (Table 5) used to be declared in four places, a "
        "parser, its phrase list, a dispatcher and the Dart equivalents, and "
        "those places had already drifted apart: the web dispatcher had "
        "silently stopped handling five capabilities that the parser could "
        "still produce. One declarative table now drives the recogniser's "
        "phrase list at runtime, generates the model's tool schema, backs a "
        "single executor, and emits a committed manifest that both test suites "
        "check field by field. We claim consistency that is enforced across "
        "sites, not single-source generation, because the field-validated "
        "parser is left in place on purpose rather than being regenerated from "
        "the table, and rewriting it would risk more than the stronger claim "
        "is worth.")

    doc.image("f2_router.png", (FIGS / "f2_router.png").read_bytes(),
              COL, COL * 2.75 / 3.33)
    doc.caption("Figure 2.",
                "Two-tier routing. Every path except the amber reply channel "
                "produces text that was written by deterministic code or "
                "picked from a fixed template, and the reply channel cannot "
                "reach any capability's output.")

    # -- 6 evaluation -----------------------------------------------------
    doc.heading("6", "Evaluation")
    doc.body(
        "Before any of the routing work, the perception and guidance layers "
        "were checked on seven recorded phone clips, which between them "
        "produced 31 announcements. Every announcement saves an annotated "
        "keyframe and all 31 were reviewed against the image. Direction was "
        "right on 31 of 31 and no announcement was made for something that was "
        "not there, while 6 of the 31 used a wrong class name and still gave "
        "the correct warning, which is the pattern behind saying the generic "
        "word “obstacle” when confidence is below threshold. These are "
        "small numbers reviewed by the author, so we report them as a sanity "
        "check on the deterministic core and not as a perception result.",
        first=True)
    doc.body(
        "The protocol and a set of 200 labelled utterances were frozen and "
        "committed before the router was written, so that the router could not "
        "be tuned against its own test set. The categories are canonical (40, "
        "phrasings the grammar covers), paraphrase (70), multi-intent (20), "
        "out-of-scope (40, where the gold label is to abstain) and ambiguous "
        "(30, where the gold answer depends on a state block stored in the "
        "record). The out-of-scope records are plausible things somebody would "
        "say to an assistive device, so weather, calls, messages, time and "
        "battery, rather than nonsense strings, because nonsense is easy to "
        "abstain on and would have made the metric look better than it is.")
    doc.body(
        "There are three configurations, keyword-only, LLM-only with tier 0 "
        "stubbed to always miss, and two-tier. Routing accuracy is exact match "
        "on the ordered action list, and a two-action utterance routed to one "
        "correct action scores zero, because the user asked for two things and "
        "got one. The over-trigger rate is the share of out-of-scope "
        "utterances that got answered with any action at all, and it is the "
        "safety metric for this layer. The fabrication check confirms that "
        "every spoken string that was executed is one the deterministic core "
        "could have produced for that record, or a fixed template, and the "
        "harness fails loudly on anything else. Intervals are Wilson "
        + c("wilson1927interval") + ", and we are not claiming significance "
        "between configurations at this set size, the comparison is "
        "descriptive.")
    doc.body(
        "Two speakers who did not author the set read a stratified 60-record "
        "subset aloud, once each, in a normal room. The recordings were "
        "transcribed by the same recogniser the handset uses for open "
        "dictation, with the grammar removed, so this is the condition the "
        "system actually runs in rather than a simulation of it. Utterance "
        "boundaries were recovered by aligning the recognised word stream to "
        "the known script, and where fewer than a third of an utterance's "
        "words aligned the record was dropped instead of being paired with a "
        "transcript we could not trust, which left 107 transcripts over 59 "
        "records. That gate takes out the utterances the recogniser handled "
        "worst, so the spoken numbers below are if anything a little kind to "
        "the system.")
    doc.body([
        "Unless stated otherwise the model is ", ("llama3.2:3b", MONO), " "
        + c("llama3", "ollama") + " under Ollama on the tether laptop. What "
        "would falsify each claim was written into the protocol before any of "
        "the runs.",
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
                "accuracy means correctly abstaining. The keyword bars sitting "
                "at zero are not degradation, they are absence, since a "
                "grammar cannot hear what is not in its grammar.")

    doc.body(
        "The overall column in Table 1 is the least interesting part of it.",
        first=True)
    doc.body(
        "The shape of the keyword row is really the motivation for this work "
        "restated as data, since it is perfect on the phrasings it was built "
        "for and sits at zero on paraphrase and multi-intent, and zero there "
        "is absence rather than degradation.")
    doc.body([
        "Putting the parser in front of the model beats using the model alone, "
        "and it does so where we expected. LLM-only loses 55% of the canonical "
        "category, because the model mis-routes utterances the parser gets "
        "right by construction, usually by picking a plausible neighbour such "
        "as ", ("describe", MONO), " for ", ("count", MONO), " or ",
        ("walk", MONO), " for ", ("zones", MONO), ". Two-tier holds 100% there "
        "because those utterances never reach the model at all, and it still "
        "picks up most of the paraphrase gain, so the deterministic tier is "
        "both faster and more accurate on the traffic it covers.",
    ])
    doc.body([
        "The part we did not expect is what happens to abstention. The keyword "
        "baseline abstains on 95% of out-of-scope input and gets that for "
        "nothing, because an utterance it cannot match returns nothing at all, "
        "and both language-model configurations spend almost all of it "
        "(Table 2). A 3B model choosing among fourteen tools will nearly "
        "always find one it likes, so “call my mum” becomes ",
        ("read", MONO), ", “what time is it” becomes ",
        ("clock", MONO), ", and “take a photo” becomes ",
        ("walk", MONO), ". We are reporting that unmitigated, because the "
        "protocol was frozen before the router existed and tuning the prompt "
        "against this set is the thing the freeze exists to prevent. It does "
        "not undo the containment result, since no run fabricated perception "
        "and tier-0 abstention is untouched for the traffic tier 0 covers, but "
        "it does rule out any reading in which adding a local model is free.",
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
        "Both of the keyword over-triggers are substring collisions, since "
        "“read my email” contains ", ("read", IT), " and “how do "
        "i get to the bus stop” contains ", ("stop", IT), ". They are what "
        "matching on keywords costs, and they are exactly the sort of error a "
        "router with sentence-level context ought to clean up, except that it "
        "does not, because tier 0 claims them before the model is ever "
        "consulted. That is the other side of putting the parser first and we "
        "would rather state it than leave it out.",
    ], first=True)
    doc.body(
        "Per-call latency at tier 1 is much the same in both configurations, "
        "1172 against 1188 ms at the median, so two-tier's advantage there is "
        "entirely about how much traffic reaches the model rather than how "
        "fast the model is. 30% of utterances are served at 5 µs, and that 30% "
        "is made up of the commands users issue most often. Tier 1 is usable "
        "for a question the user asked and unusable inside the continuous "
        "guidance loop, and every capability here happens to be the former, "
        "which is a fact about this system rather than a general result.")

    doc.image("f4_fabrication.png", (FIGS / "f4_fabrication.png").read_bytes(),
              COL, COL * 1.15 / 3.33)
    doc.caption("Figure 4.",
                "The same model with the same deterministic state block. Asked "
                "to choose a tool it fabricated nothing in any configuration; "
                "asked to answer, it fabricated in 42.5% of replies. The zero "
                "comes from construction rather than tuning, and the 42.5% is "
                "a keyword-based lower bound that only counts invented "
                "objects.")

    doc.body(
        "Figure 4 is the cleanest thing in the paper, and what the model "
        "invents is worse than the rate makes it sound. Asked to “find "
        "bottle” with a state block that listed no bottle, it replied:",
        first=True)
    doc.block_quote([
        ("“i'm walking in front of you, my cane tapping on the ground. "
         "i've stopped about 6 feet away from your right side. there's a "
         "small…”", IT)])
    doc.body(
        "It has invented an object, a distance in feet, a bearing, and a "
        "first-person travelling companion carrying a cane. A sighted user "
        "would notice and dismiss it. The user this system is for gets it in "
        "the same voice, at the same volume, with the same confidence as a "
        "real detection.")

    doc.subheading("7.1  What real speech does to all of this")
    doc.table(
        [("", "accuracy", "", "over-trigger", ""),
         ("configuration", "text", "spoken", "text", "spoken"),
         ("keyword only", "37.3", "34.6", "8.3", "8.7"),
         ("two-tier, 3.2B", "44.1", "35.5", "58.3", "69.6"),
         ("two-tier, 9.2B", "52.5", "48.6", "25.0", "21.7")],
        [1.05, 0.53, 0.53, 0.53, 0.53], header_rows=2,
        aligns=["left"] + ["right"] * 4)
    doc.caption("Table 3.",
                "Percentages on the matched subset, meaning the same 59 "
                "records scored first as written text and then as the 107 real "
                "transcripts from two speakers. The subset's category mix is "
                "different from the full set, so these figures compare with "
                "each other and not with Table 1, and the per-category "
                "breakdown is in the run reports.")

    doc.body(
        "The spoken condition changes what we can claim, which is why the "
        "protocol asked for it in advance.", first=True)
    doc.body(
        "The deterministic tier barely reacts to it. Keyword accuracy goes "
        "from 37.3 to 34.6 and its over-trigger rate is flat, 8.3 against 8.7, "
        "because a grammar matching on a few content words still matches when "
        "the recogniser drops a function word, and “how much battery is "
        "left” came back as “how much batteries left” and still "
        "abstained.")
    doc.body(
        "Most of what the agent layer was buying goes away. Two-tier beats the "
        "baseline by 6.8 points on written text, 44.1 against 37.3, and by 0.9 "
        "points on the same utterances spoken, 35.5 against 34.6. The "
        "paraphrase coverage that the agent exists to provide is mostly "
        "destroyed before it gets there, because a paraphrase is long and full "
        "of unconstrained vocabulary and that is exactly what a 40 MB "
        "open-dictation model transcribes worst. An evaluation on clean text "
        "therefore overstates what this layer gives a user who speaks to it, "
        "and we would not have known that if the protocol had not asked for "
        "the condition.")
    doc.body(
        "The third thing is one we thought we had found and then did not. The "
        "keyword configuration's over-trigger rate is stable under recognition "
        "noise, 8.3 against 8.7, while two-tier on the 3B model goes from "
        "58.3% to 69.6%, and we wrote that up as the deterministic layer "
        "keeping its abstention while the model layer loses exactly when the "
        "input gets harder to judge. It would have been the neatest result in "
        "the paper. Then we ran both conditions on the 9.2B model and its "
        "over-trigger rate went from 25.0% to 21.7%, which is flat or a little "
        "better rather than worse, so whatever we were looking at was not a "
        "property of language models under noise.")
    doc.body(
        "It is also worth saying how thin these particular numbers are. The "
        "out-of-scope slice of the matched subset is 12 records as text and 23 "
        "transcripts as speech, and the Wilson intervals on the 3B pair "
        "overlap each other comfortably, so that pair on its own would not "
        "have supported the claim either. What survives is that the keyword "
        "tier's abstention does not move when the input degrades, which we can "
        "say because it is the same parser matching the same keywords, and "
        "that we do not have the sample to say what happens to the model "
        "tier's. We are leaving the version we got wrong visible here, because "
        "it was the result we most wanted and that is exactly when a frozen "
        "protocol earns its keep.")

    doc.subheading("7.2  Putting the absolute rule back, and model size")
    doc.body([
        "The numbers above raised two questions and both are answerable with "
        "models that were already sitting on the laptop. The first is the "
        "ablation the design promised, where ", ("allow_chat", MONO), " is "
        "turned off so that no spoken token at all can come from the model, "
        "which is the rule the system started with. It scored 53.0% overall "
        "with a 55.0% over-trigger rate, identical to the shipped "
        "configuration on both counts. Conversational replies happened 6 times "
        "in 200 and a reply carries no action, so it already scored as an "
        "abstention. Opening that channel gave the user something and cost the "
        "routing metrics nothing, and it also fixed nothing.",
    ], first=True)
    doc.body([
        "The second is whether the over-triggering is about model size, and "
        "here we got it wrong the first time. We ran ", ("llama3.2:1b", MONO),
        " and it over-triggered at 55.0% against 3B's 55.0%, so we wrote that "
        "the obvious explanation had failed its first test. Then we ran the "
        "rest of what was on the machine, and Table 4 is what came back.",
    ])

    doc.table(
        [("model", "params", "overall", "paraphr.", "over-trig.", "p50"),
         ("keyword only", "—", "39.5", "0.0", "5.0", "5 µs"),
         ("llama3.2:1b", "1.2B", "49.5", "44.3", "55.0", "891 ms"),
         ("llama3.2:3b", "3.2B", "53.0", "47.1", "55.0", "1188 ms"),
         ("qwen3:4b", "4.0B", "40.5", "0.0", "5.0", "2344 ms"),
         ("qwen2.5-coder:7b", "7.6B", "65.0", "50.0", "10.0", "3407 ms"),
         ("gemma2", "9.2B", "69.5", "62.9", "10.0", "6015 ms")],
        [0.92, 0.38, 0.45, 0.45, 0.50, 0.45], size=7.4,
        aligns=["left"] + ["right"] * 5)
    doc.caption("Table 4.",
                "The same two-tier configuration and the same frozen set, "
                "across every local model on the laptop. Accuracy figures are "
                "percentages and p50 is tier-1 routing latency. No run leaked "
                "a guidance string in any configuration.")

    doc.body(
        "Over-triggering is flat at 55.0% across 1.2B and 3.2B and then falls "
        "to 10.0% at 7.6B and 9.2B, while overall accuracy climbs to 69.5%. So "
        "the abstention collapse we reported above is a property of the small "
        "models we happened to start with rather than something tiering does, "
        "and we would not have found that if we had stopped at the first "
        "comparison. Against the keyword baseline, gemma2 buys 30 points of "
        "accuracy for 5 points of abstention, which is a trade we did not "
        "expect to be able to offer.", first=True)
    doc.body(
        "What it costs is time. That model does not fit in 4 GB of VRAM, so it "
        "runs partly on the CPU and takes 6015 ms at the median and 10125 ms "
        "at p95 to route one utterance. A blind user standing still for ten "
        "seconds waiting for an answer is a different kind of failure from a "
        "wrong answer, but it is still a failure, and it is the reason we "
        "cannot simply recommend the biggest model and stop. The trade-off did "
        "not go away when we scaled up, it moved from accuracy against "
        "abstention to accuracy against latency.")
    doc.body([
        "One row in that table is a trap and we want to flag it rather than "
        "let it be read straight. ", ("qwen3:4b", MONO), " has the best "
        "over-trigger rate in the table at 5.0%, and it means nothing. Only 2 "
        "utterances out of 200 produced a usable tool call at all, 138 "
        "abstained, and its 40.5% overall is the keyword baseline plus one "
        "record. What that column is showing is tier 0 seen through a model "
        "that contributes almost nothing, and reading it as caution would be "
        "exactly backwards. It is worth something as a safety observation "
        "though, because the validation boundary held and the system degraded "
        "to fewer capabilities rather than to wrong ones, which is what it is "
        "built to do.",
    ])
    doc.body(
        "The obvious confound is that these are four different model families "
        "and not one family scaled up, so what the table really shows is that "
        "the collapse is not universal rather than that it is a clean function "
        "of parameter count. The two llama3.2 sizes are the only within-family "
        "pair we have and they are identical on the safety metric.")

    # -- 8 discussion -----------------------------------------------------
    doc.heading("8", "Discussion and limitations")
    doc.body(
        "The system has been field-walked by one sighted developer, so "
        "everything in this paper about what is safer is a design argument "
        "backed by mechanism and by tests somebody can go and read, and not by "
        "data from the people it is for. A study with blind participants is "
        "the obvious next step, and it is also the thing most likely to "
        "overturn the premise, since users may well prefer a guess to an "
        "abstention, and the over-trigger rate we have been optimising against "
        "may not be what matters to them. We do not know.", first=True)
    doc.body(
        "Over-triggering is still the biggest open problem here, but §7.2 "
        "narrows it. At 3B it is 55% on text and 69.6% on speech, and at 9.2B "
        "it is 10% on text, so what we need is not necessarily a new mechanism "
        "but a model we can afford to run, and at six seconds a query we "
        "cannot afford that one yet. Rejection examples in the prompt, a "
        "second pass that classifies whether the request is in scope, and a "
        "confidence gate on the model " + c("hendrycks2017baseline") + " are "
        "all still available and none of them is evaluated, because each would "
        "mean tuning against a frozen set, so a held-out set has to come "
        "first either way.")
    doc.body(
        "The spoken condition is two speakers, 59 records, 107 transcripts, "
        "one recogniser and one room. Neither speaker is a blind user and "
        "neither had used the system. The alignment gate drops the utterances "
        "the recogniser handled worst, so what we report is a floor on the "
        "degradation rather than an estimate of it. A bigger panel, more rooms "
        "and the Whisper path as a second recogniser would all sharpen it, "
        "though none of them is likely to reverse the direction, because the "
        "mechanism does not depend on how many speakers there are.")
    doc.body([
        "The five models in §7.2 are four different families rather than one "
        "family scaled up, so the table shows that the abstention collapse is "
        "not universal and does not show it as a clean function of parameter "
        "count. The only within-family pair we have is 1.2B against 3.2B and "
        "they are identical on the safety metric. A proper sweep inside one "
        "family is the obvious next run. The reasoning model, ",
        ("qwen3:4b", MONO), ", is a separate problem: it returned nothing "
        "parseable on almost every tier-1 call, first at 6–8 s each with its "
        "thinking output on and then again after we switched that off, so it "
        "sits in the table contributing 2 usable calls out of 200. Its "
        "validation boundary held and degraded to fewer capabilities rather "
        "than to wrong ones, which is what it is for, but nothing else in that "
        "row should be read as a result.",
    ])
    doc.body(
        "The clock mapping is a camera-frame clock rather than an Orientation "
        "and Mobility one. Frame width covers 10 to 2 o'clock over roughly a "
        "60° field of view, so “2 o'clock” means the right-hand edge "
        "of the frame and not the 90° a trained traveller would turn, and "
        "this needs relabelling or a real remapping before the system claims "
        "to fit O&M training.")
    doc.body(
        "Distance is coarse, roughly ±30–40% at 5 m with an uncalibrated "
        "focal constant, though the gating argument is about when to say a "
        "number rather than how good the number is, and a one-off per-device "
        "calibration would help any accuracy claim. The fabrication detector "
        "only flags invented objects, so it misses invented distances, "
        "bearings and counts, several of which turn up in the samples it did "
        "flag, and the number is a lower bound.")
    doc.body(
        "Conversational replies get counted and listed for inspection and "
        "excluded from the fabrication metric by definition, but we never "
        "measure whether they are right or well-calibrated, and they are part "
        "of what the system says now, so a user study would have to.")
    doc.body(
        "Finally, the remote-primary architecture assumes a laptop and a local "
        "network. §4 makes that failure safe rather than absent, and running "
        "on the phone alone waits on either a lighter detector head or "
        "hardware whose delegate partitions the model cleanly.")

    # -- 9 ethics ---------------------------------------------------------
    doc.heading("9", "Ethics, positionality and availability")
    doc.body(
        "The author is a sighted student developer and is not a member of the "
        "population this system is built for. None of it was co-designed with "
        "blind users and the one field walk was done by the author. We have "
        "tried to make that limitation do some work rather than just sit in a "
        "list, by tying every safety claim to a mechanism and a test that a "
        "reader can go and inspect, so that a study with blind participants "
        "could actually falsify the design arguments instead of merely failing "
        "to confirm them. No human-subjects data was collected and no ethics "
        "approval was needed for what is reported here, and a participant "
        "study is not attempted precisely because running one informally, with "
        "an unvalidated prototype and no approval, would be the wrong way to "
        "involve these users. The two speakers who recorded the spoken "
        "condition read a fixed list of system commands, took part "
        "voluntarily, and are identified only as A and B.", first=True)
    doc.body(
        "The system runs offline by design, with detection on a locally "
        "tethered laptop and speech recognition, synthesis and OCR on the "
        "handset, so no camera frame, no utterance and no location leaves the "
        "user's own devices, and the language model is local as well. The "
        "tether itself is an unencrypted local link, which is fine for a "
        "prototype on a personal hotspot and would need transport security "
        "before anybody deployed it.")
    doc.body([
        "Source code, the capability registry manifest, the frozen evaluation "
        "protocol, the 200-record labelled set and every run report are at "
        "github.com/Aditya17-bot/object_detection_blind. Clean-condition "
        "results carry the eval-set SHA-256 prefix ", (CLEAN_HASH, MONO),
        ", and appending the spoken transcripts changes it to ",
        (ASR_HASH, MONO), " with only the transcripts differing between the "
        "two. Any number quoted from a set with a different hash is not "
        "comparable.",
    ])

    # -- 10 conclusion ----------------------------------------------------
    doc.heading("10", "Conclusion")
    doc.body(
        "For a user who cannot check what a system tells them, being able to "
        "decline is not the error path, it is a feature that has to be "
        "designed, built and measured at every layer where the thing can be "
        "wrong. We showed five of those in a working offline assistive system, "
        "each deciding on grounds that come from its own failure mode, and "
        "extended the idea to a voice agent whose language model gets to "
        "choose what the system does and never what it says about the world. "
        "The claim worth making is not that tool mediation prevents "
        "fabrication, which it plainly does, but that the same principle also "
        "explains a distance gate, a path threshold, a null-versus-empty "
        "distinction and a ceiling on how often the system speaks, three "
        "layers away from each other. What we cannot yet tell you is whether "
        "abstaining by construction holds up better than abstaining by "
        "judgement when the input gets worse. We thought we had measured that "
        "and a larger model took it back, and finding out properly needs a "
        "held-out set and more speakers than two.", first=True)

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
    doc.caption("Table 5.",
                "The capability registry. One declarative table drives the "
                "recogniser's phrase list, the model's tool schema, the "
                "executor, and a manifest that both languages' test suites "
                "check against.")
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

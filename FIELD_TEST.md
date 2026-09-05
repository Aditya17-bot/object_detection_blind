# BlindAssist — Field Test Protocol (the final validation walk)

Goal: prove the full phone app works end-to-end in a real room — detection,
direction accuracy, timing, voice control, and the failure behaviors — and
collect the numbers EVALUATION.md still needs from a live device.

## Setup (5 min)

1. **Laptop**: connect to the phone's hotspot (or both on the same Wi-Fi).
2. Start the server: `venv\Scripts\python.exe infer_server.py`
   - Expect: `Custom model loaded: ['door', 'dustbin', 'stairs']` and
     `UDP discovery on 5002`. If "Custom model unavailable" appears, the app
     will say "door detection unavailable" — fix before walking.
   - First run: allow it through the Windows firewall prompt (both checkboxes).
3. **Phone**: open BlindAssist. Expect, in order: "Starting BlindAssist" →
   "Walk mode. Say find bottle, walk mode, or describe."
   - No IP editing needed — the app finds the laptop by UDP broadcast.
   - If it says "Cannot reach the laptop server, retrying": server not up yet
     or wrong network; it keeps retrying every 5 s, no restart needed.
4. Watch the laptop console: each frame logs `/infer ... -> N dets in X ms`.
   That X is the server-side time; note the typical value.

## Record for EVALUATION.md

- FPS shown in the app's status pill after ~1 min of walking.
- Typical server ms/frame from the console.
- Subjective lag: walk toward a chair — does the warning arrive within ~1 s
  of it filling the view?

## Walk scenarios (~15 min)

Each scenario: note what was SPOKEN vs what was TRUE. A direction is correct
if the object really was in the spoken zone/clock position.

1. **Walk mode corridor**: 2 obstacles flanking a clear path + 1 obstacle
   dead center further on. Expect: flanking objects quiet (or brief), the
   center obstacle announced and ESCALATING ("very close... move slightly
   left/right") as you approach.
2. **Door**: approach a doorway from ~4 m. Expect "Door" announcements by
   name (never generic "obstacle" — trusted-name gate).
3. **Find mode**: "find bottle" with a bottle placed at a known spot. Expect
   location updates as you turn, distance ("about N meters") when medium/far,
   sonar beeps leading toward it. Hide the bottle: expect "not visible" once,
   then "Still looking for bottle" reminders.
4. **Clear path**: stand facing the room, say "which way". Check the answer
   against reality.
5. **Voice round**: "how many chairs", "where is the cup", "describe",
   "sonar on", "mute", "unmute", "read" on a printed label, "stop" mid
   read-out, "repeat".
6. **Failure drill (important)**: mid-walk, kill the server (Ctrl+C).
   Expect within ~5 s: "Connection lost, guidance paused" and sonar SILENT
   (no fake all-clear). Restart the server: "Guidance restored" without
   touching the phone.
7. **Pocket drill**: press the power button (screen off), turn it back on.
   Expect "Resuming" and detections continuing.
8. **Agent round** (only if the server runs with `--agent-model`): say
   "assistant", wait for "Yes?", then ask five things in your OWN words —
   e.g. "is there anywhere I can sit", "what does this label say", "how many
   of them are there". Note which ones routed correctly and how long each took
   from the end of your question to the answer. Then ask one thing the system
   genuinely cannot do ("what's the weather"). **It must abstain**, not run
   the nearest tool — that is the safety property, and hearing it guess is a
   failure even when the guess sounds sensible.
9. **Agent failure drill**: with the agent enabled, kill Ollama (leave the
   inference server running). The keyword commands must all still work
   unchanged — "find the door", "describe", "sonar off" — and a free-form
   question must abstain rather than hang. Then kill the whole server: the
   phone falls back to local keyword parsing and says so.

## Score sheet

| Scenario | Announcements correct / total | Wrong-direction count | Notes |
|---|---|---|---|
| 1 corridor | | | |
| 2 door | | | |
| 3 find | | | |
| 4 clear path | | | |
| 5 voice | commands recognized: /10 | | |
| 6 failure drill | pass / fail | | |
| 7 pocket drill | pass / fail | | |
| 8 agent round | routed correctly: /5 | abstained on the out-of-scope one? | seconds to answer: |
| 9 agent failure drill | pass / fail | | |

Wrong-direction announcements are the metric that matters most — a wrong
NAME with the right direction is a known COCO limit, not a failure.

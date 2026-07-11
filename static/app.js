/* BlindAssist web UI.
   Polls /state twice a second for detections + announcements, drives the
   controls, and synthesizes the sonar beeps with WebAudio (stereo pan from
   the obstacle's horizontal position, tick rate + pitch from proximity). */

"use strict";

const $ = (id) => document.getElementById(id);

// ---------- state polling ----------

let lastAnnouncementKey = null;

async function poll() {
  let s;
  try {
    s = await (await fetch("/state")).json();
  } catch (e) {
    return; // server briefly busy — next tick will catch up
  }

  $("pill-source").textContent = "source " + s.source;
  $("pill-model").textContent = s.model.replace(".pt", "");
  $("pill-fps").textContent = s.fps.toFixed(1) + " FPS";

  const vp = $("pill-voice");
  if (s.voice.active) {
    vp.textContent = s.voice.last ? `🎤 heard: “${s.voice.last}”` : "🎤 listening";
    vp.title = "voice commands active";
  } else {
    vp.textContent = "🎤 off";
    vp.title = s.voice.error || "voice commands disabled";
  }

  const err = $("error-line");
  err.hidden = !s.error;
  if (s.error) err.textContent = "⚠ " + s.error;

  // mode controls reflect server truth (e.g. after a reload)
  setModeUI(s.mode, s.target, false);
  const mute = $("btn-mute");
  mute.setAttribute("aria-pressed", String(!s.muted));
  mute.querySelector(".toggle-state").textContent = s.muted ? "off" : "on";

  // detection chips
  $("detections").innerHTML = s.detections.map((d) => {
    const cls = d.proximity === "very close" ? "very-close"
              : d.proximity === "close" ? "close" : "";
    return `<span class="det ${cls}">${d.name}
      <small>· ${d.phrase} · ${d.proximity} · ${d.confidence}</small></span>`;
  }).join("") || '<span class="feed-empty">no target objects in view</span>';

  // announcement feed, newest first
  const feed = $("feed");
  const items = s.announcements.slice().reverse();
  feed.innerHTML = items.map((a) =>
    `<li class="${a.kind}"><span class="t">${a.t.toFixed(1)}s</span>
     <span>${a.text}</span></li>`).join("")
    || '<li class="feed-empty">nothing announced yet</li>';

  // hand the newest announcement to screen readers (and, when "speak on
  // this device" is on, to this device's own TTS) exactly once
  if (items.length) {
    const key = items[0].t + "|" + items[0].text;
    if (key !== lastAnnouncementKey) {
      const isFirstPoll = lastAnnouncementKey === null;
      lastAnnouncementKey = key;
      $("sr-live").textContent = items[0].text;
      if (localSpeech && !isFirstPoll) speakHere(items[0].text);
    }
  }

  sonar.update(s.sonar);
}
setInterval(poll, 500);
poll();

// ---------- mode controls ----------

function setModeUI(mode, target, send) {
  const walk = mode === "walk";
  $("btn-walk").classList.toggle("active", walk);
  $("btn-walk").setAttribute("aria-selected", String(walk));
  $("btn-find").classList.toggle("active", !walk);
  $("btn-find").setAttribute("aria-selected", String(!walk));
  $("find-row").hidden = walk;
  if (!walk && target) $("target-select").value = target;
  $("mode-status").textContent = walk
    ? "Walk mode — warning about obstacles ahead."
    : `Find mode — looking for a ${target || $("target-select").value}.`;
  if (send) {
    post("/mode", walk ? { mode: "walk" }
                       : { mode: "find", target: $("target-select").value });
  }
}

$("btn-walk").onclick = () => setModeUI("walk", null, true);
$("btn-find").onclick = () => setModeUI("find", $("target-select").value, true);
$("target-select").onchange = () => setModeUI("find", $("target-select").value, true);

$("btn-describe").onclick = () => post("/describe", {});

$("btn-mute").onclick = async () => {
  const nowOn = $("btn-mute").getAttribute("aria-pressed") === "true";
  await post("/mute", { muted: nowOn }); // pressed==voice on -> mute it
  poll();
};

// ---------- speak on this device (phone testing) ----------
// The laptop's pyttsx3 voice is useless when you're walking around with the
// phone — this speaks each announcement with the BROWSER's own TTS instead.

let localSpeech = false;

function speakHere(text) {
  if (!("speechSynthesis" in window)) return;
  speechSynthesis.cancel(); // stale guidance is never spoken (same rule as speech.py)
  const u = new SpeechSynthesisUtterance(text);
  u.rate = 1.15;
  speechSynthesis.speak(u);
}

$("btn-local-speech").onclick = () => {
  localSpeech = !localSpeech;
  const btn = $("btn-local-speech");
  btn.setAttribute("aria-pressed", String(localSpeech));
  btn.querySelector(".toggle-state").textContent = localSpeech ? "on" : "off";
  if (localSpeech) speakHere("Speaking on this device");
  else speechSynthesis.cancel();
};

const rate = $("rate");
rate.oninput = () => { $("rate-value").textContent = rate.value + " wpm"; };
rate.onchange = () => post("/rate", { rate: Number(rate.value) });

function post(url, body) {
  return fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// ---------- sonar (WebAudio) ----------
// Parking-sensor logic: closer obstacle => faster ticks + higher pitch;
// stereo pan mirrors where the obstacle is. Runs entirely in the browser.

const sonar = {
  ctx: null,
  panner: null,
  enabled: false,
  level: 0,            // 0 silent, 1 medium, 2 close, 3 very close
  pan: 0,
  timer: null,

  PARAMS: {
    1: { interval: 700, freq: 494 },
    2: { interval: 340, freq: 660 },
    3: { interval: 160, freq: 880 },
  },

  toggle() {
    this.enabled = !this.enabled;
    const btn = $("btn-sonar");
    btn.setAttribute("aria-pressed", String(this.enabled));
    btn.querySelector(".toggle-state").textContent = this.enabled ? "on" : "off";
    if (this.enabled) {
      if (!this.ctx) {
        this.ctx = new (window.AudioContext || window.webkitAudioContext)();
        this.panner = this.ctx.createStereoPanner();
        this.panner.connect(this.ctx.destination);
      }
      this.ctx.resume();
      this.schedule();
    } else {
      clearTimeout(this.timer);
      this.timer = null;
    }
  },

  update(s) {
    this.level = s.level;
    this.pan = s.pan;
  },

  schedule() {
    if (!this.enabled) return;
    const p = this.PARAMS[this.level];
    if (p) {
      this.beep(p.freq);
      this.timer = setTimeout(() => this.schedule(), p.interval);
    } else {
      // nothing to warn about — check again shortly
      this.timer = setTimeout(() => this.schedule(), 250);
    }
  },

  beep(freq) {
    const t = this.ctx.currentTime;
    this.panner.pan.setValueAtTime(Math.max(-1, Math.min(1, this.pan)), t);
    const osc = this.ctx.createOscillator();
    const gain = this.ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0.0001, t);
    gain.gain.exponentialRampToValueAtTime(0.5, t + 0.012);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.09);
    osc.connect(gain).connect(this.panner);
    osc.start(t);
    osc.stop(t + 0.1);
  },
};

$("btn-sonar").onclick = () => sonar.toggle();

// ---------- keyboard shortcuts ----------

document.addEventListener("keydown", (e) => {
  if (e.target.tagName === "SELECT" || e.target.tagName === "INPUT") return;
  const k = e.key.toLowerCase();
  if (k === "w") $("btn-walk").click();
  else if (k === "f") $("btn-find").click();
  else if (k === "d") $("btn-describe").click();
  else if (k === "s") $("btn-sonar").click();
  else if (k === "m") $("btn-mute").click();
  else if (k === "v") $("btn-local-speech").click();
});

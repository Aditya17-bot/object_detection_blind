"""BlindAssist — offline speech transcription for the open-dictation window.

Vosk stays the always-on listener: its grammar is a closed list, which is what
makes a small offline model reliable on the trained phrasings. But a closed
grammar cannot HEAR anything else, so free-form speech needs a second path.
This module is that path — Whisper, run locally on the tether laptop, on the
few seconds of audio captured after the trigger word.

Heavy imports stay inside load(), same rule as VoiceListener.start(), so
importing this module costs nothing. Nothing here raises: a failure lands in
.error and transcription returns None, because a dead microphone must never
take the guidance loop down with it.

The model is NOT bundled. Install and fetch it on the machine that runs the
server:

    pip install faster-whisper        # first run downloads the weights

`small.en` (~75 MB) is the default; `base.en` (~150 MB) is more accurate and
slower. Both run on CPU with int8 quantisation.
"""

_DEFAULT_MODEL = "small.en"


class Transcriber:
    """Short-utterance wrapper around faster-whisper.

    model_factory is injectable so tests never touch real weights (same
    pattern as speech.Speaker's engine_factory)."""

    def __init__(self, model_size=_DEFAULT_MODEL, device="cpu",
                 compute_type="int8", model_factory=None, language="en"):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self._factory = model_factory
        self._model = None
        self.error = None

    @property
    def ready(self):
        return self._model is not None

    def load(self):
        """Load the model now rather than on the user's first question — the
        first call otherwise pays several seconds of model init. Returns True
        on success; failure is recorded and non-fatal (the system keeps tier 0).
        """
        if self._model is not None:
            return True
        try:
            if self._factory is not None:
                self._model = self._factory(self.model_size)
            else:
                from faster_whisper import WhisperModel
                self._model = WhisperModel(self.model_size, device=self.device,
                                           compute_type=self.compute_type)
            self.error = None
            return True
        except Exception as exc:      # not installed, no weights, no disk...
            self.error = f"speech transcription unavailable ({exc})"
            return False

    # -- transcription -----------------------------------------------------

    def transcribe_pcm(self, pcm, samplerate=16000):
        """Raw signed 16-bit little-endian mono PCM -> text, or None.

        This is what VoiceListener's dictation window produces, so the audio
        never has to touch the filesystem."""
        if not pcm:
            return None
        if not self.load():
            return None
        try:
            import numpy as np
            audio = (np.frombuffer(pcm, dtype=np.int16)
                     .astype(np.float32) / 32768.0)
            if samplerate != 16000:
                # whisper wants 16 kHz; linear resample is plenty for speech
                n = int(round(len(audio) * 16000 / samplerate))
                audio = np.interp(np.linspace(0, len(audio) - 1, n),
                                  np.arange(len(audio)), audio
                                  ).astype(np.float32)
            return self._run(audio)
        except Exception as exc:
            self.error = f"transcription failed ({exc})"
            return None

    def transcribe_file(self, path):
        """Transcribe a WAV file (the /agent upload path). Returns None on any
        failure."""
        if not self.load():
            return None
        try:
            return self._run(path)
        except Exception as exc:
            self.error = f"transcription failed ({exc})"
            return None

    def _run(self, audio):
        # beam_size 1 and a fixed language: these are 2-5 word commands, and
        # every extra beam is latency the user waits through.
        segments, _ = self._model.transcribe(
            audio, language=self.language, beam_size=1,
            condition_on_previous_text=False)
        text = " ".join(getattr(s, "text", "") for s in segments).strip()
        return text or None

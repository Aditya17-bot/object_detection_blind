"""BlindAssist — the POST /agent endpoint, shared by both servers.

Lives in its own module for two reasons. It is registered by BOTH hosts —
infer_server.py (the server the phone already discovers over UDP) and
webapp.py (the dev/demo UI) — and duplicating it is exactly the mistake the
capability registry exists to stop. And it has no cv2/ultralytics/torch
imports, so the endpoint is unit-testable on any machine, which the servers
themselves are not.

The two hosts differ only in what happens AFTER routing:

  infer_server  no engine, no frame state -> returns the action list and the
                phone executes it locally.
  webapp        owns a GuidanceEngine -> passes an `execute` callback, so the
                response also carries what was spoken.

Accepts either a typed utterance (`text`, JSON or form) or a WAV upload
(`audio`). The typed path is how the whole layer is exercised with no
microphone and no Whisper model — it is the demo affordance and the debugging
tool, not an afterthought.
"""

from flask import jsonify, request

from memory_phrasing import build_record, phrase_memory
from text_summary import summarise


def register_agent_routes(app, router, transcriber=None, execute=None,
                          get_state=None):
    """Attach POST /agent to `app`.

    router       — an agent.AgentRouter
    transcriber  — a transcribe.Transcriber, or None for text-only
    execute      — optional (RouteResult) -> list[str] of spoken messages
    get_state    — optional () -> the deterministic state dict for the router
    """

    @app.post("/agent")
    def agent_endpoint():
        payload = request.get_json(silent=True) or {}
        text = payload.get("text") or request.form.get("text")
        transcript = None

        upload = request.files.get("audio")
        if upload is not None:
            if transcriber is None:
                return jsonify(error="speech transcription not enabled"), 503
            transcript = transcriber.transcribe_file(upload.stream)
            if not transcript:
                # No text is NOT an empty request: refusing to route beats
                # routing silence to whatever tool happens to match "".
                return jsonify(error=transcriber.error or "nothing heard",
                               transcript=None), 422
            text = transcript

        if not isinstance(text, str) or not text.strip():
            return jsonify(error="send text or an audio file"), 400

        # Whose facts? The host's, when it owns a GuidanceEngine (webapp). The
        # CLIENT's otherwise: infer_server has no engine — the phone runs the
        # engine and is the only party that knows what is on screen, so it
        # ships its own state block. Either way the facts come from a detector,
        # never from the model.
        state = get_state() if get_state else None
        if state is None and isinstance(payload.get("state"), dict):
            state = payload["state"]
        result = router.route(text, state)

        body = {
            "transcript": transcript,
            "text": text,
            "source": result.source,
            "latency_ms": round(result.latency_ms, 1),
            "actions": [{"tool": a.tool, "arg": a.arg} for a in result.actions],
            "ask": result.ask,
            "say": result.say,          # model-authored; only ever a reply
            "message": result.message,
            "error": result.error,
        }
        if execute is not None:
            body["spoken"] = execute(result)
        # Log the utterance and what it became. The 2026-08-02 field walk could
        # not be diagnosed from the server log: it showed 26 POSTs and not one
        # word of what had been heard, so there was no way to tell a paraphrase
        # from a door closing. This line is the difference between a bug report
        # and a guess.
        acted = ", ".join(f"{a.tool}({a.arg})" if a.arg else a.tool
                          for a in result.actions) or "-"
        print(f"/agent [{result.source}] {text!r} -> {acted}"
              f"{' ask=' + result.ask if result.ask else ''}"
              f"{' say=' + repr(result.say) if result.say else ''}"
              f" ({result.latency_ms:.0f} ms)", flush=True)
        return jsonify(body)

    # POST /phrase — turn one remembered sighting into a natural sentence.
    #
    # The phone owns the memory (it is the only party that was there), so it
    # ships the structured record and its own deterministic sentence. The model
    # only rewords; every object and every number in the reply is checked
    # against the record, and a reply that fails goes in the bin. The phone
    # already holds the fallback, so a rejection, a timeout or an absent model
    # all cost nothing but a stiffer sentence.
    #
    # This is the memory-layer instance of the rule argument grounding applies
    # to tool calls: the model may choose the WORDS, never the FACTS.
    @app.post("/phrase")
    def phrase_endpoint():
        payload = request.get_json(silent=True) or {}
        name = payload.get("object")
        fallback = payload.get("fallback") or ""
        if not isinstance(name, str) or not name.strip():
            return jsonify(error="object is required"), 400

        record = build_record(
            name.strip(),
            {"near": payload.get("near") or [],
             "context": payload.get("context") or []},
            payload.get("ago_phrase") or "",
            fallback,
        )
        llm = getattr(router, "llm", None)
        caller = (lambda p: llm.complete(p)) if llm is not None else None
        text, how = phrase_memory(record, llm=caller)
        print(f"/phrase {name!r} -> [{how}] {text!r}", flush=True)
        # `how` travels back so the phone can tell a rewording from its own
        # fallback coming home again, which is what makes this auditable in
        # the field rather than only in tests.
        return jsonify(text=text, source=how)

    # POST /summarise — one photographed page, summarised.
    #
    # The phone does the OCR (offline, on-device) and posts only the TEXT, so
    # no image leaves the handset. No retrieval: a page is under a thousand
    # tokens and fits in any context window, so an embedding store would buy
    # latency for a problem that does not exist.
    #
    # Every number in the summary must appear in the source. A summary of a
    # bill or a medical letter that invents an amount or a date is not a
    # quality problem, and that class of error is the one that is mechanically
    # checkable. Prose that mischaracterises the document is not caught, which
    # is why every answer ends by offering the full text.
    @app.post("/summarise")
    def summarise_endpoint():
        payload = request.get_json(silent=True) or {}
        text = payload.get("text")
        if not isinstance(text, str):
            return jsonify(error="text is required"), 400
        llm = getattr(router, "llm", None)
        caller = (lambda p: llm.complete(p, num_predict=160)) \
            if llm is not None else None
        message, how = summarise(text, llm=caller)
        print(f"/summarise {len(text)} chars -> [{how}] {message[:80]!r}",
              flush=True)
        return jsonify(text=message, source=how)

    return app

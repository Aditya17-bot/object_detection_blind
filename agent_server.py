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
        return jsonify(body)

    return app

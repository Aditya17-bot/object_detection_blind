"""Agent-layer tests — registry, validator, router, executor.

Pure logic: no LLM, no microphone, no network, no camera. The LLM is injected
as a fake, the same way test_speech.py fakes pyttsx3 and test_webapp.py fakes
the engine.
"""

import json
import unittest
from pathlib import Path

import agent
import voice
from agent import (ASK_TEMPLATES, TOOLS, Action, AgentRouter, Hooks,
                   capabilities_manifest, execute, execute_action,
                   grammar_phrases, render_state, state_summary,
                   tool_schemas, validate_action)
from decision import GuidanceEngine
from position import analyze_box


def box(name, conf=0.9, x1=0, y1=0, x2=100, y2=100, w=640, h=480):
    return analyze_box(name, conf, x1, y1, x2, y2, w, h)


class FakeLLM:
    """Returns whatever it was handed; records what it was asked."""

    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def route(self, text, state_text, tool_list):
        self.calls.append((text, state_text, tool_list))
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


class RegistryTest(unittest.TestCase):
    def test_every_tool_name_is_unique(self):
        names = [t.name for t in TOOLS]
        self.assertEqual(len(names), len(set(names)))

    def test_every_example_parses_to_its_own_tool(self):
        """A registry example that does not parse to its own tool would mean
        the table and the shipped parser disagree about what a phrase means."""
        for spec in TOOLS:
            for phrase in spec.examples:
                command = voice.parse_command(phrase)
                self.assertIsNotNone(command, phrase)
                self.assertEqual(command[0], spec.name, phrase)

    def test_grammar_is_a_superset_of_the_shipped_list(self):
        # recognition of the trained phrasings must not be able to regress
        self.assertTrue(set(voice.grammar_phrases())
                        <= set(grammar_phrases()))

    def test_grammar_phrases_all_parse(self):
        for phrase in grammar_phrases():
            self.assertIsNotNone(voice.parse_command(phrase), phrase)

    def test_every_parser_action_is_a_registered_tool(self):
        """The drift check in the other direction: no action the parser can
        emit may be missing from the registry (that is exactly how webapp.py
        ended up silently dropping five capabilities)."""
        actions = set()
        for phrase in voice.grammar_phrases():
            command = voice.parse_command(phrase)
            if command:
                actions.add(command[0])
        self.assertTrue(actions <= set(agent.BY_NAME), actions)

    def test_class_enum_comes_from_the_detector(self):
        from position import TARGET_CLASSES
        self.assertEqual(set(agent.ARG_ENUMS["class"]), TARGET_CLASSES)

    def test_schemas_exclude_internal_tools(self):
        names = {s["function"]["name"] for s in tool_schemas()}
        self.assertNotIn("ask", names)
        self.assertIn("abstain", names)

    def test_manifest_file_matches_the_registry(self):
        path = Path(__file__).with_name(agent.MANIFEST_PATH)
        self.assertTrue(path.exists(),
                        "run: python agent.py --write-manifest")
        on_disk = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(on_disk, capabilities_manifest())


class ValidateTest(unittest.TestCase):
    def test_accepts_a_clean_action(self):
        self.assertEqual(
            validate_action({"tool": "find", "args": {"value": "bottle"}}),
            Action("find", "bottle"))

    def test_accepts_alternative_arg_keys(self):
        for key in ("object", "target", "class", "name"):
            self.assertEqual(
                validate_action({"tool": "find", "args": {key: "chair"}}),
                Action("find", "chair"), key)

    def test_accepts_flat_args(self):
        self.assertEqual(validate_action({"tool": "count", "value": "chair"}),
                         Action("count", "chair"))

    def test_resolves_synonyms_and_plurals(self):
        self.assertEqual(validate_action({"tool": "find", "value": "sofa"}),
                         Action("find", "couch"))
        self.assertEqual(validate_action({"tool": "count", "value": "chairs"}),
                         Action("count", "chair"))

    def test_rejects_unknown_tool(self):
        self.assertIsNone(validate_action({"tool": "teleport"}))

    def test_rejects_unknown_class(self):
        self.assertIsNone(validate_action({"tool": "find", "value": "unicorn"}))

    def test_rejects_missing_required_arg(self):
        self.assertIsNone(validate_action({"tool": "find"}))
        self.assertIsNone(validate_action({"tool": "mute"}))

    def test_rejects_bad_onoff(self):
        self.assertIsNone(validate_action({"tool": "sonar", "value": "maybe"}))

    def test_optional_arg_may_be_omitted(self):
        self.assertEqual(validate_action({"tool": "sonar"}), Action("sonar"))

    def test_rejects_internal_tool(self):
        # the model may not drive the dictation window
        self.assertIsNone(validate_action({"tool": "ask"}))

    def test_rejects_non_objects(self):
        for junk in ("find the bottle", None, 42, [], {"args": {}}):
            self.assertIsNone(validate_action(junk), junk)

    def test_stray_arg_on_argless_tool_is_dropped(self):
        self.assertEqual(validate_action({"tool": "describe", "value": "x"}),
                         Action("describe"))


class StateSummaryTest(unittest.TestCase):
    def test_groups_and_counts_visible_objects(self):
        infos = [box("chair", x1=0, x2=100), box("chair", x1=10, x2=120),
                 box("bottle", x1=500, x2=560)]
        state = state_summary(infos, GuidanceEngine(), 0.0)
        by_name = {v["name"]: v for v in state["visible"]}
        self.assertEqual(by_name["chair"]["count"], 2)
        self.assertEqual(by_name["bottle"]["count"], 1)
        self.assertEqual(by_name["bottle"]["zone"], "right")

    def test_reports_engine_mode_and_memory(self):
        # The sighting is taken in WALK mode, then the search is started.
        # Seeing the cup while already in find mode would announce it and drop
        # straight back to walk -- find is eager by design (see
        # test_decision.TestEngineFind) -- and this test is about what
        # state_summary REPORTS, not about when find completes.
        engine = GuidanceEngine(mode="walk")
        engine.update([box("cup")], 0.0)
        engine.set_mode("find", "cup")
        state = state_summary([], engine, 1.0)
        self.assertEqual(state["mode"], "find")
        self.assertEqual(state["target"], "cup")
        self.assertIn("cup", state["remembered"])

    def test_stale_memories_are_not_reported(self):
        engine = GuidanceEngine(mode="walk", memory_ttl=5.0)
        engine.update([box("cup")], 0.0)
        self.assertEqual(state_summary([], engine, 99.0)["remembered"], [])

    def test_render_is_compact_text(self):
        text = render_state(state_summary([box("chair")], GuidanceEngine(), 0))
        self.assertIn("chair", text)
        self.assertIn("Mode: walk", text)

    def test_render_handles_no_state(self):
        self.assertIn("walk", render_state(None))


class RouterTierZeroTest(unittest.TestCase):
    """With no LLM the router must be indistinguishable from today's system."""

    def test_grammar_hit_matches_parse_command_exactly(self):
        router = AgentRouter(llm=None)
        for phrase in voice.grammar_phrases():
            want = voice.parse_command(phrase)
            result = router.route(phrase)
            self.assertEqual(result.source, "grammar", phrase)
            self.assertEqual(len(result.actions), 1, phrase)
            self.assertEqual(result.actions[0].as_command(), want, phrase)

    def test_miss_with_no_llm_abstains(self):
        result = AgentRouter(llm=None).route("what's the weather like")
        self.assertEqual(result.source, "abstain")
        self.assertEqual(result.actions, [])
        self.assertEqual(result.message, ASK_TEMPLATES["unknown"])

    def test_empty_utterance_abstains(self):
        self.assertEqual(AgentRouter().route("   ").ask, "not_understood")

    def test_llm_is_not_consulted_on_a_tier_zero_hit(self):
        llm = FakeLLM({"actions": [{"tool": "describe"}]})
        result = AgentRouter(llm=llm).route("find the bottle")
        self.assertEqual(llm.calls, [])
        self.assertEqual(result.actions, [Action("find", "bottle")])


class ArgumentGroundingTest(unittest.TestCase):
    """The model may CHOOSE a capability. It may not INVENT its argument.

    Every rejected case here is taken verbatim from the 2026-08-02 field walk
    log, where llama3.2:3b turned bare nouns into directional queries and the
    user heard "Nothing on your left" having said no such thing. Tool-name and
    enum validation cannot catch these: `left` IS a valid direction and `check`
    IS a real capability, so the action is well-formed. What is wrong with it
    is its PROVENANCE.
    """

    def check(self, direction):
        return {"tool": "check", "args": {"value": direction}}

    def test_a_direction_the_user_never_said_is_rejected(self):
        for utterance, direction in [("door", "left"), ("the cup", "left"),
                                     ("bag", "left"), ("the person", "right"),
                                     ("cup phones", "ahead")]:
            self.assertIsNone(validate_action(self.check(direction), utterance),
                              f"{utterance!r} -> check({direction})")

    def test_a_direction_the_user_did_say_survives(self):
        self.assertEqual(validate_action(self.check("left"), "the on my left"),
                         Action("check", "left"))
        self.assertEqual(validate_action(self.check("ahead"), "door ahead"),
                         Action("check", "ahead"))

    def test_direction_synonyms_count_as_having_been_said(self):
        for word in ("front", "forward"):
            self.assertEqual(
                validate_action(self.check("ahead"), f"anything in {word}"),
                Action("check", "ahead"))

    def test_class_arguments_are_NOT_grounded_because_paraphrase_is_the_point(self):
        # "the exit" means the door; requiring the class name verbatim would
        # delete the capability tier 1 exists to provide
        self.assertEqual(
            validate_action({"tool": "find", "args": {"value": "door"}},
                            "get me to the exit"),
            Action("find", "door"))
        self.assertEqual(
            validate_action({"tool": "find", "args": {"value": "bottle"}},
                            "i need something to drink"),
            Action("find", "bottle"))

    def test_an_invented_OPTIONAL_argument_drops_to_the_capability(self):
        # sonar's argument is optional, so an ungrounded "off" becomes a plain
        # toggle rather than a silent, unrequested state change
        self.assertEqual(
            validate_action({"tool": "sonar", "args": {"value": "off"}},
                            "the beeping"),
            Action("sonar"))

    def test_a_grounded_state_argument_survives(self):
        self.assertEqual(
            validate_action({"tool": "sonar", "args": {"value": "on"}},
                            "beeps on"),
            Action("sonar", "on"))

    def test_no_utterance_means_no_grounding_check(self):
        # validate_action is also called without context (manifest checks,
        # replay tools); grounding must not fire on an absent utterance
        self.assertEqual(validate_action(self.check("left")),
                         Action("check", "left"))


class RouterTierOneTest(unittest.TestCase):
    def test_valid_tool_call_is_used(self):
        llm = FakeLLM({"actions": [{"tool": "find",
                                    "args": {"value": "bottle"}}]})
        result = AgentRouter(llm=llm).route("i need my water bottle")
        self.assertEqual(result.source, "llm")
        self.assertEqual(result.actions, [Action("find", "bottle")])

    def test_multi_intent_preserves_order(self):
        llm = FakeLLM({"actions": [{"tool": "sonar", "args": {"value": "on"}},
                                   {"tool": "find", "args": {"value": "door"}}]})
        result = AgentRouter(llm=llm).route("beeps on and get me to the exit")
        self.assertEqual(result.actions,
                         [Action("sonar", "on"), Action("find", "door")])

    def test_actions_are_capped(self):
        llm = FakeLLM({"actions": [{"tool": "describe"}] * 5})
        self.assertEqual(len(AgentRouter(llm=llm, max_actions=2)
                             .route("x").actions), 2)

    def test_model_selected_abstain(self):
        llm = FakeLLM({"actions": [{"tool": "abstain",
                                    "args": {"value": "which_object"}}]})
        result = AgentRouter(llm=llm).route("i want that thing")
        self.assertEqual(result.source, "abstain")
        self.assertEqual(result.message, ASK_TEMPLATES["which_object"])

    def test_bare_prose_is_never_spoken(self):
        """Chat mode (2026-07-31) did NOT open this door: a reply is only
        spoken when the model deliberately used the `say` channel. Loose prose
        where a tool call belongs is still an abstention."""
        llm = FakeLLM("Sure! There is a chair to your left.")
        result = AgentRouter(llm=llm).route("what's around me")
        self.assertEqual(result.source, "abstain")
        self.assertEqual(result.actions, [])
        self.assertEqual(result.message, ASK_TEMPLATES["unknown"])

    def test_invalid_action_abstains_rather_than_guessing(self):
        llm = FakeLLM({"actions": [{"tool": "find", "args": {"value": "cat"}}]})
        result = AgentRouter(llm=llm).route("find my cat")
        self.assertEqual(result.source, "abstain")
        self.assertIn("rejected", result.error)

    def test_llm_exception_abstains_and_never_propagates(self):
        # an exception here would kill the voice thread for the whole session
        llm = FakeLLM(RuntimeError("connection refused"))
        result = AgentRouter(llm=llm).route("what's around me")
        self.assertEqual(result.source, "abstain")
        self.assertIn("unavailable", result.error)

    def test_broken_parser_does_not_propagate(self):
        def boom(_):
            raise ValueError("parser exploded")
        result = AgentRouter(llm=None, parse=boom).route("walk mode")
        self.assertEqual(result.source, "abstain")

    def test_state_is_passed_to_the_model(self):
        llm = FakeLLM({"actions": [{"tool": "describe"}]})
        state = state_summary([box("chair")], GuidanceEngine(), 0.0)
        AgentRouter(llm=llm).route("what's around", state)
        self.assertIn("chair", llm.calls[0][1])


class RecordingHooks(Hooks):
    """Hooks that record instead of acting."""

    def __init__(self, last="Chair on left, close"):
        self.events = []
        self._last = last
        super().__init__(
            set_sonar=lambda v: self.events.append(("sonar", v)),
            set_mute=lambda v: self.events.append(("mute", v)),
            stop=lambda: self.events.append(("stop", None)),
            repeat=lambda: self._last,
            read_text=lambda: "BEST BEFORE 2027",
            dictate=lambda: self.events.append(("dictate", None)))


class ExecutorTest(unittest.TestCase):
    def setUp(self):
        self.engine = GuidanceEngine()
        self.hooks = RecordingHooks()

    def run_tool(self, tool, arg=None, infos=(), now=0.0):
        return execute_action(Action(tool, arg), self.engine, list(infos), now,
                              self.hooks)

    def test_find_switches_mode_and_confirms(self):
        self.assertEqual(self.run_tool("find", "bottle"), "Finding bottle")
        self.assertEqual((self.engine.mode, self.engine.target),
                         ("find", "bottle"))

    def test_walk_switches_back(self):
        self.engine.set_mode("find", "cup")
        self.assertEqual(self.run_tool("walk"), "Walk mode")
        self.assertEqual(self.engine.mode, "walk")

    def test_describe_comes_from_decision_py(self):
        from decision import summarize_scene
        infos = [box("chair")]
        self.assertEqual(self.run_tool("describe", infos=infos),
                         summarize_scene(infos))

    def test_count_and_recall_and_path_use_the_engine(self):
        infos = [box("chair"), box("chair", x1=200, x2=300)]
        self.assertEqual(self.run_tool("count", "chair", infos=infos),
                         "2 chairs")
        self.engine.update(infos, 0.0)
        self.assertIn("chair", self.run_tool("recall", "chair", now=1.0).lower())
        self.assertIn("clear", self.run_tool("path", infos=[]).lower())

    def test_clock_and_zones_toggle_bearings(self):
        self.assertEqual(self.run_tool("zones"), "Zone mode")
        self.assertFalse(self.engine.use_clock)
        self.assertEqual(self.run_tool("clock"), "Clock mode")
        self.assertTrue(self.engine.use_clock)

    def test_hook_backed_tools_fire(self):
        self.run_tool("sonar", "on")
        self.run_tool("mute", "on")
        self.run_tool("stop")
        self.assertIn(("sonar", True), self.hooks.events)
        self.assertIn(("mute", True), self.hooks.events)
        self.assertIn(("stop", None), self.hooks.events)

    def test_sonar_without_arg_toggles(self):
        self.run_tool("sonar")
        self.assertIn(("sonar", None), self.hooks.events)

    def test_muting_says_nothing(self):
        # a spoken "muted" would be the last thing heard and contradict itself
        self.assertIsNone(self.run_tool("mute", "on"))
        self.assertEqual(self.run_tool("mute", "off"), "Voice on")

    def test_repeat_and_read_return_their_text(self):
        self.assertEqual(self.run_tool("repeat"), "Chair on left, close")
        self.assertEqual(self.run_tool("read"), "BEST BEFORE 2027")

    def test_missing_hook_says_so_instead_of_doing_nothing(self):
        """The bug this table replaces: webapp.py silently dropped read,
        sonar, stop, repeat and mute."""
        message = execute_action(Action("read"), self.engine, [], 0.0, Hooks())
        self.assertEqual(message, ASK_TEMPLATES["unsupported"])

    def test_abstain_yields_its_template(self):
        self.assertEqual(self.run_tool("abstain", "which_object"),
                         ASK_TEMPLATES["which_object"])
        self.assertEqual(self.run_tool("abstain"), ASK_TEMPLATES["unknown"])


class ExecuteResultTest(unittest.TestCase):
    def test_executes_every_action_in_order(self):
        engine = GuidanceEngine()
        hooks = RecordingHooks()
        llm = FakeLLM({"actions": [{"tool": "sonar", "args": {"value": "on"}},
                                   {"tool": "find", "args": {"value": "door"}}]})
        result = AgentRouter(llm=llm).route("beeps on then get me out")
        self.assertEqual(execute(result, engine, [], 0.0, hooks),
                         ["Sonar on", "Finding door"])
        self.assertEqual(engine.target, "door")

    def test_abstention_speaks_only_its_template(self):
        result = AgentRouter(llm=None).route("what's the weather")
        self.assertEqual(execute(result, GuidanceEngine(), [], 0.0),
                         [ASK_TEMPLATES["unknown"]])

    def test_no_guidance_string_originates_in_the_model(self):
        """C2's authority boundary as it stands after chat mode: unstructured
        prose still reaches nobody's ear, and every GUIDANCE string (walk,
        find, path, check, distance) still comes from decision.py. Only a
        deliberate `say` reply is model-authored — see ChatModeTest."""
        llm = FakeLLM("There are three chairs and a large dog to your left.")
        result = AgentRouter(llm=llm).route("what can you see")
        spoken = execute(result, GuidanceEngine(), [], 0.0, RecordingHooks())
        self.assertEqual(spoken, [ASK_TEMPLATES["unknown"]])
        self.assertNotIn("dog", " ".join(spoken))


class ChatModeTest(unittest.TestCase):
    """The one hole in the authority boundary, opened deliberately on
    2026-07-31 so the user can converse. Everything here is about keeping the
    hole exactly as wide as it was meant to be."""

    def test_say_reply_is_spoken(self):
        llm = FakeLLM({"say": "I can see a chair on your left."})
        result = AgentRouter(llm=llm).route("what does the room look like")
        self.assertEqual(result.source, "chat")
        self.assertEqual(result.actions, [])
        self.assertEqual(result.message, "I can see a chair on your left.")
        self.assertEqual(execute(result, GuidanceEngine(), [], 0.0),
                         ["I can see a chair on your left."])

    def test_actions_win_over_chat(self):
        """Doing the thing beats talking about it."""
        llm = FakeLLM({"say": "Sure, looking now.",
                       "actions": [{"tool": "describe"}]})
        result = AgentRouter(llm=llm).route("tell me what's here")
        self.assertEqual(result.source, "llm")
        self.assertIsNone(result.say)
        self.assertEqual([a.tool for a in result.actions], ["describe"])

    def test_allow_chat_false_restores_the_absolute_rule(self):
        llm = FakeLLM({"say": "There is a chair on your left."})
        result = AgentRouter(llm=llm, allow_chat=False).route("what's here")
        self.assertEqual(result.source, "abstain")
        self.assertEqual(result.message, ASK_TEMPLATES["unknown"])

    def test_long_reply_is_cut_at_a_sentence(self):
        long = ("There is a chair on your left. " * 20).strip()
        result = AgentRouter(llm=FakeLLM({"say": long})).route("tell me more")
        self.assertLessEqual(len(result.say), agent.MAX_SAY_CHARS)
        self.assertTrue(result.say.endswith("."))

    def test_truncated_reply_is_rejected(self):
        """From the 2026-08-01 eval run: Ollama's JSON mode closes the string
        when the token budget runs out, so a half-word arrives as perfectly
        valid JSON. Speaking "I don" is worse than abstaining."""
        result = AgentRouter(llm=FakeLLM({"say": "I don"})).route("can you")
        self.assertEqual(result.source, "abstain")
        # short replies that ARE complete stay allowed
        self.assertEqual(
            AgentRouter(llm=FakeLLM({"say": "Yes."})).route("can you").say,
            "Yes.")

    def test_junk_say_values_are_rejected(self):
        for junk in ("", "   ", 42, None, {"nested": 1},
                     '{"actions": [{"tool": "walk"}]}'):
            result = AgentRouter(llm=FakeLLM({"say": junk})).route("hello")
            self.assertEqual(result.source, "abstain", junk)
            self.assertIsNone(result.say, junk)

    def test_reply_dressed_as_a_tool_call_is_still_a_reply(self):
        """What llama3.2:3b actually emits for a chat turn. Rejecting the
        shape would throw the answer away over a format quibble."""
        llm = FakeLLM({"actions": [{"tool": "say",
                                    "args": {"value": "Doing fine, thanks."}}]})
        result = AgentRouter(llm=llm).route("how's it going")
        self.assertEqual(result.source, "chat")
        self.assertEqual(result.say, "Doing fine, thanks.")

    def test_say_shaped_call_still_obeys_allow_chat(self):
        llm = FakeLLM({"actions": [{"tool": "say", "args": {"value": "Hi."}}]})
        result = AgentRouter(llm=llm, allow_chat=False).route("how's it going")
        self.assertEqual(result.source, "abstain")

    def test_control_templates_are_not_the_models_to_choose(self):
        """Observed with llama3.2:3b: "how are you today" came back as
        abstain/listening, so the app answered a greeting with "Yes?" — which
        sounds exactly like it mis-heard a trigger word."""
        llm = FakeLLM({"actions": [{"tool": "abstain",
                                    "args": {"value": "listening"}}]})
        result = AgentRouter(llm=llm).route("how are you today")
        self.assertEqual(result.ask, "unknown")
        self.assertEqual(result.message, ASK_TEMPLATES["unknown"])

    def test_chat_never_preempts_tier_0(self):
        """A trained phrase must never reach the model, chat or not."""
        llm = FakeLLM({"say": "Sure, I'll describe it."})
        result = AgentRouter(llm=llm).route("find the door")
        self.assertEqual(result.source, "grammar")
        self.assertEqual(llm.calls, [])


class TriggerWordTest(unittest.TestCase):
    def test_trigger_opens_dictation(self):
        self.assertEqual(voice.parse_command("assistant"), ("ask", None))
        self.assertEqual(voice.parse_command("question"), ("ask", None))

    def test_trigger_never_outranks_a_real_command(self):
        # checked last on purpose: existing commands keep their precedence
        self.assertEqual(voice.parse_command("assistant find the bottle"),
                         ("find", "bottle"))
        self.assertEqual(voice.parse_command("assistant stop"), ("stop", None))

    def test_ask_dispatches_to_the_dictate_hook(self):
        hooks = RecordingHooks()
        execute_action(Action("ask"), GuidanceEngine(), [], 0.0, hooks)
        self.assertIn(("dictate", None), hooks.events)


class ResolveClassTest(unittest.TestCase):
    def test_resolves_names_synonyms_and_plurals(self):
        self.assertEqual(voice.resolve_class("bottle"), "bottle")
        self.assertEqual(voice.resolve_class("Sofa"), "couch")
        self.assertEqual(voice.resolve_class("people"), "person")
        self.assertEqual(voice.resolve_class("my water bottle"), "bottle")

    def test_unknown_is_none(self):
        self.assertIsNone(voice.resolve_class("unicorn"))
        self.assertIsNone(voice.resolve_class(""))
        self.assertIsNone(voice.resolve_class(None))


if __name__ == "__main__":
    unittest.main()

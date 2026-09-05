// BlindAssist — the "what can this thing do" page.
//
// The main screen is deliberately bare (a blind user gets nothing from
// buttons), so every capability that used to live in a control row lives here
// instead: one card per tool, with the exact phrases that trigger it. The list
// is generated from kTools — the same registry the recognizer grammar, the
// router and capabilities.json come from — so a capability can never appear
// here without existing, or exist without appearing here.
//
// Tapping a card RUNS the capability where that makes sense, which keeps the
// touch fallback for testing without a microphone.
library;

import 'package:flutter/material.dart';

import 'logic/agent_actions.dart';
import 'logic/voice_commands.dart';
import 'speaker.dart';
import 'settings.dart';

/// One line of plain English per capability. Kept here rather than in
/// agent_actions.dart on purpose: that table is pinned field-by-field against
/// capabilities.json, and prose is not part of the cross-language contract.
const Map<String, String> _blurbs = {
  'walk': 'Continuous warnings while you walk. Speaks only when something is '
      'close enough to matter.',
  'find': 'Search for one object and hear where it is, then go back to walking.',
  'describe': 'One sentence covering everything in view.',
  'count': 'How many of one thing are in front of you right now.',
  'recall': 'Where something was last seen, after it has left the view.',
  'path': 'Which of left, ahead and right is the most open.',
  'check': 'What is in one direction, closest first.',
  'read': 'Reads printed text out loud from the camera.',
  'clock': 'Directions as clock bearings — "door at 2 o\'clock".',
  'zones': 'Directions as left, ahead and right.',
  'sonar': 'Beeps that pan left and right and speed up as things get closer. '
      'Earphones recommended.',
  'mute': 'Silence the voice, or bring it back.',
  'stop': 'Cut off whatever is being said right now.',
  'repeat': 'Say the last announcement again.',
};

/// Tools that are pure UI noise here (the abstention pseudo-tool) or are
/// reached another way (the dictation trigger has its own card).
const Set<String> _hidden = {'abstain', 'ask'};

class FeaturesPage extends StatefulWidget {
  const FeaturesPage({
    super.key,
    required this.onCommand,
    required this.onNameChanged,
    required this.speaker,
    this.voiceActive = false,
    this.agentReady = false,
    this.muted = false,
  });

  /// Runs a capability on the assistant screen. Same dispatcher the voice
  /// tiers use — a tap here is not a second code path.
  final void Function(VoiceCommand command) onCommand;
  final void Function(String name) onNameChanged;

  /// Needed to APPLY and DEMONSTRATE an accent choice on the spot: the point
  /// of the setting is how it sounds, and a user who cannot see the list has
  /// no other way to judge it.
  final Speaker speaker;

  final bool voiceActive;
  final bool agentReady;
  final bool muted;

  @override
  State<FeaturesPage> createState() => _FeaturesPageState();
}

class _FeaturesPageState extends State<FeaturesPage> {
  late final TextEditingController _name =
      TextEditingController(text: AppSettings.userName);

  static const _accent = Color(0xFFFFC247);
  static const _teal = Color(0xFF4DD0E1);

  /// Objects worth a one-tap search. A tap is the mic-free fallback the field
  /// tests rely on; the full class list lives in the voice grammar.
  static const _quickFind = [
    'door', 'chair', 'person', 'bottle', 'cup', 'dustbin',
    'cell phone', 'laptop', 'book', 'toothbrush',
  ];

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  void _run(String tool, [String? arg]) {
    widget.onCommand((action: tool, target: arg));
    Navigator.of(context).maybePop();
  }

  @override
  Widget build(BuildContext context) {
    final tools = kTools.where((t) => !_hidden.contains(t.name)).toList();
    return Scaffold(
      backgroundColor: const Color(0xFF07090D),
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [Color(0xFF10161F), Color(0xFF07090D)],
          ),
        ),
        child: SafeArea(
          child: CustomScrollView(
            slivers: [
              SliverAppBar.large(
                backgroundColor: Colors.transparent,
                foregroundColor: Colors.white,
                title: const Text('What I can do',
                    style: TextStyle(fontWeight: FontWeight.w700)),
              ),
              SliverToBoxAdapter(child: _statusStrip()),
              SliverToBoxAdapter(child: _sectionTitle('Just talk')),
              SliverToBoxAdapter(child: _askCard()),
              SliverToBoxAdapter(child: _sectionTitle('Say any of these')),
              SliverList.builder(
                itemCount: tools.length,
                itemBuilder: (context, i) => _toolCard(tools[i]),
              ),
              SliverToBoxAdapter(child: _sectionTitle('Find, without talking')),
              SliverToBoxAdapter(child: _quickFindWrap()),
              SliverToBoxAdapter(child: _sectionTitle('Touch the screen')),
              SliverToBoxAdapter(child: _gestureCard()),
              SliverToBoxAdapter(child: _sectionTitle('Voice')),
              SliverToBoxAdapter(child: _voiceCard()),
              SliverToBoxAdapter(child: _sectionTitle('Your name')),
              SliverToBoxAdapter(child: _nameCard()),
              const SliverToBoxAdapter(child: SizedBox(height: 40)),
            ],
          ),
        ),
      ),
    );
  }


  /// Spoken accent. Every option is applied AND demonstrated on the spot —
  /// the whole point is how it sounds, and a user who cannot see the list has
  /// no other way to judge it.
  Widget _voiceCard() => _card(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('The accent everything is spoken in.',
                style: TextStyle(color: Colors.white70)),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final entry in kAccents.entries)
                  Semantics(
                    button: true,
                    selected: AppSettings.ttsLocale == entry.key,
                    label: '${entry.value} accent',
                    child: ChoiceChip(
                      label: Text(entry.value),
                      selected: AppSettings.ttsLocale == entry.key,
                      onSelected: (_) => _pickAccent(entry.key, entry.value),
                      backgroundColor: Colors.white.withValues(alpha: 0.06),
                      selectedColor: _accent.withValues(alpha: 0.85),
                      labelStyle: TextStyle(
                          color: AppSettings.ttsLocale == entry.key
                              ? Colors.black
                              : Colors.white,
                          fontSize: 16),
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 8),
            const Text(
                'If one sounds the same as another, that accent is not '
                'installed. Add it in Android Settings, Text-to-speech, '
                'Google, Install voice data.',
                style: TextStyle(color: Colors.white38, fontSize: 13)),
          ],
        ),
      );

  Future<void> _pickAccent(String locale, String label) async {
    await AppSettings.setTtsLocale(locale);
    await widget.speaker.applyVoice(locale);
    if (mounted) setState(() {});
    // Speak the sample AFTER applying, so the user hears the choice itself.
    await widget.speaker.say('$label. Door ahead, close.', onDemand: true);
  }

  Widget _sectionTitle(String text) => Padding(
        padding: const EdgeInsets.fromLTRB(20, 26, 20, 10),
        child: Text(text.toUpperCase(),
            style: const TextStyle(
                color: _teal,
                fontSize: 12,
                letterSpacing: 1.6,
                fontWeight: FontWeight.w700)),
      );

  Widget _card({required Widget child, VoidCallback? onTap}) => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 5),
        child: Material(
          color: Colors.white.withValues(alpha: 0.05),
          borderRadius: BorderRadius.circular(18),
          child: InkWell(
            borderRadius: BorderRadius.circular(18),
            onTap: onTap,
            child: Container(
              padding: const EdgeInsets.fromLTRB(18, 16, 18, 16),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(18),
                border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
              ),
              child: child,
            ),
          ),
        ),
      );

  Widget _statusStrip() => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 20),
        child: Row(
          children: [
            _pill(widget.voiceActive ? 'Microphone on' : 'Microphone off',
                widget.voiceActive),
            const SizedBox(width: 8),
            _pill(widget.agentReady ? 'Assistant online' : 'Assistant offline',
                widget.agentReady),
          ],
        ),
      );

  Widget _pill(String text, bool good) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: (good ? _teal : Colors.white24).withValues(alpha: 0.16),
          borderRadius: BorderRadius.circular(30),
        ),
        child: Text(text,
            style: TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w600,
                color: good ? _teal : Colors.white70)),
      );

  Widget _askCard() => _card(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              const Icon(Icons.auto_awesome, color: _accent, size: 20),
              const SizedBox(width: 10),
              Text('Say "${triggerWords.first}"',
                  style: const TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w700,
                      color: Colors.white)),
            ]),
            const SizedBox(height: 8),
            const Text(
              'Then ask in your own words — "could you look for my water '
              'bottle", "is the door still there", "I\'m lost, can you help". '
              'Trained phrases below are always understood on the phone '
              'itself; anything freer needs the assistant to be online.',
              style: TextStyle(color: Colors.white70, height: 1.4),
            ),
          ],
        ),
      );

  Widget _toolCard(ToolSpec spec) {
    final blurb = _blurbs[spec.name] ?? '';
    // `find`, `count` and `recall` need an object and `check` a direction, so
    // tapping them cannot run anything on its own — they read as reference.
    // `mute` does have an argument but is the one control a user must be able
    // to reach without speaking (you cannot say "unmute" over your own TTS).
    final tappable =
        spec.arg == null || spec.name == 'sonar' || spec.name == 'mute';
    return _card(
      onTap: !tappable
          ? null
          : () => _run(spec.name,
              spec.name == 'mute' ? (widget.muted ? 'off' : 'on') : null),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(spec.name,
                    style: const TextStyle(
                        fontSize: 17,
                        fontWeight: FontWeight.w700,
                        color: Colors.white)),
              ),
              if (tappable)
                const Icon(Icons.play_arrow_rounded,
                    color: _accent, size: 22),
            ],
          ),
          if (blurb.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(blurb,
                style: const TextStyle(color: Colors.white70, height: 1.35)),
          ],
          if (spec.examples.isNotEmpty) ...[
            const SizedBox(height: 10),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [
                for (final e in spec.examples)
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 10, vertical: 5),
                    decoration: BoxDecoration(
                      color: Colors.white.withValues(alpha: 0.06),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Text('"$e"',
                        style: const TextStyle(
                            fontSize: 12.5, color: _teal)),
                  ),
              ],
            ),
          ],
        ],
      ),
    );
  }

  Widget _quickFindWrap() => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final t in _quickFind)
              ActionChip(
                label: Text(t),
                backgroundColor: Colors.white.withValues(alpha: 0.06),
                side: BorderSide(color: Colors.white.withValues(alpha: 0.10)),
                labelStyle: const TextStyle(
                    color: Colors.white, fontWeight: FontWeight.w600),
                padding:
                    const EdgeInsets.symmetric(horizontal: 8, vertical: 10),
                onPressed: () => _run('find', t),
              ),
          ],
        ),
      );

  Widget _gestureCard() => _card(
        child: Column(
          children: const [
            _GestureRow(Icons.touch_app, 'One tap', 'Describe the scene'),
            Divider(color: Colors.white12, height: 22),
            _GestureRow(Icons.tap_and_play, 'Double tap', 'Sonar beeps on/off'),
            Divider(color: Colors.white12, height: 22),
            _GestureRow(Icons.back_hand_outlined, 'Long press',
                'Repeat the last announcement'),
            Divider(color: Colors.white12, height: 22),
            _GestureRow(Icons.swipe_up, 'Swipe up', 'Open this page'),
          ],
        ),
      );

  Widget _nameCard() => _card(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Used in the greeting when the app starts.',
                style: TextStyle(color: Colors.white70)),
            const SizedBox(height: 12),
            TextField(
              controller: _name,
              style: const TextStyle(color: Colors.white, fontSize: 18),
              textInputAction: TextInputAction.done,
              decoration: InputDecoration(
                filled: true,
                fillColor: Colors.white.withValues(alpha: 0.06),
                hintText: kDefaultUserName,
                hintStyle: const TextStyle(color: Colors.white38),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: BorderSide.none,
                ),
              ),
              onSubmitted: _saveName,
            ),
            const SizedBox(height: 10),
            Align(
              alignment: Alignment.centerRight,
              child: FilledButton(
                onPressed: () => _saveName(_name.text),
                style: FilledButton.styleFrom(
                    backgroundColor: _accent, foregroundColor: Colors.black),
                child: const Text('Save'),
              ),
            ),
          ],
        ),
      );

  void _saveName(String value) {
    widget.onNameChanged(value);
    if (!mounted) return;
    FocusScope.of(context).unfocus();
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(greetingFor(DateTime.now(), AppSettings.userName)),
      duration: const Duration(seconds: 2),
    ));
  }
}

class _GestureRow extends StatelessWidget {
  const _GestureRow(this.icon, this.what, this.does);

  final IconData icon;
  final String what;
  final String does;

  @override
  Widget build(BuildContext context) => Row(
        children: [
          Icon(icon, color: Colors.white54, size: 20),
          const SizedBox(width: 14),
          SizedBox(
            width: 96,
            child: Text(what,
                style: const TextStyle(
                    color: Colors.white, fontWeight: FontWeight.w600)),
          ),
          Expanded(
            child: Text(does,
                style: const TextStyle(color: Colors.white70)),
          ),
        ],
      );
}

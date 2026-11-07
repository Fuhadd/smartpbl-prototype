/// Write care note: docs/design/screens/Note.dc.html.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import '../core/api.dart';
import '../core/providers.dart';
import '../core/repository.dart';
import '../core/theme.dart';
import '../visits/format.dart';
import '../visits/models.dart';
import '../widgets/common.dart';

class NoteScreen extends ConsumerWidget {
  const NoteScreen({super.key, required this.visitId, this.clock = DateTime.now});
  final String visitId;
  final DateTime Function() clock;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final day = ref.watch(dayProvider);
    return Scaffold(
      body: SafeArea(
        child: PhoneFrame(
          child: switch (day) {
            AsyncData(:final value) => switch (value.visits.where((v) => v.visitId == visitId).firstOrNull) {
              final Visit v => _NoteForm(visit: v, carerRef: value.carerRef, clock: clock),
              null => const Center(child: Text("This visit isn't on your rota today.")),
            },
            AsyncError(:final error) => ErrorView(
              title: "Couldn't load this visit",
              error: error,
              onRetry: () => ref.invalidate(dayProvider),
            ),
            _ => const LoadingView(label: 'Loading visit'),
          },
        ),
      ),
    );
  }
}

class _NoteForm extends ConsumerStatefulWidget {
  const _NoteForm({required this.visit, required this.carerRef, required this.clock});
  final Visit visit;
  final String carerRef;
  final DateTime Function() clock;

  @override
  ConsumerState<_NoteForm> createState() => _NoteFormState();
}

class _NoteFormState extends ConsumerState<_NoteForm> {
  final _text = TextEditingController();
  // Created once per note, so a retry after a lost response reuses it: the API answers
  // 409 for an id it already saved, which here means "sent" (idempotent submit).
  late final String _noteId = noteId(widget.visit.visitId, widget.clock());
  final Set<String> _done = {};
  bool _urgent = false;
  bool _sending = false;
  String? _error;

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  Future<void> _send(NewNote note) async {
    try {
      await ref.read(repositoryProvider).submitNote(note);
    } on ApiError catch (e) {
      if (e.status != 409) rethrow; // already saved by an earlier attempt
    }
  }

  Future<void> _submit() async {
    final text = _text.text.trim();
    if (text.isEmpty) {
      setState(() => _error = 'Write a few words about the visit first.');
      return;
    }
    setState(() {
      _sending = true;
      _error = null;
    });
    final now = widget.clock();
    final visit = widget.visit;
    try {
      await _send(
        NewNote(
          noteId: _noteId,
          visit: visit,
          carerRef: widget.carerRef,
          visitTime: now,
          text: text,
          urgent: _urgent,
          tasksDone: [
            for (final t in visit.tasks)
              if (_done.contains(t.key)) t.key,
          ],
        ),
      );
      final day = ref.read(dayProvider).value;
      final next = day?.visits.where((v) => !v.done && v.visitId != visit.visitId).firstOrNull;
      ref
          .read(submissionProvider.notifier)
          .set(Submission(visit: visit, submittedAt: now, tasksDone: _done.length, urgent: _urgent, next: next));
      ref.invalidate(dayProvider);
      ref.invalidate(visitProvider(visit.visitId));
      if (mounted) context.go('/visit/${visit.visitId}/submitted');
    } catch (e) {
      final err = ApiError.from(e);
      // Nothing is lost on failure: the text stays in the box for another try.
      setState(
        () => _error = err.isNetwork
            ? "Couldn't send. Your note is still here; try again when you have signal."
            : err.message,
      );
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final v = widget.visit;
    final now = widget.clock();
    return Stack(
      children: [
        ListView(
          padding: const EdgeInsets.fromLTRB(20, 20, 20, 110),
          children: [
            Row(
              children: [
                RoundIconButton(
                  icon: LucideIcons.chevronLeft,
                  label: 'Back to visit',
                  onPressed: () => context.canPop() ? context.pop() : context.go('/visit/${v.visitId}'),
                ),
                Expanded(
                  child: Text(
                    'Visit in progress · ${hhmm(now.hour * 60 + now.minute)}',
                    textAlign: TextAlign.center,
                    style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w500, color: AppColors.textMuted),
                  ),
                ),
                const SizedBox(width: 44),
              ],
            ),
            const SizedBox(height: 16),
            PageTitle('Care note', subtitle: '${v.clientRef} · ${span(v.startMin, v.endMin).replaceAll(' – ', '–')}'),
            const SizedBox(height: 16),
            if (v.tasks.isNotEmpty) ...[
              Panel(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const SectionTitle('Tasks completed'),
                    const SizedBox(height: 12),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        for (final t in v.tasks)
                          _TaskToggle(
                            label: t.label,
                            on: _done.contains(t.key),
                            onTap: () => setState(() => _done.contains(t.key) ? _done.remove(t.key) : _done.add(t.key)),
                          ),
                      ],
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),
            ],
            Panel(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('How was the visit?', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
                  const SizedBox(height: 8),
                  const Text(
                    "Note any changes, concerns or incidents, written as you'd say them.",
                    style: TextStyle(fontSize: 12, color: AppColors.textMuted),
                  ),
                  const SizedBox(height: 8),
                  TextField(
                    controller: _text,
                    minLines: 6,
                    maxLines: 10,
                    maxLength: 5000, // the API's limit
                    textCapitalization: TextCapitalization.sentences,
                    style: const TextStyle(fontSize: 15, height: 1.5),
                    decoration: const InputDecoration(
                      hintText: 'How was the visit?',
                      fillColor: AppColors.surfaceMuted,
                      counterText: '',
                      contentPadding: EdgeInsets.all(12),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),
            Panel(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
              child: MergeSemantics(
                child: Row(
                  children: [
                    const Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('Raise an urgent concern', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
                          SizedBox(height: 2),
                          Text(
                            'Alerts the coordinator straight away',
                            style: TextStyle(fontSize: 12, color: AppColors.textMuted),
                          ),
                        ],
                      ),
                    ),
                    Switch(
                      value: _urgent,
                      onChanged: (on) => setState(() => _urgent = on),
                      activeTrackColor: AppColors.high,
                      inactiveTrackColor: AppColors.switchOff,
                      inactiveThumbColor: Colors.white,
                      trackOutlineColor: const WidgetStatePropertyAll(Colors.transparent),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 16),
            const Row(
              children: [
                Icon(LucideIcons.shieldCheck, size: 16, color: AppColors.success),
                SizedBox(width: 8),
                Text(
                  'Names and addresses are removed before AI review.',
                  style: TextStyle(fontSize: 12, color: AppColors.success),
                ),
              ],
            ),
            if (_error != null) ...[
              const SizedBox(height: 12),
              Semantics(
                liveRegion: true,
                child: Text(
                  _error!,
                  style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w500, color: AppColors.high),
                ),
              ),
            ],
          ],
        ),
        Positioned(
          left: 20,
          right: 20,
          bottom: 24,
          child: FilledButton(
            onPressed: _sending ? null : _submit,
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                // The LLM runs while this waits (seconds), so say so.
                Text(_sending ? 'Sending… checking for risks' : 'Submit note'),
                if (!_sending) ...[const SizedBox(width: 8), const Icon(LucideIcons.send, size: 18)],
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _TaskToggle extends StatelessWidget {
  const _TaskToggle({required this.label, required this.on, required this.onTap});
  final String label;
  final bool on;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Semantics(
    button: true,
    toggled: on,
    label: label,
    excludeSemantics: true,
    child: Material(
      color: on ? AppColors.primary : AppColors.surface,
      shape: StadiumBorder(side: BorderSide(color: on ? AppColors.primary : AppColors.border)),
      child: InkWell(
        customBorder: const StadiumBorder(),
        onTap: onTap,
        child: Container(
          height: 40,
          padding: const EdgeInsets.symmetric(horizontal: 14),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (on) ...[const Icon(LucideIcons.check, size: 14, color: Colors.white), const SizedBox(width: 6)],
              Text(
                label,
                style: TextStyle(fontSize: 13, fontWeight: FontWeight.w500, color: on ? Colors.white : AppColors.text),
              ),
            ],
          ),
        ),
      ),
    ),
  );
}

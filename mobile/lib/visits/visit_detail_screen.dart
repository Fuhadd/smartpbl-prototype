/// Visit detail: docs/design/screens/VisitDetail.dc.html.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:url_launcher/url_launcher.dart';

import '../core/api.dart';
import '../core/config.dart';
import '../core/providers.dart';
import '../core/theme.dart';
import '../widgets/common.dart';
import 'format.dart';
import 'models.dart';

class VisitDetailScreen extends ConsumerWidget {
  const VisitDetailScreen({super.key, required this.visitId});
  final String visitId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final visit = ref.watch(visitProvider(visitId));
    return Scaffold(
      body: SafeArea(
        child: PhoneFrame(
          child: switch (visit) {
            AsyncData(:final value) => _Detail(visit: value),
            AsyncError(:final error) => Column(
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(20, 20, 20, 0),
                  child: _Back(onBack: () => _back(context)),
                ),
                Expanded(
                  child: ApiError.from(error).status == 404
                      ? const Center(
                          child: Text(
                            "This visit isn't on your rota today.",
                            style: TextStyle(color: AppColors.textMuted),
                          ),
                        )
                      : ErrorView(
                          title: "Couldn't load this visit",
                          error: error,
                          onRetry: () => ref.invalidate(visitProvider(visitId)),
                        ),
                ),
              ],
            ),
            _ => const LoadingView(label: 'Loading visit'),
          },
        ),
      ),
    );
  }
}

void _back(BuildContext context) => context.canPop() ? context.pop() : context.go('/');

class _Back extends StatelessWidget {
  const _Back({required this.onBack});
  final VoidCallback onBack;

  @override
  Widget build(BuildContext context) => Align(
    alignment: Alignment.centerLeft,
    child: RoundIconButton(icon: LucideIcons.chevronLeft, label: "Back to today's visits", onPressed: onBack),
  );
}

class _Detail extends StatelessWidget {
  const _Detail({required this.visit});
  final Visit visit;

  @override
  Widget build(BuildContext context) {
    final window = visit.windowStartMin == null
        ? null
        : 'Agreed arrival ${span(visit.windowStartMin!, visit.windowEndMin!)}';
    return Stack(
      children: [
        ListView(
          padding: const EdgeInsets.fromLTRB(20, 20, 20, 110),
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                RoundIconButton(
                  icon: LucideIcons.chevronLeft,
                  label: "Back to today's visits",
                  onPressed: () => _back(context),
                ),
                Pill(familiarityLabel(visit.familiarity), background: AppColors.surface, weight: FontWeight.w600),
              ],
            ),
            const SizedBox(height: 14),
            PageTitle(
              visit.clientRef,
              subtitle: '${span(visit.startMin, visit.endMin).replaceAll(' – ', '–')} · ${visit.durationMin} min',
            ),
            if (window != null) ...[
              const SizedBox(height: 4),
              Text(window, style: const TextStyle(fontSize: 13, color: AppColors.textMuted)),
            ],
            if (visit.done) ...[
              const SizedBox(height: 12),
              const Pill(
                'Note sent for review',
                background: AppColors.successBg,
                foreground: AppColors.success,
                weight: FontWeight.w600,
              ),
            ],
            const SizedBox(height: 14),
            Panel(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const SectionTitle('Tasks this visit'),
                  const SizedBox(height: 10),
                  if (visit.tasks.isEmpty)
                    const Text(
                      'No task list for this visit.',
                      style: TextStyle(fontSize: 13, color: AppColors.textMuted),
                    ),
                  for (final t in visit.tasks) ...[_TaskRow(task: t), const SizedBox(height: 10)],
                  if (visit.timeCritical)
                    const Text(
                      'Time critical: arrive within the agreed window.',
                      style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: AppColors.high),
                    ),
                ],
              ),
            ),
            const SizedBox(height: 14),
            Panel(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const SectionTitle('Recent notes'),
                  const SizedBox(height: 10),
                  if (visit.recentNotes.isEmpty)
                    const Text(
                      'No notes yet for this client.',
                      style: TextStyle(fontSize: 13, color: AppColors.textMuted),
                    ),
                  for (final n in visit.recentNotes) ...[_NoteRow(note: n), const SizedBox(height: 10)],
                  const Text(
                    'Names and addresses are removed.',
                    style: TextStyle(fontSize: 11, color: AppColors.textMuted),
                  ),
                ],
              ),
            ),
          ],
        ),
        Positioned(
          left: 20,
          right: 20,
          bottom: 24,
          child: Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: () => launchUrl(Uri.parse(officePhoneUri)),
                  style: OutlinedButton.styleFrom(padding: const EdgeInsets.symmetric(horizontal: 8)),
                  child: const Text('Call office'),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                flex: 2,
                child: FilledButton(
                  onPressed: visit.done ? null : () => context.push('/visit/${visit.visitId}/note'),
                  child: Text(visit.done ? 'Note sent' : 'Write care note'),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _TaskRow extends StatelessWidget {
  const _TaskRow({required this.task});
  final Task task;

  @override
  Widget build(BuildContext context) => Row(
    children: [
      Container(
        width: 36,
        height: 36,
        decoration: BoxDecoration(color: AppColors.bg, borderRadius: BorderRadius.circular(10)),
        child: Icon(taskIcon(task.key), size: 18),
      ),
      const SizedBox(width: 12),
      Expanded(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(task.label, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
            Text(task.detail, style: const TextStyle(fontSize: 12, color: AppColors.textMuted)),
          ],
        ),
      ),
    ],
  );
}

class _NoteRow extends StatelessWidget {
  const _NoteRow({required this.note});
  final RecentNote note;

  @override
  Widget build(BuildContext context) {
    final status = note.reviewRequired ? 'awaiting review' : 'reviewed';
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 34,
          child: Text(
            weekday(note.visitTime),
            style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: AppColors.textMuted),
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                note.text,
                maxLines: 3,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontSize: 13, color: AppColors.noteText, height: 1.4),
              ),
              if (note.flags.isNotEmpty) ...[
                const SizedBox(height: 4),
                Wrap(
                  spacing: 6,
                  runSpacing: 4,
                  children: [
                    for (final f in note.flags)
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                        decoration: BoxDecoration(
                          color: f.severity == 'high' ? AppColors.highBg : AppColors.mediumBg,
                          borderRadius: BorderRadius.circular(999),
                        ),
                        child: Text(
                          '${categoryLabel(f.category)} · $status',
                          style: TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.w600,
                            color: f.severity == 'high' ? AppColors.high : AppColors.medium,
                          ),
                        ),
                      ),
                  ],
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }
}

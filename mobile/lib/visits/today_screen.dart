/// Today's visits: docs/design/screens/Visits.dc.html.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';
import 'package:url_launcher/url_launcher.dart';

import '../core/api.dart';
import '../core/providers.dart';
import '../core/theme.dart';
import '../widgets/common.dart';
import 'format.dart';
import 'models.dart';

class TodayScreen extends ConsumerWidget {
  const TodayScreen({super.key, this.clock = DateTime.now});

  /// Injectable for tests ("Good morning", "in 25 min").
  final DateTime Function() clock;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final me = ref.watch(authProvider);
    final day = ref.watch(dayProvider);
    final now = clock();
    return Scaffold(
      body: SafeArea(
        child: PhoneFrame(
          child: Stack(
            children: [
              RefreshIndicator(
                color: AppColors.primary,
                onRefresh: () => ref.refresh(dayProvider.future),
                child: ListView(
                  padding: const EdgeInsets.fromLTRB(20, 24, 20, 120),
                  children: [
                    _Header(name: firstName(me?.displayName ?? ''), now: now, day: day.value?.day),
                    const SizedBox(height: 18),
                    ...switch (day) {
                      AsyncData(:final value) => _body(context, value, now),
                      AsyncError(:final error) => [_dayError(ref, error)],
                      _ => [const SizedBox(height: 240, child: LoadingView(label: "Loading today's visits"))],
                    },
                  ],
                ),
              ),
              _BottomNav(next: day.value?.next),
            ],
          ),
        ),
      ),
    );
  }

  Widget _dayError(WidgetRef ref, Object error) {
    final e = ApiError.from(error);
    if (e.status == 404) {
      return const Panel(
        child: Text(
          "No rota yet for today. Your coordinator publishes it each morning; pull down to refresh.",
          style: TextStyle(fontSize: 14, color: AppColors.textMuted, height: 1.5),
        ),
      );
    }
    return SizedBox(
      height: 360,
      child: ErrorView(title: "Couldn't load today's visits", error: error, onRetry: () => ref.invalidate(dayProvider)),
    );
  }

  List<Widget> _body(BuildContext context, Day day, DateTime now) {
    final next = day.next;
    final rest = day.visits.where((v) => v != next).toList()
      ..sort((a, b) => (a.done ? 1 : 0).compareTo(b.done ? 1 : 0)); // to do first, done last
    return [
      _Progress(visits: day.visits.length, done: day.done, travelMin: day.travelMin),
      const SizedBox(height: 18),
      if (next != null)
        _NextCard(visit: next, label: nextLabel(now, day.day, next.startMin))
      else
        const Panel(
          child: Text(
            'All visits written up for today. Thank you.',
            style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
          ),
        ),
      const SizedBox(height: 18),
      if (rest.isNotEmpty) ...[
        const SectionTitle('Today', size: 16),
        const SizedBox(height: 10),
        for (final v in rest) ...[_VisitRow(visit: v), const SizedBox(height: 10)],
      ],
    ];
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.name, required this.now, required this.day});
  final String name;
  final DateTime now;
  final DateTime? day;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      PageTitle('${greeting(now)}${name.isEmpty ? '' : ', $name'}!'),
      const SizedBox(height: 4),
      // The design's bell has no backend yet; the demo badge (always visible) sits here.
      Row(
        children: [
          Expanded(
            child: Text(dayLabel(day ?? now), style: const TextStyle(fontSize: 14, color: AppColors.textMuted)),
          ),
          const DemoBadge(),
        ],
      ),
    ],
  );
}

class _Progress extends StatelessWidget {
  const _Progress({required this.visits, required this.done, required this.travelMin});
  final int visits;
  final int done;
  final int travelMin;

  @override
  Widget build(BuildContext context) => Semantics(
    label: "Today's progress: $visits visits, $done done, $travelMin minutes travel",
    excludeSemantics: true,
    child: Container(
      padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 8),
      decoration: BoxDecoration(color: AppColors.surface, borderRadius: BorderRadius.circular(22)),
      child: IntrinsicHeight(
        child: Row(
          children: [
            _stat('$visits', 'visits'),
            const VerticalDivider(color: AppColors.border, width: 1),
            _stat('$done', 'done'),
            const VerticalDivider(color: AppColors.border, width: 1),
            _stat('$travelMin', 'min travel'),
          ],
        ),
      ),
    ),
  );

  Widget _stat(String value, String label) => Expanded(
    child: Column(
      children: [
        Text(value, style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w700)),
        const SizedBox(height: 2),
        Text(label, style: const TextStyle(fontSize: 13, color: AppColors.textMuted)),
      ],
    ),
  );
}

class _NextCard extends StatelessWidget {
  const _NextCard({required this.visit, required this.label});
  final Visit visit;
  final String label;

  @override
  Widget build(BuildContext context) {
    final loc = visit.location;
    return Semantics(
      container: true,
      label: label,
      child: Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(color: AppColors.primary, borderRadius: BorderRadius.circular(26)),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    label,
                    style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w500, color: AppColors.onDarkMuted),
                  ),
                ),
                Pill(
                  familiarityLabel(visit.familiarity),
                  background: AppColors.darkChip,
                  foreground: Colors.white,
                  weight: FontWeight.w600,
                ),
              ],
            ),
            const SizedBox(height: 14),
            Text(
              span(visit.startMin, visit.endMin),
              style: const TextStyle(
                fontSize: 24,
                fontWeight: FontWeight.w700,
                letterSpacing: -0.48,
                color: Colors.white,
              ),
            ),
            const SizedBox(height: 2),
            Text(
              '${visit.clientRef} · ${visit.travelMin} min drive',
              style: const TextStyle(fontSize: 15, color: AppColors.onDarkSoft),
            ),
            if (visit.tasks.isNotEmpty) ...[
              const SizedBox(height: 14),
              Wrap(
                spacing: 6,
                runSpacing: 6,
                children: [
                  for (final t in visit.tasks) Pill(t.label, background: AppColors.darkChip, foreground: Colors.white),
                  if (visit.timeCritical)
                    const Pill(
                      'Time critical',
                      background: AppColors.high,
                      foreground: Colors.white,
                      weight: FontWeight.w600,
                    ),
                ],
              ),
            ],
            const SizedBox(height: 14),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: loc == null ? null : () => launchUrl(directionsUri(loc.lat, loc.lon)),
                    style: OutlinedButton.styleFrom(
                      minimumSize: const Size.fromHeight(46),
                      backgroundColor: Colors.transparent,
                      foregroundColor: Colors.white,
                      side: const BorderSide(color: AppColors.darkBorder),
                      textStyle: const TextStyle(fontFamily: 'Inter', fontSize: 14, fontWeight: FontWeight.w600),
                    ),
                    child: const Text('Directions'),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: FilledButton(
                    onPressed: () => context.push('/visit/${visit.visitId}'),
                    style: FilledButton.styleFrom(
                      minimumSize: const Size.fromHeight(46),
                      backgroundColor: Colors.white,
                      foregroundColor: AppColors.primary,
                      textStyle: const TextStyle(fontFamily: 'Inter', fontSize: 14, fontWeight: FontWeight.w600),
                    ),
                    child: const Text('Start visit'),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _VisitRow extends StatelessWidget {
  const _VisitRow({required this.visit});
  final Visit visit;

  @override
  Widget build(BuildContext context) {
    final done = visit.done;
    final sub = done
        ? (visit.note!.urgent ? 'Note sent · urgent concern raised' : 'Note sent for review')
        : visit.tasks.map((t) => t.label).join(' · ');
    return Material(
      color: AppColors.surface,
      borderRadius: BorderRadius.circular(18),
      child: InkWell(
        borderRadius: BorderRadius.circular(18),
        onTap: () => context.push('/visit/${visit.visitId}'),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          child: Row(
            children: [
              SizedBox(
                width: 52,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      hhmm(visit.startMin),
                      style: TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                        color: done ? AppColors.textMuted : AppColors.text,
                      ),
                    ),
                    Text(
                      '${visit.durationMin} min',
                      style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w500, color: AppColors.textMuted),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(visit.clientRef, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
                    const SizedBox(height: 2),
                    Text(
                      sub,
                      style: TextStyle(
                        fontSize: 12,
                        color: done ? AppColors.success : AppColors.textMuted,
                        fontWeight: done ? FontWeight.w500 : FontWeight.w400,
                      ),
                    ),
                  ],
                ),
              ),
              if (done)
                Container(
                  width: 24,
                  height: 24,
                  decoration: const BoxDecoration(color: AppColors.successBg, shape: BoxShape.circle),
                  child: const Icon(LucideIcons.check, size: 14, color: AppColors.success),
                )
              else
                const Icon(LucideIcons.chevronRight, size: 18, color: AppColors.textMuted),
            ],
          ),
        ),
      ),
    );
  }
}

/// The floating nav (Visits.dc.html), trimmed to what exists: Today, and Profile for
/// signing out. Rota and My notes have no screens yet (backlog), so they aren't shown.
class _BottomNav extends ConsumerWidget {
  const _BottomNav({required this.next});
  final Visit? next;

  @override
  Widget build(BuildContext context, WidgetRef ref) => Positioned(
    left: 20,
    right: 20,
    bottom: 24,
    child: Row(
      children: [
        Expanded(
          child: Container(
            height: 64,
            padding: const EdgeInsets.symmetric(horizontal: 8),
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: BorderRadius.circular(999),
              boxShadow: floatingShadow,
            ),
            child: Semantics(
              container: true,
              label: 'App',
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceAround,
                children: [
                  Semantics(
                    selected: true,
                    button: true,
                    label: 'Today',
                    excludeSemantics: true,
                    child: Container(
                      width: 52,
                      height: 48,
                      decoration: BoxDecoration(color: AppColors.bg, borderRadius: BorderRadius.circular(999)),
                      child: const Icon(LucideIcons.house, size: 20),
                    ),
                  ),
                  Semantics(
                    button: true,
                    label: 'Profile',
                    excludeSemantics: true,
                    child: InkWell(
                      borderRadius: BorderRadius.circular(999),
                      onTap: () => _profile(context, ref),
                      child: const SizedBox(
                        width: 52,
                        height: 48,
                        child: Icon(LucideIcons.user, size: 20, color: AppColors.textSoft),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
        const SizedBox(width: 10),
        Semantics(
          button: true,
          label: 'Write care note',
          excludeSemantics: true,
          child: Material(
            color: AppColors.surface,
            shape: const CircleBorder(),
            elevation: 0,
            child: InkWell(
              customBorder: const CircleBorder(),
              onTap: next == null ? null : () => context.push('/visit/${next!.visitId}/note'),
              child: Container(
                width: 64,
                height: 64,
                decoration: const BoxDecoration(shape: BoxShape.circle, boxShadow: floatingShadow),
                child: Icon(LucideIcons.plus, size: 24, color: next == null ? AppColors.textMuted : AppColors.primary),
              ),
            ),
          ),
        ),
      ],
    ),
  );

  void _profile(BuildContext context, WidgetRef ref) {
    final me = ref.read(authProvider);
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: AppColors.surface,
      showDragHandle: true,
      builder: (sheet) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(me?.displayName ?? '', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
              Text(me?.username ?? '', style: const TextStyle(fontSize: 13, color: AppColors.textMuted)),
              const SizedBox(height: 16),
              OutlinedButton.icon(
                onPressed: () {
                  Navigator.of(sheet).pop();
                  ref.read(authProvider.notifier).signOut();
                },
                icon: const Icon(LucideIcons.logOut, size: 18),
                label: const Text('Sign out'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

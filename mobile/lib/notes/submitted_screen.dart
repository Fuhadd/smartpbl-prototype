/// Note submitted: docs/design/screens/Submitted.dc.html.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import '../core/providers.dart';
import '../core/theme.dart';
import '../visits/format.dart';
import '../widgets/common.dart';

class SubmittedScreen extends ConsumerWidget {
  const SubmittedScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final s = ref.watch(submissionProvider);
    final me = ref.watch(authProvider);
    if (s == null) {
      // Opened directly (or after a reload): nothing to confirm, go back to today.
      WidgetsBinding.instance.addPostFrameCallback((_) => context.go('/'));
      return const Scaffold(body: SizedBox.shrink());
    }
    final name = firstName(me?.displayName ?? '');
    final total = s.visit.tasks.length;
    return Scaffold(
      body: SafeArea(
        child: PhoneFrame(
          child: Stack(
            children: [
              ListView(
                padding: const EdgeInsets.fromLTRB(20, 56, 20, 190),
                children: [
                  Center(
                    child: Container(
                      width: 84,
                      height: 84,
                      decoration: const BoxDecoration(color: AppColors.successBg, shape: BoxShape.circle),
                      child: const Icon(LucideIcons.check, size: 40, color: AppColors.success),
                    ),
                  ),
                  const SizedBox(height: 14),
                  Semantics(
                    header: true,
                    liveRegion: true,
                    child: const Text(
                      'Note sent for review',
                      textAlign: TextAlign.center,
                      style: TextStyle(fontSize: 26, fontWeight: FontWeight.w700, letterSpacing: -0.52),
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    s.urgent
                        ? 'Your coordinator has been alerted to your concern${name.isEmpty ? '' : ', $name'}.'
                        : 'Your coordinator will see it shortly. Thank you${name.isEmpty ? '' : ', $name'}.',
                    textAlign: TextAlign.center,
                    style: const TextStyle(fontSize: 15, color: AppColors.textMuted, height: 1.5),
                  ),
                  const SizedBox(height: 20),
                  Panel(
                    child: Column(
                      children: [
                        _Row('Client', s.visit.clientRef),
                        _Row('Submitted', hhmm(s.submittedAt.hour * 60 + s.submittedAt.minute)),
                        if (total > 0) _Row('Tasks', '${s.tasksDone} of $total completed'),
                        _Row('Urgent concern', s.urgent ? 'Raised' : 'None raised', last: true),
                      ],
                    ),
                  ),
                  const SizedBox(height: 20),
                  const Panel(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        SectionTitle('What happens next'),
                        SizedBox(height: 12),
                        _Step(1, 'Names removed, then AI checks for risks', current: true),
                        SizedBox(height: 12),
                        _Step(2, 'A coordinator reviews anything flagged'),
                        SizedBox(height: 12),
                        _Step(3, 'Every decision is logged for audit'),
                      ],
                    ),
                  ),
                ],
              ),
              Positioned(
                left: 20,
                right: 20,
                bottom: 24,
                child: Column(
                  children: [
                    if (s.next != null) ...[
                      Material(
                        color: AppColors.surface,
                        borderRadius: BorderRadius.circular(18),
                        child: InkWell(
                          borderRadius: BorderRadius.circular(18),
                          onTap: () => context.go('/visit/${s.next!.visitId}'),
                          child: Padding(
                            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                            child: Row(
                              children: [
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      Text(
                                        'Next visit · ${hhmm(s.next!.startMin)}',
                                        style: const TextStyle(fontSize: 12, color: AppColors.textMuted),
                                      ),
                                      Text(
                                        s.next!.clientRef,
                                        style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
                                      ),
                                    ],
                                  ),
                                ),
                                const Icon(LucideIcons.chevronRight, size: 18, color: AppColors.textMuted),
                              ],
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(height: 10),
                    ],
                    FilledButton(onPressed: () => context.go('/'), child: const Text('Back to today')),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Row extends StatelessWidget {
  const _Row(this.label, this.value, {this.last = false});
  final String label;
  final String value;
  final bool last;

  @override
  Widget build(BuildContext context) => Padding(
    padding: EdgeInsets.only(bottom: last ? 0 : 10),
    child: Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(label, style: const TextStyle(fontSize: 14, color: AppColors.textMuted)),
        Text(value, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
      ],
    ),
  );
}

class _Step extends StatelessWidget {
  const _Step(this.n, this.text, {this.current = false});
  final int n;
  final String text;
  final bool current;

  @override
  Widget build(BuildContext context) => Row(
    children: [
      Container(
        width: 26,
        height: 26,
        alignment: Alignment.center,
        decoration: BoxDecoration(color: current ? AppColors.primary : AppColors.bg, shape: BoxShape.circle),
        child: Text(
          '$n',
          style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: current ? Colors.white : AppColors.text),
        ),
      ),
      const SizedBox(width: 12),
      Expanded(child: Text(text, style: const TextStyle(fontSize: 13))),
    ],
  );
}

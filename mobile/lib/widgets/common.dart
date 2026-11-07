/// Small building blocks shared by the carer screens (the designs' cards, pills, buttons).
library;

import 'package:flutter/material.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

import '../core/api.dart';
import '../core/theme.dart';

/// Phone-width column, centred on wide screens (the app is phone-first; on a laptop
/// browser it should look like the phone screens, not stretch).
class PhoneFrame extends StatelessWidget {
  const PhoneFrame({super.key, required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) => Center(
    child: ConstrainedBox(constraints: const BoxConstraints(maxWidth: 480), child: child),
  );
}

class DemoBadge extends StatelessWidget {
  const DemoBadge({super.key});

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
    decoration: BoxDecoration(
      color: AppColors.mediumBg,
      border: Border.all(color: AppColors.mediumBorder),
      borderRadius: BorderRadius.circular(999),
    ),
    child: const Text(
      'Demo · synthetic data',
      style: TextStyle(fontSize: 12, fontWeight: FontWeight.w500, color: AppColors.medium),
    ),
  );
}

/// White rounded panel (radius 22, padding 16), the designs' section card.
class Panel extends StatelessWidget {
  const Panel({super.key, required this.child, this.padding = const EdgeInsets.all(16), this.radius = 22});
  final Widget child;
  final EdgeInsets padding;
  final double radius;

  @override
  Widget build(BuildContext context) => Container(
    width: double.infinity,
    padding: padding,
    decoration: BoxDecoration(color: AppColors.surface, borderRadius: BorderRadius.circular(radius)),
    child: child,
  );
}

class Pill extends StatelessWidget {
  const Pill(
    this.label, {
    super.key,
    this.background = AppColors.bg,
    this.foreground = AppColors.text,
    this.weight = FontWeight.w500,
  });
  final String label;
  final Color background;
  final Color foreground;
  final FontWeight weight;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
    decoration: BoxDecoration(color: background, borderRadius: BorderRadius.circular(999)),
    child: Text(
      label,
      style: TextStyle(fontSize: 12, fontWeight: weight, color: foreground),
    ),
  );
}

/// The 44 px round white icon button (back, more).
class RoundIconButton extends StatelessWidget {
  const RoundIconButton({super.key, required this.icon, required this.label, required this.onPressed});
  final IconData icon;
  final String label;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) => Semantics(
    button: true,
    label: label,
    excludeSemantics: true,
    child: Material(
      color: AppColors.surface,
      shape: const CircleBorder(),
      child: InkWell(
        customBorder: const CircleBorder(),
        onTap: onPressed,
        child: SizedBox.square(dimension: 44, child: Icon(icon, size: 20, color: AppColors.text)),
      ),
    ),
  );
}

class SectionTitle extends StatelessWidget {
  const SectionTitle(this.text, {super.key, this.size = 14});
  final String text;
  final double size;

  @override
  Widget build(BuildContext context) => Semantics(
    header: true,
    child: Text(
      text,
      style: TextStyle(fontSize: size, fontWeight: FontWeight.w600),
    ),
  );
}

class PageTitle extends StatelessWidget {
  const PageTitle(this.title, {super.key, this.subtitle});
  final String title;
  final String? subtitle;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Semantics(
        header: true,
        child: Text(title, style: const TextStyle(fontSize: 26, fontWeight: FontWeight.w700, letterSpacing: -0.52)),
      ),
      if (subtitle != null) ...[
        const SizedBox(height: 4),
        Text(subtitle!, style: const TextStyle(fontSize: 14, color: AppColors.textMuted)),
      ],
    ],
  );
}

class LoadingView extends StatelessWidget {
  const LoadingView({super.key, required this.label});
  final String label;

  @override
  Widget build(BuildContext context) => Center(
    child: Semantics(
      label: label,
      child: const CircularProgressIndicator(color: AppColors.primary, strokeWidth: 2.5),
    ),
  );
}

/// The States sheet's error, phone-sized: what happened, that nothing was lost, a retry.
class ErrorView extends StatelessWidget {
  const ErrorView({super.key, required this.title, required this.error, required this.onRetry});
  final String title;
  final Object error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final e = ApiError.from(error);
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 64,
              height: 64,
              decoration: const BoxDecoration(color: AppColors.mediumBg, shape: BoxShape.circle),
              child: const Icon(LucideIcons.triangleAlert, color: AppColors.medium, size: 28),
            ),
            const SizedBox(height: 14),
            Text(
              title,
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 6),
            Text(
              e.message,
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 14, color: AppColors.textMuted),
            ),
            const SizedBox(height: 16),
            FilledButton(onPressed: onRetry, child: const Text('Try again')),
            if (e.reference != null) ...[
              const SizedBox(height: 10),
              Text(
                'Reference: ${e.reference}',
                style: const TextStyle(fontSize: 12, fontFamily: 'monospace', color: AppColors.textMuted),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// Design tokens from docs/design/DESIGN.md, as Flutter colours and a Material theme.
library;

import 'package:flutter/material.dart';

abstract final class AppColors {
  static const bg = Color(0xFFF4F4F2);
  static const surface = Color(0xFFFFFFFF);
  static const surfaceMuted = Color(0xFFFAFAF9);
  static const border = Color(0xFFE7E7E4);
  static const text = Color(0xFF18181B);
  static const textMuted = Color(0xFF5F5F66);
  static const textSoft = Color(0xFF3F3F46);
  static const noteText = Color(0xFF27272A);
  static const primary = Color(0xFF111113);
  // The dark "next visit" card (Visits.dc.html).
  static const darkChip = Color(0xFF2A2A2E);
  static const darkBorder = Color(0xFF3F3F46);
  static const onDarkMuted = Color(0xFFD4D4D8);
  static const onDarkSoft = Color(0xFFE4E4E7);
  static const switchOff = Color(0xFFD4D4D8);
  static const high = Color(0xFFB42318);
  static const highBg = Color(0xFFFEF3F2);
  static const medium = Color(0xFF93370D);
  static const mediumBg = Color(0xFFFFFAEB);
  static const mediumBorder = Color(0xFFFEDF89);
  static const success = Color(0xFF067647);
  static const successBg = Color(0xFFECFDF3);
}

/// The floating nav's shadow: the only shadow in the designs.
const floatingShadow = [BoxShadow(color: Color(0x1A111113), blurRadius: 24, offset: Offset(0, 6))];

ThemeData appTheme() {
  const font = 'Inter';
  final base = ThemeData(
    useMaterial3: true,
    fontFamily: font,
    scaffoldBackgroundColor: AppColors.bg,
    colorScheme: ColorScheme.fromSeed(
      seedColor: AppColors.primary,
      primary: AppColors.primary,
      surface: AppColors.surface,
      error: AppColors.high,
    ),
  );
  return base.copyWith(
    textTheme: base.textTheme.apply(bodyColor: AppColors.text, displayColor: AppColors.text),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: AppColors.surface,
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
      border: _outline(AppColors.border),
      enabledBorder: _outline(AppColors.border),
      focusedBorder: _outline(AppColors.primary, width: 1.5),
      errorBorder: _outline(AppColors.high),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: AppColors.primary,
        foregroundColor: Colors.white,
        minimumSize: const Size.fromHeight(56),
        shape: const StadiumBorder(),
        textStyle: const TextStyle(fontFamily: font, fontSize: 16, fontWeight: FontWeight.w600),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: AppColors.text,
        backgroundColor: AppColors.surface,
        minimumSize: const Size.fromHeight(56),
        side: const BorderSide(color: AppColors.border),
        shape: const StadiumBorder(),
        textStyle: const TextStyle(fontFamily: font, fontSize: 15, fontWeight: FontWeight.w600),
      ),
    ),
  );
}

OutlineInputBorder _outline(Color c, {double width = 1}) => OutlineInputBorder(
  borderRadius: BorderRadius.circular(14),
  borderSide: BorderSide(color: c, width: width),
);

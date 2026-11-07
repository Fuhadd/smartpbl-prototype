/// Load the bundled Inter font for every test, so text has real widths. The default test
/// font draws every glyph as a square, which wraps headings and pushes rows off-screen.
library;

import 'dart:async';
import 'dart:io';

import 'package:flutter/services.dart';

Future<void> testExecutable(FutureOr<void> Function() testMain) async {
  final inter = FontLoader('Inter');
  for (final w in ['Regular', 'Medium', 'SemiBold', 'Bold']) {
    final bytes = File('assets/fonts/Inter-$w.ttf').readAsBytesSync();
    inter.addFont(Future.value(ByteData.sublistView(Uint8List.fromList(bytes))));
  }
  await inter.load();
  await testMain();
}

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app.dart';

void main() {
  // Riverpod 3 retries failing providers automatically. Here a failure is shown with a
  // "Try again" button instead, so a 403 or 404 isn't silently re-requested.
  runApp(ProviderScope(retry: (_, _) => null, child: const CarerApp()));
}

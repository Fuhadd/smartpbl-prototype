/// The app and its routes (DESIGN.md section 2): /login, /, /visit/:id, /visit/:id/note,
/// /visit/:id/submitted. Signed-out users are sent to /login; signed-in users never see it.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'auth/login_screen.dart';
import 'core/providers.dart';
import 'core/theme.dart';
import 'notes/note_screen.dart';
import 'notes/submitted_screen.dart';
import 'visits/today_screen.dart';
import 'visits/visit_detail_screen.dart';

/// Re-runs the router's redirect whenever the session starts or ends.
class _AuthListenable extends ChangeNotifier {
  _AuthListenable(Ref ref) {
    ref.listen(authProvider, (_, _) => notifyListeners());
  }
}

final routerProvider = Provider<GoRouter>((ref) {
  final refresh = _AuthListenable(ref);
  ref.onDispose(refresh.dispose);
  return GoRouter(
    refreshListenable: refresh,
    redirect: (context, state) {
      final signedIn = ref.read(authProvider) != null;
      final atLogin = state.matchedLocation == '/login';
      if (!signedIn) return atLogin ? null : '/login';
      return atLogin ? '/' : null;
    },
    routes: [
      GoRoute(path: '/login', builder: (_, _) => const LoginScreen()),
      GoRoute(path: '/', builder: (_, _) => const TodayScreen()),
      GoRoute(
        path: '/visit/:id',
        builder: (_, s) => VisitDetailScreen(visitId: s.pathParameters['id']!),
        routes: [
          GoRoute(
            path: 'note',
            builder: (_, s) => NoteScreen(visitId: s.pathParameters['id']!),
          ),
          GoRoute(path: 'submitted', builder: (_, _) => const SubmittedScreen()),
        ],
      ),
    ],
  );
});

class CarerApp extends ConsumerWidget {
  const CarerApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) => MaterialApp.router(
    title: 'SMARTPBL Carer',
    debugShowCheckedModeBanner: false,
    theme: appTheme(),
    routerConfig: ref.watch(routerProvider),
  );
}

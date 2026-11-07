/// Riverpod wiring. Tests override `repositoryProvider` with a fake.
library;

import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../visits/models.dart';
import 'api.dart';
import 'config.dart';
import 'repository.dart';

final tokenStoreProvider = Provider<TokenStore>((ref) => TokenStore());

final repositoryProvider = Provider<Repository>((ref) {
  final store = ref.watch(tokenStoreProvider);
  return Repository(buildDio(store, baseUrl: apiUrl), store);
});

/// The signed-in user, or null. Signing in is refused for non-carers: this app shows a
/// carer's own rota, and staff use the coordinator dashboard.
class AuthController extends Notifier<Me?> {
  StreamSubscription<void>? _ended;

  @override
  Me? build() {
    _ended = ref.watch(tokenStoreProvider).sessionEnded.listen((_) => state = null);
    ref.onDispose(() => _ended?.cancel());
    return null;
  }

  Future<void> signIn(String username, String password) async {
    final repo = ref.read(repositoryProvider);
    final me = await repo.signIn(username.trim(), password);
    if (me.role != 'carer') {
      await repo.signOut();
      throw const ApiError('This app is for carers. Coordinators and managers use the dashboard.');
    }
    state = me;
  }

  Future<void> signOut() async {
    await ref.read(repositoryProvider).signOut();
    state = null;
  }
}

final authProvider = NotifierProvider<AuthController, Me?>(AuthController.new);

/// Today's visits. Re-fetched after a note is submitted (`ref.invalidate`).
final dayProvider = FutureProvider.autoDispose<Day>((ref) => ref.watch(repositoryProvider).myDay());

/// One visit with its handover notes. Every fetch is audited server-side.
final visitProvider = FutureProvider.autoDispose.family<Visit, String>(
  (ref, id) => ref.watch(repositoryProvider).visit(id),
);

/// The last successful submission, for the Submitted screen (memory only).
class SubmissionController extends Notifier<Submission?> {
  @override
  Submission? build() => null;
  void set(Submission s) => state = s;
}

final submissionProvider = NotifierProvider<SubmissionController, Submission?>(SubmissionController.new);

/// The carer flow against a fake repository: sign in → today → visit → note → submitted.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:smartpbl_carer/app.dart';
import 'package:smartpbl_carer/core/api.dart';
import 'package:smartpbl_carer/core/providers.dart';

import 'fixtures.dart';

Future<FakeRepository> pumpApp(WidgetTester tester, {FakeRepository? repo, bool signIn = true}) async {
  tester.view.physicalSize = const Size(390 * 3, 844 * 3); // the designs' phone frame
  tester.view.devicePixelRatio = 3;
  addTearDown(tester.view.reset);
  final r = repo ?? FakeRepository();
  final container = ProviderContainer(overrides: [repositoryProvider.overrideWithValue(r)], retry: (_, _) => null);
  addTearDown(container.dispose);
  await tester.pumpWidget(UncontrolledProviderScope(container: container, child: const CarerApp()));
  await tester.pumpAndSettle();
  if (signIn) {
    await tester.tap(find.text('Sign in'));
    await tester.pumpAndSettle();
  }
  return r;
}

void main() {
  testWidgets('sign-in shows the demo account, pre-filled', (tester) async {
    await pumpApp(tester, signIn: false);
    expect(find.text('Welcome back'), findsOneWidget);
    expect(find.text('Demo carer account'), findsOneWidget);
    expect(find.widgetWithText(TextField, 'joy@demo.smartpbl'), findsOneWidget);
    expect(find.text('Demo · synthetic data'), findsOneWidget);
  });

  testWidgets('a wrong password says so, in words', (tester) async {
    await pumpApp(tester, signIn: false);
    await tester.enterText(find.byType(TextField).last, 'nope');
    await tester.tap(find.text('Sign in'));
    await tester.pumpAndSettle();
    expect(find.text('That email or password is wrong.'), findsOneWidget);
  });

  testWidgets('staff accounts are sent to the dashboard', (tester) async {
    await pumpApp(tester, repo: FakeRepository(role: 'coordinator'));
    expect(find.textContaining('Coordinators and managers use the dashboard'), findsOneWidget);
    expect(find.text('Welcome back'), findsOneWidget);
  });

  testWidgets("today shows progress, the next visit and the rest, done last", (tester) async {
    await pumpApp(tester);
    expect(find.textContaining('Joy!'), findsOneWidget);
    expect(find.text('Saturday, 7 November'), findsOneWidget);
    expect(find.bySemanticsLabel("Today's progress: 3 visits, 1 done, 38 minutes travel"), findsOneWidget);
    expect(find.text('09:30 – 10:15'), findsOneWidget); // V-0096, the first not written up
    expect(find.text('CL-0035 · 9 min drive'), findsOneWidget);
    expect(find.text('Preferred carer'), findsOneWidget);
    expect(find.text('Note sent for review'), findsOneWidget); // V-0047's row
    final rows = tester.widgetList<Text>(find.textContaining(RegExp(r'^CL-00(09|17)$'))).map((t) => t.data).toList();
    expect(rows, ['CL-0009', 'CL-0017']); // to do first, done last
  });

  testWidgets('no rota yet is an empty state, not an error', (tester) async {
    await pumpApp(tester, repo: FakeRepository(dayError: const ApiError('no rota saved yet', status: 404)));
    expect(find.textContaining('No rota yet for today'), findsOneWidget);
  });

  testWidgets('a failed load can be retried', (tester) async {
    final repo = FakeRepository(dayError: const ApiError("Couldn't reach the server."));
    await pumpApp(tester, repo: repo);
    expect(find.text("Couldn't load today's visits"), findsOneWidget);
    repo.dayError = null;
    await tester.tap(find.text('Try again'));
    await tester.pumpAndSettle();
    expect(find.text('09:30 – 10:15'), findsOneWidget);
  });

  testWidgets('visit detail lists tasks and the handover note', (tester) async {
    await pumpApp(tester);
    await tester.tap(find.text('Start visit'));
    await tester.pumpAndSettle();
    expect(find.text('CL-0035'), findsOneWidget);
    expect(find.text('Tasks this visit'), findsOneWidget);
    expect(find.text('Administer as on the MAR chart, with water'), findsOneWidget);
    expect(find.text('Mentioned knee pain on stairs.'), findsOneWidget);
    expect(find.text('Falls · reviewed'), findsOneWidget);
    expect(find.text('Call office'), findsOneWidget);
  });

  testWidgets('writing a note sends tasks, urgency and the visit, then confirms', (tester) async {
    final repo = await pumpApp(tester);
    await tester.tap(find.text('Start visit'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Write care note'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Submit note'));
    await tester.pumpAndSettle();
    expect(find.text('Write a few words about the visit first.'), findsOneWidget);
    expect(repo.submitted, isEmpty);

    await tester.tap(find.bySemanticsLabel('Medication'));
    await tester.enterText(find.byType(TextField), 'Meds taken with water. Ate most of breakfast.');
    await tester.tap(find.byType(Switch));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Submit note'));
    await tester.pumpAndSettle();

    final sent = repo.submitted.single;
    expect(sent['visit_id'], 'V-0096');
    expect(sent['client_ref'], 'CL-0035');
    expect(sent['carer_ref'], 'CR-0001');
    expect(sent['tasks_done'], ['medication']);
    expect(sent['urgent'], isTrue);
    expect(sent['note_id'], startsWith('V-0096-'));

    expect(find.text('Note sent for review'), findsOneWidget);
    expect(find.text('1 of 2 completed'), findsOneWidget);
    expect(find.text('Raised'), findsOneWidget);
    expect(find.text('Next visit · 10:45'), findsOneWidget);
    await tester.tap(find.text('Back to today'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Joy!'), findsOneWidget);
  });

  testWidgets('a lost response is retried with the same note id; 409 means it was saved', (tester) async {
    final repo = FakeRepository()
      ..submitErrors.addAll([
        const ApiError("Couldn't reach the server."), // no status: network failure
        const ApiError("note 'x' already exists", status: 409), // the first attempt did land
      ]);
    await pumpApp(tester, repo: repo);
    await tester.tap(find.text('Start visit'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Write care note'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'Synthetic note.');
    await tester.tap(find.text('Submit note'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Your note is still here'), findsOneWidget);
    expect(find.text('Synthetic note.'), findsOneWidget);
    await tester.tap(find.text('Submit note'));
    await tester.pumpAndSettle();
    expect(repo.submitted.map((n) => n['note_id']).toSet(), hasLength(1));
    expect(find.text('Note sent for review'), findsOneWidget);
  });

  testWidgets('signing out returns to sign in', (tester) async {
    await pumpApp(tester);
    await tester.tap(find.bySemanticsLabel('Profile'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Sign out'));
    await tester.pumpAndSettle();
    expect(find.text('Welcome back'), findsOneWidget);
  });
}

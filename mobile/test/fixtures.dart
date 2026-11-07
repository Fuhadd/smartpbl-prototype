/// Synthetic API responses shaped like app/api/me.py, and a fake repository.
library;

import 'package:smartpbl_carer/core/api.dart';
import 'package:smartpbl_carer/core/repository.dart';
import 'package:smartpbl_carer/visits/models.dart';

Map<String, dynamic> visitJson(
  String id,
  String client,
  int start, {
  int duration = 45,
  String familiarity = 'preferred',
  Map<String, dynamic>? note,
  List<Map<String, dynamic>> recent = const [],
}) => {
  'visit_id': id,
  'sequence': 1,
  'client_ref': client,
  'start_min': start,
  'end_min': start + duration,
  'duration_min': duration,
  'travel_min': 9,
  'familiarity': familiarity,
  'window_start_min': start,
  'window_end_min': start + 60,
  'time_critical': false,
  'tasks': [
    {'key': 'medication', 'label': 'Medication', 'detail': 'Administer as on the MAR chart, with water'},
    {'key': 'personal_care', 'label': 'Personal care', 'detail': 'Washing, dressing and toileting'},
  ],
  'location': {'lat': 52.45, 'lon': -1.89},
  'note': note,
  'recent_notes': recent,
};

Map<String, dynamic> dayJson({bool firstDone = true}) => {
  'run_id': 'run-1',
  'day': '2026-11-07',
  'carer_ref': 'CR-0001',
  'summary': {'visits': 3, 'done': firstDone ? 1 : 0, 'travel_min': 38},
  'visits': [
    visitJson(
      'V-0047',
      'CL-0017',
      8 * 60 + 15,
      duration: 30,
      note: firstDone ? {'note_id': 'V-0047-x', 'submitted_at': '2026-11-07T08:50:00Z', 'urgent': false} : null,
    ),
    visitJson('V-0096', 'CL-0035', 9 * 60 + 30),
    visitJson('V-0025', 'CL-0009', 10 * 60 + 45, familiarity: 'new'),
  ],
};

class FakeRepository implements Repository {
  FakeRepository({this.role = 'carer', Object? dayError}) : _dayError = dayError;

  final String role;
  Object? _dayError;
  final submitted = <Map<String, dynamic>>[];

  /// Errors to throw from the next submits, in order (after recording the attempt).
  final submitErrors = <Object>[];
  Day day = Day.fromJson(dayJson());

  set dayError(Object? e) => _dayError = e;

  @override
  Future<Me> signIn(String username, String password) async {
    if (password != 'demo-carer') throw const ApiError('not authenticated', status: 401);
    return me();
  }

  @override
  Future<Me> me() async => Me(username: 'joy@demo.smartpbl', displayName: 'Joy A.', role: role);

  @override
  Future<void> signOut() async {}

  @override
  Future<Day> myDay() async {
    if (_dayError != null) throw _dayError!;
    return day;
  }

  @override
  Future<Visit> visit(String visitId) async {
    final base = dayJson()['visits'] as List;
    final j = base.cast<Map<String, dynamic>>().firstWhere((v) => v['visit_id'] == visitId);
    return Visit.fromJson({
      ...j,
      'recent_notes': [
        {
          'note_id': 'n1',
          'visit_time': '2026-11-05T09:00:00Z',
          'text': 'Mentioned knee pain on stairs.',
          'review_required': false,
          'flags': [
            {'category': 'falls', 'severity': 'medium'},
          ],
        },
      ],
    });
  }

  @override
  Future<void> submitNote(NewNote note) async {
    submitted.add(note.toJson());
    if (submitErrors.isNotEmpty) throw submitErrors.removeAt(0);
    day = Day.fromJson(dayJson()); // the server would now report it done
  }
}

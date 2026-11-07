/// The carer API's responses (app/api/me.py), as immutable Dart objects.
library;

class Task {
  const Task({required this.key, required this.label, required this.detail});
  factory Task.fromJson(Map<String, dynamic> j) =>
      Task(key: j['key'] as String, label: j['label'] as String, detail: j['detail'] as String);
  final String key;
  final String label;
  final String detail;
}

class Place {
  const Place(this.lat, this.lon);
  final double lat;
  final double lon;
}

class SubmittedNote {
  const SubmittedNote({required this.noteId, required this.submittedAt, required this.urgent});
  final String? noteId;
  final DateTime submittedAt;
  final bool urgent;
}

class NoteFlag {
  const NoteFlag(this.category, this.severity);
  final String category;
  final String severity;
}

class RecentNote {
  const RecentNote({required this.visitTime, required this.text, required this.reviewRequired, required this.flags});
  factory RecentNote.fromJson(Map<String, dynamic> j) => RecentNote(
    visitTime: DateTime.parse(j['visit_time'] as String),
    text: j['text'] as String,
    reviewRequired: j['review_required'] as bool,
    flags: [for (final f in j['flags'] as List) NoteFlag((f as Map)['category'] as String, f['severity'] as String)],
  );
  final DateTime visitTime;
  final String text;
  final bool reviewRequired;
  final List<NoteFlag> flags;
}

class Visit {
  const Visit({
    required this.visitId,
    required this.sequence,
    required this.clientRef,
    required this.startMin,
    required this.endMin,
    required this.durationMin,
    required this.travelMin,
    required this.familiarity,
    required this.windowStartMin,
    required this.windowEndMin,
    required this.timeCritical,
    required this.tasks,
    required this.location,
    required this.note,
    this.recentNotes = const [],
  });

  factory Visit.fromJson(Map<String, dynamic> j) {
    final loc = j['location'] as Map<String, dynamic>?;
    final note = j['note'] as Map<String, dynamic>?;
    return Visit(
      visitId: j['visit_id'] as String,
      sequence: j['sequence'] as int,
      clientRef: j['client_ref'] as String,
      startMin: j['start_min'] as int,
      endMin: j['end_min'] as int,
      durationMin: j['duration_min'] as int,
      travelMin: j['travel_min'] as int,
      familiarity: j['familiarity'] as String,
      windowStartMin: j['window_start_min'] as int?,
      windowEndMin: j['window_end_min'] as int?,
      timeCritical: j['time_critical'] as bool,
      tasks: [for (final t in j['tasks'] as List) Task.fromJson(t as Map<String, dynamic>)],
      location: loc == null ? null : Place((loc['lat'] as num).toDouble(), (loc['lon'] as num).toDouble()),
      note: note == null
          ? null
          : SubmittedNote(
              noteId: note['note_id'] as String?,
              submittedAt: DateTime.parse(note['submitted_at'] as String),
              urgent: note['urgent'] as bool,
            ),
      recentNotes: [
        for (final n in (j['recent_notes'] as List?) ?? const []) RecentNote.fromJson(n as Map<String, dynamic>),
      ],
    );
  }

  final String visitId;
  final int sequence;
  final String clientRef;
  final int startMin; // planned arrival, minutes after midnight
  final int endMin;
  final int durationMin;
  final int travelMin;
  final String familiarity; // preferred / recent / new
  final int? windowStartMin;
  final int? windowEndMin;
  final bool timeCritical;
  final List<Task> tasks;
  final Place? location;
  final SubmittedNote? note;
  final List<RecentNote> recentNotes; // detail endpoint only

  bool get done => note != null;
}

class Day {
  const Day({required this.day, required this.carerRef, required this.visits, required this.travelMin});
  factory Day.fromJson(Map<String, dynamic> j) => Day(
    day: DateTime.parse(j['day'] as String),
    carerRef: j['carer_ref'] as String,
    visits: [for (final v in j['visits'] as List) Visit.fromJson(v as Map<String, dynamic>)],
    travelMin: (j['summary'] as Map)['travel_min'] as int,
  );

  final DateTime day;
  final String carerRef;
  final List<Visit> visits;
  final int travelMin;

  int get done => visits.where((v) => v.done).length;

  /// The next visit to do: the first without a note, in rota order (not by clock, so the
  /// demo works at any time of day).
  Visit? get next => visits.where((v) => !v.done).firstOrNull;
}

/// What the Submitted screen shows: kept in memory after a successful submit.
class Submission {
  const Submission({
    required this.visit,
    required this.submittedAt,
    required this.tasksDone,
    required this.urgent,
    required this.next,
  });
  final Visit visit;
  final DateTime submittedAt;
  final int tasksDone;
  final bool urgent;
  final Visit? next;
}

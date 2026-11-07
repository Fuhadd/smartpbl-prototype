/// Display helpers for the carer screens. Pure functions, unit tested.
library;

import 'package:flutter/widgets.dart';
import 'package:lucide_icons_flutter/lucide_icons.dart';

String hhmm(int minutes) =>
    '${(minutes ~/ 60).toString().padLeft(2, '0')}:${(minutes % 60).toString().padLeft(2, '0')}';

/// "09:30 – 10:15", with en dashes as in the designs.
String span(int start, int end) => '${hhmm(start)} – ${hhmm(end)}';

String greeting(DateTime now) {
  final h = now.hour;
  return h < 12 ? 'Good morning' : (h < 18 ? 'Good afternoon' : 'Good evening');
}

/// "Joy" from "Joy A."; falls back to the whole name.
String firstName(String displayName) {
  final parts = displayName.trim().split(RegExp(r'\s+'));
  return parts.isEmpty || parts.first.isEmpty ? displayName : parts.first;
}

// English names by hand: intl's en_GB data needs an async initialise before first use.
const _weekdays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const _months = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
];

/// "Saturday, 7 November".
String dayLabel(DateTime day) => '${_weekdays[day.weekday - 1]}, ${day.day} ${_months[day.month - 1]}';

/// The pill on the next-visit card and the detail header. Text, never colour alone.
String familiarityLabel(String familiarity) => switch (familiarity) {
  'preferred' => 'Preferred carer',
  'recent' => 'Familiar client',
  _ => 'New client',
};

/// "Next visit · in 25 min" when it's later today, otherwise just "Next visit".
String nextLabel(DateTime now, DateTime day, int startMin) {
  final today = now.year == day.year && now.month == day.month && now.day == day.day;
  final minutesNow = now.hour * 60 + now.minute;
  final inMin = startMin - minutesNow;
  if (!today || inMin <= 0) return 'Next visit';
  if (inMin < 60) return 'Next visit · in $inMin min';
  return 'Next visit · in ${inMin ~/ 60} h ${inMin % 60} min';
}

IconData taskIcon(String key) => switch (key) {
  'medication' => LucideIcons.pill,
  'catheter_care' => LucideIcons.droplet,
  'manual_handling' => LucideIcons.accessibility,
  'dementia_care' => LucideIcons.brain,
  _ => LucideIcons.bath,
};

/// Risk categories as the dashboard shortens them (web/src/review/categories.ts).
String categoryLabel(String category) => switch (category) {
  'falls' => 'Falls',
  'medication' => 'Medication',
  'nutrition_hydration' => 'Nutrition',
  'skin_integrity' => 'Skin',
  'mood_behaviour' => 'Mood',
  'safeguarding' => 'Safeguarding',
  'missed_late_visit' => 'Late visit',
  _ => category,
};

/// "Thu" for a recent note.
String weekday(DateTime t) => _weekdays[t.toLocal().weekday - 1].substring(0, 3);

/// A note id the API accepts (`^[A-Za-z0-9_.-]{1,50}$`), unique per visit and second.
String noteId(String visitId, DateTime now) {
  final u = now.toUtc();
  String two(int n) => n.toString().padLeft(2, '0');
  return '$visitId-${u.year}${two(u.month)}${two(u.day)}${two(u.hour)}${two(u.minute)}${two(u.second)}';
}

/// OpenStreetMap with a marker at the visit (mlat/mlon, documented on the OSM wiki).
Uri directionsUri(double lat, double lon) =>
    Uri.parse('https://www.openstreetmap.org/?mlat=$lat&mlon=$lon#map=17/$lat/$lon');

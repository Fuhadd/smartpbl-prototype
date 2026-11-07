import 'package:flutter_test/flutter_test.dart';
import 'package:smartpbl_carer/visits/format.dart';
import 'package:smartpbl_carer/visits/models.dart';

import 'fixtures.dart';

void main() {
  test('times and spans', () {
    expect(hhmm(9 * 60 + 5), '09:05');
    expect(span(570, 615), '09:30 – 10:15');
  });

  test('greeting and first name', () {
    expect(greeting(DateTime(2026, 11, 7, 8)), 'Good morning');
    expect(greeting(DateTime(2026, 11, 7, 14)), 'Good afternoon');
    expect(greeting(DateTime(2026, 11, 7, 19)), 'Good evening');
    expect(firstName('Joy A.'), 'Joy');
    expect(firstName(''), '');
  });

  test('day label in English without locale data', () {
    expect(dayLabel(DateTime(2026, 11, 7)), 'Saturday, 7 November');
  });

  test('"in N min" only for a later visit today', () {
    final day = DateTime(2026, 11, 7);
    expect(nextLabel(DateTime(2026, 11, 7, 9, 5), day, 570), 'Next visit · in 25 min');
    expect(nextLabel(DateTime(2026, 11, 7, 7, 0), day, 570), 'Next visit · in 2 h 30 min');
    expect(nextLabel(DateTime(2026, 11, 7, 10, 0), day, 570), 'Next visit');
    expect(nextLabel(DateTime(2026, 11, 8, 9, 0), day, 570), 'Next visit');
  });

  test('note ids match the API pattern', () {
    final id = noteId('V-0047', DateTime.utc(2026, 11, 7, 9, 41, 3));
    expect(id, 'V-0047-20261107094103');
    expect(RegExp(r'^[A-Za-z0-9_.-]{1,50}$').hasMatch(id), isTrue);
  });

  test('familiarity is said in words', () {
    expect(familiarityLabel('preferred'), 'Preferred carer');
    expect(familiarityLabel('recent'), 'Familiar client');
    expect(familiarityLabel('new'), 'New client');
  });

  test('the next visit is the first not written up, in rota order', () {
    final day = Day.fromJson(dayJson());
    expect(day.done, 1);
    expect(day.next!.visitId, 'V-0096');
    expect(Day.fromJson(dayJson(firstDone: false)).next!.visitId, 'V-0047');
  });

  test('directions open OpenStreetMap at the visit', () {
    expect(
      directionsUri(52.45, -1.89).toString(),
      'https://www.openstreetmap.org/?mlat=52.45&mlon=-1.89#map=17/52.45/-1.89',
    );
  });
}

/// Every API call the carer app makes, behind one class so widget tests can fake it.
library;

import 'package:dio/dio.dart';

import '../visits/models.dart';
import 'api.dart';

class Me {
  const Me({required this.username, required this.displayName, required this.role});
  final String username;
  final String displayName;
  final String role;
}

class NewNote {
  const NewNote({
    required this.noteId,
    required this.visit,
    required this.carerRef,
    required this.visitTime,
    required this.text,
    required this.urgent,
    required this.tasksDone,
  });
  final String noteId;
  final Visit visit;
  final String carerRef;
  final DateTime visitTime;
  final String text;
  final bool urgent;
  final List<String> tasksDone;

  Map<String, dynamic> toJson() => {
    'note_id': noteId,
    'client_ref': visit.clientRef,
    'carer_ref': carerRef,
    'visit_id': visit.visitId,
    'visit_time': visitTime.toUtc().toIso8601String(),
    'text': text,
    'urgent': urgent,
    'tasks_done': tasksDone,
  };
}

class Repository {
  Repository(this._dio, this._store);

  final Dio _dio;
  final TokenStore _store;

  Future<T> _call<T>(Future<T> Function() f) async {
    try {
      return await f();
    } catch (e) {
      throw ApiError.from(e);
    }
  }

  /// OAuth2 password form (form-encoded, as FastAPI's OAuth2PasswordRequestForm expects).
  Future<Me> signIn(String username, String password) => _call(() async {
    final r = await _dio.post<Map<String, dynamic>>(
      '/auth/token',
      data: {'username': username, 'password': password},
      options: Options(contentType: Headers.formUrlEncodedContentType),
    );
    _store.tokens = Tokens(access: r.data!['access_token'] as String, refresh: r.data!['refresh_token'] as String);
    return me();
  });

  Future<Me> me() => _call(() async {
    final r = await _dio.get<Map<String, dynamic>>('/auth/me');
    final j = r.data!;
    return Me(
      username: j['username'] as String,
      displayName: (j['display_name'] as String?) ?? '',
      role: j['role'] as String,
    );
  });

  /// Revokes the refresh token server-side; local tokens are dropped whatever happens.
  Future<void> signOut() async {
    final refresh = _store.tokens?.refresh;
    _store.tokens = null;
    if (refresh == null) return;
    try {
      await _dio.post<void>('/auth/logout', data: {'refresh_token': refresh});
    } catch (_) {
      // Offline or already revoked: the token expires on its own.
    }
  }

  Future<Day> myDay() => _call(() async {
    final r = await _dio.get<Map<String, dynamic>>('/me/visits');
    return Day.fromJson(r.data!);
  });

  Future<Visit> visit(String visitId) => _call(() async {
    final r = await _dio.get<Map<String, dynamic>>('/me/visits/$visitId');
    return Visit.fromJson(r.data!);
  });

  Future<void> submitNote(NewNote note) => _call(() async {
    await _dio.post<Map<String, dynamic>>('/notes', data: note.toJson());
  });
}

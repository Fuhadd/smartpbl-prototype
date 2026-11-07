/// The API client: Dio with a bearer token, a single-flight refresh on 401 and one retry.
///
/// Mirrors the dashboard's `authFetch` (web/src/api/client.ts). Refresh tokens are single
/// use with reuse detection (ADR-025), so requests that hit 401 together must share one
/// refresh: two parallel refreshes would look like token theft and end the session.
library;

import 'dart:async';

import 'package:dio/dio.dart';

class Tokens {
  const Tokens({required this.access, required this.refresh});
  final String access;
  final String refresh;
}

/// Where the session's tokens live: memory only, as in the dashboard (ADR-027). An
/// injected script can't read them from storage; the cost is signing in again after a
/// reload. Native builds would use the platform keystore (backlog).
class TokenStore {
  Tokens? tokens;
  final _ended = StreamController<void>.broadcast();

  /// Fires when a refresh fails: the UI returns to sign-in.
  Stream<void> get sessionEnded => _ended.stream;

  void end() {
    tokens = null;
    _ended.add(null);
  }
}

class ApiError implements Exception {
  const ApiError(this.message, {this.status, this.requestId});

  final String message;
  final int? status;
  final String? requestId;

  /// "req_8f2c41", as the dashboard shows it (from the X-Request-ID header).
  String? get reference => requestId == null ? null : 'req_${requestId!.replaceAll('-', '').substring(0, 6)}';

  bool get isNetwork => status == null;

  static ApiError from(Object e) {
    if (e is ApiError) return e;
    if (e is DioException) {
      final r = e.response;
      if (r == null) return const ApiError("Couldn't reach the server. Check your connection and try again.");
      final data = r.data;
      final detail = data is Map && data['detail'] is String ? data['detail'] as String : 'HTTP ${r.statusCode}';
      return ApiError(detail, status: r.statusCode, requestId: r.headers.value('x-request-id'));
    }
    return ApiError(e.toString());
  }

  @override
  String toString() => 'ApiError($status, $message)';
}

const _noRefresh = {'/auth/token', '/auth/refresh', '/auth/logout'};

/// A plain `Interceptor` with its own single-flight future, not a `QueuedInterceptor`: the
/// queued one serialises errors, so a retried request that also failed would wait behind
/// the very handler awaiting it (deadlock).
class AuthInterceptor extends Interceptor {
  AuthInterceptor(this._store, this._dio);

  final TokenStore _store;
  final Dio _dio;
  Future<bool>? _refreshing;

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    final t = _store.tokens;
    if (t != null && !_noRefresh.contains(options.path)) {
      options.headers['Authorization'] = 'Bearer ${t.access}';
    }
    handler.next(options);
  }

  @override
  Future<void> onError(DioException err, ErrorInterceptorHandler handler) async {
    final req = err.requestOptions;
    final retried = req.extra['retried'] == true;
    if (err.response?.statusCode != 401 || _noRefresh.contains(req.path) || retried) {
      return handler.next(err);
    }
    if (!await _refreshOnce()) return handler.next(err);
    try {
      req.extra['retried'] = true;
      req.headers['Authorization'] = 'Bearer ${_store.tokens!.access}';
      handler.resolve(await _dio.fetch<dynamic>(req));
    } on DioException catch (e) {
      handler.next(e);
    }
  }

  Future<bool> _refreshOnce() => _refreshing ??= _refresh().whenComplete(() => _refreshing = null);

  Future<bool> _refresh() async {
    final refresh = _store.tokens?.refresh;
    if (refresh == null) return false;
    try {
      final r = await _dio.post<Map<String, dynamic>>('/auth/refresh', data: {'refresh_token': refresh});
      _store.tokens = Tokens(access: r.data!['access_token'] as String, refresh: r.data!['refresh_token'] as String);
      return true;
    } on DioException {
      _store.end(); // a failed refresh ends the session (and may mean the token was reused)
      return false;
    }
  }
}

Dio buildDio(TokenStore store, {String baseUrl = '', HttpClientAdapter? adapter}) {
  final dio = Dio(
    BaseOptions(
      baseUrl: baseUrl,
      connectTimeout: const Duration(seconds: 15),
      // A note waits for the LLM (seconds) and a cold Cloud Run start; generous, not infinite.
      receiveTimeout: const Duration(seconds: 90),
      contentType: Headers.jsonContentType,
    ),
  );
  if (adapter != null) dio.httpClientAdapter = adapter;
  dio.interceptors.add(AuthInterceptor(store, dio));
  return dio;
}

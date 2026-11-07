/// The auth interceptor against a fake HTTP adapter: bearer header, one shared refresh for
/// parallel 401s, one retry, and a failed refresh ending the session.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:smartpbl_carer/core/api.dart';

class FakeAdapter implements HttpClientAdapter {
  FakeAdapter(this.handler);
  final ResponseBody Function(RequestOptions o) handler;
  final calls = <String>[];

  @override
  Future<ResponseBody> fetch(RequestOptions o, Stream<Uint8List>? body, Future<void>? cancel) async {
    calls.add('${o.method} ${o.path} ${o.headers['Authorization'] ?? '-'}');
    await Future<void>.delayed(const Duration(milliseconds: 5)); // let parallel calls overlap
    return handler(o);
  }

  @override
  void close({bool force = false}) {}
}

ResponseBody json(Object body, [int status = 200]) => ResponseBody.fromString(
  jsonEncode(body),
  status,
  headers: {
    Headers.contentTypeHeader: [Headers.jsonContentType],
    'x-request-id': ['8f2c41aa-0000-4000-8000-000000000000'],
  },
);

void main() {
  test('sends the bearer token', () async {
    final store = TokenStore()..tokens = const Tokens(access: 'A1', refresh: 'R1');
    final adapter = FakeAdapter((_) => json({'ok': true}));
    await buildDio(store, adapter: adapter).get<dynamic>('/me/visits');
    expect(adapter.calls, ['GET /me/visits Bearer A1']);
  });

  test('parallel 401s share one refresh, then each retries once with the new token', () async {
    final store = TokenStore()..tokens = const Tokens(access: 'old', refresh: 'R1');
    final adapter = FakeAdapter((o) {
      if (o.path == '/auth/refresh') return json({'access_token': 'new', 'refresh_token': 'R2'});
      return o.headers['Authorization'] == 'Bearer new' ? json({'ok': true}) : json({'detail': 'expired'}, 401);
    });
    final dio = buildDio(store, adapter: adapter);
    await Future.wait([dio.get<dynamic>('/me/visits'), dio.get<dynamic>('/me/visits/V-0047')]);
    expect(adapter.calls.where((c) => c.startsWith('POST /auth/refresh')), hasLength(1));
    expect(store.tokens!.refresh, 'R2');
    expect(adapter.calls.where((c) => c.endsWith('Bearer new')), hasLength(2));
  });

  test('a failed refresh ends the session and surfaces the 401', () async {
    final store = TokenStore()..tokens = const Tokens(access: 'old', refresh: 'R1');
    final ended = expectLater(store.sessionEnded, emits(null));
    final adapter = FakeAdapter((o) => json({'detail': 'not authenticated'}, 401));
    final dio = buildDio(store, adapter: adapter);
    final error = await dio.get<dynamic>('/me/visits').then<Object?>((_) => null, onError: (Object e) => e);
    expect(ApiError.from(error!).status, 401);
    expect(store.tokens, isNull);
    await ended;
  });

  test('errors carry the server detail and a short reference', () async {
    final store = TokenStore();
    final adapter = FakeAdapter((_) => json({'detail': "that visit isn't on your rota"}, 403));
    final error = await buildDio(
      store,
      adapter: adapter,
    ).post<dynamic>('/notes', data: {}).then<Object?>((_) => null, onError: (Object e) => e);
    final e = ApiError.from(error!);
    expect(e.message, "that visit isn't on your rota");
    expect(e.reference, 'req_8f2c41');
  });
}

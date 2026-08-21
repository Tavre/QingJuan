import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:qingjuan/core/api/api_client.dart';
import 'package:qingjuan/core/backend/user_session_store.dart';
import 'package:qingjuan/features/auth/auth_controller.dart';

void main() {
  test('loading registration policy does not block login', () async {
    final policyGate = Completer<void>();
    late AuthController auth;
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      userToken: () => auth.userToken,
      client: MockClient((request) async {
        switch (request.url.path) {
          case '/api/v1/auth/registration-policy':
            await policyGate.future;
            return _jsonResponse(<String, dynamic>{
              'emailRequired': true,
              'emailVerificationRequired': true,
              'identityBadgeRequired': false,
            });
          case '/api/v1/auth/login':
            return _jsonResponse(<String, dynamic>{
              'token': 'user-token',
              'user': _userJson,
            });
          default:
            fail('Unexpected request: ${request.url.path}');
        }
      }),
    );
    auth = AuthController(
      api,
      _MemoryUserSessionStore(),
      backendUrl: () => 'https://qingjuan.example.test',
    );
    addTearDown(() {
      auth.dispose();
      api.close();
    });
    await auth.initializeForCurrentBackend(multiUser: true);

    final loading = auth.loadRegistrationPolicy();
    expect(auth.registrationPolicyLoading, isTrue);
    expect(auth.isBusy, isFalse);

    await auth.login(username: 'reader', password: 'secret');
    expect(auth.isAuthenticated, isTrue);

    policyGate.complete();
    await loading;
    expect(auth.registrationPolicy?.emailVerificationRequired, isTrue);
    expect(auth.registrationPolicyLoading, isFalse);
  });

  test('email code errors are observable and retryable', () async {
    var attempts = 0;
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      client: MockClient((request) async {
        attempts += 1;
        if (attempts == 1) {
          return _jsonResponse(<String, String>{'detail': 'SMTP 暂不可用'}, 400);
        }
        return http.Response('', 204);
      }),
    );
    final auth = AuthController(
      api,
      _MemoryUserSessionStore(),
      backendUrl: () => 'https://qingjuan.example.test',
    );
    addTearDown(() {
      auth.dispose();
      api.close();
    });
    await auth.initializeForCurrentBackend(multiUser: true);

    await expectLater(
      auth.sendRegistrationEmailCode(email: 'reader@example.test'),
      throwsException,
    );
    expect(auth.emailCodeSending, isFalse);
    expect(auth.emailCodeError, contains('SMTP 暂不可用'));

    await auth.sendRegistrationEmailCode(email: 'reader@example.test');
    expect(auth.emailCodeSending, isFalse);
    expect(auth.emailCodeError, isNull);
  });
}

const _userJson = <String, dynamic>{
  'id': 'user-1',
  'username': 'reader',
  'displayName': '读者',
  'role': 'user',
  'status': 'active',
  'createdAt': '2026-08-21T00:00:00Z',
};

http.Response _jsonResponse(Object body, [int statusCode = 200]) =>
    http.Response.bytes(
      utf8.encode(jsonEncode(body)),
      statusCode,
      headers: const <String, String>{'content-type': 'application/json'},
    );

class _MemoryUserSessionStore implements UserSessionStore {
  String? token;

  @override
  Future<void> deleteToken() async => token = null;

  @override
  Future<String?> readToken(String backendUrl) async => token;

  @override
  Future<void> writeToken({
    required String backendUrl,
    required String token,
  }) async =>
      this.token = token;
}

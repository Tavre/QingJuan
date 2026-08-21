import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:qingjuan/core/api/api_client.dart';
import 'package:qingjuan/core/models/user_account.dart';

void main() {
  test('registration API loads policy, sends code and submits all checks',
      () async {
    final requests = <http.Request>[];
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      token: () => 'connection-token',
      userToken: () => 'stale-user-token',
      client: MockClient((request) async {
        requests.add(request);
        expect(request.headers['Authorization'], 'Bearer connection-token');
        expect(request.headers.containsKey('X-QingJuan-User-Token'), isFalse);
        switch (request.url.path) {
          case '/api/v1/auth/registration-policy':
            return _jsonResponse(<String, dynamic>{
              'emailRequired': true,
              'emailVerificationRequired': true,
              'identityBadgeRequired': true,
              'githubLoginEnabled': true,
            });
          case '/api/v1/auth/email-code':
            expect(
              jsonDecode(request.body),
              <String, dynamic>{'email': 'reader@example.test'},
            );
            return http.Response('', 204);
          case '/api/v1/auth/register':
            expect(
              jsonDecode(request.body),
              <String, dynamic>{
                'username': 'reader',
                'displayName': '读者',
                'email': 'reader@example.test',
                'password': 'very-secret-password',
                'emailCode': '246810',
                'identityBadge': 'QJ-FAMILY',
              },
            );
            return _jsonResponse(<String, dynamic>{
              'token': 'fresh-user-token',
              'user': <String, dynamic>{
                ..._userJson,
                'email': 'reader@example.test',
              },
            });
          default:
            fail('Unexpected request: ${request.method} ${request.url.path}');
        }
      }),
    );
    addTearDown(api.close);

    final policy = await api.fetchRegistrationPolicy();
    expect(policy.emailRequired, isTrue);
    expect(policy.emailVerificationRequired, isTrue);
    expect(policy.identityBadgeRequired, isTrue);
    expect(policy.githubLoginEnabled, isTrue);

    await api.sendRegistrationEmailCode(email: 'reader@example.test');
    final session = await api.registerUser(
      username: 'reader',
      displayName: '读者',
      email: 'reader@example.test',
      password: 'very-secret-password',
      emailCode: '246810',
      identityBadge: 'QJ-FAMILY',
    );

    expect(session.user.email, 'reader@example.test');
    expect(requests.map((request) => request.method), <String>[
      'GET',
      'POST',
      'POST',
    ]);
  });

  test('registration policy and user email parse older compatible payloads',
      () {
    final policy = RegistrationPolicy.fromJson(const <String, dynamic>{});
    final user = UserAccount.fromJson(_userJson);

    expect(policy.emailRequired, isTrue);
    expect(policy.emailVerificationRequired, isFalse);
    expect(policy.identityBadgeRequired, isFalse);
    expect(policy.githubLoginEnabled, isFalse);
    expect(user.email, isEmpty);
  });

  test('registration and credential posts never retry network failures',
      () async {
    var calls = 0;
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      client: MockClient((request) async {
        calls += 1;
        throw const SocketException('response lost');
      }),
    );
    addTearDown(api.close);

    await expectLater(
      api.sendRegistrationEmailCode(email: 'reader@example.test'),
      throwsException,
    );
    expect(calls, 1);

    await expectLater(
      api.registerUser(
        username: 'reader',
        displayName: '读者',
        email: 'reader@example.test',
        password: 'very-secret-password',
      ),
      throwsException,
    );
    expect(calls, 2);

    await expectLater(
      api.loginUser(username: 'reader', password: 'very-secret-password'),
      throwsException,
    );
    expect(calls, 3);
  });
}

const _userJson = <String, dynamic>{
  'id': 'user-1',
  'username': 'reader',
  'displayName': '读者',
  'role': 'user',
  'status': 'active',
  'createdAt': '2026-08-21T00:00:00Z',
  'lastLoginAt': '2026-08-21T01:00:00Z',
};

http.Response _jsonResponse(Object body, [int statusCode = 200]) =>
    http.Response.bytes(
      utf8.encode(jsonEncode(body)),
      statusCode,
      headers: const <String, String>{'content-type': 'application/json'},
    );

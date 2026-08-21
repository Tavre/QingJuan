import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:qingjuan/core/api/api_client.dart';
import 'package:qingjuan/core/models/user_account.dart';

void main() {
  test('password login models a 2FA challenge and completes it anonymously',
      () async {
    final requests = <http.Request>[];
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      token: () => 'connection-token',
      userToken: () => 'stale-user-token',
      client: MockClient((request) async {
        requests.add(request);
        expect(request.headers.containsKey('X-QingJuan-User-Token'), isFalse);
        if (request.url.path == '/api/v1/auth/login') {
          return _json(<String, dynamic>{
            'requiresTwoFactor': true,
            'challengeToken': 'challenge-secret',
            'expiresInSeconds': 300,
          });
        }
        expect(request.url.path, '/api/v1/auth/login/2fa');
        expect(jsonDecode(request.body), <String, dynamic>{
          'challengeToken': 'challenge-secret',
          'code': '123456',
        });
        return _json(<String, dynamic>{'token': 'fresh-token', 'user': _user});
      }),
    );
    addTearDown(api.close);

    final login = await api.loginUser(username: 'reader', password: 'secret');
    expect(login, isA<TwoFactorLoginChallenge>());
    final challenge = login as TwoFactorLoginChallenge;
    expect(challenge.challengeToken, 'challenge-secret');

    final session = await api.completeTwoFactorLogin(
      challengeToken: challenge.challengeToken,
      code: '123456',
    );
    expect(session.token, 'fresh-token');
    expect(requests, hasLength(2));
  });

  test('GitHub login is anonymous while binding uses the current user token',
      () async {
    final requests = <http.Request>[];
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      userToken: () => 'current-user-token',
      client: MockClient((request) async {
        requests.add(request);
        if (request.url.path.endsWith('/start')) {
          final body = jsonDecode(request.body) as Map<String, dynamic>;
          if (body['purpose'] == 'bind') {
            expect(body['password'], 'current-password');
            expect(body['code'], '123456');
          }
          return _json(<String, dynamic>{
            'flowId': 'flow-${body['purpose']}',
            'userCode': 'ABCD-EFGH',
            'verificationUri': 'https://attacker.example/phish',
            'expiresInSeconds': 900,
            'intervalSeconds': 3,
          });
        }
        return _json(<String, dynamic>{
          'status': 'pending',
          'retryAfterSeconds': 4,
        });
      }),
    );
    addTearDown(api.close);

    final login = await api.startGitHubDevice(purpose: 'login');
    expect(login.safeVerificationUri.host, 'github.com');
    expect(login.safeVerificationUri.path, '/login/device');
    await api.pollGitHubDevice(login);

    final bind = await api.startGitHubDevice(
      purpose: 'bind',
      password: 'current-password',
      code: '123456',
    );
    await api.pollGitHubDevice(bind);

    expect(
      requests.take(2).every(
            (request) => !request.headers.containsKey('X-QingJuan-User-Token'),
          ),
      isTrue,
    );
    expect(
      requests.skip(2).every(
            (request) =>
                request.headers['X-QingJuan-User-Token'] ==
                'current-user-token',
          ),
      isTrue,
    );
  });

  test('account security APIs parse setup and one-time recovery codes',
      () async {
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      userToken: () => 'current-user-token',
      client: MockClient((request) async {
        expect(
          request.headers['X-QingJuan-User-Token'],
          'current-user-token',
        );
        return switch (request.url.path) {
          '/api/v1/auth/account/security' => _json(<String, dynamic>{
              'github': <String, dynamic>{
                'available': true,
                'bound': true,
                'login': 'octocat',
              },
              'twoFactor': <String, dynamic>{
                'enabled': true,
                'recoveryCodesRemaining': 7,
              },
            }),
          '/api/v1/auth/account/2fa/setup' => _json(<String, dynamic>{
              'setupId': 'setup-id',
              'secret': 'JBSWY3DPEHPK3PXP',
              'otpauthUri': 'otpauth://totp/QingJuan:reader?secret=SECRET',
              'expiresInSeconds': 600,
            }),
          '/api/v1/auth/account/2fa/enable' ||
          '/api/v1/auth/account/2fa/recovery-codes' =>
            _json(<String, dynamic>{
              'recoveryCodes': <String>['code-one', 'code-two'],
            }),
          _ => http.Response('', 204),
        };
      }),
    );
    addTearDown(api.close);

    final security = await api.fetchAccountSecurity();
    expect(security.githubLogin, 'octocat');
    expect(security.recoveryCodesRemaining, 7);
    final setup = await api.setupTwoFactor(password: 'password');
    expect(setup.setupId, 'setup-id');
    final enabled = await api.enableTwoFactor(
      setupId: setup.setupId,
      code: '123456',
    );
    expect(enabled.values, <String>['code-one', 'code-two']);
    final regenerated = await api.regenerateTwoFactorRecoveryCodes(
      password: 'password',
      code: '654321',
    );
    expect(regenerated.values, hasLength(2));
  });

  test('secret-returning and account mutations never retry network failures',
      () async {
    var calls = 0;
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      userToken: () => 'current-user-token',
      client: MockClient((request) async {
        calls += 1;
        throw const SocketException('response lost');
      }),
    );
    addTearDown(api.close);

    await expectLater(
      api.startGitHubDevice(purpose: 'login'),
      throwsException,
    );
    expect(calls, 1);
    await expectLater(
      api.completeTwoFactorLogin(
        challengeToken: 'challenge',
        code: '123456',
      ),
      throwsException,
    );
    expect(calls, 2);
    await expectLater(
      api.unbindGitHub(password: 'password'),
      throwsException,
    );
    expect(calls, 3);
    await expectLater(
      api.setupTwoFactor(password: 'password'),
      throwsException,
    );
    expect(calls, 4);
    await expectLater(
      api.enableTwoFactor(setupId: 'setup', code: '123456'),
      throwsException,
    );
    expect(calls, 5);
    await expectLater(
      api.disableTwoFactor(password: 'password', code: '123456'),
      throwsException,
    );
    expect(calls, 6);
    await expectLater(
      api.regenerateTwoFactorRecoveryCodes(
        password: 'password',
        code: '123456',
      ),
      throwsException,
    );
    expect(calls, 7);
  });
}

const _user = <String, dynamic>{
  'id': 'user-1',
  'username': 'reader',
  'displayName': '读者',
  'role': 'user',
  'status': 'active',
  'createdAt': '2026-08-21T00:00:00Z',
};

http.Response _json(Object body, [int statusCode = 200]) => http.Response.bytes(
      utf8.encode(jsonEncode(body)),
      statusCode,
      headers: const <String, String>{'content-type': 'application/json'},
    );

import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:qingjuan/core/api/api_client.dart';
import 'package:qingjuan/core/backend/user_session_store.dart';
import 'package:qingjuan/core/models/user_account.dart';
import 'package:qingjuan/features/auth/auth_controller.dart';

void main() {
  test('password login keeps a 2FA challenge and completes without password',
      () async {
    final store = _MemoryStore();
    late AuthController auth;
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      userToken: () => auth.userToken,
      client: MockClient((request) async {
        if (request.url.path == '/api/v1/auth/login') {
          return _json(<String, dynamic>{
            'requiresTwoFactor': true,
            'challengeToken': 'challenge-token',
            'expiresInSeconds': 300,
          });
        }
        expect(request.url.path, '/api/v1/auth/login/2fa');
        return _json(<String, dynamic>{'token': 'user-token', 'user': _user});
      }),
    );
    auth = AuthController(
      api,
      store,
      backendUrl: () => 'https://qingjuan.example.test',
    );
    addTearDown(() {
      auth.dispose();
      api.close();
    });
    await auth.initializeForCurrentBackend(multiUser: true);

    await auth.login(username: 'reader', password: 'password');
    expect(auth.loginTwoFactorChallenge?.challengeToken, 'challenge-token');
    expect(auth.isAuthenticated, isFalse);

    await auth.completeTwoFactorLogin(code: '123456');
    expect(auth.isAuthenticated, isTrue);
    expect(auth.loginTwoFactorChallenge, isNull);
    expect(store.token, 'user-token');
  });

  test('GitHub device polling supports pending then authenticated', () async {
    var polls = 0;
    final store = _MemoryStore();
    late AuthController auth;
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      userToken: () => auth.userToken,
      client: MockClient((request) async {
        if (request.url.path.endsWith('/start')) {
          return _json(<String, dynamic>{
            'flowId': 'flow-id',
            'userCode': 'ABCD-EFGH',
            'verificationUri': 'https://github.com/login/device',
            'expiresInSeconds': 900,
            'intervalSeconds': 1,
          });
        }
        polls += 1;
        if (polls == 1) {
          return _json(<String, dynamic>{
            'status': 'pending',
            'retryAfterSeconds': 1,
          });
        }
        return _json(<String, dynamic>{
          'status': 'authenticated',
          'token': 'github-user-token',
          'user': _user,
        });
      }),
    );
    auth = AuthController(
      api,
      store,
      backendUrl: () => 'https://qingjuan.example.test',
    );
    addTearDown(() {
      auth.dispose();
      api.close();
    });
    await auth.initializeForCurrentBackend(multiUser: true);

    final flow = await auth.startGitHubDevice(purpose: 'login');
    final pending = await auth.pollGitHubDevice(flow);
    expect(pending.status.name, 'pending');
    await auth.pollGitHubDevice(flow);

    expect(auth.isAuthenticated, isTrue);
    expect(store.token, 'github-user-token');
  });

  test('GitHub login still requires and completes the 2FA challenge', () async {
    final store = _MemoryStore();
    late AuthController auth;
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      userToken: () => auth.userToken,
      client: MockClient((request) async {
        return switch (request.url.path) {
          '/api/v1/auth/github/device/start' => _json(<String, dynamic>{
              'flowId': 'flow-with-2fa',
              'userCode': 'ABCD-EFGH',
              'verificationUri': 'https://github.com/login/device',
              'expiresInSeconds': 900,
              'intervalSeconds': 1,
            }),
          '/api/v1/auth/github/device/poll' => _json(<String, dynamic>{
              'status': 'twoFactorRequired',
              'requiresTwoFactor': true,
              'challengeToken': 'github-2fa-challenge',
              'expiresInSeconds': 300,
            }),
          '/api/v1/auth/login/2fa' => _json(<String, dynamic>{
              'token': 'two-factor-user-token',
              'user': _user,
            }),
          _ => throw StateError('Unexpected request: ${request.url.path}'),
        };
      }),
    );
    auth = AuthController(
      api,
      store,
      backendUrl: () => 'https://qingjuan.example.test',
    );
    addTearDown(() {
      auth.dispose();
      api.close();
    });
    await auth.initializeForCurrentBackend(multiUser: true);

    final flow = await auth.startGitHubDevice(purpose: 'login');
    final result = await auth.pollGitHubDevice(flow);

    expect(result.status, GitHubDevicePollStatus.twoFactorRequired);
    expect(auth.isAuthenticated, isFalse);
    expect(
        auth.loginTwoFactorChallenge?.challengeToken, 'github-2fa-challenge');
    expect(store.token, isNull);

    await auth.completeTwoFactorLogin(code: '123456');

    expect(auth.isAuthenticated, isTrue);
    expect(auth.loginTwoFactorChallenge, isNull);
    expect(store.token, 'two-factor-user-token');
  });

  test('cancelling GitHub flow prevents a delayed response taking ownership',
      () async {
    final responseGate = Completer<void>();
    late AuthController auth;
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      userToken: () => auth.userToken,
      client: MockClient((request) async {
        await responseGate.future;
        return _json(<String, dynamic>{
          'flowId': 'late-flow',
          'userCode': 'ABCD-EFGH',
          'verificationUri': 'https://github.com/login/device',
          'expiresInSeconds': 900,
          'intervalSeconds': 5,
        });
      }),
    );
    auth = AuthController(
      api,
      _MemoryStore(),
      backendUrl: () => 'https://qingjuan.example.test',
    );
    addTearDown(() {
      if (!responseGate.isCompleted) responseGate.complete();
      auth.dispose();
      api.close();
    });
    await auth.initializeForCurrentBackend(multiUser: true);

    final starting = auth.startGitHubDevice(purpose: 'login');
    expect(auth.githubDeviceBusy, isTrue);
    auth.cancelGitHubDeviceFlow();
    responseGate.complete();

    await expectLater(starting, throwsStateError);
    expect(auth.status, UserAuthStatus.anonymous);
    expect(auth.githubDeviceFlow, isNull);
  });

  test('recovery codes survive a failed security-status refresh', () async {
    var securityRequests = 0;
    final refreshGate = Completer<void>();
    final store = _MemoryStore()..token = 'saved-token';
    late AuthController auth;
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      userToken: () => auth.userToken,
      client: MockClient((request) async {
        switch (request.url.path) {
          case '/api/v1/auth/session':
            return _json(_user);
          case '/api/v1/auth/account/2fa/enable':
            return _json(<String, dynamic>{
              'recoveryCodes': <String>['keep-me-one', 'keep-me-two'],
            });
          case '/api/v1/auth/account/security':
            securityRequests += 1;
            await refreshGate.future;
            return _json(<String, String>{'detail': '刷新暂时失败'}, 500);
          default:
            fail('Unexpected request: ${request.url.path}');
        }
      }),
    );
    auth = AuthController(
      api,
      store,
      backendUrl: () => 'https://qingjuan.example.test',
    );
    addTearDown(() {
      if (!refreshGate.isCompleted) refreshGate.complete();
      auth.dispose();
      api.close();
    });
    await auth.initializeForCurrentBackend(multiUser: true);

    final recoveryCodes = await auth.enableTwoFactor(
      setupId: 'setup-id',
      code: '123456',
    );

    expect(recoveryCodes.values, <String>['keep-me-one', 'keep-me-two']);
    await Future<void>.delayed(Duration.zero);
    expect(securityRequests, 1);
    expect(auth.accountSecurityBusy, isFalse);
    refreshGate.complete();
    await Future<void>.delayed(Duration.zero);
    expect(auth.accountSecurityError, contains('刷新暂时失败'));
  });

  test('account 403 stays local while a genuine protected 401 expires session',
      () async {
    final store = _MemoryStore()..token = 'saved-token';
    late AuthController auth;
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      userToken: () => auth.userToken,
      onUserSessionExpired: () => auth.invalidateSession(),
      client: MockClient((request) async {
        return switch (request.url.path) {
          '/api/v1/auth/session' => _json(_user),
          '/api/v1/auth/account/github/unbind' =>
            _json(<String, String>{'detail': '当前密码或验证码错误'}, 403),
          '/api/v1/auth/account/security' =>
            _json(<String, String>{'detail': '用户会话已失效'}, 401),
          _ => throw StateError('Unexpected request: ${request.url.path}'),
        };
      }),
    );
    auth = AuthController(
      api,
      store,
      backendUrl: () => 'https://qingjuan.example.test',
    );
    addTearDown(() {
      auth.dispose();
      api.close();
    });
    await auth.initializeForCurrentBackend(multiUser: true);

    await expectLater(
      auth.unbindGitHub(password: 'wrong-password'),
      throwsException,
    );
    expect(auth.isAuthenticated, isTrue);
    expect(auth.userToken, 'saved-token');
    expect(store.token, 'saved-token');
    expect(auth.accountSecurityError, contains('当前密码或验证码错误'));

    await expectLater(api.fetchAccountSecurity(), throwsException);
    await Future<void>.delayed(Duration.zero);
    expect(auth.status, UserAuthStatus.anonymous);
    expect(auth.userToken, isEmpty);
    expect(store.token, isNull);
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

class _MemoryStore implements UserSessionStore {
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

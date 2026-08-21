import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:qingjuan/core/api/api_client.dart';
import 'package:qingjuan/core/backend/user_session_store.dart';
import 'package:qingjuan/features/auth/auth_controller.dart';

void main() {
  test('Windows local backend uses an implicit administrator', () async {
    final api = ApiClient(() => 'http://127.0.0.1:19453');
    final auth = AuthController(
      api,
      _MemoryUserSessionStore(),
      backendUrl: () => 'http://127.0.0.1:19453',
    );

    await auth.initializeForCurrentBackend(multiUser: false);

    expect(auth.isLocalAdministrator, isTrue);
    expect(auth.canAccessWorkspace, isTrue);
    expect(auth.user, isNull);
    expect(auth.userToken, isEmpty);
    auth.dispose();
    api.close();
  });

  test('Windows local administrator cannot start 2FA setup', () async {
    var requests = 0;
    final api = ApiClient(
      () => 'http://127.0.0.1:19453',
      client: MockClient((request) async {
        requests += 1;
        return _jsonResponse(<String, dynamic>{});
      }),
    );
    final auth = AuthController(
      api,
      _MemoryUserSessionStore(),
      backendUrl: () => 'http://127.0.0.1:19453',
    );
    addTearDown(() {
      auth.dispose();
      api.close();
    });
    await auth.initializeForCurrentBackend(multiUser: false);

    await expectLater(
      auth.setupTwoFactor(password: 'local-password'),
      throwsStateError,
    );
    expect(requests, 0);
  });

  test('anonymous Linux user cannot start 2FA setup', () async {
    var requests = 0;
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      client: MockClient((request) async {
        requests += 1;
        return _jsonResponse(<String, dynamic>{});
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
      auth.setupTwoFactor(password: 'anonymous-password'),
      throwsStateError,
    );
    expect(requests, 0);
  });

  test('Linux session restores, authenticates resources and logs out',
      () async {
    final store = _MemoryUserSessionStore()
      ..backendUrl = 'https://qingjuan.example.test'
      ..token = 'saved-user-token';
    late AuthController auth;
    final requestedPaths = <String>[];
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      token: () => 'connection-token',
      userToken: () => auth.userToken,
      onUserSessionExpired: () => auth.invalidateSession(),
      client: MockClient((request) async {
        requestedPaths.add(request.url.path);
        expect(request.headers['Authorization'], 'Bearer connection-token');
        expect(
          request.headers['X-QingJuan-User-Token'],
          'saved-user-token',
        );
        if (request.url.path == '/api/v1/auth/logout') {
          return http.Response('', 204);
        }
        return _jsonResponse(_userJson);
      }),
    );
    auth = AuthController(
      api,
      store,
      backendUrl: () => 'https://qingjuan.example.test',
    );

    await auth.initializeForCurrentBackend(multiUser: true);

    expect(auth.isAuthenticated, isTrue);
    expect(auth.user?.username, 'reader');
    expect(auth.workspaceIdentity, contains('user-1'));

    await auth.logout();

    expect(auth.status, UserAuthStatus.anonymous);
    expect(auth.userToken, isEmpty);
    expect(store.token, isNull);
    expect(
      requestedPaths,
      <String>['/api/v1/auth/session', '/api/v1/auth/logout'],
    );
    auth.dispose();
    api.close();
  });

  test('login persists the new user token for the current backend', () async {
    final store = _MemoryUserSessionStore();
    late AuthController auth;
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      token: () => 'connection-token',
      userToken: () => auth.userToken,
      client: MockClient((request) async {
        expect(request.url.path, '/api/v1/auth/login');
        expect(request.headers.containsKey('X-QingJuan-User-Token'), isFalse);
        return _jsonResponse(<String, dynamic>{
          'token': 'new-user-token',
          'user': _userJson,
        });
      }),
    );
    auth = AuthController(
      api,
      store,
      backendUrl: () => 'https://qingjuan.example.test',
    );
    await auth.initializeForCurrentBackend(multiUser: true);

    await auth.login(username: 'reader', password: 'secret');

    expect(auth.isAuthenticated, isTrue);
    expect(auth.userToken, 'new-user-token');
    expect(store.backendUrl, 'https://qingjuan.example.test');
    expect(store.token, 'new-user-token');
    auth.dispose();
    api.close();
  });

  test('a protected 401 invalidates the persisted user session', () async {
    final store = _MemoryUserSessionStore()
      ..backendUrl = 'https://qingjuan.example.test'
      ..token = 'saved-user-token';
    late AuthController auth;
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      token: () => 'connection-token',
      userToken: () => auth.userToken,
      onUserSessionExpired: () => auth.invalidateSession(),
      client: MockClient((request) async {
        if (request.url.path == '/api/v1/auth/session') {
          return _jsonResponse(_userJson);
        }
        return _jsonResponse(<String, String>{'detail': '用户会话已失效'}, 401);
      }),
    );
    auth = AuthController(
      api,
      store,
      backendUrl: () => 'https://qingjuan.example.test',
    );
    await auth.initializeForCurrentBackend(multiUser: true);

    await expectLater(api.fetchBooks(), throwsException);
    await Future<void>.delayed(Duration.zero);

    expect(auth.status, UserAuthStatus.anonymous);
    expect(auth.user, isNull);
    expect(auth.userToken, isEmpty);
    expect(store.token, isNull);
    auth.dispose();
    api.close();
  });
}

http.Response _jsonResponse(Object body, [int statusCode = 200]) =>
    http.Response.bytes(
      utf8.encode(jsonEncode(body)),
      statusCode,
      headers: const <String, String>{'content-type': 'application/json'},
    );

const _userJson = <String, dynamic>{
  'id': 'user-1',
  'username': 'reader',
  'displayName': '读者',
  'role': 'user',
  'status': 'active',
  'createdAt': '2026-08-21T00:00:00Z',
  'lastLoginAt': '2026-08-21T01:00:00Z',
};

class _MemoryUserSessionStore implements UserSessionStore {
  String? backendUrl;
  String? token;

  @override
  Future<void> deleteToken() async => token = null;

  @override
  Future<String?> readToken(String backendUrl) async =>
      this.backendUrl == backendUrl ? token : null;

  @override
  Future<void> writeToken({
    required String backendUrl,
    required String token,
  }) async {
    this.backendUrl = backendUrl;
    this.token = token;
  }
}

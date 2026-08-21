import 'dart:convert';

import 'package:fluent_ui/fluent_ui.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:qingjuan/core/api/api_client.dart';
import 'package:qingjuan/core/backend/backend_connection_manager.dart';
import 'package:qingjuan/core/backend/user_session_store.dart';
import 'package:qingjuan/features/auth/auth_controller.dart';
import 'package:qingjuan/features/auth/widgets/auth_account_card.dart';
import 'package:qingjuan/shared/responsive.dart';

void main() {
  testWidgets('Windows local mode shows only the implicit administrator',
      (tester) async {
    final api = ApiClient(() => 'http://127.0.0.1:19453');
    final auth = AuthController.localAdministrator(api);
    final backend = BackendConnectionManager(api, isConfigured: () => true)
      ..status = BackendStatus.ready;
    addTearDown(() async {
      auth.dispose();
      await backend.dispose();
      api.close();
    });

    await tester.pumpWidget(
      FluentApp(
        home: UiPlatformScope(
          platform: TargetPlatform.windows,
          child: AuthAccountCard(
            auth: auth,
            backend: backend,
            isLocalMode: true,
            backendUrl: 'http://127.0.0.1:19453',
            backendRevision: 0,
          ),
        ),
      ),
    );

    expect(find.text('本机管理员'), findsOneWidget);
    expect(find.byKey(const ValueKey('auth-login-tab')), findsNothing);
    expect(find.byKey(const ValueKey('auth-register-tab')), findsNothing);
    expect(find.byKey(const ValueKey('auth-logout')), findsNothing);
  });

  testWidgets('Linux account card logs in and exposes the personal shelf state',
      (tester) async {
    late AuthController auth;
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      token: () => 'connection-token',
      userToken: () => auth.userToken,
      client: MockClient((request) async {
        expect(request.url.path, '/api/v1/auth/login');
        return _jsonResponse(<String, dynamic>{
          'token': 'user-token',
          'user': _userJson,
        });
      }),
    );
    auth = AuthController(
      api,
      _MemoryUserSessionStore(),
      backendUrl: () => 'https://qingjuan.example.test',
    );
    await auth.initializeForCurrentBackend(multiUser: true);
    final backend = BackendConnectionManager(api, isConfigured: () => true)
      ..status = BackendStatus.ready
      ..multiUserEnabled = true;
    addTearDown(() async {
      auth.dispose();
      await backend.dispose();
      api.close();
    });

    await tester.pumpWidget(
      FluentApp(
        home: UiPlatformScope(
          platform: TargetPlatform.windows,
          child: SingleChildScrollView(
            child: AuthAccountCard(
              auth: auth,
              backend: backend,
              isLocalMode: false,
              backendUrl: 'https://qingjuan.example.test',
              backendRevision: 0,
            ),
          ),
        ),
      ),
    );

    await tester.enterText(
      find.byKey(const ValueKey('auth-username')),
      'reader',
    );
    await tester.enterText(
      find.byKey(const ValueKey('auth-password')),
      'very-secret-password',
    );
    await tester.tap(find.byKey(const ValueKey('auth-submit')));
    await tester.pumpAndSettle();

    expect(auth.isAuthenticated, isTrue);
    expect(find.text('个人书架已启用'), findsOneWidget);
    expect(find.byKey(const ValueKey('auth-logout')), findsOneWidget);
  });

  testWidgets('registration mode collects display name and confirmation',
      (tester) async {
    late Map<String, dynamic> submitted;
    var requestCount = 0;
    late AuthController auth;
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      token: () => 'connection-token',
      userToken: () => auth.userToken,
      client: MockClient((request) async {
        requestCount += 1;
        if (request.url.path == '/api/v1/auth/registration-policy') {
          return _jsonResponse(<String, dynamic>{
            'emailRequired': true,
            'emailVerificationRequired': false,
            'identityBadgeRequired': false,
          });
        }
        expect(request.url.path, '/api/v1/auth/register');
        submitted = jsonDecode(request.body) as Map<String, dynamic>;
        return _jsonResponse(<String, dynamic>{
          'token': 'user-token',
          'user': _userJson,
        });
      }),
    );
    auth = AuthController(
      api,
      _MemoryUserSessionStore(),
      backendUrl: () => 'https://qingjuan.example.test',
    );
    await auth.initializeForCurrentBackend(multiUser: true);
    final backend = BackendConnectionManager(api, isConfigured: () => true)
      ..status = BackendStatus.ready
      ..multiUserEnabled = true;
    addTearDown(() async {
      auth.dispose();
      await backend.dispose();
      api.close();
    });

    await tester.pumpWidget(
      FluentApp(
        home: UiPlatformScope(
          platform: TargetPlatform.android,
          child: SingleChildScrollView(
            child: AuthAccountCard(
              auth: auth,
              backend: backend,
              isLocalMode: false,
              backendUrl: 'https://qingjuan.example.test',
              backendRevision: 0,
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.byKey(const ValueKey('auth-register-tab')));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const ValueKey('auth-username')),
      'reader',
    );
    await tester.enterText(
      find.byKey(const ValueKey('auth-display-name')),
      '读者',
    );
    await tester.enterText(
      find.byKey(const ValueKey('auth-email')),
      'reader@example.test',
    );
    await tester.enterText(
      find.byKey(const ValueKey('auth-password')),
      'short',
    );
    await tester.enterText(
      find.byKey(const ValueKey('auth-confirm-password')),
      'short',
    );
    await tester.tap(find.byKey(const ValueKey('auth-submit')));
    await tester.pump();
    expect(find.text('密码长度需要为 12–256 个字符'), findsOneWidget);
    expect(requestCount, 1);

    await tester.enterText(
      find.byKey(const ValueKey('auth-password')),
      'very-secret-password',
    );
    await tester.enterText(
      find.byKey(const ValueKey('auth-confirm-password')),
      'very-secret-password',
    );
    await tester.tap(find.byKey(const ValueKey('auth-submit')));
    await tester.pumpAndSettle();

    expect(submitted, <String, dynamic>{
      'username': 'reader',
      'displayName': '读者',
      'email': 'reader@example.test',
      'password': 'very-secret-password',
    });
    expect(requestCount, 2);
  });

  testWidgets('same URL connection revision clears account credentials',
      (tester) async {
    late AuthController auth;
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      userToken: () => auth.userToken,
      client: MockClient((request) async {
        expect(request.url.path, '/api/v1/auth/registration-policy');
        return _jsonResponse(<String, dynamic>{
          'emailRequired': true,
          'emailVerificationRequired': false,
          'identityBadgeRequired': false,
          'githubLoginEnabled': false,
        });
      }),
    );
    auth = AuthController(
      api,
      _MemoryUserSessionStore(),
      backendUrl: () => 'https://qingjuan.example.test',
    );
    await auth.initializeForCurrentBackend(multiUser: true);
    final backend = BackendConnectionManager(api, isConfigured: () => true)
      ..status = BackendStatus.ready
      ..multiUserEnabled = true;
    addTearDown(() async {
      auth.dispose();
      await backend.dispose();
      api.close();
    });

    var backendRevision = 0;
    late StateSetter updateHost;
    await tester.pumpWidget(
      FluentApp(
        home: StatefulBuilder(
          builder: (context, setState) {
            updateHost = setState;
            return UiPlatformScope(
              platform: TargetPlatform.windows,
              child: AuthAccountCard(
                auth: auth,
                backend: backend,
                isLocalMode: false,
                backendUrl: 'https://qingjuan.example.test',
                backendRevision: backendRevision,
              ),
            );
          },
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const ValueKey('auth-username')),
      'reader',
    );
    await tester.enterText(
      find.byKey(const ValueKey('auth-password')),
      'very-secret-password',
    );

    updateHost(() => backendRevision += 1);
    await tester.pump();

    expect(
      tester
          .widget<TextBox>(find.byKey(const ValueKey('auth-username')))
          .controller
          ?.text,
      isEmpty,
    );
    expect(
      tester
          .widget<TextBox>(find.byKey(const ValueKey('auth-password')))
          .controller
          ?.text,
      isEmpty,
    );
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

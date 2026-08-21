import 'dart:async';
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
  testWidgets('enabled email code and identity badge are both required',
      (tester) async {
    tester.view.physicalSize = const Size(320, 760);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    late Map<String, dynamic> submitted;
    var codeRequests = 0;
    late AuthController auth;
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      userToken: () => auth.userToken,
      client: MockClient((request) async {
        switch (request.url.path) {
          case '/api/v1/auth/registration-policy':
            return _jsonResponse(<String, dynamic>{
              'emailRequired': true,
              'emailVerificationRequired': true,
              'identityBadgeRequired': true,
            });
          case '/api/v1/auth/email-code':
            codeRequests += 1;
            expect(
              jsonDecode(request.body),
              <String, dynamic>{'email': 'reader@example.test'},
            );
            return http.Response('', 204);
          case '/api/v1/auth/register':
            submitted = jsonDecode(request.body) as Map<String, dynamic>;
            return _jsonResponse(<String, dynamic>{
              'token': 'user-token',
              'user': <String, dynamic>{
                ..._userJson,
                'email': 'reader@example.test',
              },
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

    expect(find.text('注册 Linux 后端账号'), findsOneWidget);
    expect(find.byKey(const ValueKey('auth-email')), findsOneWidget);
    expect(find.byKey(const ValueKey('auth-email-code')), findsOneWidget);
    expect(find.byKey(const ValueKey('auth-identity-badge')), findsOneWidget);
    expect(tester.takeException(), isNull);

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
      'very-secret-password',
    );
    await tester.enterText(
      find.byKey(const ValueKey('auth-confirm-password')),
      'very-secret-password',
    );

    final sendCode = find.byKey(const ValueKey('auth-send-email-code'));
    await tester.ensureVisible(sendCode);
    await tester.tap(sendCode);
    await tester.pump();
    await tester.pump();
    expect(codeRequests, 1);
    expect(find.byKey(const ValueKey('auth-email-code-sent')), findsOneWidget);
    expect(find.text('60 秒后重发'), findsOneWidget);

    final submit = find.byKey(const ValueKey('auth-submit'));
    await tester.ensureVisible(submit);
    await tester.tap(submit);
    await tester.pump();
    expect(find.text('请填写邮箱验证码'), findsOneWidget);

    await tester.enterText(
      find.byKey(const ValueKey('auth-email-code')),
      '12a45',
    );
    await tester.ensureVisible(submit);
    await tester.tap(submit);
    await tester.pump();
    expect(find.text('邮箱验证码需为 6 位数字'), findsOneWidget);

    await tester.enterText(
      find.byKey(const ValueKey('auth-email-code')),
      '246810',
    );
    await tester.ensureVisible(submit);
    await tester.tap(submit);
    await tester.pump();
    expect(find.text('请填写身份牌'), findsOneWidget);

    await tester.enterText(
      find.byKey(const ValueKey('auth-identity-badge')),
      'QJ-FAMILY',
    );
    await tester.ensureVisible(submit);
    await tester.tap(submit);
    await tester.pumpAndSettle();

    expect(submitted, <String, dynamic>{
      'username': 'reader',
      'displayName': '读者',
      'email': 'reader@example.test',
      'password': 'very-secret-password',
      'emailCode': '246810',
      'identityBadge': 'QJ-FAMILY',
    });
    expect(auth.isAuthenticated, isTrue);
    expect(tester.takeException(), isNull);
  });

  testWidgets('policy loading never prevents switching back to login',
      (tester) async {
    final policyGate = Completer<void>();
    var policyRequests = 0;
    late AuthController auth;
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      userToken: () => auth.userToken,
      client: MockClient((request) async {
        final attempt = ++policyRequests;
        if (attempt == 1) await policyGate.future;
        return _jsonResponse(<String, dynamic>{
          'emailRequired': true,
          'emailVerificationRequired': false,
          'identityBadgeRequired': attempt > 1,
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
      if (!policyGate.isCompleted) policyGate.complete();
      auth.dispose();
      await backend.dispose();
      api.close();
    });

    await _pumpCard(tester, auth: auth, backend: backend);
    await tester.tap(find.byKey(const ValueKey('auth-register-tab')));
    await tester.pump();
    expect(
      find.byKey(const ValueKey('auth-registration-policy-loading')),
      findsOneWidget,
    );
    expect(auth.isBusy, isFalse);

    await tester.tap(find.byKey(const ValueKey('auth-login-tab')));
    await tester.pump();
    expect(find.byKey(const ValueKey('auth-email')), findsNothing);
    expect(find.byKey(const ValueKey('auth-submit')), findsOneWidget);

    policyGate.complete();
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('auth-email')), findsNothing);

    await tester.tap(find.byKey(const ValueKey('auth-register-tab')));
    await tester.pumpAndSettle();
    expect(policyRequests, 2);
    expect(find.byKey(const ValueKey('auth-identity-badge')), findsOneWidget);
  });

  testWidgets('failed policy load has a working retry state', (tester) async {
    var attempts = 0;
    late AuthController auth;
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      userToken: () => auth.userToken,
      client: MockClient((request) async {
        attempts += 1;
        if (attempts == 1) {
          return _jsonResponse(<String, String>{'detail': '暂时无法读取'}, 400);
        }
        return _jsonResponse(<String, dynamic>{
          'emailRequired': true,
          'emailVerificationRequired': false,
          'identityBadgeRequired': true,
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

    await _pumpCard(tester, auth: auth, backend: backend);
    await tester.tap(find.byKey(const ValueKey('auth-register-tab')));
    await tester.pumpAndSettle();
    expect(
      find.byKey(const ValueKey('auth-registration-policy-error')),
      findsOneWidget,
    );
    expect(find.textContaining('暂时无法读取'), findsOneWidget);

    await tester.tap(
      find.byKey(const ValueKey('auth-registration-policy-retry')),
    );
    await tester.pumpAndSettle();
    expect(
      find.byKey(const ValueKey('auth-registration-policy-ready')),
      findsOneWidget,
    );
    expect(find.byKey(const ValueKey('auth-identity-badge')), findsOneWidget);
    expect(attempts, 2);

    await tester.tap(
      find.byKey(const ValueKey('auth-registration-policy-refresh')),
    );
    await tester.pumpAndSettle();
    expect(attempts, 3);
  });

  testWidgets('backend changes clear every draft but ordinary rebuilds do not',
      (tester) async {
    late AuthController auth;
    final api = ApiClient(
      () => 'https://old.example.test',
      userToken: () => auth.userToken,
      client: MockClient((request) async {
        if (request.url.path == '/api/v1/auth/registration-policy') {
          return _jsonResponse(<String, dynamic>{
            'emailRequired': true,
            'emailVerificationRequired': true,
            'identityBadgeRequired': true,
          });
        }
        if (request.url.path == '/api/v1/auth/email-code') {
          return http.Response('', 204);
        }
        fail('Unexpected request: ${request.url.path}');
      }),
    );
    auth = AuthController(
      api,
      _MemoryUserSessionStore(),
      backendUrl: () => 'https://old.example.test',
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

    await _pumpCard(tester, auth: auth, backend: backend);
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
      find.byKey(const ValueKey('auth-email-code')),
      '246810',
    );
    await tester.enterText(
      find.byKey(const ValueKey('auth-identity-badge')),
      'QJ-FAMILY',
    );
    await tester.enterText(
      find.byKey(const ValueKey('auth-password')),
      'very-secret-password',
    );
    await tester.enterText(
      find.byKey(const ValueKey('auth-confirm-password')),
      'very-secret-password',
    );
    final sendCode = find.byKey(const ValueKey('auth-send-email-code'));
    await tester.ensureVisible(sendCode);
    await tester.tap(sendCode);
    await tester.pump();
    await tester.pump();
    expect(find.text('60 秒后重发'), findsOneWidget);

    await _pumpCard(tester, auth: auth, backend: backend);
    await tester.pump();
    expect(find.text('注册 Linux 后端账号'), findsOneWidget);
    expect(_textBoxValue(tester, 'auth-username'), 'reader');
    expect(_textBoxValue(tester, 'auth-email'), 'reader@example.test');
    expect(_textBoxValue(tester, 'auth-email-code'), '246810');
    expect(_textBoxValue(tester, 'auth-identity-badge'), 'QJ-FAMILY');
    expect(_textBoxValue(tester, 'auth-password'), 'very-secret-password');

    await _pumpCard(
      tester,
      auth: auth,
      backend: backend,
      backendUrl: 'https://new.example.test',
    );
    await tester.pump();
    expect(find.text('登录 Linux 后端'), findsOneWidget);
    expect(_textBoxValue(tester, 'auth-username'), isEmpty);
    expect(_textBoxValue(tester, 'auth-password'), isEmpty);

    await tester.tap(find.byKey(const ValueKey('auth-register-tab')));
    await tester.pumpAndSettle();
    expect(_textBoxValue(tester, 'auth-display-name'), isEmpty);
    expect(_textBoxValue(tester, 'auth-email'), isEmpty);
    expect(_textBoxValue(tester, 'auth-email-code'), isEmpty);
    expect(_textBoxValue(tester, 'auth-identity-badge'), isEmpty);
    expect(_textBoxValue(tester, 'auth-confirm-password'), isEmpty);
    expect(find.text('发送验证码'), findsOneWidget);
  });
}

Future<void> _pumpCard(
  WidgetTester tester, {
  required AuthController auth,
  required BackendConnectionManager backend,
  String backendUrl = 'https://qingjuan.example.test',
}) =>
    tester.pumpWidget(
      FluentApp(
        home: UiPlatformScope(
          platform: TargetPlatform.android,
          child: SingleChildScrollView(
            child: AuthAccountCard(
              auth: auth,
              backend: backend,
              isLocalMode: false,
              backendUrl: backendUrl,
              backendRevision: 0,
            ),
          ),
        ),
      ),
    );

String _textBoxValue(WidgetTester tester, String key) =>
    tester.widget<TextBox>(find.byKey(ValueKey(key))).controller?.text ?? '';

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

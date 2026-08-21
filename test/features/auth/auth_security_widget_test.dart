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
  testWidgets(
      'password login advances to 2FA without asking for password again',
      (tester) async {
    late AuthController auth;
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      userToken: () => auth.userToken,
      client: MockClient((request) async {
        return switch (request.url.path) {
          '/api/v1/auth/registration-policy' => _json(<String, dynamic>{
              'emailRequired': true,
              'emailVerificationRequired': false,
              'identityBadgeRequired': false,
              'githubLoginEnabled': false,
            }),
          '/api/v1/auth/login' => _json(<String, dynamic>{
              'requiresTwoFactor': true,
              'challengeToken': 'challenge-token',
              'expiresInSeconds': 300,
            }),
          '/api/v1/auth/login/2fa' =>
            _json(<String, dynamic>{'token': 'user-token', 'user': _user}),
          _ => throw StateError('Unexpected request: ${request.url.path}'),
        };
      }),
    );
    auth = AuthController(
      api,
      _MemoryStore(),
      backendUrl: () => 'https://qingjuan.example.test',
    );
    await auth.initializeForCurrentBackend(multiUser: true);
    final backend = _readyBackend(api);
    addTearDown(() async {
      auth.dispose();
      await backend.dispose();
      api.close();
    });
    await _pumpCard(tester, auth: auth, backend: backend);
    await tester.pumpAndSettle();

    await tester.enterText(
      find.byKey(const ValueKey('auth-username')),
      'reader',
    );
    await tester.enterText(
      find.byKey(const ValueKey('auth-password')),
      'password',
    );
    await tester.tap(find.byKey(const ValueKey('auth-submit')));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('auth-two-factor-step')), findsOneWidget);
    expect(find.byKey(const ValueKey('auth-password')), findsNothing);
    await tester.enterText(
      find.byKey(const ValueKey('auth-two-factor-code')),
      '123456',
    );
    await tester.tap(find.byKey(const ValueKey('auth-two-factor-submit')));
    await tester.pumpAndSettle();

    expect(auth.isAuthenticated, isTrue);
    expect(find.byKey(const ValueKey('auth-account-security')), findsOneWidget);
  });

  testWidgets('GitHub button shows code and never trusts a returned URL',
      (tester) async {
    late AuthController auth;
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      userToken: () => auth.userToken,
      client: MockClient((request) async {
        if (request.url.path == '/api/v1/auth/registration-policy') {
          return _json(<String, dynamic>{
            'emailRequired': true,
            'emailVerificationRequired': false,
            'identityBadgeRequired': false,
            'githubLoginEnabled': true,
          });
        }
        expect(request.url.path, '/api/v1/auth/github/device/start');
        return _json(<String, dynamic>{
          'flowId': 'flow-id',
          'userCode': 'ABCD-EFGH',
          'verificationUri': 'https://attacker.example/phish',
          'expiresInSeconds': 900,
          'intervalSeconds': 60,
        });
      }),
    );
    auth = AuthController(
      api,
      _MemoryStore(),
      backendUrl: () => 'https://qingjuan.example.test',
    );
    await auth.initializeForCurrentBackend(multiUser: true);
    final backend = _readyBackend(api);
    addTearDown(() async {
      auth.dispose();
      await backend.dispose();
      api.close();
    });
    await _pumpCard(tester, auth: auth, backend: backend);
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('auth-github-login')), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('auth-github-login')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.text('ABCD-EFGH'), findsOneWidget);
    expect(find.text('https://github.com/login/device'), findsOneWidget);
    expect(find.textContaining('attacker.example'), findsNothing);

    await tester.tap(find.byKey(const ValueKey('github-device-cancel')));
    await tester.pumpAndSettle();
    expect(auth.status, UserAuthStatus.anonymous);
    expect(auth.githubDeviceFlow, isNull);
  });

  testWidgets('bound GitHub can be unbound after administrator disables login',
      (tester) async {
    tester.view.physicalSize = const Size(320, 760);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final store = _MemoryStore()..token = 'saved-token';
    late AuthController auth;
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      userToken: () => auth.userToken,
      client: MockClient((request) async {
        return switch (request.url.path) {
          '/api/v1/auth/session' => _json(_user),
          '/api/v1/auth/registration-policy' => _json(<String, dynamic>{
              'emailRequired': true,
              'emailVerificationRequired': false,
              'identityBadgeRequired': false,
              'githubLoginEnabled': false,
            }),
          '/api/v1/auth/account/security' => _json(<String, dynamic>{
              'github': <String, dynamic>{
                'available': false,
                'bound': true,
                'login': 'octocat',
              },
              'twoFactor': <String, dynamic>{
                'enabled': false,
                'recoveryCodesRemaining': 0,
              },
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
    await auth.initializeForCurrentBackend(multiUser: true);
    final backend = _readyBackend(api);
    addTearDown(() async {
      auth.dispose();
      await backend.dispose();
      api.close();
    });
    await _pumpCard(
      tester,
      auth: auth,
      backend: backend,
      platform: TargetPlatform.android,
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey('auth-account-security')));
    await tester.pumpAndSettle();

    expect(find.text('已绑定 @octocat'), findsOneWidget);
    expect(
      find.byKey(const ValueKey('account-security-github-unbind')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('account-security-github-bind')),
      findsNothing,
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('2FA enable cannot close while recovery codes are in flight',
      (tester) async {
    final enableGate = Completer<void>();
    final store = _MemoryStore()..token = 'saved-token';
    late AuthController auth;
    final api = ApiClient(
      () => 'https://qingjuan.example.test',
      userToken: () => auth.userToken,
      client: MockClient((request) async {
        return switch (request.url.path) {
          '/api/v1/auth/session' => _json(_user),
          '/api/v1/auth/registration-policy' => _json(<String, dynamic>{
              'emailRequired': true,
              'emailVerificationRequired': false,
              'identityBadgeRequired': false,
            }),
          '/api/v1/auth/account/security' => _json(<String, dynamic>{
              'github': <String, dynamic>{
                'available': false,
                'bound': false,
                'login': '',
              },
              'twoFactor': <String, dynamic>{
                'enabled': false,
                'recoveryCodesRemaining': 0,
              },
            }),
          '/api/v1/auth/account/2fa/setup' => _json(<String, dynamic>{
              'setupId': 'setup-id',
              'secret': 'JBSWY3DPEHPK3PXP',
              'otpauthUri':
                  'otpauth://totp/QingJuan:reader?secret=JBSWY3DPEHPK3PXP',
              'expiresInSeconds': 600,
            }),
          '/api/v1/auth/account/2fa/enable' => () async {
              await enableGate.future;
              return _json(<String, dynamic>{
                'recoveryCodes': <String>['one-time-1', 'one-time-2'],
              });
            }(),
          _ => throw StateError('Unexpected request: ${request.url.path}'),
        };
      }),
    );
    auth = AuthController(
      api,
      store,
      backendUrl: () => 'https://qingjuan.example.test',
    );
    await auth.initializeForCurrentBackend(multiUser: true);
    final backend = _readyBackend(api);
    addTearDown(() async {
      if (!enableGate.isCompleted) enableGate.complete();
      auth.dispose();
      await backend.dispose();
      api.close();
    });
    await _pumpCard(tester, auth: auth, backend: backend);
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('auth-account-security')));
    await tester.pumpAndSettle();
    await tester.tap(
      find.byKey(const ValueKey('account-security-2fa-enable')),
    );
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const ValueKey('2fa-setup-password')),
      'password',
    );
    await tester.tap(find.byKey(const ValueKey('2fa-setup-continue')));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const ValueKey('2fa-setup-code')),
      '123456',
    );
    final enable = find.byKey(const ValueKey('2fa-setup-continue'));
    await tester.ensureVisible(enable);
    await tester.tap(enable);
    await tester.pump();

    final cancelButton = tester.widget<Button>(
      find.widgetWithText(Button, '取消').last,
    );
    expect(cancelButton.onPressed, isNull);
    await tester.binding.handlePopRoute();
    await tester.pump();
    expect(find.byKey(const ValueKey('2fa-setup-code')), findsOneWidget);

    enableGate.complete();
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('2fa-recovery-warning')), findsOneWidget);
    expect(find.textContaining('one-time-1'), findsOneWidget);
  });
}

BackendConnectionManager _readyBackend(ApiClient api) =>
    BackendConnectionManager(api, isConfigured: () => true)
      ..status = BackendStatus.ready
      ..multiUserEnabled = true;

Future<void> _pumpCard(
  WidgetTester tester, {
  required AuthController auth,
  required BackendConnectionManager backend,
  TargetPlatform platform = TargetPlatform.windows,
}) =>
    tester.pumpWidget(
      FluentApp(
        home: UiPlatformScope(
          platform: platform,
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

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:qingjuan/core/backend/user_session_store.dart';

void main() {
  const store = SecureUserSessionStore();

  setUp(() => FlutterSecureStorage.setMockInitialValues(<String, String>{}));

  test('session token is bound to the normalized Linux backend URL', () async {
    await store.writeToken(
      backendUrl: 'https://qingjuan.example.test///',
      token: 'user-session-token',
    );

    expect(
      await store.readToken('https://qingjuan.example.test'),
      'user-session-token',
    );
    expect(await store.readToken('https://other.example.test'), isNull);
  });

  test('deleting the user session keeps unrelated secure values', () async {
    const storage = FlutterSecureStorage();
    FlutterSecureStorage.setMockInitialValues(<String, String>{
      'unrelated-secret': 'keep-me',
    });

    await store.writeToken(
      backendUrl: 'https://qingjuan.example.test',
      token: 'user-session-token',
    );
    await store.deleteToken();

    expect(
      await store.readToken('https://qingjuan.example.test'),
      isNull,
    );
    expect(await storage.read(key: 'unrelated-secret'), 'keep-me');
  });
}

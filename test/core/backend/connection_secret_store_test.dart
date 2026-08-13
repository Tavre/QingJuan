import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:qingjuan/core/backend/connection_secret_store.dart';

void main() {
  const storage = FlutterSecureStorage();
  const secrets = SecureConnectionSecretStore();

  test('legacy backend token migrates to the Linux profile key', () async {
    FlutterSecureStorage.setMockInitialValues(<String, String>{
      'qingjuan.backendToken': 'legacy-token',
    });

    expect(await secrets.readToken(), 'legacy-token');
    expect(
      await storage.read(key: 'qingjuan.backend.remote.token'),
      'legacy-token',
    );
    expect(await storage.read(key: 'qingjuan.backendToken'), isNull);
  });

  test('dedicated Linux token wins and removes a stale legacy copy', () async {
    FlutterSecureStorage.setMockInitialValues(<String, String>{
      'qingjuan.backend.remote.token': 'current-token',
      'qingjuan.backendToken': 'stale-token',
    });

    expect(await secrets.readToken(), 'current-token');
    expect(await storage.read(key: 'qingjuan.backendToken'), isNull);
  });

  test('write and delete only operate on connection token keys', () async {
    FlutterSecureStorage.setMockInitialValues(<String, String>{
      'unrelated-secret': 'keep-me',
    });

    await secrets.writeToken('remote-token');
    expect(
      await storage.read(key: 'qingjuan.backend.remote.token'),
      'remote-token',
    );

    await secrets.deleteToken();
    expect(
      await storage.read(key: 'qingjuan.backend.remote.token'),
      isNull,
    );
    expect(await storage.read(key: 'unrelated-secret'), 'keep-me');
  });
}

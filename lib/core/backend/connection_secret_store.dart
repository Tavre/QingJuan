import 'package:flutter_secure_storage/flutter_secure_storage.dart';

abstract interface class ConnectionSecretStore {
  Future<String?> readToken();

  Future<void> writeToken(String token);

  Future<void> deleteToken();
}

class SecureConnectionSecretStore implements ConnectionSecretStore {
  const SecureConnectionSecretStore();

  static const _remoteTokenKey = 'qingjuan.backend.remote.token';
  static const _legacyTokenKey = 'qingjuan.backendToken';
  static const _storage = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
  );

  @override
  Future<String?> readToken() async {
    final remoteToken = await _storage.read(key: _remoteTokenKey);
    if (remoteToken != null) {
      await _storage.delete(key: _legacyTokenKey);
      return remoteToken;
    }

    final legacyToken = await _storage.read(key: _legacyTokenKey);
    if (legacyToken == null) return null;
    await _storage.write(key: _remoteTokenKey, value: legacyToken);
    await _storage.delete(key: _legacyTokenKey);
    return legacyToken;
  }

  @override
  Future<void> writeToken(String token) async {
    await _storage.write(key: _remoteTokenKey, value: token);
    await _storage.delete(key: _legacyTokenKey);
  }

  @override
  Future<void> deleteToken() async {
    await _storage.delete(key: _remoteTokenKey);
    await _storage.delete(key: _legacyTokenKey);
  }
}

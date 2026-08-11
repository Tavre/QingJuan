import 'package:flutter_secure_storage/flutter_secure_storage.dart';

abstract interface class ConnectionSecretStore {
  Future<String?> readToken();

  Future<void> writeToken(String token);

  Future<void> deleteToken();
}

class SecureConnectionSecretStore implements ConnectionSecretStore {
  const SecureConnectionSecretStore();

  static const _tokenKey = 'qingjuan.backendToken';
  static const _storage = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
  );

  @override
  Future<String?> readToken() => _storage.read(key: _tokenKey);

  @override
  Future<void> writeToken(String token) =>
      _storage.write(key: _tokenKey, value: token);

  @override
  Future<void> deleteToken() => _storage.delete(key: _tokenKey);
}

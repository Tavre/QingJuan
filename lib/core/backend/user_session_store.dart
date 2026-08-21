import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

abstract interface class UserSessionStore {
  Future<String?> readToken(String backendUrl);

  Future<void> writeToken({
    required String backendUrl,
    required String token,
  });

  Future<void> deleteToken();
}

class SecureUserSessionStore implements UserSessionStore {
  const SecureUserSessionStore();

  static const _sessionKey = 'qingjuan.user.remote.session';
  static const _storage = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
  );

  @override
  Future<String?> readToken(String backendUrl) async {
    final raw = await _storage.read(key: _sessionKey);
    if (raw == null || raw.isEmpty) return null;
    try {
      final payload = jsonDecode(raw);
      if (payload is! Map) return null;
      final storedUrl = _normalize(payload['backendUrl'] as String? ?? '');
      final token = payload['token'] as String? ?? '';
      if (storedUrl != _normalize(backendUrl) || token.trim().isEmpty) {
        return null;
      }
      return token;
    } on FormatException {
      return null;
    }
  }

  @override
  Future<void> writeToken({
    required String backendUrl,
    required String token,
  }) =>
      _storage.write(
        key: _sessionKey,
        value: jsonEncode(<String, String>{
          'backendUrl': _normalize(backendUrl),
          'token': token,
        }),
      );

  @override
  Future<void> deleteToken() => _storage.delete(key: _sessionKey);

  static String _normalize(String value) =>
      value.trim().replaceAll(RegExp(r'/+$'), '');
}

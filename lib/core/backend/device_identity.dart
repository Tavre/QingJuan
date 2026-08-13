import 'dart:io';
import 'dart:math';

import 'package:shared_preferences/shared_preferences.dart';

class DeviceIdentity {
  const DeviceIdentity({
    required this.id,
    required this.name,
    required this.platform,
  });

  static const _deviceIdKey = 'qingjuan.deviceId';
  static final _deviceIdPattern = RegExp(r'^[a-f0-9]{32}$');

  final String id;
  final String name;
  final String platform;

  Map<String, String> get headers => <String, String>{
        'X-QingJuan-Device-ID': id,
        'X-QingJuan-Device-Name': Uri.encodeComponent(name),
        'X-QingJuan-Device-Platform': platform,
      };

  static Future<DeviceIdentity> load(
    SharedPreferences preferences, {
    String? operatingSystem,
    String? hostname,
    Random? random,
  }) async {
    var id = preferences.getString(_deviceIdKey)?.trim().toLowerCase() ?? '';
    if (!_deviceIdPattern.hasMatch(id)) {
      final source = random ?? Random.secure();
      id = List<int>.generate(16, (_) => source.nextInt(256))
          .map((value) => value.toRadixString(16).padLeft(2, '0'))
          .join();
      await preferences.setString(_deviceIdKey, id);
    }

    final platform =
        _normalizePlatform(operatingSystem ?? Platform.operatingSystem);
    final candidate = (hostname ?? _localHostname()).trim();
    final name = candidate.isNotEmpty && candidate.toLowerCase() != 'localhost'
        ? candidate
        : '${_platformLabel(platform)} ${id.substring(0, 6)}';
    return DeviceIdentity(id: id, name: name, platform: platform);
  }

  static String _normalizePlatform(String value) =>
      switch (value.toLowerCase()) {
        'android' => 'android',
        'windows' => 'windows',
        'linux' => 'linux',
        'macos' => 'macos',
        'ios' => 'ios',
        _ => 'other',
      };

  static String _platformLabel(String value) => switch (value) {
        'android' => 'Android 设备',
        'windows' => 'Windows 设备',
        'linux' => 'Linux 设备',
        'macos' => 'macOS 设备',
        'ios' => 'iOS 设备',
        _ => '未知设备',
      };

  static String _localHostname() {
    try {
      return Platform.localHostname;
    } catch (_) {
      return '';
    }
  }
}

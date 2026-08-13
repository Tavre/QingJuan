import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:qingjuan/core/backend/device_identity.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  test('device identity is stable and uses ordinary preferences', () async {
    final preferences = await SharedPreferences.getInstance();
    final first = await DeviceIdentity.load(
      preferences,
      operatingSystem: 'windows',
      hostname: '阅读电脑',
      random: Random(42),
    );
    final second = await DeviceIdentity.load(
      preferences,
      operatingSystem: 'windows',
      hostname: '阅读电脑',
      random: Random(99),
    );

    expect(first.id, matches(RegExp(r'^[a-f0-9]{32}$')));
    expect(second.id, first.id);
    expect(first.platform, 'windows');
    expect(first.name, '阅读电脑');
    expect(first.headers, <String, String>{
      'X-QingJuan-Device-ID': first.id,
      'X-QingJuan-Device-Name': '%E9%98%85%E8%AF%BB%E7%94%B5%E8%84%91',
      'X-QingJuan-Device-Platform': 'windows',
    });
  });

  test('generic hostnames use a platform label and id suffix', () async {
    final preferences = await SharedPreferences.getInstance();
    final identity = await DeviceIdentity.load(
      preferences,
      operatingSystem: 'android',
      hostname: 'localhost',
      random: Random(7),
    );

    expect(identity.name, 'Android 设备 ${identity.id.substring(0, 6)}');
  });
}

import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:window_manager/window_manager.dart';

import 'app/qingjuan_app.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await windowManager.ensureInitialized();
  const windowOptions = WindowOptions(
    size: Size(1360, 860),
    minimumSize: Size(960, 640),
    center: true,
    backgroundColor: Color(0xFFF3F3F3),
    skipTaskbar: false,
    title: '青卷',
    titleBarStyle: TitleBarStyle.hidden,
    windowButtonVisibility: false,
  );
  unawaited(
    windowManager.waitUntilReadyToShow(windowOptions, () async {
      await windowManager.show();
      await windowManager.focus();
    }),
  );
  final app = await QingJuanApp.bootstrap();
  runApp(app);
}

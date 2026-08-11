import 'package:flutter/widgets.dart';
import 'package:flutter/services.dart';

import 'app/qingjuan_app.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
  final app = await QingJuanApp.bootstrap();
  runApp(app);
}

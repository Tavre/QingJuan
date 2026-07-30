import 'package:flutter/widgets.dart';

import 'app/qingjuan_app.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final app = await QingJuanApp.bootstrap();
  runApp(app);
}

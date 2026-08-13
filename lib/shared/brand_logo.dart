import 'package:flutter/widgets.dart';

class QingJuanLogo extends StatelessWidget {
  const QingJuanLogo({this.size = 32, super.key});

  static const assetPath = 'assets/logo.png';

  final double size;

  @override
  Widget build(BuildContext context) {
    return Image.asset(
      assetPath,
      width: size,
      height: size,
      fit: BoxFit.contain,
      filterQuality: FilterQuality.high,
      semanticLabel: '青卷标志',
    );
  }
}

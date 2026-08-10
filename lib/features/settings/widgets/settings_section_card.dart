import 'package:fluent_ui/fluent_ui.dart';

import '../../../shared/app_surface.dart';

class SettingsSectionCard extends StatelessWidget {
  const SettingsSectionCard({
    required this.icon,
    required this.child,
    super.key,
  });

  final IconData icon;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return AppSurface(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          AccentIcon(icon),
          const SizedBox(width: 16),
          Expanded(child: child),
        ],
      ),
    );
  }
}

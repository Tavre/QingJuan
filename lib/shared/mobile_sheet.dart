import 'package:fluent_ui/fluent_ui.dart';

import 'motion.dart';

Future<T?> showMobileSheet<T>({
  required BuildContext context,
  required WidgetBuilder builder,
  bool barrierDismissible = true,
}) {
  final duration = QjMotion.duration(context, QjMotionSpeed.medium);
  return showGeneralDialog<T>(
    context: context,
    barrierDismissible: barrierDismissible,
    barrierLabel: '关闭面板',
    barrierColor: const Color(0x66000000),
    transitionDuration: duration,
    pageBuilder: (context, _, __) => builder(context),
    transitionBuilder: (context, animation, _, child) {
      final offset = Tween<Offset>(
        begin: const Offset(0, 0.08),
        end: Offset.zero,
      ).animate(
        CurvedAnimation(parent: animation, curve: QjMotion.enterCurve),
      );
      return FadeTransition(
        opacity: animation,
        child: SlideTransition(position: offset, child: child),
      );
    },
  );
}

class MobileSheet extends StatelessWidget {
  const MobileSheet({
    required this.title,
    required this.child,
    this.subtitle,
    this.actions = const <Widget>[],
    this.onClose,
    this.trailing,
    this.maxWidth = 660,
    this.maxHeightFactor = 0.9,
    super.key,
  });

  final String title;
  final String? subtitle;
  final Widget child;
  final List<Widget> actions;
  final VoidCallback? onClose;
  final Widget? trailing;
  final double maxWidth;
  final double maxHeightFactor;

  @override
  Widget build(BuildContext context) {
    final theme = FluentTheme.of(context);
    final dark = theme.brightness == Brightness.dark;
    final screen = MediaQuery.sizeOf(context);
    final keyboardInset = MediaQuery.viewInsetsOf(context).bottom;
    return SafeArea(
      top: false,
      child: AnimatedPadding(
        duration: QjMotion.duration(context, QjMotionSpeed.fast),
        curve: QjMotion.enterCurve,
        padding: EdgeInsets.fromLTRB(10, 10, 10, keyboardInset + 10),
        child: Align(
          alignment: Alignment.bottomCenter,
          child: ConstrainedBox(
            key: const ValueKey('mobile-sheet-surface'),
            constraints: BoxConstraints(
              maxWidth: maxWidth,
              maxHeight: screen.height * maxHeightFactor,
            ),
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: theme.cardColor,
                borderRadius: BorderRadius.circular(22),
                border: Border.all(
                  color:
                      dark ? const Color(0xFF303640) : const Color(0xFFE8ECF2),
                ),
                boxShadow: <BoxShadow>[
                  BoxShadow(
                    color: const Color(0xFF101828).withAlpha(dark ? 70 : 30),
                    blurRadius: 28,
                    offset: const Offset(0, 10),
                  ),
                ],
              ),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(22),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    Padding(
                      padding: const EdgeInsets.fromLTRB(18, 15, 12, 13),
                      child: Row(
                        children: <Widget>[
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: <Widget>[
                                Text(
                                  title,
                                  style: theme.typography.subtitle?.copyWith(
                                    fontWeight: FontWeight.w700,
                                  ),
                                ),
                                if (subtitle case final subtitle?) ...<Widget>[
                                  const SizedBox(height: 3),
                                  Text(
                                    subtitle,
                                    style: theme.typography.caption,
                                  ),
                                ],
                              ],
                            ),
                          ),
                          if (trailing != null) ...<Widget>[
                            const SizedBox(width: 10),
                            trailing!,
                          ],
                          Tooltip(
                            message: '关闭',
                            child: IconButton(
                              icon: const Icon(
                                FluentIcons.chrome_close,
                                size: 14,
                                semanticLabel: '关闭',
                              ),
                              onPressed: onClose,
                            ),
                          ),
                        ],
                      ),
                    ),
                    Container(
                      height: 1,
                      color: dark
                          ? const Color(0xFF303640)
                          : const Color(0xFFE8ECF2),
                    ),
                    Flexible(child: child),
                    if (actions.isNotEmpty) ...<Widget>[
                      Container(
                        height: 1,
                        color: dark
                            ? const Color(0xFF303640)
                            : const Color(0xFFE8ECF2),
                      ),
                      Padding(
                        padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
                        child: Row(
                          children: <Widget>[
                            for (var index = 0;
                                index < actions.length;
                                index++) ...<Widget>[
                              if (index > 0) const SizedBox(width: 10),
                              Expanded(child: actions[index]),
                            ],
                          ],
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

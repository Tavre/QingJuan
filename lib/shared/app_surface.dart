import 'package:fluent_ui/fluent_ui.dart';

/// 青卷中承载同层级内容的标准表面。
///
/// 普通表面不使用阴影；只有可点击表面通过轻微的背景和描边变化提供反馈。
class AppSurface extends StatelessWidget {
  const AppSurface({
    required this.child,
    this.padding = const EdgeInsets.all(16),
    this.margin,
    this.onPressed,
    this.selected = false,
    super.key,
  });

  final Widget child;
  final EdgeInsetsGeometry padding;
  final EdgeInsetsGeometry? margin;
  final VoidCallback? onPressed;
  final bool selected;

  @override
  Widget build(BuildContext context) {
    if (onPressed == null) {
      return _SurfaceBody(
        padding: padding,
        margin: margin,
        selected: selected,
        hovered: false,
        child: child,
      );
    }

    return HoverButton(
      onPressed: onPressed,
      builder: (context, states) => _SurfaceBody(
        padding: padding,
        margin: margin,
        selected: selected,
        hovered: states.isHovered,
        child: child,
      ),
    );
  }
}

class _SurfaceBody extends StatelessWidget {
  const _SurfaceBody({
    required this.child,
    required this.padding,
    required this.margin,
    required this.selected,
    required this.hovered,
  });

  final Widget child;
  final EdgeInsetsGeometry padding;
  final EdgeInsetsGeometry? margin;
  final bool selected;
  final bool hovered;

  @override
  Widget build(BuildContext context) {
    final theme = FluentTheme.of(context);
    final borderColor = selected
        ? theme.accentColor
        : hovered
            ? theme.resources.controlStrokeColorSecondary
            : theme.resources.cardStrokeColorDefault;
    return AnimatedContainer(
      duration: MediaQuery.maybeOf(context)?.disableAnimations ?? false
          ? Duration.zero
          : theme.fasterAnimationDuration,
      curve: Curves.easeOutCubic,
      width: double.infinity,
      margin: margin,
      padding: padding,
      decoration: BoxDecoration(
        color: hovered
            ? theme.resources.subtleFillColorSecondary
            : theme.cardColor,
        border: Border.all(color: borderColor),
        borderRadius: BorderRadius.circular(8),
      ),
      child: child,
    );
  }
}

class AccentIcon extends StatelessWidget {
  const AccentIcon(this.icon, {this.enabled = true, super.key});

  final IconData icon;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    final theme = FluentTheme.of(context);
    final foreground = enabled
        ? theme.accentColor.defaultBrushFor(theme.brightness)
        : theme.resources.textFillColorSecondary;
    return Container(
      width: 40,
      height: 40,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: enabled
            ? theme.accentColor.withAlpha(
                theme.brightness == Brightness.dark ? 52 : 28,
              )
            : theme.resources.subtleFillColorSecondary,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Icon(icon, size: 18, color: foreground),
    );
  }
}

class StatusPill extends StatelessWidget {
  const StatusPill(this.label, {this.accented = false, super.key});

  final String label;
  final bool accented;

  @override
  Widget build(BuildContext context) {
    final theme = FluentTheme.of(context);
    final foreground = accented
        ? theme.accentColor.defaultBrushFor(theme.brightness)
        : theme.resources.textFillColorSecondary;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: accented
            ? theme.accentColor.withAlpha(
                theme.brightness == Brightness.dark ? 46 : 22,
              )
            : theme.resources.subtleFillColorSecondary,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: theme.typography.caption?.copyWith(color: foreground),
      ),
    );
  }
}

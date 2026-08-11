import 'package:fluent_ui/fluent_ui.dart';

import 'responsive.dart';

enum AppSurfaceTone { standard, muted, accent, elevated, danger }

/// 青卷中承载同层级内容的标准表面。
///
/// 手机表面使用极轻的描边与抬升感区分背景；可点击表面再通过背景变化提供反馈。
class AppSurface extends StatelessWidget {
  const AppSurface({
    required this.child,
    this.padding = const EdgeInsets.all(16),
    this.margin,
    this.onPressed,
    this.selected = false,
    this.tone = AppSurfaceTone.standard,
    this.borderRadius,
    super.key,
  });

  final Widget child;
  final EdgeInsetsGeometry padding;
  final EdgeInsetsGeometry? margin;
  final VoidCallback? onPressed;
  final bool selected;
  final AppSurfaceTone tone;
  final double? borderRadius;

  @override
  Widget build(BuildContext context) {
    if (onPressed == null) {
      return _SurfaceBody(
        padding: padding,
        margin: margin,
        selected: selected,
        tone: tone,
        borderRadius: borderRadius,
        hovered: false,
        pressed: false,
        child: child,
      );
    }

    return HoverButton(
      onPressed: onPressed,
      builder: (context, states) => AnimatedScale(
        duration: MediaQuery.disableAnimationsOf(context)
            ? Duration.zero
            : FluentTheme.of(context).fasterAnimationDuration,
        curve: Curves.easeOutCubic,
        scale: states.isPressed ? 0.985 : 1,
        child: _SurfaceBody(
          padding: padding,
          margin: margin,
          selected: selected,
          tone: tone,
          borderRadius: borderRadius,
          hovered: states.isHovered,
          pressed: states.isPressed,
          child: child,
        ),
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
    required this.tone,
    required this.borderRadius,
    required this.hovered,
    required this.pressed,
  });

  final Widget child;
  final EdgeInsetsGeometry padding;
  final EdgeInsetsGeometry? margin;
  final bool selected;
  final AppSurfaceTone tone;
  final double? borderRadius;
  final bool hovered;
  final bool pressed;

  @override
  Widget build(BuildContext context) {
    final theme = FluentTheme.of(context);
    final compact = windowClassOf(context) == WindowClass.compact;
    final dark = theme.brightness == Brightness.dark;
    final fill = switch (tone) {
      AppSurfaceTone.standard => theme.cardColor,
      AppSurfaceTone.muted =>
        dark ? const Color(0xFF211F1C) : const Color(0xFFECE6DA),
      AppSurfaceTone.accent => theme.accentColor.withAlpha(dark ? 48 : 24),
      AppSurfaceTone.elevated =>
        dark ? const Color(0xFF2C2A25) : const Color(0xFFFFFDF8),
      AppSurfaceTone.danger =>
        dark ? const Color(0xFF352321) : const Color(0xFFFFF0EA),
    };
    final borderColor = selected
        ? theme.accentColor.withAlpha(
            dark ? 190 : 150,
          )
        : hovered
            ? theme.resources.controlStrokeColorSecondary
            : tone == AppSurfaceTone.muted
                ? theme.resources.cardStrokeColorDefault.withAlpha(55)
                : theme.resources.cardStrokeColorDefault.withAlpha(
                    compact ? 92 : 120,
                  );
    return AnimatedContainer(
      duration: MediaQuery.maybeOf(context)?.disableAnimations ?? false
          ? Duration.zero
          : theme.fasterAnimationDuration,
      curve: Curves.easeOutCubic,
      width: double.infinity,
      margin: margin,
      padding: padding,
      decoration: BoxDecoration(
        color: pressed
            ? theme.resources.subtleFillColorTertiary
            : hovered
                ? Color.lerp(fill, theme.resources.subtleFillColorSecondary, .2)
                : fill,
        border: Border.all(color: borderColor),
        borderRadius: BorderRadius.circular(
          borderRadius ?? (compact ? 19 : 14),
        ),
        boxShadow: tone == AppSurfaceTone.elevated ||
                (compact && tone == AppSurfaceTone.standard)
            ? <BoxShadow>[
                BoxShadow(
                  color: const Color(0xFF4B3529).withAlpha(
                    dark ? 28 : 13,
                  ),
                  blurRadius: 20,
                  offset: const Offset(0, 8),
                ),
              ]
            : null,
      ),
      child: child,
    );
  }
}

class AccentIcon extends StatelessWidget {
  const AccentIcon(
    this.icon, {
    this.enabled = true,
    this.color,
    this.size,
    super.key,
  });

  final IconData icon;
  final bool enabled;
  final Color? color;
  final double? size;

  @override
  Widget build(BuildContext context) {
    final theme = FluentTheme.of(context);
    final compact = windowClassOf(context) == WindowClass.compact;
    final foreground = enabled
        ? color ?? theme.accentColor.defaultBrushFor(theme.brightness)
        : theme.resources.textFillColorSecondary;
    return Container(
      width: size ?? (compact ? 44 : 40),
      height: size ?? (compact ? 44 : 40),
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: enabled
            ? foreground.withAlpha(
                theme.brightness == Brightness.dark ? 58 : 26,
              )
            : theme.resources.subtleFillColorSecondary,
        borderRadius: BorderRadius.circular(compact ? 13 : 8),
      ),
      child: Icon(icon, size: compact ? 20 : 18, color: foreground),
    );
  }
}

class StatusPill extends StatelessWidget {
  const StatusPill(
    this.label, {
    this.accented = false,
    this.color,
    this.icon,
    super.key,
  });

  final String label;
  final bool accented;
  final Color? color;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    final theme = FluentTheme.of(context);
    final compact = windowClassOf(context) == WindowClass.compact;
    final foreground = color ??
        (accented
            ? theme.accentColor.defaultBrushFor(theme.brightness)
            : theme.resources.textFillColorSecondary);
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: compact ? 10 : 8,
        vertical: compact ? 5 : 3,
      ),
      decoration: BoxDecoration(
        color: accented || color != null
            ? foreground.withAlpha(
                theme.brightness == Brightness.dark ? 46 : 22,
              )
            : theme.resources.subtleFillColorSecondary,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          if (icon != null) ...<Widget>[
            Icon(icon, size: 12, color: foreground),
            const SizedBox(width: 5),
          ],
          Flexible(
            child: Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: theme.typography.caption?.copyWith(color: foreground),
            ),
          ),
        ],
      ),
    );
  }
}

class FeatureHero extends StatelessWidget {
  const FeatureHero({
    required this.icon,
    required this.title,
    required this.message,
    this.trailing,
    this.child,
    this.warm = false,
    super.key,
  });

  final IconData icon;
  final String title;
  final String message;
  final Widget? trailing;
  final Widget? child;
  final bool warm;

  @override
  Widget build(BuildContext context) {
    final theme = FluentTheme.of(context);
    final dark = theme.brightness == Brightness.dark;
    final accent = warm
        ? (dark ? const Color(0xFFE7A274) : const Color(0xFFBE6947))
        : theme.accentColor.defaultBrushFor(theme.brightness);
    return ClipRRect(
      borderRadius: BorderRadius.circular(24),
      child: DecoratedBox(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: AlignmentDirectional.topStart,
            end: AlignmentDirectional.bottomEnd,
            colors: warm
                ? (dark
                    ? const <Color>[Color(0xFF382A23), Color(0xFF25211D)]
                    : const <Color>[Color(0xFFF4DACA), Color(0xFFFFF6E9)])
                : (dark
                    ? const <Color>[Color(0xFF2F3028), Color(0xFF23231F)]
                    : const <Color>[Color(0xFFE7E1C9), Color(0xFFF8F2E7)]),
          ),
        ),
        child: Stack(
          children: <Widget>[
            PositionedDirectional(
              end: -34,
              top: -46,
              child: ExcludeSemantics(
                child: Container(
                  width: 142,
                  height: 142,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: accent.withAlpha(dark ? 18 : 16),
                  ),
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(18),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      AccentIcon(icon, color: accent, size: 48),
                      const SizedBox(width: 14),
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
                            const SizedBox(height: 4),
                            Text(
                              message,
                              style: theme.typography.caption?.copyWith(
                                height: 1.45,
                                color: theme.resources.textFillColorSecondary,
                              ),
                            ),
                          ],
                        ),
                      ),
                      if (trailing != null) ...<Widget>[
                        const SizedBox(width: 12),
                        trailing!,
                      ],
                    ],
                  ),
                  if (child != null) ...<Widget>[
                    const SizedBox(height: 16),
                    child!,
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class AppMetric extends StatelessWidget {
  const AppMetric({
    required this.value,
    required this.label,
    this.accented = false,
    super.key,
  });

  final String value;
  final String label;
  final bool accented;

  @override
  Widget build(BuildContext context) {
    final theme = FluentTheme.of(context);
    final color = accented
        ? theme.accentColor.defaultBrushFor(theme.brightness)
        : theme.resources.textFillColorPrimary;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Text(
          value,
          style: theme.typography.subtitle?.copyWith(
            color: color,
            fontWeight: FontWeight.w800,
          ),
        ),
        const SizedBox(height: 3),
        Text(label, maxLines: 1, style: theme.typography.caption),
      ],
    );
  }
}

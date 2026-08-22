import 'dart:ui' as ui;

import 'package:fluent_ui/fluent_ui.dart';
import 'package:flutter_miuix/miuix.dart' as miuix;

import 'motion.dart';
import 'responsive.dart';

enum AppSurfaceTone { standard, muted, accent, elevated, danger }

/// 用于导航栏和阅读浮层的受控液态玻璃表面。
///
/// 模糊始终被圆角裁剪和重绘边界限制；高对比度模式下关闭模糊并使用不透明
/// 表面，避免透明效果削弱文字和图标的可读性。
class AppGlassSurface extends StatelessWidget {
  const AppGlassSurface({
    required this.child,
    this.borderRadius = 22,
    this.blurSigma = 16,
    this.padding = EdgeInsets.zero,
    super.key,
  });

  final Widget child;
  final double borderRadius;
  final double blurSigma;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) {
    final theme = FluentTheme.of(context);
    final dark = theme.brightness == Brightness.dark;
    final highContrast = MediaQuery.highContrastOf(context);
    final radius = BorderRadius.circular(borderRadius);
    final fill = highContrast
        ? theme.cardColor
        : dark
            ? const Color(0xDC1D222B)
            : const Color(0xDCFFFFFF);
    final borderColor = highContrast
        ? theme.resources.controlStrokeColorDefault
        : dark
            ? const Color(0x4DFFFFFF)
            : const Color(0xBFE3EAF3);
    final surface = DecoratedBox(
      decoration: BoxDecoration(
        color: fill,
        border: Border.all(color: borderColor),
        borderRadius: radius,
      ),
      child: Padding(padding: padding, child: child),
    );

    return RepaintBoundary(
      child: DecoratedBox(
        decoration: BoxDecoration(
          borderRadius: radius,
          boxShadow: <BoxShadow>[
            BoxShadow(
              color: const Color(0xFF101828).withAlpha(dark ? 64 : 22),
              blurRadius: 20,
              spreadRadius: -3,
              offset: const Offset(0, 6),
            ),
          ],
        ),
        child: ClipRRect(
          borderRadius: radius,
          child: highContrast || blurSigma <= 0
              ? surface
              : BackdropFilter(
                  filter: ui.ImageFilter.blur(
                    sigmaX: blurSigma,
                    sigmaY: blurSigma,
                  ),
                  child: surface,
                ),
        ),
      ),
    );
  }
}

/// 青卷中承载同层级内容的标准表面。
///
/// 手机表面使用留白、明度与极轻分隔线区分层级；可点击表面通过背景变化提供反馈。
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
    final mobile = usesMobileUi(context);
    if (mobile) {
      return _MiuixSurfaceBody(
        padding: padding,
        margin: margin,
        selected: selected,
        tone: tone,
        borderRadius: borderRadius,
        onPressed: onPressed,
        child: child,
      );
    }
    if (onPressed == null) {
      return _SurfaceBody(
        padding: padding,
        margin: margin,
        selected: selected,
        tone: tone,
        borderRadius: borderRadius,
        hovered: false,
        pressed: false,
        animate: false,
        child: child,
      );
    }

    return HoverButton(
      onPressed: onPressed,
      builder: (context, states) {
        final body = _SurfaceBody(
          padding: padding,
          margin: margin,
          selected: selected,
          tone: tone,
          borderRadius: borderRadius,
          hovered: states.isHovered,
          pressed: states.isPressed,
          animate: true,
          child: child,
        );
        if (!mobile) return body;
        return AnimatedScale(
          duration: QjMotion.duration(context, QjMotionSpeed.faster),
          curve: QjMotion.enterCurve,
          scale: states.isPressed ? 0.985 : 1,
          child: body,
        );
      },
    );
  }
}

class _MiuixSurfaceBody extends StatelessWidget {
  const _MiuixSurfaceBody({
    required this.child,
    required this.padding,
    required this.margin,
    required this.selected,
    required this.tone,
    required this.borderRadius,
    required this.onPressed,
  });

  final Widget child;
  final EdgeInsetsGeometry padding;
  final EdgeInsetsGeometry? margin;
  final bool selected;
  final AppSurfaceTone tone;
  final double? borderRadius;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    final colors = miuix.MiuixTheme.of(context).colors;
    final effectiveTone = selected ? AppSurfaceTone.accent : tone;
    final cardColors = switch (effectiveTone) {
      AppSurfaceTone.standard ||
      AppSurfaceTone.elevated =>
        miuix.MiuixCardColors(
          color: colors.surfaceContainer,
          contentColor: colors.onSurfaceContainer,
        ),
      AppSurfaceTone.muted => miuix.MiuixCardColors(
          color: colors.surfaceContainerHigh,
          contentColor: colors.onSurfaceContainerHigh,
        ),
      AppSurfaceTone.accent => miuix.MiuixCardColors(
          color: colors.primaryContainer,
          contentColor: colors.onPrimaryContainer,
        ),
      AppSurfaceTone.danger => miuix.MiuixCardColors(
          color: colors.errorContainer,
          contentColor: colors.onErrorContainer,
        ),
    };
    final card = miuix.MiuixCard(
      cornerRadius: borderRadius ?? 18,
      insideMargin: padding,
      colors: cardColors,
      onPressed: onPressed,
      feedbackType: onPressed == null
          ? miuix.MiuixPressFeedbackType.none
          : miuix.MiuixPressFeedbackType.sink,
      child: child,
    );
    if (margin == null) return card;
    return Padding(padding: margin!, child: card);
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
    required this.animate,
  });

  final Widget child;
  final EdgeInsetsGeometry padding;
  final EdgeInsetsGeometry? margin;
  final bool selected;
  final AppSurfaceTone tone;
  final double? borderRadius;
  final bool hovered;
  final bool pressed;
  final bool animate;

  @override
  Widget build(BuildContext context) {
    final theme = FluentTheme.of(context);
    final compact = usesMobileUi(context);
    final dark = theme.brightness == Brightness.dark;
    if (!compact) {
      final borderColor = selected
          ? theme.accentColor
          : hovered
              ? theme.resources.controlStrokeColorSecondary
              : theme.resources.cardStrokeColorDefault;
      return AnimatedContainer(
        duration: QjMotion.duration(context, QjMotionSpeed.faster),
        curve: QjMotion.enterCurve,
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
    final fill = switch (tone) {
      AppSurfaceTone.standard => theme.cardColor,
      AppSurfaceTone.muted =>
        dark ? const Color(0xFF20242B) : const Color(0xFFF0F3F7),
      AppSurfaceTone.accent =>
        dark ? const Color(0xFF182740) : const Color(0xFFEDF4FF),
      AppSurfaceTone.elevated =>
        dark ? const Color(0xFF20242B) : const Color(0xFFFFFFFF),
      AppSurfaceTone.danger =>
        dark ? const Color(0xFF352326) : const Color(0xFFFFF1F2),
    };
    final borderColor = selected
        ? theme.accentColor.withAlpha(
            dark ? 190 : 138,
          )
        : hovered
            ? theme.resources.controlStrokeColorSecondary
            : tone == AppSurfaceTone.muted
                ? const Color(0x00000000)
                : dark
                    ? const Color(0xFF303640)
                    : const Color(0xFFE8ECF2);
    final decoration = BoxDecoration(
      color: pressed
          ? theme.resources.subtleFillColorTertiary
          : hovered
              ? Color.lerp(fill, theme.resources.subtleFillColorSecondary, .2)
              : fill,
      border: Border.all(color: borderColor),
      borderRadius: BorderRadius.circular(borderRadius ?? 16),
      boxShadow: tone == AppSurfaceTone.elevated
          ? <BoxShadow>[
              BoxShadow(
                color: const Color(0xFF101828).withAlpha(dark ? 22 : 9),
                blurRadius: 12,
                offset: const Offset(0, 3),
              ),
            ]
          : null,
    );
    if (!animate) {
      return Container(
        width: double.infinity,
        margin: margin,
        padding: padding,
        decoration: decoration,
        child: child,
      );
    }
    return AnimatedContainer(
      duration: QjMotion.duration(context, QjMotionSpeed.faster),
      curve: QjMotion.enterCurve,
      width: double.infinity,
      margin: margin,
      padding: padding,
      decoration: decoration,
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
    final compact = usesMobileUi(context);
    final foreground = enabled
        ? color ?? theme.accentColor.defaultBrushFor(theme.brightness)
        : theme.resources.textFillColorSecondary;
    final extent = size ?? (compact ? 42 : 40);
    return Container(
      width: extent,
      height: extent,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: enabled
            ? foreground.withAlpha(
                theme.brightness == Brightness.dark ? 58 : 26,
              )
            : theme.resources.subtleFillColorSecondary,
        borderRadius: BorderRadius.circular(compact ? 12 : 8),
      ),
      child: Icon(
        icon,
        size: compact ? 20 : (size == null ? 18 : size! * 0.42),
        color: foreground,
      ),
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
    final compact = usesMobileUi(context);
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
    if (!usesMobileUi(context)) {
      return AppSurface(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                AccentIcon(icon),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text(title, style: theme.typography.subtitle),
                      const SizedBox(height: 4),
                      Text(
                        message,
                        style: theme.typography.caption?.copyWith(
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
      );
    }
    final accent = theme.accentColor.defaultBrushFor(theme.brightness);
    return AppSurface(
      tone: AppSurfaceTone.accent,
      borderRadius: 18,
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              AccentIcon(icon, color: accent, size: 44),
              const SizedBox(width: 13),
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
            const SizedBox(height: 14),
            child!,
          ],
        ],
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

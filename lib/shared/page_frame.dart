import 'package:fluent_ui/fluent_ui.dart';

import 'responsive.dart';

class PageFrame extends StatelessWidget {
  const PageFrame({
    required this.title,
    required this.subtitle,
    required this.child,
    this.command,
    this.compactHeader,
    this.scrollable = true,
    this.maxContentWidth,
    this.desktopHorizontalPadding,
    super.key,
  });

  final String title;
  final String subtitle;
  final Widget child;
  final Widget? command;
  final Widget? compactHeader;
  final bool scrollable;
  final double? maxContentWidth;
  final double? desktopHorizontalPadding;

  @override
  Widget build(BuildContext context) {
    final compact = usesMobileUi(context);
    final horizontalPadding = compact ? 18.0 : desktopHorizontalPadding ?? 32.0;
    final body = Align(
      alignment: Alignment.topCenter,
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxWidth: maxContentWidth ?? contentMaxWidth(context),
        ),
        child: Padding(
          padding: EdgeInsets.fromLTRB(
            horizontalPadding,
            compact ? 12 : 28,
            horizontalPadding,
            compact ? 24 : 32,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              if (compact)
                compactHeader ??
                    _MobilePageHeader(
                      title: title,
                      subtitle: subtitle,
                      command: command,
                    )
              else
                _DesktopPageHeader(
                  title: title,
                  subtitle: subtitle,
                  command: command,
                ),
              SizedBox(height: compact ? 18 : 24),
              child,
            ],
          ),
        ),
      ),
    );
    return scrollable ? SingleChildScrollView(child: body) : body;
  }
}

class _DesktopPageHeader extends StatelessWidget {
  const _DesktopPageHeader({
    required this.title,
    required this.subtitle,
    this.command,
  });

  final String title;
  final String subtitle;
  final Widget? command;

  @override
  Widget build(BuildContext context) {
    final theme = FluentTheme.of(context);
    final heading = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Text(title, style: theme.typography.title),
        const SizedBox(height: 6),
        Text(
          subtitle,
          style: theme.typography.body?.copyWith(
            color: theme.resources.textFillColorSecondary,
          ),
        ),
      ],
    );
    return LayoutBuilder(
      builder: (context, constraints) {
        if (command != null && constraints.maxWidth < 680) {
          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              heading,
              const SizedBox(height: 16),
              command!,
            ],
          );
        }
        return Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Expanded(child: heading),
            if (command != null) ...<Widget>[
              const SizedBox(width: 20),
              command!,
            ],
          ],
        );
      },
    );
  }
}

class _MobilePageHeader extends StatelessWidget {
  const _MobilePageHeader({
    required this.title,
    required this.subtitle,
    this.command,
  });

  final String title;
  final String subtitle;
  final Widget? command;

  @override
  Widget build(BuildContext context) {
    final theme = FluentTheme.of(context);
    final textScaler = TextScaler.linear(
      MediaQuery.textScalerOf(context).scale(1).clamp(1.0, 1.35),
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Text(
          title,
          textScaler: textScaler,
          style: theme.typography.title?.copyWith(
            fontSize: 28,
            height: 1.16,
            fontWeight: FontWeight.w700,
            letterSpacing: -0.2,
          ),
        ),
        const SizedBox(height: 7),
        Text(
          subtitle,
          textScaler: textScaler,
          style: theme.typography.body?.copyWith(
            fontSize: 13,
            height: 1.5,
            color: theme.resources.textFillColorSecondary,
          ),
        ),
        if (command != null) ...<Widget>[
          const SizedBox(height: 16),
          MediaQuery(
            data: MediaQuery.of(context).copyWith(textScaler: textScaler),
            child: command!,
          ),
        ],
      ],
    );
  }
}

/// 手机阅读类首页使用的紧凑标题栏。
///
/// 它不承担全局品牌展示，只提供当前场景、简短状态与一到两个快捷操作。
class ReadingPageHeader extends StatelessWidget {
  const ReadingPageHeader({
    required this.title,
    required this.subtitle,
    required this.actions,
    super.key,
  });

  final String title;
  final String subtitle;
  final List<Widget> actions;

  @override
  Widget build(BuildContext context) {
    final theme = FluentTheme.of(context);
    final textScaler = TextScaler.linear(
      MediaQuery.textScalerOf(context).scale(1).clamp(1.0, 1.25),
    );
    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: <Widget>[
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(
                title,
                textScaler: textScaler,
                style: theme.typography.title?.copyWith(
                  fontSize: 28,
                  height: 1.16,
                  fontWeight: FontWeight.w700,
                  letterSpacing: -0.2,
                ),
              ),
              const SizedBox(height: 6),
              Text(
                subtitle,
                textScaler: textScaler,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: theme.typography.caption?.copyWith(
                  fontSize: 13,
                  color: theme.resources.textFillColorSecondary,
                ),
              ),
            ],
          ),
        ),
        if (actions.isNotEmpty) ...<Widget>[
          const SizedBox(width: 12),
          MediaQuery(
            data: MediaQuery.of(context).copyWith(textScaler: textScaler),
            child: Row(mainAxisSize: MainAxisSize.min, children: actions),
          ),
        ],
      ],
    );
  }
}

class SectionTitle extends StatelessWidget {
  const SectionTitle(this.title, {this.trailing, super.key});

  final String title;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final compact = usesMobileUi(context);
    return Padding(
      padding: EdgeInsets.only(bottom: compact ? 14 : 12),
      child: Row(
        children: <Widget>[
          Expanded(
            child: Text(
              title,
              style: FluentTheme.of(context).typography.subtitle?.copyWith(
                    fontSize: compact ? 17 : null,
                    fontWeight: compact ? FontWeight.w700 : null,
                  ),
            ),
          ),
          if (trailing != null) trailing!,
        ],
      ),
    );
  }
}

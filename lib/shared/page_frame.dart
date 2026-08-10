import 'package:fluent_ui/fluent_ui.dart';

import 'responsive.dart';

class PageFrame extends StatelessWidget {
  const PageFrame({
    required this.title,
    required this.subtitle,
    required this.child,
    this.command,
    this.scrollable = true,
    super.key,
  });

  final String title;
  final String subtitle;
  final Widget child;
  final Widget? command;
  final bool scrollable;

  @override
  Widget build(BuildContext context) {
    final compact = windowClassOf(context) == WindowClass.compact;
    final padding = EdgeInsets.fromLTRB(
      compact ? 18 : 32,
      compact ? 18 : 28,
      compact ? 18 : 32,
      32,
    );
    final body = Align(
      alignment: Alignment.topCenter,
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: contentMaxWidth(context)),
        child: Padding(
          padding: padding,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              LayoutBuilder(
                builder: (context, constraints) {
                  final stackCommand = command != null &&
                      (compact || constraints.maxWidth < 680);
                  final heading = Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text(
                        title,
                        style: FluentTheme.of(context).typography.title,
                      ),
                      const SizedBox(height: 6),
                      Text(
                        subtitle,
                        style:
                            FluentTheme.of(context).typography.body?.copyWith(
                                  color: FluentTheme.of(context)
                                      .resources
                                      .textFillColorSecondary,
                                ),
                      ),
                    ],
                  );
                  if (stackCommand) {
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
              ),
              const SizedBox(height: 24),
              child,
            ],
          ),
        ),
      ),
    );
    return scrollable ? SingleChildScrollView(child: body) : body;
  }
}

class SectionTitle extends StatelessWidget {
  const SectionTitle(this.title, {this.trailing, super.key});

  final String title;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        children: <Widget>[
          Expanded(
            child: Text(
              title,
              style: FluentTheme.of(context).typography.subtitle,
            ),
          ),
          if (trailing != null) trailing!,
        ],
      ),
    );
  }
}

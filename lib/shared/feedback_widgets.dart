import 'package:fluent_ui/fluent_ui.dart';

class LoadingView extends StatelessWidget {
  const LoadingView({this.label = '正在加载', super.key});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(48),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            const ProgressRing(),
            const SizedBox(height: 14),
            Text(label),
          ],
        ),
      ),
    );
  }
}

class EmptyView extends StatelessWidget {
  const EmptyView({
    required this.icon,
    required this.title,
    required this.message,
    this.action,
    super.key,
  });

  final IconData icon;
  final String title;
  final String message;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 64, horizontal: 24),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 460),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Icon(icon, size: 34, color: FluentTheme.of(context).accentColor),
              const SizedBox(height: 16),
              Text(title, style: FluentTheme.of(context).typography.subtitle),
              const SizedBox(height: 8),
              Text(message, textAlign: TextAlign.center),
              if (action != null) ...<Widget>[
                const SizedBox(height: 18),
                action!
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class ErrorView extends StatelessWidget {
  const ErrorView({required this.message, required this.onRetry, super.key});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return EmptyView(
      icon: FluentIcons.error,
      title: '暂时无法加载',
      message: message,
      action: Button(onPressed: onRetry, child: const Text('重试')),
    );
  }
}

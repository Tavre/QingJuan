import 'package:fluent_ui/fluent_ui.dart';

/// 青卷共享动效时长。
///
/// Feature 只选择语义速度，不直接复制毫秒数；系统请求减少动态效果时，
/// 所有入口统一解析为零时长。
enum QjMotionSpeed { faster, fast, medium, slow }

abstract final class QjMotion {
  static const Curve enterCurve = Curves.easeOutCubic;
  static const Curve exitCurve = Curves.easeInCubic;

  static bool disabled(BuildContext context) =>
      MediaQuery.maybeOf(context)?.disableAnimations ?? false;

  static Duration duration(
    BuildContext context, [
    QjMotionSpeed speed = QjMotionSpeed.medium,
  ]) {
    if (disabled(context)) return Duration.zero;
    final theme = FluentTheme.of(context);
    return switch (speed) {
      QjMotionSpeed.faster => theme.fasterAnimationDuration,
      QjMotionSpeed.fast => theme.fastAnimationDuration,
      QjMotionSpeed.medium => theme.mediumAnimationDuration,
      QjMotionSpeed.slow => theme.slowAnimationDuration,
    };
  }

  static Duration resolve(BuildContext context, Duration duration) =>
      disabled(context) ? Duration.zero : duration;
}

/// 顶层导航使用的淡入位移切换。
///
/// 旧页面立即退出，避免交叉动画期间出现重复焦点、语义或可点击控件；新页面
/// 由重绘边界隔离后轻量入场。业务 Controller 位于 AppScope，不会重新创建。
class QjPageSwitcher extends StatelessWidget {
  const QjPageSwitcher({
    required this.pageKey,
    required this.child,
    this.beginOffset = const Offset(0.025, 0),
    super.key,
  });

  final Object pageKey;
  final Widget child;
  final Offset beginOffset;

  @override
  Widget build(BuildContext context) {
    final keyedChild = KeyedSubtree(
      key: ValueKey<Object>(pageKey),
      child: RepaintBoundary(child: child),
    );
    if (QjMotion.disabled(context)) return keyedChild;

    return TweenAnimationBuilder<double>(
      key: ValueKey<Object>(pageKey),
      tween: Tween<double>(begin: 0, end: 1),
      duration: QjMotion.duration(context),
      curve: QjMotion.enterCurve,
      builder: (context, progress, transitionChild) {
        return Opacity(
          opacity: progress,
          child: FractionalTranslation(
            translation: Offset(
              beginOffset.dx * (1 - progress),
              beginOffset.dy * (1 - progress),
            ),
            child: transitionChild,
          ),
        );
      },
      child: keyedChild,
    );
  }
}

/// `Navigator` 等外部动画驱动的共享淡入位移过渡。
class QjPageTransition extends StatelessWidget {
  const QjPageTransition({
    required this.animation,
    required this.child,
    this.beginOffset = const Offset(0.018, 0),
    super.key,
  });

  final Animation<double> animation;
  final Widget child;
  final Offset beginOffset;

  @override
  Widget build(BuildContext context) {
    if (QjMotion.disabled(context)) return child;
    final curved = animation.drive(CurveTween(curve: QjMotion.enterCurve));
    return FadeTransition(
      opacity: curved,
      child: SlideTransition(
        position: Tween<Offset>(
          begin: beginOffset,
          end: Offset.zero,
        ).animate(curved),
        child: RepaintBoundary(child: child),
      ),
    );
  }
}

/// 创建统一的详情 / 阅读页面路由，并自动遵循系统减少动态效果设置。
PageRoute<T> qjPageRoute<T>({
  required BuildContext context,
  required WidgetBuilder builder,
  RouteSettings? settings,
  Offset beginOffset = const Offset(0.025, 0),
}) {
  final transitionDuration = QjMotion.duration(context);
  final reverseTransitionDuration =
      QjMotion.duration(context, QjMotionSpeed.fast);
  return PageRouteBuilder<T>(
    settings: settings,
    transitionDuration: transitionDuration,
    reverseTransitionDuration: reverseTransitionDuration,
    pageBuilder: (routeContext, animation, secondaryAnimation) =>
        builder(routeContext),
    transitionsBuilder: (routeContext, animation, secondaryAnimation, child) {
      if (transitionDuration == Duration.zero) return child;
      return QjPageTransition(
        animation: animation,
        beginOffset: beginOffset,
        child: child,
      );
    },
  );
}

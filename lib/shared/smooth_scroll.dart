import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/rendering.dart' show ScrollDirection;
import 'package:flutter/widgets.dart';

/// A scroll controller that smooths discrete mouse-wheel steps on desktop.
///
/// Precision trackpads already provide small, frequent deltas and therefore
/// stay on Flutter's native pointer-scroll path. Touch dragging and mobile
/// scrolling are not changed either.
class QjScrollController extends ScrollController {
  QjScrollController({
    super.initialScrollOffset,
    super.keepScrollOffset,
    super.debugLabel,
    super.onAttach,
    super.onDetach,
    bool? smoothDesktopWheel,
  }) : _smoothDesktopWheel =
            smoothDesktopWheel ?? _isDesktopPlatform(defaultTargetPlatform);

  final bool _smoothDesktopWheel;

  @override
  ScrollPosition createScrollPosition(
    ScrollPhysics physics,
    ScrollContext context,
    ScrollPosition? oldPosition,
  ) =>
      _QjScrollPosition(
        physics: physics,
        context: context,
        initialPixels: initialScrollOffset,
        keepScrollOffset: keepScrollOffset,
        oldPosition: oldPosition,
        debugLabel: debugLabel,
        smoothDesktopWheel: _smoothDesktopWheel,
      );
}

/// Owns a [QjScrollController] for scroll views built by otherwise stateless
/// page widgets.
class QjScrollControllerBuilder extends StatefulWidget {
  const QjScrollControllerBuilder({
    required this.builder,
    this.debugLabel,
    super.key,
  });

  final Widget Function(BuildContext context, ScrollController controller)
      builder;
  final String? debugLabel;

  @override
  State<QjScrollControllerBuilder> createState() =>
      _QjScrollControllerBuilderState();
}

class _QjScrollControllerBuilderState extends State<QjScrollControllerBuilder> {
  late final QjScrollController _controller = QjScrollController(
    debugLabel: widget.debugLabel,
  );

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => widget.builder(context, _controller);
}

bool _isDesktopPlatform(TargetPlatform platform) => switch (platform) {
      TargetPlatform.windows ||
      TargetPlatform.linux ||
      TargetPlatform.macOS =>
        true,
      _ => false,
    };

class _QjScrollPosition extends ScrollPositionWithSingleContext {
  _QjScrollPosition({
    required super.physics,
    required super.context,
    required this.smoothDesktopWheel,
    super.initialPixels,
    super.keepScrollOffset,
    super.oldPosition,
    super.debugLabel,
  });

  /// Flutter desktop currently reports a standard mouse-wheel notch as about
  /// 20 logical pixels. Smaller values are normally precision scrolling, which
  /// is already smooth and must remain immediate.
  static const double _discreteWheelThreshold = 18;
  static const Duration _wheelAnimationDuration = Duration(milliseconds: 110);

  final bool smoothDesktopWheel;

  double? _wheelTarget;
  int _wheelAnimationGeneration = 0;

  @override
  void pointerScroll(double delta) {
    final notificationContext = context.notificationContext;
    final reduceMotion = notificationContext != null &&
        (MediaQuery.maybeOf(notificationContext)?.disableAnimations ?? false);
    if (!smoothDesktopWheel ||
        reduceMotion ||
        delta.abs() < _discreteWheelThreshold) {
      _cancelPendingWheelTarget();
      super.pointerScroll(delta);
      return;
    }
    if (delta == 0 || !hasContentDimensions) {
      super.pointerScroll(delta);
      return;
    }

    final base = _wheelTarget ?? pixels;
    final target =
        (base + delta).clamp(minScrollExtent, maxScrollExtent).toDouble();
    if (target == pixels && _wheelTarget == null) {
      super.pointerScroll(delta);
      return;
    }

    _wheelTarget = target;
    final generation = ++_wheelAnimationGeneration;
    updateUserScrollDirection(
      delta < 0 ? ScrollDirection.forward : ScrollDirection.reverse,
    );
    unawaited(
      animateTo(
        target,
        duration: _wheelAnimationDuration,
        curve: Curves.easeOutCubic,
      ).whenComplete(() {
        if (generation == _wheelAnimationGeneration) _wheelTarget = null;
      }),
    );
  }

  void _cancelPendingWheelTarget() {
    _wheelAnimationGeneration += 1;
    _wheelTarget = null;
  }
}

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';

enum WindowClass { compact, medium, expanded }

class UiPlatformScope extends InheritedWidget {
  const UiPlatformScope({
    required this.platform,
    required super.child,
    super.key,
  });

  final TargetPlatform platform;

  static TargetPlatform of(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<UiPlatformScope>()?.platform ??
      defaultTargetPlatform;

  @override
  bool updateShouldNotify(UiPlatformScope oldWidget) =>
      platform != oldWidget.platform;
}

/// 平台决定顶层视觉语言，窗口宽度只负责同一平台内部的重排。
bool usesMobileUi(BuildContext context) =>
    switch (UiPlatformScope.of(context)) {
      TargetPlatform.android ||
      TargetPlatform.iOS ||
      TargetPlatform.fuchsia =>
        true,
      TargetPlatform.windows ||
      TargetPlatform.macOS ||
      TargetPlatform.linux =>
        false,
    };

WindowClass windowClassOf(BuildContext context) {
  final width = MediaQuery.sizeOf(context).width;
  if (width < 700) return WindowClass.compact;
  if (width < 1100) return WindowClass.medium;
  return WindowClass.expanded;
}

double contentMaxWidth(BuildContext context) =>
    switch (windowClassOf(context)) {
      WindowClass.compact => double.infinity,
      WindowClass.medium => 920,
      WindowClass.expanded => 1320,
    };

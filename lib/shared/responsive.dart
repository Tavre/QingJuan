import 'package:flutter/widgets.dart';

enum WindowClass { compact, medium, expanded }

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

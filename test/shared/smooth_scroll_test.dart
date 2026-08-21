import 'package:flutter/foundation.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:qingjuan/shared/smooth_scroll.dart';

void main() {
  setUp(() => debugDefaultTargetPlatformOverride = null);
  tearDown(() => debugDefaultTargetPlatformOverride = null);

  testWidgets('desktop wheel steps animate instead of jumping', (tester) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.windows;
    final controller = QjScrollController();
    debugDefaultTargetPlatformOverride = null;
    addTearDown(controller.dispose);
    await tester.pumpWidget(_scrollFixture(controller));

    await _sendWheel(tester, 20);

    expect(controller.offset, 0);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 45));
    expect(controller.offset, greaterThan(0));
    expect(controller.offset, lessThan(20));
    await tester.pumpAndSettle();
    expect(controller.offset, closeTo(20, 0.01));
  });

  testWidgets('rapid desktop wheel steps accumulate their target',
      (tester) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.windows;
    final controller = QjScrollController();
    debugDefaultTargetPlatformOverride = null;
    addTearDown(controller.dispose);
    await tester.pumpWidget(_scrollFixture(controller));

    await _sendWheel(tester, 20);
    await _sendWheel(tester, 20);
    await _sendWheel(tester, 20);
    await tester.pumpAndSettle();

    expect(controller.offset, closeTo(60, 0.01));
  });

  testWidgets('fine desktop pointer deltas keep native immediate scrolling',
      (tester) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.windows;
    final controller = QjScrollController();
    debugDefaultTargetPlatformOverride = null;
    addTearDown(controller.dispose);
    await tester.pumpWidget(_scrollFixture(controller));

    await _sendWheel(tester, 4);

    expect(controller.offset, closeTo(4, 0.01));
  });

  testWidgets('reduced motion keeps desktop wheel scrolling immediate',
      (tester) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.windows;
    final controller = QjScrollController();
    debugDefaultTargetPlatformOverride = null;
    addTearDown(controller.dispose);
    await tester.pumpWidget(
      MediaQuery(
        data: const MediaQueryData(disableAnimations: true),
        child: _scrollFixture(controller),
      ),
    );

    await _sendWheel(tester, 20);

    expect(controller.offset, closeTo(20, 0.01));
  });

  testWidgets('mobile pointer scrolling keeps Flutter native behavior',
      (tester) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.android;
    final controller = QjScrollController();
    debugDefaultTargetPlatformOverride = null;
    addTearDown(controller.dispose);
    await tester.pumpWidget(_scrollFixture(controller));

    await _sendWheel(tester, 20);

    expect(controller.offset, closeTo(20, 0.01));
  });
}

Widget _scrollFixture(ScrollController controller) => Directionality(
      textDirection: TextDirection.ltr,
      child: SizedBox(
        width: 320,
        height: 240,
        child: ListView.builder(
          controller: controller,
          itemExtent: 60,
          itemCount: 20,
          itemBuilder: (_, index) => Text('row $index'),
        ),
      ),
    );

Future<void> _sendWheel(WidgetTester tester, double delta) =>
    tester.sendEventToBinding(
      PointerScrollEvent(
        kind: PointerDeviceKind.mouse,
        position: tester.getCenter(find.byType(ListView)),
        scrollDelta: Offset(0, delta),
      ),
    );

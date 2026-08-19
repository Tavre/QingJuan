import 'package:fluent_ui/fluent_ui.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:qingjuan/app/app_theme.dart';
import 'package:qingjuan/shared/mobile_sheet.dart';

void main() {
  testWidgets('mobile sheet opens from the bottom with full-width actions',
      (tester) async {
    await tester.pumpWidget(
      FluentApp(
        theme: buildQingJuanTheme(
          Brightness.light,
          platform: TargetPlatform.android,
        ),
        home: MediaQuery(
          data: const MediaQueryData(size: Size(390, 844)),
          child: Builder(
            builder: (context) => Center(
              child: Button(
                key: const ValueKey('open-mobile-sheet'),
                onPressed: () => showMobileSheet<void>(
                  context: context,
                  builder: (dialogContext) => MobileSheet(
                    title: '添加书籍',
                    subtitle: '网页地址或本地文件',
                    onClose: () => Navigator.pop(dialogContext),
                    actions: <Widget>[
                      Button(
                        onPressed: () => Navigator.pop(dialogContext),
                        child: const Text('取消'),
                      ),
                      FilledButton(
                        onPressed: () => Navigator.pop(dialogContext),
                        child: const Text('添加'),
                      ),
                    ],
                    child: const Padding(
                      padding: EdgeInsets.all(18),
                      child: Text('面板内容'),
                    ),
                  ),
                ),
                child: const Text('打开'),
              ),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.byKey(const ValueKey('open-mobile-sheet')));
    await tester.pumpAndSettle();

    expect(find.byType(ContentDialog), findsNothing);
    expect(find.text('添加书籍'), findsOneWidget);
    final surface = find.byKey(const ValueKey('mobile-sheet-surface'));
    expect(surface, findsOneWidget);
    final logicalViewHeight =
        tester.view.physicalSize.height / tester.view.devicePixelRatio;
    expect(
      tester.getBottomLeft(surface).dy,
      closeTo(logicalViewHeight - 10, 1),
    );
    expect(tester.takeException(), isNull);
  });
}

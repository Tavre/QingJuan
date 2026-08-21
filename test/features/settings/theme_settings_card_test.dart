import 'package:fluent_ui/fluent_ui.dart';
import 'package:flutter/material.dart' show Icons;
import 'package:flutter_test/flutter_test.dart';
import 'package:qingjuan/app/app_state.dart';
import 'package:qingjuan/features/settings/widgets/theme_settings_card.dart';
import 'package:qingjuan/shared/responsive.dart';

void main() {
  testWidgets(
    'mobile theme choices keep the system label visible and use Material icons',
    (tester) async {
      await tester.binding.setSurfaceSize(const Size(320, 640));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      AppThemeMode? selectedMode;
      await tester.pumpWidget(
        FluentApp(
          home: MediaQuery(
            data: const MediaQueryData(
              size: Size(320, 640),
              textScaler: TextScaler.linear(1.5),
            ),
            child: UiPlatformScope(
              platform: TargetPlatform.android,
              child: Padding(
                padding: const EdgeInsets.all(26),
                child: ThemeSettingsCard(
                  themeMode: AppThemeMode.system,
                  onChanged: (mode) => selectedMode = mode,
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      final systemChoice = find.byKey(
        const ValueKey<String>('theme-mode-system'),
      );
      final systemLabel = find.descendant(
        of: systemChoice,
        matching: find.text('跟随系统'),
      );

      expect(systemChoice, findsOneWidget);
      expect(systemLabel, findsOneWidget);
      expect(find.byIcon(Icons.brightness_auto_rounded), findsOneWidget);
      expect(find.byIcon(Icons.light_mode_rounded), findsOneWidget);
      expect(find.byIcon(Icons.dark_mode_rounded), findsOneWidget);
      expect(find.byIcon(FluentIcons.system), findsNothing);
      expect(find.byIcon(FluentIcons.brightness), findsNothing);
      expect(find.byIcon(FluentIcons.clear_night), findsNothing);
      expect(tester.takeException(), isNull);

      final choiceRect = tester.getRect(systemChoice);
      final labelRect = tester.getRect(systemLabel);
      expect(labelRect.left, greaterThanOrEqualTo(choiceRect.left));
      expect(labelRect.right, lessThanOrEqualTo(choiceRect.right));

      await tester.tap(
        find.byKey(const ValueKey<String>('theme-mode-dark')),
      );
      await tester.pump(const Duration(milliseconds: 150));
      expect(selectedMode, AppThemeMode.dark);
    },
  );

  testWidgets('desktop theme choice keeps the desktop system icon',
      (tester) async {
    await tester.pumpWidget(
      FluentApp(
        home: UiPlatformScope(
          platform: TargetPlatform.windows,
          child: ThemeSettingsCard(
            themeMode: AppThemeMode.system,
            onChanged: (_) {},
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byIcon(FluentIcons.system), findsOneWidget);
    expect(find.byIcon(FluentIcons.brightness), findsOneWidget);
    expect(find.byIcon(FluentIcons.clear_night), findsOneWidget);
    expect(find.byIcon(Icons.brightness_auto_rounded), findsNothing);
  });
}

import 'package:fluent_ui/fluent_ui.dart';

import '../../../app/app_state.dart';
import '../../../shared/app_surface.dart';
import '../../../shared/responsive.dart';
import 'settings_section_card.dart';

class ThemeSettingsCard extends StatelessWidget {
  const ThemeSettingsCard({
    required this.themeMode,
    required this.onChanged,
    super.key,
  });

  final AppThemeMode themeMode;
  final ValueChanged<AppThemeMode> onChanged;

  @override
  Widget build(BuildContext context) {
    final platformLabel = switch (UiPlatformScope.of(context)) {
      TargetPlatform.windows => 'Windows',
      TargetPlatform.android => 'Android',
      _ => '当前设备',
    };
    return SettingsSectionCard(
      icon: FluentIcons.color,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(
            '外观模式',
            style: FluentTheme.of(context)
                .typography
                .bodyLarge
                ?.copyWith(fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 4),
          Text(
            '跟随系统可自动响应$platformLabel的浅色与深色设置。',
            style: FluentTheme.of(context).typography.caption,
          ),
          const SizedBox(height: 14),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: AppThemeMode.values.map((mode) {
              final label = switch (mode) {
                AppThemeMode.system => '跟随系统',
                AppThemeMode.light => '浅色',
                AppThemeMode.dark => '深色',
              };
              final icon = switch (mode) {
                AppThemeMode.system => FluentIcons.system,
                AppThemeMode.light => FluentIcons.brightness,
                AppThemeMode.dark => FluentIcons.clear_night,
              };
              return _ThemeModeChoice(
                key: ValueKey<String>('theme-mode-${mode.name}'),
                label: label,
                icon: icon,
                selected: themeMode == mode,
                onPressed: () => onChanged(mode),
              );
            }).toList(),
          ),
        ],
      ),
    );
  }
}

class _ThemeModeChoice extends StatelessWidget {
  const _ThemeModeChoice({
    required this.label,
    required this.icon,
    required this.selected,
    required this.onPressed,
    super.key,
  });

  final String label;
  final IconData icon;
  final bool selected;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final theme = FluentTheme.of(context);
    final accent = theme.accentColor.defaultBrushFor(theme.brightness);
    return SizedBox(
      width: 92,
      child: AppSurface(
        onPressed: onPressed,
        selected: selected,
        tone: selected ? AppSurfaceTone.accent : AppSurfaceTone.muted,
        borderRadius: 16,
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 12),
        child: Column(
          children: <Widget>[
            Icon(
              icon,
              semanticLabel: '$label外观',
              size: 20,
              color: selected ? accent : theme.resources.textFillColorSecondary,
            ),
            const SizedBox(height: 7),
            Text(
              label,
              maxLines: 1,
              style: theme.typography.caption?.copyWith(
                color: selected ? accent : null,
                fontWeight: selected ? FontWeight.w700 : null,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

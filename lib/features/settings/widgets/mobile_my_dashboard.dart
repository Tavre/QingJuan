import 'package:fluent_ui/fluent_ui.dart';
import 'package:flutter_miuix/miuix.dart' as miuix;

import '../../../shared/app_surface.dart';

class MobileMyDashboard extends StatelessWidget {
  const MobileMyDashboard({
    required this.displayName,
    required this.profileSubtitle,
    required this.roleLabel,
    required this.avatarText,
    required this.connectionLabel,
    required this.connected,
    required this.canAccessWorkspace,
    required this.bookCount,
    required this.activeTaskCount,
    required this.completedTaskCount,
    required this.backendLabel,
    required this.themeLabel,
    required this.voiceLabel,
    required this.translationLabel,
    required this.onOpenAccount,
    required this.onOpenBackend,
    required this.onOpenTheme,
    required this.onOpenVoice,
    required this.onOpenTranslation,
    required this.onOpenTasks,
    required this.onOpenAbout,
    this.inlineAccount,
    this.onOpenPlugins,
    super.key,
  });

  final String displayName;
  final String profileSubtitle;
  final String roleLabel;
  final String avatarText;
  final String connectionLabel;
  final bool connected;
  final bool canAccessWorkspace;
  final int bookCount;
  final int activeTaskCount;
  final int completedTaskCount;
  final String backendLabel;
  final String themeLabel;
  final String voiceLabel;
  final String translationLabel;
  final VoidCallback onOpenAccount;
  final VoidCallback onOpenBackend;
  final VoidCallback onOpenTheme;
  final VoidCallback onOpenVoice;
  final VoidCallback onOpenTranslation;
  final VoidCallback onOpenTasks;
  final VoidCallback onOpenAbout;
  final Widget? inlineAccount;
  final VoidCallback? onOpenPlugins;

  @override
  Widget build(BuildContext context) {
    final scale = MediaQuery.textScalerOf(context).scale(1).clamp(1.0, 1.35);
    return MediaQuery(
      data: MediaQuery.of(
        context,
      ).copyWith(textScaler: TextScaler.linear(scale)),
      child: Column(
        key: const ValueKey('mobile-my-dashboard'),
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          _ProfileCard(
            displayName: displayName,
            subtitle: profileSubtitle,
            roleLabel: roleLabel,
            avatarText: avatarText,
            connectionLabel: connectionLabel,
            connected: connected,
            onPressed: onOpenAccount,
          ),
          if (inlineAccount case final account?) ...<Widget>[
            const SizedBox(height: 18),
            KeyedSubtree(
              key: const ValueKey('my-inline-account'),
              child: account,
            ),
          ],
          const SizedBox(height: 18),
          _ReadingOverviewCard(
            canAccessWorkspace: canAccessWorkspace,
            bookCount: bookCount,
            activeTaskCount: activeTaskCount,
            completedTaskCount: completedTaskCount,
          ),
          const SizedBox(height: 18),
          _SettingsGrid(
            backendLabel: backendLabel,
            themeLabel: themeLabel,
            voiceLabel: voiceLabel,
            translationLabel: translationLabel,
            onOpenBackend: onOpenBackend,
            onOpenTheme: onOpenTheme,
            onOpenVoice: onOpenVoice,
            onOpenTranslation: onOpenTranslation,
            onOpenTasks: onOpenTasks,
            onOpenPlugins: onOpenPlugins,
            onOpenAbout: onOpenAbout,
          ),
        ],
      ),
    );
  }
}

class _ProfileCard extends StatelessWidget {
  const _ProfileCard({
    required this.displayName,
    required this.subtitle,
    required this.roleLabel,
    required this.avatarText,
    required this.connectionLabel,
    required this.connected,
    required this.onPressed,
  });

  final String displayName;
  final String subtitle;
  final String roleLabel;
  final String avatarText;
  final String connectionLabel;
  final bool connected;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final theme = FluentTheme.of(context);
    final accent = theme.accentColor.defaultBrushFor(theme.brightness);
    return AppSurface(
      key: const ValueKey('my-profile-card'),
      onPressed: onPressed,
      tone: AppSurfaceTone.standard,
      borderRadius: 24,
      padding: const EdgeInsets.all(18),
      child: Row(
        children: <Widget>[
          Container(
            width: 72,
            height: 72,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: <Color>[accent.withAlpha(230), accent.withAlpha(130)],
              ),
            ),
            child: Text(
              avatarText,
              maxLines: 1,
              style: theme.typography.title?.copyWith(
                color: const Color(0xFFFFFFFF),
                fontSize: 28,
                fontWeight: FontWeight.w800,
              ),
            ),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  displayName,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: theme.typography.title?.copyWith(
                    fontSize: 22,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 5),
                Text(
                  subtitle,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: theme.typography.caption?.copyWith(
                    height: 1.35,
                    color: theme.resources.textFillColorSecondary,
                  ),
                ),
                const SizedBox(height: 9),
                Wrap(
                  spacing: 7,
                  runSpacing: 7,
                  children: <Widget>[
                    StatusPill(roleLabel, accented: canEmphasizeRole),
                    StatusPill(
                      connectionLabel,
                      icon: connected
                          ? FluentIcons.plug_connected
                          : FluentIcons.warning,
                    ),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(width: 8),
          Icon(
            FluentIcons.chevron_right,
            size: 17,
            color: theme.resources.textFillColorSecondary,
          ),
        ],
      ),
    );
  }

  bool get canEmphasizeRole => roleLabel == '管理员' || roleLabel == '普通用户';
}

class _ReadingOverviewCard extends StatelessWidget {
  const _ReadingOverviewCard({
    required this.canAccessWorkspace,
    required this.bookCount,
    required this.activeTaskCount,
    required this.completedTaskCount,
  });

  final bool canAccessWorkspace;
  final int bookCount;
  final int activeTaskCount;
  final int completedTaskCount;

  @override
  Widget build(BuildContext context) {
    final theme = FluentTheme.of(context);
    return AppSurface(
      key: const ValueKey('my-reading-overview-card'),
      tone: AppSurfaceTone.elevated,
      borderRadius: 24,
      padding: const EdgeInsets.fromLTRB(18, 17, 18, 18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Expanded(
                child: Text(
                  '我的阅读',
                  style: theme.typography.subtitle?.copyWith(
                    fontSize: 19,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              Text(
                canAccessWorkspace ? '个人数据' : '登录后启用',
                style: theme.typography.caption?.copyWith(
                  color: theme.resources.textFillColorSecondary,
                ),
              ),
            ],
          ),
          const SizedBox(height: 20),
          Row(
            children: <Widget>[
              Expanded(
                child: _ReadingMetric(
                  value: canAccessWorkspace ? '$bookCount' : '—',
                  label: '书架',
                ),
              ),
              Expanded(
                child: _ReadingMetric(
                  value: canAccessWorkspace ? '$activeTaskCount' : '—',
                  label: '进行中',
                ),
              ),
              Expanded(
                child: _ReadingMetric(
                  value: canAccessWorkspace ? '$completedTaskCount' : '—',
                  label: '已完成',
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _ReadingMetric extends StatelessWidget {
  const _ReadingMetric({required this.value, required this.label});

  final String value;
  final String label;

  @override
  Widget build(BuildContext context) {
    final theme = FluentTheme.of(context);
    return Column(
      children: <Widget>[
        Text(
          value,
          style: theme.typography.title?.copyWith(
            fontSize: 26,
            fontWeight: FontWeight.w800,
          ),
        ),
        const SizedBox(height: 5),
        Text(
          label,
          maxLines: 1,
          style: theme.typography.caption?.copyWith(
            color: theme.resources.textFillColorSecondary,
          ),
        ),
      ],
    );
  }
}

class _SettingsGrid extends StatelessWidget {
  const _SettingsGrid({
    required this.backendLabel,
    required this.themeLabel,
    required this.voiceLabel,
    required this.translationLabel,
    required this.onOpenBackend,
    required this.onOpenTheme,
    required this.onOpenVoice,
    required this.onOpenTranslation,
    required this.onOpenTasks,
    required this.onOpenAbout,
    this.onOpenPlugins,
  });

  final String backendLabel;
  final String themeLabel;
  final String voiceLabel;
  final String translationLabel;
  final VoidCallback onOpenBackend;
  final VoidCallback onOpenTheme;
  final VoidCallback onOpenVoice;
  final VoidCallback onOpenTranslation;
  final VoidCallback onOpenTasks;
  final VoidCallback onOpenAbout;
  final VoidCallback? onOpenPlugins;

  @override
  Widget build(BuildContext context) {
    final theme = FluentTheme.of(context);
    final items = <_SettingsEntry>[
      _SettingsEntry(
        keyName: 'backend',
        icon: FluentIcons.plug_connected,
        title: '后端连接',
        subtitle: backendLabel,
        onPressed: onOpenBackend,
      ),
      _SettingsEntry(
        keyName: 'theme',
        icon: FluentIcons.color,
        title: '外观主题',
        subtitle: themeLabel,
        onPressed: onOpenTheme,
      ),
      _SettingsEntry(
        keyName: 'voice',
        icon: FluentIcons.volume3,
        title: '听书声音',
        subtitle: voiceLabel,
        onPressed: onOpenVoice,
      ),
      _SettingsEntry(
        keyName: 'translation',
        icon: FluentIcons.locale_language,
        title: '翻译服务',
        subtitle: translationLabel,
        onPressed: onOpenTranslation,
      ),
      _SettingsEntry(
        keyName: 'tasks',
        icon: FluentIcons.processing,
        title: '任务日志',
        subtitle: '查看下载、翻译进度与运行记录',
        onPressed: onOpenTasks,
      ),
      if (onOpenPlugins case final openPlugins?)
        _SettingsEntry(
          keyName: 'plugins',
          icon: FluentIcons.plug_connected,
          title: '插件配置',
          subtitle: '管理本机站点插件',
          onPressed: openPlugins,
        ),
      _SettingsEntry(
        keyName: 'about',
        icon: FluentIcons.info,
        title: '关于青卷',
        subtitle: '版本、许可与项目说明',
        onPressed: onOpenAbout,
      ),
    ];

    const primaryCount = 4;
    return Column(
      key: const ValueKey('my-settings-grid'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Padding(
          padding: const EdgeInsetsDirectional.only(start: 4, bottom: 10),
          child: Text(
            '设置与服务',
            style: theme.typography.subtitle?.copyWith(
              fontSize: 19,
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
        _SettingsGroup(entries: items.take(primaryCount).toList()),
        const SizedBox(height: 18),
        Padding(
          padding: const EdgeInsetsDirectional.only(start: 4, bottom: 10),
          child: Text(
            '任务与支持',
            style: theme.typography.subtitle?.copyWith(
              fontSize: 19,
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
        _SettingsGroup(entries: items.skip(primaryCount).toList()),
      ],
    );
  }
}

class _SettingsEntry {
  const _SettingsEntry({
    required this.keyName,
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onPressed,
  });

  final String keyName;
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onPressed;
}

class _SettingsTile extends StatelessWidget {
  const _SettingsTile({required this.entry});

  final _SettingsEntry entry;

  @override
  Widget build(BuildContext context) {
    final colors = miuix.MiuixTheme.of(context).colors;
    return miuix.MiuixBasicComponent(
      key: ValueKey<String>('my-feature-${entry.keyName}'),
      title: entry.title,
      summary: entry.subtitle,
      startAction: AccentIcon(entry.icon, size: 38),
      endActions: <Widget>[
        Icon(
          FluentIcons.chevron_right,
          size: 16,
          color: colors.onSurfaceVariantActions,
        ),
      ],
      onClick: entry.onPressed,
      onClickLabel: entry.title,
      insideMargin: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
    );
  }
}

class _SettingsGroup extends StatelessWidget {
  const _SettingsGroup({required this.entries});

  final List<_SettingsEntry> entries;

  @override
  Widget build(BuildContext context) {
    final colors = miuix.MiuixTheme.of(context).colors;
    return miuix.MiuixCard(
      cornerRadius: 20,
      colors: miuix.MiuixCardColors(
        color: colors.surfaceContainer,
        contentColor: colors.onSurfaceContainer,
      ),
      child: Column(
        children: <Widget>[
          for (var index = 0; index < entries.length; index++) ...<Widget>[
            if (index > 0)
              Padding(
                padding: const EdgeInsetsDirectional.only(start: 66),
                child: miuix.MiuixHorizontalDivider(color: colors.dividerLine),
              ),
            _SettingsTile(entry: entries[index]),
          ],
        ],
      ),
    );
  }
}

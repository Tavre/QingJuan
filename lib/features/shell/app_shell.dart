import 'dart:ui' as ui;

import 'package:fluent_ui/fluent_ui.dart';
import 'package:flutter/services.dart';

import '../../app/app_scope.dart';
import '../../app/app_state.dart';
import '../../shared/feedback_widgets.dart';
import '../../shared/page_frame.dart';
import '../../shared/responsive.dart';
import '../about/about_page.dart';
import '../library/library_page.dart';
import '../search/search_page.dart';
import '../settings/settings_page.dart';
import '../sources/sources_page.dart';
import '../tasks/tasks_page.dart';

class AppShell extends StatelessWidget {
  const AppShell({super.key});

  static const _primarySections = <AppSection>[
    AppSection.library,
    AppSection.search,
    AppSection.sources,
    AppSection.tasks,
    AppSection.settings,
  ];

  static const _backendSections = <AppSection>{
    AppSection.library,
    AppSection.search,
    AppSection.sources,
    AppSection.tasks,
  };

  Widget _page(AppState app, AppSection section) {
    if (!app.hasBackendConnection && _backendSections.contains(section)) {
      return _BackendRequiredPage(
        section: section,
        label: _label(section),
        icon: _icon(section),
        onOpenSettings: () => _selectSection(app, AppSection.settings),
      );
    }
    return switch (section) {
      AppSection.library => const LibraryPage(),
      AppSection.search => const SearchPage(),
      AppSection.sources => const SourcesPage(),
      AppSection.tasks => const TasksPage(),
      AppSection.settings => const SettingsPage(),
      AppSection.about => AboutPage(
          onBack: () => _selectSection(app, AppSection.settings),
        ),
    };
  }

  String _label(AppSection section) => switch (section) {
        AppSection.library => '书架',
        AppSection.search => '搜索',
        AppSection.sources => '书源',
        AppSection.tasks => '任务',
        AppSection.settings => '设置',
        AppSection.about => '关于',
      };

  IconData _icon(AppSection section) => switch (section) {
        AppSection.library => FluentIcons.library,
        AppSection.search => FluentIcons.search,
        AppSection.sources => FluentIcons.database,
        AppSection.tasks => FluentIcons.history,
        AppSection.settings => FluentIcons.settings,
        AppSection.about => FluentIcons.info,
      };

  void _selectSection(AppState app, AppSection section) {
    app.clearNotice();
    app.selectSection(section);
  }

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context).appState;
    return AnimatedBuilder(
      animation: app,
      builder: (context, _) {
        final theme = FluentTheme.of(context);
        final dark = theme.brightness == Brightness.dark;
        final content = windowClassOf(context) == WindowClass.compact
            ? _MobileShell(
                section: app.section,
                page: _page(app, app.section),
                primarySections: _primarySections,
                labelFor: _label,
                iconFor: _icon,
                onSelected: (section) => _selectSection(app, section),
              )
            : _TabletShell(
                section: app.section,
                pageFor: (section) => _page(app, section),
                primarySections: _primarySections,
                labelFor: _label,
                iconFor: _icon,
                onSelected: (section) => _selectSection(app, section),
              );
        return AnnotatedRegion<SystemUiOverlayStyle>(
          value: SystemUiOverlayStyle(
            statusBarColor: const Color(0x00000000),
            statusBarIconBrightness: dark ? Brightness.light : Brightness.dark,
            systemNavigationBarColor: const Color(0x00000000),
            systemNavigationBarIconBrightness:
                dark ? Brightness.light : Brightness.dark,
            systemNavigationBarDividerColor: const Color(0x00000000),
          ),
          child: ColoredBox(
            color: theme.scaffoldBackgroundColor,
            child: SafeArea(child: content),
          ),
        );
      },
    );
  }
}

class _BackendRequiredPage extends StatelessWidget {
  const _BackendRequiredPage({
    required this.section,
    required this.label,
    required this.icon,
    required this.onOpenSettings,
  });

  final AppSection section;
  final String label;
  final IconData icon;
  final VoidCallback onOpenSettings;

  @override
  Widget build(BuildContext context) {
    return PageFrame(
      key: ValueKey<String>('backend-required-${section.name}'),
      title: label,
      subtitle: '此区域的数据由 Linux 后端提供。',
      child: EmptyView(
        icon: icon,
        title: '尚未连接 Linux 后端',
        message: '导航已经可用。连接服务器后，青卷会在这里加载最新数据。',
        action: FilledButton(
          key: const ValueKey('backend-required-open-settings'),
          onPressed: onOpenSettings,
          child: const Text('前往设置'),
        ),
      ),
    );
  }
}

class _MobileShell extends StatelessWidget {
  const _MobileShell({
    required this.section,
    required this.page,
    required this.primarySections,
    required this.labelFor,
    required this.iconFor,
    required this.onSelected,
  });

  final AppSection section;
  final Widget page;
  final List<AppSection> primarySections;
  final String Function(AppSection) labelFor;
  final IconData Function(AppSection) iconFor;
  final ValueChanged<AppSection> onSelected;

  @override
  Widget build(BuildContext context) {
    final theme = FluentTheme.of(context);
    return PopScope(
      canPop: section != AppSection.about,
      onPopInvokedWithResult: (didPop, result) {
        if (!didPop) onSelected(AppSection.settings);
      },
      child: ColoredBox(
        color: theme.scaffoldBackgroundColor,
        child: Column(
          children: <Widget>[
            Expanded(
              child: TweenAnimationBuilder<double>(
                key: ValueKey<AppSection>(section),
                tween: Tween<double>(begin: 0, end: 1),
                duration: MediaQuery.disableAnimationsOf(context)
                    ? Duration.zero
                    : theme.fastAnimationDuration,
                curve: Curves.easeOutCubic,
                builder: (context, value, child) {
                  return Opacity(
                    opacity: value,
                    child: Transform.translate(
                      offset: Offset(8 * (1 - value), 0),
                      child: child,
                    ),
                  );
                },
                child: page,
              ),
            ),
            _MobileNavigationBar(
              section: section,
              sections: primarySections,
              labelFor: labelFor,
              iconFor: iconFor,
              onSelected: onSelected,
            ),
          ],
        ),
      ),
    );
  }
}

class _MobileNavigationBar extends StatelessWidget {
  const _MobileNavigationBar({
    required this.section,
    required this.sections,
    required this.labelFor,
    required this.iconFor,
    required this.onSelected,
  });

  final AppSection section;
  final List<AppSection> sections;
  final String Function(AppSection) labelFor;
  final IconData Function(AppSection) iconFor;
  final ValueChanged<AppSection> onSelected;

  @override
  Widget build(BuildContext context) {
    final theme = FluentTheme.of(context);
    final dark = theme.brightness == Brightness.dark;
    return SizedBox(
      key: const ValueKey('mobile-bottom-navigation'),
      height: 78,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(10, 5, 10, 9),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(21),
          child: BackdropFilter(
            filter: ui.ImageFilter.blur(sigmaX: 18, sigmaY: 18),
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: dark ? const Color(0xE821201D) : const Color(0xEFFFFBF4),
                borderRadius: BorderRadius.circular(21),
                border: Border.all(
                  color:
                      dark ? const Color(0x2AFFFFFF) : const Color(0xB3FFFFFF),
                ),
                boxShadow: <BoxShadow>[
                  BoxShadow(
                    color: const Color(0xFF4B3529).withAlpha(dark ? 42 : 18),
                    blurRadius: 22,
                    offset: const Offset(0, 7),
                  ),
                ],
              ),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 6),
                child: Row(
                  children: <Widget>[
                    for (final item in sections)
                      Expanded(
                        child: Semantics(
                          selected: item == section,
                          button: true,
                          label: labelFor(item),
                          child: Button(
                            key: ValueKey<String>(
                              'mobile-navigation-${item.name}',
                            ),
                            style: ButtonStyle(
                              padding: const WidgetStatePropertyAll(
                                EdgeInsets.zero,
                              ),
                              shape: WidgetStatePropertyAll(
                                RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(16),
                                ),
                              ),
                              backgroundColor: const WidgetStatePropertyAll(
                                Color(0x00000000),
                              ),
                            ),
                            onPressed: () => onSelected(item),
                            child: Column(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: <Widget>[
                                AnimatedScale(
                                  duration:
                                      MediaQuery.disableAnimationsOf(context)
                                          ? Duration.zero
                                          : theme.fastAnimationDuration,
                                  curve: Curves.easeOutBack,
                                  scale: item == section ? 1.06 : 1,
                                  child: AnimatedContainer(
                                    duration:
                                        MediaQuery.disableAnimationsOf(context)
                                            ? Duration.zero
                                            : theme.fastAnimationDuration,
                                    curve: Curves.easeOutCubic,
                                    width: 42,
                                    height: 27,
                                    alignment: Alignment.center,
                                    decoration: BoxDecoration(
                                      color: item == section
                                          ? theme.accentColor.withAlpha(
                                              dark ? 52 : 26,
                                            )
                                          : const Color(0x00000000),
                                      borderRadius: BorderRadius.circular(99),
                                    ),
                                    child: Icon(
                                      iconFor(item),
                                      size: 20,
                                      color: item == section
                                          ? theme.accentColor
                                          : theme
                                              .resources.textFillColorSecondary,
                                    ),
                                  ),
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  labelFor(item),
                                  maxLines: 1,
                                  style: theme.typography.caption?.copyWith(
                                    fontSize: 11,
                                    fontWeight: item == section
                                        ? FontWeight.w700
                                        : FontWeight.w400,
                                    color: item == section
                                        ? theme.accentColor
                                        : theme
                                            .resources.textFillColorSecondary,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _TabletShell extends StatelessWidget {
  const _TabletShell({
    required this.section,
    required this.pageFor,
    required this.primarySections,
    required this.labelFor,
    required this.iconFor,
    required this.onSelected,
  });

  final AppSection section;
  final Widget Function(AppSection) pageFor;
  final List<AppSection> primarySections;
  final String Function(AppSection) labelFor;
  final IconData Function(AppSection) iconFor;
  final ValueChanged<AppSection> onSelected;

  @override
  Widget build(BuildContext context) {
    final selectedIndex = section == AppSection.about
        ? primarySections.length
        : primarySections.indexOf(section);
    return NavigationView(
      key: const ValueKey('tablet-navigation'),
      transitionBuilder: (child, animation) =>
          SuppressPageTransition(child: child),
      appBar: const NavigationAppBar(
        automaticallyImplyLeading: false,
        title: Padding(
          padding: EdgeInsetsDirectional.only(start: 12),
          child: Text('青卷'),
        ),
      ),
      pane: NavigationPane(
        selected: selectedIndex,
        displayMode: PaneDisplayMode.open,
        onChanged: (index) {
          final next = index == primarySections.length
              ? AppSection.about
              : primarySections[index];
          onSelected(next);
        },
        header: const Text('工作区'),
        items: <NavigationPaneItem>[
          for (final item in primarySections)
            PaneItem(
              icon: Icon(iconFor(item)),
              title: Text(labelFor(item)),
              body: pageFor(item),
            ),
        ],
        footerItems: <NavigationPaneItem>[
          PaneItem(
            key: const ValueKey('about-navigation-item'),
            icon: Icon(iconFor(AppSection.about)),
            title: Text(labelFor(AppSection.about)),
            body: pageFor(AppSection.about),
          ),
        ],
      ),
    );
  }
}

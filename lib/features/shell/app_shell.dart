import 'package:fluent_ui/fluent_ui.dart';
import 'package:flutter/services.dart';
import 'package:flutter_miuix/miuix.dart' as miuix;

import '../../app/app_scope.dart';
import '../../app/app_state.dart';
import '../../shared/desktop_title_bar.dart';
import '../../shared/feedback_widgets.dart';
import '../../shared/motion.dart';
import '../../shared/mobile_miuix.dart';
import '../../shared/page_frame.dart';
import '../../shared/responsive.dart';
import '../about/about_page.dart';
import '../library/library_page.dart';
import '../search/search_page.dart';
import '../settings/settings_page.dart';
import '../sources/plugins_page.dart';
import '../sources/sources_page.dart';
import '../tasks/tasks_page.dart';

class AppShell extends StatelessWidget {
  const AppShell({super.key});

  static const _mobileSections = <AppSection>[
    AppSection.library,
    AppSection.search,
    AppSection.sources,
    AppSection.tasks,
    AppSection.settings,
  ];

  static const _desktopLocalSections = <AppSection>[
    AppSection.library,
    AppSection.search,
    AppSection.sources,
    AppSection.plugins,
    AppSection.tasks,
    AppSection.settings,
  ];

  static const _desktopRemoteSections = <AppSection>[
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
    AppSection.plugins,
    AppSection.tasks,
  };

  Widget _page(AppScope scope, AppSection section) {
    final app = scope.appState;
    if (section == AppSection.plugins && !app.clientPluginManagementAvailable) {
      return const SettingsPage();
    }
    if (!app.hasBackendConnection && _backendSections.contains(section)) {
      return _BackendRequiredPage(
        section: section,
        label: _label(section),
        icon: _icon(section),
        onOpenSettings: () => _selectSection(app, AppSection.settings),
      );
    }
    if (_backendSections.contains(section) &&
        scope.backend.multiUserEnabled &&
        !scope.auth.canAccessWorkspace) {
      return _AuthenticationRequiredPage(
        section: section,
        label: _label(section),
        icon: _icon(section),
        onOpenAccount: () => _selectSection(app, AppSection.settings),
      );
    }
    return switch (section) {
      AppSection.library => const LibraryPage(),
      AppSection.search => const SearchPage(),
      AppSection.sources => const SourcesPage(),
      AppSection.plugins => PluginsPage(
          onBack: () => _selectSection(app, AppSection.settings),
        ),
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
        AppSection.sources => '书源管理',
        AppSection.plugins => '插件配置',
        AppSection.tasks => '任务',
        AppSection.settings => '设置',
        AppSection.about => '关于',
      };

  String _mobileLabel(AppSection section) => switch (section) {
        AppSection.library => '书架',
        AppSection.search => '搜索',
        AppSection.sources => '书源',
        AppSection.plugins => '插件',
        AppSection.tasks => '任务',
        AppSection.settings => '我的',
        AppSection.about => '关于',
      };

  IconData _icon(AppSection section) => switch (section) {
        AppSection.library => FluentIcons.library,
        AppSection.search => FluentIcons.search,
        AppSection.sources => FluentIcons.database,
        AppSection.plugins => FluentIcons.plug_connected,
        AppSection.tasks => FluentIcons.history,
        AppSection.settings => FluentIcons.settings,
        AppSection.about => FluentIcons.info,
      };

  IconData _mobileIcon(AppSection section) => switch (section) {
        AppSection.settings => FluentIcons.contact,
        _ => _icon(section),
      };

  void _selectSection(AppState app, AppSection section) {
    app.clearNotice();
    app.selectSection(section);
  }

  @override
  Widget build(BuildContext context) {
    final scope = AppScope.of(context);
    final app = scope.appState;
    return AnimatedBuilder(
      animation: Listenable.merge(<Listenable>[app, scope.auth, scope.tasks]),
      builder: (context, _) {
        final theme = FluentTheme.of(context);
        final dark = theme.brightness == Brightness.dark;
        final mobile = usesMobileUi(context);
        final desktopSections = app.clientPluginManagementAvailable
            ? _desktopLocalSections
            : _desktopRemoteSections;
        final content = mobile
            ? QingJuanMiuixTheme(
                child: _MobileShell(
                  section: app.section,
                  pageFor: (section) => _page(scope, section),
                  primarySections: _mobileSections,
                  labelFor: _mobileLabel,
                  iconFor: _mobileIcon,
                  activeTaskCount: scope.tasks.activeCount,
                  onSelected: (section) => _selectSection(app, section),
                ),
              )
            : _DesktopShell(
                section: app.section,
                pageFor: (section) => _page(scope, section),
                primarySections: desktopSections,
                labelFor: _label,
                iconFor: _icon,
                onSelected: (section) => _selectSection(app, section),
              );
        if (!mobile) {
          return ColoredBox(
            color: theme.scaffoldBackgroundColor,
            child: content,
          );
        }
        return AnnotatedRegion<SystemUiOverlayStyle>(
          value: SystemUiOverlayStyle(
            statusBarColor: const Color(0x00000000),
            statusBarIconBrightness: dark ? Brightness.light : Brightness.dark,
            systemNavigationBarColor: const Color(0x00000000),
            systemNavigationBarIconBrightness:
                dark ? Brightness.light : Brightness.dark,
            systemNavigationBarDividerColor: const Color(0x00000000),
          ),
          child: content,
        );
      },
    );
  }
}

class _AuthenticationRequiredPage extends StatelessWidget {
  const _AuthenticationRequiredPage({
    required this.section,
    required this.label,
    required this.icon,
    required this.onOpenAccount,
  });

  final AppSection section;
  final String label;
  final IconData icon;
  final VoidCallback onOpenAccount;

  @override
  Widget build(BuildContext context) {
    final visibleLabel = usesMobileUi(context)
        ? switch (section) {
            AppSection.sources => '书源',
            _ => label,
          }
        : label;
    return PageFrame(
      key: ValueKey<String>('auth-required-${section.name}'),
      title: visibleLabel,
      subtitle: '登录后加载你的个人工作区。',
      child: EmptyView(
        icon: icon,
        title: '请先登录 Linux 后端',
        message: '每个用户拥有独立书架、阅读进度和任务记录。',
        action: FilledButton(
          key: const ValueKey('auth-required-open-account'),
          onPressed: onOpenAccount,
          child: const Text('前往“我的”登录'),
        ),
      ),
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
    final visibleLabel = usesMobileUi(context)
        ? switch (section) {
            AppSection.sources => '书源',
            AppSection.plugins => '站点插件',
            AppSection.settings => '我的',
            _ => label,
          }
        : label;
    return PageFrame(
      key: ValueKey<String>('backend-required-${section.name}'),
      title: visibleLabel,
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
    required this.pageFor,
    required this.primarySections,
    required this.labelFor,
    required this.iconFor,
    required this.activeTaskCount,
    required this.onSelected,
  });

  final AppSection section;
  final Widget Function(AppSection) pageFor;
  final List<AppSection> primarySections;
  final String Function(AppSection) labelFor;
  final IconData Function(AppSection) iconFor;
  final int activeTaskCount;
  final ValueChanged<AppSection> onSelected;

  @override
  Widget build(BuildContext context) {
    final colors = miuix.MiuixTheme.of(context).colors;
    final primaryIndex = primarySections.indexOf(section);
    final navigationSection = primaryIndex < 0 ? AppSection.settings : section;
    final stackIndex = primaryIndex < 0
        ? primarySections.indexOf(AppSection.settings)
        : primaryIndex;
    final primaryStack = IndexedStack(
      key: const ValueKey('mobile-primary-pages'),
      index: stackIndex,
      children: <Widget>[for (final item in primarySections) pageFor(item)],
    );
    final page = primaryIndex >= 0
        ? primaryStack
        : Stack(
            fit: StackFit.expand,
            children: <Widget>[
              Offstage(offstage: true, child: primaryStack),
              QjPageSwitcher(pageKey: section, child: pageFor(section)),
            ],
          );
    return PopScope(
      canPop: section != AppSection.about && section != AppSection.plugins,
      onPopInvokedWithResult: (didPop, result) {
        if (!didPop) onSelected(AppSection.settings);
      },
      child: miuix.MiuixScaffold(
        key: const ValueKey('mobile-miuix-scaffold'),
        containerColor: colors.background,
        bottomBar: _MobileNavigationBar(
          section: navigationSection,
          sections: primarySections,
          labelFor: labelFor,
          iconFor: iconFor,
          activeTaskCount: activeTaskCount,
          onSelected: onSelected,
        ),
        content: (padding) => Padding(padding: padding, child: page),
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
    required this.activeTaskCount,
    required this.onSelected,
  });

  final AppSection section;
  final List<AppSection> sections;
  final String Function(AppSection) labelFor;
  final IconData Function(AppSection) iconFor;
  final int activeTaskCount;
  final ValueChanged<AppSection> onSelected;

  @override
  Widget build(BuildContext context) {
    final textScaler = TextScaler.linear(
      MediaQuery.textScalerOf(context).scale(1).clamp(1.0, 1.2),
    );
    return MediaQuery(
      key: const ValueKey('mobile-bottom-navigation'),
      data: MediaQuery.of(context).copyWith(textScaler: textScaler),
      child: miuix.MiuixNavigationBar(
        showDivider: false,
        mode: miuix.MiuixNavigationBarDisplayMode.iconAndText,
        children: <Widget>[
          for (final item in sections)
            miuix.MiuixNavigationBarItem(
              key: ValueKey<String>('mobile-navigation-${item.name}'),
              selected: item == section,
              onPressed: () => onSelected(item),
              icon: Icon(iconFor(item)),
              label: labelFor(item),
              badge: item == AppSection.tasks && activeTaskCount > 0
                  ? miuix.MiuixBadge(
                      child: Text(
                        activeTaskCount > 99 ? '99+' : '$activeTaskCount',
                      ),
                    )
                  : null,
            ),
        ],
      ),
    );
  }
}

class _DesktopShell extends StatefulWidget {
  const _DesktopShell({
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
  State<_DesktopShell> createState() => _DesktopShellState();
}

class _DesktopShellState extends State<_DesktopShell> {
  static const _defaultPaneWidth = 256.0;
  static const _minimumPaneWidth = 220.0;
  static const _maximumPaneWidth = 420.0;

  double _paneWidth = _defaultPaneWidth;
  bool _paneCollapsed = false;
  bool _resizeHandleHovered = false;

  @override
  void initState() {
    super.initState();
    HardwareKeyboard.instance.addHandler(_handleKeyEvent);
  }

  @override
  void dispose() {
    HardwareKeyboard.instance.removeHandler(_handleKeyEvent);
    super.dispose();
  }

  bool _handleKeyEvent(KeyEvent event) {
    if (event is! KeyDownEvent || !HardwareKeyboard.instance.isControlPressed) {
      return false;
    }
    final sections = <AppSection>[...widget.primarySections, AppSection.about];
    for (var index = 0; index < sections.length; index++) {
      if (event.logicalKey == _shortcutKey(index) ||
          event.physicalKey == _shortcutPhysicalKey(index)) {
        widget.onSelected(sections[index]);
        return true;
      }
    }
    return false;
  }

  void _togglePane() {
    setState(() => _paneCollapsed = !_paneCollapsed);
  }

  void _resizePane(DragUpdateDetails details, double maximumWidth) {
    setState(() {
      _paneWidth = (_paneWidth + details.delta.dx)
          .clamp(_minimumPaneWidth, maximumWidth)
          .toDouble();
    });
  }

  Widget _paneToggleButton() {
    return SizedBox(
      width: 48,
      height: 40,
      child: Tooltip(
        message: _paneCollapsed ? '展开导航栏' : '收起导航栏',
        child: IconButton(
          key: const ValueKey('navigation-pane-toggle'),
          icon: const Icon(FluentIcons.global_nav_button, size: 16),
          onPressed: _togglePane,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = FluentTheme.of(context);
    final windowClass = windowClassOf(context);
    final isExpanded = windowClass == WindowClass.expanded;
    final maximumPaneWidth = (MediaQuery.sizeOf(context).width * 0.36)
        .clamp(_minimumPaneWidth, _maximumPaneWidth)
        .toDouble();
    final paneWidth =
        _paneWidth.clamp(_minimumPaneWidth, maximumPaneWidth).toDouble();
    final selectedIndex = widget.section == AppSection.about
        ? widget.primarySections.length
        : widget.primarySections.indexOf(widget.section);
    final displayMode = isExpanded && !_paneCollapsed
        ? PaneDisplayMode.open
        : PaneDisplayMode.compact;

    return Stack(
      key: const ValueKey('desktop-shell'),
      children: <Widget>[
        NavigationPaneTheme.merge(
          data: NavigationPaneThemeData(
            animationDuration: QjMotion.duration(context, QjMotionSpeed.fast),
            animationCurve: QjMotion.enterCurve,
          ),
          child: NavigationView(
            key: const ValueKey('tablet-navigation'),
            transitionBuilder: (child, _) => QjPageSwitcher(
              pageKey: child.key ?? widget.section,
              beginOffset: const Offset(0.018, 0),
              child: child,
            ),
            appBar: NavigationAppBar(
              automaticallyImplyLeading: false,
              height: desktopTitleBarHeight,
              backgroundColor: theme.micaBackgroundColor,
              title: const DesktopTitleBar(),
            ),
            pane: NavigationPane(
              selected: selectedIndex,
              displayMode: displayMode,
              onChanged: (index) {
                final next = index == widget.primarySections.length
                    ? AppSection.about
                    : widget.primarySections[index];
                widget.onSelected(next);
              },
              size: NavigationPaneSize(
                openWidth: paneWidth,
                openMinWidth: _minimumPaneWidth,
                openMaxWidth: maximumPaneWidth,
              ),
              menuButton: isExpanded ? _paneToggleButton() : null,
              header: Text(
                '工作区',
                style: theme.typography.caption?.copyWith(
                  color: theme.resources.textFillColorSecondary,
                  fontWeight: FontWeight.w600,
                ),
              ),
              items: <NavigationPaneItem>[
                for (final item in widget.primarySections)
                  PaneItem(
                    icon: Icon(widget.iconFor(item)),
                    title: Text(widget.labelFor(item)),
                    body: widget.pageFor(item),
                  ),
              ],
              footerItems: <NavigationPaneItem>[
                PaneItem(
                  key: const ValueKey('about-navigation-item'),
                  icon: Icon(widget.iconFor(AppSection.about)),
                  title: Text(widget.labelFor(AppSection.about)),
                  body: widget.pageFor(AppSection.about),
                ),
              ],
            ),
          ),
        ),
        if (isExpanded && !_paneCollapsed)
          PositionedDirectional(
            start: paneWidth - 4,
            top: desktopTitleBarHeight,
            bottom: 0,
            width: 8,
            child: Semantics(
              label: '调整导航栏宽度',
              child: MouseRegion(
                key: const ValueKey('navigation-pane-resizer'),
                cursor: SystemMouseCursors.resizeColumn,
                onEnter: (_) => setState(() => _resizeHandleHovered = true),
                onExit: (_) => setState(() => _resizeHandleHovered = false),
                child: GestureDetector(
                  behavior: HitTestBehavior.translucent,
                  onHorizontalDragUpdate: (details) =>
                      _resizePane(details, maximumPaneWidth),
                  child: Center(
                    child: AnimatedContainer(
                      duration: QjMotion.duration(
                        context,
                        QjMotionSpeed.faster,
                      ),
                      curve: QjMotion.enterCurve,
                      width: _resizeHandleHovered ? 2 : 1,
                      color: _resizeHandleHovered
                          ? theme.accentColor
                          : theme.resources.cardStrokeColorDefault,
                    ),
                  ),
                ),
              ),
            ),
          ),
      ],
    );
  }

  LogicalKeyboardKey _shortcutKey(int index) => switch (index) {
        0 => LogicalKeyboardKey.digit1,
        1 => LogicalKeyboardKey.digit2,
        2 => LogicalKeyboardKey.digit3,
        3 => LogicalKeyboardKey.digit4,
        4 => LogicalKeyboardKey.digit5,
        5 => LogicalKeyboardKey.digit6,
        _ => LogicalKeyboardKey.digit7,
      };

  PhysicalKeyboardKey _shortcutPhysicalKey(int index) => switch (index) {
        0 => PhysicalKeyboardKey.digit1,
        1 => PhysicalKeyboardKey.digit2,
        2 => PhysicalKeyboardKey.digit3,
        3 => PhysicalKeyboardKey.digit4,
        4 => PhysicalKeyboardKey.digit5,
        5 => PhysicalKeyboardKey.digit6,
        _ => PhysicalKeyboardKey.digit7,
      };
}

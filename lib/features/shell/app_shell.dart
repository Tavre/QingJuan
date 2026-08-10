import 'package:fluent_ui/fluent_ui.dart';
import 'package:flutter/services.dart';

import '../../app/app_scope.dart';
import '../../app/app_state.dart';
import '../../shared/desktop_title_bar.dart';
import '../../shared/responsive.dart';
import '../about/about_page.dart';
import '../library/library_page.dart';
import '../search/search_page.dart';
import '../settings/settings_page.dart';
import '../sources/sources_page.dart';
import '../tasks/tasks_page.dart';

class AppShell extends StatefulWidget {
  const AppShell({super.key});

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  static const _defaultPaneWidth = 256.0;
  static const _minimumPaneWidth = 220.0;
  static const _maximumPaneWidth = 420.0;

  static const _sections = <AppSection>[
    AppSection.library,
    AppSection.search,
    AppSection.sources,
    AppSection.tasks,
    AppSection.settings,
    AppSection.about,
  ];

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
    int? index;
    for (var candidate = 0; candidate < _sections.length; candidate++) {
      if (event.logicalKey == _shortcutKey(candidate) ||
          event.physicalKey == _shortcutPhysicalKey(candidate)) {
        index = candidate;
        break;
      }
    }
    if (index == null) return false;
    AppScope.of(context).appState.selectSection(_sections[index]);
    return true;
  }

  Widget _page(AppSection section) => switch (section) {
        AppSection.library => const LibraryPage(),
        AppSection.search => const SearchPage(),
        AppSection.sources => const SourcesPage(),
        AppSection.tasks => const TasksPage(),
        AppSection.settings => const SettingsPage(),
        AppSection.about => const AboutPage(),
      };

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
    final app = AppScope.of(context).appState;
    return AnimatedBuilder(
      animation: app,
      builder: (context, _) {
        final theme = FluentTheme.of(context);
        final windowClass = windowClassOf(context);
        final isExpanded = windowClass == WindowClass.expanded;
        final maximumPaneWidth = (MediaQuery.sizeOf(context).width * 0.36)
            .clamp(_minimumPaneWidth, _maximumPaneWidth)
            .toDouble();
        final paneWidth =
            _paneWidth.clamp(_minimumPaneWidth, maximumPaneWidth).toDouble();
        final selectedIndex = _sections.indexOf(app.section);
        final displayMode = isExpanded && !_paneCollapsed
            ? PaneDisplayMode.open
            : PaneDisplayMode.compact;

        return Stack(
          children: <Widget>[
            NavigationView(
              appBar: NavigationAppBar(
                automaticallyImplyLeading: false,
                height: desktopTitleBarHeight,
                backgroundColor: theme.micaBackgroundColor,
                title: const DesktopTitleBar(),
              ),
              pane: NavigationPane(
                selected: selectedIndex,
                onChanged: (index) => app.selectSection(_sections[index]),
                displayMode: displayMode,
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
                  for (final section
                      in _sections.where((item) => item != AppSection.about))
                    PaneItem(
                      icon: Icon(_icon(section)),
                      title: Text(_label(section)),
                      body: _page(section),
                    ),
                ],
                footerItems: <NavigationPaneItem>[
                  PaneItem(
                    key: const ValueKey('about-navigation-item'),
                    icon: Icon(_icon(AppSection.about)),
                    title: Text(_label(AppSection.about)),
                    body: _page(AppSection.about),
                  ),
                ],
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
                        child: Container(
                          width: _resizeHandleHovered ? 2 : 1,
                          color: _resizeHandleHovered
                              ? FluentTheme.of(context).accentColor
                              : FluentTheme.of(context)
                                  .resources
                                  .cardStrokeColorDefault,
                        ),
                      ),
                    ),
                  ),
                ),
              ),
          ],
        );
      },
    );
  }

  LogicalKeyboardKey _shortcutKey(int index) => switch (index) {
        0 => LogicalKeyboardKey.digit1,
        1 => LogicalKeyboardKey.digit2,
        2 => LogicalKeyboardKey.digit3,
        3 => LogicalKeyboardKey.digit4,
        4 => LogicalKeyboardKey.digit5,
        _ => LogicalKeyboardKey.digit6,
      };

  PhysicalKeyboardKey _shortcutPhysicalKey(int index) => switch (index) {
        0 => PhysicalKeyboardKey.digit1,
        1 => PhysicalKeyboardKey.digit2,
        2 => PhysicalKeyboardKey.digit3,
        3 => PhysicalKeyboardKey.digit4,
        4 => PhysicalKeyboardKey.digit5,
        _ => PhysicalKeyboardKey.digit6,
      };
}

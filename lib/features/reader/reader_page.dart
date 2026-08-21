import 'dart:async';
import 'dart:math' as math;

import 'package:fluent_ui/fluent_ui.dart';
import 'package:flutter/services.dart';

import '../../app/app_scope.dart';
import '../../app/app_state.dart';
import '../../core/models/book.dart';
import '../../shared/feedback_widgets.dart';
import '../../shared/motion.dart';
import '../../shared/responsive.dart';
import '../../shared/smooth_scroll.dart';
import '../audiobook/audiobook_page.dart';
import 'reader_controls.dart';
import 'reader_hardware_key_service.dart';
import 'reader_pagination.dart';
import 'reader_theme.dart';

class ReaderPage extends StatefulWidget {
  const ReaderPage({
    required this.detail,
    required this.initialChapterIndex,
    super.key,
  });

  final BookDetail detail;
  final int initialChapterIndex;

  @override
  State<ReaderPage> createState() => _ReaderPageState();
}

class _ReaderPageState extends State<ReaderPage> with WidgetsBindingObserver {
  static const Duration _visibleChapterCheckInterval =
      Duration(milliseconds: 80);
  static const Duration _progressSaveDelay = Duration(milliseconds: 420);
  static const int _hardwareKeyAnimationMilliseconds = 170;
  static const MethodChannel _readerPlatformChannel =
      MethodChannel('qingjuan/reader');

  final ScrollController _scrollController = QjScrollController(
    debugLabel: 'reader-content',
  );
  final ReaderHardwareKeyService _hardwareKeys = ReaderHardwareKeyService();
  final Map<String, ChapterContent> _chapterCache = <String, ChapterContent>{};
  final Map<String, Future<ChapterContent>> _inflight =
      <String, Future<ChapterContent>>{};
  final Map<ChapterContent, List<String>> _paragraphCache =
      Map<ChapterContent, List<String>>.identity();
  final Map<int, GlobalKey> _chapterHeadingKeys = <int, GlobalKey>{};

  late AppScope _scope;
  late Brightness _hostBrightness;
  PageController _pageController = PageController();
  ChapterContent? _content;
  late int _chapterIndex;
  late ReaderFlowMode _flowMode;
  late ReaderPaletteMode _paletteMode;
  late ReaderPageAnimation _pageAnimation;
  late ReaderLineSpacing _lineSpacing;
  late double _fontSize;
  late bool _volumeKeyReadingEnabled;
  final List<int> _continuousChapterIndices = <int>[];
  String _mode = 'translated';
  bool _loading = true;
  bool _switchingChapter = false;
  bool _controlsVisible = true;
  bool _settingsVisible = false;
  bool _initialized = false;
  Future<void>? _continuousChapterAheadRequest;
  bool _checkingVisibleChapter = false;
  bool _mobileUi = false;
  int _loadToken = 0;
  int _systemChromeRevision = 0;
  int _pageIndex = 0;
  int _pageCount = 1;
  double? _pendingChapterSlider;
  Timer? _hideControlsTimer;
  Timer? _visibleChapterTimer;
  Timer? _progressSaveTimer;
  ChapterContent? _paginationContent;
  Size? _paginationViewport;
  double? _paginationFontSize;
  double? _paginationLineHeight;
  double? _paginationScaledFontSize;
  double? _paginationFirstPageHeight;
  TextStyle? _paginationTextStyle;
  TextDirection? _paginationTextDirection;
  Locale? _paginationLocale;
  List<String> _paginationPages = const <String>[];
  final List<ReaderHardwareKey> _pendingHardwareKeys = <ReaderHardwareKey>[];
  bool _drainingHardwareKeys = false;
  Offset? _readerPointerDown;
  String? _error;
  String? _switchError;

  int get _chapterCount => widget.detail.chapters.length;
  bool get _hasPreviousChapter => _chapterIndex > 1;
  bool get _hasNextChapter => _chapterIndex < _chapterCount;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _chapterIndex = widget.initialChapterIndex.clamp(1, _chapterCount);
    _scrollController.addListener(_handleContinuousScroll);
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && _initialized && _mobileUi) {
      unawaited(_applySystemChrome());
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _scope = AppScope.of(context);
    if (_initialized) return;
    _initialized = true;
    _mobileUi = usesMobileUi(context);
    _hostBrightness = FluentTheme.of(context).brightness;
    _flowMode = _scope.appState.readerFlowMode;
    _paletteMode = _scope.appState.readerPaletteMode;
    _pageAnimation = _scope.appState.readerPageAnimation;
    _lineSpacing = _scope.appState.readerLineSpacing;
    _fontSize = _scope.appState.readerFontSize;
    _volumeKeyReadingEnabled = _scope.appState.volumeKeyReadingEnabled;
    if (_mobileUi) {
      unawaited(
        _hardwareKeys.attach(
          enabled: _volumeKeyReadingEnabled,
          onKey: _handleHardwareKey,
        ),
      );
    }
    unawaited(_loadChapter(_chapterIndex, initial: true));
    if (_mobileUi) {
      _scheduleControlsHide();
      unawaited(_applySystemChrome());
    }
  }

  ReaderPalette get _palette {
    final palette = ReaderPalette.fromMode(_paletteMode);
    if (!_mobileUi) return palette;
    return palette.withAccent(
      palette.isDark ? const Color(0xFF79A8FF) : const Color(0xFF3377F6),
    );
  }

  String _cacheKey(int chapterIndex, String mode) => '$mode:$chapterIndex';

  List<String> _readerParagraphs(ChapterContent content) =>
      _paragraphCache.putIfAbsent(
        content,
        () => readerParagraphsForLayout(
          content.paragraphs,
          content.content,
        ),
      );

  Future<ChapterContent> _getChapter(
    int chapterIndex,
    String mode, {
    bool prefetch = false,
  }) {
    final key = _cacheKey(chapterIndex, mode);
    final cached = _chapterCache[key];
    if (cached != null) return Future<ChapterContent>.value(cached);
    final pending = _inflight[key];
    if (pending != null) return pending;
    final request = _scope.api
        .fetchChapter(
      widget.detail.book.id,
      chapterIndex,
      mode: mode,
      prefetch: prefetch,
    )
        .then((content) {
      _chapterCache[key] = content;
      _trimCache();
      return content;
    }).whenComplete(() {
      _inflight.remove(key);
    });
    _inflight[key] = request;
    return request;
  }

  void _trimCache() {
    const maximumCachedChapters = 10;
    if (_chapterCache.length <= maximumCachedChapters) return;
    final protected = <int>{
      _chapterIndex,
      _chapterIndex - 1,
      _chapterIndex + 1,
      ..._continuousChapterIndices,
    };
    final removable = _chapterCache.keys.where((key) {
      final index = int.tryParse(key.split(':').last);
      return index != null && !protected.contains(index);
    }).toList();
    for (final key in removable) {
      if (_chapterCache.length <= maximumCachedChapters) break;
      final removed = _chapterCache.remove(key);
      if (removed != null) _paragraphCache.remove(removed);
      _evictChapterImages(removed);
    }
  }

  Future<void> _loadChapter(
    int chapterIndex, {
    bool initial = false,
  }) async {
    if (chapterIndex < 1 || chapterIndex > _chapterCount) return;
    final loadToken = ++_loadToken;
    final firstLoad = _content == null;
    if (mounted) {
      setState(() {
        _loading = firstLoad;
        _switchingChapter = !firstLoad;
        _error = null;
        _switchError = null;
      });
    }
    try {
      final mode = _mode;
      final contentRequest = _getChapter(chapterIndex, mode);
      if (chapterIndex < _chapterCount) {
        unawaited(_prefetchChapter(chapterIndex + 1, mode));
      }
      final content = await contentRequest;
      if (!mounted || loadToken != _loadToken) return;
      final oldController = _pageController;
      _pageController = PageController();
      setState(() {
        _chapterIndex = chapterIndex;
        _content = content;
        _loading = false;
        _switchingChapter = false;
        _pageIndex = 0;
        _pageCount = 1;
        _pendingChapterSlider = null;
        _continuousChapterIndices
          ..clear()
          ..add(chapterIndex);
        _chapterHeadingKeys.clear();
      });
      WidgetsBinding.instance.addPostFrameCallback((_) {
        oldController.dispose();
        if ((!_mobileUi || _flowMode == ReaderFlowMode.continuous) &&
            _scrollController.hasClients) {
          _scrollController.jumpTo(0);
        }
      });
      if (chapterIndex > 1) {
        unawaited(_prefetchChapter(chapterIndex - 1, mode));
      }
      if (_flowMode == ReaderFlowMode.continuous) {
        unawaited(_ensureContinuousChapterAhead());
      }
    } catch (error) {
      if (!mounted || loadToken != _loadToken) return;
      setState(() {
        _loading = false;
        _switchingChapter = false;
        if (_content == null || initial) {
          _error = '$error';
        } else {
          _switchError = '$error';
        }
      });
    }
  }

  Future<void> _prefetchAdjacent(int chapterIndex) async {
    final mode = _mode;
    final requests = <Future<void>>[];
    if (chapterIndex < _chapterCount) {
      requests.add(_prefetchChapter(chapterIndex + 1, mode));
    }
    if (chapterIndex > 1) {
      requests.add(_prefetchChapter(chapterIndex - 1, mode));
    }
    await Future.wait(requests);
  }

  Future<void> _prefetchChapter(int chapterIndex, String mode) async {
    try {
      await _getChapter(chapterIndex, mode, prefetch: true);
    } catch (_) {
      // 预取失败不覆盖当前正文；真正切章时会再次给出可重试错误。
    }
  }

  Future<void> _ensureContinuousChapterAhead() async {
    if (_flowMode != ReaderFlowMode.continuous ||
        _continuousChapterIndices.isEmpty) {
      return;
    }
    final pending = _continuousChapterAheadRequest;
    if (pending != null) {
      await pending;
      return;
    }
    final next = _continuousChapterIndices.last + 1;
    if (next > _chapterCount) return;
    final mode = _mode;
    final request = () async {
      try {
        await _getChapter(next, mode);
        if (!mounted ||
            _flowMode != ReaderFlowMode.continuous ||
            mode != _mode ||
            _continuousChapterIndices.contains(next) ||
            _continuousChapterIndices.last + 1 != next) {
          return;
        }
        setState(() => _continuousChapterIndices.add(next));
      } catch (_) {
        // 到达章末时仍可通过底栏重试，预取失败不插入错误整页。
      }
    }();
    _continuousChapterAheadRequest = request;
    try {
      await request;
    } finally {
      if (identical(_continuousChapterAheadRequest, request)) {
        _continuousChapterAheadRequest = null;
      }
    }
  }

  Future<void> _saveProgress({
    int? chapterIndex,
    double? ratio,
  }) async {
    final targetChapter = chapterIndex ?? _chapterIndex;
    final targetRatio = ratio ?? _currentProgressRatio();
    try {
      await _scope.api.saveProgress(
        widget.detail.book.id,
        targetChapter,
        targetRatio,
      );
    } catch (_) {
      // 阅读进度采用尽力保存，不阻断翻页、切章或退出。
    }
  }

  void _scheduleProgressSave() {
    _progressSaveTimer?.cancel();
    _progressSaveTimer = Timer(_progressSaveDelay, () {
      _progressSaveTimer = null;
      if (mounted) unawaited(_saveProgress());
    });
  }

  void _cancelScheduledProgressSave() {
    _progressSaveTimer?.cancel();
    _progressSaveTimer = null;
  }

  double _currentProgressRatio() {
    if (!_mobileUi && _scrollController.hasClients) {
      final max = _scrollController.position.maxScrollExtent;
      return max <= 0 ? 0 : (_scrollController.offset / max).clamp(0.0, 1.0);
    }
    if (_flowMode == ReaderFlowMode.paged) {
      return _pageCount <= 1
          ? 0
          : (_pageIndex / (_pageCount - 1)).clamp(0.0, 1.0);
    }
    final currentContext = _chapterHeadingKeys[_chapterIndex]?.currentContext;
    if (currentContext == null) return 0;
    final currentBox = currentContext.findRenderObject() as RenderBox?;
    final nextBox = _chapterHeadingKeys[_chapterIndex + 1]
        ?.currentContext
        ?.findRenderObject() as RenderBox?;
    if (currentBox == null || nextBox == null) return 0;
    final currentY = currentBox.localToGlobal(Offset.zero).dy;
    final nextY = nextBox.localToGlobal(Offset.zero).dy;
    if (nextY <= currentY) return 0;
    return ((72 - currentY) / (nextY - currentY)).clamp(0.0, 1.0);
  }

  Future<void> _moveChapter(int delta) async {
    final next = _chapterIndex + delta;
    if (next < 1 || next > _chapterCount || _switchingChapter) return;
    final previous = _chapterIndex;
    _cancelScheduledProgressSave();
    unawaited(_saveProgress(chapterIndex: previous));
    if (_flowMode == ReaderFlowMode.continuous &&
        _continuousChapterIndices.contains(next)) {
      final targetContext = _chapterHeadingKeys[next]?.currentContext;
      if (targetContext != null) {
        await Scrollable.ensureVisible(
          targetContext,
          duration: _motionDuration(220),
          curve: QjMotion.enterCurve,
          alignment: 0.02,
        );
        return;
      }
    }
    await _loadChapter(next);
  }

  Future<void> _jumpToChapter(int chapterIndex) async {
    if (chapterIndex == _chapterIndex) {
      if (_flowMode == ReaderFlowMode.continuous &&
          _scrollController.hasClients) {
        await _moveScrollTo(0, milliseconds: 180);
      }
      return;
    }
    _cancelScheduledProgressSave();
    unawaited(_saveProgress());
    await _loadChapter(chapterIndex);
  }

  void _handleContinuousScroll() {
    if (_flowMode != ReaderFlowMode.continuous ||
        !_scrollController.hasClients) {
      return;
    }
    final position = _scrollController.position;
    if (position.extentAfter < position.viewportDimension * 1.4) {
      unawaited(_ensureContinuousChapterAhead());
    }
    if (_checkingVisibleChapter || _visibleChapterTimer != null) return;
    _visibleChapterTimer = Timer(_visibleChapterCheckInterval, () {
      _visibleChapterTimer = null;
      if (!mounted || _flowMode != ReaderFlowMode.continuous) return;
      _checkingVisibleChapter = true;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _checkingVisibleChapter = false;
        if (mounted) _updateVisibleChapter();
      });
    });
  }

  void _updateVisibleChapter() {
    if (_flowMode != ReaderFlowMode.continuous) return;
    var visible = _chapterIndex;
    for (final index in _continuousChapterIndices) {
      final context = _chapterHeadingKeys[index]?.currentContext;
      final box = context?.findRenderObject() as RenderBox?;
      if (box == null) continue;
      if (box.localToGlobal(Offset.zero).dy > 92) break;
      visible = index;
    }
    if (visible == _chapterIndex) return;
    final previous = _chapterIndex;
    setState(() {
      _chapterIndex = visible;
      _content = _chapterCache[_cacheKey(visible, _mode)] ?? _content;
    });
    unawaited(
      _saveProgress(
        chapterIndex: previous,
        ratio: visible > previous ? 1 : 0,
      ),
    );
    unawaited(_prefetchAdjacent(visible));
  }

  Future<void> _scrollByPage(
    int direction, {
    int milliseconds = 220,
  }) async {
    if (!_scrollController.hasClients || direction == 0) return;
    var position = _scrollController.position;
    final distance = position.viewportDimension * 0.84;
    final desiredTarget = _scrollController.offset + distance * direction;

    if (direction > 0 && desiredTarget > position.maxScrollExtent) {
      final previousLastChapter = _continuousChapterIndices.isEmpty
          ? null
          : _continuousChapterIndices.last;
      await _ensureContinuousChapterAhead();
      if (!mounted || !_scrollController.hasClients) return;
      final currentLastChapter = _continuousChapterIndices.isEmpty
          ? null
          : _continuousChapterIndices.last;
      if (currentLastChapter != previousLastChapter) {
        await WidgetsBinding.instance.endOfFrame;
      }
    } else if (direction < 0 &&
        desiredTarget < position.minScrollExtent &&
        _continuousChapterIndices.isNotEmpty &&
        _continuousChapterIndices.first > 1) {
      await _openPreviousContinuousChapterAtEnd(
        _continuousChapterIndices.first - 1,
      );
      return;
    }

    if (!_scrollController.hasClients) return;
    position = _scrollController.position;
    final target = (_scrollController.offset +
            position.viewportDimension * 0.84 * direction)
        .clamp(position.minScrollExtent, position.maxScrollExtent)
        .toDouble();
    await _moveScrollTo(target, milliseconds: milliseconds);
  }

  Future<void> _openPreviousContinuousChapterAtEnd(int chapterIndex) async {
    if (chapterIndex < 1 || chapterIndex > _chapterCount || _switchingChapter) {
      return;
    }
    final loadToken = ++_loadToken;
    final mode = _mode;
    final previous = _chapterIndex;
    _cancelScheduledProgressSave();
    unawaited(_saveProgress(chapterIndex: previous, ratio: 0));
    setState(() {
      _switchingChapter = true;
      _switchError = null;
    });
    try {
      final content = await _getChapter(chapterIndex, mode);
      if (!mounted ||
          loadToken != _loadToken ||
          mode != _mode ||
          _flowMode != ReaderFlowMode.continuous) {
        return;
      }
      setState(() {
        _chapterIndex = chapterIndex;
        _content = content;
        _switchingChapter = false;
        _pageIndex = 0;
        _pageCount = 1;
        _continuousChapterIndices
          ..clear()
          ..add(chapterIndex);
        _chapterHeadingKeys.clear();
      });
      await WidgetsBinding.instance.endOfFrame;
      if (!mounted || !_scrollController.hasClients) return;
      _scrollController.jumpTo(_scrollController.position.maxScrollExtent);
      if (chapterIndex > 1) {
        unawaited(_prefetchChapter(chapterIndex - 1, mode));
      }
      unawaited(_ensureContinuousChapterAhead());
      _scheduleProgressSave();
    } catch (error) {
      if (!mounted || loadToken != _loadToken) return;
      setState(() {
        _switchingChapter = false;
        _switchError = '$error';
      });
    }
  }

  Future<void> _moveScrollTo(
    double target, {
    int milliseconds = 220,
  }) async {
    if (!_scrollController.hasClients) return;
    if (QjMotion.disabled(context)) {
      _scrollController.jumpTo(target);
      return;
    }
    await _scrollController.animateTo(
      target,
      duration: Duration(milliseconds: milliseconds),
      curve: QjMotion.enterCurve,
    );
  }

  void _handleHardwareKey(ReaderHardwareKey key) {
    if (!_volumeKeyReadingEnabled || !mounted) return;
    _pendingHardwareKeys.add(key);
    if (!_drainingHardwareKeys) unawaited(_drainHardwareKeys());
  }

  Future<void> _drainHardwareKeys() async {
    _drainingHardwareKeys = true;
    try {
      while (mounted &&
          _volumeKeyReadingEnabled &&
          _pendingHardwareKeys.isNotEmpty) {
        final key = _pendingHardwareKeys.removeAt(0);
        final direction = key == ReaderHardwareKey.up ? -1 : 1;
        if (_flowMode == ReaderFlowMode.continuous) {
          await _scrollByPage(
            direction,
            milliseconds: _hardwareKeyAnimationMilliseconds,
          );
        } else {
          await _turnPageWithHardwareKey(direction);
        }
      }
    } finally {
      _drainingHardwareKeys = false;
      if (mounted &&
          _volumeKeyReadingEnabled &&
          _pendingHardwareKeys.isNotEmpty) {
        unawaited(_drainHardwareKeys());
      }
    }
  }

  Future<void> _turnPageWithHardwareKey(int direction) async {
    if (_switchingChapter || direction == 0) return;
    final target = _pageIndex + direction;
    if (target >= 0 && target < _pageCount && _pageController.hasClients) {
      await _goToPage(
        target,
        maximumMilliseconds: _hardwareKeyAnimationMilliseconds,
      );
      return;
    }
    final previousChapter = _chapterIndex;
    await _moveChapter(direction);
    if (!mounted ||
        _flowMode != ReaderFlowMode.paged ||
        _chapterIndex == previousChapter) {
      return;
    }
    // _loadChapter replaces the PageController before the rebuilt PageView has
    // attached and calculated its page count. Keep the queue paused until that
    // layout is ready, otherwise the next key mistakes the new chapter for a
    // one-page chapter and skips it.
    await WidgetsBinding.instance.endOfFrame;
  }

  Future<void> _goToPage(
    int pageIndex, {
    int? maximumMilliseconds,
  }) async {
    if (_pageController.positions.length != 1) return;
    if (_pageAnimation == ReaderPageAnimation.none ||
        QjMotion.disabled(context)) {
      _pageController.jumpToPage(pageIndex);
      return;
    }
    var duration = switch (_pageAnimation) {
      ReaderPageAnimation.cover => 300,
      ReaderPageAnimation.slide => 220,
      ReaderPageAnimation.fade => 260,
      ReaderPageAnimation.none => 0,
    };
    if (maximumMilliseconds != null) {
      duration = math.min(duration, maximumMilliseconds);
    }
    final curve = switch (_pageAnimation) {
      ReaderPageAnimation.cover => Curves.easeInOutCubic,
      ReaderPageAnimation.slide => Curves.easeOutCubic,
      ReaderPageAnimation.fade => Curves.easeInOut,
      ReaderPageAnimation.none => Curves.linear,
    };
    await _pageController.animateToPage(
      pageIndex,
      duration: Duration(milliseconds: duration),
      curve: curve,
    );
  }

  void _previousPage() {
    if (_switchingChapter) return;
    if (_pageIndex > 0 && _pageController.hasClients) {
      unawaited(_goToPage(_pageIndex - 1));
    } else {
      unawaited(_moveChapter(-1));
    }
  }

  void _nextPage() {
    if (_switchingChapter) return;
    if (_pageIndex + 1 < _pageCount && _pageController.hasClients) {
      unawaited(_goToPage(_pageIndex + 1));
    } else {
      unawaited(_moveChapter(1));
    }
  }

  void _handleReaderTap(Offset localPosition, double width) {
    if (_flowMode == ReaderFlowMode.paged && !_controlsVisible) {
      if (localPosition.dx < width * 0.25) {
        _previousPage();
        return;
      }
      if (localPosition.dx > width * 0.75) {
        _nextPage();
        return;
      }
    }
    _setControlsVisible(!_controlsVisible);
  }

  void _handleReaderPointerDown(PointerDownEvent event) {
    _readerPointerDown = event.localPosition;
  }

  void _handleReaderPointerUp(PointerUpEvent event, double width) {
    final pointerDown = _readerPointerDown;
    _readerPointerDown = null;
    if (pointerDown == null ||
        (event.localPosition - pointerDown).distance > 12) {
      return;
    }
    _handleReaderTap(event.localPosition, width);
  }

  Duration _motionDuration(
    int milliseconds, {
    BuildContext? targetContext,
  }) {
    final mediaContext = targetContext ?? context;
    return QjMotion.resolve(
      mediaContext,
      Duration(milliseconds: milliseconds),
    );
  }

  Future<void> _setNativeReaderSystemUi(bool enabled) async {
    try {
      // Color.value is required for the Flutter 3.24 release toolchain.
      // ignore: deprecated_member_use
      final backgroundColor = _palette.background.value;
      await _readerPlatformChannel.invokeMethod<void>(
        'setReaderSystemUi',
        <String, Object>{
          'enabled': enabled,
          'backgroundColor': backgroundColor,
        },
      );
    } on MissingPluginException {
      // 非 Android 平台和 Widget 测试没有原生阅读窗口通道。
    } on PlatformException {
      // 系统栏增强失败不能阻断正文阅读。
    }
  }

  Future<void> _applySystemChrome() async {
    if (!_mobileUi) return;
    final revision = ++_systemChromeRevision;
    final palette = _palette;
    await SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
    if (revision != _systemChromeRevision) return;
    SystemChrome.setSystemUIOverlayStyle(
      SystemUiOverlayStyle(
        statusBarColor: palette.background,
        statusBarIconBrightness:
            palette.isDark ? Brightness.light : Brightness.dark,
        systemNavigationBarColor: palette.background,
        systemNavigationBarIconBrightness:
            palette.isDark ? Brightness.light : Brightness.dark,
        systemStatusBarContrastEnforced: false,
        systemNavigationBarContrastEnforced: false,
      ),
    );
    await _setNativeReaderSystemUi(true);
  }

  Future<void> _restoreHostSystemChrome() async {
    if (!_mobileUi) return;
    final revision = ++_systemChromeRevision;
    await _setNativeReaderSystemUi(false);
    if (revision != _systemChromeRevision) return;
    await SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
    if (revision != _systemChromeRevision) return;
    SystemChrome.setSystemUIOverlayStyle(
      SystemUiOverlayStyle(
        statusBarColor: const Color(0x00000000),
        statusBarIconBrightness: _hostBrightness == Brightness.dark
            ? Brightness.light
            : Brightness.dark,
        systemNavigationBarColor: const Color(0x00000000),
        systemNavigationBarIconBrightness: _hostBrightness == Brightness.dark
            ? Brightness.light
            : Brightness.dark,
      ),
    );
  }

  void _setControlsVisible(bool value) {
    if (!mounted) return;
    setState(() {
      _controlsVisible = value;
      if (!value) _settingsVisible = false;
    });
    unawaited(_applySystemChrome());
    if (value) {
      _scheduleControlsHide();
    } else {
      _hideControlsTimer?.cancel();
    }
  }

  void _scheduleControlsHide() {
    _hideControlsTimer?.cancel();
    if (_settingsVisible) return;
    _hideControlsTimer = Timer(const Duration(seconds: 4), () {
      if (mounted && !_settingsVisible) _setControlsVisible(false);
    });
  }

  void _toggleSettings() {
    setState(() => _settingsVisible = !_settingsVisible);
    if (_settingsVisible) {
      _hideControlsTimer?.cancel();
    } else {
      _scheduleControlsHide();
    }
  }

  void _setPaletteMode(ReaderPaletteMode value) {
    if (_paletteMode == value) return;
    setState(() => _paletteMode = value);
    unawaited(_applySystemChrome());
    unawaited(_scope.appState.setReaderPaletteMode(value));
  }

  void _toggleNightPalette() {
    _setPaletteMode(
      _paletteMode == ReaderPaletteMode.night
          ? ReaderPaletteMode.parchment
          : ReaderPaletteMode.night,
    );
  }

  void _setPageAnimation(ReaderPageAnimation value) {
    if (_pageAnimation == value) return;
    setState(() => _pageAnimation = value);
    unawaited(_scope.appState.setReaderPageAnimation(value));
  }

  void _setLineSpacing(ReaderLineSpacing value) {
    if (_lineSpacing == value) return;
    setState(() => _lineSpacing = value);
    unawaited(_scope.appState.setReaderLineSpacing(value));
  }

  void _changeFontSize(double delta) {
    final next = (_fontSize + delta).clamp(15, 30).toDouble();
    if (next == _fontSize) return;
    setState(() => _fontSize = next);
    unawaited(_scope.appState.setReaderFontSize(next));
  }

  void _setFlowMode(ReaderFlowMode value) {
    if (_flowMode == value) return;
    _pendingHardwareKeys.clear();
    _cancelScheduledProgressSave();
    unawaited(_saveProgress());
    setState(() {
      _flowMode = value;
      _pageIndex = 0;
      _continuousChapterIndices
        ..clear()
        ..add(_chapterIndex);
      _chapterHeadingKeys.clear();
    });
    unawaited(_scope.appState.setReaderFlowMode(value));
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (value == ReaderFlowMode.continuous && _scrollController.hasClients) {
        _scrollController.jumpTo(0);
        unawaited(_ensureContinuousChapterAhead());
      } else if (_pageController.hasClients) {
        _pageController.jumpToPage(0);
      }
    });
  }

  Future<void> _setContentMode(String value) async {
    if (_mode == value || _switchingChapter) return;
    setState(() => _mode = value);
    await _loadChapter(_chapterIndex);
  }

  Future<void> _openAudiobook() async {
    if (widget.detail.book.kind == '漫画') return;
    _hideControlsTimer?.cancel();
    _pendingHardwareKeys.clear();
    unawaited(_hardwareKeys.setEnabled(false));
    await _restoreHostSystemChrome();
    if (!mounted) return;
    await Navigator.of(context).push<void>(
      qjPageRoute<void>(
        context: context,
        beginOffset: const Offset(0, 0.025),
        builder: (_) => AudiobookPage(
          detail: widget.detail,
          voice: _scope.appState.ttsVoice,
          style: _scope.appState.ttsSpeechStyle,
          onStyleChanged: _scope.appState.setTtsSpeechStyle,
          initialChapterIndex: _chapterIndex,
          loadChapter: (index, mode) => _getChapter(index, mode),
        ),
      ),
    );
    if (!mounted) return;
    unawaited(_applySystemChrome());
    unawaited(_hardwareKeys.setEnabled(_volumeKeyReadingEnabled));
    _scheduleControlsHide();
  }

  void _setVolumeKeyReading(bool value) {
    setState(() => _volumeKeyReadingEnabled = value);
    if (!value) _pendingHardwareKeys.clear();
    unawaited(_scope.appState.setVolumeKeyReadingEnabled(value));
    unawaited(_hardwareKeys.setEnabled(value));
  }

  Future<void> _showChapterPicker() async {
    _hideControlsTimer?.cancel();
    _pendingHardwareKeys.clear();
    unawaited(_hardwareKeys.setEnabled(false));
    if (!mounted) return;
    final palette = _palette;
    final controller = QjScrollController(
      initialScrollOffset: math.max(0, (_chapterIndex - 3) * 58).toDouble(),
      debugLabel: 'reader-chapter-list',
    );
    final selected = await showGeneralDialog<int>(
      context: context,
      barrierDismissible: true,
      barrierLabel: '关闭章节目录',
      barrierColor: palette.overlay,
      transitionDuration: _motionDuration(300),
      pageBuilder: (dialogContext, animation, secondaryAnimation) {
        final size = MediaQuery.sizeOf(dialogContext);
        return SafeArea(
          top: false,
          child: Align(
            alignment: Alignment.bottomCenter,
            child: SizedBox(
              key: const ValueKey('reader-chapter-dialog'),
              width: math.min(size.width, 620),
              height: math.min(size.height * 0.86, 760),
              child: _readerGlassSurface(
                borderRadius: const BorderRadius.vertical(
                  top: Radius.circular(28),
                ),
                child: Column(
                  children: <Widget>[
                    Padding(
                      padding: const EdgeInsets.fromLTRB(22, 18, 12, 12),
                      child: Row(
                        children: <Widget>[
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: <Widget>[
                                Text(
                                  '目录',
                                  style: TextStyle(
                                    color: palette.text,
                                    fontSize: 23,
                                    fontWeight: FontWeight.w800,
                                  ),
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  '${widget.detail.book.title} · 共 $_chapterCount 章',
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: TextStyle(
                                    color: palette.secondaryText,
                                    fontSize: 13,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          IconButton(
                            icon: Icon(
                              FluentIcons.chrome_close,
                              color: palette.secondaryText,
                              semanticLabel: '关闭章节目录',
                            ),
                            onPressed: () => Navigator.pop(dialogContext),
                          ),
                        ],
                      ),
                    ),
                    Container(height: 1, color: palette.divider),
                    Expanded(
                      child: ListView.builder(
                        controller: controller,
                        padding: const EdgeInsets.fromLTRB(12, 10, 12, 24),
                        itemExtent: 58,
                        itemCount: _chapterCount,
                        itemBuilder: (context, index) {
                          final chapter = widget.detail.chapters[index];
                          final current = chapter.index == _chapterIndex;
                          return Padding(
                            padding: const EdgeInsets.symmetric(vertical: 2),
                            child: Button(
                              key: ValueKey<String>(
                                'reader-chapter-${chapter.index}',
                              ),
                              style: ButtonStyle(
                                elevation: const WidgetStatePropertyAll(0),
                                padding: const WidgetStatePropertyAll(
                                  EdgeInsets.symmetric(horizontal: 14),
                                ),
                                foregroundColor: WidgetStatePropertyAll(
                                  current ? palette.accent : palette.text,
                                ),
                                backgroundColor: WidgetStatePropertyAll(
                                  current
                                      ? palette.accent.withAlpha(
                                          palette.isDark ? 38 : 24,
                                        )
                                      : const Color(0x00000000),
                                ),
                                shape: WidgetStatePropertyAll(
                                  RoundedRectangleBorder(
                                    borderRadius: BorderRadius.circular(14),
                                    side: const BorderSide(
                                      color: Color(0x00000000),
                                    ),
                                  ),
                                ),
                              ),
                              onPressed: () => Navigator.pop(
                                dialogContext,
                                chapter.index,
                              ),
                              child: Row(
                                children: <Widget>[
                                  SizedBox(
                                    width: 44,
                                    child: Text(
                                      '${chapter.index}',
                                      style: TextStyle(
                                        color: current
                                            ? palette.accent
                                            : palette.secondaryText,
                                        fontSize: 13,
                                        fontWeight: current
                                            ? FontWeight.w800
                                            : FontWeight.w500,
                                      ),
                                    ),
                                  ),
                                  Expanded(
                                    child: Text(
                                      chapter.title,
                                      maxLines: 1,
                                      overflow: TextOverflow.ellipsis,
                                      style: TextStyle(
                                        color: current
                                            ? palette.accent
                                            : palette.text,
                                        fontSize: 15,
                                        fontWeight: current
                                            ? FontWeight.w700
                                            : FontWeight.w500,
                                      ),
                                    ),
                                  ),
                                  if (current)
                                    Icon(
                                      FluentIcons.check_mark,
                                      size: 15,
                                      color: palette.accent,
                                    ),
                                ],
                              ),
                            ),
                          );
                        },
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        );
      },
      transitionBuilder: (context, animation, secondaryAnimation, child) {
        final position = Tween<Offset>(
          begin: const Offset(0, 0.16),
          end: Offset.zero,
        ).animate(
          CurvedAnimation(parent: animation, curve: QjMotion.enterCurve),
        );
        return FadeTransition(
          opacity: animation,
          child: SlideTransition(position: position, child: child),
        );
      },
    );
    controller.dispose();
    if (!mounted) return;
    unawaited(_hardwareKeys.setEnabled(_volumeKeyReadingEnabled));
    if (selected != null) await _jumpToChapter(selected);
    _scheduleControlsHide();
  }

  void _evictChapterImages(ChapterContent? content) {
    if (content == null || !_initialized) return;
    for (final source in content.imageSources) {
      unawaited(
        NetworkImage(
          source,
          headers: _scope.api.headersForUrl(source),
        ).evict().then<void>((_) {}),
      );
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _hideControlsTimer?.cancel();
    _visibleChapterTimer?.cancel();
    _cancelScheduledProgressSave();
    _pendingHardwareKeys.clear();
    unawaited(_saveProgress());
    unawaited(_hardwareKeys.detach());
    unawaited(_restoreHostSystemChrome());
    for (final content in _chapterCache.values) {
      _evictChapterImages(content);
    }
    _scrollController
      ..removeListener(_handleContinuousScroll)
      ..dispose();
    _pageController.dispose();
    _paragraphCache.clear();
    super.dispose();
  }

  List<_ReaderElement> _continuousElements() {
    final elements = <_ReaderElement>[];
    for (final chapterIndex in _continuousChapterIndices) {
      final content = _chapterCache[_cacheKey(chapterIndex, _mode)];
      if (content == null) continue;
      elements.add(_ReaderElement.heading(chapterIndex, content));
      final itemCount = content.imageSources.isNotEmpty
          ? content.imageSources.length
          : _readerParagraphs(content).length;
      for (var index = 0; index < itemCount; index++) {
        elements.add(_ReaderElement.content(chapterIndex, content, index));
      }
      elements.add(_ReaderElement.footer(chapterIndex, content));
    }
    return elements;
  }

  Widget _buildContinuousReader(BuildContext context) {
    final elements = _continuousElements();
    final viewPadding = MediaQuery.viewPaddingOf(context);
    return LayoutBuilder(
      builder: (context, constraints) => Listener(
        behavior: HitTestBehavior.translucent,
        onPointerDown: _handleReaderPointerDown,
        onPointerUp: (event) =>
            _handleReaderPointerUp(event, constraints.maxWidth),
        onPointerCancel: (_) => _readerPointerDown = null,
        child: ListView.builder(
          key: ValueKey<String>('reader-continuous-$_mode'),
          controller: _scrollController,
          padding: EdgeInsets.fromLTRB(
            24,
            math.max(22, viewPadding.top + 14),
            24,
            math.max(28, viewPadding.bottom + 18),
          ),
          cacheExtent: 420,
          addAutomaticKeepAlives: false,
          itemCount: elements.length,
          itemBuilder: (context, index) => Center(
            child: SizedBox(
              width:
                  elements[index].content.imageSources.isNotEmpty ? 920 : 720,
              child: _buildContinuousElement(context, elements[index]),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildContinuousElement(
    BuildContext context,
    _ReaderElement element,
  ) {
    final textColor = _readerTextColor(context);
    if (element.kind == _ReaderElementKind.heading) {
      return Padding(
        key: _chapterHeadingKeys.putIfAbsent(
          element.chapterIndex,
          GlobalKey.new,
        ),
        padding: const EdgeInsets.only(top: 8, bottom: 28),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Text(
              element.content.chapter.title,
              style: FluentTheme.of(context).typography.title?.copyWith(
                    color: textColor,
                    fontSize: 25,
                    fontWeight: FontWeight.w800,
                    height: 1.3,
                  ),
            ),
            const SizedBox(height: 10),
            Text(
              '第 ${element.chapterIndex} 章 · ${widget.detail.book.title}',
              style: FluentTheme.of(context).typography.caption?.copyWith(
                    color: _palette.secondaryText,
                  ),
            ),
          ],
        ),
      );
    }
    if (element.kind == _ReaderElementKind.footer) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 30),
        child: Row(
          children: <Widget>[
            Expanded(child: Container(height: 1, color: _palette.divider)),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 14),
              child: Text(
                element.chapterIndex < _chapterCount ? '本章完 · 继续阅读' : '全书完',
                style: FluentTheme.of(context).typography.caption?.copyWith(
                      color: _palette.secondaryText,
                    ),
              ),
            ),
            Expanded(child: Container(height: 1, color: _palette.divider)),
          ],
        ),
      );
    }
    return _buildContentItem(
      context,
      element.content,
      element.contentIndex,
      textColor,
    );
  }

  Widget _buildContentItem(
    BuildContext context,
    ChapterContent content,
    int contentIndex,
    Color textColor,
  ) {
    if (content.imageSources.isNotEmpty) {
      final translation = contentIndex < content.pageTranslations.length
          ? content.pageTranslations[contentIndex].trim()
          : '';
      final placeholderHeight =
          (MediaQuery.sizeOf(context).height * 0.72).clamp(360.0, 720.0);
      return Padding(
        padding: const EdgeInsets.only(bottom: 18),
        child: Column(
          children: <Widget>[
            Image.network(
              content.imageSources[contentIndex],
              headers:
                  _scope.api.headersForUrl(content.imageSources[contentIndex]),
              width: double.infinity,
              fit: BoxFit.contain,
              filterQuality: FilterQuality.medium,
              loadingBuilder: (context, child, progress) => progress == null
                  ? child
                  : SizedBox(
                      height: placeholderHeight,
                      child: const Center(child: ProgressRing()),
                    ),
              errorBuilder: (_, __, ___) => const InfoBar(
                title: Text('当前图片加载失败'),
                severity: InfoBarSeverity.warning,
              ),
            ),
            if (translation.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: SelectableText(
                  translation,
                  style: TextStyle(
                    color: textColor,
                    fontSize: _fontSize,
                    height: _lineSpacing.height,
                  ),
                ),
              ),
          ],
        ),
      );
    }
    final paragraphs = _readerParagraphs(content);
    return Padding(
      padding: const EdgeInsets.only(bottom: 18),
      child: SelectableText.rich(
        readerTextSpanForLayout(
          paragraphs[contentIndex],
          fontSize: _fontSize,
          textScaler: MediaQuery.textScalerOf(context),
        ),
        textAlign: TextAlign.justify,
        style: TextStyle(
          color: textColor,
          fontSize: _fontSize,
          height: _lineSpacing.height,
          letterSpacing: 0.15,
        ),
      ),
    );
  }

  Widget _applyPageEffect(int index, Widget child) {
    if (_pageAnimation == ReaderPageAnimation.slide ||
        _pageAnimation == ReaderPageAnimation.none) {
      return child;
    }
    return AnimatedBuilder(
      animation: _pageController,
      child: child,
      builder: (context, page) {
        var activePage = _pageIndex.toDouble();
        if (_pageController.positions.length == 1 &&
            _pageController.position.hasContentDimensions) {
          activePage = _pageController.page ?? activePage;
        }
        final pageDelta = (activePage - index).clamp(-1.0, 1.0).toDouble();
        final distance = pageDelta.abs();
        if (_pageAnimation == ReaderPageAnimation.fade) {
          return Opacity(
            opacity: 1 - distance * 0.72,
            child: page,
          );
        }
        return FractionalTranslation(
          translation: Offset(pageDelta * 0.035, 0),
          child: page,
        );
      },
    );
  }

  List<String> _pagesFor(
    BuildContext context,
    ChapterContent content,
    Size viewport, {
    required double firstPageHeight,
    required TextStyle style,
  }) {
    final lineHeight = _lineSpacing.height;
    final textScaler = MediaQuery.textScalerOf(context);
    final scaledFontSize = textScaler.scale(_fontSize);
    final textDirection = Directionality.of(context);
    final locale = Localizations.maybeLocaleOf(context);
    if (identical(_paginationContent, content) &&
        _paginationViewport == viewport &&
        _paginationFontSize == _fontSize &&
        _paginationLineHeight == lineHeight &&
        _paginationScaledFontSize == scaledFontSize &&
        _paginationFirstPageHeight == firstPageHeight &&
        _paginationTextStyle == style &&
        _paginationTextDirection == textDirection &&
        _paginationLocale == locale) {
      return _paginationPages;
    }
    final pages = content.imageSources.isNotEmpty
        ? List<String>.filled(content.imageSources.length, '', growable: false)
        : paginateReaderTextForLayout(
            _readerParagraphs(content).join('\n\n'),
            maxWidth: viewport.width,
            pageHeight: viewport.height,
            firstPageHeight: firstPageHeight,
            style: style,
            textScaler: textScaler,
            textDirection: textDirection,
            locale: locale,
          );
    _paginationContent = content;
    _paginationViewport = viewport;
    _paginationFontSize = _fontSize;
    _paginationLineHeight = lineHeight;
    _paginationScaledFontSize = scaledFontSize;
    _paginationFirstPageHeight = firstPageHeight;
    _paginationTextStyle = style;
    _paginationTextDirection = textDirection;
    _paginationLocale = locale;
    _paginationPages = pages;
    return pages;
  }

  Widget _buildPagedReader(BuildContext context) {
    final content = _content!;
    final textColor = _readerTextColor(context);
    final viewPadding = MediaQuery.viewPaddingOf(context);
    return LayoutBuilder(
      builder: (context, constraints) {
        final textScaler = MediaQuery.textScalerOf(context);
        final textDirection = Directionality.of(context);
        final locale = Localizations.maybeLocaleOf(context);
        final defaultTextStyle = DefaultTextStyle.of(context).style;
        final textInsets = EdgeInsets.fromLTRB(
          24,
          math.max(20, viewPadding.top + 14),
          24,
          math.max(20, viewPadding.bottom + 14),
        );
        final imageInsets = EdgeInsets.fromLTRB(
          16,
          math.max(20, viewPadding.top + 14),
          16,
          math.max(20, viewPadding.bottom + 14),
        );
        final titleStyle = defaultTextStyle.merge(
          FluentTheme.of(context).typography.title?.copyWith(
                    color: textColor,
                    fontSize: 25,
                    fontWeight: FontWeight.w800,
                    height: 1.28,
                  ) ??
              TextStyle(
                color: textColor,
                fontSize: 25,
                fontWeight: FontWeight.w800,
                height: 1.28,
              ),
        );
        final bodyStyle = defaultTextStyle.merge(
          TextStyle(
            color: textColor,
            fontSize: _fontSize,
            height: _lineSpacing.height,
            letterSpacing: 0.12,
          ),
        );
        final footerBookStyle = defaultTextStyle.merge(
          TextStyle(
            color: _palette.secondaryText.withAlpha(150),
            fontSize: 11.5,
          ),
        );
        final footerPageStyle = defaultTextStyle.merge(
          TextStyle(
            color: _palette.secondaryText.withAlpha(165),
            fontSize: 11.5,
          ),
        );
        final footerPainter = TextPainter(
          text: TextSpan(text: '1 / 1', style: footerPageStyle),
          textDirection: textDirection,
          textScaler: textScaler,
          locale: locale,
          maxLines: 1,
        )..layout();
        final pageFooterHeight = math.max(18.0, footerPainter.height);
        final textWidth = math.max(
          1.0,
          constraints.maxWidth - textInsets.horizontal,
        );
        final bodyHeight = math.max(
          1.0,
          constraints.maxHeight - textInsets.vertical - pageFooterHeight,
        );
        final titlePainter = TextPainter(
          text: TextSpan(text: content.chapter.title, style: titleStyle),
          textDirection: textDirection,
          textScaler: textScaler,
          locale: locale,
        )..layout(maxWidth: textWidth);
        final pages = _pagesFor(
          context,
          content,
          Size(textWidth, bodyHeight),
          firstPageHeight: bodyHeight - titlePainter.height - 23,
          style: bodyStyle,
        );
        _pageCount = math.max(1, pages.length);
        return Listener(
          behavior: HitTestBehavior.translucent,
          onPointerDown: _handleReaderPointerDown,
          onPointerUp: (event) =>
              _handleReaderPointerUp(event, constraints.maxWidth),
          onPointerCancel: (_) => _readerPointerDown = null,
          child: PageView.builder(
            key: ValueKey<String>(
              'reader-paged-$_chapterIndex-$_mode-${_fontSize.round()}',
            ),
            controller: _pageController,
            itemCount: pages.length + (_hasNextChapter ? 1 : 0),
            onPageChanged: (index) {
              if (index >= pages.length) {
                unawaited(_moveChapter(1));
                return;
              }
              setState(() => _pageIndex = index);
              _scheduleProgressSave();
            },
            itemBuilder: (context, index) {
              if (index >= pages.length) {
                return const Center(child: ProgressRing());
              }
              if (content.imageSources.isNotEmpty) {
                return _applyPageEffect(
                  index,
                  Padding(
                    padding: imageInsets,
                    child: _buildContentItem(
                      context,
                      content,
                      index,
                      textColor,
                    ),
                  ),
                );
              }
              return _applyPageEffect(
                index,
                Padding(
                  padding: textInsets,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      if (index == 0) ...<Widget>[
                        Text(
                          content.chapter.title,
                          style: titleStyle,
                        ),
                        const SizedBox(height: 23),
                      ],
                      Expanded(
                        child: SelectionArea(
                          child: Text.rich(
                            readerTextSpanForLayout(
                              pages[index],
                              fontSize: _fontSize,
                              textScaler: MediaQuery.textScalerOf(context),
                            ),
                            textAlign: TextAlign.justify,
                            style: bodyStyle,
                          ),
                        ),
                      ),
                      SizedBox(
                        height: pageFooterHeight,
                        child: Row(
                          children: <Widget>[
                            Expanded(
                              child: Text(
                                widget.detail.book.title,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: footerBookStyle,
                              ),
                            ),
                            Text(
                              '${index + 1} / ${pages.length}',
                              style: footerPageStyle,
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              );
            },
          ),
        );
      },
    );
  }

  Color _readerTextColor(BuildContext context) => _palette.text;

  Color _readerBackgroundColor(BuildContext context) => _palette.background;

  Widget _readerGlassSurface({
    required Widget child,
    required BorderRadius borderRadius,
  }) {
    final palette = _palette;
    return RepaintBoundary(
      child: ClipRRect(
        borderRadius: borderRadius,
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: palette.surface.withAlpha(palette.isDark ? 240 : 242),
            borderRadius: borderRadius,
            border: Border.all(
              color: palette.isDark
                  ? const Color(0xFFFFFFFF).withAlpha(24)
                  : const Color(0xFFFFFFFF).withAlpha(160),
              width: 0.8,
            ),
            boxShadow: <BoxShadow>[
              BoxShadow(
                color: const Color(0xFF000000).withAlpha(
                  palette.isDark ? 34 : 14,
                ),
                blurRadius: 18,
                offset: const Offset(0, 6),
              ),
            ],
          ),
          child: child,
        ),
      ),
    );
  }

  Widget _buildTopControls(BuildContext context) {
    final palette = _palette;
    final duration = _motionDuration(240, targetContext: context);
    return Positioned(
      top: 0,
      left: 0,
      right: 0,
      child: AnimatedOpacity(
        duration: duration,
        curve: Curves.easeOut,
        opacity: _controlsVisible ? 1 : 0,
        child: AnimatedSlide(
          key: const ValueKey('reader-top-controls'),
          duration: duration,
          curve: QjMotion.enterCurve,
          offset: _controlsVisible ? Offset.zero : const Offset(0, -0.35),
          child: IgnorePointer(
            ignoring: !_controlsVisible,
            child: SafeArea(
              bottom: false,
              minimum: const EdgeInsets.fromLTRB(10, 8, 10, 0),
              child: _readerGlassSurface(
                borderRadius: BorderRadius.circular(16),
                child: SizedBox(
                  height: 56,
                  child: Row(
                    children: <Widget>[
                      const SizedBox(width: 5),
                      Tooltip(
                        message: '返回作品详情',
                        child: IconButton(
                          key: const ValueKey('reader-back-button'),
                          icon: Icon(
                            FluentIcons.back,
                            color: palette.text,
                            semanticLabel: '返回作品详情',
                          ),
                          onPressed: () => Navigator.pop(context),
                        ),
                      ),
                      const SizedBox(width: 4),
                      Expanded(
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: <Widget>[
                            Text(
                              widget.detail.book.title,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                color: palette.text,
                                fontSize: 15.5,
                                height: 1.15,
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                            const SizedBox(height: 4),
                            Text(
                              '第 $_chapterIndex / $_chapterCount 章',
                              style: TextStyle(
                                color: palette.secondaryText,
                                fontSize: 11.5,
                                height: 1,
                              ),
                            ),
                          ],
                        ),
                      ),
                      if (_switchingChapter)
                        Padding(
                          padding: const EdgeInsets.only(right: 8),
                          child: SizedBox(
                            width: 18,
                            height: 18,
                            child: ProgressRing(
                              strokeWidth: 2.3,
                              activeColor: palette.accent,
                            ),
                          ),
                        ),
                      Tooltip(
                        message: '阅读设置',
                        child: IconButton(
                          key: const ValueKey('reader-more-button'),
                          icon: Icon(
                            FluentIcons.more,
                            color: palette.text,
                            semanticLabel: '阅读设置',
                          ),
                          onPressed: () {
                            if (!_settingsVisible) _toggleSettings();
                          },
                        ),
                      ),
                      const SizedBox(width: 5),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildBottomControls(BuildContext context) {
    final palette = _palette;
    final duration = _motionDuration(280, targetContext: context);
    return Positioned(
      left: 0,
      right: 0,
      bottom: 0,
      child: AnimatedOpacity(
        duration: duration,
        curve: Curves.easeOut,
        opacity: _controlsVisible ? 1 : 0,
        child: AnimatedSlide(
          key: const ValueKey('reader-bottom-controls'),
          duration: duration,
          curve: QjMotion.enterCurve,
          offset: _controlsVisible ? Offset.zero : const Offset(0, 0.28),
          child: IgnorePointer(
            ignoring: !_controlsVisible,
            child: SafeArea(
              top: false,
              minimum: const EdgeInsets.fromLTRB(10, 0, 10, 10),
              child: _readerGlassSurface(
                borderRadius: BorderRadius.circular(20),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    if (_switchError != null)
                      Padding(
                        padding: const EdgeInsets.fromLTRB(14, 10, 14, 0),
                        child: InfoBar(
                          title: const Text('章节切换失败'),
                          content: Text(_switchError!),
                          severity: InfoBarSeverity.warning,
                          onClose: () => setState(() => _switchError = null),
                        ),
                      ),
                    AnimatedSwitcher(
                      duration: _motionDuration(240, targetContext: context),
                      switchInCurve: QjMotion.enterCurve,
                      switchOutCurve: QjMotion.exitCurve,
                      transitionBuilder: (child, animation) {
                        final slide = Tween<Offset>(
                          begin: const Offset(0, 0.06),
                          end: Offset.zero,
                        ).animate(animation);
                        return FadeTransition(
                          opacity: animation,
                          child: SlideTransition(position: slide, child: child),
                        );
                      },
                      child: _settingsVisible
                          ? _buildSettingsPanel(context)
                          : _buildChapterNavigator(context),
                    ),
                    Padding(
                      padding: const EdgeInsets.fromLTRB(6, 2, 6, 5),
                      child: Row(
                        children: <Widget>[
                          ReaderBottomAction(
                            key: const ValueKey('reader-directory-button'),
                            icon: FluentIcons.bulleted_list,
                            label: '目录',
                            palette: palette,
                            onPressed: _showChapterPicker,
                          ),
                          ReaderBottomAction(
                            key: const ValueKey('reader-audiobook-button'),
                            icon: FluentIcons.headset,
                            label: '听书',
                            palette: palette,
                            onPressed: widget.detail.book.kind == '漫画'
                                ? null
                                : _openAudiobook,
                          ),
                          ReaderBottomAction(
                            key: const ValueKey('reader-night-button'),
                            icon: _paletteMode == ReaderPaletteMode.night
                                ? FluentIcons.sunny
                                : FluentIcons.clear_night,
                            label: _paletteMode == ReaderPaletteMode.night
                                ? '日间'
                                : '夜间',
                            palette: palette,
                            selected: _paletteMode == ReaderPaletteMode.night,
                            onPressed: _toggleNightPalette,
                          ),
                          ReaderBottomAction(
                            key: const ValueKey('reader-settings-button'),
                            icon: FluentIcons.settings,
                            label: _settingsVisible ? '收起' : '设置',
                            palette: palette,
                            selected: _settingsVisible,
                            onPressed: _toggleSettings,
                          ),
                        ],
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

  Widget _buildChapterNavigator(BuildContext context) {
    final palette = _palette;
    final theme = FluentTheme.of(context);
    return Padding(
      key: const ValueKey('reader-chapter-navigator'),
      padding: const EdgeInsets.fromLTRB(16, 10, 16, 2),
      child: Row(
        children: <Widget>[
          HyperlinkButton(
            key: const ValueKey('reader-previous-button'),
            onPressed: _hasPreviousChapter && !_switchingChapter
                ? () => _moveChapter(-1)
                : null,
            child: Text(
              '上一章',
              style: TextStyle(
                color: _hasPreviousChapter
                    ? palette.text
                    : palette.secondaryText.withAlpha(95),
                fontSize: 13,
              ),
            ),
          ),
          Expanded(
            child: FluentTheme(
              data: theme.copyWith(accentColor: palette.fluentAccent),
              child: Slider(
                key: const ValueKey('reader-chapter-slider'),
                value: _pendingChapterSlider ?? _chapterIndex.toDouble(),
                min: 1,
                max: math.max(1, _chapterCount).toDouble(),
                divisions:
                    _chapterCount > 1 ? math.min(_chapterCount - 1, 300) : null,
                onChanged: _chapterCount > 1
                    ? (value) => setState(() => _pendingChapterSlider = value)
                    : null,
                onChangeEnd: _chapterCount > 1
                    ? (value) {
                        setState(() => _pendingChapterSlider = null);
                        unawaited(_jumpToChapter(value.round()));
                      }
                    : null,
              ),
            ),
          ),
          HyperlinkButton(
            key: const ValueKey('reader-next-button'),
            onPressed: _hasNextChapter && !_switchingChapter
                ? () => _moveChapter(1)
                : null,
            child: Text(
              '下一章',
              style: TextStyle(
                color: _hasNextChapter
                    ? palette.text
                    : palette.secondaryText.withAlpha(95),
                fontSize: 13,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSettingsPanel(BuildContext context) {
    final theme = FluentTheme.of(context);
    final palette = _palette;
    final maxHeight = (MediaQuery.sizeOf(context).height * 0.52)
        .clamp(260.0, 460.0)
        .toDouble();

    Widget section(String title, Widget child) => Padding(
          padding: const EdgeInsets.only(top: 15),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(
                title,
                style: TextStyle(
                  color: palette.secondaryText,
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 0.45,
                ),
              ),
              const SizedBox(height: 9),
              child,
            ],
          ),
        );

    Widget softPanel(Widget child) => DecoratedBox(
          decoration: BoxDecoration(
            color: palette.background.withAlpha(palette.isDark ? 122 : 132),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: palette.divider.withAlpha(150)),
          ),
          child: child,
        );

    return ConstrainedBox(
      key: const ValueKey('reader-settings-panel'),
      constraints: BoxConstraints(maxHeight: maxHeight),
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(16, 15, 16, 8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Row(
              children: <Widget>[
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text(
                        '阅读偏好',
                        style: TextStyle(
                          color: palette.text,
                          fontSize: 17,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                      const SizedBox(height: 3),
                      Text(
                        '浮层设置，正文排版保持稳定',
                        style: TextStyle(
                          color: palette.secondaryText,
                          fontSize: 11.5,
                        ),
                      ),
                    ],
                  ),
                ),
                ReaderChoiceChip(
                  key: const ValueKey('reader-content-mode'),
                  label: _mode == 'translated' ? '译文' : '原文',
                  selected: _mode == 'translated',
                  compact: true,
                  palette: palette,
                  onPressed: () => unawaited(
                    _setContentMode(
                      _mode == 'translated' ? 'original' : 'translated',
                    ),
                  ),
                ),
              ],
            ),
            section(
              '字号',
              softPanel(
                Padding(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 10,
                    vertical: 8,
                  ),
                  child: Row(
                    children: <Widget>[
                      ReaderChoiceChip(
                        key: const ValueKey('reader-font-decrease'),
                        label: 'A−',
                        selected: false,
                        compact: true,
                        palette: palette,
                        onPressed: () => _changeFontSize(-1),
                      ),
                      Expanded(
                        child: AnimatedSwitcher(
                          duration: _motionDuration(
                            160,
                            targetContext: context,
                          ),
                          child: Text(
                            '${_fontSize.round()} px',
                            key: ValueKey<int>(_fontSize.round()),
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              color: palette.text,
                              fontSize: 15,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ),
                      ),
                      ReaderChoiceChip(
                        key: const ValueKey('reader-font-increase'),
                        label: 'A+',
                        selected: false,
                        compact: true,
                        palette: palette,
                        onPressed: () => _changeFontSize(1),
                      ),
                    ],
                  ),
                ),
              ),
            ),
            section(
              '纸张配色',
              Wrap(
                spacing: 12,
                runSpacing: 10,
                children: ReaderPalette.palettes
                    .map(
                      (choice) => ReaderPaletteSwatch(
                        palette: choice,
                        selected: choice.mode == _paletteMode,
                        onPressed: () => _setPaletteMode(choice.mode),
                      ),
                    )
                    .toList(),
              ),
            ),
            section(
              '阅读方式',
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: <Widget>[
                  ReaderChoiceChip(
                    key: const ValueKey('reader-mode-paged'),
                    label: '左右翻页',
                    selected: _flowMode == ReaderFlowMode.paged,
                    compact: true,
                    palette: palette,
                    onPressed: () => _setFlowMode(ReaderFlowMode.paged),
                  ),
                  ReaderChoiceChip(
                    key: const ValueKey('reader-mode-continuous'),
                    label: '上下滚动',
                    selected: _flowMode == ReaderFlowMode.continuous,
                    compact: true,
                    palette: palette,
                    onPressed: () => _setFlowMode(ReaderFlowMode.continuous),
                  ),
                ],
              ),
            ),
            section(
              '翻页动效',
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: ReaderPageAnimation.values
                    .map(
                      (animation) => ReaderChoiceChip(
                        key: ValueKey<String>(
                          'reader-animation-${animation.name}',
                        ),
                        label: animation.label,
                        selected: _flowMode == ReaderFlowMode.paged &&
                            _pageAnimation == animation,
                        compact: true,
                        palette: palette,
                        onPressed: () {
                          _setPageAnimation(animation);
                          _setFlowMode(ReaderFlowMode.paged);
                        },
                      ),
                    )
                    .toList(),
              ),
            ),
            section(
              '排版与按键',
              softPanel(
                Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Wrap(
                        spacing: 7,
                        runSpacing: 8,
                        children: ReaderLineSpacing.values
                            .map(
                              (spacing) => ReaderChoiceChip(
                                key: ValueKey<String>(
                                  'reader-spacing-${spacing.name}',
                                ),
                                label: spacing.label,
                                selected: _lineSpacing == spacing,
                                compact: true,
                                palette: palette,
                                onPressed: () => _setLineSpacing(spacing),
                              ),
                            )
                            .toList(),
                      ),
                      const SizedBox(height: 12),
                      FluentTheme(
                        data: theme.copyWith(
                          accentColor: palette.fluentAccent,
                        ),
                        child: ToggleSwitch(
                          key: const ValueKey('reader-volume-key-toggle'),
                          checked: _volumeKeyReadingEnabled,
                          onChanged: _setVolumeKeyReading,
                          content: Text(
                            '音量键滑动 / 翻页',
                            style: TextStyle(
                              color: palette.text,
                              fontSize: 13,
                            ),
                          ),
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
    );
  }

  Widget _buildDesktopReaderItem(
    BuildContext context,
    ChapterContent content,
    int index,
  ) {
    final theme = FluentTheme.of(context);
    if (index == 0) {
      return Padding(
        padding: const EdgeInsets.only(bottom: 30),
        child: Text(content.chapter.title, style: theme.typography.title),
      );
    }

    final contentIndex = index - 1;
    if (content.imageSources.isNotEmpty) {
      final translation = contentIndex < content.pageTranslations.length
          ? content.pageTranslations[contentIndex].trim()
          : '';
      final placeholderHeight =
          (MediaQuery.sizeOf(context).height * 0.72).clamp(360.0, 720.0);
      return Padding(
        padding: const EdgeInsets.only(bottom: 18),
        child: Column(
          children: <Widget>[
            Image.network(
              content.imageSources[contentIndex],
              headers:
                  _scope.api.headersForUrl(content.imageSources[contentIndex]),
              width: double.infinity,
              fit: BoxFit.contain,
              filterQuality: FilterQuality.medium,
              loadingBuilder: (context, child, progress) => progress == null
                  ? child
                  : SizedBox(
                      height: placeholderHeight,
                      child: const Center(child: ProgressRing()),
                    ),
              errorBuilder: (_, __, ___) => const InfoBar(
                title: Text('图片加载失败'),
                severity: InfoBarSeverity.warning,
              ),
            ),
            if (translation.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 10),
                child: SelectableText(
                  translation,
                  style: TextStyle(fontSize: _fontSize, height: 1.7),
                ),
              ),
          ],
        ),
      );
    }

    final paragraphs = _readerParagraphs(content);
    return Padding(
      padding: const EdgeInsets.only(bottom: 18),
      child: SelectableText.rich(
        readerTextSpanForLayout(
          paragraphs[contentIndex],
          fontSize: _fontSize,
          textScaler: MediaQuery.textScalerOf(context),
        ),
        textAlign: TextAlign.justify,
        style: TextStyle(fontSize: _fontSize, height: 1.85),
      ),
    );
  }

  Widget _buildDesktopReader(BuildContext context) {
    final theme = FluentTheme.of(context);
    return NavigationView(
      key: const ValueKey('desktop-reader-page'),
      appBar: NavigationAppBar(
        automaticallyImplyLeading: false,
        backgroundColor: theme.micaBackgroundColor,
        leading: Tooltip(
          message: '返回作品详情',
          child: IconButton(
            icon: const Icon(
              FluentIcons.back,
              semanticLabel: '返回作品详情',
            ),
            onPressed: () => Navigator.pop(context),
          ),
        ),
        title: Text(widget.detail.book.title),
        actions: Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Tooltip(
              message: '减小字号',
              child: IconButton(
                icon: const Icon(
                  FluentIcons.font_decrease,
                  semanticLabel: '减小字号',
                ),
                onPressed: () => _changeFontSize(-1),
              ),
            ),
            Tooltip(
              message: '增大字号',
              child: IconButton(
                icon: const Icon(
                  FluentIcons.font_increase,
                  semanticLabel: '增大字号',
                ),
                onPressed: () => _changeFontSize(1),
              ),
            ),
            ToggleButton(
              checked: _mode == 'original',
              onChanged: (checked) => unawaited(
                _setContentMode(checked ? 'original' : 'translated'),
              ),
              child: Text(_mode == 'original' ? '原文' : '译文'),
            ),
            const SizedBox(width: 12),
          ],
        ),
      ),
      content: Column(
        children: <Widget>[
          if (_switchError != null)
            InfoBar(
              title: const Text('章节切换失败'),
              content: Text(_switchError!),
              severity: InfoBarSeverity.warning,
            ),
          Expanded(
            child: _loading
                ? const LoadingView(label: '正在打开章节')
                : _error != null
                    ? ErrorView(
                        message: _error!,
                        onRetry: () => _loadChapter(_chapterIndex),
                      )
                    : Scrollbar(
                        controller: _scrollController,
                        child: ListView.builder(
                          key: ValueKey<String>(
                            'desktop-reader-$_chapterIndex-$_mode',
                          ),
                          controller: _scrollController,
                          padding: const EdgeInsets.fromLTRB(24, 32, 24, 72),
                          addAutomaticKeepAlives: false,
                          itemCount: 1 +
                              (_content!.imageSources.isNotEmpty
                                  ? _content!.imageSources.length
                                  : _readerParagraphs(_content!).length),
                          itemBuilder: (context, index) => Center(
                            child: SizedBox(
                              width:
                                  _content!.imageSources.isNotEmpty ? 920 : 760,
                              child: _buildDesktopReaderItem(
                                context,
                                _content!,
                                index,
                              ),
                            ),
                          ),
                        ),
                      ),
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 10),
            decoration: BoxDecoration(
              color: theme.micaBackgroundColor,
              border: Border(
                top: BorderSide(
                  color: theme.resources.cardStrokeColorDefault,
                ),
              ),
            ),
            child: Row(
              children: <Widget>[
                Button(
                  onPressed:
                      _hasPreviousChapter && !_loading && !_switchingChapter
                          ? () => _moveChapter(-1)
                          : null,
                  child: const Text('上一章'),
                ),
                Expanded(
                  child: Text(
                    '第 $_chapterIndex / $_chapterCount 章',
                    textAlign: TextAlign.center,
                  ),
                ),
                FilledButton(
                  onPressed: _hasNextChapter && !_loading && !_switchingChapter
                      ? () => _moveChapter(1)
                      : null,
                  child: const Text('下一章'),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (!usesMobileUi(context)) return _buildDesktopReader(context);
    return PopScope(
      canPop: !_settingsVisible,
      onPopInvokedWithResult: (didPop, result) {
        if (!didPop && _settingsVisible) _toggleSettings();
      },
      child: AnimatedContainer(
        key: const ValueKey('reader-mobile-surface'),
        duration: _motionDuration(260, targetContext: context),
        curve: QjMotion.enterCurve,
        color: _readerBackgroundColor(context),
        child: Stack(
          children: <Widget>[
            Positioned.fill(
              child: _loading
                  ? const LoadingView(label: '正在打开章节')
                  : _error != null
                      ? ErrorView(
                          message: _error!,
                          onRetry: () => _loadChapter(_chapterIndex),
                        )
                      : _flowMode == ReaderFlowMode.paged
                          ? _buildPagedReader(context)
                          : _buildContinuousReader(context),
            ),
            Positioned.fill(
              child: IgnorePointer(
                child: AnimatedOpacity(
                  duration: _motionDuration(220, targetContext: context),
                  opacity: _controlsVisible && _settingsVisible ? 1 : 0,
                  child: ColoredBox(
                    color: _palette.isDark
                        ? const Color(0x19000000)
                        : const Color(0x12000000),
                  ),
                ),
              ),
            ),
            _buildTopControls(context),
            _buildBottomControls(context),
          ],
        ),
      ),
    );
  }
}

enum _ReaderElementKind { heading, content, footer }

class _ReaderElement {
  const _ReaderElement._(
    this.chapterIndex,
    this.content,
    this.kind,
    this.contentIndex,
  );

  const _ReaderElement.heading(int chapterIndex, ChapterContent content)
      : this._(chapterIndex, content, _ReaderElementKind.heading, -1);

  const _ReaderElement.content(
    int chapterIndex,
    ChapterContent content,
    int contentIndex,
  ) : this._(
          chapterIndex,
          content,
          _ReaderElementKind.content,
          contentIndex,
        );

  const _ReaderElement.footer(int chapterIndex, ChapterContent content)
      : this._(chapterIndex, content, _ReaderElementKind.footer, -1);

  final int chapterIndex;
  final ChapterContent content;
  final _ReaderElementKind kind;
  final int contentIndex;
}

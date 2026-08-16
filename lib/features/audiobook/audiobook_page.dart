import 'dart:async';

import 'package:fluent_ui/fluent_ui.dart';

import '../../core/models/book.dart';
import '../../core/models/tts_speech_style.dart';
import '../../core/models/tts_voice.dart';
import '../../shared/app_surface.dart';
import '../../shared/feedback_widgets.dart';
import '../../shared/responsive.dart';
import 'audiobook_controller.dart';
import 'flutter_tts_engine.dart';

class AudiobookPage extends StatefulWidget {
  const AudiobookPage({
    required this.detail,
    required this.loadChapter,
    this.initialChapterIndex,
    this.engine,
    this.voice,
    this.style = TtsSpeechStyle.natural,
    this.onStyleChanged,
    super.key,
  });

  final BookDetail detail;
  final ChapterLoader loadChapter;
  final int? initialChapterIndex;
  final TtsEngine? engine;
  final TtsVoice? voice;
  final TtsSpeechStyle style;
  final Future<void> Function(TtsSpeechStyle style)? onStyleChanged;

  @override
  State<AudiobookPage> createState() => _AudiobookPageState();
}

class _AudiobookPageState extends State<AudiobookPage> {
  late final AudiobookController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AudiobookController(
      detail: widget.detail,
      engine: widget.engine ?? FlutterTtsEngine(voice: widget.voice),
      loadChapter: widget.loadChapter,
      initialChapterIndex: widget.initialChapterIndex,
      initialStyle: widget.style,
    );
    unawaited(_controller.initialize());
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, _) {
        final theme = FluentTheme.of(context);
        if (!usesMobileUi(context)) return _buildDesktopPage(context, theme);
        final dark = theme.brightness == Brightness.dark;
        return NavigationView(
          content: DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: dark
                    ? const <Color>[Color(0xFF18352F), Color(0xFF111715)]
                    : const <Color>[Color(0xFFE0F1EA), Color(0xFFF7F7F4)],
                stops: const <double>[0, .58],
              ),
            ),
            child: SafeArea(
              child: Center(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 760),
                  child: SingleChildScrollView(
                    padding: const EdgeInsets.fromLTRB(18, 12, 18, 28),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: <Widget>[
                        Row(
                          children: <Widget>[
                            Tooltip(
                              message: '返回作品详情',
                              child: IconButton(
                                icon: const Icon(
                                  FluentIcons.back,
                                  semanticLabel: '返回作品详情',
                                ),
                                onPressed: () => Navigator.pop(context),
                              ),
                            ),
                            const SizedBox(width: 10),
                            Expanded(
                              child: Text(
                                '听书 · ${widget.detail.book.title}',
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: theme.typography.subtitle?.copyWith(
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                            ),
                            StatusPill(
                              _stateLabel(_controller.state),
                              accented: _controller.isPlaying,
                              icon: _controller.isPlaying
                                  ? FluentIcons.volume3
                                  : FluentIcons.headset,
                            ),
                          ],
                        ),
                        const SizedBox(height: 22),
                        Center(
                          child: _AudiobookArtwork(
                            title: widget.detail.book.title,
                          ),
                        ),
                        const SizedBox(height: 22),
                        Text(
                          _controller.currentChapter.title,
                          textAlign: TextAlign.center,
                          style: theme.typography.title?.copyWith(
                            fontSize: 25,
                            fontWeight: FontWeight.w800,
                          ),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                        ),
                        const SizedBox(height: 7),
                        Text(
                          '第 ${_controller.chapterIndex} / ${widget.detail.chapters.length} 章',
                          textAlign: TextAlign.center,
                          style: theme.typography.caption,
                        ),
                        const SizedBox(height: 18),
                        ProgressBar(
                          value: _controller.chapterProgress,
                          strokeWidth: 4,
                        ),
                        const SizedBox(height: 20),
                        _PlaybackControls(controller: _controller),
                        const SizedBox(height: 22),
                        AppSurface(
                          tone: AppSurfaceTone.elevated,
                          borderRadius: 24,
                          padding: const EdgeInsets.all(18),
                          child: _SpeechSettings(
                            controller: _controller,
                            onStyleChanged: (style) async {
                              await _controller.setStyle(style);
                              await widget.onStyleChanged?.call(style);
                            },
                          ),
                        ),
                        const SizedBox(height: 16),
                        AppSurface(
                          tone: AppSurfaceTone.muted,
                          borderRadius: 22,
                          padding: const EdgeInsets.all(18),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: <Widget>[
                              Text(
                                '本章文字',
                                style: theme.typography.subtitle?.copyWith(
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                              const SizedBox(height: 12),
                              ConstrainedBox(
                                constraints:
                                    const BoxConstraints(maxHeight: 240),
                                child: _controller.isLoading
                                    ? const LoadingView(label: '正在加载章节正文')
                                    : _controller.error != null
                                        ? ErrorView(
                                            message: _controller.error!,
                                            onRetry: _controller.initialize,
                                          )
                                        : SingleChildScrollView(
                                            child: SelectionArea(
                                              child: Text(
                                                _controller.currentText,
                                                style: theme
                                                    .typography.bodyLarge
                                                    ?.copyWith(height: 1.8),
                                              ),
                                            ),
                                          ),
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
      },
    );
  }

  Widget _buildDesktopPage(BuildContext context, FluentThemeData theme) {
    return NavigationView(
      key: const ValueKey('desktop-audiobook-page'),
      appBar: NavigationAppBar(
        automaticallyImplyLeading: false,
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
        title: Text('听书 · ${widget.detail.book.title}'),
      ),
      content: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 760),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(28, 28, 28, 24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                Text(
                  _controller.currentChapter.title,
                  style: theme.typography.title,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 6),
                Text(
                  '第 ${_controller.chapterIndex} / '
                  '${widget.detail.chapters.length} 章 · '
                  '${_stateLabel(_controller.state)}',
                  style: theme.typography.caption,
                ),
                const SizedBox(height: 20),
                ProgressBar(value: _controller.chapterProgress),
                const SizedBox(height: 24),
                Expanded(
                  child: Container(
                    padding: const EdgeInsets.all(22),
                    decoration: BoxDecoration(
                      color: theme.cardColor,
                      border: Border.all(
                        color: theme.resources.cardStrokeColorDefault,
                      ),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: _controller.isLoading
                        ? const LoadingView(label: '正在加载章节正文')
                        : _controller.error != null
                            ? ErrorView(
                                message: _controller.error!,
                                onRetry: _controller.initialize,
                              )
                            : SingleChildScrollView(
                                child: SelectionArea(
                                  child: Text(
                                    _controller.currentText,
                                    style: theme.typography.bodyLarge
                                        ?.copyWith(height: 1.8),
                                  ),
                                ),
                              ),
                  ),
                ),
                const SizedBox(height: 20),
                _PlaybackControls(controller: _controller),
                const SizedBox(height: 18),
                _SpeechSettings(
                  controller: _controller,
                  onStyleChanged: (style) async {
                    await _controller.setStyle(style);
                    await widget.onStyleChanged?.call(style);
                  },
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  String _stateLabel(AudiobookPlaybackState state) => switch (state) {
        AudiobookPlaybackState.loading => '加载中',
        AudiobookPlaybackState.playing => '正在播放',
        AudiobookPlaybackState.paused => '已暂停',
        AudiobookPlaybackState.stopped => '已停止',
        AudiobookPlaybackState.completed => '本书播放完成',
        AudiobookPlaybackState.error => '播放失败',
        AudiobookPlaybackState.idle => '准备播放',
      };
}

class _AudiobookArtwork extends StatelessWidget {
  const _AudiobookArtwork({required this.title});

  final String title;

  @override
  Widget build(BuildContext context) {
    final theme = FluentTheme.of(context);
    final dark = theme.brightness == Brightness.dark;
    return Container(
      width: 138,
      height: 184,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: dark
              ? const <Color>[Color(0xFF236D63), Color(0xFF18251F)]
              : const <Color>[Color(0xFF4BAA9E), Color(0xFFB9D9C9)],
        ),
        borderRadius: BorderRadius.circular(22),
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: const Color(0xFF102A26).withAlpha(dark ? 76 : 42),
            blurRadius: 24,
            offset: const Offset(0, 12),
          ),
        ],
      ),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: <Widget>[
          const Icon(FluentIcons.headset, color: Color(0xFFFFFFFF), size: 38),
          const SizedBox(height: 14),
          Text(
            title,
            maxLines: 3,
            overflow: TextOverflow.ellipsis,
            textAlign: TextAlign.center,
            style: theme.typography.bodyLarge?.copyWith(
              color: const Color(0xFFFFFFFF),
              fontWeight: FontWeight.w800,
            ),
          ),
        ],
      ),
    );
  }
}

class _PlaybackControls extends StatelessWidget {
  const _PlaybackControls({required this.controller});

  final AudiobookController controller;

  @override
  Widget build(BuildContext context) {
    if (!usesMobileUi(context)) {
      return Wrap(
        alignment: WrapAlignment.center,
        crossAxisAlignment: WrapCrossAlignment.center,
        spacing: 14,
        runSpacing: 10,
        children: <Widget>[
          Button(
            onPressed: controller.chapterIndex > 1 && !controller.isLoading
                ? () => unawaited(
                      controller.moveChapter(
                        -1,
                        autoplay: controller.isPlaying,
                      ),
                    )
                : null,
            child: const Text('上一章'),
          ),
          Tooltip(
            message: '停止播放',
            child: IconButton(
              icon: const Icon(
                FluentIcons.stop,
                size: 20,
                semanticLabel: '停止播放',
              ),
              onPressed: controller.isLoading
                  ? null
                  : () => unawaited(controller.stop()),
            ),
          ),
          FilledButton(
            onPressed: controller.isLoading
                ? null
                : () => unawaited(
                      controller.isPlaying
                          ? controller.pause()
                          : controller.play(),
                    ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Icon(
                  controller.isPlaying ? FluentIcons.pause : FluentIcons.play,
                  size: 16,
                ),
                const SizedBox(width: 8),
                Text(
                  controller.isPlaying
                      ? '暂停'
                      : controller.isPaused
                          ? '继续'
                          : '播放',
                ),
              ],
            ),
          ),
          Button(
            onPressed:
                controller.chapterIndex < controller.detail.chapters.length &&
                        !controller.isLoading
                    ? () => unawaited(
                          controller.moveChapter(
                            1,
                            autoplay: controller.isPlaying,
                          ),
                        )
                    : null,
            child: const Text('下一章'),
          ),
        ],
      );
    }
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: <Widget>[
        IconButton(
          onPressed: controller.chapterIndex > 1 && !controller.isLoading
              ? () => unawaited(
                    controller.moveChapter(
                      -1,
                      autoplay: controller.isPlaying,
                    ),
                  )
              : null,
          icon: const Icon(
            FluentIcons.previous,
            semanticLabel: '上一章',
            size: 22,
          ),
        ),
        const SizedBox(width: 12),
        Tooltip(
          message: '停止播放',
          child: IconButton(
            icon: const Icon(
              FluentIcons.stop,
              size: 20,
              semanticLabel: '停止播放',
            ),
            onPressed: controller.isLoading
                ? null
                : () => unawaited(controller.stop()),
          ),
        ),
        const SizedBox(width: 12),
        FilledButton(
          style: ButtonStyle(
            padding: const WidgetStatePropertyAll(
              EdgeInsets.symmetric(horizontal: 24, vertical: 15),
            ),
            shape: WidgetStatePropertyAll(
              RoundedRectangleBorder(borderRadius: BorderRadius.circular(99)),
            ),
          ),
          onPressed: controller.isLoading
              ? null
              : () => unawaited(
                    controller.isPlaying
                        ? controller.pause()
                        : controller.play(),
                  ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Icon(
                controller.isPlaying ? FluentIcons.pause : FluentIcons.play,
                size: 16,
              ),
              const SizedBox(width: 8),
              Text(controller.isPlaying
                  ? '暂停'
                  : controller.isPaused
                      ? '继续'
                      : '播放'),
            ],
          ),
        ),
        const SizedBox(width: 12),
        IconButton(
          onPressed:
              controller.chapterIndex < controller.detail.chapters.length &&
                      !controller.isLoading
                  ? () => unawaited(
                        controller.moveChapter(
                          1,
                          autoplay: controller.isPlaying,
                        ),
                      )
                  : null,
          icon: const Icon(
            FluentIcons.next,
            semanticLabel: '下一章',
            size: 22,
          ),
        ),
      ],
    );
  }
}

class _SpeechSettings extends StatelessWidget {
  const _SpeechSettings({
    required this.controller,
    required this.onStyleChanged,
  });

  final AudiobookController controller;
  final Future<void> Function(TtsSpeechStyle style) onStyleChanged;

  @override
  Widget build(BuildContext context) {
    final theme = FluentTheme.of(context);
    if (!usesMobileUi(context)) {
      return Wrap(
        crossAxisAlignment: WrapCrossAlignment.center,
        spacing: 18,
        runSpacing: 12,
        children: <Widget>[
          SizedBox(
            width: 230,
            child: InfoLabel(
              label: '朗读风格',
              child: ComboBox<TtsSpeechStyle>(
                value: controller.style,
                isExpanded: true,
                items: TtsSpeechStyle.values
                    .map(
                      (style) => ComboBoxItem<TtsSpeechStyle>(
                        value: style,
                        child:
                            Text(style.label, overflow: TextOverflow.ellipsis),
                      ),
                    )
                    .toList(),
                onChanged: controller.isLoading
                    ? null
                    : (style) {
                        if (style != null) unawaited(onStyleChanged(style));
                      },
              ),
            ),
          ),
          Row(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              const Text('朗读版本'),
              const SizedBox(width: 10),
              ToggleButton(
                checked: controller.mode == 'original',
                onChanged: controller.isLoading
                    ? null
                    : (checked) => unawaited(
                          controller.setMode(
                            checked ? 'original' : 'translated',
                          ),
                        ),
                child: Text(controller.mode == 'original' ? '原文' : '译文'),
              ),
            ],
          ),
          SizedBox(
            width: 250,
            child: Row(
              children: <Widget>[
                const Text('语速'),
                Expanded(
                  child: Slider(
                    value: controller.rate,
                    min: 0.2,
                    max: 1,
                    divisions: 8,
                    onChanged: (value) => unawaited(controller.setRate(value)),
                  ),
                ),
                Text('${controller.rate.toStringAsFixed(2)}×'),
              ],
            ),
          ),
          SizedBox(
            width: 250,
            child: Row(
              children: <Widget>[
                const Text('音量'),
                Expanded(
                  child: Slider(
                    value: controller.volume,
                    min: 0,
                    max: 1,
                    divisions: 10,
                    onChanged: (value) =>
                        unawaited(controller.setVolume(value)),
                  ),
                ),
                Text('${(controller.volume * 100).round()}%'),
              ],
            ),
          ),
          SizedBox(
            width: 320,
            child: Text(
              controller.style.description,
              style: theme.typography.caption,
            ),
          ),
        ],
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Text(
          '播放设置',
          style: theme.typography.subtitle?.copyWith(
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 16),
        SizedBox(
          width: double.infinity,
          child: InfoLabel(
            label: '朗读风格',
            child: ComboBox<TtsSpeechStyle>(
              value: controller.style,
              isExpanded: true,
              items: TtsSpeechStyle.values
                  .map(
                    (style) => ComboBoxItem<TtsSpeechStyle>(
                      value: style,
                      child: Text(
                        style.label,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  )
                  .toList(),
              onChanged: controller.isLoading
                  ? null
                  : (style) {
                      if (style != null) unawaited(onStyleChanged(style));
                    },
            ),
          ),
        ),
        const SizedBox(height: 16),
        Row(
          children: <Widget>[
            Expanded(
              child: Text(
                '朗读版本',
                style: theme.typography.body?.copyWith(
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
            ToggleButton(
              checked: controller.mode == 'original',
              onChanged: controller.isLoading
                  ? null
                  : (checked) => unawaited(
                        controller.setMode(
                          checked ? 'original' : 'translated',
                        ),
                      ),
              child: Text(controller.mode == 'original' ? '原文' : '译文'),
            ),
          ],
        ),
        const SizedBox(height: 16),
        SizedBox(
          width: double.infinity,
          child: Row(
            children: <Widget>[
              const Text('语速'),
              Expanded(
                child: Slider(
                  value: controller.rate,
                  min: 0.2,
                  max: 1,
                  divisions: 8,
                  onChanged: (value) => unawaited(controller.setRate(value)),
                ),
              ),
              Text('${controller.rate.toStringAsFixed(2)}×'),
            ],
          ),
        ),
        const SizedBox(height: 12),
        SizedBox(
          width: double.infinity,
          child: Row(
            children: <Widget>[
              const Text('音量'),
              Expanded(
                child: Slider(
                  value: controller.volume,
                  min: 0,
                  max: 1,
                  divisions: 10,
                  onChanged: (value) => unawaited(controller.setVolume(value)),
                ),
              ),
              Text('${(controller.volume * 100).round()}%'),
            ],
          ),
        ),
        const SizedBox(height: 12),
        SizedBox(
          width: double.infinity,
          child: Text(
            controller.style.description,
            style: theme.typography.caption?.copyWith(height: 1.45),
          ),
        ),
      ],
    );
  }
}

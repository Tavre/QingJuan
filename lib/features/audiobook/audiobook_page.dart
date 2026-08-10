import 'dart:async';

import 'package:fluent_ui/fluent_ui.dart';

import '../../core/models/book.dart';
import '../../core/models/tts_speech_style.dart';
import '../../core/models/tts_voice.dart';
import '../../shared/feedback_widgets.dart';
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
        return NavigationView(
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
                      '第 ${_controller.chapterIndex} / ${widget.detail.chapters.length} 章 · ${_stateLabel(_controller.state)}',
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
      },
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

class _PlaybackControls extends StatelessWidget {
  const _PlaybackControls({required this.controller});

  final AudiobookController controller;

  @override
  Widget build(BuildContext context) {
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
              Text(controller.isPlaying
                  ? '暂停'
                  : controller.isPaused
                      ? '继续'
                      : '播放'),
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
                  onChanged: (value) => unawaited(controller.setVolume(value)),
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
            style: FluentTheme.of(context).typography.caption,
          ),
        ),
      ],
    );
  }
}

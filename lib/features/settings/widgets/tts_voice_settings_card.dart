import 'dart:async';

import 'package:fluent_ui/fluent_ui.dart';

import '../../../app/app_state.dart';
import '../../../core/models/tts_speech_style.dart';
import '../../../core/models/tts_voice.dart';
import '../../audiobook/tts_voice_service.dart';
import 'settings_section_card.dart';
import 'tts_voice_selector.dart';

class TtsVoiceSettingsCard extends StatefulWidget {
  const TtsVoiceSettingsCard({
    required this.appState,
    required this.compact,
    this.voiceService,
    super.key,
  });

  final AppState appState;
  final bool compact;
  final TtsVoiceService? voiceService;

  @override
  State<TtsVoiceSettingsCard> createState() => _TtsVoiceSettingsCardState();
}

class _TtsVoiceSettingsCardState extends State<TtsVoiceSettingsCard> {
  late TtsVoiceService _voiceService;
  List<TtsVoice> _voices = const <TtsVoice>[];
  bool _voicesLoading = true;
  String? _voiceError;
  String? _previewingVoiceKey;

  @override
  void initState() {
    super.initState();
    _voiceService = widget.voiceService ?? FlutterTtsVoiceService();
    unawaited(_loadVoices());
  }

  @override
  void didUpdateWidget(covariant TtsVoiceSettingsCard oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (identical(oldWidget.voiceService, widget.voiceService)) return;
    unawaited(_voiceService.dispose());
    _voiceService = widget.voiceService ?? FlutterTtsVoiceService();
    unawaited(_loadVoices());
  }

  Future<void> _loadVoices() async {
    if (mounted) {
      setState(() {
        _voicesLoading = true;
        _voiceError = null;
      });
    }
    try {
      final voices = await _voiceService.loadVoices();
      if (!mounted) return;
      setState(() {
        _voices = voices;
        _voicesLoading = false;
        if (voices.isEmpty) {
          _voiceError = '当前设备没有可用的系统声音，请先安装或启用 TTS 语音包。';
        }
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _voicesLoading = false;
        _voiceError = '$error';
      });
    }
  }

  Future<void> _selectVoice(String? key) async {
    final voice = key == null
        ? null
        : _voices.cast<TtsVoice?>().firstWhere(
              (item) => item?.stableKey == key,
              orElse: () => widget.appState.ttsVoice,
            );
    await _voiceService.stop();
    await widget.appState.setTtsVoice(voice);
  }

  Future<void> _previewVoice(
    TtsVoice voice,
    TtsSpeechStyle style,
  ) async {
    setState(() {
      _previewingVoiceKey = voice.stableKey;
      _voiceError = null;
    });
    try {
      await _voiceService.preview(voice, style: style);
    } catch (error) {
      if (mounted) setState(() => _voiceError = '$error');
    } finally {
      if (mounted) setState(() => _previewingVoiceKey = null);
    }
  }

  @override
  void dispose() {
    unawaited(_voiceService.dispose());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final appState = widget.appState;
    return SettingsSectionCard(
      icon: FluentIcons.volume3,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          InfoLabel(
            label: '默认朗读风格',
            child: SizedBox(
              width: widget.compact ? double.infinity : 320,
              child: ComboBox<TtsSpeechStyle>(
                value: appState.ttsSpeechStyle,
                isExpanded: true,
                items: TtsSpeechStyle.values
                    .map(
                      (style) => ComboBoxItem<TtsSpeechStyle>(
                        value: style,
                        child: Text(
                          '${style.label} · ${style.description}',
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    )
                    .toList(),
                onChanged: (style) {
                  if (style != null) {
                    unawaited(appState.setTtsSpeechStyle(style));
                  }
                },
              ),
            ),
          ),
          const SizedBox(height: 14),
          TtsVoiceSelector(
            compact: widget.compact,
            voices: _voices,
            selected: appState.ttsVoice,
            voicesLoading: _voicesLoading,
            previewingVoiceKey: _previewingVoiceKey,
            onVoiceChanged: (key) => unawaited(_selectVoice(key)),
            onPreview: (voice) => unawaited(
              _previewVoice(voice, appState.ttsSpeechStyle),
            ),
            onReload: _loadVoices,
          ),
          const SizedBox(height: 8),
          Text(
            _voicesLoading
                ? '正在读取设备已安装声音…'
                : '已发现 ${_voices.length} 个系统声音。选择会立即保存，并用于之后打开的听书页面。',
            style: FluentTheme.of(context).typography.caption,
          ),
          if (!_voicesLoading) ...<Widget>[
            const SizedBox(height: 10),
            InfoBar(
              title: Text(
                _voices.any((voice) => voice.isNatural)
                    ? '已检测到自然声线'
                    : '建议安装 Natural / Neural 声线',
              ),
              content: Text(
                _voices.any((voice) => voice.isNatural)
                    ? '自然声线配合朗读风格，可获得更接近真人的节奏和语调。'
                    : '朗读风格会改善节奏、停顿和语调，但基础音色仍由系统 TTS 引擎决定；标准声线可能保留机械感。',
              ),
              severity: _voices.any((voice) => voice.isNatural)
                  ? InfoBarSeverity.success
                  : InfoBarSeverity.warning,
            ),
          ],
          if (_voicesLoading) ...<Widget>[
            const SizedBox(height: 10),
            const ProgressBar(),
          ],
          if (_voiceError != null) ...<Widget>[
            const SizedBox(height: 12),
            InfoBar(
              title: const Text('声音服务不可用'),
              content: Text(_voiceError!),
              severity: InfoBarSeverity.warning,
            ),
          ],
        ],
      ),
    );
  }
}

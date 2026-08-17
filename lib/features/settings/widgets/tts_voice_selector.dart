import 'package:fluent_ui/fluent_ui.dart';

import '../../../core/models/tts_voice.dart';

class TtsVoiceSelector extends StatelessWidget {
  const TtsVoiceSelector({
    required this.compact,
    required this.voices,
    required this.selected,
    required this.voicesLoading,
    required this.previewingVoiceKey,
    required this.onVoiceChanged,
    required this.onPreview,
    required this.onReload,
    super.key,
  });

  static const _systemVoiceKey = '__system_default__';

  final bool compact;
  final List<TtsVoice> voices;
  final TtsVoice? selected;
  final bool voicesLoading;
  final String? previewingVoiceKey;
  final ValueChanged<String?> onVoiceChanged;
  final ValueChanged<TtsVoice> onPreview;
  final VoidCallback onReload;

  @override
  Widget build(BuildContext context) {
    final selectedAvailable = selected == null ||
        voices.any((voice) => voice.stableKey == selected!.stableKey);
    final choices = <TtsVoice>[
      ...voices,
      if (selected != null && !selectedAvailable) selected!,
    ];
    final selectedKey = selected?.stableKey ?? _systemVoiceKey;
    final selectedVoice = selected == null
        ? null
        : choices.cast<TtsVoice?>().firstWhere(
              (voice) => voice?.stableKey == selected!.stableKey,
              orElse: () => null,
            );
    final previewing =
        selectedVoice != null && previewingVoiceKey == selectedVoice.stableKey;

    return InfoLabel(
      label: '系统声线',
      child: Wrap(
        spacing: 10,
        runSpacing: 10,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: <Widget>[
          SizedBox(
            width: compact ? double.infinity : 520,
            child: ComboBox<String>(
              value: selectedKey,
              isExpanded: true,
              items: <ComboBoxItem<String>>[
                const ComboBoxItem<String>(
                  value: _systemVoiceKey,
                  child: Text('跟随系统默认声音'),
                ),
                ...choices.map(
                  (voice) => ComboBoxItem<String>(
                    value: voice.stableKey,
                    child: Text(
                      '${voice.name} · ${voice.description}'
                      ' · ${voice.qualityLabel}'
                      '${!selectedAvailable && voice == selected ? '（当前不可用）' : ''}',
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ),
              ],
              onChanged: voicesLoading
                  ? null
                  : (key) => onVoiceChanged(
                        key == _systemVoiceKey ? null : key,
                      ),
            ),
          ),
          Button(
            onPressed: selectedVoice == null ||
                    voicesLoading ||
                    previewingVoiceKey != null ||
                    !selectedAvailable
                ? null
                : () => onPreview(selectedVoice),
            child: Text(previewing ? '试听中…' : '试听'),
          ),
          Tooltip(
            message: '重新扫描系统声音',
            child: IconButton(
              icon: const Icon(
                FluentIcons.refresh,
                size: 16,
                semanticLabel: '重新扫描系统声音',
              ),
              onPressed: voicesLoading ? null : onReload,
            ),
          ),
        ],
      ),
    );
  }
}

import 'dart:io';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/services.dart';
import 'package:path_provider/path_provider.dart';

typedef TemporaryDirectoryProvider = Future<Directory> Function();
typedef DesktopFileSaver = Future<String?> Function({
  required String sourcePath,
  required String suggestedName,
  required String mimeType,
});

class SavedExport<T> {
  const SavedExport({
    required this.value,
    required this.fileName,
    required this.documentUri,
  });

  final T value;
  final String fileName;
  final String documentUri;
}

class ExportFileService {
  ExportFileService({
    MethodChannel? channel,
    TemporaryDirectoryProvider? temporaryDirectory,
    bool? useDocumentChannel,
    DesktopFileSaver? desktopFileSaver,
  })  : _channel = channel ?? const MethodChannel('qingjuan/files'),
        _temporaryDirectory = temporaryDirectory ?? getTemporaryDirectory,
        _useDocumentChannel = useDocumentChannel ?? Platform.isAndroid,
        _desktopFileSaver = desktopFileSaver ?? _saveWithSystemPicker;

  final MethodChannel _channel;
  final TemporaryDirectoryProvider _temporaryDirectory;
  final bool _useDocumentChannel;
  final DesktopFileSaver _desktopFileSaver;

  Future<SavedExport<T>?> save<T>({
    required String suggestedName,
    required String mimeType,
    required Future<T> Function(String temporaryPath) download,
  }) async {
    final root = await _temporaryDirectory();
    final workingDirectory = await root.createTemp('qingjuan-export-');
    final safeName = suggestedName.replaceAll(RegExp(r'[\\/]'), '_');
    final temporaryFile =
        File('${workingDirectory.path}${Platform.pathSeparator}$safeName');

    try {
      final value = await download(temporaryFile.path);
      final documentUri = _useDocumentChannel
          ? await _channel.invokeMethod<String>(
              'saveFile',
              <String, String>{
                'sourcePath': temporaryFile.path,
                'suggestedName': safeName,
                'mimeType': mimeType,
              },
            )
          : await _desktopFileSaver(
              sourcePath: temporaryFile.path,
              suggestedName: safeName,
              mimeType: mimeType,
            );
      if (documentUri == null || documentUri.isEmpty) return null;
      return SavedExport<T>(
        value: value,
        fileName: safeName,
        documentUri: documentUri,
      );
    } finally {
      if (await workingDirectory.exists()) {
        await workingDirectory.delete(recursive: true);
      }
    }
  }
}

Future<String?> _saveWithSystemPicker({
  required String sourcePath,
  required String suggestedName,
  required String mimeType,
}) async {
  final dot = suggestedName.lastIndexOf('.');
  final extension = dot >= 0 && dot < suggestedName.length - 1
      ? suggestedName.substring(dot + 1).toLowerCase()
      : null;
  final location = await getSaveLocation(
    suggestedName: suggestedName,
    acceptedTypeGroups: extension == null
        ? const <XTypeGroup>[]
        : <XTypeGroup>[
            XTypeGroup(
              label: '青卷导出文件',
              extensions: <String>[extension],
            ),
          ],
  );
  if (location == null) return null;
  await XFile(sourcePath, name: suggestedName, mimeType: mimeType)
      .saveTo(location.path);
  return location.path;
}

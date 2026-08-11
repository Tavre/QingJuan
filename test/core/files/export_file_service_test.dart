import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:qingjuan/core/files/export_file_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('downloads to cache and copies through the Android document channel',
      () async {
    final root = await Directory.systemTemp.createTemp('qingjuan-save-test-');
    addTearDown(() => root.delete(recursive: true));
    const channel = MethodChannel('qingjuan/files-test');
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(channel, (call) async {
      expect(call.method, 'saveFile');
      final arguments = Map<String, dynamic>.from(call.arguments as Map);
      expect(arguments['suggestedName'], 'chapter.txt');
      expect(arguments['mimeType'], 'text/plain');
      expect(
        await File(arguments['sourcePath'] as String).readAsString(),
        'chapter content',
      );
      return 'content://documents/chapter.txt';
    });
    addTearDown(() => messenger.setMockMethodCallHandler(channel, null));
    final service = ExportFileService(
      channel: channel,
      temporaryDirectory: () async => root,
      useDocumentChannel: true,
    );

    final saved = await service.save<int>(
      suggestedName: 'chapter.txt',
      mimeType: 'text/plain',
      download: (path) async {
        await File(path).writeAsString('chapter content');
        return 7;
      },
    );

    expect(saved?.value, 7);
    expect(saved?.fileName, 'chapter.txt');
    expect(saved?.documentUri, 'content://documents/chapter.txt');
    expect(root.listSync(), isEmpty);
  });

  test('cleans the cached download when the user cancels saving', () async {
    final root = await Directory.systemTemp.createTemp('qingjuan-save-test-');
    addTearDown(() => root.delete(recursive: true));
    const channel = MethodChannel('qingjuan/files-cancel-test');
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(channel, (_) async => null);
    addTearDown(() => messenger.setMockMethodCallHandler(channel, null));
    final service = ExportFileService(
      channel: channel,
      temporaryDirectory: () async => root,
      useDocumentChannel: true,
    );

    final saved = await service.save<void>(
      suggestedName: '../chapter.txt',
      mimeType: 'text/plain',
      download: (path) async {
        await File(path).writeAsString('temporary');
      },
    );

    expect(saved, isNull);
    expect(root.listSync(), isEmpty);
  });

  test('uses the system save path on Windows and cleans the cached download',
      () async {
    final root = await Directory.systemTemp.createTemp('qingjuan-save-test-');
    final destinationRoot =
        await Directory.systemTemp.createTemp('qingjuan-save-destination-');
    addTearDown(() => root.delete(recursive: true));
    addTearDown(() => destinationRoot.delete(recursive: true));
    final destination = File(
      '${destinationRoot.path}${Platform.pathSeparator}chapter.txt',
    );
    final service = ExportFileService(
      temporaryDirectory: () async => root,
      useDocumentChannel: false,
      desktopFileSaver: ({
        required sourcePath,
        required suggestedName,
        required mimeType,
      }) async {
        expect(suggestedName, 'chapter.txt');
        expect(mimeType, 'text/plain');
        expect(await File(sourcePath).readAsString(), 'desktop chapter');
        await File(sourcePath).copy(destination.path);
        return destination.path;
      },
    );

    final saved = await service.save<int>(
      suggestedName: 'chapter.txt',
      mimeType: 'text/plain',
      download: (path) async {
        await File(path).writeAsString('desktop chapter');
        return 9;
      },
    );

    expect(saved?.value, 9);
    expect(saved?.documentUri, destination.path);
    expect(await destination.readAsString(), 'desktop chapter');
    expect(root.listSync(), isEmpty);
  });
}

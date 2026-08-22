import 'package:flutter_test/flutter_test.dart';
import 'package:qingjuan/core/models/task.dart';

void main() {
  test('TaskLog parses task runtime log fields', () {
    final log = TaskLog.fromJson(<String, dynamic>{
      'sequence': 12,
      'taskId': 'task-1',
      'level': 'error',
      'message': '章节翻译失败',
      'createdAt': '2026-08-23T08:30:00Z',
    });

    expect(log.sequence, 12);
    expect(log.taskId, 'task-1');
    expect(log.level, 'error');
    expect(log.message, '章节翻译失败');
    expect(log.createdAt, '2026-08-23T08:30:00Z');
  });

  test('TaskLog uses safe defaults for incomplete payloads', () {
    final log = TaskLog.fromJson(<String, dynamic>{});

    expect(log.sequence, 0);
    expect(log.taskId, isEmpty);
    expect(log.level, 'info');
    expect(log.message, isEmpty);
    expect(log.createdAt, isEmpty);
  });

  test('TaskLog normalizes unknown levels to info', () {
    final log = TaskLog.fromJson(<String, dynamic>{'level': 'debug'});

    expect(log.level, 'info');
  });
}

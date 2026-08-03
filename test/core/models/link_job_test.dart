import 'package:flutter_test/flutter_test.dart';
import 'package:qingjuan/core/models/link_job.dart';

void main() {
  test('LinkJob parses progress logs and preview result', () {
    final job = LinkJob.fromJson(<String, dynamic>{
      'id': 'link-1',
      'mode': 'preview',
      'status': 'running',
      'progress': 55,
      'message': '正在解析章节目录',
      'logs': <Map<String, dynamic>>[
        <String, dynamic>{
          'sequence': 1,
          'level': 'info',
          'message': '已提交链接',
          'createdAt': '2026-08-03 12:00:00',
        },
      ],
      'preview': <String, dynamic>{
        'title': '测试漫画',
        'author': '作者',
        'synopsis': '',
        'chapterCount': 2,
        'bookKind': '漫画',
      },
      'createdAt': '2026-08-03 12:00:00',
      'updatedAt': '2026-08-03 12:00:03',
    });

    expect(job.isActive, isTrue);
    expect(job.progress, 55);
    expect(job.logs.single.message, '已提交链接');
    expect(job.preview?.title, '测试漫画');
  });
}

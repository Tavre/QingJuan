import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:qingjuan/features/reader/reader_pagination.dart';

void main() {
  test('pagination preserves the complete chapter text in order', () {
    final text = List<String>.generate(
      80,
      (index) => '第 ${index + 1} 段内容，应该完整保留。',
    ).join('\n');

    final pages = paginateReaderText(text, 120);

    expect(pages, hasLength(greaterThan(1)));
    expect(pages.join(), text);
    expect(pages.every((page) => page.isNotEmpty), isTrue);
  });

  test('page capacity responds to viewport size and font size', () {
    final compact = estimateReaderPageCharacters(const Size(360, 640), 24);
    final spacious = estimateReaderPageCharacters(const Size(800, 1200), 18);

    expect(compact, greaterThanOrEqualTo(80));
    expect(spacious, greaterThan(compact));
  });
}

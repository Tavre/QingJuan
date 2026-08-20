import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:qingjuan/features/reader/reader_pagination.dart';

void main() {
  test('reader paragraphs use one stable two-character first-line indent', () {
    final paragraphs = readerParagraphsForLayout(
      const <String>['  第一段。  ', '\u3000\u3000第二段。', '   '],
      '',
    );

    expect(
      paragraphs,
      const <String>[
        '$readerFirstLineIndent第一段。',
        '$readerFirstLineIndent第二段。',
      ],
    );
    expect(
      readerTextForPagination(paragraphs, ''),
      '$readerFirstLineIndent第一段。\n\n'
      '$readerFirstLineIndent第二段。',
    );
  });

  test('justified long and short paragraphs keep the same first-line indent',
      () {
    const fontSize = 20.0;
    const shortBody = '正文。';
    const longBody = '正文需要足够长并自动换行，用于验证两端对齐时首行缩进不会被排版引擎裁掉。';

    double firstCharacterLeft(String body) {
      final text = '$readerFirstLineIndent$body';
      final painter = TextPainter(
        text: TextSpan(
          text: text,
          style: const TextStyle(fontSize: fontSize),
        ),
        textAlign: TextAlign.justify,
        textDirection: TextDirection.ltr,
      )..layout(maxWidth: 180);
      final contentOffset = text.indexOf('正');
      return painter
          .getBoxesForSelection(
            TextSelection(
              baseOffset: contentOffset,
              extentOffset: contentOffset + 1,
            ),
          )
          .first
          .left;
    }

    expect(readerFirstLineIndent.trim(), readerFirstLineIndent);
    expect(firstCharacterLeft(longBody), firstCharacterLeft(shortBody));
    expect(firstCharacterLeft(longBody), closeTo(fontSize * 2, 0.01));
  });

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

  test('a page continuation does not repeat the paragraph indent', () {
    final text = readerTextForPagination(
      <String>[List<String>.filled(150, '字').join()],
      '',
    );

    final pages = paginateReaderText(text, 40);

    expect(pages, hasLength(greaterThan(1)));
    expect(pages.first.startsWith(readerFirstLineIndent), isTrue);
    expect(
      pages.skip(1).every(
            (page) => !page.startsWith(readerFirstLineIndent),
          ),
      isTrue,
    );
  });

  test('page capacity responds to viewport size and font size', () {
    final compact = estimateReaderPageCharacters(const Size(360, 640), 24);
    final spacious = estimateReaderPageCharacters(const Size(800, 1200), 18);

    expect(compact, greaterThanOrEqualTo(80));
    expect(spacious, greaterThan(compact));
  });

  test('relaxed line spacing fits fewer characters per page', () {
    final compact = estimateReaderPageCharacters(
      const Size(390, 844),
      19,
      lineHeight: 1.62,
    );
    final relaxed = estimateReaderPageCharacters(
      const Size(390, 844),
      19,
      lineHeight: 2.04,
    );

    expect(relaxed, lessThan(compact));
  });
}

import 'package:flutter_test/flutter_test.dart';
import 'package:qingjuan/core/models/book.dart';

void main() {
  test('Book.fromJson fills optional values safely', () {
    final book = Book.fromJson(<String, dynamic>{
      'id': 'book-1',
      'title': '青卷测试',
      'bookKind': '轻小说',
      'language': '日文',
      'chapterCount': 12,
      'translated': true,
    });

    expect(book.id, 'book-1');
    expect(book.title, '青卷测试');
    expect(book.kind, '轻小说');
    expect(book.chapterCount, 12);
    expect(book.lastReadChapterIndex, 1);
    expect(book.synopsis, isEmpty);
  });

  test('ChapterContent.fromJson preserves text and image content', () {
    final content = ChapterContent.fromJson(<String, dynamic>{
      'chapter': <String, dynamic>{
        'index': 2,
        'title': '第二章',
        'downloaded': true,
        'translated': false,
      },
      'content': '正文',
      'paragraphs': <String>['第一段', '第二段'],
      'mode': 'original',
      'translatedAvailable': false,
      'imageSources': <String>['/books/1/assets/1.png'],
      'pageTranslations': <String>['译文'],
    });

    expect(content.chapter.index, 2);
    expect(content.paragraphs, hasLength(2));
    expect(content.imageSources.single, '/books/1/assets/1.png');
    expect(content.mode, 'original');
  });
}

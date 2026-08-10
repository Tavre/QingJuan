import 'package:fluent_ui/fluent_ui.dart';

import '../../../app/app_scope.dart';
import '../../../core/models/book.dart';
import '../../../shared/app_surface.dart';

class BookCard extends StatelessWidget {
  const BookCard({required this.book, required this.onOpen, super.key});

  final Book book;
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) {
    final theme = FluentTheme.of(context);
    final api = AppScope.of(context).api;
    final cover = book.cover?.trim();
    return AppSurface(
      onPressed: onOpen,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: SizedBox(
              width: 70,
              height: 102,
              child: cover == null || cover.isEmpty
                  ? ColoredBox(
                      color: theme.accentColor.withAlpha(
                        theme.brightness == Brightness.dark ? 52 : 30,
                      ),
                      child: Icon(
                        FluentIcons.reading_mode,
                        color:
                            theme.accentColor.defaultBrushFor(theme.brightness),
                      ),
                    )
                  : Image.network(
                      api.resolveUrl(cover),
                      headers: api.headersForUrl(cover),
                      fit: BoxFit.cover,
                      cacheWidth:
                          (70 * MediaQuery.devicePixelRatioOf(context)).round(),
                      cacheHeight:
                          (102 * MediaQuery.devicePixelRatioOf(context))
                              .round(),
                      errorBuilder: (_, __, ___) => ColoredBox(
                        color: theme.accentColor.withAlpha(
                          theme.brightness == Brightness.dark ? 52 : 30,
                        ),
                        child: Icon(
                          FluentIcons.book_answers,
                          color: theme.accentColor
                              .defaultBrushFor(theme.brightness),
                        ),
                      ),
                    ),
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Tooltip(
                  message: book.title,
                  child: Text(
                    book.title,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: theme.typography.bodyLarge
                        ?.copyWith(fontWeight: FontWeight.w600),
                  ),
                ),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 6,
                  runSpacing: 5,
                  children: <Widget>[
                    StatusPill(book.kind),
                    StatusPill(book.language),
                    if (book.translated)
                      const StatusPill('已翻译', accented: true),
                  ],
                ),
                const Spacer(),
                Wrap(
                  spacing: 8,
                  runSpacing: 2,
                  children: <Widget>[
                    Text(
                      '上次读到第 ${book.lastReadChapterIndex} 章',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: theme.typography.caption?.copyWith(
                        color: theme.resources.textFillColorSecondary,
                      ),
                    ),
                    Text(
                      '${book.lastReadChapterIndex}/${book.chapterCount}',
                      style: theme.typography.caption,
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                ProgressBar(
                  value: book.chapterCount <= 0
                      ? 0
                      : (book.lastReadChapterIndex / book.chapterCount * 100)
                          .clamp(0, 100),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

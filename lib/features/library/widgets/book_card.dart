import 'package:fluent_ui/fluent_ui.dart';

import '../../../app/app_scope.dart';
import '../../../core/models/book.dart';

class BookCard extends StatelessWidget {
  const BookCard({required this.book, required this.onOpen, super.key});

  final Book book;
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) {
    final theme = FluentTheme.of(context);
    final api = AppScope.of(context).api;
    final cover = book.cover?.trim();
    return HoverButton(
      onPressed: onOpen,
      builder: (context, states) {
        final hovered = states.isHovered;
        return AnimatedContainer(
          duration: const Duration(milliseconds: 140),
          curve: Curves.easeOutCubic,
          width: double.infinity,
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: hovered
                ? theme.resources.subtleFillColorSecondary
                : theme.cardColor,
            border: Border.all(color: theme.resources.cardStrokeColorDefault),
            borderRadius: BorderRadius.circular(8),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              ClipRRect(
                borderRadius: BorderRadius.circular(5),
                child: SizedBox(
                  width: 70,
                  height: 98,
                  child: cover == null || cover.isEmpty
                      ? ColoredBox(
                          color: theme.accentColor.lightest,
                          child: Icon(FluentIcons.reading_mode,
                              color: theme.accentColor.dark),
                        )
                      : Image.network(
                          api.resolveUrl(cover),
                          fit: BoxFit.cover,
                          cacheWidth:
                              (70 * MediaQuery.devicePixelRatioOf(context))
                                  .round(),
                          cacheHeight:
                              (98 * MediaQuery.devicePixelRatioOf(context))
                                  .round(),
                          errorBuilder: (_, __, ___) => ColoredBox(
                            color: theme.accentColor.lightest,
                            child: Icon(FluentIcons.book_answers,
                                color: theme.accentColor.dark),
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
                    const SizedBox(height: 7),
                    Row(
                      children: <Widget>[
                        Flexible(child: _Tag(book.kind)),
                        const SizedBox(width: 6),
                        Flexible(child: _Tag(book.language)),
                        if (book.translated) ...<Widget>[
                          const SizedBox(width: 6),
                          const Flexible(child: _Tag('已翻译')),
                        ],
                      ],
                    ),
                    const Spacer(),
                    Text(
                      '上次读到第 ${book.lastReadChapterIndex} 章',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: theme.typography.caption
                          ?.copyWith(color: theme.accentColor),
                    ),
                    const SizedBox(height: 8),
                    ProgressBar(
                      value: book.chapterCount <= 0
                          ? 0
                          : (book.lastReadChapterIndex /
                                  book.chapterCount *
                                  100)
                              .clamp(0, 100),
                    ),
                  ],
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _Tag extends StatelessWidget {
  const _Tag(this.label);

  final String label;

  @override
  Widget build(BuildContext context) {
    final theme = FluentTheme.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
      decoration: BoxDecoration(
        color: theme.resources.subtleFillColorSecondary,
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(
        label,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: theme.typography.caption,
      ),
    );
  }
}

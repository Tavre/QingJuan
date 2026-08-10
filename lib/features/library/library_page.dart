import 'package:fluent_ui/fluent_ui.dart';

import '../../app/app_scope.dart';
import '../../core/state/load_state.dart';
import '../../shared/feedback_widgets.dart';
import '../../shared/page_frame.dart';
import '../detail/book_detail_page.dart';
import 'import_book_dialog.dart';
import 'widgets/book_card.dart';

class LibraryPage extends StatelessWidget {
  const LibraryPage({super.key});

  @override
  Widget build(BuildContext context) {
    final controller = AppScope.of(context).library;
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final books = controller.filteredBooks;
        final textScale = MediaQuery.textScalerOf(context).scale(1);
        final scaleAllowance = 64 * (textScale - 1).clamp(0.0, 1.5).toDouble();
        return PageFrame(
          title: '书架',
          subtitle: '集中管理下载、翻译与阅读进度。',
          scrollable: false,
          command: Wrap(
            spacing: 8,
            runSpacing: 8,
            children: <Widget>[
              if (controller.linkJob != null) ...<Widget>[
                Button(
                  onPressed: () => _openImportDialog(context),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: <Widget>[
                      if (controller.hasActiveLinkJob) ...<Widget>[
                        const SizedBox(
                          width: 14,
                          height: 14,
                          child: ProgressRing(strokeWidth: 2.5),
                        ),
                        const SizedBox(width: 8),
                      ],
                      Text(controller.hasActiveLinkJob ? '链接解析中' : '查看链接任务'),
                    ],
                  ),
                ),
              ],
              FilledButton(
                onPressed: () => _openImportDialog(context),
                child: const Text('添加书籍'),
              ),
            ],
          ),
          child: Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Row(
                  children: <Widget>[
                    Expanded(
                      child: TextBox(
                        placeholder: '搜索书名或简介',
                        prefix: const Padding(
                          padding: EdgeInsets.only(left: 10),
                          child: Icon(FluentIcons.search),
                        ),
                        onChanged: controller.setQuery,
                      ),
                    ),
                    const SizedBox(width: 10),
                    Tooltip(
                      message: '刷新书架',
                      child: IconButton(
                        icon: const Icon(
                          FluentIcons.refresh,
                          semanticLabel: '刷新书架',
                        ),
                        onPressed: () => controller.load(),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 22),
                Expanded(
                  child: switch (controller.state) {
                    LoadState.idle ||
                    LoadState.loading =>
                      const LoadingView(label: '正在整理书架'),
                    LoadState.error => ErrorView(
                        message: controller.error ?? '未知错误',
                        onRetry: controller.load,
                      ),
                    LoadState.empty => EmptyView(
                        icon: FluentIcons.library,
                        title: '书架还是空的',
                        message: '添加网页作品或本地文本，青卷会在这里保存阅读进度。',
                        action: FilledButton(
                          onPressed: () => showImportBookDialog(context),
                          child: const Text('添加第一本书'),
                        ),
                      ),
                    LoadState.ready when books.isEmpty => const EmptyView(
                        icon: FluentIcons.search,
                        title: '没有匹配结果',
                        message: '试试更短的书名或作者关键词。',
                      ),
                    _ => GridView.builder(
                        cacheExtent: 420,
                        itemCount: books.length,
                        gridDelegate: SliverGridDelegateWithMaxCrossAxisExtent(
                          maxCrossAxisExtent: 352,
                          mainAxisExtent: 164 + scaleAllowance,
                          crossAxisSpacing: 16,
                          mainAxisSpacing: 16,
                        ),
                        itemBuilder: (context, index) {
                          final book = books[index];
                          return BookCard(
                            book: book,
                            onOpen: () => Navigator.of(context).push<void>(
                              PageRouteBuilder<void>(
                                pageBuilder: (_, __, ___) =>
                                    BookDetailPage(bookId: book.id),
                              ),
                            ),
                          );
                        },
                      ),
                  },
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Future<void> _openImportDialog(BuildContext context) async {
    final book = await showImportBookDialog(context);
    if (book != null && context.mounted) {
      await Navigator.of(context).push<void>(
        PageRouteBuilder<void>(
          pageBuilder: (_, __, ___) => BookDetailPage(bookId: book.id),
        ),
      );
    }
  }
}

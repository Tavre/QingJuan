import 'package:flutter/foundation.dart';

import '../../core/api/api_client.dart';
import '../../core/models/book.dart';
import '../../core/state/load_state.dart';

class LibraryController extends ChangeNotifier {
  LibraryController(this.api);

  final ApiClient api;
  LoadState state = LoadState.idle;
  List<Book> books = const [];
  String query = '';
  String? error;

  List<Book> get filteredBooks {
    final needle = query.trim().toLowerCase();
    if (needle.isEmpty) return books;
    return books
        .where(
          (book) =>
              book.title.toLowerCase().contains(needle) ||
              book.synopsis.toLowerCase().contains(needle),
        )
        .toList();
  }

  Future<void> load({bool silent = false}) async {
    if (!silent) {
      state = LoadState.loading;
      error = null;
      notifyListeners();
    }
    try {
      books = await api.fetchBooks();
      state = books.isEmpty ? LoadState.empty : LoadState.ready;
    } catch (exception) {
      error = '$exception';
      state = LoadState.error;
    }
    notifyListeners();
  }

  void setQuery(String value) {
    if (query == value) return;
    query = value;
    notifyListeners();
  }

  Future<BookPreview> preview(JsonMap payload) => api.previewBook(payload);

  Future<Book> import(JsonMap payload) async {
    final book = await api.importBook(payload);
    await load(silent: true);
    return book;
  }

  Future<Book> importLocal({
    required String filePath,
    required String kind,
    required String language,
    required bool translate,
    String? title,
  }) async {
    final book = await api.importLocalBook(
      filePath: filePath,
      kind: kind,
      language: language,
      translate: translate,
      title: title,
    );
    await load(silent: true);
    return book;
  }

  Future<void> delete(String bookId) async {
    await api.deleteBook(bookId);
    books = books.where((book) => book.id != bookId).toList();
    state = books.isEmpty ? LoadState.empty : LoadState.ready;
    notifyListeners();
  }
}

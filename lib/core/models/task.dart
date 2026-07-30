import 'book.dart';

class BookTask {
  const BookTask({
    required this.id,
    required this.bookId,
    required this.type,
    required this.status,
    required this.totalCount,
    required this.completedCount,
    required this.progress,
    required this.message,
    required this.attempts,
    required this.updatedAt,
    this.error,
  });

  factory BookTask.fromJson(JsonMap json) => BookTask(
        id: json['id'] as String? ?? '',
        bookId: json['bookId'] as String? ?? '',
        type: json['taskType'] as String? ?? '',
        status: json['status'] as String? ?? 'queued',
        totalCount: (json['totalCount'] as num?)?.toInt() ?? 0,
        completedCount: (json['completedCount'] as num?)?.toInt() ?? 0,
        progress: (json['progress'] as num?)?.toDouble() ?? 0,
        message: json['message'] as String? ?? '',
        attempts: (json['attempts'] as num?)?.toInt() ?? 0,
        updatedAt: json['updatedAt'] as String? ?? '',
        error: json['error'] as String?,
      );

  final String id;
  final String bookId;
  final String type;
  final String status;
  final int totalCount;
  final int completedCount;
  final double progress;
  final String message;
  final int attempts;
  final String updatedAt;
  final String? error;
}

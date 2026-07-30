import 'package:fluent_ui/fluent_ui.dart';

import '../../app/app_scope.dart';
import '../../core/models/task.dart';
import '../../core/state/load_state.dart';
import '../../shared/feedback_widgets.dart';
import '../../shared/page_frame.dart';

class TasksPage extends StatelessWidget {
  const TasksPage({super.key});

  @override
  Widget build(BuildContext context) {
    final controller = AppScope.of(context).tasks;
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) => PageFrame(
        title: '任务',
        subtitle: '查看下载、翻译与失败重试进度。',
        scrollable: false,
        command: IconButton(
          icon: const Icon(FluentIcons.refresh),
          onPressed: controller.load,
        ),
        child: Expanded(
          child: switch (controller.state) {
            LoadState.idle ||
            LoadState.loading =>
              const LoadingView(label: '正在同步任务'),
            LoadState.error => ErrorView(
                message: controller.error ?? '未知错误',
                onRetry: controller.load,
              ),
            LoadState.empty => const EmptyView(
                icon: FluentIcons.history,
                title: '暂无任务',
                message: '从作品详情页创建下载或翻译任务后，进度会显示在这里。',
              ),
            _ => ListView.builder(
                cacheExtent: 360,
                itemCount: controller.tasks.length,
                itemBuilder: (context, index) =>
                    _TaskTile(task: controller.tasks[index]),
              ),
          },
        ),
      ),
    );
  }
}

class _TaskTile extends StatelessWidget {
  const _TaskTile({required this.task});

  final BookTask task;

  @override
  Widget build(BuildContext context) {
    final theme = FluentTheme.of(context);
    final controller = AppScope.of(context).tasks;
    final failed = task.status == 'failed';
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: theme.cardColor,
        border: Border.all(color: theme.resources.cardStrokeColorDefault),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Icon(task.type == 'translate'
                  ? FluentIcons.locale_language
                  : FluentIcons.download),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  task.type == 'translate' ? '翻译任务' : '下载任务',
                  style: theme.typography.bodyLarge
                      ?.copyWith(fontWeight: FontWeight.w600),
                ),
              ),
              Text('${task.completedCount} / ${task.totalCount}'),
              if (failed) ...<Widget>[
                const SizedBox(width: 10),
                Button(
                    onPressed: () => controller.retry(task.id),
                    child: const Text('重试')),
              ],
            ],
          ),
          const SizedBox(height: 10),
          ProgressBar(value: (task.progress * 100).clamp(0, 100)),
          const SizedBox(height: 8),
          Text(task.error ?? task.message, style: theme.typography.caption),
        ],
      ),
    );
  }
}

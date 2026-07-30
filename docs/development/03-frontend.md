# Flutter 客户端开发规范

## 1. Dart 基本规则

- 遵循 `flutter_lints`，不得无理由忽略 analyzer 警告。
- 提交前执行 `dart format`，不手工对齐空格。
- 默认使用 `final`；确实需要重新赋值时才使用 `var`。
- 公共 API 声明明确类型；避免 `dynamic`，解析 JSON 时逐字段校验。
- 异步函数返回具体 `Future<T>`，不丢弃 Future；刻意后台执行时使用 `unawaited`。
- 空安全是领域约束的一部分，不通过大量 `!` 绕过。
- 构造函数尽可能 `const`。

## 2. Widget 边界

页面负责布局与把用户事件交给 Controller，不直接实现网络或复杂业务。建议结构：

```dart
class LibraryPage extends StatefulWidget {
  const LibraryPage({super.key});
}

class _LibraryPageState extends State<LibraryPage> {
  @override
  Widget build(BuildContext context) {
    final controller = AppScope.of(context).libraryController;
    return PageFrame(
      title: '书架',
      child: _LibraryContent(controller: controller),
    );
  }
}
```

拆分标准：

- 可独立命名、复用或测试的视觉区块提取为 Widget。
- 对话框放在独立文件或清晰的私有 Widget 中。
- 大列表条目使用独立 Widget，避免在 `itemBuilder` 中堆积复杂树。
- 只为缩短文件而抽取无语义的一行 Widget 没有价值。

Widget 不应：

- 创建 `http.Client` 或 `Process`；
- 读写 `SharedPreferences`；
- 解析后端 JSON；
- 持有全局单例；
- 在 `build` 中发起请求或改变状态。

## 3. Controller 与状态

Controller 表达一个功能域的用例和可观察状态：

- 通过构造函数注入 `ApiClient` 等依赖。
- 状态变化后统一通知监听者。
- 暴露只读集合，不让页面任意修改内部列表。
- 防止重复加载、并发保存和销毁后的通知。
- 将后端错误归一化为用户可理解的状态。
- `dispose` 中停止 Timer、订阅和其他资源。

全局 `AppState` 只保存真正跨功能的内容，例如主题、当前导航位置和后端地址。
书架、任务、书源、设置分别由自己的 Controller 管理；不得把所有状态塞入一个全局类。

## 4. API 与模型

`ApiClient` 负责：

- 基础 URL、超时和请求头；
- JSON 编解码；
- HTTP 状态码到 `ApiException` 的映射；
- 健康检查和资源 API。

领域 Model 负责：

- 从已验证的 JSON 创建类型安全对象；
- 提供不可变字段和必要的值转换；
- 不依赖 Flutter Widget 或 `BuildContext`。

规则：

- URL 使用 `Uri` 组合，不用字符串拼接。
- 每个请求设置有限超时。
- 非 2xx 读取后端 `detail`，但不能泄露响应中的敏感字段。
- 文件路径使用 `path` 包，Windows 路径不手工拼接斜杠。
- API 字段变化必须同步更新后端模型、客户端模型和契约测试。

## 5. 依赖注入与应用启动

`QingJuanApp` 是组合根，按顺序：

1. 初始化 Flutter；
2. 读取持久化偏好；
3. 创建 API 客户端；
4. 检查或启动本地后端；
5. 创建各 Feature Controller；
6. 加载首屏必要数据；
7. 渲染 `FluentApp`。

依赖通过 `AppScope` 或明确构造参数下发。禁止 Service Locator、隐藏全局变量和在 Feature 内重复创建基础设施对象。

## 6. 导航

- 顶层导航统一由 `NavigationView` 管理。
- 书籍详情和阅读器属于内容层级，不复制一套侧栏。
- 导航目标使用类型或稳定索引，不散落字符串。
- 页面离开时保存必要阅读进度并释放资源。
- 窄窗口仍使用 Fluent 紧凑窗格，不切换移动端底部导航。

## 7. 持久化

- 轻量客户端偏好可存 `SharedPreferences`：主题、后端地址、最后导航位置。
- 书籍、任务、凭据和阅读进度由后端 SQLite 管理。
- 不在多个位置存同一权威数据。
- 设置保存采用“后端成功后更新本地状态”，失败时保留用户输入并提示。

## 8. 错误与生命周期

- 捕获可预期异常并显示操作建议。
- 不使用空 `catch`；忽略错误时写明原因。
- `mounted` 检查应出现在异步 UI 回调返回后。
- 后端不可用时应用仍应显示诊断和重新连接入口。
- 应用只终止自己启动的后端，不杀死用户手动启动或其他程序占用端口的进程。

## 9. 客户端评审清单

- [ ] 文件和类职责单一，未形成巨型页面或 Controller。
- [ ] Widget 未直接进行 HTTP、进程或持久化操作。
- [ ] JSON 与空值边界有类型保护。
- [ ] 异步状态、重复点击和 dispose 场景正确。
- [ ] 主题、窄窗口、键盘与错误态已验证。
- [ ] 单元和 Widget 测试覆盖新增行为。
- [ ] `dart format`、`flutter analyze`、`flutter test` 全部通过。

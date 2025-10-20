# 分批传输 Diff 内容的优化方案

## 问题背景

在使用 Claude API 分析大型 PR 时,当 `diff_section` 内容过大时,会导致以下错误:
```
This error originated either by throwing inside of an async function without a catch block,
or by rejecting a promise which was not handled with .catch()
```

原因是单次 API 调用的内容超过了限制。

## 解决方案

采用**分批传输策略**,将大型内容分成多个小批次,通过多轮对话逐步传给 Claude。

### 核心改进

#### 1. 分离基本信息和 Diff 内容

**之前的问题**: 每次传输都重复发送 PR 的基本信息(标题、描述、创建时间等),浪费 token。

**优化后**:
- **第1步**: 单独发送 PR 基本信息(标题、描述、评论等)
- **第2步**: 只发送 diff 内容,分多批传输
- **第3步**: 发送分析请求

#### 2. 智能分割 Diff

```python
def split_diff_into_chunks(self, diff_content: str, max_chunk_size: int = 8000) -> list[str]:
    """
    将大型diff分割成多个块,按文件边界分割,避免截断单个文件的diff
    """
```

特点:
- 按文件边界分割,保持每个文件 diff 的完整性
- 如果单个文件超过限制,再进行进一步分割
- 默认每块最大 8000 字符(约 2000 tokens)

#### 3. 统一分批发送

**移除了** `use_chunked_diff` 参数,所有 PR 分析统一使用分批发送策略。

## 使用方法

### 基本使用

```python
from pr_analysis_with_claude import PRAnalysisWithClaude

analyzer = PRAnalysisWithClaude()

# 分析指定PR (自动使用分批传输)
result = await analyzer.analyze_single_pr(pr_number=14591)

if result["success"]:
    print(f"分析成功!")
    print(f"使用了 {result['diff_chunks_count']} 个diff批次")
    print(f"分析结果: {result['analysis']}")
```

### 传输流程示例

假设一个 PR 有 25000 字符的 diff:

```
Step 1: 发送基本信息
  📤 发送: PR #14591 的标题、描述、评论等 (约 2000 字符)
  ✓ Claude 确认收到

Step 2: 分批发送 Diff (分为 4 批)
  📤 第 1/4 批: 8000 字符
  ✓ Claude 确认收到

  📤 第 2/4 批: 8000 字符
  ✓ Claude 确认收到

  📤 第 3/4 批: 8000 字符
  ✓ Claude 确认收到

  📤 第 4/4 批: 1000 字符 (最后一部分)
  ✓ Claude 确认收到

Step 3: 请求分析
  📤 发送分析问题(6个维度)
  📥 接收完整分析结果
```

## 代码结构

### 主要方法

1. **`split_diff_into_chunks()`** - 智能分割 diff
2. **`build_basic_info_query()`** - 构建基本信息查询
3. **`build_diff_chunk_query()`** - 构建单个 diff 块查询
4. **`analyze_single_pr()`** - 执行完整的分批分析流程

### 工作流程

```
analyze_single_pr()
  ├─ 获取 PR 数据
  ├─ 分割 diff 内容
  ├─ 发送基本信息 → 等待确认
  ├─ 循环发送 diff 块
  │   ├─ 发送块 1 → 等待确认
  │   ├─ 发送块 2 → 等待确认
  │   └─ ...
  └─ 发送分析请求 → 收集结果
```

## 优势

### ✅ 相比截断方式

| 对比项 | 截断方式 | 分批传输 |
|--------|---------|---------|
| 信息完整性 | ❌ 丢失部分内容 | ✅ 保留所有信息 |
| 分析准确性 | ⚠️ 可能不准确 | ✅ 基于完整信息 |
| 处理大 PR | ❌ 无法处理超大 PR | ✅ 可处理任意大小 |
| Token 效率 | ✅ 单次调用 | ⚠️ 多次调用 |

### ✅ 相比原实现

- 避免重复发送基本信息,节省 token
- 清晰的三步流程,便于调试
- 每步都有确认,减少错误
- 无需手动选择是否分批

## 测试

### 运行测试

```bash
# 测试完整分析流程
python test_chunked_diff.py
# 选择: 1

# 仅测试分割算法
python test_chunked_diff.py
# 选择: 2
```

### 测试场景

1. **小型 PR** (diff < 8000 字符)
   - 基本信息 + 1个diff块 + 分析请求 = 3轮

2. **中型 PR** (8000 < diff < 24000 字符)
   - 基本信息 + 2-3个diff块 + 分析请求 = 4-5轮

3. **大型 PR** (diff > 24000 字符)
   - 基本信息 + N个diff块 + 分析请求 = N+2轮

## 配置选项

可以在 `analyze_single_pr()` 中调整:

```python
# 调整每个块的大小 (默认 8000 字符)
diff_chunks = split_diff_into_chunks(
    diff_content,
    max_chunk_size=8000  # 可调整
)

# 调整最大轮次 (默认 50)
ClaudeCodeOptions(
    max_turns=50  # 可调整
)
```

## 监控和调试

代码中包含详细的日志输出:

```
📦 Diff 将分为 3 个部分进行传输
📊 基本信息大小: 1,234 字符 (~308 tokens)
📤 正在发送PR基本信息...
✓ Claude确认: 我已收到PR的基本信息...

📊 Diff第1/3批大小: 8,000 字符
📤 正在发送Diff第1批...
✓ Claude确认: 已收到第一部分diff...

...

=== 分析完成 (基本信息 + 3 批diff + 分析请求) ===
```

## 注意事项

1. **API 调用次数**: 分批传输会增加 API 调用次数,请注意配额
2. **响应时间**: 总体响应时间会略微增加
3. **网络稳定性**: 需要稳定的网络连接完成多轮对话
4. **Token 消费**: 虽然单次减少,但总量可能略微增加

## 未来优化方向

1. **并行传输**: 探索是否可以并行发送多个 diff 块
2. **智能压缩**: 对 diff 内容进行智能压缩(去除空白行等)
3. **断点续传**: 如果传输中断,支持从断点继续
4. **自适应分块**: 根据网络状况动态调整块大小

## 版本历史

- **v2.0** (2025-01-XX): 分离基本信息和 diff,移除 use_chunked_diff 参数
- **v1.0** (2025-01-XX): 初始版本,支持分批传输

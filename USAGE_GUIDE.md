# IoTDB PR分析工具 - 快速使用指南

## 完整工作流程

### 步骤1: 安装依赖

```bash
pip install -r requirements.txt
```

### 步骤2: 分析PR并保存到向量数据库

```bash
# 分析单个PR
python analyze_pr_claude.py --pr 16487

# 分析并保存到JSON文件
python analyze_pr_claude.py --pr 16487 --output pr_16487_analysis.json
```

输出示例:
```
✅ PR分析器初始化成功
正在加载embedding模型...
向量数据库已初始化: ./chroma_db
✅ 向量数据库已启用

🔍 正在分析 PR #16487...
正在分析 PR #16487: Fix jdbc feature.xml error

=== Claude 分析结果 ===
...

💾 正在将分析结果写入向量数据库...
✅ PR #16487 分析结果已添加到向量数据库 (6 个文档块)

================================================================================
PR #16487: Fix jdbc feature.xml error
================================================================================
✅ 分析完成于: 2025-10-18T20:38:57.352765
💾 已保存到向量数据库

📋 分析结果:
------------------------------------------------------------
...
```

### 步骤3: 搜索相关PR分析

```bash
# 基本搜索
python search_pr_analysis.py search "JDBC配置问题"

# 查看相似度分数
python search_pr_analysis.py search "Maven构建错误" --with-score

# 显示完整内容
python search_pr_analysis.py search "feature.xml" --full --top-k 3
```

### 步骤4: 查看数据库状态

```bash
python search_pr_analysis.py stats
```

## 实际应用场景

### 场景1: 查找类似问题的历史PR

当客户报告一个问题时，可以快速搜索是否有类似的PR已经修复过:

```bash
python search_pr_analysis.py search "客户报告的错误信息或症状" --with-score
```

### 场景2: 技术调研

想了解某个技术组件的相关修复:

```bash
python search_pr_analysis.py search "JDBC连接池" --top-k 10
```

### 场景3: 影响分析

评估某个修复对系统的影响:

```bash
python search_pr_analysis.py search "性能优化 内存泄漏" --with-score
```

### 场景4: 批量分析多个PR

```bash
# 分析多个PR
for pr in 16487 16488 16489; do
    python analyze_pr_claude.py --pr $pr
done

# 然后搜索相关主题
python search_pr_analysis.py search "你关心的主题"
```

## 测试向量数据库功能

运行完整的测试套件:

```bash
python test_vector_store.py
```

这会测试:
- 添加PR分析到向量数据库
- 语义搜索功能
- 相似度评分
- 元数据过滤

## 目录结构

```
.
├── analyze_pr_claude.py        # 主分析脚本
├── pr_analysis_with_claude.py  # 分析核心逻辑
├── vector_store.py              # 向量数据库管理
├── search_pr_analysis.py        # 搜索工具
├── test_vector_store.py         # 测试脚本
├── database.py                  # MySQL数据库
├── chroma_db/                   # 向量数据库存储目录
│   └── (自动生成的向量数据)
├── requirements.txt             # 依赖列表
├── VECTOR_STORE_README.md       # 向量数据库详细文档
└── USAGE_GUIDE.md               # 本文件
```

## 提示和技巧

1. **首次运行较慢**: 第一次使用会下载embedding模型(约420MB)，后续运行会很快

2. **搜索技巧**:
   - 使用描述性短语: "JDBC连接超时问题"
   - 而非单个关键词: "jdbc"

3. **批量操作**: 可以编写脚本批量分析所有PR

4. **数据备份**: 定期备份 `./chroma_db` 目录

5. **性能调优**: 如果内存不足，可以在 `vector_store.py` 中调小chunk_size

## 常见问题

**Q: 向量数据库和MySQL有什么区别?**

A:
- MySQL: 存储原始PR数据(标题、描述、diff等)
- Chroma: 存储Claude分析结果的向量表示，支持语义搜索
- 用途不同，互为补充

**Q: 可以不使用向量数据库吗?**

A: 可以。在代码中设置 `use_vector_store=False`:
```python
analyzer = PRAnalysisWithClaude(use_vector_store=False)
```

**Q: 搜索结果不准确怎么办?**

A:
1. 尝试调整搜索关键词
2. 增加返回结果数 `--top-k`
3. 使用 `--with-score` 查看相似度分数

**Q: 如何清空向量数据库?**

A: 删除 `./chroma_db` 目录即可

## 下一步

- 阅读 `VECTOR_STORE_README.md` 了解更多高级功能
- 查看 `vector_store.py` 源码了解实现细节
- 根据需要定制搜索和存储逻辑

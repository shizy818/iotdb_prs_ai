# IoTDB PR分析工具 - 向量数据库集成 🚀

> 使用LangChain和Chroma向量数据库实现PR分析结果的智能存储和语义搜索

## ✨ 新功能亮点

- 🤖 **自动化存储**: PR分析结果自动保存到向量数据库
- 🔍 **语义搜索**: 基于意图理解的智能搜索，而非简单关键词匹配
- 📊 **相似度评分**: 量化搜索结果的相关性
- 🎯 **精准过滤**: 支持基于元数据的条件筛选
- 💾 **持久化**: 本地存储，支持离线查询
- 🌏 **多语言**: 支持中英文混合搜索

## 🚀 快速开始

### 1️⃣ 安装依赖

```bash
pip install -r requirements.txt
```

这会安装：
- `langchain` - LangChain框架
- `chromadb` - Chroma向量数据库
- `sentence-transformers` - 文本向量化模型

### 2️⃣ 分析PR

```bash
# 分析单个PR（自动保存到向量数据库）
python analyze_pr_claude.py --pr 16487
```

输出示例：
```
✅ PR分析器初始化成功
向量数据库已初始化: ./chroma_db
✅ 向量数据库已启用

🔍 正在分析 PR #16487...
💾 正在将分析结果写入向量数据库...
✅ PR #16487 分析结果已添加到向量数据库 (6 个文档块)
💾 已保存到向量数据库
```

### 3️⃣ 搜索相关PR

```bash
# 基本搜索
python search_pr_analysis.py search "JDBC配置问题"

# 显示相似度分数
python search_pr_analysis.py search "Maven构建错误" --with-score

# 返回更多结果
python search_pr_analysis.py search "Karaf部署" --top-k 10
```

### 4️⃣ 查看统计

```bash
python search_pr_analysis.py stats
```

## 📖 使用场景

### 场景1: 快速定位类似问题

当客户报告一个bug时，快速查找是否有类似问题已被修复：

```bash
python search_pr_analysis.py search "连接超时 JDBC" --with-score
```

### 场景2: 技术调研

了解某个组件的历史修复记录：

```bash
python search_pr_analysis.py search "性能优化 查询引擎" --top-k 20
```

### 场景3: 影响评估

评估某类修复对系统的影响范围：

```bash
python search_pr_analysis.py search "内存泄漏 稳定性" --with-score
```

## 🎯 搜索示例

### 示例1: 语义理解

```bash
# 查询: "如何修复JDBC连接问题"
# 能匹配包含以下内容的PR:
# - "JDBC驱动配置错误"
# - "连接池超时修复"
# - "数据库连接异常处理"
```

即使关键词不完全匹配，也能找到语义相关的PR！

### 示例2: 带评分的搜索

```bash
$ python search_pr_analysis.py search "构建失败" --with-score

结果 #1 - 相似度: 0.3245
PR #16487: Fix jdbc feature.xml error
内容片段: Maven构建配置中feature.xml文件路径错误...

结果 #2 - 相似度: 0.2891
PR #16488: Update build configuration
内容片段: 修复了pom.xml中的依赖冲突问题...
```

## 🛠️ 工具脚本

| 脚本 | 用途 |
|------|------|
| `vector_store.py` | 向量数据库核心模块 |
| `search_pr_analysis.py` | 命令行搜索工具 |
| `test_vector_store.py` | 功能测试脚本 |
| `demo_workflow.py` | 完整流程演示 |

## 📚 文档

| 文档 | 内容 |
|------|------|
| `USAGE_GUIDE.md` | 快速使用指南 |
| `VECTOR_STORE_README.md` | 详细技术文档 |
| `IMPLEMENTATION_SUMMARY.md` | 实现总结 |

## 🧪 测试

运行完整测试：

```bash
python test_vector_store.py
```

运行演示：

```bash
python demo_workflow.py
```

## ⚙️ 技术架构

```
┌─────────────────────────────────────────────────┐
│              PR数据 (MySQL)                      │
└────────────────┬────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────┐
│     PRAnalysisWithClaude.analyze_single_pr()     │
│              (调用Claude分析)                     │
└────────────────┬────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────┐
│            Claude分析结果 (文本)                  │
└────────────────┬────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────┐
│      VectorStoreManager.add_pr_analysis()        │
│         (文本分块 + 向量化)                       │
└────────────────┬────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────┐
│         Chroma向量数据库 (./chroma_db)           │
│              (持久化存储)                         │
└─────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────┐
│      语义搜索 (VectorStoreManager.search)        │
│         (查询 → 向量化 → 相似度匹配)              │
└─────────────────────────────────────────────────┘
```

## 🔧 高级用法

### 编程接口

```python
from vector_store import VectorStoreManager

# 初始化
vector_store = VectorStoreManager()

# 添加分析
vector_store.add_pr_analysis(
    pr_number=16487,
    pr_title="Fix jdbc feature.xml error",
    analysis="详细分析内容...",
    metadata={"labels": ["bug", "jdbc"]}
)

# 搜索
results = vector_store.search_similar_prs("JDBC问题", k=5)

# 带分数搜索
results = vector_store.search_with_score("构建错误", k=5)
for doc, score in results:
    print(f"PR #{doc.metadata['pr_number']} - Score: {score:.4f}")

# 删除
vector_store.delete_pr_analysis(pr_number=16487)
```

### 禁用向量数据库

如果不需要向量数据库功能：

```python
analyzer = PRAnalysisWithClaude(use_vector_store=False)
```

## 💡 提示和技巧

1. **首次运行较慢**: 需要下载embedding模型(约420MB)
2. **搜索技巧**: 使用描述性短语效果更好
   - ✅ "JDBC连接超时问题"
   - ❌ "jdbc"
3. **批量操作**: 可批量分析多个PR丰富数据库
4. **数据备份**: 定期备份 `./chroma_db` 目录

## ❓ 常见问题

**Q: 向量数据库和MySQL有什么区别？**

A:
- **MySQL**: 存储原始PR数据（标题、描述、diff、评论等）- 精确查询
- **Chroma**: 存储Claude分析结果的向量表示 - 语义搜索
- 两者互补，各司其职

**Q: 如何清空向量数据库？**

A: 删除 `./chroma_db` 目录即可

**Q: 搜索结果不准确怎么办？**

A:
1. 调整搜索关键词，使用更描述性的短语
2. 增加返回结果数 `--top-k`
3. 使用 `--with-score` 查看相似度分数

## 📈 性能指标

- **模型大小**: 420MB
- **首次加载**: 10-30秒
- **后续启动**: <5秒
- **搜索速度**: <1秒
- **存储开销**: 原始文本的2-3倍

## 🎓 学习资源

- [LangChain官方文档](https://python.langchain.com/)
- [Chroma官方文档](https://docs.trychroma.com/)
- [Sentence Transformers](https://www.sbert.net/)

## 📝 更新日志

### v1.0.0 (2025-10-19)
- ✅ 集成LangChain + Chroma向量数据库
- ✅ 实现自动PR分析存储
- ✅ 实现语义搜索功能
- ✅ 添加命令行搜索工具
- ✅ 完整的测试和文档

## 🤝 贡献

欢迎提交Issue和Pull Request！

## 📄 许可

与主项目相同。

---

**开始使用**: `python demo_workflow.py`

**获取帮助**: 查看 `USAGE_GUIDE.md`

**深入了解**: 阅读 `VECTOR_STORE_README.md`

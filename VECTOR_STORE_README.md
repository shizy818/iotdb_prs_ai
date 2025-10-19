# PR分析向量数据库使用指南

本项目集成了LangChain和Chroma向量数据库，用于存储和检索PR分析结果，支持语义搜索功能。

## 功能特性

- ✅ 自动将Claude分析结果存储到向量数据库
- ✅ 支持语义搜索，而非简单的关键词匹配
- ✅ 文档自动分块，提高检索精度
- ✅ 支持相似度评分和元数据过滤
- ✅ 持久化存储，可离线查询

## 安装依赖

```bash
pip install -r requirements.txt
```

主要依赖:
- `langchain`: LangChain框架
- `langchain-community`: LangChain社区扩展
- `chromadb`: Chroma向量数据库
- `sentence-transformers`: 文本向量化模型

## 快速开始

### 1. 分析PR并自动保存到向量数据库

```bash
# 分析指定PR (默认启用向量数据库)
python analyze_pr_claude.py --pr 16487

# 分析并保存到JSON文件
python analyze_pr_claude.py --pr 16487 --output pr_16487_analysis.json
```

分析完成后，结果会自动保存到 `./chroma_db` 目录。

### 2. 搜索PR分析结果

```bash
# 基本搜索
python search_pr_analysis.py search "JDBC配置问题"

# 带相似度分数的搜索
python search_pr_analysis.py search "Maven构建错误" --with-score

# 返回更多结果
python search_pr_analysis.py search "Karaf部署问题" --top-k 10

# 显示完整内容
python search_pr_analysis.py search "feature.xml路径" --full
```

### 3. 查看数据库统计

```bash
python search_pr_analysis.py stats
```

## 使用示例

### 示例1: 搜索JDBC相关问题

```bash
$ python search_pr_analysis.py search "JDBC驱动问题" --with-score

🔍 搜索查询: JDBC驱动问题
📊 返回结果数: 5
📚 数据库包含 12 个文档

找到 5 个相关结果:

================================================================================
结果 #1 - 相似度: 0.3245
================================================================================
PR编号: #16487
PR标题: Fix jdbc feature.xml error
分析时间: 2025-10-18T20:38:57.352765
文档块: 1/6

内容片段
--------------------------------------------------------------------------------
PR #16487: Fix jdbc feature.xml error

我将从IoTDB JDBC客户端构建配置的角度,对这个PR进行详细的技术分析...
```

### 示例2: 查找构建错误相关的PR

```bash
python search_pr_analysis.py search "构建失败 Maven错误" --top-k 3
```

### 示例3: 在代码中使用向量数据库

```python
from vector_store import VectorStoreManager

# 初始化向量数据库
vector_store = VectorStoreManager()

# 添加PR分析
vector_store.add_pr_analysis(
    pr_number=16487,
    pr_title="Fix jdbc feature.xml error",
    analysis="详细的分析内容...",
    metadata={"labels": ["bug", "jdbc"]}
)

# 语义搜索
results = vector_store.search_similar_prs("JDBC配置问题", k=5)
for result in results:
    print(f"PR #{result['pr_number']}: {result['pr_title']}")
    print(result['content'][:200])
```

## 测试功能

运行测试脚本验证向量数据库功能:

```bash
python test_vector_store.py
```

测试内容包括:
1. 基本CRUD操作
2. 语义搜索
3. 带相似度分数的搜索
4. 元数据过滤搜索

## 向量数据库架构

### 数据结构

每个PR分析被分成多个文档块存储:

```
PR #16487
  ├─ chunk_0: PR基本信息 + 分析开头
  ├─ chunk_1: 分析内容片段1
  ├─ chunk_2: 分析内容片段2
  └─ chunk_N: 分析内容片段N
```

### 元数据字段

每个文档块包含以下元数据:
- `pr_number`: PR编号
- `pr_title`: PR标题
- `analyzed_at`: 分析时间
- `source`: 来源 (claude_analysis)
- `chunk_id`: 唯一块标识
- `chunk_index`: 块索引
- `total_chunks`: 总块数
- `labels`: PR标签
- `user`: PR作者
- `merged_at`: 合并时间

### 文本分块策略

- **块大小**: 1000字符
- **重叠**: 200字符
- **分隔符**: 优先按段落、句子分割
- **目的**: 提高检索精度和上下文保持

## 高级功能

### 1. 使用元数据过滤

```python
# 只搜索特定PR编号的分析
results = vector_store.search_similar_prs(
    "配置问题",
    k=5,
    filter_dict={"pr_number": 16487}
)
```

### 2. 获取相似度分数

```python
# 返回文档和相似度分数
results = vector_store.search_with_score("构建错误", k=5)
for doc, score in results:
    print(f"Score: {score:.4f} - PR #{doc.metadata['pr_number']}")
```

### 3. 删除PR分析

```python
# 删除特定PR的所有分析数据
vector_store.delete_pr_analysis(pr_number=16487)
```

### 4. 禁用向量数据库

如果不需要向量数据库功能:

```python
# 在代码中禁用
analyzer = PRAnalysisWithClaude(use_vector_store=False)
```

## 性能优化

### Embedding模型

默认使用 `paraphrase-multilingual-MiniLM-L12-v2` 模型:
- ✅ 支持中英文
- ✅ 模型较小 (约420MB)
- ✅ CPU友好
- ✅ 质量和速度平衡

如需更高精度，可在 `vector_store.py` 中修改模型:

```python
self.embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/paraphrase-multilingual-mpnet-base-v2",  # 更大更准确
    # 或使用中文专用模型
    # model_name="shibing624/text2vec-base-chinese",
)
```

### 持久化

向量数据库自动持久化到 `./chroma_db` 目录:
- 首次加载模型较慢 (下载+初始化)
- 后续启动直接加载本地数据
- 支持增量更新

## 故障排查

### 问题1: 模型下载失败

```bash
# 手动下载模型
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"
```

### 问题2: 内存不足

减小分块大小或使用更小的模型:

```python
# 在 vector_store.py 中修改
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,  # 从1000减小到500
    chunk_overlap=100,
)
```

### 问题3: 搜索结果不准确

- 增加返回结果数 `k` 值
- 调整查询关键词
- 检查元数据过滤条件

## 与MySQL数据库的关系

- **MySQL**: 存储原始PR数据、diff、评论
- **Chroma向量数据库**: 存储Claude分析结果的向量表示
- **用途**:
  - MySQL: 结构化查询、精确匹配
  - Chroma: 语义搜索、模糊匹配、智能推荐

两者互补，各司其职。

## 最佳实践

1. **定期分析新PR**: 保持向量数据库更新
2. **使用描述性查询**: 例如"JDBC配置问题"比"jdbc"效果更好
3. **结合元数据过滤**: 提高搜索精度
4. **备份数据库**: 定期备份 `./chroma_db` 目录
5. **监控性能**: 关注嵌入生成和搜索时间

## 参考资料

- [LangChain文档](https://python.langchain.com/)
- [Chroma文档](https://docs.trychroma.com/)
- [Sentence Transformers](https://www.sbert.net/)

## 许可

与主项目相同。

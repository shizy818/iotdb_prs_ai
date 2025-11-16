# IoTDB PR智能助手

基于GLM-4.6模型的IoTDB PR智能分析系统，提供自然语言查询和推荐功能。

## 🚀 快速开始

### 1. 环境准备

**Python依赖安装**
```bash
pip install -r requirements.txt
```

**Clone IoTDB项目**
```bash
git clone https://github.com/apache/iotdb.git
```

**MySQL数据库配置**
```bash
# 安装MySQL数据库
sudo apt-get install mysql-server  # Ubuntu/Debian
brew install mysql                  # macOS
# 或下载MySQL Community Server

# 启动MySQL服务
sudo systemctl start mysql  # Linux
brew services start mysql  # macOS
```

**下载MiniLM模型**
```bash
# 安装huggingface-cli
pip install huggingface_hub

# 使用CLI下载多语言MiniLM模型
huggingface-cli download sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 --local-dir ./models/paraphrase-multilingual-MiniLM-L12-v2
```

### 2. 数据准备

**拉取和分析PR数据**
```bash
# 拉取指定时间范围的PR数据
python scraper.py --since_date 2025-01-01 --days 30

# 分析指定时间范围的PR并存入向量数据库
python analysis_vectordb_chain.py --since_date 2025-01-01 --days 30
```

### 3. 启动应用

**命令行界面**
```bash
python chat_cli.py
```

**Web界面**
```bash
python chat_web_interface.py --host 0.0.0.0 --port 9000
```

## 📋 功能特性

- 🤖 **智能对话**: 基于GLM-4.6的自然语言交互
- 🔍 **PR搜索**: 支持关键词、版本号、技术问题等多种搜索方式
- 📊 **智能推荐**: 根据问题描述推荐最相关的PR
- 💬 **多界面**: 支持命令行和Web两种使用方式
- 🎯 **精准匹配**: 使用向量数据库实现语义搜索

## 💡 使用示例

### 命令行界面示例
```bash
# 启动CLI
python chat_cli.py

# 示例查询
💬 您: iotdb1.3.2版本遇到内存泄漏问题，请列出最相关的5个PR
🤖 助手: [基于搜索结果的相关PR推荐]

💬 您: 我想了解JDBC连接相关的问题
🤖 助手: [JDBC相关的PR分析结果]
```

### Web界面示例
1. 启动Web服务器: `python chat_web_interface.py`
2. 浏览器访问: `http://localhost:9000`
3. 在界面中输入自然语言查询

### 查询类型
- **版本问题**: "1.3.0版本有哪些重要的bug修复PR？"
- **技术问题**: "查询性能优化相关的PR"
- **具体PR**: "我想了解PR 16487的详细内容"
- **关键词搜索**: "搜索包含内存管理和TSFile的PR"

## 📁 项目结构

```
├── chat_application.py      # 命令行聊天应用主程序
├── chat_web_interface.py    # Web聊天界面
├── glm_chat_handler.py      # GLM-4.6聊天处理器
├── chat_vector_tool.py      # 向量数据库工具
├── scraper.py              # GitHub PR数据抓取器
├── pr_analysis_anthropic.py # Anthropic PR分析器
├── pr_analysis_langchain.py # LangChain PR分析器
├── analysis_vectordb_chain.py   # PR分析器并写入向量数据库
├── config.py               # 配置文件
├── requirements.txt        # Python依赖
└── chroma_db/             # 向量数据库存储目录
```

## ⚙️ 配置说明

在 `config.py` 中配置以下参数（参考 `config.py.example`）：

```python
# GLM API配置
ANTHROPIC_BASE_URL = "https://open.bigmodel.cn/api/anthropic"
ANTHROPIC_API_KEY = "your-api-key-here"

# GitHub配置
GITHUB_TOKEN = "ghp_your-github-token-here"

# IoTDB源码目录
DEFAULT_IOTDB_SOURCE_DIR = "/path/to/your/iotdb"

# MySQL数据库配置
DEFAULT_DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "your-password",
    "database": "iotdb_prs_db"
}

# 日志配置
LOG_LEVEL = "INFO"
LOG_FILE = "logs/iotdb_analysis.log"
LOG_OUTPUT = "both"

# 向量数据库路径
CHROMA_PERSIST_DIRECTORY = "./chroma_db"
```

## 🔧 数据更新

### 手动更新
```bash
# 抓取最新PR数据
python scraper.py --since 2025-01-01 --days 7

# 分析最新PR数据
python analysis_vectordb_chain.py --since 2025-01-01 --days 7
```

## 📊 数据库统计

获取数据库状态：
```bash
# CLI方式
python search_pr_analysis.py stats

# API方式
curl http://localhost:9000/stats
```

## 📝 系统要求

- Python 3.8+
- 内存: 4GB+
- 存储: 2GB+ (用于向量数据库)
- 网络: 稳定的互联网连接

## 🤝 贡献

欢迎提交Issue和Pull Request来改进这个项目！

## 📄 许可证

本项目采用Apache 2.0许可证。

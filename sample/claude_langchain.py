#!/usr/bin/env python3
"""
使用 LangChain 实现 Claude 对话的示例
相比 claude_sample.py 更加简洁和灵活
"""

import sys
from pathlib import Path

# 添加父目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
from langchain_anthropic import ChatAnthropic
from langchain.schema import HumanMessage, SystemMessage
from config import ANTHROPIC_BASE_URL, ANTHROPIC_API_KEY

# 配置智谱AI的Anthropic兼容接口
os.environ["ANTHROPIC_BASE_URL"] = ANTHROPIC_BASE_URL
os.environ["ANTHROPIC_API_KEY"] = ANTHROPIC_API_KEY


def main():
    """使用 LangChain 调用 Claude"""

    # 初始化 Claude 模型
    llm = ChatAnthropic(
        model="glm-4-plus",
        # model="claude-sonnet-4-5-20250929",
        temperature=0,
        max_tokens=8192,
        streaming=True,  # 启用流式输出
    )

    # 准备消息
    messages = [
        SystemMessage(content="您是一名时序数据库IoTDB专家。"),
        HumanMessage(content="你好"),
    ]

    print("正在查询Claude...\n")
    print("回答:")
    print("-" * 50)

    # 流式输出响应
    for chunk in llm.stream(messages):
        print(chunk.content, end="", flush=True)

    print("\n" + "-" * 50)


if __name__ == "__main__":
    main()

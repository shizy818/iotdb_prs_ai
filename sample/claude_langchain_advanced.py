#!/usr/bin/env python3
"""
使用 LangChain 的高级功能实现 Claude 对话
展示：对话历史、提示模板、链式调用等
"""

import sys
from pathlib import Path

# 添加父目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
from langchain_anthropic import ChatAnthropic
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.memory import ConversationBufferMemory
from langchain.chains import LLMChain
from config import ANTHROPIC_BASE_URL, ANTHROPIC_API_KEY

# 配置智谱AI的Anthropic兼容接口
os.environ["ANTHROPIC_BASE_URL"] = ANTHROPIC_BASE_URL
os.environ["ANTHROPIC_API_KEY"] = ANTHROPIC_API_KEY


def simple_chat_example():
    """示例1: 简单对话"""
    print("=" * 60)
    print("示例1: 简单对话")
    print("=" * 60)

    llm = ChatAnthropic(
        model="claude-sonnet-4-5-20250929", temperature=0, streaming=True
    )

    # 使用提示模板
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "您是一名时序数据库IoTDB专家。"),
            ("human", "{question}"),
        ]
    )

    # 创建链
    chain = prompt | llm

    # 流式输出
    print("\n问题: 分析SharedTsBlockQueue的作用\n")
    print("回答:")
    for chunk in chain.stream({"question": "分析SharedTsBlockQueue的作用"}):
        print(chunk.content, end="", flush=True)
    print("\n")


def conversation_with_memory():
    """示例2: 带记忆的多轮对话"""
    print("=" * 60)
    print("示例2: 带记忆的多轮对话")
    print("=" * 60)

    llm = ChatAnthropic(model="claude-sonnet-4-5-20250929", temperature=0)

    # 创建对话记忆
    memory = ConversationBufferMemory(return_messages=True, memory_key="chat_history")

    # 创建提示模板（包含对话历史）
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "您是一名时序数据库IoTDB专家。请简洁回答问题。"),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{question}"),
        ]
    )

    # 创建对话链
    chain = LLMChain(llm=llm, prompt=prompt, memory=memory, verbose=False)

    # 模拟多轮对话
    questions = [
        "SharedTsBlockQueue是什么?",
        "它有什么作用?",
        "它和普通队列有什么区别?",
    ]

    for i, question in enumerate(questions, 1):
        print(f"\n第{i}轮对话:")
        print(f"问: {question}")
        response = chain.predict(question=question)
        print(f"答: {response}")


def batch_processing_example():
    """示例3: 批量处理多个问题"""
    print("=" * 60)
    print("示例3: 批量处理")
    print("=" * 60)

    llm = ChatAnthropic(model="claude-sonnet-4-5-20250929", temperature=0)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "您是一名时序数据库IoTDB专家。请用一句话简洁回答。"),
            ("human", "{question}"),
        ]
    )

    chain = prompt | llm

    # 批量处理多个问题
    questions = [
        {"question": "什么是TsBlock?"},
        {"question": "什么是SharedTsBlockQueue?"},
        {"question": "IoTDB的存储引擎叫什么?"},
    ]

    print("\n批量处理3个问题:")
    results = chain.batch(questions)

    for i, (q, result) in enumerate(zip(questions, results), 1):
        print(f"\n问题{i}: {q['question']}")
        print(f"回答: {result.content}")


def with_structured_output():
    """示例4: 结构化输出（使用Function Calling）"""
    print("=" * 60)
    print("示例4: 结构化输出")
    print("=" * 60)

    from langchain_core.pydantic_v1 import BaseModel, Field

    # 定义输出结构
    class ComponentAnalysis(BaseModel):
        """IoTDB组件分析结果"""

        component_name: str = Field(description="组件名称")
        purpose: str = Field(description="主要用途")
        category: str = Field(description="类别（如：存储、查询、网络等）")
        importance: str = Field(description="重要性级别（高/中/低）")

    llm = ChatAnthropic(model="claude-3-5-sonnet-20241022", temperature=0)

    # 配置结构化输出
    structured_llm = llm.with_structured_output(ComponentAnalysis)

    # 发送请求
    result = structured_llm.invoke("分析SharedTsBlockQueue这个组件")

    print("\n结构化分析结果:")
    print(f"  组件名: {result.component_name}")
    print(f"  用途: {result.purpose}")
    print(f"  类别: {result.category}")
    print(f"  重要性: {result.importance}")


def main():
    """运行所有示例"""
    try:
        # 示例1: 简单对话
        simple_chat_example()

        # 示例2: 带记忆的对话
        # conversation_with_memory()

        # 示例3: 批量处理
        # batch_processing_example()

        # 示例4: 结构化输出
        # with_structured_output()

    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
使用 LangChain LCEL (LangChain Expression Language)
将 PR 分析和向量数据库存储串联起来

使用管道操作符: analyze_pr | save_to_vector_store
支持多种框架: langchain, claude_agent_sdk, anthropic
"""
import os
import asyncio
import argparse
from datetime import datetime, timedelta
from typing import Dict, Optional, Literal, List

from langchain_core.runnables import RunnableLambda, RunnablePassthrough

from pr_analysis_langchain import PRAnalysisLangChain
from pr_analysis_cc_sdk import PRAnalysisClaudeAgentSDK
from pr_analysis_anthropic import PRAnalysisAnthropic
from vector_store import VectorStoreManager
from database import DatabaseManager

os.environ["TOKENIZERS_PARALLELISM"] = "false"

# 框架类型定义
FrameworkType = Literal["langchain", "claude_agent_sdk", "anthropic"]


class PRAnalysisRunnable:
    """PR 分析的 Runnable 包装器 - 支持多种框架"""

    def __init__(
        self, framework: FrameworkType = "langchain", enable_tools: bool = True
    ):
        """
        初始化 PR 分析器

        Args:
            framework: 分析框架 ('langchain', 'claude_agent_sdk', 'anthropic')
            enable_tools: 是否启用工具调用
        """
        self.framework = framework
        self.enable_tools = enable_tools

        print(f"🔧 初始化 PR 分析器 (框架: {framework})...")

        # 根据框架类型创建对应的 analyzer
        if framework == "langchain":
            self.analyzer = PRAnalysisLangChain()
        elif framework == "claude_agent_sdk":
            self.analyzer = PRAnalysisClaudeAgentSDK()
        elif framework == "anthropic":
            self.analyzer = PRAnalysisAnthropic()
        else:
            raise ValueError(f"不支持的框架: {framework}")

        print(f"✅ 分析器初始化完成\n")

    def __call__(self, inputs: Dict) -> Dict:
        """执行 PR 分析（同步调用）"""
        pr_number = inputs.get("pr_number")
        print(f"\n🔍 步骤 1: 分析 PR #{pr_number if pr_number else '(最新)'}...")
        print(f"   使用框架: {self.framework}")
        print(f"   工具调用: {'启用' if self.enable_tools else '禁用'}\n")

        # 对于异步的 analyzer，需要在事件循环中运行
        result = asyncio.run(
            self.analyzer.analyze_pr(
                pr_number=pr_number, enable_tools=self.enable_tools
            )
        )

        if result.get("success"):
            print(f"✅ PR 分析完成\n")
        else:
            print(f"❌ PR 分析失败: {result.get('error')}\n")

        return result

    def close(self):
        """关闭资源"""
        if self.analyzer:
            self.analyzer.close()


class VectorStoreRunnable:
    """向量数据库存储的 Runnable 包装器"""

    def __init__(self):
        print("🔧 初始化向量数据库...")
        try:
            self.vector_store = VectorStoreManager()
            self.enabled = True
            print("✅ 向量数据库已启用\n")
        except Exception as e:
            print(f"⚠️ 向量数据库初始化失败: {e}")
            print("⚠️ 将跳过向量数据库存储步骤\n")
            self.vector_store = None
            self.enabled = False

    def __call__(self, analysis_result: Dict) -> Dict:
        """保存分析结果到向量数据库"""
        if not self.enabled or not analysis_result.get("success"):
            analysis_result["vector_stored"] = False
            return analysis_result

        print(f"💾 步骤 2: 保存到向量数据库...")

        try:
            pr_number = analysis_result["pr_number"]
            pr_title = analysis_result["pr_title"]
            analysis = analysis_result["analysis"]

            # 构建 metadata
            metadata = {
                "analyzed_at": analysis_result.get(
                    "analyzed_at", datetime.now().isoformat()
                ),
            }

            # 检查是否已存在
            if self.vector_store.pr_exists(pr_number):
                print(f"⚠️ PR #{pr_number} 已存在，更新记录...")
                self.vector_store.delete_pr_analysis(pr_number)

            # 添加到向量数据库
            success = self.vector_store.add_pr_analysis(
                pr_number=pr_number,
                pr_title=pr_title,
                analysis=analysis,
                metadata=metadata,
            )

            analysis_result["vector_stored"] = success

            if success:
                print(f"✅ 已保存到向量数据库\n")
            else:
                print(f"⚠️ 向量数据库保存失败\n")

        except Exception as e:
            print(f"❌ 向量数据库存储失败: {e}\n")
            import traceback

            traceback.print_exc()
            analysis_result["vector_stored"] = False

        return analysis_result


def create_pr_analysis_chain(
    framework: FrameworkType = "langchain",
    enable_tools: bool = True,
    save_to_vector: bool = True,
):
    """
    创建 PR 分析 Chain（使用 LangChain LCEL 语法）

    Args:
        framework: 分析框架 ('langchain', 'claude_agent_sdk', 'anthropic')
        enable_tools: 是否启用工具调用（read, glob, grep）
        save_to_vector: 是否保存到向量数据库

    Returns:
        LangChain Runnable Chain

    使用方法:
        # 使用 LangChain
        chain = create_pr_analysis_chain(framework='langchain')
        result = chain.invoke({"pr_number": 15685})

        # 使用 Anthropic API
        chain = create_pr_analysis_chain(framework='anthropic')
        result = chain.invoke({"pr_number": 15685})

        # 使用 Claude Agent SDK
        chain = create_pr_analysis_chain(framework='claude_agent_sdk')
        result = chain.invoke({"pr_number": 15685})
    """
    print("🔧 创建 PR 分析 Chain...")
    print(f"   框架: {framework}")
    print(f"   工具调用: {'启用' if enable_tools else '禁用'}")
    print(f"   向量存储: {'启用' if save_to_vector else '禁用'}")
    print()

    # 创建 PR 分析 Runnable
    analyze_runnable = PRAnalysisRunnable(
        framework=framework, enable_tools=enable_tools
    )

    # 如果需要向量存储，创建完整链
    if save_to_vector:
        vector_store_runnable = VectorStoreRunnable()

        # 使用 LCEL 管道操作符组合链
        # analyze -> vector_store
        chain = (
            RunnablePassthrough()
            | RunnableLambda(analyze_runnable)
            | RunnableLambda(vector_store_runnable)
        )
    else:
        # 只有分析，不保存到向量存储
        chain = RunnablePassthrough() | RunnableLambda(analyze_runnable)

    return chain


def run_pr_analysis(
    pr_number: Optional[int] = None,
    framework: FrameworkType = "langchain",
    enable_tools: bool = True,
    save_to_vector: bool = True,
) -> Dict:
    """
    便捷函数：运行 PR 分析 Chain

    Args:
        pr_number: PR 编号，如果为 None 则分析最新 PR
        framework: 分析框架 ('langchain', 'claude_agent_sdk', 'anthropic')
        enable_tools: 是否启用工具调用（read, glob, grep）
        save_to_vector: 是否保存到向量数据库

    Returns:
        分析结果字典，包含 vector_stored 字段

    示例:
        # 使用 LangChain
        result = run_pr_analysis(pr_number=15685, framework='langchain')

        # 使用 Anthropic API
        result = run_pr_analysis(pr_number=15685, framework='anthropic')

        # 使用 Claude Agent SDK，不启用工具
        result = run_pr_analysis(pr_number=15685, framework='claude_agent_sdk', enable_tools=False)

        # 只分析，不保存到向量数据库
        result = run_pr_analysis(pr_number=15685, save_to_vector=False)
    """
    print(f"\n{'='*80}")
    print(f"🚀 启动 PR 分析工作流")
    print(f"{'='*80}\n")

    # 创建 Chain
    chain = create_pr_analysis_chain(
        framework=framework, enable_tools=enable_tools, save_to_vector=save_to_vector
    )

    # 运行 Chain
    result = chain.invoke({"pr_number": pr_number})

    print(f"{'='*80}")
    print(f"🎉 工作流完成")
    print(f"{'='*80}\n")

    return result


def get_prs_by_date_range(
    since_date: str,
    days: int = 7,
) -> List[int]:
    """
    从数据库中获取指定日期范围内已合并的 PR 编号列表

    Args:
        since_date: 起始日期 (格式: YYYY-MM-DD)，必需
        days: 天数范围，默认 7 天

    Returns:
        PR 编号列表
    """
    db = DatabaseManager()

    try:
        # 计算日期范围
        start_date = since_date
        end_date = (
            datetime.strptime(since_date, "%Y-%m-%d") + timedelta(days=days)
        ).strftime("%Y-%m-%d")

        # 从数据库查询, [start_date, end_date)
        pr_numbers = db.get_merged_prs_in_range(start_date, end_date)

        print(f"📅 日期范围: {start_date} 到 {end_date}")
        print(f"📊 找到 {len(pr_numbers)} 个已合并的 PR\n")

        return pr_numbers

    finally:
        db.close()


def batch_analyze_prs(
    pr_numbers: List[int],
    framework: FrameworkType = "langchain",
    enable_tools: bool = True,
    save_to_vector: bool = True,
) -> Dict:
    """
    批量分析多个 PR

    Args:
        pr_numbers: PR 编号列表
        framework: 分析框架
        enable_tools: 是否启用工具调用
        save_to_vector: 是否保存到向量数据库

    Returns:
        包含成功和失败统计的结果字典
    """
    print(f"\n{'='*80}")
    print(f"🚀 批量分析 {len(pr_numbers)} 个 PR")
    print(f"{'='*80}\n")

    results = {
        "total": len(pr_numbers),
        "success": 0,
        "failed": 0,
        "failed_prs": [],
    }

    # 创建一个 Chain 对象，复用于所有 PR
    print(f"🔧 创建 PR 分析 Chain...")
    print(f"   框架: {framework}")
    print(f"   工具调用: {'启用' if enable_tools else '禁用'}")
    print(f"   向量存储: {'启用' if save_to_vector else '禁用'}")
    print()

    chain = create_pr_analysis_chain(
        framework=framework, enable_tools=enable_tools, save_to_vector=save_to_vector
    )

    for i, pr_number in enumerate(pr_numbers, 1):
        print(f"\n{'='*80}")
        print(f"进度: {i}/{len(pr_numbers)} - PR #{pr_number}")
        print(f"{'='*80}\n")

        try:
            # 使用复用的 chain 对象
            result = chain.invoke({"pr_number": pr_number})

            if result.get("success"):
                results["success"] += 1
                print(f"✅ PR #{pr_number} 分析成功\n")
            else:
                results["failed"] += 1
                results["failed_prs"].append(pr_number)
                print(f"❌ PR #{pr_number} 分析失败\n")

        except Exception as e:
            results["failed"] += 1
            results["failed_prs"].append(pr_number)
            print(f"❌ PR #{pr_number} 处理异常: {e}\n")

    print(f"\n{'='*80}")
    print(f"📊 批量分析完成")
    print(f"{'='*80}")
    print(f"总计: {results['total']}")
    print(f"成功: {results['success']}")
    print(f"失败: {results['failed']}")
    if results["failed_prs"]:
        print(f"失败的PR: {results['failed_prs']}")
    print(f"{'='*80}\n")

    return results


# 主方法
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="PR 分析 + 向量数据库存储工具 (支持批量处理)"
    )

    # 日期范围参数
    parser.add_argument(
        "--since_date",
        type=str,
        help="起始日期 (格式: YYYY-MM-DD)，用于批量处理时必需",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="从起始日期开始的天数范围 (默认: 7)",
    )

    # PR 编号参数（单个 PR）
    parser.add_argument(
        "--pr_number",
        type=int,
        help="单个 PR 编号（与日期范围参数互斥）",
    )

    # 框架选择
    parser.add_argument(
        "--framework",
        type=str,
        choices=["langchain", "claude_agent_sdk", "anthropic"],
        default="claude_agent_sdk",
        help="分析框架 (默认: claude_agent_sdk)",
    )

    # 工具和存储选项
    parser.add_argument(
        "--no_tools",
        action="store_true",
        help="禁用工具调用",
    )
    parser.add_argument(
        "--no_vector",
        action="store_true",
        help="不保存到向量数据库",
    )

    args = parser.parse_args()

    print("🚀 PR 分析 + 向量数据库存储工具")
    print("使用 LangChain LCEL: analyze | vector_store")
    print("支持多种框架: langchain, claude_agent_sdk, anthropic")
    print("=" * 80)
    print()

    enable_tools = not args.no_tools
    save_to_vector = not args.no_vector

    # 判断是单个 PR 还是批量处理
    if args.pr_number:
        # 单个 PR 模式
        if args.since_date:
            print("❌ 错误: --pr_number 不能与 --since_date 同时使用")
            exit(1)

        result = run_pr_analysis(
            pr_number=args.pr_number,
            framework=args.framework,
            enable_tools=enable_tools,
            save_to_vector=save_to_vector,
        )

        # 打印结果摘要
        print(f"\n📋 结果摘要:")
        print(f"  PR 编号: {result.get('pr_number')}")
        print(f"  PR 标题: {result.get('pr_title')}")
        print(f"  分析成功: {result.get('success')}")
        print(f"  向量存储: {result.get('vector_stored', False)}")

        if result.get("success"):
            print(f"\n📄 分析内容预览:")
            analysis = result.get("analysis", "")
            preview = analysis[:500] + "..." if len(analysis) > 500 else analysis
            print(preview)

    elif args.since_date:
        # 批量处理模式
        pr_numbers = get_prs_by_date_range(
            since_date=args.since_date,
            days=args.days,
        )

        if not pr_numbers:
            print("❌ 未找到符合条件的 PR")
            exit(0)

        results = batch_analyze_prs(
            pr_numbers=pr_numbers,
            framework=args.framework,
            enable_tools=enable_tools,
            save_to_vector=save_to_vector,
        )

    else:
        print("❌ 错误: 必须指定 --pr_number 或 --since_date")
        parser.print_help()
        exit(1)

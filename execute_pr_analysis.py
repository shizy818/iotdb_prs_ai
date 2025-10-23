#!/usr/bin/env python3
"""
IoTDB PR分析工具 - 统一入口
支持多种框架：LangChain、Claude Agent SDK、Anthropic API
"""

import asyncio
import argparse
import json
import sys
from typing import Dict, Optional

from pr_analysis_langchain import PRAnalysisLangChain
from pr_analysis_cc_sdk import PRAnalysisClaudeAgentSDK
from pr_analysis_anthropic import PRAnalysisAnthropic


def print_analysis_result(result: Dict, framework: str):
    """打印分析结果"""
    print(f"\n{'='*80}")

    if result.get("pr_number"):
        pr_title = result.get("pr_title", "")
        print(f"PR #{result['pr_number']}: {pr_title}")
    else:
        print("PR分析结果")

    print(f"使用框架: {framework}")
    print(f"{'='*80}")

    if result["success"]:
        print(f"✅ 分析完成")
        if "analyzed_at" in result:
            print(f"分析时间: {result['analyzed_at']}")

        print(f"\n📋 分析结果:")
        print(f"{'-'*60}")
        print(result.get("analysis", "无分析结果"))

        # 显示 token 使用统计（如果有）
        if "usage" in result:
            usage = result["usage"]
            print(f"\n📊 Token 使用统计:")
            print(f"   输入 tokens: {usage.get('input_tokens', 0):,}")
            print(f"   输出 tokens: {usage.get('output_tokens', 0):,}")
            if usage.get("tool_calls"):
                print(f"   工具调用次数: {usage.get('tool_calls', 0)}")
    else:
        print(f"❌ 分析失败: {result.get('error', '未知错误')}")

    print(f"\n{'='*80}")


async def analyze_with_langchain(
    pr_number: Optional[int] = None, enable_tools: bool = True
) -> Dict:
    """使用 LangChain 框架分析 PR"""
    print(f"📦 使用 LangChain 框架...")
    analyzer = PRAnalysisLangChain()
    try:
        result = await analyzer.analyze_pr(
            pr_number=pr_number, enable_tools=enable_tools
        )
        return result
    finally:
        analyzer.close()


async def analyze_with_claude_agent_sdk(
    pr_number: Optional[int] = None, enable_tools: bool = True
) -> Dict:
    """使用 Claude Agent SDK 框架分析 PR"""
    print(f"📦 使用 Claude Agent SDK 框架...")
    analyzer = PRAnalysisClaudeAgentSDK()
    try:
        result = await analyzer.analyze_pr(
            pr_number=pr_number, enable_tools=enable_tools
        )
        return result
    finally:
        analyzer.close()


async def analyze_with_anthropic(
    pr_number: Optional[int] = None, enable_tools: bool = True
) -> Dict:
    """使用 Anthropic API 框架分析 PR"""
    print(f"📦 使用 Anthropic API 框架...")
    analyzer = PRAnalysisAnthropic()
    try:
        result = await analyzer.analyze_pr(
            pr_number=pr_number, enable_tools=enable_tools
        )
        return result
    finally:
        analyzer.close()


async def main():
    parser = argparse.ArgumentParser(
        description="IoTDB PR分析工具 - 支持多种分析框架",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --pr 15685                                    # 使用默认框架(langchain)分析PR
  %(prog)s --pr 15685 --frame anthropic                  # 使用Anthropic API分析PR
  %(prog)s --pr 15685 --frame claude_agent_sdk           # 使用Claude Agent SDK分析PR
  %(prog)s --pr 15685 --output result.json               # 将结果保存到JSON文件
  %(prog)s --pr 15685 --frame langchain --no-tools       # 禁用工具调用
        """,
    )

    parser.add_argument(
        "--pr",
        "--pr_number",
        dest="pr_number",
        type=int,
        help="PR编号（必需）",
        required=True,
    )

    parser.add_argument(
        "--frame",
        "--framework",
        dest="framework",
        type=str,
        choices=["langchain", "claude_agent_sdk", "anthropic"],
        default="langchain",
        help="选择分析框架（默认: langchain）",
    )

    parser.add_argument(
        "--output",
        type=str,
        help="输出结果到JSON文件",
    )

    parser.add_argument(
        "--no-tools",
        dest="enable_tools",
        action="store_false",
        default=True,
        help="禁用工具调用（read, glob, grep）",
    )

    args = parser.parse_args()

    try:
        print("🚀 IoTDB PR 分析工具")
        print("=" * 60)
        print(f"PR编号: {args.pr_number}")
        print(f"框架: {args.framework}")
        print(f"工具调用: {'启用' if args.enable_tools else '禁用'}")
        if args.output:
            print(f"输出文件: {args.output}")
        print("=" * 60)

        # 根据选择的框架调用相应的分析函数
        if args.framework == "langchain":
            result = await analyze_with_langchain(
                pr_number=args.pr_number, enable_tools=args.enable_tools
            )
        elif args.framework == "claude_agent_sdk":
            result = await analyze_with_claude_agent_sdk(
                pr_number=args.pr_number, enable_tools=args.enable_tools
            )
        elif args.framework == "anthropic":
            result = await analyze_with_anthropic(
                pr_number=args.pr_number, enable_tools=args.enable_tools
            )
        else:
            print(f"❌ 不支持的框架: {args.framework}")
            return 1

        # 打印分析结果
        print_analysis_result(result, args.framework)

        # 输出结果到JSON文件
        if args.output:
            try:
                with open(args.output, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                print(f"\n📁 结果已保存到: {args.output}")
            except Exception as e:
                print(f"\n❌ 保存文件失败: {e}")
                return 1

        # 返回成功或失败状态
        return 0 if result.get("success") else 1

    except KeyboardInterrupt:
        print("\n⏹️ 用户中断操作")
        return 1
    except Exception as e:
        print(f"\n❌ 执行过程中出现错误: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

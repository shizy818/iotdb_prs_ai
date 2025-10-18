#!/usr/bin/env python3
"""
IoTDB PR分析工具 - 使用ClaudeSDKClient
利用ClaudeSDKClient分析IoTDB PR的问题和潜在影响
"""

import asyncio
import argparse
import json
import sys
import os
from typing import Dict

from pr_analysis_with_claude import PRAnalysisWithClaude


def print_analysis_result(result: Dict):
    """打印分析结果"""
    print(f"\n{'='*80}")

    if result.get("pr_number") and result.get("pr_title"):
        print(f"PR #{result['pr_number']}: {result['pr_title']}")
    else:
        print("PR分析结果")

    print(f"{'='*80}")

    if result["success"]:
        print(f"✅ 分析完成于: {result['analyzed_at']}")
        print(f"\n📋 分析结果:")
        print(f"{'-'*60}")
        print(result["analysis"])
    else:
        print(f"❌ 分析失败: {result['error']}")

    print(f"\n{'='*80}")


async def main():
    parser = argparse.ArgumentParser(
        description="IoTDB PR分析工具 - 使用ClaudeSDKClient"
    )
    parser.add_argument("--pr", type=int, help="分析特定PR编号")
    parser.add_argument("--output", type=str, help="输出结果到JSON文件")

    args = parser.parse_args()

    # 初始化分析器
    try:
        analyzer = PRAnalysisWithClaude()
        print("✅ PR分析器初始化成功")
    except Exception as e:
        print(f"❌ 初始化失败: {e}")
        return 1

    try:
        # 分析单个PR
        if args.pr:
            print(f"\n🔍 正在分析 PR #{args.pr}...")
        else:
            print(f"\n🔍 正在分析最新PR...")

        result = await analyzer.analyze_single_pr(args.pr)

        print_analysis_result(result)

        # 输出结果到文件
        if args.output:
            try:
                with open(args.output, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                print(f"\n📁 结果已保存到: {args.output}")
            except Exception as e:
                print(f"\n❌ 保存文件失败: {e}")

        # 如果没有指定PR编号，显示帮助
        if not args.pr:
            print(f"\n💡 使用方法:")
            print("  --pr NUMBER    分析特定PR编号")
            print("  --output FILE   输出结果到JSON文件")
            print("\n示例:")
            print("  python analyze_pr_claude.py --pr 15114")
            print(
                "  python analyze_pr_claude.py --pr 15114 --output pr_15114_analysis.json"
            )

    except KeyboardInterrupt:
        print("\n⏹️ 用户中断操作")
        return 1
    except Exception as e:
        print(f"\n❌ 执行过程中出现错误: {e}")
        return 1
    finally:
        analyzer.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

#!/usr/bin/env python3
"""
演示完整工作流程：分析PR并使用向量数据库搜索
"""

import sys
from pathlib import Path

# 添加父目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import json
from pr_analysis_with_claude import PRAnalysisWithClaude
from vector_store import VectorStoreManager


async def demo_workflow():
    """演示完整的PR分析和搜索工作流程"""

    print("=" * 80)
    print("IoTDB PR分析工具 - 完整工作流程演示")
    print("=" * 80)

    # 步骤1: 初始化分析器和向量数据库
    print("\n步骤1: 初始化PR分析器和向量数据库")
    print("-" * 80)
    analyzer = PRAnalysisWithClaude()
    vector_store = VectorStoreManager()

    # 步骤2: 分析一个PR
    print("\n步骤2: 分析PR #16487")
    print("-" * 80)

    # 检查是否已有分析结果
    import os

    analysis_file = "pr_16487_analysis.json"

    if os.path.exists(analysis_file):
        print(f"✅ 发现已有分析结果: {analysis_file}")
        with open(analysis_file, "r", encoding="utf-8") as f:
            result = json.load(f)
        print(f"PR #{result['pr_number']}: {result['pr_title']}")
        print(f"分析时间: {result['analyzed_at']}")

        # 确保已添加到向量数据库
        print("\n正在确保分析结果已添加到向量数据库...")
        vector_store.add_pr_analysis(
            pr_number=result["pr_number"],
            pr_title=result["pr_title"],
            analysis=result["analysis"],
            metadata={"analyzed_at": result["analyzed_at"]},
        )
    else:
        print("正在调用Claude分析PR...")
        result = await analyzer.analyze_pr_with_anthropic(pr_number=16487)

        if result["success"]:
            print(f"✅ 分析成功!")
            print(f"PR #{result['pr_number']}: {result['pr_title']}")

            # 保存到文件
            with open(analysis_file, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"✅ 结果已保存到: {analysis_file}")
        else:
            print(f"❌ 分析失败: {result['error']}")
            analyzer.close()
            return

    # 步骤3: 查看向量数据库统计
    print("\n步骤3: 查看向量数据库统计信息")
    print("-" * 80)
    stats = vector_store.get_collection_stats()
    print(f"集合名称: {stats.get('collection_name', 'N/A')}")
    print(f"总文档数: {stats.get('total_documents', 0)}")
    print(f"存储路径: {stats.get('persist_directory', 'N/A')}")

    # 步骤4: 执行语义搜索
    print("\n步骤4: 执行语义搜索")
    print("-" * 80)

    # 定义一些搜索查询
    search_queries = [
        "JDBC配置错误",
        "Maven构建问题",
        "feature.xml文件路径",
    ]

    for query in search_queries:
        print(f"\n🔍 搜索: '{query}'")
        print("  " + "-" * 76)

        results = vector_store.search_with_score(query, k=2)

        if results:
            for idx, (doc, score) in enumerate(results, 1):
                pr_num = doc.metadata.get("pr_number")
                pr_title = doc.metadata.get("pr_title")
                chunk_idx = doc.metadata.get("chunk_index", 0)
                print(
                    f"  结果 {idx}: PR #{pr_num} - {pr_title} (相似度: {score:.4f}, 文档块: {chunk_idx+1})"
                )
                # 显示内容片段
                content_preview = doc.page_content[:1000].replace("\n", " ")
                print(f"    内容: {content_preview}...")
        else:
            print("  未找到相关结果")

    # 步骤5: 总结
    print("\n" + "=" * 80)
    print("演示完成!")
    print("=" * 80)
    print("\n接下来你可以:")
    print("1. 使用 search_pr_analysis.py 进行更多搜索")
    print("2. 分析更多PR以丰富向量数据库")
    print("3. 查看 VECTOR_STORE_README.md 了解更多功能")
    print("=" * 80)

    # 清理
    analyzer.close()


async def quick_search_demo():
    """快速搜索演示"""
    print("\n" + "=" * 80)
    print("快速搜索演示")
    print("=" * 80)

    vector_store = VectorStoreManager()

    query = "如何修复构建错误"
    print(f"\n搜索查询: '{query}'")
    print("-" * 80)

    results = vector_store.search_similar_prs(query, k=3)

    if results:
        for idx, result in enumerate(results, 1):
            print(f"\n结果 {idx}:")
            print(f"  PR #{result['pr_number']}: {result['pr_title']}")
            print(f"  内容片段: {result['content'][:1000]}...")
    else:
        print("未找到相关结果")


if __name__ == "__main__":
    import sys

    try:
        if len(sys.argv) > 1 and sys.argv[1] == "search":
            # 快速搜索模式
            asyncio.run(quick_search_demo())
        else:
            # 完整演示模式
            asyncio.run(demo_workflow())
    except KeyboardInterrupt:
        print("\n\n⏹️ 用户中断操作")
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback

        traceback.print_exc()

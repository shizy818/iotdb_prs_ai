#!/usr/bin/env python3
"""
PR分析搜索工具
使用向量数据库进行语义搜索，快速找到相关的PR分析结果
"""

import argparse
import sys
from typing import List, Dict
from vector_store import VectorStoreManager


def format_search_result(result: Dict, index: int, show_full: bool = False) -> str:
    """格式化搜索结果"""
    output = []
    output.append(f"\n{'='*80}")
    output.append(f"结果 #{index}")
    output.append(f"{'='*80}")
    output.append(f"PR编号: #{result['pr_number']}")
    output.append(f"PR标题: {result['pr_title']}")

    # 显示元数据
    metadata = result.get("metadata", {})
    if metadata.get("analyzed_at"):
        output.append(f"分析时间: {metadata['analyzed_at']}")
    if metadata.get("chunk_index") is not None:
        output.append(
            f"文档块: {metadata['chunk_index'] + 1}/{metadata.get('total_chunks', '?')}"
        )

    output.append(f"\n{'内容片段':^80}")
    output.append("-" * 80)

    # 显示内容
    content = result["content"]
    if show_full:
        output.append(content)
    else:
        # 只显示前500个字符
        preview = content[:500]
        if len(content) > 500:
            preview += "\n...(更多内容)"
        output.append(preview)

    return "\n".join(output)


def format_search_result_with_score(
    doc, score: float, index: int, show_full: bool = False
) -> str:
    """格式化带分数的搜索结果"""
    output = []
    output.append(f"\n{'='*80}")
    output.append(f"结果 #{index} - 相似度: {score:.4f}")
    output.append(f"{'='*80}")
    output.append(f"PR编号: #{doc.metadata.get('pr_number')}")
    output.append(f"PR标题: {doc.metadata.get('pr_title')}")

    # 显示元数据
    if doc.metadata.get("analyzed_at"):
        output.append(f"分析时间: {doc.metadata['analyzed_at']}")
    if doc.metadata.get("chunk_index") is not None:
        output.append(
            f"文档块: {doc.metadata['chunk_index'] + 1}/{doc.metadata.get('total_chunks', '?')}"
        )

    output.append(f"\n{'内容片段':^80}")
    output.append("-" * 80)

    # 显示内容
    content = doc.page_content
    if show_full:
        output.append(content)
    else:
        # 只显示前500个字符
        preview = content[:500]
        if len(content) > 500:
            preview += "\n...(更多内容)"
        output.append(preview)

    return "\n".join(output)


def search_command(args):
    """执行搜索命令"""
    print(f"\n🔍 搜索查询: {args.query}")
    print(f"📊 返回结果数: {args.top_k}")

    # 初始化向量数据库
    vector_store = VectorStoreManager()

    # 获取统计信息
    stats = vector_store.get_collection_stats()
    print(f"📚 数据库包含 {stats.get('total_documents', 0)} 个文档")

    # 执行搜索
    if args.with_score:
        print("\n正在执行语义搜索（带相似度分数）...")
        results = vector_store.search_with_score(args.query, k=args.top_k)

        if results:
            print(f"\n找到 {len(results)} 个相关结果:")
            for idx, (doc, score) in enumerate(results, 1):
                print(format_search_result_with_score(doc, score, idx, args.full))
        else:
            print("\n未找到相关结果")
    else:
        print("\n正在执行语义搜索...")
        results = vector_store.search_similar_prs(args.query, k=args.top_k)

        if results:
            print(f"\n找到 {len(results)} 个相关结果:")
            for idx, result in enumerate(results, 1):
                print(format_search_result(result, idx, args.full))
        else:
            print("\n未找到相关结果")


def fetch_command(args):
    """根据PR编号获取分析结果"""
    pr_number = args.pr_number
    print(f"\n🔍 获取PR #{pr_number}的分析结果...")

    # 初始化向量数据库
    vector_store = VectorStoreManager()

    # 获取特定PR
    result = vector_store.get_pr_by_number(pr_number)

    if not result:
        print(f"\n❌ 未找到PR #{pr_number}的分析结果")
        print("💡 提示: 该PR可能尚未被分析，请先使用analyze_pr.py进行分析")
        return

    print(f"\n✅ 找到PR #{pr_number}的分析结果")
    print("=" * 80)
    print(f"PR编号: #{result['pr_number']}")
    print(f"PR标题: {result['pr_title']}")

    metadata = result.get("metadata", {})
    if metadata.get("analyzed_at"):
        print(f"分析时间: {metadata['analyzed_at']}")

    print("=" * 80)
    print("\n分析内容:\n")
    print(result["content"])
    print("\n" + "=" * 80)


def stats_command(args):
    """显示统计信息"""
    print("\n📊 向量数据库统计信息")
    print("=" * 80)

    vector_store = VectorStoreManager()
    stats = vector_store.get_collection_stats()

    print(f"集合名称: {stats.get('collection_name', 'N/A')}")
    print(f"总文档数: {stats.get('total_documents', 0)}")
    print(f"存储路径: {stats.get('persist_directory', 'N/A')}")
    print("=" * 80)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="PR分析搜索工具 - 使用向量数据库进行语义搜索",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 搜索JDBC相关问题
  python search_pr_analysis.py search "JDBC配置问题"

  # 搜索并显示相似度分数
  python search_pr_analysis.py search "Maven构建错误" --with-score

  # 返回更多结果
  python search_pr_analysis.py search "Karaf部署" --top-k 10

  # 显示完整内容
  python search_pr_analysis.py search "feature.xml" --full

  # 获取指定PR的分析结果
  python search_pr_analysis.py fetch 16487

  # 查看数据库统计
  python search_pr_analysis.py stats
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # 搜索命令
    search_parser = subparsers.add_parser("search", help="搜索PR分析")
    search_parser.add_argument("query", type=str, help="搜索查询")
    search_parser.add_argument(
        "--top-k", type=int, default=5, help="返回的结果数量 (默认: 5)"
    )
    search_parser.add_argument(
        "--with-score", action="store_true", help="显示相似度分数"
    )
    search_parser.add_argument("--full", action="store_true", help="显示完整内容")

    # 获取PR命令
    fetch_parser = subparsers.add_parser("fetch", help="获取指定PR的分析结果")
    fetch_parser.add_argument("pr_number", type=int, help="PR编号")

    # 统计命令
    subparsers.add_parser("stats", help="显示数据库统计信息")

    args = parser.parse_args()

    # 执行命令
    try:
        if args.command == "search":
            search_command(args)
        elif args.command == "fetch":
            fetch_command(args)
        elif args.command == "stats":
            stats_command(args)
        else:
            parser.print_help()
            return 1

        return 0

    except KeyboardInterrupt:
        print("\n⏹️ 用户中断操作")
        return 1
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

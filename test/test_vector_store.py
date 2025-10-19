#!/usr/bin/env python3
"""
测试向量数据库功能
演示如何使用向量数据库存储和检索PR分析结果
"""

import sys
from pathlib import Path

# 添加父目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
from vector_store import VectorStoreManager


def test_basic_operations():
    """测试基本的CRUD操作"""
    print("=" * 80)
    print("测试1: 基本的向量数据库操作")
    print("=" * 80)

    # 初始化向量数据库
    vector_store = VectorStoreManager()

    # 测试数据：使用实际的PR分析结果
    with open("pr_16487_analysis.json", "r", encoding="utf-8") as f:
        pr_data = json.load(f)

    # 添加PR分析到向量数据库
    print(f"\n1. 添加PR #{pr_data['pr_number']} 到向量数据库...")
    success = vector_store.add_pr_analysis(
        pr_number=pr_data["pr_number"],
        pr_title=pr_data["pr_title"],
        analysis=pr_data["analysis"],
        metadata={"analyzed_at": pr_data["analyzed_at"]},
    )

    if success:
        print(f"   ✅ 成功添加")
    else:
        print(f"   ❌ 添加失败")

    # 获取统计信息
    print(f"\n2. 查看数据库统计信息...")
    stats = vector_store.get_collection_stats()
    print(f"   总文档数: {stats.get('total_documents', 0)}")
    print(f"   集合名称: {stats.get('collection_name', 'N/A')}")
    print(f"   存储路径: {stats.get('persist_directory', 'N/A')}")

    return vector_store


def test_semantic_search(vector_store):
    """测试语义搜索功能"""
    print("\n" + "=" * 80)
    print("测试2: 语义搜索功能")
    print("=" * 80)

    # 定义测试查询
    test_queries = [
        "JDBC配置相关的问题",
        "Maven构建错误",
        "Karaf部署问题",
        "feature.xml文件路径",
        "如何修复构建失败",
    ]

    for query in test_queries:
        print(f"\n查询: '{query}'")
        print("-" * 60)

        # 执行搜索
        results = vector_store.search_similar_prs(query, k=3)

        if results:
            for idx, result in enumerate(results, 1):
                print(f"\n结果 {idx}:")
                print(f"  PR #{result['pr_number']}: {result['pr_title']}")
                print(f"  内容片段: {result['content'][:200]}...")
        else:
            print("  未找到相关结果")


def test_search_with_score(vector_store):
    """测试带相似度分数的搜索"""
    print("\n" + "=" * 80)
    print("测试3: 带相似度分数的搜索")
    print("=" * 80)

    query = "Maven构建配置错误"
    print(f"\n查询: '{query}'")
    print("-" * 60)

    # 执行带分数的搜索
    results = vector_store.search_with_score(query, k=3)

    if results:
        for idx, (doc, score) in enumerate(results, 1):
            print(f"\n结果 {idx} (相似度分数: {score:.4f}):")
            print(
                f"  PR #{doc.metadata.get('pr_number')}: {doc.metadata.get('pr_title')}"
            )
            print(f"  内容片段: {doc.page_content[:200]}...")
    else:
        print("  未找到相关结果")


def test_filter_search(vector_store):
    """测试带过滤条件的搜索"""
    print("\n" + "=" * 80)
    print("测试4: 带元数据过滤的搜索")
    print("=" * 80)

    query = "配置问题"
    filter_dict = {"pr_number": 16487}

    print(f"\n查询: '{query}'")
    print(f"过滤条件: PR编号 = 16487")
    print("-" * 60)

    # 执行过滤搜索
    results = vector_store.search_similar_prs(query, k=5, filter_dict=filter_dict)

    if results:
        for idx, result in enumerate(results, 1):
            print(f"\n结果 {idx}:")
            print(f"  PR #{result['pr_number']}: {result['pr_title']}")
            print(f"  Chunk ID: {result['metadata'].get('chunk_id')}")
            print(f"  内容片段: {result['content'][:200]}...")
    else:
        print("  未找到相关结果")


def main():
    """主测试函数"""
    print("\n" + "=" * 80)
    print("向量数据库功能测试")
    print("=" * 80)

    try:
        # 测试1: 基本操作
        vector_store = test_basic_operations()

        # 测试2: 语义搜索
        test_semantic_search(vector_store)

        # 测试3: 带分数的搜索
        test_search_with_score(vector_store)

        # 测试4: 带过滤的搜索
        test_filter_search(vector_store)

        print("\n" + "=" * 80)
        print("✅ 所有测试完成!")
        print("=" * 80)

    except FileNotFoundError:
        print("\n❌ 错误: 找不到 pr_16487_analysis.json 文件")
        print(
            "请先运行: python analyze_pr_claude.py --pr 16487 --output pr_16487_analysis.json"
        )
    except Exception as e:
        print(f"\n❌ 测试过程中出现错误: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()

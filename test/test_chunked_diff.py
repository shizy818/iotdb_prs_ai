#!/usr/bin/env python3
"""
测试分批处理diff的功能
"""

import sys
from pathlib import Path

# 添加父目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from pr_analysis_with_claude import PRAnalysisWithClaude, split_diff_into_chunks


async def test_chunked_analysis():
    """测试分批分析功能"""
    analyzer = PRAnalysisWithClaude()

    try:
        print("🧪 测试分批处理大型diff的PR分析\n")
        print("=" * 60)

        # 测试一个可能有大diff的PR
        pr_number = 14591

        print("\n开始分析 (使用优化后的分批传输策略):")
        print("  - 第1步: 发送PR基本信息")
        print("  - 第2步: 分批发送diff内容")
        print("  - 第3步: 请求完整分析")
        print("-" * 60)

        result = await analyzer.analyze_single_pr(pr_number=pr_number)

        if result["success"]:
            print(f"\n✅ 分析成功!")
            print(f"PR #{result['pr_number']}: {result['pr_title']}")
            print(f"Diff使用了 {result.get('diff_chunks_count', 0)} 个批次")
            print(f"\n完整分析结果:\n{result['analysis']}")
        else:
            print(f"\n❌ 分析失败: {result['error']}")
            if "error_details" in result:
                print(f"\n详细错误:\n{result['error_details']}")

        print("\n" + "=" * 60)

    except KeyboardInterrupt:
        print("\n⏹️  用户中断测试")
    except Exception as e:
        print(f"\n❌ 测试过程中出现错误: {e}")
        import traceback

        traceback.print_exc()
    finally:
        analyzer.close()
        print("\n✓ 测试完成")


async def test_chunk_splitting():
    """测试diff分割功能"""
    analyzer = PRAnalysisWithClaude()

    print("\n🧪 测试diff分割算法")
    print("=" * 60)

    # 创建一个模拟的大diff
    mock_diff = ""
    for i in range(5):
        mock_diff += (
            f"""
diff --git a/file{i}.java b/file{i}.java
index 1234567..abcdefg 100644
--- a/file{i}.java
+++ b/file{i}.java
@@ -1,10 +1,20 @@
 package org.example;

+import java.util.List;
+
 public class TestClass{i} {{
-    private int value;
+    private long value;
+    private String name;

-    public void method() {{
-        // old implementation
+    public void newMethod() {{
+        // new implementation
+        for (int j = 0; j < 100; j++) {{
+            System.out.println("Line " + j);
+        }}
     }}
 }}
"""
            * 100
        )  # 重复100次使其变大

    print(f"模拟diff大小: {len(mock_diff):,} 字符\n")

    # 测试分割
    chunks = split_diff_into_chunks(mock_diff, max_chunk_size=8000)

    print(f"分割结果:")
    print(f"  - 总块数: {len(chunks)}")
    for idx, chunk in enumerate(chunks):
        print(f"  - 块 {idx + 1}: {len(chunk):,} 字符")

    analyzer.close()
    print("\n✓ 分割测试完成")


if __name__ == "__main__":
    print("选择测试模式:")
    print("1. 测试完整的分批分析功能 (需要API)")
    print("2. 仅测试diff分割算法 (无需API)")

    choice = input("\n请选择 (1 或 2): ").strip()

    if choice == "1":
        asyncio.run(test_chunked_analysis())
    elif choice == "2":
        asyncio.run(test_chunk_splitting())
    else:
        print("无效选择")

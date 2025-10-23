#!/usr/bin/env python3
"""
测试 can_use_tool 回调函数的安全性
"""

import asyncio
from pathlib import Path
from claude_agent_sdk import ToolPermissionContext

from config import DEFAULT_IOTDB_SOURCE_DIR


# 模拟配置
class MockConfig:
    ANTHROPIC_BASE_URL = "https://api.example.com"
    ANTHROPIC_API_KEY = "test-key"
    DEFAULT_IOTDB_SOURCE_DIR = "/path/to/iotdb"

# 导入类
import sys
sys.path.insert(0, str(Path(__file__).parent))

from pr_analysis_cc_sdk import PRAnalysisClaudeAgentSDK

async def test_can_use_tool():
    """测试工具权限回调"""

    # 创建测试实例
    analyzer = PRAnalysisClaudeAgentSDK(DEFAULT_IOTDB_SOURCE_DIR)

    # 模拟上下文
    context = ToolPermissionContext()

    print("=" * 70)
    print("测试 can_use_tool 工具权限回调")
    print("=" * 70)

    # 测试用例
    test_cases = [
        # 1. 正常的 read 操作
        {
            "name": "✅ 正常读取 Java 文件",
            "tool_name": "read",
            "tool_input": {"file_path": "src/main/java/Main.java"},
            "should_allow": True,
        },
        # 2. 尝试读取敏感文件
        {
            "name": "🚨 读取敏感文件 (.env)",
            "tool_name": "read",
            "tool_input": {"file_path": ".env"},
            "should_allow": False,
        },
        # 3. 尝试路径遍历攻击
        {
            "name": "🚨 路径遍历攻击 (../)",
            "tool_name": "read",
            "tool_input": {"file_path": "../../etc/passwd"},
            "should_allow": False,
        },
        # 4. 正常的 glob 操作
        {
            "name": "✅ 正常 glob 搜索",
            "tool_name": "glob",
            "tool_input": {"pattern": "**/*.java", "path": "src"},
            "should_allow": True,
        },
        # 5. 尝试搜索敏感目录
        {
            "name": "🚨 搜索敏感目录 (.git)",
            "tool_name": "glob",
            "tool_input": {"pattern": "*", "path": ".git"},
            "should_allow": False,
        },
        # 6. 正常的 grep 操作
        {
            "name": "✅ 正常 grep 搜索",
            "tool_name": "grep",
            "tool_input": {"pattern": "class Main", "path": "src", "file_type": "java"},
            "should_allow": True,
        },
        # 7. 尝试使用未授权的工具
        {
            "name": "🚨 未授权工具 (bash)",
            "tool_name": "bash",
            "tool_input": {"command": "ls -la"},
            "should_allow": False,
        },
    ]

    # 运行测试
    for i, test in enumerate(test_cases, 1):
        print(f"\n测试 {i}: {test['name']}")
        print(f"  工具: {test['tool_name']}")
        print(f"  参数: {test['tool_input']}")

        result = await analyzer.can_use_tool(
            test["tool_name"],
            test["tool_input"],
            context
        )

        # 检查结果类型
        from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny

        is_allowed = isinstance(result, PermissionResultAllow)
        is_denied = isinstance(result, PermissionResultDeny)

        if is_allowed:
            print(f"  结果: ✅ 允许")
        elif is_denied:
            print(f"  结果: ❌ 拒绝")
            print(f"  原因: {result.message}")

        # 验证期望
        expected = test["should_allow"]
        actual = is_allowed

        if expected == actual:
            print(f"  验证: ✓ 通过")
        else:
            print(f"  验证: ✗ 失败 (期望: {'允许' if expected else '拒绝'}, 实际: {'允许' if actual else '拒绝'})")

    print("\n" + "=" * 70)
    print("测试完成")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(test_can_use_tool())

#!/usr/bin/env python3
"""
Git 工具功能测试
测试 LangChain 中新增的 git 工具（支持管道）
"""
import sys
from pathlib import Path

# 添加父目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent))


from pr_analysis_langchain import PRAnalysisLangChain


def test_git_tool():
    """测试 git 工具的各种功能"""

    print("=" * 80)
    print("🧪 Git 工具功能测试")
    print("=" * 80)

    # 初始化分析器
    analyzer = PRAnalysisLangChain()

    # 获取 git 工具
    tools = analyzer._create_tools()
    git_tool = None
    bash_tool = None

    for tool in tools:
        if tool.name == "git":
            git_tool = tool
        elif tool.name == "bash":
            bash_tool = tool

    if not git_tool:
        print("❌ 未找到 git 工具")
        return False

    print(f"✅ 找到 git 工具: {git_tool.name}")
    print(f"✅ 找到 bash 工具: {bash_tool.name if bash_tool else 'None'}")
    print()

    # 测试用例
    test_cases = [
        {
            "name": "基本命令：git status",
            "command": "git status",
            "should_succeed": True,
            "tool": "git",
        },
        {
            "name": "基本命令：git log",
            "command": "git log --oneline -5",
            "should_succeed": True,
            "tool": "git",
        },
        {
            "name": "管道命令：git log | grep（匹配 Fix）",
            "command": "git log --oneline -10 | grep -i 'fix'",
            "should_succeed": True,
            "tool": "git",
        },
        {
            "name": "管道命令：git log | head",
            "command": "git log --oneline | head -3",
            "should_succeed": True,
            "tool": "git",
        },
        {
            "name": "管道命令：git branch | grep",
            "command": "git branch -a | grep 'HEAD'",
            "should_succeed": True,
            "tool": "git",
        },
        {
            "name": "重定向：git log 输出到文件",
            "command": "git log --oneline -5 > /tmp/git_test_output.txt && cat /tmp/git_test_output.txt",
            "should_succeed": True,
            "tool": "git",
        },
        {
            "name": "重定向：git status 追加到文件",
            "command": "git status >> /tmp/git_test_output.txt && tail -3 /tmp/git_test_output.txt",
            "should_succeed": True,
            "tool": "git",
        },
        {
            "name": "命令链接：git branch && git status",
            "command": "git branch && git status",
            "should_succeed": True,
            "tool": "git",
        },
        {
            "name": "复杂组合：checkout && log | grep",
            "command": "git log --oneline -20 | grep -i 'cache' | head -3",
            "should_succeed": True,
            "tool": "git",
        },
        {
            "name": "危险命令拦截：git push",
            "command": "git push origin main",
            "should_succeed": False,
            "tool": "git",
        },
        {
            "name": "危险命令拦截：git reset",
            "command": "git reset --hard HEAD",
            "should_succeed": False,
            "tool": "git",
        },
        {
            "name": "安全检查：命令注入",
            "command": "git status; rm -rf /tmp/test",
            "should_succeed": False,
            "tool": "git",
        },
        {
            "name": "Bash工具（不支持管道）：git log | grep",
            "command": "git log --oneline -10 | grep '添加'",
            "should_succeed": False,  # bash 工具不支持管道
            "tool": "bash",
        },
    ]

    results = []

    for i, test in enumerate(test_cases, 1):
        print(f"\n{'='*80}")
        print(f"测试 {i}/{len(test_cases)}: {test['name']}")
        print(f"{'='*80}")
        print(f"命令: {test['command']}")
        print(f"使用工具: {test['tool']}")
        print(f"预期: {'✅ 应该成功' if test['should_succeed'] else '❌ 应该失败'}")
        print()

        # 选择工具
        tool = git_tool if test['tool'] == 'git' else bash_tool
        if not tool:
            print(f"⚠️ 跳过测试（工具不存在）")
            continue

        # 执行命令
        try:
            result = tool.func(command=test['command'])

            # 判断是否成功
            is_success = not result.startswith("错误")

            # 检查结果是否符合预期
            if is_success == test['should_succeed']:
                print(f"\n✅ 测试通过")
                results.append(True)
            else:
                print(f"\n❌ 测试失败")
                print(f"   预期: {'成功' if test['should_succeed'] else '失败'}")
                print(f"   实际: {'成功' if is_success else '失败'}")
                results.append(False)

            # 显示输出摘要
            if len(result) > 200:
                print(f"\n📝 输出摘要（前200字符）:")
                print(result[:200] + "...")
            else:
                print(f"\n📝 完整输出:")
                print(result)

        except Exception as e:
            print(f"\n❌ 执行异常: {e}")
            results.append(False)

    # 汇总结果
    print(f"\n\n{'='*80}")
    print("📊 测试结果汇总")
    print(f"{'='*80}")

    passed = sum(results)
    total = len(results)

    print(f"通过: {passed}/{total}")
    print(f"失败: {total - passed}/{total}")
    print(f"成功率: {passed/total*100:.1f}%")

    if passed == total:
        print("\n🎉 所有测试通过！")
        return True
    else:
        print(f"\n⚠️ 有 {total - passed} 个测试失败")
        return False


def main():
    """主函数"""
    try:
        success = test_git_tool()
        return 0 if success else 1
    except KeyboardInterrupt:
        print("\n\n⏹️ 测试被中断")
        return 1
    except Exception as e:
        print(f"\n\n❌ 测试过程出错: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

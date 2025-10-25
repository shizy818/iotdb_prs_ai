import asyncio
from typing import Any, Dict, Optional
from datetime import datetime

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)
from database import DatabaseManager
from config import ANTHROPIC_BASE_URL, ANTHROPIC_API_KEY, DEFAULT_IOTDB_SOURCE_DIR

from pr_analysis_common import (
    build_analysis_query,
    get_pr_by_number,
)


class PRAnalysisClaudeAgentSDK:
    def __init__(self, iotdb_source_dir: str = DEFAULT_IOTDB_SOURCE_DIR):
        """
        初始化PR分析器，使用ClaudeSDKClient和数据库连接

        Args:
            iotdb_source_dir: IoTDB 源码目录路径
        """
        self.iotdb_source_dir = iotdb_source_dir
        self.db = DatabaseManager()

        # Claude SDK 配置
        self.claude_config = {
            "ANTHROPIC_BASE_URL": ANTHROPIC_BASE_URL,
            "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
            # 添加这行来禁用 prompt caching
            # "DISABLE_PROMPT_CACHING": "1",
        }

        # 允许的工具列表（首字母大写，与 SDK 实际使用的格式一致）
        self.allowed_tools = ["Bash", "Read", "Glob", "Grep"]

    async def can_use_tool(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        context: ToolPermissionContext,
    ):
        """
        工具权限回调函数

        由于 cwd 参数已经限制了 CLI 工具的工作目录，
        这里只需要检查：
        1. 工具名称白名单
        2. 敏感文件/目录黑名单
        3. 对于 bash 工具，检查命令是否安全（特别是 git 命令）

        Args:
            tool_name: 工具名称（如 "Read", "Glob", "Grep", "Bash"）
            tool_input: 工具输入参数（如 {"file_path": "..."}）
            context: 工具权限上下文

        Returns:
            PermissionResult: 允许或拒绝的决策
        """

        print("Tool name: ", tool_name)

        # 记录工具调用
        tool_call_info = {
            "name": tool_name,
            "input": tool_input,
            "allowed": False,
        }

        # 1. 检查工具是否在允许列表中
        if tool_name not in self.allowed_tools:
            return PermissionResultDeny(
                message=f"❌ 工具 '{tool_name}' 不在允许列表中（允许: {', '.join(self.allowed_tools)}）",
                interrupt=False,
            )

        # 2. 检查 Read 工具 - 禁止读取敏感文件
        if tool_name == "Read":
            file_path = tool_input.get("file_path", "")

            # 禁止读取敏感文件
            sensitive_patterns = [
                ".env",
                ".password",
                "secret",
                "credentials",
                "config.py",
                ".key",
                ".pem",
            ]
            if any(pattern in file_path.lower() for pattern in sensitive_patterns):
                return PermissionResultDeny(
                    message=f"🚨 禁止读取敏感文件: {file_path}",
                    interrupt=False,
                )

            print(f"   📄 读取文件: {file_path}")
            tool_call_info["allowed"] = True
            self.tool_calls.append(tool_call_info)
            return PermissionResultAllow()

        # 3. 检查 Glob 工具 - 禁止搜索敏感目录
        elif tool_name == "Glob":
            pattern = tool_input.get("pattern", "")
            search_path = tool_input.get("path", "")

            # 禁止搜索敏感目录
            forbidden_patterns = [
                "node_modules",
                ".git",
                ".env",
                "secret",
                "__pycache__",
                ".venv",
            ]
            search_str = f"{search_path} {pattern}".lower()
            if any(forbidden in search_str for forbidden in forbidden_patterns):
                return PermissionResultDeny(
                    message=f"❌ 禁止在敏感目录搜索: path={search_path}, pattern={pattern}",
                    interrupt=False,
                )

            print(f"   📁 查找文件: {pattern}")
            tool_call_info["allowed"] = True
            self.tool_calls.append(tool_call_info)
            return PermissionResultAllow()

        # 4. 检查 Grep 工具 - 直接允许
        elif tool_name == "Grep":
            pattern = tool_input.get("pattern", "")
            print(f"   🔍 搜索: {pattern}")
            tool_call_info["allowed"] = True
            self.tool_calls.append(tool_call_info)
            return PermissionResultAllow()

        # 5. 检查 Bash 工具 - 只允许安全的 git 命令
        elif tool_name == "Bash":
            command = tool_input.get("command", "")

            # 提取命令的第一个词
            cmd_parts = command.strip().split()
            if not cmd_parts:
                return PermissionResultDeny(
                    message=f"❌ Bash 命令为空",
                    interrupt=False,
                )

            first_cmd = cmd_parts[0].lower()

            # 检查是否是 git 命令
            if first_cmd == "git":
                if len(cmd_parts) < 2:
                    return PermissionResultDeny(
                        message=f"❌ Git 命令不完整",
                        interrupt=False,
                    )

                git_subcmd = cmd_parts[1].lower()

                # 允许的安全 git 命令（只读 + checkout）
                safe_git_commands = {
                    "checkout",
                    "status",
                    "log",
                    "show",
                    "diff",
                    "branch",
                    "rev-parse",
                    "ls-tree",
                    "ls-files",
                }

                # 危险命令黑名单
                dangerous_git_commands = {
                    "push",
                    "reset",
                    "clean",
                    "rm",
                    "commit",
                    "rebase",
                    "merge",
                    "pull",
                    "fetch",
                    "add",
                }

                if git_subcmd in dangerous_git_commands:
                    return PermissionResultDeny(
                        message=f"🚨 禁止执行危险的 git 命令: git {git_subcmd}",
                        interrupt=False,
                    )

                if git_subcmd not in safe_git_commands:
                    return PermissionResultDeny(
                        message=f"❌ Git 命令 '{git_subcmd}' 不在允许列表中（允许: {', '.join(sorted(safe_git_commands))}）",
                        interrupt=False,
                    )

                print(f"   🌿 Bash 命令: {command}")
                tool_call_info["allowed"] = True
                self.tool_calls.append(tool_call_info)
                return PermissionResultAllow()
            else:
                # 不是 git 命令，拒绝
                return PermissionResultDeny(
                    message=f"❌ Bash 命令 '{first_cmd}' 不被允许（只允许 git 命令）",
                    interrupt=False,
                )

        # 6. 其他工具
        else:
            return PermissionResultDeny(
                message=f"❌ 未知工具: {tool_name}",
                interrupt=False,
            )

    def get_pr_by_number(self, pr_number: Optional[int] = None) -> Optional[Dict]:
        """
        从数据库获取指定PR的数据，如果没有指定编号则获取最新的PR
        """
        return get_pr_by_number(pr_number, self.db)

    async def analyze_pr(
        self, pr_number: Optional[int] = None, enable_tools: bool = True
    ) -> Dict:
        """
        分析单个PR，如果没有指定编号则分析最新的PR
        使用ClaudeSDKClient进行分析

        Args:
            pr_number: PR编号
            enable_tools: 是否启用工具调用（read, glob, grep）（默认 True）
        """
        # 获取PR数据
        target_pr = self.get_pr_by_number(pr_number)

        if not target_pr:
            if pr_number:
                return {"success": False, "error": f"未找到编号为 {pr_number} 的PR"}
            else:
                return {"success": False, "error": "数据库中没有找到PR数据"}

        pr_number = target_pr["number"]
        print(f"正在分析 PR #{pr_number}: {target_pr['title']}")

        # 重置工具调用记录
        self.tool_calls = []

        try:
            # 获取diff内容
            diff_content = target_pr.get("diff_content", "")
            diff_size = len(diff_content) if diff_content else 0

            # 使用ClaudeSDKClient发送查询（claude-agent-sdk）
            print("🔄 正在初始化 Claude Agent 客户端...")

            # 构建系统提示
            system_prompt = "您是一名时序数据库IoTDB专家，请根据提供的PR信息和本地iotdb源码进行分析，然后提供详细的分析结果。"
            if enable_tools:
                system_prompt += """

**重要：在分析之前，请务必按照以下步骤操作：**
1. 使用 Bash 工具执行 git checkout 命令，将IoTDB源码切换到 PR 的 merge_commit（查询中会提供该 commit SHA）
   - 例如：Bash 工具执行 `git checkout <merge_commit_sha>`
2. 使用 Glob 工具查找 diff 中涉及的源码文件（例如：`**/ClassName.java`）
3. 使用 Read 工具读取这些完整的源码文件
4. 使用 Grep 工具搜索相关的类、方法或关键字以获取更多上下文

注意：Bash 工具只允许执行安全的 git 命令（checkout, status, log, show, diff 等），禁止使用 push、reset、clean 等危险命令。"""
            print(system_prompt)

            # 打印配置信息
            print(f"\n[配置检查] enable_tools={enable_tools}")
            print(f"[配置检查] 使用 can_use_tool 回调进行权限控制")

            async with ClaudeSDKClient(
                options=ClaudeAgentOptions(
                    system_prompt=system_prompt,
                    max_turns=50,
                    cwd=str(self.iotdb_source_dir),  # IoTDB 源码目录
                    env=self.claude_config,  # 传递API配置
                    # 不设置 allowed_tools，而是通过 can_use_tool 回调来控制
                    # allowed_tools=(
                    #         self.allowed_tools if enable_tools else None
                    # ),  # 允许工具
                    can_use_tool=(
                        self.can_use_tool if enable_tools else None
                    ),  # 工具权限回调
                )
            ) as client:
                print("✓ 客户端初始化成功")
                print(f"📦 Diff大小: {diff_size:,} 字符")

                # 构建完整查询
                query = build_analysis_query(target_pr, diff_content)
                query_size = len(query)
                print(
                    f"📊 完整查询大小: {query_size:,} 字符 (~{query_size // 4:,} tokens)"
                )
                print(f"🚀 正在使用 Claude Agent SDK 发送分析请求...")
                print(
                    f"   工具支持: {'启用 (Bash, Read, Glob, Grep)' if enable_tools else '禁用'}"
                )

                await client.query(query)

                # 收集分析结果
                analysis_result = ""
                print("\n=== Claude 分析结果 ===\n")

                async for message in client.receive_response():
                    if hasattr(message, "content"):
                        for block in message.content:
                            # 收集文本内容
                            if hasattr(block, "text"):
                                analysis_result += block.text
                                print(block.text, end="", flush=True)

                print(f"\n=== 分析完成 ===\n")

                # 显示工具调用统计
                if self.tool_calls:
                    print(f"📊 工具调用统计:")
                    print(f"   总计调用: {len(self.tool_calls)} 次")

                    tool_counts = {}
                    for tc in self.tool_calls:
                        if tc.get("allowed", False):
                            tool_name = tc["name"]
                            tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1

                    if tool_counts:
                        for tool_name, count in sorted(tool_counts.items()):
                            print(f"   - {tool_name}: {count} 次")
                    print()
                else:
                    print("ℹ️  未检测到工具调用\n")

                # 返回分析结果
                return {
                    "success": True,
                    "pr_number": pr_number,
                    "pr_title": target_pr["title"],
                    "analysis": analysis_result,
                    "analyzed_at": datetime.now().isoformat(),
                    "pr_data": target_pr,
                }

        except Exception as e:
            import traceback

            error_details = f"{str(e)}\nTraceback:\n{traceback.format_exc()}"
            print(f"\n❌ 错误详情:\n{error_details}")
            return {
                "success": False,
                "pr_number": pr_number,
                "pr_title": target_pr.get("title", ""),
                "error": str(e),
                "error_details": error_details,
                "analyzed_at": datetime.now().isoformat(),
            }

    def close(self):
        """
        关闭数据库连接
        """
        if self.db:
            self.db.close()


async def main():
    """
    主函数 - 使用 ClaudeSDKClient 进行PR分析
    """
    analyzer = PRAnalysisClaudeAgentSDK()

    try:
        print("🚀 IoTDB PR 分析工具 (ClaudeSDKClient)")
        print("=" * 60)

        # 获取 PR 编号
        # pr_number = 15685  # Insert into
        pr_number = 12879

        print("\n" + "=" * 60)
        print("🚀 开始PR分析 (使用 ClaudeSDKClient + 工具调用)...")

        result = await analyzer.analyze_pr(pr_number=pr_number, enable_tools=True)

        if result["success"]:
            print(f"\n✅ 分析完成！")
            print(f"PR #{result['pr_number']}: {result['pr_title']}")
            print(f"\n分析结果:\n{result['analysis']}")
        else:
            print(f"\n❌ 分析失败: {result['error']}")
            if "error_details" in result:
                print(f"\n详细错误:\n{result['error_details']}")

    except KeyboardInterrupt:
        print("\n⏹️ 用户中断操作")
    except ValueError:
        print("\n❌ PR 编号必须是数字")
    except Exception as e:
        print(f"\n❌ 执行过程中出现错误: {e}")
        import traceback

        traceback.print_exc()
    finally:
        analyzer.close()


if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Dict, Optional, List

import anthropic
from database import DatabaseManager
from config import ANTHROPIC_BASE_URL, ANTHROPIC_API_KEY, DEFAULT_IOTDB_SOURCE_DIR

from pr_analysis_common import (
    build_analysis_query,
    get_pr_by_number,
)


def get_tool_definitions() -> List[Dict]:
    """
    获取工具定义（Anthropic API 格式）
    """
    return [
        {
            "name": "read",
            "description": "读取 IoTDB 源码文件的内容。文件路径相对于 IoTDB 源码根目录。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "要读取的文件路径，相对于 IoTDB 源码根目录（如 'iotdb-core/datanode/src/main/java/org/apache/iotdb/db/queryengine/execution/operator/process/TableIntoOperator.java'）",
                    }
                },
                "required": ["file_path"],
            },
        },
        {
            "name": "glob",
            "description": "使用 glob 模式查找匹配的文件。支持 ** 通配符。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob 模式（如 '**/*TableIntoOperator*.java', '**/*.xml'）",
                    },
                    "path": {
                        "type": "string",
                        "description": "搜索路径，相对于 IoTDB 源码根目录（可选，默认为根目录）",
                    },
                },
                "required": ["pattern"],
            },
        },
        {
            "name": "grep",
            "description": "在 IoTDB 源码中搜索匹配的内容。使用正则表达式模式。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "搜索模式（正则表达式）",
                    },
                    "path": {
                        "type": "string",
                        "description": "搜索路径，相对于 IoTDB 源码根目录（可选）",
                    },
                    "file_type": {
                        "type": "string",
                        "description": "文件类型过滤（如 'java', 'py', 'xml'）（可选）",
                    },
                },
                "required": ["pattern"],
            },
        },
        {
            "name": "bash",
            "description": "执行安全的 git 命令（只允许只读命令和 checkout）。在 IoTDB 源码目录中执行。",
            "input_schema": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的 git 命令（如 'git checkout <commit_sha>', 'git status', 'git log'）",
                    }
                },
                "required": ["command"],
            },
        },
    ]


class PRAnalysisAnthropic:
    def __init__(self, iotdb_source_dir: str = DEFAULT_IOTDB_SOURCE_DIR):
        """
        初始化PR分析器，使用Anthropic API和数据库连接

        Args:
            iotdb_source_dir: IoTDB 源码目录路径
        """
        self.iotdb_source_dir = Path(iotdb_source_dir)
        self.db = DatabaseManager()

    def _execute_read_tool(self, file_path: str) -> Dict:
        """
        执行 read 工具：读取文件内容

        Args:
            file_path: 文件路径（相对于 iotdb_source_dir）

        Returns:
            工具执行结果
        """
        try:
            full_path = self.iotdb_source_dir / file_path
            if not full_path.exists():
                return {"success": False, "error": f"文件不存在: {file_path}"}

            # 读取文件内容（限制大小）
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read(500000)  # 限制 500KB

            return {"success": True, "content": content, "file_path": file_path}
        except Exception as e:
            return {"success": False, "error": f"读取文件失败: {str(e)}"}

    def _execute_glob_tool(self, pattern: str, path: str = "") -> Dict:
        """
        执行 glob 工具：查找匹配的文件

        Args:
            pattern: glob 模式（如 "**/*.java"）
            path: 搜索路径（相对于 iotdb_source_dir）

        Returns:
            工具执行结果
        """
        try:
            search_dir = self.iotdb_source_dir / path if path else self.iotdb_source_dir
            matches = list(search_dir.glob(pattern))

            # 转换为相对路径
            relative_paths = [
                str(p.relative_to(self.iotdb_source_dir)) for p in matches[:100]
            ]  # 限制 100 个结果

            return {
                "success": True,
                "matches": relative_paths,
                "count": len(relative_paths),
            }
        except Exception as e:
            return {"success": False, "error": f"Glob 搜索失败: {str(e)}"}

    def _execute_grep_tool(
        self, pattern: str, path: str = "", file_type: str = ""
    ) -> Dict:
        """
        执行 grep 工具：搜索文件内容

        Args:
            pattern: 搜索模式（正则表达式）
            path: 搜索路径（相对于 iotdb_source_dir）
            file_type: 文件类型过滤（如 "java", "py"）

        Returns:
            工具执行结果
        """
        try:
            search_dir = self.iotdb_source_dir / path if path else self.iotdb_source_dir

            # 构建 rg (ripgrep) 命令
            cmd = ["rg", "--json", pattern, str(search_dir)]
            if file_type:
                cmd.extend(["--type", file_type])

            # 执行搜索
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

            # 解析结果
            matches = []
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if data.get("type") == "match":
                        match_data = data.get("data", {})
                        file_path = match_data.get("path", {}).get("text", "")
                        line_number = match_data.get("line_number")
                        line_text = match_data.get("lines", {}).get("text", "").strip()

                        # 转换为相对路径
                        if file_path:
                            rel_path = str(
                                Path(file_path).relative_to(self.iotdb_source_dir)
                            )
                            matches.append(
                                {
                                    "file": rel_path,
                                    "line": line_number,
                                    "content": line_text,
                                }
                            )
                except json.JSONDecodeError:
                    continue

            return {
                "success": True,
                "matches": matches[:50],  # 限制 50 个结果
                "count": len(matches),
            }
        except FileNotFoundError:
            return {
                "success": False,
                "error": "ripgrep (rg) 未安装，请安装: brew install ripgrep",
            }
        except Exception as e:
            return {"success": False, "error": f"Grep 搜索失败: {str(e)}"}

    def _execute_bash_tool(self, command: str) -> Dict:
        """
        执行 bash 工具：只允许安全的 git 命令

        Args:
            command: 要执行的命令

        Returns:
            工具执行结果
        """
        try:
            # 解析命令
            cmd_parts = command.strip().split()
            if not cmd_parts:
                return {"success": False, "error": "命令为空"}

            first_cmd = cmd_parts[0].lower()

            # 只允许 git 命令
            if first_cmd != "git":
                return {
                    "success": False,
                    "error": f"只允许 git 命令，不允许: {first_cmd}",
                }

            if len(cmd_parts) < 2:
                return {"success": False, "error": "Git 命令不完整"}

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
                return {
                    "success": False,
                    "error": f"禁止执行危险的 git 命令: git {git_subcmd}",
                }

            if git_subcmd not in safe_git_commands:
                return {
                    "success": False,
                    "error": f"Git 命令 '{git_subcmd}' 不在允许列表中（允许: {', '.join(sorted(safe_git_commands))}）",
                }

            # 执行命令
            result = subprocess.run(
                cmd_parts,
                cwd=str(self.iotdb_source_dir),
                capture_output=True,
                text=True,
                timeout=30,
            )

            # 合并 stdout 和 stderr
            output = result.stdout
            if result.stderr:
                output += "\n" + result.stderr

            return {
                "success": result.returncode == 0,
                "output": output.strip(),
                "returncode": result.returncode,
            }

        except subprocess.TimeoutExpired:
            return {"success": False, "error": "命令执行超时（30秒）"}
        except Exception as e:
            return {"success": False, "error": f"命令执行失败: {str(e)}"}

    def _execute_tool(self, tool_name: str, tool_input: Dict) -> Dict:
        """
        执行工具调用

        Args:
            tool_name: 工具名称
            tool_input: 工具输入参数

        Returns:
            工具执行结果
        """
        if tool_name == "read":
            return self._execute_read_tool(tool_input.get("file_path", ""))
        elif tool_name == "glob":
            return self._execute_glob_tool(
                tool_input.get("pattern", ""), tool_input.get("path", "") or ""
            )
        elif tool_name == "grep":
            return self._execute_grep_tool(
                tool_input.get("pattern", ""),
                tool_input.get("path", "") or "",
                tool_input.get("file_type", "") or "",
            )
        elif tool_name == "bash":
            return self._execute_bash_tool(tool_input.get("command", ""))
        else:
            return {"success": False, "error": f"未知工具: {tool_name}"}

    def get_pr_by_number(self, pr_number: Optional[int] = None) -> Optional[Dict]:
        """
        从数据库获取指定PR的数据，如果没有指定编号则获取最新的PR
        """
        return get_pr_by_number(pr_number, self.db)

    async def analyze_pr(
        self,
        pr_number: Optional[int] = None,
        max_tokens: int = 16384,
        temperature: float = 0.3,
        enable_tools: bool = True,
        max_tool_rounds: int = 10,
        use_cache: bool = True,
    ) -> Dict:
        """
        使用 Anthropic API 进行 PR 分析（支持工具调用：read, glob, grep + cache_control）

        Args:
            pr_number: PR编号
            max_tokens: 最大输出 tokens（默认 16384）
            temperature: 温度参数，控制输出随机性（0-1，默认 0.3，越低越一致）
            enable_tools: 是否启用工具调用（read, glob, grep）（默认 True）
            max_tool_rounds: 最大工具调用轮数（默认 10）
            use_cache: 是否使用 prompt caching（默认 True）
        """
        # 获取PR数据
        target_pr = self.get_pr_by_number(pr_number)

        if not target_pr:
            if pr_number:
                return {"success": False, "error": f"未找到编号为 {pr_number} 的PR"}
            else:
                return {"success": False, "error": "数据库中没有找到PR数据"}

        pr_number = target_pr["number"]
        print(f"🔍 正在分析 PR #{pr_number}: {target_pr['title']}")

        try:
            # 初始化 Anthropic 客户端
            client = anthropic.Anthropic(
                base_url=ANTHROPIC_BASE_URL, api_key=ANTHROPIC_API_KEY
            )

            # 获取 diff 内容
            diff_content = target_pr.get("diff_content", "")
            diff_size = len(diff_content) if diff_content else 0
            print(f"📦 Diff 大小: {diff_size:,} 字符 (~{diff_size // 4:,} tokens)")

            # 构建完整查询
            query = build_analysis_query(target_pr, diff_content)
            query_size = len(query)
            print(f"📊 完整查询大小: {query_size:,} 字符 (~{query_size // 4:,} tokens)")

            # 构建系统提示
            system_prompt = "您是一名时序数据库IoTDB专家，请根据提供的PR信息和本地iotdb源码进行分析，然后提供详细的分析结果。"
            if enable_tools:
                system_prompt += """

**重要：在分析之前，请务必按照以下步骤操作：**
1. 使用 bash 工具执行 git checkout 命令，将IoTDB源码切换到 PR 的 merge_commit（查询中会提供该 commit SHA）
   - 例如：bash 工具执行 `git checkout <merge_commit_sha>`
2. 使用 glob 工具查找 diff 中涉及的源码文件（例如：`**/ClassName.java`）
3. 使用 read 工具读取这些完整的源码文件
4. 使用 grep 工具搜索相关的类、方法或关键字以获取更多上下文

注意：bash 工具只允许执行安全的 git 命令（checkout, status, log, show, diff 等），禁止使用 push、reset、clean 等危险命令。"""

            print(f"🚀 正在使用 Anthropic API 发送分析请求...")
            print(f"   模型: GLM-4.6")
            print(f"   最大输出 tokens: {max_tokens:,}")
            print(f"   Temperature: {temperature}")
            print(
                f"   工具支持: {'启用 (read, glob, grep, bash)' if enable_tools else '禁用'}"
            )
            print(f"   Prompt Caching: {'启用' if use_cache else '禁用'}")

            # 初始化对话历史（如果使用缓存，在第一条消息上添加 cache_control）
            if use_cache:
                system = [
                    {
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }
                ]
                messages = [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": query,
                                "cache_control": {"type": "ephemeral"},
                            }
                        ],
                    }
                ]
            else:
                system = [
                    {
                        "type": "text",
                        "text": system_prompt,
                    }
                ]
                messages = [
                    {
                        "role": "user",
                        "content": query,
                    }
                ]

            analysis_result = ""
            total_input_tokens = 0
            total_output_tokens = 0
            total_cache_creation_tokens = 0
            total_cache_read_tokens = 0
            tool_call_count = 0

            print(f"\n=== Claude 分析结果 ===\n")

            # 工具调用循环
            for round_num in range(max_tool_rounds):
                stream_params = {
                    # "model": "claude-sonnet-4-5-20250929",
                    "model": "glm-4.6",
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "system": system,
                    "messages": messages,
                }

                # 如果启用工具，添加工具定义
                if enable_tools:
                    stream_params["tools"] = get_tool_definitions()

                # 如果启用缓存，添加必要的 header
                if use_cache:
                    stream_params["extra_headers"] = {
                        "anthropic-beta": "prompt-caching-2024-07-31"
                    }

                # 使用流式 API
                with client.messages.stream(**stream_params) as stream:
                    # 实时打印流式输出
                    for text in stream.text_stream:
                        print(text, end="", flush=True)

                    # 获取完整响应
                    response = stream.get_final_message()

                    # 更新 token 统计
                    total_input_tokens += response.usage.input_tokens
                    total_output_tokens += response.usage.output_tokens

                    # 更新缓存统计（如果有）
                    if hasattr(response.usage, "cache_creation_input_tokens"):
                        total_cache_creation_tokens += (
                            response.usage.cache_creation_input_tokens or 0
                        )
                    if hasattr(response.usage, "cache_read_input_tokens"):
                        total_cache_read_tokens += (
                            response.usage.cache_read_input_tokens or 0
                        )

                    # 检查是否有工具调用
                    has_tool_use = any(
                        block.type == "tool_use" for block in response.content
                    )

                    if has_tool_use:
                        print()  # 工具调用前换行
                        # 处理工具调用
                        tool_results = []
                        for block in response.content:
                            if block.type == "tool_use":
                                tool_call_count += 1
                                tool_name = block.name
                                tool_input = block.input
                                tool_use_id = block.id

                                print(f"🔧 [工具调用 #{tool_call_count}] {tool_name}")

                                # 打印工具参数
                                if tool_name == "read":
                                    print(
                                        f"   📄 读取文件: {tool_input.get('file_path', '')}"
                                    )
                                elif tool_name == "glob":
                                    print(
                                        f"   📁 查找文件: {tool_input.get('pattern', '')}"
                                    )
                                elif tool_name == "grep":
                                    print(
                                        f"   🔍 搜索: {tool_input.get('pattern', '')}"
                                    )
                                elif tool_name == "bash":
                                    print(
                                        f"   🌿 Bash 命令: {tool_input.get('command', '')}"
                                    )

                                # 执行工具
                                tool_result = self._execute_tool(tool_name, tool_input)

                                # 构建工具结果消息
                                if tool_result.get("success"):
                                    # 成功的结果
                                    result_content = json.dumps(
                                        tool_result, ensure_ascii=False, indent=2
                                    )
                                else:
                                    # 失败的结果
                                    result_content = (
                                        f"错误: {tool_result.get('error', '未知错误')}"
                                    )

                                tool_results.append(
                                    {
                                        "type": "tool_result",
                                        "tool_use_id": tool_use_id,
                                        "content": result_content,
                                    }
                                )

                                print(f"   ✓ 执行完成\n")

                        # 将 assistant 的响应添加到历史
                        messages.append(
                            {"role": "assistant", "content": response.content}
                        )

                        # 将工具结果添加到历史
                        messages.append({"role": "user", "content": tool_results})

                    else:
                        # 没有工具调用，说明分析完成
                        for block in response.content:
                            if hasattr(block, "text"):
                                analysis_result += block.text
                        break

            print(f"\n=== 分析完成 ===\n")

            # 打印统计信息
            print(f"📊 Token 使用统计:")
            print(f"   输入 tokens: {total_input_tokens:,}")
            print(f"   输出 tokens: {total_output_tokens:,}")

            if use_cache:
                print(f"   缓存创建 tokens: {total_cache_creation_tokens:,}")
                print(f"   缓存读取 tokens: {total_cache_read_tokens:,}")
                if total_cache_read_tokens > 0:
                    # 缓存读取节省 90% 成本
                    cache_savings = total_cache_read_tokens * 0.9
                    print(f"   💰 缓存节省: ~{cache_savings:,.0f} tokens 成本")

            print(f"   总计 tokens: {total_input_tokens + total_output_tokens:,}")

            if enable_tools:
                print(f"   工具调用次数: {tool_call_count}")

            return {
                "success": True,
                "pr_number": pr_number,
                "analysis": analysis_result,
                "usage": {
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                    "cache_creation_tokens": total_cache_creation_tokens,
                    "cache_read_tokens": total_cache_read_tokens,
                    "tool_calls": tool_call_count,
                },
            }

        except Exception as e:
            error_msg = f"分析过程出错: {str(e)}"
            print(f"❌ {error_msg}")
            import traceback

            traceback.print_exc()
            return {"success": False, "error": error_msg}

    def close(self):
        """
        关闭数据库连接
        """
        if self.db:
            self.db.close()


async def main():
    """
    主函数 - 使用 Anthropic API 进行PR分析
    """
    analyzer = PRAnalysisAnthropic()

    try:
        print("🚀 IoTDB PR 分析工具 (Anthropic API)")
        print("=" * 60)

        # 获取 PR 编号
        pr_number = 13097

        print("\n" + "=" * 60)
        print("🚀 开始PR分析 (使用 Anthropic API + 工具调用 + Cache Control)...")

        result = await analyzer.analyze_pr(
            pr_number=pr_number,
            enable_tools=True,  # 默认启用工具
            use_cache=True,  # 默认启用缓存
        )

        if result["success"]:
            print(f"\n✅ 分析完成！")
            print(f"PR #{result['pr_number']}")

            # 显示 token 使用情况
            usage = result.get("usage", {})
            print(f"\n📊 详细统计:")
            print(f"   输入 tokens: {usage.get('input_tokens', 0):,}")
            print(f"   输出 tokens: {usage.get('output_tokens', 0):,}")
            print(f"   缓存创建: {usage.get('cache_creation_tokens', 0):,}")
            print(f"   缓存读取: {usage.get('cache_read_tokens', 0):,}")
        else:
            print(f"\n❌ 分析失败: {result['error']}")

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

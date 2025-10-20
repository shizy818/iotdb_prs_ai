import asyncio
import json
import os
from typing import Dict, Optional, List
from datetime import datetime
from pathlib import Path
import subprocess

from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
import anthropic

from database import DatabaseManager


def build_analysis_query(pr_data: Dict, diff_content: str) -> str:
    """
    构建完整的一次性PR分析查询（用于小型diff）

    Args:
        pr_data: PR数据
        diff_content: 完整的diff内容
    """
    # 构建评论部分
    if pr_data.get("comments"):
        comments_section = "- PR 讨论评论\n"
        for idx, comment in enumerate(pr_data["comments"], 1):
            comment_time = comment.get("created_at", "")
            comment_user = comment.get("user", "未知用户")
            comment_body = comment.get("body", "")
            comments_section += f"""  评论 {idx} (作者: {comment_user}, 时间: {comment_time}):
{comment_body}
---
"""
    else:
        comments_section = "- PR 讨论评论: 无\n"

    template = """
IoTDB PR详细信息：
- 编号: {number}
- 标题: {title}
- 描述: {body}
- 创建时间: {created_at}
- 合并时间: {merged_at}
- 作者: {user}
- 标签: {labels}
- 代码变更: +{additions} 行, -{deletions} 行
- 分支: {head} -> {base}
- Diff链接: {diff_url}
{comments_section}

这是一个IoTDB的Pull Request，请先阅读上述基本信息。接下来是代码变更的diff内容：

```diff
{diff_content}
```

现在你已经收到了完整的PR信息（包括基本信息和diff内容）。

**重要：在分析之前，请务必使用以下工具读取相关源码文件以便深入理解：**
1. 使用 Glob 工具查找 diff 中涉及的源码文件（例如：`**/ClassName.java`）
2. 使用 Read 工具读取这些完整的源码文件
3. 使用 Grep 工具搜索相关的类、方法或关键字以获取更多上下文

**然后进行深入分析：**
1. 这个PR具体解决了什么技术问题？
2. 如果客户环境没有这个修复，系统可能出现什么具体错误？
3. 可能出现的错误信息、异常堆栈或日志是什么？
4. 对系统稳定性、性能和功能的影响程度？
5. 建议的临时解决方案或规避措施？
6. 推荐的升级优先级？

请提供详细、结构化的分析结果。"""

    return template.format(
        number=pr_data.get("number", ""),
        title=pr_data.get("title", ""),
        body=pr_data.get("body", "无描述"),
        created_at=pr_data.get("created_at", ""),
        merged_at=pr_data.get("merged_at", ""),
        user=pr_data.get("user", ""),
        labels=json.dumps(pr_data.get("labels", []), ensure_ascii=False),
        additions=pr_data.get("additions", 0),
        deletions=pr_data.get("deletions", 0),
        head=pr_data.get("head", ""),
        base=pr_data.get("base", ""),
        comments_section=comments_section,
        diff_url=pr_data.get("diff_url", "无"),
        diff_content=diff_content if diff_content else "无代码变更",
    )


class PRAnalysisWithClaude:
    def __init__(
        self, iotdb_source_dir: str = "/Users/shizy/projects/iotdb_issues_ai/iotdb"
    ):
        """
        初始化PR分析器，使用ClaudeSDKClient和数据库连接

        Args:
            iotdb_source_dir: IoTDB 源码目录路径
        """
        self.db = DatabaseManager()
        self.iotdb_source_dir = Path(iotdb_source_dir)

        # 设置Claude SDK环境变量
        # os.environ["ANTHROPIC_BASE_URL"] = "https://open.bigmodel.cn/api/anthropic"
        # os.environ["ANTHROPIC_API_KEY"] = (
        #    "9be7a6c89bfc4cd99efb491c77140aa4.GI2bDndwSd7hqy69"
        # )
        os.environ["ANTHROPIC_BASE_URL"] = "https://claude.ihainan.me/api"
        os.environ["ANTHROPIC_API_KEY"] = (
            "cr_03077874a9a4ba5a5ff4135387c70f3614ed4e58b949df94e7b6f87282d44483"
        )

    def get_pr_by_number(self, pr_number: Optional[int] = None) -> Optional[Dict]:
        """
        从数据库获取指定PR的数据，如果没有指定编号则获取最新的PR
        """
        try:
            cursor = self.db.connection.cursor(dictionary=True)

            if pr_number:
                query = """
                SELECT number, title, body, created_at, merged_at, user, labels,
                       head, base, additions, deletions, diff_url, comments_url
                FROM iotdb_prs
                WHERE number = %s
                """
                cursor.execute(query, (pr_number,))
            else:
                query = """
                SELECT number, title, body, created_at, merged_at, user, labels,
                       head, base, additions, deletions, diff_url, comments_url
                FROM iotdb_prs
                ORDER BY merged_at DESC
                LIMIT 1
                """
                cursor.execute(query)

            pr = cursor.fetchone()

            if pr:
                # 解析JSON格式的labels
                if pr["labels"]:
                    try:
                        pr["labels"] = json.loads(pr["labels"])
                    except (json.JSONDecodeError, TypeError):
                        pr["labels"] = []
                else:
                    pr["labels"] = []

                # 获取对应的diff内容
                diff_query = """
                SELECT diff_content
                FROM pr_diffs
                WHERE pr_number = %s
                ORDER BY created_at DESC
                LIMIT 1
                """
                cursor.execute(diff_query, (pr["number"],))
                diff_result = cursor.fetchone()

                if diff_result and diff_result["diff_content"]:
                    pr["diff_content"] = diff_result["diff_content"]
                else:
                    pr["diff_content"] = None

                # 获取对应的评论内容
                comments_query = """
                SELECT id, user, body, created_at, updated_at, html_url
                FROM pr_comments
                WHERE pr_number = %s
                ORDER BY created_at ASC
                """
                cursor.execute(comments_query, (pr["number"],))
                comments_results = cursor.fetchall()

                if comments_results:
                    pr["comments"] = comments_results
                else:
                    pr["comments"] = []

            cursor.close()
            return pr

        except Exception as e:
            print(f"从数据库获取PR数据时出错: {e}")
            return None

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
            # 如果没有 ripgrep，回退到 grep
            return {
                "success": False,
                "error": "ripgrep (rg) 未安装，请安装: brew install ripgrep",
            }
        except Exception as e:
            return {"success": False, "error": f"Grep 搜索失败: {str(e)}"}

    def _get_tool_definitions(self) -> List[Dict]:
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
        ]

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
                tool_input.get("pattern", ""), tool_input.get("path", "")
            )
        elif tool_name == "grep":
            return self._execute_grep_tool(
                tool_input.get("pattern", ""),
                tool_input.get("path", ""),
                tool_input.get("file_type", ""),
            )
        else:
            return {"success": False, "error": f"未知工具: {tool_name}"}

    async def analyze_pr_with_anthropic(
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
            client = anthropic.Anthropic()

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
                system_prompt += "\n您可以使用以下工具来读取和搜索 IoTDB 源码：read（读取文件）、glob（查找文件）、grep（搜索内容）。"

            print(f"🚀 正在使用 Anthropic API 发送分析请求...")
            print(f"   模型: claude-sonnet-4-5-20250929")
            print(f"   最大输出 tokens: {max_tokens:,}")
            print(f"   Temperature: {temperature}")
            print(
                f"   工具支持: {'启用 (read, glob, grep)' if enable_tools else '禁用'}"
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
                    "model": "claude-sonnet-4-5-20250929",
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "system": system,
                    "messages": messages,
                }

                # 如果启用工具，添加工具定义
                if enable_tools:
                    stream_params["tools"] = self._get_tool_definitions()

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

            print(f"\n\n=== 分析完成 ===\n")

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

    async def analyze_pr_with_cc_sdk(self, pr_number: Optional[int] = None) -> Dict:
        """
        分析单个PR，如果没有指定编号则分析最新的PR
        使用分批传输策略：先发送基本信息，再分批发送diff内容

        Args:
            pr_number: PR编号
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

        try:
            # 获取diff内容
            diff_content = target_pr.get("diff_content", "")
            diff_size = len(diff_content) if diff_content else 0

            # 使用ClaudeSDKClient发送查询（claude-agent-sdk）
            print("🔄 正在初始化 Claude Agent 客户端...")
            async with ClaudeSDKClient(
                options=ClaudeAgentOptions(
                    system_prompt="您是一名时序数据库IoTDB专家，请根据提供的PR信息和本地iotdb源码进行分析，然后提供详细的分析结果。",
                    max_turns=50,
                    cwd=self.iotdb_source_dir,  # IoTDB 源码目录
                    allowed_tools=["read", "glob", "grep"],  # 允许读取文件
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
                print("📤 正在发送完整的PR分析请求...")

                await client.query(query)

                # 收集分析结果
                analysis_result = ""
                tool_calls = []  # 记录工具调用
                print("\n=== Claude 分析结果 ===\n")

                async for message in client.receive_response():
                    if hasattr(message, "content"):
                        for block in message.content:
                            # 检查工具调用
                            if hasattr(block, "type") and block.type == "tool_use":
                                tool_info = {
                                    "name": getattr(block, "tool_name", "unknown"),
                                    "input": getattr(block, "input", {}),
                                }
                                tool_calls.append(tool_info)
                                print(f"\n🔧 [工具调用] {tool_info['name']}")
                                # 打印工具参数（简化显示）
                                if tool_info["name"] == "read":
                                    file_path = tool_info["input"].get("file_path", "")
                                    print(f"   📄 读取文件: {file_path}")
                                elif tool_info["name"] == "grep":
                                    pattern = tool_info["input"].get("pattern", "")
                                    print(f"   🔍 搜索: {pattern}")
                                elif tool_info["name"] == "glob":
                                    pattern = tool_info["input"].get("pattern", "")
                                    print(f"   📁 查找文件: {pattern}")
                                print()

                            # 收集文本内容
                            if hasattr(block, "text"):
                                analysis_result += block.text
                                print(block.text, end="", flush=True)

                print(f"\n\n=== 分析完成 ===\n")

                # 显示工具调用统计
                if tool_calls:
                    print(f"📊 工具调用统计:")
                    print(f"   总计调用: {len(tool_calls)} 次")
                    tool_counts = {}
                    for tc in tool_calls:
                        tool_counts[tc["name"]] = tool_counts.get(tc["name"], 0) + 1
                    for tool_name, count in tool_counts.items():
                        print(f"   - {tool_name}: {count} 次")
                    print()
                else:
                    print("ℹ️  未检测到工具调用")

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
    主函数 - 统一入口，支持选择使用 ClaudeSDKClient 或 Anthropic API
    """
    analyzer = PRAnalysisWithClaude()

    try:
        print("🚀 IoTDB PR 分析工具")
        print("=" * 60)
        print("请选择分析方式：")
        print("1. 使用 ClaudeSDKClient (支持工具调用、读取源码)")
        print("2. 使用 Anthropic API (支持工具调用 + cache_control)")
        print("=" * 60)

        # 获取用户选择
        choice = input("请输入选项 (1 或 2): ").strip()

        if choice not in ["1", "2"]:
            print("❌ 无效的选项，请输入 1 或 2")
            return

        # 获取 PR 编号
        # pr_number = 14591  # Memory table
        # pr_number = 16487 #
        pr_number = 15685  # Insert into

        print("\n" + "=" * 60)

        if choice == "1":
            # 使用 ClaudeSDKClient
            print("🚀 开始PR分析 (使用 ClaudeSDKClient - 支持工具调用)...")
            result = await analyzer.analyze_pr_with_cc_sdk(pr_number=pr_number)

            if result["success"]:
                print(f"\n✅ 分析完成！")
                print(f"PR #{result['pr_number']}: {result['pr_title']}")
                print(f"\n分析结果:\n{result['analysis']}")
            else:
                print(f"\n❌ 分析失败: {result['error']}")
                if "error_details" in result:
                    print(f"\n详细错误:\n{result['error_details']}")

        else:  # choice == "2"
            # 使用 Anthropic API（默认启用工具和缓存）
            print("🚀 开始PR分析 (使用 Anthropic API + 工具调用 + Cache Control)...")

            result = await analyzer.analyze_pr_with_anthropic(
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

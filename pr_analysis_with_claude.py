import asyncio
import json
import os
from typing import Dict, Optional, cast, Iterable, Any
from datetime import datetime

from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
import anthropic
from anthropic.types import TextBlockParam, MessageParam, CacheControlEphemeralParam

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
    def __init__(self):
        """
        初始化PR分析器，使用ClaudeSDKClient和数据库连接
        """
        self.db = DatabaseManager()

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

    async def analyze_pr_with_anthropic(
        self,
        pr_number: Optional[int] = None,
        max_tokens: int = 8192,
        temperature: float = 0.3,
    ) -> Dict:
        """
        使用 Anthropic API 进行一次性 PR 分析（支持 cache_control 和自定义 max_tokens）

        Args:
            pr_number: PR编号
            max_tokens: 最大输出 tokens（默认 8192）
            temperature: 温度参数，控制输出随机性（0-1，默认 0.3，越低越一致）
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
            system_prompt = "您是一名时序数据库IoTDB专家，请根据提供的PR信息和本地iotdb源码进行分析，然后提供详细的分析结果"

            print(f"🚀 正在使用 Anthropic API 发送分析请求...")
            print(f"   模型: claude-sonnet-4-5-20250929")
            print(f"   最大输出 tokens: {max_tokens:,}")
            print(f"   Temperature: {temperature} (越低越一致)")
            print(f"   使用缓存: 是")

            # 使用流式传输（避免超时问题）
            print(f"\n=== Claude 分析结果 ===\n")

            analysis_result = ""
            usage_info = None

            # 准备缓存控制参数
            cache_control: CacheControlEphemeralParam = CacheControlEphemeralParam(
                type="ephemeral"
            )

            # 准备类型化的参数
            system_params: Iterable[TextBlockParam] = [
                TextBlockParam(
                    type="text", text=system_prompt, cache_control=cache_control
                )
            ]

            # 准备消息参数
            message_params: Iterable[MessageParam] = [
                MessageParam(
                    role="user",
                    content=[
                        TextBlockParam(
                            type="text", text=query, cache_control=cache_control
                        )
                    ],
                )
            ]

            with client.messages.stream(
                model="claude-sonnet-4-5-20250929",
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_params,
                messages=message_params,
                extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
            ) as stream:
                # 实时打印流式内容
                for text in stream.text_stream:
                    print(text, end="", flush=True)
                    analysis_result += text

                # 获取最终的消息对象（包含 usage 信息）
                message = stream.get_final_message()
                usage_info = message.usage

            print(f"\n\n=== 分析完成 ===\n")

            # 打印 token 使用统计
            if usage_info:
                print(f"📊 Token 使用统计:")
                print(f"   输入 tokens: {usage_info.input_tokens:,}")
                if hasattr(usage_info, "cache_creation_input_tokens"):
                    print(
                        f"   缓存创建 tokens: {usage_info.cache_creation_input_tokens:,}"
                    )
                if hasattr(usage_info, "cache_read_input_tokens"):
                    print(f"   缓存读取 tokens: {usage_info.cache_read_input_tokens:,}")
                print(f"   输出 tokens: {usage_info.output_tokens:,}")

                # 计算成本节约
                if (
                    hasattr(usage_info, "cache_read_input_tokens")
                    and usage_info.cache_read_input_tokens > 0
                ):
                    cache_savings = (
                        usage_info.cache_read_input_tokens * 0.9
                    )  # 缓存节省90%成本
                    print(f"   💰 缓存节省: ~{cache_savings:,.0f} tokens 成本")

            return {
                "success": True,
                "pr_number": pr_number,
                "analysis": analysis_result,
                "usage": {
                    "input_tokens": usage_info.input_tokens if usage_info else 0,
                    "output_tokens": usage_info.output_tokens if usage_info else 0,
                    "cache_creation_tokens": (
                        usage_info.cache_creation_input_tokens
                        if usage_info
                        and hasattr(usage_info, "cache_creation_input_tokens")
                        else 0
                    ),
                    "cache_read_tokens": (
                        usage_info.cache_read_input_tokens
                        if usage_info and hasattr(usage_info, "cache_read_input_tokens")
                        else 0
                    ),
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
                    cwd="/Users/shizy/projects/iotdb_issues_ai/iotdb",  # IoTDB 源码目录
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
        print("2. 使用 Anthropic API (支持 cache_control、自定义 max_tokens)")
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
            # 使用 Anthropic API
            print("🚀 开始PR分析 (使用 Anthropic API + Cache Control)...")

            # 可以自定义参数（这里使用默认值，也可以让用户输入）
            result = await analyzer.analyze_pr_with_anthropic(
                pr_number=pr_number,
                max_tokens=8192,  # 可调整
                temperature=0.3,  # 0.3 保持约 90% 的输出一致性
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

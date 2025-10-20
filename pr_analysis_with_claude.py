import asyncio
import json
import os
from typing import Dict, Optional
from datetime import datetime

from claude_code_sdk import ClaudeSDKClient, ClaudeCodeOptions
from database import DatabaseManager


def split_diff_into_chunks(diff_content: str, max_chunk_size: int = 8000) -> list[str]:
    """
    将大型diff分割成多个块

    Args:
        diff_content: 完整的diff内容
        max_chunk_size: 每个块的最大字符数

    Returns:
        diff块列表
    """
    if not diff_content or len(diff_content) <= max_chunk_size:
        return [diff_content] if diff_content else []

    chunks = []
    # 按文件分割diff (以 'diff --git' 为分隔符)
    import re

    file_diffs = re.split(r"(?=diff --git)", diff_content)

    current_chunk = ""
    for file_diff in file_diffs:
        if not file_diff.strip():
            continue

        # 如果单个文件的diff就超过限制，需要进一步分割
        if len(file_diff) > max_chunk_size:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""

            # 分割单个大文件
            for i in range(0, len(file_diff), max_chunk_size):
                chunks.append(file_diff[i : i + max_chunk_size])
        else:
            # 尝试添加到当前块
            if len(current_chunk) + len(file_diff) > max_chunk_size:
                # 当前块已满，保存并开始新块
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = file_diff
            else:
                current_chunk += file_diff

    # 添加最后一个块
    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def build_basic_info_query(pr_data: Dict) -> str:
    """
    构建PR基本信息查询（不包含diff内容）

    Args:
        pr_data: PR数据
    """
    # 构建评论部分
    if pr_data.get("comments"):
        comments_section = "- PR 讨论评论:\n"
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

这是一个IoTDB的Pull Request。我接下来会分批发送代码变更的diff内容，请先阅读上述基本信息。

请回复"已收到基本信息"以确认，然后等待接收diff内容。"""

    return template.format(
        number=pr_data.get("number", ""),
        title=pr_data.get("title", ""),
        body=pr_data.get("body", ""),
        created_at=pr_data.get("created_at", ""),
        merged_at=pr_data.get("merged_at", ""),
        user=pr_data.get("user", ""),
        labels=json.dumps(pr_data.get("labels", []), ensure_ascii=False),
        additions=pr_data.get("additions", 0),
        deletions=pr_data.get("deletions", 0),
        head=pr_data.get("head", ""),
        base=pr_data.get("base", ""),
        diff_url=pr_data.get("diff_url", "无"),
        comments_section=comments_section,
    )


def build_complete_analysis_query(pr_data: Dict, diff_content: str) -> str:
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

现在你已经收到了完整的PR信息（包括基本信息和diff内容），请进行深入分析：

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


def build_diff_chunk_query(
    chunk_content: str, chunk_index: int, total_chunks: int
) -> str:
    """
    构建单个diff块的查询

    Args:
        chunk_content: diff块内容
        chunk_index: 当前块索引 (0-based)
        total_chunks: 总块数
    """
    if total_chunks == 1:
        return f"""
以下是完整的代码变更详情（Diff）：

```diff
{chunk_content}
```

请回复"已收到完整diff"以确认。"""
    else:
        if chunk_index == total_chunks - 1:
            # 最后一块
            return f"""
以下是代码变更的第 {chunk_index + 1}/{total_chunks} 部分（最后一部分）：

```diff
{chunk_content}
```

这是最后一部分diff内容，请回复"已收到全部 {total_chunks} 部分diff"以确认。"""
        else:
            # 中间的块
            return f"""
以下是代码变更的第 {chunk_index + 1}/{total_chunks} 部分：

```diff
{chunk_content}
```

请回复"已收到第 {chunk_index + 1} 部分"以确认，然后等待下一部分。"""


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

    async def analyze_single_pr(self, pr_number: Optional[int] = None) -> Dict:
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
            # 检查diff内容大小
            diff_content = target_pr.get("diff_content", "")
            diff_size = len(diff_content) if diff_content else 0

            # 如果diff小于5000字符，使用一次性发送模式
            use_single_query = diff_size < 5000

            # 使用ClaudeSDKClient发送查询
            print("🔄 正在初始化 Claude SDK 客户端...")
            async with ClaudeSDKClient(
                options=ClaudeCodeOptions(
                    system_prompt="您是一名时序数据库IoTDB专家，请根据提供的PR信息进行分析，然后提供详细的分析结果",
                    permission_mode="plan",
                    max_turns=100,  # 增加轮次以支持多批次传输
                )
            ) as client:
                print("✓ 客户端初始化成功")

                # 根据diff大小选择发送模式
                if use_single_query:
                    print(f"📦 Diff大小: {diff_size:,} 字符 - 使用一次性发送模式")

                    # ========== 一次性发送模式 ==========
                    complete_query = build_complete_analysis_query(
                        target_pr, diff_content
                    )
                    query_size = len(complete_query)
                    print(
                        f"📊 完整查询大小: {query_size:,} 字符 (~{query_size // 4:,} tokens)"
                    )
                    print("📤 正在发送完整的PR分析请求...")

                    await client.query(complete_query)

                    # 收集分析结果
                    analysis_result = ""
                    print("\n=== Claude 分析结果 ===\n")

                    async for message in client.receive_response():
                        if hasattr(message, "content"):
                            for block in message.content:
                                if hasattr(block, "text"):
                                    analysis_result += block.text
                                    print(block.text, end="", flush=True)

                    print(f"\n=== 分析完成 (一次性发送) ===\n")

                else:
                    # 分割diff内容
                    diff_chunks = split_diff_into_chunks(
                        diff_content, max_chunk_size=4000
                    )
                    print(
                        f"📦 Diff大小: {diff_size:,} 字符 - 将分为 {len(diff_chunks)} 个部分进行传输"
                    )

                    # ========== 多轮发送模式 ==========
                    # 步骤1: 先发送基本信息
                    basic_info_query = build_basic_info_query(target_pr)
                    basic_info_size = len(basic_info_query)
                    print(
                        f"📊 基本信息大小: {basic_info_size:,} 字符 (~{basic_info_size // 4:,} tokens)"
                    )
                    print("📤 正在发送PR基本信息...")
                    await client.query(basic_info_query)

                    # 等待确认收到基本信息 - 必须完整消费响应流
                    basic_info_response = ""
                    async for message in client.receive_response():
                        if hasattr(message, "content"):
                            for block in message.content:
                                if hasattr(block, "text") and block.text:
                                    basic_info_response += block.text

                    # 循环结束后，打印一次完整的确认信息
                    if basic_info_response:
                        if len(basic_info_response) > 100:
                            print(f"✓ Claude确认: {basic_info_response[:100]}...")
                        else:
                            print(f"✓ Claude确认: {basic_info_response}")
                    else:
                        print("⚠️  警告: 基本信息未收到确认响应，继续发送diff...")

                    # 步骤2: 分批发送diff内容
                    if diff_chunks:
                        total_chunks = len(diff_chunks)
                        for chunk_idx, chunk_content in enumerate(diff_chunks):
                            if chunk_idx != total_chunks -1:
                                continue

                            diff_chunk_query = build_diff_chunk_query(
                                chunk_content, chunk_idx, total_chunks
                            )
                            chunk_size = len(diff_chunk_query)
                            print(
                                f"\n📊 Diff第{chunk_idx + 1}/{total_chunks}批大小: {chunk_size:,} 字符"
                            )

                            print(f"📤 正在发送Diff第{chunk_idx + 1}批...")
                            await client.query(diff_chunk_query)

                            # 等待确认 - 必须完整消费响应流
                            chunk_response = ""
                            async for message in client.receive_response():
                                if hasattr(message, "content"):
                                    for block in message.content:
                                        if hasattr(block, "text") and block.text:
                                            chunk_response += block.text

                            # 循环结束后，打印一次完整的确认信息
                            if chunk_response:
                                if len(chunk_response) > 100:
                                    print(f"✓ Claude确认: {chunk_response[:100]}...")
                                else:
                                    print(f"✓ Claude确认: {chunk_response}")
                            else:
                                print(
                                    f"⚠️  警告: Diff第{chunk_idx + 1}批未收到确认响应，继续发送下一批..."
                                )
                    else:
                        print("⚠️  没有diff内容")

                    # 步骤3: 发送最终分析请求
                    final_analysis_query = """
现在你已经收到了完整的PR信息（包括基本信息和所有diff内容），请进行深入分析：

1. 这个PR具体解决了什么技术问题？
2. 如果客户环境没有这个修复，系统可能出现什么具体错误？
3. 可能出现的错误信息、异常堆栈或日志是什么？
4. 对系统稳定性、性能和功能的影响程度？
5. 建议的临时解决方案或规避措施？
6. 推荐的升级优先级？

请提供详细、结构化的分析结果。"""

                    print("\n📤 发送最终分析请求...")
                    await client.query(final_analysis_query)

                    # 收集最终分析结果
                    analysis_result = ""
                    print("\n=== Claude 分析结果 ===\n")

                    message_count = 0
                    has_messages = False

                    try:
                        async for message in client.receive_response():
                            message_count += 1
                            has_messages = True

                            if hasattr(message, "content"):
                                for block in message.content:
                                    if hasattr(block, "text"):
                                        analysis_result += block.text
                                        print(block.text, end="", flush=True)
                    except Exception as e:
                        print(f"\n[ERROR] 接收响应时出错: {e}")
                        if not has_messages:
                            raise Exception(
                                f"未收到任何助手消息。可能的原因：API错误、查询内容过大或格式问题。原始错误: {e}"
                            )

                    if not has_messages:
                        raise Exception("未收到任何助手消息。请检查API配置和查询内容。")

                    print(
                        f"\n=== 分析完成 (基本信息 + {total_chunks} 批diff + 分析请求) ===\n"
                    )

                    if not analysis_result:
                        raise Exception("收到消息但没有文本内容。请检查API响应格式。")

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
    主函数 - 使用示例
    """
    analyzer = PRAnalysisWithClaude()

    try:
        print("🚀 开始PR分析 (使用优化的分批传输策略)...")
        print("=" * 60)

        # 分析单个PR
        # pr_number = 14591  # simple
        # pr_number = 16487 # Memory table
        pr_number = 15685 # Insert into
        result = await analyzer.analyze_single_pr(pr_number=pr_number)

        if result["success"]:
            print(f"\n✅ 分析完成！")
            print(f"PR #{result['pr_number']}: {result['pr_title']}")
            print(f"使用了 {result.get('diff_chunks_count', 0)} 个diff批次")
            print(f"\n分析结果:\n{result['analysis']}")
        else:
            print(f"\n❌ 分析失败: {result['error']}")
            if "error_details" in result:
                print(f"\n详细错误:\n{result['error_details']}")

    except KeyboardInterrupt:
        print("\n⏹️ 用户中断操作")
    except Exception as e:
        print(f"\n❌ 执行过程中出现错误: {e}")
        import traceback

        traceback.print_exc()
    finally:
        analyzer.close()


if __name__ == "__main__":
    asyncio.run(main())

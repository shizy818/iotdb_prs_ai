import asyncio
import json
import os
from typing import Dict, Optional
from datetime import datetime

from claude_code_sdk import ClaudeSDKClient, ClaudeCodeOptions
from database import DatabaseManager


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
                FROM pull_requests
                WHERE number = %s
                """
                cursor.execute(query, (pr_number,))
            else:
                query = """
                SELECT number, title, body, created_at, merged_at, user, labels,
                       head, base, additions, deletions, diff_url, comments_url
                FROM pull_requests
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

    def build_analysis_query(self, pr_data: Dict) -> str:
        """
        构建PR分析查询模板
        """
        # 构建diff部分
        if pr_data.get("diff_content"):
            diff_section = f"""
- 代码变更详情（Diff）:
```diff
{pr_data.get("diff_content")}
```
"""
        else:
            diff_section = f"- Diff链接: {pr_data.get('diff_url', '无')}"

        # 构建评论部分
        comments_section = ""
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
{diff_section}
{comments_section}

请从以下角度进行深入分析：
1. 这个PR具体解决了什么技术问题？
2. 如果客户环境没有这个修复，系统可能出现什么具体错误？
3. 可能出现的错误信息、异常堆栈或日志是什么？
4. 对系统稳定性、性能和功能的影响程度？
5. 建议的临时解决方案或规避措施？
6. 推荐的升级优先级？"""

        return template.format(
            number=pr_data.get("number", ""),
            title=pr_data.get("title", ""),
            # body=pr_data.get('body', '')[:3000] if pr_data.get('body') else '',  # 限制描述长度
            body=pr_data.get("body", ""),
            created_at=pr_data.get("created_at", ""),
            merged_at=pr_data.get("merged_at", ""),
            user=pr_data.get("user", ""),
            labels=json.dumps(pr_data.get("labels", []), ensure_ascii=False),
            additions=pr_data.get("additions", 0),
            deletions=pr_data.get("deletions", 0),
            head=pr_data.get("head", ""),
            base=pr_data.get("base", ""),
            diff_section=diff_section,
            comments_section=comments_section,
        )

    async def analyze_single_pr(self, pr_number: Optional[int] = None) -> Dict:
        """
        分析单个PR，如果没有指定编号则分析最新的PR
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
            # 构建分析查询
            query = self.build_analysis_query(target_pr)
            print(query)

            # 使用ClaudeSDKClient发送查询
            async with ClaudeSDKClient(
                options=ClaudeCodeOptions(
                    system_prompt="您是一名时序数据库IoTDB专家，请根据提供的PR信息进行详细分析，提供完整的分析结果。",
                    max_turns=5,  # 增加轮次以确保完整响应
                )
            ) as client:
                # 发送查询
                await client.query(query)

                # 收集响应
                analysis_result = ""
                print("\n=== Claude 分析结果 ===\n")

                # 接收所有消息直到结束
                # message_count = 0
                async for message in client.receive_response():
                    # message_count += 1
                    # print(f"[DEBUG] 收到第 {message_count} 个消息，类型: {type(message)}")

                    if hasattr(message, "content"):
                        for block in message.content:
                            if hasattr(block, "text"):
                                analysis_result += block.text

                # print(f"\n\n=== 分析完成 (共收到 {message_count} 个消息) ===\n")
                # print(f"[DEBUG] 累积结果长度: {len(analysis_result)} 字符\n")

                return {
                    "success": True,
                    "pr_number": pr_number,
                    "pr_title": target_pr["title"],
                    "analysis": analysis_result,
                    "analyzed_at": datetime.now().isoformat(),
                }

        except Exception as e:
            return {
                "success": False,
                "pr_number": pr_number,
                "pr_title": target_pr.get("title", ""),
                "error": str(e),
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
        print("🚀 开始PR分析...")

        # 分析单个PR (最新的PR)
        print("\n📋 分析最新PR...")
        result = await analyzer.analyze_single_pr()

        if result["success"]:
            print(f"\n✅ 分析完成！")
            print(f"PR #{result['pr_number']}: {result['pr_title']}")
            print(f"\n分析结果:\n{result['analysis']}")
        else:
            print(f"\n❌ 分析失败: {result['error']}")

    except KeyboardInterrupt:
        print("\n⏹️ 用户中断操作")
    except Exception as e:
        print(f"\n❌ 执行过程中出现错误: {e}")
    finally:
        analyzer.close()


if __name__ == "__main__":
    asyncio.run(main())

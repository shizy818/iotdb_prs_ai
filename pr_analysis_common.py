import json
from typing import Dict, Optional
from pathlib import Path

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
- 合并Commit: {merge_commit}
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
        merge_commit=pr_data.get("merge_commit", "无"),
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


def get_pr_by_number(
    pr_number: Optional[int] = None, db: Optional[DatabaseManager] = None
) -> Optional[Dict]:
    """
    从数据库获取指定PR的数据，如果没有指定编号则获取最新的PR

    Args:
        pr_number: PR编号
        db: DatabaseManager实例，如果不提供则内部创建（仅用于兼容性）
    """
    if db is None:
        db = DatabaseManager()
        should_close = True
    else:
        should_close = False

    try:
        cursor = db.connection.cursor(dictionary=True)

        if pr_number:
            query = """
            SELECT number, title, body, created_at, merged_at, user, labels,
                   head, base, additions, deletions, diff_url, comments_url, merge_commit
            FROM iotdb_prs
            WHERE number = %s
            """
            cursor.execute(query, (pr_number,))
        else:
            query = """
            SELECT number, title, body, created_at, merged_at, user, labels,
                   head, base, additions, deletions, diff_url, comments_url, merge_commit
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
        if should_close:
            db.close()
        return pr

    except Exception as e:
        print(f"从数据库获取PR数据时出错: {e}")
        if should_close:
            db.close()
        return None

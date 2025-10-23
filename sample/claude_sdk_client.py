#!/usr/bin/env python3

import sys
from pathlib import Path

# 添加父目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# legal-agent.py
import asyncio
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
from config import ANTHROPIC_BASE_URL, ANTHROPIC_API_KEY

# Claude SDK 配置
claude_config = {
    "ANTHROPIC_BASE_URL": ANTHROPIC_BASE_URL,
    "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
}


async def main():
    async with ClaudeSDKClient(
        options=ClaudeAgentOptions(
            permission_mode="plan",
            system_prompt="您是一名时序数据库IoTDB专家。",
            max_turns=2,
            env=claude_config,
        )
    ) as client:
        # 发送查询
        await client.query("分析SharedTsBlockQueue的作用")

        # 流式传输响应
        async for message in client.receive_response():
            if hasattr(message, "content"):
                # 在内容到达时打印流式内容
                for block in message.content:
                    if hasattr(block, "text"):
                        print(block.text, end="", flush=True)


if __name__ == "__main__":
    asyncio.run(main())

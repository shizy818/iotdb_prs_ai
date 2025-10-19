# legal-agent.py
import asyncio
from claude_code_sdk import ClaudeSDKClient, ClaudeCodeOptions

import os

os.environ["ANTHROPIC_BASE_URL"] = "https://open.bigmodel.cn/api/anthropic"
os.environ["ANTHROPIC_API_KEY"] = "9be7a6c89bfc4cd99efb491c77140aa4.GI2bDndwSd7hqy69"


async def main():
    async with ClaudeSDKClient(
        options=ClaudeCodeOptions(
            permission_mode="plan",
            system_prompt="您是一名时序数据库IoTDB专家。",
            max_turns=2,
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

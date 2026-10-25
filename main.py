import re
from astrbot.api.event import filter
from astrbot.api.star import Star
from astrbot.api import logger

class AtNicknameFixer(Star):
    """在LLM请求前，用mentions字段中的username替换content中的<@OpenID>标记"""

    @filter.on_llm_request()
    async def fix_at_nickname(self, event, req):
        try:
            # 获取原始消息对象（botpy 的 GroupMessage 对象）
            raw_msg = event.message_obj.raw_message
            if not raw_msg or not hasattr(raw_msg, 'mentions'):
                return

            mentions = raw_msg.mentions
            content = getattr(raw_msg, 'content', '')

            if not mentions or not content:
                return

            # 构建 OpenID -> username 的映射
            id_to_name = {}
            for user in mentions:
                openid = getattr(user, 'member_openid', None) or getattr(user, 'id', None)
                username = getattr(user, 'username', None)
                if openid and username:
                    id_to_name[openid] = username

            if not id_to_name:
                return

            # 替换 <@OpenID> 为 @username
            def replace_mention(match):
                openid = match.group(1)
                return f"@{id_to_name.get(openid, openid)}"

            new_content = re.sub(r'<@([A-Z0-9]+)>', replace_mention, content)

            # 将修改后的文本写回 event.message_obj.message_str
            # 这是 LLM 实际读取的字段
            event.message_obj.message_str = new_content
            logger.info(f"[AtNicknameFixer] 已将 @OpenID 替换为昵称，新文本: {new_content}")

        except Exception as e:
            logger.error(f"[AtNicknameFixer] 处理 @ 昵称时出错: {e}")
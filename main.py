import re
from astrbot.api.event import filter
from astrbot.api.star import Star
from astrbot.api import logger

class AtNicknameFixer(Star):
    """在LLM请求前，用mentions字段中的username替换content中的<@OpenID>标记"""

    @filter.on_llm_request()
    async def fix_at_nickname(self, event, req):
        # 在 fix_at_nickname 方法开头添加
        logger.info(f"[AtNicknameFixer] raw_msg type: {type(raw_msg)}")
        logger.info(f"[AtNicknameFixer] raw_msg attrs: {[a for a in dir(raw_msg) if not a.startswith('__')]}")
        if hasattr(raw_msg, 'mentions'):
            logger.info(f"[AtNicknameFixer] raw_msg.mentions: {raw_msg.mentions}")
        try:
            raw_msg = event.message_obj.raw_message
            if not raw_msg:
                return

            # 兼容 botpy 对象：mentions 可能是 raw_msg.mentions 或 raw_msg.message.mentions
            mentions = getattr(raw_msg, 'mentions', None) or getattr(getattr(raw_msg, 'message', None), 'mentions', None)
            if not mentions:
                return

            content = getattr(raw_msg, 'content', '')
            if not content:
                return

            # 构建 OpenID -> username 映射（兼容多种属性名）
            id_to_name = {}
            for user in mentions:
                # 尝试从 user 对象本身或其 member/user 子对象获取信息
                openid = (
                    getattr(user, 'member_openid', None)
                    or getattr(user, 'id', None)
                    or getattr(getattr(user, 'member', None), 'member_openid', None)
                    or getattr(getattr(user, 'user', None), 'id', None)
                )
                username = (
                    getattr(user, 'username', None)
                    or getattr(user, 'nickname', None)
                    or getattr(getattr(user, 'member', None), 'username', None)
                    or getattr(getattr(user, 'user', None), 'username', None)
                )
                if openid and username:
                    id_to_name[openid] = username

            if not id_to_name:
                logger.warning("[AtNicknameFixer] 未能从 mentions 中解析出有效的 OpenID -> username 映射")
                return

            # 替换 <@OpenID> 为 @username
            def replace_mention(match):
                openid = match.group(1)
                return f"@{id_to_name.get(openid, openid)}"

            new_content = re.sub(r'<@([A-Z0-9]+)>', replace_mention, content)

            # 将修改后的文本写回，供LLM读取
            event.message_obj.message_str = new_content
            logger.info(f"[AtNicknameFixer] 替换成功，新文本: {new_content}")

        except Exception as e:
            logger.error(f"[AtNicknameFixer] 处理 @ 昵称时出错: {e}")
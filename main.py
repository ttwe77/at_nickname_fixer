import re
from astrbot.api.event import filter
from astrbot.api.star import Star
from astrbot.api import logger


class AtNicknameFixer(Star):
    """在LLM请求前，用mentions字段中的username替换content中的<@OpenID>标记"""

    @filter.on_llm_request()
    async def fix_at_nickname(self, event, req):
        logger.debug("[AtNicknameFixer] ===== 开始处理 LLM 请求中的 @ 昵称 =====")
        try:
            # 1. 安全地获取 raw_message，避免 UnboundLocalError
            logger.debug("[AtNicknameFixer] [步骤1] 尝试获取 event.message_obj")
            message_obj = getattr(event, 'message_obj', None)
            if message_obj is None:
                logger.warning("[AtNicknameFixer] event.message_obj 为 None，跳过处理")
                return
            logger.debug(
                f"[AtNicknameFixer] 获取到 message_obj，类型: {type(message_obj).__name__}"
            )

            raw_msg = getattr(message_obj, 'raw_message', None)
            if raw_msg is None:
                logger.warning("[AtNicknameFixer] raw_message 为 None，跳过处理")
                return
            logger.debug(
                f"[AtNicknameFixer] 获取到 raw_message，类型: {type(raw_msg).__name__}"
            )

            # 2. 安全地获取 mentions 列表
            # botpy 的 GroupMessage 在 __slots__ 中定义了 mentions
            logger.debug("[AtNicknameFixer] [步骤2] 尝试获取 mentions 列表")
            mentions = getattr(raw_msg, 'mentions', None)
            if not mentions:
                logger.info("[AtNicknameFixer] 消息中没有 mentions 字段或为空，无需处理")
                return
            logger.debug(
                f"[AtNicknameFixer] 获取到 mentions 列表，数量: {len(mentions)}"
            )

            # 3. 安全地获取 content
            logger.debug("[AtNicknameFixer] [步骤3] 尝试获取 content")
            content = getattr(raw_msg, 'content', '')
            if not content:
                logger.info("[AtNicknameFixer] 消息 content 为空，无需处理")
                return
            logger.debug(f"[AtNicknameFixer] 原始 content: {content!r}")

            # 4. 构建 OpenID -> username 映射
            logger.debug("[AtNicknameFixer] [步骤4] 开始构建 OpenID -> username 映射")
            id_to_name = {}
            for idx, user in enumerate(mentions):
                # botpy 的 mentions 列表元素通常是 _User 对象
                # 优先使用 member_openid（群聊场景），其次 id
                openid = (
                    getattr(user, 'member_openid', None)
                    or getattr(user, 'id', None)
                )
                # 获取昵称字段 username
                username = getattr(user, 'username', None)

                logger.debug(
                    f"[AtNicknameFixer] 解析 mentions[{idx}]: "
                    f"类型={type(user).__name__}, openid={openid!r}, username={username!r}"
                )

                if openid and username:
                    id_to_name[openid] = username
                else:
                    logger.debug(
                        f"[AtNicknameFixer] mentions[{idx}] 缺少 openid 或 username，已跳过"
                    )

            if not id_to_name:
                logger.warning(
                    "[AtNicknameFixer] 未能从 mentions 中解析出有效的 OpenID -> username 映射"
                )
                return
            logger.debug(f"[AtNicknameFixer] 映射构建完成: {id_to_name}")

            # 5. 替换 <@OpenID> 为 @username
            logger.debug("[AtNicknameFixer] [步骤5] 开始执行 <@OpenID> 替换")
            matched_records = []  # 记录每个匹配到的 OpenID 及替换结果

            def replace_mention(match):
                openid = match.group(1)
                hit = openid in id_to_name
                name = id_to_name.get(openid, openid)
                matched_records.append((openid, name, hit))
                return f"@{name}"

            new_content = re.sub(r'<@([A-Za-z0-9]+)>', replace_mention, content)

            if matched_records:
                for i, (openid, name, hit) in enumerate(matched_records):
                    logger.debug(
                        f"[AtNicknameFixer] 匹配[{i}]: openid={openid!r} -> "
                        f"@{name} (命中映射: {hit})"
                    )
            else:
                logger.debug(
                    "[AtNicknameFixer] 正则未匹配到任何 <@OpenID> 标记"
                )

            if new_content == content:
                logger.info("[AtNicknameFixer] 替换前后内容相同，无需修改")
                return

            # 6. 将修改后的文本写回，供 LLM 读取
            logger.debug("[AtNicknameFixer] [步骤6] 将修改后的文本写回 message_obj.message_str")
            message_obj.message_str = new_content
            logger.info(f"[AtNicknameFixer] 替换成功，新文本: {new_content!r}")
            logger.debug("[AtNicknameFixer] ===== 处理完成 =====")

        except Exception as e:
            logger.error(
                f"[AtNicknameFixer] 处理 @ 昵称时发生未预期错误: {e}",
                exc_info=True,
            )
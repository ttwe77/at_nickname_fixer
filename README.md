# AstrBot 插件：At 昵称修复

> 修复 QQ 官方机器人（`qq_official`）群聊中，模型看不到被 @ 用户昵称的问题。

插件识别名：`astrbot_plugin_at_nickname_fixer`  
当前版本：`v1.1.6`　|　作者：`ttwe77`　|　适用 AstrBot：`>= 4.17.0`

---

## 一、问题背景

在 QQ 官方机器人适配器下，群聊消息（`GROUP_MESSAGE_CREATE`）进入 AstrBot 后，`content` 里只保留了 `<@OpenID>` 形式的占位符，例如：

```text
[At:D024...] 这个人的名字叫啥<@7266...>
```

而用户的真实昵称其实存在于原始事件的 `mentions` 数组中，字段为 `User.username`。由于 `content` 中并没有昵称，模型只能看到一个无意义的 OpenID，于是会出现"不知道被 @ 的是谁"的回答。

排查过程中确认了两个常见误区：

- **升级 AstrBot 核心**：相关修复主要处理**出站**消息格式，不会补全**入站**消息中的昵称。
- **使用 AstrNa 等成员查询插件**：在 `qq_official` 平台调用成员资料接口会返回 `unsupported_platform`，无法通过接口反查昵称。

因此，本插件采用最直接的方式：**在 LLM 请求发出前，用事件自带的 `mentions.username` 就地替换 `<@OpenID>`**，不依赖任何额外接口。

---

## 二、工作原理

插件监听 `OnLLMRequestEvent`（`@filter.on_llm_request()`），在每一轮 LLM 请求前处理当前用户输入：

```text
QQ 群消息
  content:  "这个人的名字叫啥<@7266...>"
  mentions: [ { member_openid: "D024...", username: "鲸鱼娘" } ]
        │
        ▼
OnLLMRequestEvent → AtNicknameFixer.fix_at_nickname(event, req)
        │
        ├─ 1. 安全获取 event.message_obj / raw_message（getattr，避免空值异常）
        ├─ 2. 读取 raw_message.mentions，为空则跳过
        ├─ 3. 读取 raw_message.content，为空则跳过
        ├─ 4. 构建映射：member_openid（群聊）或 id → username
        ├─ 5. 正则 <@([A-Za-z0-9]+)> 替换为 @昵称
        └─ 6. 写回 req.prompt（LLM 实际读取的当前输入）
        │
        ▼
模型看到：
"@鲸鱼娘 这个人的名字叫啥@VeryStorm181096"
```

几个关键实现点：

| 实现 | 说明 |
| --- | --- |
| `@filter.on_llm_request()` | AstrBot 的 LLM 请求钩子，可在此修改即将发送给模型的内容 |
| `getattr` 安全取值 | 兼容不同 botpy 版本的 `message_obj` / `raw_message` 结构，避免 `UnboundLocalError` |
| `member_openid` 优先，其次 `id` | 群聊场景下 `member_openid` 才是消息中出现的那串 OpenID |
| 正则替换 | `<@([A-Za-z0-9]+)>` 匹配所有 @ 标记，逐个查表替换 |
| 写回 `req.prompt` | **必须写回 `req.prompt`**；写 `message_obj.message_str` 不会影响模型输入 |
| 未命中保留原样 | OpenID 不在 `mentions` 中时，替换为 `@原OpenID`，不丢失信息 |

---

## 三、效果示例

修复前：

```text
用户：@鲸鱼娘 这个人的名字叫啥 @VeryStorm181096
模型：抱歉，我无法看到被 @ 用户的名字。
```

修复后：

```text
用户：@鲸鱼娘 这个人的名字叫啥 @VeryStorm181096
模型：@VeryStorm181096 名字都写你脸上了还问，你无敌了
```

---

## 四、支持的平台

- `qq_official`（QQ 官方机器人适配器）
- `qq_official_webhook`（Webhook 接入方式）

插件只针对上述平台的入站消息做了适配；其他平台通常已在消息体里携带昵称，无需处理。在非目标平台上，由于 `mentions` 为空或没有 `username` 字段，插件会直接跳过，不会影响原有逻辑。

---

## 五、安装

1. 将本仓库放入 AstrBot 的插件目录：

   ```text
   AstrBot/data/plugins/astrbot_plugin_at_nickname_fixer/
   ```

2. 在 AstrBot WebUI 的「插件管理」中重载插件，或重启 AstrBot。
3. 确认插件状态为已启用。

也可以直接在插件市场搜索「At昵称修复」安装。

---

## 六、配置

**无需任何配置。** 插件不带配置文件，也不注册指令，安装后自动生效。

---

## 七、日志与排查

插件在 `debug` 级别输出完整处理链路，排查时可将日志级别调整为 `DEBUG`。可参考以下信息判断问题位置：

- `event.message_obj 为 None` / `raw_message 为 None`：当前平台未提供原始消息对象。
- `消息中没有 mentions 字段或为空`：该消息没有 @ 任何人，属正常跳过。
- `未能从 mentions 中解析出有效的 OpenID -> username 映射`：`mentions` 结构异常，建议打印对象结构确认字段名。
- `正则未匹配到任何 <@OpenID> 标记`：`content` 中的 @ 形式与 `<@OpenID>` 不一致。
- `替换前后内容相同`：所有命中的 OpenID 都在映射中，但没有实际变化（通常说明映射为空）。
- `替换成功，新 prompt: ...`：替换已生效，可直接核对内容是否正确。

若日志显示替换成功但模型仍"不认识"被 @ 的人，优先检查是否写回了错误字段——本插件写回的是 `req.prompt`。

---

## 八、已知限制与后续优化

- **拼接问题**：替换后的 `@昵称` 与前后文之间没有空格，可能出现黏连（如 `@鲸鱼娘这个人的名字`）。后续计划在昵称后补一个空格。
- **多轮上下文**：插件只处理当前轮 `req.prompt`。若历史上下文（`req.contexts`）中仍保留 `<@OpenID>`，模型在回看历史时依然可能看到 OpenID，后续可考虑一并清洗。
- **昵称可靠性**：昵称完全依赖事件携带的 `mentions[].username`。如果平台未下发该字段，插件无法凭空补全。
- **仅覆盖入站**：出站消息（回复中的 @ 渲染）由 AstrBot 核心与适配器负责，不在本插件范围内。

---

## 九、目录结构

```text
at_nickname_fixer/
├── main.py         # 插件实现：OnLLMRequestEvent 钩子与 @ 昵称替换
├── metadata.yaml   # 插件元数据（名称、版本、作者、支持平台等）
├── README.md       # 本说明
└── LICENSE         # AGPL-3.0
```

> 注意：AstrBot 插件元数据文件是 `metadata.yaml`，不是 `plugin.json`。

---

## 十、参考

- [AstrBot 仓库](https://github.com/AstrBotDevs/AstrBot)
- [AstrBot 插件开发文档（中文）](https://docs.astrbot.app/dev/star/plugin-new.html)
- [AstrBot 插件开发文档（English）](https://docs.astrbot.app/en/dev/star/plugin-new.html)

---

## 十一、许可证

本项目采用 [AGPL-3.0](LICENSE) 许可证。

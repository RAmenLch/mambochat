# MamboChat Context Caching Usage Guide

> For everyday users. This document helps you understand: which daily operations make long-conversation input costs higher, which do not, and how to develop cost-saving habits.
> It only concerns cost — it does not affect answer quality.

---

## 1. What Is Context Caching

Every time you send a message to the AI, the system resends the **entire conversation starting from the first message** so that the model can "remember" the previous dialogue. The longer the conversation, the more content is sent each time.

Providers (such as DeepSeek) offer an automatic optimization: if the **beginning of two requests is exactly identical**, that repeated prefix is cached, and the cached portion is billed at a **lower price** (about 1/10 of the original).

Key rules:

- **Must match verbatim**: Caching requires the prefix starting from the first message to be exactly the same; once the prefix changes, everything after the change point is billed at full price **for that request**.
- **The earlier, the more critical**: Any change to the beginning of the request (the system prompt area) invalidates the cache for the entire conversation; changing only messages near the end has almost no impact.
- **Cache expires**: If you pause the conversation for a long time, the cache naturally expires, and the next request is billed at full price. This is normal and requires no action.
- **Only affects cost**: Whether the cache is hit has nothing to do with answer quality.

> **Scope**: This document analyzes the impact on caching and cost when you **change configuration or content mid-conversation** and then continue that conversation. If you configure everything first and then **start a new conversation**, you don't need to worry about these effects — the new conversation rebuilds its own cache; and as long as you don't continue the old conversation, its cache won't be damaged by configuration changes either.

---

## 2. Which Operations Break the Cache

To determine whether an operation breaks the cache and how costly it is, just look at one thing: **where in the request the change ultimately lands**.

The request structure is fixed:

```
System prompt (very beginning) + history messages (in chronological order)
```

- Change lands in the **system prompt** → entire conversation cache invalidated (severe)
- Change lands in the middle of the **history messages** → cache invalidated from that point (severity depends on position)
- Change **does not enter the request content** → cache unaffected

> Note: after the cache is broken, **only the immediately following first request** is billed at full price; the system then rebuilds the cache with the new prefix, and subsequent requests enjoy the cached price again.

### 1. Changing "system prompt" content → Severe: entire conversation cache invalidated

**This is the most impactful category.** The system prompt sits at the very beginning of every request; any change invalidates the cache from the very start, and **the first request afterwards is billed at full price** (the cache is then rebuilt with the new prefix, restoring the discount for subsequent requests).

The key point: **regardless of which feature entry you use to make the change, the effect is exactly the same.** For example, "editing the Agent's system prompt" and "editing the conversation's system prompt" have identical cache impact — both cause full invalidation.

Common entries (frontend features):

| Frontend operation | Description |
|---------|------|
| Edit the system prompt in **conversation settings** | Directly rewrites the prompt |
| Edit the system prompt in **Agent editing** | Identical impact to the above |
| Mount, edit, or publish a new version of a **system prompt resource** | Resource content is spliced into the prompt |
| Mount or switch **message templates** in **conversation settings** | Template content is spliced into the prompt (different from mounting in the input box toolbar — see category 2) |
| Modify a **knowledge base's name or description** | Knowledge base info is written into the prompt (changing document content doesn't affect it — see category 3) |
| Modify a **skill's name or description** | The skill list is written into the prompt (changing files inside the skill doesn't affect it — see category 3) |
| Modify a **sub-agent's name or description** | The sub-agent list is written into the prompt |
| Switch **web search mode** (off / read-only / search-and-read) | Mode description is written into the prompt and available tools change |
| Mount/unmount **MCP services**, enable/disable **suggested tools** | Tool info is written into the prompt |
| Modify the **description of a mounted Backend** | Backend description is written into the prompt |
| Switch **model or provider** | Caches of different models are entirely incompatible, so full invalidation is inevitable |

### 2. Changing "history message" content → Impact depends on position

- **Editing or deleting a history message** → cache invalidated from the edited message onwards
- **Regenerating from a middle message** → invalidated from that message onwards
- **Switching message branches** → invalidated from the branch point onwards
- **Mounting a message template in the input box and sending it** (toolbar mounting) → the template content is injected into this message and, per the template's "participation length" setting, participates in the context for the following rounds; once the participation rounds are used up, the template disappears from subsequent requests, the prefix changes at the **QA pair where the template was mounted**, and the cache after that position is invalidated

> Rule: the earlier the change and the longer the conversation, the higher the cost; changing only the last message has little impact.
> About toolbar-mounted templates: the breakage is limited to the QA pair where the template was mounted and what follows — **not the whole conversation**; if the template's "participation length" is set to 0, the template doesn't enter the context, so the cache is unaffected.

### 3. Modifying content that "doesn't enter the request" → Cache unaffected

- **Document content inside a knowledge base** (re-uploading, updating chunks) — retrieval happens during answering and doesn't occupy the beginning of the request
- **File content inside a skill** — skills are read on demand; file content doesn't enter the prompt

### 4. Proactively compressing history → Cost-effective

- **Compressing history (manual summary)**: the dialogue before the compression point is replaced with a short summary. This "breaks" the original cache, but it's an **intentional, cost-effective** operation — every subsequent request becomes much shorter, saving significant money over the long run.
- **Automatic summarization**: same principle as manual compression; it's the system's automatic cost-saving mechanism when a conversation gets too long.

### 5. Other cases that don't break the cache but lower the hit rate

The following cases **don't break the cache**, but they do lower the cache hit rate:

- **Tools returning large results**: when a tool (such as web search, code execution, etc.) returns a very large result, that result is written into the context as a new input message. The higher the share of new input, the lower the share of cacheable content, and the cache hit rate drops accordingly.
- **AI moderation feature**: AI moderation essentially starts a separate, extremely short conversation. Because the share of "new input messages" is very high in a short conversation, the cache hit rate drops noticeably — but such conversations are usually very short, so the actual overhead is generally small.

---

## 3. Which Operations Do NOT Break the Cache (Safe to Use)

The following routine operations don't affect cache hits:

- Normally sending new messages, uploading attachments, asking follow-ups
- Modifying **document content in a knowledge base** (re-uploading, updating chunks)
- Modifying **file content inside a skill**
- **Regenerating a reply** from a message (the new request only contains history up to that message, exactly reusing the existing cache — actually saves money)
- Viewing historical versions, comparing diffs, **rolling back workspace files** (version control/rollback targets workspace file content, which doesn't enter the request prefix; rollback records also don't enter the context)
- Changing the conversation **title**, archiving, exporting, importing conversations
- Viewing request logs, switching UI themes, and other display-only operations

> Note the distinction: this refers to **version control/rollback of workspace files**. If you roll back **system prompts, message templates**, or other resource versions that get spliced into the prompt in "Resource Management", that still falls under category 1 and breaks the cache.

---

## 4. Practical Cost-Saving Tips

1. **Configure before chatting**: before starting a long conversation, set up the system prompt, mounted resources, message templates, and web search mode all at once; try not to adjust them mid-conversation.
2. **Be careful with the beginning of long conversations**: any operation that rewrites the system prompt (changing the conversation or Agent prompt, switching mounts, editing skill/sub-agent descriptions, etc.) has the same, maximum cost in long conversations — when adjustment is unavoidable, prefer **starting a new conversation**.
3. **Both ways to correct an answer save money**: when unsatisfied with the AI's reply, there are two common approaches — click **regenerate** on the target message, or send a new message pointing out the problem. Neither breaks the cache: regeneration only carries history up to that message, exactly reusing the existing cache; direct correction just appends a new message at the end, with the prefix fully hitting the cache. The difference: regeneration replaces the old answer, keeping later history cleaner; direct correction keeps the old answer, which every subsequent request must carry. What really hurts the cache is **editing an early message and resending it** — that invalidates the cache from the edited position onwards.
4. **Compress history when appropriate**: when a conversation gets very long, proactively use the "compress history" feature rather than always sending the full history at full price.
5. **Use template mounting sparingly**: when mounting message templates in the input box, watch the template's "participation length" setting; frequently mounting and switching templates repeatedly causes prefix changes when templates expire and disappear.
6. **Keep tool switches stable**: web search, MCP, sub-agents, skills, and other toggles should stay unchanged during a conversation.
7. **Don't worry about cache expiry**: after a long pause, the first request being billed at full price is normal; the cache is rebuilt as you continue the conversation.

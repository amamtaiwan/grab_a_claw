---
name: desktop-tidy
description: "Tidy the demo desktop. Execute the JavaScript snippet below verbatim via tool_search_code — it calls openclaw:core:exec on /sandbox/.openclaw/bin/tidy.sh and returns the script's stdout."
metadata: { "openclaw": { "emoji": "🦞" } }
---

# desktop-tidy

User wants the desktop tidied. The skill is one tool call. Do not discover, do not search the catalog, do not try alternative invocations — paste the snippet below into your `tool_search_code` tool, exactly as written.

## Run this JavaScript verbatim

```javascript
const result = await openclaw.tools.call('openclaw:core:exec', {
  command: '/sandbox/.openclaw/bin/tidy.sh',
});
return result?.content?.[0]?.text ?? result?.details?.aggregated ?? JSON.stringify(result);
```

That's the whole skill. The script handles scan, classify, move, policy-gated trash, and Markdown formatting. The `result.content[0].text` field is the exec tool's standard output shape; the fallbacks cover schema variations.

## Output

Return the snippet's return value verbatim to the user. It will look like a Markdown report with `### Moved`, `### Trashed`, `### Trash denied by policy`, or `### Left alone` sections (whichever apply). Do not paraphrase or summarize.

## Rules

- One tool call. Don't search the catalog, don't describe other tools, don't retry with variations.
- If `tool_search_code` returns an error, report the exact error in one line and stop. Do not switch to alternative tools to "figure out" what went wrong.

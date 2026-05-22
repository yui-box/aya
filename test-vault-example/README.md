# Aya Vault — Index

This vault is Aya's brain — Andrea's personal AI assistant.

## Structure

```
vault/
├── _aya/              ← High-priority context (always injected)
│   ├── aya-persona.md     Personality instructions and behavior rules
│   ├── expertise.md       Andrea's areas of expertise
│   └── background.md      Professional history and personal context
│
├── daily/             ← Daily notes (tagged with #today, #pending)
├── projects/          ← Active client projects
├── personal/          ← Family, routine, reminders
├── knowledge/         ← Technical reference notes
└── inbox/             ← Pending email summaries
```

## Tag conventions

| Tag | Meaning |
|---|---|
| `#today` | Appears in today's briefing |
| `#pending` | Incomplete task, appears in briefing |
| `#inbox` | Email or message pending a reply |
| `#project` | Active project |
| `#knowledge` | Technical reference note |
| `#personal` | Personal or family information |
| `#family` | Kids' events and reminders |

## For Aya: how to read this vault

- The `_aya/` folder contains your definition and Andrea's context — read it first
- Notes with explicit dates (`YYYY-MM-DD`) are candidates for reminders
- Notes tagged `#pending` are active tasks that must appear in the briefing
- Notes tagged `#inbox` have emails waiting for a reply


## Testing Querys Discord
@Aya what do I have pending for today?
@Aya what do I know about RAG and what are its limitations?
@Aya when is Sofia's concert?
@Aya what are the technical risks of Client B?
@Aya which LLM model should I use for tasks that require privacy?
!briefing
!reminders
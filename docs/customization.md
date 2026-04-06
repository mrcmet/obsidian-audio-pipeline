# Customization Guide

There are three layers for customizing how notes are built, in order of effort.

---

## Layer 1: custom_prompt_instructions (easiest)

In `config.yaml`, under `note.custom_prompt_instructions`.
Plain English appended verbatim to the LLM's system prompt.

```yaml
note:
  custom_prompt_instructions: |
    Write the summary as bullet points, not prose.
    If a project name is mentioned, format it as a [[wikilink]] in the summary.
    Add an "Open Questions" section for anything unresolved.
    Format action item owners as [[First Last]] wikilinks when full names are given.
```

The LLM receives this after the base instructions and the tag list.
Changes here affect note *content* — what the AI extracts and how it phrases things.

---

## Layer 2: Custom Jinja2 template

Set `note.template_file` to a `.j2` file path to fully control markdown layout.
Copy the `DEFAULT_TEMPLATE` string from `note_writer.py` as your starting point.

### All available template variables

| Variable | Type | Description |
|---|---|---|
| `title` | str | LLM-generated title |
| `date` | str | YYYY-MM-DD |
| `time` | str | HH:MM |
| `datetime_human` | str | "Monday, April 05, 2026 at 2:30 PM" |
| `audio_filename` | str | Original audio file name |
| `duration` | str | "12m 34s" |
| `tags` | list[str] | Obsidian tags (no # prefix) |
| `attendees` | list[str] | Names mentioned |
| `summary` | str | Paragraph or bullets |
| `key_points` | list[str] | Main takeaways |
| `todos` | list[dict] | `{task, owner, due}` |
| `decisions` | list[str] | Concrete decisions |
| `follow_ups` | list[str] | Parking lot items |
| `custom_sections` | dict | `{section_name: content}` |
| `transcript` | str | Raw transcript text |
| `include_transcript` | bool | From config |
| `collapse_transcript` | bool | From config |

### Example: minimal template

```jinja
---
date: {{ date }}
tags: [{{ tags | join(', ') }}]
---

# {{ title }}

{{ summary }}

{% for todo in todos %}
- [ ] {{ todo.task }} ({{ todo.owner }})
{% endfor %}
```

### Jinja2 tips for Obsidian

```jinja
{# Wikilink from attendee list #}
{% for name in attendees %}[[{{ name }}]] {% endfor %}

{# Conditional section #}
{% if decisions %}
## Decisions
{% for d in decisions %}- {{ d }}
{% endfor %}
{% endif %}

{# Loop over custom sections the LLM generated #}
{% for name, content in custom_sections.items() %}
## {{ name }}
{{ content }}
{% endfor %}
```

---

## Layer 3: Modify llm.py directly

For structural changes — adding new extracted fields, changing the JSON schema,
or doing multi-pass prompting.

### Adding a new extracted field

1. Add it to the JSON schema description in `build_system_prompt()`:
   ```python
   "risks": ["list of risks or concerns raised"]
   ```

2. Add a safe default in `_parse_llm_response()`:
   ```python
   defaults["risks"] = []
   ```

3. Add it as a template variable in `note_writer.render_and_write()`:
   ```python
   "risks": note_data.get("risks", []),
   ```

4. Use `{{ risks }}` in your Jinja2 template.

### Adding a new LLM backend

Add a `_call_<backend>()` function following the same signature:
```python
def _call_mybackend(system_prompt: str, user_prompt: str, cfg: dict) -> str:
    # ... call your API ...
    return response_text
```

Then add it to the dispatch in `extract_note_data()`:
```python
elif backend == "mybackend":
    raw = _call_mybackend(system_prompt, user_prompt, llm_cfg)
```

---

## Vault Tag Scanning

Tags are loaded from your vault automatically at pipeline startup via `vault_tags.py`.

- Reads YAML frontmatter tags (`tags: [foo, bar]` or block list style)
- Reads inline `#hashtags` from note bodies
- Skips `.obsidian/` system folders
- Cached in-process — scans once per session
- Falls back to `note.fallback_tags` in config.yaml if vault is unreachable

To force a re-scan within a running session:
```python
from vault_tags import refresh_tags
tags = refresh_tags("~/Documents/Obsidian")
```

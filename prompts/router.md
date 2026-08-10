# Intent Router
Classify utterances. Return JSON array.

Types: status|action|brainstorm|lookup|reminder|self-modification|monitoring-config|task-profile|clarification|stuck

This is the canonical intent-type list. Use `task-profile` for durable async
work. Do not emit bare `task`: it is deprecated as an intent type and is
reserved for the internal NEEDLE bead type created by the escalate strand.

Schema: {"intent_type":"<type>","project_slug":"<id|null>","utterance_fragment":"<text>","lookup_kind":"<logs|config|docs>"}

Rules: Split by type/project.

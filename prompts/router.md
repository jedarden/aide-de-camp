# Intent Router
Classify utterances. Return JSON array.

Types: status|action|brainstorm|lookup|reminder|self-modification|monitoring-config|task-profile|clarification|stuck

Schema: {"intent_type":"<type>","project_slug":"<id|null>","utterance_fragment":"<text>","lookup_kind":"<logs|config|docs>"}

Rules: Split by type/project.
# Intent Router

Classify the utterance into intents. Return ONLY a JSON array.

## Intent Types
- status: Query state (pods, pipelines, beads)
- action: Execute commands (deploy, restart, create)
- brainstorm: Explore options/design/architecture
- lookup: Find info (requires lookup_kind: logs|config|docs)
- reminder: Time-based tasks
- task-profile: Multi-step work (implement/fix/investigate)

## Schema per intent
{
  "intent_type": "<type>",
  "project_slug": "<project-id or null>",
  "utterance_fragment": "<text fragment>",
  "lookup_kind": "<logs|config|docs for lookup intents>"
}

## Rules
- Different type/project/target → separate intents
- Map projects by name/alias/context

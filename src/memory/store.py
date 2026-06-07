"""
Memory store for ADC - simplified user memory extraction and persistence.

Extracts salient facts from conversation turns and persists them to disk.
Based on DUCK-E's memory module but simplified for ADC's context.
"""
import hashlib
import httpx
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from logging import Logger
from pathlib import Path
from typing import Optional


DEFAULT_MEMORY_DIR = "/home/coding/aide-de-camp/data/memory"
MAX_FACTS = 100


class FactCategory(str, Enum):
    """Categories for user memory facts."""
    PREFERENCE = "preference"    # User preferences (e.g., "prefers dark mode")
    PERSONAL = "personal"        # Personal details (e.g., "lives in Berlin")
    CORRECTION = "correction"    # User correcting previous behavior
    CONTEXT = "context"          # Other contextual information


@dataclass
class Fact:
    """A memory fact with metadata."""
    text: str
    category: FactCategory
    confidence: float
    created_at: str
    last_referenced: str

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "category": self.category.value,
            "confidence": self.confidence,
            "created_at": self.created_at,
            "last_referenced": self.last_referenced,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Fact":
        return cls(
            text=data["text"],
            category=FactCategory(data["category"]),
            confidence=data["confidence"],
            created_at=data["created_at"],
            last_referenced=data["last_referenced"],
        )


class MemoryStore:
    """
    Simple memory store for ADC voice mode.

    Extracts and persists user-specific facts from conversation turns.
    Fire-and-forget safe — all errors are suppressed to avoid disrupting sessions.
    """

    def __init__(
        self,
        session_id: str,
        memory_dir: str = DEFAULT_MEMORY_DIR,
        logger: Optional[Logger] = None,
    ):
        self.session_id = session_id
        self.memory_dir = Path(memory_dir)
        self.logger = logger or __import__("logging").getLogger(__name__)
        # Hash session_id to avoid path traversal issues
        self.user_hash = hashlib.sha256(session_id.encode()).hexdigest()[:16]
        self.file_path = self.memory_dir / f"session_{self.user_hash}.json"
        self._data: dict = {}
        self._facts: list[Fact] = []

    def load(self) -> None:
        """Load memory from disk. No-op if file doesn't exist."""
        try:
            if self.file_path.exists():
                with open(self.file_path, "r") as f:
                    self._data = json.load(f)
            else:
                self._data = {"facts": [], "session_id": self.session_id}
        except (json.JSONDecodeError, OSError) as e:
            self.logger.debug(f"Failed to load memory: {e}")
            self._data = {"facts": [], "session_id": self.session_id}

        # Load facts
        self._facts = []
        for f in self._data.get("facts", []):
            if isinstance(f, dict):
                self._facts.append(Fact.from_dict(f))

        self.logger.debug(f"Loaded {len(self._facts)} facts from memory")

    def save(self) -> None:
        """Persist memory to disk."""
        try:
            self.memory_dir.mkdir(parents=True, exist_ok=True)
            self._data["facts"] = [f.to_dict() for f in self._facts]
            self._data["updated_at"] = datetime.now(timezone.utc).isoformat()
            with open(self.file_path, "w") as f:
                json.dump(self._data, f, indent=2)
        except OSError as e:
            self.logger.warning(f"Failed to save memory: {e}")

    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison."""
        return " ".join(text.lower().split())

    def _is_duplicate(self, new_fact: str, category: FactCategory) -> bool:
        """Check if a fact already exists (exact or near-exact match)."""
        new_normalized = self._normalize_text(new_fact)
        for fact in self._facts:
            if fact.category == category:
                existing_normalized = self._normalize_text(fact.text)
                # Check for exact match or one containing the other
                if new_normalized == existing_normalized:
                    return True
                # Near-exact: one is a prefix of the other with significant overlap
                if len(new_normalized) > 20 and len(existing_normalized) > 20:
                    shorter, longer = sorted([new_normalized, existing_normalized], key=len)
                    if longer.startswith(shorter) or shorter in longer:
                        return True
        return False

    def add_fact(
        self,
        text: str,
        category: FactCategory = FactCategory.CONTEXT,
        confidence: float = 0.7,
    ) -> bool:
        """
        Add a fact about the user with deduplication.
        Returns True if fact was added, False if duplicate.
        """
        text = text.strip()
        if not text:
            return False

        # Deduplication: skip if exact or near-exact match exists
        if self._is_duplicate(text, category):
            return False

        # Trim oldest facts if at limit
        if len(self._facts) >= MAX_FACTS:
            self._facts.pop(0)

        now = datetime.now(timezone.utc).isoformat()
        fact = Fact(
            text=text,
            category=category,
            confidence=min(1.0, max(0.0, confidence)),
            created_at=now,
            last_referenced=now,
        )
        self._facts.append(fact)
        self.save()
        self.logger.info(f"Added fact: [{category.value}] {text[:50]}...")
        return True

    def get_facts(self) -> list[Fact]:
        """Return all facts, updating last_referenced timestamps."""
        now = datetime.now(timezone.utc).isoformat()
        for fact in self._facts:
            fact.last_referenced = now
        return self._facts.copy()

    def get_facts_by_topic(self, topic: str) -> list[str]:
        """Return facts relevant to topic using keyword matching."""
        topic_words = [w.lower() for w in topic.split() if len(w) > 3]
        if not topic_words:
            return []
        matched = []
        for fact in self._facts:
            fact_lower = fact.text.lower()
            if any(word in fact_lower for word in topic_words):
                matched.append(fact.text)
        return matched

    async def extract_and_save(
        self,
        user_text: str,
        assistant_text: str,
        api_key: str,
        model: str = "gpt-4o-mini",
    ) -> None:
        """
        Extract memorable facts from a conversation turn and save them.

        Uses a lightweight LLM call to identify user-specific facts worth
        persisting. Fire-and-forget safe — all errors are suppressed.

        Args:
            user_text: What the user said this turn
            assistant_text: What the assistant responded
            api_key: OpenAI API key for extraction
            model: Model to use for extraction (default: gpt-4o-mini)
        """
        if not user_text.strip():
            return

        prompt = (
            "Extract facts about the USER worth remembering for future conversations. "
            "Categorize each fact and assign a confidence score (0.0-1.0).\n\n"
            "Categories:\n"
            "- preference: User's likes, dislikes, choices (e.g., 'prefers dark mode')\n"
            "- personal: Personal details (e.g., 'lives in Berlin', 'works on Python projects')\n"
            "- correction: User correcting previous assistant behavior\n"
            "- context: Other contextual information (e.g., 'working on Kubernetes cluster')\n\n"
            "Confidence scoring:\n"
            "- 0.9-1.0: Explicitly stated preference or fact\n"
            "- 0.7-0.9: Reasonably inferred from conversation\n"
            "- 0.5-0.7: Possible but uncertain\n\n"
            "Return ONLY a valid JSON array of objects with 'text', 'category', and 'confidence'. "
            "Example: [{\"text\": \"User lives in Paris\", \"category\": \"personal\", \"confidence\": 0.9}]\n"
            "Return [] if nothing is worth saving."
        )
        turn = f"[User]: {user_text}\n[Assistant]: {assistant_text}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": prompt},
                            {"role": "user", "content": turn},
                        ],
                        "temperature": 0,
                        "max_tokens": 512,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

                content = data["choices"][0]["message"]["content"].strip()
                facts = json.loads(content)
                if isinstance(facts, list):
                    for fact in facts:
                        if isinstance(fact, dict) and "text" in fact:
                            text = fact["text"].strip()
                            if text:
                                try:
                                    category = FactCategory(fact.get("category", "context"))
                                except ValueError:
                                    category = FactCategory.CONTEXT
                                confidence = min(1.0, max(0.0, float(fact.get("confidence", 0.7))))
                                self.add_fact(text, category, confidence)
        except Exception as e:
            self.logger.debug(f"Memory extraction failed: {e}")
            # Never crash the session over memory extraction

    def get_memory_summary(self) -> str:
        """Generate a brief summary of stored facts for inclusion in system prompts."""
        if not self._facts:
            return ""

        # Group by category
        by_category: dict[FactCategory, list[str]] = {
            cat: [] for cat in FactCategory
        }
        for fact in self._facts:
            by_category[fact.category].append(fact.text)

        sections = []
        if by_category[FactCategory.PREFERENCE]:
            sections.append("Preferences:\n- " + "\n- ".join(by_category[FactCategory.PREFERENCE]))
        if by_category[FactCategory.PERSONAL]:
            sections.append("Personal:\n- " + "\n- ".join(by_category[FactCategory.PERSONAL]))
        if by_category[FactCategory.CONTEXT]:
            sections.append("Context:\n- " + "\n- ".join(by_category[FactCategory.CONTEXT]))
        if by_category[FactCategory.CORRECTION]:
            sections.append("Corrections:\n- " + "\n- ".join(by_category[FactCategory.CORRECTION]))

        return "\n\n".join(sections)

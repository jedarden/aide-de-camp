"""
Memory extraction handler for voice session turns.

Integrates with VoiceSession's on_turn_done callback to extract and persist
salient user facts from each conversation turn.
"""
import os
from logging import getLogger

from .store import MemoryStore


logger = getLogger(__name__)


class MemoryExtractionHandler:
    """
    Handles memory extraction for voice sessions.

    Extracts and persists salient user facts from each conversation turn,
    enabling the voice mode to build persistent context across sessions.
    """

    def __init__(self, session_id: str, api_key: str | None = None):
        """
        Initialize the memory extraction handler.

        Args:
            session_id: Unique session identifier
            api_key: OpenAI API key (falls back to environment if not provided)
        """
        self.session_id = session_id
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")

        if not self.api_key:
            logger.warning("No OpenAI API key provided - memory extraction disabled")

        # Initialize memory store
        self.memory_store = MemoryStore(session_id=session_id, logger=logger)
        self.memory_store.load()

    async def on_turn_done(self, user_text: str, assistant_text: str) -> None:
        """
        Callback handler for conversation turn completion.

        Extracts salient facts from the conversation turn and persists them.

        Args:
            user_text: What the user said this turn
            assistant_text: What the assistant responded
        """
        if not self.api_key:
            return

        if not user_text.strip():
            return

        try:
            await self.memory_store.extract_and_save(
                user_text=user_text,
                assistant_text=assistant_text,
                api_key=self.api_key,
            )
            logger.debug(f"Memory extraction completed for session {self.session_id}")
        except Exception as e:
            # Never crash the session over memory extraction
            logger.warning(f"Memory extraction failed: {e}")

    def get_memory_summary(self) -> str:
        """
        Get a summary of stored facts for system prompt injection.

        Returns a formatted string of categorized facts for inclusion
        in voice system prompts to maintain context across turns.
        """
        return self.memory_store.get_memory_summary()

    def get_facts_by_topic(self, topic: str) -> list[str]:
        """
        Get facts relevant to a specific topic.

        Args:
            topic: Topic to search for

        Returns:
            List of fact texts relevant to the topic
        """
        return self.memory_store.get_facts_by_topic(topic)


def create_memory_handler(session_id: str, api_key: str | None = None) -> MemoryExtractionHandler | None:
    """
    Factory function to create a memory extraction handler.

    Returns None if API key is not available, allowing graceful degradation.

    Args:
        session_id: Unique session identifier
        api_key: OpenAI API key (optional)

    Returns:
        MemoryExtractionHandler instance or None
    """
    api_key = api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    return MemoryExtractionHandler(session_id=session_id, api_key=api_key)

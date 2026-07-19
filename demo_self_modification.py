#!/usr/bin/env python3
"""
Demonstration of end-to-end self-modification cycle.

This script demonstrates:
1. User instruction → diff generation
2. Diff surfaced for approval
3. User approval → change applied
4. Hot-reload takes effect (no redeploy needed)
"""

import asyncio
from src.agents.self_modification import get_self_modification_agent, ArtifactDiff
from src.components.hot_reload import get_reload_manager
from src.components.library import get_library
from src.feedback.processor import get_feedback_processor, FeedbackRequest, FeedbackType


def print_section(title: str):
    """Print a section header."""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_diff(diff: ArtifactDiff):
    """Print a diff in a readable format."""
    print(f"\n📝 Artifact: {diff.artifact_name} ({diff.artifact_type.value})")
    print(f"📊 Confidence: {diff.confidence:.0%}")
    print(f"📄 Summary: {diff.change_summary}")
    print("\n--- BEFORE ---")
    print(diff.before[:200] + "..." if len(diff.before) > 200 else diff.before)
    print("\n--- AFTER (first 300 chars) ---")
    print(diff.after[:300] + "..." if len(diff.after) > 300 else diff.after)


async def demo_self_modification_cycle():
    """Demonstrate the complete self-modification cycle."""

    print_section("PHASE 2: Self-Improvement Loop Demo")

    # Initialize components
    print("\n🔧 Initializing components...")
    agent = get_self_modification_agent()
    reload_mgr = get_reload_manager()
    library = get_library()
    feedback_processor = get_feedback_processor()

    print(f"✓ Self-modification agent ready")
    print(f"✓ Hot-reload manager monitoring {len(reload_mgr.list_artifacts())} artifacts")
    print(f"✓ Component library ready")
    print(f"✓ Feedback processor ready")

    # Step 1: User instruction
    print_section("Step 1: User Instruction")
    instruction = "Always include pod restart count in status results"
    print(f"\n👤 User says: \"{instruction}\"")

    # Step 2: Generate diff
    print_section("Step 2: Generating Diff")
    diff = await agent.process_instruction(instruction)
    print_diff(diff)

    # Step 3: Surface for approval
    print_section("Step 3: Approval Request")
    print(f"\n📋 Approval required for this change")
    print(f"   Type 'approve' to apply, 'reject' to discard")

    # Simulate approval (auto-approve for demo)
    user_decision = "approve"
    print(f"\n👤 User: {user_decision}")

    if user_decision == "approve":
        # Step 4: Apply change
        print_section("Step 4: Applying Change")
        success = agent.apply_diff(diff)

        if success:
            print(f"\n✅ Change applied successfully!")
            print(f"   Artifact '{diff.artifact_name}' has been updated")
            print(f"   Hot-reload: Change will take effect on next invocation")

            # Verify the change
            print_section("Step 5: Verification")
            current_content = reload_mgr.get_prompt(diff.artifact_name)
            if "restart count" in current_content.lower():
                print(f"\n✅ Verified: New content includes 'restart count'")
                print(f"\n📄 Updated content (excerpt):")
                # Find and show the relevant lines
                for line in current_content.split('\n'):
                    if 'restart' in line.lower():
                        print(f"   {line}")
            else:
                print(f"\n⚠️  Warning: Expected content not found")

        else:
            print(f"\n❌ Failed to apply change")
    else:
        print(f"\n🚫 Change rejected by user")
        agent.reject_diff(diff)

    # Component iteration demo
    print_section("Bonus: Component Iteration")

    # Check if we have any components
    components = library.list_components(limit=5)
    if components:
        comp = components[0]
        print(f"\n📦 Found component: {comp.name} (v{comp.version})")

        # Simulate feedback
        feedback = "Add a status indicator to show health"
        print(f"👤 User feedback: \"{feedback}\"")

        # Process component feedback
        from src.feedback.processor import FeedbackRequest as FReq
        result = await feedback_processor.process_feedback(
            FReq(
                feedback=feedback,
                feedback_type=FeedbackType.COMPONENT_ITERATION,
                context={"component_id": comp.id},
                session_id="demo-session",
                require_approval=False
            )
        )
        print(f"\n✅ {result.message}")
    else:
        print(f"\n📦 No components found. Component library is empty.")

    # Summary
    print_section("Demo Complete")
    print("""
The self-modification cycle is complete:

1. ✅ User instruction received
2. ✅ Diff generated and surfaced
3. ✅ User approved the change
4. ✅ Change applied to artifact
5. ✅ Hot-reload ensures change takes effect without redeploy

Key capabilities demonstrated:
- Self-modification agent reads/writes artifacts
- Hot-reload manager tracks artifact changes
- Approval workflow for safety
- Component iteration support
- End-to-end feedback processing
""")


if __name__ == "__main__":
    asyncio.run(demo_self_modification_cycle())

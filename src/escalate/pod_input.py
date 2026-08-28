"""
Pod name input collection and validation module.

Handles interactive user input for pod selection, validation against
available pod lists, and storage of the selected pod name for
deletion operations.
"""

import sys
import threading
from typing import Dict, List, Optional, Tuple


class PodInputCollector:
    """
    Collects and validates pod names from user input.

    Provides interactive prompts for pod selection, validates against
    available pod lists, and stores the selected pod name for use in
    deletion operations.
    """

    def __init__(self):
        """Initialize the pod input collector."""
        self._selected_pod: Optional[str] = None
        self._available_pods: List[Dict] = []
        self._state_lock = threading.RLock()

    def set_available_pods(self, pods: List[Dict]) -> None:
        """
        Set the list of available pods for validation.

        Args:
            pods: List of pod dictionaries containing pod information.
                   Each pod should have at least a 'name' field.
        """
        with self._state_lock:
            self._available_pods = list(pods)

    def get_available_pod_names(self) -> List[str]:
        """
        Get list of available pod names.

        Returns:
            List of pod names available for selection.
        """
        with self._state_lock:
            pods = list(self._available_pods)
        return [pod.get("name", "") for pod in pods if pod.get("name")]

    def validate_pod_name(self, pod_name: str) -> Tuple[bool, Optional[str]]:
        """
        Validate that a pod name exists in the available list.

        Args:
            pod_name: The pod name to validate.

        Returns:
            Tuple of (is_valid, error_message). If valid, error_message is None.
        """
        available_names = self.get_available_pod_names()

        if not pod_name.strip():
            return False, "Pod name cannot be empty."

        if pod_name not in available_names:
            return False, f"Pod '{pod_name}' not found in available pods."

        return True, None

    def collect_pod_name(self, prompt_message: Optional[str] = None) -> Optional[str]:
        """
        Collect pod name from user via interactive prompt.

        Displays a prompt asking the user to enter a pod name, validates
        the input against the available list, and prompts again if invalid.

        Args:
            prompt_message: Optional custom prompt message. If not provided,
                           uses a default prompt that references the pod list.

        Returns:
            The validated pod name, or None if the user cancels/enters empty.
        """
        with self._state_lock:
            has_available_pods = bool(self._available_pods)
        if not has_available_pods:
            print("❌ No pods available for selection.", file=sys.stderr)
            print("   Please ensure pods are listed before attempting selection.", file=sys.stderr)
            return None

        # Use default prompt if none provided
        if prompt_message is None:
            prompt_message = self._build_default_prompt()

        # Collect and validate input
        while True:
            try:
                print("\n" + prompt_message)
                print("(Enter 'cancel' to exit)\n")

                user_input = input("Pod name: ").strip()

                # Check for cancellation
                if not user_input or user_input.lower() == 'cancel':
                    print("\n⏹️  Pod selection cancelled.")
                    return None

                # Validate the pod name
                is_valid, error_msg = self.validate_pod_name(user_input)

                if is_valid:
                    with self._state_lock:
                        self._selected_pod = user_input
                    print(f"\n✓ Selected pod: {user_input}")
                    return user_input
                else:
                    print(f"\n❌ Invalid selection: {error_msg}")
                    print("   Please enter a pod name from the list above.\n")

            except (EOFError, KeyboardInterrupt):
                print("\n\n⏹️  Pod selection cancelled.")
                return None
            except Exception as e:
                print(f"\n❌ Error reading input: {e}", file=sys.stderr)
                return None

    def _build_default_prompt(self) -> str:
        """
        Build the default prompt message referencing available pods.

        Returns:
            A formatted prompt message showing the available pods.
        """
        lines = [
            "─── ─── ─── ─── ─── ─── ─── ─── ─── ─── ─── ───",
            "🎯 Pod Selection",
            "",
            "Available Pods:",
            "",
        ]

        # Group pods by namespace if available
        pods_by_namespace: Dict[str, List[Dict]] = {}

        with self._state_lock:
            pods = list(self._available_pods)
        for pod in pods:
            namespace = pod.get("namespace", "default")
            if namespace not in pods_by_namespace:
                pods_by_namespace[namespace] = []
            pods_by_namespace[namespace].append(pod)

        # Display pods grouped by namespace
        for namespace, pods in sorted(pods_by_namespace.items()):
            lines.append(f"  Namespace: {namespace}")
            for pod in pods:
                pod_name = pod.get("name", "unknown")
                status = pod.get("status", "Unknown")
                ready = pod.get("ready", "N/A")
                age = pod.get("age", "N/A")

                lines.append(f"    • {pod_name}")
                lines.append(f"      Status: {status} | Ready: {ready} | Age: {age}")
            lines.append("")

        lines.extend([
            "Which pod would you like to delete?",
            "Please enter the exact pod name from the list above.",
        ])

        return "\n".join(lines)

    def confirm_pod_deletion(self, pod_name: str) -> bool:
        """
        Request explicit user confirmation for pod deletion.

        Displays a warning message and prompts the user with "Delete <pod>? (y/n)".
        Only returns True if the user explicitly confirms with 'y' or 'yes'.

        Args:
            pod_name: The pod name to confirm deletion for.

        Returns:
            True if user confirms deletion (y/yes), False otherwise.
            Returns False on 'n/no', EOFError, KeyboardInterrupt, or any exception.

        Behavior:
            - Shows clear warning about deletion being irreversible
            - Explains automatic recreation for managed pods
            - Loops until valid input (y/n) or cancellation
            - Handles keyboard interrupts gracefully
        """
        print(f"\n⚠️  Confirm Deletion")
        print(f"=" * 50)
        print(f"You are about to delete pod: {pod_name}")
        print(f"\nThis action cannot be undone.")
        print(f"If the pod is managed by a Deployment or ReplicaSet,")
        print(f"it will be automatically recreated after deletion.")

        while True:
            try:
                response = input(f"\nDelete '{pod_name}'? (y/n): ").strip().lower()

                if response in ('y', 'yes'):
                    print(f"\n✅ Confirmed deletion of pod: {pod_name}")
                    return True
                elif response in ('n', 'no'):
                    print(f"\n❌ Deletion cancelled for pod: {pod_name}")
                    return False
                else:
                    print(f"\n⚠️  Please enter 'y' or 'n'.")

            except (EOFError, KeyboardInterrupt):
                print(f"\n\n⏹️  Deletion cancelled for pod: {pod_name}")
                return False
            except Exception as e:
                print(f"\n❌ Error reading input: {e}", file=sys.stderr)
                return False

    def collect_and_confirm_pod_name(
        self,
        prompt_message: Optional[str] = None,
    ) -> Optional[str]:
        """
        Collect pod name from user and request explicit deletion confirmation.

        This is the complete flow: list pods, get selection, validate, and
        confirm deletion before proceeding. This method implements the full
        acceptance criteria for pod deletion confirmation.

        Acceptance Criteria:
            1. User is presented with the pod list and asked to specify ✅
            2. User provides a specific pod name ✅
            3. Pod name is validated against the available pods list ✅
            4. Target pod is confirmed with explicit user confirmation ✅

        Args:
            prompt_message: Optional custom prompt message. If not provided,
                          uses a default prompt that references the pod list.

        Returns:
            The validated and confirmed pod name, or None if user cancels
            at any point (selection or confirmation). Returns None if:
            - No pods available for selection
            - User enters 'cancel' or empty input during selection
            - User rejects confirmation (n/no)
            - User cancels via EOFError or KeyboardInterrupt
            - Any exception occurs during input

        Behavior:
            - Step 1: Calls collect_pod_name() to display list and get selection
            - Step 2: Calls confirm_pod_deletion() for explicit confirmation
            - Step 3: Returns pod name if both steps succeed, None otherwise
            - Clears _selected_pod if confirmation is rejected

        Example:
            >>> collector.set_available_pods(pods_list)
            >>> confirmed_pod = collector.collect_and_confirm_pod_name()
            >>> if confirmed_pod:
            >>>     # Proceed with deletion
            >>> else:
            >>>     # User cancelled
        """
        # Step 1: Collect and validate pod name
        selected_pod = self.collect_pod_name(prompt_message)

        # Step 2: Request explicit confirmation
        if selected_pod:
            if self.confirm_pod_deletion(selected_pod):
                return selected_pod
            else:
                # User cancelled confirmation
                with self._state_lock:
                    self._selected_pod = None
                return None

        return None

    def get_selected_pod(self) -> Optional[str]:
        """
        Get the currently selected pod name.

        Returns:
            The selected pod name, or None if no pod has been selected.
        """
        with self._state_lock:
            return self._selected_pod

    def reset(self) -> None:
        """Reset the collector state (clear selected pod and available list)."""
        with self._state_lock:
            # Publish a fresh empty collector generation in one transition.
            self._selected_pod = None
            self._available_pods = []


# Global collector instance
_collector: Optional[PodInputCollector] = None


def get_pod_input_collector() -> PodInputCollector:
    """Get or create the global pod input collector instance."""
    global _collector
    if _collector is None:
        _collector = PodInputCollector()
    return _collector


def collect_pod_name_interactive(
    available_pods: List[Dict],
    prompt_message: Optional[str] = None,
) -> Optional[str]:
    """
    Convenience function to collect pod name from user.

    Creates a collector, sets available pods, and collects user input.

    Args:
        available_pods: List of available pod dictionaries.
        prompt_message: Optional custom prompt message.

    Returns:
        The validated pod name, or None if cancelled.
    """
    collector = get_pod_input_collector()
    collector.set_available_pods(available_pods)
    return collector.collect_pod_name(prompt_message)


def collect_and_confirm_pod_interactive(
    available_pods: List[Dict],
    prompt_message: Optional[str] = None,
) -> Optional[str]:
    """
    Convenience function to collect pod name and confirm deletion.

    Creates a collector, sets available pods, collects input, and confirms
    deletion before proceeding.

    Args:
        available_pods: List of available pod dictionaries.
        prompt_message: Optional custom prompt message.

    Returns:
        The validated and confirmed pod name, or None if cancelled at any point.
    """
    collector = get_pod_input_collector()
    collector.set_available_pods(available_pods)
    return collector.collect_and_confirm_pod_name(prompt_message)


if __name__ == "__main__":
    # Demo with sample pods from the previous task
    sample_pods = [
        {
            "name": "pbx-web-5ff68464d-mkn8n",
            "namespace": "default",
            "status": "Running",
            "ready": "2/2",
            "age": "8d",
        },
        {
            "name": "pbx-rebuild-relay-588d79c5b9-vmmlz",
            "namespace": "default",
            "status": "Running",
            "ready": "1/1",
            "age": "22d",
        },
        {
            "name": "lab-rebuild-relay-79957dbd4-xsqhl",
            "namespace": "default",
            "status": "Running",
            "ready": "1/1",
            "age": "9d",
        },
        {
            "name": "whisper-stt-847fd8d7b9-v2rs5",
            "namespace": "default",
            "status": "Running",
            "ready": "1/1",
            "age": "24d",
        },
        {
            "name": "whisper-openai-68966786fb-jsb5d",
            "namespace": "default",
            "status": "Running",
            "ready": "1/1",
            "age": "53d",
        },
    ]

    print("🧪 Pod Input Collector Demo")
    print("=" * 50)
    print("\nThis demo shows the complete pod selection and confirmation flow.")

    # Use the new collect_and_confirm_pod_interactive function
    selected = collect_and_confirm_pod_interactive(sample_pods)

    if selected:
        print(f"\n✅ Successfully selected and confirmed pod: {selected}")
        print(f"   Ready for deletion processing.")
        print(f"\nNext steps:")
        print(f"   1. Check pod ownership (Deployment/ReplicaSet)")
        print(f"   2. Execute kubectl delete pod")
        print(f"   3. Handle recreation warning if managed")
    else:
        print("\n⏹️  Pod selection or confirmation cancelled.")
        print(f"   No pod will be deleted.")

    sys.exit(0 if selected else 1)

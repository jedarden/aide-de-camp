#!/usr/bin/env python3
"""
Resolve, or honestly retire, underspecified beads that starve the ready frontier.

An open, dependency-free bead that is unactionable as written — "kubectl delete
pod" with no pod name or namespace (aidedeca-a1ba8617 sat that way for two
weeks) — is exactly what pluck reports as frontier-invisible, and until now
only a human could decide its fate. This script gives that decision a
deterministic first pass. For every open bead with no declared dependencies
whose text carries an awaiting-user-input marker it attempts to resolve the
missing parameter from live evidence, in order:

  1. the bead's own notes thread  (a later note naming the resource)
  2. read-only kubectl through the credential-free per-cluster proxies
     (`kubectl --server=http://traefik-<cluster>:8001 get pods -A -o json`,
     filtered by the bead's stated context — namespaces and distinctive tokens
     the bead itself names)
  3. the workspace's git log      (recent commits for any file the bead names)

and then acts on the candidate count:

  exactly one candidate  -> append the resolved specifics to the bead's notes.
                            `bead update` cannot rewrite a title or description,
                            so the note is the delivery vehicle; the bead stays
                            open and becomes genuinely claimable
  zero, or several       -> `bead update <id> --status deferred` with a note
                            opening "underspecified: N candidates, needs
                            disambiguation", so the bead leaves the frontier
                            honestly instead of starving it

A bead whose text does not state a machine-parseable request is left alone
(recorded as no-request-shape): deferring a request this tool could not even
parse would hide it from the humans who have to disambiguate it.

Safety rules enforced here:

  - The only cluster command ever issued is
    `kubectl --server=<proxy> get pods -A -o json`. The verb in the bead's text
    is parsed, never executed — any cluster mutation stays out of scope and
    with declarative-config (commit + ArgoCD sync).
  - Bead text is data, never a command line: nothing from a bead is passed to a
    shell; live pods are matched against extracted tokens, and only pod names
    from the live API end up in a note.
  - manual_blocked beads and beads carrying the "human" label are untouched — a
    person set those aside. Beads with an assignee are untouched too.
  - `bead update --notes` REPLACES the notes field, so an append here is a
    read-modify-write guarded by --if-revision; a concurrent writer can never
    be clobbered, and a lost race is reported, not retried.
  - Only two mutations are ever issued: a notes append on an open bead, and the
    open -> deferred transition. Nothing is closed, reopened, or deleted.

Run standalone, or from scripts/bead-healthcheck.sh (Step 3b, after the
checkpoint flush and before the frontier classification, so the same run's
verdict reflects any deferral) so an underspecified bead is resolved within one
timer period. With no qualifying bead present it does nothing beyond one
read-only bead list — the healthcheck fires every 15 minutes and must stay
cheap on a quiet workspace.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# A bead qualifies when its notes (or, failing that, its description —
# NEEDLE-authored beads carry the phrasing in the body before any note exists)
# carries one of these markers. Each hit is only the *first* gate: a bead is
# acted on only if a concrete request is also parsed out of its text.
AWAITING_INPUT_MARKERS = (
    "awaiting user input",
    "awaiting user specification",
    "awaiting-user-input",
    "needs user input",
    "requires clarification from the user",
    "requires user clarification",
    "requires user input",
    "ask the user to specify",
    "user must specify",
    "did not specify",
    "needs disambiguation",
    "blocked pending user",
    "human input required",
    "needs your input",
)

# Present in a bead's notes once this script has acted on it. The deferral
# note below opens with DEFERRED_MARKER too, so both outcomes are idempotent.
ENRICHMENT_MARKER = "Underspecified bead enrichment (automated):"
DEFERRED_MARKER = "underspecified:"

DEFER_NOTE_FORMAT = "underspecified: {count} candidates, needs disambiguation"
MAX_CANDIDATE_LINES = 10

# The credential-free read-only endpoints from the environment's CLAUDE.md.
# iad-kalshi has no Traefik; the Tailscale operator exposes its proxy Service
# directly. Override with ADC_KUBECTL_PROXIES (a JSON object) when the fleet
# changes — the script never hard-fails on a cluster that does not answer.
KUBECTL_PROXIES = {
    "ardenone-cluster": "http://traefik-ardenone-cluster:8001",
    "ardenone-manager": "http://traefik-ardenone-manager:8001",
    "rs-manager": "http://traefik-rs-manager:8001",
    "iad-ci": "http://traefik-iad-ci:8001",
    "iad-options": "http://traefik-iad-options:8001",
    "ord-devimprint": "http://traefik-ord-devimprint:8001",
    "apexalgo-iad": "http://traefik-apexalgo-iad:8001",
    "iad-kalshi": "http://kubectl-proxy-iad-kalshi:8001",
}

# kubectl verbs this tool can recognise in bead text. Recognition is not
# execution: the verb is recorded in the note and never run.
KUBECTL_VERBS = {
    "apply", "create", "delete", "edit", "get", "describe", "explain",
    "logs", "scale", "patch", "annotate", "label", "rollout", "drain",
    "cordon", "uncordon", "taint", "top", "expose", "run", "set", "wait",
}

# A bead often mentions kubectl more than once ("list the pods … then delete
# the pod"). The parameter that is missing — and that the bead is blocked on —
# is the one on the mutation, so mutating invocations outrank read-only ones
# when picking which request to resolve.
MUTATING_KUBECTL_VERBS = {
    "apply", "create", "delete", "edit", "scale", "patch", "annotate",
    "label", "rollout", "drain", "cordon", "uncordon", "taint", "set",
}

# Flags that take a value, so the tokenizer does not mistake the value for a
# positional resource name.
VALUE_FLAGS = {
    "-n", "--namespace", "-o", "--output", "--context", "--cluster",
    "--user", "--server", "--kubeconfig", "-l", "--selector",
    "--field-selector", "--container", "-c", "--revision", "--to",
}

# Resource kinds whose live instances this tool can enumerate. Only pods are
# enumerated (`get pods -A`); any other kind is deferred with an explanatory
# line rather than resolved against the wrong resource set.
ENUMERABLE_KINDS = {"pod", "pods", "po"}
KIND_ALIASES = {
    "pod": "pod", "pods": "pod", "po": "pod",
    "deployment": "deployment", "deployments": "deployment", "deploy": "deployment",
    "service": "service", "services": "service", "svc": "service",
    "statefulset": "statefulset", "sts": "statefulset",
    "daemonset": "daemonset", "ds": "daemonset",
    "job": "job", "jobs": "job", "cronjob": "cronjob",
}

# Words that appear in nearly every operational bead and must never count as
# evidence that a pod is "the one the bead meant".
TOKEN_STOPWORDS = set(
    """
    kubectl delete pods pod namespace namespaces cluster clusters deployment
    service services manifest manifests declarative argocd gitops user users
    please specify specifying specified name names named target targets
    ambiguous ambiguity disambiguation clarification clarify confirmation
    confirm must should shall will the and for with from that this those these
    have has had been being were was are you your yours their they them its
    into onto over under after before during between against without within
    which what when where who whom whose why how then than thus also only just
    even still once twice some many much more most less least very quite
    none nothing everything anything someone anyone everyone no yes not nor
    cannot cant dont doesnt didnt isnt arent wasnt werent wont wouldnt
    before after above below first second third last next previous following
    step steps task tasks bead beads issue issues note notes description
    success criteria implementation important critical required requires
    require needed need example examples current currently existing exists
    available unavailable command commands output result results execute
    executing execution running runs ran state status live local remote
    human agent worker workers policy policies rule rules allowed forbidden
    retry attempt attempts candidate candidates resolved resolution
    kubernetes kube pod-name podname resource resources instance instances
    """.split()
)

TOKEN_RE = re.compile(r"[a-z][a-z0-9][a-z0-9-]{2,}")
PATHLIKE_RE = re.compile(
    r"\b([\w.-]+(?:/[\w.-]+)+\.(?:py|sh|md|toml|ya?ml|json|html|js|ts|go|c|h))\b"
)

# A target token that is visibly a placeholder rather than a real name:
# <pod_name>, {pod}, $POD_NAME, POD_NAME, <namespace>, "unspecified", ...
PLACEHOLDER_RE = re.compile(r"^(<.*>|\{.*\}|\$.*|[A-Z][A-Z0-9_]{2,})$")
UNSPECIFIED_WORDS = {"unspecified", "unnamed", "unknown", "placeholder", "todo", "tbd"}

GIT_LOG_PATHS = 3
GIT_LOG_COUNT = 3

# bead list silently caps output at its --limit (default 100); fetch the whole
# open set, or a qualifying bead sitting past the cap starves on — invisible to
# this tool exactly as it was to pluck. (Same constant, same reason, as
# enrich_starvation_alerts.py and unblock_credential_gated_beads.py.)
BEAD_LIST_LIMIT = 999999


# ---------------------------------------------------------------------------
# bead list plumbing (mirrors scripts/enrich_starvation_alerts.py)
# ---------------------------------------------------------------------------


def resolve_bead_bin(explicit: Optional[str] = None) -> str:
    """Locate the bead CLI.

    The systemd user manager runs the healthcheck with a minimal PATH that
    misses ~/.local/bin and ~/.cargo/bin, where this box's bead wrapper and
    binaries live. Mirrors resolve_bead_bin() in enrich_starvation_alerts.py.
    """
    if explicit:
        return explicit
    found = shutil.which("bead")
    if found:
        return found
    for candidate in (
        Path.home() / ".local" / "bin" / "bead",
        Path.home() / ".cargo" / "bin" / "bead",
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return "bead"  # let subprocess surface the familiar not-found error


def normalize_bead_stream(stdout: str) -> List[Dict[str, Any]]:
    """Flatten `bead list --json` output into a list of bead objects.

    The CLI emits compact JSONL, prints a bare "[]" for an empty result, and
    has been seen emitting nested arrays; slurp-and-flatten normalizes every
    shape. Progress lines that are not JSON are skipped rather than fatal.
    """
    if not stdout.strip():
        return []
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        parsed = []
        for line in stdout.splitlines():
            if not line.strip():
                continue
            try:
                parsed.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # progress chatter, not a bead
    if isinstance(parsed, dict):
        parsed = [parsed]
    flat: List[Dict[str, Any]] = []
    for item in parsed:
        if isinstance(item, list):
            flat.extend(i for i in item if isinstance(i, dict))
        elif isinstance(item, dict):
            flat.append(item)
    return flat


def run_bead_list(
    args: List[str], bead_bin: str, workspace: Path, timeout: int = 60
) -> List[Dict[str, Any]]:
    result = subprocess.run(
        [bead_bin, "list", *args, "--json", "--limit", str(BEAD_LIST_LIMIT)],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(workspace),
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"bead list {' '.join(args)} failed (rc={result.returncode}): "
            f"{result.stderr.strip()[:300]}"
        )
    return normalize_bead_stream(result.stdout)


# ---------------------------------------------------------------------------
# discovery
# ---------------------------------------------------------------------------


def bead_text(bead: Dict[str, Any]) -> str:
    """The bead's free text: notes thread plus description."""
    return "\n".join(
        part for part in (bead.get("notes") or "", bead.get("description") or "") if part
    )


def carries_awaiting_input_marker(bead: Dict[str, Any]) -> bool:
    text = bead_text(bead).lower()
    return any(marker in text for marker in AWAITING_INPUT_MARKERS)


def has_no_declared_deps(bead: Dict[str, Any]) -> bool:
    """No declared dependencies at all — the frontier-invisible shape.

    Deliberately stricter than "no unclosed blockers": a bead whose blockers
    are all closed is already claimable and needs no enrichment.
    """
    return not (bead.get("dependencies") or [])


def already_processed(bead: Dict[str, Any]) -> bool:
    notes = bead.get("notes") or ""
    return ENRICHMENT_MARKER in notes or notes.startswith(DEFERRED_MARKER)


def is_off_limits(bead: Dict[str, Any]) -> bool:
    """A human or a live claim owns this bead; automation must not touch it."""
    if bead.get("manual_blocked") or "human" in (bead.get("labels") or []):
        return True
    return bead.get("assignee") is not None


def find_underspecified_beads(
    beads: List[Dict[str, Any]], statuses: Tuple[str, ...] = ("open",)
) -> List[Dict[str, Any]]:
    """Open, dependency-free beads awaiting user input that no one has resolved."""
    found = []
    for bead in beads:
        status = bead.get("status") or bead.get("effective_status")
        if status in statuses and has_no_declared_deps(bead) and not is_off_limits(bead):
            if not already_processed(bead) and carries_awaiting_input_marker(bead):
                found.append(bead)
    return found


# ---------------------------------------------------------------------------
# request parsing
# ---------------------------------------------------------------------------


class Request:
    """A kubectl-shaped request parsed out of a bead's text."""

    def __init__(
        self,
        verb: str,
        kind: Optional[str],
        name: Optional[str],
        named_namespaces: List[str],
        raw: str,
    ) -> None:
        self.verb = verb
        self.kind = kind
        self.name = name
        self.named_namespaces = named_namespaces
        self.raw = raw.strip()

    @property
    def underspecified(self) -> bool:
        """True when the target resource is not pinned down by name."""
        return self.name is None

    def describe(self) -> str:
        target = self.name or "<no resource name given>"
        kind = self.kind or "<no resource kind given>"
        scope = f" in namespace {self.named_namespaces[0]}" if self.named_namespaces else ""
        return f"kubectl {self.verb} {kind} {target}{scope}"


def _is_placeholder(token: str) -> bool:
    if PLACEHOLDER_RE.match(token):
        return True
    return token.lower().strip("<>{}$") in UNSPECIFIED_WORDS


def _split_command_line(line: str) -> Tuple[List[str], List[str]]:
    """Split a kubectl invocation into (positionals, namespaces).

    Flags are consumed with their values so a namespace value is never read as
    a resource name, and namespace placeholders are dropped — a literal
    `<namespace>` says the namespace is missing, not that it is called
    "namespace".

    The first placeholder also ends the positional list: whatever follows it in
    the source line is the sentence around the command ("…`kubectl delete pod
    <pod_name>` once the target is confirmed"), and prose must never be read as
    a resource name. Flag/value pairs after the placeholder are still parsed,
    because `-n <namespace>` routinely trails it.
    """
    positionals: List[str] = []
    namespaces: List[str] = []
    past_placeholder = False
    tokens = line.split()
    index = 0
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if token.startswith("-"):
            if "=" in token:
                flag, _, value = token.partition("=")
                if flag in ("-n", "--namespace") and not _is_placeholder(value):
                    namespaces.append(value)
            elif token in VALUE_FLAGS and index < len(tokens):
                value = tokens[index]
                index += 1
                if token in ("-n", "--namespace") and not _is_placeholder(value):
                    namespaces.append(value)
            continue
        if _is_placeholder(token):
            past_placeholder = True
            continue
        if not past_placeholder:
            positionals.append(token)
    return positionals, namespaces


# A fenced or quoted invocation first — ```kubectl …```, `kubectl …`, "kubectl …"
# — because its end is unambiguous; the bare end-of-line form is only the
# fallback. Without the fence-first pass, prose after a command would be read
# as part of it.
KUBECTL_FENCED_RE = re.compile(r"[`\"']+(kubectl\b[^`\"']*[`\"']+)", re.IGNORECASE)
KUBECTL_LINE_RE = re.compile(r"kubectl\s+(.+)", re.IGNORECASE)


def _kubectl_invocations(text: str) -> List[str]:
    """Candidate command strings, most reliably delimited first."""
    found = [match.group(1) for match in KUBECTL_FENCED_RE.finditer(text)]
    if found:
        return found
    return [match.group(1) for match in KUBECTL_LINE_RE.finditer(text)]


def _parse_one_invocation(invocation: str) -> Optional[Request]:
    positionals, namespaces = _split_command_line(invocation)
    # The fenced form captures the leading "kubectl" itself; the bare
    # line form does not. Normalize before reading the verb.
    if positionals and positionals[0].lower() == "kubectl":
        positionals = positionals[1:]
    if not positionals:
        return None
    verb = positionals[0].lower()
    if verb not in KUBECTL_VERBS:
        return None

    kind = None
    name = None
    rest = positionals[1:]
    # A "kubectl rollout restart deploy/web" shape carries the kind inline.
    inline = [t for t in rest if "/" in t]
    if inline:
        kind_part, _, name_part = inline[0].partition("/")
        kind = KIND_ALIASES.get(kind_part.lower())
        if name_part and not _is_placeholder(name_part):
            name = name_part
        rest = [t for t in rest if t != inline[0]]
    if kind is None:
        for token in rest:
            alias = KIND_ALIASES.get(token.lower())
            if alias:
                kind = alias
                rest = [t for t in rest[rest.index(token) + 1 :] if t != token]
                break
    if name is None:
        for token in rest:
            if token.lower() not in TOKEN_STOPWORDS:
                name = token
                break
    return Request(
        verb=verb, kind=kind, name=name, named_namespaces=namespaces, raw=invocation
    )


def _request_rank(request: Request) -> Tuple[bool, bool]:
    """Mutating requests first, then requests whose kind is known.

    Both components are booleans, so a bigger tuple wins and document order
    breaks ties — deterministic, and biased toward the request a bead is
    actually blocked on.
    """
    return (request.verb in MUTATING_KUBECTL_VERBS, request.kind is not None)


def parse_kubectl_request(text: str) -> Optional[Request]:
    """Parse the request a bead is blocked on, or None.

    Returns a Request whose `name` is None when the bead asks for an operation
    on an unnamed resource — the underspecified shape. Text whose kubectl
    invocations all carry an unrecognised verb yields no request.

    The resource kind is only believed when it is a known kind alias: a bare
    "kubectl delete" is treated as kind-unknown (and enumerated over pods)
    rather than trusting whatever word happens to follow the verb. Closing
    quote characters are stripped first, so a `` `kubectl delete pod` `` fence
    parses as "pod", not as the never-existing resource "pod`".
    """
    best: Optional[Request] = None
    for invocation in _kubectl_invocations(text):
        request = _parse_one_invocation(invocation.strip("`'\" \t"))
        if request is None:
            continue
        if best is None or _request_rank(request) > _request_rank(best):
            best = request
    return best


# ---------------------------------------------------------------------------
# context extraction
# ---------------------------------------------------------------------------


def distinctive_tokens(text: str) -> List[str]:
    """Lowercased tokens that could single a resource out.

    Every stopword is dropped, so "delete the pod" matches nothing and only a
    genuinely distinctive word ("whisper-stt", "kalshi", "pluck") can nominate a
    pod as the bead's target.
    """
    tokens = []
    seen = set()
    for match in TOKEN_RE.finditer(text.lower()):
        token = match.group(0).strip("-")
        if token in TOKEN_STOPWORDS or len(token) < 4 or token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens


def mentioned_clusters(text: str) -> List[str]:
    lowered = text.lower()
    return [cluster for cluster in sorted(KUBECTL_PROXIES) if cluster in lowered]


# ---------------------------------------------------------------------------
# live evidence
# ---------------------------------------------------------------------------


def cluster_proxies(only: Optional[List[str]] = None) -> Dict[str, str]:
    proxies = dict(KUBECTL_PROXIES)
    override = os.environ.get("ADC_KUBECTL_PROXIES")
    if override:
        try:
            proxies.update(json.loads(override))
        except json.JSONDecodeError:
            print(
                f"WARN ADC_KUBECTL_PROXIES is not valid JSON, ignored: {override[:120]}",
                file=sys.stderr,
            )
    if only:
        wanted = set(only)
        proxies = {name: url for name, url in proxies.items() if name in wanted}
    return proxies


def fetch_pods(
    cluster: str, server: str, timeout: int = 8
) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
    """`kubectl --server=<proxy> get pods -A -o json` — the only cluster call.

    Returns (pods, None) on success, (None, reason) when the cluster does not
    answer. Read-only by construction: the verb is built here, never taken from
    bead text.
    """
    result = subprocess.run(
        ["kubectl", f"--server={server}", "get", "pods", "-A", "-o", "json"],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        return None, (result.stderr.strip() or f"rc={result.returncode}")[:200]
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return None, f"unparseable kubectl output: {exc}"
    return payload.get("items") or [], None


def _pod_haystack(pod: Dict[str, Any]) -> str:
    metadata = pod.get("metadata") or {}
    labels = " ".join(
        str(value) for value in (metadata.get("labels") or {}).values()
    )
    owners = " ".join(
        str(owner.get("name") or "") for owner in metadata.get("ownerReferences") or []
    )
    images = " ".join(
        str(container.get("image") or "")
        for container in (pod.get("spec") or {}).get("containers") or []
    )
    return " ".join(
        [str(metadata.get("name") or ""), str(metadata.get("namespace") or ""), labels, owners, images]
    ).lower()


class Candidate:
    def __init__(self, cluster: str, namespace: str, name: str, reason: str) -> None:
        self.cluster = cluster
        self.namespace = namespace
        self.name = name
        self.reason = reason

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Candidate) and (
            (self.cluster, self.namespace, self.name)
            == (other.cluster, other.namespace, other.name)
        )

    def __hash__(self) -> int:
        return hash((self.cluster, self.namespace, self.name))

    def line(self) -> str:
        return (
            f"- candidate: pod/{self.name} namespace={self.namespace} "
            f"cluster={self.cluster} ({self.reason})"
        )


def match_pods(
    beads_context_tokens: List[str],
    namespaces: List[str],
    cluster: str,
    pods: List[Dict[str, Any]],
) -> List[Candidate]:
    """Pods on one cluster that the bead's own context singles out."""
    candidates: List[Candidate] = []
    for pod in pods:
        metadata = pod.get("metadata") or {}
        name = str(metadata.get("name") or "")
        namespace = str(metadata.get("namespace") or "")
        if not name:
            continue
        haystack = _pod_haystack(pod)
        if namespace in namespaces:
            candidates.append(
                Candidate(cluster, namespace, name, f'namespace "{namespace}" named in the bead')
            )
            continue
        hit = next((token for token in beads_context_tokens if token in haystack), None)
        if hit:
            candidates.append(Candidate(cluster, namespace, name, f'token "{hit}" in the bead matches live pod metadata'))
    return candidates


def notes_candidates(request: Request, notes: str) -> List[Tuple[str, str]]:
    """(namespace, pod) pairs a later note names, used to corroborate live data.

    A name from the notes only counts once the live query agrees it exists —
    notes are evidence, not authority.
    """
    pairs: List[Tuple[str, str]] = []
    namespace = None
    for match in re.finditer(r"(?:-n |--namespace=|--namespace )([\w-]+)", notes):
        if not _is_placeholder(match.group(1)):
            namespace = match.group(1)
    for match in re.finditer(r"\bpods?/([\w][\w.-]*)", notes):
        pod = match.group(1).rstrip(".")
        if not _is_placeholder(pod):
            pairs.append((namespace, pod))
    return pairs


def git_evidence(text: str, workspace: Path, timeout: int = 10) -> List[str]:
    """Recent commits for workspace files the bead names — context, not proof.

    A bead asking to "fix the retry logic in src/utilities/retry.py" is easier
    to claim when the note shows what recently touched that file. Nothing here
    decides candidacy; it only rides along in the note.
    """
    evidence: List[str] = []
    named = list(dict.fromkeys(PATHLIKE_RE.findall(text)))[:GIT_LOG_PATHS]
    for relative in named:
        if not (workspace / relative).is_file():
            continue
        result = subprocess.run(
            ["git", "-C", str(workspace), "log", f"-{GIT_LOG_COUNT}", "--oneline", "--", relative],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0 or not result.stdout.strip():
            continue
        commits = "; ".join(line.strip() for line in result.stdout.strip().splitlines())
        evidence.append(f"{relative}: {commits}")
    return evidence


def gather_candidates(
    request: Request,
    text: str,
    notes: str,
    workspace: Path,
    proxies: Dict[str, str],
    kubectl_timeout: int = 8,
) -> Tuple[List[Candidate], List[str]]:
    """Resolve the missing target against live evidence.

    Returns (candidates, unreachable_cluster_names). Namespace-scoped tokens
    from the bead, corroborated names from the notes thread, and the live pod
    list are the only inputs; nothing is invented.
    """
    tokens = distinctive_tokens(text)
    candidates: List[Candidate] = []
    unreachable: List[str] = []

    for cluster, server in sorted(proxies.items()):
        try:
            pods, error = fetch_pods(cluster, server, timeout=kubectl_timeout)
        except (subprocess.SubprocessError, OSError):
            pods = None
        if pods is None:
            unreachable.append(cluster)
            continue
        candidates.extend(match_pods(tokens, request.named_namespaces, cluster, pods))
        for namespace, pod in notes_candidates(request, notes):
            for item in pods:
                metadata = item.get("metadata") or {}
                if str(metadata.get("name") or "") == pod and namespace in (
                    None,
                    str(metadata.get("namespace") or ""),
                ):
                    candidates.append(
                        Candidate(
                            cluster,
                            str(metadata.get("namespace") or ""),
                            pod,
                            f"named in the bead's notes and live on {cluster}",
                        )
                    )

    # A pod can be nominated two ways (namespace plus a token); dedupe, keeping
    # the first reason.
    unique: List[Candidate] = []
    seen = set()
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            unique.append(candidate)
    return unique, unreachable


# ---------------------------------------------------------------------------
# note formatting
# ---------------------------------------------------------------------------


def format_caveats(unreachable: List[str]) -> List[str]:
    if not unreachable:
        return []
    return [
        "- caveat: no live evidence from unreachable cluster(s) "
        + ", ".join(sorted(unreachable))
        + " — the candidate set may be incomplete"
    ]


def format_resolved_note(
    request: Request,
    candidates: List[Candidate],
    unreachable: List[str],
    git_lines: List[str],
) -> str:
    lines = [
        ENRICHMENT_MARKER,
        "- Resolved: 1 candidate matched the bead's stated context",
        f"- Request: {request.describe()}",
        * [candidate.line() for candidate in candidates[:MAX_CANDIDATE_LINES]],
        "- Live evidence: kubectl --server=<per-cluster proxy> get pods -A -o json (read-only)",
        * format_caveats(unreachable),
    ]
    if git_lines:
        lines.append("- Git context (recent commits on files the bead names):")
        lines.extend(f"  - {line}" for line in git_lines)
    lines.append(
        "- Discovery only: any cluster mutation stays out of scope here and "
        "belongs to a declarative-config edit (commit + ArgoCD sync)."
    )
    return "\n".join(lines)


def format_deferred_note(
    request: Optional[Request],
    candidates: List[Candidate],
    unreachable: List[str],
) -> str:
    count = len(candidates)
    lines = [
        DEFER_NOTE_FORMAT.format(count=count),
    ]
    if request is not None:
        lines.append(f"- Request: {request.describe()}")
    if candidates:
        lines.extend(candidate.line() for candidate in candidates[:MAX_CANDIDATE_LINES])
        if count > MAX_CANDIDATE_LINES:
            lines.append(f"- … and {count - MAX_CANDIDATE_LINES} more")
    else:
        lines.append(
            "- No live resource matched the bead's stated context, so the "
            "missing parameter could not be resolved deterministically"
        )
    lines.extend(format_caveats(unreachable))
    lines.append(f"- {ENRICHMENT_MARKER}: deferred out of the ready frontier")
    return "\n".join(lines)


def append_notes(existing: str, note: str) -> str:
    """Append to the notes field without losing what is already there.

    `bead update --notes` replaces the field, so the caller passes the current
    notes back through with the new block appended.
    """
    existing = (existing or "").rstrip()
    if not existing:
        return note
    return f"{existing}\n\n{note}"


# ---------------------------------------------------------------------------
# bead mutations
# ---------------------------------------------------------------------------


def update_bead(
    bead: Dict[str, Any],
    bead_bin: str,
    workspace: Path,
    note: str,
    status: Optional[str] = None,
) -> None:
    """One guarded `bead update`: notes read-modify-write, optional transition.

    `--if-revision` makes the read-modify-write safe against a concurrent
    writer; the CLI exits 4 on a stale revision without changing anything,
    which surfaces as RuntimeError and is reported, never retried.
    """
    args = [bead_bin, "update", bead["id"], "--if-revision", str(bead.get("revision", 0))]
    if status:
        args += ["--status", status]
    args += ["--notes", append_notes(bead.get("notes") or "", note)]
    result = subprocess.run(
        args, capture_output=True, text=True, timeout=60, cwd=str(workspace)
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[:300]
        raise RuntimeError(
            f"bead update {bead['id']} failed (rc={result.returncode}): {detail}"
        )


# ---------------------------------------------------------------------------
# decision
# ---------------------------------------------------------------------------

ACTION_RESOLVE = "resolve"
ACTION_DEFER = "defer"
ACTION_NO_REQUEST_SHAPE = "no-request-shape"
ACTION_UNSUPPORTED_KIND = "unsupported-kind"
ACTION_ALREADY_SPECIFIC = "already-specific"


def decide(request: Optional[Request], candidates: List[Candidate]) -> str:
    """The whole policy in one place.

    Exactly one live candidate makes the bead claimable; any other count sends
    it to deferred with the count stated. A bead with no parseable request, or
    one whose target is a resource kind this tool does not enumerate, is left
    for a human rather than guessed at.
    """
    if request is None:
        return ACTION_NO_REQUEST_SHAPE
    if request.kind is not None and request.kind not in ENUMERABLE_KINDS:
        return ACTION_UNSUPPORTED_KIND
    if not request.underspecified:
        return ACTION_ALREADY_SPECIFIC
    if len(candidates) == 1:
        return ACTION_RESOLVE
    return ACTION_DEFER


# ---------------------------------------------------------------------------
# per-bead enrichment
# ---------------------------------------------------------------------------


def enrich_bead(
    bead: Dict[str, Any],
    workspace: Path,
    bead_bin: str,
    proxies: Dict[str, str],
    kubectl_timeout: int = 8,
    dry_run: bool = False,
) -> Dict[str, Any]:
    bead_id = bead["id"]
    text = bead_text(bead)
    notes = bead.get("notes") or ""
    request = parse_kubectl_request(text)

    if request is None:
        return {"bead_id": bead_id, "action": ACTION_NO_REQUEST_SHAPE}
    if request.kind is not None and request.kind not in ENUMERABLE_KINDS:
        return {"bead_id": bead_id, "action": ACTION_UNSUPPORTED_KIND, "kind": request.kind}
    if not request.underspecified:
        return {"bead_id": bead_id, "action": ACTION_ALREADY_SPECIFIC}

    candidates, unreachable = gather_candidates(
        request, text, notes, workspace, proxies, kubectl_timeout
    )
    action = decide(request, candidates)

    if dry_run:
        return {
            "bead_id": bead_id,
            "action": f"would-{action}",
            "candidates": [c.line() for c in candidates],
            "unreachable": sorted(unreachable),
        }

    try:
        if action == ACTION_RESOLVE:
            git_lines = git_evidence(text, workspace)
            note = format_resolved_note(request, candidates, unreachable, git_lines)
            update_bead(bead, bead_bin, workspace, note)
        else:
            note = format_deferred_note(request, candidates, unreachable)
            update_bead(bead, bead_bin, workspace, note, status="deferred")
    except (RuntimeError, subprocess.SubprocessError) as exc:
        print(f"ERROR enriching {bead_id}: {exc}", file=sys.stderr)
        return {"bead_id": bead_id, "action": "failed", "error": str(exc)}

    print(
        f"{action.upper()} {bead_id} candidates={len(candidates)} "
        f"unreachable_clusters={len(unreachable)}"
    )
    return {
        "bead_id": bead_id,
        "action": action,
        "candidates": [c.line() for c in candidates],
        "unreachable": sorted(unreachable),
        "request": request.describe(),
    }


def enrich(
    workspace: Path,
    bead_bin: str,
    dry_run: bool = False,
    only_beads: Optional[List[str]] = None,
    clusters: Optional[List[str]] = None,
    kubectl_timeout: int = 8,
) -> List[Dict[str, Any]]:
    """Enrich every qualifying bead; one record per bead, ordered by discovery."""
    open_beads = run_bead_list(["--status", "open"], bead_bin, workspace)
    candidates = find_underspecified_beads(open_beads)
    if only_beads is not None:
        wanted = set(only_beads)
        candidates = [bead for bead in candidates if bead.get("id") in wanted]
        missing = wanted - {bead.get("id") for bead in candidates}
        for bead_id in sorted(missing):
            print(f"SKIP {bead_id}: not an unresolved open underspecified bead", file=sys.stderr)

    if not candidates:
        # Nothing qualifies, so no kubectl call is made at all: the healthcheck
        # runs this every 15 minutes and a quiet workspace must stay cheap.
        return []

    proxies = cluster_proxies(clusters)
    return [
        enrich_bead(
            bead,
            workspace,
            bead_bin,
            proxies,
            kubectl_timeout=kubectl_timeout,
            dry_run=dry_run,
        )
        for bead in candidates
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve or honestly retire underspecified beads awaiting user input"
    )
    parser.add_argument(
        "--workspace",
        default="/home/coding/aide-de-camp",
        help="Path to the beads workspace (default: /home/coding/aide-de-camp)",
    )
    parser.add_argument(
        "--bead",
        action="append",
        dest="only_beads",
        metavar="ID",
        help="Consider only this bead id (repeatable). Status filters still apply.",
    )
    parser.add_argument(
        "--cluster",
        action="append",
        dest="clusters",
        metavar="NAME",
        help="Restrict live pod discovery to this cluster (repeatable). "
        "Default: every cluster in the fleet map.",
    )
    parser.add_argument(
        "--kubectl-timeout",
        type=int,
        default=8,
        help="Per-cluster timeout for the read-only pod listing (default: 8s)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be resolved or deferred without mutating anything",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Print a JSON summary of the actions taken",
    )
    parser.add_argument(
        "--bead-bin",
        help="Path to the bead CLI (default: bead on PATH, falling "
        "back to ~/.local/bin/bead and ~/.cargo/bin/bead)",
    )
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()
    bead_bin = resolve_bead_bin(args.bead_bin)

    try:
        records = enrich(
            workspace=workspace,
            bead_bin=bead_bin,
            dry_run=args.dry_run,
            only_beads=args.only_beads,
            clusters=args.clusters,
            kubectl_timeout=args.kubectl_timeout,
        )
    except (RuntimeError, subprocess.SubprocessError) as exc:
        print(f"ERROR could not read the queue: {exc}", file=sys.stderr)
        return 1

    if args.as_json:
        print(json.dumps({"workspace": str(workspace), "records": records}, indent=2))
    else:
        resolved = sum(1 for r in records if r.get("action") == ACTION_RESOLVE)
        deferred = sum(1 for r in records if r.get("action") == ACTION_DEFER)
        print(
            f"Done: {resolved} resolved, {deferred} deferred, "
            f"{len(records)} record(s) total"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

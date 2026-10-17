# Action execution step types

This page describes the seven status and evidence steps used by `ActionExecutor`. Workflow definitions are ordered lists of step names under `projects.<slug>.workflows.<name>.steps` in `config/registry.yaml`. The executor also registers `gitops_commit`, `argocd_sync_status` (and `argocd_sync`), `pod_logs`, and `argocd_events`; their implementation is outside this reference.

## Active executor contract

`ActionExecutor` calls each step function in `src/action/steps/__init__.py` with `intent_id`, `session_id`, `project_slug`, and the project's `project_cfg`. Each function returns a **plain dictionary** on success or raises `ValueError`/`RuntimeError` on failure. `ActionExecutor` wraps that dictionary in `src.action.models.StepResult.output`, marks the step `completed`, and streams its result. A raised exception becomes a `failed` step and halts the workflow before subsequent steps run. There is no `success`/`data` wrapper in this path.

The standalone `CIStatusStep`, `ImageTagStep`, and `PodStatusStep` classes in `src/action/steps/read.py` use a different `StepResult(success, data, error)` type. The active `execute_ci_status_step` and `execute_image_tag_step` functions adapt those class results to the plain-dictionary/exception contract.

Read steps do not mutate the cluster, ArgoCD, Git, or bead store. `ci_status` and `image_tag` are read-only gates. `pod_status` is an additional readiness gate when it follows a completed ArgoCD sync step in the same workflow. A standalone `pod_status` step reports status without enforcing readiness.

| Step | Required project context | Main output | Failure or gate |
| --- | --- | --- | --- |
| `deployment_info` | `cluster`, `namespace` | `deployments`, `statefulsets`, `namespace`, `cluster` | Missing config/proxy, malformed response, or HTTP error raises |
| `git_log` | `repo_path` | `commits`, `count`, `repo_path` | Missing repo, failed Git command, or timeout raises |
| `argocd_apps` | `cluster` for cluster-aware routing; otherwise global ArgoCD URL | `applications`, `cluster` | Unmapped/authenticated cluster, missing endpoint, or HTTP error raises |
| `open_beads` | `repo_path` with native bead-rs state | `open_beads`, `count`, `repo_path`, `project_filter` | Missing workspace, command failure, invalid JSONL, or timeout raises |
| `ci_status` | `project_slug` | `status`, `phase`, `workflow_name`, CI metadata | Only latest `Succeeded` workflow passes; all other outcomes raise |
| `pod_status` | `cluster`, `namespace` | `total_pods`, phase counts, `pod_names`, `namespace`, `cluster` | Missing config/proxy or HTTP error raises; optional post-sync readiness gate |
| `image_tag` | Successful preceding `ci_status` output | `tag`, `registry_path`, `digest`, `project_slug` | Missing/invalid CI image evidence or `latest` raises |

## Step details

### `deployment_info`

The step resolves `project_cfg.cluster` to a Kubernetes read-only proxy from `config/registry.yaml`, then GETs both `/apis/apps/v1/namespaces/{namespace}/deployments` and `/apis/apps/v1/namespaces/{namespace}/statefulsets`. Both requests use a 10-second HTTP timeout. The response is parsed as Kubernetes JSON objects.

```json
{
  "deployments": [{"name": "api", "replicas": 3, "ready": 2, "updated": 3}],
  "statefulsets": [{"name": "db", "replicas": 1, "ready": 1}],
  "namespace": "prod",
  "cluster": "ardenone-cluster"
}
```

Missing replica status fields become `0`; missing `spec.replicas` becomes `1`. This step reports workload state. It does not require every workload to be ready.

### `git_log`

`project_cfg.repo_path` must name a local directory. The step runs `git -C {repo_path} log -{count} --oneline` with a 10-second timeout. `project_cfg.commit_count` is an optional positive integer; its default is `10`.

```json
{
  "commits": [{"hash": "abc1234", "message": "Update manifest"}],
  "count": 1,
  "repo_path": "/home/coding/declarative-config"
}
```

The hash and message come from each `--oneline` line. A missing path, nonzero Git exit, or timeout fails the step.

### `argocd_apps`

When `project_cfg.cluster` is set, the step resolves that cluster's ArgoCD endpoint through `config/clusters.yaml`. Only endpoints with `access: read-only-proxy` are usable. An unmapped cluster or an authenticated-only endpoint fails rather than querying a different ArgoCD instance. Without a cluster, the step uses the global `argocd.base_url` in `config/registry.yaml`.

It GETs `/api/v1/applications` with a 10-second HTTP timeout. If `project_slug` is present, it filters by `project_cfg.argocd_app` or, by default, the slug. No matching application yields an empty list.

```json
{
  "applications": [{
    "name": "pbx-web",
    "namespace": "argocd",
    "sync_status": "Synced",
    "health_status": "Healthy",
    "operation": null
  }],
  "cluster": "ardenone-cluster"
}
```

This is an information query; an `OutOfSync` or `Degraded` application is returned as data and does not fail this step.

### `open_beads`

`project_cfg.repo_path` must be a directory containing `.beads/config.json` (native bead-rs state). For the `aide-de-camp` project only, a missing path defaults to this repository. The step resolves the `bead` executable from `PATH` or `~/.cargo/bin/bead` and runs:

```text
bead list --status open --json --limit 999999
```

It runs in `repo_path` with a 10-second timeout. Standard output is JSON Lines: one bead object per nonempty line. Invalid JSONL fails the step rather than showing a plausible empty backlog. The command does **not** pass `--project`; a project's own bead workspace is already the selection boundary.

```json
{
  "open_beads": [{"id": "adc-123", "title": "Repair status query", "status": "open"}],
  "count": 1,
  "repo_path": "/home/coding/aide-de-camp",
  "project_filter": null
}
```

### `ci_status`

`project_slug` is required. The step uses `project_cfg.kubectl_config`, defaulting to `/home/coding/.kube/iad-ci.kubeconfig`, and `project_cfg.ci_timeout`, defaulting to 15 seconds. It queries Argo Workflows in the `argo-workflows` namespace with label `project={project_slug}`, sorted by creation time, and inspects the latest workflow.

```json
{
  "status": "success",
  "phase": "Succeeded",
  "workflow_name": "pbx-web-build-123",
  "created_at": "2026-10-17T12:00:00Z",
  "message": "",
  "cluster": "iad-ci",
  "project_slug": "pbx-web",
  "image_tag": "v1.2.3",
  "image_digest": null,
  "registry_path": "registry.example/pbx-web:v1.2.3"
}
```

Image fields are taken from the latest workflow's output parameters, annotations, or labels; underscore and hyphenated field names are accepted. A missing kubeconfig, no matching workflow, non-`Succeeded` phase, failed command, malformed response, or timeout **raises and halts the workflow**. There is no nonblocking `skipped` or `no_workflows` outcome at the active executor boundary.

### `pod_status`

The step requires `project_cfg.cluster` and `project_cfg.namespace`, resolves the Kubernetes read-only proxy from `config/registry.yaml`, and GETs `/api/v1/namespaces/{namespace}/pods` with a 10-second timeout.

```json
{
  "total_pods": 2,
  "running": 1,
  "pending": 1,
  "failed": 0,
  "pod_names": ["api-1", "api-2"],
  "namespace": "prod",
  "cluster": "ardenone-cluster"
}
```

The counts describe pod *phases*, not container readiness. `ActionExecutor` passes `verify_ready=True` when a preceding `argocd_sync` or `argocd_sync_status` step completed. In that mode, zero pods, a pod outside `Running`, a terminating pod, a pod without container statuses, an unready container, or a `Ready=False` pod condition raises and halts the workflow. Otherwise the step reports pod phases without enforcing a gate.

### `image_tag`

`ActionExecutor` passes the output of the preceding completed `ci_status` step as `ci_status_result`. A direct caller may pass that plain dictionary as an optional keyword argument to `execute_image_tag_step`; a successful CI result is required. The step prefers `image_tag`, then `image_digest`, then a recognizable version or digest in the workflow name. It uses `registry_path` from CI when supplied; otherwise it builds one from `project_cfg.image_repository` or `ronaldraygun/{project_slug}`.

```json
{
  "tag": "v1.2.3",
  "registry_path": "registry.example/pbx-web:v1.2.3",
  "digest": null,
  "project_slug": "pbx-web"
}
```

A missing tag/digest, `latest` tag or path, or registry path whose suffix does not match the CI tag fails the step. For a digest, the generated image reference uses `@sha256:...` and `digest` carries that value. Image resolution is read-only; it does not edit a manifest.

## Workflow behavior and verification

The executor runs steps in registry order. It captures exceptions in `StepResult.error`, marks the step `failed`, and stops. Successful plain dictionaries are stored in `StepResult.output`. A deployment workflow that uses these gates should put `ci_status` before `image_tag`, then perform its authorized GitOps step, sync check, and `pod_status` verification.

The targeted contract tests are in `tests/test_action_step_coverage.py` and `tests/test_action_read_steps.py`. Their HTTP, subprocess, and CI workflow payloads are mocked; they do not prove live cluster or ArgoCD reachability.

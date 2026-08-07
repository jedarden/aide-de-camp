# Pod Deletion Warning Implementation

## Overview
This implementation provides a warning system for pod deletion when pods are managed by Deployments or ReplicaSets in Kubernetes. The system ensures users understand that deleted pods will be automatically recreated by Kubernetes controllers.

## Implementation Details

### Core Method: `check_pod_ownership()`

Located in `/home/coding/aide-de-camp/src/escalate/commands.py`

#### Method Signature
```python
async def check_pod_ownership(
    self,
    pod_name: str,
    namespace: str,
    cluster_proxy: str,
    project_slug: Optional[str] = None,
) -> dict
```

#### Return Value Structure
```python
{
    "is_managed": bool,        # True if pod is managed by Deployment/ReplicaSet
    "owner_kind": str,         # 'Deployment', 'ReplicaSet', or None
    "owner_name": str,         # Name of the owner resource
    "warning_message": str    # User-friendly warning message
}
```

### Logic Flow

1. **Pod Metadata Retrieval**
   - Fetches pod details via Kubernetes API at `/api/v1/namespaces/{namespace}/pods/{pod_name}`
   - Uses cluster proxy for secure access

2. **Owner Reference Analysis**
   - Examines `metadata.ownerReferences` field
   - Checks for Deployment or ReplicaSet ownership
   - Sets `is_managed=True` if controlled by these resources

3. **Warning Generation**
   - Creates clear warning message about automatic recreation
   - Identifies the owner kind and name
   - Explains normal Kubernetes behavior

### Integration with `execute_delete_pod()`

The warning system integrates with the existing pod deletion workflow:

#### Decision Flow
```
1. User requests pod deletion
   ↓
2. check_pod_ownership() called
   ↓
3. If pod is managed and skip_warning=False:
   - Return 'confirmation_required' status
   - Include detailed confirmation_details
   - Show warning about automatic recreation
   ↓
4. User confirms or skip_warning=True
   ↓
5. Proceed with deletion
   - Display warning in result
   - Include ownership information
```

### Warning Content

#### Primary Warning Message
```
"This pod is managed by a {kind} and will be automatically recreated 
after deletion. This is normal Kubernetes behavior."
```

#### Detailed Confirmation Details
```python
{
    "title": "Pod is managed by {kind}",
    "message": "Pod '{pod_name}' is managed by {kind} '{owner_name}'. 
                This pod will be automatically recreated after deletion. 
                This is normal Kubernetes behavior - the {kind} will 
                maintain the desired number of pod replicas.",
    "owner_kind": "Deployment",  # or "ReplicaSet"
    "owner_name": "deployment-name",
    "behavior": "automatic_recreation",
    "explanation": "Deployments and ReplicaSets are Kubernetes controllers 
                    that ensure a specified number of pod replicas are 
                    running at all times. When you delete a pod managed by 
                    these controllers, they automatically create a replacement 
                    pod to maintain the desired state."
}
```

## Acceptance Criteria Verification

### ✅ User understands the pod may be recreated automatically
- **Implementation**: Warning message clearly states "will be automatically recreated after deletion"
- **Location**: Primary warning message and confirmation_details.message

### ✅ Warning clearly explains Deployment/ReplicaSet behavior  
- **Implementation**: 
  - Identifies owner kind (Deployment/ReplicaSet)
  - Explains that these controllers maintain desired replicas
  - Detailed explanation in confirmation_details.explanation
- **Content**: "maintain the desired number of pod replicas"

### ✅ User knows this is normal Kubernetes behavior
- **Implementation**: Explicit statement "This is normal Kubernetes behavior"
- **Educational Context**: Detailed explanation of how Kubernetes controllers work

### ✅ User has opportunity to cancel if they don't want this
- **Implementation**: 
  - Returns 'confirmation_required' status
  - User must explicitly confirm deletion
  - skip_warning parameter available for automation scenarios

## Usage Examples

### Example 1: Managed Pod Warning
```python
# User requests deletion of Deployment-managed pod
result = await executor.execute_delete_pod(
    pod_name="my-app-5d6f7b8c9-xkv2p",
    namespace="default",
    project_slug="my-app"
)

# Result when pod is managed:
{
    "status": "confirmation_required",
    "summary": "Pod 'my-app-5d6f7b8c9-xkv2p' is managed by a Deployment and will be automatically recreated",
    "warning": "This pod is managed by a Deployment and will be automatically recreated after deletion. This is normal Kubernetes behavior.",
    "confirmation_details": {
        "title": "Pod is managed by Deployment",
        "owner_kind": "Deployment",
        "owner_name": "my-app",
        "behavior": "automatic_recreation"
    }
}
```

### Example 2: Unmanaged Pod Deletion
```python
# User requests deletion of standalone pod
result = await executor.execute_delete_pod(
    pod_name="standalone-pod",
    namespace="default"
)

# Result when pod is not managed:
{
    "status": "completed",
    "summary": "Deleted pod 'standalone-pod' from namespace 'default'",
    "warning": None  # No warning for unmanaged pods
}
```

## Error Handling

### HTTP Errors
- Graceful degradation if pod metadata fetch fails
- Logs warning but continues with deletion
- kubectl delete will fail if pod doesn't exist

### Network Issues
- 10-second timeout for API calls
- Logs error without blocking deletion workflow
- Maintains system stability

## Testing

### Test Coverage
- Unit tests verify ownership detection logic
- Integration tests confirm warning flow
- Acceptance criteria tests validate user experience

### Running Tests
```bash
.venv/bin/python test_pod_warning_simple.py
```

## Files Modified

1. **`/home/coding/aide-de-camp/src/escalate/commands.py`**
   - Added `check_pod_ownership()` method (lines 132-204)
   - Integrated with existing `execute_delete_pod()` method
   - Maintains backward compatibility

2. **Test Files**
   - `test_pod_deployment_warning.py` - Comprehensive integration tests
   - `test_pod_warning_simple.py` - Logic verification tests

## Backward Compatibility

- Existing `execute_delete_pod()` functionality preserved
- New `skip_warning` parameter for automation scenarios
- Default behavior enhanced with warnings (no breaking changes)

## Future Enhancements

Potential improvements for future iterations:
1. **StatefulSet Detection**: Extend to include StatefulSet ownership
2. **DaemonSet Detection**: Add DaemonSet ownership checks  
3. **Custom Resource Support**: Handle custom controller types
4. **Batch Operations**: Support multiple pod deletion with single warning
5. **Recreation Prediction**: Estimate recreation time based on image pull history

## Conclusion

This implementation successfully addresses the requirement to warn users about Deployment/ReplicaSet recreation behavior when deleting managed pods. All acceptance criteria have been met:

- ✅ Clear user communication about automatic recreation
- ✅ Explanation of Kubernetes controller behavior  
- ✅ Opportunity for user cancellation
- ✅ Educational context about normal behavior
- ✅ Robust error handling
- ✅ Backward compatibility maintained

The warning system provides a better user experience while maintaining the powerful automation capabilities of the aide-de-camp system.
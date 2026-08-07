#!/usr/bin/env python3
"""
Validate workflow labels for pbx-web-build template
"""
import json
from pathlib import Path
from typing import Dict, List, Any

def validate_workflow_labels(workflow_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate that workflows have the expected workflow-template label.

    Args:
        workflow_data: Parsed workflow JSON data with 'workflows' key

    Returns:
        Validation report with statistics and findings
    """
    workflows = workflow_data.get('workflows', [])
    expected_label = 'workflows.argoproj.io/workflow-template'
    expected_value = 'pbx-web-build'

    results = {
        'total_workflows': len(workflows),
        'expected_label': expected_label,
        'expected_value': expected_value,
        'workflows_with_correct_label': 0,
        'workflows_with_incorrect_label': 0,
        'workflows_missing_label': 0,
        'label_values_found': {},
        'incorrect_workflows': [],
        'missing_label_workflows': []
    }

    for workflow in workflows:
        workflow_name = workflow.get('metadata', {}).get('name', 'unknown')
        labels = workflow.get('metadata', {}).get('labels', {})
        template_ref = workflow.get('spec', {}).get('workflowTemplateRef', {}).get('name', 'unknown')

        # Check if the expected label exists
        if expected_label in labels:
            label_value = labels[expected_label]

            # Track unique label values found
            if label_value not in results['label_values_found']:
                results['label_values_found'][label_value] = []
            results['label_values_found'][label_value].append(workflow_name)

            # Check if the value is correct
            if label_value == expected_value:
                results['workflows_with_correct_label'] += 1
            else:
                results['workflows_with_incorrect_label'] += 1
                results['incorrect_workflows'].append({
                    'name': workflow_name,
                    'label_value': label_value,
                    'template_ref': template_ref,
                    'all_labels': labels
                })
        else:
            # Label is completely missing
            results['workflows_missing_label'] += 1
            results['missing_label_workflows'].append({
                'name': workflow_name,
                'template_ref': template_ref,
                'existing_labels': list(labels.keys())
            })

    return results

def generate_markdown_report(results: Dict[str, Any]) -> str:
    """Generate a markdown validation report."""

    total = results['total_workflows']
    correct = results['workflows_with_correct_label']
    incorrect = results['workflows_with_incorrect_label']
    missing = results['workflows_missing_label']

    report = f"""# Workflow Template Label Validation Report

## Summary

- **Total Workflows Checked:** {total}
- **Expected Label:** `{results['expected_label']}={results['expected_value']}`
- **Workflows with Correct Label:** {correct}
- **Workflows with Incorrect Label:** {incorrect}
- **Workflows Missing Label:** {missing}

## Compliance Rate

{correct}/{total} workflows ({(correct/total*100):.1f}%) have the correct template label.

## Label Values Found

"""

    if results['label_values_found']:
        report += "The following label values were discovered:\n\n"
        for value, workflows in results['label_values_found'].items():
            report += f"- `{value}` ({len(workflows)} workflows)\n"
    else:
        report += "*No workflows have the expected label*\n"

    report += "\n"

    # Section for incorrect labels
    if results['incorrect_workflows']:
        report += "## Workflows with Incorrect Label Value\n\n"
        for wf in results['incorrect_workflows']:
            report += f"### `{wf['name']}`\n"
            report += f"- **Template Reference:** `{wf['template_ref']}`\n"
            report += f"- **Label Value Found:** `{wf['label_value']}`\n"
            report += f"- **All Labels:** `{json.dumps(wf['all_labels'], indent=2)}`\n\n"

    # Section for missing labels
    if results['missing_label_workflows']:
        report += "## Workflows Missing the Expected Label\n\n"
        for wf in results['missing_label_workflows']:
            report += f"### `{wf['name']}`\n"
            report += f"- **Template Reference:** `{wf['template_ref']}`\n"
            report += f"- **Existing Labels:** {', '.join(wf['existing_labels']) if wf['existing_labels'] else '*none*'}\n\n"

    # Conclusions
    report += "## Conclusions\n\n"

    if correct == total:
        report += "✅ **All workflows have the correct template label.**\n\n"
    elif correct > 0:
        report += f"⚠️ **Partial compliance:** Only {correct} of {total} workflows have the correct label.\n\n"
    else:
        report += "❌ **No workflows have the expected template label.**\n\n"

    if missing > 0:
        report += f"**Issue:** {missing} workflows are completely missing the `{results['expected_label']}` label.\n\n"

    if incorrect > 0:
        report += f"**Issue:** {incorrect} workflows have incorrect label values.\n\n"

    return report

def main():
    """Main execution function."""
    # Read the workflow data
    workflow_file = Path('/home/coding/aide-de-camp/research/pbx-web-workflows-raw.json')

    if not workflow_file.exists():
        print(f"Error: Workflow data file not found: {workflow_file}")
        return 1

    with open(workflow_file) as f:
        workflow_data = json.load(f)

    # Validate the labels
    results = validate_workflow_labels(workflow_data)

    # Generate the report
    report = generate_markdown_report(results)

    # Save the report
    report_file = Path('/home/coding/aide-de-camp/workflow_label_validation_report.md')
    with open(report_file, 'w') as f:
        f.write(report)

    # Print summary to stdout
    print(f"Workflow Label Validation Complete")
    print(f"==================================")
    print(f"Total workflows: {results['total_workflows']}")
    print(f"With correct label: {results['workflows_with_correct_label']}")
    print(f"With incorrect label: {results['workflows_with_incorrect_label']}")
    print(f"Missing label: {results['workflows_missing_label']}")
    print(f"\nFull report saved to: {report_file}")

    return 0

if __name__ == '__main__':
    exit(main())
/**
 * Simple verification script for stuck and failed card rendering.
 * Tests that the cards render with proper styling classes and structure.
 */

const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

// Load the canvas.js file
const canvasJs = fs.readFileSync(path.join(__dirname, 'src/canvas/canvas.js'), 'utf8');

// Create a DOM environment
const dom = new JSDOM('<!DOCTYPE html><html><head><title>Test</title></head><body></body></html>', {
  runScripts: 'dangerously',
  url: 'http://localhost'
});

global.document = dom.window.document;
global.window = dom.window;

// Execute the canvas.js to load the functions
eval(canvasJs);

// Test stuck card
console.log('=== Testing Stuck Card Rendering ===');
const stuckData = {
  bead_id: 'adc-12345',
  stuck_reason: 'Agent refused to complete task due to missing dependencies',
  refusal_count: 3,
  message: 'This task needs manual intervention to proceed',
  action_hint: 'Please review the bead and update the requirements'
};

const stuckCard = createStuckCard(stuckData);
const stuckHtml = stuckCard.outerHTML;

console.log('Stuck card classes:', stuckCard.className);
console.log('Stuck card data attributes:', stuckCard.dataset.builtin, stuckCard.dataset.beadId);

// Verify key elements are present
const stuckChecks = {
  'Has stuck-card class': stuckHtml.includes('stuck-card'),
  'Has builtin-card class': stuckHtml.includes('builtin-card'),
  'Has construction icon': stuckHtml.includes('🚧'),
  'Has correct title': stuckHtml.includes('Task stuck — needs your input'),
  'Has stuck reason': stuckHtml.includes('stuck-reason'),
  'Has stuck reason wrap': stuckHtml.includes('stuck-reason-wrap'),
  'Shows bead ID': stuckHtml.includes('adc-12345'),
  'Shows refusal count': stuckHtml.includes('Refusals: 3'),
  'Has view bead button': stuckHtml.includes('stuck-view-bead'),
  'Has warning theme elements': stuckHtml.includes('stuck-reason') && stuckHtml.includes('stuck-message')
};

console.log('\nStuck Card Checks:');
Object.entries(stuckChecks).forEach(([check, passed]) => {
  console.log(`${passed ? '✓' : '✗'} ${check}`);
});

// Test failed card
console.log('\n=== Testing Failed Card Rendering ===');
const failedData = {
  bead_id: 'adc-67890',
  failure_reason: 'Worker process crashed: out of memory',
  error_type: 'worker_crash',
  message: 'The task failed to complete due to a system error'
};

const failedCard = createFailedCard(failedData);
const failedHtml = failedCard.outerHTML;

console.log('Failed card classes:', failedCard.className);
console.log('Failed card data attributes:', failedCard.dataset.builtin, failedCard.dataset.beadId);

// Verify key elements are present
const failedChecks = {
  'Has failed-card class': failedHtml.includes('failed-card'),
  'Has builtin-card class': failedHtml.includes('builtin-card'),
  'Has X icon': failedHtml.includes('❌'),
  'Has correct title': failedHtml.includes('Task failed'),
  'Has failed reason': failedHtml.includes('failed-reason'),
  'Has failed reason wrap': failedHtml.includes('failed-reason-wrap'),
  'Shows bead ID': failedHtml.includes('adc-67890'),
  'Shows error type': failedHtml.includes('Error type: worker_crash'),
  'Has retry button': failedHtml.includes('failed-retry'),
  'Has error theme elements': failedHtml.includes('failed-reason') && failedHtml.includes('failed-message')
};

console.log('\nFailed Card Checks:');
Object.entries(failedChecks).forEach(([check, passed]) => {
  console.log(`${passed ? '✓' : '✗'} ${check}`);
});

// Summary
const stuckPassed = Object.values(stuckChecks).filter(v => v).length;
const failedPassed = Object.values(failedChecks).filter(v => v).length;
const totalChecks = Object.keys(stuckChecks).length + Object.keys(failedChecks).length;

console.log('\n=== Summary ===');
console.log(`Stuck card: ${stuckPassed}/${Object.keys(stuckChecks).length} checks passed`);
console.log(`Failed card: ${failedPassed}/${Object.keys(failedChecks).length} checks passed`);
console.log(`Total: ${stuckPassed + failedPassed}/${totalChecks} checks passed`);

if (stuckPassed + failedPassed === totalChecks) {
  console.log('\n✓ All rendering checks passed!');
  process.exit(0);
} else {
  console.log('\n✗ Some rendering checks failed!');
  process.exit(1);
}

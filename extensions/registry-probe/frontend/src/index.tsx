import React from 'react';
import { views, extensions } from '@apache-superset/core';

// A supported SQL Lab contribution is our positive loader control. Registering
// an arbitrary location does NOT create a consumer at that location. This is a
// deliberately negative experiment, never a shippable calendar replacement.
const range = '2025-03-20T20:30:00 : 2025-03-21T20:30:00';
function Candidate({ onChange = () => {} } = {}) {
  return React.createElement('button', {
    'data-test': 'jalali-probe-date-control',
    onClick: () => onChange(range),
  }, 'JALALI PROBE — ۱۴۰۴/۰۱/۰۱');
}
views.registerView(
  { id: 'jalali-lab.registry-probe.diagnostic', name: 'Jalali integration diagnostic' },
  'sqllab.panels',
  () => React.createElement('section', { 'data-test': 'jalali-probe-loaded' },
    React.createElement('p', null, 'Diagnostic extension loaded through the public API.'),
    React.createElement('pre', { 'data-test': 'jalali-probe-api' }, JSON.stringify({
      extensionAPIs: Object.keys(extensions).sort(),
      hasDateRegistry: typeof extensions.getExtensionsRegistry === 'function',
    })),
  ),
);
views.registerView(
  { id: 'jalali-lab.registry-probe.date', name: 'Jalali probe date control' },
  'filter.dateFilterControl',
  () => React.createElement(Candidate),
);

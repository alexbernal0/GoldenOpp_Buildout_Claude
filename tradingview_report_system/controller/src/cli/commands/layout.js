import { register } from '../router.js';
import * as core from '../../core/ui.js';
import * as layout from '../../core/layout.js';

register('layout', {
  description: 'Layout tools (list, switch, save, status)',
  subcommands: new Map([
    ['list', {
      description: 'List saved chart layouts',
      handler: () => core.layoutList(),
    }],
    ['switch', {
      description: 'Switch to a saved layout by name or ID',
      handler: (opts, positionals) => {
        if (!positionals[0]) throw new Error('Layout name required. Usage: tv layout switch "My Layout"');
        return core.layoutSwitch({ name: positionals.join(' ') });
      },
    }],
    ['save', {
      description: 'Save current layout immediately (calls saveChartSilently — use after adding indicators)',
      handler: () => layout.saveLayout(),
    }],
    ['status', {
      description: 'Get current layout name, ID and whether it has unsaved changes',
      handler: () => layout.getLayoutStatus(),
    }],
  ]),
});

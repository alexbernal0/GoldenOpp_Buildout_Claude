/**
 * Core layout management functions.
 * Uses TradingView's internal getSaveChartService() API (MaudeView-sourced pattern).
 *
 * Key function: saveLayout() — calls saveChartSilently() which persists the
 * current chart state (studies, indicators, drawings) immediately without
 * waiting for TV's background autosave. Call this after adding any indicator
 * via Pine editor to prevent loss on TV restart.
 */
import { evaluateAsync } from '../connection.js';

const TV_API_PREAMBLE = `
var api = null;
try {
  if (window.TradingViewApi) api = window.TradingViewApi;
  else if (window.TradingView && window.TradingView.api) api = window.TradingView.api;
} catch(_) {}
`;

/**
 * Save the current chart layout silently.
 * Equivalent to MaudeView's POST /api/v1/layout/save.
 * Uses api.getSaveChartService().saveChartSilently() internally.
 */
export async function saveLayout() {
  const result = await evaluateAsync(`
    (async function() {
      ${TV_API_PREAMBLE}
      if (!api) return { ok: false, error: 'TradingViewApi unavailable' };
      var svc = typeof api.getSaveChartService === 'function' ? api.getSaveChartService() : null;
      if (!svc || typeof svc.saveChartSilently !== 'function') {
        return { ok: false, error: 'saveChartSilently unavailable — TV may not be fully loaded' };
      }
      try {
        await svc.saveChartSilently(undefined, undefined, {});
      } catch(e) {
        return { ok: false, error: String(e && e.message || e) };
      }
      var layoutName = typeof api.layoutName === 'function' ? String(api.layoutName() || '') : '';
      var layoutId   = typeof api.layoutId   === 'function' ? String(api.layoutId()   || '') : '';
      return { ok: true, layout_name: layoutName, layout_id: layoutId };
    })()
  `);

  if (!result?.ok) throw new Error(result?.error || 'saveChartSilently failed');
  return {
    success: true,
    action: 'layout_saved',
    layout_name: result.layout_name,
    layout_id: result.layout_id,
  };
}

/**
 * Get current layout status (name, id, has_changes).
 */
export async function getLayoutStatus() {
  const result = await evaluateAsync(`
    (async function() {
      ${TV_API_PREAMBLE}
      if (!api) return { ok: false, error: 'TradingViewApi unavailable' };
      var layoutName = typeof api.layoutName === 'function' ? String(api.layoutName() || '') : '';
      var layoutId   = typeof api.layoutId   === 'function' ? String(api.layoutId()   || '') : '';
      var hasChanges = false;
      try {
        var svc = typeof api.getSaveChartService === 'function' ? api.getSaveChartService() : null;
        if (svc) {
          var hc = typeof svc.hasChanges === 'function' ? svc.hasChanges() : svc.hasChanges;
          if (hc && typeof hc.value === 'function') hc = hc.value();
          hasChanges = Boolean(hc);
        }
      } catch(_) {}
      return { ok: true, layout_name: layoutName, layout_id: layoutId, has_changes: hasChanges };
    })()
  `);

  if (!result?.ok) throw new Error(result?.error || 'getLayoutStatus failed');
  return {
    success: true,
    layout_name: result.layout_name,
    layout_id: result.layout_id,
    has_changes: result.has_changes,
  };
}

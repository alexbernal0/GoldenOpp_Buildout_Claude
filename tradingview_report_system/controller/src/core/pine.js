/**
 * Core Pine Script logic — shared between MCP tools and CLI.
 * All functions accept plain options objects and return plain JS objects.
 * They throw on error (callers catch and format).
 *
 * Upgraded 2026-04-06:
 *  - Monaco via webpack module cache (window.__tvMonacoNs) — more reliable than React fiber walk
 *  - Pine editor toggle uses trusted CDP Input.dispatchMouseEvent (not DOM .click())
 *  - "Add to chart" via Ctrl+Enter + dialog poll — replaces fragile DOM button hunt
 *  - saveChartSilently() after every successful compile — kills the autosave timing bug
 *  - saveAs(name): saves under new name, creates a genuine new script slot
 *  - newTab(): Shift+Alt+T opens a real new editor tab (genuine new slot, not overwrite)
 */
import { evaluate, evaluateAsync, getClient } from '../connection.js';

// ── Monaco namespace — webpack module cache method (MaudeView pattern) ──
// Tries webpack cache scan first, falls back to React fiber walk.
// Caches result on window.__tvMonacoNs for fast reuse within a session.
const MONACO_PREAMBLE = `
(function() {
  if (window.__tvMonacoNs && window.__tvMonacoNs.editor) return window.__tvMonacoNs;
  // Method 1: webpack require cache scan
  try {
    var wpReq = null;
    var globalKeys = Object.keys(window);
    for (var gk = 0; gk < globalKeys.length; gk++) {
      var k = globalKeys[gk];
      if ((k.startsWith('__webpack_require__') || k === 'webpackJsonp') && window[k] && window[k].c) {
        wpReq = window[k]; break;
      }
    }
    if (wpReq && wpReq.c) {
      var cacheKeys = Object.keys(wpReq.c);
      for (var ck = 0; ck < cacheKeys.length; ck++) {
        var mod = wpReq.c[cacheKeys[ck]];
        if (!mod || !mod.exports) continue;
        var exp = mod.exports;
        if (exp && exp.editor && typeof exp.editor.getModels === 'function') {
          window.__tvMonacoNs = exp; return exp;
        }
        if (exp && exp.default && exp.default.editor && typeof exp.default.editor.getModels === 'function') {
          window.__tvMonacoNs = exp.default; return exp.default;
        }
      }
    }
  } catch(_) {}
  // Method 2: React fiber walk — try ALL .monaco-editor elements (not just first)
  var FIBER_PREFIX = '__reactFiber' + '$'; // split to avoid template literal interpolation
  var containers = document.querySelectorAll('.monaco-editor');
  for (var ci = 0; ci < containers.length; ci++) {
    var container = containers[ci];
    if (!container.offsetParent) continue;
    var el = container;
    var fiberKey;
    for (var i = 0; i < 20; i++) {
      if (!el) break;
      fiberKey = Object.keys(el).find(function(k) { return k.startsWith(FIBER_PREFIX); });
      if (fiberKey) break;
      el = el.parentElement;
    }
    if (!fiberKey) continue;
    var current = el[fiberKey];
    for (var d = 0; d < 30; d++) {
      if (!current) break;
      if (current.memoizedProps && current.memoizedProps.value && current.memoizedProps.value.monacoEnv) {
        var env = current.memoizedProps.value.monacoEnv;
        if (env && env.editor && typeof env.editor.getModels === 'function') {
          var mods = env.editor.getModels();
          if (mods && mods.length > 0) {
            window.__tvMonacoNs = env; return env;
          }
        }
      }
      current = current.return;
    }
  }
  return null;
})()
`;

// ── Monaco access helpers ──
// All return serializable primitives (boolean, string, array) because
// CDP evaluate() uses returnByValue:true and cannot serialize Monaco objects.
//
// ensureMonacoNs() caches the Monaco namespace on window.__tvMonacoNs via the
// React fiber walk. Subsequent calls just check the cache.
// The fiber walk is inlined (not via MONACO_PREAMBLE template nesting) to avoid
// template-literal escaping issues when building nested JS strings.

const ENSURE_NS = `
(function ensureMonacoNs() {
  if (window.__tvMonacoNs && window.__tvMonacoNs.editor) return true;
  var fiberPrefix = '__reactFiber' + '\x24'; // \x24 = $, avoids template interpolation
  var containers = document.querySelectorAll('.monaco-editor');
  for (var ci = 0; ci < containers.length; ci++) {
    var c = containers[ci];
    if (!c.offsetParent) continue;
    var el = c;
    var fk = null;
    for (var i = 0; i < 20; i++) {
      if (!el) break;
      var keys = Object.keys(el);
      for (var ki = 0; ki < keys.length; ki++) {
        if (keys[ki].indexOf(fiberPrefix) === 0) { fk = keys[ki]; break; }
      }
      if (fk) break;
      el = el.parentElement;
    }
    if (!fk) continue;
    var cur = el[fk];
    for (var d = 0; d < 40; d++) {
      if (!cur) break;
      if (cur.memoizedProps && cur.memoizedProps.value && cur.memoizedProps.value.monacoEnv) {
        var env = cur.memoizedProps.value.monacoEnv;
        if (env && env.editor && typeof env.editor.getModels === 'function') {
          var mods = env.editor.getModels();
          if (mods && mods.length > 0) { window.__tvMonacoNs = env; return true; }
        }
      }
      cur = cur.return;
    }
  }
  return false;
})()`;

// Returns true if Monaco is ready (namespace cached + models available)
const FIND_MONACO = `(function() {
  var ok = ${ENSURE_NS};
  if (!ok) return null;
  var ns = window.__tvMonacoNs;
  if (!ns || !ns.editor) return null;
  var mods = ns.editor.getModels();
  return (mods && mods.length > 0) ? true : null;
})()`;

// Returns the source string from Monaco model[0]
const GET_SOURCE = `(function() {
  if (!window.__tvMonacoNs || !window.__tvMonacoNs.editor) return null;
  var mods = window.__tvMonacoNs.editor.getModels();
  return (mods && mods.length > 0) ? mods[0].getValue() : null;
})()`;

// Returns serializable error markers array
const GET_MARKERS = `(function() {
  if (!window.__tvMonacoNs || !window.__tvMonacoNs.editor) return [];
  var mods = window.__tvMonacoNs.editor.getModels();
  if (!mods || mods.length === 0) return [];
  var markers = window.__tvMonacoNs.editor.getModelMarkers({ resource: mods[0].uri });
  return (markers || []).map(function(mk) {
    return { line: mk.startLineNumber, column: mk.startColumn, message: mk.message, severity: mk.severity };
  });
})()`;

// SET_SOURCE helper factory — returns JS string that sets source and returns boolean
function makeSetSourceExpr(escaped) {
  return `(function() {
  if (!window.__tvMonacoNs || !window.__tvMonacoNs.editor) return false;
  var mods = window.__tvMonacoNs.editor.getModels();
  if (!mods || mods.length === 0) return false;
  var model = mods[0];
  var orig = null;
  if (model._onDidChangeContent && model._onDidChangeContent.fire) {
    orig = model._onDidChangeContent.fire;
    model._onDidChangeContent.fire = function() {};
  } else if (model._eventEmitter) {
    orig = model._eventEmitter.fire;
    model._eventEmitter.fire = function() {};
  }
  model.setValue(${escaped});
  if (orig) {
    setTimeout(function() {
      if (model._onDidChangeContent) model._onDidChangeContent.fire = orig;
      else if (model._eventEmitter) model._eventEmitter.fire = orig;
    }, 10);
  }
  return true;
})()`;
}

// TradingView internal API preamble
const TV_API_PREAMBLE = `
var api = null;
try {
  if (window.TradingViewApi) api = window.TradingViewApi;
  else if (window.TradingView && window.TradingView.api) api = window.TradingView.api;
} catch(_) {}
var chart = null;
try {
  if (api && typeof api.activeChart === 'function') chart = api.activeChart();
  else if (api && api._activeChartWidgetWV && typeof api._activeChartWidgetWV.value === 'function')
    chart = api._activeChartWidgetWV.value();
} catch(_) {}
`;

/**
 * Opens the Pine Editor panel and waits for Monaco to become available.
 * Uses trusted CDP mouse event (not DOM .click()) so React handlers fire correctly.
 * Returns true if editor is accessible, false on timeout.
 */
export async function ensurePineEditorOpen() {
  const already = await evaluate(`(function() { return ${FIND_MONACO} !== null; })()`);
  if (already) return true;

  // Step 1: Try bottomWidgetBar internal API
  await evaluate(`
    (function() {
      var bwb = window.TradingView && window.TradingView.bottomWidgetBar;
      if (!bwb) return;
      if (typeof bwb.activateScriptEditorTab === 'function') bwb.activateScriptEditorTab();
      else if (typeof bwb.showWidget === 'function') bwb.showWidget('pine-editor');
      else if (typeof bwb.activateWidget === 'function') bwb.activateWidget('pine_logs');
    })()
  `);

  // Step 2: Locate Pine toggle button and click via trusted CDP mouse event
  const btnCoords = await evaluate(`
    (function() {
      var btn = document.querySelector('button[data-name="pine-dialog-button"]')
             || document.querySelector('button[aria-label="Pine"]');
      if (!btn) {
        var allBtns = document.querySelectorAll('[role="toolbar"] button, [class*="toolbar"] button');
        for (var i = 0; i < allBtns.length; i++) {
          if ((allBtns[i].textContent || '').trim() === 'Pine') { btn = allBtns[i]; break; }
        }
      }
      if (!btn) return null;
      var r = btn.getBoundingClientRect();
      return { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) };
    })()
  `);

  if (btnCoords) {
    const c = await getClient();
    const { x, y } = btnCoords;
    await c.Input.dispatchMouseEvent({ type: 'mouseMoved', x, y, button: 'none' });
    await new Promise(r => setTimeout(r, 100));
    await c.Input.dispatchMouseEvent({ type: 'mousePressed', x, y, button: 'left', clickCount: 1, buttons: 1 });
    await new Promise(r => setTimeout(r, 100));
    await c.Input.dispatchMouseEvent({ type: 'mouseReleased', x, y, button: 'left', clickCount: 1, buttons: 0 });
  }

  // Poll for Monaco (up to 10s)
  for (let i = 0; i < 50; i++) {
    await new Promise(r => setTimeout(r, 200));
    const ready = await evaluate(`(function() { return ${FIND_MONACO} !== null; })()`);
    if (ready) return true;
  }
  return false;
}

/**
 * Focus the Monaco textarea so it receives CDP keyboard shortcuts.
 */
async function focusMonacoEditor() {
  await evaluate(`
    (function() {
      var el = document.querySelector('.monaco-editor textarea.inputarea')
            || document.querySelector('.monaco-editor');
      if (el) el.focus();
    })()
  `);
  await new Promise(r => setTimeout(r, 150));
}

/**
 * Save chart layout silently after a study is added so it persists across restarts.
 * Non-fatal — best effort only.
 */
async function saveChartSilently() {
  try {
    await evaluateAsync(`
      (function() {
        ${TV_API_PREAMBLE}
        if (!api) return Promise.resolve('no_api');
        var svc = typeof api.getSaveChartService === 'function' ? api.getSaveChartService() : null;
        if (!svc || typeof svc.saveChartSilently !== 'function') return Promise.resolve('no_svc');
        return Promise.resolve(svc.saveChartSilently(undefined, undefined, {}));
      })()
    `);
  } catch(_) { /* non-fatal */ }
}

// ── Pure / offline functions ──

export function analyze({ source }) {
  const lines = source.split('\n');
  const diagnostics = [];

  let isV6 = false;
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith('//@version=6')) { isV6 = true; break; }
    if (trimmed.startsWith('//@version=')) break;
    if (trimmed === '' || trimmed.startsWith('//')) continue;
    break;
  }

  const arrays = new Map();
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const fromMatch = line.match(/(\w+)\s*=\s*array\.from\(([^)]*)\)/);
    if (fromMatch) {
      const name = fromMatch[1].trim();
      const args = fromMatch[2].trim();
      const size = args === '' ? 0 : args.split(',').length;
      arrays.set(name, { name, size, line: i + 1 });
      continue;
    }
    const newMatch = line.match(/(\w+)\s*=\s*array\.new(?:<\w+>|_\w+)\((\d+)?/);
    if (newMatch) {
      const name = newMatch[1].trim();
      const size = newMatch[2] !== undefined ? parseInt(newMatch[2], 10) : null;
      arrays.set(name, { name, size, line: i + 1 });
    }
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const pattern = /array\.(get|set)\(\s*(\w+)\s*,\s*(-?\d+)/g;
    let match;
    while ((match = pattern.exec(line)) !== null) {
      const method = match[1];
      const arrName = match[2];
      const idx = parseInt(match[3], 10);
      const info = arrays.get(arrName);
      if (!info || info.size === null) continue;
      if (idx < 0 || idx >= info.size) {
        diagnostics.push({
          line: i + 1, column: match.index + 1,
          message: `array.${method}(${arrName}, ${idx}) — index ${idx} out of bounds (array size is ${info.size})`,
          severity: 'error',
        });
      }
    }
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const firstLastPattern = /(\w+)\.(first|last)\(\)/g;
    let match;
    while ((match = firstLastPattern.exec(line)) !== null) {
      const arrName = match[1];
      if (arrName === 'array') continue;
      const info = arrays.get(arrName);
      if (info && info.size === 0) {
        diagnostics.push({
          line: i + 1, column: match.index + 1,
          message: `${arrName}.${match[2]}() called on possibly empty array (declared with size 0)`,
          severity: 'warning',
        });
      }
    }
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();
    if (trimmed.includes('strategy.entry') || trimmed.includes('strategy.close')) {
      let hasStrategyDecl = false;
      for (const l of lines) {
        if (l.trim().startsWith('strategy(')) { hasStrategyDecl = true; break; }
      }
      if (!hasStrategyDecl) {
        diagnostics.push({
          line: i + 1, column: 1,
          message: 'strategy.entry/close used but no strategy() declaration found — did you mean to use indicator()?',
          severity: 'error',
        });
        break;
      }
    }
  }

  if (!isV6 && source.includes('//@version=')) {
    const vMatch = source.match(/\/\/@version=(\d+)/);
    if (vMatch && parseInt(vMatch[1]) < 5) {
      diagnostics.push({
        line: 1, column: 1,
        message: `Script uses Pine v${vMatch[1]} — consider upgrading to v6 for latest features`,
        severity: 'info',
      });
    }
  }

  return {
    success: true,
    issue_count: diagnostics.length,
    diagnostics,
    note: diagnostics.length === 0 ? 'No static analysis issues found. Use pine_compile or pine_smart_compile for full server-side compilation check.' : undefined,
  };
}

export async function check({ source }) {
  const formData = new URLSearchParams();
  formData.append('source', source);

  const response = await fetch(
    'https://pine-facade.tradingview.com/pine-facade/translate_light?user_name=Guest&pine_id=00000000-0000-0000-0000-000000000000',
    {
      method: 'POST',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Referer': 'https://www.tradingview.com/',
      },
      body: formData,
    }
  );

  if (!response.ok) {
    throw new Error(`TradingView API returned ${response.status}: ${response.statusText}`);
  }

  const result = await response.json();
  const errors = [];
  const warnings = [];
  const inner = result?.result;

  if (inner) {
    if (inner.errors2 && inner.errors2.length > 0) {
      for (const e of inner.errors2) {
        errors.push({
          line: e.start?.line, column: e.start?.column,
          end_line: e.end?.line, end_column: e.end?.column,
          message: e.message,
        });
      }
    }
    if (inner.warnings2 && inner.warnings2.length > 0) {
      for (const w of inner.warnings2) {
        warnings.push({ line: w.start?.line, column: w.start?.column, message: w.message });
      }
    }
  }

  if (result.error && typeof result.error === 'string') {
    errors.push({ message: result.error });
  }

  const compiled = errors.length === 0;
  return {
    success: true,
    compiled,
    error_count: errors.length,
    warning_count: warnings.length,
    errors: errors.length > 0 ? errors : undefined,
    warnings: warnings.length > 0 ? warnings : undefined,
    note: compiled ? 'Pine Script compiled successfully.' : undefined,
  };
}

// ── Functions requiring TradingView connection ──

export async function getSource() {
  const editorReady = await ensurePineEditorOpen();
  if (!editorReady) throw new Error('Could not open Pine Editor — Monaco not found.');

  const source = await evaluate(GET_SOURCE);

  if (source === null || source === undefined) throw new Error('Monaco found but getValue() returned null.');
  return { success: true, source, line_count: source.split('\n').length, char_count: source.length };
}

export async function setSource({ source }) {
  const editorReady = await ensurePineEditorOpen();
  if (!editorReady) throw new Error('Could not open Pine Editor.');

  const escaped = JSON.stringify(source);
  // Ensure Monaco is cached first
  await evaluate(ENSURE_NS);
  const set = await evaluate(makeSetSourceExpr(escaped));

  if (!set) throw new Error('Monaco found but setValue() failed — no models available.');
  return { success: true, lines_set: source.split('\n').length };
}

/**
 * Add current Pine script to chart using Ctrl+Enter (MaudeView-proven approach).
 * Focuses editor → Ctrl+Enter → polls for "Save and add to chart" dialog.
 */
export async function compile() {
  const editorReady = await ensurePineEditorOpen();
  if (!editorReady) throw new Error('Could not open Pine Editor.');

  await evaluate(`(function(){var s=document.querySelector('[class*="loadingScreen"]');if(s&&s.parentElement)s.parentElement.style.display='none';})()`);
  // Method 1: JS click the hidden "Add to chart" button (title attribute, works even when invisible)
  const jsClicked = await evaluate(`
    (function() {
      var btns = document.querySelectorAll('button');
      for (var i = 0; i < btns.length; i++) {
        if (btns[i].title === 'Add to chart') { btns[i].click(); return true; }
      }
      return false;
    })()
  `);

  if (jsClicked) {
    // Poll for "Save and add to chart" confirmation dialog
    for (let i = 0; i < 15; i++) {
      await new Promise(r => setTimeout(r, 200));
      const handled = await evaluate(`
        (function() {
          var btns = document.querySelectorAll('button');
          for (var i = 0; i < btns.length; i++) {
            if ((btns[i].textContent || '').trim() === 'Save and add to chart') { btns[i].click(); return true; }
          }
          return false;
        })()
      `);
      if (handled) { await new Promise(r => setTimeout(r, 2000)); return { success: true, method: 'js_click_hidden_btn', dialog_handled: true }; }
    }
    await new Promise(r => setTimeout(r, 1500));
    return { success: true, method: 'js_click_hidden_btn', dialog_handled: false };
  }

  // Method 2: Ctrl+Enter fallback
  await focusMonacoEditor();
  const c = await getClient();
  await c.Input.dispatchKeyEvent({ type: 'keyDown', modifiers: 2, key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 });
  await new Promise(r => setTimeout(r, 100));
  await c.Input.dispatchKeyEvent({ type: 'keyUp', modifiers: 0, key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 });

  let dialogHandled = false;
  for (let i = 0; i < 15; i++) {
    await new Promise(r => setTimeout(r, 200));
    dialogHandled = await evaluate(`
      (function() {
        var btns = document.querySelectorAll('button');
        for (var i = 0; i < btns.length; i++) {
          if ((btns[i].textContent || '').trim() === 'Save and add to chart') { btns[i].click(); return true; }
        }
        return false;
      })()
    `);
    if (dialogHandled) break;
  }

  await new Promise(r => setTimeout(r, dialogHandled ? 2000 : 1500));
  return { success: true, method: 'ctrl_enter', dialog_handled: dialogHandled };
}

export async function getErrors() {
  const editorReady = await ensurePineEditorOpen();
  if (!editorReady) throw new Error('Could not open Pine Editor.');

  const errors = await evaluate(GET_MARKERS);

  return { success: true, has_errors: errors?.length > 0, error_count: errors?.length || 0, errors: errors || [] };
}

export async function save() {
  const editorReady = await ensurePineEditorOpen();
  if (!editorReady) throw new Error('Could not open Pine Editor.');

  await focusMonacoEditor();
  const c = await getClient();
  await c.Input.dispatchKeyEvent({ type: 'keyDown', modifiers: 2, key: 's', code: 'KeyS', windowsVirtualKeyCode: 83 });
  await new Promise(r => setTimeout(r, 100));
  await c.Input.dispatchKeyEvent({ type: 'keyUp', modifiers: 0, key: 's', code: 'KeyS', windowsVirtualKeyCode: 83 });
  await new Promise(r => setTimeout(r, 800));

  // Handle "Save Script" name dialog for new/unsaved scripts
  const dialogHandled = await evaluate(`
    (function() {
      var btns = document.querySelectorAll('button');
      for (var i = 0; i < btns.length; i++) {
        if (btns[i].textContent.trim() === 'Save' && btns[i].offsetParent !== null) {
          var parent = btns[i].closest('[class*="dialog"], [class*="modal"], [class*="popup"], [role="dialog"]');
          if (parent) { btns[i].click(); return true; }
        }
      }
      return false;
    })()
  `);

  if (dialogHandled) await new Promise(r => setTimeout(r, 500));
  return { success: true, action: dialogHandled ? 'saved_with_dialog' : 'ctrl_s_dispatched' };
}

export async function getConsole() {
  const editorReady = await ensurePineEditorOpen();
  if (!editorReady) throw new Error('Could not open Pine Editor.');

  const entries = await evaluate(`
    (function() {
      var results = [];
      var rows = document.querySelectorAll('[class*="consoleRow"], [class*="log-"], [class*="consoleLine"]');
      if (rows.length === 0) {
        var bottomArea = document.querySelector('[class*="layout__area--bottom"]')
          || document.querySelector('[class*="bottom-widgetbar-content"]');
        if (bottomArea) {
          rows = bottomArea.querySelectorAll('[class*="message"], [class*="log"], [class*="console"]');
        }
      }
      if (rows.length === 0) {
        var pinePanel = document.querySelector('.pine-editor-container')
          || document.querySelector('[class*="pine-editor"]')
          || document.querySelector('[class*="layout__area--bottom"]');
        if (pinePanel) {
          var allSpans = pinePanel.querySelectorAll('span, div');
          for (var s = 0; s < allSpans.length; s++) {
            var txt = allSpans[s].textContent.trim();
            if (/^\\d{2}:\\d{2}:\\d{2}/.test(txt) || /error|warning|info/i.test(allSpans[s].className)) {
              rows = Array.from(rows || []);
              rows.push(allSpans[s]);
            }
          }
        }
      }
      for (var i = 0; i < rows.length; i++) {
        var text = rows[i].textContent.trim();
        if (!text) continue;
        var ts = null;
        var tsMatch = text.match(/^(\\d{4}-\\d{2}-\\d{2}\\s+)?\\d{2}:\\d{2}:\\d{2}/);
        if (tsMatch) ts = tsMatch[0];
        var type = 'info';
        var cls = rows[i].className || '';
        if (/error/i.test(cls) || /error/i.test(text.substring(0, 30))) type = 'error';
        else if (/compil/i.test(text.substring(0, 40))) type = 'compile';
        else if (/warn/i.test(cls)) type = 'warning';
        results.push({ timestamp: ts, type: type, message: text });
      }
      return results;
    })()
  `);

  return { success: true, entries: entries || [], entry_count: entries?.length || 0 };
}

/**
 * Smart compile: Ctrl+Enter → dialog poll → error check → study count diff → saveChartSilently.
 * This is the main entry point for adding a Pine script to chart.
 */
export async function smartCompile() {
  const editorReady = await ensurePineEditorOpen();
  if (!editorReady) throw new Error('Could not open Pine Editor.');

  const studiesBefore = await evaluate(`
    (function() {
      try {
        ${TV_API_PREAMBLE}
        if (chart && typeof chart.getAllStudies === 'function') return chart.getAllStudies().length;
      } catch(_) {}
      return null;
    })()
  `);

  await evaluate(`(function(){var s=document.querySelector('[class*="loadingScreen"]');if(s&&s.parentElement)s.parentElement.style.display='none';})()`);

  // Method 1: JS click hidden "Add to chart" button (title attr — works even when invisible)
  let addClicked = await evaluate(`
    (function() {
      var btns = document.querySelectorAll('button');
      for (var i = 0; i < btns.length; i++) {
        if (btns[i].title === 'Add to chart') { btns[i].click(); return true; }
      }
      return false;
    })()
  `);

  if (!addClicked) {
    // Method 2: Ctrl+Enter fallback
    await focusMonacoEditor();
    const c = await getClient();
    await c.Input.dispatchKeyEvent({ type: 'keyDown', modifiers: 2, key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 });
    await new Promise(r => setTimeout(r, 100));
    await c.Input.dispatchKeyEvent({ type: 'keyUp', modifiers: 0, key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13 });
  }

  // Poll for "Save and add to chart" dialog
  let dialogHandled = false;
  for (let i = 0; i < 15; i++) {
    await new Promise(r => setTimeout(r, 200));
    dialogHandled = await evaluate(`
      (function() {
        var btns = document.querySelectorAll('button');
        for (var i = 0; i < btns.length; i++) {
          if ((btns[i].textContent || '').trim() === 'Save and add to chart') { btns[i].click(); return true; }
        }
        return false;
      })()
    `);
    if (dialogHandled) break;
  }

  await new Promise(r => setTimeout(r, dialogHandled ? 2000 : 1500));

  // Check Monaco errors
  const errors = await evaluate(GET_MARKERS);

  const studiesAfter = await evaluate(`
    (function() {
      try {
        ${TV_API_PREAMBLE}
        if (chart && typeof chart.getAllStudies === 'function') return chart.getAllStudies().length;
      } catch(_) {}
      return null;
    })()
  `);

  const studyAdded = (studiesBefore !== null && studiesAfter !== null) ? studiesAfter > studiesBefore : null;

  // ── KEY FIX: save layout so new study persists across TV restarts ──
  if (studyAdded) await saveChartSilently();

  return {
    success: true,
    method: 'ctrl_enter',
    dialog_handled: dialogHandled,
    has_errors: errors?.length > 0,
    errors: errors || [],
    study_added: studyAdded,
    studies_before: studiesBefore,
    studies_after: studiesAfter,
    layout_saved: studyAdded === true,
  };
}

export async function newScript({ type }) {
  const editorReady = await ensurePineEditorOpen();
  if (!editorReady) throw new Error('Could not open Pine Editor.');

  const templates = {
    indicator: '//@version=6\nindicator("My script")\nplot(close)',
    strategy: '//@version=6\nstrategy("My strategy", overlay=true)\n',
    library: '//@version=6\n// @description TODO: add library description here\nlibrary("MyLibrary")\n',
  };
  const template = templates[type] || templates.indicator;
  const escaped = JSON.stringify(template);

  await evaluate(ENSURE_NS);
  const set = await evaluate(`(function() {
    if (!window.__tvMonacoNs || !window.__tvMonacoNs.editor) return false;
    var mods = window.__tvMonacoNs.editor.getModels();
    if (!mods || mods.length === 0) return false;
    mods[0].setValue(${escaped});
    return true;
  })()`);

  if (!set) throw new Error('Monaco editor not found. Ensure Pine Editor is open.');
  return { success: true, type, action: 'new_script_created' };
}

/**
 * Save current script under a new name — creates a genuine new TV cloud script slot.
 * Sequence: Ctrl+S → name dialog appears → clear + type name → click Save.
 * Use this instead of pine new when you need a second named indicator slot.
 */
export async function saveAs({ name }) {
  const editorReady = await ensurePineEditorOpen();
  if (!editorReady) throw new Error('Could not open Pine Editor.');

  await focusMonacoEditor();

  const c = await getClient();
  await c.Input.dispatchKeyEvent({ type: 'keyDown', modifiers: 2, key: 's', code: 'KeyS', windowsVirtualKeyCode: 83 });
  await new Promise(r => setTimeout(r, 100));
  await c.Input.dispatchKeyEvent({ type: 'keyUp', modifiers: 0, key: 's', code: 'KeyS', windowsVirtualKeyCode: 83 });
  await new Promise(r => setTimeout(r, 1000));

  const escapedName = JSON.stringify(name);
  const result = await evaluateAsync(`
    (async function() {
      var deadline = Date.now() + 3000;
      var inp = null;
      while (Date.now() < deadline) {
        var dlg = document.querySelector('[class*="dialog"], [role="dialog"], [class*="modal"]');
        if (dlg) {
          inp = dlg.querySelector('input[type="text"], input:not([type])');
          if (inp && inp.offsetParent !== null) break;
        }
        await new Promise(function(r) { setTimeout(r, 200); });
      }
      if (!inp) return { ok: false, error: 'Save name dialog not found' };
      inp.focus();
      inp.select();
      document.execCommand('selectAll', false, null);
      document.execCommand('insertText', false, ${escapedName});
      await new Promise(function(r) { setTimeout(r, 300); });
      var dlg2 = inp.closest('[class*="dialog"], [role="dialog"], [class*="modal"]');
      if (!dlg2) return { ok: false, error: 'Dialog container lost' };
      var btns = dlg2.querySelectorAll('button');
      var saveBtn = null;
      for (var i = 0; i < btns.length; i++) {
        var txt = btns[i].textContent.trim();
        if (txt === 'Save' || txt === 'OK' || txt === 'Confirm') { saveBtn = btns[i]; break; }
      }
      if (!saveBtn) return { ok: false, error: 'Save button not found in dialog' };
      saveBtn.click();
      await new Promise(function(r) { setTimeout(r, 1000); });
      return { ok: true };
    })()
  `);

  if (!result?.ok) throw new Error(result?.error || 'save-as dialog failed');
  return { success: true, name, action: 'saved_as_new_slot' };
}

/**
 * Open a new Pine editor tab via Shift+Alt+T.
 * Creates a genuine NEW script slot — does NOT overwrite the currently active slot.
 * Use this before pine set + pine compile to safely add a second indicator.
 */
export async function newTab() {
  const editorReady = await ensurePineEditorOpen();
  if (!editorReady) throw new Error('Could not open Pine Editor.');

  await focusMonacoEditor();

  // Shift+Alt+T (Shift=1, Alt=4 → combined modifier=5)
  const c = await getClient();
  await c.Input.dispatchKeyEvent({ type: 'keyDown', modifiers: 5, key: 'T', code: 'KeyT', windowsVirtualKeyCode: 84 });
  await new Promise(r => setTimeout(r, 100));
  await c.Input.dispatchKeyEvent({ type: 'keyUp', modifiers: 0, key: 'T', code: 'KeyT', windowsVirtualKeyCode: 84 });
  await new Promise(r => setTimeout(r, 1500));

  const ready = await evaluate(`(function() { return ${FIND_MONACO} !== null; })()`);
  return { success: true, action: 'new_tab_opened', monaco_ready: ready };
}

export async function openScript({ name }) {
  const editorReady = await ensurePineEditorOpen();
  if (!editorReady) throw new Error('Could not open Pine Editor.');

  const escapedName = JSON.stringify(name.toLowerCase());

  const result = await evaluateAsync(`
    (function() {
      var target = ${escapedName};
      return fetch('https://pine-facade.tradingview.com/pine-facade/list/?filter=saved', { credentials: 'include' })
        .then(function(r) { return r.json(); })
        .then(function(scripts) {
          if (!Array.isArray(scripts)) return {error: 'pine-facade returned unexpected data'};
          var match = null;
          for (var i = 0; i < scripts.length; i++) {
            var sn = (scripts[i].scriptName || '').toLowerCase();
            var st = (scripts[i].scriptTitle || '').toLowerCase();
            if (sn === target || st === target) { match = scripts[i]; break; }
          }
          if (!match) {
            for (var j = 0; j < scripts.length; j++) {
              var sn2 = (scripts[j].scriptName || '').toLowerCase();
              var st2 = (scripts[j].scriptTitle || '').toLowerCase();
              if (sn2.indexOf(target) !== -1 || st2.indexOf(target) !== -1) { match = scripts[j]; break; }
            }
          }
          if (!match) return {error: 'Script "' + target + '" not found. Use pine_list_scripts to see available scripts.'};

          var id = match.scriptIdPart;
          var ver = match.version || 1;
          return fetch('https://pine-facade.tradingview.com/pine-facade/get/' + id + '/' + ver, { credentials: 'include' })
            .then(function(r2) { return r2.json(); })
            .then(function(data) {
              var source = data.source || '';
              if (!source) return {error: 'Script source is empty', name: match.scriptName || match.scriptTitle};
              var ns = window.__tvMonacoNs;
              if (ns && ns.editor) {
                var mods = ns.editor.getModels();
                if (mods && mods.length > 0) {
                  mods[0].setValue(source);
                  return {success: true, name: match.scriptName || match.scriptTitle, id: id, lines: source.split('\\n').length};
                }
              }
              return {error: 'Monaco editor not found to inject source', name: match.scriptName || match.scriptTitle};
            });
        })
        .catch(function(e) { return {error: e.message}; });
    })()
  `);

  if (result?.error) {
    throw new Error(result.error);
  }

  return { success: true, name: result.name, script_id: result.id, lines: result.lines, source: 'internal_api', opened: true };
}

export async function listScripts() {
  const scripts = await evaluateAsync(`
    fetch('https://pine-facade.tradingview.com/pine-facade/list/?filter=saved', { credentials: 'include' })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (!Array.isArray(data)) return {scripts: [], error: 'Unexpected response from pine-facade'};
        return {
          scripts: data.map(function(s) {
            return {
              id: s.scriptIdPart || null,
              name: s.scriptName || s.scriptTitle || 'Untitled',
              title: s.scriptTitle || null,
              version: s.version || null,
              modified: s.modified || null,
            };
          })
        };
      })
      .catch(function(e) { return {scripts: [], error: e.message}; })
  `);

  return {
    success: true,
    scripts: scripts?.scripts || [],
    count: scripts?.scripts?.length || 0,
    source: 'internal_api',
    error: scripts?.error,
  };
}

// Purpose: content script that detects DeceptiForge trace markers pasted into AI input fields.
// Responsibilities: run only on monitored AI domains and only when policy is enabled and not
//   paused; observe explicit paste/beforeinput events on eligible editable fields (never password/
//   payment/hidden); match locally against the hashed trace registry; and report only a matched
//   trace id to the background worker. Never blocks paste, never mutates the page, never sends the
//   pasted text. Dependencies: pure lib modules + chrome.runtime messaging.
import type { PlasmoCSConfig } from 'plasmo';

import { classifyDestination, isMonitored } from '~lib/classify';
import { editorKind, shouldObserve, type TargetDescriptor } from '~lib/dom';
import { buildIndex, matchText, type TraceIndex } from '~lib/matcher';
import type { DetectionMessage, PolicyDoc, RegistryDoc } from '~lib/types';

// Static host allowlist for the supported AI surfaces. Organization-defined domains are still
// gated at runtime by the policy's monitored_domains; the manifest host permissions bound access.
export const config: PlasmoCSConfig = {
  matches: [
    'https://chatgpt.com/*',
    'https://chat.openai.com/*',
    'https://claude.ai/*',
    'https://gemini.google.com/*',
    'https://copilot.microsoft.com/*',
    'https://github.com/*',
  ],
  run_at: 'document_idle',
  all_frames: false,
};

interface RuntimeConfig {
  policy: PolicyDoc | null;
  registry: RegistryDoc | null;
  paused: boolean;
}

let index: TraceIndex | null = null;
let policy: PolicyDoc | null = null;
let active = false;
const recentTraces = new Map<string, number>(); // trace -> ts, for dedupe/debounce
const DEDUPE_WINDOW_MS = 3_000;

function describe(el: Element): TargetDescriptor {
  const input = el as HTMLInputElement;
  const html = el as HTMLElement;
  const hidden =
    html.offsetParent === null ||
    html.hidden ||
    getComputedStyle(html).display === 'none';
  return {
    tag: el.tagName.toLowerCase(),
    inputType: el.tagName.toLowerCase() === 'input' ? (input.type ?? 'text') : null,
    isContentEditable: (html as HTMLElement).isContentEditable === true,
    hidden,
    ariaHidden: html.getAttribute('aria-hidden') === 'true',
    autocomplete: html.getAttribute('autocomplete'),
  };
}

function debounced(trace: string): boolean {
  const now = Date.now();
  const last = recentTraces.get(trace);
  if (last && now - last < DEDUPE_WINDOW_MS) return true;
  recentTraces.set(trace, now);
  return false;
}

async function handlePaste(target: Element, text: string): Promise<void> {
  if (!active || !index || !policy || index.byToken.size === 0) return;
  const desc = describe(target);
  if (!shouldObserve(desc)) return; // password/payment/hidden/non-editable -> ignored
  const kind = editorKind(desc);
  if (kind === null) return;
  const match = await matchText(text, index);
  if (match === null) return; // no known marker -> no event, nothing leaves the page
  if (debounced(match.trace_id)) return;
  const host = location.hostname;
  const message: DetectionMessage = {
    kind: 'df_ai_paste_detection',
    version: 1,
    trace_id: match.trace_id,
    destination_domain: host,
    match_method: match.match_method,
    editor_kind: kind,
  };
  // Fire-and-forget; the background worker signs + reports or queues. Never block paste.
  void chrome.runtime.sendMessage(message);
  const classification = classifyDestination(host, policy.rules);
  if (policy.show_user_notification) {
    // Presentation-only: a minimal, non-defensive notice. No trace details are exposed to the page.
    console.info(
      `DeceptiForge: synthetic protected content detected paste to a ${classification} AI tool; ` +
        'only the trace id and destination classification were reported.',
    );
  }
}

function onPaste(event: ClipboardEvent): void {
  const text = event.clipboardData?.getData('text/plain') ?? '';
  const target = event.target as Element | null;
  if (target && text) void handlePaste(target, text);
}

function onBeforeInput(event: InputEvent): void {
  if (event.inputType !== 'insertFromPaste') return;
  const text = event.data ?? '';
  const target = event.target as Element | null;
  if (target && text) void handlePaste(target, text);
}

function attach(): void {
  document.addEventListener('paste', onPaste, true);
  document.addEventListener('beforeinput', onBeforeInput as EventListener, true);
}

function detach(): void {
  document.removeEventListener('paste', onPaste, true);
  document.removeEventListener('beforeinput', onBeforeInput as EventListener, true);
}

async function refresh(): Promise<void> {
  const cfg = (await chrome.runtime.sendMessage({ kind: 'df_get_config' })) as RuntimeConfig | null;
  policy = cfg?.policy ?? null;
  const host = location.hostname;
  const enabled =
    !!policy &&
    policy.enabled &&
    !cfg?.paused &&
    isMonitored(host, policy.monitored_domains);
  index = cfg?.registry ? buildIndex(cfg.registry) : null;
  if (enabled && !active) {
    active = true;
    attach();
  } else if (!enabled && active) {
    active = false;
    detach();
  }
}

// Re-check policy on load and when the SPA tab becomes visible again (handles SPA navigation and
// policy/pause changes without polling).
void refresh();
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') void refresh();
});
window.addEventListener('pagehide', detach);

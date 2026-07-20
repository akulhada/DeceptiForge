// Purpose: pure decisions about which fields the content script may observe.
// Responsibilities: describe a paste target as a minimal, serializable descriptor and decide
//   whether it is eligible — never password/payment/hidden fields, only editable AI-input surfaces.
//   Kept pure so it is testable without a DOM. The content script is a thin adapter over this.

export type EditorKind = 'input' | 'textarea' | 'contenteditable';

export interface TargetDescriptor {
  tag: string; // lowercase tag name
  inputType: string | null; // <input type>, lowercased
  isContentEditable: boolean;
  hidden: boolean; // display:none / hidden attr / offsetParent null
  ariaHidden: boolean;
  autocomplete: string | null;
}

const BLOCKED_INPUT_TYPES = new Set([
  'password',
  'hidden',
  'email', // treat structured credential-ish inputs conservatively
  'tel',
  'number',
]);

// Autocomplete tokens that indicate payment or credential fields — never observed.
const BLOCKED_AUTOCOMPLETE = ['cc-', 'current-password', 'new-password', 'one-time-code'];

export function editorKind(d: TargetDescriptor): EditorKind | null {
  if (d.isContentEditable) return 'contenteditable';
  if (d.tag === 'textarea') return 'textarea';
  if (d.tag === 'input') return 'input';
  return null;
}

export function shouldObserve(d: TargetDescriptor): boolean {
  if (d.hidden || d.ariaHidden) return false;
  const kind = editorKind(d);
  if (kind === null) return false;
  if (kind === 'input') {
    const type = (d.inputType ?? 'text').toLowerCase();
    if (BLOCKED_INPUT_TYPES.has(type)) return false;
  }
  const ac = (d.autocomplete ?? '').toLowerCase();
  if (BLOCKED_AUTOCOMPLETE.some((p) => ac.includes(p))) return false;
  return true;
}

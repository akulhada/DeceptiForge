// Purpose: verify field-eligibility decisions — password/payment/hidden ignored, editable AI
//   surfaces (input/textarea/contenteditable) observed.
import { describe, expect, it } from 'vitest';

import { editorKind, shouldObserve, type TargetDescriptor } from '../src/lib/dom';

function target(over: Partial<TargetDescriptor>): TargetDescriptor {
  return {
    tag: 'textarea',
    inputType: null,
    isContentEditable: false,
    hidden: false,
    ariaHidden: false,
    autocomplete: null,
    ...over,
  };
}

describe('shouldObserve', () => {
  it('observes a textarea', () => {
    expect(shouldObserve(target({ tag: 'textarea' }))).toBe(true);
  });

  it('observes a contenteditable div', () => {
    expect(shouldObserve(target({ tag: 'div', isContentEditable: true }))).toBe(true);
    expect(editorKind(target({ tag: 'div', isContentEditable: true }))).toBe('contenteditable');
  });

  it('ignores password fields', () => {
    expect(shouldObserve(target({ tag: 'input', inputType: 'password' }))).toBe(false);
  });

  it('ignores payment/credential autocomplete', () => {
    expect(shouldObserve(target({ tag: 'input', inputType: 'text', autocomplete: 'cc-number' }))).toBe(
      false,
    );
    expect(
      shouldObserve(target({ tag: 'input', inputType: 'text', autocomplete: 'current-password' })),
    ).toBe(false);
  });

  it('ignores hidden and aria-hidden fields', () => {
    expect(shouldObserve(target({ hidden: true }))).toBe(false);
    expect(shouldObserve(target({ ariaHidden: true }))).toBe(false);
  });

  it('ignores non-editable elements', () => {
    expect(shouldObserve(target({ tag: 'span' }))).toBe(false);
  });
});

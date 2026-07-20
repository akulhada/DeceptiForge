// Purpose: verify local destination classification and monitored-domain gating.
import { describe, expect, it } from 'vitest';

import { classifyDestination, eventTypeFor, isMonitored } from '../src/lib/classify';
import type { DomainRule } from '../src/lib/types';

const rules: DomainRule[] = [
  { domain: 'chatgpt.com', classification: 'shadow' },
  { domain: 'tenant.chatgpt.com', classification: 'approved' },
  { domain: 'copilot.microsoft.com', classification: 'approved' },
];

describe('classifyDestination', () => {
  it('approved vs shadow, longest match wins', () => {
    expect(classifyDestination('tenant.chatgpt.com', rules)).toBe('approved');
    expect(classifyDestination('chatgpt.com', rules)).toBe('shadow');
    expect(classifyDestination('www.chatgpt.com', rules)).toBe('shadow');
  });

  it('unknown when no rule matches', () => {
    expect(classifyDestination('some-consumer-ai.example', rules)).toBe('unknown');
  });
});

describe('isMonitored', () => {
  it('matches configured domains and subdomains only', () => {
    expect(isMonitored('chatgpt.com', ['chatgpt.com'])).toBe(true);
    expect(isMonitored('app.chatgpt.com', ['chatgpt.com'])).toBe(true);
    expect(isMonitored('example.com', ['chatgpt.com'])).toBe(false);
  });
});

describe('eventTypeFor', () => {
  it('maps classification to event type', () => {
    expect(eventTypeFor('approved')).toBe('approved_ai_paste_detected');
    expect(eventTypeFor('shadow')).toBe('shadow_ai_paste_detected');
    expect(eventTypeFor('unknown')).toBe('shadow_ai_paste_detected');
  });
});

// Purpose: verify strict message-schema validation and trusted-sender origin checks (blocks
//   malicious page spoofing).
import { describe, expect, it } from 'vitest';

import { isDetectionMessage, isTrustedSender } from '../src/lib/messaging';

describe('isDetectionMessage', () => {
  const valid = {
    kind: 'df_ai_paste_detection',
    version: 1,
    trace_id: 'DFAI-abc',
    destination_domain: 'chatgpt.com',
    match_method: 'exact',
    editor_kind: 'textarea',
  };

  it('accepts a well-formed message', () => {
    expect(isDetectionMessage(valid)).toBe(true);
  });

  it('rejects wrong kind, version, or extra-typed junk', () => {
    expect(isDetectionMessage({ ...valid, kind: 'evil' })).toBe(false);
    expect(isDetectionMessage({ ...valid, version: 2 })).toBe(false);
    expect(isDetectionMessage({ ...valid, match_method: 'sql' })).toBe(false);
    expect(isDetectionMessage('nope')).toBe(false);
    expect(isDetectionMessage(null)).toBe(false);
  });
});

describe('isTrustedSender', () => {
  it('accepts monitored origins only', () => {
    expect(isTrustedSender('https://chatgpt.com', ['chatgpt.com'])).toBe(true);
    expect(isTrustedSender('https://app.chatgpt.com', ['chatgpt.com'])).toBe(true);
  });

  it('rejects non-monitored or malformed origins', () => {
    expect(isTrustedSender('https://evil.example', ['chatgpt.com'])).toBe(false);
    expect(isTrustedSender(undefined, ['chatgpt.com'])).toBe(false);
    expect(isTrustedSender('not a url', ['chatgpt.com'])).toBe(false);
  });
});

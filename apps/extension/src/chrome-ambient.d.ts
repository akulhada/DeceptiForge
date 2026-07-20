// Purpose: minimal ambient typing for the subset of the Chromium extension API this sensor uses.
// Responsibilities: type storage.local, runtime messaging, alarms, and the manifest accessor so the
//   source typechecks under strict mode without pulling a full @types/chrome dependency. This is a
//   narrow surface — extend only when the extension genuinely uses more.
declare namespace chrome {
  namespace runtime {
    interface MessageSender {
      origin?: string;
      url?: string;
    }
    function getManifest(): { version: string };
    function sendMessage(message: unknown): Promise<unknown>;
    const onMessage: {
      addListener(
        cb: (
          message: unknown,
          sender: MessageSender,
          sendResponse: (response?: unknown) => void,
        ) => boolean | void,
      ): void;
    };
    const onInstalled: { addListener(cb: () => void): void };
  }
  namespace storage {
    interface Area {
      get(keys: string[]): Promise<Record<string, unknown>>;
      set(items: Record<string, unknown>): Promise<void>;
      remove(keys: string[]): Promise<void>;
    }
    const local: Area;
  }
  namespace alarms {
    interface Alarm {
      name: string;
    }
    function create(name: string, info: { when?: number; periodInMinutes?: number }): void;
    const onAlarm: { addListener(cb: (alarm: Alarm) => void): void };
  }
}

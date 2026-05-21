declare global {
  interface Window {
    overlord?: {
      backendUrl: () => Promise<string>;
      openExternal: (url: string) => Promise<void>;
      platform?: () => Promise<{
        os: NodeJS.Platform;
        arch: string;
        version: string;
        isPackaged: boolean;
        isSetupDone: boolean;
      }>;
      autoStart?: {
        get: () => Promise<boolean>;
        set: (enabled: boolean) => Promise<boolean>;
      };
      envKeys?: () => Promise<Record<string, string>>;
    };
  }
}

export {};

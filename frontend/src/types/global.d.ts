declare global {
  interface Window {
    overlord?: {
      backendUrl: () => Promise<string>;
      openExternal: (url: string) => Promise<void>;
    };
  }
}

export {};

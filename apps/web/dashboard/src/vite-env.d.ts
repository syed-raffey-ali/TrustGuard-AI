/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the TrustGuard gateway, e.g. http://localhost:8080 */
  readonly VITE_GATEWAY_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

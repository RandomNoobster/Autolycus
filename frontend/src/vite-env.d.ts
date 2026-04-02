/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string;
  /** Seconds; must match API TOKEN_MAX_AGE_SEC when overriding token lifetime */
  readonly VITE_TOKEN_MAX_AGE_SEC?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

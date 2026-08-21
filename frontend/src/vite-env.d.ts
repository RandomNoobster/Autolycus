/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string;
  /** Public site origin for link previews (og:image, canonical); no trailing slash. Injected into index.html at build time. */
  readonly VITE_SITE_ORIGIN?: string;
  /** Seconds; must match API TOKEN_MAX_AGE_SEC when overriding token lifetime */
  readonly VITE_TOKEN_MAX_AGE_SEC?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

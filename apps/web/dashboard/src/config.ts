/** Gateway base URL, overridable via VITE_GATEWAY_URL at build time. */
function defaultGateway(): string {
  if (typeof window !== 'undefined' && window.location?.hostname) {
    const host = window.location.hostname;
    const { protocol, port } = window.location;
    // Served from a standard port (80/443) — the gateway is behind the same
    // origin (reverse proxy), so use it as-is.
    if (!port || port === '80' || port === '443') {
      return `${protocol}//${host}`;
    }
    // Any other port (Vite dev on 5173, gateway-served on 8080, …) — the
    // gateway listens on 8080 on this host. Never the dashboard's own port.
    return `${protocol}//${host}:8080`;
  }
  return 'http://localhost:8080';
}

const configured = (import.meta.env.VITE_GATEWAY_URL ?? '').trim();

export const GATEWAY_URL: string = (configured || defaultGateway()).replace(/\/+$/, '');

/** WebSocket base derived from the HTTP base (http->ws, https->wss). */
export const WS_BASE: string = GATEWAY_URL.replace(/^http/i, 'ws');

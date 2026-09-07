import { useEffect, useRef, useState } from 'react';
import type { SocketStatus } from './types';

const BASE_DELAY_MS = 600;
const MAX_DELAY_MS = 15000;
const MAX_EXPONENT = 5;

/**
 * WebSocket wrapper with auto-reconnect and exponential backoff + jitter.
 * Reconnects forever until stop() is called; onOpen fires again after each
 * successful reconnect so registration messages can be re-sent.
 */
export class ReconnectingSocket {
  private ws: WebSocket | null = null;
  private attempts = 0;
  private stopped = false;
  private timer: number | null = null;

  constructor(
    private readonly url: string,
    private readonly handlers: {
      onMessage: (data: unknown, ev: MessageEvent) => void;
      onStatus?: (status: SocketStatus) => void;
      onOpen?: (socket: ReconnectingSocket) => void;
    },
  ) {}

  start(): void {
    this.stopped = false;
    this.connect();
  }

  send(message: unknown): boolean {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
      return true;
    }
    return false;
  }

  stop(): void {
    this.stopped = true;
    if (this.timer != null) window.clearTimeout(this.timer);
    this.timer = null;
    if (this.ws) {
      const ws = this.ws;
      this.ws = null;
      ws.onopen = null;
      ws.onmessage = null;
      ws.onerror = null;
      ws.onclose = null;
      try {
        ws.close();
      } catch {
        /* already closing */
      }
    }
    this.handlers.onStatus?.('closed');
  }

  private connect(): void {
    if (this.stopped) return;
    if (this.timer != null) window.clearTimeout(this.timer);
    this.timer = null;
    this.handlers.onStatus?.(this.attempts === 0 ? 'connecting' : 'retrying');

    let ws: WebSocket;
    try {
      ws = new WebSocket(this.url);
    } catch {
      this.scheduleReconnect();
      return;
    }
    this.ws = ws;

    ws.onopen = () => {
      this.attempts = 0;
      this.handlers.onStatus?.('open');
      this.handlers.onOpen?.(this);
    };
    ws.onmessage = (ev: MessageEvent) => {
      let payload: unknown = ev.data;
      try {
        payload = JSON.parse(String(ev.data));
      } catch {
        /* keep raw payload */
      }
      this.handlers.onMessage(payload, ev);
    };
    ws.onerror = () => {
      /* onclose always follows an error */
    };
    ws.onclose = () => {
      if (this.ws === ws) this.ws = null;
      if (this.stopped) {
        this.handlers.onStatus?.('closed');
        return;
      }
      this.scheduleReconnect();
    };
  }

  private scheduleReconnect(): void {
    if (this.stopped) return;
    const expo = BASE_DELAY_MS * 2 ** Math.min(this.attempts, MAX_EXPONENT);
    const delay = Math.min(MAX_DELAY_MS, expo * (0.7 + Math.random() * 0.6));
    this.attempts += 1;
    this.handlers.onStatus?.('retrying');
    this.timer = window.setTimeout(() => this.connect(), delay);
  }
}

export interface SocketHandlers {
  onMessage: (data: unknown) => void;
  /** Called on every (re)connect; use for register handshakes. */
  onOpen?: (socket: ReconnectingSocket) => void;
}

/** React hook: opens a gateway websocket for `url` (null disables it). */
export function useGatewaySocket(url: string | null, handlers: SocketHandlers): SocketStatus {
  const [status, setStatus] = useState<SocketStatus>('closed');
  // Keep latest handlers in a ref so changing callbacks never reconnects the socket.
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;

  useEffect(() => {
    if (!url) {
      setStatus('closed');
      return;
    }
    const sock = new ReconnectingSocket(url, {
      onMessage: (data) => handlersRef.current.onMessage(data),
      onOpen: (socket) => handlersRef.current.onOpen?.(socket),
      onStatus: setStatus,
    });
    sock.start();
    return () => {
      sock.stop();
    };
  }, [url]);

  return status;
}

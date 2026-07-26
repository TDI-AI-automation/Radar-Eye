import { tokenStore } from "../auth/tokenStore";

export type WsChannel = "threats" | "incidents" | "camera_health" | "reviews" | "alarms";

/** apps/api/app/websockets/routes.py's actual paths -- camera_health's
 * URL segment uses a hyphen, unlike its channel name. */
const CHANNEL_PATH: Record<WsChannel, string> = {
  threats: "threats",
  incidents: "incidents",
  camera_health: "camera-health",
  reviews: "reviews",
  alarms: "alarms",
};

const wsBaseUrl = import.meta.env.VITE_WS_BASE_URL ?? "ws://localhost:8000";

const MAX_RECONNECT_DELAY_MS = 30_000;
const BASE_RECONNECT_DELAY_MS = 1_000;

type MessageHandler = (message: unknown) => void;

/**
 * One persistent connection per channel, shared by every subscriber
 * (mirrors the backend's own "one EventBus subscription per event type,
 * not per connection" design, apps/api/app/websockets/bridge.py). Opens
 * lazily on first subscribe, closes when the last subscriber leaves.
 *
 * Auth: the backend validates `?token=` at handshake and closes with 1008
 * on missing/invalid tokens (routes.py::_authenticate) -- there is no
 * mid-connection re-auth. This class reacts to tokenStore changes: a new
 * token (login, or proactive refresh) doesn't need to reopen an already-
 * open connection (the token was only checked once, at handshake); a
 * cleared token (logout, forced logout on 401) closes the connection
 * immediately rather than leaving a stale authenticated stream open on a
 * shared operator workstation.
 */
class ChannelConnection {
  private socket: WebSocket | null = null;
  private reconnectAttempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private readonly handlers = new Set<MessageHandler>();

  constructor(private readonly channel: WsChannel) {
    tokenStore.subscribe(() => {
      if (!tokenStore.getAccessToken()) {
        this.socket?.close();
        return;
      }
      if (!this.socket && this.handlers.size > 0) this.open();
    });
  }

  subscribe(handler: MessageHandler): () => void {
    this.handlers.add(handler);
    if (!this.socket) this.open();
    return () => {
      this.handlers.delete(handler);
      if (this.handlers.size === 0) this.close();
    };
  }

  private open(): void {
    const token = tokenStore.getAccessToken();
    if (!token) return; // tokenStore.subscribe() above retries once one appears

    const url = `${wsBaseUrl}/ws/${CHANNEL_PATH[this.channel]}?token=${encodeURIComponent(token)}`;
    const socket = new WebSocket(url);

    socket.onopen = () => {
      this.reconnectAttempt = 0;
    };
    socket.onmessage = (event: MessageEvent<string>) => {
      let parsed: unknown;
      try {
        parsed = JSON.parse(event.data);
      } catch {
        return;
      }
      for (const handler of this.handlers) handler(parsed);
    };
    socket.onclose = () => {
      if (this.socket === socket) this.socket = null;
      if (this.handlers.size > 0) this.scheduleReconnect();
    };
    socket.onerror = () => socket.close();

    this.socket = socket;
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer) return;
    const delay = Math.min(
      BASE_RECONNECT_DELAY_MS * 2 ** this.reconnectAttempt,
      MAX_RECONNECT_DELAY_MS,
    );
    this.reconnectAttempt += 1;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      if (this.handlers.size > 0) this.open();
    }, delay);
  }

  private close(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.socket?.close();
    this.socket = null;
  }
}

const connections = new Map<WsChannel, ChannelConnection>();

function getConnection(channel: WsChannel): ChannelConnection {
  let connection = connections.get(channel);
  if (!connection) {
    connection = new ChannelConnection(channel);
    connections.set(channel, connection);
  }
  return connection;
}

/**
 * Subscribes to a channel's broadcast messages. Returns an unsubscribe
 * function -- call it on unmount (e.g. from a `useEffect` cleanup in a
 * Phase 2/3 query hook that writes messages into the TanStack Query
 * cache per docs/FRONTEND_ARCHITECTURE.md §5). SSR-safe no-op: this
 * module only ever runs a real connection on the client.
 */
export function subscribeToChannel(channel: WsChannel, handler: MessageHandler): () => void {
  if (typeof WebSocket === "undefined") return () => {};
  return getConnection(channel).subscribe(handler);
}

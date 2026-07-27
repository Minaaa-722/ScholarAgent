import { useEffect, useRef, useCallback, useState } from "react";

const API_BASE = "http://localhost:8000";

interface WebSocketOptions {
  taskId?: string;
  onMessage: (data: any) => void;
  enabled?: boolean;
}

export function useWebSocket({ taskId = "current", onMessage, enabled = true }: WebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const attemptRef = useRef(0);
  const [connected, setConnected] = useState(false);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  const connect = useCallback(() => {
    if (!enabled) return;
    attemptRef.current += 1;
    const ws = new WebSocket(`${API_BASE.replace("http", "ws")}/ws/stream/${taskId}`);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      attemptRef.current = 0;
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onMessageRef.current(data);
      } catch { /* ignore parse errors */ }
    };

    ws.onclose = () => {
      setConnected(false);
      wsRef.current = null;
      const delay = Math.min(2000 * Math.pow(2, attemptRef.current - 1), 30000);
      reconnectTimerRef.current = setTimeout(connect, delay);
    };

    ws.onerror = () => { ws.close(); };
  }, [taskId, enabled]);

  const disconnect = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    attemptRef.current = 0;
    setConnected(false);
  }, []);

  useEffect(() => {
    connect();
    return () => disconnect();
  }, [connect, disconnect]);

  return { connected, disconnect };
}
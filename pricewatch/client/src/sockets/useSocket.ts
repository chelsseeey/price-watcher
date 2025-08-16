import { useEffect, useRef, useState } from "react";

/**
 * 서버가 Socket.IO라면 네이티브 WS로는 연결이 안 될 수 있어요.
 * UI 확인용으로 실패해도 조용히 무시하고 메시지 없이 동작합니다.
 */
export function useSocket() {
  const wsRef = useRef<WebSocket|null>(null);
  const [messages, setMessages] = useState<any[]>([]);

  useEffect(() => {
    try {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const url = `${proto}://${location.host}/ws`;
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => setMessages(m=>[...m, { type:"info", msg:"ws connected" }]);
      ws.onmessage = (ev) => {
        try { setMessages(m=>[...m, JSON.parse(ev.data)]); }
        catch { setMessages(m=>[...m, { type:"raw", data:String(ev.data) }]); }
      };
      ws.onclose = () => setMessages(m=>[...m, { type:"info", msg:"ws closed" }]);
      ws.onerror = () => setMessages(m=>[...m, { type:"error", msg:"ws error" }]);

      return () => { try { ws.close(); } catch {} };
    } catch {
      // 연결 실패해도 UI는 유지
      return () => {};
    }
  }, []);

  return { socket: wsRef.current, messages };
}

import { useSocket } from "../sockets/useSocket";

export default function LiveCharts() {
  const { messages } = useSocket();
  return (
    <section>
      <h3>실시간 메시지</h3>
      <div style={{ border:"1px solid #eee", borderRadius:8, padding:10, maxHeight:260, overflow:"auto" }}>
        {messages.map((m,i)=>(
          <pre key={i} style={{ margin:0, padding:8, background:"#fafafa", borderRadius:6 }}>
            {JSON.stringify(m, null, 2)}
          </pre>
        ))}
        {!messages.length && <p style={{ color:"#888" }}>대기 중…</p>}
      </div>
    </section>
  );
}

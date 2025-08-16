import { useEffect, useState } from "react";
import { listRuns } from "../api/runs";
import LiveCharts from "../components/LiveCharts";

export default function Runs() {
  const [rows, setRows] = useState<any[]>([]);
  useEffect(()=>{ listRuns().then(setRows); }, []);
  return (
    <div style={{ display:"grid", gap:18 }}>
      <section>
        <h3>실행 목록</h3>
        {rows.length === 0 ? (
          <p style={{ color:"#888" }}>데이터 없음 (서버 구현 필요)</p>
        ) : (
          <table style={{ width:"100%", borderCollapse:"collapse" }}>
            <thead><tr><Th>run_id</Th><Th>platform</Th><Th>status</Th></tr></thead>
            <tbody>{rows.map((r,i)=>(<tr key={i}><Td>{r.run_id}</Td><Td>{r.platform}</Td><Td>{r.status}</Td></tr>))}</tbody>
          </table>
        )}
      </section>
      <LiveCharts/>
    </div>
  );
}
function Th({children}:{children:React.ReactNode}){return <th style={{textAlign:"left",padding:8,borderBottom:"1px solid #eee"}}>{children}</th>;}
function Td({children}:{children:React.ReactNode}){return <td style={{padding:8,borderBottom:"1px solid #f5f5f5"}}>{children}</td>;}

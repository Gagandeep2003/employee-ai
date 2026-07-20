import React, { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { toast } from "sonner";
import { H1, Card, Search, Row, Th, Td, Btn, Pill, fmtDT } from "./_ui";

export default function Users() {
  const [items, setItems] = useState([]);
  const [q, setQ] = useState("");
  const load = () => api.get("/admin/users", { params: q ? { q } : {} }).then(({ data }) => setItems(data));
  useEffect(() => { const t = setTimeout(load, 300); return () => clearTimeout(t); }, [q]);

  const doAction = async (uid, action) => {
    if (action === "delete" && !window.confirm("Delete this user?")) return;
    try {
      await api.post(`/admin/users/${uid}/action`, { action });
      toast.success(action);
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Failed"); }
  };

  return (
    <div className="p-6 md:p-8 space-y-4">
      <H1 eyebrow="Identity & access" title="User Management">
        <Search value={q} onChange={setQ} placeholder="Search name, email, id…" />
      </H1>
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-secondary/50"><tr>
              <Th>Email</Th><Th>Name</Th><Th>Role</Th><Th>Businesses</Th><Th>Referral</Th><Th>Joined</Th><Th>Status</Th><Th></Th>
            </tr></thead>
            <tbody>
              {items.map((u) => (
                <Row key={u.user_id}>
                  <Td className="font-mono text-xs">{u.email}</Td>
                  <Td>{u.name}</Td>
                  <Td><Pill tone={u.role === "admin" ? "accent" : "default"}>{u.role}</Pill></Td>
                  <Td>{u.business_count}</Td>
                  <Td className="font-mono text-[11px]">{u.referral_code}</Td>
                  <Td className="text-xs text-muted-foreground">{fmtDT(u.created_at)}</Td>
                  <Td>{u.disabled ? <Pill tone="danger">disabled</Pill> : <Pill tone="ok">active</Pill>}</Td>
                  <Td className="text-right whitespace-nowrap space-x-1">
                    {u.disabled
                      ? <Btn onClick={() => doAction(u.user_id, "enable")}>Enable</Btn>
                      : <Btn variant="ghost" onClick={() => doAction(u.user_id, "disable")}>Disable</Btn>}
                    {u.role !== "admin"
                      ? <Btn variant="ghost" onClick={() => doAction(u.user_id, "make_admin")}>Make admin</Btn>
                      : <Btn variant="ghost" onClick={() => doAction(u.user_id, "make_owner")}>Demote</Btn>}
                    <Btn variant="danger" onClick={() => doAction(u.user_id, "delete")}>Delete</Btn>
                  </Td>
                </Row>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

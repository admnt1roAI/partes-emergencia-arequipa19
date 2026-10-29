import { useCallback, useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { supabase } from '../lib/supabase';

type Stats = {
  total_reports: number; this_month: number; total_victims: number; total_units: number; unique_firefighters: number;
  by_emergency: { label: string; count: number }[];
  by_district: { label: string; count: number }[];
  by_month: { label: string; count: number }[];
  by_firefighter?: { label: string; count: number }[];
  by_firefighter_emergency?: { firefighter: string; emergency_type: string; count: number }[];
};
type Company = { id: string; name: string; short_name: string; is_active: boolean };
type ManagedUser = {
  id: string; email: string; created_at: string; last_sign_in_at: string | null;
  profile: { user_id: string; company_id: string | null; role: string; full_name: string; is_active: boolean } | null;
};
type Report = { id: string; report_number: string; occurred_at: string; emergency_type: string; address: string; district: string; status: string; created_at: string; total_count: number };
type Catalog = { id: string; company_id: string; category: string; value: string; is_active: boolean };
type NumberConfig = { company_id: string; company_name: string; report_year: number; next_number: number; number_prefix: string; padding: number };
type Tab = 'resumen' | 'partes' | 'usuarios' | 'catalogos' | 'numeracion';

const roleLabels: Record<string, string> = {
  general_admin: 'Superadministrador', company_admin: 'Administrador de compañía', reporter: 'Usuario de registro', viewer: 'Consulta',
};

function downloadText(content: string, filename: string, mimeType: string) {
  const url = URL.createObjectURL(new Blob([content], { type: mimeType }));
  const link = document.createElement('a');
  link.href = url; link.download = filename;
  document.body.appendChild(link); link.click(); link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function SuperAdminConsole({ onNewReport, onSignOut }: { onNewReport: () => void; onSignOut: () => void }) {
  const [tab, setTab] = useState<Tab>('resumen');
  const [stats, setStats] = useState<Stats | null>(null);
  const [reports, setReports] = useState<Report[]>([]);
  const [query, setQuery] = useState('');
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [catalogs, setCatalogs] = useState<Catalog[]>([]);
  const [numberConfigs, setNumberConfigs] = useState<NumberConfig[]>([]);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [userDialog, setUserDialog] = useState<ManagedUser | 'new' | null>(null);
  const [catalogDialog, setCatalogDialog] = useState<Catalog | 'new' | null>(null);
  const [reportDetail, setReportDetail] = useState<Record<string, unknown> | null>(null);

  const loadStats = useCallback(async () => {
    if (!supabase) return;
    const { data, error: rpcError } = await supabase.rpc('admin_report_statistics');
    if (rpcError) throw rpcError;
    setStats(data as Stats);
  }, []);
  const loadReports = useCallback(async (text = query) => {
    if (!supabase) return;
    const { data, error: rpcError } = await supabase.rpc('admin_search_reports', { p_query: text, p_limit: 100, p_offset: 0 });
    if (rpcError) throw rpcError;
    setReports((data ?? []) as Report[]);
  }, [query]);
  const callUserAdmin = useCallback(async (payload: Record<string, unknown>) => {
    if (!supabase) throw new Error('No hay conexión con Supabase.');
    const { data, error: invokeError } = await supabase.functions.invoke('admin-users', { body: payload });
    if (invokeError) {
      let detail = invokeError.message;
      const context = (invokeError as Error & { context?: Response }).context;
      if (context && typeof context.json === 'function') {
        try {
          const body = await context.clone().json() as { error?: string; message?: string };
          detail = body.error || body.message || detail;
        } catch { /* Keep the SDK message when the response isn't JSON. */ }
      }
      throw new Error(detail);
    }
    if (data?.error) throw new Error(data.error);
    return data;
  }, []);
  const loadUsers = useCallback(async () => {
    const data = await callUserAdmin({ action: 'list' });
    setUsers(data.users as ManagedUser[]); setCompanies(data.companies as Company[]);
  }, [callUserAdmin]);
  const loadCatalogs = useCallback(async () => {
    if (!supabase) return;
    const { data, error: queryError } = await supabase.from('report_catalogs')
      .select('id, company_id, category, value, is_active').order('category').order('value');
    if (queryError) throw queryError;
    setCatalogs((data ?? []) as Catalog[]);
    if (companies.length === 0) {
      const { data: companyData, error: companyError } = await supabase.from('companies').select('id, name, short_name, is_active').order('short_name');
      if (companyError) throw companyError;
      setCompanies((companyData ?? []) as Company[]);
    }
  }, [companies.length]);
  const loadNumbering = useCallback(async () => {
    if (!supabase) return;
    const { data, error: rpcError } = await supabase.rpc('admin_get_numbering_configuration', {
      p_report_year: new Date().getFullYear(),
    });
    if (rpcError) throw rpcError;
    setNumberConfigs((data ?? []) as NumberConfig[]);
  }, []);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setBusy(true); setError('');
      try {
        if (tab === 'resumen') await loadStats();
        if (tab === 'partes') await loadReports('');
        if (tab === 'usuarios') await loadUsers();
        if (tab === 'catalogos') await loadCatalogs();
        if (tab === 'numeracion') await loadNumbering();
      } catch (reason) { if (active) setError(reason instanceof Error ? reason.message : 'No se pudieron cargar los datos.'); }
      finally { if (active) setBusy(false); }
    };
    void load();
    return () => { active = false; };
  }, [tab, loadStats, loadReports, loadUsers, loadCatalogs, loadNumbering]);

  const run = async (action: () => Promise<void>, success: string) => {
    setBusy(true); setError(''); setMessage('');
    try { await action(); setMessage(success); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'No se pudo completar la operación.'); }
    finally { setBusy(false); }
  };
  const openReport = async (report: Report) => {
    if (!supabase) return;
    await run(async () => {
      const childTables = ['report_victims', 'report_vehicles', 'report_units', 'report_personnel', 'report_support_vehicles', 'report_pnp_support'] as const;
      const [parent, ...children] = await Promise.all([
        supabase!.from('emergency_reports').select('*').eq('id', report.id).single(),
        ...childTables.map(table => supabase!.from(table).select('*').eq('report_id', report.id)),
      ]);
      if (parent.error) throw parent.error;
      for (const child of children) if (child.error) throw child.error;
      setReportDetail({ ...parent.data, victims: children[0].data, vehicles: children[1].data, units: children[2].data,
        personnel: children[3].data, supports: children[4].data, pnp_support: children[5].data });
    }, 'Parte cargado.');
  };
  const printReport = () => {
    if (!reportDetail) return;
    const escape = (value: unknown) => String(value ?? '').replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]!));
    const labels: Record<string, string> = { report_number: 'N.º de parte', occurred_at: 'Fecha y hora', emergency_type: 'Emergencia', codification: 'Codificación', address: 'Dirección', district: 'Distrito', work_description: 'Trabajo realizado', materials: 'Material utilizado', uniformed: 'Uniformidad', equipment_orderly: 'Material conforme', logbook_recorded: 'Bitácora', shift_operator: 'Centralista de turno', filled_by: 'Llenado por', observations: 'Observaciones', signature_name: 'Firma / conformidad' };
    const scalar = Object.entries(labels).map(([key, label]) => `<tr><th>${label}</th><td>${escape(reportDetail[key])}</td></tr>`).join('');
    const sections: [string, string][] = [['Víctimas', 'victims'], ['Vehículos involucrados', 'vehicles'], ['Unidades que asistieron', 'units'], ['Efectivos en servicio', 'personnel'], ['Vehículos de apoyo CGBVP', 'supports'], ['Apoyo PNP / otras instituciones', 'pnp_support']];
    const tables = sections.map(([title, key]) => {
      const rows = reportDetail[key] as Record<string, unknown>[] | null;
      if (!rows?.length) return '';
      return `<h2>${title}</h2><table>${rows.map(row => `<tr>${Object.entries(row).filter(([field]) => !['id', 'report_id', 'company_id', 'created_at'].includes(field)).map(([field, value]) => `<td><b>${escape(field.replaceAll('_', ' '))}:</b> ${escape(value)}</td>`).join('')}</tr>`).join('')}</table>`;
    }).join('');
    const windowRef = window.open('', '_blank');
    if (!windowRef) { setError('El navegador bloqueó la ventana de impresión. Permite ventanas emergentes para este sitio.'); return; }
    windowRef.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>Parte ${escape(reportDetail.report_number)}</title><style>body{font:14px Arial;color:#183b5c;margin:32px}h1{text-align:center;color:#174c7f}table{width:100%;border-collapse:collapse;margin:8px 0 18px}td,th{border:1px solid #bfd1e1;padding:7px;text-align:left}th{width:25%;background:#edf5fc}h2{color:#174c7f;font-size:16px;border-bottom:2px solid #bfd1e1;padding-bottom:5px}.sign{margin:50px auto 0;border-top:1px solid #123;width:280px;text-align:center;padding-top:6px}@media print{button{display:none}}</style></head><body><h1>PARTE DE EMERGENCIA</h1><table>${scalar}</table>${tables}<div class="sign">${escape(reportDetail.signature_name)}<br>Firma / conformidad</div><p><button onclick="window.print()">Imprimir / Guardar como PDF</button></p></body></html>`);
    windowRef.document.close();
  };
  const exportStatisticsCsv = () => {
    if (!stats) return;
    const rows: unknown[][] = [['Grupo', 'Dato', 'Cantidad'],
      ['Resumen', 'Total de emergencias', stats.total_reports], ['Resumen', 'Emergencias este mes', stats.this_month],
      ['Resumen', 'Víctimas registradas', stats.total_victims], ['Resumen', 'Unidades utilizadas', stats.total_units],
      ['Resumen', 'Bomberos distintos registrados', stats.unique_firefighters],
      ...stats.by_emergency.map(item => ['Emergencias por tipo', item.label, item.count]),
      ...stats.by_district.map(item => ['Emergencias por distrito', item.label, item.count]),
      ...stats.by_month.map(item => ['Emergencias por mes', item.label, item.count]),
      ...(stats.by_firefighter ?? []).map(item => ['Participación de bomberos', item.label, item.count]),
      ...(stats.by_firefighter_emergency ?? []).map(item => ['Bombero por tipo de emergencia', `${item.firefighter} · ${item.emergency_type}`, item.count]),
    ];
    const csv = `\uFEFF${rows.map(row => row.map(value => `"${String(value ?? '').replaceAll('"', '""')}"`).join(',')).join('\r\n')}`;
    downloadText(csv, `estadisticas-emergencias-${new Date().toISOString().slice(0, 10)}.csv`, 'text/csv;charset=utf-8');
  };
  const printStatistics = () => {
    if (!stats) return;
    const escape = (value: unknown) => String(value ?? '').replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]!));
    const rows = (title: string, values: { label: string; count: number }[]) => `<h2>${title}</h2><table><thead><tr><th>Dato</th><th>Emergencias</th></tr></thead><tbody>${values.map(item => `<tr><td>${escape(item.label)}</td><td>${item.count}</td></tr>`).join('')}</tbody></table>`;
    const personnel = `<h2>Bomberos por tipo de emergencia</h2><table><thead><tr><th>Bombero</th><th>Tipo de emergencia</th><th>Partes atendidos</th></tr></thead><tbody>${(stats.by_firefighter_emergency ?? []).map(item => `<tr><td>${escape(item.firefighter)}</td><td>${escape(item.emergency_type)}</td><td>${item.count}</td></tr>`).join('')}</tbody></table>`;
    const popup = window.open('', '_blank');
    if (!popup) { setError('El navegador bloqueó la ventana de impresión. Permite ventanas emergentes para este sitio.'); return; }
    popup.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>Estadísticas globales de emergencias</title><style>body{font:13px Arial;color:#183b5c;margin:28px}h1{color:#174c7f}h2{margin:22px 0 7px;color:#174c7f;font-size:16px}table{width:100%;border-collapse:collapse}th,td{padding:7px;border:1px solid #bfd1e1;text-align:left}th{background:#edf5fc}.summary{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.summary div{border:1px solid #bfd1e1;padding:10px;background:#f5f9fd}.actions{margin:18px 0}@media print{.actions{display:none}}</style></head><body><h1>Estadísticas globales de emergencias</h1><p>Generado: ${escape(new Date().toLocaleString())}</p><div class="summary"><div><b>Total de emergencias</b><br>${stats.total_reports}</div><div><b>Emergencias este mes</b><br>${stats.this_month}</div><div><b>Bomberos distintos</b><br>${stats.unique_firefighters}</div><div><b>Víctimas registradas</b><br>${stats.total_victims}</div><div><b>Unidades utilizadas</b><br>${stats.total_units}</div></div>${rows('Emergencias por tipo', stats.by_emergency)}${rows('Emergencias por distrito', stats.by_district)}${rows('Emergencias por mes', stats.by_month)}${rows('Bomberos con mayor participación', stats.by_firefighter ?? [])}${personnel}<div class="actions"><button onclick="window.print()">Imprimir / Guardar como PDF</button></div></body></html>`);
    popup.document.close();
  };
  const exportReportsCsv = () => {
    const rows: unknown[][] = [['N.º de parte', 'Fecha y hora', 'Emergencia', 'Dirección', 'Distrito', 'Estado'],
      ...reports.map(report => [report.report_number, new Date(report.occurred_at).toLocaleString(), report.emergency_type, report.address, report.district, report.status])];
    const csv = `\uFEFF${rows.map(row => row.map(value => `"${String(value ?? '').replaceAll('"', '""')}"`).join(',')).join('\r\n')}`;
    downloadText(csv, `partes-emergencia-${new Date().toISOString().slice(0, 10)}.csv`, 'text/csv;charset=utf-8');
  };
  const saveNumberConfig = async (config: NumberConfig) => {
    await run(async () => {
      const { error: rpcError } = await supabase!.rpc('admin_save_numbering_configuration', {
        p_company_id: config.company_id, p_report_year: config.report_year,
        p_next_number: Number(config.next_number), p_number_prefix: config.number_prefix,
        p_padding: Number(config.padding),
      });
      if (rpcError) throw rpcError;
      await loadNumbering();
    }, `Numeración guardada para ${config.company_name}.`);
  };

  return <main className="admin-console">
    <div className="admin-heading"><div><p className="eyebrow">AREQUIPA 19 · CONSOLA CENTRAL</p><h1>Panel de superadministración</h1><p className="muted">Administración del sistema web y datos alojados en Supabase.</p></div><div className="admin-actions"><button onClick={onNewReport}>＋ Nuevo parte</button><button onClick={onSignOut}>Cerrar sesión</button></div></div>
    <nav className="admin-tabs">{([['resumen', 'Resumen'], ['partes', 'Buscar partes'], ['usuarios', 'Usuarios y permisos'], ['catalogos', 'Datos desplegables'], ['numeracion', 'Numeración']] as [Tab, string][]).map(([key, label]) => <button key={key} className={tab === key ? 'selected' : ''} onClick={() => { setTab(key); setMessage(''); setError(''); }}>{label}</button>)}</nav>
    {message && <p className="success" role="status">{message}</p>}{error && <p className="error" role="alert">{error}</p>}{busy && <p className="muted">Cargando o procesando…</p>}
    {tab === 'resumen' && <>
      <div className="report-export-actions"><button onClick={exportStatisticsCsv} disabled={!stats}>Descargar estadísticas CSV</button><button onClick={printStatistics} disabled={!stats}>Imprimir / Guardar estadísticas PDF</button></div>
      <div className="stat-cards">{[['Total de emergencias atendidas', stats?.total_reports], ['Emergencias este mes', stats?.this_month], ['Víctimas registradas', stats?.total_victims], ['Unidades utilizadas', stats?.total_units], ['Bomberos distintos en servicio', stats?.unique_firefighters]].map(([label, value]) => <article className="stat-card" key={String(label)}><span>{label}</span><strong>{value ?? '—'}</strong></article>)}</div>
      <div className="chart-grid"><Chart title="Emergencias por tipo" rows={stats?.by_emergency ?? []} /><Chart title="Emergencias por distrito" rows={stats?.by_district ?? []} /><Chart title="Últimos 12 meses" rows={stats?.by_month ?? []} /><Chart title="Bomberos con mayor participación" rows={stats?.by_firefighter ?? []} /></div>
      <section className="admin-panel personnel-stat-panel"><h2>Emergencias atendidas por bombero y tipo</h2>{stats?.by_firefighter_emergency?.length ? <div className="table-scroll"><table className="admin-table"><thead><tr><th>Bombero</th><th>Tipo de emergencia</th><th>Partes atendidos</th></tr></thead><tbody>{stats.by_firefighter_emergency.map((item, index) => <tr key={`${item.firefighter}-${item.emergency_type}-${index}`}><td>{item.firefighter}</td><td>{item.emergency_type}</td><td>{item.count}</td></tr>)}</tbody></table></div> : <p className="muted">Sin registros de personal todavía.</p>}</section>
      <p className="small muted">Las estadísticas incluyen todos los registros de las compañías que existan en la base de datos y excluyen los partes retirados.</p>
    </>}
    {tab === 'partes' && <section className="admin-panel"><form className="admin-search" onSubmit={event => { event.preventDefault(); void run(() => loadReports(query), 'Búsqueda actualizada.'); }}><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Buscar por número, emergencia, dirección o distrito" /><button className="primary">Buscar</button><button type="button" onClick={() => { setQuery(''); void run(() => loadReports(''), 'Lista completa cargada.'); }}>Ver todos</button><button type="button" onClick={exportReportsCsv} disabled={!reports.length}>Descargar resultados CSV</button></form>
      <div className="table-scroll"><table className="admin-table"><thead><tr><th>N.º parte</th><th>Fecha</th><th>Emergencia</th><th>Distrito</th><th>Estado</th><th>Acciones</th></tr></thead><tbody>{reports.map(report => <tr key={report.id}><td>{report.report_number}</td><td>{new Date(report.occurred_at).toLocaleString()}</td><td>{report.emergency_type}</td><td>{report.district}</td><td>{report.status}</td><td><button onClick={() => void openReport(report)}>Ver / PDF</button>{report.status !== 'voided' && <button className="danger" onClick={() => { const reason = window.prompt(`Motivo para retirar el parte ${report.report_number}:`); if (reason?.trim()) void run(async () => { const { error: rpcError } = await supabase!.rpc('admin_void_emergency_report', { p_report_id: report.id, p_reason: reason.trim() }); if (rpcError) throw rpcError; await loadReports(); await loadStats(); }, 'Parte retirado; el historial permanece guardado.'); }}>Retirar</button>}</td></tr>)}</tbody></table></div>
      {reportDetail && <article className="report-detail"><div className="panel-title"><b>Parte {String(reportDetail.report_number ?? '')}</b><span><button onClick={printReport}>Imprimir / Guardar PDF</button><button onClick={() => setReportDetail(null)}>Cerrar</button></span></div><pre>{JSON.stringify(reportDetail, null, 2)}</pre><p className="small muted">Vista completa de los datos guardados. La impresión genera una hoja de consulta local.</p></article>}
    </section>}
    {tab === 'usuarios' && <section className="admin-panel"><div className="panel-title"><b>Cuentas, roles y acceso</b><button className="add" onClick={() => setUserDialog('new')}>＋ Crear usuario</button></div><div className="table-scroll"><table className="admin-table"><thead><tr><th>Nombre</th><th>Correo</th><th>Rol</th><th>Compañía</th><th>Estado</th><th>Acciones</th></tr></thead><tbody>{users.map(user => <tr key={user.id}><td>{user.profile?.full_name ?? 'Sin perfil'}</td><td>{user.email}</td><td>{roleLabels[user.profile?.role ?? ''] ?? user.profile?.role ?? 'Sin perfil'}</td><td>{companies.find(company => company.id === user.profile?.company_id)?.short_name ?? '—'}</td><td>{user.profile?.is_active ? 'Activo' : 'Inactivo'}</td><td><button onClick={() => setUserDialog(user)}>Editar</button>{user.profile && <button className="danger" onClick={() => { if (window.confirm(`¿Eliminar la cuenta ${user.email}? Si ya tiene partes, se deberá desactivar para conservar el historial.`)) void run(async () => { await callUserAdmin({ action: 'delete', user_id: user.id }); await loadUsers(); }, 'Cuenta eliminada.'); }}>Eliminar</button>}</td></tr>)}</tbody></table></div></section>}
    {tab === 'catalogos' && <section className="admin-panel"><div className="panel-title"><b>Opciones de los formularios</b><button className="add" onClick={() => setCatalogDialog('new')}>＋ Agregar opción</button></div><div className="table-scroll"><table className="admin-table"><thead><tr><th>Compañía</th><th>Grupo</th><th>Opción</th><th>Estado</th><th>Acciones</th></tr></thead><tbody>{catalogs.map(item => <tr key={item.id}><td>{companies.find(company => company.id === item.company_id)?.short_name ?? '—'}</td><td>{item.category}</td><td>{item.value}</td><td>{item.is_active ? 'Activa' : 'Inactiva'}</td><td><button onClick={() => setCatalogDialog(item)}>Editar</button><button className="danger" onClick={() => { if (window.confirm(`¿Desactivar la opción “${item.value}”?`)) void run(async () => { const { error: updateError } = await supabase!.from('report_catalogs').update({ is_active: false }).eq('id', item.id); if (updateError) throw updateError; await loadCatalogs(); }, 'Opción desactivada.'); }}>Desactivar</button></td></tr>)}</tbody></table></div><p className="small muted">Las opciones usadas en partes anteriores se conservan en esos registros.</p></section>}
    {tab === 'numeracion' && <section className="admin-panel"><div className="panel-title"><b>Configuración de numeración automática</b></div><p className="small muted">El siguiente número debe ser superior a cualquier número ya utilizado o reservado para ese año. Los números digitados manualmente en un parte se conservan.</p>{numberConfigs.map(config => <NumberingEditor key={`${config.company_id}-${config.report_year}`} config={config} onSave={saveNumberConfig} />)}</section>}
    {userDialog && <UserEditor value={userDialog} companies={companies} onCancel={() => setUserDialog(null)} onSave={async payload => { await run(async () => { await callUserAdmin(payload); await loadUsers(); setUserDialog(null); }, userDialog === 'new' ? 'Cuenta creada.' : 'Cuenta actualizada.'); }} />}
    {catalogDialog && <CatalogEditor value={catalogDialog} companies={companies} onCancel={() => setCatalogDialog(null)} onSave={async (value) => { await run(async () => { const queryBuilder = supabase!.from('report_catalogs'); const result = catalogDialog === 'new'
      ? await queryBuilder.insert(value)
      : await queryBuilder.update({ category: value.category, value: value.value, company_id: value.company_id }).eq('id', catalogDialog.id);
      if (result.error) throw result.error; await loadCatalogs(); setCatalogDialog(null); }, 'Opción guardada.'); }} />}
  </main>;
}

function NumberingEditor({ config, onSave }: { config: NumberConfig; onSave: (config: NumberConfig) => Promise<void> }) {
  const [draft, setDraft] = useState(config);
  useEffect(() => setDraft(config), [config]);
  return <form className="numbering-row" onSubmit={event => { event.preventDefault(); void onSave(draft); }}>
    <h3>{config.company_name} · {config.report_year}</h3>
    <label>Prefijo<input maxLength={24} value={draft.number_prefix} onChange={event => setDraft({ ...draft, number_prefix: event.target.value })} /></label>
    <label>Siguiente número<input type="number" min={1} required value={draft.next_number} onChange={event => setDraft({ ...draft, next_number: Number(event.target.value) })} /></label>
    <label>Posiciones (ceros)<input type="number" min={1} max={12} required value={draft.padding} onChange={event => setDraft({ ...draft, padding: Number(event.target.value) })} /></label>
    <span className="number-preview">Ejemplo: {draft.number_prefix}{String(draft.next_number).padStart(draft.padding, '0')}</span>
    <button className="primary" disabled={draft.next_number < config.next_number}>Guardar numeración</button>
  </form>;
}

function Chart({ title, rows }: { title: string; rows: { label: string; count: number }[] }) {
  const max = Math.max(1, ...rows.map(row => Number(row.count)));
  return <section className="admin-panel"><h2>{title}</h2>{rows.length ? rows.map(row => <div className="bar-row" key={row.label}><span>{row.label}</span><div><i style={{ width: `${Math.max(3, Number(row.count) / max * 100)}%` }} /></div><b>{row.count}</b></div>) : <p className="muted">Sin registros todavía.</p>}</section>;
}

function UserEditor({ value, companies, onCancel, onSave }: { value: ManagedUser | 'new'; companies: Company[]; onCancel: () => void; onSave: (payload: Record<string, unknown>) => Promise<void> }) {
  const existing = value !== 'new' ? value : null;
  const [fullName, setFullName] = useState(existing?.profile?.full_name ?? '');
  const [email, setEmail] = useState(existing?.email ?? '');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState(existing?.profile?.role ?? 'reporter');
  const [companyId, setCompanyId] = useState(existing?.profile?.company_id ?? companies[0]?.id ?? '');
  const [isActive, setIsActive] = useState(existing?.profile?.is_active ?? true);
  const submit = (event: FormEvent) => { event.preventDefault(); void onSave({ action: existing ? 'update' : 'create', ...(existing ? { user_id: existing.id } : {}), full_name: fullName, email, password, role, company_id: companyId, is_active: isActive }); };
  return <div className="modal-backdrop"><form className="admin-modal" onSubmit={submit}><h2>{existing ? 'Editar cuenta' : 'Crear cuenta de acceso'}</h2><label>Nombre completo<input required value={fullName} onChange={event => setFullName(event.target.value)} /></label><label>Correo institucional<input required type="email" value={email} onChange={event => setEmail(event.target.value)} /></label><label>{existing ? 'Nueva contraseña (opcional)' : 'Contraseña inicial'}<input type="password" minLength={existing && !password ? undefined : 12} required={!existing} value={password} onChange={event => setPassword(event.target.value)} placeholder="Mínimo 12 caracteres" /></label><label>Rol<select value={role} onChange={event => setRole(event.target.value)}>{Object.entries(roleLabels).map(([key, text]) => <option key={key} value={key}>{text}</option>)}</select></label><label>Compañía<select required value={companyId} onChange={event => setCompanyId(event.target.value)}>{companies.filter(company => company.is_active).map(company => <option key={company.id} value={company.id}>{company.name}</option>)}</select></label><label className="check-label"><input type="checkbox" checked={isActive} onChange={event => setIsActive(event.target.checked)} />Cuenta activa</label><div className="actions"><button className="primary">Guardar</button><button type="button" onClick={onCancel}>Cancelar</button></div><p className="small muted">No compartas contraseñas por chat. La contraseña se transmite directamente a Supabase Auth.</p></form></div>;
}

function CatalogEditor({ value, companies, onCancel, onSave }: { value: Catalog | 'new'; companies: Company[]; onCancel: () => void; onSave: (payload: { company_id: string; category: string; value: string }) => Promise<void> }) {
  const existing = value !== 'new' ? value : null;
  const [companyId, setCompanyId] = useState(existing?.company_id ?? companies[0]?.id ?? '');
  const [category, setCategory] = useState(existing?.category ?? 'district');
  const [option, setOption] = useState(existing?.value ?? '');
  return <div className="modal-backdrop"><form className="admin-modal" onSubmit={event => { event.preventDefault(); void onSave({ company_id: companyId, category, value: option.trim() }); }}><h2>{existing ? 'Editar opción' : 'Agregar opción'}</h2><label>Compañía<select required value={companyId} onChange={event => setCompanyId(event.target.value)}>{companies.filter(company => company.is_active).map(company => <option key={company.id} value={company.id}>{company.name}</option>)}</select></label><label>Grupo / campo<input required value={category} onChange={event => setCategory(event.target.value)} placeholder="district, firefighter, unit…" /></label><label>Opción<input required value={option} onChange={event => setOption(event.target.value)} /></label><div className="actions"><button className="primary">Guardar</button><button type="button" onClick={onCancel}>Cancelar</button></div><p className="small muted">Usa el nombre técnico del grupo mostrado en la tabla, por ejemplo district o shift_operator.</p></form></div>;
}

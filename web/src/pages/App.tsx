import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import type { Session, User } from '@supabase/supabase-js';
import { supabase } from '../lib/supabase';
import SuperAdminConsole from './SuperAdminConsole';

type Profile = { full_name: string; role: string; company_id: string; is_active: boolean };
type Catalog = { category: string; value: string };
type RecordRow = Record<string, string>;
type SectionKey = 'victims' | 'vehicles' | 'units' | 'personnel' | 'supports' | 'pnp_support';
type GeneralData = {
  occurred_at: string;
  emergency_type: string;
  codification: string;
  address: string;
  district: string;
  work_description: string;
  materials: string;
  uniformed: string;
  equipment_orderly: string;
  logbook_recorded: string;
  shift_operator: string;
  filled_by: string;
  observations: string;
  signature_name: string;
};
type FieldDefinition = { key: string; label: string; catalog?: string; type?: string; width?: number };

const seedCatalogs: Record<string, string[]> = {
  district: ['Alto Selva Alegre', 'Cayma', 'Cercado', 'Cerro Colorado', 'Characato', 'Chiguata', 'Hunter (Jacobo Hunter)', 'José Luis Bustamante y Rivero', 'La Joya', 'Mariano Melgar', 'Miraflores', 'Mollebaya', 'Paucarpata', 'Pocsi', 'Polobaya', 'Quequeña', 'Sabandía', 'Sachaca', 'San Juan de Siguas', 'San Juan de Tarucani', 'Santa Isabel de Siguas', 'Santa Rita de Siguas', 'Socabaya', 'Tiabaya', 'Uchumayo', 'Vítor', 'Yanahuara', 'Yarabamba', 'Yura'],
  emergency_type: ['10.41 Herido', '10.42 Muerto', '10.43 Efectivo FF.AA. FF.PP herido', '10.46', '10.51', '20.01', '20.02', '20.03', '20.04', 'Accidente vehicular', 'Atención prehospitalaria', 'Falsa alarma', 'Incendio', 'Materiales peligrosos', 'Otros', 'Rescate'],
  codification: ['CODIGO1', 'CODIGO2', 'CODIGO3', 'CODIGO4'],
  unit: ['Ambulancia', 'Auxiliar', 'Escala', 'Maquina', 'Medica', 'Rescate'],
  firefighter: [],
  company: ['B12', 'B140', 'B19', 'B77', 'B78'],
  police_station: ['Cruz roja', 'Policia', 'SAMU', 'Serenazgo'],
  shift_operator: [],
  personnel_condition: ['Asiste', 'Retén'],
  yes_no: ['Sí', 'No'],
};
const emblemSrc = `${import.meta.env.BASE_URL}emblem-reference.png`;

const fieldSets: Record<SectionKey, { title: string; fields: FieldDefinition[] }> = {
  victims: { title: 'Víctimas', fields: [
    { key: 'full_name', label: 'Nombres y apellidos', width: 50 }, { key: 'dni', label: 'DNI', width: 20 },
    { key: 'age', label: 'Edad', width: 10 }, { key: 'injury', label: 'Lesión', width: 20 },
  ] },
  vehicles: { title: 'Vehículos involucrados', fields: [
    { key: 'plate', label: 'Placa' }, { key: 'make', label: 'Marca' }, { key: 'model', label: 'Modelo' },
    { key: 'color', label: 'Color' }, { key: 'year', label: 'Año', type: 'number' },
  ] },
  units: { title: 'Unidades que asistieron', fields: [
    { key: 'unit', label: 'Unidad', catalog: 'unit', width: 12 }, { key: 'pilot', label: 'Piloto', catalog: 'firefighter', width: 16 },
    { key: 'command', label: 'Al mando', catalog: 'firefighter', width: 18 }, { key: 'kms_out', label: 'KM salida', width: 10 },
    { key: 'kms_in', label: 'KM ingreso', width: 10 }, { key: 'hour_out', label: 'H. salida', type: 'time', width: 10 },
    { key: 'hour_in', label: 'H. ingreso', type: 'time', width: 10 }, { key: 'soat', label: 'SOAT', catalog: 'yes_no', width: 7 },
    { key: 'citv', label: 'CITV', catalog: 'yes_no', width: 7 },
  ] },
  personnel: { title: 'Efectivos en servicio', fields: [
    { key: 'firefighter', label: 'Efectivo', catalog: 'firefighter', width: 80 },
    { key: 'condition', label: 'Condición', catalog: 'personnel_condition', width: 20 },
  ] },
  supports: { title: 'Vehículos de apoyo del CGBVP', fields: [
    { key: 'company_name', label: 'Compañía', catalog: 'company' }, { key: 'unit', label: 'Unidad', catalog: 'unit' },
    { key: 'command', label: 'Al mando' },
  ] },
  pnp_support: { title: 'Apoyo PNP / otras instituciones', fields: [
    { key: 'institution', label: 'Institución / dependencia', catalog: 'police_station' },
    { key: 'vehicle', label: 'Vehículo' }, { key: 'command', label: 'Al mando' },
  ] },
};

function localDateTime(): string {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function emptyGeneral(name = ''): GeneralData {
  return {
    occurred_at: localDateTime(), emergency_type: '', codification: '', address: '', district: '',
    work_description: '', materials: '', uniformed: 'Sí', equipment_orderly: 'Sí', logbook_recorded: 'Sí',
    shift_operator: '', filled_by: name, observations: '', signature_name: name,
  };
}

function SignIn({ message, setMessage }: { message: string; setMessage: (value: string) => void }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!supabase) return;
    setBusy(true); setMessage('');
    const { error } = await supabase.auth.signInWithPassword({ email: email.trim(), password });
    if (error) setMessage('No se pudo iniciar sesión. Revisa tu correo y contraseña o consulta al administrador.');
    setBusy(false);
  };
  return <main className="auth-wrap">
    <section className="auth-card">
      <img className="auth-crest" src={emblemSrc} alt="Escudo del Cuerpo General de Bomberos Voluntarios del Perú" />
      <p className="auth-org">CGBVP</p>
      <h1>Gestión de partes de emergencia</h1>
      <p className="muted">Ingresa con la cuenta que te asignó el administrador.</p>
      <form onSubmit={submit} className="auth-form">
        <label>Correo institucional<input type="email" autoComplete="username" required value={email} onChange={e => setEmail(e.target.value)} /></label>
        <label>Contraseña<input type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} /></label>
        {message && <p className="error" role="alert">{message}</p>}
        <button className="primary" disabled={busy}>{busy ? 'Ingresando…' : 'Iniciar sesión'}</button>
      </form>
      <p className="small muted">El acceso requiere una cuenta activa y autorización para registrar partes.</p>
      <p className="powered-by">powered by decibelius</p>
    </section>
  </main>;
}

export default function App() {
  const demoMode = !supabase;
  const [session, setSession] = useState<Session | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(Boolean(supabase));
  const [authMessage, setAuthMessage] = useState('');
  const [accessError, setAccessError] = useState('');
  const [catalogs, setCatalogs] = useState<Record<string, string[]>>(seedCatalogs);
  const [general, setGeneral] = useState<GeneralData>(() => emptyGeneral());
  const [reportNumber, setReportNumber] = useState('');
  const [records, setRecords] = useState<Record<SectionKey, RecordRow[]>>({
    victims: [], vehicles: [], units: [], personnel: [], supports: [], pnp_support: [],
  });
  const [busy, setBusy] = useState(false);
  const [success, setSuccess] = useState('');
  const [submitError, setSubmitError] = useState('');
  const [showSuperAdmin, setShowSuperAdmin] = useState(true);

  useEffect(() => {
    const client = supabase;
    if (!client) return;
    let active = true;
    const loadAccess = async (user: User) => {
      if (!active) return;
      setLoading(true); setAccessError('');
      const { data, error } = await client.from('profiles')
        .select('full_name, role, company_id, is_active').eq('user_id', user.id).maybeSingle();
      if (!active) return;
      if (error || !data || !data.is_active || !['reporter', 'company_admin', 'general_admin'].includes(data.role)) {
        await client.auth.signOut();
        setSession(null); setProfile(null);
        setAccessError(error ? 'No se pudo verificar tu autorización. Revisa la configuración con el administrador.' :
          'Tu cuenta no está habilitada para registrar partes. Solicita autorización al administrador.');
        setLoading(false);
        return;
      }
      setProfile(data as Profile);
      setGeneral(emptyGeneral(data.full_name));
      const { data: catalogRows } = await client.from('report_catalogs')
        .select('category, value').eq('is_active', true).order('value');
      if (active && catalogRows?.length) {
        const merged: Record<string, string[]> = { ...seedCatalogs };
        const databaseCatalogs: Record<string, string[]> = {};
        for (const row of catalogRows as Catalog[]) {
          databaseCatalogs[row.category] = [...(databaseCatalogs[row.category] ?? []), row.value];
        }
        for (const [category, values] of Object.entries(databaseCatalogs)) merged[category] = values;
        for (const category of Object.keys(merged)) merged[category] = [...new Set(merged[category])];
        setCatalogs(merged);
      }
      setLoading(false);
    };
    const { data: { subscription } } = client.auth.onAuthStateChange((event, nextSession) => {
      setSession(nextSession);
      if (nextSession?.user) {
        if (event === 'SIGNED_IN') void loadAccess(nextSession.user);
      } else { setProfile(null); setLoading(false); }
    });
    void client.auth.getSession().then(({ data }) => {
      if (active && data.session) {
        setSession(data.session);
        void loadAccess(data.session.user);
      } else if (active) setLoading(false);
    });
    return () => { active = false; subscription.unsubscribe(); };
  }, []);

  const setGeneralValue = (key: keyof GeneralData, value: string) => {
    setGeneral(current => ({ ...current, [key]: value }));
    setSuccess(''); setSubmitError('');
  };
  const addRow = (section: SectionKey) => {
    const row: RecordRow = {};
    fieldSets[section].fields.forEach(field => { row[field.key] = ''; });
    setRecords(current => ({ ...current, [section]: [...current[section], row] }));
  };
  const updateRow = (section: SectionKey, index: number, key: string, value: string) => {
    setRecords(current => ({ ...current, [section]: current[section].map((row, i) => i === index ? { ...row, [key]: value } : row) }));
    setSuccess(''); setSubmitError('');
  };
  const removeRow = (section: SectionKey, index: number) => {
    setRecords(current => ({ ...current, [section]: current[section].filter((_row, i) => i !== index) }));
  };

  const renderField = (field: FieldDefinition, value: string, onChange: (value: string) => void) => {
    const listId = field.catalog ? `catalog-${field.catalog}` : undefined;
    return <label key={field.key} className="field" style={field.width ? { flexGrow: field.width } : undefined}>
      {field.label}
      <input type={field.type ?? 'text'} list={listId} value={value} onChange={event => onChange(event.target.value)}
        placeholder={field.catalog ? 'Seleccione o escriba…' : ''} />
    </label>;
  };
  const renderSection = (section: SectionKey) => {
    const definition = fieldSets[section];
    return <section className="panel" key={section}>
      <div className="panel-title"><b>{definition.title}</b><button type="button" className="add" onClick={() => addRow(section)}>＋ Agregar fila</button></div>
      {records[section].length === 0 && <p className="empty-state">Sin filas agregadas.</p>}
      <div className="records-list">{records[section].map((row, index) => <div className={`record-row record-${section}`} key={`${section}-${index}`}>
        {definition.fields.map(field => renderField(field, row[field.key] ?? '', value => updateRow(section, index, field.key, value)))}
        <button className="remove-row" type="button" onClick={() => removeRow(section, index)} aria-label={`Eliminar fila ${index + 1}`}>Eliminar</button>
      </div>)}</div>
    </section>;
  };

  const saveReport = async (event: FormEvent) => {
    event.preventDefault();
    if (demoMode) {
      setSubmitError('');
      setSuccess(`Formulario de demostración${reportNumber.trim() ? ` · N.º ${reportNumber.trim()}` : ''}: no se envió ni guardó información.`);
      return;
    }
    if (!supabase || !profile || !session) return;
    setBusy(true); setSuccess(''); setSubmitError('');
    const compact = (rows: RecordRow[]) => rows.filter(row => Object.values(row).some(value => value.trim()));
    const payload = {
      ...general,
      report_number: reportNumber.trim(),
      occurred_at: new Date(general.occurred_at).toISOString(),
      victims: compact(records.victims), vehicles: compact(records.vehicles), units: compact(records.units),
      personnel: compact(records.personnel), supports: compact(records.supports), pnp_support: compact(records.pnp_support),
    };
    const { data, error } = await supabase.rpc('register_emergency_report', { p_report: payload });
    if (error) setSubmitError(error.message.includes('42501') ? 'Tu cuenta no tiene permiso para registrar este parte.' : `No se pudo guardar el parte: ${error.message}`);
    else {
      const report = Array.isArray(data) ? data[0] : data;
      setSuccess(`Parte ${report?.report_number ?? 'registrado'} guardado correctamente en el sistema.`);
      setGeneral(emptyGeneral(profile.full_name));
      setReportNumber('');
      setRecords({ victims: [], vehicles: [], units: [], personnel: [], supports: [], pnp_support: [] });
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
    setBusy(false);
  };

  const signOut = async () => {
    await supabase?.auth.signOut();
    setSession(null); setProfile(null); setAuthMessage(''); setAccessError('');
  };

  if (!demoMode && loading) return <div className="loading-screen">Verificando autorización…</div>;
  if (!demoMode && (!session || !profile)) return <><header className="topbar"><img className="top-crest" src={emblemSrc} alt="" /><div className="identity"><strong>CUERPO GENERAL DE BOMBEROS VOLUNTARIOS DEL PERÚ</strong><span>VII COMANDANCIA DEPARTAMENTAL</span></div><div className="product">Registro web de partes</div></header>
    <SignIn message={authMessage || accessError} setMessage={setAuthMessage} />
  </>;

  if (!demoMode && profile?.role === 'general_admin' && showSuperAdmin) return <div className="app-shell">
    <header className="topbar"><img className="top-crest" src={emblemSrc} alt="Escudo CGBVP" /><div className="identity"><strong>CUERPO GENERAL DE BOMBEROS VOLUNTARIOS DEL PERÚ</strong><span>VII COMANDANCIA DEPARTAMENTAL</span><span>BENEMÉRITA Y CENTENARIA COMPAÑÍA DE BOMBEROS AREQUIPA 19</span></div><div className="product">Consola de superadministración</div><div className="user-box"><span>{profile.full_name}</span><button type="button" onClick={signOut}>Cerrar sesión</button></div></header>
    <SuperAdminConsole onNewReport={() => setShowSuperAdmin(false)} onSignOut={signOut} />
  </div>;

  return <div className="app-shell">
    <header className="topbar"><img className="top-crest" src={emblemSrc} alt="Escudo CGBVP" /><div className="identity"><strong>CUERPO GENERAL DE BOMBEROS VOLUNTARIOS DEL PERÚ</strong><span>VII COMANDANCIA DEPARTAMENTAL</span><span>BENEMÉRITA Y CENTENARIA COMPAÑÍA DE BOMBEROS AREQUIPA 19</span></div><div className="product">Registro web de partes</div>{demoMode ? <div className="user-box"><span>Vista pública</span></div> : <div className="user-box">{profile?.role === 'general_admin' && <button type="button" onClick={() => setShowSuperAdmin(true)}>Panel administrador</button>}<span>{profile?.full_name}</span><button type="button" onClick={signOut}>Cerrar sesión</button></div>}</header>
    <main className="main-content">
      {demoMode && <div className="demo-banner"><strong>Vista previa pública</strong><span>Puedes explorar y completar el formulario. Los datos de demostración no se guardan ni se envían.</span></div>}
      <div className="form-heading"><div className="heading-icon">▤</div><div><h1>Parte de emergencia</h1><p>Registro digital · Los campos con * son obligatorios</p></div></div>
      <div className={`auth-status ${demoMode ? 'demo-status' : ''}`}><span className="status-dot" /> {demoMode ? 'Modo de demostración · sin inicio de sesión' : 'Sesión autorizada para registrar partes'}</div>
      {accessError && <p className="error" role="alert">{accessError}</p>}
      {success && <p className="success" role="status">{success}</p>}
      {submitError && <p className="error" role="alert">{submitError}</p>}
      <form onSubmit={saveReport}>
        <section className="panel general-panel"><div className="panel-title"><b>Datos generales</b></div><div className="general-grid">
          <label>N.º de parte<input value={reportNumber} onChange={e => setReportNumber(e.target.value)} placeholder="Escriba el número o déjelo vacío para asignación automática" /></label>
          <label>Fecha y hora *<input type="datetime-local" required value={general.occurred_at} onChange={e => setGeneralValue('occurred_at', e.target.value)} /></label>
          <label>Emergencia *<input required list="catalog-emergency_type" value={general.emergency_type} onChange={e => setGeneralValue('emergency_type', e.target.value)} placeholder="Seleccione o escriba…" /></label>
          <label>Codificación *<input required list="catalog-codification" value={general.codification} onChange={e => setGeneralValue('codification', e.target.value)} placeholder="Seleccione o escriba…" /></label>
          <label className="span-2">Dirección *<input required value={general.address} onChange={e => setGeneralValue('address', e.target.value)} placeholder="Dirección del incidente" /></label>
          <label>Distrito *<input required list="catalog-district" value={general.district} onChange={e => setGeneralValue('district', e.target.value)} placeholder="Seleccione o escriba…" /></label>
          <label className="span-all">Trabajo realizado *<textarea required rows={3} value={general.work_description} onChange={e => setGeneralValue('work_description', e.target.value)} /></label>
        </div></section>
        {renderSection('victims')}{renderSection('vehicles')}{renderSection('units')}{renderSection('personnel')}
        <section className="panel"><div className="panel-title"><b>Material utilizado</b></div><textarea className="panel-textarea" rows={3} value={general.materials} onChange={e => setGeneralValue('materials', e.target.value)} /></section>
        <section className="panel"><div className="panel-title"><b>Verificaciones</b></div><div className="check-grid">
          {([['uniformed', 'El personal asistió correctamente uniformado'], ['equipment_orderly', 'Se dejó el material conforme, limpio y ordenado'], ['logbook_recorded', 'Se registró la bitácora correctamente']] as const).map(([key, label]) =>
            <label key={key}>{label}<select value={general[key]} onChange={e => setGeneralValue(key, e.target.value)}><option>Sí</option><option>No</option></select></label>)}
        </div></section>
        {renderSection('supports')}{renderSection('pnp_support')}
        <section className="panel"><div className="panel-title"><b>Cierre del parte</b></div><div className="general-grid">
          <label>Centralista de turno<input list="catalog-shift_operator" value={general.shift_operator} onChange={e => setGeneralValue('shift_operator', e.target.value)} placeholder="Seleccione o escriba…" /></label>
          <label>Llenado por<input value={general.filled_by} onChange={e => setGeneralValue('filled_by', e.target.value)} /></label>
          <label className="span-all">Observaciones<textarea rows={2} value={general.observations} onChange={e => setGeneralValue('observations', e.target.value)} /></label>
          <label className="span-all">Firma / conformidad *<input required value={general.signature_name} onChange={e => setGeneralValue('signature_name', e.target.value)} /></label>
        </div></section>
        <div className="actions"><button className="primary" type="submit" disabled={busy}>{demoMode ? 'Probar formulario' : busy ? 'Guardando parte…' : 'Guardar parte'}</button><button type="reset" onClick={() => { setGeneral(emptyGeneral(profile?.full_name ?? '')); setReportNumber(''); setRecords({ victims: [], vehicles: [], units: [], personnel: [], supports: [], pnp_support: [] }); setSuccess(''); setSubmitError(''); }}>Limpiar formulario</button></div>
      </form>
      {Object.entries(catalogs).map(([category, values]) => <datalist id={`catalog-${category}`} key={category}>{values.map(value => <option value={value} key={value} />)}</datalist>)}
      <footer>{demoMode ? 'Demostración pública · No ingresar información real o sensible' : 'Arequipa 19 · Registro web · El número de parte se asigna al guardar'}</footer>
    </main>
  </div>;
}

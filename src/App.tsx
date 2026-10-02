import { useEffect, useState } from 'react';
import { Activity, ArrowUpRight, BookOpen, ChevronRight, Database, FlaskConical, MapPin, Menu, Radio, X, Zap } from 'lucide-react';
import { useResource } from './api';
import { ErrorState, Loading } from './components';
import ForecastPage from './pages/ForecastPage';
import EvaluationPage from './pages/EvaluationPage';
import DataPage from './pages/DataPage';
import NotesPage from './pages/NotesPage';
import EnergyPage from './pages/EnergyPage';
import type { Meta } from './types';
const pages = [
  { id: 'forecast', title: 'Forecast workspace', icon: Activity },
  { id: 'evaluation', title: 'Model evaluation', icon: FlaskConical },
  { id: 'data', title: 'Data explorer', icon: Database },
  { id: 'notes', title: 'Project notes', icon: BookOpen },
  { id: 'energy', title: 'Energy planning', icon: Zap },
];
function initialPage() { const key = location.hash.slice(1); return pages.some(p => p.id === key) ? key : 'forecast'; }
export default function App() {
  const [page, setPage] = useState(initialPage);
  const [mobile, setMobile] = useState(false);
  const meta = useResource<Meta>('meta');
  useEffect(() => { const handle = () => setPage(initialPage()); window.addEventListener('hashchange', handle); return () => window.removeEventListener('hashchange', handle); }, []);
  useEffect(() => { const close = (e: KeyboardEvent) => { if (e.key === 'Escape') setMobile(false); }; window.addEventListener('keydown', close); return () => window.removeEventListener('keydown', close); }, []);
  function navigate(id: string) { location.hash = id; setPage(id); setMobile(false); window.scrollTo(0, 0); }
  return <div className="app-shell">
    {mobile && <button className="nav-overlay" aria-label="Close navigation" onClick={() => setMobile(false)}/>}
    <aside className={`sidebar ${mobile ? 'is-open' : ''}`} aria-label="Main navigation">
      <a className="brand" href="#forecast" onClick={() => navigate('forecast')}><div className="brand-mark"><Zap size={23} fill="currentColor"/></div><div><strong>India Grid<span>AI</span></strong><small>DEMAND INTELLIGENCE</small></div></a>
      <button className="nav-close" aria-label="Close navigation" onClick={() => setMobile(false)}><X size={20}/></button>
      <div className="nav-section-label">WORKSPACE</div>
      <nav>{pages.map(p => <a key={p.id} href={`#${p.id}`} onClick={() => navigate(p.id)} className={`nav-item ${page === p.id ? 'active' : ''}`} aria-current={page === p.id ? 'page' : undefined}><p.icon size={18}/><span>{p.title}</span>{page === p.id && <ChevronRight size={14}/>}</a>)}</nav>
      <div className="sidebar-project"><div className="project-icon"><FlaskConical size={17}/></div><b>Built on India data</b><p>XGBoost forecasts.<br/>Measured, not simulated.</p><button onClick={() => navigate('notes')}>Explore the methodology<ArrowUpRight size={14}/></button></div>
      <div className="sidebar-footer"><span className="status-dot"/><div><b>{meta.data ? 'Forecast service ready' : 'Connecting to service'}</b><small>Local research demo</small></div></div>
    </aside>
    <main className="main-shell"><header className="topbar"><div className="breadcrumb"><button className="menu-button" aria-label="Open navigation" aria-expanded={mobile} onClick={() => setMobile(true)}><Menu size={21}/></button><span>Workspace</span><ChevronRight size={14}/><b>{pages.find(p => p.id === page)?.title}</b></div><div className="topbar-right"><span className="region-label"><MapPin size={14}/>India-wide demand</span><span className="demo-badge"><Radio size={13}/>Historical replay</span><span className="avatar" title="College project demo">ID</span></div></header>
      <div className="page-content">{meta.loading ? <Loading message="Connecting to your forecasting model…"/> : meta.error ? <ErrorState message={meta.error} retry={meta.retry}/> : meta.data && <>
        {page === 'forecast' && <ForecastPage meta={meta.data} navigate={navigate}/>}
        {page === 'evaluation' && <EvaluationPage/>}
        {page === 'data' && <DataPage meta={meta.data}/>}
        {page === 'notes' && <NotesPage meta={meta.data}/>}
        {page === 'energy' && <EnergyPage meta={meta.data}/>}
      </>}</div>
      <footer className="app-footer"><span>India Energy Demand Forecasting & Grid Intelligence</span><span>Demand displayed in GW · All times IST · 2023–2024 dataset</span></footer>
    </main>
  </div>;
}

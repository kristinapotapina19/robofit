import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, setToken } from './api.js'
import { AdminPage, AuthModal, CatalogPage, ProjectsModal, SolutionModal } from './components/Panels.jsx'
import { ErrorBox, Loading, Toast } from './components/ui.jsx'
import CompareStep from './steps/CompareStep.jsx'
import EconomicsStep from './steps/EconomicsStep.jsx'
import ExportStep from './steps/ExportStep.jsx'
import ObjectStep from './steps/ObjectStep.jsx'
import ParamsStep from './steps/ParamsStep.jsx'
import SelectionStep from './steps/SelectionStep.jsx'
import SimulationStep from './steps/SimulationStep.jsx'
import WhatIfStep from './steps/WhatIfStep.jsx'

const STEPS = ['Объект', 'Параметры', 'Подбор', 'Сравнение', 'Экономика', 'What-if', 'Визуализация', 'Отчёт']

export default function App() {
  const [view, setView] = useState('wizard')
  const [step, setStep] = useState(0)
  const [boot, setBoot] = useState({ loading: true, error: null })
  const [objectTypes, setObjectTypes] = useState([])
  const [meta, setMeta] = useState(null)
  const [user, setUser] = useState(null)
  const [objectType, setObjectType] = useState('warehouse')
  const [profileCode, setProfileCode] = useState('pallet_transport')
  const [presets, setPresets] = useState({})
  const [values, setValuesMap] = useState({})
  const [selection, setSelection] = useState({ data: null, loading: false, error: null })
  const [compareIds, setCompareIds] = useState([])
  const [solutionId, setSolutionId] = useState(null)
  const [overrides, setOverrides] = useState({})
  const [options, setOptions] = useState({})
  const [calc, setCalc] = useState({ data: null, loading: false, error: null })
  const [project, setProject] = useState(null)
  const [modal, setModal] = useState(null)
  const [detailId, setDetailId] = useState(null)
  const [toast, setToast] = useState(null)

  const notify = useCallback((text, bad = false) => setToast({ text, bad }), [])

  const loadBoot = () => {
    setBoot({ loading: true, error: null })
    Promise.all([api.get('/catalog/object-types'), api.get('/meta'), api.get('/auth/me')])
      .then(([ot, m, me]) => { setObjectTypes(ot); setMeta(m); setUser(me.user); setBoot({ loading: false, error: null }) })
      .catch(error => setBoot({ loading: false, error }))
  }
  useEffect(loadBoot, [])

  useEffect(() => {
    if (!objectType || presets[objectType]) return
    api.get(`/catalog/presets/${objectType}`).then(p => {
      setPresets(prev => ({ ...prev, [objectType]: p }))
      setValuesMap(prev => prev[objectType] ? prev : { ...prev, [objectType]: Object.fromEntries(p.parameters.map(x => [x.label, x.default])) })
    }).catch(e => notify(e.message, true))
  }, [objectType, presets, notify])

  const profile = useMemo(() => objectTypes.find(o => o.code === objectType)?.profiles.find(p => p.code === profileCode), [objectTypes, objectType, profileCode])
  const params = values[objectType] || {}
  const setParams = (v) => { setValuesMap(prev => ({ ...prev, [objectType]: v })); invalidate() }

  const invalidate = () => { setSelection(s => ({ ...s, data: null })); setCalc(c => ({ ...c, data: null })) }

  const request = useMemo(() => ({ profile_code: profileCode, params, solution_id: solutionId, overrides, options }),
    [profileCode, params, solutionId, overrides, options])

  const runSelection = useCallback(() => {
    setSelection({ data: null, loading: true, error: null })
    api.post('/selection', { profile_code: profileCode, params })
      .then(data => setSelection({ data, loading: false, error: null }))
      .catch(error => setSelection({ data: null, loading: false, error }))
  }, [profileCode, params])

  const runCalc = useCallback((over = overrides, opts = options, sid = solutionId) => {
    if (!sid) return
    setCalc({ data: null, loading: true, error: null })
    api.post('/evaluate', { profile_code: profileCode, params, solution_id: sid, overrides: over, options: opts })
      .then(data => setCalc({ data, loading: false, error: null }))
      .catch(error => setCalc({ data: null, loading: false, error }))
  }, [profileCode, params, overrides, options, solutionId])

  const go = (i) => {
    if (i === 2 && !selection.data && !selection.loading) runSelection()
    if (i >= 4 && !calc.data && !calc.loading && solutionId) runCalc()
    setStep(i)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const chooseSolution = (id) => {
    setSolutionId(id)
    setOverrides({})
    setOptions({})
    runCalc({}, {}, id)
    go(4)
  }

  const toggleCompare = (c) => {
    if (compareIds.includes(c.solution_id)) { setCompareIds(compareIds.filter(x => x !== c.solution_id)); return }
    if (compareIds.length >= 5) { notify('В сравнении не больше 5 решений', true); return }
    if (c.verdict === 'excluded' && !window.confirm(`Решение не прошло подбор: ${c.decisive_reason}\nВсё равно добавить в сравнение?`)) return
    setCompareIds([...compareIds, c.solution_id])
  }

  const selectObject = (ot, pc) => {
    if (ot !== objectType || pc !== profileCode) {
      setObjectType(ot); setProfileCode(pc); setCompareIds([]); setSolutionId(null); setProject(null); invalidate()
    }
  }

  const openProject = async (p) => {
    setProject(p)
    setObjectType(p.object_type)
    setProfileCode(p.profile_code || objectTypes.find(o => o.code === p.object_type)?.profiles[0].code)
    setValuesMap(prev => ({ ...prev, [p.object_type]: { ...(prev[p.object_type] || {}), ...p.parameters } }))
    invalidate()
    const last = p.scenarios[p.scenarios.length - 1]
    if (last) {
      setSolutionId(last.solution_external_id); setOverrides(last.overrides); setOptions(last.options)
      setCalc({ data: null, loading: true, error: null })
      setView('wizard'); setStep(4)
      try {
        const r = await api.post(`/projects/${p.id}/scenarios/${last.id}/replay`)
        setCalc({ data: r.result, loading: false, error: null })
        notify(r.matches_saved ? `Расчёт воспроизведён: результат совпадает с сохранённым (каталог ${r.versions.saved.catalog}, модель ${r.versions.saved.model})`
          : `Расчёт воспроизведён на текущих данных: версии изменились с ${r.versions.saved.catalog}/${r.versions.saved.model}, цифры отличаются от сохранённых`, !r.matches_saved)
      } catch (e) { setCalc({ data: null, loading: false, error: e }) }
    } else { setView('wizard'); setStep(1) }
  }

  const logout = () => { setToken(null); setUser(null); setProject(null); notify('Вы вышли из системы') }

  const available = [true, !!profile, !!profile, compareIds.length > 0, !!solutionId, !!calc.data, !!calc.data, !!calc.data]

  if (boot.loading) return <Loading text="Подключение к платформе…" />
  if (boot.error) return <div className="page"><ErrorBox error={boot.error} onRetry={loadBoot} /></div>

  return (
    <>
      <header className="topbar">
        <div className="brand">
          <svg viewBox="0 0 24 24" fill="none" stroke="#ec4899" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="m12 2 9 5-9 5-9-5 9-5z" /><path d="m3 12 9 5 9-5" /><path d="m3 17 9 5 9-5" />
          </svg>
          Роботизация | ЛЦТ 2026<span>РобоФит — подбор решений и расчёт эффекта</span>
        </div>
        <nav className="topnav">
          <button className={view === 'wizard' ? 'active' : ''} onClick={() => setView('wizard')}>Расчёт</button>
          <button className={view === 'catalog' ? 'active' : ''} onClick={() => setView('catalog')}>Каталог</button>
          {user && <button onClick={() => setModal('projects')}>Мои проекты</button>}
          {user?.role === 'admin' && <button className={view === 'admin' ? 'active' : ''} onClick={() => setView('admin')}>Администрирование</button>}
        </nav>
        <div className="spacer" />
        {project && <span className="badge accent" title="Открытый проект">Проект: {project.title}</span>}
        <div className="userbox">
          {user ? <>
            <span className="badge">{user.username} · {user.role === 'admin' ? 'администратор' : 'пользователь'}</span>
            <button className="btn small" onClick={logout}>Выйти</button>
          </> : <>
            <span className="badge">гость</span>
            <button className="btn small primary" onClick={() => setModal('auth')}>Войти</button>
          </>}
        </div>
      </header>

      <main className="page">
        {view === 'catalog' && <CatalogPage objectTypes={objectTypes} onDetail={setDetailId} />}
        {view === 'admin' && <AdminPage user={user} notify={notify} onDetail={setDetailId} />}
        {view === 'wizard' && <>
          <nav className="stepper" aria-label="Шаги">
            {STEPS.map((s, i) => (
              <button key={s} className={`${i === step ? 'active' : ''} ${i < step && available[i] ? 'done' : ''}`}
                disabled={!available[i]} onClick={() => go(i)}><b>{i + 1}</b>{s}</button>
            ))}
          </nav>
          {step === 0 && <ObjectStep objectTypes={objectTypes} objectType={objectType} profileCode={profileCode} onSelect={selectObject} onNext={() => go(1)} />}
          {step === 1 && (presets[objectType] && profile
            ? <ParamsStep preset={presets[objectType]} profile={profile} values={params} setValues={setParams} notify={notify} onBack={() => go(0)} onNext={() => { runSelection(); go(2) }} />
            : <Loading />)}
          {step === 2 && <SelectionStep selection={selection.data} loading={selection.loading} error={selection.error} retry={runSelection} meta={meta}
            compareIds={compareIds} toggleCompare={toggleCompare} solutionId={solutionId} onCalc={chooseSolution} onDetail={setDetailId}
            onBack={() => go(1)} onNext={() => go(3)} />}
          {step === 3 && <CompareStep profileCode={profileCode} params={params} ids={compareIds} remove={(id) => setCompareIds(compareIds.filter(x => x !== id))} onCalc={chooseSolution} onBack={() => go(2)} />}
          {step === 4 && <EconomicsStep result={calc.data} loading={calc.loading} error={calc.error} retry={() => runCalc()} overrides={overrides} setOverrides={setOverrides}
            onRecalc={(o) => runCalc(o, options)} onBack={() => go(compareIds.length ? 3 : 2)} onNext={() => go(5)} />}
          {step === 5 && <WhatIfStep key={calc.data?.calculated_at} result={calc.data} request={request} onApply={(o) => { setOptions(o); runCalc(overrides, o); go(4) }} onBack={() => go(4)} onNext={() => go(6)} />}
          {step === 6 && <SimulationStep key={calc.data?.calculated_at} result={calc.data} onBack={() => go(5)} onNext={() => go(7)} />}
          {step === 7 && <ExportStep result={calc.data} request={request} user={user} project={project} setProject={setProject} notify={notify}
            onLogin={() => setModal('auth')} onOpenProjects={() => setModal('projects')} onBack={() => go(6)} />}
        </>}
      </main>

      {modal === 'auth' && <AuthModal onClose={() => setModal(null)} onAuth={(u) => { setUser(u); notify(`Добро пожаловать, ${u.username}`) }} />}
      {modal === 'projects' && <ProjectsModal onClose={() => setModal(null)} onOpen={openProject} notify={notify} />}
      {detailId && <SolutionModal id={detailId} onClose={() => setDetailId(null)} />}
      <Toast toast={toast} onDone={() => setToast(null)} />
    </>
  )
}

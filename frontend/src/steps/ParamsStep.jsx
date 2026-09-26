import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api.js'
import { Info } from '../components/ui.jsx'
import { fmt } from '../format.js'

export default function ParamsStep({ preset, profile, values, setValues, onBack, onNext, notify }) {
  const [check, setCheck] = useState(null)
  const [onlyUsed, setOnlyUsed] = useState(true)
  const [busy, setBusy] = useState(false)
  const fileRef = useRef(null)
  const used = useMemo(() => new Set(profile?.used_params || []), [profile])

  useEffect(() => {
    if (!preset) return
    const t = setTimeout(() => {
      api.post(`/params/validate?profile=${profile.code}`, { object_type: preset.code, values })
        .then(setCheck).catch(() => setCheck(null))
    }, 300)
    return () => clearTimeout(t)
  }, [values, preset, profile])

  if (!preset) return null
  const errors = Object.fromEntries((check?.errors || []).map(e => [e.label, e]))
  const warnings = Object.fromEntries((check?.warnings || []).map(e => [e.label, e]))
  const shown = preset.parameters.filter(p => !onlyUsed || used.has(p.label))
  const sections = []
  shown.forEach(p => {
    const s = p.section || 'Параметры'
    if (!sections.length || sections[sections.length - 1].name !== s) sections.push({ name: s, items: [] })
    sections[sections.length - 1].items.push(p)
  })

  const set = (label, v) => setValues({ ...values, [label]: v })
  const resetDemo = () => {
    setValues(Object.fromEntries(preset.parameters.map(p => [p.label, p.default])))
    notify('Загружены демонстрационные значения организатора')
  }

  const upload = async (file) => {
    if (!file) return
    setBusy(true)
    try {
      const r = await api.upload(`/params/upload?object_type=${preset.code}&profile=${profile.code}`, file)
      setValues({ ...values, ...r.values })
      notify(`Загружено параметров: ${r.matched} из ${r.total}` +
        (r.validation.errors.length ? `. Ошибок: ${r.validation.errors.length} — исправьте подсвеченные поля` : ''),
        r.validation.errors.length > 0)
    } catch (e) {
      notify(e.message, true)
    } finally {
      setBusy(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const template = (fmtName) => api.download(`/params/template/${preset.code}?fmt=${fmtName}`, undefined, `шаблон.${fmtName}`)
    .catch(e => notify(e.message, true))

  const nErr = check?.errors?.length || 0
  const nWarn = (check?.warnings || []).filter(w => used.has(w.label)).length

  return (
    <div>
      <div className="card">
        <div className="card-head">
          <div style={{ flex: 1 }}>
            <h2>Шаг 2. Параметры объекта: {preset.title.toLowerCase()}</h2>
            <p>Операция: <b>{profile.title}</b>. Поля со звёздочкой участвуют в расчёте. Значения по умолчанию — демо-датасет организатора; их можно изменить вручную или загрузить из Excel/CSV.</p>
          </div>
        </div>
        <div className="row">
          <button className="btn" onClick={resetDemo}>Демо-данные организатора</button>
          <button className="btn" onClick={() => fileRef.current?.click()} disabled={busy}>{busy ? 'Загрузка…' : 'Загрузить Excel / CSV'}</button>
          <input ref={fileRef} type="file" accept=".xlsx,.csv" hidden onChange={(e) => upload(e.target.files[0])} />
          <button className="btn ghost" onClick={() => template('xlsx')}>Шаблон .xlsx</button>
          <button className="btn ghost" onClick={() => template('csv')}>Шаблон .csv</button>
          <div className="spacer" />
          <div className="seg">
            <button className={onlyUsed ? 'on' : ''} onClick={() => setOnlyUsed(true)}>Для расчёта ({used.size})</button>
            <button className={!onlyUsed ? 'on' : ''} onClick={() => setOnlyUsed(false)}>Все ({preset.parameters.length})</button>
          </div>
        </div>
        {nErr > 0 && <div className="mt"><Info kind="bad">Исправьте ошибки в {nErr} {nErr === 1 ? 'поле' : 'полях'} — они подсвечены красным.</Info></div>}
        {nErr === 0 && nWarn > 0 && <div className="mt"><Info kind="warn">{nWarn} значений вне типового диапазона — расчёт выполнится, но проверьте единицы измерения.</Info></div>}

        {sections.map(sec => (
          <div key={sec.name}>
            <div className="section-title">{sec.name}</div>
            <div className="params">
              {sec.items.map(p => {
                const numeric = typeof p.default === 'number'
                const e = errors[p.label]
                const w = warnings[p.label]
                const v = values[p.label]
                return (
                  <div className="param" key={p.label}>
                    <div className="lbl">{used.has(p.label) && <span className="req" title="Используется в расчёте">*</span>}<span>{p.label}</span></div>
                    <div className="inp">
                      <input type={numeric ? 'number' : 'text'} step="any" value={v ?? ''} className={e ? 'err' : w ? 'wrn' : ''}
                        onChange={(ev) => set(p.label, numeric ? (ev.target.value === '' ? '' : Number(ev.target.value)) : ev.target.value)}
                        aria-invalid={!!e} />
                      <span className="unit">{p.unit && p.unit !== '-' ? p.unit : ''}</span>
                    </div>
                    {e && <div className="msg e">{e.message}. {e.fix}</div>}
                    {!e && w && <div className="msg w">{w.message}</div>}
                    {!e && !w && <div className="hint">
                      {numeric && p.min !== null && p.max !== null && typeof p.min === 'number' && p.min !== p.max ? `Типовой диапазон ${fmt(p.min, 3)}–${fmt(p.max, 3)}. ` : ''}
                      {p.source_note ? p.source_note : `Пример: ${p.default ?? '—'}`}
                    </div>}
                  </div>
                )
              })}
            </div>
          </div>
        ))}
      </div>
      <div className="stepfoot">
        <button className="btn" onClick={onBack}>← Назад</button>
        <button className="btn apply" disabled={nErr > 0} onClick={onNext}>✓ Применить параметры и подобрать решения →</button>
      </div>
    </div>
  )
}

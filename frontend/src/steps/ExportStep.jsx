import { useState } from 'react'
import { api } from '../api.js'
import { Info } from '../components/ui.jsx'
import { mln, years } from '../format.js'
import { ScenarioTable, VerdictBox } from './EconomicsStep.jsx'

export default function ExportStep({ result, request, user, project, setProject, onLogin, notify, onOpenProjects, onBack }) {
  const [title, setTitle] = useState(project?.title || `${result?.profile.title || 'Проект'} — ${new Date().toLocaleDateString('ru-RU')}`)
  const [scTitle, setScTitle] = useState(result ? `${result.solution.name.split(' (')[0]}, ${result.fleet.count} шт.` : '')
  const [busy, setBusy] = useState('')

  if (!result) return <div className="card"><div className="empty">Сначала выполните расчёт экономики.</div></div>

  const download = async (fmt) => {
    setBusy(fmt)
    try { await api.download(`/report/${fmt}`, request, `отчёт.${fmt}`); notify(`Отчёт ${fmt.toUpperCase()} сформирован`) } catch (e) { notify(e.message, true) } finally { setBusy('') }
  }

  const save = async () => {
    setBusy('save')
    try {
      let p = project
      if (!p) {
        p = await api.post('/projects', { title, object_type: result.profile.object_type, profile_code: result.profile.code, parameters: request.params })
      } else {
        p = await api.put(`/projects/${p.id}`, { title, profile_code: result.profile.code, parameters: request.params })
      }
      await api.post(`/projects/${p.id}/scenarios`, { ...request, title: scTitle })
      setProject(await api.get(`/projects/${p.id}`))
      notify('Сценарий сохранён в проект')
    } catch (e) { notify(e.message, true) } finally { setBusy('') }
  }

  const removeScenario = async (sid) => {
    await api.del(`/projects/${project.id}/scenarios/${sid}`)
    setProject(await api.get(`/projects/${project.id}`))
  }

  return (
    <div>
      <div className="card">
        <div className="card-head"><div><h2>Шаг 8. Сохранение и экспорт</h2>
          <p>Отчёт содержит параметры объекта, подбор с причинами, состав оборудования, расчёт с формулами, допущения и источники, чувствительность, риски и результаты имитации.</p></div></div>
        <VerdictBox rec={result.recommendation} />
        <div className="tablewrap mt"><ScenarioTable result={result} /></div>
        <div className="row mt">
          <button className="btn primary" onClick={() => download('pdf')} disabled={!!busy}>{busy === 'pdf' ? 'Формируем…' : 'Скачать отчёт PDF'}</button>
          <button className="btn" onClick={() => download('xlsx')} disabled={!!busy}>{busy === 'xlsx' ? 'Формируем…' : 'Скачать расчёт Excel'}</button>
        </div>
      </div>

      <div className="card">
        <h3>Проект и сценарии</h3>
        {!user && (
          <div className="mt-s">
            <Info>Гость может считать и выгружать отчёты, но не сохранять проекты. Войдите или зарегистрируйтесь, чтобы сохранить проект, сравнивать сценарии и вернуться к расчёту позже.</Info>
            <button className="btn primary mt" onClick={onLogin}>Войти или зарегистрироваться</button>
          </div>
        )}
        {user && (
          <div className="stack mt-s">
            <div className="grid g2">
              <label className="field"><span>Название проекта</span><input type="text" value={title} onChange={e => setTitle(e.target.value)} /></label>
              <label className="field"><span>Название сценария</span><input type="text" value={scTitle} onChange={e => setScTitle(e.target.value)} /></label>
            </div>
            <div className="row">
              <button className="btn primary" onClick={save} disabled={busy === 'save'}>{project ? 'Добавить сценарий в проект' : 'Создать проект и сохранить сценарий'}</button>
              <button className="btn ghost" onClick={onOpenProjects}>Мои проекты</button>
            </div>
            {project && project.scenarios.length > 0 && (
              <div className="tablewrap mt-s">
                <p className="muted" style={{ marginBottom: 6 }}>Сценарии проекта «{project.title}» — можно сравнить до нескольких вариантов решений и допущений:</p>
                <table className="t">
                  <thead><tr><th>Сценарий</th><th>Решение</th><th className="r">Парк</th><th className="r">CAPEX покупки, млн</th><th className="r">Эффект, млн/год</th><th className="r">Окупаемость</th><th className="r">Эффект RaaS</th><th>Вывод</th><th>Версии</th><th /></tr></thead>
                  <tbody>{project.scenarios.map(s => (
                    <tr key={s.id}>
                      <td>{s.title}</td><td style={{ fontSize: 12 }}>{s.summary.solution_name}</td>
                      <td className="r">{s.summary.fleet}</td>
                      <td className="r num">{mln(s.summary.scenarios.purchase.capex_total)}</td>
                      <td className="r num">{mln(s.summary.scenarios.purchase.annual_effect)}</td>
                      <td className="r">{years(s.summary.scenarios.purchase.payback_years)}</td>
                      <td className="r num">{mln(s.summary.scenarios.raas.annual_effect)}</td>
                      <td style={{ fontSize: 12 }}>{s.summary.recommendation}</td>
                      <td className="muted" style={{ fontSize: 11 }}>каталог {s.catalog_version}<br />модель {s.model_version}</td>
                      <td><button className="btn ghost small danger" onClick={() => removeScenario(s.id)}>удалить</button></td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
      <div className="stepfoot"><button className="btn" onClick={onBack}>← Назад</button></div>
    </div>
  )
}

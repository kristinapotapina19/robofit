import { ObjectIcon } from '../components/ui.jsx'

export default function ObjectStep({ objectTypes, objectType, profileCode, onSelect, onNext }) {
  const current = objectTypes.find(o => o.code === objectType)
  return (
    <div>
      <div className="card">
        <div className="card-head">
          <div>
            <h2>Шаг 1. Выберите отрасль и тип объекта</h2>
            <p>Для склада, аэропорта и медучреждения загружены демонстрационные данные организатора — расчёт можно выполнить сразу, без ввода параметров.</p>
          </div>
        </div>
        <div className="objgrid">
          {objectTypes.map(o => (
            <button key={o.code} className={`objcard ${o.code === objectType ? 'on' : ''}`}
              onClick={() => onSelect(o.code, o.profiles[0]?.code)}>
              <div className="ico"><ObjectIcon code={o.code} /></div>
              <div><small>{o.industry}</small><h3>{o.title}</h3></div>
              <p className="muted" style={{ fontSize: 12.5 }}>{o.description}</p>
              <span className={`badge ${o.code === 'custom' ? '' : 'good'}`}>
                {o.code === 'custom' ? 'Параметры задаёт пользователь' : 'Есть демо-датасет'}
              </span>
            </button>
          ))}
        </div>
      </div>

      {current && (
        <div className="card">
          <div className="card-head">
            <div>
              <h3>Какую операцию роботизируем?</h3>
              <p>Операция определяет, откуда берётся объём работы, в каких единицах считается производительность и какой персонал высвобождается.</p>
            </div>
          </div>
          <div className="opgrid">
            {current.profiles.map(p => (
              <button key={p.code} className={`opcard ${p.code === profileCode ? 'on' : ''}`}
                onClick={() => onSelect(objectType, p.code)}>
                <b>{p.title}</b>
                <p>{p.note}</p>
                <div className="row mt-s">
                  <span className="badge accent">{p.unit}</span>
                  <span className="badge">{p.mode === 'area' ? 'уборка по участкам' : p.mode === 'stationary' ? 'стационарная система' : 'мобильные роботы'}</span>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="stepfoot">
        <span className="muted">{current ? `${current.title}: источник данных — ${current.data_source}` : ''}</span>
        <button className="btn primary" disabled={!profileCode} onClick={onNext}>Далее: параметры объекта →</button>
      </div>
    </div>
  )
}

const nf = (d) => new Intl.NumberFormat('ru-RU', { maximumFractionDigits: d, minimumFractionDigits: 0 })

export const fmt = (v, d = 0) => (v === null || v === undefined || Number.isNaN(v)) ? '—' : nf(d).format(v)
export const mln = (v, d = 1) => (v === null || v === undefined) ? '—' : nf(d).format(v / 1e6)
export const rub = (v) => (v === null || v === undefined) ? '—' : `${nf(0).format(v)} ₽`
export const pct = (v, d = 0) => (v === null || v === undefined) ? '—' : `${nf(d).format(v * 100)}%`
export const years = (v) => (v === null || v === undefined) ? 'не окупается' : `${nf(1).format(v)} ${plural(v, 'год', 'года', 'лет')}`

export function plural(n, one, few, many) {
  const x = Math.abs(Math.floor(n)) % 100
  const y = x % 10
  if (!Number.isInteger(n)) return few
  if (x > 10 && x < 20) return many
  if (y > 1 && y < 5) return few
  if (y === 1) return one
  return many
}

export const STATUS = { operation: 'В эксплуатации', piloting: 'Пилот', rnd: 'НИОКР' }
export const VERDICT = { fit: 'Подходит', check_needed: 'Требует проверки', excluded: 'Исключено' }
export const VERDICT_CLASS = { fit: 'good', check_needed: 'warn', excluded: 'bad' }
export const SCEN_COLOR = { baseline: 'var(--s-base)', purchase: 'var(--s-buy)', raas: 'var(--s-raas)' }
export const SCEN_SHORT = { baseline: 'Без роботизации', purchase: 'Покупка', raas: 'RaaS (подписка)' }

export const SPEC_LABELS = {
  payload_kg: ['Грузоподъёмность', 'кг'],
  speed_ms: ['Скорость', 'м/с'],
  runtime_h: ['Автономность', 'ч'],
  charge_min: ['Зарядка', 'мин'],
  charge_h: ['Зарядка', 'ч'],
  throughput_per_h: ['Производительность', ''],
  throughput_unit: ['Ед. производительности', ''],
  width_mm: ['Ширина', 'мм'],
  length_mm: ['Длина', 'мм'],
  height_mm: ['Высота', 'мм'],
  robot_mass_kg: ['Масса робота', 'кг'],
  navigation: ['Навигация', ''],
  positioning_mm: ['Точность позиционирования', 'мм'],
  min_aisle_mm: ['Мин. ширина прохода', 'мм'],
  lift_height_mm: ['Высота подъёма', 'мм'],
  tank_l: ['Бак', 'л'],
  cleaning_width_cm: ['Ширина уборки', 'см'],
  range_km: ['Запас хода', 'км'],
  battery_kwh: ['Батарея', 'кВт·ч'],
  pallets_capacity: ['Вместимость', 'паллет'],
  max_rack_height_m: ['Макс. высота стеллажа', 'м'],
}

export const ASSUMPTION_LABELS = {
  infrastructure_share: 'Инфраструктура (доля от оборудования)',
  software_share: 'ПО управления парком (доля)',
  integration_share: 'Интеграция с WMS/ERP (доля)',
  commissioning_share: 'Пусконаладка (доля)',
  training_share: 'Обучение персонала (доля)',
  contingency_share: 'Резерв CAPEX (доля)',
  service_share: 'Сервисный контракт, в год (доля)',
  spares_share: 'Расходники и ремонт, в год (доля)',
  license_share: 'Лицензии ПО, в год (доля от ПО)',
  power_price: 'Тариф на электроэнергию',
  robot_power_kw: 'Потребление робота',
  operators_per_10_robots: 'Операторов на 10 роботов',
  operator_salary_month: 'З/п оператора парка',
  payroll_factor: 'Коэффициент начислений на ФОТ',
  utilization: 'Коэффициент загрузки',
  availability: 'Коэффициент готовности',
  reserve: 'Резерв парка',
  traffic_factor: 'Замедление на маршруте',
  default_speed_ms: 'Скорость по умолчанию',
  default_runtime_h: 'Автономность по умолчанию',
  default_charge_min: 'Зарядка по умолчанию',
  robots_per_charger: 'Роботов на зарядную станцию',
  depreciation_years: 'Срок амортизации',
  horizon_years: 'Горизонт расчёта',
  component_replacement_year: 'Год замены компонентов',
  component_replacement_share: 'Замена компонентов (доля)',
  raas_monthly_share: 'Ставка RaaS в месяц (доля)',
  raas_onboarding_share: 'Подключение RaaS (доля)',
}

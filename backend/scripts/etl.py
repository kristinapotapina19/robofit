"""
ETL: исходные файлы организатора -> нормализованные JSON для загрузки в БД.

Запуск:  python scripts/etl.py
Вход:    data/raw/catalog_export_v4.csv, data/raw/datasets.xlsx
Выход:   data/seed/solutions.json, data/seed/object_presets.json, data/seed/etl_report.json

Важно: все извлечённые характеристики помечаются признаком происхождения
(source = "catalog" | "parsed_from_name" | "parsed_from_description" | "manual")
и confirmed=False, если значение вытащено парсером. Это требование п. 3.3.4 ТЗ.
"""
import json
import re
import unicodedata
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

BASE = Path(__file__).resolve().parents[1]
RAW = BASE / "data" / "raw"
SEED = BASE / "data" / "seed"
SEED.mkdir(parents=True, exist_ok=True)

NBSP = "\u00a0"
CATALOG_DATE = "2026-09-20"      # дата выгрузки каталога организатора


# --------------------------------------------------------------------------
# каталог решений
# --------------------------------------------------------------------------
def parse_price(value) -> float | None:
    """'2 700 000,00' -> 2700000.0"""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).replace(NBSP, " ").replace(" ", "").replace(",", ".")
    s = re.sub(r"[^\d.]", "", s)
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def norm(text) -> str:
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return ""
    return unicodedata.normalize("NFKC", str(text)).replace(NBSP, " ").strip()


PAYLOAD_RE = re.compile(
    r"грузоподъ[её]мност[ьи][^.;)]*?(\d[\d\s.,]*)\s*(кг|т\b|тонн)", re.IGNORECASE)
PAYLOAD_SHORT_RE = re.compile(r"(?:до\s*)?(\d[\d\s.,]*)\s*кг", re.IGNORECASE)
SPEED_RE = re.compile(r"скорост[ьи][^.;)]*?(\d[\d.,]*)\s*(м/с|км/ч)", re.IGNORECASE)
RUNTIME_RE = re.compile(
    r"(?:автономност[ьи]|время\s+работы|работа\s+без\s+подзарядки)[^.;)]*?(\d[\d.,]*)\s*(ч|час)",
    re.IGNORECASE)
PERF_RE = re.compile(r"(\d[\d\s]*)\s*(?:посылок|коробов|заказов|операций|строк)\s*/?\s*(час|ч\b)",
                     re.IGNORECASE)

NAVIGATION_HINTS = {
    "SLAM": ["slam"],
    "Лидар": ["лидар", "lidar"],
    "Магнитная лента": ["магнитн", "лент"],
    "QR / метки": ["qr", "метк", "маркер"],
    "Компьютерное зрение": ["компьютерн", "техническ", "зрени"],
}


def to_number(raw: str) -> float | None:
    s = raw.replace(NBSP, " ").replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


REFERENCE = json.loads((RAW / "reference_specs.json").read_text(encoding="utf-8"))


def reference_specs(name: str, subtype: str) -> dict:
    """ТТХ из документа организатора «Примеры решений по типам объектов».
    Сначала ищем точную модель, иначе берём типовые значения по подтипу."""
    low = name.lower()
    for entry in REFERENCE["models"]:
        if any(token in low for token in entry["match"]):
            return {k: {"value": v, "unit": None, "confirmed": True,
                        "source": f"Паспортные ТТХ {entry['model']} "
                                  f"(документ организатора «Примеры решений»)"}
                    for k, v in entry["specs"].items()}
    defaults = REFERENCE["subtype_defaults"].get(subtype)
    if defaults:
        return {k: {"value": v, "unit": None, "confirmed": False,
                    "source": f"Типовое значение для подтипа «{subtype}» "
                              f"(документ организатора). Уточнить у вендора"}
                for k, v in defaults.items()}
    return {}


def extract_specs(name: str, description: str) -> dict:
    """Вытаскивает ТТХ из названия и описания. Каждое значение с источником."""
    specs: dict[str, dict] = {}

    def put(key, value, unit, source):
        if value is not None and key not in specs:
            specs[key] = {"value": value, "unit": unit, "source": source, "confirmed": False}

    m = PAYLOAD_RE.search(name)
    if m:
        v = to_number(m.group(1))
        if v is not None:
            put("payload_kg", v * 1000 if m.group(2).lower().startswith("т") else v,
                "кг", "parsed_from_name")
    if "payload_kg" not in specs:
        m = PAYLOAD_RE.search(description)
        if m:
            v = to_number(m.group(1))
            if v is not None:
                put("payload_kg", v * 1000 if m.group(2).lower().startswith("т") else v,
                    "кг", "parsed_from_description")
    if "payload_kg" not in specs:
        m = PAYLOAD_SHORT_RE.search(name)
        if m:
            put("payload_kg", to_number(m.group(1)), "кг", "parsed_from_name")

    for text, src in ((name, "parsed_from_name"), (description, "parsed_from_description")):
        m = SPEED_RE.search(text)
        if m:
            v = to_number(m.group(1))
            if v is not None:
                put("speed_ms", round(v / 3.6, 2) if m.group(2).lower() == "км/ч" else v,
                    "м/с", src)
        m = RUNTIME_RE.search(text)
        if m:
            put("runtime_h", to_number(m.group(1)), "ч", src)
        m = PERF_RE.search(text)
        if m:
            put("throughput_per_h", to_number(m.group(1)), "оп./ч", src)

    haystack = (name + " " + description).lower()
    for label, keys in NAVIGATION_HINTS.items():
        if all(k in haystack for k in keys[:1]):
            specs.setdefault("navigation", {"value": label, "unit": None,
                                            "source": "parsed_from_description",
                                            "confirmed": False})
            break
    return specs


# сценарии каталога -> типы объектов, к которым они применимы.
# Таблица соответствия — единственное место, где задаётся привязка каталога к
# объектам: новый тип объекта добавляется строкой, ядро не меняется (п. 4.2.6).
SCENARIO_OBJECTS = {
    "Внутрискладская логистика": {"warehouse", "clinic"},
    "Внутрипроизводственная логистика": {"warehouse"},
    "Сортировка грузов": {"warehouse", "airport"},
    "Уборка помещений": {"warehouse", "airport", "clinic"},
    "Погрузочно-разгрузочные работы": {"warehouse"},
    "Инвентаризация склада": {"warehouse"},
    "Перевозка грузов на закрытых площадках": {"airport", "warehouse"},
    "Мониторинг": {"airport"},
    "Мониторинг и патрулирование": {"airport"},
    "Патрулирование территории": {"airport"},
    "Администрирование торгового зала": {"airport", "clinic"},
    "Уборка улиц": {"airport"},
    "Доставка внутри здания": {"clinic"},
}


def object_types_for(scenarios: list[str]) -> list[str]:
    out: set[str] = set()
    for sc in scenarios:
        out |= SCENARIO_OBJECTS.get(sc, set())
    return sorted(out)


def build_solutions() -> list[dict]:
    """Каталог организатора содержит одну и ту же позицию несколько раз — по строке
    на каждый сценарий применения (223 строки, 187 уникальных id). Строки с одним id
    объединяются в одно решение со списком сценариев, иначе при загрузке в БД
    с уникальным ключом часть сценариев теряется."""
    df = pd.read_csv(RAW / "catalog_export_v4.csv", sep=";", encoding="utf-8-sig")
    by_id: dict[str, dict] = {}
    for _, row in df.iterrows():
        ext_id = norm(row["id"])
        scenario = norm(row["Сценарий"]).replace("\r", " ").replace("\n", " ")
        scenario = re.sub(r"\s+", " ", scenario)
        industry = norm(row["Отрасль"])
        if ext_id in by_id:
            item = by_id[ext_id]
            if scenario and scenario not in item["scenarios"]:
                item["scenarios"].append(scenario)
            if industry and industry not in item["industries"]:
                item["industries"].append(industry)
            item["object_types"] = object_types_for(item["scenarios"])
            continue
        name = norm(row["Название"])
        description = norm(row["описание"])
        by_id[ext_id] = {
            "external_id": ext_id,
            "name": name,
            "vendor": norm(row["компания"]).replace('""', '"'),
            "kind": norm(row["тип"]),                    # bas / brs / software
            "status": norm(row["статус"]),               # operation / piloting / rnd
            "group": norm(row["Тип"]),                   # Мобильные роботы и т.д.
            "subtype": norm(row["Подтип"]),
            "scenario": scenario,
            "scenarios": [scenario] if scenario else [],
            "industry": industry,
            "industries": [industry] if industry else [],
            "region": norm(row["Регион"]),
            "country": "Россия",
            "trl": None if pd.isna(row["УГТ"]) else int(row["УГТ"]),
            "market_potential": None if pd.isna(row["Рын Потенциал"]) else float(row["Рын Потенциал"]),
            "description": description,
            "cases": norm(row["Кейсы"]),
            "price_rub": parse_price(row["Цена изделия"]),
            "price_note": "Цена каталога организатора, с НДС; без доставки, пусконаладки "
                          "и глубокой интеграции (пояснения к ТЗ, п. 6)",
            "object_types": object_types_for([scenario]),
            "specs": {**reference_specs(name, norm(row["Подтип"])),
                      **extract_specs(name, description)},
            "data_source": "Каталог организатора catalog_export_v4",
            "source_url": None,
            "updated_at": CATALOG_DATE,
        }
    return list(by_id.values())


def open_source_solutions() -> list[dict]:
    """Решения, добавленные командой из открытых источников (пояснения к ТЗ, п. 3.2):
    не более нескольких позиций на тип объекта, у каждой ТТХ — ссылка и дата."""
    data = json.loads((RAW / "open_sources.json").read_text(encoding="utf-8"))
    out = []
    for item in data["solutions"]:
        specs = {k: {"value": v, "unit": None, "confirmed": True,
                     "source": item["source_url"]}
                 for k, v in item["specs"].items()}
        out.append({
            "external_id": item["external_id"],
            "name": item["name"], "vendor": item["vendor"], "kind": "brs",
            "status": item["status"], "group": "Мобильные роботы",
            "subtype": item["subtype"], "scenario": item["scenarios"][0],
            "scenarios": item["scenarios"], "industry": item["industry"],
            "industries": [item["industry"]], "region": "", "country": item["country"],
            "trl": item.get("trl"), "market_potential": None,
            "description": item["description"], "cases": item.get("cases", ""),
            "price_rub": item["price_rub"], "price_note": item["price_note"],
            "object_types": object_types_for(item["scenarios"]),
            "specs": specs,
            "data_source": "Открытые источники (добавлено командой)",
            "source_url": item["source_url"],
            "updated_at": item["retrieved_at"],
        })
    return out


# --------------------------------------------------------------------------
# демо-датасеты объектов
# --------------------------------------------------------------------------
SHEET_TO_CODE = {"Склад": "warehouse", "Аэропорт": "airport", "Медучреждение": "clinic"}


def slugify(label: str, used: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", label.lower().translate(TRANSLIT)).strip("_")[:48] or "param"
    slug, i = base, 2
    while slug in used:
        slug, i = f"{base}_{i}", i + 1
    used.add(slug)
    return slug


TRANSLIT = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "c",
    "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e",
    "ю": "yu", "я": "ya",
})


def to_value(cell):
    if cell is None:
        return None
    if isinstance(cell, (int, float)):
        return cell
    s = norm(cell)
    return s or None


def build_presets() -> dict:
    wb = load_workbook(RAW / "datasets.xlsx", read_only=True, data_only=True)
    presets = {}
    for sheet, code in SHEET_TO_CODE.items():
        if sheet not in wb.sheetnames:
            continue
        ws = wb[sheet]
        rows = list(ws.iter_rows(values_only=True))
        section, params, used = None, [], set()
        for row in rows:
            cells = [to_value(c) for c in row]
            if not cells or all(c is None for c in cells):
                continue
            first = cells[0]
            if not isinstance(first, str):
                continue
            if first.startswith("▌"):                       # заголовок раздела
                section = first.replace("▌", "").strip()
                continue
            if first.startswith("ДЕМО-ДАТАСЕТ") or first == "Параметр":
                continue
            params.append({
                "code": slugify(first, used),
                "label": first,
                "section": section,
                "unit": cells[1] if len(cells) > 1 else None,
                "default": cells[2] if len(cells) > 2 else None,
                "min": cells[3] if len(cells) > 3 else None,
                "max": cells[4] if len(cells) > 4 else None,
                "source_note": cells[5] if len(cells) > 5 else None,
            })
        presets[code] = {
            "code": code,
            "title": sheet,
            "parameters": params,
            "data_source": "Демо-датасет организатора, лист «%s»" % sheet,
        }
    presets["custom"] = custom_preset()
    return presets


CUSTOM_PARAMS = [
    # раздел, параметр, ед., по умолчанию, мин, макс, пояснение
    ("ОБЩИЕ ПАРАМЕТРЫ ОБЪЕКТА", "Тип объекта (описание)", "-", "Производственный цех", None, None, "Свободное описание объекта"),
    ("ОБЩИЕ ПАРАМЕТРЫ ОБЪЕКТА", "Площадь объекта", "м2", 8000, 500, 200000, "Площадь зоны, где будут работать роботы"),
    ("ОБЩИЕ ПАРАМЕТРЫ ОБЪЕКТА", "Ширина проходов", "м", 2.5, 1, 6, "Минимальная ширина проходов на маршруте"),
    ("РЕЖИМ РАБОТЫ", "Количество смен в сутки", "смен", 2, 1, 3, None),
    ("РЕЖИМ РАБОТЫ", "Продолжительность смены", "ч", 8, 4, 12, None),
    ("РЕЖИМ РАБОТЫ", "Рабочих дней в году", "дн.", 250, 200, 365, None),
    ("РЕЖИМ РАБОТЫ", "Пиковый коэффициент нагрузки", "-", 1.3, 1, 3, "Отношение нагрузки в пиковый час к средней"),
    ("ОПЕРАЦИИ", "Объём перемещений в сутки", "рейсов/сут", 600, 10, 50000, "Сколько раз в сутки груз перевозится из точки А в точку Б"),
    ("ОПЕРАЦИИ", "Средняя масса перемещаемого груза", "кг", 300, 1, 3000, None),
    ("ОПЕРАЦИИ", "Средняя длина маршрута в одну сторону", "м", 100, 10, 2000, None),
    ("ПЕРСОНАЛ", "Численность персонала на операции", "чел.", 12, 1, 500, "Сотрудники, чью работу может взять робот"),
    ("ПЕРСОНАЛ", "Средняя з/п сотрудника (gross)", "руб./мес.", 80000, 30000, 250000, None),
    ("ПЕРСОНАЛ", "Коэффициент начислений на ФОТ", "-", 1.302, 1.302, 1.302, "Страховые взносы 30,2%"),
    ("ФИНАНСЫ", "Планируемый бюджет на роботизацию (CAPEX)", "млн руб.", 30, 1, 500, None),
    ("ФИНАНСЫ", "Горизонт расчёта окупаемости", "лет", 5, 3, 10, "Не менее 5 лет по ТЗ"),
]


def custom_preset() -> dict:
    used: set[str] = set()
    return {
        "code": "custom",
        "title": "Другой объект",
        "parameters": [{
            "code": slugify(label, used), "label": label, "section": section, "unit": unit,
            "default": default, "min": mn, "max": mx, "source_note": note,
        } for section, label, unit, default, mn, mx, note in CUSTOM_PARAMS],
        "data_source": "Произвольный объект: значения по умолчанию — пример, задаются пользователем",
    }


def main() -> None:
    solutions = build_solutions() + open_source_solutions()
    presets = build_presets()

    (SEED / "solutions.json").write_text(
        json.dumps(solutions, ensure_ascii=False, indent=2), encoding="utf-8")
    (SEED / "object_presets.json").write_text(
        json.dumps(presets, ensure_ascii=False, indent=2), encoding="utf-8")

    with_price = sum(1 for s in solutions if s["price_rub"])
    with_payload = sum(1 for s in solutions if "payload_kg" in s["specs"])
    with_throughput = sum(1 for s in solutions if "throughput_per_h" in s["specs"])
    confirmed = sum(1 for s in solutions
                    if any(v.get("confirmed") for v in s["specs"].values()))
    import hashlib
    digest = hashlib.sha1()
    for f in ("catalog_export_v4.csv", "datasets.xlsx", "reference_specs.json", "open_sources.json"):
        digest.update((RAW / f).read_bytes())
    report = {
        "catalog_version": digest.hexdigest()[:10],
        "solutions_total": len(solutions),
        "from_open_sources": sum(1 for s in solutions if s["source_url"]),
        "with_price": with_price,
        "with_payload": with_payload,
        "with_throughput": with_throughput,
        "with_confirmed_specs": confirmed,
        "by_object_type": {
            code: sum(1 for s in solutions if code in s["object_types"])
            for code in ("warehouse", "airport", "clinic", "custom")
        },
        "presets": {code: len(p["parameters"]) for code, p in presets.items()},
        "gaps": {
            "payload_missing": len(solutions) - with_payload,
            "comment": "Недостающие обязательные ТТХ добиваются вручную через админку "
                       "с указанием источника (п. 3.3.3-3.3.5 ТЗ).",
        },
    }
    (SEED / "etl_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

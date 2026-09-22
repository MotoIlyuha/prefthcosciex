"""Task 3 — a question about three linked tables (a small relational database).

The trap is never the arithmetic: it is the four filters hidden in one sentence, and
the difference between pieces and packs. An instance is released only when the
"typical mistake" answers — pieces instead of packs, the wrong operation type, the
period read exclusively — all differ from the correct one, so a misread gives a
visibly different number rather than a near miss.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from egegen.core.errors import GenerationFailed
from egegen.core.generator import Generator
from egegen.core.registry import register
from egegen.core.rng import Rng
from egegen.core.tables import preview, to_csv, to_ods_multi
from egegen.core.templates import render
from egegen.core.types import Attachment, Instance, Uniqueness

DEPARTMENTS = [
    "Бакалея", "Молоко", "Овощи", "Напитки", "Кондитерские изделия",
    "Хлеб", "Заморозка", "Бытовая химия",
]
DISTRICTS = ["Центральный", "Северный", "Южный", "Заречный"]
PRODUCT_WORDS = [
    "Гречка", "Рис", "Сахар", "Молоко", "Кефир", "Сыр", "Морковь", "Картофель",
    "Яблоки", "Сок", "Вода", "Чай", "Печенье", "Конфеты", "Батон", "Булочки",
    "Пельмени", "Мороженое", "Порошок", "Мыло", "Гель", "Салфетки",
]
OPERATIONS = ["Поступление", "Продажа"]
MOVEMENT_HEADER = ["Дата", "Артикул", "Магазин", "Операция", "Количество"]
PRODUCT_HEADER = ["Артикул", "Название", "Отдел", "В упаковке", "Цена"]
SHOP_HEADER = ["ID", "Название", "Район"]


class Task03(Generator):
    task_no = 3
    answer_kind = "int"
    checker = "exact"
    uniqueness = Uniqueness.FUNCTIONAL
    generation_budget_ms = 500

    def build(self, rng: Rng, difficulty: int, subtype: str) -> Instance:
        for _ in range(30):
            candidate = self._attempt(rng, difficulty, subtype)
            if candidate is not None:
                return candidate
            rng = rng.fork("retry")
        raise GenerationFailed(f"t03/{subtype}: no instance with a distinguishing answer")

    def _attempt(self, rng: Rng, difficulty: int, subtype: str) -> Instance | None:
        products, shops, movements = self._random_database(rng, difficulty)
        start = date(2026, 10, 1)
        period_from = start + timedelta(days=rng.randint(0, 8))
        period_to = period_from + timedelta(days=rng.randint(5, 14))
        query: dict[str, Any] = {
            "department": rng.choice(DEPARTMENTS),
            "district": rng.choice(DISTRICTS),
            "operation": rng.choice(OPERATIONS),
            "from": period_from.isoformat(),
            "to": period_to.isoformat(),
        }
        meta: dict[str, Any] = {
            "subtype": subtype,
            "question": {
                "3.1_sum_quantity": "pieces",
                "3.2_packs": "packs",
                "3.3_revenue": "revenue",
                "3.4_difference": "difference",
                "3.5_change": "change",
            }.get(subtype),
            "products": products,
            "shops": shops,
            "movements": movements,
            "query": query,
        }
        if meta["question"] is None:
            return None

        answer = self.solve_fast(meta)
        if not 5 <= int(answer) <= 10**9:
            return None
        if not self._distinguishable(meta, int(answer)):
            return None

        movement_rows = [MOVEMENT_HEADER, *movements]
        product_rows = [PRODUCT_HEADER, *products]
        shop_rows = [SHOP_HEADER, *shops]
        template = self.templates.pick(rng, subtype)
        statement = render(
            template,
            department=query["department"],
            district=query["district"],
            operation=query["operation"].lower(),
            date_from=self._ru_date(period_from),
            date_to=self._ru_date(period_to),
            rows=len(movements),
            preview=preview(movement_rows, limit=5),
        )
        return Instance(
            task_no=self.task_no,
            subtype=subtype,
            difficulty=difficulty,
            seed=0,
            statement_md=statement,
            answer=answer,
            solution_steps=self._solution(meta, answer),
            reference_code=self._reference_code(meta),
            template_id=template.id,
            assets=[
                Attachment("3-movement.csv", "text/csv", "csv", to_csv(movement_rows)),
                Attachment("3-products.csv", "text/csv", "csv", to_csv(product_rows)),
                Attachment("3-shops.csv", "text/csv", "csv", to_csv(shop_rows)),
                Attachment(
                    "3.ods",
                    "application/vnd.oasis.opendocument.spreadsheet",
                    "ods",
                    to_ods_multi(
                        {
                            "Движение товаров": movement_rows,
                            "Товары": product_rows,
                            "Магазины": shop_rows,
                        }
                    ),
                ),
            ],
            meta=meta,
        )

    def _random_database(
        self, rng: Rng, difficulty: int
    ) -> tuple[list[list[Any]], list[list[Any]], list[list[Any]]]:
        products: list[list[Any]] = []
        article = 1000
        for department in DEPARTMENTS:
            for _ in range(rng.randint(6, 10)):
                article += rng.randint(1, 7)
                products.append(
                    [
                        article,
                        rng.choice(PRODUCT_WORDS),
                        department,
                        rng.choice([4, 6, 8, 10, 12, 20, 24]),
                        rng.randint(20, 900),
                    ]
                )
        shops: list[list[Any]] = []
        for i in range(rng.randint(6, 9)):
            shops.append([100 + i, f"Магазин №{100 + i}", rng.choice(DISTRICTS)])

        count = 300 + difficulty * 180
        start = date(2026, 10, 1)
        movements: list[list[Any]] = []
        for _ in range(count):
            product = rng.choice(products)
            shop = rng.choice(shops)
            movements.append(
                [
                    (start + timedelta(days=rng.randint(0, 29))).isoformat(),
                    product[0],
                    shop[0],
                    rng.choice(OPERATIONS),
                    rng.randint(1, 40) * product[3],
                ]
            )
        movements.sort(key=lambda row: (row[0], row[1]))
        return products, shops, movements

    def _ru_date(self, value: date) -> str:
        months = [
            "января", "февраля", "марта", "апреля", "мая", "июня",
            "июля", "августа", "сентября", "октября", "ноября", "декабря",
        ]
        return f"{value.day} {months[value.month - 1]} {value.year} года"

    # -- solving ------------------------------------------------------------
    def _matches(self, row: list[Any], meta: dict[str, Any], by_article: dict[int, list[Any]],
                 by_shop: dict[int, list[Any]], *, operation: str | None = None,
                 inclusive: bool = True) -> bool:
        query = meta["query"]
        day, article, shop_id, op, _ = row
        product = by_article[article]
        shop = by_shop[shop_id]
        if product[2] != query["department"] or shop[2] != query["district"]:
            return False
        if op != (operation if operation is not None else query["operation"]):
            return False
        if inclusive:
            return query["from"] <= day <= query["to"]
        return query["from"] < day < query["to"]

    def solve_fast(self, meta: dict[str, Any]) -> str:
        """Index the two reference tables, then make a single pass over movements."""
        by_article = {row[0]: row for row in meta["products"]}
        by_shop = {row[0]: row for row in meta["shops"]}
        total = 0
        for row in meta["movements"]:
            if meta["question"] in ("difference", "change"):
                if not self._matches(row, meta, by_article, by_shop, operation="Поступление") \
                        and not self._matches(row, meta, by_article, by_shop, operation="Продажа"):
                    continue
                sign = 1 if row[3] == "Поступление" else -1
                total += sign * row[4]
                continue
            if not self._matches(row, meta, by_article, by_shop):
                continue
            match meta["question"]:
                case "pieces":
                    total += row[4]
                case "packs":
                    total += row[4] // by_article[row[1]][3]
                case "revenue":
                    total += (row[4] // by_article[row[1]][3]) * by_article[row[1]][4]
        return str(abs(total))

    def solve_naive(self, meta: dict[str, Any]) -> str | None:
        """No dictionaries: look every reference row up by scanning, as in a spreadsheet."""
        query = meta["query"]
        total = 0
        for day, article, shop_id, op, quantity in meta["movements"]:
            product = next(p for p in meta["products"] if p[0] == article)
            shop = next(s for s in meta["shops"] if s[0] == shop_id)
            if product[2] != query["department"]:
                continue
            if shop[2] != query["district"]:
                continue
            if not (query["from"] <= day <= query["to"]):
                continue
            if meta["question"] in ("difference", "change"):
                total += quantity if op == "Поступление" else -quantity
                continue
            if op != query["operation"]:
                continue
            match meta["question"]:
                case "pieces":
                    total += quantity
                case "packs":
                    total += quantity // product[3]
                case "revenue":
                    total += (quantity // product[3]) * product[4]
        return str(abs(total))

    def _distinguishable(self, meta: dict[str, Any], answer: int) -> bool:
        """Every classic misreading must land on a different number.

        Otherwise a student who read "штук" instead of "упаковок" would be marked
        correct, and the task would measure nothing.
        """
        variants: list[int] = []
        by_article = {row[0]: row for row in meta["products"]}
        by_shop = {row[0]: row for row in meta["shops"]}
        # Pieces instead of packs (and the other way round).
        other_unit = 0
        for row in meta["movements"]:
            if self._matches(row, meta, by_article, by_shop):
                other_unit += (
                    row[4] * by_article[row[1]][3]
                    if meta["question"] == "packs"
                    else row[4] // by_article[row[1]][3]
                )
        variants.append(other_unit)
        # The opposite operation type.
        flipped = 0
        opposite = "Продажа" if meta["query"]["operation"] == "Поступление" else "Поступление"
        for row in meta["movements"]:
            if self._matches(row, meta, by_article, by_shop, operation=opposite):
                flipped += row[4]
        variants.append(flipped)
        # The period read exclusively rather than inclusively.
        exclusive = 0
        for row in meta["movements"]:
            if self._matches(row, meta, by_article, by_shop, inclusive=False):
                exclusive += row[4]
        variants.append(exclusive)
        return all(v != answer for v in variants)

    # -- explanation --------------------------------------------------------
    def _reference_code(self, meta: dict[str, Any]) -> str:
        query = meta["query"]
        amount = {
            "pieces": "q",
            "packs": "q // pack",
            "revenue": "(q // pack) * price",
            "difference": "q if op == 'Поступление' else -q",
            "change": "q if op == 'Поступление' else -q",
        }[meta["question"]]
        op_filter = (
            ""
            if meta["question"] in ("difference", "change")
            else f"    if op != '{query['operation']}': continue\n"
        )
        return (
            "import csv\n\n"
            "product = {}\n"
            "for a, name, dep, pack, price in list(csv.reader(open('3-products.csv')))[1:]:\n"
            "    product[a] = (dep, int(pack), int(price))\n"
            "shop = {}\n"
            "for sid, name, district in list(csv.reader(open('3-shops.csv')))[1:]:\n"
            "    shop[sid] = district\n\n"
            "total = 0\n"
            "for day, art, sid, op, qty in list(csv.reader(open('3-movement.csv')))[1:]:\n"
            "    dep, pack, price = product[art]\n"
            "    q = int(qty)\n"
            f"    if dep != '{query['department']}': continue\n"
            f"    if shop[sid] != '{query['district']}': continue\n"
            f"    if not ('{query['from']}' <= day <= '{query['to']}'): continue\n"
            + op_filter
            + f"    total += {amount}\n"
            "print(abs(total))\n"
        )

    def _solution(self, meta: dict[str, Any], answer: str) -> list[str]:
        query = meta["query"]
        filters = [
            f"отдел — «{query['department']}»",
            f"район — «{query['district']}»",
            f"период с {query['from']} по {query['to']} **включительно**",
        ]
        if meta["question"] not in ("difference", "change"):
            filters.append(f"операция — «{query['operation']}»")
        unit_note = {
            "pieces": "Количество в файле указано **в штуках** — его и суммируем.",
            "packs": "Количество в файле указано в штуках, а спрашивают **упаковки**: "
            "делим на «В упаковке» из справочника товаров.",
            "revenue": "Цена в справочнике указана **за упаковку**, поэтому сначала "
            "переводим штуки в упаковки, потом умножаем на цену.",
            "difference": "Складываем поступления и вычитаем продажи — это две разные "
            "операции, а не одна.",
            "change": "Изменение остатка — это поступления минус продажи за период.",
        }[meta["question"]]
        return [
            "**Шаг 1.** Выпишите на черновик **все** фильтры из условия, до того как "
            "начнёте считать:\n\n" + "\n".join(f"- {f}" for f in filters),
            "**Шаг 2.** " + unit_note,
            "**Шаг 3.** Два справочника превращаем в словари (по артикулу и по "
            "ID магазина), затем один проход по таблице движения:\n\n```python\n"
            + self._reference_code(meta)
            + "```",
            f"**Ответ:** **{answer}**.",
        ]


register(Task03())

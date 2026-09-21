"""Task 7 — volume of raster images and sound.

Everything reduces to "turn it into bits, then convert once": I = W·H·i for images,
I = f·i·t·channels for sound, and the exam's units are powers of two (1 Кбайт = 2^10
байт), except sampling frequency in kHz, which is a plain 1000.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any

from egegen.core.errors import GenerationFailed
from egegen.core.generator import Generator
from egegen.core.registry import register
from egegen.core.rng import Rng
from egegen.core.templates import render
from egegen.core.types import Instance, Uniqueness
from egegen.solvers.numbers import bits_per_symbol

BIT_UNITS: dict[str, int] = {
    "бит": 1,
    "байт": 8,
    "Кбайт": 8 * 1024,
    "Мбайт": 8 * 1024 * 1024,
    "Гбайт": 8 * 1024 * 1024 * 1024,
}
SPEED_UNITS: dict[str, int] = {
    "бит/с": 1,
    "Кбит/с": 1024,
    "Мбит/с": 1024 * 1024,
}
PALETTES = [2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 4096, 65536]


class Task07(Generator):
    task_no = 7
    answer_kind = "int"
    checker = "exact"
    uniqueness = Uniqueness.FUNCTIONAL

    def build(self, rng: Rng, difficulty: int, subtype: str) -> Instance:
        for _ in range(60):
            candidate = self._attempt(rng, difficulty, subtype)
            if candidate is not None:
                return candidate
            rng = rng.fork("retry")
        raise GenerationFailed(f"t07/{subtype}: no valid instance")

    def _attempt(self, rng: Rng, difficulty: int, subtype: str) -> Instance | None:
        builder = {
            "7.1_image_volume": self._image,
            "7.2_ratio": self._ratio,
            "7.3_sound": self._sound,
            "7.4_transfer": self._transfer,
            "7.5_palette": self._palette,
        }[subtype]
        built = builder(rng, difficulty)
        if built is None:
            return None
        meta, fields = built
        meta["subtype"] = subtype
        answer = self.solve_fast(meta)
        if not 1 <= int(answer) <= 10**9:
            return None
        template = self.templates.pick(rng, subtype)
        return Instance(
            task_no=self.task_no,
            subtype=subtype,
            difficulty=difficulty,
            seed=0,
            statement_md=render(template, **fields),
            answer=answer,
            solution_steps=self._solution(meta, answer),
            template_id=template.id,
            meta=meta,
        )

    # -- subtype builders ---------------------------------------------------
    def _image(self, rng: Rng, difficulty: int) -> tuple[dict[str, Any], dict[str, Any]] | None:
        width = rng.choice([160, 192, 256, 320, 512, 640, 800, 1024])
        height = rng.choice([120, 128, 200, 240, 256, 480, 512, 600])
        colours = rng.choice(PALETTES[: 6 + difficulty])
        total_bits = width * height * bits_per_symbol(colours)
        wanted = ["Кбайт"] if difficulty <= 3 else ["Мбайт", "Кбайт"]
        unit = self._exact_unit(total_bits, wanted)
        if unit is None:
            return None
        meta = {
            "question": "image_volume",
            "width": width,
            "height": height,
            "colours": colours,
            "unit": unit,
        }
        return meta, {
            "width": width, "height": height, "colours": colours, "unit": unit
        }

    def _ratio(self, rng: Rng, difficulty: int) -> tuple[dict[str, Any], dict[str, Any]] | None:
        scale = rng.choice([2, 4, 8])
        old_colours = rng.choice([256, 65536, 16, 4096])
        old_bits = bits_per_symbol(old_colours)
        # Below difficulty 3 the palette grows (a plain multiplication); above it the
        # palette shrinks, so the student has to divide and can lose the factor.
        new_bits = old_bits * 2 if difficulty < 3 else old_bits // rng.choice([2, 4])
        if not 1 <= new_bits <= 32:
            return None
        new_colours = 2**new_bits
        meta = {
            "question": "ratio",
            "scale": scale,
            "old_colours": old_colours,
            "new_colours": new_colours,
        }
        ratio = Fraction(scale * scale * old_bits, new_bits)
        if ratio.denominator != 1 or ratio == 1:
            return None
        return meta, {
            "scale": scale, "old_colours": old_colours, "new_colours": new_colours
        }

    def _sound(self, rng: Rng, difficulty: int) -> tuple[dict[str, Any], dict[str, Any]] | None:
        freq_khz = rng.choice([8, 16, 24, 32, 48, 64])
        depth = rng.choice([8, 16, 24, 32])
        minutes = rng.choice([1, 2, 3, 4, 5, 6, 10])
        channels = 1 if difficulty <= 2 else rng.choice([1, 2])
        bits = freq_khz * 1000 * depth * minutes * 60 * channels
        wanted = ["Кбайт"] if difficulty <= 3 else ["Мбайт", "Кбайт"]
        unit = self._exact_unit(bits, wanted)
        if unit is None:
            return None
        meta = {
            "question": "sound",
            "freq_khz": freq_khz,
            "depth": depth,
            "minutes": minutes,
            "channels": channels,
            "unit": unit,
        }
        return meta, {
            "freq": freq_khz,
            "depth": depth,
            "minutes": minutes,
            "channels": "стерео" if channels == 2 else "моно",
            "unit": unit,
        }

    def _transfer(self, rng: Rng, difficulty: int) -> tuple[dict[str, Any], dict[str, Any]] | None:
        size = rng.choice([128, 256, 512, 1024, 2048, 4096])
        size_unit = rng.choice(["Кбайт", "Мбайт"])
        speed = rng.choice([64, 128, 256, 512, 1024])
        speed_unit = "Кбит/с" if difficulty <= 3 else rng.choice(["Кбит/с", "Мбит/с"])
        meta = {
            "question": "transfer",
            "size": size,
            "size_unit": size_unit,
            "speed": speed,
            "speed_unit": speed_unit,
        }
        bits = size * BIT_UNITS[size_unit]
        rate = speed * SPEED_UNITS[speed_unit]
        if bits % rate != 0 or bits // rate < 2:
            return None
        return meta, {
            "size": size, "size_unit": size_unit, "speed": speed, "speed_unit": speed_unit
        }

    def _palette(self, rng: Rng, difficulty: int) -> tuple[dict[str, Any], dict[str, Any]] | None:
        width = rng.choice([256, 320, 512, 640])
        height = rng.choice([128, 200, 256, 480])
        unit = "Кбайт"
        budget = rng.choice([32, 64, 128, 256, 512])
        meta = {
            "question": "max_colours",
            "width": width,
            "height": height,
            "budget": budget,
            "unit": unit,
        }
        bits_available = budget * BIT_UNITS[unit]
        per_pixel = bits_available // (width * height)
        if not 1 <= per_pixel <= 24:
            return None
        return meta, {"width": width, "height": height, "budget": budget, "unit": unit}

    def _exact_unit(self, bits: int, wanted: list[str]) -> str | None:
        """First unit from ``wanted`` in which the volume is a whole number.

        The exam never asks for a fractional volume, so an instance whose numbers do
        not divide evenly is discarded rather than rounded.
        """
        for unit in wanted:
            if bits % BIT_UNITS[unit] == 0 and bits // BIT_UNITS[unit] >= 1:
                return unit
        return None

    # -- solving ------------------------------------------------------------
    def solve_fast(self, meta: dict[str, Any]) -> str:
        """Closed-form formulas, converting to the target unit exactly once."""
        match meta["question"]:
            case "image_volume":
                bits = meta["width"] * meta["height"] * bits_per_symbol(meta["colours"])
                return str(bits // BIT_UNITS[meta["unit"]])
            case "ratio":
                old_bits = bits_per_symbol(meta["old_colours"])
                new_bits = bits_per_symbol(meta["new_colours"])
                scale = meta["scale"]
                return str(scale * scale * old_bits // new_bits)
            case "sound":
                bits = (
                    meta["freq_khz"] * 1000 * meta["depth"] * meta["minutes"] * 60
                    * meta["channels"]
                )
                return str(bits // BIT_UNITS[meta["unit"]])
            case "transfer":
                bits = meta["size"] * BIT_UNITS[meta["size_unit"]]
                return str(bits // (meta["speed"] * SPEED_UNITS[meta["speed_unit"]]))
            case "max_colours":
                bits = meta["budget"] * BIT_UNITS[meta["unit"]]
                per_pixel = bits // (meta["width"] * meta["height"])
                return str(2**per_pixel)
        raise ValueError(meta["question"])

    def solve_naive(self, meta: dict[str, Any]) -> str | None:
        """Independent path: exact rational arithmetic and a linear log2 scan.

        This never calls :func:`math.log2` or an integer division shortcut, so a wrong
        constant or a missing ceiling in the fast path shows up as a mismatch.
        """
        def ceil_log2(k: int) -> int:
            bits, capacity = 0, 1
            while capacity < k:
                capacity *= 2
                bits += 1
            return bits

        def to_unit(bits: Fraction, unit: str) -> Fraction:
            value = bits
            for step in self._unit_ladder(unit):
                value = value / step
            return value

        match meta["question"]:
            case "image_volume":
                pixels = Fraction(meta["width"]) * meta["height"]
                bits = pixels * ceil_log2(meta["colours"])
                return str(int(to_unit(bits, meta["unit"])))
            case "ratio":
                old = Fraction(meta["scale"] ** 2) * ceil_log2(meta["old_colours"])
                new = Fraction(ceil_log2(meta["new_colours"]))
                value = old / new
                return str(int(value)) if value.denominator == 1 else None
            case "sound":
                samples = Fraction(meta["freq_khz"]) * 1000 * meta["minutes"] * 60
                bits = samples * meta["depth"] * meta["channels"]
                return str(int(to_unit(bits, meta["unit"])))
            case "transfer":
                bits = Fraction(meta["size"])
                for step in self._unit_ladder(meta["size_unit"]):
                    bits = bits * step
                rate = Fraction(meta["speed"])
                for step in self._unit_ladder(meta["speed_unit"]):
                    rate = rate * step
                value = bits / rate
                return str(int(value)) if value.denominator == 1 else None
            case "max_colours":
                bits = Fraction(meta["budget"])
                for step in self._unit_ladder(meta["unit"]):
                    bits = bits * step
                per_pixel = bits / (Fraction(meta["width"]) * meta["height"])
                whole = int(per_pixel)
                total = 1
                for _ in range(whole):
                    total *= 2
                return str(total)
        return None

    def _unit_ladder(self, unit: str) -> list[int]:
        """The conversion steps for a unit, spelled out instead of one constant."""
        return {
            "бит": [],
            "байт": [8],
            "Кбайт": [8, 1024],
            "Мбайт": [8, 1024, 1024],
            "Гбайт": [8, 1024, 1024, 1024],
            "бит/с": [],
            "Кбит/с": [1024],
            "Мбит/с": [1024, 1024],
        }[unit]

    def validate_answer(self, answer: str, meta: dict[str, Any]) -> None:
        if int(answer) < 1:
            raise ValueError("t07: volume must be positive")

    # -- explanation --------------------------------------------------------
    def _solution(self, meta: dict[str, Any], answer: str) -> list[str]:
        match meta["question"]:
            case "image_volume":
                i = bits_per_symbol(meta["colours"])
                pixels = meta["width"] * meta["height"]
                return [
                    f"**Шаг 1.** Бит на пиксель: i = ⌈log₂ {meta['colours']}⌉ = **{i}**.",
                    f"**Шаг 2.** Пикселей: {meta['width']} × {meta['height']} = {pixels}. "
                    f"Объём в битах: {pixels} × {i} = {pixels * i}.",
                    f"**Шаг 3.** Переводим в {meta['unit']} "
                    f"(1 {meta['unit']} = {BIT_UNITS[meta['unit']]} бит): "
                    f"{pixels * i} / {BIT_UNITS[meta['unit']]} = **{answer}**.",
                ]
            case "ratio":
                ob, nb = bits_per_symbol(meta["old_colours"]), bits_per_symbol(meta["new_colours"])
                s = meta["scale"]
                return [
                    f"**Шаг 1.** Выпишем «было/стало». Число пикселей выросло в "
                    f"{s} × {s} = {s * s} раз.",
                    f"**Шаг 2.** Бит на пиксель: было ⌈log₂ {meta['old_colours']}⌉ = {ob}, "
                    f"стало ⌈log₂ {meta['new_colours']}⌉ = {nb}.",
                    f"**Шаг 3.** Считаем отношение, а не абсолютные объёмы: "
                    f"{s * s} × {ob} / {nb} = **{answer}**.",
                ]
            case "sound":
                bits = (
                    meta["freq_khz"] * 1000 * meta["depth"] * meta["minutes"] * 60
                    * meta["channels"]
                )
                return [
                    f"**Шаг 1.** Переводим время в секунды: {meta['minutes']} мин = "
                    f"{meta['minutes'] * 60} с. Частота в герцах: {meta['freq_khz']} кГц = "
                    f"{meta['freq_khz'] * 1000} Гц (кГц — это ×1000, не ×1024).",
                    f"**Шаг 2.** I = f · i · t · каналы = {meta['freq_khz'] * 1000} × "
                    f"{meta['depth']} × {meta['minutes'] * 60} × {meta['channels']} = "
                    f"{bits} бит.",
                    f"**Шаг 3.** В {meta['unit']}: {bits} / {BIT_UNITS[meta['unit']]} = "
                    f"**{answer}**.",
                ]
            case "transfer":
                bits = meta["size"] * BIT_UNITS[meta["size_unit"]]
                rate = meta["speed"] * SPEED_UNITS[meta["speed_unit"]]
                return [
                    f"**Шаг 1.** Объём в битах: {meta['size']} {meta['size_unit']} = "
                    f"{bits} бит.",
                    f"**Шаг 2.** Скорость в битах в секунду: {meta['speed']} "
                    f"{meta['speed_unit']} = {rate} бит/с.",
                    f"**Шаг 3.** Время = объём / скорость = {bits} / {rate} = "
                    f"**{answer}** с.",
                ]
            case "max_colours":
                bits = meta["budget"] * BIT_UNITS[meta["unit"]]
                pixels = meta["width"] * meta["height"]
                per_pixel = bits // pixels
                return [
                    f"**Шаг 1.** Доступно {meta['budget']} {meta['unit']} = {bits} бит "
                    f"на {pixels} пикселей.",
                    f"**Шаг 2.** На один пиксель приходится {bits} / {pixels} = "
                    f"{per_pixel} бит (берём целую часть — больше не поместится).",
                    f"**Шаг 3.** Число цветов K = 2^i = 2^{per_pixel} = **{answer}**. "
                    "Отвечаем числом цветов, а не числом бит.",
                ]
        return []


register(Task07())

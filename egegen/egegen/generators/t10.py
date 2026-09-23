"""Task 10 — subnet masks (moved to this slot in 2027).

The 2027 answer shape is the **sum of the octets** of the address found, which is
why the transform is read from ``fipi_2027.yaml`` rather than hard-coded: if the
approved demo version in November switches back to "the address without dots", only
that YAML changes.
"""

from __future__ import annotations

import ipaddress
from typing import Any

from egegen.core.errors import GenerationFailedError
from egegen.core.fipi import load_fipi_config
from egegen.core.generator import Generator
from egegen.core.registry import register
from egegen.core.rng import Rng
from egegen.core.templates import render
from egegen.core.types import Instance, Uniqueness

ANSWER_HINT = {
    "octet_sum": "сумму числовых значений октетов найденного адреса",
    "address_no_dots": "найденный адрес без разделительных точек",
    "number": "найденное число",
}


class Task10(Generator):
    task_no = 10
    answer_kind = "int"
    checker = "exact"
    uniqueness = Uniqueness.FUNCTIONAL

    def build(self, rng: Rng, difficulty: int, subtype: str) -> Instance:
        for _ in range(80):
            candidate = self._attempt(rng, difficulty, subtype)
            if candidate is not None:
                return candidate
            rng = rng.fork("retry")
        raise GenerationFailedError(f"t10/{subtype}: no valid instance")

    def _attempt(self, rng: Rng, difficulty: int, subtype: str) -> Instance | None:
        cfg = load_fipi_config().t10
        lo, hi = max(cfg.min_prefix, 16 + difficulty), min(cfg.max_prefix, 22 + difficulty * 2)
        if subtype == "10.3_count_addresses":
            # Walking every address of the network must stay cheap on a phone, so the
            # network holds at most 4096 of them.
            lo, hi = max(lo, 20), max(hi, 20)
        if lo > hi:
            return None
        prefix = rng.randint(lo, hi)
        network = self._random_network(rng, prefix)
        meta: dict[str, Any] = {
            "subtype": subtype,
            "prefix": prefix,
            "network": str(network.network_address),
            "answer_transform": cfg.answer_transform,
        }
        fields: dict[str, Any] = {
            "answer_hint": ANSWER_HINT[cfg.answer_transform],
            "mask": str(network.netmask),
            "prefix": prefix,
        }

        match subtype:
            case "10.1_same_network":
                hosts = self._two_hosts(rng, network)
                if hosts is None:
                    return None
                a, b = hosts
                meta["question"] = "same_network"
                meta["ip1"], meta["ip2"] = a, b
                fields["ip1"], fields["ip2"] = a, b
            case "10.2_network_address":
                host = self._random_host(rng, network)
                meta["question"] = "network_address"
                meta["ip1"] = host
                fields["ip1"] = host
                fields["mask"] = str(network.netmask)
            case "10.3_count_addresses":
                ones = rng.randint(6, 14)
                meta["question"] = "count_with_ones"
                meta["ones"] = ones
                fields["ones"] = ones
                fields["network"] = str(network.network_address)
            case "10.4_find_mask":
                host = self._random_host(rng, network)
                meta["question"] = "mask_ones"
                meta["ip1"] = host
                fields["ip1"] = host
                fields["network"] = str(network.network_address)
            case "10.5_mask_byte":
                byte_index = rng.randint(2, 3)
                meta["question"] = "mask_byte"
                meta["byte_index"] = byte_index
                meta["ip1"], meta["ip2"] = self._two_hosts(rng, network) or ("", "")
                if not meta["ip1"]:
                    return None
                fields["ip1"], fields["ip2"] = meta["ip1"], meta["ip2"]
                fields["byte_index"] = {2: "второй", 3: "третий", 4: "четвёртый"}[byte_index]
            case _:
                return None

        answer = self.solve_fast(meta)
        if not answer or not 1 <= int(answer) <= 10**10:
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
            # Questions that pick an extremum over the mask length can be swept;
            # "address & mask" is a plain computation with nothing to search.
            uniqueness=(
                Uniqueness.ENUMERATED
                if meta["question"] in ("same_network", "mask_ones", "mask_byte")
                else Uniqueness.FUNCTIONAL
            ),
            meta=meta,
        )

    def _random_network(self, rng: Rng, prefix: int) -> ipaddress.IPv4Network:
        while True:
            octets = [rng.randint(1, 223), rng.randint(0, 255), rng.randint(0, 255), 0]
            if octets[0] == 127:
                continue
            addr = ".".join(str(o) for o in octets)
            return ipaddress.IPv4Network(f"{addr}/{prefix}", strict=False)

    def _random_host(self, rng: Rng, network: ipaddress.IPv4Network) -> str:
        size = network.num_addresses
        offset = rng.randint(1, max(1, size - 2))
        return str(ipaddress.ip_address(int(network.network_address) + offset))

    def _two_hosts(self, rng: Rng, network: ipaddress.IPv4Network) -> tuple[str, str] | None:
        """Two hosts far enough apart that the mask is pinned down by them."""
        size = network.num_addresses
        if size < 8:
            return None
        low = int(network.network_address) + rng.randint(1, size // 4)
        high = int(network.network_address) + rng.randint(3 * size // 4, size - 2)
        if low >= high:
            return None
        return str(ipaddress.ip_address(low)), str(ipaddress.ip_address(high))

    # -- solving ------------------------------------------------------------
    def solve_fast(self, meta: dict[str, Any]) -> str:
        """Uses the :mod:`ipaddress` module, as the method card teaches."""
        match meta["question"]:
            case "same_network":
                prefix = self._longest_common_prefix_lib(meta["ip1"], meta["ip2"])
                net = ipaddress.ip_network(f"{meta['ip1']}/{prefix}", strict=False)
                return self._transform(str(net.network_address), meta)
            case "network_address":
                net = ipaddress.ip_network(f"{meta['ip1']}/{meta['prefix']}", strict=False)
                return self._transform(str(net.network_address), meta)
            case "count_with_ones":
                net = ipaddress.ip_network(f"{meta['network']}/{meta['prefix']}", strict=False)
                target = meta["ones"]
                return str(sum(1 for addr in net if bin(int(addr)).count("1") == target))
            case "mask_ones":
                return str(self._longest_common_prefix_lib(meta["ip1"], meta["network"]))
            case "mask_byte":
                prefix = self._longest_common_prefix_lib(meta["ip1"], meta["ip2"])
                netmask = ipaddress.ip_network(f"0.0.0.0/{prefix}").netmask
                return str(int(str(netmask).split(".")[meta["byte_index"] - 1]))
        raise ValueError(meta["question"])

    def solve_naive(self, meta: dict[str, Any]) -> str | None:
        """Plain 32-bit integer arithmetic, without :mod:`ipaddress`."""

        def to_int(text: str) -> int:
            value = 0
            for part in text.split("."):
                value = value * 256 + int(part)
            return value

        def to_text(value: int) -> str:
            return ".".join(str((value >> shift) & 255) for shift in (24, 16, 8, 0))

        def mask_of(prefix: int) -> int:
            bits = 0
            for i in range(32):
                if i < prefix:
                    bits |= 1 << (31 - i)
            return bits

        def common_prefix(a: int, b: int) -> int:
            for k in range(32, -1, -1):
                if a & mask_of(k) == b & mask_of(k):
                    return k
            return 0

        match meta["question"]:
            case "same_network":
                a, b = to_int(meta["ip1"]), to_int(meta["ip2"])
                k = common_prefix(a, b)
                return self._transform(to_text(a & mask_of(k)), meta)
            case "network_address":
                a = to_int(meta["ip1"])
                return self._transform(to_text(a & mask_of(meta["prefix"])), meta)
            case "count_with_ones":
                base = to_int(meta["network"]) & mask_of(meta["prefix"])
                span = 1 << (32 - meta["prefix"])
                if span > 1 << 16:
                    return None  # too many addresses to walk one by one
                target = meta["ones"]
                count = 0
                for offset in range(span):
                    value = base + offset
                    ones = 0
                    while value:
                        ones += value & 1
                        value >>= 1
                    count += ones == target
                return str(count)
            case "mask_ones":
                return str(common_prefix(to_int(meta["ip1"]), to_int(meta["network"])))
            case "mask_byte":
                k = common_prefix(to_int(meta["ip1"]), to_int(meta["ip2"]))
                return to_text(mask_of(k)).split(".")[int(meta["byte_index"]) - 1]
        return None

    def _longest_common_prefix_lib(self, a: str, b: str) -> int:
        """Largest k for which both addresses share a /k network (the smallest network)."""
        for k in range(32, -1, -1):
            if ipaddress.ip_address(b) in ipaddress.ip_network(f"{a}/{k}", strict=False):
                return k
        return 0

    def _transform(self, address: str, meta: dict[str, Any]) -> str:
        """Apply the FIPI answer transform — configuration, never a code path."""
        match meta["answer_transform"]:
            case "octet_sum":
                return str(sum(int(part) for part in address.split(".")))
            case "address_no_dots":
                return address.replace(".", "")
            case "number":
                value = 0
                for part in address.split("."):
                    value = value * 256 + int(part)
                return str(value)
        raise ValueError(meta["answer_transform"])

    def enumerate_answers(self, meta: dict[str, Any]) -> list[str] | None:
        """The extremum over the mask length is attained at exactly one k."""
        if meta["question"] not in ("same_network", "mask_ones", "mask_byte"):
            return None
        a, b = meta["ip1"], meta.get("ip2") or meta["network"]
        fits = [
            k
            for k in range(33)
            if ipaddress.ip_address(b) in ipaddress.ip_network(f"{a}/{k}", strict=False)
        ]
        best = max(fits)
        if meta["question"] == "mask_ones":
            return [str(best)]
        if meta["question"] == "mask_byte":
            netmask = ipaddress.ip_network(f"0.0.0.0/{best}").netmask
            return [str(int(str(netmask).split(".")[meta["byte_index"] - 1]))]
        net = ipaddress.ip_network(f"{a}/{best}", strict=False)
        return [self._transform(str(net.network_address), meta)]

    def validate_answer(self, answer: str, meta: dict[str, Any]) -> None:
        if not answer:
            raise ValueError("t10: no answer produced")
        if meta["answer_transform"] == "octet_sum" and not 1 <= int(answer) <= 1020:
            raise ValueError(f"t10: octet sum out of range: {answer}")

    # -- explanation --------------------------------------------------------
    def _solution(self, meta: dict[str, Any], answer: str) -> list[str]:
        transform_line = {
            "octet_sum": "Ответ 2027 года — **сумма октетов** найденного адреса",
            "address_no_dots": "Ответ — адрес, записанный без точек",
            "number": "Ответ — числовое значение адреса",
        }[meta["answer_transform"]]
        match meta["question"]:
            case "same_network":
                k = self._longest_common_prefix_lib(meta["ip1"], meta["ip2"])
                net = ipaddress.ip_network(f"{meta['ip1']}/{k}", strict=False)
                return [
                    "**Шаг 1.** «Наименьшее возможное число адресов в сети» — это "
                    "**наибольшее** число единиц в маске. Перебираем k от 32 вниз "
                    "и берём первое k, при котором оба адреса попадают в одну сеть.",
                    f"**Шаг 2.** Подходит k = **{k}**, маска {net.netmask}. "
                    f"Адрес сети = адрес & маска = **{net.network_address}**.",
                    f"**Шаг 3.** {transform_line}: "
                    + " + ".join(str(net.network_address).split("."))
                    + f" = **{answer}**.\n\n```python\nimport ipaddress\n"
                    f"ip1, ip2 = '{meta['ip1']}', '{meta['ip2']}'\n"
                    "for k in range(32, -1, -1):\n"
                    "    net = ipaddress.ip_network(f'{ip1}/{k}', strict=False)\n"
                    "    if ipaddress.ip_address(ip2) in net:\n"
                    "        a = net.network_address\n"
                    "        print(k, a, sum(map(int, str(a).split('.')))); break\n```",
                ]
            case "network_address":
                net = ipaddress.ip_network(f"{meta['ip1']}/{meta['prefix']}", strict=False)
                return [
                    f"**Шаг 1.** Маска {net.netmask} — это {meta['prefix']} единиц "
                    "слева и нули справа. Записываем адрес и маску в двоичном виде "
                    "по октетам (`bin(x)[2:].zfill(8)`).",
                    "**Шаг 2.** Адрес сети получается побитовым И: адрес & маска = "
                    f"**{net.network_address}**.",
                    f"**Шаг 3.** {transform_line}: **{answer}**.",
                ]
            case "count_with_ones":
                return [
                    f"**Шаг 1.** Сеть — {meta['network']}/{meta['prefix']}, в ней "
                    f"2^(32−{meta['prefix']}) адресов.",
                    f"**Шаг 2.** Условие «ровно {meta['ones']} единиц» считается по "
                    "**всем 32 битам** адреса, а не по последнему октету.",
                    "**Шаг 3.** Перебираем адреса сети и считаем подходящие:\n\n"
                    "```python\nimport ipaddress\n"
                    f"net = ipaddress.ip_network('{meta['network']}/{meta['prefix']}')\n"
                    f"print(sum(bin(int(a)).count('1') == {meta['ones']} for a in net))\n```"
                    f"\n\nОтвет — **{answer}**.",
                ]
            case "mask_ones":
                return [
                    "**Шаг 1.** Маска состоит только из **подряд идущих** единиц "
                    "слева; значит, надо найти, сколько старших битов совпадает "
                    "у адреса узла и адреса сети.",
                    f"**Шаг 2.** Перебираем k от 32 вниз: первое k, при котором "
                    f"адрес & маска даёт {meta['network']}, равно **{answer}**.",
                    "**Шаг 3.** Это и есть число единиц в маске.",
                ]
            case "mask_byte":
                k = self._longest_common_prefix_lib(meta["ip1"], meta["ip2"])
                netmask = ipaddress.ip_network(f"0.0.0.0/{k}").netmask
                return [
                    "**Шаг 1.** Находим наибольшее число единиц маски, при котором "
                    f"оба адреса лежат в одной сети: k = **{k}**.",
                    f"**Шаг 2.** Маска при k = {k} — это {netmask}.",
                    f"**Шаг 3.** Нужный байт маски — **{answer}**.",
                ]
        return []


register(Task10())

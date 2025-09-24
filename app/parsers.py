"""Parsing utilities for extracting ventilation specification entities."""
from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Dict, Iterable, List, Tuple

logger = logging.getLogger(__name__)


def _compile(patterns: Iterable[str]) -> List[re.Pattern]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


def parse_equipment(lines: List[str], patterns: Dict) -> List[Dict[str, str]]:
    """Extract equipment entries from text lines."""
    results: List[Dict[str, str]] = []
    equipment_patterns = patterns.get("equipment", [])
    for config in equipment_patterns:
        element_name = config.get("element", "")
        keywords = [kw.lower() for kw in config.get("keywords", [])]
        regexes = _compile(config.get("model_regex", []))
        for line in lines:
            if not line:
                continue
            lower_line = line.lower()
            matched_regex = False
            for regex in regexes:
                for match in regex.finditer(line):
                    value = match.group(0).strip()
                    if not value:
                        continue
                    results.append({"element": element_name, "wymiar": value})
                    matched_regex = True
            if matched_regex:
                continue
            if any(keyword in lower_line for keyword in keywords):
                results.append({"element": element_name, "wymiar": line.strip()})
    return results


def _search_sizes(texts: Iterable[str], regexes: List[re.Pattern]) -> str:
    for text in texts:
        if text is None:
            continue
        for regex in regexes:
            match = regex.search(text)
            if match:
                if match.groups():
                    return match.group(0).strip()
                return match.group(0).strip()
    return ""


def parse_fittings(lines: List[str], patterns: Dict, window: int = 1) -> List[Dict[str, str]]:
    """Detect fittings (kolano, trójnik, redukcja, etc.)"""
    results: List[Dict[str, str]] = []
    fittings_patterns = patterns.get("fittings", [])
    compiled_cache = {
        config.get("element", ""): _compile(config.get("size_regex", []))
        for config in fittings_patterns
    }
    for idx, line in enumerate(lines):
        lower_line = line.lower()
        for config in fittings_patterns:
            element_name = config.get("element", "")
            keywords = [kw.lower() for kw in config.get("keywords", [])]
            if not any(keyword in lower_line for keyword in keywords):
                continue
            start = max(0, idx - window)
            end = min(len(lines), idx + window + 1)
            neighbourhood = lines[start:end]
            size_value = _search_sizes(neighbourhood, compiled_cache.get(element_name, []))
            results.append({"element": element_name, "wymiar": size_value})
    return results


def parse_duct_sizes(text: str, patterns: Dict) -> Tuple[Dict[str, int], Dict[str, int]]:
    """Extract round and rectangular duct sizes from normalized text."""
    round_patterns = _compile(patterns.get("sizes", {}).get("round", []))
    rect_patterns = _compile(patterns.get("sizes", {}).get("rect", []))
    ranges = patterns.get("ranges", {})
    round_min = int(ranges.get("round_min", 0))
    round_max = int(ranges.get("round_max", 10**6))
    rect_min = int(ranges.get("rect_min", 0))
    rect_max = int(ranges.get("rect_max", 10**6))

    round_counter: Counter[str] = Counter()
    for regex in round_patterns:
        for match in regex.findall(text):
            value = match[0] if isinstance(match, tuple) else match
            try:
                diameter = int(value)
            except ValueError:
                continue
            if not (round_min <= diameter <= round_max):
                continue
            round_counter[f"Ø{diameter}"] += 1

    rect_counter: Counter[str] = Counter()
    for regex in rect_patterns:
        for match in regex.findall(text):
            if isinstance(match, tuple):
                width, height = match
            else:
                parts = match.split("x")
                if len(parts) != 2:
                    continue
                width, height = parts
            try:
                w = int(width)
                h = int(height)
            except ValueError:
                continue
            if not (rect_min <= w <= rect_max and rect_min <= h <= rect_max):
                continue
            rect_counter[f"{w}x{h}"] += 1

    return dict(round_counter), dict(rect_counter)


def aggregate_items(items: List[Dict[str, str]]) -> List[Dict[str, object]]:
    """Aggregate parsed items into rows for the output table."""
    grouped: Dict[Tuple[str, str], Dict[str, object]] = {}
    for item in items:
        element = item.get("element", "")
        wymiar = item.get("wymiar", "") or ""
        uwagi = item.get("uwagi", "") or ""
        key = (element, wymiar)
        if key not in grouped:
            grouped[key] = {"Element": element, "Wymiar": wymiar, "Ilość": 0, "Uwagi": set()}
        grouped[key]["Ilość"] = int(grouped[key]["Ilość"]) + 1
        if uwagi:
            grouped[key]["Uwagi"].add(uwagi)
    rows: List[Dict[str, object]] = []
    for data in grouped.values():
        uwagi_values = ", ".join(sorted(data["Uwagi"])) if data["Uwagi"] else ""
        rows.append({
            "Element": data["Element"],
            "Wymiar": data["Wymiar"],
            "Ilość": data["Ilość"],
            "Uwagi": uwagi_values,
        })
    return rows

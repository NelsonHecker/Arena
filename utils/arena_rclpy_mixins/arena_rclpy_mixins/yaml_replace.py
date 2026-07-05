from __future__ import annotations

import dataclasses
import re
import typing

import yaml


class YAMLReplacer:
    """`${var}` / `${var:-default}` / `${*list}` / `${**dict}` substitution engine
    for nested YAML-loaded dicts/lists. Launch-free so it is importable on paths
    (e.g. Isaac) that must not import `launch`.

    `replace()` mutates its input dict/list in place (and also returns it).
    """

    @dataclasses.dataclass(frozen=True)
    class Replacement:
        value: typing.Any

    @dataclasses.dataclass(frozen=True)
    class NoReplacement(Replacement):
        value: typing.Any

    @dataclasses.dataclass(frozen=True)
    class StringReplacement(Replacement):
        value: typing.Any

    @dataclasses.dataclass(frozen=True)
    class DictSpreadReplacement(Replacement):
        value: dict

    @dataclasses.dataclass(frozen=True)
    class ListSpreadReplacement(Replacement):
        value: list

    _substitutions: dict

    def _replace_inter_string(self, v: str) -> NoReplacement | None:
        counter: int = 0
        replacements: list[tuple[int, int]] = []
        opening: int = 0
        for i, c in enumerate(v):
            if v[i : i + 2] == '${':
                if counter == 0:
                    opening = i
                counter += 1
            if c == '}':
                counter -= 1
                if counter < 0:
                    break
                if counter == 0:
                    replacements.append((opening, i + 1))

        if counter == 0 and replacements:
            # abandon inter-string substitution
            if replacements[0] == (0, len(v)):
                return None

            result = ''
            last_end: int = 0
            for start, end in replacements:
                result += v[last_end:start]

                matchable = v[start:end]

                match = self._sub_match(matchable, strict_string=True)

                if not isinstance(match.value, str):
                    raise ValueError(f'misplaced substitution {matchable} of type {type(match.value)} in {v}')

                result += match.value
                last_end = end

            result += v[last_end:]
            return self.NoReplacement(value=result)

        return None

    def _sub_match(self, v: str, *, strict_string: bool = False) -> Replacement:

        str_v: str | None = v
        replacement: None | YAMLReplacer.Replacement = None
        used_default: bool = False

        while str_v is not None:
            if (match := re.match(r'^\$\{(.*)\}$', str_v)) is None:  # not a full-length substitution
                value: typing.Any = str_v
                # Defaults from `${var:-literal}` are written in YAML syntax - coerce
                # so numeric/bool defaults round-trip as their parsed type instead of
                # leaking strings into typed ROS parameters. `strict_string` keeps the
                # inter-string concatenation path on raw strings.
                if used_default and not strict_string:
                    try:
                        value = yaml.safe_load(str_v)
                    except yaml.YAMLError:
                        pass
                return self.NoReplacement(value=value)

            sub, *defaults = match.group(1).split(':-', 1)
            default = defaults[0] if defaults else None

            if sub.startswith('**'):
                if isinstance((substitution := self._substitutions.get(sub[len('**') :])), dict):
                    return self.DictSpreadReplacement(value=substitution)

            if sub.startswith('*'):
                if isinstance((substitution := self._substitutions.get(sub[len('*') :])), list):
                    return self.ListSpreadReplacement(value=substitution)

            if sub in self._substitutions:
                return self.StringReplacement(value=self._substitutions[sub])

            str_v = default
            used_default = True

        if replacement is None:
            if (inter_sub := self._replace_inter_string(v)) is not None:
                return inter_sub
            raise ValueError(f'could not find substitution for {v}')

        return replacement

    def _replace_list(self, obj: list) -> list:
        to_insert: list[tuple[int, list]] = []

        for k, v in enumerate(obj):
            if isinstance(v, str):
                replacement = self._sub_match(v)

                if isinstance(replacement, self.DictSpreadReplacement):
                    raise ValueError('dict spread argument placed outside dict')
                elif isinstance(replacement, self.ListSpreadReplacement):
                    to_insert.append((k, replacement.value))
                    continue
                elif isinstance(replacement, self.StringReplacement):
                    obj[k] = replacement.value

            obj[k] = self.replace(obj[k])

        offset: int = 0
        for i, insertions in to_insert:
            expanded = self._replace_list(insertions)
            obj.pop(i + offset)
            obj[i + offset : i + offset] = expanded
            offset += len(expanded) - 1

        return obj

    def _replace_dict(self, obj: dict) -> dict:
        to_insert: list[tuple[str, dict]] = []

        for k, v in obj.items():
            if isinstance(replacement := self._sub_match(k), self.DictSpreadReplacement):
                to_insert.append((k, replacement.value))
                continue

            if isinstance(v, str):
                replacement = self._sub_match(v)

                if isinstance(replacement, self.DictSpreadReplacement):
                    raise ValueError('dict spreads should be placed in dict keys')
                elif isinstance(replacement, self.ListSpreadReplacement):
                    raise ValueError('list spread argument placed outside list')
                elif isinstance(replacement, self.StringReplacement):
                    obj[k] = replacement.value

            obj[k] = self.replace(v)

        for key, insertions in to_insert:
            obj.pop(key)
            obj.update(self._replace_dict(insertions))

        return obj

    def _replace_str(self, obj: str) -> str | dict | list | object:
        if (inter_v := self._replace_inter_string(obj)) is not None:
            return self.replace(inter_v.value)
        replacement = self._sub_match(obj)
        if isinstance(replacement, self.DictSpreadReplacement):
            raise ValueError('dict spread argument placed outside dict')
        elif isinstance(replacement, self.ListSpreadReplacement):
            raise ValueError('list spread argument placed outside list')
        elif isinstance(replacement, self.StringReplacement):
            return self.replace(replacement.value)
        elif isinstance(replacement, self.NoReplacement):
            return replacement.value
        return obj

    @typing.overload
    def replace(self, obj: dict) -> dict: ...

    @typing.overload
    def replace(self, obj: list) -> list: ...

    @typing.overload
    def replace(self, obj: str) -> str: ...

    def replace(self, obj: typing.Any) -> typing.Any:
        if isinstance(obj, list):
            return self._replace_list(obj)
        if isinstance(obj, dict):
            return self._replace_dict(obj)
        if isinstance(obj, str):
            return self._replace_str(obj)
        return obj

    def __init__(self, substitutions: dict):
        self._substitutions = substitutions

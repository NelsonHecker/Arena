import os

_ENDPOINT = os.environ.get("LLM_API_ENDPOINT")


def _build_genai_shim() -> object:
    from google import genai as _genai

    if not _ENDPOINT:

        class _GenaiShim:
            Client = _genai.Client

            def __getattr__(self, name: str) -> object:
                return getattr(_genai, name)

        return _GenaiShim()

    class _LocalCache:
        def __init__(self, name: str, system_instruction: object, contents: object, model: object) -> None:
            self.name = name
            self.system_instruction = system_instruction
            self.contents = contents
            self.model = model
            self.display_name = ""

    # Process-wide cache store. Shared across every _LocalClient instance so a
    # cache created on one client is visible to generate_content on another.
    _cache_store: dict[str, _LocalCache] = {}
    _cache_counter = [0]

    class _LocalCaches:
        def create(self, *, model: object, config: object) -> _LocalCache:
            _cache_counter[0] += 1
            name = f"local-cache-{_cache_counter[0]}"
            cache = _LocalCache(
                name=name,
                system_instruction=getattr(config, "system_instruction", None),
                contents=getattr(config, "contents", None),
                model=model,
            )
            _cache_store[name] = cache
            return cache

        def list(self) -> list[_LocalCache]:
            return list(_cache_store.values())

        def delete(self, *, name: str) -> None:
            _cache_store.pop(name, None)

    def _expand(contents: object, config: object) -> tuple[object, object]:
        cached = getattr(config, "cached_content", None)
        if not cached or cached not in _cache_store:
            return contents, config
        cache = _cache_store[cached]
        # Build a new config dropping cached_content and adding system_instruction.
        # Tolerate pydantic v1/v2 and plain dataclasses via model_copy/replace/dict.
        if hasattr(config, "model_copy"):
            new_config = config.model_copy(
                update={
                    "cached_content": None,
                    "system_instruction": cache.system_instruction,
                }
            )
        else:
            from dataclasses import replace

            new_config = replace(
                config,
                cached_content=None,
                system_instruction=cache.system_instruction,
            )
        prefix = cache.contents if cache.contents is not None else []
        if not isinstance(prefix, list):
            prefix = [prefix]
        if isinstance(contents, list):
            new_contents = prefix + contents
        else:
            new_contents = prefix + [contents]
        return new_contents, new_config

    class _LocalModels:
        def __init__(self, real: object) -> None:
            self._real = real

        def generate_content(self, *, model: object, contents: object, config: object = None, **kw: object) -> object:
            contents, config = _expand(contents, config)
            return self._real.generate_content(model=model, contents=contents, config=config, **kw)

        def __getattr__(self, name: str) -> object:
            return getattr(self._real, name)

    class _LocalAsyncModels:
        def __init__(self, real: object) -> None:
            self._real = real

        async def generate_content(self, *, model: object, contents: object, config: object = None, **kw: object) -> object:
            contents, config = _expand(contents, config)
            return await self._real.generate_content(model=model, contents=contents, config=config, **kw)

        def __getattr__(self, name: str) -> object:
            return getattr(self._real, name)

    class _LocalAio:
        def __init__(self, real: object) -> None:
            self._real = real
            self._models = _LocalAsyncModels(real.models)

        @property
        def models(self) -> _LocalAsyncModels:
            return self._models

        def __getattr__(self, name: str) -> object:
            return getattr(self._real, name)

    class _LocalClient(_genai.Client):
        def __init__(self, *_a: object, **_kw: object) -> None:
            super().__init__(
                api_key="sk-local",
                http_options={"base_url": _ENDPOINT, "api_version": "v1beta"},
            )
            self.__dict__["_caches"] = _LocalCaches()
            self.__dict__["_models"] = _LocalModels(super().__getattribute__("models"))
            self.__dict__["_aio"] = _LocalAio(super().__getattribute__("aio"))

        @property
        def caches(self) -> _LocalCaches:
            return self.__dict__["_caches"]

        @property
        def models(self) -> _LocalModels:
            return self.__dict__["_models"]

        @property
        def aio(self) -> _LocalAio:
            return self.__dict__["_aio"]

    class _GenaiShim:
        Client: type[_genai.Client] = _LocalClient

        def __getattr__(self, name: str) -> object:
            return getattr(_genai, name)

    return _GenaiShim()


def _build_openai_shim() -> object:
    import openai as _openai

    class _LocalOpenAI(_openai.OpenAI):
        def __init__(self, *_a: object, **_kw: object) -> None:
            super().__init__(base_url=f"{_ENDPOINT}/v1", api_key="sk-local")

    class _LocalAsyncOpenAI(_openai.AsyncOpenAI):
        def __init__(self, *_a: object, **_kw: object) -> None:
            super().__init__(base_url=f"{_ENDPOINT}/v1", api_key="sk-local")

    class _OpenAIShim:
        OpenAI: type[_openai.OpenAI] = _LocalOpenAI if _ENDPOINT else _openai.OpenAI
        AsyncOpenAI: type[_openai.AsyncOpenAI] = _LocalAsyncOpenAI if _ENDPOINT else _openai.AsyncOpenAI

        def __getattr__(self, name: str) -> object:
            return getattr(_openai, name)

    return _OpenAIShim()


_builders = {"genai": _build_genai_shim, "openai": _build_openai_shim}


def __getattr__(name: str) -> object:
    builder = _builders.get(name)
    if builder is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    shim = builder()
    globals()[name] = shim
    return shim

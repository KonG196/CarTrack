"""Every annotation in the app must actually resolve.

**Why this test exists.** The dev venv runs Python 3.14, where PEP 649 defers
annotation evaluation: a function annotated with a name that was never
imported is built without complaint, and the module imports clean. The
Dockerfile that ships this app is ``python:3.12-slim``, where annotations are
evaluated eagerly at ``def`` time — so the very same line raises NameError
while the module is being imported, and the container never finishes booting.

The whole test suite can therefore be green on a codebase that cannot start in
production. This test closes that gap by forcing every annotation to resolve,
which is what Python <=3.13 does for free at import.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import typing

import pytest

import app

# routers/ocr.py and services/ocr.py belong to another session; they are
# imported like everything else but are not this test's to fix.
MODULES = sorted(
    module.name
    for module in pkgutil.walk_packages(app.__path__, prefix="app.")
    if not module.ispkg
)


def _annotated_objects(module: object):
    for _, obj in inspect.getmembers(module):
        if inspect.isfunction(obj) and obj.__module__ == module.__name__:
            yield obj
        elif inspect.isclass(obj) and obj.__module__ == module.__name__:
            for _, method in inspect.getmembers(obj, inspect.isfunction):
                if method.__module__ == module.__name__:
                    yield method


@pytest.mark.parametrize("module_name", MODULES)
def test_module_annotations_resolve(module_name: str) -> None:
    """No annotation may name something the module never defined or imported.

    ``get_type_hints`` evaluates the annotations in the module's own globals —
    exactly the lookup Python 3.12 performs at def time.
    """
    module = importlib.import_module(module_name)
    unresolved: list[str] = []
    for obj in _annotated_objects(module):
        try:
            typing.get_type_hints(obj)
        except NameError as error:
            unresolved.append(f"{obj.__qualname__}: {error}")
        except Exception:  # noqa: BLE001
            # Forward refs into third-party generics can fail for reasons that
            # are not a missing import; only NameError is this test's business.
            continue
    assert not unresolved, (
        f"{module_name} has annotations that do not resolve — this module "
        f"raises NameError at import on Python <=3.13 (Dockerfile: "
        f"python:3.12-slim):\n  " + "\n  ".join(unresolved)
    )

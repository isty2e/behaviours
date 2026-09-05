"""Unsupported framework paths are observable, versioned watchpoints."""

import pytest

from behaviours import StrictMixin


class Summary(StrictMixin):
    def summary(self) -> str:
        return type(self).__name__


def test_pydantic_base_model_metaclass_watchpoint():
    pydantic = pytest.importorskip("pydantic")
    with pytest.raises(TypeError, match="metaclass conflict"):

        class Unsupported(Summary, pydantic.BaseModel):
            name: str


def test_django_model_metaclass_watchpoint():
    django = pytest.importorskip("django")
    from django.conf import settings

    if not settings.configured:
        settings.configure(INSTALLED_APPS=[], SECRET_KEY="test-only")
        django.setup()
    from django.db import models

    with pytest.raises(TypeError, match="metaclass conflict"):

        class Unsupported(Summary, models.Model):
            class Meta:
                app_label = "behaviours_test"

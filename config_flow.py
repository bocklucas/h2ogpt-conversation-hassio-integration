"""Config flow for H2OGPT Conversation integration."""
from __future__ import annotations

from functools import partial
import logging
import types
from types import MappingProxyType
from typing import Any
import requests

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    TemplateSelector,
)

from .const import (
    CONF_PROMPT_CONTEXT,
    DEFAULT_PROMPT_CONTEXT,
    CONF_HOST_URL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST_URL): str,
    }
)

DEFAULT_OPTIONS = types.MappingProxyType(
    {
        CONF_PROMPT_CONTEXT: DEFAULT_PROMPT_CONTEXT,
    }
)


def check_connection(host_url: str):
    response = requests.get(host_url)
    if response.status_code == 200:
        return "Connection to API successful!"

    raise requests.exceptions.HTTPError


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """

    await hass.async_add_executor_job(
        partial(check_connection(data[CONF_HOST_URL]), request_timeout=10)
    )


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for H2OGPT Conversation."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA
            )

        errors = {}

        try:
            await validate_input(self.hass, user_input)
        except requests.exceptions.HTTPError:
            errors["base"] = "cannot_connect"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            return self.async_create_entry(title="H2OGPT Conversation", data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return OptionsFlow(config_entry)


class OptionsFlow(config_entries.OptionsFlow):
    """H2OGPT config flow options handler."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="H2OGPT Conversation", data=user_input)
        schema = h2ogpt_conversation_config_option_schema(self.config_entry.options)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema),
        )


def h2ogpt_conversation_config_option_schema(
    options: MappingProxyType[str, Any]
) -> dict:
    """Return a schema for H2OGPT completion options."""
    if not options:
        options = DEFAULT_OPTIONS
    return {
        vol.Optional(
            CONF_PROMPT_CONTEXT,
            description={"suggested_value": options[CONF_PROMPT_CONTEXT]},
            default=DEFAULT_PROMPT_CONTEXT,
        ): TemplateSelector(),
    }

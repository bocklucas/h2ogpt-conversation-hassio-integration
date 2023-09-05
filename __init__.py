"""The H2OGPT Conversation integration."""
from __future__ import annotations

from functools import partial
import logging
from typing import Literal

from urllib import request

import ast


from homeassistant.components import conversation
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, MATCH_ALL
from homeassistant.core import (
    HomeAssistant,
)
from homeassistant.exceptions import (
    ConfigEntryNotReady,
    HomeAssistantError,
    TemplateError,
)
from homeassistant.helpers import config_validation as cv, intent, selector, template
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import ulid


from .const import (
    CONF_PROMPT_CONTEXT,
    CONF_HOST_URL,
    DEFAULT_PROMPT_CONTEXT,
    DOMAIN,
)

from .h2ogpt_gradio_client import GradioClient

from .config_flow import check_connection

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up H2OGPT Conversation from a config entry."""
    try:
        await hass.async_add_executor_job(
            lambda: check_connection(entry.data[CONF_HOST_URL]),
        )
    except request.URLError as err:
        _LOGGER.error("Unable to connect: %s", err)
        return False
    except Exception as err:
        raise ConfigEntryNotReady(err) from err

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = entry.data[CONF_HOST_URL]

    conversation.async_set_agent(hass, entry, H2OGPTAgent(hass, entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload H2OGPT."""
    hass.data[DOMAIN].pop(entry.entry_id)
    conversation.async_unset_agent(hass, entry)
    return True


def _call_h2o_gpt_api(client: GradioClient, prompt: str) -> str:
    # don't specify prompt_type etc., use whatever endpoint setup
    kwargs = dict(
        stream_output=False,
        max_time=360,
        instruction_nochat=prompt,
    )
    return client.predict(str(kwargs), api_name="/submit_nochat_api")


prompt_template = '''
"""
{context}
"""
{question}
'''


def answer_question_using_context(
    client: GradioClient, question: str, context: str
) -> str:
    prompt = prompt_template.format(context=context, question=question)
    answer = _call_h2o_gpt_api(client, prompt)
    return ast.literal_eval(answer)["response"]


class H2OGPTAgent(conversation.AbstractConversationAgent):
    """H2OGPT conversation agent."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the agent."""
        self.hass = hass
        self.entry = entry
        self.history: dict[str, list[dict]] = {}

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        """Return a list of supported languages."""
        return MATCH_ALL

    async def async_process(
        self, user_input: conversation.ConversationInput
    ) -> conversation.ConversationResult:
        """Process a sentence."""
        _LOGGER.debug("Creating H2OGPT Client...")
        client = await self.hass.async_add_executor_job(
            lambda: GradioClient(self.entry.data[CONF_HOST_URL]),
        )
        _LOGGER.debug("Client Created!")
        raw_prompt_context = self.entry.options.get(
            CONF_PROMPT_CONTEXT, DEFAULT_PROMPT_CONTEXT
        )

        if user_input.conversation_id in self.history:
            conversation_id = user_input.conversation_id
            messages = self.history[conversation_id]
        else:
            conversation_id = ulid.ulid()
            messages = [{"role": "system", "content": raw_prompt_context}]

        messages.append({"role": "user", "content": user_input.text})

        _LOGGER.debug("Prompt for h2ogpt: %s", messages)

        try:
            result = await self.hass.async_add_executor_job(
                lambda: answer_question_using_context(
                    client, user_input.text, raw_prompt_context
                ),
            )

        except Exception as err:
            intent_response = intent.IntentResponse(language=user_input.language)
            intent_response.async_set_error(
                intent.IntentResponseErrorCode.UNKNOWN,
                f"Sorry, I had a problem talking to H2OGPT: {err}",
            )
            return conversation.ConversationResult(
                response=intent_response, conversation_id=conversation_id
            )

        _LOGGER.debug("Response %s", result)
        response = result
        messages.append(response)
        self.history[conversation_id] = messages

        intent_response = intent.IntentResponse(language=user_input.language)
        intent_response.async_set_speech(response)
        return conversation.ConversationResult(
            response=intent_response, conversation_id=conversation_id
        )

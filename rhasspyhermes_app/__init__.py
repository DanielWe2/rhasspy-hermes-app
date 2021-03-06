"""Helper library to create voice apps for Rhasspy using the Hermes protocol."""
import argparse
import asyncio
import logging
import re
import typing
from dataclasses import dataclass

import paho.mqtt.client as mqtt
import rhasspyhermes.cli as hermes_cli
from rhasspyhermes.client import HermesClient
from rhasspyhermes.dialogue import DialogueContinueSession, DialogueEndSession
from rhasspyhermes.nlu import NluIntent, NluIntentNotRecognized
from rhasspyhermes.wake import HotwordDetected

_LOGGER = logging.getLogger("HermesApp")


class HermesApp(HermesClient):
    """A Rhasspy app using the Hermes protocol.

    Attributes:
        args (:class:`argparse.Namespace`): Command-line arguments for the Hermes app.

    Example:

    .. literalinclude:: ../time_app.py
    """

    def __init__(
        self,
        name: str,
        parser: typing.Optional[argparse.ArgumentParser] = None,
        mqtt_client: typing.Optional[mqtt.Client] = None,
    ):
        """Initialize the Rhasspy Hermes app.

        Args:
            name (str): The name of this object.

            parser (:class:`argparse.ArgumentParser`, optional): An argument parser.
                If the argument is not specified, the object creates an
                argument parser itself.

            mqtt_client (:class:`paho.mqtt.client.Client`, optional): An MQTT client. If the argument
                is not specified, the object creates an MQTT client itself.
        """
        if parser is None:
            parser = argparse.ArgumentParser(prog=name)
        # Add default arguments
        hermes_cli.add_hermes_args(parser)

        # Parse command-line arguments
        self.args = parser.parse_args()

        # Set up logging
        hermes_cli.setup_logging(self.args)
        _LOGGER.debug(self.args)

        # Create MQTT client
        if mqtt_client is None:
            mqtt_client = mqtt.Client()

        # Initialize HermesClient
        super().__init__(name, mqtt_client, site_ids=self.args.site_id)

        self._callbacks_hotword: typing.List[
            typing.Callable[[HotwordDetected], None]
        ] = []

        self._callbacks_intent: typing.Dict[
            str,
            typing.List[
                typing.Callable[[NluIntent], typing.Union[ContinueSession, EndSession]]
            ],
        ] = {}

        self._callbacks_intent_not_recognized: typing.List[
            typing.Callable[
                [NluIntentNotRecognized], typing.Union[ContinueSession, EndSession]
            ]
        ] = []

        self._callbacks_topic: typing.Dict[
            str, typing.List[typing.Callable[[TopicData, bytes], None]]
        ] = {}

        self._callbacks_topic_regex: typing.List[
            typing.Callable[[TopicData, bytes], None]
        ] = []

        self._additional_topic: typing.List[str] = []

    def _subscribe_callbacks(self):
        # Remove duplicate intent names
        intent_names = list(set(self._callbacks_intent.keys()))
        topics = [
            NluIntent.topic(intent_name=intent_name) for intent_name in intent_names
        ]

        if self._callbacks_hotword:
            topics.append(HotwordDetected.topic())

        if self._callbacks_intent_not_recognized:
            topics.append(NluIntentNotRecognized.topic())

        topic_names = list(set(self._callbacks_topic.keys()))
        topics.extend(topic_names)
        topics.extend(self._additional_topic)

        self.subscribe_topics(*topics)

    async def on_raw_message(self, topic: str, payload: bytes):
        """This method handles messages from the MQTT broker.

        Args:
            topic (str): The topic of the received MQTT message.

            payload (bytes): The payload of the received MQTT message.

        .. warning:: Don't override this method in your app. This is where all the magic happens in Rhasspy Hermes App.
        """
        try:
            if HotwordDetected.is_topic(topic):
                # hermes/hotword/<wakeword_id>/detected
                try:
                    hotword_detected = HotwordDetected.from_json(payload)
                    for function_h in self._callbacks_hotword:
                        function_h(hotword_detected)
                except KeyError as key:
                    _LOGGER.error(
                        "Missing key %s in JSON payload for %s: %s", key, topic, payload
                    )
            elif NluIntent.is_topic(topic):
                # hermes/intent/<intent_name>
                try:
                    nlu_intent = NluIntent.from_json(payload)
                    intent_name = nlu_intent.intent.intent_name
                    if intent_name in self._callbacks_intent:
                        for function_i in self._callbacks_intent[intent_name]:
                            function_i(nlu_intent)
                except KeyError as key:
                    _LOGGER.error(
                        "Missing key %s in JSON payload for %s: %s", key, topic, payload
                    )
            elif NluIntentNotRecognized.is_topic(topic):
                # hermes/nlu/intentNotRecognized
                try:
                    nlu_intent_not_recognized = NluIntentNotRecognized.from_json(
                        payload
                    )
                    for function_inr in self._callbacks_intent_not_recognized:
                        function_inr(nlu_intent_not_recognized)
                except KeyError as key:
                    _LOGGER.error(
                        "Missing key %s in JSON payload for %s: %s", key, topic, payload
                    )
            else:
                unexpected_topic = True
                if topic in self._callbacks_topic:
                    for function_1 in self._callbacks_topic[topic]:
                        function_1(TopicData(topic, {}), payload)
                        unexpected_topic = False
                else:
                    for function_2 in self._callbacks_topic_regex:
                        if hasattr(function_2, "topic_extras"):
                            topic_extras = getattr(function_2, "topic_extras")
                            for pattern, named_positions in topic_extras:
                                if re.match(pattern, topic) is not None:
                                    data = TopicData(topic, {})
                                    parts = topic.split(sep="/")
                                    if named_positions is not None:
                                        for name, position in named_positions.items():
                                            data.data[name] = parts[position]

                                    function_2(data, payload)
                                    unexpected_topic = False

                if unexpected_topic:
                    _LOGGER.warning("Unexpected topic: %s", topic)

        except Exception:
            _LOGGER.exception("on_raw_message")

    def on_hotword(self, function):
        """Apply this decorator to a function that you want to act on a detected hotword.

        The function needs to have the following signature:

        function(hotword: :class:`rhasspyhermes.wake.HotwordDetected`)

        Example:

        .. code-block:: python

            @app.on_hotword
            def wake(hotword):
                print(f"Hotword {hotword.model_id} detected on site {hotword.site_id}")
        """

        self._callbacks_hotword.append(function)

        return function

    def on_intent(self, *intent_names: str):
        """Apply this decorator to a function that you want to act on a received intent.

        Args:
            *intent_names (str): Names of the intents you want the function to act on.

        The function needs to have the following signature:

        function(intent: :class:`rhasspyhermes.nlu.NluIntent`)

        Example:

        .. code-block:: python

            @app.on_intent("GetTime")
            def get_time(intent: NluIntent):
                return EndSession("It's too late.")
        """

        def wrapper(function):
            def wrapped(intent: NluIntent):
                message = function(intent)
                if isinstance(message, EndSession):
                    if intent.session_id is not None:
                        self.publish(
                            DialogueEndSession(
                                session_id=intent.session_id,
                                site_id=intent.site_id,
                                text=message.text,
                                custom_data=message.custom_data,
                            )
                        )
                    else:
                        _LOGGER.error(
                            "Cannot end session of intent without session ID."
                        )
                elif isinstance(message, ContinueSession):
                    if intent.session_id is not None:
                        self.publish(
                            DialogueContinueSession(
                                session_id=intent.session_id,
                                site_id=intent.site_id,
                                text=message.text,
                                intent_filter=message.intent_filter,
                                custom_data=message.custom_data,
                                send_intent_not_recognized=message.send_intent_not_recognized,
                            )
                        )
                    else:
                        _LOGGER.error(
                            "Cannot continue session of intent without session ID."
                        )

            for intent_name in intent_names:
                try:
                    self._callbacks_intent[intent_name].append(wrapped)
                except KeyError:
                    self._callbacks_intent[intent_name] = [wrapped]

            return wrapped

        return wrapper

    def on_intent_not_recognized(self):
        """Apply this decorator to a function that you want to act when the NLU system
        hasn't recognized an intent.

        The function needs to have the following signature:

        function(intent_not_recognized: :class:`rhasspyhermes.nlu.IntentNotRecognized`)

        Example:

        .. code-block:: python

            @app.on_intent_not_recognized
            def notunderstood(intent_not_recognized):
                print(f"Didn't understand \"{intent_not_recognized.input}\" on site {intent_not_recognized.site_id}")
        """

        def wrapper(function):
            def wrapped(inr: NluIntentNotRecognized):
                message = function(inr)
                if isinstance(message, EndSession):
                    if inr.session_id is not None:
                        self.publish(
                            DialogueEndSession(
                                session_id=inr.session_id,
                                site_id=inr.site_id,
                                text=message.text,
                                custom_data=message.custom_data,
                            )
                        )
                    else:
                        _LOGGER.error(
                            "Cannot end session of intent not recognized message without session ID."
                        )
                elif isinstance(message, ContinueSession):
                    if inr.session_id is not None:
                        self.publish(
                            DialogueContinueSession(
                                session_id=inr.session_id,
                                site_id=inr.site_id,
                                text=message.text,
                                intent_filter=message.intent_filter,
                                custom_data=message.custom_data,
                                send_intent_not_recognized=message.send_intent_not_recognized,
                            )
                        )
                    else:
                        _LOGGER.error(
                            "Cannot continue session of intent not recognized message without session ID."
                        )

            self._callbacks_intent_not_recognized.append(wrapped)

            return wrapped

        return wrapper

    def on_topic(self, *topic_names: str):
        """Apply this decorator to a function that you want to act on a received raw MQTT message.

        Args:
            *topic_names (str): The MQTT topics you want the function to act on.

        The function needs to have the following signature:

        function(data: :class:`TopicData`, payload: bytes)

        Example:

        .. code-block:: python

            @app.on_topic("hermes/+/{site_id}/playBytes/#")
            def test_topic1(data: TopicData, payload: bytes):
                _LOGGER.debug("topic: %s, site_id: %s", data.topic, data.data.get("site_id"))

        .. note:: The topic names can contain MQTT wildcards (`+` and `#`) or templates (`{foobar}`).
            In the latter case the value of the named template is available in the decorated function
            as part of the ``data`` argument.
        """

        def wrapper(function):
            def wrapped(data: TopicData, payload: bytes):
                function(data, payload)

            replaced_topic_names = []

            for topic_name in topic_names:
                named_positions = {}
                parts = topic_name.split(sep="/")
                length = len(parts) - 1

                def placeholder_mapper(part):
                    i, token = tuple(part)
                    if token.startswith("{") and token.endswith("}"):
                        named_positions[token[1:-1]] = i
                        return "+"

                    return token

                parts = list(map(placeholder_mapper, enumerate(parts)))
                replaced_topic_name = "/".join(parts)

                def regex_mapper(part):
                    i, token = tuple(part)
                    value = token
                    if i == 0:
                        value = (
                            "^[^+#/]"
                            if token == "+"
                            else "[^/]+"
                            if length == 0 and token == "#"
                            else "^" + token
                        )
                    elif i < length:
                        value = "[^/]+" if token == "+" else token
                    elif i == length:
                        value = (
                            "[^/]+"
                            if token == "#"
                            else "[^/]+$"
                            if token == "+"
                            else token + "$"
                        )

                    return value

                pattern = "/".join(map(regex_mapper, enumerate(parts)))

                if topic_name == pattern[1:-1]:
                    try:
                        self._callbacks_topic[topic_name].append(wrapped)
                    except KeyError:
                        self._callbacks_topic[topic_name] = [wrapped]
                else:
                    replaced_topic_names.append(replaced_topic_name)
                    if not hasattr(wrapped, "topic_extras"):
                        wrapped.topic_extras = []
                    wrapped.topic_extras.append(
                        (
                            re.compile(pattern),
                            named_positions if len(named_positions) > 0 else None,
                        )
                    )

            if hasattr(wrapped, "topic_extras"):
                self._callbacks_topic_regex.append(wrapped)
                self._additional_topic.extend(replaced_topic_names)

            return wrapped

        return wrapper

    def run(self):
        """Run the app. This method:

        - subscribes to all MQTT topics for the functions you decorated;
        - connects to the MQTT broker;
        - starts the MQTT event loop and reacts to received MQTT messages.
        """
        # Subscribe to callbacks
        self._subscribe_callbacks()

        # Try to connect
        _LOGGER.debug("Connecting to %s:%s", self.args.host, self.args.port)
        hermes_cli.connect(self.mqtt_client, self.args)
        self.mqtt_client.loop_start()

        try:
            # Run main loop
            asyncio.run(self.handle_messages_async())
        except KeyboardInterrupt:
            pass
        finally:
            self.mqtt_client.loop_stop()


@dataclass
class ContinueSession:
    """Helper class to continue the current session.

    Attributes:
        text (str, optional): The text the TTS should say to start this additional request of the session.
        intent_filter (List[str], optional): A list of intents names to restrict the NLU resolution on the
            answer of this query.
        custom_data (str, optional): An update to the session's custom data. If not provided, the custom data
            will stay the same.
        send_intent_not_recognized (bool): Indicates whether the dialogue manager should handle non recognized
            intents by itself or send them for the client to handle.
    """

    custom_data: typing.Optional[str] = None
    text: typing.Optional[str] = None
    intent_filter: typing.Optional[typing.List[str]] = None
    send_intent_not_recognized: bool = False


@dataclass
class EndSession:
    """Helper class to end the current session.

    Attributes:
        text (str, optional): The text the TTS should say to end the session.
        custom_data (str, optional): An update to the session's custom data. If not provided, the custom data
            will stay the same.
    """

    text: typing.Optional[str] = None
    custom_data: typing.Optional[str] = None


@dataclass
class TopicData:
    """Helper class for topic subscription.

    Attributes:
        topic (str): The MQTT topic.
        data (Dict[str, str]): A dictionary holding extracted data for the given placeholder.
    """

    topic: str
    data: typing.Dict[str, str]

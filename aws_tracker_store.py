from __future__ import annotations
import contextlib
import itertools
import json
import logging
import os
from inspect import isawaitable, iscoroutinefunction

from time import sleep
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    Iterator,
    List,
    Optional,
    Text,
    Union,
    TYPE_CHECKING,
    Generator,
    TypeVar,
    Generic,
)

from boto3.dynamodb.conditions import Key
from pymongo.collection import Collection

import rasa.core.utils as core_utils
import rasa.shared.utils.cli
import rasa.shared.utils.common
import rasa.shared.utils.io
from rasa.plugin import plugin_manager
from rasa.shared.core.constants import ACTION_LISTEN_NAME
from rasa.core.brokers.broker import EventBroker
from rasa.core.constants import (
    POSTGRESQL_SCHEMA,
    POSTGRESQL_MAX_OVERFLOW,
    POSTGRESQL_POOL_SIZE,
)
from rasa.shared.core.conversation import Dialogue
from rasa.shared.core.domain import Domain
from rasa.shared.core.events import SessionStarted, Event
from rasa.shared.core.trackers import (
    ActionExecuted,
    DialogueStateTracker,
    EventVerbosity,
    TrackerEventDiffEngine,
)
from rasa.shared.exceptions import ConnectionException, RasaException
from rasa.shared.nlu.constants import INTENT_NAME_KEY
from rasa.utils.endpoints import EndpointConfig
import sqlalchemy as sa
from sqlalchemy.ext.declarative import declarative_base, DeclarativeMeta

if TYPE_CHECKING:
    import boto3.resources.factory.dynamodb.Table
    from sqlalchemy.engine.url import URL
    from sqlalchemy.engine.base import Engine
    from sqlalchemy.orm import Session, Query
    from sqlalchemy import Sequence


def check_if_tracker_store_async(tracker_store: TrackerStore) -> bool:
    """Evaluates if a tracker store object is async based on implementation of methods.

    :param tracker_store: tracker store object we're evaluating
    :return: if the tracker store correctly implements all async methods
    """
    return all(
        iscoroutinefunction(getattr(tracker_store, method))
        for method in _get_async_tracker_store_methods()
    )


def _get_async_tracker_store_methods() -> List[str]:
    return [
        attribute
        for attribute in dir(TrackerStore)
        if iscoroutinefunction(getattr(TrackerStore, attribute))
    ]


class TrackerDeserialisationException(RasaException):
    """Raised when an error is encountered while deserialising a tracker."""


SerializationType = TypeVar("SerializationType")


class SerializedTrackerRepresentation(Generic[SerializationType]):
    """Mixin class for specifying different serialization methods per tracker store."""

    @staticmethod
    def serialise_tracker(tracker: DialogueStateTracker) -> SerializationType:
        """Requires implementation to return representation of tracker."""
        raise NotImplementedError()


class SerializedTrackerAsText(SerializedTrackerRepresentation[Text]):
    """Mixin class that returns the serialized tracker as string."""

    @staticmethod
    def serialise_tracker(tracker: DialogueStateTracker) -> Text:
        """Serializes the tracker, returns representation of the tracker."""
        dialogue = tracker.as_dialogue()

        return json.dumps(dialogue.as_dict())


class SerializedTrackerAsDict(SerializedTrackerRepresentation[Dict]):
    """Mixin class that returns the serialized tracker as dictionary."""

    @staticmethod
    def serialise_tracker(tracker: DialogueStateTracker) -> Dict:
        """Serializes the tracker, returns representation of the tracker."""
        d = tracker.as_dialogue().as_dict()
        d.update({"sender_id": tracker.sender_id})
        return d


class TrackerStore:
    """Represents common behavior and interface for all `TrackerStore`s."""

    def __init__(
        self,
        domain: Optional[Domain],
        event_broker: Optional[EventBroker] = None,
        **kwargs: Dict[Text, Any],
    ) -> None:
        """Create a TrackerStore.

        Args:
            domain: The `Domain` to initialize the `DialogueStateTracker`.
            event_broker: An event broker to publish any new events to another
                destination.
            kwargs: Additional kwargs.
        """
        self._domain = domain or Domain.empty()
        self.event_broker = event_broker
        self.max_event_history: Optional[int] = None

    @staticmethod
    def create(
        obj: Union[TrackerStore, EndpointConfig, None],
        domain: Optional[Domain] = None,
        event_broker: Optional[EventBroker] = None,
    ) -> TrackerStore:
        """Factory to create a tracker store."""
        if isinstance(obj, TrackerStore):
            return obj

        from botocore.exceptions import BotoCoreError
        import pymongo.errors
        import sqlalchemy.exc

        try:
            _tracker_store = plugin_manager().hook.create_tracker_store(
                endpoint_config=obj,
                domain=domain,
                event_broker=event_broker,
            )

            tracker_store = (
                _tracker_store
                if _tracker_store
                else create_tracker_store(obj, domain, event_broker)
            )

            return tracker_store
        except (
            BotoCoreError,
            pymongo.errors.ConnectionFailure,
            sqlalchemy.exc.OperationalError,
            ConnectionError,
            pymongo.errors.OperationFailure,
        ) as error:
            raise ConnectionException(
                "Cannot connect to tracker store." + str(error)
            ) from error

    async def get_or_create_tracker(
        self,
        sender_id: Text,
        max_event_history: Optional[int] = None,
        append_action_listen: bool = True,
    ) -> "DialogueStateTracker":
        """Returns tracker or creates one if the retrieval returns None.

        Args:
            sender_id: Conversation ID associated with the requested tracker.
            max_event_history: Value to update the tracker store's max event history to.
            append_action_listen: Whether or not to append an initial `action_listen`.
        """
        self.max_event_history = max_event_history

        tracker = await self.retrieve(sender_id)

        if tracker is None:
            tracker = await self.create_tracker(
                sender_id, append_action_listen=append_action_listen
            )

        return tracker

    def init_tracker(self, sender_id: Text) -> "DialogueStateTracker":
        """Returns a Dialogue State Tracker."""
        return DialogueStateTracker(
            sender_id,
            self.domain.slots,
            max_event_history=self.max_event_history,
        )

    async def create_tracker(
        self, sender_id: Text, append_action_listen: bool = True
    ) -> DialogueStateTracker:
        """Creates a new tracker for `sender_id`.

        The tracker begins with a `SessionStarted` event and is initially listening.

        Args:
            sender_id: Conversation ID associated with the tracker.
            append_action_listen: Whether or not to append an initial `action_listen`.

        Returns:
            The newly created tracker for `sender_id`.
        """
        tracker = self.init_tracker(sender_id)

        if append_action_listen:
            tracker.update(ActionExecuted(ACTION_LISTEN_NAME))

        await self.save(tracker)

        return tracker

    async def save(self, tracker: DialogueStateTracker) -> None:
        """Save method that will be overridden by specific tracker."""
        raise NotImplementedError()

    async def exists(self, conversation_id: Text) -> bool:
        """Checks if tracker exists for the specified ID.

        This method may be overridden by the specific tracker store for
        faster implementations.

        Args:
            conversation_id: Conversation ID to check if the tracker exists.

        Returns:
            `True` if the tracker exists, `False` otherwise.
        """
        return await self.retrieve(conversation_id) is not None

    async def retrieve(self, sender_id: Text) -> Optional[DialogueStateTracker]:
        """Retrieves tracker for the latest conversation session.

        This method will be overridden by the specific tracker store.

        Args:
            sender_id: Conversation ID to fetch the tracker for.

        Returns:
            Tracker containing events from the latest conversation sessions.
        """
        raise NotImplementedError()

    async def retrieve_full_tracker(
        self, conversation_id: Text
    ) -> Optional[DialogueStateTracker]:
        """Retrieve method for fetching all tracker events across conversation sessions\
        that may be overridden by specific tracker.

        The default implementation uses `self.retrieve()`.

        Args:
            conversation_id: The conversation ID to retrieve the tracker for.

        Returns:
            The fetch tracker containing all events across session starts.
        """
        return await self.retrieve(conversation_id)

    async def get_or_create_full_tracker(
        self,
        sender_id: Text,
        append_action_listen: bool = True,
    ) -> "DialogueStateTracker":
        """Returns tracker or creates one if the retrieval returns None.

        Args:
            sender_id: Conversation ID associated with the requested tracker.
            append_action_listen: Whether to append an initial `action_listen`.

        Returns:
            The tracker for the conversation ID.
        """
        tracker = await self.retrieve_full_tracker(sender_id)

        if tracker is None:
            tracker = await self.create_tracker(
                sender_id, append_action_listen=append_action_listen
            )

        return tracker

    async def stream_events(self, tracker: DialogueStateTracker) -> None:
        """Streams events to a message broker."""
        if self.event_broker is None:
            logger.debug("No event broker configured. Skipping streaming events.")
            return None

        old_tracker = await self.retrieve(tracker.sender_id)
        new_events = TrackerEventDiffEngine.event_difference(old_tracker, tracker)

        await self._stream_new_events(self.event_broker, new_events, tracker.sender_id)

    async def _stream_new_events(
        self,
        event_broker: EventBroker,
        new_events: List[Event],
        sender_id: Text,
    ) -> None:
        """Publishes new tracker events to a message broker."""
        for event in new_events:
            body = {"sender_id": sender_id}
            body.update(event.as_dict())
            event_broker.publish(body)

    async def keys(self) -> Iterable[Text]:
        """Returns the set of values for the tracker store's primary key."""
        raise NotImplementedError()

    def deserialise_tracker(
        self, sender_id: Text, serialised_tracker: Union[Text, bytes]
    ) -> Optional[DialogueStateTracker]:
        """Deserializes the tracker and returns it."""
        tracker = self.init_tracker(sender_id)

        try:
            dialogue = Dialogue.from_parameters(json.loads(serialised_tracker))
        except UnicodeDecodeError as e:
            raise TrackerDeserialisationException(
                "Tracker cannot be deserialised. "
                "Trackers must be serialised as json. "
                "Support for deserialising pickled trackers has been removed."
            ) from e

        tracker.recreate_from_dialogue(dialogue)

        return tracker

    @property
    def domain(self) -> Domain:
        """Returns the domain of the tracker store."""
        return self._domain

    @domain.setter
    def domain(self, domain: Optional[Domain]) -> None:
        self._domain = domain or Domain.empty()


class InMemoryTrackerStore(TrackerStore, SerializedTrackerAsText):
    """Stores conversation history in memory."""

    def __init__(
        self,
        domain: Domain,
        event_broker: Optional[EventBroker] = None,
        **kwargs: Dict[Text, Any],
    ) -> None:
        """Initializes the tracker store."""
        self.store: Dict[Text, Text] = {}
        super().__init__(domain, event_broker, **kwargs)

    async def save(self, tracker: DialogueStateTracker) -> None:
        """Updates and saves the current conversation state."""
        await self.stream_events(tracker)
        serialised = InMemoryTrackerStore.serialise_tracker(tracker)
        self.store[tracker.sender_id] = serialised

    async def retrieve(self, sender_id: Text) -> Optional[DialogueStateTracker]:
        """Returns tracker matching sender_id."""
        return await self._retrieve(sender_id, fetch_all_sessions=False)

    async def keys(self) -> Iterable[Text]:
        """Returns sender_ids of the Tracker Store in memory."""
        return self.store.keys()

    async def retrieve_full_tracker(
        self, sender_id: Text
    ) -> Optional[DialogueStateTracker]:
        """Returns tracker matching sender_id.

        Args:
            sender_id: Conversation ID to fetch the tracker for.
        """
        return await self._retrieve(sender_id, fetch_all_sessions=True)

    async def _retrieve(
        self, sender_id: Text, fetch_all_sessions: bool
    ) -> Optional[DialogueStateTracker]:
        """Returns tracker matching sender_id.

        Args:
            sender_id: Conversation ID to fetch the tracker for.
            fetch_all_sessions: Whether to fetch all sessions or only the last one.
        """
        if sender_id not in self.store:
            logger.debug(f"Could not find tracker for conversation ID '{sender_id}'.")
            return None

        logger.debug(f"Recreating tracker for id '{sender_id}'")

        tracker = self.deserialise_tracker(sender_id, self.store[sender_id])

        if not tracker:
            logger.debug(f"Could not find tracker for conversation ID '{sender_id}'.")
            return None

        if fetch_all_sessions:
            return tracker

        # only return the last session
        multiple_tracker_sessions = (
            rasa.shared.core.trackers.get_trackers_for_conversation_sessions(tracker)
        )

        if 0 <= len(multiple_tracker_sessions) <= 1:
            return tracker

        return multiple_tracker_sessions[-1]


class MongoTrackerStore(TrackerStore, SerializedTrackerAsText):
    """Stores conversation history in Mongo.

    Property methods:
        conversations: returns the current conversation
    """

    def __init__(
        self,
        domain: Domain,
        host: Optional[Text] = "mongodb://localhost:27017",
        db: Optional[Text] = "rasa",
        username: Optional[Text] = None,
        password: Optional[Text] = None,
        auth_source: Optional[Text] = "admin",
        collection: Text = "conversations",
        event_broker: Optional[EventBroker] = None,
        **kwargs: Dict[Text, Any],
    ) -> None:
        from pymongo.database import Database
        from pymongo import MongoClient

        self.client: MongoClient = MongoClient(
            host,
            username=username,
            password=password,
            authSource=auth_source,
            # delay connect until process forking is done
            connect=False,
        )

        self.db = Database(self.client, db)
        self.collection = collection
        super().__init__(domain, event_broker, **kwargs)

        self._ensure_indices()

    @property
    def conversations(self) -> Collection:
        """Returns the current conversation."""
        return self.db[self.collection]

    def _ensure_indices(self) -> None:
        """Create an index on the sender_id."""
        self.conversations.create_index("sender_id")

    @staticmethod
    def _current_tracker_state_without_events(tracker: DialogueStateTracker) -> Dict:
        # get current tracker state and remove `events` key from state
        # since events are pushed separately in the `update_one()` operation
        state = tracker.current_state(EventVerbosity.ALL)
        state.pop("events", None)

        return state

    async def save(self, tracker: DialogueStateTracker) -> None:
        """Saves the current conversation state."""
        await self.stream_events(tracker)

        additional_events = self._additional_events(tracker)

        self.conversations.update_one(
            {"sender_id": tracker.sender_id},
            {
                "$set": self._current_tracker_state_without_events(tracker),
                "$push": {
                    "events": {"$each": [e.as_dict() for e in additional_events]}
                },
            },
            upsert=True,
        )

    def _additional_events(self, tracker: DialogueStateTracker) -> Iterator:
        """Return events from the tracker which aren't currently stored.

        Args:
            tracker: Tracker to inspect.

        Returns:
            List of serialised events that aren't currently stored.

        """
        stored = self.conversations.find_one({"sender_id": tracker.sender_id}) or {}
        all_events = self._events_from_serialized_tracker(stored)

        number_events_since_last_session = len(
            self._events_since_last_session_start(all_events)
        )

        return itertools.islice(
            tracker.events, number_events_since_last_session, len(tracker.events)
        )

    @staticmethod
    def _events_from_serialized_tracker(serialised: Dict) -> List[Dict]:
        return serialised.get("events", [])

    @staticmethod
    def _events_since_last_session_start(events: List[Dict]) -> List[Dict]:
        """Retrieve events since and including the latest `SessionStart` event.

        Args:
            events: All events for a conversation ID.

        Returns:
            List of serialised events since and including the latest `SessionStarted`
            event. Returns all events if no such event is found.

        """
        events_after_session_start = []
        for event in reversed(events):
            events_after_session_start.append(event)
            if event["event"] == SessionStarted.type_name:
                break

        return list(reversed(events_after_session_start))

    async def _retrieve(
        self, sender_id: Text, fetch_events_from_all_sessions: bool
    ) -> Optional[List[Dict[Text, Any]]]:
        stored = self.conversations.find_one({"sender_id": sender_id})

        # look for conversations which have used an `int` sender_id in the past
        # and update them.
        if not stored and sender_id.isdigit():
            from pymongo import ReturnDocument

            stored = self.conversations.find_one_and_update(
                {"sender_id": int(sender_id)},
                {"$set": {"sender_id": str(sender_id)}},
                return_document=ReturnDocument.AFTER,
            )

        if not stored:
            return None

        events = self._events_from_serialized_tracker(stored)

        if not fetch_events_from_all_sessions:
            events = self._events_since_last_session_start(events)

        return events

    async def retrieve(self, sender_id: Text) -> Optional[DialogueStateTracker]:
        """Retrieves tracker for the latest conversation session."""
        events = await self._retrieve(sender_id, fetch_events_from_all_sessions=False)

        if not events:
            return None

        return DialogueStateTracker.from_dict(sender_id, events, self.domain.slots)

    async def retrieve_full_tracker(
        self, conversation_id: Text
    ) -> Optional[DialogueStateTracker]:
        """Fetching all tracker events across conversation sessions."""
        events = await self._retrieve(
            conversation_id, fetch_events_from_all_sessions=True
        )

        if not events:
            return None

        return DialogueStateTracker.from_dict(
            conversation_id, events, self.domain.slots
        )

    async def keys(self) -> Iterable[Text]:
        """Returns sender_ids of the Mongo Tracker Store."""
        return [c["sender_id"] for c in self.conversations.find()]


def _create_sequence(table_name: Text) -> "Sequence":
    """Creates a sequence object for a specific table name.

    If using Oracle you will need to create a sequence in your database,
    as described here: https://rasa.com/docs/rasa/tracker-stores#sqltrackerstore
    Args:
        table_name: The name of the table, which gets a Sequence assigned

    Returns: A `Sequence` object
    """
    from sqlalchemy.ext.declarative import declarative_base

    sequence_name = f"{table_name}_seq"
    Base = declarative_base()
    return sa.Sequence(sequence_name, metadata=Base.metadata, optional=True)


def is_postgresql_url(url: Union[Text, "URL"]) -> bool:
    """Determine whether `url` configures a PostgreSQL connection.

    Args:
        url: SQL connection URL.

    Returns:
        `True` if `url` is a PostgreSQL connection URL.
    """
    if isinstance(url, str):
        return "postgresql" in url

    return url.drivername == "postgresql"


def create_engine_kwargs(url: Union[Text, "URL"]) -> Dict[Text, Any]:
    """Get `sqlalchemy.create_engine()` kwargs.

    Args:
        url: SQL connection URL.

    Returns:
        kwargs to be passed into `sqlalchemy.create_engine()`.
    """
    if not is_postgresql_url(url):
        return {}

    kwargs: Dict[Text, Any] = {}

    schema_name = os.environ.get(POSTGRESQL_SCHEMA)

    if schema_name:
        logger.debug(f"Using PostgreSQL schema '{schema_name}'.")
        kwargs["connect_args"] = {"options": f"-csearch_path={schema_name}"}

    # pool_size and max_overflow can be set to control the number of
    # connections that are kept in the connection pool. Not available
    # for SQLite, and only  tested for PostgreSQL. See
    # https://docs.sqlalchemy.org/en/13/core/pooling.html#sqlalchemy.pool.QueuePool
    kwargs["pool_size"] = int(
        os.environ.get(POSTGRESQL_POOL_SIZE, POSTGRESQL_DEFAULT_POOL_SIZE)
    )
    kwargs["max_overflow"] = int(
        os.environ.get(POSTGRESQL_MAX_OVERFLOW, POSTGRESQL_DEFAULT_MAX_OVERFLOW)
    )

    return kwargs


def ensure_schema_exists(session: "Session") -> None:
    """Ensure that the requested PostgreSQL schema exists in the database.

    Args:
        session: Session used to inspect the database.

    Raises:
        `ValueError` if the requested schema does not exist.
    """
    schema_name = os.environ.get(POSTGRESQL_SCHEMA)

    if not schema_name:
        return

    engine = session.get_bind()

    if is_postgresql_url(engine.url):
        query = sa.exists(
            sa.select([(sa.text("schema_name"))])
            .select_from(sa.text("information_schema.schemata"))
            .where(sa.text(f"schema_name = '{schema_name}'"))
        )
        if not session.query(query).scalar():
            raise ValueError(schema_name)


def validate_port(port: Any) -> Optional[int]:
    """Ensure that port can be converted to integer.

    Raises:
        RasaException if port cannot be cast to integer.
    """
    if port is not None and not isinstance(port, int):
        try:
            port = int(port)
        except ValueError as e:
            raise RasaException(f"The port '{port}' cannot be cast to integer.") from e

    return port


class FailSafeTrackerStore(TrackerStore):
    """Tracker store wrapper.

    Allows a fallback to a different tracker store in case of errors.
    """

    def __init__(
        self,
        tracker_store: TrackerStore,
        on_tracker_store_error: Optional[Callable[[Exception], None]] = None,
        fallback_tracker_store: Optional[TrackerStore] = None,
    ) -> None:
        """Create a `FailSafeTrackerStore`.

        Args:
            tracker_store: Primary tracker store.
            on_tracker_store_error: Callback which is called when there is an error
                in the primary tracker store.
            fallback_tracker_store: Fallback tracker store.
        """
        self._fallback_tracker_store: Optional[TrackerStore] = fallback_tracker_store
        self._tracker_store = tracker_store
        self._on_tracker_store_error = on_tracker_store_error

        super().__init__(tracker_store.domain, tracker_store.event_broker)

    @property
    def domain(self) -> Domain:
        """Returns the domain of the primary tracker store."""
        return self._tracker_store.domain

    @domain.setter
    def domain(self, domain: Domain) -> None:
        self._tracker_store.domain = domain

        if self._fallback_tracker_store:
            self._fallback_tracker_store.domain = domain

    @property
    def fallback_tracker_store(self) -> TrackerStore:
        """Returns the fallback tracker store."""
        if not self._fallback_tracker_store:
            self._fallback_tracker_store = InMemoryTrackerStore(
                self._tracker_store.domain, self._tracker_store.event_broker
            )

        return self._fallback_tracker_store

    def on_tracker_store_error(self, error: Exception) -> None:
        """Calls the callback when there is an error in the primary tracker store."""
        if self._on_tracker_store_error:
            self._on_tracker_store_error(error)
        else:
            logger.error(
                f"Error happened when trying to save conversation tracker to "
                f"'{self._tracker_store.__class__.__name__}'. Falling back to use "
                f"the '{InMemoryTrackerStore.__name__}'. Please "
                f"investigate the following error: {error}."
            )

    async def retrieve(self, sender_id: Text) -> Optional[DialogueStateTracker]:
        """Calls `retrieve` method of primary tracker store."""
        try:
            return await self._tracker_store.retrieve(sender_id)
        except Exception as e:
            self.on_tracker_store_retrieve_error(e)
            return None

    async def keys(self) -> Iterable[Text]:
        """Calls `keys` method of primary tracker store."""
        try:
            return await self._tracker_store.keys()
        except Exception as e:
            self.on_tracker_store_error(e)
            return []

    async def save(self, tracker: DialogueStateTracker) -> None:
        """Calls `save` method of primary tracker store."""
        try:
            await self._tracker_store.save(tracker)
        except Exception as e:
            self.on_tracker_store_error(e)
            await self.fallback_tracker_store.save(tracker)

    async def retrieve_full_tracker(
        self, sender_id: Text
    ) -> Optional[DialogueStateTracker]:
        """Calls `retrieve_full_tracker` method of primary tracker store.

        Args:
            sender_id: The sender id of the tracker to retrieve.
        """
        try:
            return await self._tracker_store.retrieve_full_tracker(sender_id)
        except Exception as e:
            self.on_tracker_store_retrieve_error(e)
            return None

    def on_tracker_store_retrieve_error(self, error: Exception) -> None:
        """Calls `_on_tracker_store_error` callable attribute if set.

        Otherwise, logs the error.

        Args:
            error: The error that occurred.
        """
        if self._on_tracker_store_error:
            self._on_tracker_store_error(error)
        else:
            logger.error(
                f"Error happened when trying to retrieve conversation tracker from "
                f"'{self._tracker_store.__class__.__name__}'. Falling back to use "
                f"the '{InMemoryTrackerStore.__name__}'. Please "
                f"investigate the following error: {error}."
            )


def _create_from_endpoint_config(
    endpoint_config: Optional[EndpointConfig] = None,
    domain: Optional[Domain] = None,
    event_broker: Optional[EventBroker] = None,
    ) -> TrackerStore:
    """Given an endpoint configuration, create a proper tracker store object."""
    domain = domain or Domain.empty()

    if endpoint_config is None or endpoint_config.type is None:
        # default tracker store if no type is set
        tracker_store: TrackerStore = InMemoryTrackerStore(domain, event_broker)
    elif endpoint_config.type.lower() == "redis":
        tracker_store = RedisTrackerStore(
            domain=domain,
            host=endpoint_config.url,
            event_broker=event_broker,
            **endpoint_config.kwargs,
        )
    elif endpoint_config.type.lower() == "mongod":
        tracker_store = MongoTrackerStore(
            domain=domain,
            host=endpoint_config.url,
            event_broker=event_broker,
            **endpoint_config.kwargs,
        )
    elif endpoint_config.type.lower() == "sql":
        tracker_store = SQLTrackerStore(
            domain=domain,
            host=endpoint_config.url,
            event_broker=event_broker,
            **endpoint_config.kwargs,
        )
    elif endpoint_config.type.lower() == "dynamo":
        tracker_store = DynamoTrackerStore(
            domain=domain, event_broker=event_broker, **endpoint_config.kwargs
        )
    else:
        tracker_store = _load_from_module_name_in_endpoint_config(
            domain, endpoint_config, event_broker
        )

    logger.debug(f"Connected to {tracker_store.__class__.__name__}.")

    return tracker_store


def _load_from_module_name_in_endpoint_config(
    domain: Domain, store: EndpointConfig, event_broker: Optional[EventBroker] = None
    ) -> TrackerStore:
    """Initializes a custom tracker.

    Defaults to the InMemoryTrackerStore if the module path can not be found.

    Args:
        domain: defines the universe in which the assistant operates
        store: the specific tracker store
        event_broker: an event broker to publish events

    Returns:
        a tracker store from a specified type in a stores endpoint configuration
    """
    try:
        tracker_store_class = rasa.shared.utils.common.class_from_module_path(
            store.type
        )

        return tracker_store_class(
            host=store.url, domain=domain, event_broker=event_broker, **store.kwargs
        )
    except (AttributeError, ImportError):
        rasa.shared.utils.io.raise_warning(
            f"Tracker store with type '{store.type}' not found. "
            f"Using `InMemoryTrackerStore` instead."
        )
        return InMemoryTrackerStore(domain)


def create_tracker_store(
    endpoint_config: Optional[EndpointConfig],
    domain: Optional[Domain] = None,
    event_broker: Optional[EventBroker] = None,
    ) -> TrackerStore:
    """Creates a tracker store based on the current configuration."""
    tracker_store = _create_from_endpoint_config(endpoint_config, domain, event_broker)

    if not check_if_tracker_store_async(tracker_store):
        rasa.shared.utils.io.raise_deprecation_warning(
            f"Tracker store implementation "
            f"{tracker_store.__class__.__name__} "
            f"is not asynchronous. Non-asynchronous tracker stores "
            f"are currently deprecated and will be removed in 4.0. "
            f"Please make the following methods async: "
            f"{_get_async_tracker_store_methods()}"
        )
        tracker_store = AwaitableTrackerStore(tracker_store)

    return tracker_store


class AwaitableTrackerStore(TrackerStore):
    """Wraps a tracker store so it can be implemented with async overrides."""

    def __init__(
        self,
        tracker_store: TrackerStore,
    ) -> None:
        """Create a `AwaitableTrackerStore`.

        Args:
            tracker_store: the wrapped tracker store.
        """
        self._tracker_store = tracker_store

        super().__init__(tracker_store.domain, tracker_store.event_broker)

    @property
    def domain(self) -> Domain:
        """Returns the domain of the primary tracker store."""
        return self._tracker_store.domain

    @domain.setter
    def domain(self, domain: Optional[Domain]) -> None:
        """Setter method to modify the wrapped tracker store's domain field."""
        self._tracker_store.domain = domain or Domain.empty()

    @staticmethod
    def create(
        obj: Union[TrackerStore, EndpointConfig, None],
        domain: Optional[Domain] = None,
        event_broker: Optional[EventBroker] = None,
    ) -> TrackerStore:
        """Wrapper to call `create` method of primary tracker store."""
        if isinstance(obj, TrackerStore):
            return AwaitableTrackerStore(obj)
        elif isinstance(obj, EndpointConfig):
            return AwaitableTrackerStore(_create_from_endpoint_config(obj))
        else:
            raise ValueError(
                f"{type(obj).__name__} supplied "
                f"but expected object of type {TrackerStore.__name__} or "
                f"of type {EndpointConfig.__name__}."
            )

    async def retrieve(self, sender_id: Text) -> Optional[DialogueStateTracker]:
        """Wrapper to call `retrieve` method of primary tracker store."""
        result = self._tracker_store.retrieve(sender_id)
        return (
            await result
            if isawaitable(result)
            else result  # type: ignore[return-value]
        )

    async def keys(self) -> Iterable[Text]:
        """Wrapper to call `keys` method of primary tracker store."""
        result = self._tracker_store.keys()
        return await result if isawaitable(result) else result

    async def save(self, tracker: DialogueStateTracker) -> None:
        """Wrapper to call `save` method of primary tracker store."""
        result = self._tracker_store.save(tracker)
        return await result if isawaitable(result) else result

    async def retrieve_full_tracker(
        self, conversation_id: Text
    ) -> Optional[DialogueStateTracker]:
        """Wrapper to call `retrieve_full_tracker` method of primary tracker store."""
        result = self._tracker_store.retrieve_full_tracker(conversation_id)
        return (
            await result
            if isawaitable(result)
            else result  # type: ignore[return-value]
        )

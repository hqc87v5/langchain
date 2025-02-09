"""Astra DB - based chat message history, based on astrapy."""
from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, List, Optional, Sequence

from langchain_community.utilities.astradb import (
    SetupMode,
    _AstraDBCollectionEnvironment,
)

if TYPE_CHECKING:
    from astrapy.db import AstraDB

from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import (
    BaseMessage,
    message_to_dict,
    messages_from_dict,
)

DEFAULT_COLLECTION_NAME = "langchain_message_store"


class AstraDBChatMessageHistory(BaseChatMessageHistory):
    """Chat message history that stores history in Astra DB.

    Args (only keyword-arguments accepted):
        session_id: arbitrary key that is used to store the messages
            of a single chat session.
        collection_name (str): name of the Astra DB collection to create/use.
        token (Optional[str]): API token for Astra DB usage.
        api_endpoint (Optional[str]): full URL to the API endpoint,
            such as "https://<DB-ID>-us-east1.apps.astra.datastax.com".
        astra_db_client (Optional[Any]): *alternative to token+api_endpoint*,
            you can pass an already-created 'astrapy.db.AstraDB' instance.
        namespace (Optional[str]): namespace (aka keyspace) where the
            collection is created. Defaults to the database's "default namespace".
    """

    def __init__(
        self,
        *,
        session_id: str,
        collection_name: str = DEFAULT_COLLECTION_NAME,
        token: Optional[str] = None,
        api_endpoint: Optional[str] = None,
        astra_db_client: Optional[AstraDB] = None,
        namespace: Optional[str] = None,
        setup_mode: SetupMode = SetupMode.SYNC,
        pre_delete_collection: bool = False,
    ) -> None:
        """Create an Astra DB chat message history."""
        self.astra_env = _AstraDBCollectionEnvironment(
            collection_name=collection_name,
            token=token,
            api_endpoint=api_endpoint,
            astra_db_client=astra_db_client,
            namespace=namespace,
            setup_mode=setup_mode,
            pre_delete_collection=pre_delete_collection,
        )

        self.collection = self.astra_env.collection
        self.async_collection = self.astra_env.async_collection

        self.session_id = session_id
        self.collection_name = collection_name

    @property
    def messages(self) -> List[BaseMessage]:
        """Retrieve all session messages from DB"""
        self.astra_env.ensure_db_setup()
        message_blobs = [
            doc["body_blob"]
            for doc in sorted(
                self.collection.paginated_find(
                    filter={
                        "session_id": self.session_id,
                    },
                    projection={
                        "timestamp": 1,
                        "body_blob": 1,
                    },
                ),
                key=lambda _doc: _doc["timestamp"],
            )
        ]
        items = [json.loads(message_blob) for message_blob in message_blobs]
        messages = messages_from_dict(items)
        return messages

    @messages.setter
    def messages(self, messages: List[BaseMessage]) -> None:
        raise NotImplementedError("Use add_messages instead")

    async def aget_messages(self) -> List[BaseMessage]:
        """Retrieve all session messages from DB"""
        await self.astra_env.aensure_db_setup()
        docs = self.async_collection.paginated_find(
            filter={
                "session_id": self.session_id,
            },
            projection={
                "timestamp": 1,
                "body_blob": 1,
            },
        )
        sorted_docs = sorted(
            [doc async for doc in docs],
            key=lambda _doc: _doc["timestamp"],
        )
        message_blobs = [doc["body_blob"] for doc in sorted_docs]
        items = [json.loads(message_blob) for message_blob in message_blobs]
        messages = messages_from_dict(items)
        return messages

    def add_messages(self, messages: Sequence[BaseMessage]) -> None:
        """Write a message to the table"""
        self.astra_env.ensure_db_setup()
        docs = [
            {
                "timestamp": time.time(),
                "session_id": self.session_id,
                "body_blob": json.dumps(message_to_dict(message)),
            }
            for message in messages
        ]
        self.collection.chunked_insert_many(docs)

    async def aadd_messages(self, messages: Sequence[BaseMessage]) -> None:
        """Write a message to the table"""
        await self.astra_env.aensure_db_setup()
        docs = [
            {
                "timestamp": time.time(),
                "session_id": self.session_id,
                "body_blob": json.dumps(message_to_dict(message)),
            }
            for message in messages
        ]
        await self.async_collection.chunked_insert_many(docs)

    def clear(self) -> None:
        """Clear session memory from DB"""
        self.astra_env.ensure_db_setup()
        self.collection.delete_many(filter={"session_id": self.session_id})

    async def aclear(self) -> None:
        """Clear session memory from DB"""
        await self.astra_env.aensure_db_setup()
        await self.async_collection.delete_many(filter={"session_id": self.session_id})

import re
from datetime import datetime
from enum import Enum
from os.path import join, normpath
from typing import Dict, List, Optional
from uuid import UUID

from fastapi import Path
from pydantic import BaseModel, Field, root_validator

PathPublishId = Path(
    ...,
    title="publish ID",
    description="UUID of an existing publish object.",
)

PathTaskId = Path(
    ..., title="task ID", description="UUID of an existing task object."
)


def normalize_path(path: str):
    if path:
        path = normpath(path)
        path = "/" + path if not path.startswith("/") else path
    return path


class ItemBase(BaseModel):
    web_uri: str = Field(
        ...,
        description="URI, relative to CDN root, which shall be used to expose this object.",
    )
    object_key: str = Field(
        "",
        description=(
            "Key of blob to be exposed; should be the SHA256 checksum of a previously uploaded "
            "piece of content, in lowercase hex-digest form. \n\n"
            "Alternatively, the string 'absent' to indicate that no content shall be exposed at the given URI. "
            "Publishing an item with key 'absent' can be used to effectively delete formerly published "
            "content from the point of view of a CDN consumer."
        ),
    )
    content_type: str = Field(
        "",
        description="Content type of the content associated with this object.",
    )
    link_to: str = Field("", description="Path of file targeted by symlink.")

    @root_validator()
    @classmethod
    def validate_item(cls, values):
        web_uri = values.get("web_uri")
        object_key = values.get("object_key")
        content_type = values.get("content_type")
        link_to = values.get("link_to")

        if not web_uri:
            raise ValueError("No URI: %s" % values)
        values["web_uri"] = normalize_path(web_uri)

        if link_to and object_key:
            raise ValueError(
                "Both link target and object key present: %s" % values
            )
        if link_to and content_type:
            raise ValueError("Content type specified for link: %s" % values)

        if link_to:
            values["link_to"] = normalize_path(link_to)
        elif object_key:
            pattern = re.compile(r"[0-9a-f]{64}")
            if object_key == "absent":
                if content_type:
                    raise ValueError(
                        "Cannot set content type when object_key is 'absent': %s"
                        % values
                    )
            elif not re.match(pattern, object_key):
                raise ValueError(
                    "Invalid object key; must be sha256sum: %s" % values
                )
        else:
            raise ValueError("No object key or link target: %s" % values)

        if content_type:
            # Enforce MIME type structure
            # TYPE/SUBTYPE[+SUFFIX][;PARAMETER=VALUE]
            pattern = re.compile(
                r"^[-\w]+/[-.\w]+(\+[-\w]*)?(;[-\w]+=[-\w]+)?"
            )
            if not re.match(pattern, content_type):
                raise ValueError("Invalid content type: %s" % values)

        return values


class Item(ItemBase):
    publish_id: UUID = Field(
        ..., description="Unique ID of publish object containing this item."
    )

    class Config:
        orm_mode = True


class PublishStates(str, Enum):
    pending = "PENDING"
    committing = "COMMITTING"
    committed = "COMMITTED"
    failed = "FAILED"

    @classmethod
    def terminal(cls) -> List["PublishStates"]:
        return [cls.committed, cls.failed]


class PublishBase(BaseModel):
    id: UUID = Field(..., description="Unique ID of publish object.")


class Publish(PublishBase):
    env: str = Field(
        ..., description="""Environment to which this publish belongs."""
    )
    state: PublishStates = Field(
        ..., description="Current state of this publish."
    )
    updated: datetime = Field(
        None,
        description="DateTime of last update to this publish. None if never updated.",
    )
    links: Dict[str, str] = Field(
        {}, description="""URL links related to this publish."""
    )
    items: List[Item] = Field(
        [],
        description="""All items (pieces of content) included in this publish.""",
    )

    @root_validator
    @classmethod
    def make_links(cls, values):
        _self = join("/", values["env"], "publish", str(values["id"]))
        values["links"] = {"self": _self, "commit": join(_self, "commit")}
        return values

    class Config:
        orm_mode = True


class TaskStates(str, Enum):
    not_started = "NOT_STARTED"
    in_progress = "IN_PROGRESS"
    complete = "COMPLETE"
    failed = "FAILED"

    @classmethod
    def terminal(cls) -> List["TaskStates"]:
        return [cls.failed, cls.complete]


class Task(BaseModel):
    id: UUID = Field(..., description="Unique ID of task object.")
    publish_id: Optional[UUID] = Field(
        ..., description="Unique ID of publish object handled by this task."
    )
    state: TaskStates = Field(..., description="Current state of this task.")
    updated: datetime = Field(
        None,
        description="DateTime of last update to this task. None if never updated.",
    )
    links: Dict[str, str] = Field(
        {}, description="""URL links related to this task."""
    )

    @root_validator
    @classmethod
    def make_links(cls, values):
        values["links"] = {"self": join("/task", str(values["id"]))}
        return values

    class Config:
        orm_mode = True


class MessageResponse(BaseModel):
    detail: str = Field(
        ..., description="A human-readable message with additional info."
    )


class EmptyResponse(BaseModel):
    """An empty object."""

from contextlib import AbstractContextManager
from langgraph.checkpoint.base import BaseCheckpointSaver

class PostgresSaver(BaseCheckpointSaver):
    @classmethod
    def from_conn_string(cls, conn_string: str) -> AbstractContextManager[PostgresSaver]: ...
    def setup(self) -> None: ...

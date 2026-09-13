from collections.abc import Sequence
import numpy as np
from numpy.typing import NDArray

class BM25Okapi:
    def __init__(self, corpus: Sequence[Sequence[str]]) -> None: ...
    def get_scores(self, query: Sequence[str]) -> NDArray[np.float64]: ...

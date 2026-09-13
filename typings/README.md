# Adapter type declarations

These declarations describe only the dependency methods called by FailureLab.
They let Mypy check the base installation without downloading optional ML models
or installing the PostgreSQL deployment extra. They contain no runtime code and
do not establish that either optional integration has been exercised.

`rank_bm25` lacks a `py.typed` marker. The optional sentence-transformer and
PostgreSQL declarations cover their existing adapter calls. Keep these signatures
in sync when changing those calls; missing imports and type errors remain enabled.

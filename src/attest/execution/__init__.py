"""Controller/executor split (X-01): a versioned, content-addressed request/result
protocol between the privileged controller and an untrusted executor.

The controller mints a task nonce per run, materialises immutable inputs by
digest, dispatches to an adapter, and accepts a result only when the envelope
answers that nonce and every artifact matches its declared digest and bound.
The adapter that runs pytest in-process on the developer's host is
``local_development_best_effort`` and is never a production profile.
"""

# `Generate` files a question under the wrong topic when the reply names another

- Where: `app/modules/education/routes.py` `generate_now` (falls back to `items[0]` when no element names the chosen topic)
- Found: 2026-09-12, sync-architecture
- Status: open

What happens: the page action asks for one question on the topic that has waited longest and then looks for an element whose `topic_id` is that topic. When none matches it takes the first element anyway and inserts it under the chosen topic, and the validator only checks that the topic is active. A reply carrying another topic's id therefore becomes a question on the wrong topic, counted against the topic that waited longest. The nightly task rejects such an element as `not asked for`; the page action does not.

Expected: a reply that does not name the asked topic is a 502, the same as any other rejected reply.

Fix: remove the `items[0]` fallback and let the missing match raise into the existing 502 path.

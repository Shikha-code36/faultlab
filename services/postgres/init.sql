CREATE TABLE IF NOT EXISTS items (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    value NUMERIC NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO items (name, value)
SELECT
    'item-' || gs,
    (random() * 1000)::numeric(10, 2)
FROM generate_series(1, 5000) AS gs
ON CONFLICT DO NOTHING;

CREATE INDEX IF NOT EXISTS idx_items_name ON items (name);

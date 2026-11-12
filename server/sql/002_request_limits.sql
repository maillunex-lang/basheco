-- Request throttling counters, updated atomically by the API.
CREATE TABLE request_limits (
  bucket text NOT NULL,
  key_hash text NOT NULL,
  window_start timestamptz NOT NULL,
  attempts integer NOT NULL CHECK (attempts >= 0),
  PRIMARY KEY (bucket, key_hash)
);
CREATE INDEX request_limits_window_idx ON request_limits(window_start);

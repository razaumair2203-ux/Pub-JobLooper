-- Sanitized representative schema from Lodestar.
-- Retrieval plane: derived from primary-source documents and rebuildable.

CREATE TABLE IF NOT EXISTS chunks (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id    uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  chunk_text     text NOT NULL,
  chunk_index    integer NOT NULL,
  section_label  text,

  tsv tsvector GENERATED ALWAYS AS (
    to_tsvector('english', coalesce(section_label, '') || ' ' || chunk_text)
  ) STORED,

  embedding      vector(1024),
  criterion_tags text[] NOT NULL DEFAULT '{}',
  visa_class     text[] NOT NULL DEFAULT '{}',
  metadata       jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at     timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT chunks_document_chunk_uidx UNIQUE (document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw_idx
  ON chunks USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS chunks_tsv_gin_idx
  ON chunks USING gin (tsv);

CREATE INDEX IF NOT EXISTS chunks_visa_class_gin_idx
  ON chunks USING gin (visa_class);

CREATE INDEX IF NOT EXISTS chunks_criterion_tags_gin_idx
  ON chunks USING gin (criterion_tags);

CREATE INDEX IF NOT EXISTS chunks_document_id_idx
  ON chunks (document_id);

CREATE OR REPLACE FUNCTION "extra_update" ("old" JSONB, "set" JSONB, "drop" TEXT[])
    RETURNS JSONB AS $$
        DECLARE "result" JSONB;
        BEGIN
            SELECT jsonb_object_agg("key", "value") INTO "result" FROM (
                SELECT "key", "value" FROM jsonb_each("old" || "set") WHERE NOT ("key" = ANY ("drop"))
            ) "t";
            RETURN COALESCE("result", '{}'::JSONB);
        END
    $$
    LANGUAGE plpgsql
    IMMUTABLE;

CREATE TABLE "priorities" (
    "category" INTEGER NOT NULL,
    "brand" INTEGER NOT NULL,
    "sex" TEXT NOT NULL,
    "status" SMALLINT NOT NULL DEFAULT 0,
    "cache" JSONB NOT NULL DEFAULT '[]'::JSONB,
    "created" TIMESTAMP NOT NULL DEFAULT NOW(),
    "updated" TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT "priorities_pk" PRIMARY KEY ("category", "brand", "sex")
);

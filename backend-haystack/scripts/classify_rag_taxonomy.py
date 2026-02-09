#!/usr/bin/env python3
"""
Classify RAG sources with taxonomy using LLM.

Run from backend-haystack directory:
  python -m scripts.classify_rag_taxonomy [--dry-run] [--limit N] [--force]

Options:
  --dry-run    Preview without saving
  --limit N    Process at most N sources
  --force      Re-classify sources that already have taxonomy
"""

import argparse
import asyncio
import logging
import os
import sys

# Add app to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser(description="Classify RAG sources with taxonomy")
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving")
    parser.add_argument("--limit", type=int, default=0, help="Max sources to process (0=all)")
    parser.add_argument("--force", action="store_true", help="Re-classify even if taxonomy exists")
    args = parser.parse_args()

    # Initialize DB and pipeline (required for generator)
    from app.database import init_db
    from app.rag.pipeline import initialize_pipeline

    await init_db()
    await initialize_pipeline()

    from app.database import async_session
    from app.admin.models import RAGSource, SourceStatus
    from app.rag.metadata_extractor import extract_taxonomy
    from app.rag.pipeline import get_pipeline_manager
    from sqlalchemy import select

    manager = get_pipeline_manager()
    generator = manager.get_generator()

    async with async_session() as db:
        query = select(RAGSource).where(RAGSource.status == SourceStatus.active)
        if not args.force:
            query = query.where(RAGSource.taxonomy.is_(None))
        query = query.order_by(RAGSource.id)
        if args.limit:
            query = query.limit(args.limit)

        result = await db.execute(query)
        sources = list(result.scalars().all())

    if not sources:
        logger.info("No sources to classify")
        return

    logger.info(f"Classifying {len(sources)} sources (dry_run={args.dry_run})")

    for source in sources:
        # Get content snippet
        content_snippet = ""
        if source.content:
            content_snippet = source.content[:2500]
        else:
            from app.rag.indexing import get_source_chunks
            chunks = await asyncio.to_thread(get_source_chunks, source.id, limit=5, offset=0)
            if chunks:
                content_snippet = "\n\n".join((c.content or "")[:500] for c in chunks)

        if not content_snippet.strip():
            logger.warning(f"Source {source.id} ({source.title[:40]}): no content, skipping")
            continue

        try:
            taxonomy = await extract_taxonomy(
                content_snippet=content_snippet,
                url=source.source_url or "",
                title=source.title,
                generator=generator,
            )
        except Exception as e:
            logger.error(f"Source {source.id}: taxonomy extraction failed: {e}")
            continue

        if not taxonomy:
            logger.warning(f"Source {source.id}: no taxonomy extracted")
            continue

        logger.info(f"Source {source.id} ({source.title[:50]}): {list(taxonomy.keys())}")

        if not args.dry_run:
            async with async_session() as db:
                result = await db.execute(select(RAGSource).where(RAGSource.id == source.id))
                s = result.scalar_one_or_none()
                if s:
                    s.taxonomy = taxonomy
                    await db.commit()
                    logger.info(f"Saved taxonomy for source {source.id}")

    logger.info("Done")


if __name__ == "__main__":
    asyncio.run(main())

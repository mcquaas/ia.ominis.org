'use strict';

/**
 * rag-source controller
 */

const { createCoreController } = require('@strapi/strapi').factories;

module.exports = createCoreController('api::rag-source.rag-source', ({ strapi }) => ({
  // Custom action to trigger re-indexing of a source
  async reindex(ctx) {
    const { id } = ctx.params;
    
    try {
      const entity = await strapi.db.query('api::rag-source.rag-source').findOne({
        where: { id },
      });
      
      if (!entity) {
        return ctx.notFound('RAG Source not found');
      }
      
      // Update status to processing
      await strapi.db.query('api::rag-source.rag-source').update({
        where: { id },
        data: {
          status: 'processing',
          indexingError: null,
        },
      });
      
      // TODO: Trigger actual re-indexing process
      // This would call your Python RAG pipeline
      
      return ctx.send({
        message: 'Re-indexing started',
        sourceId: id,
        status: 'processing',
      });
    } catch (error) {
      ctx.throw(500, error);
    }
  },
  
  // Custom action to get indexing statistics
  async stats(ctx) {
    try {
      const total = await strapi.db.query('api::rag-source.rag-source').count();
      const indexed = await strapi.db.query('api::rag-source.rag-source').count({
        where: { status: 'indexed' },
      });
      const pending = await strapi.db.query('api::rag-source.rag-source').count({
        where: { status: 'pending' },
      });
      const processing = await strapi.db.query('api::rag-source.rag-source').count({
        where: { status: 'processing' },
      });
      const failed = await strapi.db.query('api::rag-source.rag-source').count({
        where: { status: 'failed' },
      });
      
      // Get total chunks
      const sources = await strapi.db.query('api::rag-source.rag-source').findMany({
        select: ['chunksCount'],
      });
      const totalChunks = sources.reduce((sum, s) => sum + (s.chunksCount || 0), 0);
      
      return ctx.send({
        total,
        byStatus: {
          indexed,
          pending,
          processing,
          failed,
        },
        totalChunks,
      });
    } catch (error) {
      ctx.throw(500, error);
    }
  },
}));

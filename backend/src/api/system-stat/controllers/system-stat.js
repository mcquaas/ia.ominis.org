'use strict';

/**
 * system-stats controller
 */

const { createCoreController } = require('@strapi/strapi').factories;

module.exports = createCoreController('api::system-stat.system-stat', ({ strapi }) => ({
  // Refresh stats from external sources
  async refresh(ctx) {
    try {
      // Get RAG source stats
      const totalSources = await strapi.db.query('api::rag-source.rag-source').count();
      const indexedSources = await strapi.db.query('api::rag-source.rag-source').count({
        where: { status: 'indexed' },
      });
      
      // Get total chunks
      const sources = await strapi.db.query('api::rag-source.rag-source').findMany({
        select: ['chunksCount'],
      });
      const totalChunks = sources.reduce((sum, s) => sum + (s.chunksCount || 0), 0);
      
      // Get query stats (last 24h, week, month)
      const now = new Date();
      const yesterday = new Date(now - 24 * 60 * 60 * 1000);
      const weekAgo = new Date(now - 7 * 24 * 60 * 60 * 1000);
      const monthAgo = new Date(now - 30 * 24 * 60 * 60 * 1000);
      
      const totalQueries24h = await strapi.db.query('api::query-log.query-log').count({
        where: { createdAt: { $gte: yesterday } },
      });
      
      const totalQueriesWeek = await strapi.db.query('api::query-log.query-log').count({
        where: { createdAt: { $gte: weekAgo } },
      });
      
      const totalQueriesMonth = await strapi.db.query('api::query-log.query-log').count({
        where: { createdAt: { $gte: monthAgo } },
      });
      
      // Calculate error rate
      const errors24h = await strapi.db.query('api::query-log.query-log').count({
        where: { 
          createdAt: { $gte: yesterday },
          success: false,
        },
      });
      const errorRate24h = totalQueries24h > 0 ? (errors24h / totalQueries24h) * 100 : 0;
      
      // Update system stats
      const updated = await strapi.db.query('api::system-stat.system-stat').update({
        data: {
          totalSources,
          indexedSources,
          totalChunks,
          totalQueries24h,
          totalQueriesWeek,
          totalQueriesMonth,
          errorRate24h,
          lastHealthCheck: new Date(),
        },
      });
      
      return ctx.send({
        message: 'Stats refreshed',
        stats: updated,
      });
    } catch (error) {
      ctx.throw(500, error);
    }
  },
  
  // Health check endpoint
  async health(ctx) {
    try {
      const stats = await strapi.db.query('api::system-stat.system-stat').findOne({});
      
      return ctx.send({
        status: 'ok',
        timestamp: new Date().toISOString(),
        model: {
          version: stats?.modelVersion || 'ominis-2.0',
          status: stats?.modelStatus || 'unknown',
        },
        servers: {
          cpu: stats?.cpuServerStatus || 'unknown',
          gpu: stats?.gpuServerStatus || 'unknown',
        },
        lastCheck: stats?.lastHealthCheck,
      });
    } catch (error) {
      ctx.throw(500, error);
    }
  },
}));

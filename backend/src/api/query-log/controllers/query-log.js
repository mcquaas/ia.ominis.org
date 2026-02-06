'use strict';

/**
 * query-log controller
 */

const { createCoreController } = require('@strapi/strapi').factories;

module.exports = createCoreController('api::query-log.query-log', ({ strapi }) => ({
  // Get aggregated stats
  async aggregated(ctx) {
    const { period = 'day' } = ctx.query;
    
    try {
      const now = new Date();
      let startDate;
      
      switch (period) {
        case 'hour':
          startDate = new Date(now - 60 * 60 * 1000);
          break;
        case 'day':
          startDate = new Date(now - 24 * 60 * 60 * 1000);
          break;
        case 'week':
          startDate = new Date(now - 7 * 24 * 60 * 60 * 1000);
          break;
        case 'month':
          startDate = new Date(now - 30 * 24 * 60 * 60 * 1000);
          break;
        default:
          startDate = new Date(now - 24 * 60 * 60 * 1000);
      }
      
      const logs = await strapi.db.query('api::query-log.query-log').findMany({
        where: { createdAt: { $gte: startDate } },
      });
      
      const total = logs.length;
      const successful = logs.filter(l => l.success).length;
      const failed = total - successful;
      
      const avgResponseTime = total > 0 
        ? logs.reduce((sum, l) => sum + (l.responseTimeMs || 0), 0) / total 
        : 0;
      
      const totalTokens = logs.reduce((sum, l) => sum + (l.tokensGenerated || 0), 0);
      
      const byEndpoint = {
        query: logs.filter(l => l.endpoint === 'query').length,
        'query-gpu': logs.filter(l => l.endpoint === 'query-gpu').length,
      };
      
      return ctx.send({
        period,
        startDate,
        endDate: now,
        total,
        successful,
        failed,
        successRate: total > 0 ? (successful / total) * 100 : 0,
        avgResponseTimeMs: Math.round(avgResponseTime),
        totalTokens,
        byEndpoint,
      });
    } catch (error) {
      ctx.throw(500, error);
    }
  },
}));

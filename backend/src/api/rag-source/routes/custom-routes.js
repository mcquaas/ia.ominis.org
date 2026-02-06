'use strict';

/**
 * Custom routes for rag-source
 */

module.exports = {
  routes: [
    {
      method: 'POST',
      path: '/rag-sources/:id/reindex',
      handler: 'rag-source.reindex',
      config: {
        policies: [],
        middlewares: [],
      },
    },
    {
      method: 'GET',
      path: '/rag-sources/stats',
      handler: 'rag-source.stats',
      config: {
        policies: [],
        middlewares: [],
      },
    },
  ],
};

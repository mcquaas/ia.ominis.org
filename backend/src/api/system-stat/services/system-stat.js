'use strict';

/**
 * system-stats service
 */

const { createCoreService } = require('@strapi/strapi').factories;

module.exports = createCoreService('api::system-stat.system-stat');

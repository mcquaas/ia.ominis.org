'use strict';

/**
 * api-key service
 */

const { createCoreService } = require('@strapi/strapi').factories;

module.exports = createCoreService('api::api-key.api-key');
